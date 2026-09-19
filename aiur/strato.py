"""Executable engineering checks for STRATO-P0, the observation platform.

STRATO-P0 carries no aircraft and releases nothing.  It lifts an imaging
package into the stratosphere, looks down, reports what it sees, and comes
back under a parachute.  Every question the article has to answer is one of
four kinds, and this module is the executable form of each:

* **Will it get there?**  A standard atmosphere, the lifting-gas density
  that goes with it, and the two vehicle regimes the program uses: a
  constant-gas-mass sounding balloon that climbs until it bursts, and a
  fixed-volume float envelope that stops where its buoyancy runs out.
* **What can it see from there?**  Horizon, visible cap, nadir ground
  sample distance, swath, and slant range for a stated optic.
* **Will it stay alive?**  Ambient temperature at altitude, a battery
  budget for the sounding flight, and a day/night balance for the float
  article that follows it.
* **Will it come down safely and legally?**  Parachute descent rate and
  the payload-package thresholds under which an unmanned free balloon is
  exempt from 14 CFR Part 101 Subpart D.

Numbers marked *allocation* or *target* are engineering targets, not
measured performance.  The atmosphere is the 1976 U.S. Standard Atmosphere,
which is a reference condition and not a forecast; a real launch day is
warmer, colder, and windier than it.  Everything is dependency-free and
deterministic so the numbers quoted in docs/prototype-strato-p0.md can be
regenerated with ``python -m aiur.strato``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from typing import Iterable

# --------------------------------------------------------------------------
# Physical constants (1976 U.S. Standard Atmosphere, CODATA where it differs)
# --------------------------------------------------------------------------

#: Standard gravitational acceleration, m/s².
G0_M_S2 = 9.80665
#: Universal gas constant, J/(mol·K).
R_UNIVERSAL_J_MOL_K = 8.31446
#: Molar mass of dry air, kg/mol.
M_AIR_KG_MOL = 0.0289644
#: Specific gas constant of dry air, J/(kg·K).
R_AIR_J_KG_K = R_UNIVERSAL_J_MOL_K / M_AIR_KG_MOL
#: Earth radius used for the geopotential conversion in the 1976 standard, m.
EARTH_RADIUS_GEOPOTENTIAL_M = 6_356_766.0
#: Mean Earth radius for horizon and footprint geometry, m.
EARTH_RADIUS_MEAN_M = 6_371_000.0
#: Solar constant at the top of the atmosphere, W/m².  A float platform at
#: 20 km sits above ~93 % of the air column, so this is the right order for
#: a stratospheric solar budget; a 0.95 transmission is applied below.
SOLAR_CONSTANT_W_M2 = 1361.0

#: Sea-level values of the standard atmosphere, used as sanity anchors.
SEA_LEVEL_TEMPERATURE_K = 288.15
SEA_LEVEL_PRESSURE_PA = 101_325.0
SEA_LEVEL_AIR_DENSITY_KG_M3 = SEA_LEVEL_PRESSURE_PA / (
    R_AIR_J_KG_K * SEA_LEVEL_TEMPERATURE_K
)

#: The program's altitude threshold for "stratospheric".  The tropopause
#: sits at ~11 km in the standard atmosphere but ranges from ~8 km at the
#: poles to ~18 km in the tropics, so 20 km is the lowest altitude that is
#: unambiguously stratospheric at every latitude and season.
STRATOSPHERE_THRESHOLD_M = 20_000.0

#: Ceiling of the atmosphere model.  The layers below cover 0–47 km, which
#: is above any burst altitude a latex sounding balloon reaches.
ATMOSPHERE_CEILING_M = 47_000.0


class LiftingGas(str, Enum):
    """Lifting gases the model knows, by molar mass.

    Hydrogen is modelled so the trade can be quoted; STRATO-P0 flies helium
    only, for the same reason CARRIER-P0 did — it adds a hazard without
    helping answer the question the article exists for.
    """

    HELIUM = "helium"
    HYDROGEN = "hydrogen"

    @property
    def molar_mass_kg_mol(self) -> float:
        return _GAS_MOLAR_MASS[self]


_GAS_MOLAR_MASS: dict[LiftingGas, float] = {
    LiftingGas.HELIUM: 0.0040026,
    LiftingGas.HYDROGEN: 0.00201588,
}


# --------------------------------------------------------------------------
# Standard atmosphere
# --------------------------------------------------------------------------

#: 1976 U.S. Standard Atmosphere layers below 47 km: (base geopotential
#: altitude m, base temperature K, lapse rate K/m).  Base pressures are
#: derived at import time from the sea-level value so the table cannot
#: disagree with the formula that uses it.
_LAYERS: tuple[tuple[float, float, float], ...] = (
    (0.0, 288.15, -0.0065),
    (11_000.0, 216.65, 0.0),
    (20_000.0, 216.65, 0.001),
    (32_000.0, 228.65, 0.0028),
    (47_000.0, 270.65, 0.0),
)


def _layer_base_pressures() -> tuple[float, ...]:
    pressures = [SEA_LEVEL_PRESSURE_PA]
    for index in range(1, len(_LAYERS)):
        base_h, base_t, lapse = _LAYERS[index - 1]
        top_h = _LAYERS[index][0]
        pressures.append(_pressure_in_layer(pressures[-1], base_t, lapse, top_h - base_h))
    return tuple(pressures)


def _pressure_in_layer(
    base_pressure_pa: float, base_temperature_k: float, lapse_k_m: float, dh_m: float
) -> float:
    if lapse_k_m == 0.0:
        return base_pressure_pa * math.exp(-G0_M_S2 * dh_m / (R_AIR_J_KG_K * base_temperature_k))
    temperature_k = base_temperature_k + lapse_k_m * dh_m
    exponent = -G0_M_S2 / (R_AIR_J_KG_K * lapse_k_m)
    return base_pressure_pa * (temperature_k / base_temperature_k) ** exponent


_LAYER_BASE_PRESSURES_PA = _layer_base_pressures()


def geopotential_altitude_m(geometric_altitude_m: float) -> float:
    """Geopotential altitude for a geometric altitude, per the 1976 standard."""

    r0 = EARTH_RADIUS_GEOPOTENTIAL_M
    return r0 * geometric_altitude_m / (r0 + geometric_altitude_m)


@dataclass(frozen=True)
class AtmosphereState:
    """Ambient conditions at one geometric altitude."""

    altitude_m: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15


def standard_atmosphere(altitude_m: float) -> AtmosphereState:
    """1976 U.S. Standard Atmosphere between sea level and 47 km geometric."""

    if altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    if altitude_m > ATMOSPHERE_CEILING_M:
        raise ValueError(f"altitude exceeds the {ATMOSPHERE_CEILING_M:.0f} m model ceiling")

    h = geopotential_altitude_m(altitude_m)
    layer_index = 0
    for index, (base_h, _, _) in enumerate(_LAYERS):
        if h >= base_h:
            layer_index = index
    base_h, base_t, lapse = _LAYERS[layer_index]
    base_p = _LAYER_BASE_PRESSURES_PA[layer_index]

    temperature_k = base_t + lapse * (h - base_h)
    pressure_pa = _pressure_in_layer(base_p, base_t, lapse, h - base_h)
    density = pressure_pa / (R_AIR_J_KG_K * temperature_k)
    return AtmosphereState(altitude_m, temperature_k, pressure_pa, density)


def lifting_gas_density_kg_m3(
    altitude_m: float,
    gas: LiftingGas = LiftingGas.HELIUM,
    *,
    superpressure_pa: float = 0.0,
) -> float:
    """Density of the lifting gas at ambient temperature and ambient + superpressure.

    Assumes the gas is at ambient temperature.  Daytime solar heating raises
    the gas above ambient ("supertemperature") and adds lift; ignoring it is
    conservative for lift and is stated as a modelling assumption, not a
    physical claim.
    """

    if superpressure_pa < 0.0:
        raise ValueError("superpressure must be non-negative")
    state = standard_atmosphere(altitude_m)
    return (
        (state.pressure_pa + superpressure_pa)
        * gas.molar_mass_kg_mol
        / (R_UNIVERSAL_J_MOL_K * state.temperature_k)
    )


def net_lift_per_m3_kg(
    altitude_m: float, gas: LiftingGas = LiftingGas.HELIUM, *, superpressure_pa: float = 0.0
) -> float:
    """Mass lifted per cubic metre of envelope at altitude (air minus gas)."""

    state = standard_atmosphere(altitude_m)
    return state.density_kg_m3 - lifting_gas_density_kg_m3(
        altitude_m, gas, superpressure_pa=superpressure_pa
    )


# --------------------------------------------------------------------------
# Float regime: fixed-volume envelope stops where its buoyancy runs out
# --------------------------------------------------------------------------


def envelope_volume_for_float_m3(
    gross_mass_kg: float,
    float_altitude_m: float,
    gas: LiftingGas = LiftingGas.HELIUM,
    *,
    superpressure_pa: float = 0.0,
) -> float:
    """Fully-inflated envelope volume that floats a gross mass at an altitude.

    ``gross_mass_kg`` is everything except the lifting gas: envelope, rigging,
    payload package.  The gas mass is implied by the volume and is reported
    separately by :func:`gas_mass_kg`.
    """

    if gross_mass_kg <= 0.0:
        raise ValueError("gross mass must be positive")
    return gross_mass_kg / net_lift_per_m3_kg(
        float_altitude_m, gas, superpressure_pa=superpressure_pa
    )


def float_altitude_m(
    envelope_volume_m3: float,
    gross_mass_kg: float,
    gas: LiftingGas = LiftingGas.HELIUM,
    *,
    superpressure_pa: float = 0.0,
) -> float:
    """Altitude at which a full fixed-volume envelope carries the gross mass.

    Solved by bisection on net lift, which is monotonic in altitude.  Raises
    if the envelope cannot lift the mass at sea level, or if it would still be
    climbing at the model ceiling.
    """

    if envelope_volume_m3 <= 0.0:
        raise ValueError("envelope volume must be positive")
    if gross_mass_kg <= 0.0:
        raise ValueError("gross mass must be positive")

    def net_lift(altitude: float) -> float:
        return envelope_volume_m3 * net_lift_per_m3_kg(
            altitude, gas, superpressure_pa=superpressure_pa
        ) - gross_mass_kg

    low, high = 0.0, ATMOSPHERE_CEILING_M
    if net_lift(low) < 0.0:
        raise ValueError("envelope cannot lift the gross mass at sea level")
    if net_lift(high) > 0.0:
        raise ValueError("envelope would float above the model ceiling")
    for _ in range(80):
        mid = 0.5 * (low + high)
        if net_lift(mid) > 0.0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def gas_mass_kg(
    envelope_volume_m3: float,
    altitude_m: float,
    gas: LiftingGas = LiftingGas.HELIUM,
    *,
    superpressure_pa: float = 0.0,
) -> float:
    """Mass of lifting gas filling a volume at altitude."""

    if envelope_volume_m3 < 0.0:
        raise ValueError("envelope volume must be non-negative")
    return envelope_volume_m3 * lifting_gas_density_kg_m3(
        altitude_m, gas, superpressure_pa=superpressure_pa
    )


# --------------------------------------------------------------------------
# Sounding regime: constant gas mass, climbs until the envelope bursts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SoundingBalloon:
    """A latex sounding balloon and what hangs from it.

    ``burst_diameter_m`` is a vendor figure for the balloon size flown and
    must be taken from the manufacturer's sheet for the exact lot; the
    default is representative of a 1200 g latex balloon and is a design
    input, not an Aiur measurement.  ``drag_coefficient`` is the value the
    hobby-sounding community's ascent predictors use for a latex balloon; it
    is an engineering assumption until a flight measures the ascent profile.
    """

    balloon_mass_kg: float = 1.2
    burst_diameter_m: float = 8.63
    payload_mass_kg: float = 0.85
    free_lift_kg: float = 0.9
    drag_coefficient: float = 0.3
    gas: LiftingGas = LiftingGas.HELIUM

    @property
    def lifted_mass_kg(self) -> float:
        """Everything the gas has to carry: balloon skin plus payload package."""

        return self.balloon_mass_kg + self.payload_mass_kg

    def _validate(self) -> None:
        if self.balloon_mass_kg <= 0.0 or self.payload_mass_kg < 0.0:
            raise ValueError("balloon mass must be positive and payload non-negative")
        if self.burst_diameter_m <= 0.0:
            raise ValueError("burst diameter must be positive")
        if self.free_lift_kg <= 0.0:
            raise ValueError("free lift must be positive; a neutral balloon does not climb")
        if self.drag_coefficient <= 0.0:
            raise ValueError("drag coefficient must be positive")

    def launch_volume_m3(self) -> float:
        """Gas volume at sea level that gives the lifted mass plus free lift."""

        self._validate()
        return (self.lifted_mass_kg + self.free_lift_kg) / net_lift_per_m3_kg(0.0, self.gas)

    def gas_mass_kg(self) -> float:
        return gas_mass_kg(self.launch_volume_m3(), 0.0, self.gas)

    def diameter_at_m(self, altitude_m: float) -> float:
        """Balloon diameter as the fixed gas mass expands with altitude."""

        volume = self.gas_mass_kg() / lifting_gas_density_kg_m3(altitude_m, self.gas)
        return (6.0 * volume / math.pi) ** (1.0 / 3.0)

    def ascent_rate_at_m_s(self, altitude_m: float) -> float:
        """Terminal ascent rate where free lift balances drag.

        With the gas at ambient temperature the free lift is constant with
        altitude, and the growing balloon's drag area rises more slowly than
        air density falls, so the ascent rate creeps up on the way to burst.
        """

        self._validate()
        density = standard_atmosphere(altitude_m).density_kg_m3
        area = math.pi * self.diameter_at_m(altitude_m) ** 2 / 4.0
        return math.sqrt(
            2.0 * G0_M_S2 * self.free_lift_kg / (density * self.drag_coefficient * area)
        )

    def burst_altitude_m(self) -> float:
        """Altitude at which the expanding envelope reaches its burst diameter.

        Bisection on diameter, which is monotonic in altitude.  Raises if the
        balloon is over-filled enough to burst on the ground, or if it would
        still be intact at the model ceiling.
        """

        self._validate()
        low, high = 0.0, ATMOSPHERE_CEILING_M
        if self.diameter_at_m(low) >= self.burst_diameter_m:
            raise ValueError("balloon is at burst diameter on the ground")
        if self.diameter_at_m(high) < self.burst_diameter_m:
            raise ValueError("balloon would not burst below the model ceiling")
        for _ in range(80):
            mid = 0.5 * (low + high)
            if self.diameter_at_m(mid) < self.burst_diameter_m:
                low = mid
            else:
                high = mid
        return 0.5 * (low + high)

    def time_to_burst_s(self, step_m: float = 100.0) -> float:
        """Ascent time integrated over the altitude profile."""

        if step_m <= 0.0:
            raise ValueError("integration step must be positive")
        burst = self.burst_altitude_m()
        altitude = 0.0
        elapsed = 0.0
        while altitude < burst:
            top = min(altitude + step_m, burst)
            mid = 0.5 * (altitude + top)
            elapsed += (top - altitude) / self.ascent_rate_at_m_s(mid)
            altitude = top
        return elapsed

    def time_above_stratosphere_threshold_s(
        self, threshold_m: float = STRATOSPHERE_THRESHOLD_M, step_m: float = 100.0
    ) -> float:
        """Ascent time spent above the threshold before burst (descent excluded)."""

        burst = self.burst_altitude_m()
        if burst <= threshold_m:
            return 0.0
        altitude = threshold_m
        elapsed = 0.0
        while altitude < burst:
            top = min(altitude + step_m, burst)
            mid = 0.5 * (altitude + top)
            elapsed += (top - altitude) / self.ascent_rate_at_m_s(mid)
            altitude = top
        return elapsed


# --------------------------------------------------------------------------
# Descent
# --------------------------------------------------------------------------


def parachute_descent_rate_m_s(
    descending_mass_kg: float,
    canopy_area_m2: float,
    *,
    altitude_m: float = 0.0,
    drag_coefficient: float = 0.75,
) -> float:
    """Steady descent rate under a round canopy at the stated altitude.

    The default drag coefficient is the flat-circular-canopy value used in
    parachute sizing; the landing-speed requirement is evaluated at sea-level
    density, where the package is slowest and where people are.
    """

    if descending_mass_kg <= 0.0:
        raise ValueError("descending mass must be positive")
    if canopy_area_m2 <= 0.0:
        raise ValueError("canopy area must be positive")
    if drag_coefficient <= 0.0:
        raise ValueError("drag coefficient must be positive")
    density = standard_atmosphere(altitude_m).density_kg_m3
    return math.sqrt(
        2.0 * descending_mass_kg * G0_M_S2 / (density * drag_coefficient * canopy_area_m2)
    )


def canopy_area_for_landing_m2(
    descending_mass_kg: float,
    landing_rate_m_s: float,
    *,
    drag_coefficient: float = 0.75,
) -> float:
    """Canopy area that lands the mass at the target sea-level rate."""

    if landing_rate_m_s <= 0.0:
        raise ValueError("landing rate must be positive")
    return (
        2.0
        * descending_mass_kg
        * G0_M_S2
        / (SEA_LEVEL_AIR_DENSITY_KG_M3 * drag_coefficient * landing_rate_m_s**2)
    )


# --------------------------------------------------------------------------
# Observation geometry
# --------------------------------------------------------------------------


def horizon_distance_m(altitude_m: float) -> float:
    """Straight-line distance to the geometric horizon (no refraction)."""

    if altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    r = EARTH_RADIUS_MEAN_M
    return math.sqrt(2.0 * r * altitude_m + altitude_m**2)


def horizon_ground_range_m(altitude_m: float) -> float:
    """Great-circle distance along the ground to the horizon."""

    if altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    r = EARTH_RADIUS_MEAN_M
    return r * math.acos(r / (r + altitude_m))


def visible_cap_area_km2(altitude_m: float) -> float:
    """Area of the spherical cap inside the geometric horizon."""

    if altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    r = EARTH_RADIUS_MEAN_M
    return 2.0 * math.pi * r**2 * altitude_m / (r + altitude_m) / 1e6


@dataclass(frozen=True)
class Optic:
    """A camera as the geometry sees it.

    Defaults describe a 1-inch-class sensor behind a 25 mm lens.  They are a
    stand-in for whichever module the program buys; the point of the class
    is that the buy is checked against a GSD target before it is made.
    """

    focal_length_m: float = 0.025
    pixel_pitch_m: float = 2.4e-6
    sensor_width_m: float = 0.0132
    sensor_height_m: float = 0.0088

    def _validate(self) -> None:
        if min(self.focal_length_m, self.pixel_pitch_m, self.sensor_width_m, self.sensor_height_m) <= 0:
            raise ValueError("optic dimensions must be positive")

    def nadir_gsd_m(self, altitude_m: float) -> float:
        """Ground sample distance straight down."""

        self._validate()
        return altitude_m * self.pixel_pitch_m / self.focal_length_m

    def off_nadir_gsd_m(self, altitude_m: float, off_nadir_deg: float) -> float:
        """Along-scan GSD at an off-nadir angle (flat-Earth; fine inside 60°)."""

        if not 0.0 <= off_nadir_deg < 90.0:
            raise ValueError("off-nadir angle must be in [0, 90) degrees")
        theta = math.radians(off_nadir_deg)
        return self.nadir_gsd_m(altitude_m) / math.cos(theta) ** 2

    def swath_m(self, altitude_m: float) -> tuple[float, float]:
        """Nadir footprint (across, along) of one frame."""

        self._validate()
        scale = altitude_m / self.focal_length_m
        return (self.sensor_width_m * scale, self.sensor_height_m * scale)

    def slant_range_m(self, altitude_m: float, off_nadir_deg: float) -> float:
        if not 0.0 <= off_nadir_deg < 90.0:
            raise ValueError("off-nadir angle must be in [0, 90) degrees")
        return altitude_m / math.cos(math.radians(off_nadir_deg))


# --------------------------------------------------------------------------
# Power and thermal
# --------------------------------------------------------------------------


def sounding_battery_wh(
    load_w: float,
    flight_hours: float,
    *,
    cold_capacity_fraction: float = 0.6,
    margin_factor: float = 1.5,
) -> float:
    """Battery energy to buy for a sounding flight, derated for cold and margin.

    ``cold_capacity_fraction`` is the fraction of room-temperature capacity a
    cell delivers at the payload's coldest internal temperature.  0.6 is a
    placeholder until the chamber soak on S0-A measures it for the chosen
    cell; the test replaces the number, the formula stays.
    """

    if load_w < 0.0 or flight_hours < 0.0:
        raise ValueError("load and duration must be non-negative")
    if not 0.0 < cold_capacity_fraction <= 1.0:
        raise ValueError("cold capacity fraction must be in (0, 1]")
    if margin_factor < 1.0:
        raise ValueError("margin factor must be at least 1")
    return load_w * flight_hours * margin_factor / cold_capacity_fraction


@dataclass(frozen=True)
class FloatPowerBudget:
    """Day/night energy balance for the persistent float article (STRATO-P1).

    Not needed for the sounding flight, but the float article is where
    observation becomes persistent, and its power balance is the first thing
    that decides whether a given envelope can carry it.  Sun hours are a
    latitude/season input; the defaults are a mid-latitude equinox.
    """

    continuous_load_w: float = 12.0
    solar_area_m2: float = 0.5
    cell_efficiency: float = 0.20
    #: Mean cosine of the sun angle over the day for a horizontal array.
    mean_incidence_factor: float = 0.55
    atmospheric_transmission: float = 0.95
    sun_hours: float = 12.0
    night_hours: float = 12.0
    battery_wh: float = 300.0
    depth_of_discharge: float = 0.8
    charge_efficiency: float = 0.9

    def daily_generation_wh(self) -> float:
        return (
            SOLAR_CONSTANT_W_M2
            * self.atmospheric_transmission
            * self.solar_area_m2
            * self.cell_efficiency
            * self.mean_incidence_factor
            * self.sun_hours
        )

    def night_energy_wh(self) -> float:
        return self.continuous_load_w * self.night_hours

    def usable_battery_wh(self) -> float:
        return self.battery_wh * self.depth_of_discharge

    def battery_margin(self) -> float:
        """Usable battery over night demand; < 1 means the night is not survived."""

        night = self.night_energy_wh()
        return math.inf if night == 0.0 else self.usable_battery_wh() / night

    def recharge_margin(self) -> float:
        """Daytime surplus (after the day load) over the night's draw; < 1 drains daily."""

        surplus = self.daily_generation_wh() - self.continuous_load_w * self.sun_hours
        night = self.night_energy_wh()
        if night == 0.0:
            return math.inf
        return surplus * self.charge_efficiency / night

    def closes(self) -> bool:
        return self.battery_margin() >= 1.0 and self.recharge_margin() >= 1.0


