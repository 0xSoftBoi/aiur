"""SIL gates for the CARRIER-P0 digital twin.

These gates are the executable form of the engineering loop's first stage:
before an article revision goes to the bench, its software must close the
matching SIL gate in the twin.  They deliberately mirror the P0-B/C/D
hardware gates but demand *more* — a simulated campaign is cheap, so the
twin runs hundreds of episodes and requires a fault-injection quota that a
ten-attempt bench session cannot provide.

Two principles carried over from the hardware gates:

* missing evidence fails the gate (enforced by reusing the real
  ``evaluate_gate_definition``);
* safety metrics are absolute zeros — no strike, contact, or unsafe fault
  outcome is acceptable at any campaign size.

A passed SIL gate is a statement about the model, not the vehicle: it means
"the software survives everything the twin knows how to throw at it," and
the twin's knowledge is itself gated by the calibration ledger in
docs/digital-twin.md.
"""

from __future__ import annotations

from typing import Mapping

from ..loop_graph import Criterion, Gate, GateVerdict, Stage, evaluate_gate_definition

SIL_GATES: tuple[Gate, ...] = (
    Gate(
        "SIL-B",
        "simulated moving suspended dock",
        Stage.SIL,
        (
            Criterion("episodes", ">=", 200, "at least 200 seeded episodes"),
            Criterion(
                "nominal_capture_rate_pct",
                ">=",
                95.0,
                "at least 95% capture rate over fault-free episodes",
                "%",
            ),
            Criterion(
                "max_contact_closing_m_s",
                "<=",
                0.20,
                "no funnel contact above the P0 closing-speed limit",
                "m/s",
                safety=True,
            ),
            Criterion(
                "prop_funnel_contacts", "==", 0, "no propeller/funnel contact", safety=True
            ),
            Criterion(
                "overspeed_contacts", "==", 0, "no overspeed probe contact", safety=True
            ),
            Criterion(
                "envelope_strikes", "==", 0, "no gas-envelope strikes", safety=True
            ),
            Criterion("fault_episodes", ">=", 50, "at least 50 fault-injection episodes"),
            Criterion(
                "unsafe_fault_outcomes",
                "==",
                0,
                "every injected fault ends in a safe abort, capture, or landing",
                safety=True,
            ),
        ),
    ),
    Gate(
        "SIL-C",
        "simulated tethered carrier cycle",
        Stage.SIL,
        (
            Criterion("episodes", ">=", 200, "at least 200 seeded episodes"),
            Criterion(
                "nominal_capture_rate_pct",
                ">=",
                95.0,
                "at least 95% full launch/recovery cycles over fault-free episodes",
                "%",
            ),
            Criterion(
                "max_contact_closing_m_s",
                "<=",
                0.20,
                "no funnel contact above the P0 closing-speed limit",
                "m/s",
                safety=True,
            ),
            Criterion(
                "prop_funnel_contacts", "==", 0, "no propeller/funnel contact", safety=True
            ),
            Criterion(
                "overspeed_contacts", "==", 0, "no overspeed probe contact", safety=True
            ),
            Criterion(
                "envelope_strikes", "==", 0, "no gas-envelope strikes", safety=True
            ),
            Criterion("fault_episodes", ">=", 50, "at least 50 fault-injection episodes"),
            Criterion(
                "unsafe_fault_outcomes",
                "==",
                0,
                "every injected fault ends in a safe abort, capture, or landing",
                safety=True,
            ),
        ),
    ),
    Gate(
        "SIL-D",
        "simulated two-aircraft sequencing",
        Stage.SIL,
        (
            Criterion("episodes", ">=", 50, "at least 50 seeded sequences"),
            Criterion(
                "sequence_success_rate_pct",
                ">=",
                90.0,
                "at least 90% complete sequences over fault-free episodes",
                "%",
            ),
            Criterion(
                "separation_violations",
                "==",
                0,
                "positive separation is never lost",
                safety=True,
            ),
            Criterion(
                "simultaneous_dock_approaches",
                "==",
                0,
                "never two aircraft approaching the dock",
                safety=True,
            ),
            Criterion(
                "prop_funnel_contacts", "==", 0, "no propeller/funnel contact", safety=True
            ),
            Criterion(
                "envelope_strikes", "==", 0, "no gas-envelope strikes", safety=True
            ),
            Criterion("fault_episodes", ">=", 10, "at least 10 fault-injection episodes"),
            Criterion(
                "unsafe_fault_outcomes",
                "==",
                0,
                "every injected fault ends in a safe abort, capture, or landing",
                safety=True,
            ),
        ),
    ),
)


def sil_gate_by_id(gate_id: str) -> Gate:
    for gate in SIL_GATES:
        if gate.gate_id == gate_id:
            return gate
    raise KeyError(f"unknown SIL gate: {gate_id}")


def evaluate_sil_gate(
    gate_id: str,
    metrics: Mapping[str, float | int | bool],
) -> GateVerdict:
    """Evaluate one SIL gate through the shared gate evaluator."""

    return evaluate_gate_definition(sil_gate_by_id(gate_id), metrics)


def validate_sil_gates() -> tuple[str, ...]:
    """Structural checks mirroring loop_graph.validate_loop_graph."""

    errors: list[str] = []
    gate_ids = [gate.gate_id for gate in SIL_GATES]
    if gate_ids != ["SIL-B", "SIL-C", "SIL-D"]:
        errors.append("SIL gates must remain ordered SIL-B through SIL-D")
    for gate in SIL_GATES:
        if gate.stage is not Stage.SIL:
            errors.append(f"{gate.gate_id} is not at the SIL stage")
        metrics = [criterion.metric for criterion in gate.criteria]
        if len(metrics) != len(set(metrics)):
            errors.append(f"{gate.gate_id} contains duplicate metrics")
        safety_zeros = {
            "prop_funnel_contacts",
            "envelope_strikes",
            "unsafe_fault_outcomes",
        }
        present = {criterion.metric for criterion in gate.criteria}
        for required in safety_zeros - present:
            errors.append(f"{gate.gate_id} is missing safety metric {required}")
    return tuple(errors)
