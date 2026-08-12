"""Machine-checked requirement closure matrix for CARRIER-P0.

The program already had the two halves of a verification cross-reference
matrix and no index joining them: docs/engineering-loop.md defines the
five-field requirement schema (id, observable, limit, failure response,
evidence source), and ``aiur.loop_graph`` / ``aiur.sim.gates`` evaluate the
gate criteria.  Nothing said *which gate closes which requirement*, so a
requirement could sit open forever, be declared closed in prose without a
named run, or point at a gate criterion that a later edit renamed away.

This module is that index — the VCRM/DVP&R equivalent for a one-article
program.  Every requirement carries its verification method (the standard
test / analysis / inspection / demonstration taxonomy), the loop stage and
gate that close it, an optional link to the exact gate criterion, and either
the evidence that closed it or a written rationale for accepting the
residual.  ``validate_requirements`` is the CI check: closed-without-evidence,
accepted-without-rationale, method-less, and dangling gate/criterion links are
all errors, so requirement drift fails a test instead of decaying quietly.

Contents are seeded from what the repository already states — the targets in
docs/prototype-p0.md, the gate ladder in docs/engineering-loop.md, and the
twin findings in docs/digital-twin.md.  Numeric limits repeated here are the
program's engineering targets, not measured performance; the closure status
is the only claim this file makes about evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

from .loop_graph import GATES, Gate, Stage
from .sim.gates import SIL_GATES


class VerificationMethod(str, Enum):
    """How a requirement is shown to be met (the T/A/I/D taxonomy)."""

    #: Instrumented run against the article; measured values decide.
    TEST = "test"
    #: Model, budget, or calculation; the executable models in this package.
    ANALYSIS = "analysis"
    #: Examination of the article or its records (dimensions, configuration).
    INSPECTION = "inspection"
    #: Observed function under representative conditions, pass/fail by
    #: witness rather than by a measured number.
    DEMONSTRATION = "demonstration"


class ClosureStatus(str, Enum):
    OPEN = "open"
    #: Verification has started and partial evidence exists (a model result, a
    #: unit-tested implementation) but the closing gate has not been run.
    IN_WORK = "in_work"
    CLOSED = "closed"
    #: Deliberately not verified for P0.  Requires a written rationale naming
    #: the exposure and the conditions under which it is revisited.
    ACCEPTED_RISK = "accepted_risk"


@dataclass(frozen=True)
class Requirement:
    """One promoted requirement plus its verification and closure record.

    The first five fields are the schema from docs/engineering-loop.md.  The
    rest are the closure index: how it is verified, where it closes, and what
    closed it.
    """

    id: str
    observable: str
    limit: str
    failure_response: str
    evidence_source: str
    method: VerificationMethod
    stage: Stage
    #: Gate that closes this requirement, from ``GATES`` or ``SIL_GATES``.
    #: ``None`` means no verification path is assigned yet.
    gate_id: str | None = None
    #: Exact criterion metric inside that gate, when the requirement reduces
    #: to a single evaluated metric.  Validated against the gate definition.
    criterion_metric: str | None = None
    status: ClosureStatus = ClosureStatus.OPEN
    #: Required for CLOSED: run_id, reproducible command, commit, or document.
    closing_evidence: str = ""
    #: Required for ACCEPTED_RISK: why the residual is accepted for P0.
    rationale: str = ""


REQUIREMENTS: tuple[Requirement, ...] = (
    # ------------------------------------------------------------------
    # Composite structures.  The dock's flight article is a thin prepreg
    # laminate, and the discipline that produces it carries its own
    # closure problem: the analysis is executable today and the material
    # data underneath it is not measured, so these requirements are
    # deliberately IN_WORK rather than closed by their own models.
    # ------------------------------------------------------------------
    Requirement(
        "P0-CMP-001",
        "structural allowables for every laminate in a flight article",
        "B-basis values from >= 6 specimens across >= 3 material lots; A-basis on "
        "the retention path (CS-400)",
        "no composite part is released to a flight article on handbook lamina data",
        "coupon campaign CP-01..CP-08 in docs/composites/allowables.md, reduced by "
        "`python -m aiur.composites.allowables`",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-CMP-002",
        "laminate schedules against their design rules, mass allocations and load cases",
        "every schedule symmetric, balanced, inside its areal-mass allocation, and "
        "above its required strength ratio; rule breaks carry a written waiver",
        "the composites gate fails and the part is not released to layup",
        "`python -m aiur.composites.schedules`; four schedules, zero failing checks",
        VerificationMethod.ANALYSIS,
        Stage.REQUIREMENT,
        None,
        None,
        ClosureStatus.IN_WORK,
        "aiur/composites/schedules.py, run in CI; closure waits on P0-CMP-001, "
        "because a rule check against unmeasured lamina data verifies the "
        "arithmetic and not the part",
        "",
    ),
    Requirement(
        "P0-CMP-003",
        "cure cycle delivered to the part, measured at the part rather than the oven",
        "cure completeness >= 0.95 of the hold temperature's ceiling; Tg - T_service "
        ">= 30 K; part-to-oven lag <= 15 K; pressure applied inside the computed flow "
        "window",
        "quarantine the parts from that run; the cure the recipe describes is not the "
        "cure the part received",
        "part-thermocouple trace per cure run, against `python -m aiur.composites.cure`",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.IN_WORK,
        "acceptance criteria and two qualified cycles are executable; the kinetic "
        "constants under them are handbook-representative until DOE-1 runs",
        "",
    ),
    Requirement(
        "P0-CMP-004",
        "constituent content of every structural panel",
        "void fraction <= 2.0 % (1.0 % on CS-400); fibre volume fraction 0.50-0.62; "
        "cured ply thickness within +-10 % of nominal",
        "reject the panel; a porous laminate is a different material from the one "
        "that was sized",
        "panel record reduced by `aiur.composites.process.evaluate_panel`, one "
        "density coupon per panel from the trim offcut",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-CMP-005",
        "moulded angle of every functional corner after demould",
        "within +-0.25 deg of nominal after tool compensation",
        "correct the tool from the first-article measurement; reject subsequent "
        "articles that miss",
        "CMM measurement against the compensated tool angle, closed through "
        "`aiur.composites.springin.update_from_measurement`",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-CMP-006",
        "ply count and ply orientation of every laminate",
        "verified against the schedule by a second person before the bag goes on",
        "the part is rejected; after cure this cannot be disproved and will not be "
        "accepted on an operator's signature",
        "traveler hold point OP-35, evaluated by "
        "`aiur.composites.traveler.evaluate_traveler`",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-CMP-006B",
        "sensitivity of a conical part to the fibre-angle drift its own geometry "
        "imposes",
        "in-plane stiffness varying by <= 10 % over the part's full fibre-angle "
        "drift, or a gore count that holds the angle to +-3 deg",
        "the laminate is restacked toward in-plane isotropy; a cone cannot be made "
        "to hold a ply angle by cutting more carefully",
        "`python -m aiur.composites.flatpattern` rotational stiffness envelope "
        "against the developed sector angle",
        VerificationMethod.ANALYSIS,
        Stage.REQUIREMENT,
        None,
        None,
        ClosureStatus.IN_WORK,
        "CS-100 closes at 7 % over a 255 deg drift; the check is executable and "
        "runs in CI, and full closure waits on P0-CMP-001 like every other "
        "analysis here",
        "",
    ),
    Requirement(
        "P0-CMP-006C",
        "qualification route for every structural bonded joint",
        "each joint either out-strengths its adherend by 1.5, or carries 2.0 on "
        "its design load together with a proof test on every article; every "
        "critical joint is proof tested regardless",
        "the joint is not built; an unverifiable bond with neither route has "
        "nothing distinguishing a good bond from a kissing bond before flight",
        "`python -m aiur.composites.bonding`; three joints, each reporting the "
        "route it qualifies on",
        VerificationMethod.ANALYSIS,
        Stage.REQUIREMENT,
        None,
        None,
        ClosureStatus.IN_WORK,
        "the routes are executable and run in CI; the adhesive properties under "
        "them are handbook-representative, and no coupon in the current plan "
        "measures a bonded joint at all — PS-400 records that gap",
        "",
    ),
    Requirement(
        "P0-CMP-006D",
        "adhesive bond workmanship on every structural joint",
        "surface prepared and bonded within one shift, water-break clean before "
        "bonding, bondline thickness recorded, and the article proof tested",
        "reject the joint; a kissing bond has near-zero strength, passes "
        "ultrasonic inspection, and is not detectable by any method this "
        "program holds",
        "bonding traveler records and the proof-test result per article, per "
        "docs/composites/ps-400-bonding.md",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-CMP-007",
        "stowed strain in the deployable capture-ring boom",
        "surface strain at the stowed radius <= 50 % of the fibre-direction ultimate",
        "the boom is not stowed at that radius; increase the radius or thin the laminate",
        "`python -m aiur.composites.schedules` stowage check on CS-200; the knockdown "
        "itself needs a stowage-hold test before flight",
        VerificationMethod.ANALYSIS,
        Stage.REQUIREMENT,
        None,
        None,
        ClosureStatus.IN_WORK,
        "the geometric check is executable and passes at a 16 mm stow radius; the "
        "factor of two on ultimate strain covers creep and stress relaxation over "
        "the stowed dwell and is an engineering target, not a measurement",
        "",
    ),
    Requirement(
        "P0-CMP-008",
        "prepreg cumulative room-temperature out-time at layup",
        "<= 240 h cumulative, tracked across every exposure and not reset by "
        "returning the roll to the freezer",
        "scrap the material; an out-time exceedance produces a porous, starved part "
        "that passes every inspection this program can perform",
        "out-time log per roll, checked by "
        "`aiur.composites.traveler.evaluate_traveler`",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.OPEN,
        "",
        "",
    ),
    Requirement(
        "P0-DOCK-001",
        "funnel entrance diameter of the as-built dock",
        "180 mm engineering target (docs/prototype-p0.md)",
        "reject the article; do not run capture attempts with an undersized funnel",
        "as-built caliper measurement recorded with the P0-A article identity",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
    ),
    Requirement(
        "P0-DOCK-002",
        "terminal closing speed at funnel entry",
        "<= 0.20 m/s",
        "abort approach",
        "synchronized flight + dock telemetry",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-B",
        "max_closing_speed_m_s",
    ),
    Requirement(
        "P0-DOCK-003",
        "commanded closing speed during initial terminal approach",
        "<= 0.10 m/s engineering target, inside the 0.20 m/s envelope limit",
        "hold outside the funnel until the commanded profile is inside the target",
        "commanded-velocity channel of the recovery telemetry",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-B",
    ),
    Requirement(
        "P0-DOCK-004",
        "capture-confirmed assertion versus the two independent switches",
        "capture confirmed only when S1 (seat) AND S2 (keeper closed) are true; "
        "a commanded servo position is never sufficient",
        "hold or abort; never declare capture on a single sensor",
        "dock controller state trace against S1/S2 channels during P0-A cycling",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        "ambiguous_capture_confirmations",
        ClosureStatus.IN_WORK,
    ),
    Requirement(
        "P0-DOCK-005",
        "drone disarm command versus capture-confirmed state",
        "disarm permitted only while capture is confirmed; never on a pose estimate",
        "inhibit disarm and abort the recovery",
        "arm/disarm channel time-aligned with the dock controller state trace",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        None,
        ClosureStatus.IN_WORK,
    ),
    Requirement(
        "P0-DOCK-006",
        "structural damage across the P0-A cycle set",
        "0 structural failures",
        "stop the campaign; return the article to design",
        "per-cycle inspection log and end-of-set teardown record",
        VerificationMethod.INSPECTION,
        Stage.BENCH_HIL,
        "P0-A",
        "structural_failures",
    ),
    Requirement(
        "P0-DOCK-007",
        "capture success rate on the moving suspended dock",
        ">= 9 captures in 10 consecutive attempts",
        "return to bench; do not promote to the carrier",
        "per-attempt outcome record with run identity",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-B",
        "captures_last_10",
    ),
    Requirement(
        "P0-DOCK-008",
        "capture success rate on the tethered helium carrier",
        ">= 9 captures in 10 consecutive attempts",
        "return to the suspended-dock rig at the lowest stage exposing the failure",
        "per-attempt outcome record with run identity",
        VerificationMethod.TEST,
        Stage.TETHERED_FLIGHT,
        "P0-C",
        "captures_last_10",
    ),
    Requirement(
        "P0-DOCK-009",
        "propeller or airframe contact with the funnel during approach",
        "0 contacts",
        "abort approach; stop the run set on any contact",
        "dock/aircraft telemetry plus witness and video corroboration",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-B",
        "prop_funnel_contacts",
    ),
    Requirement(
        "P0-DOCK-010",
        "S1 seat-switch actuation mode: position versus maintained force",
        "S1 stays actuated once the probe is seated and the aircraft's weight "
        "has transferred to the keeper, i.e. S1 is actuated by probe position "
        "with sufficient over-travel, not by maintained contact force",
        "an S1 that opens on weight transfer must be treated as a hardware "
        "defect, not tuned around in software",
        "P0-A cycling: S1 state trace across the disarm and hang-off "
        "transition, plus measured actuation force and over-travel",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        "ambiguous_capture_confirmations",
    ),
    Requirement(
        "P0-DOCK-011",
        "keeper command after a controller restart with the keeper closed",
        "a restarted controller holds a closed keeper and never commands it "
        "open on its own; opening a keeper whose contents are unknown "
        "requires an explicit emergency-release command",
        "hold the keeper closed and report the ambiguous state; await an "
        "operator decision",
        "hardware fault insertion CONTROLLER_RESET_WHILE_CAPTURED with a "
        "dummy mass retained, plus the controller unit tests",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        "fault_insertion_unsafe_responses",
    ),
    Requirement(
        "P0-FLEET-001",
        "completion of a sequential two-aircraft release/recovery cycle",
        ">= 1 complete sequence, one aircraft at a time",
        "ground the second aircraft and revert to single-aircraft operation",
        "sequenced mission log with per-aircraft dock occupancy",
        VerificationMethod.TEST,
        Stage.TETHERED_FLIGHT,
        "P0-D",
        "successful_two_aircraft_sequences",
    ),
    Requirement(
        "P0-FLEET-002",
        "inter-aircraft separation during two-aircraft operation",
        "0 separation violations against the configured minimum",
        "command both aircraft to hold, then land the non-recovering aircraft",
        "time-aligned pose logs of both aircraft",
        VerificationMethod.TEST,
        Stage.TETHERED_FLIGHT,
        "P0-D",
        "separation_violations",
    ),
    Requirement(
        "P0-FLEET-003",
        "number of aircraft inside the dock approach volume",
        "0 simultaneous dock approaches; the active dock serves one aircraft at a time",
        "deny the approach clearance; the second aircraft holds",
        "approach-clearance state in the sequencing log",
        VerificationMethod.TEST,
        Stage.TETHERED_FLIGHT,
        "P0-D",
        "simultaneous_dock_approaches",
    ),
    Requirement(
        "P0-MASS-001",
        "mass of the complete carrier-side dock assembly",
        "<= 180 g",
        "re-budget or redesign before flight integration",
        "scale measurement of the assembled dock recorded with the article identity",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        "dock_mass_g",
    ),
    Requirement(
        "P0-MASS-002",
        "mass of the complete drone-side probe including fasteners",
        "<= 8 g",
        "redesign the probe; do not trade aircraft flight time silently",
        "scale measurement of the fitted probe recorded with the article identity",
        VerificationMethod.TEST,
        Stage.BENCH_HIL,
        "P0-A",
        "probe_mass_g",
    ),
    Requirement(
        "P0-MASS-003",
        "total carried mass allocation against the vendor-rated payload",
        "<= 1.0 kg rated payload, with the baseline allocation <= 425.4 g",
        "cut allocation before adding hardware; never spend the rated-payload reserve",
        "executable mass budget in aiur/p0.py",
        VerificationMethod.ANALYSIS,
        Stage.REQUIREMENT,
        None,
        None,
        ClosureStatus.CLOSED,
        "aiur/p0.py baseline_p0_budget + tests/test_p0.py payload-margin case; "
        "allocation only — re-open when measured article masses exist",
    ),
    Requirement(
        "P0-SAFE-001",
        "contact between any aircraft and the gas envelope",
        "0 envelope strikes",
        "abort; stop the run set and return to bench/HIL",
        "carrier and aircraft pose logs plus post-run envelope inspection",
        VerificationMethod.TEST,
        Stage.TETHERED_FLIGHT,
        "P0-C",
        "envelope_strikes",
    ),
    Requirement(
        "P0-SAFE-002",
        "manual emergency release of a captured aircraft",
        "0 failures over the P0-A emergency-release trials; release authority retained "
        "in every controller state including fail-locked",
        "stop the campaign; the article does not fly until release is unconditional",
        "per-trial emergency-release record and dock controller state trace",
        VerificationMethod.DEMONSTRATION,
        Stage.BENCH_HIL,
        "P0-A",
        "emergency_release_failures",
    ),
    Requirement(
        "P0-SAFE-003",
        "commanded safety abort during an autonomous approach",
        "0 abort failures",
        "stop the run set; abort authority is a precondition for further attempts",
        "abort command and outcome in the run telemetry",
        VerificationMethod.DEMONSTRATION,
        Stage.BENCH_HIL,
        "P0-B",
        "safety_abort_failures",
    ),
    Requirement(
        "P0-SAFE-004",
        "pilot abort of release or recovery at any point in the cycle",
        "0 abort-path failures",
        "stop the run set and return to the suspended-dock rig",
        "abort command, timestamp, and outcome in the run telemetry",
        VerificationMethod.DEMONSTRATION,
        Stage.TETHERED_FLIGHT,
        "P0-C",
        "abort_path_failures",
    ),
    Requirement(
        "P0-SAFE-005",
        "physical kill path that disables carrier propulsion and inhibits release",
        "functions with the autonomy computer powered off or unresponsive",
        "no session proceeds; loss of the kill path is a campaign stop rule",
        "pre-session end-to-end check record with the autonomy computer off",
        VerificationMethod.DEMONSTRATION,
        Stage.TETHERED_FLIGHT,
        "P0-C",
    ),
    Requirement(
        "SIL-001",
        "simulated capture rate over fault-free episodes of the sil-p0b scenario",
        ">= 95% over >= 200 seeded episodes",
        "software does not earn bench time; fix the model or the software",
        "seeded Monte Carlo campaign report from aiur.sim.campaign",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        "SIL-B",
        "nominal_capture_rate_pct",
        ClosureStatus.CLOSED,
        "python -m aiur.sim.campaign --scenario sil-p0b --episodes 200 --seed 1 "
        "(SIL-B passed, 2026-08-08); replayable from the seed, run in CI on every push",
    ),
    Requirement(
        "SIL-002",
        "outcome of every injected-fault episode in the sil-p0b scenario",
        "0 unsafe outcomes over >= 50 activated fault episodes",
        "software does not earn bench time; the fault handling is wrong, not the quota",
        "fault-episode ledger in the campaign report",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        "SIL-B",
        "unsafe_fault_outcomes",
        ClosureStatus.CLOSED,
        "python -m aiur.sim.campaign --scenario sil-p0b --episodes 200 --seed 1 "
        "(SIL-B passed, 2026-08-08); replayable from the seed, run in CI on every push",
    ),
    Requirement(
        "SIL-003",
        "simulated completion rate of the full launch/sortie/recovery cycle in the "
        "sil-p0c scenario",
        ">= 95% over >= 200 seeded episodes",
        "the tethered-carrier software does not earn bench or flight time",
        "seeded Monte Carlo campaign report from aiur.sim.campaign",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        "SIL-C",
        "nominal_capture_rate_pct",
        ClosureStatus.CLOSED,
        "python -m aiur.sim.campaign --scenario sil-p0c --episodes 200 --seed 1 "
        "(SIL-C passed, 2026-08-08); replayable from the seed",
    ),
    Requirement(
        "SIL-004",
        "simulated two-aircraft sequence success rate in the sil-p0d scenario",
        ">= 90% complete sequences with 0 separation or simultaneous-approach violations",
        "the sequencing logic does not go to the carrier",
        "seeded Monte Carlo campaign report from aiur.sim.campaign",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        "SIL-D",
        "sequence_success_rate_pct",
        ClosureStatus.CLOSED,
        "python -m aiur.sim.campaign --scenario sil-p0d --episodes 80 --seed 1 "
        "(SIL-D passed, 2026-08-08); replayable from the seed",
    ),
    Requirement(
        "SIL-005",
        "detection of a persistent relative-navigation bias before it reaches the funnel rim",
        "no undetected bias that walks the aircraft outside the funnel acceptance",
        "quarantine the approach on a detected jump; no response exists for an undetected bias",
        "twin finding 3 in docs/digital-twin.md (jump-detector sweep)",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        None,
        None,
        ClosureStatus.ACCEPTED_RISK,
        "",
        "Single-source relative navigation cannot observe its own slow bias. The jump "
        "detector catches step anomalies, including across measurement gaps, but a slowly "
        "ramping bias is invisible from inside one positioning system. Accepted for P0 as "
        "instrumented: the 180 mm funnel is the mechanical tolerance, indoor Lighthouse is "
        "the reference, and a second terminal sensing modality is the named mitigation "
        "carried into the risk register rather than into the P0 build.",
    ),
    Requirement(
        "SIL-006",
        "capture confirmation with a stuck-closed seat switch combined with a masked "
        "navigation bias",
        "no confirmed capture on an empty throat",
        "none available in software; every supervisor gate reads the same biased estimate",
        "twin finding 5 in docs/digital-twin.md (double-fault campaign)",
        VerificationMethod.ANALYSIS,
        Stage.SIL,
        None,
        None,
        ClosureStatus.ACCEPTED_RISK,
        "",
        "This is a double fault, outside the single-fault regime P0 tests to. Software "
        "cannot close it: a supervisor built on the biased measurement agrees with the "
        "stuck switch. The mitigation is mechanical and scheduled for Rev-B — a keeper "
        "closed position that discriminates closed-on-probe from closed-on-empty-throat "
        "(position or current sensing) — giving one signal no navigation fault can spoof. "
        "Accepted until Rev-B; revisited on any move to unattended operation.",
    ),
)


def _gate_index() -> dict[str, Gate]:
    """Every gate a requirement may close against: hardware and SIL."""

    return {gate.gate_id: gate for gate in (*GATES, *SIL_GATES)}


def requirement_by_id(
    requirement_id: str,
    requirements: tuple[Requirement, ...] = REQUIREMENTS,
) -> Requirement:
    for requirement in requirements:
        if requirement.id == requirement_id:
            return requirement
    raise KeyError(f"unknown requirement: {requirement_id}")


def requirements_for_gate(
    gate_id: str,
    requirements: tuple[Requirement, ...] = REQUIREMENTS,
) -> tuple[Requirement, ...]:
    """Requirements a given gate is expected to close."""

    return tuple(r for r in requirements if r.gate_id == gate_id)


def validate_requirements(
    requirements: tuple[Requirement, ...] = REQUIREMENTS,
) -> tuple[str, ...]:
    """Return closure-matrix errors; an empty tuple is a valid matrix."""

    errors: list[str] = []

    ids = [requirement.id for requirement in requirements]
    if len(set(ids)) != len(ids):
        errors.append("requirement ids must be unique")
    if ids != sorted(ids):
        errors.append("requirement ids must be listed in sorted order")

    gates = _gate_index()

    for requirement in requirements:
        if not isinstance(requirement.method, VerificationMethod):
            errors.append(f"{requirement.id} has no verification method")
        if not isinstance(requirement.stage, Stage):
            errors.append(f"{requirement.id} has no loop stage")

        for field in ("observable", "limit", "failure_response", "evidence_source"):
            if not str(getattr(requirement, field)).strip():
                errors.append(f"{requirement.id} has an empty {field}")

        if requirement.status is ClosureStatus.CLOSED and not requirement.closing_evidence.strip():
            errors.append(f"{requirement.id} is closed without closing evidence")
        if requirement.status is ClosureStatus.ACCEPTED_RISK and not requirement.rationale.strip():
            errors.append(f"{requirement.id} accepts risk without a rationale")

        gate = None
        if requirement.gate_id is not None:
            gate = gates.get(requirement.gate_id)
            if gate is None:
                errors.append(
                    f"{requirement.id} references unknown gate {requirement.gate_id}"
                )
            elif gate.stage is not requirement.stage:
                errors.append(
                    f"{requirement.id} is staged {requirement.stage.value} but gate "
                    f"{gate.gate_id} closes at {gate.stage.value}"
                )

        if requirement.criterion_metric is None:
            continue
        if requirement.gate_id is None:
            errors.append(
                f"{requirement.id} links criterion {requirement.criterion_metric} "
                "without a gate"
            )
        elif gate is not None:
            metrics = {criterion.metric for criterion in gate.criteria}
            if requirement.criterion_metric not in metrics:
                errors.append(
                    f"{requirement.id} links criterion {requirement.criterion_metric} "
                    f"which gate {gate.gate_id} does not define"
                )

    return tuple(errors)


def coverage_report(
    requirements: tuple[Requirement, ...] = REQUIREMENTS,
) -> dict[str, object]:
    """Closure coverage: what is closed, by what method, and what is left.

    ``open_ids_by_stage`` lists everything not yet closed and not accepted as
    residual risk — remaining verification work, per loop stage.
    ``unverified`` is the harder question: requirements with no gate assigned
    and no closing evidence, so nothing in the program is scheduled to close
    them.  Accepted-risk rows appear there by construction, which is the
    honest reading — an accepted risk is an unverified requirement someone
    signed for.
    """

    by_status = {status.value: 0 for status in ClosureStatus}
    by_method = {method.value: 0 for method in VerificationMethod}
    by_stage = {stage.value: 0 for stage in Stage}
    open_ids_by_stage: dict[str, list[str]] = {stage.value: [] for stage in Stage}
    unverified: list[str] = []

    for requirement in requirements:
        by_status[requirement.status.value] += 1
        by_method[requirement.method.value] += 1
        by_stage[requirement.stage.value] += 1

        if requirement.status in (ClosureStatus.OPEN, ClosureStatus.IN_WORK):
            open_ids_by_stage[requirement.stage.value].append(requirement.id)
        if requirement.gate_id is None and not requirement.closing_evidence.strip():
            unverified.append(requirement.id)

    return {
        "total": len(requirements),
        "by_status": by_status,
        "by_method": by_method,
        "by_stage": by_stage,
        "open_ids_by_stage": open_ids_by_stage,
        "unverified": unverified,
    }


def snapshot() -> dict[str, object]:
    errors = validate_requirements()
    return {
        "valid": not errors,
        "errors": list(errors),
        "coverage": coverage_report(),
        "requirements": [
            {
                "id": requirement.id,
                "observable": requirement.observable,
                "limit": requirement.limit,
                "failure_response": requirement.failure_response,
                "evidence_source": requirement.evidence_source,
                "method": requirement.method.value,
                "stage": requirement.stage.value,
                "gate_id": requirement.gate_id,
                "criterion_metric": requirement.criterion_metric,
                "status": requirement.status.value,
                "closing_evidence": requirement.closing_evidence,
                "rationale": requirement.rationale,
            }
            for requirement in REQUIREMENTS
        ],
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
