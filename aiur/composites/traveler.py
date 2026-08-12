"""Manufacturing controls: travelers, hold points, and prepreg out-time.

A traveler is the document that follows a part through the shop and comes
back with signatures on it.  It is the only artefact that connects a cured
part to the conditions that made it, and a program that cannot answer "what
was different about that one" is a program that cannot fix a yield problem.

This module makes the traveler executable.  The step list is data, the
acceptance rules are code, and a completed traveler record is *evaluated*
rather than filed — so a missing signature, an out-of-sequence step, a
skipped hold point, or an expired material is a computed nonconformance
instead of something a reviewer might notice.

Three controls do most of the work:

**Hold points.**  A step marked as a hold cannot be passed by the person who
performed it.  Layup verification before bagging is the canonical one: after
the bag goes on, the ply count and orientations are unverifiable forever, and
an ultrasonic inspection of a cured part cannot tell you a ply was laid at 0
instead of 45.  The hold exists because the evidence is destroyed by the next
step.

**Out-time.**  Prepreg advances at room temperature — slowly, but it does
advance, and the clock does not reset when it goes back in the freezer.
Exceeding the out-time limit gives a resin that no longer flows properly:
the part comes out porous and resin-starved, the cure looks normal, and
nothing in the finished part records why.  So out-time is tracked
cumulatively across every exposure, and it is the single most commonly
falsified number in composites manufacturing precisely because it is
inconvenient.

**Traceability.**  Lot, roll, and freezer log, tied to the panel record and
the cure run.  Without it, an allowable computed from coupons cannot be
claimed to apply to a part, because nothing links them.

The step list here is the real one for the P0 parts, in order, with the
inspections that the inspection spec calls out attached at the points where
the evidence still exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json

#: Cumulative room-temperature out-time allowed on the 180 degC prepreg
#: before it is scrapped, hours.  Engineering target standing in for a
#: supplier limit; DOE-1's aged-prepreg arm is what makes it a measurement.
OUT_TIME_LIMIT_H = 240.0
#: Out-time at which the material is restricted to non-structural use.
OUT_TIME_WARNING_H = 200.0
#: Minimum thaw time before a sealed roll may be opened, hours.  Opening a
#: cold roll condenses atmospheric water onto the prepreg, and that water
#: becomes steam-driven porosity at cure — a defect whose cause is invisible
#: in the finished part and unarguable in the traveler.
MIN_THAW_H = 8.0


class StepType(str, Enum):
    MATERIAL = "material"
    PREPARATION = "preparation"
    LAYUP = "layup"
    CURE = "cure"
    MACHINING = "machining"
    INSPECTION = "inspection"


@dataclass(frozen=True)
class TravelerStep:
    """One numbered operation on the traveler."""

    step_id: str
    step_type: StepType
    title: str
    instruction: str
    #: Specification this step is performed to.
    spec_ref: str
    #: True when a second person must sign before work continues.
    hold_point: bool = False
    #: Why the hold exists.  A hold point without a stated reason gets
    #: negotiated away the first time the shop is busy.
    hold_reason: str = ""
    #: Fields the operator must record. A step that records nothing cannot
    #: contribute to a yield investigation later.
    records: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.hold_point and not self.hold_reason:
            raise ValueError(f"{self.step_id}: a hold point must state why it exists")


TRAVELER_STEPS: tuple[TravelerStep, ...] = (
    TravelerStep(
        "OP-05", StepType.MATERIAL, "material issue and thaw",
        "Draw the sealed roll from the freezer, record lot and roll, and thaw "
        "sealed to room temperature before breaking the bag.",
        "PS-100", hold_point=False,
        records=("lot_id", "roll_id", "removed_from_freezer_at", "bag_opened_at",
                 "cumulative_out_time_h"),
    ),
    TravelerStep(
        "OP-10", StepType.PREPARATION, "tool preparation",
        "Clean the tool, verify the moulding surface against the surface "
        "criteria, and apply release per the tool log. Record the release "
        "system and the number of cures since the last full strip.",
        "PS-100",
        records=("tool_id", "release_system", "cures_since_strip"),
    ),
    TravelerStep(
        "OP-20", StepType.LAYUP, "ply cutting and kitting",
        "Cut plies to the flat patterns with the fibre direction indexed to "
        "the pattern's zero mark. Kit in lay-down order, top ply last.",
        "PS-100",
        records=("kit_id", "plies_cut", "operator"),
    ),
    TravelerStep(
        "OP-30", StepType.LAYUP, "layup with scheduled debulks",
        "Lay up to the part's laminate schedule, debulking at the scheduled "
        "ply counts under full vacuum for the specified dwell.",
        "PS-100",
        records=("debulk_cycles", "vacuum_kpa", "operator"),
    ),
    TravelerStep(
        "OP-35", StepType.INSPECTION, "layup verification",
        "Second person verifies ply count, orientation of each ply against "
        "the schedule, and the absence of foreign object debris.",
        "PS-300", hold_point=True,
        hold_reason=(
            "after the bag goes on, ply count and orientation are unverifiable "
            "for the life of the part: no cured-part inspection method "
            "distinguishes a ply laid at 0 from one laid at 45"
        ),
        records=("verified_ply_count", "verified_orientations", "inspector"),
    ),
    TravelerStep(
        "OP-40", StepType.CURE, "bagging and leak check",
        "Bag with the specified bleeder and breather stack. Hold vacuum and "
        "verify the leak rate against the limit before the oven is loaded.",
        "PS-200", hold_point=True,
        hold_reason=(
            "a bag that leaks during cure produces a porous part and the leak "
            "cannot be detected afterwards; the check is worthless once the "
            "cure has started"
        ),
        records=("vacuum_kpa", "leak_rate_kpa_per_5min", "inspector"),
    ),
    TravelerStep(
        "OP-50", StepType.CURE, "cure",
        "Run the qualified cure cycle. Thermocouples on the part, not on the "
        "oven air. Record the full part trace and the pressure application "
        "time against the computed flow window.",
        "PS-200",
        records=("cure_cycle_id", "run_id", "part_thermocouple_trace",
                 "pressure_applied_at_min", "max_part_temperature_c"),
    ),
    TravelerStep(
        "OP-60", StepType.MACHINING, "demould and trim",
        "Demould, trim to the net-trim line, and deburr. Record demould "
        "condition and any tool damage before the tool goes back on the shelf.",
        "PS-100",
        records=("demould_condition", "tool_condition", "operator"),
    ),
    TravelerStep(
        "OP-70", StepType.INSPECTION, "dimensional and constituent inspection",
        "Thickness map, moulded angle check against the compensated nominal, "
        "mass, and a density coupon from the trim offcut.",
        "PS-300",
        records=("thickness_map", "moulded_angle_deg", "part_mass_g",
                 "coupon_density_g_cm3", "inspector"),
    ),
    TravelerStep(
        "OP-80", StepType.INSPECTION, "acceptance",
        "Reduce the constituent data, evaluate against the acceptance limits, "
        "and disposition the part.",
        "PS-300", hold_point=True,
        hold_reason="the part is not released to assembly on an operator's signature alone",
        records=("void_fraction", "fibre_volume_fraction", "disposition", "inspector"),
    ),
)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StepRecord:
    """A completed traveler step as signed on the shop floor."""

    step_id: str
    operator: str
    #: Second signature; required on hold points and refused elsewhere when
    #: it matches the operator.
    inspector: str = ""
    values: dict[str, object] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class TravelerRecord:
    """One part's complete traveler."""

    serial: str
    part_id: str
    lot_id: str
    roll_id: str
    #: Cumulative room-temperature out-time on the material at layup, hours.
    cumulative_out_time_h: float
    #: Hours the sealed roll was allowed to thaw before opening.
    thaw_time_h: float
    cure_cycle_id: str
    steps: tuple[StepRecord, ...] = ()


