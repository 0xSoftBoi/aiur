"""Strict evidence reducer for the CARRIER-P0 P0-A bench gate.

The reducer turns four raw CSV logs into the exact numeric metrics consumed by
``evaluate_gate``.  Structural completeness is checked before a verdict is
allowed: a missing pre/post load direction is missing evidence, not a zero or a
silent pass.

Cycle rows carry an explicit phase.  ``run_in`` cycles come first and exist to
let a fresh mechanism wear in; their per-cycle insertion/release forces must
level off before the ``life`` cycles that satisfy the derived life-test
requirement begin.  Trending run-in rather than assuming it is the difference
between a life test and a long demonstration.

The fourth log records hardware fault insertion: each row is one deliberately
injected electrical fault and the response the mechanism actually produced.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .loop_graph import REQUIRED_FAULT_MODES, evaluate_gate


RUN_KEY_FIELDS = ("run_id", "article_rev", "git_commit")
LOAD_PHASES = ("pre_cycle", "post_cycle")
LOAD_DIRECTIONS = ("AXIAL", "+X", "-X", "+Y", "-Y")
CYCLE_PHASES = ("run_in", "life")

#: Fraction by which the mean per-cycle force may still be changing across the
#: back half of run-in and still count as leveled off.  An engineering target
#: until real run-in data exists.
RUN_IN_STABILITY_FRACTION = 0.10



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


def _run_in_trend_stabilized(forces: list[float]) -> bool:
    """Return True when per-cycle force has leveled off across run-in.

    Compares the mean of the first half of the run-in series against the mean
    of the second half.  A mechanism still bedding in shows a monotone drift;
    a run-in that is complete shows halves within a few percent.
    """

    usable = [value for value in forces if value > 0.0]
    if len(usable) < 4:
        return False
    midpoint = len(usable) // 2
    first = sum(usable[:midpoint]) / midpoint
    second = sum(usable[midpoint:]) / (len(usable) - midpoint)
    if first <= 0.0:
        return False
    return abs(second - first) / first <= RUN_IN_STABILITY_FRACTION


def reduce_p0a(
    article_csv: Path,
    cycles_csv: Path,
    loads_csv: Path,
    faults_csv: Path | None = None,
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
    keeper_close_force_margin = _float(article, "keeper_close_force_margin", "article")
    keeper_open_force_margin = _float(article, "keeper_open_force_margin", "article")

    cycle_rows = _read_csv(cycles_csv)
    cycle_numbers: list[int] = []
    run_in_cycles = 0
    life_cycles = 0
    run_in_forces: list[float] = []
    structural_failures = 0
    ambiguous_confirmations = 0
    emergency_trials = 0
    emergency_failures = 0
    loaded_emergency_trials = 0
    loaded_emergency_failures = 0

    for index, row in enumerate(cycle_rows, start=2):
        context = f"cycles row {index}"
        _assert_run_key(row, identity, context)
        cycle = _int(row, "cycle", context)
        cycle_numbers.append(cycle)
        phase = _required(row, "phase", context)
        if phase not in CYCLE_PHASES:
            raise EvidenceError(f"{context}: phase must be one of {CYCLE_PHASES}")
        capture_confirmed = _bool(row, "capture_confirmed", context)
        release_completed = _bool(row, "release_completed", context)
        if capture_confirmed and release_completed:
            if phase == "run_in":
                run_in_cycles += 1
                run_in_forces.append(_float(row, "insertion_force_n", context))
            else:
                life_cycles += 1
        structural_failures += int(_bool(row, "structural_failure", context))
        ambiguous_confirmations += int(
            _bool(row, "ambiguous_capture_confirmation", context)
        )
        emergency_trial = _bool(row, "emergency_release_trial", context)
        if emergency_trial:
            succeeded = _bool(row, "emergency_release_success", context)
            # A release performed with the screening load applied is the case
            # mechanism practice cares about; unloaded releases prove less.
            if _float(row, "emergency_release_load_n", context) > 0.0:
                loaded_emergency_trials += 1
                loaded_emergency_failures += int(not succeeded)
            else:
                emergency_trials += 1
                emergency_failures += int(not succeeded)

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

    fault_trials = 0
    fault_unsafe = 0
    if faults_csv is not None:
        fault_rows = _read_csv(faults_csv)
        observed_modes: set[str] = set()
        for index, row in enumerate(fault_rows, start=2):
            context = f"faults row {index}"
            _assert_run_key(row, identity, context)
            mode = _required(row, "fault_mode", context)
            if mode not in REQUIRED_FAULT_MODES:
                raise EvidenceError(
                    f"{context}: unknown fault mode {mode!r}; expected one of "
                    f"{REQUIRED_FAULT_MODES}"
                )
            observed_modes.add(mode)
            fault_trials += 1
            # The required response is written on the row before the trial and
            # compared to what happened; a fault that produced "something
            # reasonable" that was not the required response is a failure.
            fault_unsafe += int(not _bool(row, "required_response_observed", context))
            fault_unsafe += int(_bool(row, "unsafe_state_entered", context))

        missing_modes = sorted(set(REQUIRED_FAULT_MODES) - observed_modes)
        if missing_modes:
            raise EvidenceError(
                f"faults: required fault modes never exercised: {missing_modes}"
            )

    return {
        "run_in_cycles": run_in_cycles,
        "run_in_force_trend_stabilized": int(_run_in_trend_stabilized(run_in_forces)),
        "life_test_cycles": life_cycles,
        "dock_mass_g": dock_mass_g,
        "probe_mass_g": probe_mass_g,
        "axial_screen_load_held_n": axial_load,
        "lateral_screen_load_held_n": lateral_load,
        "keeper_close_force_margin": keeper_close_force_margin,
        "keeper_open_force_margin": keeper_open_force_margin,
        "structural_failures": structural_failures,
        "ambiguous_capture_confirmations": ambiguous_confirmations,
        "emergency_release_trials": emergency_trials,
        "emergency_release_failures": emergency_failures,
        "loaded_emergency_release_trials": loaded_emergency_trials,
        "loaded_emergency_release_failures": loaded_emergency_failures,
        "fault_insertion_trials": fault_trials,
        "fault_insertion_unsafe_responses": fault_unsafe,
        "propellers_installed": int(propellers_installed),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reduce CARRIER-P0 P0-A evidence")
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--cycles", type=Path, required=True)
    parser.add_argument("--loads", type=Path, required=True)
    parser.add_argument("--faults", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        metrics = reduce_p0a(args.article, args.cycles, args.loads, args.faults)
    except EvidenceError as exc:
        print(json.dumps({"gate_id": "P0-A", "passed": False, "evidence_error": str(exc)}, indent=2))
        return 2

    verdict = evaluate_gate("P0-A", metrics)
    print(json.dumps({"metrics": metrics, "verdict": asdict(verdict)}, indent=2, sort_keys=True))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
