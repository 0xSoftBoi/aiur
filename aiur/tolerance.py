"""Executable tolerance stack for the CARRIER-P0 capture chain.

Rev-A geometry (``hardware/dock/cad/generate_rev_a.py``) is drawn at nominal.
Nominal geometry is a statement about a drawing, not about the part that comes
off the printer: an FDM funnel, an FDM keeper, a commodity rod, and a bolted
assembly each contribute their own variation, and the capture chain is a series
of small differences between larger numbers.  A 4.2 mm slot on a 3 mm mast has
0.6 mm of clearance per side; the printer's own tolerance is half of that.
Stacking those contributions by hand once, in a document, is how a design ships
a jam or a drop.  So the stack is code, it runs in CI, and a stack that closes
only at nominal is reported as a finding instead of being rounded away.

Two conventions make the arithmetic auditable:

* Every contributor carries a **sign**: ``+1`` when growing that dimension opens
  the clearance, ``-1`` when growing it closes the clearance.  The clearance at
  nominal is ``sum(sign * nominal)``; the worst case subtracts each dimension's
  tolerance *in the direction that closes the clearance* (a ``+1`` contributor
  closes on its minus tolerance, a ``-1`` contributor on its plus tolerance).
* Every tolerance here is an **explicitly labeled engineering target**, not a
  measured process capability and not a vendor figure.  ``ASSUMPTIONS`` lists
  them with their basis.  They exist to be deleted: the as-built template in
  ``hardware/dock`` collects the caliper set for a physical article, and
  :func:`as_built` re-runs any stack against that article's real numbers.  The
  predicted stack sizes the design; the as-built stack accepts an article.

``critical`` marks the stacks whose failure defeats retention (the dock drops a
captured aircraft) or defeats release (the dock traps one).  A non-critical
stack failure prevents capture, which is a benign abort.

Rev-A failed all three critical stacks — it could bind on the mast, its
retention ledge vanished at worst case, and its keeper could not retract far
enough to release a captured aircraft at all.  Rev-B moves four coupled
dimensions and closes every stack with margin; ``RESOLVED_FINDINGS`` keeps the
reason on the record.  :func:`validate_stacks` requires the finding record to
stay in sync in both directions, so a failure cannot be silenced by loosening a
minimum and a stale finding cannot outlive its own fix.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Mapping


#: Assumed process tolerances.  Every one of them is an engineering target
#: standing in for a measurement this program has not taken yet, so each is
#: restated with its basis in ``ASSUMPTIONS`` and each is replaceable per
#: article by :func:`as_built`.  Printed tolerance is split at a feature size
#: because shrink and warp scale with the dimension, while a small printed
#: feature is dominated by extrusion width and first-layer squish.
FDM_TOLERANCE_SMALL_MM = 0.30
FDM_TOLERANCE_LARGE_MM = 0.50
FDM_LARGE_FEATURE_MM = 50.0

#: Extra minus-side allowance on printed internal features, which are assumed
#: to close up by roughly one extrusion trace.  Carried as asymmetry rather
#: than as a shifted nominal so the assumption stays visible in the report.
FDM_INTERNAL_UNDERSIZE_MM = 0.20

#: Commodity Ø3 rod is not a printed feature and does not deserve the printed
#: tolerance; it gets its own tighter, separately labeled figure.
ROD_STOCK_TOLERANCE_MM = 0.05

#: Delivered keeper stroke and seated lateral position are assembly-level
#: outcomes, not part features, so they carry their own targets.
ACTUATED_TRAVEL_TOLERANCE_MM = 0.40
SEATED_LATERAL_TOLERANCE_MM = 0.35

#: As-built measurement uncertainty, taken as caliper display resolution.
CALIPER_UNCERTAINTY_MM = 0.02

#: Dimensions that are a difference of two measured features rather than one.
#: An as-built record measures the parts, not the fit, so a derived dimension
#: inherits both measurements' uncertainty — added arithmetically, matching
#: the worst-case convention used everywhere else in this module.
DERIVED_DIMENSIONS: frozenset[str] = frozenset({"probe_head_to_mast_float"})


@dataclass(frozen=True)
class Assumption:
    """One labeled engineering target that the stack currently rests on."""

    name: str
    value_mm: float
    basis: str


ASSUMPTIONS: tuple[Assumption, ...] = (
    Assumption(
        "fdm_tolerance_small",
        FDM_TOLERANCE_SMALL_MM,
        "engineering target: plus/minus tolerance on a printed feature below "
        f"{FDM_LARGE_FEATURE_MM:g} mm. Not a measured process capability; the "
        "as-built template exists to replace it per printer and material lot.",
    ),
    Assumption(
        "fdm_tolerance_large",
        FDM_TOLERANCE_LARGE_MM,
        "engineering target: plus/minus tolerance on a printed feature at or "
        f"above {FDM_LARGE_FEATURE_MM:g} mm, where shrink and warp scale with "
        "size.",
    ),
    Assumption(
        "fdm_internal_undersize",
        FDM_INTERNAL_UNDERSIZE_MM,
        "engineering target: extra minus-side allowance on printed internal "
        "features (bores, slots), which are assumed to bias undersize. Applied "
        "as asymmetry, not as a shifted nominal, so the assumption is visible.",
    ),
    Assumption(
        "rod_stock_tolerance",
        ROD_STOCK_TOLERANCE_MM,
        "engineering target for commodity Ø3 rod stock, tighter than the "
        "printed tolerance because the mast is drawn or extruded stock rather "
        "than a printed feature. Confirm with a micrometer on the received "
        "lot; no vendor tolerance is claimed here.",
    ),
    Assumption(
        "actuated_travel_tolerance",
        ACTUATED_TRAVEL_TOLERANCE_MM,
        "engineering target on delivered keeper stroke: XL330-M288-T horn "
        "radius error, linkage backlash, and travel-stop repeatability lumped "
        "into one tolerance. Measure the real stroke with a dial indicator.",
    ),
    Assumption(
        "seated_lateral_tolerance",
        SEATED_LATERAL_TOLERANCE_MM,
        "engineering target for the lateral offset between the seated probe "
        "mast and the keeper slot centreline at the keeper plane: funnel "
        "throat concentricity, keeper-carrier registration through M3 "
        "clearance holes, guide cross-travel play, and residual probe "
        "centring. The CAD contains no centring feature at the keeper plane (the "
        "terminal collet in hardware/dock/README.md is not modelled), so this "
        "tolerance is assumed, not demonstrated. It is the dominant unknown in "
        "two stacks, which is why Rev-B was sized to tolerate roughly twice "
        "it — measure it at A0 before trusting either margin.",
    ),
    Assumption(
        "caliper_uncertainty",
        CALIPER_UNCERTAINTY_MM,
        "engineering target for as-built measurement uncertainty, taken as "
        "digital-caliper display resolution. Replace with a gauge study before "
        "an as-built margin below 0.1 mm is used to accept an article.",
    ),
)


@dataclass(frozen=True)
class Dimension:
    """One dimension in a stack, with its tolerance stated as magnitudes."""

    name: str
    nominal_mm: float
    plus_tol_mm: float
    minus_tol_mm: float
    process: str
    source: str

    def __post_init__(self) -> None:
        if self.plus_tol_mm < 0.0 or self.minus_tol_mm < 0.0:
            raise ValueError(f"{self.name}: tolerances are magnitudes and must be >= 0")

    @property
    def max_mm(self) -> float:
        return self.nominal_mm + self.plus_tol_mm

    @property
    def min_mm(self) -> float:
        return self.nominal_mm - self.minus_tol_mm

    def closing_tolerance_mm(self, sign: int) -> float:
        """Tolerance magnitude in the direction that closes the clearance."""

        if sign == 1:
            return self.minus_tol_mm
        if sign == -1:
            return self.plus_tol_mm
        raise ValueError(f"{self.name}: sign must be +1 or -1, got {sign!r}")


def fdm_tolerance_mm(feature_size_mm: float) -> float:
    """Assumed plus/minus FDM tolerance for a feature of this size."""

    if abs(feature_size_mm) >= FDM_LARGE_FEATURE_MM:
        return FDM_TOLERANCE_LARGE_MM
    return FDM_TOLERANCE_SMALL_MM


def printed_length(name: str, nominal_mm: float, source: str) -> Dimension:
    """Printed external length, symmetric about nominal."""

    tolerance = fdm_tolerance_mm(nominal_mm)
    return Dimension(
        name,
        nominal_mm,
        tolerance,
        tolerance,
        "FDM printed (external feature)",
        source,
    )


def printed_radius(
    name: str,
    diameter_mm: float,
    source: str,
    *,
    internal: bool,
) -> Dimension:
    """Radial dimension derived from a printed diameter.

    The tolerance is chosen at the diameter's scale and then halved: a diametral
    variation is assumed to be shared equally between the two sides of a
    nominally round, concentric feature.  Gross eccentricity is not folded in
    here — it is carried explicitly by ``seated_probe_lateral_offset`` so it
    stays visible and measurable.
    """

    tolerance = fdm_tolerance_mm(diameter_mm)
    minus = tolerance + (FDM_INTERNAL_UNDERSIZE_MM if internal else 0.0)
    kind = "internal" if internal else "external"
    return Dimension(
        name,
        diameter_mm / 2.0,
        tolerance / 2.0,
        minus / 2.0,
        f"FDM printed ({kind} feature)",
        f"{source}; radius derived from the printed diameter",
    )


def rod_radius(name: str, diameter_mm: float, source: str) -> Dimension:
    """Radial dimension of commodity rod stock, at the rod tolerance."""

    return Dimension(
        name,
        diameter_mm / 2.0,
        ROD_STOCK_TOLERANCE_MM / 2.0,
        ROD_STOCK_TOLERANCE_MM / 2.0,
        "extruded rod stock",
        f"{source}; radius derived from the stock diameter",
    )


def lateral_offset(
    name: str,
    tolerance_mm: float,
    process: str,
    source: str,
) -> Dimension:
    """A positional contributor: zero at nominal, error in either direction."""

    return Dimension(name, 0.0, tolerance_mm, tolerance_mm, process, source)


FUNNEL_THROAT_RADIUS = printed_radius(
    "funnel_throat_radius",
    16.0,
    "generate_rev_a.RevA.funnel_throat_diameter_mm = 16.0",
    internal=True,
)
PROBE_HEAD_MAX_RADIUS = printed_radius(
    "probe_head_max_radius",
    12.0,
    "generate_rev_a.RevA.probe_head_diameter_mm = 12.0; the Ø12 belt is the "
    "profile point (6.0, 6.0) in probe_head_mesh()",
    internal=False,
)
PROBE_HEAD_SEAT_RADIUS = printed_radius(
    "probe_head_seat_radius",
    9.0,
    "generate_rev_a.REV_B.probe_head_seat_diameter_mm = 9.0; the head's lower "
    "cylinder is what the keeper bears on, and the Ø12 belt above it is a "
    "funnel-guidance diameter that never touches the keeper. Rev-A used Ø6, "
    "which left a 0.8 mm nominal ledge that the stack consumed entirely",
    internal=False,
)
PROBE_HEAD_BORE_RADIUS = printed_radius(
    "probe_head_bore_radius",
    3.2,
    "generate_rev_a.RevA.probe_head_bore_diameter_mm = 3.2",
    internal=True,
)
PROBE_MAST_RADIUS = rod_radius(
    "probe_mast_radius",
    3.0,
    "generate_rev_a.RevA.probe_mast_diameter_mm = 3.0, commodity Ø3 rod",
)
KEEPER_SLOT_HALF_WIDTH = printed_radius(
    "keeper_slot_half_width",
    5.2,
    "generate_rev_a.REV_B.keeper_slot_width_mm = 5.2; widened from Rev-A's 4.2 "
    "so the slot clears the mast at worst case. The widening costs retention "
    "ledge, which is why the seat diameter moved with it",
    internal=True,
)
KEEPER_TINE_REACH = printed_length(
    "keeper_tine_reach",
    5.0,
    "generate_rev_a.REV_B.keeper_tine_reach_mm = 5.0, the keeper_mesh() polygon "
    "right edge measured from the slot round-end centre, which sits on the dock "
    "axis when the keeper is closed. Shortened from Rev-A's 8.0: every "
    "millimetre of reach is a millimetre of stroke the servo must deliver to "
    "release, and 5.0 still fully bears the Ø9 seat",
)
KEEPER_OPEN_TRAVEL = Dimension(
    "keeper_open_travel",
    13.0,
    ACTUATED_TRAVEL_TOLERANCE_MM,
    ACTUATED_TRAVEL_TOLERANCE_MM,
    "servo-driven linkage",
    "generate_rev_a.REV_B.keeper_open_travel_mm = 13.0, delivered by the "
    "XL330-M288-T through a horn and link. Rev-A declared 11.0 while its "
    "geometry needed 13.62; the CAD now derives the requirement from the "
    "tine reach and head diameter so the two cannot drift apart again. The "
    "longer stroke is a linkage requirement to verify at A0, not a free "
    "parameter",
)
SEATED_PROBE_LATERAL_OFFSET = lateral_offset(
    "seated_probe_lateral_offset",
    SEATED_LATERAL_TOLERANCE_MM,
    "assembly datum",
    "assumed lateral offset between the seated mast axis and the keeper slot "
    "centreline at the keeper plane; see the seated_lateral_tolerance assumption",
)


def _head_to_mast_float() -> Dimension:
    """Radial float of the printed head on the mast, derived from both fits.

    The head is a printed Ø3.2 bore on Ø3 rod, so its axis can sit off the mast
    axis by the radial difference.  The minus side is clipped at zero float: a
    bore that prints smaller than the mast is reamed to fit at assembly, it does
    not become an interference the stack can spend.
    """

    nominal = PROBE_HEAD_BORE_RADIUS.nominal_mm - PROBE_MAST_RADIUS.nominal_mm
    largest = PROBE_HEAD_BORE_RADIUS.max_mm - PROBE_MAST_RADIUS.min_mm
    smallest = max(0.0, PROBE_HEAD_BORE_RADIUS.min_mm - PROBE_MAST_RADIUS.max_mm)
    return Dimension(
        "probe_head_to_mast_float",
        nominal,
        largest - nominal,
        nominal - smallest,
        "derived fit",
        "derived from probe_head_bore_radius and probe_mast_radius; the mast "
        "carries no separate contribution where this term appears, so its own "
        "is not counted twice",
    )


PROBE_HEAD_TO_MAST_FLOAT = _head_to_mast_float()

DIMENSIONS: tuple[Dimension, ...] = (
    FUNNEL_THROAT_RADIUS,
    PROBE_HEAD_MAX_RADIUS,
    PROBE_HEAD_SEAT_RADIUS,
    PROBE_HEAD_BORE_RADIUS,
    PROBE_MAST_RADIUS,
    PROBE_HEAD_TO_MAST_FLOAT,
    KEEPER_SLOT_HALF_WIDTH,
    KEEPER_TINE_REACH,
    KEEPER_OPEN_TRAVEL,
    SEATED_PROBE_LATERAL_OFFSET,
)


@dataclass(frozen=True)
class Stack:
    """A one-dimensional clearance built from signed contributors."""

    name: str
    description: str
    contributors: tuple[tuple[Dimension, int], ...]
    minimum_mm: float
    minimum_rationale: str
    critical: bool

    def __post_init__(self) -> None:
        if len(self.contributors) < 2:
            raise ValueError(f"{self.name}: a stack needs at least two contributors")
        if self.minimum_mm < 0.0:
            raise ValueError(
                f"{self.name}: required minimum clearance cannot be negative"
            )
        names = [dimension.name for dimension, _ in self.contributors]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name}: a dimension appears twice in the same stack")
        for dimension, sign in self.contributors:
            # Raises for any sign other than +1/-1.
            dimension.closing_tolerance_mm(sign)


ENTRY_CLEARANCE = Stack(
    name="probe_head_entry_clearance",
    description=(
        "Radial clearance between the Ø12 probe-head belt and the Ø16 funnel "
        "throat. The funnel absorbs the last millimetres of lateral error, so "
        "this clearance is what makes the throat a guide instead of a stop."
    ),
    contributors=(
        (FUNNEL_THROAT_RADIUS, 1),
        (PROBE_HEAD_MAX_RADIUS, -1),
    ),
    minimum_mm=0.50,
    minimum_rationale=(
        "Engineering target. 0.5 mm radial covers first-layer bulge and "
        "stringing on the printed throat and keeps insertion a sliding fit. A "
        "press fit shows up as insertion force on the P0-A cycle sheet, which "
        "the capture logic cannot see and the approach controller cannot fly."
    ),
    critical=False,
)

SLOT_MAST_CLEARANCE = Stack(
    name="keeper_slot_mast_clearance",
    description=(
        "Per-side clearance between the keeper slot wall and the Ø3 mast with "
        "the keeper closed. The slot must remain a clearance fit through the "
        "whole stroke."
    ),
    contributors=(
        (KEEPER_SLOT_HALF_WIDTH, 1),
        (PROBE_MAST_RADIUS, -1),
        (SEATED_PROBE_LATERAL_OFFSET, -1),
    ),
    minimum_mm=0.10,
    minimum_rationale=(
        "Engineering target. A slot that pinches the mast turns keeper travel "
        "into a side load on the probe and can stall the XL330-M288-T short of "
        "its closed stop, so S2 never closes and capture is never confirmed; "
        "the same pinch blocks release. 0.1 mm per side is the smallest gap "
        "that is still a gap after slot-lip rounding on a printed part."
    ),
    critical=True,
)

KEEPER_HEAD_OVERLAP = Stack(
    name="keeper_head_overlap",
    description=(
        "Radial overlap of the keeper tine under the probe-head seat face. "
        "This ledge is the entire mechanical retention path: the governing "
        "diameter is the head's Ø6 lower cylinder, not the Ø12 belt."
    ),
    contributors=(
        (PROBE_HEAD_SEAT_RADIUS, 1),
        (KEEPER_SLOT_HALF_WIDTH, -1),
        (PROBE_HEAD_TO_MAST_FLOAT, -1),
        (SEATED_PROBE_LATERAL_OFFSET, -1),
    ),
    minimum_mm=0.50,
    minimum_rationale=(
        "Engineering target. At zero overlap the keeper is not under the head "
        "and the dock drops the aircraft, so this stack is sized for margin "
        "rather than for existence: 0.5 mm per side leaves a ledge after "
        "slot-lip rounding on a printed part and keeps the ledge wider than "
        "the assumed lateral offset, so a lateral disturbance cannot walk the "
        "tine out from under the head. Contact pressure is not the driver at "
        "5 N on this footprint; loss of engagement is."
    ),
    critical=True,
)

RELEASE_CLEARANCE = Stack(
    name="keeper_release_clearance",
    description=(
        "Retraction left over after the keeper tine tips clear the head's "
        "widest belt on release. Linear and therefore conservative: the tines "
        "only exist outside the slot half width, so the exact requirement is "
        "keeper_tine_reach + sqrt(head_max_radius^2 - slot_half_width^2), "
        "reported as EXACT_RELEASE_TRAVEL_MM."
    ),
    contributors=(
        (KEEPER_OPEN_TRAVEL, 1),
        (KEEPER_TINE_REACH, -1),
        (PROBE_HEAD_MAX_RADIUS, -1),
    ),
    minimum_mm=0.50,
    minimum_rationale=(
        "Engineering target. Release is a safety path: the head must pass the "
        "keeper plane on a normal release and on an emergency release ordered "
        "while the autonomy computer is confused. 0.5 mm keeps the head off "
        "the tine tips so release is a clean drop rather than a scrape whose "
        "friction depends on print finish."
    ),
    critical=True,
)

STACKS: tuple[Stack, ...] = (
    ENTRY_CLEARANCE,
    SLOT_MAST_CLEARANCE,
    KEEPER_HEAD_OVERLAP,
    RELEASE_CLEARANCE,
)

EXACT_RELEASE_TRAVEL_MM = KEEPER_TINE_REACH.nominal_mm + math.sqrt(
    PROBE_HEAD_MAX_RADIUS.nominal_mm**2 - KEEPER_SLOT_HALF_WIDTH.nominal_mm**2
)


@dataclass(frozen=True)
class StackResult:
    name: str
    critical: bool
    nominal_mm: float
    worst_case_mm: float
    rss_mm: float
    minimum_mm: float
    worst_case_margin_mm: float
    rss_margin_mm: float
    passes_worst_case: bool
    passes_rss: bool


def nominal_mm(stack: Stack) -> float:
    """Clearance with every dimension exactly on its nominal."""

    return sum(sign * dimension.nominal_mm for dimension, sign in stack.contributors)


def worst_case_mm(stack: Stack) -> float:
    """Arithmetic worst case: every contributor at its clearance-closing limit."""

    closing = sum(
        dimension.closing_tolerance_mm(sign) for dimension, sign in stack.contributors
    )
    return nominal_mm(stack) - closing


def rss_mm(stack: Stack) -> float:
    """Statistical stack: root-sum-square of the clearance-closing tolerances.

    Same contributions as the worst case, combined in quadrature.  This is a
    bounding statistical estimate, not a distribution: the asymmetric bands on
    printed internal features also shift the mean, and that shift is left in the
    worst-case column rather than being credited here.
    """

    closing = math.sqrt(
        sum(
            dimension.closing_tolerance_mm(sign) ** 2
            for dimension, sign in stack.contributors
        )
    )
    return nominal_mm(stack) - closing


def dominant_contributor(stack: Stack) -> tuple[str, float]:
    """Name and magnitude of the largest clearance-closing contribution."""

    ranked = sorted(
        (
            (dimension.closing_tolerance_mm(sign), dimension.name)
            for dimension, sign in stack.contributors
        ),
        reverse=True,
    )
    magnitude, name = ranked[0]
    return name, magnitude


def evaluate_stack(stack: Stack) -> StackResult:
    """Full verdict for one stack: nominal, worst case, RSS, margins, pass/fail."""

    worst_case = worst_case_mm(stack)
    rss = rss_mm(stack)
    return StackResult(
        name=stack.name,
        critical=stack.critical,
        nominal_mm=nominal_mm(stack),
        worst_case_mm=worst_case,
        rss_mm=rss,
        minimum_mm=stack.minimum_mm,
        worst_case_margin_mm=worst_case - stack.minimum_mm,
        rss_margin_mm=rss - stack.minimum_mm,
        passes_worst_case=worst_case >= stack.minimum_mm,
        passes_rss=rss >= stack.minimum_mm,
    )


def evaluate_all(stacks: tuple[Stack, ...] = STACKS) -> tuple[StackResult, ...]:
    """Evaluate every stack in definition order."""

    return tuple(evaluate_stack(stack) for stack in stacks)


@dataclass(frozen=True)
class ChainVerdict:
    passed: bool
    critical_failures: tuple[str, ...]
    advisory_failures: tuple[str, ...]


def chain_verdict(results: tuple[StackResult, ...] | None = None) -> ChainVerdict:
    """Worst-case verdict over the whole capture chain.

    Worst case, not RSS: a statistical stack is an argument about a population,
    and P0-A is one article.  RSS is reported so the gap between the two is
    visible, never so a failing worst case can be waived by it.
    """

    results = evaluate_all() if results is None else results
    critical = tuple(
        result.name
        for result in results
        if result.critical and not result.passes_worst_case
    )
    advisory = tuple(
        result.name
        for result in results
        if not result.critical and not result.passes_worst_case
    )
    return ChainVerdict(
        passed=not critical and not advisory,
        critical_failures=critical,
        advisory_failures=advisory,
    )


def stack_by_name(name: str) -> Stack:
    for stack in STACKS:
        if stack.name == name:
            return stack
    raise KeyError(f"unknown stack: {name}")


@dataclass(frozen=True)
class OpenFinding:
    """A stack that does not close, recorded rather than tuned away."""

    stack: str
    summary: str
    driver: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedFinding:
    """A stack that used to fail, kept so the reason for a revision survives.

    Deleting these when the numbers changed would leave the new geometry
    looking arbitrary.  They are the argument for why Rev-B exists.
    """

    stack: str
    revision: str
    was: str
    resolution: str


#: Rev-A failures, resolved by the Rev-B geometry.  Kept as the record of why
#: four dimensions moved at once.
RESOLVED_FINDINGS: tuple[ResolvedFinding, ...] = (
    ResolvedFinding(
        stack="keeper_slot_mast_clearance",
        revision="Rev-B",
        was="A 4.2 mm slot on a Ø3 mast left 0.6 mm of clearance per side at "
        "nominal, which the printed tolerance and the assumed seated lateral "
        "offset consumed entirely: worst case was an interference fit, so the "
        "keeper could bind on the mast instead of closing.",
        resolution="Slot widened to 5.2 mm, giving +0.475 mm at worst case "
        "against a 0.10 mm minimum. The widening costs retention ledge, which "
        "is why the seat diameter moved in the same revision.",
    ),
    ResolvedFinding(
        stack="keeper_head_overlap",
        revision="Rev-B",
        was="The retention ledge was set by the head's Ø6 lower cylinder "
        "against the 4.2 mm slot — 0.9 mm per side, 0.8 mm after the "
        "head-to-mast float. Worst case was line-to-line: the ledge "
        "disappeared and the dock would drop a captured aircraft.",
        resolution="Seat grown to Ø9 while the slot went to 5.2 mm, giving "
        "+0.975 mm at worst case against a 0.50 mm minimum. Seat and slot are "
        "coupled and were sized together rather than one at a time.",
    ),
    ResolvedFinding(
        stack="keeper_release_clearance",
        revision="Rev-B",
        was="Negative at nominal, not merely at worst case. The tines reached "
        "8.0 mm past the dock axis, so clearing the Ø12 belt needed 13.62 mm "
        "of stroke against the 11.0 mm declared in CAD — a number no generated "
        "geometry consumed, which is how the two drifted apart. The keeper "
        "uncovered the mast but not the head, so a captured aircraft could not "
        "be released, and emergency release is a P0-A gate criterion.",
        resolution="Tines shortened to 5.0 mm and stroke lengthened to "
        "13.0 mm: +1.150 mm at worst case, and 2.59 mm of margin on the exact "
        "fork geometry. CAD now derives the requirement from the tine reach "
        "and head diameter (DockRevision.exact_release_travel_mm) so the "
        "commanded stroke cannot silently disagree with it again.",
    ),
)

#: Empty: every capture-chain stack closes at worst case on the current
#: revision.  :func:`validate_stacks` errors if a stack fails without a record
#: here, and equally if a record survives its own fix.
OPEN_FINDINGS: tuple[OpenFinding, ...] = ()


def validate_stacks(
    stacks: tuple[Stack, ...] = STACKS,
    findings: tuple[OpenFinding, ...] = OPEN_FINDINGS,
) -> tuple[str, ...]:
    """Structural errors in the stack definitions and the finding record.

    The arguments exist so a test can hand this check a deliberately broken
    chain; CI calls it on the real one.
    """

    errors: list[str] = []

    names = [stack.name for stack in stacks]
    if len(names) != len(set(names)):
        errors.append("stack names must be unique")

    known = {dimension.name: dimension for dimension in DIMENSIONS}
    if len(known) != len(DIMENSIONS):
        errors.append("dimension names must be unique")

    for stack in stacks:
        for dimension, _ in stack.contributors:
            registered = known.get(dimension.name)
            if registered is None:
                errors.append(
                    f"{stack.name} uses unregistered dimension {dimension.name}"
                )
            elif registered != dimension:
                errors.append(
                    f"{stack.name} redefines dimension {dimension.name}; a "
                    "dimension must mean the same thing in every stack"
                )

    for feature in AS_BUILT_FEATURES:
        if feature.dimension not in known:
            errors.append(
                f"as-built feature {feature.feature} maps to unknown dimension "
                f"{feature.dimension}"
            )

    for name in sorted(DERIVED_DIMENSIONS - set(known)):
        errors.append(f"derived dimension {name} is not a registered dimension")

    # Every contributor a stack actually uses must be reachable from a caliper,
    # directly or through a derived fit.  An unmeasurable contributor cannot be
    # replaced by as-built data, so its assumption would never expire.
    measurable = {feature.dimension for feature in AS_BUILT_FEATURES}
    measurable |= DERIVED_DIMENSIONS
    used = {
        dimension.name for stack in stacks for dimension, _ in stack.contributors
    }
    for name in sorted(used - measurable):
        errors.append(f"stack dimension {name} has no as-built measurement route")

    if not any(stack.critical for stack in stacks):
        errors.append("the capture chain must contain at least one critical stack")

    failing = {
        result.name
        for result in evaluate_all(stacks)
        if not result.passes_worst_case
    }
    recorded = {finding.stack for finding in findings}
    for name in sorted(recorded - failing):
        errors.append(f"{name} is recorded as an open finding but now passes")
    for name in sorted(failing - recorded):
        errors.append(f"{name} fails worst case with no open finding recorded")
    for finding in findings:
        if finding.stack not in names:
            errors.append(f"open finding refers to unknown stack {finding.stack}")

    return tuple(errors)


@dataclass(frozen=True)
class AsBuiltFeature:
    """One row type in ``hardware/dock/as-built-template.csv``.

    Operators measure what a caliper can reach — diameters and lengths — while
    the stack is written in radial terms.  ``scale`` is that conversion, kept in
    code so the CSV never asks anyone to halve a number by hand.
    """

    feature: str
    part: str
    nominal_mm: float
    dimension: str
    scale: float
    instrument: str


AS_BUILT_FEATURES: tuple[AsBuiltFeature, ...] = (
    AsBuiltFeature(
        feature="funnel_throat_diameter",
        part="funnel",
        nominal_mm=16.0,
        dimension="funnel_throat_radius",
        scale=0.5,
        instrument="digital caliper, two orthogonal readings",
    ),
    AsBuiltFeature(
        feature="probe_head_max_diameter",
        part="probe_head",
        nominal_mm=12.0,
        dimension="probe_head_max_radius",
        scale=0.5,
        instrument="digital caliper at the Ø12 belt",
    ),
    AsBuiltFeature(
        feature="probe_head_seat_diameter",
        part="probe_head",
        nominal_mm=9.0,
        dimension="probe_head_seat_radius",
        scale=0.5,
        instrument="digital caliper on the lower cylinder",
    ),
    AsBuiltFeature(
        feature="probe_head_bore_diameter",
        part="probe_head",
        nominal_mm=3.2,
        dimension="probe_head_bore_radius",
        scale=0.5,
        instrument="pin gauge or caliper jaws, post-ream",
    ),
    AsBuiltFeature(
        feature="probe_mast_diameter",
        part="mast",
        nominal_mm=3.0,
        dimension="probe_mast_radius",
        scale=0.5,
        instrument="micrometer, three stations along the mast",
    ),
    AsBuiltFeature(
        feature="keeper_slot_width",
        part="keeper",
        nominal_mm=5.2,
        dimension="keeper_slot_half_width",
        scale=0.5,
        instrument="pin gauge at the slot mouth and at the round end",
    ),
    AsBuiltFeature(
        feature="keeper_tine_reach",
        part="keeper",
        nominal_mm=5.0,
        dimension="keeper_tine_reach",
        scale=1.0,
        instrument="digital caliper from the slot round-end centre to the tine tip",
    ),
    AsBuiltFeature(
        feature="keeper_open_travel",
        part="keeper",
        nominal_mm=13.0,
        dimension="keeper_open_travel",
        scale=1.0,
        instrument="dial indicator between the closed and open stops",
    ),
    AsBuiltFeature(
        feature="seated_probe_lateral_offset",
        part="assembly",
        nominal_mm=0.0,
        dimension="seated_probe_lateral_offset",
        scale=1.0,
        instrument="dial indicator on the seated mast, worst of two orthogonal axes",
    ),
)

AS_BUILT_COLUMNS: tuple[str, ...] = (
    "run_id",
    "article_rev",
    "article_serial",
    "git_commit",
    "part",
    "feature",
    "nominal_mm",
    "measured_mm",
    "instrument",
    "operator",
    "date",
    "notes",
)


def measured_dimensions(measurements: Mapping[str, float]) -> dict[str, float]:
    """Convert as-built feature measurements into stack dimension values.

    Raises on any feature name that is not in the template, because a
    mis-keyed row is missing evidence, not a default.
    """

    catalogue = {feature.feature: feature for feature in AS_BUILT_FEATURES}
    unknown = sorted(set(measurements) - set(catalogue))
    if unknown:
        raise KeyError(f"unknown as-built features: {', '.join(unknown)}")

    values = {
        catalogue[name].dimension: value * catalogue[name].scale
        for name, value in measurements.items()
    }
    if "probe_head_bore_radius" in values and "probe_mast_radius" in values:
        values["probe_head_to_mast_float"] = max(
            0.0, values["probe_head_bore_radius"] - values["probe_mast_radius"]
        )
    return values


def _as_built_dimension(
    dimension: Dimension,
    measured_mm: Mapping[str, float],
    uncertainty_mm: float,
) -> Dimension:
    if dimension.name not in measured_mm:
        return dimension

    band = uncertainty_mm * (2.0 if dimension.name in DERIVED_DIMENSIONS else 1.0)
    return Dimension(
        dimension.name,
        measured_mm[dimension.name],
        band,
        band,
        "measured as-built",
        f"as-built record for {dimension.name}",
    )


def as_built(
    stack: Stack,
    measured_mm: Mapping[str, float],
    uncertainty_mm: float = CALIPER_UNCERTAINTY_MM,
) -> Stack:
    """Rebuild a stack from one article's measured dimensions.

    A measured dimension keeps only its measurement uncertainty, doubled for
    the derived fits in :data:`DERIVED_DIMENSIONS` because those are the
    difference of two readings.  Any dimension the article has not been
    measured for keeps its predicted tolerance, which is wider, so an
    unmeasured feature can never turn a failing stack into a passing one.
    """

    unknown = sorted(set(measured_mm) - {dimension.name for dimension in DIMENSIONS})
    if unknown:
        raise KeyError(f"unknown as-built dimensions: {', '.join(unknown)}")

    contributors = tuple(
        (_as_built_dimension(dimension, measured_mm, uncertainty_mm), sign)
        for dimension, sign in stack.contributors
    )
    return Stack(
        name=f"{stack.name}_as_built",
        description=f"As-built article check of {stack.name}.",
        contributors=contributors,
        minimum_mm=stack.minimum_mm,
        minimum_rationale=stack.minimum_rationale,
        critical=stack.critical,
    )


def _rounded(record: dict[str, object]) -> dict[str, object]:
    return {
        key: round(value, 4) if isinstance(value, float) else value
        for key, value in record.items()
    }


def _stack_snapshot(stack: Stack, result: StackResult) -> dict[str, object]:
    driver, driver_tolerance = dominant_contributor(stack)
    return {
        "name": stack.name,
        "description": stack.description,
        "critical": stack.critical,
        "minimum_mm": stack.minimum_mm,
        "minimum_rationale": stack.minimum_rationale,
        "contributors": [
            _rounded(
                {
                    **asdict(dimension),
                    "sign": sign,
                    "closing_tolerance_mm": dimension.closing_tolerance_mm(sign),
                }
            )
            for dimension, sign in stack.contributors
        ],
        "dominant_contributor": {
            "name": driver,
            "closing_tolerance_mm": round(driver_tolerance, 4),
        },
        "result": _rounded(asdict(result)),
    }


def snapshot() -> dict[str, object]:
    errors = validate_stacks()
    results = evaluate_all()
    return {
        "article": "CARRIER-P0 P0-A Rev-A",
        "units": "mm",
        "valid": not errors,
        "errors": list(errors),
        "verdict": asdict(chain_verdict(results)),
        "exact_release_travel_mm": round(EXACT_RELEASE_TRAVEL_MM, 4),
        "assumptions": [asdict(assumption) for assumption in ASSUMPTIONS],
        "stacks": [
            _stack_snapshot(stack, result)
            for stack, result in zip(STACKS, results)
        ],
        "open_findings": [asdict(finding) for finding in OPEN_FINDINGS],
        "as_built_features": [asdict(feature) for feature in AS_BUILT_FEATURES],
        "as_built_columns": list(AS_BUILT_COLUMNS),
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    # Two different failures, both of which must be non-zero.
    #
    # A registry error — an unrecorded stack failure, or a finding that
    # outlived its fix — means the record and the arithmetic disagree, and
    # nothing downstream can be trusted.
    #
    # A failing *critical* stack means the built article could drop or trap
    # an aircraft.  Recording a finding for it makes the failure honest; it
    # does not make it mergeable, and returning 0 here would have let the
    # exact Rev-A release defect sit green in CI for as long as someone kept
    # the paperwork tidy.  Advisory failures stay green with a finding
    # recorded, because they prevent a capture rather than endanger one.
    verdict = chain_verdict()
    if not report["valid"] or verdict.critical_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