# --------------------------------------------------------------------------
# Mass budget and regulatory thresholds
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MassItem:
    """One item in the payload-package mass budget."""

    name: str
    mass_kg_each: float
    quantity: int = 1

    @property
    def total_mass_kg(self) -> float:
        if self.mass_kg_each < 0:
            raise ValueError("mass must be non-negative")
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        return self.mass_kg_each * self.quantity


#: Program ceiling on the payload package: the allocation the sounding
#: article is designed against.  Deliberately well under the regulatory
#: threshold so the article is never engineered against its last gram.
PAYLOAD_PACKAGE_ALLOCATION_KG = 1.0

#: 14 CFR 101.1(a)(4) payload-package thresholds, in the regulation's own
#: units, above which an unmanned free balloon becomes subject to Subpart D.
#: The program takes the 4 lb single-package limb as its hard ceiling and
#: does not use the weight/size-ratio limb that would permit heavier
#: packages, because a lighter package is also a safer one.  Read the
#: regulation; this is the program's reading of it, and it applies only in
#: U.S. airspace — another jurisdiction is its own check.
POUND_KG = 0.45359237
REGULATORY_SINGLE_PACKAGE_LB = 4.0
REGULATORY_ANY_PACKAGE_LB = 6.0
REGULATORY_COMBINED_PACKAGES_LB = 12.0
REGULATORY_SEPARATION_FORCE_LBF = 50.0
REGULATORY_SINGLE_PACKAGE_KG = REGULATORY_SINGLE_PACKAGE_LB * POUND_KG


