"""Hazard log with named residual-risk acceptance for CARRIER-P0.

MIL-STD-882E w/Change 1 tracks every hazard on a severity x probability
matrix, and the part worth copying is not the matrix: it is that residual
risk is never accepted anonymously.  Section 4.3.7 ("Accept risk and
document") reads "Before exposing people, equipment, or the environment to
known system-related hazards, the risks shall be accepted by the appropriate
authority as defined in applicable DoDI 5000 series", and Task 106.2.q
requires the tracking record to carry the acceptance authority by title and
organization, the date of acceptance, and the location of the signed
document.  This module is that record for a $3k indoor prototype: a hazard
whose residual is above LOW is somebody's decision by name, date, and scope,
or it is an open item that blocks exposing a person to it.

Tailoring, stated instead of hidden
-----------------------------------
Table I assigns severity from three limbs: death/injury, environmental
impact, and monetary loss.  The monetary limb is DoD-scale — Catastrophic
begins at "monetary loss equal to or exceeding $10M" — and says nothing
useful about an article whose entire bill of materials is a few thousand
dollars.  Scored on money, every hazard below is Negligible and the matrix
is inert.  CARRIER-P0 therefore reads severity from the injury limb of
Table I verbatim and substitutes a program-scaled system-loss limb
(``SEVERITY_PROGRAM_SCALING``) for the monetary one.  Tables II and III are
used unmodified.

882E 4.3.3.d permits tailored alternate definitions "derived from Tables I
through III" when they are "formally approved in accordance with DoD
Component policy".  There is no DoD Component here and this is not a DoD
program, so the substitution above is documented program tailoring, not an
approved alternate and not a compliance claim.

Two further honest deviations
-----------------------------
1. The DoD Systems Engineering Guidebook records that "[i]n accordance with
   MIL-STD-882, a risk is never closed nor is the term 'residual' risk
   used".  This log uses "residual" anyway, because for a prototype the
   word names exactly the thing the program keeps forgetting to sign for.
   The underlying rule is kept: nothing here is ever "closed" — a hazard
   reaches a verified mitigation and an accepted residual, and re-opens the
   moment the scope of that acceptance changes.
2. The acceptance ladder in ``ACCEPTANCE_AUTHORITY`` is program-defined.
   The escalating-authority *idea* comes from the DoD model (DoDI 5000.88
   §3.6.e(1)(b)1: High to the CAE or DAE, Serious to PEO level, Medium and
   Low to the PM, with user-representative concurrence before Serious and
   High acceptances).  A three-person indoor test crew has no CAE and no
   PEO, so the mapping is not copied — only its structure.

State of this file
------------------
Every acceptance record in ``HAZARDS`` is absent, because no human has
signed one.  That is the true state of the program and it is left visible on
purpose: ``validate_hazards()`` checks the structure of the log and stays
green, ``validate_hazards(require_acceptance=True)`` is the pre-exposure
check demanded by 4.3.7 and currently fails, and ``open_items()`` names
every residual still waiting for a signature and who is allowed to give it.
Filling these records in without a real decision would be the one failure
mode this module exists to prevent.

Probabilities here are qualitative Table II judgements, not measured rates:
no hardware article has been built and no gate campaign has been run.  They
are engineering estimates that the P0-A/P0-B evidence is meant to replace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from enum import Enum
import json
import re

from .loop_graph import GATES
from .requirements import REQUIREMENTS
from .sim.gates import SIL_GATES


class Severity(int, Enum):
    """MIL-STD-882E Table I severity categories.

    The enum values are the standard's own category numbers, so
    ``Severity.CRITICAL`` is literally the "2" in a Risk Assessment Code of
    2C.  Lower is worse.
    """

    CATASTROPHIC = 1
    CRITICAL = 2
    MARGINAL = 3
    NEGLIGIBLE = 4

    @property
    def mishap_result_criteria(self) -> str:
        """Table I "Mishap Result Criteria", verbatim."""

        return MISHAP_RESULT_CRITERIA[self]

    @property
    def program_criteria(self) -> str:
        """How CARRIER-P0 reads this category (monetary limb replaced)."""

        return SEVERITY_PROGRAM_SCALING[self]


#: MIL-STD-882E w/Change 1, Table I, "Mishap Result Criteria" column,
#: verbatim.  Quoted rather than paraphrased so the tailoring below is a
#: visible edit against a known text.
MISHAP_RESULT_CRITERIA: dict[Severity, str] = {
    Severity.CATASTROPHIC: (
        "Could result in one or more of the following: death, permanent total "
        "disability, irreversible significant environmental impact, or monetary "
        "loss equal to or exceeding $10M."
    ),
    Severity.CRITICAL: (
        "Could result in one or more of the following: permanent partial "
        "disability, injuries or occupational illness that may result in "
        "hospitalization of at least three personnel, reversible significant "
        "environmental impact, or monetary loss equal to or exceeding $1M but "
        "less than $10M."
    ),
    Severity.MARGINAL: (
        "Could result in one or more of the following: injury or occupational "
        "illness resulting in one or more lost work day(s), reversible moderate "
        "environmental impact, or monetary loss equal to or exceeding $100K but "
        "less than $1M."
    ),
    Severity.NEGLIGIBLE: (
        "Could result in one or more of the following: injury or occupational "
        "illness not resulting in a lost work day, minimal environmental impact, "
        "or monetary loss less than $100K."
    ),
}

#: The program-scaled reading actually used to score the hazards below.  The
#: injury limb is Table I unchanged; the monetary limb is replaced by a
#: system-loss limb sized to a one-article indoor prototype.  Environmental
#: impact is retained implicitly: the only inventory that can leave the room
#: is helium, which is inert.
SEVERITY_PROGRAM_SCALING: dict[Severity, str] = {
    Severity.CATASTROPHIC: (
        "Death or permanent total disability to any person; or loss of the gas "
        "envelope with an uncontrolled descent onto occupied floor space, or a "
        "fire that leaves the test room."
    ),
    Severity.CRITICAL: (
        "Permanent partial disability or an injury needing hospital treatment "
        "(an eye or face injury from a propeller, or a lithium fire, is the "
        "credible case at this scale); or loss of the carrier or of the only "
        "dock article, which stops the program."
    ),
    Severity.MARGINAL: (
        "Injury or occupational illness resulting in one or more lost work "
        "day(s); or damage costing a rebuild and a schedule slip - a destroyed "
        "aircraft, funnel, keeper, or actuator."
    ),
    Severity.NEGLIGIBLE: (
        "Injury not resulting in a lost work day; or damage repaired from the "
        "spares already on the bench."
    ),
}


class Probability(str, Enum):
    """MIL-STD-882E Table II probability levels.

    Values are the standard's level letters, so ``Probability.OCCASIONAL``
    is the "C" in a RAC of 2C.  Earlier letters are worse.

    Level F is reachable only by design: 4.3.3.b states "No amount of
    doctrine, training, warning, caution, or Personal Protective Equipment
    (PPE) can move a mishap probability to level F."
    """

    FREQUENT = "A"
    PROBABLE = "B"
    OCCASIONAL = "C"
    REMOTE = "D"
    IMPROBABLE = "E"
    ELIMINATED = "F"

    @property
    def specific_individual_item(self) -> str:
        """Table II "Specific Individual Item" definition, verbatim.

        The single-item column is the right one for this program: there is
        one dock, one carrier, and two aircraft.  The fleet/inventory column
        describes a population that does not exist here.
        """

        return SPECIFIC_INDIVIDUAL_ITEM[self]

    @property
    def rank(self) -> int:
        """0 for Frequent through 5 for Eliminated; higher is better."""

        return PROBABILITY_ORDER.index(self)


#: MIL-STD-882E w/Change 1, Table II, "Specific Individual Item" column,
#: verbatim.
SPECIFIC_INDIVIDUAL_ITEM: dict[Probability, str] = {
    Probability.FREQUENT: "Likely to occur often in the life of an item.",
    Probability.PROBABLE: "Will occur several times in the life of an item.",
    Probability.OCCASIONAL: "Likely to occur sometime in the life of an item.",
    Probability.REMOTE: "Unlikely, but possible to occur in the life of an item.",
    Probability.IMPROBABLE: (
        "So unlikely, it can be assumed occurrence may not be experienced in the "
        "life of an item."
    ),
    Probability.ELIMINATED: (
        "Incapable of occurrence. This level is used when potential hazards are "
        "identified and later eliminated."
    ),
}

PROBABILITY_ORDER: tuple[Probability, ...] = (
    Probability.FREQUENT,
    Probability.PROBABLE,
    Probability.OCCASIONAL,
    Probability.REMOTE,
    Probability.IMPROBABLE,
    Probability.ELIMINATED,
)


class RiskLevel(str, Enum):
    """Table III risk levels, plus the Eliminated state of probability F."""

    HIGH = "high"
    SERIOUS = "serious"
    MEDIUM = "medium"
    LOW = "low"
    ELIMINATED = "eliminated"

    @property
    def rank(self) -> int:
        """0 for Eliminated through 4 for High; higher is worse."""

        return RISK_RANK[self]


RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.ELIMINATED: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.SERIOUS: 3,
    RiskLevel.HIGH: 4,
}

#: Severity order of the Table III columns, left to right.
SEVERITY_COLUMNS: tuple[Severity, ...] = (
    Severity.CATASTROPHIC,
    Severity.CRITICAL,
    Severity.MARGINAL,
    Severity.NEGLIGIBLE,
)

#: Table III transcribed as data — one row per probability level, columns in
#: severity order 1..4 — so the mapping can be diffed line by line against
#: the printed table instead of being reverse-engineered out of an if-chain.
#: The F row is a single spanning "Eliminated" cell in the standard.
_TABLE_III: tuple[tuple[str, tuple[str, str, str, str]], ...] = (
    ("A", ("high", "high", "serious", "medium")),
    ("B", ("high", "high", "serious", "medium")),
    ("C", ("high", "serious", "medium", "low")),
    ("D", ("serious", "medium", "medium", "low")),
    ("E", ("medium", "medium", "medium", "low")),
    ("F", ("eliminated", "eliminated", "eliminated", "eliminated")),
)

RISK_ASSESSMENT_MATRIX: dict[tuple[Severity, Probability], RiskLevel] = {
    (severity, Probability(letter)): RiskLevel(cell)
    for letter, row in _TABLE_III
    for severity, cell in zip(SEVERITY_COLUMNS, row)
}


def risk_level(severity: Severity, probability: Probability) -> RiskLevel:
    """Table III lookup: one severity category + one probability level."""

    return RISK_ASSESSMENT_MATRIX[(severity, probability)]


def risk_code(severity: Severity, probability: Probability) -> str:
    """Risk Assessment Code, e.g. 2C.

    Per 4.3.3.c, "a RAC of 1A is the combination of a Catastrophic severity
    category and a Frequent probability level".
    """

    return f"{severity.value}{probability.value}"


class AcceptanceAuthority(str, Enum):
    """Who may accept a residual at each risk level, on this program.

    Program-defined and deliberately small.  The DoD ladder this imitates
    (DoDI 5000.88 §3.6.e(1)(b)1) escalates CAE / PEO / PM; a three-person
    indoor test crew escalates test conductor / safety observer / program
    lead.  The structure is the point: authority rises with risk, and above
    a line nobody may accept at all.

    This program is stricter than the DoD model at the top.  DoDI 5000.88
    lets a High risk be accepted by the CAE; here a High residual is a stop.
    There is no authority on this program with the standing to accept a High
    risk, and no reason to run an indoor prototype that still carries one.
    """

    NOT_REQUIRED = "no acceptance required"
    TEST_CONDUCTOR = "test conductor"
    SAFETY_OBSERVER_AND_TEST_CONDUCTOR = "safety observer + test conductor"
    PROGRAM_LEAD = "program lead, with written rationale"
    NOT_ACCEPTABLE = "not acceptable; must be mitigated before exposure"


ACCEPTANCE_AUTHORITY: dict[RiskLevel, AcceptanceAuthority] = {
    RiskLevel.HIGH: AcceptanceAuthority.NOT_ACCEPTABLE,
    RiskLevel.SERIOUS: AcceptanceAuthority.PROGRAM_LEAD,
    RiskLevel.MEDIUM: AcceptanceAuthority.SAFETY_OBSERVER_AND_TEST_CONDUCTOR,
    RiskLevel.LOW: AcceptanceAuthority.TEST_CONDUCTOR,
    RiskLevel.ELIMINATED: AcceptanceAuthority.NOT_REQUIRED,
}

#: Residuals at or below this level run on the standing test-card rules and
#: need no separate signature.  Anything worse needs a named acceptance
#: before a person is exposed to it.
ACCEPTANCE_THRESHOLD = RiskLevel.LOW


def required_authority(level: RiskLevel) -> AcceptanceAuthority:
    """Program-scaled acceptance authority for a residual risk level."""

    return ACCEPTANCE_AUTHORITY[level]


def acceptance_required(level: RiskLevel) -> bool:
    """True when a residual at this level needs a signed acceptance."""

    return level.rank > ACCEPTANCE_THRESHOLD.rank


#: Fields that must all be present for an acceptance to be a decision rather
#: than a sentence.  ``accepted_by``/``date``/``scope``/``rationale`` are the
#: 882E Task 106.2.q elements scaled to one program; ``role`` is added
#: because an acceptance with no role cannot be checked against the ladder.
REQUIRED_ACCEPTANCE_FIELDS: tuple[str, ...] = (
    "accepted_by",
    "role",
    "date",
    "scope",
    "rationale",
)


@dataclass(frozen=True)
class ResidualAcceptance:
    """One person's signature on one residual risk.

    Every field is here because its absence is a way for a residual to
    become nobody's decision:

    - ``accepted_by`` / ``role``: the name and the standing.  "The team
      accepted it" is not an acceptance.
    - ``date``: acceptances go stale; a dated record can be re-reviewed.
    - ``scope``: the regime the acceptance covers, e.g. "indoor tethered P0
      single-fault regime".  This is the field that forces re-acceptance
      when the program leaves the regime instead of letting an indoor
      signature quietly authorise outdoor flight.
    - ``rationale``: why this residual is tolerable, in writing, so a later
      reviewer can disagree with the reasoning rather than guess at it.

    Defaults are empty on purpose: an unsigned record is invalid, and the
    validator says so.
    """

    accepted_by: str = ""
    role: str = ""
    date: str = ""
    scope: str = ""
    rationale: str = ""

    def missing_fields(self) -> tuple[str, ...]:
        """Required fields that are empty or whitespace."""

        return tuple(
            field
            for field in REQUIRED_ACCEPTANCE_FIELDS
            if not str(getattr(self, field)).strip()
        )

    @property
    def is_signed(self) -> bool:
        return not self.missing_fields()


class HazardStatus(str, Enum):
    """Where a hazard sits in the mitigate/verify sequence.

    There is no CLOSED state.  A hazard reaches ``MITIGATION_VERIFIED`` with
    an accepted residual and stays in the log for the life of the article.
    """

    #: In the log; no mitigation selected yet.
    IDENTIFIED = "identified"
    #: Mitigation chosen and present in the design, software, or procedure,
    #: but the verification named below has not produced evidence.
    MITIGATION_SELECTED = "mitigation_selected"
    #: The named verification has run and produced evidence.
    MITIGATION_VERIFIED = "mitigation_verified"
    #: Residual probability is F: the hazard cannot occur in the current
    #: design.  Not reachable by procedure or PPE (4.3.3.b).
    ELIMINATED = "eliminated"


@dataclass(frozen=True)
class Hazard:
    """One tracked hazard and its two risk assessments.

    Field order follows the 882E Task 106 record: what the hazard is, what
    causes it, what it does, the initial risk, the mitigations and how they
    are verified, the residual risk, and who accepted that residual.
    """

    id: str
    title: str
    description: str
    cause: str
    effect: str
    severity: Severity
    probability: Probability
    mitigations: tuple[str, ...]
    #: How the mitigations are shown to work: a gate id, a gate criterion, a
    #: requirement id, or an explicit statement that nothing measures this.
    verification: str
    residual_severity: Severity
    residual_probability: Probability
    acceptance: ResidualAcceptance | None = None
    status: HazardStatus = HazardStatus.IDENTIFIED

    @property
    def initial_risk(self) -> RiskLevel:
        return risk_level(self.severity, self.probability)

    @property
    def residual_risk(self) -> RiskLevel:
        return risk_level(self.residual_severity, self.residual_probability)

    @property
    def initial_code(self) -> str:
        return risk_code(self.severity, self.probability)

    @property
    def residual_code(self) -> str:
        return risk_code(self.residual_severity, self.residual_probability)

    @property
    def required_authority(self) -> AcceptanceAuthority:
        return required_authority(self.residual_risk)

    @property
    def is_accepted(self) -> bool:
        return self.acceptance is not None and self.acceptance.is_signed


#: The standing scope sentence for P0 acceptances.  Any acceptance signed
#: for a wider regime than this is a different decision and needs its own
#: record; leaving the regime re-opens every hazard signed under it.
P0_ACCEPTANCE_SCOPE = "indoor tethered P0 single-fault regime, propeller-guarded"


HAZARDS: tuple[Hazard, ...] = (
    Hazard(
        id="HAZ-001",
        title="Confirmed capture on an empty dock after a correlated double fault",
        description=(
            "The controller asserts capture_confirmed with no probe in the "
            "throat, and the recovery sequence disarms an aircraft that is "
            "still flying."
        ),
        cause=(
            "S1 stuck closed (welded or contaminated contact, jammed plunger, "
            "harness short to the rail) coincident with a slowly ramping "
            "single-source navigation bias that the jump detector cannot see. "
            "The two are not independent: the supervisor's plausibility gate "
            "is computed from the same Lighthouse measurement the bias is in, "
            "so no software check built on that source can arbitrate."
        ),
        effect=(
            "capture_confirmed = S1 AND S2 is true with an empty throat; the "
            "aircraft is disarmed in free air and falls from carrier height "
            "onto floor, equipment, or a person."
        ),
        severity=Severity.MARGINAL,
        probability=Probability.OCCASIONAL,
        mitigations=(
            "Supervisor refuses to enable capture, and above all to disarm, "
            "unless its own relative estimate places the probe at the seat "
            "(twin finding 2).",
            "Capture enable is edge-gated on a tight seat confirm and then "
            "latched, so a noisy per-sample estimate cannot flap the "
            "controller (twin finding 1).",
            "Dual-contact NC+NO decode on S1 and S2 turns a shorted or open "
            "line into a detected wiring fault rather than a state.",
            "Gold-contact switch variants with an external pull-up sized above "
            "the datasheet minimum applicable load (1 mA at 5 VDC for the "
            "gold-alloy Omron D2F-01 family), so logic-level switching does "
            "not create the intermittents this hazard feeds on.",
            "Rev-B candidate, not yet designed: keeper closed-position "
            "discrimination (position or current sensing) that separates "
            "'closed on probe' from 'closed on empty throat' and gives the "
            "system one signal no navigation fault can spoof.",
        ),
        verification=(
            "SIL-006 (twin campaign with a stuck-closed seat switch); P0-A "
            "fault modes S1_SHORT and S1_S2_BOTH_OPEN with written required "
            "responses; P0-A criterion ambiguous_capture_confirmations; "
            "requirement P0-DOCK-005. Nothing verifies the Rev-B keeper "
            "discrimination because it does not exist yet."
        ),
        residual_severity=Severity.MARGINAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-002",
        title="Undetectable navigation bias walks the aircraft into the dock rim",
        description=(
            "A persistent relative-navigation bias is invisible from inside a "
            "single positioning system and steers a nominally healthy approach "
            "off centre."
        ),
        cause=(
            "Lighthouse-derived relative pose is the only terminal sensing "
            "modality. A bias that ramps slowly, or that arises under a long "
            "measurement gap at transit speed, stays under the jump detector's "
            "threshold (twin finding 3)."
        ),
        effect=(
            "The aircraft closes on a point that is not the throat: propeller "
            "or airframe contact with the funnel rim or the dock structure, "
            "damaged aircraft and dock, fragments in the test volume."
        ),
        severity=Severity.MARGINAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Jump detector quarantines step anomalies, including across "
            "measurement gaps where the threshold widens by plausible own "
            "motion.",
            "Funnel mechanical tolerance: a 180 mm mouth against a Lighthouse-"
            "grade position error absorbs a bias far larger than the sensor's "
            "own noise before it becomes contact.",
            "Estimate-validity abort in the safety supervisor; approach holds "
            "outside the funnel until the estimate is trusted.",
            "Propeller guards fitted, and the probe standoff keeps the rotor "
            "plane below the funnel lip so an off-centre approach hits "
            "structure with a guard, not a blade.",
            "Second terminal sensing modality is the real fix and is not in "
            "the P0 build.",
        ),
        verification=(
            "SIL-005 (bias detection before rim contact) and the "
            "degraded-sensor-sweep study; P0-B criterion prop_funnel_contacts; "
            "requirement P0-DOCK-009."
        ),
        residual_severity=Severity.MARGINAL,
        residual_probability=Probability.OCCASIONAL,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-003",
        title="Gas-envelope strike by a powered aircraft",
        description=(
            "An aircraft under power contacts the helium envelope during "
            "launch, station-keeping, or recovery."
        ),
        cause=(
            "Approach path or evasion manoeuvre that passes inside the hull "
            "keep-out; carrier drift under room airflow; navigation error; "
            "loss of aircraft control near the hull."
        ),
        effect=(
            "Envelope tear, loss of lift, uncontrolled descent of a 4.5 m "
            "carrier and its payload onto occupied floor space; release of the "
            "envelope's helium inventory into the room; loss of the only "
            "carrier article."
        ),
        severity=Severity.CRITICAL,
        probability=Probability.OCCASIONAL,
        mitigations=(
            "Envelope keep-out ellipsoid in guidance; the aircraft is never "
            "commanded through hull space.",
            "Hull-proximity evasion reflex, required indoors as well as "
            "outdoors (twin finding 4).",
            "Propeller guards on every aircraft that flies near the carrier.",
            "Dock geometry: 110 mm probe standoff against a 65 mm funnel keeps "
            "roughly 45 mm nominal separation between the funnel lip and the "
            "propeller plane at zero tilt.",
            "Envelope contact is a campaign stop rule, not a logged anomaly.",
        ),
        verification=(
            "P0-C criterion envelope_strikes; requirement P0-SAFE-001; SIL-C "
            "campaign safety zeros over the full launch/sortie/recovery cycle."
        ),
        residual_severity=Severity.CRITICAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-004",
        title="Captured aircraft is dropped by the dock",
        description=(
            "A genuinely captured aircraft leaves the keeper in flight and "
            "falls."
        ),
        cause=(
            "Keeper back-drive under load; servo power loss with the keeper "
            "short of its closed stop; retention carried by the compliant "
            "collet instead of the positive keeper; probe neck or probe base "
            "failure; fastener loosening across the cycle set; a printed part "
            "that has bedded in past its fit."
        ),
        effect=(
            "A 37 g aircraft falls from carrier height onto floor, equipment, "
            "or a person; loss of one of two flight articles."
        ),
        severity=Severity.MARGINAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Positive keeper with mechanically stable closed geometry: rigid "
            "guides and a closed end-stop react retention load, not the servo "
            "geartrain.",
            "5 N axial and 1 N four-direction lateral screening loads held for "
            "10 s, run before and after life cycling.",
            "600 derived life-test cycles after a 15-cycle run-in whose force "
            "trend must level off first.",
            "Controller fails locked on post-capture sensor disagreement so "
            "software cannot drop a docked aircraft.",
            "Fastener, collet, keeper and probe inspection after cycling; any "
            "keeper motion without a command is a stop rule.",
        ),
        verification=(
            "P0-A criteria axial_screen_load_held_n, "
            "lateral_screen_load_held_n, life_test_cycles and "
            "structural_failures; requirement P0-DOCK-006."
        ),
        residual_severity=Severity.MARGINAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-005",
        title="Propeller contact with the funnel, dock structure, or a person",
        description=(
            "A powered 55 mm propeller strikes the dock or an unprotected "
            "person in the test volume."
        ),
        cause=(
            "Approach error, carrier motion during terminal approach, a "
            "bounced capture, an evasion manoeuvre toward the crew, or a "
            "person inside the volume during a powered run."
        ),
        effect=(
            "Cut or eye injury to a person; broken propellers and fragments; "
            "damaged funnel rim; an aircraft destabilised into a further "
            "strike."
        ),
        severity=Severity.CRITICAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Propeller guards fitted; the 37 g figure is the guard-equipped "
            "takeoff weight, so guards are in the mass budget rather than an "
            "option.",
            "Propellers removed for all P0-A bench work; the gate refuses "
            "evidence collected with them installed.",
            "Geometry that does not rely on the aircraft entering the funnel "
            "mouth: 155 mm swept diameter against a 180 mm mouth leaves only "
            "12.5 mm coplanar clearance, so the probe standoff, not the "
            "funnel, provides rotor-plane separation.",
            "Crew stand-off distance, the KILL call with a named caller, and "
            "no personnel inside the volume during powered runs.",
            "Propeller/funnel contact is a campaign stop rule.",
        ),
        verification=(
            "P0-A criterion propellers_installed; P0-B criterion "
            "prop_funnel_contacts; requirement P0-DOCK-009; crew placement and "
            "abort phraseology in docs/test-cards.md."
        ),
        residual_severity=Severity.CRITICAL,
        residual_probability=Probability.OCCASIONAL,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-006",
        title="Keeper closes on a finger during bench work",
        description=(
            "The sliding fork keeper traverses while a hand is in the funnel "
            "throat or across the keeper slot."
        ),
        cause=(
            "Commanded close during manual probe insertion; a spurious close "
            "from a stuck capture_enable; software position limits not yet set "
            "from the physical stops; two people working one article."
        ),
        effect=(
            "Pinch or abrasion of a fingertip between the keeper tines and the "
            "throat. The XL330-M288-T develops 0.52 N.m stall torque at 5 V "
            "through a short lever, so the available pinch force is small but "
            "not zero."
        ),
        severity=Severity.NEGLIGIBLE,
        probability=Probability.PROBABLE,
        mitigations=(
            "Software position limits established from the physical open and "
            "closed stops before the probe is reconnected.",
            "Bench supply current limit set before the first powered keeper "
            "motion; the XL330 draws about 1.47 A at stall at 5 V.",
            "Keeper run disconnected from the probe first, so travel is proven "
            "before anything is in the throat.",
            "Hands out of the throat whenever actuator power is on; actuator "
            "power switched independently of controller power on the "
            "OpenRB-150.",
        ),
        verification=(
            "P0-A procedure steps 3-5 (fixture safety, unloaded keeper motion, "
            "position limits before reconnection). No gate criterion measures "
            "a pinch; this hazard is verified by procedure and inspection "
            "only, and that gap is deliberate at this severity."
        ),
        residual_severity=Severity.NEGLIGIBLE,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-007",
        title="Lithium-polymer thermal event during charge or storage",
        description=(
            "A 250 mAh single-cell aircraft pack vents, ignites, or propagates "
            "a fire on the bench."
        ),
        cause=(
            "Charging past 4.20 V/cell (tolerance +/-50 mV); charging a pack "
            "damaged in a dropped-capture impact; charging outside the "
            "vendor's 0-45 C charge window; unattended charging; continuous "
            "trickle charge, which plates metallic lithium; storage at full "
            "charge next to combustibles."
        ),
        effect=(
            "Burns to a person, smoke in an occupied indoor space, loss of the "
            "bench and the article, and in the worst case a fire that leaves "
            "the room."
        ),
        severity=Severity.CRITICAL,
        probability=Probability.OCCASIONAL,
        mitigations=(
            "Charge and store in a fireproof container, in an area devoid of "
            "combustibles, never inside the model.",
            "Never charge unattended; charge at 0.5C-1C with balance charging "
            "and charge cessation at the per-cell voltage.",
            "Store at roughly 40-50% state of charge (about 3.8 V/cell), not "
            "at full charge.",
            "Retire on any swelling or crash damage; hold a crash-damaged pack "
            "under observation for at least half an hour before handling.",
            "Pack identity and cycle count recorded in the promotion telemetry "
            "so a pack's history travels with it; UN 38.3 test summary on file "
            "for every pack type.",
        ),
        verification=(
            "No gate criterion measures this. Verified by the battery SOP and "
            "by pack identity/cycle count in the P0-A article record and the "
            "promotion contract in docs/engineering-loop.md."
        ),
        residual_severity=Severity.CRITICAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-008",
        title="Loss of the physical kill path",
        description=(
            "The kill path is unavailable, fails permissive, or depends on the "
            "computer it exists to override."
        ),
        cause=(
            "Kill routed through flight software; shared supply with the "
            "autonomy computer so one brownout takes both; a link or power "
            "loss that leaves propulsion enabled; the kill actuator physically "
            "out of reach of the safety observer; kill and abort actuated the "
            "same way and confused under stress."
        ),
        effect=(
            "No means to stop propulsion or inhibit release when the autonomy "
            "computer is confused; the mishap the kill path exists to arrest "
            "proceeds to completion. This hazard is an enabler for HAZ-003, "
            "HAZ-005 and HAZ-011 rather than a mishap in itself."
        ),
        severity=Severity.CRITICAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Kill path independent of the autonomy computer and its supply "
            "rail, with independent command path (P0-KILL-001/002/003).",
            "Fail-safe on loss of its own power, link, or command: propulsion "
            "disabled and release inhibited (P0-KILL-007).",
            "End-to-end demonstration before every run set, and again with the "
            "autonomy computer powered off (P0-KILL-004/005).",
            "Kill actuation physically distinct from an abort command "
            "(P0-KILL-006), with pre-briefed phraseology and a named caller.",
            "Emergency-procedure dress rehearsal before the first run of each "
            "new gate.",
        ),
        verification=(
            "Criteria kill_path_preflight_checks, kill_path_failures and "
            "kill_path_verified_with_autonomy_off on P0-B, P0-C and P0-D; "
            "requirement P0-SAFE-005; docs/kill-path.md."
        ),
        residual_severity=Severity.CRITICAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-009",
        title="Helium asphyxiation in a small enclosed test room",
        description=(
            "Helium displaces breathable air in the test volume, most credibly "
            "as a ceiling-level layer rather than a uniformly mixed room."
        ),
        cause=(
            "Filling or purging the envelope in a closed room; a large valve "
            "or fill-line leak from a cylinder whose inventory is far larger "
            "than the envelope's; an envelope rupture; a person working at "
            "ceiling level on a ladder or mezzanine where the gas collects; "
            "inhaling from the fill line, which is the mechanism behind most "
            "recorded helium fatalities."
        ),
        effect=(
            "Inert-gas asphyxiation, which gives no warning symptoms before "
            "unconsciousness. Worst credible outcome is a fatality."
        ),
        severity=Severity.CATASTROPHIC,
        probability=Probability.REMOTE,
        mitigations=(
            "Fill and purge only in a ventilated bay or outdoors, never in a "
            "closed room; the test room's ventilation path is declared on the "
            "test card before a fill.",
            "Cylinder secured, valve closed whenever it is not actively "
            "filling, regulator removed for storage.",
            "Nobody inhales from the fill line or the envelope, ever; this is "
            "an explicit crew rule and not left to common sense.",
            "Two-person rule during fills, with nobody at ceiling level during "
            "or immediately after a fill.",
            "Oxygen monitoring is the engineered control if a room without a "
            "ventilation path ever has to be used; today the answer is not to "
            "use one.",
        ),
        verification=(
            "No gate criterion and no instrument measures this today, which is "
            "why the residual probability is a judgement rather than a number. "
            "Reviewed at the P0-C readiness review before the first helium "
            "fill; the envelope inventory (roughly 3 m3, engineering estimate "
            "for a 4.5 m hull) and the room volume are recorded there."
        ),
        residual_severity=Severity.CATASTROPHIC,
        residual_probability=Probability.IMPROBABLE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-010",
        title="Keeper servo stalls and overheats",
        description=(
            "The keeper actuator is driven against an obstruction or an "
            "end-stop and holds stall current."
        ),
        cause=(
            "Keeper blocked by debris, by a partially seated probe, or by a "
            "position limit set outside the physical stops; a controller that "
            "re-commands close after a failed lock; a jammed fork slot."
        ),
        effect=(
            "Winding heating past the actuator's 70 C rated limit, smoke, a "
            "destroyed servo, and loss of keeper authority mid-capture. The "
            "actuator sits against printed polymer, so sustained stall is also "
            "a local ignition concern."
        ),
        severity=Severity.MARGINAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Lock attempt times out to FAULT_OPEN after the configured lock "
            "timeout; the controller does not re-drive a stalled keeper.",
            "Software position limits set from the physical stops so the "
            "keeper cannot over-travel into either end.",
            "Bench supply current limit set before the first powered motion; "
            "1.47 A is the datasheet stall current at 5 V.",
            "DYNAMIXEL temperature, current and voltage telemetry recorded per "
            "cycle, so a rising stall trend is visible before failure.",
            "Actuator power switched independently of controller power, so "
            "removing drive does not take the controller down with it.",
        ),
        verification=(
            "P0-A fault mode SERVO_STALL with its written required response; "
            "P0-A criteria fault_insertion_trials and "
            "fault_insertion_unsafe_responses; hardware/dock/fault-insertion.md."
        ),
        residual_severity=Severity.MARGINAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-011",
        title="Uncommanded release over a person",
        description=(
            "The keeper opens with an aircraft retained, or a release is "
            "commanded while someone is under the carrier."
        ),
        cause=(
            "Spurious release_request; emergency-release line shorted or "
            "actuated in error; controller reset that leaves the keeper "
            "commanded open; keeper back-drive; a software fault in the "
            "release sequence."
        ),
        effect=(
            "An aircraft leaves the dock uncontrolled above a person. If it is "
            "armed at release, the worst credible outcome is propeller contact "
            "at head height."
        ),
        severity=Severity.CRITICAL,
        probability=Probability.OCCASIONAL,
        mitigations=(
            "Closed keeper geometry is mechanically stable and reacts load "
            "into a closed end-stop rather than the servo geartrain.",
            "Release inhibit in the physical kill path, independent of flight "
            "software state (P0-KILL-002).",
            "Controller fails locked on post-capture sensor disagreement and "
            "ignores a normal release request from FAULT_LOCKED; only "
            "emergency release opens from every state.",
            "No personnel under the carrier during dock operations, per the "
            "test-card crew placement.",
            "Uncommanded keeper motion or release is a campaign stop rule.",
        ),
        verification=(
            "P0-A criteria emergency_release_failures and "
            "loaded_emergency_release_failures; requirement P0-SAFE-002; "
            "release inhibit covered by kill_path_verified_with_autonomy_off "
            "on P0-B, P0-C and P0-D."
        ),
        residual_severity=Severity.CRITICAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
    Hazard(
        id="HAZ-012",
        title="Carrier overruns its own aircraft or drifts into the crew",
        description=(
            "The tethered carrier sweeps through airspace a station-holding "
            "aircraft expected to stay clear, or drifts into people and "
            "equipment."
        ),
        cause=(
            "Room airflow or an HVAC transient moving a buoyant 4.5 m hull "
            "faster than a station-holding micro-UAV expects (twin finding 4); "
            "thrust-limited station-keeping that cannot arrest the drift; "
            "tether geometry that permits a pendulum swing."
        ),
        effect=(
            "Hull-to-aircraft contact, an aircraft pinned against structure, "
            "or the carrier and its payload contacting crew or equipment."
        ),
        severity=Severity.MARGINAL,
        probability=Probability.PROBABLE,
        mitigations=(
            "Hull-proximity evasion reflex in aircraft guidance, required "
            "indoors and not only outdoors.",
            "Envelope keep-out ellipsoid sized around the hull rather than the "
            "gondola.",
            "Indoor operation with building airflow off during runs; the twin "
            "shows capture collapsing between 0.5 and 1.5 m/s mean wind, so "
            "still air is a precondition and not a preference.",
            "Ground tether and declared station placement, treated as a "
            "planning constraint.",
            "Crew stand-off from the carrier's reachable volume, not just from "
            "its nominal position.",
        ),
        verification=(
            "P0-C criterion full_payload_control_loss_events; SIL-C campaign; "
            "the outdoor-gust-sweep study bounds the airflow case."
        ),
        residual_severity=Severity.MARGINAL,
        residual_probability=Probability.REMOTE,
        acceptance=None,
        status=HazardStatus.MITIGATION_SELECTED,
    ),
)


_REFERENCE_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")


def _known_reference_ids() -> frozenset[str]:
    """Ids a hazard's verification field is allowed to point at.

    Gate ids, SIL gate ids, gate criterion metrics, and requirement ids.  A
    verification note that names none of them is a mitigation nobody has
    scheduled to check.
    """

    gates = (*GATES, *SIL_GATES)
    ids = {gate.gate_id for gate in gates}
    ids |= {criterion.metric for gate in gates for criterion in gate.criteria}
    ids |= {requirement.id for requirement in REQUIREMENTS}
    return frozenset(ids)


def _is_iso_date(value: str) -> bool:
    try:
        _date.fromisoformat(value)
    except ValueError:
        return False
    return True


def hazard_by_id(hazard_id: str, hazards: tuple[Hazard, ...] = HAZARDS) -> Hazard:
    for hazard in hazards:
        if hazard.id == hazard_id:
            return hazard
    raise KeyError(f"unknown hazard: {hazard_id}")


def validate_hazards(
    hazards: tuple[Hazard, ...] = HAZARDS,
    *,
    require_acceptance: bool = False,
) -> tuple[str, ...]:
    """Return hazard-log errors; an empty tuple is a valid log.

    Two modes, because the log has two different kinds of correctness.

    The default mode checks the *structure* of the log: unique sorted ids,
    populated fields, a verification note that points at something real,
    residual risk that is not worse than initial risk, and — the rule this
    module exists for — that any acceptance record present is a decision by
    a named person on a dated, scoped, argued basis, and that no High
    residual has been accepted at all.  CI runs this mode, and it is green.

    ``require_acceptance=True`` adds the 4.3.7 pre-exposure check: every
    residual above LOW must already carry a signed acceptance.  This is the
    check a run-readiness review runs before anyone stands next to the
    article, and on the committed registry it currently fails for every
    hazard, because nobody has signed anything.  That failure is the honest
    state of the program, not a defect in the log.
    """

    errors: list[str] = []

    ids = [hazard.id for hazard in hazards]
    if len(set(ids)) != len(ids):
        errors.append("hazard ids must be unique")
    if ids != sorted(ids):
        errors.append("hazard ids must be listed in sorted order")

    known = _known_reference_ids()

    for hazard in hazards:
        for field in ("id", "title", "description", "cause", "effect", "verification"):
            if not str(getattr(hazard, field)).strip():
                errors.append(f"{hazard.id} has an empty {field}")

        if hazard.status is not HazardStatus.IDENTIFIED and not hazard.mitigations:
            errors.append(f"{hazard.id} is {hazard.status.value} with no mitigation")
        if hazard.status is HazardStatus.MITIGATION_VERIFIED and not hazard.mitigations:
            errors.append(f"{hazard.id} claims verified mitigation with no mitigation")

        eliminated_probability = hazard.residual_probability is Probability.ELIMINATED
        if (hazard.status is HazardStatus.ELIMINATED) != eliminated_probability:
            errors.append(
                f"{hazard.id} status {hazard.status.value} disagrees with residual "
                f"probability {hazard.residual_probability.value}: eliminated status "
                "and probability F must be set together"
            )

        tokens = set(_REFERENCE_TOKEN.findall(hazard.verification))
        if not tokens & known:
            errors.append(
                f"{hazard.id} verification names no known gate, criterion, or "
                "requirement id"
            )

        if hazard.residual_severity.value < hazard.severity.value:
            errors.append(
                f"{hazard.id} residual severity {hazard.residual_severity.name} is "
                f"worse than initial severity {hazard.severity.name}"
            )
        if hazard.residual_probability.rank < hazard.probability.rank:
            errors.append(
                f"{hazard.id} residual probability "
                f"{hazard.residual_probability.value} is worse than initial "
                f"probability {hazard.probability.value}"
            )
        if hazard.residual_risk.rank > hazard.initial_risk.rank:
            errors.append(
                f"{hazard.id} residual risk {hazard.residual_risk.value} "
                f"({hazard.residual_code}) is worse than initial risk "
                f"{hazard.initial_risk.value} ({hazard.initial_code})"
            )

        acceptance = hazard.acceptance
        if acceptance is not None:
            if hazard.residual_risk is RiskLevel.HIGH:
                errors.append(
                    f"{hazard.id} carries an acceptance for a HIGH residual "
                    f"({hazard.residual_code}); a HIGH residual must be mitigated, "
                    "not accepted"
                )
            for field in acceptance.missing_fields():
                errors.append(
                    f"{hazard.id} accepts a residual with no {field}: an "
                    "acceptance missing any of "
                    f"{', '.join(REQUIRED_ACCEPTANCE_FIELDS)} is anonymous"
                )
            if acceptance.date.strip() and not _is_iso_date(acceptance.date):
                errors.append(
                    f"{hazard.id} acceptance date {acceptance.date!r} is not an "
                    "ISO-8601 date"
                )

        if not require_acceptance:
            continue
        if hazard.residual_risk is RiskLevel.HIGH:
            errors.append(
                f"{hazard.id} has a HIGH residual ({hazard.residual_code}) and "
                "cannot be exposed to people until it is mitigated"
            )
        elif acceptance_required(hazard.residual_risk) and not hazard.is_accepted:
            errors.append(
                f"{hazard.id} residual {hazard.residual_risk.value} "
                f"({hazard.residual_code}) has no signed acceptance; required "
                f"authority: {hazard.required_authority.value}"
            )

    return tuple(errors)


@dataclass(frozen=True)
class OpenItem:
    """One residual still waiting on a decision, and who has to make it."""

    hazard_id: str
    title: str
    residual_code: str
    residual_risk: RiskLevel
    required_authority: AcceptanceAuthority
    reason: str


def open_items(hazards: tuple[Hazard, ...] = HAZARDS) -> tuple[OpenItem, ...]:
    """Residuals above LOW with no signed acceptance.

    This is the work list, and on the committed registry it is every hazard
    above LOW: the machinery is built, the signatures are not.  A residual
    leaves this list only when a named person dates and scopes a rationale
    for it, or when the mitigation moves the residual down to LOW.
    """

    items: list[OpenItem] = []
    for hazard in hazards:
        level = hazard.residual_risk
        if level is RiskLevel.HIGH:
            reason = "HIGH residual: not acceptable at any authority; mitigate"
        elif not acceptance_required(level):
            continue
        elif hazard.acceptance is None:
            reason = "no acceptance record"
        elif not hazard.acceptance.is_signed:
            reason = (
                "incomplete acceptance record, missing "
                + ", ".join(hazard.acceptance.missing_fields())
            )
        else:
            continue

        items.append(
            OpenItem(
                hazard_id=hazard.id,
                title=hazard.title,
                residual_code=hazard.residual_code,
                residual_risk=level,
                required_authority=hazard.required_authority,
                reason=reason,
            )
        )
    return tuple(items)


def risk_profile(hazards: tuple[Hazard, ...] = HAZARDS) -> dict[str, object]:
    """Counts of initial and residual risk levels, and the acceptance gap."""

    initial = {level.value: 0 for level in RiskLevel}
    residual = {level.value: 0 for level in RiskLevel}
    for hazard in hazards:
        initial[hazard.initial_risk.value] += 1
        residual[hazard.residual_risk.value] += 1

    return {
        "total": len(hazards),
        "initial_by_level": initial,
        "residual_by_level": residual,
        "requiring_acceptance": sum(
            1 for hazard in hazards if acceptance_required(hazard.residual_risk)
        ),
        "accepted": sum(1 for hazard in hazards if hazard.is_accepted),
    }


def snapshot() -> dict[str, object]:
    structural = validate_hazards()
    pre_exposure = validate_hazards(require_acceptance=True)
    return {
        "valid": not structural,
        "errors": list(structural),
        "pre_exposure_errors": list(pre_exposure),
        "profile": risk_profile(),
        "matrix": {
            probability.value: {
                str(severity.value): risk_level(severity, probability).value
                for severity in SEVERITY_COLUMNS
            }
            for probability in PROBABILITY_ORDER
        },
        "acceptance_ladder": {
            level.value: required_authority(level).value for level in RiskLevel
        },
        "open_items": [
            {
                "hazard_id": item.hazard_id,
                "title": item.title,
                "residual_code": item.residual_code,
                "residual_risk": item.residual_risk.value,
                "required_authority": item.required_authority.value,
                "reason": item.reason,
            }
            for item in open_items()
        ],
        "hazards": [
            {
                "id": hazard.id,
                "title": hazard.title,
                "description": hazard.description,
                "cause": hazard.cause,
                "effect": hazard.effect,
                "initial_code": hazard.initial_code,
                "initial_risk": hazard.initial_risk.value,
                "mitigations": list(hazard.mitigations),
                "verification": hazard.verification,
                "residual_code": hazard.residual_code,
                "residual_risk": hazard.residual_risk.value,
                "required_authority": hazard.required_authority.value,
                "acceptance": (
                    None
                    if hazard.acceptance is None
                    else {
                        "accepted_by": hazard.acceptance.accepted_by,
                        "role": hazard.acceptance.role,
                        "date": hazard.acceptance.date,
                        "scope": hazard.acceptance.scope,
                        "rationale": hazard.acceptance.rationale,
                        "signed": hazard.acceptance.is_signed,
                    }
                ),
                "status": hazard.status.value,
            }
            for hazard in HAZARDS
        ],
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
