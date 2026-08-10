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
    #: True when violating this criterion means something was damaged, struck,
    #: dropped, or contacted — as opposed to a rate or quota that only means
    #: the evidence is thin.  Safety criteria hold at any sample size, so the
    #: pre-merge screen enforces exactly these.
    #:
    #: It is a declared property rather than one inferred from the operator.
    #: Inferring "== 0" missed max_contact_closing_m_s <= 0.20, whose
    #: violation is a real contact above the closing-speed limit but which
    #: does not raise an unsafe event unless it also exceeds the bounce
    #: threshold — so the screen silently skipped the one criterion that
    #: catches a too-fast capture.
    safety: bool = False

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


#: Expected capture/release cycles the Rev-A article must survive to carry the
#: program through P0-D, itemized so the life-test requirement is derived
#: rather than a round number:
#:
#:   bench development, fit, and rehearsal   ~50
#:   P0-B run sets (10 attempts x sets+retry) ~100
#:   P0-C run sets                            ~100
#:   P0-D sequences (two aircraft)            ~40
#:   contingency for re-runs after changes    ~10
#:                                            ----
#:   expected operational cycles              ~300
#:
#: Mechanism practice multiplies expected cycles by a life factor before
#: declaring a design life-tested.  A factor of 2.0 is the low end of that
#: range and is used here because the article is room-temperature, ground-
#: accessible, and cheap to reprint; the resulting requirement is 600 cycles.
#: This derivation is an engineering target until P0-B/P0-C actual cycle
#: counts replace the estimates.
EXPECTED_OPERATIONAL_CYCLES = 300
LIFE_TEST_FACTOR = 2.0
DERIVED_LIFE_TEST_CYCLES = int(EXPECTED_OPERATIONAL_CYCLES * LIFE_TEST_FACTOR)

#: Force-margin factor required of the keeper drive against worst-case
#: measured resistance at minimum supply voltage.  Mechanism practice
#: requires the actuator to demonstrate at least twice the force needed;
#: an actuator that merely "worked once" has no demonstrated margin.
KEEPER_FORCE_MARGIN_FACTOR = 2.0

#: Electrical fault modes the bench fault-insertion unit must exercise, each
#: paired with a required response written before the trial.  The set mirrors
#: the twin's fault menu so a hardware trial and its simulated counterpart can
#: be compared directly.  The gate criterion counts this list rather than a
#: literal, because the two drifted apart the first time a mode was added.
REQUIRED_FAULT_MODES: tuple[str, ...] = (
    "S1_OPEN",
    "S1_SHORT",
    "S2_OPEN",
    "S2_SHORT",
    "S1_S2_BOTH_OPEN",
    "SERVO_POWER_LOSS",
    "SERVO_STALL",
    "CONTROLLER_RESET_DURING_LOCK",
    # Distinct from the mode above: resetting during LOCKING risks nothing,
    # because nothing is retained yet.  Resetting while an aircraft hangs from
    # the keeper is the case that can drop it, and it is what a brownout
    # during a docked cruise actually produces.
    "CONTROLLER_RESET_WHILE_CAPTURED",
)

#: The physical kill path (carrier propulsion disable + release inhibit) is
#: held to a higher standard than the autonomy it protects: it must be
#: demonstrated end-to-end before every session and must still work with the
#: autonomy computer powered off, because "the computer is confused" is
#: exactly the case it exists for.  Applied to every gate that flies an
#: aircraft; P0-A has no propulsion to kill.
KILL_PATH_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "kill_path_preflight_checks",
        ">=",
        1,
        "kill path demonstrated end-to-end before the run set",
    ),
    Criterion("kill_path_failures", "==", 0, "kill path never fails when commanded"),
    Criterion(
        "kill_path_verified_with_autonomy_off",
        "==",
        1,
        "kill path demonstrated with the autonomy computer powered off",
    ),
)

GATES: tuple[Gate, ...] = (
    Gate(
        "P0-A",
        "bench capture",
        Stage.BENCH_HIL,
        (
            Criterion(
                "run_in_cycles",
                ">=",
                15,
                "run-in completed before life-test cycling begins",
            ),
            Criterion(
                "run_in_force_trend_stabilized",
                "==",
                1,
                "per-cycle insertion/release force leveled off during run-in",
            ),
            Criterion(
                "life_test_cycles",
                ">=",
                DERIVED_LIFE_TEST_CYCLES,
                "derived life test: expected cycles through P0-D x life factor",
            ),
            Criterion("dock_mass_g", "<=", 180, "dock assembly stays within mass budget", "g"),
            Criterion("probe_mass_g", "<=", 8, "drone-side probe stays within mass budget", "g"),
            Criterion(
                "axial_screen_load_held_n",
                ">=",
                5.0,
                "positive keeper holds the P0 axial screening load",
                "N",
            ),
            Criterion(
                "lateral_screen_load_held_n",
                ">=",
                1.0,
                "positive keeper holds the P0 lateral screening load",
                "N",
            ),
            Criterion(
                "keeper_close_force_margin",
                ">=",
                KEEPER_FORCE_MARGIN_FACTOR,
                "keeper closes with demonstrated force margin at minimum voltage",
            ),
            Criterion(
                "keeper_open_force_margin",
                ">=",
                KEEPER_FORCE_MARGIN_FACTOR,
                "keeper opens with demonstrated force margin at minimum voltage",
            ),
            Criterion("structural_failures", "==", 0, "no structural failures"),
            Criterion(
                "ambiguous_capture_confirmations",
                "==",
                0,
                "capture confirmation is unambiguous",
            ),
            Criterion(
                "emergency_release_trials",
                ">=",
                10,
                "at least 10 unloaded emergency-release trials",
            ),
            Criterion(
                "emergency_release_failures",
                "==",
                0,
                "manual emergency release always works unloaded",
            ),
            Criterion(
                "loaded_emergency_release_trials",
                ">=",
                10,
                "at least 10 emergency releases under the axial screening load",
            ),
            Criterion(
                "loaded_emergency_release_failures",
                "==",
                0,
                "emergency release works while the mechanism is loaded",
            ),
            Criterion(
                "fault_insertion_trials",
                ">=",
                len(REQUIRED_FAULT_MODES),
                "every insertable electrical fault mode exercised on hardware",
            ),
            Criterion(
                "fault_insertion_unsafe_responses",
                "==",
                0,
                "every inserted fault produced its required safe response",
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
            Criterion(
                "fault_insertion_trials",
                ">=",
                5,
                "hardware fault insertion exercised with a live aircraft",
            ),
            Criterion(
                "fault_insertion_unsafe_responses",
                "==",
                0,
                "every inserted fault produced its required safe response",
            ),
            *KILL_PATH_CRITERIA,
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
            *KILL_PATH_CRITERIA,
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
            *KILL_PATH_CRITERIA,
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
    """Evaluate one P0 hardware gate from measured metrics."""

    return evaluate_gate_definition(gate_by_id(gate_id), metrics)


def evaluate_gate_definition(
    gate: Gate,
    metrics: Mapping[str, float | int | bool],
) -> GateVerdict:
    """Evaluate any gate definition from measured metrics.

    Shared by the hardware gates above and the SIL gates in ``aiur.sim``:
    both must go through the same rule that missing evidence is a failed
    gate, never an implicit pass.
    """

    missing: list[str] = []
    failed: list[str] = []

    for criterion in gate.criteria:
        if criterion.metric not in metrics:
            missing.append(criterion.metric)
            continue
        if not criterion.passes(metrics[criterion.metric]):
            failed.append(criterion.description)

    return GateVerdict(
        gate_id=gate.gate_id,
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