def baseline_strato_budget() -> tuple[MassItem, ...]:
    """Baseline payload-package allocation for the sounding article.

    Every figure is an engineering allocation to be replaced by a scale
    reading against the article identity; none is a vendor mass.
    """

    return (
        MassItem("imager module + lens allocation", 0.120),
        MassItem("flight computer + IMU + GNSS allocation", 0.060),
        MassItem("telemetry (primary radio + independent tracker) allocation", 0.090),
        MassItem("lithium primary battery allocation", 0.150),
        MassItem("enclosure + insulation allocation", 0.180),
        MassItem("parachute + rigging allocation", 0.120),
        MassItem("flight termination (cutdown) allocation", 0.040),
        MassItem("wiring + mounting reserve", 0.090),
    )


def payload_mass_kg(items: Iterable[MassItem]) -> float:
    return sum(item.total_mass_kg for item in items)


def payload_allocation_margin_kg(items: Iterable[MassItem]) -> float:
    return PAYLOAD_PACKAGE_ALLOCATION_KG - payload_mass_kg(items)


def regulatory_exemption_check(
    package_masses_kg: Iterable[float], *, separation_force_n: float
) -> tuple[str, ...]:
    """Reasons the configuration would fall under 14 CFR 101 Subpart D.

    An empty tuple means every package is under the program's reading of the
    exemption thresholds.  This is a check against the program's own limits;
    it is not legal advice and it does not replace coordinating the launch
    with the airspace authority.
    """

    masses = tuple(package_masses_kg)
    if not masses:
        raise ValueError("at least one package is required")
    if any(mass < 0.0 for mass in masses):
        raise ValueError("package masses must be non-negative")
    if separation_force_n < 0.0:
        raise ValueError("separation force must be non-negative")

    reasons: list[str] = []
    for index, mass in enumerate(masses):
        if mass > REGULATORY_SINGLE_PACKAGE_KG:
            reasons.append(
                f"package {index} is {mass:.3f} kg, over the program's "
                f"{REGULATORY_SINGLE_PACKAGE_LB:.0f} lb single-package ceiling"
            )
    if len(masses) >= 2 and sum(masses) > REGULATORY_COMBINED_PACKAGES_LB * POUND_KG:
        reasons.append(
            f"combined packages are {sum(masses):.3f} kg, over "
            f"{REGULATORY_COMBINED_PACKAGES_LB:.0f} lb"
        )
    if separation_force_n > REGULATORY_SEPARATION_FORCE_LBF * POUND_KG * G0_M_S2:
        reasons.append(
            f"suspension separates at {separation_force_n:.0f} N, over "
            f"{REGULATORY_SEPARATION_FORCE_LBF:.0f} lbf"
        )
    return tuple(reasons)


