# fngg — island browsing and Discovery analytics

A local app for browsing Fortnite islands and analysing why they do or do not
surface in Discover, with the analytics tuned for **RP, FFA and open-world** maps.

Runs on nothing but CPython — no pip installs, no build step, no account.

```
fngg demo      # sample data, so you can look around right now
fngg serve     # dashboard at http://127.0.0.1:8770
```

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Where the data comes from](#where-the-data-comes-from)
- [The thing that shapes everything: no backfill](#the-thing-that-shapes-everything-no-backfill)
- [Discovery Fitness](#discovery-fitness)
- [Discover row fit](#discover-row-fit)
- [Genres and cohorts](#genres-and-cohorts)
- [Dashboard tabs](#dashboard-tabs)
- [CLI reference](#cli-reference)
- [MCP tools](#mcp-tools)
- [The fortnite.gg adapter](#the-fortnitegg-adapter)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## What it does

Epic gives every creator seven raw counters for their own island and nothing at
all for anyone else's. That is enough to know how big you are and not enough to
know whether that is good, what is holding you back, or who is beating you.

fngg answers three questions the raw numbers cannot:

1. **Is this number good?** Every metric is reported as a percentile inside a
   cohort of comparable islands. A 14% day-7 retention is weak for an RP city and
   excellent for a box-fight map — the same number, two opposite verdicts.
2. **What should I fix first?** The Discovery model ranks your weaknesses by how
   many points each one is actually worth for *your* genre, so effort goes where
   it pays.
3. **Which Discover row am I built for?** The Discover surface is a stack of rows
   that reward different things. An island can be a lock for Community Choice and
   invisible in Trending at the same time.

---

## Quick start

### Look around immediately

```bash
python -m fngg demo      # 140 synthetic islands with 21 days of history
python -m fngg serve     # http://127.0.0.1:8770
```

The demo data is synthetic but shaped from how these formats really behave — RP
sessions in the 45–140 minute band, FFA in the 6–22 band, retention distributions
to match. It exists so the interface is explorable on day one, when a real
database is necessarily empty.

### Real data

```bash
python -m fngg sync --limit 2000      # pull Epic's island catalogue
python -m fngg poll                   # take one reading per island
python -m fngg serve
```

Then keep history accumulating. This is the important part:

```bash
python -m fngg watch --every 360      # poll every 6 hours, ctrl-c to stop
```

Or as a daily cron / Task Scheduler entry:

```
0 4 * * *  cd /path/to/uefn-mcp-server && python -m fngg poll
```

### Track your own islands

```bash
python -m fngg track 1234-5678-9012 2345-6789-0123
python -m fngg poll --tracked
python -m fngg report 1234-5678-9012
```

Tracked islands are polled first on every run, so they keep a complete history
even when a large catalogue sync is running behind them.

---

## Where the data comes from

**Epic's Fortnite Ecosystem API** — `https://api.fortnite.com/ecosystem/v1`,
public, no authentication, covers every island that is public and discoverable.

| Endpoint | What it gives |
|---|---|
| `GET /islands` | Cursor-paginated catalogue (~100/page, `?after=<cursor>`) |
| `GET /islands/{code}` | Title, creator code, category, tags, creation date |
| `GET /islands/{code}/metrics/{day\|hour\|minute}` | The seven metric series plus retention |

Metrics available: `uniquePlayers`, `peakCCU`, `minutesPlayed`,
`averageMinutesPerPlayer`, `plays`, `favorites`, `recommendations`, and
`retention` (as `d1` / `d7`).

**fortnite.gg** — optional, for live concurrency and observed Discover row
placements. See [the adapter section](#the-fortnitegg-adapter).

---

## The thing that shapes everything: no backfill

Epic's metrics endpoint looks like a time series. It is not one.

Every bucket in every series comes back `null` except the single most recent
populated one, and `from` values older than roughly six days are rejected
outright. So one call gives you *one* reading per metric — a live snapshot in the
shape of a history.

**A day you did not poll is a day nobody can reconstruct.** Not this tool, not any
competitor, not Epic on request. That is why:

- every reading is appended to a local SQLite log and never overwritten,
- snapshots dedup on `capturedAt`, so re-polling costs nothing,
- `fngg watch` exists at all,
- momentum, rank deltas and trend charts appear only after roughly three days of
  polling, and say so plainly until then rather than showing a fabricated zero.

The `day` bucket only rolls over once per day, so polling it more often writes
nothing new — six-hourly is comfortable margin against a missed run. Use
`--interval hour` on a small tracked set when you need finer resolution.

---

## Discovery Fitness

A single 0–100 score per island, plus the breakdown that makes it useful.

### What it is built on

Epic documents *what* the algorithmic Discover rows respond to — number of
players, how many play in parties, and how often players come back — but not the
formula. Discovery Fitness is an explicit model over those documented signals:

| Component | Built from |
|---|---|
| **Scale** | unique players (60%), peak CCU (40%) |
| **Retention** | D1 (45%), D7 (40%), D7÷D1 curve hold (15%) |
| **Session depth** | minutes per player (55%), minutes per session (25%), sessions per player (20%) |
| **Advocacy** | favourites per player (65%), recommendations per player (35%) |
| **Momentum** | blended 7-day growth in players, minutes and CCU |

Each component is a **cohort percentile**, so 40 means "60% of comparable islands
beat you here". The components are then weighted by genre and summed.

### Why the weights differ by genre

```
              retention  depth  scale  advocacy  momentum
RP                 0.32   0.26   0.18      0.14      0.10
Open world         0.28   0.24   0.20      0.14      0.14
FFA                0.22   0.12   0.30      0.14      0.22
```

An RP city lives or dies on whether people come back and stay for an hour. An FFA
map is a throughput business: raw concurrency and growth rate dominate, and a
12-minute session is already a good one. Scoring both against one formula would
tell an RP creator to chase concurrency and an FFA creator to chase session
length, and both would be wrong.

### What it cannot see

These caveats travel with every score, in the UI and in the MCP output:

- It is a model on Epic's **documented inputs**, not Epic's ranking formula. Treat
  it as a diagnostic, never as a prediction.
- **Party-play percentage** is a documented Discover input with no public data
  source. It is absent rather than faked.
- **Epic's Picks** and **By Epic** are editorially curated. No metric earns them,
  and the app reports them as not-modelled rather than scoring them.
- Percentiles move when the cohort moves, not only when you do.

### Levers

The most useful output is not the score, it is the lever list:

```
WHERE THE POINTS ARE
  +  7.4  Session depth  p47 → p75, weighted 0.26
  +  2.5  Advocacy       p57 → p75, weighted 0.14

  Fix first: Session depth.
```

Upside is `weight × distance to the cohort's 75th percentile`. A weak component
that barely counts for your genre never outranks a nearly-as-weak one that counts
double, so the top of this list is genuinely where the effort belongs.

---

## Discover row fit

The same measurements, re-weighted per row. This is the "other tabs" analysis.

| Row | What it rewards | Notes |
|---|---|---|
| **Popular** | scale 70%, retention 20%, depth 10% | Hardest to enter cold, most self-reinforcing once in |
| **Trending / Rising** | momentum 65%, scale 20%, retention 15% | The realistic first row for a small island |
| **New Releases** | retention 40%, momentum 35%, depth 25% | Time-boxed (~30 days); early retention decides if the launch converts |
| **By Players Like You** | retention 50%, depth 30%, advocacy 20% | Personalised — RP and open world over-index here |
| **Community Choice** | advocacy 60%, retention 25%, depth 15% | The one row a small island can win on ratio, not volume |
| **Top Charts / Most Played** | scale 45%, depth 40%, retention 15% | Runs on total minutes, so long sessions substitute for headcount |
| **Epic's Picks**, **By Epic** | — | Curated. Reported as not-modelled. |

New Releases closes when an island passes its window, and the app marks it
ineligible rather than quietly scoring it.

---

## Genres and cohorts

Islands are classified in three passes:

1. **Manual override** — `fngg genre <code> rp`, or `auto` to clear it.
2. **Weighted keywords** over tags, title and Epic category. Tags weigh 1.5× a
   title match: a creator who tags "Roleplay" is telling Epic's own taxonomy what
   the island is. Matching is on word boundaries, so "corporate" never reads as RP.
3. **Behavioural fallback** for islands whose text says nothing ("MY MAP v2"),
   inferred from session length and sessions per player. This resolves only to a
   family-typical genre and carries deliberately low confidence.

Genres: `rp`, `ffa`, `open_world`, `box_fight`, `zone_wars`, `practice`, `tycoon`,
`horror`, `parkour`, `puzzle`, `racing`, `pve`, `party`, `hide_and_seek`,
`prop_hunt`, `battle_royale`, `music`, `other`.

They group into **session-shape families**: `long_form` (RP, open world, tycoon,
PvE), `short_loop` (FFA, box fight, zone wars, practice, racing), and `mixed`.

**Cohort fallback.** Percentiles need a population. When a genre has fewer than 8
islands in your database, the cohort falls back to its family, then to everything,
and the Benchmarks tab tells you when that happened. Sync more of the catalogue to
sharpen it.

---

## Dashboard tabs

| Tab | What it is for |
|---|---|
| **Discovery** | Fitness leaderboard with per-component columns, plus a row-by-row panel showing who is built for each Discover row |
| **Browse** | The full catalogue — search, genre filter, sortable columns, sparklines |
| **Movers** | Biggest 7-day risers and fallers, with rank deltas and a volatility column that separates a real climb from one loud evening |
| **Retention** | D1 against D7 scatter with quadrants, and a curve-hold leaderboard |
| **Engagement** | Session length against sessions per player — the axis that separates RP from FFA — plus audience against total player hours |
| **Benchmarks** | Percentile tables per genre: what "good" actually looks like |
| **Compare** | Islands side by side on cohort percentiles |
| **Status** | History depth, poll runs, fortnite.gg probe results, database path |
| **Map detail** | Fitness dial, component percentiles, ranked levers, row fit, history charts, every metric against cohort |

Charts are inline SVG, generated server-side. No CDN, no external requests, works
offline, prints correctly, and follows your system light/dark theme with a manual
toggle.

---

## CLI reference

```
fngg demo [--count N] [--days N] [--reset]     load synthetic data
fngg sync [--limit N] [--fresh]                pull Epic's catalogue (resumable)
fngg poll [--limit N] [--interval day|hour|minute] [--tracked] [--gg]
fngg watch [--every MINUTES] [--tracked] [--gg]
fngg serve [--host H] [--port P] [--open]
fngg track CODE... [--remove]
fngg genre CODE {rp|ffa|open_world|...|auto}
fngg report CODE [--json]                      full analysis in the terminal
fngg top [--genre G] [--metric M] [--limit N]
fngg movers [--genre G] [--falling] [--min N]
fngg benchmarks [GENRE]
fngg stats
fngg export [--format csv|json] [--genre G] [--out FILE]
fngg probe [--code CODE]                       test fortnite.gg from this machine
```

Invoke as `python -m fngg <command>`.

---

## MCP tools

`fngg_mcp_server.py` exposes the analytics to Claude Code, so island questions can
be asked in the same session where the map is being built.

```json
{
  "mcpServers": {
    "fngg": {
      "command": "python",
      "args": ["/path/to/uefn-mcp-server/fngg_mcp_server.py"]
    }
  }
}
```

Requires `pip install mcp`. Works with both MCP SDK 1.x (`FastMCP`) and 2.x
(`MCPServer`).

| Tool | Purpose |
|---|---|
| `island_report` | Full analysis of one island, formatted or structured |
| `discovery_leaderboard` | Fitness ranking, optionally per genre |
| `row_fit` | Per-Discover-row fit for one island |
| `movers` | 7-day risers or fallers |
| `benchmarks` | Percentile table for a genre |
| `search_islands` | Search by title, code, creator or tag |
| `compare_islands` | Side-by-side percentiles |
| `genre_breakdown` | Catalogue composition and history depth |
| `track_island` | Mark an island as priority-polled |
| `set_genre` | Override a misclassified genre |
| `poll_now` | Take a fresh reading from Epic |
| `sync_catalog` | Walk Epic's catalogue |
| `database_stats` | What is stored locally |
| `probe_fortnitegg` | Test the optional adapter |

Then, in Claude Code:

> *"How does my RP map 1234-5678-9012 compare to its cohort, and what should I fix first?"*
>
> *"Which FFA islands are rising fastest this week?"*
>
> *"What does good day-7 retention look like for open-world maps?"*

---

## The fortnite.gg adapter

Epic's API gives authoritative daily metrics but not two things: **live**
concurrency right now, and which Discover row an island is actually sitting in.
fortnite.gg surfaces both, and this adapter reads them into the same local log.

fortnite.gg is a website, not a documented API. It has no published contract and
its markup can change without notice, so the adapter is built defensively:

- a list of **candidate URLs** per task, tried in order,
- **tolerant parsers** — embedded JSON first, then a text scan that pairs island
  codes with the nearest preceding row heading,
- failures are caught and reported, never propagated.

Check what works from your machine:

```bash
python -m fngg probe
```

The result is shown on the Status tab. To add or reorder candidates without
touching code, drop a file at `~/.fngg/fortnitegg_strategies.json`:

```json
{
  "island": ["https://fortnite.gg/island?code={code}"],
  "browse": ["https://fortnite.gg/creative?sort=players"],
  "discovery": ["https://fortnite.gg/discover"]
}
```

Your entries are tried first; the built-in candidates remain as fallback.

**This source is entirely optional.** Every Ecosystem-backed feature — which is
all the analytics — works without it.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FNGG_HOME` | `~/.fngg` | Data directory |
| `FNGG_DB` | `$FNGG_HOME/fngg.sqlite3` | Database path |
| `FNGG_WEB_HOST` | `127.0.0.1` | Dashboard host |
| `FNGG_WEB_PORT` | `8770` | Dashboard port |
| `FNGG_RATE_LIMIT_RPS` | `6` | Requests per second to Epic |
| `FNGG_HTTP_TIMEOUT` | `20` | Seconds |
| `FNGG_HTTP_RETRIES` | `3` | Retries on 429 / 5xx / network errors |
| `FNGG_CATALOG_LIMIT` | `5000` | Default islands per `sync` |

The dashboard binds to localhost and has no authentication, by design — it is a
local tool reading a local database and should not be exposed to a network.

---

## Troubleshooting

**"No island has enough polling history yet."**
Expected on a new install. Epic does not backfill, so trends need roughly three
days of polling. Keep `fngg watch` running.

**Momentum is empty but I have been polling for days.**
Check `fngg stats` for `history_days`. If it is near zero while snapshots are
accumulating, the `day` bucket has not rolled over between polls — that is normal
and dedup is doing its job. History advances one point per day on that interval.

**Benchmarks say the cohort fell back.**
Fewer than 8 islands of that genre are in your database. Run
`fngg sync --limit 5000`.

**An island is classified wrong.**
`fngg genre <code> rp`. This changes which cohort it is benchmarked against, so it
materially changes its scores. `auto` restores automatic classification.

**`fngg probe` reports fortnite.gg unreachable.**
Optional source; everything else still works. If the site is up for you in a
browser, add the URL you see to `~/.fngg/fortnitegg_strategies.json`.

**`ModuleNotFoundError: No module named 'mcp'`**
Only `fngg_mcp_server.py` needs it: `pip install mcp`. The CLI and dashboard are
stdlib-only.

---

## Tests

```bash
python -m unittest discover -s tests -p "test_fngg.py" -v
```

69 tests, fully offline — no network, no live API.
