"""The scan loop: ask every source about every profile, score, store, report what is new."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import db, scoring
from .config import Profile, load_profiles
from .sources import DEFAULT_SOURCES, SourceError, build


@dataclass
class ScanResult:
    profiles: list[str]
    sources: list[str]
    seen: int = 0
    added: int = 0
    new_findings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        line = (
            f"Przeskanowano {len(self.profiles)} profil(i) x {len(self.sources)} zrodel: "
            f"{self.seen} trafien, {self.added} nowych."
        )
        if self.errors:
            line += f" Bledy: {len(self.errors)}."
        return line


def scan(
    profile_ids: list[str] | None = None,
    source_names: list[str] | None = None,
    per_source_limit: int = 40,
    min_score: float = 0.0,
) -> ScanResult:
    """Run a full pass and persist everything scoring above `min_score`."""
    all_profiles = load_profiles()

    if profile_ids:
        unknown = [p for p in profile_ids if p not in all_profiles]
        if unknown:
            raise ValueError(
                f"unknown profile(s): {', '.join(unknown)}. "
                f"Available: {', '.join(all_profiles)}"
            )
        selected: list[Profile] = [all_profiles[p] for p in profile_ids]
    else:
        selected = list(all_profiles.values())

    source_names = source_names or list(DEFAULT_SOURCES)
    sources = build(source_names)

    result = ScanResult(profiles=[p.id for p in selected], sources=source_names)

    with db.connect() as conn:
        for profile in selected:
            for source in sources:
                try:
                    findings = source.search(profile, per_source_limit)
                except SourceError as exc:
                    result.errors.append(f"[{source.name}/{profile.id}] {exc}")
                    continue
                except Exception as exc:  # noqa: BLE001 - one bad source must not kill the scan
                    result.errors.append(f"[{source.name}/{profile.id}] unexpected: {exc}")
                    continue

                for finding in findings:
                    result.seen += 1
                    # A tool can legitimately be relevant to two themes, so the
                    # profile is part of the identity rather than a mutable field.
                    finding.uid = f"{profile.id}/{finding.uid}"
                    finding.score, finding.breakdown = scoring.score(finding, profile)
                    if finding.score < min_score or finding.score == 0.0:
                        continue
                    if db.upsert(conn, finding):
                        result.added += 1
                        result.new_findings.append(
                            {
                                "uid": finding.uid,
                                "name": finding.name,
                                "url": finding.url,
                                "profile": finding.profile,
                                "score": finding.score,
                                "stars": finding.stars,
                                "description": finding.description,
                            }
                        )

        db.record_run(
            conn,
            result.profiles,
            result.sources,
            result.seen,
            result.added,
            result.errors,
        )

    result.new_findings.sort(key=lambda f: f["score"], reverse=True)
    return result