# --------------------------------------------------------------------------
# Program reference article
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StratoP0Targets:
    """Engineering targets the S0 gates evaluate against."""

    stratosphere_threshold_m: float = STRATOSPHERE_THRESHOLD_M
    min_burst_altitude_m: float = 25_000.0
    max_nadir_gsd_m_at_threshold: float = 3.0
    max_landing_rate_m_s: float = 5.0
    payload_package_allocation_kg: float = PAYLOAD_PACKAGE_ALLOCATION_KG
    payload_package_ceiling_kg: float = REGULATORY_SINGLE_PACKAGE_KG
    sounding_flight_hours: float = 3.0
    payload_load_w: float = 4.0


def _summary() -> dict[str, object]:
    targets = StratoP0Targets()
    balloon = SoundingBalloon()
    optic = Optic()
    items = baseline_strato_budget()
    threshold = targets.stratosphere_threshold_m
    at_threshold = standard_atmosphere(threshold)
    burst = balloon.burst_altitude_m()
    at_burst = standard_atmosphere(burst)
    landing_chute_m2 = canopy_area_for_landing_m2(
        payload_mass_kg(items), targets.max_landing_rate_m_s
    )
    float_reference_mass = 3.0
    swath = optic.swath_m(threshold)
    return {
        "targets": asdict(targets),
        "atmosphere": {
            "at_threshold": asdict(at_threshold),
            "at_threshold_temperature_c": round(at_threshold.temperature_c, 2),
            "at_burst_temperature_c": round(at_burst.temperature_c, 2),
        },
        "sounding": {
            **{k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(balloon).items()},
            "launch_volume_m3": round(balloon.launch_volume_m3(), 3),
            "gas_mass_kg": round(balloon.gas_mass_kg(), 4),
            "launch_ascent_rate_m_s": round(balloon.ascent_rate_at_m_s(0.0), 3),
            "burst_altitude_m": round(burst, 0),
            "time_to_burst_min": round(balloon.time_to_burst_s() / 60.0, 1),
            "ascent_minutes_above_threshold": round(
                balloon.time_above_stratosphere_threshold_s() / 60.0, 1
            ),
            "meets_min_burst_altitude": burst >= targets.min_burst_altitude_m,
        },
        "observation_at_threshold": {
            "horizon_distance_km": round(horizon_distance_m(threshold) / 1e3, 1),
            "horizon_ground_range_km": round(horizon_ground_range_m(threshold) / 1e3, 1),
            "visible_cap_area_km2": round(visible_cap_area_km2(threshold), 0),
            "optic": asdict(optic),
            "nadir_gsd_m": round(optic.nadir_gsd_m(threshold), 3),
            "gsd_at_45deg_m": round(optic.off_nadir_gsd_m(threshold, 45.0), 3),
            "frame_swath_km": [round(swath[0] / 1e3, 2), round(swath[1] / 1e3, 2)],
            "meets_gsd_target": optic.nadir_gsd_m(threshold) <= targets.max_nadir_gsd_m_at_threshold,
        },
        "descent": {
            "canopy_area_for_target_landing_m2": round(landing_chute_m2, 3),
            "landing_rate_with_that_canopy_m_s": round(
                parachute_descent_rate_m_s(payload_mass_kg(items), landing_chute_m2), 3
            ),
            "descent_rate_at_threshold_m_s": round(
                parachute_descent_rate_m_s(
                    payload_mass_kg(items), landing_chute_m2, altitude_m=threshold
                ),
                2,
            ),
        },
        "power": {
            "sounding_battery_wh": round(
                sounding_battery_wh(targets.payload_load_w, targets.sounding_flight_hours), 1
            ),
            "float_reference": {
                **asdict(FloatPowerBudget()),
                "daily_generation_wh": round(FloatPowerBudget().daily_generation_wh(), 1),
                "battery_margin": round(FloatPowerBudget().battery_margin(), 2),
                "recharge_margin": round(FloatPowerBudget().recharge_margin(), 2),
                "closes": FloatPowerBudget().closes(),
            },
        },
        "float_reference": {
            "gross_mass_kg": float_reference_mass,
            "envelope_volume_for_threshold_m3": round(
                envelope_volume_for_float_m3(float_reference_mass, threshold), 2
            ),
            "helium_mass_kg": round(
                gas_mass_kg(
                    envelope_volume_for_float_m3(float_reference_mass, threshold), threshold
                ),
                3,
            ),
        },
        "mass_budget": {
            "baseline_payload_package_kg": round(payload_mass_kg(items), 4),
            "allocation_margin_kg": round(payload_allocation_margin_kg(items), 4),
            "regulatory_ceiling_kg": round(REGULATORY_SINGLE_PACKAGE_KG, 4),
            "regulatory_findings": list(
                regulatory_exemption_check([payload_mass_kg(items)], separation_force_n=100.0)
            ),
            "items": [
                {**asdict(item), "total_mass_kg": round(item.total_mass_kg, 4)} for item in items
            ],
        },
    }


if __name__ == "__main__":
    print(json.dumps(_summary(), indent=2))