@dataclass(frozen=True)
class Nonconformance:
    """A computed departure from the process, not an opinion about one."""

    serial: str
    code: str
    detail: str
    #: Critical nonconformances make the part unusable rather than reworkable.
    critical: bool


def evaluate_traveler(record: TravelerRecord) -> list[Nonconformance]:
    """Evaluate a completed traveler against the process controls."""

    findings: list[Nonconformance] = []
    by_id = {step.step_id: step for step in TRAVELER_STEPS}
    recorded = {step.step_id: step for step in record.steps}

    # Material controls first: they invalidate everything downstream.
    if record.cumulative_out_time_h > OUT_TIME_LIMIT_H:
        findings.append(
            Nonconformance(
                record.serial, "NCR-OUTTIME",
                f"cumulative out-time {record.cumulative_out_time_h:g} h exceeds the "
                f"{OUT_TIME_LIMIT_H:g} h limit; the resin no longer flows to "
                "specification and the part cannot be accepted on inspection",
                critical=True,
            )
        )
    elif record.cumulative_out_time_h > OUT_TIME_WARNING_H:
        findings.append(
            Nonconformance(
                record.serial, "NCR-OUTTIME-WARN",
                f"cumulative out-time {record.cumulative_out_time_h:g} h is past the "
                f"{OUT_TIME_WARNING_H:g} h restriction point; non-structural use only",
                critical=False,
            )
        )
    if record.thaw_time_h < MIN_THAW_H:
        findings.append(
            Nonconformance(
                record.serial, "NCR-THAW",
                f"roll opened after {record.thaw_time_h:g} h of thaw against a "
                f"{MIN_THAW_H:g} h minimum; condensed moisture drives cure porosity",
                critical=True,
            )
        )
    if not record.lot_id or not record.roll_id:
        findings.append(
            Nonconformance(
                record.serial, "NCR-TRACE",
                "material lot or roll not recorded; the part cannot be tied to any "
                "allowable and is not traceable",
                critical=True,
            )
        )

    # Step completeness, order, and signatures.
    missing = [step.step_id for step in TRAVELER_STEPS if step.step_id not in recorded]
    if missing:
        findings.append(
            Nonconformance(
                record.serial, "NCR-INCOMPLETE",
                f"steps not signed: {', '.join(missing)}",
                critical=True,
            )
        )

    order = [step.step_id for step in TRAVELER_STEPS]
    signed_order = [step.step_id for step in record.steps if step.step_id in by_id]
    expected_positions = [order.index(step_id) for step_id in signed_order]
    if expected_positions != sorted(expected_positions):
        findings.append(
            Nonconformance(
                record.serial, "NCR-SEQUENCE",
                "steps signed out of sequence; the traveler does not describe what "
                "happened to the part",
                critical=True,
            )
        )

    for step_record in record.steps:
        step = by_id.get(step_record.step_id)
        if step is None:
            findings.append(
                Nonconformance(
                    record.serial, "NCR-UNKNOWN-STEP",
                    f"{step_record.step_id} is not a step in this traveler",
                    critical=False,
                )
            )
            continue
        if step.hold_point:
            if not step_record.inspector:
                findings.append(
                    Nonconformance(
                        record.serial, "NCR-HOLD",
                        f"{step.step_id} is a hold point with no second signature: "
                        f"{step.hold_reason}",
                        critical=True,
                    )
                )
            elif step_record.inspector == step_record.operator:
                findings.append(
                    Nonconformance(
                        record.serial, "NCR-HOLD-SELF",
                        f"{step.step_id} was verified by the person who performed it; "
                        "a hold point requires an independent second signature",
                        critical=True,
                    )
                )
        absent = [name for name in step.records if name not in step_record.values]
        if absent:
            findings.append(
                Nonconformance(
                    record.serial, "NCR-RECORD",
                    f"{step.step_id} missing required records: {', '.join(absent)}",
                    critical=False,
                )
            )
    return findings


