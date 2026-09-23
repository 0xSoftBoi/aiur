"""Strict evidence reducers for the STRATO-P0 S0-A and S0-C gates.

Raw logs in, the exact metrics ``evaluate_gate`` consumes out.  As with the
carrier's P0-A reducer, structural completeness is checked before a verdict
is allowed: a missing manifest field, a log with no landing, or a trial set
without the computer-off case is missing evidence, not a zero.

Two sources feed the same shapes: the real package writes the flight log and
manifest, and ``aiur.strato_sim`` writes identical files from a simulated
flight.  The manifest's ``evidence_kind`` (``flown`` or ``simulated``) is
carried into every report so a simulated pass is never mistaken for a flown
one.  Only ``flown`` evidence closes a requirement.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable

from .loop_graph import evaluate_gate

STRATOSPHERE_THRESHOLD_M = 20_000.0

FLIGHT_MANIFEST_FIELDS = (
    "run_id",
    "article_rev",
    "git_commit",
    "evidence_kind",
    "predicted_landing_x_km",
    "predicted_landing_y_km",
    "airspace_coordination_ref",
    "recovered",
    "recovery_x_km",
    "recovery_y_km",
    "storage_checksum_verified",
    "third_party_contacts",
)
FLIGHT_LOG_REQUIRED = (
    "t_s",
    "gnss_valid",
    "altitude_m",
    "state",
    "frame_captured",
    "geotagged",
    "telemetry_received",
)
TRIAL_FIELDS = ("trial_id", "kind", "computer_powered", "fired")
SOAK_FIELDS = (
    "t_s",
    "internal_temp_c",
    "imaging_ok",
    "tracking_ok",
    "termination_ok",
    "frame_stored",
)
DROP_FIELDS = ("drop_id", "descent_rate_m_s")
BENCH_MANIFEST_FIELDS = (
    "run_id",
    "article_rev",
    "git_commit",
    "evidence_kind",
    "payload_package_mass_kg",
)
EVIDENCE_KINDS = ("flown", "simulated", "bench")


class EvidenceError(ValueError):
    """Raised when the raw evidence set is incomplete or internally inconsistent."""


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise EvidenceError(f"{path}: no evidence rows")
    return rows


def read_manifest(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{path}: manifest is not valid JSON") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{path}: manifest must be a JSON object")
    return data


def _require_columns(rows: list[dict[str, str]], fields: Iterable[str], context: str) -> None:
    missing = [field for field in fields if field not in rows[0]]
    if missing:
        raise EvidenceError(f"{context}: missing columns {', '.join(missing)}")


def _bool(value: object, field: str, context: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    raise EvidenceError(f"{context}: {field} must be 0/1 or true/false")


def _float(value: object, field: str, context: str) -> float:
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise EvidenceError(f"{context}: {field} must be numeric") from exc


def _require_manifest(manifest: dict[str, object], fields: Iterable[str], context: str) -> None:
    missing = [field for field in fields if field not in manifest or manifest[field] in ("", None)]
    if missing:
        raise EvidenceError(f"{context}: manifest missing {', '.join(missing)}")
    kind = str(manifest["evidence_kind"])
    if kind not in EVIDENCE_KINDS:
        raise EvidenceError(f"{context}: evidence_kind must be one of {', '.join(EVIDENCE_KINDS)}")


# ----------------------------------------------------------------------
# Termination and link trials (shared by S0-A, S0-B, S0-C)
# ----------------------------------------------------------------------


def reduce_trials(rows: list[dict[str, str]], context: str = "trials") -> dict[str, int]:
    _require_columns(rows, TRIAL_FIELDS, context)
    termination_trials = 0
    termination_failures = 0
    computer_off_fired = 0
    link_trials = 0
    link_failures = 0
    for row in rows:
        where = f"{context} {row.get('trial_id', '?')}"
        kind = row["kind"].strip().lower()
        fired = _bool(row["fired"], "fired", where)
        powered = _bool(row["computer_powered"], "computer_powered", where)
        if kind == "termination":
            termination_trials += 1
            if not fired:
                termination_failures += 1
            if not powered and fired:
                computer_off_fired += 1
        elif kind == "link":
            link_trials += 1
            if not fired:
                link_failures += 1
        else:
            raise EvidenceError(f"{where}: kind must be termination or link")
    return {
        "termination_command_trials": termination_trials,
        "termination_failures": termination_failures,
        "termination_verified_with_payload_computer_off": int(computer_off_fired > 0),
        "telemetry_link_trials": link_trials,
        "telemetry_link_failures": link_failures,
    }


# ----------------------------------------------------------------------
# S0-C: free flights
# ----------------------------------------------------------------------


def reduce_flight(
    rows: list[dict[str, str]], manifest: dict[str, object], context: str = "flight"
) -> dict[str, float | int]:
    """Metrics for one free flight; the gate is judged across all of them."""

    _require_columns(rows, FLIGHT_LOG_REQUIRED, context)
    _require_manifest(manifest, FLIGHT_MANIFEST_FIELDS, context)

    max_altitude = -math.inf
    frames_above = 0
    last_rx: float | None = None
    max_gap = 0.0
    landed = False
    previous_t: float | None = None
    for index, row in enumerate(rows):
        where = f"{context} row {index + 1}"
        t = _float(row["t_s"], "t_s", where)
        if previous_t is not None and t < previous_t:
            raise EvidenceError(f"{where}: t_s is not monotonic")
        previous_t = t
        gnss = _bool(row["gnss_valid"], "gnss_valid", where)
        altitude = _float(row["altitude_m"], "altitude_m", where) if gnss else None
        if altitude is not None:
            max_altitude = max(max_altitude, altitude)
        if _bool(row["frame_captured"], "frame_captured", where) and _bool(
            row["geotagged"], "geotagged", where
        ):
            if altitude is None:
                raise EvidenceError(f"{where}: a geotagged frame needs a valid fix")
            if altitude >= STRATOSPHERE_THRESHOLD_M:
                frames_above += 1
        if row["state"].strip().lower() == "landed":
            landed = True
        # Gaps are judged in flight only: once landed the package is in
        # beacon cadence by design, and that is not a telemetry gap.
        if not landed and _bool(row["telemetry_received"], "telemetry_received", where):
            if last_rx is not None:
                max_gap = max(max_gap, t - last_rx)
            last_rx = t
    if max_altitude == -math.inf:
        raise EvidenceError(f"{context}: no valid fix in the whole log")
    if last_rx is None:
        raise EvidenceError(f"{context}: no telemetry received in the whole log")
    recovered = _bool(manifest["recovered"], "recovered", context)
    if recovered and not landed:
        raise EvidenceError(f"{context}: manifest says recovered but the log never reached landed")
    if recovered and not _bool(manifest["storage_checksum_verified"], "storage_checksum_verified", context):
        raise EvidenceError(f"{context}: recovered package without a verified storage checksum")

    dx = _float(manifest["recovery_x_km"], "recovery_x_km", context) - _float(
        manifest["predicted_landing_x_km"], "predicted_landing_x_km", context
    )
    dy = _float(manifest["recovery_y_km"], "recovery_y_km", context) - _float(
        manifest["predicted_landing_y_km"], "predicted_landing_y_km", context
    )
    return {
        "max_altitude_m": max_altitude,
        "geotagged_frames_above_threshold": frames_above,
        "telemetry_gap_max_s": max_gap,
        "payload_recovered": int(recovered),
        "landing_error_km": math.hypot(dx, dy),
        "airspace_authorisation_on_file": int(bool(str(manifest["airspace_coordination_ref"]).strip())),
        "third_party_contacts": int(_float(manifest["third_party_contacts"], "third_party_contacts", context)),
    }


def reduce_flights(
    flights: list[tuple[list[dict[str, str]], dict[str, object]]],
    trials: list[dict[str, str]],
) -> dict[str, object]:
    """S0-C metrics across every flight, judged at the worst flight."""

    if not flights:
        raise EvidenceError("no flights")
    per_flight = []
    kinds = set()
    run_ids = set()
    for rows, manifest in flights:
        context = f"flight {manifest.get('run_id', '?')}"
        per_flight.append(reduce_flight(rows, manifest, context))
        kinds.add(str(manifest["evidence_kind"]))
        run_ids.add(str(manifest["run_id"]))
    if len(run_ids) != len(flights):
        raise EvidenceError("flights must carry distinct run_ids")
    metrics: dict[str, object] = {
        "sounding_flights": len(flights),
        "max_altitude_m": min(f["max_altitude_m"] for f in per_flight),
        "geotagged_frames_above_threshold": min(
            f["geotagged_frames_above_threshold"] for f in per_flight
        ),
        "telemetry_gap_max_s": max(f["telemetry_gap_max_s"] for f in per_flight),
        "payload_recovered": int(all(f["payload_recovered"] for f in per_flight)),
        "landing_error_km": max(f["landing_error_km"] for f in per_flight),
        "airspace_authorisation_on_file": int(
            all(f["airspace_authorisation_on_file"] for f in per_flight)
        ),
        "third_party_contacts": sum(int(f["third_party_contacts"]) for f in per_flight),
    }
    metrics.update(
        {
            key: value
            for key, value in reduce_trials(trials).items()
            if key.startswith("termination")
        }
    )
    metrics["evidence_kind"] = "flown" if kinds == {"flown"} else ",".join(sorted(kinds))
    return metrics


# ----------------------------------------------------------------------
# S0-B: tethered ascents
# ----------------------------------------------------------------------

TETHERED_MANIFEST_FIELDS = (
    "run_id",
    "article_rev",
    "git_commit",
    "evidence_kind",
    "images_downlinked",
    "parachute_deployments",
    "parachute_failures",
    "crew_contacts",
)


def reduce_tethered_ascent(
    rows: list[dict[str, str]], manifest: dict[str, object], context: str = "ascent"
) -> dict[str, float | int]:
    """Metrics for one tethered ascent from its log and ground-side manifest."""

    _require_columns(rows, FLIGHT_LOG_REQUIRED, context)
    _require_manifest(manifest, TETHERED_MANIFEST_FIELDS, context)
    last_rx: float | None = None
    max_gap = 0.0
    previous_t: float | None = None
    for index, row in enumerate(rows):
        where = f"{context} row {index + 1}"
        t = _float(row["t_s"], "t_s", where)
        if previous_t is not None and t < previous_t:
            raise EvidenceError(f"{where}: t_s is not monotonic")
        previous_t = t
        if _bool(row["telemetry_received"], "telemetry_received", where):
            if last_rx is not None:
                max_gap = max(max_gap, t - last_rx)
            last_rx = t
    if last_rx is None:
        raise EvidenceError(f"{context}: no telemetry received in the whole log")
    deployments = int(_float(manifest["parachute_deployments"], "parachute_deployments", context))
    failures = int(_float(manifest["parachute_failures"], "parachute_failures", context))
    if failures > deployments:
        raise EvidenceError(f"{context}: more parachute failures than deployments")
    return {
        "end_to_end_images_downlinked": int(
            _float(manifest["images_downlinked"], "images_downlinked", context)
        ),
        "position_report_gap_max_s": max_gap,
        "parachute_deployments": deployments,
        "parachute_failures": failures,
        "crew_contacts": int(_float(manifest["crew_contacts"], "crew_contacts", context)),
    }


def reduce_tethered(
    ascents: list[tuple[list[dict[str, str]], dict[str, object]]],
    trials: list[dict[str, str]],
) -> dict[str, object]:
    """S0-B metrics across every tethered ascent."""

    if not ascents:
        raise EvidenceError("no tethered ascents")
    per = []
    kinds = set()
    run_ids = set()
    for rows, manifest in ascents:
        context = f"ascent {manifest.get('run_id', '?')}"
        per.append(reduce_tethered_ascent(rows, manifest, context))
        kinds.add(str(manifest["evidence_kind"]))
        run_ids.add(str(manifest["run_id"]))
    if len(run_ids) != len(ascents):
        raise EvidenceError("ascents must carry distinct run_ids")
    metrics: dict[str, object] = {
        "tethered_flights": len(ascents),
        "end_to_end_images_downlinked": sum(int(a["end_to_end_images_downlinked"]) for a in per),
        "position_report_gap_max_s": max(a["position_report_gap_max_s"] for a in per),
        "parachute_deployments": sum(int(a["parachute_deployments"]) for a in per),
        "parachute_failures": sum(int(a["parachute_failures"]) for a in per),
        "crew_contacts": sum(int(a["crew_contacts"]) for a in per),
    }
    metrics.update(
        {k: v for k, v in reduce_trials(trials).items() if k.startswith("termination")}
    )
    metrics["evidence_kind"] = "flown" if kinds == {"flown"} else ",".join(sorted(kinds))
    return metrics


# ----------------------------------------------------------------------
# S0-A: bench and cold chamber
# ----------------------------------------------------------------------


def reduce_chamber(
    soak: list[dict[str, str]],
    trials: list[dict[str, str]],
    drops: list[dict[str, str]],
    manifest: dict[str, object],
) -> dict[str, object]:
    _require_columns(soak, SOAK_FIELDS, "soak")
    _require_columns(drops, DROP_FIELDS, "drops")
    _require_manifest(manifest, BENCH_MANIFEST_FIELDS, "bench")

    times = []
    min_temp = math.inf
    dropouts = 0
    captures = 0
    for index, row in enumerate(soak):
        where = f"soak row {index + 1}"
        times.append(_float(row["t_s"], "t_s", where))
        min_temp = min(min_temp, _float(row["internal_temp_c"], "internal_temp_c", where))
        ok = all(_bool(row[field], field, where) for field in ("imaging_ok", "tracking_ok", "termination_ok"))
        if not ok:
            dropouts += 1
        if _bool(row["frame_stored"], "frame_stored", where):
            captures += 1
    if times != sorted(times):
        raise EvidenceError("soak: t_s is not monotonic")

    rates = [_float(row["descent_rate_m_s"], "descent_rate_m_s", f"drop {row['drop_id']}") for row in drops]

    metrics: dict[str, object] = {
        "payload_package_mass_kg": _float(
            manifest["payload_package_mass_kg"], "payload_package_mass_kg", "bench"
        ),
        "cold_soak_hours": (times[-1] - times[0]) / 3600.0,
        "cold_soak_min_temp_c": min_temp,
        "cold_soak_functional_dropouts": dropouts,
        "imaging_chain_captures": captures,
        "parachute_descent_rate_m_s": max(rates),
    }
    metrics.update(reduce_trials(trials))
    metrics["evidence_kind"] = str(manifest["evidence_kind"])
    return metrics


# ----------------------------------------------------------------------
# Verdicts and CLI
# ----------------------------------------------------------------------


def verdict(gate_id: str, metrics: dict[str, object]) -> dict[str, object]:
    numeric = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    result = evaluate_gate(gate_id, numeric)
    return {
        "gate": gate_id,
        "evidence_kind": metrics.get("evidence_kind"),
        "closes_requirements": result.passed and metrics.get("evidence_kind") in ("flown", "bench"),
        "passed": result.passed,
        "failed_criteria": list(result.failed_criteria),
        "missing_metrics": list(result.missing_metrics),
        "metrics": numeric,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reduce STRATO-P0 evidence to gate metrics.")
    sub = parser.add_subparsers(dest="command", required=True)

    flight = sub.add_parser("flight", help="S0-C: one or more free flights")
    flight.add_argument("--log", type=Path, action="append", required=True)
    flight.add_argument("--manifest", type=Path, action="append", required=True)
    flight.add_argument("--trials", type=Path, required=True)

    tethered = sub.add_parser("tethered", help="S0-B: tethered ascents")
    tethered.add_argument("--log", type=Path, action="append", required=True)
    tethered.add_argument("--manifest", type=Path, action="append", required=True)
    tethered.add_argument("--trials", type=Path, required=True)

    chamber = sub.add_parser("chamber", help="S0-A: bench and cold chamber")
    chamber.add_argument("--soak", type=Path, required=True)
    chamber.add_argument("--trials", type=Path, required=True)
    chamber.add_argument("--drops", type=Path, required=True)
    chamber.add_argument("--manifest", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "flight":
            if len(args.log) != len(args.manifest):
                raise EvidenceError("each --log needs one --manifest, in order")
            flights = [
                (read_csv(log), read_manifest(manifest))
                for log, manifest in zip(args.log, args.manifest)
            ]
            report = verdict("S0-C", reduce_flights(flights, read_csv(args.trials)))
        elif args.command == "tethered":
            if len(args.log) != len(args.manifest):
                raise EvidenceError("each --log needs one --manifest, in order")
            ascents = [
                (read_csv(log), read_manifest(manifest))
                for log, manifest in zip(args.log, args.manifest)
            ]
            report = verdict("S0-B", reduce_tethered(ascents, read_csv(args.trials)))
        else:
            report = verdict(
                "S0-A",
                reduce_chamber(
                    read_csv(args.soak),
                    read_csv(args.trials),
                    read_csv(args.drops),
                    read_manifest(args.manifest),
                ),
            )
    except EvidenceError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
