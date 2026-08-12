"""Bonded joints: shear-lag sizing, and why sizing is not the hard part.

Every composite assembly is held together by joints, and a bonded joint is
the only kind that does not put a hole through the fibre.  It is also the
only structural feature in this program whose strength cannot be verified
after the fact, and those two sentences between them contain the whole
subject.

The analysis here is Volkersen's shear-lag solution, which is the right
first model and is honest about being one.  Two adherends stretch under
load; the adhesive between them shears to transfer that load; the adherends'
strain mismatch is largest at the ends of the overlap, so that is where the
adhesive works hardest.  The governing parameter is

    omega = sqrt( (Ga / ta) (1/S1 + 1/S2) )

with ``S = E t`` the adherends' extensional stiffness.  ``1/omega`` is the
length over which load actually transfers, and everything interesting
follows from how short it is.

**Overlap length saturates.**  Past about ``6/omega`` the middle of the
overlap carries essentially nothing and adding length adds no strength at
all.  For the deployable boom that length is 3.5 mm: a 40 mm overlap is
exactly as strong as a 5 mm one, and any drawing that calls a long overlap
"for strength" is describing something else.  Overlap in this program is
sized by handling, tolerance and peel resistance, and the specification says
so rather than implying a strength benefit that does not exist.

**A thicker bondline can be stronger.**  ``omega`` falls as the square root
of bondline thickness, so a slightly thicker, softer adhesive layer spreads
the load transfer and lowers the peak.  This is genuinely counterintuitive
and genuinely bounded: past a few tenths of a millimetre the bondline traps
voids and loses peel strength faster than it gains shear.

**"Design it to fail the adherend" is not always available.**  The standard
rule for an unverifiable bond is to make it stronger than what it joins, so
that an overload fails the laminate — which is visible and inspectable —
rather than the bondline, which is neither.  That rule is achievable for a
thin adherend and *arithmetically impossible* for a thick one: the keeper
tine's laminate carries 729 N/mm, and no adhesive at any bondline thickness
reaches 1.5 times that.  Writing the rule as an unconditional requirement
would have made two of the three joints here permanently non-compliant with
no route to compliance, which is how a design rule gets ignored.  So there
are two qualification routes, the second of which is always available:
out-strength the adherend, **or** carry margin on the design load *and* a
proof test on every article.

**Strength is not the problem.**  Every bond in this set has hundreds of
times the margin its actual load needs, because the loads are tiny.  The
governing risk is a **kissing bond** — surfaces in full intimate contact
with no adhesion across them — which has near-zero strength, looks perfect,
and returns a clean ultrasonic inspection because there is no gap to
reflect from.  No amount of overlap protects against it.  What protects
against it is surface preparation, bondline thickness control, and a proof
test, and this module's real output is that those are the controls.

Limits, stated rather than implied.  Volkersen assumes the adhesive carries
shear only and the adherends do not bend.  A **single-lap** joint violates
both: its load path is eccentric, so it bends and peels, and the peel stress
it develops is what actually fails composite single laps.  The results here
are therefore *non-conservative* for a single lap, and the program's answer
is not a better model but a better joint — double lap or scarf, where the
eccentricity is designed out.  :func:`evaluate_joint` refuses to call a
single-lap joint acceptable on shear alone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math

from .materials import Basis
from .schedules import schedule

#: Factor by which a bond should out-strength its adherend, so that an
#: overload fails the laminate — which is visible and inspectable — rather
#: than the bondline, which is neither.
ADHEREND_FAILURE_FACTOR = 1.5

#: Factor of safety on a bonded joint against its design load.  Higher than
#: the structural factor elsewhere in the program because bond strength is a
#: process outcome that cannot be verified nondestructively.
BOND_FACTOR_OF_SAFETY = 2.0

#: Bondline thickness limits, mm.  Thin starves the joint and concentrates
#: the load; thick traps voids and loses peel strength.
MIN_BONDLINE_MM = 0.10
MAX_BONDLINE_MM = 0.40

#: Multiple of the load-transfer length past which added overlap is inert.
SATURATION_MULTIPLE = 6.0


class JointType(str, Enum):
    #: Two adherends overlapped. Load path is eccentric, so it peels.
    SINGLE_LAP = "single_lap"
    #: Inner adherend captured between two outer straps. Symmetric, so the
    #: eccentricity and its peel stress cancel.
    DOUBLE_LAP = "double_lap"
    #: Tapered scallop. The best joint available and the hardest to make.
    SCARF = "scarf"


@dataclass(frozen=True)
class Adhesive:
    name: str
    basis: Basis
    #: Shear modulus, MPa, and shear strength, MPa.
    shear_modulus_mpa: float
    shear_strength_mpa: float
    #: Flatwise tensile (peel) strength of the bondline, MPa.
    peel_strength_mpa: float
    #: Nominal bondline thickness the process holds, mm.
    nominal_bondline_mm: float
    cure_temperature_c: float
    note: str = ""

    def __post_init__(self) -> None:
        if self.shear_modulus_mpa <= 0 or self.shear_strength_mpa <= 0:
            raise ValueError(f"{self.name}: adhesive properties must be positive")
        if not MIN_BONDLINE_MM <= self.nominal_bondline_mm <= MAX_BONDLINE_MM:
            raise ValueError(
                f"{self.name}: nominal bondline outside the "
                f"{MIN_BONDLINE_MM}-{MAX_BONDLINE_MM} mm process band"
            )


#: Toughened epoxy film adhesive, scrim-carried.  The scrim is what holds
#: the bondline thickness, and holding the bondline thickness is most of
#: what makes a film adhesive better than a paste.
FILM_ADHESIVE = Adhesive(
    name="AF-CLASS-FILM",
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    shear_modulus_mpa=700.0,
    shear_strength_mpa=35.0,
    peel_strength_mpa=45.0,
    nominal_bondline_mm=0.20,
    cure_temperature_c=175.0,
    note="co-curable with the 180 degC prepreg system; scrim controls the bondline",
)

#: Two-part paste, room-temperature cure.  Needed wherever a bond cannot go
#: back in the oven, and it pays for that in strength and in bondline
#: control, which becomes the operator's problem instead of the scrim's.
PASTE_ADHESIVE = Adhesive(
    name="EA-CLASS-PASTE",
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    shear_modulus_mpa=500.0,
    shear_strength_mpa=25.0,
    peel_strength_mpa=25.0,
    nominal_bondline_mm=0.25,
    cure_temperature_c=25.0,
    note="bondline held by glass beads; without them an operator squeezes it out",
)

ADHESIVES: dict[str, Adhesive] = {
    adhesive.name: adhesive for adhesive in (FILM_ADHESIVE, PASTE_ADHESIVE)
}


def adhesive(name: str) -> Adhesive:
    try:
        return ADHESIVES[name]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown adhesive {name!r}; known: {sorted(ADHESIVES)}") from None


# --------------------------------------------------------------------------
# Shear lag
# --------------------------------------------------------------------------


def shear_lag_parameter(
    *,
    shear_modulus_mpa: float,
    bondline_mm: float,
    stiffness_1_n_mm: float,
    stiffness_2_n_mm: float,
) -> float:
    """Volkersen's ``omega``, 1/mm.

    ``stiffness`` is the adherend's extensional stiffness ``E t`` in N/mm.
    Its reciprocal appears twice because both adherends stretch; a rigid
    adherend contributes nothing, which is why bonding a thin laminate to
    a metal fitting behaves like bonding it to a wall.
    """

    for value in (shear_modulus_mpa, bondline_mm, stiffness_1_n_mm, stiffness_2_n_mm):
        if value <= 0:
            raise ValueError("all shear-lag inputs must be positive")
    return math.sqrt(
        (shear_modulus_mpa / bondline_mm)
        * (1.0 / stiffness_1_n_mm + 1.0 / stiffness_2_n_mm)
    )


def load_transfer_length_mm(omega_per_mm: float) -> float:
    """``1/omega``: the length over which the adhesive actually works."""

    if omega_per_mm <= 0:
        raise ValueError("omega must be positive")
    return 1.0 / omega_per_mm


def saturation_overlap_mm(omega_per_mm: float) -> float:
    """Overlap past which added length carries no additional load."""

    return SATURATION_MULTIPLE * load_transfer_length_mm(omega_per_mm)


def shear_stress_mpa(
    position_mm: float,
    *,
    load_n_per_mm: float,
    overlap_mm: float,
    omega_per_mm: float,
    stiffness_ratio: float = 1.0,
) -> float:
    """Adhesive shear at ``position_mm`` from the overlap centre, MPa.

    The Volkersen distribution:

        tau(x) = (p omega / 2) [ cosh(omega x) / sinh(omega L/2)
                                 + k sinh(omega x) / cosh(omega L/2) ]

    where ``k = (S2 - S1)/(S2 + S1)`` is the adherend stiffness imbalance.
    The cosh term is symmetric and carries the whole load; the sinh term
    integrates to zero and simply moves the peak toward whichever end has
    the more compliant adherend.
    """

    if overlap_mm <= 0:
        raise ValueError("overlap must be positive")
    if abs(position_mm) > overlap_mm / 2.0 + 1e-9:
        raise ValueError("position lies outside the overlap")
    half = omega_per_mm * overlap_mm / 2.0
    imbalance = (stiffness_ratio - 1.0) / (stiffness_ratio + 1.0)
    symmetric = math.cosh(omega_per_mm * position_mm) / math.sinh(half)
    antisymmetric = imbalance * math.sinh(omega_per_mm * position_mm) / math.cosh(half)
    return load_n_per_mm * omega_per_mm / 2.0 * (symmetric + antisymmetric)


def peak_shear_mpa(
    *,
    load_n_per_mm: float,
    overlap_mm: float,
    omega_per_mm: float,
    stiffness_ratio: float = 1.0,
) -> float:
    """Peak adhesive shear, MPa.  Occurs at one end of the overlap."""

    half = omega_per_mm * overlap_mm / 2.0
    imbalance = abs((stiffness_ratio - 1.0) / (stiffness_ratio + 1.0))
    return (
        load_n_per_mm
        * omega_per_mm
        / 2.0
        * (1.0 / math.tanh(half) + imbalance * math.tanh(half))
    )


def stress_concentration(*, overlap_mm: float, omega_per_mm: float) -> float:
    """Peak shear divided by average shear, for balanced adherends.

    ``(omega L / 2) coth(omega L / 2)``, which tends to ``omega L / 2`` for a
    long overlap — meaning the peak stops depending on ``L`` at all.  This
    single expression is why a long overlap is not a strong one.
    """

    half = omega_per_mm * overlap_mm / 2.0
    return half / math.tanh(half)


# --------------------------------------------------------------------------
# Joints
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BondedJoint:
    """One bonded joint in the assembly."""

    joint_id: str
    name: str
    description: str
    joint_type: JointType
    #: Part whose laminate forms the loaded adherend.
    adherend_part_id: str
    #: Extensional stiffness of the mating structure, N/mm.  A metal fitting
    #: is effectively rigid; ``None`` means "much stiffer than the adherend"
    #: and is modelled as such.
    mating_stiffness_n_mm: float | None
    adhesive: str
    overlap_mm: float
    width_mm: float
    #: Running load the joint is designed to carry, N/mm.
    design_load_n_per_mm: float
    design_load_basis: str
    #: Bondline thickness, mm, when the joint holds one other than the
    #: adhesive's nominal.  Thicker is not automatically worse: it lowers
    #: ``omega`` and spreads the load transfer, and a slotted fitting needs
    #: gap fill anyway.
    bondline_mm: float | None = None
    #: Proof load applied to every article, as a multiple of limit load.
    #: Zero means no proof test.  A bond that cannot out-strength its
    #: adherend has to have one: it is the only screen that finds a kissing
    #: bond before flight does.
    proof_test_factor: float = 0.0
    #: A critical joint is one whose failure endangers a captured aircraft.
    critical: bool = False
    #: Why the overlap is what it is, when strength did not set it.
    overlap_rationale: str = ""
    note: str = ""


def _adherend_stiffness_n_mm(part_id: str) -> float:
    laminate = schedule(part_id).laminate()
    return laminate.engineering_constants()["ex_mpa"] * laminate.thickness_mm


def adherend_capacity_n_per_mm(part_id: str) -> float:
    """Running load at which the adherend laminate itself fails, N/mm.

    Taken from the laminate's own first-ply-failure ratio under a unit
    running load, so the bond is always compared against the same failure
    model the part was sized with.
    """

    laminate = schedule(part_id).laminate()
    return laminate.response(n_per_mm=(1.0, 0.0, 0.0)).first_ply_failure_ratio


def evaluate_joint(joint: BondedJoint) -> dict[str, object]:
    """Size one joint and report what actually governs it."""

    glue = adhesive(joint.adhesive)
    bondline = joint.bondline_mm if joint.bondline_mm is not None else glue.nominal_bondline_mm
    adherend_stiffness = _adherend_stiffness_n_mm(joint.adherend_part_id)
    # A mating structure much stiffer than the adherend contributes almost
    # nothing to the strain mismatch; modelled as a large finite stiffness so
    # the arithmetic stays a limit rather than a special case.
    mating_stiffness = (
        joint.mating_stiffness_n_mm
        if joint.mating_stiffness_n_mm is not None
        else adherend_stiffness * 1000.0
    )

    if joint.joint_type is JointType.DOUBLE_LAP:
        # Symmetric half: the inner adherend splits its stiffness between two
        # bondlines, and each bondline carries half the load.
        effective_adherend = adherend_stiffness / 2.0
        bondlines = 2
    else:
        effective_adherend = adherend_stiffness
        bondlines = 1

    omega = shear_lag_parameter(
        shear_modulus_mpa=glue.shear_modulus_mpa,
        bondline_mm=bondline,
        stiffness_1_n_mm=effective_adherend,
        stiffness_2_n_mm=mating_stiffness,
    )
    load_per_bondline = joint.design_load_n_per_mm / bondlines
    ratio = mating_stiffness / effective_adherend
    peak = peak_shear_mpa(
        load_n_per_mm=load_per_bondline,
        overlap_mm=joint.overlap_mm,
        omega_per_mm=omega,
        stiffness_ratio=ratio,
    )
    # Capacity: invert the peak-shear expression at the adhesive's strength.
    capacity_per_bondline = (
        glue.shear_strength_mpa
        / peak_shear_mpa(
            load_n_per_mm=1.0,
            overlap_mm=joint.overlap_mm,
            omega_per_mm=omega,
            stiffness_ratio=ratio,
        )
    )
    capacity = capacity_per_bondline * bondlines
    adherend_capacity = adherend_capacity_n_per_mm(joint.adherend_part_id)
    saturation = saturation_overlap_mm(omega)

    adherend_first = capacity >= ADHEREND_FAILURE_FACTOR * adherend_capacity
    load_margin_met = capacity >= BOND_FACTOR_OF_SAFETY * joint.design_load_n_per_mm
    proof_tested = joint.proof_test_factor > 0.0

    checks = [
        {
            "name": "margin_on_design_load",
            "actual": round(capacity / joint.design_load_n_per_mm, 2),
            "limit": BOND_FACTOR_OF_SAFETY,
            "comparison": ">=",
            "passed": load_margin_met,
            "consequence": "the joint fails below its factored design load",
        },
        {
            # Two ways to qualify a bond, and only one of them is always
            # available.  Out-strengthing the adherend means an overload
            # fails the laminate, which is visible; it is achievable for a
            # thin adherend and arithmetically impossible for a thick one.
            # Where it is impossible, the joint must instead carry margin
            # against its load *and* a proof test on every article, because
            # nothing else screens a kissing bond.
            "name": "qualification_route",
            "actual": (
                "adherend-first"
                if adherend_first
                else ("load margin + proof test" if proof_tested else "none")
            ),
            "limit": "adherend-first, or load margin with a proof test",
            "comparison": "==",
            "passed": adherend_first or (load_margin_met and proof_tested),
            "consequence": (
                "the joint has no qualification route: it cannot out-strength its "
                "adherend and has no proof test, so nothing distinguishes a good "
                "bond from a kissing bond before flight"
            ),
        },
        {
            "name": "critical_joint_is_proof_tested",
            "actual": joint.proof_test_factor,
            "limit": 1.0,
            "comparison": ">=" if joint.critical else "n/a",
            "passed": (not joint.critical) or joint.proof_test_factor >= 1.0,
            "consequence": (
                "a critical bond is unverifiable without a proof test, whatever "
                "its calculated margin"
            ),
        },
        {
            "name": "bondline_thickness_mm",
            "actual": bondline,
            "limit": [MIN_BONDLINE_MM, MAX_BONDLINE_MM],
            "comparison": "within",
            "passed": MIN_BONDLINE_MM <= bondline <= MAX_BONDLINE_MM,
            "consequence": "thin starves and concentrates; thick traps voids and loses peel",
        },
        {
            "name": "not_single_lap_when_critical",
            "actual": joint.joint_type.value,
            "limit": "double_lap or scarf",
            "comparison": "==",
            "passed": not (joint.critical and joint.joint_type is JointType.SINGLE_LAP),
            "consequence": (
                "a single lap peels, and this model does not predict peel, so a "
                "critical single-lap joint is unsized rather than sized"
            ),
        },
    ]

    return {
        "joint_id": joint.joint_id,
        "name": joint.name,
        "description": joint.description,
        "joint_type": joint.joint_type.value,
        "critical": joint.critical,
        "adhesive": joint.adhesive,
        "bondlines": bondlines,
        "adherend_part_id": joint.adherend_part_id,
        "adherend_stiffness_n_mm": round(adherend_stiffness, 1),
        "adherend_capacity_n_per_mm": round(adherend_capacity, 2),
        "omega_per_mm": round(omega, 4),
        "load_transfer_length_mm": round(load_transfer_length_mm(omega), 3),
        "saturation_overlap_mm": round(saturation, 2),
        "overlap_mm": joint.overlap_mm,
        # The number that says a long overlap bought nothing.
        "overlap_beyond_saturation_mm": round(max(joint.overlap_mm - saturation, 0.0), 2),
        "overlap_rationale": joint.overlap_rationale,
        "stress_concentration": round(
            stress_concentration(overlap_mm=joint.overlap_mm, omega_per_mm=omega), 2
        ),
        "design_load_n_per_mm": joint.design_load_n_per_mm,
        "design_load_basis": joint.design_load_basis,
        "peak_shear_mpa": round(peak, 3),
        "adhesive_shear_strength_mpa": glue.shear_strength_mpa,
        "capacity_n_per_mm": round(capacity, 2),
        "bondline_mm": bondline,
        "adherend_first_ratio": round(capacity / adherend_capacity, 2),
        "bondline_for_adherend_first_mm": round(
            bondline * (ADHEREND_FAILURE_FACTOR * adherend_capacity / capacity) ** 2, 3
        ),
        "adherend_first_achievable": (
            bondline * (ADHEREND_FAILURE_FACTOR * adherend_capacity / capacity) ** 2
            <= MAX_BONDLINE_MM
        ),
        "proof_test_factor": joint.proof_test_factor,
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "note": joint.note,
    }


# --------------------------------------------------------------------------
# The program's joints
# --------------------------------------------------------------------------

JOINTS: tuple[BondedJoint, ...] = (
    BondedJoint(
        joint_id="BJ-100",
        name="throat cup flange to dock body",
        description=(
            "Bonded flange carrying the throat cup into the dock structure. "
            "Double lap so the cup's moulded flange is captured between the "
            "body and a retaining ring, which removes the eccentricity."
        ),
        joint_type=JointType.DOUBLE_LAP,
        adherend_part_id="CS-100",
        mating_stiffness_n_mm=None,
        adhesive="AF-CLASS-FILM",
        overlap_mm=12.0,
        width_mm=345.0,
        proof_test_factor=1.2,
        design_load_n_per_mm=0.05,
        design_load_basis=(
            "aircraft contact load spread around the throat circumference; "
            "derived from the P0 capture energy, and very small"
        ),
        overlap_rationale=(
            "12 mm is set by flange width, fit-up tolerance and having somewhere "
            "to put the adhesive, not by strength: load transfer saturates at "
            "about 9 mm and the last 3 mm carry nothing"
        ),
        note="cured with the part where schedule allows, co-bonded otherwise",
    ),
    BondedJoint(
        joint_id="BJ-200",
        name="deployable boom root to hub fitting",
        description=(
            "The boom's root, bonded into a slotted hub fitting. The highest-"
            "loaded bond in the set and the one that decides whether the "
            "capture ring deploys."
        ),
        joint_type=JointType.DOUBLE_LAP,
        adherend_part_id="CS-200",
        mating_stiffness_n_mm=None,
        adhesive="AF-CLASS-FILM",
        overlap_mm=15.0,
        width_mm=35.0,
        bondline_mm=0.30,
        proof_test_factor=1.2,
        design_load_n_per_mm=2.0,
        design_load_basis=(
            "deployment and membrane-tension reaction at the boom root, as an "
            "engineering target pending a deployed-load measurement"
        ),
        overlap_rationale=(
            "15 mm is a handling and fit-up length. Load transfer saturates at "
            "3.5 mm; a 40 mm overlap would carry exactly what a 5 mm one does"
        ),
        note=(
            "The one joint in the set that can be made to fail its adherend "
            "first, and it takes a 0.30 mm bondline to do it. At the "
            "adhesive's 0.20 mm nominal the ratio is 1.29 against a 1.5 "
            "requirement; thickening the bondline lowers omega, spreads the "
            "load transfer and reaches 1.57. That the joint gets stronger as "
            "the glue line gets thicker is real and is bounded — past about "
            "0.4 mm the bondline traps voids faster than it gains shear. The "
            "slotted fitting needs the gap fill anyway."
        ),
    ),
    BondedJoint(
        joint_id="BJ-300",
        name="keeper tine root to carrier",
        description=(
            "The tine's root into the keeper carriage. On the retention path: "
            "its failure drops a captured aircraft."
        ),
        joint_type=JointType.DOUBLE_LAP,
        adherend_part_id="CS-400",
        mating_stiffness_n_mm=None,
        adhesive="AF-CLASS-FILM",
        overlap_mm=18.0,
        width_mm=12.0,
        proof_test_factor=1.5,
        design_load_n_per_mm=0.24,
        design_load_basis=(
            "retention force at the limit load factor spread over the 12 mm "
            "tine width; derived from the P0 mass budget"
        ),
        critical=True,
        overlap_rationale=(
            "18 mm follows the carrier's own geometry. Strength did not set it "
            "and could not: the design load is 0.24 N/mm against a capacity "
            "three orders of magnitude above it"
        ),
        note=(
            "The one bond on the retention path, and the one where the margin "
            "is irrelevant. A kissing bond here has near-zero strength, passes "
            "ultrasonic inspection, and is caught only by surface-preparation "
            "control and a proof test. PS-400 is written around that."
        ),
    ),
)


def joint(joint_id: str) -> BondedJoint:
    for item in JOINTS:
        if item.joint_id == joint_id:
            return item
    raise KeyError(f"unknown joint {joint_id!r}")


# --------------------------------------------------------------------------
# Surface preparation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfacePreparation:
    """One way of preparing a composite surface for bonding."""

    name: str
    #: Relative bond durability, judgement, best = 1.0.
    durability: float
    #: How reliably it is executed by a technician under time pressure.
    repeatability: float
    #: Whether it leaves a contamination risk that is invisible afterwards.
    contamination_risk: str
    note: str


SURFACE_PREPARATIONS: tuple[SurfacePreparation, ...] = (
    SurfacePreparation(
        "peel ply, removed immediately before bonding",
        durability=0.85,
        repeatability=0.90,
        contamination_risk="high if the ply carries a release agent",
        note=(
            "Convenient and the default everywhere, and the source of most "
            "bonding failures: a peel ply treated with release agent to make it "
            "peel easily transfers that agent to the surface it just exposed. "
            "Peel ply must be qualified as a bonding surface, not assumed to be one."
        ),
    ),
    SurfacePreparation(
        "abrasion and solvent wipe",
        durability=0.90,
        repeatability=0.60,
        contamination_risk="moderate; depends entirely on operator technique",
        note=(
            "Works well and varies with who does it. Abrade through the resin "
            "without cutting fibre, and the window between the two is narrow."
        ),
    ),
    SurfacePreparation(
        "atmospheric plasma",
        durability=1.00,
        repeatability=0.95,
        contamination_risk="low",
        note=(
            "The best available and the only one that is genuinely measurable "
            "in process, by water-break or contact angle. Needs equipment this "
            "program does not have, and is the upgrade path if bond yield "
            "becomes the constraint."
        ),
    ),
)


def snapshot() -> dict[str, object]:
    results = [evaluate_joint(item) for item in JOINTS]
    failures = [
        {"joint_id": result["joint_id"], "check": check["name"], "critical": result["critical"]}
        for result in results
        for check in result["checks"]  # type: ignore[union-attr]
        if not check["passed"]
    ]
    return {
        "units": {"stress": "MPa", "length": "mm", "running_load": "N/mm"},
        "valid": not failures,
        "failing_checks": failures,
        "critical_failures": [failure for failure in failures if failure["critical"]],
        "design_rules": {
            "adherend_failure_factor": ADHEREND_FAILURE_FACTOR,
            "bond_factor_of_safety": BOND_FACTOR_OF_SAFETY,
            "bondline_band_mm": [MIN_BONDLINE_MM, MAX_BONDLINE_MM],
            "saturation_multiple": SATURATION_MULTIPLE,
        },
        "governing_risk": (
            "Not strength. Every joint here carries far more than its load. The "
            "governing risk is a kissing bond: full contact, no adhesion, "
            "near-zero strength, and no ultrasonic signature because there is no "
            "gap to reflect from. Surface preparation, bondline control and a "
            "proof test are the controls; overlap length is not."
        ),
        "adhesives": [asdict(item) for item in ADHESIVES.values()],
        "surface_preparations": [asdict(item) for item in SURFACE_PREPARATIONS],
        "joints": results,
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    if report["critical_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
