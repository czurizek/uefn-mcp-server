"""Test suite for the fngg island analytics package.

Runs entirely offline against synthetic fixtures - no network, no live API.

    python -m unittest discover -s tests -v
    python tests/test_fngg.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point every test at a throwaway database before importing anything that reads config.
_TMP = tempfile.mkdtemp(prefix="fngg-test-")
os.environ["FNGG_HOME"] = _TMP
os.environ["FNGG_DB"] = str(Path(_TMP) / "test.sqlite3")

from fngg import genres, seed, store  # noqa: E402
from fngg.analytics import build_dataset  # noqa: E402
from fngg.analytics.cohort import Cohorts, percentile_of  # noqa: E402
from fngg.analytics.discovery import row_fit, score_discovery, weights_for  # noqa: E402
from fngg.analytics.kpis import derive_kpis, format_kpi  # noqa: E402
from fngg.analytics.movers import composite_growth, compute_momentum, linear_slope  # noqa: E402
from fngg.sources import ecosystem, fortnitegg  # noqa: E402
from fngg.sources.ecosystem import Island, MetricReading  # noqa: E402


def iso(days_ago: int) -> str:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return when.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


# ---------------------------------------------------------------- ecosystem


class TestEcosystemParsing(unittest.TestCase):
    """Epic returns a time series with only the newest bucket populated."""

    def test_reduces_to_latest_non_null(self):
        payload = {
            "uniquePlayers": [
                {"timestamp": "2026-08-19T00:00:00Z", "value": None},
                {"timestamp": "2026-08-20T00:00:00Z", "value": None},
                {"timestamp": "2026-08-21T00:00:00Z", "value": 4200},
            ],
            "peakCCU": [{"timestamp": "2026-08-21T00:00:00Z", "value": 310}],
        }
        reading = ecosystem.reading_from_payload("1-2-3", "day", payload)
        self.assertIsNotNone(reading)
        self.assertEqual(reading.unique_players, 4200.0)
        self.assertEqual(reading.peak_ccu, 310.0)
        self.assertEqual(reading.captured_at, "2026-08-21T00:00:00Z")

    def test_retention_uses_d1_d7_shape(self):
        payload = {
            "retention": [
                {"timestamp": "2026-08-20T00:00:00Z", "d1": None, "d7": None},
                {"timestamp": "2026-08-21T00:00:00Z", "d1": 0.28, "d7": 0.11},
            ]
        }
        reading = ecosystem.reading_from_payload("1-2-3", "day", payload)
        self.assertAlmostEqual(reading.retention_d1, 0.28)
        self.assertAlmostEqual(reading.retention_d7, 0.11)

    def test_all_null_payload_yields_nothing(self):
        payload = {"uniquePlayers": [{"timestamp": "t", "value": None}]}
        self.assertIsNone(ecosystem.reading_from_payload("1-2-3", "day", payload))

    def test_accepts_data_wrapped_payload(self):
        payload = {"data": {"plays": [{"timestamp": "2026-08-21T00:00:00Z", "value": 90}]}}
        reading = ecosystem.reading_from_payload("1-2-3", "day", payload)
        self.assertEqual(reading.plays, 90.0)

    def test_full_series_keeps_every_populated_bucket(self):
        payload = {
            "uniquePlayers": [
                {"timestamp": "2026-08-20T00:00:00Z", "value": 100},
                {"timestamp": "2026-08-21T00:00:00Z", "value": 120},
            ]
        }
        readings = ecosystem.readings_from_payload("1-2-3", "day", payload)
        self.assertEqual([r.unique_players for r in readings], [100.0, 120.0])

    def test_rejects_unknown_interval(self):
        with self.assertRaises(ValueError):
            ecosystem.fetch_metrics_raw("1-2-3", "fortnight")

    def test_island_from_api_tolerates_missing_fields(self):
        island = Island.from_api({"code": "1-2-3"})
        self.assertEqual(island.tags, [])
        self.assertIsNone(island.title)


# -------------------------------------------------------------------- store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "s.sqlite3"
        self.conn = store.connect(self.path)
        store.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _reading(self, code="1-2-3", when="2026-08-21T00:00:00Z", players=100):
        return MetricReading(
            code=code, interval="day", captured_at=when, unique_players=players, peak_ccu=10
        )

    def test_snapshot_dedup_on_captured_at(self):
        reading = self._reading()
        self.assertTrue(store.insert_snapshot(self.conn, reading))
        self.assertFalse(store.insert_snapshot(self.conn, reading))
        self.assertEqual(store.snapshot_count(self.conn), 1)

    def test_upsert_preserves_existing_fields_on_partial_update(self):
        store.upsert_island(self.conn, Island(code="1-2-3", title="Original", tags=["Roleplay"]))
        store.upsert_island(self.conn, Island(code="1-2-3"))
        row = store.row_to_dict(store.get_island(self.conn, "1-2-3"))
        self.assertEqual(row["title"], "Original")
        self.assertEqual(row["tags"], ["Roleplay"])

    def test_latest_rows_returns_newest_snapshot_per_island(self):
        store.upsert_island(self.conn, Island(code="1-2-3", title="X"))
        store.insert_snapshot(self.conn, self._reading(when=iso(3), players=50))
        store.insert_snapshot(self.conn, self._reading(when=iso(1), players=90))
        rows = store.latest_rows(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unique_players"], 90.0)

    def test_tracked_islands_are_polled_first(self):
        for code in ("1-1-1", "2-2-2", "3-3-3"):
            store.upsert_island(self.conn, Island(code=code))
        store.set_tracked(self.conn, "3-3-3", True)
        self.assertEqual(store.poll_candidates(self.conn)[0], "3-3-3")

    def test_long_missing_islands_drop_out_of_rotation(self):
        store.upsert_island(self.conn, Island(code="1-1-1"))
        self.conn.execute(
            "UPDATE islands SET missing_since=? WHERE code=?", (iso(40), "1-1-1")
        )
        self.assertNotIn("1-1-1", store.poll_candidates(self.conn))

    def test_mark_polled_clears_missing_flag(self):
        store.upsert_island(self.conn, Island(code="1-1-1"))
        store.mark_missing(self.conn, "1-1-1")
        self.assertIsNotNone(store.get_island(self.conn, "1-1-1")["missing_since"])
        store.mark_polled(self.conn, "1-1-1")
        self.assertIsNone(store.get_island(self.conn, "1-1-1")["missing_since"])

    def test_parse_ts_handles_z_suffix_and_naive(self):
        self.assertIsNotNone(store.parse_ts("2026-08-21T00:00:00Z"))
        self.assertIsNotNone(store.parse_ts("2026-08-21T00:00:00"))
        self.assertIsNone(store.parse_ts(None))
        self.assertIsNone(store.parse_ts("not a date"))

    def test_placements_are_unique_per_row_and_observation(self):
        self.assertTrue(store.insert_placement(self.conn, "1-2-3", iso(0), "popular"))
        self.assertFalse(store.insert_placement(self.conn, "1-2-3", iso(0), "popular"))


# ------------------------------------------------------------------ genres


class TestGenres(unittest.TestCase):
    def test_classifies_the_three_focus_genres(self):
        self.assertEqual(genres.classify("Los Angeles City RP", ["Roleplay"]).genre, genres.RP)
        self.assertEqual(genres.classify("Neon FFA Arena", ["Deathmatch"]).genre, genres.FFA)
        self.assertEqual(
            genres.classify("Frostlands Open World Survival", ["Open World"]).genre,
            genres.OPEN_WORLD,
        )

    def test_rp_token_respects_word_boundaries(self):
        # "corporate" contains "rp" but must not classify as roleplay.
        self.assertNotEqual(genres.classify("Corporate Ladder Simulator").genre, genres.RP)

    def test_override_wins_over_keywords(self):
        result = genres.classify("Neon FFA Arena", ["Deathmatch"], override=genres.RP)
        self.assertEqual(result.genre, genres.RP)
        self.assertEqual(result.source, "override")
        self.assertEqual(result.confidence, 1.0)

    def test_behaviour_fallback_when_text_says_nothing(self):
        long_session = genres.classify(
            "MY MAP v2", average_minutes_per_player=95, retention_d1=0.3
        )
        self.assertEqual(long_session.source, "behaviour")
        self.assertEqual(genres.family_of(long_session.genre), genres.LONG_FORM)

        short_loop = genres.classify(
            "MY MAP v2", average_minutes_per_player=7, plays=400, unique_players=100
        )
        self.assertEqual(genres.family_of(short_loop.genre), genres.SHORT_LOOP)

    def test_unclassifiable_falls_back_to_other(self):
        result = genres.classify("zzz")
        self.assertEqual(result.genre, genres.OTHER)
        self.assertEqual(result.source, "unknown")

    def test_ambiguous_titles_get_lower_confidence(self):
        clear = genres.classify("Open World Survival Sandbox", ["Open World"])
        mixed = genres.classify("Roleplay Tycoon")
        self.assertGreater(clear.confidence, mixed.confidence)

    def test_families_split_rp_and_ffa(self):
        self.assertEqual(genres.family_of(genres.RP), genres.LONG_FORM)
        self.assertEqual(genres.family_of(genres.FFA), genres.SHORT_LOOP)


# -------------------------------------------------------------------- kpis


class TestKPIs(unittest.TestCase):
    def test_derives_ratios(self):
        kpis = derive_kpis(
            {
                "unique_players": 1000,
                "minutes_played": 60000,
                "plays": 2000,
                "favorites": 50,
                "peak_ccu": 100,
                "recommendations": 10,
            }
        )
        self.assertAlmostEqual(kpis["minutes_per_player"], 60.0)
        self.assertAlmostEqual(kpis["minutes_per_play"], 30.0)
        self.assertAlmostEqual(kpis["replays_per_player"], 2.0)
        self.assertAlmostEqual(kpis["favorites_rate"], 0.05)
        self.assertAlmostEqual(kpis["player_hours"], 1000.0)

    def test_prefers_epics_average_minutes_field(self):
        kpis = derive_kpis(
            {"unique_players": 1000, "minutes_played": 60000, "average_minutes_per_player": 88.0}
        )
        self.assertAlmostEqual(kpis["minutes_per_player"], 88.0)

    def test_retention_normalised_from_percent_or_fraction(self):
        self.assertAlmostEqual(derive_kpis({"retention_d1": 31.0})["retention_d1"], 0.31)
        self.assertAlmostEqual(derive_kpis({"retention_d1": 0.31})["retention_d1"], 0.31)

    def test_missing_inputs_yield_none_not_zero(self):
        kpis = derive_kpis({"unique_players": None, "plays": 5})
        self.assertIsNone(kpis["replays_per_player"])
        self.assertIsNone(kpis["minutes_per_player"])

    def test_division_by_zero_is_none(self):
        self.assertIsNone(derive_kpis({"plays": 0, "minutes_played": 10})["minutes_per_play"])

    def test_formatting(self):
        self.assertEqual(format_kpi("retention_d1", 0.312), "31.2%")
        self.assertEqual(format_kpi("unique_players", 42000), "42.0K")
        self.assertEqual(format_kpi("unique_players", None), "–")


# ------------------------------------------------------------------ cohorts


class TestCohorts(unittest.TestCase):
    def test_percentile_rank_counts_ties_as_half(self):
        values = [1, 2, 2, 2, 3]
        self.assertAlmostEqual(percentile_of(values, 2), 50.0)
        self.assertEqual(percentile_of(values, 0), 0.0)
        self.assertIsNone(percentile_of(values, None))
        self.assertIsNone(percentile_of([], 5))

    def test_thin_cohort_falls_back_to_family_then_global(self):
        rows = [{"genre": genres.RP, "unique_players": 10}]  # 1 island: below MIN_COHORT
        rows += [{"genre": genres.TYCOON, "unique_players": i} for i in range(20)]
        cohorts = Cohorts(rows, ("unique_players",))
        # rp has 1 member, and its family (long_form) has 21 including the tycoons.
        self.assertEqual(cohorts.resolve_key(genres.RP, "unique_players"), "family:long_form")

    def test_blended_percentile_renormalises_over_present_metrics(self):
        rows = [{"genre": genres.RP, "a": i, "b": i} for i in range(20)]
        cohorts = Cohorts(rows, ("a", "b"))
        both = cohorts.blended_percentile(genres.RP, {"a": 10, "b": 10}, {"a": 0.5, "b": 0.5})
        one = cohorts.blended_percentile(genres.RP, {"a": 10, "b": None}, {"a": 0.5, "b": 0.5})
        self.assertAlmostEqual(both, one)  # a missing metric must not drag the score down

    def test_quantiles_are_ordered(self):
        rows = [{"genre": genres.FFA, "unique_players": i} for i in range(100)]
        stats = Cohorts(rows, ("unique_players",)).stats(genres.FFA, "unique_players")
        self.assertLess(stats.quantile(10), stats.quantile(50))
        self.assertLess(stats.quantile(50), stats.quantile(90))


# ---------------------------------------------------------------- discovery


class TestDiscovery(unittest.TestCase):
    def _cohorts(self):
        rows = []
        for i in range(30):
            rows.append(
                {
                    "genre": genres.RP,
                    "unique_players": i * 100,
                    "peak_ccu": i * 10,
                    "retention_d1": 0.1 + i * 0.005,
                    "retention_d7": 0.05 + i * 0.002,
                    "d7_over_d1": 0.4,
                    "minutes_per_player": 40 + i,
                    "minutes_per_play": 30 + i,
                    "replays_per_player": 1.2,
                    "favorites_rate": 0.02 + i * 0.001,
                    "recommend_rate": 0.01,
                    "composite_growth": i * 0.01,
                }
            )
        from fngg.analytics.dataset import COHORT_METRICS

        return rows, Cohorts(rows, COHORT_METRICS)

    def test_genre_weighting_differs_between_rp_and_ffa(self):
        rp = weights_for(genres.RP)
        ffa = weights_for(genres.FFA)
        # RP is retention-led, FFA is scale-led. That difference is the whole point.
        self.assertGreater(rp["retention"], rp["scale"])
        self.assertGreater(ffa["scale"], ffa["retention"])
        self.assertAlmostEqual(sum(rp.values()), 1.0, places=6)
        self.assertAlmostEqual(sum(ffa.values()), 1.0, places=6)

    def test_score_is_bounded_and_ordered_by_strength(self):
        rows, cohorts = self._cohorts()
        weak = score_discovery(rows[1], cohorts, momentum_percentile=10)
        strong = score_discovery(rows[-1], cohorts, momentum_percentile=90)
        self.assertGreater(strong.score, weak.score)
        for result in (weak, strong):
            self.assertGreaterEqual(result.score, 0)
            self.assertLessEqual(result.score, 100)

    def test_missing_momentum_does_not_void_the_score(self):
        rows, cohorts = self._cohorts()
        result = score_discovery(rows[10], cohorts, momentum_percentile=None)
        self.assertIsNotNone(result.score)
        self.assertIn("momentum", result.missing)
        self.assertLess(result.data_completeness, 1.0)

    def test_levers_rank_by_weighted_upside(self):
        rows, cohorts = self._cohorts()
        result = score_discovery(rows[2], cohorts, momentum_percentile=95)
        levers = result.levers
        self.assertEqual(levers, sorted(levers, key=lambda l: -l["upside"]))
        # A component already above the target has no upside.
        for lever in levers:
            if lever["percentile"] >= 75:
                self.assertEqual(lever["upside"], 0.0)

    def test_curated_rows_are_never_scored(self):
        rows, cohorts = self._cohorts()
        result = score_discovery(rows[-1], cohorts, momentum_percentile=80)
        curated = [e for e in row_fit(result) if e["curated"]]
        self.assertTrue(curated)
        for entry in curated:
            self.assertIsNone(entry["fit"])
            self.assertFalse(entry["eligible"])

    def test_new_releases_closes_after_its_window(self):
        rows, cohorts = self._cohorts()
        result = score_discovery(rows[-1], cohorts, momentum_percentile=80)
        fresh = {e["key"]: e for e in row_fit(result, age_days=5)}["new_releases"]
        stale = {e["key"]: e for e in row_fit(result, age_days=200)}["new_releases"]
        self.assertTrue(fresh["eligible"])
        self.assertFalse(stale["eligible"])

    def test_score_carries_caveats(self):
        rows, cohorts = self._cohorts()
        result = score_discovery(rows[5], cohorts, momentum_percentile=50)
        self.assertTrue(result.caveats)
        self.assertTrue(any("not Epic's actual ranking" in c for c in result.caveats))


# ------------------------------------------------------------------ momentum


class TestMomentum(unittest.TestCase):
    def _series(self, values):
        return [
            {"captured_at": iso(len(values) - i - 1), "unique_players": v}
            for i, v in enumerate(values)
        ]

    def test_growth_and_direction(self):
        result = compute_momentum(self._series([100, 110, 130, 160]), "unique_players")
        self.assertAlmostEqual(result.change_pct, 0.6, places=3)
        self.assertEqual(result.direction, "surging")
        self.assertTrue(result.reliable)

    def test_decline_is_reported_as_such(self):
        result = compute_momentum(self._series([200, 150, 120, 90]), "unique_players")
        self.assertLess(result.change_pct, 0)
        self.assertEqual(result.direction, "collapsing")

    def test_single_reading_is_not_reliable(self):
        result = compute_momentum(self._series([100]), "unique_players")
        self.assertIsNone(result.change_pct)
        self.assertEqual(result.direction, "unknown")
        self.assertFalse(result.reliable)

    def test_empty_series_is_safe(self):
        result = compute_momentum([], "unique_players")
        self.assertIsNone(result.latest)
        self.assertFalse(result.reliable)

    def test_slope_direction(self):
        rising = self._series([10, 20, 30, 40])
        points = [(store.parse_ts(r["captured_at"]), r["unique_players"]) for r in rising]
        self.assertGreater(linear_slope(points), 0)

    def test_composite_growth_compresses_extremes(self):
        modest = composite_growth(self._series([100, 120]))   # +20%
        wild = composite_growth(self._series([3, 300]))       # +9900%
        self.assertGreater(wild, modest)
        # Log compression must stop a tiny island going 3 -> 300 from swamping the
        # cohort's percentile scale: the raw growth ratio is ~495x, the scored gap
        # must come out far smaller than that.
        raw_ratio = 99.0 / 0.2
        self.assertLess(wild / modest, raw_ratio / 10)

    def test_volatility_needs_three_points(self):
        self.assertIsNone(compute_momentum(self._series([100, 110]), "unique_players").volatility)
        self.assertIsNotNone(
            compute_momentum(self._series([100, 140, 90, 130]), "unique_players").volatility
        )


# ---------------------------------------------------------------- fortnitegg


class TestFortniteGG(unittest.TestCase):
    HTML = """
    <html><body>
      <h2>Epic's Picks</h2>
      <div data-x='{"code":"1111-2222-3333","title":"RP City","players":"12.3K","peak":"18,400"}'>
        1111-2222-3333</div>
      <div>2222-3333-4444</div>
      <h2>Popular</h2>
      <div>3333-4444-5555</div>
      <script>var maps=[{"code":"9999-8888-7777","name":"FFA","ccu":842,"rank":17}];</script>
    </body></html>
    """

    def test_number_parsing(self):
        self.assertEqual(fortnitegg.parse_number("12.3K"), 12300.0)
        self.assertEqual(fortnitegg.parse_number("18,400"), 18400.0)
        self.assertEqual(fortnitegg.parse_number("1.2M"), 1_200_000.0)
        self.assertEqual(fortnitegg.parse_number(842), 842.0)
        self.assertIsNone(fortnitegg.parse_number(None))
        self.assertIsNone(fortnitegg.parse_number("n/a"))

    def test_extracts_islands_from_embedded_json(self):
        found = {i.code: i for i in fortnitegg.parse_islands_from_html(self.HTML)}
        self.assertIn("1111-2222-3333", found)
        self.assertEqual(found["1111-2222-3333"].ccu, 12300.0)
        self.assertEqual(found["9999-8888-7777"].rank_overall, 17)

    def test_pairs_codes_with_nearest_preceding_row_heading(self):
        rows = fortnitegg.parse_discovery_rows(self.HTML)
        by_row = {}
        for entry in rows:
            by_row.setdefault(entry.row_key, []).append(entry.code)
        self.assertEqual(by_row["epic_s_picks"], ["1111-2222-3333", "2222-3333-4444"])
        self.assertEqual(by_row["popular"], ["3333-4444-5555"])

    def test_malformed_html_does_not_raise(self):
        self.assertEqual(fortnitegg.parse_islands_from_html("<div><span>oops"), [])
        self.assertEqual(fortnitegg.parse_discovery_rows(""), [])

    def test_ignores_records_without_a_valid_island_code(self):
        html = '<script>var x={"code":"not-a-code","players":10};</script>'
        self.assertEqual(fortnitegg.parse_islands_from_html(html), [])

    # A page as a real listing serves it: codes live in href attributes, and only
    # the hero tile carries embedded JSON.
    REAL_SHAPED = """
    <html><body>
      <h2>Epic's Picks</h2>
      <div data-map='{"code":"1865-4829-7018","title":"Tokyo City RP","players":12934,"peak":18402}'>
        <a href="/island?code=1865-4829-7018">Tokyo City RP</a><span>12,934 players</span></div>
      <div><a href="/island?code=4021-9987-1122">Neon FFA</a><span>3.1K players</span></div>
      <h2>Popular</h2>
      <div><a href="/island?code=7788-1234-9090">Frostlands</a><span>842 players</span></div>
    </body></html>
    """

    def test_finds_codes_that_only_exist_in_href_attributes(self):
        found = {i.code for i in fortnitegg.parse_islands_from_html(self.REAL_SHAPED)}
        self.assertEqual(found, {"1865-4829-7018", "4021-9987-1122", "7788-1234-9090"})

    def test_markup_scan_supplements_embedded_json(self):
        # One tile has JSON, the rest are plain HTML. Treating the JSON as the
        # complete answer would silently drop almost the whole page.
        islands = {i.code: i for i in fortnitegg.parse_islands_from_html(self.REAL_SHAPED)}
        self.assertEqual(islands["1865-4829-7018"].peak_24h, 18402.0)   # from JSON
        self.assertEqual(islands["4021-9987-1122"].ccu, 3100.0)         # from markup

    def test_discovery_rows_read_codes_from_hrefs(self):
        rows = fortnitegg.parse_discovery_rows(self.REAL_SHAPED)
        by_row = {}
        for entry in rows:
            by_row.setdefault(entry.row_key, []).append(entry.code)
        self.assertEqual(by_row["epic_s_picks"], ["1865-4829-7018", "4021-9987-1122"])
        self.assertEqual(by_row["popular"], ["7788-1234-9090"])

    def test_duplicate_code_in_one_tile_does_not_shift_positions(self):
        rows = fortnitegg.parse_discovery_rows(self.REAL_SHAPED)
        picks = [r for r in rows if r.row_key == "epic_s_picks"]
        # The hero tile names its code twice (data attribute + href).
        self.assertEqual([r.position for r in picks], [1, 2])

    def test_same_island_may_appear_in_two_rows(self):
        html = """
        <h2>Epic's Picks</h2><div><a href="/island?code=1111-2222-3333">A</a></div>
        <h2>Popular</h2><div><a href="/island?code=1111-2222-3333">A</a></div>
        """
        rows = fortnitegg.parse_discovery_rows(html)
        self.assertEqual({r.row_key for r in rows}, {"epic_s_picks", "popular"})

    def test_capture_reports_endpoints_and_parser_state(self):
        captured = {}

        def fake_get_text(url, **kwargs):
            captured[url] = True
            if url.endswith(".js"):
                return 'fetch("/api/v2/island-stats.json?code="+c);'
            return (
                self.REAL_SHAPED
                + '<script src="/js/app.js"></script>'
                + '<script>var C="/api/chart-data.php?id=1&range=30d";</script>'
            )

        original = fortnitegg.get_text
        fortnitegg.get_text = fake_get_text
        try:
            bundle = fortnitegg.capture(sample_code="1865-4829-7018", fetch_scripts=True)
        finally:
            fortnitegg.get_text = original

        page = bundle["pages"]["browse"]
        self.assertEqual(page["island_codes_found"], 3)
        self.assertIn("/api/chart-data.php?id=1&range=30d", page["data_urls_in_markup"])
        self.assertTrue(page["embedded_json"])
        self.assertEqual(page["current_parser_count"], 3)
        # Script scanning is where a site's real JSON API usually surfaces.
        scanned = [u for entry in page["script_scan"] for u in entry.get("data_urls", [])]
        self.assertTrue(any("island-stats.json" in u for u in scanned))

    def test_capture_survives_an_unreachable_site(self):
        def boom(url, **kwargs):
            raise fortnitegg.HttpError("network error")

        original = fortnitegg.get_text
        fortnitegg.get_text = boom
        try:
            bundle = fortnitegg.capture()
        finally:
            fortnitegg.get_text = original
        for page in bundle["pages"].values():
            self.assertIsNone(page["resolved_url"])
            self.assertTrue(page["attempts"])

    def test_strategies_include_the_three_kinds(self):
        strategies = fortnitegg.load_strategies()
        for kind in ("island", "browse", "discovery"):
            self.assertTrue(strategies.get(kind))


# ------------------------------------------------------------- end to end


class TestDatasetEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(tempfile.mkdtemp()) / "e2e.sqlite3"
        cls.conn = store.connect(cls.path)
        store.init_db(cls.conn)
        seed.load_into(cls.conn, count=90, days=14, seed=7)
        cls.dataset = build_dataset(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_every_island_is_classified_and_scored(self):
        self.assertGreater(len(self.dataset), 0)
        for row in self.dataset.rows:
            self.assertIsNotNone(row["genre"])
            self.assertIsNotNone(row["discovery_score"])
            self.assertGreaterEqual(row["discovery_score"], 0)
            self.assertLessEqual(row["discovery_score"], 100)

    def test_focus_genres_are_present_in_the_sample(self):
        found = {row["genre"] for row in self.dataset.rows}
        for genre in genres.FOCUS_GENRES:
            self.assertIn(genre, found, f"{genre} missing from generated sample")

    def test_rows_sorted_by_fitness(self):
        scores = [r["discovery_score"] for r in self.dataset.rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_cohort_ranks_are_dense_and_start_at_one(self):
        for genre in {r["genre"] for r in self.dataset.rows}:
            peers = [r for r in self.dataset.rows if r["genre"] == genre]
            ranks = sorted(r["genre_rank"] for r in peers if r.get("genre_rank"))
            self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_filters(self):
        rp_only = self.dataset.filter(genre=genres.RP)
        self.assertTrue(rp_only)
        self.assertTrue(all(r["genre"] == genres.RP for r in rp_only))
        self.assertTrue(self.dataset.filter(query="roleplay"))
        self.assertEqual(self.dataset.filter(min_players=10**9), [])

    def test_movers_returns_both_directions(self):
        self.assertTrue(self.dataset.movers(rising=True, min_players=0))
        self.assertTrue(self.dataset.movers(rising=False, min_players=0))

    def test_summary_shape(self):
        summary = self.dataset.summary()
        for key in ("islands", "scored", "with_history", "history_days", "genres"):
            self.assertIn(key, summary)

    def test_report_round_trip(self):
        from fngg.report import format_island_report, island_report

        code = self.dataset.rows[0]["code"]
        data = island_report(self.dataset, code)
        self.assertIsNotNone(data)
        text = format_island_report(data)
        self.assertIn("DISCOVERY FITNESS", text)
        self.assertIn(code, text)
        self.assertIsNone(island_report(self.dataset, "0000-0000-0000"))


class TestEmptyDatabase(unittest.TestCase):
    """A fresh install has nothing in it. Nothing may crash on that path."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "empty.sqlite3"
        self.conn = store.connect(self.path)
        store.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_dataset_on_empty_db(self):
        dataset = build_dataset(self.conn)
        self.assertEqual(len(dataset), 0)
        self.assertEqual(dataset.summary()["islands"], 0)
        self.assertTrue(dataset.warnings)  # must say why it is empty
        self.assertEqual(dataset.movers(), [])
        self.assertIsNone(dataset.get("1-2-3"))

    def test_stats_on_empty_db(self):
        stats = store.stats(self.conn)
        self.assertEqual(stats["islands"], 0)
        self.assertEqual(stats["history_days"], 0.0)