def disposition(findings: list[Nonconformance]) -> str:
    if any(finding.critical for finding in findings):
        return "reject"
    if findings:
        return "use-as-is pending review"
    return "accept"


def validate_traveler_definition() -> list[str]:
    """Structural checks on the traveler definition itself."""

    errors: list[str] = []
    seen: set[str] = set()
    for step in TRAVELER_STEPS:
        if step.step_id in seen:
            errors.append(f"{step.step_id}: duplicate step id")
        seen.add(step.step_id)
        if not step.records:
            errors.append(
                f"{step.step_id}: records nothing; a step that records nothing cannot "
                "contribute to a yield investigation"
            )
        if not step.spec_ref:
            errors.append(f"{step.step_id}: no specification reference")
    # Every inspection that destroys its own evidence downstream must be a
    # hold point.  Layup verification is the one that matters most.
    if not any(step.step_id == "OP-35" and step.hold_point for step in TRAVELER_STEPS):
        errors.append("OP-35 layup verification must remain a hold point")
    return errors


#: A worked traveler for a part that was built slightly wrong, kept so the
#: evaluation path is exercised by CI and so a reviewer can see what the
#: output looks like when something is off.
EXAMPLE_RECORD = TravelerRecord(
    serial="CS-400-SN003",
    part_id="CS-400",
    lot_id="LOT-2411-A",
    roll_id="R-0007",
    cumulative_out_time_h=212.0,
    thaw_time_h=10.0,
    cure_cycle_id="CC-180-STD",
    steps=tuple(
        StepRecord(
            step.step_id,
            operator="A. Operator",
            inspector=("A. Operator" if step.step_id == "OP-35" else "B. Inspector")
            if step.hold_point
            else "",
            values={name: "recorded" for name in step.records},
        )
        for step in TRAVELER_STEPS
    ),
)


def snapshot() -> dict[str, object]:
    errors = validate_traveler_definition()
    findings = evaluate_traveler(EXAMPLE_RECORD)
    return {
        "valid": not errors,
        "errors": errors,
        "material_controls": {
            "out_time_limit_h": OUT_TIME_LIMIT_H,
            "out_time_warning_h": OUT_TIME_WARNING_H,
            "min_thaw_h": MIN_THAW_H,
            "basis": "engineering targets standing in for supplier limits",
        },
        "steps": [
            {**asdict(step), "step_type": step.step_type.value} for step in TRAVELER_STEPS
        ],
        "hold_points": [step.step_id for step in TRAVELER_STEPS if step.hold_point],
        "example_evaluation": {
            "serial": EXAMPLE_RECORD.serial,
            "findings": [asdict(finding) for finding in findings],
            "disposition": disposition(findings),
        },
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
