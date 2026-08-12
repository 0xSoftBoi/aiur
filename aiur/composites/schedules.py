"""Laminate schedules for the CARRIER-P0 composite structures.

A laminate schedule is the contract between design and the shop floor: which
material, how many plies, at what angles, in what order, to what thickness,
against which load cases.  Everything else in this package exists to make one
of these schedules defensible.

The composite content of the P0 recovery dock and its deployable capture
ring, after the trade described below:

``CS-100``  capture throat cup — the small, stiff, high-precision cone at the
            funnel throat that does the final centring;
``CS-200``  deployable capture-ring boom — a slit-tube tape spring that stows
            rolled against the keel and springs the funnel rim out;
``CS-300``  keel rail web — the beam the dock carriage runs along;
``CS-400``  keeper tine — the retention finger that closes over the probe.

Three results came out of writing and running this file.  All three changed
the design, so they are recorded here rather than in a slide.

**These parts are not strength-driven by flight loads.**  A 48 g aircraft
closing at 0.20 m/s and arrested over 5 mm develops about 0.2 N.  Every
capture load case is orders of magnitude below what the thinnest
manufacturable laminate carries.  What sizes them is minimum gauge, handling
load, stiffness, residual stress, and — for the deployable — stowed strain.

**The funnel is not a laminate.**  Sized honestly, a monolithic skin able to
carry the handling load across the boom pitch weighs 789 g/m^2, which is
54 g over the funnel's area — a third of the entire dock mass allocation for
a part that only has to guide an aircraft.  The funnel therefore became a
tensioned membrane between the deployable booms, and the laminate content
retreated to the throat cup, where the spans are short and the precision
requirement is real.  ``docs/composites/laminate-design.md`` carries the
numbers.  Deciding a part should not be composite is part of owning the
composite structures.

**Cooldown is a sizing load case, and it picked the material.**  A 180 degC
cure leaves a 155 K cooldown, and cure shrinkage after gelation adds to it.
The first keel rail — high-modulus tape at 0/90 — was predicted to
microcrack on the tool at a strength ratio of 0.56, before it ever saw a
load.  The fix was not a thicker part; it was intermediate-modulus tape with
fabric carrying the transverse direction, which closes at 1.41 and costs
20 g.  The lighter high-modulus rail is available if the program ever
qualifies a second, lower-temperature resin system, and that is recorded as
a deferred opportunity rather than quietly dropped.

Design rules are enforced, not suggested.  A schedule that breaks one must
carry a written :class:`Waiver`; :func:`validate_schedules` fails when a rule
is broken without one *and* when a waiver outlives the rule break it was
written for — the same two-way check the capture-chain tolerance stack uses,
so paperwork cannot drift away from the design in either direction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .clt import Laminate, Ply, minimum_stow_radius_mm
from .materials import Basis, allowable_grade, material as lookup_material

#: Room temperature the parts are used and measured at, degC.
ROOM_TEMPERATURE_C = 25.0

#: Fraction of total cure shrinkage occurring after gelation, and therefore
#: building residual stress.  Engineering target; DOE-3 in the experiment
#: plan replaces it with a measurement.
POST_GEL_SHRINKAGE_FRACTION = 0.5

#: Inadvertent-contact handling load: a hand steadying a part, or a part set
#: down on an edge.  15 N over a 25 mm footprint is an explicitly labeled
#: engineering target, and it is deliberately *not* a step or grab load.
#:
#: The first pass at this file carried 50 N, and no ultralight skin survived
#: it: a 0.33 mm laminate on a 100 mm unsupported span reaches 2 % surface
#: strain, roughly twice any allowable here, and thickening the skin to fix
#: that costs more mass than the whole dock structural allocation.  That is
#: the right answer to the wrong question.  Parts this light are not handled
#: bare — they are handled in a fixture — so the load case became a
#: defensible inadvertent-contact load, the *support pitch* became a design
#: output, and the handling fixture became a requirement in the layup process
#: spec instead of an assumption hidden inside a load case.
HANDLING_FORCE_N = 15.0
HANDLING_FOOTPRINT_MM = 25.0

#: Limit load factor on a retained aircraft.  Engineering target: the carrier
#: is a slow buoyant vehicle operating indoors, so the driver is a handling
#: drop of the dock assembly rather than a flight manoeuvre.
RETENTION_LIMIT_LOAD_FACTOR = 6.0

#: Longest run of same-orientation unidirectional plies allowed.
MAX_CONTIGUOUS_PLIES = 4
#: Minimum thickness share for each of the 0 / 90 / 45 families.
TEN_PERCENT_RULE = 0.10
#: Knockdown applied to ultimate strain for a stowed deployable.
STOWAGE_KNOCKDOWN = 0.5

RULE_NAMES: tuple[str, ...] = (
    "symmetric",
    "balanced",
    "ten_percent_rule",
    "max_contiguous_plies",
    "surface_ply_off_axis",
)


# --------------------------------------------------------------------------
# Load definition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadCase:
    """One sizing condition applied to a laminate."""

    name: str
    description: str
    #: Force and moment resultants, N/mm and N.
    n_per_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    m_per_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: Signed temperature change from the stress-free (cure) state.
    delta_t_k: float = 0.0
    shrinkage_fraction: float = 0.0
    #: Required strength ratio: 1.0 is "does not fail", above that is the
    #: factor of safety this program holds for the case.
    min_strength_ratio: float = 1.5
    #: A critical case is one whose failure endangers a captured aircraft.
    #: Critical failures fail CI; advisory failures need a recorded finding.
    critical: bool = False
    #: Transverse boundary condition; see ``Laminate.response``.
    edge: str = "free"
    basis: str = "engineering target"


def handling_moment_n(span_mm: float) -> float:
    """Bending moment resultant from the handling load case, N.

    A centre load ``P`` on a simply supported span ``L``, spread over a
    footprint ``w``, gives a peak moment ``P L / 4`` carried across the
    footprint: ``M = P L / (4 w)`` per unit width.  Simply supported is the
    conservative end condition, and the flat-plate idealisation ignores part
    curvature, which is conservative again.
    """

    if span_mm <= 0:
        raise ValueError("span must be positive")
    return HANDLING_FORCE_N * span_mm / (4.0 * HANDLING_FOOTPRINT_MM)


def handling_case(span_mm: float, *, edge: str = "free") -> LoadCase:
    """Handling load case for a part supported at ``span_mm`` pitch."""

    return LoadCase(
        name="LC-HANDLE",
        description=(
            f"{HANDLING_FORCE_N:g} N inadvertent-contact load over a "
            f"{HANDLING_FOOTPRINT_MM:g} mm footprint on a {span_mm:g} mm "
            "unsupported span, simply supported"
        ),
        m_per_mm=(handling_moment_n(span_mm), 0.0, 0.0),
        min_strength_ratio=1.5,
        edge=edge,
        basis="engineering target; governs every thin part in this program",
    )


def cooldown_case(cure_temperature_c: float) -> LoadCase:
    """The residual-stress case: cure temperature down to room temperature.

    Always evaluated with free edges, because a part coming off its tool is
    unrestrained — that is the whole point of the check.
    """

    return LoadCase(
        name="LC-COOL",
        description=(
            f"cooldown from {cure_temperature_c:g} degC cure to room temperature "
            "with post-gel cure shrinkage; no external load"
        ),
        delta_t_k=ROOM_TEMPERATURE_C - cure_temperature_c,
        shrinkage_fraction=POST_GEL_SHRINKAGE_FRACTION,
        # Residual stress alone must not crack a ply, but it is a
        # self-equilibrating state that redistributes once a crack forms, so
        # it is held to 1.0 rather than to a flight factor of safety.  A
        # first-ply failure here is matrix microcracking, not part failure.
        min_strength_ratio=1.0,
        edge="free",
        basis="analysis; ply CTE and shrinkage are handbook-representative",
    )


def _aircraft_mass_kg() -> float:
    """Aircraft mass carried into the dock, kg.

    Read from the P0 mass budget rather than restated, so a change to the
    aircraft cannot leave a stale number in the structures model.
    """

    from ..p0 import baseline_p0_budget

    wanted = {
        "Crazyflie 2.1 Brushless + guards",
        "Lighthouse positioning deck",
        "drone-side capture probe allocation",
    }
    items = [item for item in baseline_p0_budget() if item.name in wanted]
    if len(items) != len(wanted):  # pragma: no cover - defensive
        raise ValueError("P0 mass budget no longer names the aircraft items")
    return sum(item.mass_kg_each for item in items)


def retention_force_n() -> float:
    return _aircraft_mass_kg() * 9.81 * RETENTION_LIMIT_LOAD_FACTOR


def budget_line_kg(name: str) -> float:
    """Look up one line of the P0 mass budget, kg."""

    from ..p0 import baseline_p0_budget

    for item in baseline_p0_budget():
        if item.name == name:
            return item.total_mass_kg
    raise KeyError(f"P0 mass budget has no line {name!r}")


#: The two P0 budget lines the composite structures are drawn against.
DOCK_BUDGET_LINE = "active recovery dock allocation"
MOUNTING_BUDGET_LINE = "wiring + mounting reserve"


# --------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Waiver:
    """A deliberate, recorded break of a laminate design rule."""

    rule: str
    rationale: str


@dataclass(frozen=True)
class Check:
    """One evaluated criterion on a schedule."""

    name: str
    actual: float | bool
    limit: float | bool
    comparison: str
    passed: bool
    critical: bool = False
    waived: bool = False
    note: str = ""


@dataclass(frozen=True)
class LaminateSchedule:
    """A complete, checkable laminate definition for one part."""

    part_id: str
    name: str
    description: str
    #: Plies **top surface first**, where "top" is the face away from the
    #: tool.  This is the order a drawing lists a stack and the order the CLT
    #: model reverses internally so that ply one sits at the most negative z.
    #:
    #: It is deliberately **not** the order a laminator works in.  A laminator
    #: starts against the tool, which is the *last* entry here, so lay-down
    #: order is this tuple reversed — which is exactly ``laminate().plies``.
    #: An earlier version of this comment claimed the two were the same
    #: order.  They are not, and on any unsymmetric detail that error builds
    #: the part inside out, so the ply book takes its sequence from
    #: ``laminate().plies`` and prints which surface the tool controls.
    plies_top_down: tuple[Ply, ...]
    #: Wetted area of one shipset of this part, m^2, and the mass allocated
    #: to it from a named P0 budget line, g.  The areal-mass limit is the
    #: quotient — so a mass limit here can never drift away from the vehicle
    #: budget it came from.
    area_m2: float
    mass_allocation_g: float
    budget_line: str
    quantity: int = 1
    min_ex_mpa: float = 0.0
    min_bending_stiffness_n_mm: float = 0.0
    #: Designed support pitch for the handling case, mm.
    support_pitch_mm: float | None = None
    #: Stowed rolling radius for deployables, mm.
    stow_radius_mm: float | None = None
    #: Transverse boundary condition for the part's mechanical load cases.
    edge: str = "free"
    edge_rationale: str = ""
    load_cases: tuple[LoadCase, ...] = ()
    waivers: tuple[Waiver, ...] = ()
    #: Which tool face controls the moulded surface.  Spring-in compensation
    #: and surface tolerance both attach to it.
    tool_side: str = "outer mould line"
    notes: str = ""

    def laminate(self) -> Laminate:
        return Laminate.from_top_down(self.plies_top_down, name=self.part_id)

    @property
    def max_areal_mass_g_m2(self) -> float:
        return self.mass_allocation_g / (self.area_m2 * self.quantity)

    @property
    def waived_rules(self) -> frozenset[str]:
        return frozenset(waiver.rule for waiver in self.waivers)

    def part_mass_g(self) -> float:
        return self.laminate().areal_mass_g_m2 * self.area_m2 * self.quantity


CS_100_THROAT_CUP = LaminateSchedule(
    part_id="CS-100",
    name="capture throat cup",
    description=(
        "Thin high-precision cone at the funnel throat. It is the last "
        "geometry an arriving aircraft touches before the keeper closes, so "
        "its moulded surface feeds the capture-chain tolerance stack."
    ),
    plies_top_down=(
        # Outer (tool) surface: glass, for abrasion against an arriving
        # airframe and to keep carbon off the antenna ground plane.
        Ply("PW-G-1080", 45.0),
        Ply("PW-C-80", 45.0),
        # Equal carbon thickness at 0 and 45 is not a stiffness choice; it
        # is what makes the laminate in-plane isotropic, which is what a
        # conical part needs.  See the note below.
        Ply("PW-C-80", 0.0),
        Ply("PW-C-80", 0.0),
        Ply("PW-C-80", 45.0),
        Ply("PW-G-1080", 45.0),
    ),
    #: Area is the developed area of the cone in
    #: ``aiur.composites.flatpattern.PART_SHAPES``, not an estimate;
    #: ``validate_geometry`` fails if the two drift apart.
    area_m2=0.011663,
    mass_allocation_g=8.0,
    budget_line=DOCK_BUDGET_LINE,
    min_ex_mpa=25_000.0,
    min_bending_stiffness_n_mm=60.0,
    support_pitch_mm=25.0,
    edge="cylindrical",
    edge_rationale=(
        "A cone gore is long between its bonded flange and the throat ring, "
        "so the surrounding skin prevents the anticlastic curvature a free "
        "strip would develop. Evaluated free instead, the same laminate "
        "loses half its apparent bending capacity."
    ),
    load_cases=(
        handling_case(25.0, edge="cylindrical"),
        cooldown_case(180.0),
    ),
    tool_side="outer mould line (female tool, aircraft-contact surface)",
    notes=(
        "Glass surface plies are structural bookkeeping as well as abrasion: "
        "they put the highest-strain, lowest-modulus material where bending "
        "strain and impact damage are highest. "
        "The carbon plies are split evenly between 0 and 45 degrees to make "
        "the laminate in-plane isotropic, because this is the only conical "
        "part in the set and a cone does not let a ply hold its angle: the "
        "development spans 255 degrees, and a straight fibre's angle to the "
        "local meridian drifts one degree per degree of that sector. The "
        "five-ply predecessor, with one carbon ply at 0 against two at 45, "
        "varied by 47 % in Ex around its own circumference. This stack "
        "varies by 7 %, and that residue is entirely the two glass plies, "
        "which sit at 45 with nothing at 0 to balance them. See "
        "aiur.composites.flatpattern."
    ),
)

CS_200_DEPLOYABLE_BOOM = LaminateSchedule(
    part_id="CS-200",
    name="deployable capture-ring boom",
    description=(
        "Slit-tube tape spring that stows rolled flat against the keel and "
        "deploys the capture ring, carrying the funnel membrane. Sized by "
        "stowed strain first and deployed stiffness second."
    ),
    plies_top_down=(
        Ply("PW-C-80", 45.0),
        Ply("PW-C-80", 45.0),
    ),
    area_m2=0.0088,
    quantity=12,
    mass_allocation_g=30.0,
    budget_line=DOCK_BUDGET_LINE,
    min_ex_mpa=15_000.0,
    stow_radius_mm=16.0,
    edge="free",
    edge_rationale="A 35 mm wide tape spring is a narrow strip with free edges.",
    load_cases=(cooldown_case(180.0),),
    waivers=(
        Waiver(
            rule="ten_percent_rule",
            rationale=(
                "A tape spring is deliberately shear-dominated: +-45 fabric is "
                "what lets the section flatten elastically and snap back. "
                "Adding a 0/90 ply to satisfy the 10 % rule raises the "
                "longitudinal stiffness that resists flattening and pushes "
                "stowed strain past allowable. The 0 and 90 directions carry "
                "no required load in this part — deployed bending is reacted "
                "by the section shape, not by fibre in one direction."
            ),
        ),
    ),
    tool_side="inner mould line (male mandrel; controls the stowed radius fit)",
    notes=(
        "Thin ply is the enabling choice, not a preference: at 0.20 mm ply "
        "thickness this laminate cannot reach the stow radius without "
        "exceeding its strain allowable."
    ),
)

CS_300_KEEL_RAIL = LaminateSchedule(
    part_id="CS-300",
    name="keel rail web",
    description=(
        "Unidirectional-dominated web carrying the dock carriage along the "
        "keel. The one part in the set where axial stiffness, not gauge, "
        "sets the ply count."
    ),
    plies_top_down=(
        Ply("PW-C-193", 45.0),
        Ply("UD-C-IM", 0.0),
        Ply("PW-C-193", 0.0),
        Ply("UD-C-IM", 0.0),
        Ply("UD-C-IM", 0.0),
        Ply("PW-C-193", 0.0),
        Ply("UD-C-IM", 0.0),
        Ply("PW-C-193", 45.0),
    ),
    area_m2=0.020,
    mass_allocation_g=45.0,
    budget_line=MOUNTING_BUDGET_LINE,
    min_ex_mpa=80_000.0,
    min_bending_stiffness_n_mm=3_000.0,
    support_pitch_mm=120.0,
    edge="free",
    edge_rationale=(
        "A 40 mm wide web between carriage supports is narrow relative to "
        "its span; free edges are both the correct and the conservative model."
    ),
    load_cases=(
        handling_case(120.0),
        LoadCase(
            name="LC-RAIL",
            description=(
                "carriage reaction from a retained aircraft at the limit load "
                "factor, reacted as a running load over a 40 mm rail width"
            ),
            n_per_mm=(retention_force_n() / 40.0, 0.0, 0.0),
            min_strength_ratio=1.5,
            basis="derived from the P0 mass budget and a target load factor",
        ),
        cooldown_case(180.0),
    ),
    tool_side="inner mould line (flat caul on the bagged side)",
    notes=(
        "Fabric plies on both faces and at the mid-plane are there for "
        "handling, drilled-hole bearing and transverse residual stress, not "
        "for stiffness: bare unidirectional tape splits along the fibre at a "
        "fastener and frays at a trimmed edge. Intermediate-modulus tape is "
        "chosen over high-modulus because the high-modulus stack is predicted "
        "to microcrack on cooldown; see the module docstring."
    ),
)

CS_400_KEEPER_TINE = LaminateSchedule(
    part_id="CS-400",
    name="keeper tine",
    description=(
        "The retention finger that closes over the aircraft's capture probe. "
        "Small, thick for its size, and the only part in the set whose "
        "failure drops a captured aircraft."
    ),
    plies_top_down=(
        Ply("PW-C-193", 45.0),
        Ply("PW-C-193", 0.0),
        Ply("PW-C-193", 0.0),
        Ply("PW-C-193", 45.0),
        Ply("PW-C-193", 45.0),
        Ply("PW-C-193", 0.0),
        Ply("PW-C-193", 0.0),
        Ply("PW-C-193", 45.0),
    ),
    area_m2=0.0012,
    quantity=2,
    mass_allocation_g=6.5,
    budget_line=DOCK_BUDGET_LINE,
    min_ex_mpa=40_000.0,
    min_bending_stiffness_n_mm=8_000.0,
    support_pitch_mm=25.0,
    edge="free",
    edge_rationale="A 12 mm wide cantilevered tine is a narrow strip.",
    load_cases=(
        LoadCase(
            name="LC-RETAIN",
            description=(
                "retention load from the aircraft at the limit load factor, "
                "applied as a root cantilever moment over a 12 mm tine width"
            ),
            m_per_mm=(retention_force_n() * 8.0 / 12.0, 0.0, 0.0),
            # This is the retention path: its failure drops an aircraft, so
            # it carries a higher factor than general structure, and a
            # failure here is not waivable.
            min_strength_ratio=2.0,
            critical=True,
            basis="derived from the P0 mass budget and a target load factor",
        ),
        handling_case(25.0),
        cooldown_case(180.0),
    ),
    tool_side="matched tool (both faces controlled)",
    notes=(
        "Critical retention path. Its gauge is set by the retention-ledge "
        "geometry the capture-chain tolerance stack requires (see "
        "aiur.tolerance, KEEPER_HEAD_OVERLAP), not by the retention load — a "
        "strength ratio of 100-plus is a statement about how small the load "
        "is, not about how good the design is. Converting this part from a "
        "printed article to a laminate does not relieve the stack; it moves "
        "the same ledge dimension onto a moulded tolerance, which is why the "
        "matched tool controls both faces. This schedule is the one that "
        "must be backed by measured allowables before flight; the requirement "
        "matrix records that closure as open."
    ),
)

SCHEDULES: tuple[LaminateSchedule, ...] = (
    CS_100_THROAT_CUP,
    CS_200_DEPLOYABLE_BOOM,
    CS_300_KEEL_RAIL,
    CS_400_KEEPER_TINE,
)


def schedule(part_id: str) -> LaminateSchedule:
    for item in SCHEDULES:
        if item.part_id == part_id:
            return item
    raise KeyError(f"unknown part {part_id!r}; known: {[s.part_id for s in SCHEDULES]}")


# --------------------------------------------------------------------------
# Findings: advisory check failures that the program has accepted for now
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenFinding:
    """A known, accepted failure of a non-critical check."""

    part_id: str
    check: str
    exposure: str
    disposition: str


#: Populated when an advisory check fails and the program has decided to
#: carry it.  Empty is the healthy state; ``validate_schedules`` requires
#: this list and the evaluated checks to agree in both directions.
OPEN_FINDINGS: tuple[OpenFinding, ...] = ()


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def max_unsupported_span_mm(
    laminate: Laminate,
    *,
    factor_of_safety: float = 1.5,
    edge: str = "free",
    limit_mm: float = 2000.0,
) -> float:
    """Largest span carrying the handling load with the required factor.

    This is the design output the handling case actually produces: not a
    pass/fail on a skin, but the pitch at which that skin has to be
    supported — by a rib, a bond line, or a handling fixture.  Bisected
    because the strength ratio is monotone in span but not analytic once
    several plies and two failure criteria are in play.
    """

    def ratio_at(span: float) -> float:
        return laminate.response(
            m_per_mm=(handling_moment_n(span), 0.0, 0.0), edge=edge
        ).first_ply_failure_ratio

    if ratio_at(limit_mm) >= factor_of_safety:
        return limit_mm
    low, high = 1e-3, limit_mm
    for _ in range(60):
        mid = 0.5 * (low + high)
        if ratio_at(mid) >= factor_of_safety:
            low = mid
        else:
            high = mid
    return low


def _rule_checks(item: LaminateSchedule) -> list[Check]:
    laminate = item.laminate()
    fractions = laminate.orientation_fractions()
    contiguous = laminate.max_contiguous_same_angle()
    # A surface ply at 45 degrees resists the surface-parallel splitting that
    # handling damage starts, and it is the ply an operator scuffs.
    surface_ok = all(
        abs((ply.angle_deg % 90.0) - 45.0) < 1e-6
        for ply in (item.plies_top_down[0], item.plies_top_down[-1])
    )
    # The 10 % rule applies to all three families, including the ones a stack
    # leaves empty — an empty family is exactly the case the rule exists to
    # catch, so it is checked against zero rather than skipped.
    families = {key: fractions[key] for key in ("0", "90", "45")}
    thinnest = min(families.values())

    raw = [
        Check("symmetric", laminate.is_symmetric(), True, "==", laminate.is_symmetric()),
        Check("balanced", laminate.is_balanced(), True, "==", laminate.is_balanced()),
        Check(
            "ten_percent_rule",
            round(thinnest, 4),
            TEN_PERCENT_RULE,
            ">=",
            thinnest >= TEN_PERCENT_RULE,
            note="thinnest of the 0 / 90 / 45 families",
        ),
        Check(
            "max_contiguous_plies",
            contiguous,
            MAX_CONTIGUOUS_PLIES,
            "<=",
            contiguous <= MAX_CONTIGUOUS_PLIES,
            note="longest run of same-orientation unidirectional plies",
        ),
        Check("surface_ply_off_axis", surface_ok, True, "==", surface_ok),
    ]
    return [
        Check(
            check.name,
            check.actual,
            check.limit,
            check.comparison,
            check.passed or check.name in item.waived_rules,
            waived=(not check.passed) and check.name in item.waived_rules,
            note=check.note,
        )
        for check in raw
    ]


def evaluate(item: LaminateSchedule) -> dict[str, object]:
    """Evaluate one schedule against its rules, limits, and load cases."""

    laminate = item.laminate()
    constants = laminate.engineering_constants()
    checks: list[Check] = list(_rule_checks(item))

    areal = laminate.areal_mass_g_m2
    checks.append(
        Check("areal_mass_g_m2", round(areal, 1), round(item.max_areal_mass_g_m2, 1),
              "<=", areal <= item.max_areal_mass_g_m2,
              note=f"from {item.mass_allocation_g:g} g allocated on '{item.budget_line}'")
    )
    if item.min_ex_mpa:
        checks.append(
            Check("ex_mpa", round(constants["ex_mpa"], 0), item.min_ex_mpa, ">=",
                  constants["ex_mpa"] >= item.min_ex_mpa)
        )
    if item.min_bending_stiffness_n_mm:
        d11 = laminate.d_matrix()[0][0]
        checks.append(
            Check("d11_n_mm", round(d11, 1), item.min_bending_stiffness_n_mm, ">=",
                  d11 >= item.min_bending_stiffness_n_mm)
        )

    span_capacity = None
    if item.support_pitch_mm is not None:
        span_capacity = max_unsupported_span_mm(laminate, edge=item.edge)
        checks.append(
            Check("support_pitch_mm", item.support_pitch_mm, round(span_capacity, 1),
                  "<=", item.support_pitch_mm <= span_capacity,
                  note="designed pitch must not exceed the handling-load span capacity")
        )

    stow: dict[str, object] | None = None
    if item.stow_radius_mm is not None:
        minimum = minimum_stow_radius_mm(laminate, knockdown=STOWAGE_KNOCKDOWN)
        strain = laminate.thickness_mm / (2.0 * item.stow_radius_mm)
        checks.append(
            Check("stow_radius_mm", item.stow_radius_mm, round(minimum, 2), ">=",
                  item.stow_radius_mm >= minimum,
                  note="required radius from strain allowable with stowage knockdown")
        )
        stow = {
            "stow_radius_mm": item.stow_radius_mm,
            "minimum_radius_mm": round(minimum, 3),
            "stowed_surface_strain": round(strain, 5),
            "knockdown_on_ultimate_strain": STOWAGE_KNOCKDOWN,
        }

    case_results = []
    for case in item.load_cases:
        response = laminate.response(
            n_per_mm=case.n_per_mm,
            m_per_mm=case.m_per_mm,
            delta_t_k=case.delta_t_k,
            shrinkage_fraction=case.shrinkage_fraction,
            edge=case.edge,
        )
        critical_ply = response.critical_ply
        ratio = response.first_ply_failure_ratio
        checks.append(
            Check(
                f"strength_ratio[{case.name}]",
                round(min(ratio, 1e4), 3),
                case.min_strength_ratio,
                ">=",
                ratio >= case.min_strength_ratio,
                critical=case.critical,
            )
        )
        case_results.append(
            {
                "name": case.name,
                "description": case.description,
                "basis": case.basis,
                "critical": case.critical,
                "edge": case.edge,
                "required_strength_ratio": case.min_strength_ratio,
                "first_ply_failure_ratio": round(min(ratio, 1e4), 3),
                "margin_of_safety": round(min(ratio, 1e4) / case.min_strength_ratio - 1.0, 3),
                # A case whose ratio is far above its requirement is not
                # sizing anything, and saying so keeps attention on the two
                # or three cases that actually drive the design.
                "sizing": ratio < 3.0 * case.min_strength_ratio,
                "max_tsai_wu_index": round(response.max_tsai_wu, 4),
                "max_strain_index": round(response.max_strain_index, 4),
                "critical_ply": {
                    "index": critical_ply.index,
                    "material": critical_ply.material,
                    "angle_deg": critical_ply.angle_deg,
                    "z_mm": round(critical_ply.z_mm, 4),
                    "stress_12_mpa": [round(value, 2) for value in critical_ply.stress_12_mpa],
                },
                "mid_plane_strain": [round(value, 6) for value in response.mid_strain],
                "curvature_per_mm": [round(value, 8) for value in response.curvature],
            }
        )

    materials_used = sorted({ply.material for ply in item.plies_top_down})
    weakest_basis = min(
        (lookup_material(name).basis for name in materials_used),
        key=lambda basis: list(Basis).index(basis),
    )

    return {
        "part_id": item.part_id,
        "name": item.name,
        "description": item.description,
        "stack": laminate.describe(),
        "plies_top_down": [
            {"material": ply.material, "angle_deg": ply.angle_deg,
             "thickness_mm": round(ply.thickness, 4)}
            for ply in item.plies_top_down
        ],
        "thickness_mm": round(laminate.thickness_mm, 4),
        "ply_count": laminate.ply_count,
        "quantity": item.quantity,
        "area_m2": item.area_m2,
        "areal_mass_g_m2": round(areal, 1),
        "part_mass_g": round(item.part_mass_g(), 2),
        "mass_allocation_g": item.mass_allocation_g,
        "budget_line": item.budget_line,
        "tool_side": item.tool_side,
        "edge": item.edge,
        "edge_rationale": item.edge_rationale,
        "materials": materials_used,
        "evidence_grade": allowable_grade(weakest_basis),
        "engineering_constants": {
            key: (round(value, 4) if isinstance(value, float) else value)
            for key, value in constants.items()
        },
        "laminate_cte_per_k": [f"{value:.3e}" for value in laminate.cte_per_k()],
        "orientation_fractions": {
            key: round(value, 4) for key, value in laminate.orientation_fractions().items()
        },
        "coupling_ratio": round(laminate.coupling_ratio(), 12),
        "max_unsupported_span_mm": (
            None if span_capacity is None else round(span_capacity, 1)
        ),
        "stowage": stow,
        "waivers": [asdict(waiver) for waiver in item.waivers],
        "checks": [asdict(check) for check in checks],
        "load_cases": case_results,
        "passed": all(check.passed for check in checks),
        "notes": item.notes,
    }


def evaluate_all() -> list[dict[str, object]]:
    return [evaluate(item) for item in SCHEDULES]


def failing_checks(results: list[dict[str, object]] | None = None) -> list[dict[str, object]]:
    """Checks that fail, with their criticality."""

    results = evaluate_all() if results is None else results
    failures: list[dict[str, object]] = []
    for result in results:
        for check in result["checks"]:  # type: ignore[index]
            if not check["passed"]:
                failures.append(
                    {
                        "part_id": result["part_id"],
                        "check": check["name"],
                        "actual": check["actual"],
                        "comparison": check["comparison"],
                        "limit": check["limit"],
                        "critical": check["critical"],
                    }
                )
    return failures


def mass_rollup() -> list[dict[str, object]]:
    """Composite mass drawn against each P0 budget line it charges to."""

    lines: dict[str, dict[str, object]] = {}
    for item in SCHEDULES:
        if item.budget_line not in lines:
            # An unknown budget line is a registry error, reported by
            # validate_schedules.  The rollup has to survive it rather than
            # raise, because a validator that cannot run on a broken registry
            # reports nothing at all — including the other things that are
            # wrong with it.
            try:
                budget_g: float | None = round(budget_line_kg(item.budget_line) * 1000.0, 1)
            except KeyError:
                budget_g = None
            lines[item.budget_line] = {
                "budget_line": item.budget_line,
                "budget_g": budget_g,
                "allocated_g": 0.0,
                "actual_g": 0.0,
                "parts": [],
            }
        entry = lines[item.budget_line]
        entry["allocated_g"] = round(
            float(entry["allocated_g"]) + item.mass_allocation_g, 2
        )
        entry["actual_g"] = round(float(entry["actual_g"]) + item.part_mass_g(), 2)
        entry["parts"].append(item.part_id)  # type: ignore[union-attr]
    for entry in lines.values():
        entry["within_allocation"] = entry["actual_g"] <= entry["allocated_g"]
        entry["allocation_within_budget"] = (
            entry["budget_g"] is not None and entry["allocated_g"] <= entry["budget_g"]
        )
    return list(lines.values())


def validate_schedules() -> list[str]:
    """CI check over the schedule set.  Empty list means consistent."""

    errors: list[str] = []
    seen: set[str] = set()
    for item in SCHEDULES:
        if item.part_id in seen:
            errors.append(f"{item.part_id}: duplicate part id")
        seen.add(item.part_id)
        if not item.load_cases:
            errors.append(f"{item.part_id}: no load cases; a schedule with none is a drawing")
        if item.edge not in ("free", "cylindrical"):
            errors.append(f"{item.part_id}: unknown edge condition {item.edge!r}")
        if item.edge == "cylindrical" and not item.edge_rationale:
            errors.append(
                f"{item.part_id}: a cylindrical edge condition roughly doubles the "
                "apparent bending capacity and must carry a written rationale"
            )
        for ply in item.plies_top_down:
            if ply.thickness_mm is not None:
                errors.append(
                    f"{item.part_id}: ply thickness override on a design schedule; "
                    "overrides belong to an as-built record"
                )
        try:
            budget_line_kg(item.budget_line)
        except KeyError:
            errors.append(f"{item.part_id}: charges to unknown budget line {item.budget_line!r}")

        laminate = item.laminate()
        # A symmetry break is never waivable: an unsymmetric laminate warps
        # off the tool, and no rationale makes a warped precision part good.
        if not laminate.is_symmetric():
            errors.append(f"{item.part_id}: laminate is not symmetric")
        if laminate.is_coupled():
            errors.append(f"{item.part_id}: laminate has bending-extension coupling")

        checks = {check.name: check for check in _rule_checks(item)}
        for rule in item.waived_rules:
            if rule not in RULE_NAMES:
                errors.append(f"{item.part_id}: waiver names unknown rule {rule!r}")
                continue
            if not checks[rule].waived:
                errors.append(
                    f"{item.part_id}: waiver for {rule!r} outlived the rule break it "
                    "was written for; delete the waiver"
                )
        for waiver in item.waivers:
            if len(waiver.rationale) < 40:
                errors.append(
                    f"{item.part_id}: waiver for {waiver.rule!r} needs a written rationale"
                )

    for entry in mass_rollup():
        if entry["budget_g"] is None:
            continue  # already reported as an unknown budget line above
        if not entry["allocation_within_budget"]:
            errors.append(
                f"{entry['budget_line']}: composite allocations total "
                f"{entry['allocated_g']} g against a {entry['budget_g']} g budget line"
            )

    # Findings and evaluated checks must agree in both directions, so a
    # failure cannot be silenced by deleting a finding and a stale finding
    # cannot outlive its own fix.
    recorded = {(finding.part_id, finding.check) for finding in OPEN_FINDINGS}
    observed = {
        (failure["part_id"], failure["check"])
        for failure in failing_checks()
        if not failure["critical"]
    }
    for missing in sorted(observed - recorded):
        errors.append(
            f"{missing[0]}: check {missing[1]!r} fails with no finding recorded"
        )
    for stale in sorted(recorded - observed):
        errors.append(
            f"{stale[0]}: finding recorded for {stale[1]!r} which now passes; delete it"
        )
    return errors


def snapshot() -> dict[str, object]:
    results = evaluate_all()
    errors = validate_schedules()
    failures = failing_checks(results)
    return {
        "article": "CARRIER-P0 composite structures",
        "units": {"stress": "MPa", "length": "mm", "areal_mass": "g/m^2", "mass": "g"},
        "valid": not errors,
        "errors": errors,
        "failing_checks": failures,
        "critical_failures": [failure for failure in failures if failure["critical"]],
        "open_findings": [asdict(finding) for finding in OPEN_FINDINGS],
        "shared_load_bases": {
            "aircraft_mass_kg": round(_aircraft_mass_kg(), 4),
            "retention_limit_load_factor": RETENTION_LIMIT_LOAD_FACTOR,
            "retention_force_n": round(retention_force_n(), 3),
            "handling_force_n": HANDLING_FORCE_N,
            "handling_footprint_mm": HANDLING_FOOTPRINT_MM,
            "post_gel_shrinkage_fraction": POST_GEL_SHRINKAGE_FRACTION,
        },
        "mass_rollup": mass_rollup(),
        "schedules": results,
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    # Two distinct failures, both fatal.  A registry error means the record
    # and the arithmetic disagree.  A failing *critical* check means the
    # built part could drop a captured aircraft; recording a finding for it
    # would make the failure honest without making it acceptable.
    if not report["valid"] or report["critical_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