# -------------------------------------------------------------------- web


class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(tempfile.mkdtemp()) / "web.sqlite3"
        cls.conn = store.connect(cls.path)
        store.init_db(cls.conn)
        seed.load_into(cls.conn, count=60, days=10, seed=11)
        cls.dataset = build_dataset(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_every_page_renders(self):
        from fngg.web import render

        pages = (
            render.page_discovery,
            render.page_browse,
            render.page_movers,
            render.page_retention,
            render.page_engagement,
            render.page_cohorts,
            render.page_compare,
        )
        for page in pages:
            html = page(self.dataset, {})
            self.assertIn("<section", html, f"{page.__name__} produced no content")
            self.assertNotIn("None", html, f"{page.__name__} leaked a literal None")

    def test_island_page_renders(self):
        from fngg.web import render

        row = self.dataset.rows[0]
        history = [dict(r) for r in store.snapshot_series(self.conn, row["code"], "day")]
        for record in history:
            record.update(derive_kpis(record))
        html = render.page_island(self.dataset, row, history, None, [])
        self.assertIn("DISCOVER", html.upper())
        self.assertIn(row["code"], html)

    def test_layout_escapes_untrusted_titles(self):
        from fngg.web import render

        html = render.layout(title='<script>alert(1)</script>', active="", body="")
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_charts_handle_degenerate_input(self):
        from fngg.web import charts

        self.assertIn("svg", charts.sparkline([]))
        self.assertIn("chart-empty", charts.line_chart([]))
        self.assertIn("chart-empty", charts.scatter([]))
        self.assertIn("–", charts.percentile_bar(None))
        self.assertIn("empty", charts.score_dial(None))

    def test_axis_bounds_never_go_negative_for_positive_data(self):
        from fngg.web.charts import _nice_bounds

        lo, _ = _nice_bounds([1.0, 2.0, 3.0])
        self.assertGreaterEqual(lo, 0.0)


class TestCLIParsing(unittest.TestCase):
    def test_subcommands_parse(self):
        from fngg.cli import build_parser

        parser = build_parser()
        self.assertEqual(parser.parse_args(["poll", "--interval", "hour"]).interval, "hour")
        self.assertTrue(parser.parse_args(["track", "1-2-3", "4-5-6"]).codes)
        self.assertEqual(parser.parse_args(["report", "1-2-3"]).code, "1-2-3")
        self.assertEqual(parser.parse_args(["serve", "--port", "9000"]).port, 9000)

    def test_invalid_interval_rejected(self):
        from fngg.cli import build_parser

        with self.assertRaises(SystemExit):
            build_parser().parse_args(["poll", "--interval", "fortnight"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
