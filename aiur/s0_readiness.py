"""Executable readiness graph for STRATO-P0.

"Done" for a hardware program has two halves, and this register keeps
them apart so neither can be mistaken for the other.  The *software* half
is everything that can be closed at a desk: models, gates, requirements,
hazards, the flight supervisor, the simulated flights, the evidence
reducers, the drawings, the procedures.  The *hardware* half is what only
a scale, a cold chamber, a tether, and a free flight can close, and it
stays open here until the reducer says otherwise.

Each item names what closes it, what it depends on, and the evidence that
shows it closed.  ``validate_readiness`` checks that the graph is acyclic,
that every closed item's evidence exists in the tree, and that nothing
hardware-closable is marked closed by a software commit.
``software_done`` is the loop's exit condition: true when no
software-closable item is open.

    python -m aiur.s0_readiness
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClosedBy(str, Enum):
    SOFTWARE = "software"
    DECISION = "decision"
    BENCH = "bench"
    TETHERED = "tethered"
    FLIGHT = "flight"


class ItemStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    title: str
    closed_by: ClosedBy
    status: ItemStatus
    #: Repository paths that are the evidence for a closed item, or that the
    #: open item will produce.  Every listed path must exist for CLOSED.
    evidence: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    #: For open items: the next concrete action.
    next_action: str = ""


#: Where decisions are recorded.  A DECISION item may be closed by a commit
#: only when this document carries a name and an ISO date under the item's
#: heading; the validator reads it.
DECISIONS_DOC = "docs/decisions/strato-decisions.md"


def decision_is_recorded(item_id: str, root: Path = ROOT) -> bool:
    """True when the decisions document has a signed, dated record for the item."""

    path = root / DECISIONS_DOC
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    heading = f"## {item_id}"
    start = text.find(heading)
    if start < 0:
        return False
    end = text.find("\n## ", start + len(heading))
    section = text[start : end if end > 0 else len(text)]
    decided_by = _table_value(section, "Decided by")
    date = _table_value(section, "Date")
    if not decided_by or not date:
        return False
    try:
        from datetime import date as _date

        _date.fromisoformat(date)
    except ValueError:
        return False
    return True


def _table_value(section: str, field: str) -> str:
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == field:
            return cells[1]
    return ""


ITEMS: tuple[ReadinessItem, ...] = (
    # ---- software ---------------------------------------------------
    ReadinessItem(
        "SW-MODEL",
        "atmosphere, ascent, float, descent, geometry, and power model anchored to the standard's tables",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/strato.py", "tests/test_strato.py"),
    ),
    ReadinessItem(
        "SW-GATES",
        "S0-A/S0-B/S0-C gate ladder with a free-flight stage entered only from a passed tethered gate",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/loop_graph.py", "tests/test_loop_graph.py"),
        ("SW-MODEL",),
    ),
    ReadinessItem(
        "SW-REQS",
        "S0-* requirement closure rows validated against the gates",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/requirements.py", "tests/test_requirements.py"),
        ("SW-GATES",),
    ),
    ReadinessItem(
        "SW-HAZARDS",
        "HAZ-013..017 in the hazard log with verification pointing at real gate criteria",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/hazards.py", "tests/test_hazards.py"),
        ("SW-REQS",),
    ),
    ReadinessItem(
        "SW-SUPERVISOR",
        "fail-safe flight supervisor with a latched cutdown and an independent timer model",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/flight_supervisor.py", "tests/test_flight_supervisor.py"),
        ("SW-GATES",),
    ),
    ReadinessItem(
        "SW-SIM",
        "simulated flights across the hazard log's fault menu, asserting the outcomes the log expects",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/strato_sim.py", "tests/test_strato_sim.py"),
        ("SW-SUPERVISOR", "SW-MODEL"),
    ),
    ReadinessItem(
        "SW-REDUCE",
        "strict evidence reducers for every S0 gate (A, B, C) with simulated evidence labelled and non-closing",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/s0_evidence.py", "tests/test_s0_evidence.py"),
        ("SW-SIM", "SW-GATES"),
    ),
    ReadinessItem(
        "SW-CAD",
        "generated enclosure cut sheet, section, and manifest with the weight/size ratio",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        (
            "hardware/strato/cad/generate_package_rev_a.py",
            "hardware/strato/cad/generated/strato_package_rev_a_manifest.json",
            "tests/test_package_cad.py",
        ),
        ("SW-MODEL",),
    ),
    ReadinessItem(
        "SW-PACKET",
        "BOM, S0-A test card, launch checklist, and log/manifest templates",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        (
            "hardware/strato/README.md",
            "hardware/strato/bom.csv",
            "hardware/strato/s0a-test-card.md",
            "hardware/strato/launch-checklist.md",
            "hardware/strato/s0-flight-manifest-template.json",
        ),
        ("SW-CAD", "SW-REDUCE"),
    ),
    ReadinessItem(
        "SW-PREDICT",
        "launch-day landing prediction from a measured wind profile, with the geofence derived from it",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        (
            "aiur/strato_predict.py",
            "tests/test_strato_predict.py",
            "hardware/strato/s0-sounding-template.csv",
        ),
        ("SW-SIM",),
    ),
    ReadinessItem(
        "SW-FLIGHT-MAIN",
        "runnable flight program: sensor abstraction, 1 Hz loop, real flight-log writer, simulated backend",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/flight_main.py", "tests/test_flight_main.py"),
        ("SW-SUPERVISOR",),
    ),
    ReadinessItem(
        "SW-GROUND-MERGE",
        "ground receive log merged into the package log so telemetry gaps are judged from the ground side",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("aiur/s0_evidence.py", "hardware/strato/s0-ground-log-template.csv"),
        ("SW-REDUCE",),
    ),
    ReadinessItem(
        "DOC-HAZLOG",
        "docs/hazard-log.md generated from the registry and checked in CI",
        ClosedBy.SOFTWARE,
        ItemStatus.CLOSED,
        ("docs/hazard-log.md", "tools/render_hazard_log.py", "tests/test_hazard_log_doc.py"),
        ("SW-HAZARDS",),
    ),
    # ---- decisions ----------------------------------------------------
    ReadinessItem(
        "DEC-JURISDICTION",
        "launch jurisdiction and its notice rules decided and recorded",
        ClosedBy.DECISION,
        ItemStatus.OPEN,
        (DECISIONS_DOC, "hardware/strato/s0-flight-manifest-template.json"),
        ("SW-PACKET",),
        "founder decision: sign and date the DEC-JURISDICTION record in docs/decisions/strato-decisions.md",
    ),
    ReadinessItem(
        "DEC-TRACKER",
        "independent tracker chosen (APRS with a licence, or a satellite beacon with a plan)",
        ClosedBy.DECISION,
        ItemStatus.OPEN,
        (DECISIONS_DOC, "hardware/strato/bom.csv"),
        ("DEC-JURISDICTION",),
        "depends on the jurisdiction; sign the DEC-TRACKER record, then unblock order lines S0-20..S0-23",
    ),
    # ---- hardware -----------------------------------------------------
    ReadinessItem(
        "HW-S0A",
        "S0-A: measured mass, cold soak, termination and link trials, drop tests reduced to a PASS",
        ClosedBy.BENCH,
        ItemStatus.OPEN,
        ("hardware/strato/s0a-test-card.md",),
        ("SW-PACKET", "SW-FLIGHT-MAIN", "DEC-TRACKER"),
        "build the Rev-A package and run the card; python -m aiur.s0_evidence chamber",
    ),
    ReadinessItem(
        "HW-S0B",
        "S0-B: three tethered ascents with one termination aloft, reduced to a PASS",
        ClosedBy.TETHERED,
        ItemStatus.OPEN,
        ("hardware/strato/launch-checklist.md",),
        ("HW-S0A",),
        "python -m aiur.s0_evidence tethered",
    ),
    ReadinessItem(
        "HW-S0C",
        "S0-C: two free flights of one configuration past 20 km, recovered, reduced to a PASS",
        ClosedBy.FLIGHT,
        ItemStatus.OPEN,
        ("hardware/strato/launch-checklist.md",),
        ("HW-S0B", "SW-PREDICT", "SW-GROUND-MERGE", "DEC-JURISDICTION"),
        "python -m aiur.s0_evidence flight",
    ),
)


def item_by_id(item_id: str, items: tuple[ReadinessItem, ...] = ITEMS) -> ReadinessItem:
    for item in items:
        if item.id == item_id:
            return item
    raise KeyError(f"unknown readiness item: {item_id}")


def topological_order(items: tuple[ReadinessItem, ...] = ITEMS) -> tuple[str, ...]:
    """Dependency order; raises on a cycle or a dangling dependency."""

    by_id = {item.id: item for item in items}
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(item_id: str, path: tuple[str, ...]) -> None:
        if item_id not in by_id:
            raise ValueError(f"{path[-1]} depends on unknown item {item_id}")
        if state.get(item_id) == 1:
            raise ValueError(f"cycle through {' -> '.join(path + (item_id,))}")
        if state.get(item_id) == 2:
            return
        state[item_id] = 1
        for dep in by_id[item_id].depends_on:
            visit(dep, path + (item_id,))
        state[item_id] = 2
        order.append(item_id)

    for item in items:
        visit(item.id, ())
    return tuple(order)


def validate_readiness(items: tuple[ReadinessItem, ...] = ITEMS, root: Path = ROOT) -> tuple[str, ...]:
    errors: list[str] = []
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        errors.append("readiness ids must be unique")
    try:
        topological_order(items)
    except ValueError as exc:
        errors.append(str(exc))
    for item in items:
        if not item.evidence:
            errors.append(f"{item.id} names no evidence")
        if item.status is ItemStatus.CLOSED:
            if item.closed_by is ClosedBy.DECISION:
                if not decision_is_recorded(item.id, root):
                    errors.append(
                        f"{item.id} is closed but {DECISIONS_DOC} carries no signed, dated record for it"
                    )
            elif item.closed_by is not ClosedBy.SOFTWARE:
                errors.append(
                    f"{item.id} is closed by {item.closed_by.value} evidence, which a commit cannot supply"
                )
            for path in item.evidence:
                if not (root / path).exists():
                    errors.append(f"{item.id} is closed but evidence {path} does not exist")
        elif not item.next_action.strip():
            errors.append(f"{item.id} is open without a next action")
    return tuple(errors)


def software_done(items: tuple[ReadinessItem, ...] = ITEMS) -> bool:
    return not any(
        item.status is ItemStatus.OPEN and item.closed_by is ClosedBy.SOFTWARE for item in items
    )


def next_software_items(items: tuple[ReadinessItem, ...] = ITEMS) -> tuple[ReadinessItem, ...]:
    """Open software items whose dependencies are all closed, in graph order."""

    by_id = {item.id: item for item in items}
    ready = []
    for item_id in topological_order(items):
        item = by_id[item_id]
        if item.status is ItemStatus.OPEN and item.closed_by is ClosedBy.SOFTWARE:
            if all(by_id[dep].status is ItemStatus.CLOSED for dep in item.depends_on):
                ready.append(item)
    return tuple(ready)


def ladder(items: tuple[ReadinessItem, ...] = ITEMS) -> str:
    """Text rendering of the graph in dependency order."""

    by_id = {item.id: item for item in items}
    lines = []
    for item_id in topological_order(items):
        item = by_id[item_id]
        mark = "x" if item.status is ItemStatus.CLOSED else " "
        deps = f"  <- {', '.join(item.depends_on)}" if item.depends_on else ""
        lines.append(f"[{mark}] {item.id:<16} {item.closed_by.value:<9} {item.title}{deps}")
    return "\n".join(lines)


def snapshot() -> dict[str, object]:
    errors = validate_readiness()
    by_closer = {closer.value: {"open": 0, "closed": 0} for closer in ClosedBy}
    for item in ITEMS:
        by_closer[item.closed_by.value][item.status.value] += 1
    return {
        "valid": not errors,
        "errors": list(errors),
        "software_done": software_done(),
        "next_software_items": [item.id for item in next_software_items()],
        "by_closer": by_closer,
        "order": list(topological_order()),
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "closed_by": item.closed_by.value,
                "status": item.status.value,
                "depends_on": list(item.depends_on),
                "evidence": list(item.evidence),
                "next_action": item.next_action,
            }
            for item in ITEMS
        ],
    }


#: The site reads this file; ``--export`` writes it and a test keeps it fresh.
SITE_EXPORT = "web/lib/readiness.json"


def site_export() -> dict[str, object]:
    """The subset of the snapshot the public site renders."""

    data = snapshot()
    return {
        "software_done": data["software_done"],
        "by_closer": data["by_closer"],
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "closed_by": item["closed_by"],
                "status": item["status"],
                "depends_on": item["depends_on"],
            }
            for item in data["items"]  # type: ignore[union-attr]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="STRATO-P0 readiness graph.")
    parser.add_argument("--export", action="store_true", help=f"write {SITE_EXPORT}")
    args = parser.parse_args(argv)
    if args.export:
        path = ROOT / SITE_EXPORT
        path.write_text(json.dumps(site_export(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {SITE_EXPORT}")
        return 0
    print(ladder())
    print()
    print(json.dumps({k: v for k, v in snapshot().items() if k != "items"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
