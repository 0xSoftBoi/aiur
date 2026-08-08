"""Executable development-loop contract for CARRIER-P0.

The graph is intentionally small.  It describes how evidence is allowed to move
the prototype from a requirement to flight and back into the next engineering
iteration.  A changed article never jumps straight back to flight.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Mapping


class Stage(str, Enum):
    REQUIREMENT = "requirement"
    SIL = "sil"
    BENCH_HIL = "bench_hil"
    TETHERED_FLIGHT = "tethered_flight"
    DEBRIEF = "debrief"
    DISPOSITION = "disposition"


@dataclass(frozen=True)
class Edge:
    source: Stage
    target: Stage
    event: str


ENGINEERING_LOOP: tuple[Edge, ...] = (
    Edge(Stage.REQUIREMENT, Stage.SIL, "requirement_is_testable"),
    Edge(Stage.SIL, Stage.BENCH_HIL, "model_and_fault_injection_pass"),
    Edge(Stage.BENCH_HIL, Stage.TETHERED_FLIGHT, "bench_gate_pass"),
    Edge(Stage.TETHERED_FLIGHT, Stage.DEBRIEF, "run_set_complete_or_aborted"),
    Edge(Stage.DEBRIEF, Stage.DISPOSITION, "evidence_packet_complete"),
    Edge(Stage.DISPOSITION, Stage.REQUIREMENT, "advance_or_change_requirement"),
    Edge(Stage.DISPOSITION, Stage.SIL, "model_or_software_changed"),
    Edge(Stage.DISPOSITION, Stage.BENCH_HIL, "hardware_or_instrumentation_changed"),
    Edge(
        Stage.DISPOSITION,
        Stage.TETHERED_FLIGHT,
        "repeat_exact_configuration_for_more_evidence",
    ),
)


@dataclass(frozen=True)
class Criterion:
    metric: str
    operator: str
    threshold: float
    description: str
    unit: str = "count"

    def passes(self, value: float | int | bool) -> bool:
        if not isinstance(value, (int, float, bool)):
            raise TypeError(f"metric {self.metric!r} must be numeric or boolean")

        if self.operator == ">=":
            return value >= self.threshold
        if self.operator == "<=":
            return value <= self.threshold
        if self.operator == "==":
            return value == self.threshold
        raise ValueError(f"unsupported operator: {self.operator}")


@dataclass(frozen=True)
class Gate:
    gate_id: str
    name: str
    stage: Stage
    criteria: tuple[Criterion, ...]


GATES: tuple[Gate, ...] = (
    Gate(
        "P0-A",
        "bench capture",
        Stage.BENCH_HIL,
        (
            Criterion("manual_cycles", ">=", 50, "50 manual capture/release cycles"),
            Criterion("structural_failures", "==", 0, "no structural failures"),
            Criterion(
                "ambiguous_capture_confirmations",
                "==",
                0,
                "capture confirmation is unambiguous",
            ),
            Criterion(
                "emergency_release_failures",
                "==",
                0,
                "manual emergency release always works",
            ),
            Criterion("propellers_installed", "==", 0, "propellers are removed"),
        ),
    ),
    Gate(
        "P0-B",
        "moving suspended dock",
        Stage.BENCH_HIL,
        (
            Criterion("consecutive_attempts", ">=", 10, "10 consecutive attempts"),
            Criterion("captures_last_10", ">=", 9, "at least 9 captures in the last 10"),
            Criterion(
                "max_closing_speed_m_s",
                "<=",
                0.20,
                "closing speed stays inside the capture envelope",
                "m/s",
            ),
            Criterion("prop_funnel_contacts", "==", 0, "no propeller/funnel contact"),
            Criterion(
                "safety_abort_failures",
                "==",
                0,
                "every commanded safety abort succeeds",
            ),
        ),
    ),
    Gate(
        "P0-C",
        "tethered carrier recovery",
        Stage.TETHERED_FLIGHT,
        (
            Criterion("consecutive_attempts", ">=", 10, "10 consecutive recovery attempts"),
            Criterion("captures_last_10", ">=", 9, "at least 9 captures in the last 10"),
            Criterion(
                "max_closing_speed_m_s",
                "<=",
                0.20,
                "closing speed stays inside the capture envelope",
                "m/s",
            ),
            Criterion("envelope_strikes", "==", 0, "no gas-envelope strikes"),
            Criterion("abort_path_failures", "==", 0, "pilot abort path always works"),
            Criterion(
                "full_payload_control_loss_events",
                "==",
                0,
                "no carrier control loss with the complete P0 payload",
            ),
        ),
    ),
    Gate(
        "P0-D",
        "two-aircraft sequencing",
        Stage.TETHERED_FLIGHT,
        (
            Criterion(
                "successful_two_aircraft_sequences",
                ">=",
                1,
                "complete a sequential two-aircraft release/recovery sequence",
            ),
            Criterion("separation_violations", "==", 0, "maintain positive separation"),
            Criterion(
                "simultaneous_dock_approaches",
                "==",
                0,
                "never allow simultaneous approach to the active dock",
            ),
            Criterion("envelope_strikes", "==", 0, "no gas-envelope strikes"),
        ),
    ),
)


@dataclass(frozen=True)
class GateVerdict:
    gate_id: str
    passed: bool
    missing_metrics: tuple[str, ...]
    failed_criteria: tuple[str, ...]


def gate_by_id(gate_id: str) -> Gate:
    for gate in GATES:
        if gate.gate_id == gate_id:
            return gate
    raise KeyError(f"unknown gate: {gate_id}")


def evaluate_gate(
    gate_id: str,
    metrics: Mapping[str, float | int | bool],
) -> GateVerdict:
    """Evaluate one gate from measured metrics.

    Missing evidence is a failed gate, never an implicit pass.
    """

    gate = gate_by_id(gate_id)
    missing: list[str] = []
    failed: list[str] = []

    for criterion in gate.criteria:
        if criterion.metric not in metrics:
            missing.append(criterion.metric)
            continue
        if not criterion.passes(metrics[criterion.metric]):
            failed.append(criterion.description)

    return GateVerdict(
        gate_id=gate_id,
        passed=not missing and not failed,
        missing_metrics=tuple(missing),
        failed_criteria=tuple(failed),
    )


def _reachable_from(start: Stage) -> set[Stage]:
    adjacency: dict[Stage, set[Stage]] = {stage: set() for stage in Stage}
    for edge in ENGINEERING_LOOP:
        adjacency[edge.source].add(edge.target)

    seen: set[Stage] = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(adjacency[node] - seen)
    return seen


def validate_loop_graph() -> tuple[str, ...]:
    """Return structural errors in the engineering-loop definition."""

    errors: list[str] = []
    reachable = _reachable_from(Stage.REQUIREMENT)
    if reachable != set(Stage):
        missing = sorted(stage.value for stage in set(Stage) - reachable)
        errors.append(f"stages unreachable from requirement: {', '.join(missing)}")

    outgoing = {stage: 0 for stage in Stage}
    for edge in ENGINEERING_LOOP:
        outgoing[edge.source] += 1
    dead_ends = sorted(stage.value for stage, count in outgoing.items() if count == 0)
    if dead_ends:
        errors.append(f"stages with no feedback path: {', '.join(dead_ends)}")

    flight_entries = [
        edge for edge in ENGINEERING_LOOP if edge.target is Stage.TETHERED_FLIGHT
    ]
    allowed_flight_entries = {
        (Stage.BENCH_HIL, "bench_gate_pass"),
        (Stage.DISPOSITION, "repeat_exact_configuration_for_more_evidence"),
    }
    for edge in flight_entries:
        if (edge.source, edge.event) not in allowed_flight_entries:
            errors.append(
                "tethered flight has an unsafe shortcut from "
                f"{edge.source.value} via {edge.event}"
            )

    gate_ids = [gate.gate_id for gate in GATES]
    if gate_ids != ["P0-A", "P0-B", "P0-C", "P0-D"]:
        errors.append("P0 gates must remain ordered P0-A through P0-D")

    for gate in GATES:
        metrics = [criterion.metric for criterion in gate.criteria]
        if len(metrics) != len(set(metrics)):
            errors.append(f"{gate.gate_id} contains duplicate metrics")

    return tuple(errors)


def snapshot() -> dict[str, object]:
    return {
        "valid": not validate_loop_graph(),
        "errors": list(validate_loop_graph()),
        "stages": [stage.value for stage in Stage],
        "edges": [
            {
                "source": edge.source.value,
                "target": edge.target.value,
                "event": edge.event,
            }
            for edge in ENGINEERING_LOOP
        ],
        "gates": [
            {
                "gate_id": gate.gate_id,
                "name": gate.name,
                "stage": gate.stage.value,
                "criteria": [asdict(criterion) for criterion in gate.criteria],
            }
            for gate in GATES
        ],
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))

