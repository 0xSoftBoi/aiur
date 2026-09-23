#!/usr/bin/env python3
"""Render the generated block of docs/hazard-log.md from ``aiur.hazards``.

The document is prose around one table that must never drift from the
registry.  This tool renders that table (and the acceptance counts the
prose quotes) between ``<!-- generated:hazards -->`` markers; the test in
tests/test_hazard_log_doc.py fails when the committed block differs from
what the registry renders, so a hazard added to the code without
regenerating the document is a red build, not a stale page.

    python tools/render_hazard_log.py --write   # splice into the document
    python tools/render_hazard_log.py --check   # exit 1 if the document is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiur.hazards import HAZARDS, RiskLevel, acceptance_required, open_items  # noqa: E402

DOC = ROOT / "docs" / "hazard-log.md"
BEGIN = "<!-- generated:hazards -->"
END = "<!-- /generated:hazards -->"


def render_block() -> str:
    lines = [
        BEGIN,
        "",
        "| ID | Hazard | Initial | Residual | Acceptance required from | State |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for hazard in HAZARDS:
        if acceptance_required(hazard.residual_risk):
            authority = hazard.required_authority.value
            state = "signed" if hazard.is_accepted else "unsigned"
        else:
            authority = "none required at LOW"
            state = "n/a"
        lines.append(
            f"| `{hazard.id}` | {hazard.title} | {hazard.initial_code} {hazard.initial_risk.value} | "
            f"{hazard.residual_code} {hazard.residual_risk.value} | {authority} | {state} |"
        )
    items = open_items()
    above_low = [h for h in HAZARDS if h.residual_risk.rank > RiskLevel.LOW.rank]
    lines += [
        "",
        f"{len(HAZARDS)} hazards; {len(above_low)} residuals above LOW; "
        f"{len(items)} open acceptance items; "
        f"{sum(1 for h in HAZARDS if h.is_accepted)} signed.",
        "",
        END,
    ]
    return "\n".join(lines)


def splice(text: str, block: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ValueError("docs/hazard-log.md has no generated:hazards markers")
    return text[:start] + block + text[end + len(END):]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    current = DOC.read_text(encoding="utf-8")
    updated = splice(current, render_block())
    if args.write:
        DOC.write_text(updated, encoding="utf-8")
        print(f"wrote {DOC.relative_to(ROOT)}")
        return 0
    if updated != current:
        print("docs/hazard-log.md is stale; run tools/render_hazard_log.py --write")
        return 1
    print("docs/hazard-log.md matches the registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
