"""Composites discipline gate: ``python -m aiur.composites``.

Runs every self-check in the package and returns non-zero when the record
and the arithmetic disagree, or when a critical structural check fails.

The distinction is the same one the capture-chain tolerance stack makes, and
for the same reason.  A **registry error** — a schedule that breaks a design
rule with no waiver, a waiver that outlived its rule break, a qualified cure
cycle that fails its own acceptance criteria, a traveler step that records
nothing — means the documentation and the analysis have drifted apart, and
nothing downstream can be trusted.  A **critical check failure** means a
built part could drop a captured aircraft.  Neither is mergeable.

Advisory failures are different: they are recorded as findings and stay
green, because a program that cannot carry a known, written-down shortfall
ends up hiding it instead.
"""

from __future__ import annotations

import json

from . import (
    allowables,
    cure,
    doe,
    flatpattern,
    materials,
    process,
    schedules,
    spc,
    springin,
    tooling,
    traveler,
)


def snapshot() -> dict[str, object]:
    """Aggregate every module's self-report into one document."""

    material_report = materials.snapshot()
    schedule_report = schedules.snapshot()
    cure_report = cure.snapshot()
    traveler_report = traveler.snapshot()
    doe_report = doe.snapshot()
    pattern_report = flatpattern.snapshot()

    errors: list[str] = []
    errors.extend(f"materials: {error}" for error in material_report["errors"])  # type: ignore[union-attr]
    errors.extend(f"schedules: {error}" for error in schedule_report["errors"])  # type: ignore[union-attr]
    errors.extend(f"cure: {error}" for error in cure_report["errors"])  # type: ignore[union-attr]
    errors.extend(f"traveler: {error}" for error in traveler_report["errors"])  # type: ignore[union-attr]
    errors.extend(f"doe: {error}" for error in doe_report["errors"])  # type: ignore[union-attr]
    errors.extend(f"flatpattern: {error}" for error in pattern_report["errors"])  # type: ignore[union-attr]

    critical = list(schedule_report["critical_failures"])  # type: ignore[arg-type]

    return {
        "article": "CARRIER-P0 composite structures",
        "valid": not errors,
        "errors": errors,
        "critical_failures": critical,
        "evidence_state": allowables.program_status(),
        "materials": material_report,
        "schedules": schedule_report,
        "cure": cure_report,
        "flatpattern": pattern_report,
        "springin": springin.snapshot(),
        "tooling": tooling.snapshot(),
        "process": process.snapshot(),
        "traveler": traveler_report,
        "allowables": allowables.snapshot(),
        "spc": spc.snapshot(),
        "doe": doe_report,
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2, default=str))
    if not report["valid"] or report["critical_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
