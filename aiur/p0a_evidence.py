"""Strict evidence reducer for the CARRIER-P0 P0-A bench gate.

The reducer turns three raw CSV logs into the exact numeric metrics consumed by
``evaluate_gate``.  Structural completeness is checked before a verdict is
allowed: a missing pre/post load direction is missing evidence, not a zero or a
silent pass.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .loop_graph import evaluate_gate


RUN_KEY_FIELDS = ("run_id", "article_rev", "git_commit")
LOAD_PHASES = ("pre_cycle", "post_cycle")
LOAD_DIRECTIONS = ("AXIAL", "+X", "-X", "+Y", "-Y")


class EvidenceError(ValueError):
    """Raised when the raw evidence set is incomplete or internally inconsistent."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise EvidenceError(f"{path}: no evidence rows")
    return rows


def _required(row: dict[str, str], field: str, context: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise EvidenceError(f"{context}: missing {field}")
    return value


def _bool(row: dict[str, str], field: str, context: str) -> bool:
    value = _required(row, field, context).lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    raise EvidenceError(f"{context}: {field} must be 0/1 or true/false")


def _float(row: dict[str, str], field: str, context: str) -> float:
    try:
        return float(_required(row, field, context))
    except ValueError as exc:
        raise EvidenceError(f"{context}: {field} must be numeric") from exc


def _int(row: dict[str, str], field: str, context: str) -> int:
    value = _float(row, field, context)
    if not value.is_integer():
        raise EvidenceError(f"{context}: {field} must be an integer")
    return int(value)


def _run_key(row: dict[str, str], context: str) -> tuple[str, str, str]:
    return tuple(_required(row, field, context) for field in RUN_KEY_FIELDS)  # type: ignore[return-value]


def _assert_run_key(
    row: dict[str, str], expected: tuple[str, str, str], context: str
) -> None:
    if _run_key(row, context) != expected:
        raise EvidenceError(f"{context}: run/article/git identity does not match article record")


def reduce_p0a(
    article_csv: Path,
    cycles_csv: Path,
    loads_csv: Path,
) -> dict[str, float | int | bool]:
    """Reduce complete raw P0-A logs into executable gate metrics."""

    article_rows = _read_csv(article_csv)
    if len(article_rows) != 1:
        raise EvidenceError(f"{article_csv}: expected exactly one article row")
    article = article_rows[0]
    identity = _run_key(article, "article")
    dock_mass_g = _float(article, "dock_mass_g", "article")
    probe_mass_g = _float(article, "probe_mass_g", "article")
    propellers_installed = _bool(article, "propellers_installed", "article")

    cycle_rows = _read_csv(cycles_csv)
    cycle_numbers: list[int] = []
    completed_cycles = 0
    structural_failures = 0
    ambiguous_confirmations = 0
    emergency_trials = 0
    emergency_failures = 0

    for index, row in enumerate(cycle_rows, start=2):
        context = f"cycles row {index}"
        _assert_run_key(row, identity, context)
        cycle = _int(row, "cycle", context)
        cycle_numbers.append(cycle)
        capture_confirmed = _bool(row, "capture_confirmed", context)
        release_completed = _bool(row, "release_completed", context)
        if capture_confirmed and release_completed:
            completed_cycles += 1
        structural_failures += int(_bool(row, "structural_failure", context))
        ambiguous_confirmations += int(
            _bool(row, "ambiguous_capture_confirmation", context)
        )
        emergency_trial = _bool(row, "emergency_release_trial", context)
        if emergency_trial:
            emergency_trials += 1
            emergency_failures += int(
                not _bool(row, "emergency_release_success", context)
            )

    if len(set(cycle_numbers)) != len(cycle_numbers):
        raise EvidenceError("cycles: duplicate cycle number")
    if sorted(cycle_numbers) != list(range(1, max(cycle_numbers) + 1)):
        raise EvidenceError("cycles: cycle numbers must be contiguous from 1")

    load_rows = _read_csv(loads_csv)
    expected = {(phase, direction) for phase in LOAD_PHASES for direction in LOAD_DIRECTIONS}
    observed: dict[tuple[str, str], float] = {}

    for index, row in enumerate(load_rows, start=2):
        context = f"loads row {index}"
        _assert_run_key(row, identity, context)
        phase = _required(row, "phase", context)
        direction = _required(row, "direction", context)
        key = (phase, direction)
        if key not in expected:
            raise EvidenceError(f"{context}: unexpected phase/direction {key}")
        if key in observed:
            raise EvidenceError(f"{context}: duplicate load screen {key}")

        held_load = _float(row, "held_load_n", context)
        duration = _float(row, "duration_s", context)
        retained = _bool(row, "retained", context)
        damage = _bool(row, "structural_damage", context)
        structural_failures += int(damage)

        # A short-duration or released screen receives zero credited load.  The
        # row remains valid evidence of a failed test rather than disappearing.
        observed[key] = held_load if duration >= 10.0 and retained and not damage else 0.0

    missing = sorted(expected - observed.keys())
    if missing:
        raise EvidenceError(f"loads: missing required pre/post screens: {missing}")

    axial_load = min(observed[(phase, "AXIAL")] for phase in LOAD_PHASES)
    lateral_load = min(
        observed[(phase, direction)]
        for phase in LOAD_PHASES
        for direction in LOAD_DIRECTIONS
        if direction != "AXIAL"
    )

    return {
        "manual_cycles": completed_cycles,
        "dock_mass_g": dock_mass_g,
        "probe_mass_g": probe_mass_g,
        "axial_screen_load_held_n": axial_load,
        "lateral_screen_load_held_n": lateral_load,
        "structural_failures": structural_failures,
        "ambiguous_capture_confirmations": ambiguous_confirmations,
        "emergency_release_trials": emergency_trials,
        "emergency_release_failures": emergency_failures,
        "propellers_installed": int(propellers_installed),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reduce CARRIER-P0 P0-A evidence")
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--cycles", type=Path, required=True)
    parser.add_argument("--loads", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        metrics = reduce_p0a(args.article, args.cycles, args.loads)
    except EvidenceError as exc:
        print(json.dumps({"gate_id": "P0-A", "passed": False, "evidence_error": str(exc)}, indent=2))
        return 2

    verdict = evaluate_gate("P0-A", metrics)
    print(json.dumps({"metrics": metrics, "verdict": asdict(verdict)}, indent=2, sort_keys=True))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
