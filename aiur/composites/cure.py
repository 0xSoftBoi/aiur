"""Cure-cycle model and cure-cycle acceptance for CARRIER-P0 laminates.

A cure cycle is a recipe — ramp here, hold this long, pull vacuum then, apply
pressure at this point, cool no faster than that.  Written down, every cure
cycle looks equally plausible.  Run against the resin's kinetics, they stop
being equally plausible, and the four failures a cycle can hide become
visible and testable:

**Undercure.**  The part reaches the end of the recipe at a degree of cure
below what its service temperature needs.  It looks perfect, passes a visual
and an ultrasonic inspection, and fails hot/wet.

**Vitrification.**  A subtler undercure: the reaction does not merely run out
of time, it *stops*, because the partially cured resin's glass transition
climbs past the cure temperature and the molecules can no longer move.
Holding longer at that temperature buys nothing at all — the fix is a higher
hold, and no amount of patience substitutes.  The diffusion factor in the
kinetic model is what makes this predictable instead of surprising.

**Exotherm runaway.**  The reaction is strongly exothermic; in a thick part
or a thermally insulated tool the heat generated outruns the heat removed,
the part overshoots its own oven, and the overshoot accelerates the
reaction further.

**A missed pressure window.**  Resin viscosity falls as the part heats, then
climbs steeply as the reaction takes hold, and gelation ends flow entirely.
Apply consolidation pressure too early and the resin bleeds out, leaving a
resin-starved laminate; too late and the trapped volatiles and interply air
have nowhere to go, leaving voids.  The window between minimum viscosity and
gelation is often the only genuinely time-critical instruction on the
traveler, and it is the one most often written as "apply pressure at 100 C"
by someone who never computed where the window was.

The model integrates part temperature, degree of cure, glass transition and
viscosity together, because they are coupled: temperature drives the
reaction, the reaction releases heat and raises the glass transition, and
the glass transition shuts the reaction down.

Limits worth stating.  This is a **lumped** thermal model — one temperature
for the part — which is right for the 0.16-1.6 mm laminates in this program
and wrong for a thick part, where a through-thickness gradient is the whole
problem.  The kinetic constants are handbook-representative for the resin
*class*, not measured on this program's lot: DOE-1 in the experiment plan is
the DSC campaign that replaces them, and until it runs, every cure cycle
here is a starting point for a trial, not a qualified process.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math

from .materials import CureChemistry, chemistry as lookup_chemistry

#: Universal gas constant, J/(mol.K).
GAS_CONSTANT = 8.314462618

#: Absolute zero offset.
KELVIN = 273.15

#: Specific heat of a cured carbon/epoxy laminate, J/(kg.K).  Engineering
#: target; it moves the exotherm prediction and nothing else.
LAMINATE_SPECIFIC_HEAT_J_KG_K = 1_000.0

#: Convective film coefficient in a forced-convection oven, W/(m^2.K).
#: Engineering target from ordinary oven practice; DOE-1's instrumented
#: panel measures the real lag directly and makes this obsolete.
OVEN_FILM_COEFFICIENT_W_M2_K = 25.0

#: Heat-exchanging area per unit part area.  A part on a tool exchanges heat
#: with the oven over more than its own footprint: the bag side, the tool's
#: underside, and the tool's edges are all in the airstream.  Modelling the
#: tool's thermal mass while giving it only the part's footprint to breathe
#: through is the classic way to predict an exotherm that never happens; the
#: first run of this model reported a 34 K spike in a 1.6 mm laminate for
#: exactly that reason.
HEAT_EXCHANGE_AREA_FACTOR = 2.0

#: Resin viscosity below which the resin is considered mobile enough to
#: consolidate under pressure, Pa.s.
FLOW_VISCOSITY_LIMIT_PA_S = 100.0


def kelvin(celsius: float) -> float:
    return celsius + KELVIN


# --------------------------------------------------------------------------
# Resin state
# --------------------------------------------------------------------------


def reaction_rate(chem: CureChemistry, alpha: float, temperature_c: float) -> float:
    """Degree-of-cure rate, 1/s, from the diffusion-limited autocatalytic model.

    The diffusion denominator is the term that predicts vitrification: as the
    conversion approaches the critical value for the current temperature, the
    denominator grows exponentially and the rate collapses.
    """

    if alpha >= 1.0:
        return 0.0
    alpha = max(alpha, 0.0)
    temperature_k = kelvin(temperature_c)
    arrhenius = chem.kinetic_a_per_s * math.exp(-chem.kinetic_ea_j_mol / (GAS_CONSTANT * temperature_k))
    chemical = (alpha ** chem.kinetic_m) * ((1.0 - alpha) ** chem.kinetic_n)
    critical = chem.diffusion_alpha_c0 + chem.diffusion_alpha_ct_per_k * temperature_k
    exponent = chem.diffusion_c * (alpha - critical)
    # Guard the exponential: far past the critical conversion the rate is
    # zero, and math.exp would overflow before saying so.
    if exponent > 700.0:
        return 0.0
    diffusion = 1.0 + math.exp(exponent)
    return arrhenius * chemical / diffusion


def glass_transition_c(chem: CureChemistry, alpha: float) -> float:
    """Glass transition temperature at a degree of cure, degC (DiBenedetto)."""

    alpha = min(max(alpha, 0.0), 1.0)
    numerator = chem.tg_lambda * alpha
    denominator = 1.0 - (1.0 - chem.tg_lambda) * alpha
    return chem.tg_uncured_c + (chem.tg_full_c - chem.tg_uncured_c) * numerator / denominator


def conversion_ceiling(chem: CureChemistry, temperature_c: float) -> float:
    """Degree of cure at which the reaction stalls at this temperature.

    The diffusion factor's critical conversion.  Holding longer at a
    temperature cannot pass this value by any meaningful margin — the resin
    has vitrified — which is why a cure spec that demands a conversion above
    its own hold temperature's ceiling is asking for a part that can never
    be built, and why postcure exists.
    """

    return chem.diffusion_alpha_c0 + chem.diffusion_alpha_ct_per_k * kelvin(temperature_c)


def temperature_for_conversion(chem: CureChemistry, alpha: float) -> float:
    """Lowest hold temperature whose ceiling reaches this conversion, degC."""

    if not 0.0 < alpha < 1.0:
        raise ValueError("conversion must be in (0, 1)")
    return (alpha - chem.diffusion_alpha_c0) / chem.diffusion_alpha_ct_per_k - KELVIN


def viscosity_pa_s(chem: CureChemistry, alpha: float, temperature_c: float) -> float:
    """Resin viscosity, Pa.s (Castro-Macosko).

    Undefined at and past gelation, where the resin is no longer a liquid;
    reported as infinity so a caller cannot accidentally treat a gelled
    resin as flowable.
    """

    if alpha >= chem.gel_conversion:
        return math.inf
    temperature_k = kelvin(temperature_c)
    base = chem.viscosity_mu1_pa_s * math.exp(chem.viscosity_u_j_mol / (GAS_CONSTANT * temperature_k))
    ratio = chem.gel_conversion / (chem.gel_conversion - alpha)
    return base * ratio ** (chem.viscosity_a + chem.viscosity_b * alpha)


# --------------------------------------------------------------------------
# Cycle definition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CureSegment:
    """Ramp to a temperature at a rate, then hold there."""

    target_c: float
    rate_c_per_min: float
    hold_min: float = 0.0
    note: str = ""

    def __post_init__(self) -> None:
        if self.rate_c_per_min <= 0:
            raise ValueError("ramp rate must be positive; direction comes from the target")
        if self.hold_min < 0:
            raise ValueError("hold must be non-negative")


@dataclass(frozen=True)
class PressureStep:
    """Bag or press pressure applied from a trigger point onward."""

    #: Applied when the *part* first reaches this temperature on the way up.
    at_part_temperature_c: float
    pressure_kpa: float
    note: str = ""


@dataclass(frozen=True)
class CureCycle:
    """A complete, runnable cure recipe."""

    cycle_id: str
    name: str
    chemistry: str
    segments: tuple[CureSegment, ...]
    #: Vacuum held under the bag for the whole cycle, kPa absolute.
    vacuum_abs_kpa: float = 5.0
    pressure_steps: tuple[PressureStep, ...] = ()
    #: Service temperature the part must hold without softening, degC.
    service_temperature_c: float = 60.0
    #: Areal heat capacity of the tool the part sits on, J/(m^2.K).  A heavy
    #: tool is the usual reason a part's own temperature never reaches the
    #: oven's, and therefore the usual reason a recipe undercures.
    tool_areal_heat_capacity_j_m2_k: float = 0.0
    note: str = ""

    def air_temperature_c(self, minutes: float, start_c: float) -> float:
        """Oven set-point at a given time, degC."""

        time_left = minutes
        current = start_c
        for segment in self.segments:
            ramp_minutes = abs(segment.target_c - current) / segment.rate_c_per_min
            if time_left <= ramp_minutes:
                direction = 1.0 if segment.target_c >= current else -1.0
                return current + direction * segment.rate_c_per_min * time_left
            time_left -= ramp_minutes
            current = segment.target_c
            if time_left <= segment.hold_min:
                return current
            time_left -= segment.hold_min
        return current

    def duration_min(self, start_c: float) -> float:
        total = 0.0
        current = start_c
        for segment in self.segments:
            total += abs(segment.target_c - current) / segment.rate_c_per_min
            total += segment.hold_min
            current = segment.target_c
        return total

    @property
    def peak_temperature_c(self) -> float:
        return max(segment.target_c for segment in self.segments)


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CureSample:
    """One instant of the simulated cure."""

    minutes: float
    air_c: float
    part_c: float
    alpha: float
    tg_c: float
    viscosity_pa_s: float


@dataclass(frozen=True)
class CureResult:
    """Everything the cycle acceptance criteria need to look at."""

    cycle_id: str
    laminate_thickness_mm: float
    duration_min: float
    final_alpha: float
    final_tg_c: float
    peak_part_c: float
    peak_air_c: float
    #: Largest amount the part's own temperature exceeded the oven's, K.
    max_exotherm_overshoot_k: float
    #: Largest amount the part lagged the oven on the way up, K.
    max_thermal_lag_k: float
    gel_time_min: float | None
    minimum_viscosity_pa_s: float
    minimum_viscosity_time_min: float | None
    #: Window during which consolidation pressure may be applied, minutes.
    pressure_window_min: tuple[float, float] | None
    #: True when the reaction stalled because Tg overtook the part
    #: temperature, rather than because the cycle ended.
    vitrified: bool
    #: Tg minus service temperature at the end of cure, K.
    service_margin_k: float
    samples: tuple[CureSample, ...] = field(repr=False, default=())


def simulate(
    cycle: CureCycle,
    *,
    laminate_thickness_mm: float,
    laminate_density_g_cm3: float = 1.55,
    resin_mass_fraction: float = 0.35,
    start_c: float = 20.0,
    time_step_s: float = 2.0,
    sample_every_min: float = 2.0,
) -> CureResult:
    """Integrate part temperature, conversion, Tg and viscosity through a cycle.

    Lumped thermal model:

        (rho c t + C_tool) dT/dt = h (T_air - T) + rho t w_resin H da/dt

    The tool's areal heat capacity sits alongside the part's own because in
    an oven cure the tool and part heat together, and for a 0.3 mm skin on a
    6 mm aluminium tool the tool is 95 % of the thermal mass.
    """

    if laminate_thickness_mm <= 0:
        raise ValueError("thickness must be positive")
    if not 0.0 < resin_mass_fraction < 1.0:
        raise ValueError("resin mass fraction must be in (0, 1)")

    chem = lookup_chemistry(cycle.chemistry)
    thickness_m = laminate_thickness_mm * 1e-3
    density_kg_m3 = laminate_density_g_cm3 * 1000.0
    part_capacity = density_kg_m3 * thickness_m * LAMINATE_SPECIFIC_HEAT_J_KG_K
    capacity = part_capacity + cycle.tool_areal_heat_capacity_j_m2_k
    resin_areal_mass = density_kg_m3 * thickness_m * resin_mass_fraction
    exchange_coefficient = OVEN_FILM_COEFFICIENT_W_M2_K * HEAT_EXCHANGE_AREA_FACTOR

    duration = cycle.duration_min(start_c)
    steps = max(int(duration * 60.0 / time_step_s), 1)

    part_c = start_c
    alpha = chem.initial_conversion
    minutes = 0.0
    peak_part = part_c
    max_overshoot = 0.0
    max_lag = 0.0
    running_max_air = start_c
    previous_air = start_c
    gel_time: float | None = None
    min_viscosity = math.inf
    min_viscosity_time: float | None = None
    flow_window_open: float | None = None
    samples: list[CureSample] = []
    next_sample = 0.0

    for _ in range(steps):
        air_c = cycle.air_temperature_c(minutes, start_c)
        rate = reaction_rate(chem, alpha, part_c)
        heat_flux = exchange_coefficient * (air_c - part_c)
        exotherm_flux = resin_areal_mass * chem.enthalpy_j_g * 1000.0 * rate
        part_c += (heat_flux + exotherm_flux) / capacity * time_step_s
        alpha = min(alpha + rate * time_step_s, 1.0)
        minutes += time_step_s / 60.0

        peak_part = max(peak_part, part_c)
        # Both thermal metrics are measured only while the oven is heating or
        # holding.  On the cooldown the part necessarily trails the falling
        # air, and counting that as either an exotherm or a lag is how the
        # first version of this model reported a 14 K "exotherm" that was
        # nothing but a thermally massive tool giving its heat back.
        heating_or_holding = air_c >= previous_air - 1e-9
        running_max_air = max(running_max_air, air_c)
        if heating_or_holding:
            max_overshoot = max(max_overshoot, part_c - running_max_air)
            max_lag = max(max_lag, air_c - part_c)
        previous_air = air_c
        if gel_time is None and alpha >= chem.gel_conversion:
            gel_time = minutes
        if alpha < chem.gel_conversion:
            mu = viscosity_pa_s(chem, alpha, part_c)
            if mu < min_viscosity:
                min_viscosity = mu
                min_viscosity_time = minutes
            if flow_window_open is None and mu <= FLOW_VISCOSITY_LIMIT_PA_S:
                flow_window_open = minutes
        if minutes >= next_sample:
            samples.append(
                CureSample(
                    round(minutes, 3),
                    round(air_c, 2),
                    round(part_c, 2),
                    round(alpha, 5),
                    round(glass_transition_c(chem, alpha), 2),
                    viscosity_pa_s(chem, alpha, part_c),
                )
            )
            next_sample += sample_every_min

    final_tg = glass_transition_c(chem, alpha)
    # Vitrification: the reaction is still incomplete and the resin's own
    # glass transition has caught up with the hottest the part ever got.
    vitrified = alpha < 0.95 and final_tg >= cycle.peak_temperature_c - 2.0

    window: tuple[float, float] | None = None
    if flow_window_open is not None:
        window = (round(flow_window_open, 2), round(gel_time if gel_time else duration, 2))

    return CureResult(
        cycle_id=cycle.cycle_id,
        laminate_thickness_mm=laminate_thickness_mm,
        duration_min=round(duration, 2),
        final_alpha=round(alpha, 4),
        final_tg_c=round(final_tg, 2),
        peak_part_c=round(peak_part, 2),
        peak_air_c=cycle.peak_temperature_c,
        max_exotherm_overshoot_k=round(max_overshoot, 3),
        max_thermal_lag_k=round(max_lag, 2),
        gel_time_min=None if gel_time is None else round(gel_time, 2),
        minimum_viscosity_pa_s=round(min_viscosity, 4) if min_viscosity < math.inf else math.inf,
        minimum_viscosity_time_min=None if min_viscosity_time is None else round(min_viscosity_time, 2),
        pressure_window_min=window,
        vitrified=vitrified,
        service_margin_k=round(final_tg - cycle.service_temperature_c, 2),
        samples=tuple(samples),
    )


# --------------------------------------------------------------------------
# Acceptance
# --------------------------------------------------------------------------

#: Cure completeness: achieved conversion as a fraction of the ceiling the
#: hold temperature can reach.
#:
#: An absolute degree-of-cure requirement is the obvious criterion and it is
#: the wrong one.  The diffusion-limited kinetics impose a **conversion
#: ceiling** that rises with cure temperature — this chemistry cannot pass
#: about 0.86 at 180 degC however long it is held, because the partially
#: cured resin vitrifies there.  Reaching 0.90 needs roughly 199 degC, that
#: is, a freestanding postcure above the cure temperature.  A spec demanding
#: 0.90 at a 180 degC hold is asking for a part that cannot be built, and the
#: 120 degC system, whose ceiling is 0.68, would fail such a spec forever
#: while making perfectly serviceable parts for a 35 degC service limit.
#:
#: So the two criteria are separated, and between them they catch the two
#: distinct ways a cycle goes wrong:
#:
#: * **completeness** — conversion against its own ceiling — catches a hold
#:   that is too *short*;
#: * **service margin** — Tg over service temperature — catches a hold that
#:   is too *cold*.
MIN_CURE_COMPLETENESS = 0.95
#: Minimum margin between the cured glass transition and service temperature.
MIN_SERVICE_MARGIN_K = 30.0
#: Largest self-heating overshoot allowed above the oven set-point.
MAX_EXOTHERM_OVERSHOOT_K = 8.0
#: Largest lag allowed between oven and part on the way up.  A bigger lag
#: means the recipe's hold times are being measured against a temperature the
#: part never had.
MAX_THERMAL_LAG_K = 15.0
#: Shortest usable pressure window; anything less cannot be hit reliably by
#: a technician watching a thermocouple.
MIN_PRESSURE_WINDOW_MIN = 10.0


@dataclass(frozen=True)
class CureCheck:
    name: str
    actual: float | bool
    limit: float | bool
    comparison: str
    passed: bool
    consequence: str


def acceptance(result: CureResult, cycle: CureCycle) -> list[CureCheck]:
    """Evaluate a simulated cycle against the cure acceptance criteria."""

    window_length = (
        result.pressure_window_min[1] - result.pressure_window_min[0]
        if result.pressure_window_min
        else 0.0
    )
    chem = lookup_chemistry(cycle.chemistry)
    ceiling = conversion_ceiling(chem, cycle.peak_temperature_c)
    completeness = min(result.final_alpha / ceiling, 1.0) if ceiling > 0 else 0.0
    checks = [
        CureCheck(
            "cure_completeness", round(completeness, 4), MIN_CURE_COMPLETENESS, ">=",
            completeness >= MIN_CURE_COMPLETENESS,
            "hold is too short: the reaction is still running when the cycle ends",
        ),
        CureCheck(
            "service_margin_k", result.service_margin_k, MIN_SERVICE_MARGIN_K, ">=",
            result.service_margin_k >= MIN_SERVICE_MARGIN_K,
            "part softens in service; stiffness and bond strength fall with temperature",
        ),
        CureCheck(
            "not_vitrified", not result.vitrified, True, "==", not result.vitrified,
            "reaction stalled below full cure; holding longer at this temperature cannot fix it",
        ),
        CureCheck(
            "exotherm_overshoot_k", result.max_exotherm_overshoot_k, MAX_EXOTHERM_OVERSHOOT_K,
            "<=", result.max_exotherm_overshoot_k <= MAX_EXOTHERM_OVERSHOOT_K,
            "self-heating outruns the oven; local overcure, resin degradation, distortion",
        ),
        CureCheck(
            "thermal_lag_k", result.max_thermal_lag_k, MAX_THERMAL_LAG_K, "<=",
            result.max_thermal_lag_k <= MAX_THERMAL_LAG_K,
            "hold time is being counted against an oven temperature the part never reached",
        ),
        CureCheck(
            "pressure_window_min", round(window_length, 2), MIN_PRESSURE_WINDOW_MIN, ">=",
            window_length >= MIN_PRESSURE_WINDOW_MIN,
            "consolidation window too short to hit reliably; voids or resin bleed-out",
        ),
    ]
    for step in cycle.pressure_steps:
        if result.pressure_window_min is None:
            checks.append(
                CureCheck(
                    f"pressure_step[{step.pressure_kpa:g}kPa]", False, True, "==", False,
                    "no flow window found; pressure instruction cannot be satisfied",
                )
            )
            continue
        # Find when the part first reached the step's trigger temperature.
        trigger = next(
            (sample.minutes for sample in result.samples
             if sample.part_c >= step.at_part_temperature_c),
            None,
        )
        inside = (
            trigger is not None
            and result.pressure_window_min[0] <= trigger <= result.pressure_window_min[1]
        )
        checks.append(
            CureCheck(
                f"pressure_step[{step.at_part_temperature_c:g}C]",
                round(trigger, 2) if trigger is not None else False,
                result.pressure_window_min,
                "within",
                inside,
                "pressure applied outside the flow window: early bleeds resin out, late traps voids",
            )
        )
    return checks


# --------------------------------------------------------------------------
# The program's cure cycles
# --------------------------------------------------------------------------

#: Areal heat capacity of a 6 mm aluminium tool, J/(m^2.K).  Carried
#: explicitly because it, not the laminate, dominates the thermal lag.
ALUMINIUM_TOOL_6MM_J_M2_K = 2700.0 * 0.006 * 900.0

CURE_180_STANDARD = CureCycle(
    cycle_id="CC-180-STD",
    name="180 degC two-dwell cure",
    chemistry="epoxy-180C-toughened",
    segments=(
        CureSegment(110.0, 2.0, 60.0, "flow dwell: viscosity minimum, consolidate and debulk"),
        CureSegment(180.0, 2.0, 120.0, "cure dwell"),
        CureSegment(60.0, 2.5, 0.0, "controlled cooldown; see the spring-in model for why the rate matters"),
    ),
    pressure_steps=(
        PressureStep(100.0, 300.0, "full press pressure once the resin is mobile and before gel"),
    ),
    service_temperature_c=60.0,
    tool_areal_heat_capacity_j_m2_k=ALUMINIUM_TOOL_6MM_J_M2_K,
    note=(
        "The intermediate dwell is not tradition. It holds the part at the "
        "viscosity minimum long enough for interply air to be pulled out "
        "under vacuum before the reaction thickens the resin."
    ),
)

CURE_180_FAST = CureCycle(
    cycle_id="CC-180-FAST",
    name="180 degC single-dwell cure (candidate)",
    chemistry="epoxy-180C-toughened",
    segments=(
        CureSegment(180.0, 5.0, 90.0, "single dwell"),
        CureSegment(60.0, 5.0, 0.0, "uncontrolled cooldown"),
    ),
    pressure_steps=(PressureStep(120.0, 300.0),),
    service_temperature_c=60.0,
    tool_areal_heat_capacity_j_m2_k=ALUMINIUM_TOOL_6MM_J_M2_K,
    note=(
        "Candidate cycle kept in the register precisely because it is "
        "tempting: it saves about ninety minutes per part. What it costs is "
        "measured rather than argued about."
    ),
)

CURE_120_OVEN = CureCycle(
    cycle_id="CC-120-OVEN",
    name="120 degC oven cure",
    chemistry="epoxy-120C-oven",
    segments=(
        CureSegment(80.0, 1.5, 45.0, "flow dwell"),
        CureSegment(120.0, 1.5, 180.0, "cure dwell"),
        CureSegment(50.0, 2.0, 0.0, "controlled cooldown"),
    ),
    pressure_steps=(PressureStep(75.0, 95.0, "vacuum-bag only; no press"),),
    vacuum_abs_kpa=5.0,
    service_temperature_c=35.0,
    tool_areal_heat_capacity_j_m2_k=ALUMINIUM_TOOL_6MM_J_M2_K,
    note=(
        "Lower-temperature alternative. Halving the cooldown roughly halves "
        "residual stress and spring-in, which is why the high-modulus keel "
        "rail option is only viable with this system."
    ),
)

CYCLES: tuple[CureCycle, ...] = (CURE_180_STANDARD, CURE_180_FAST, CURE_120_OVEN)

#: Cycles the program has qualified for production use.  A cycle in
#: ``CYCLES`` but not here is a candidate, and is expected to fail something.
QUALIFIED_CYCLE_IDS: frozenset[str] = frozenset({"CC-180-STD", "CC-120-OVEN"})

#: Representative laminate the cycles are checked against: the thickest part
#: in the schedule set, because thickness drives both exotherm and lag.
REFERENCE_THICKNESS_MM = 1.6


def cycle(cycle_id: str) -> CureCycle:
    for item in CYCLES:
        if item.cycle_id == cycle_id:
            return item
    raise KeyError(f"unknown cure cycle {cycle_id!r}")


def evaluate_cycle(item: CureCycle, *, thickness_mm: float = REFERENCE_THICKNESS_MM) -> dict[str, object]:
    result = simulate(item, laminate_thickness_mm=thickness_mm)
    checks = acceptance(result, item)
    return {
        "cycle_id": item.cycle_id,
        "name": item.name,
        "chemistry": item.chemistry,
        "qualified": item.cycle_id in QUALIFIED_CYCLE_IDS,
        "note": item.note,
        "segments": [asdict(segment) for segment in item.segments],
        "pressure_steps": [asdict(step) for step in item.pressure_steps],
        "vacuum_abs_kpa": item.vacuum_abs_kpa,
        "tool_areal_heat_capacity_j_m2_k": round(item.tool_areal_heat_capacity_j_m2_k, 1),
        "result": {
            key: value
            for key, value in asdict(result).items()
            if key != "samples"
        },
        "conversion_ceiling_at_hold": round(
            conversion_ceiling(lookup_chemistry(item.chemistry), item.peak_temperature_c), 4
        ),
        "temperature_for_alpha_0p90_c": round(
            temperature_for_conversion(lookup_chemistry(item.chemistry), 0.90), 1
        ),
        "checks": [asdict(check) for check in checks],
        "passed": all(check.passed for check in checks),
    }


def validate_cycles() -> list[str]:
    """A qualified cycle must pass every acceptance criterion."""

    errors: list[str] = []
    for item in CYCLES:
        report = evaluate_cycle(item)
        if item.cycle_id in QUALIFIED_CYCLE_IDS and not report["passed"]:
            failed = [
                check["name"] for check in report["checks"] if not check["passed"]  # type: ignore[index]
            ]
            errors.append(
                f"{item.cycle_id}: qualified cycle fails {', '.join(failed)}"
            )
    return errors


def snapshot() -> dict[str, object]:
    errors = validate_cycles()
    return {
        "reference_thickness_mm": REFERENCE_THICKNESS_MM,
        "valid": not errors,
        "errors": errors,
        "acceptance_limits": {
            "min_cure_completeness": MIN_CURE_COMPLETENESS,
            "min_service_margin_k": MIN_SERVICE_MARGIN_K,
            "max_exotherm_overshoot_k": MAX_EXOTHERM_OVERSHOOT_K,
            "max_thermal_lag_k": MAX_THERMAL_LAG_K,
            "min_pressure_window_min": MIN_PRESSURE_WINDOW_MIN,
            "flow_viscosity_limit_pa_s": FLOW_VISCOSITY_LIMIT_PA_S,
        },
        "cycles": [evaluate_cycle(item) for item in CYCLES],
    }


def main() -> int:
    report = snapshot()
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
