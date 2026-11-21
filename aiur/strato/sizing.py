"""Mass and energy closure: turn a mission into a vehicle.

Two architectures are sized through the same budget so they can be compared
line for line:

``hull``
    One streamlined, pressure-stabilised film hull launched nearly empty
    ("flaccid launch", as HiSentinel flew it) with a stern propulsor,
    air-beam fins and the equipment strung along a spine.  The hull itself is
    the air frame: internal pressure, not a keel, carries bending.

``tandem``
    Two COTS latex sounding balloons on a boom with propellers between them -
    the JP Aerospace *Tandem* layout.  No custom envelope at all, so it is
    the cheapest thing that can be called a powered stratospheric airship,
    and it pays for that in drag.

The closure is the classic one: lift grows with volume, envelope mass with
volume^(2/3), so there is a minimum size below which nothing closes, and that
size depends brutally on film areal density and float density.  ``size_*``
finds the smallest volume at which lift equals the sum of everything else,
with propulsion and energy re-derived at every trial volume.

Run ``python -m aiur.strato.sizing`` for the design ladder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import sys

from .atmosphere import G0, WindProfile, isa
from .energy import (ARRAYS, CELLS, Pack, array_power_w_per_m2,
                     daily_array_energy_wh_per_m2, pack_for_energy)
from .gas import GASES
from .hull import Hull, sphere_drag_coefficient
from .materials import FILMS, LATEX, Tube
from .propulsion import ESC_EFFICIENCY, MOTORS, Propeller
from .thermal import (FilmOptics, RadiativeEnvironment, bay_heater_power_w,
                      equilibrium_supertemperature_k)


@dataclass(frozen=True)
class Mission:
    """What the vehicle has to do.  Everything else is derived."""

    name: str
    float_altitude_m: float = 20_000.0
    payload_kg: float = 1.0
    payload_w: float = 5.0
    #: Airspeed the energy system sustains for the whole powered phase.
    cruise_airspeed_m_s: float = 6.0
    #: Airspeed the propulsion can reach on battery for short periods.
    dash_airspeed_m_s: float = 10.0
    #: "battery" (powered hours on stored energy), "solar-day" (array carries
    #: the day, small buffer), or "diurnal" (array + battery through the night).
    energy_mode: str = "battery"
    powered_hours: float = 2.0
    night_airspeed_m_s: float = 3.0
    latitude_deg: float = 50.0
    day_of_year: int = 172
    gas: str = "hydrogen"
    #: Launch free lift as a fraction of gross mass.
    #: 0.45 not the textbook 0.10-0.15: a small vehicle climbs as mass^(1/6), and
    #: the Monte Carlo loses a quarter of summer flights to jet-stream drift at
    #: 15 %. Hydrogen is cents; range is the mission.
    free_lift_fraction: float = 0.45
    recoverable: bool = True
    dry_margin: float = 0.10


@dataclass(frozen=True)
class Avionics:
    """Fixed equipment; kept equal to hardware/strato/avionics/components.csv
    by ``python -m aiur.strato.harness --check-budget``."""

    mass_kg: float = 0.31
    power_w: float = 6.1
    bay_area_m2: float = 0.22
    bay_insulation_m: float = 0.025
    bay_mass_kg: float = 0.14
    bay_target_c: float = 5.0


@dataclass
class DesignPoint:
    architecture: str
    mission: dict
    closed: bool
    reason: str = ""
    geometry: dict = field(default_factory=dict)
    mass_kg: dict = field(default_factory=dict)
    lift: dict = field(default_factory=dict)
    propulsion: dict = field(default_factory=dict)
    energy: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    stability: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)

    @property
    def gross_kg(self) -> float:
        return self.mass_kg.get("gross", float("nan"))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


#: Droppable trim ballast as a fraction of gross mass [estimate from the
#: ascent model: forced-convection cooling at cruise costs ~1 % of lift].
TRIM_BALLAST_FRACTION = 0.03


# --- shared pieces -----------------------------------------------------------

def _propulsion(air, drag_dash_n: float, dash: float, drag_cruise_n: float,
                cruise: float, n_props: int, prop_diameter_m: float, bus_v: float) -> dict:
    """Pick motors for the dash point and report the cruise operating point."""

    prop = Propeller(prop_diameter_m)
    dash_op = prop.operating_point(air, drag_dash_n / n_props, dash)
    cruise_op = prop.operating_point(air, max(drag_cruise_n, 1e-3) / n_props, cruise)
    chosen = None
    for key in sorted(MOTORS, key=lambda k: MOTORS[k].mass_kg):
        m = MOTORS[key]
        e_dash = m.electrical(dash_op["rpm"], dash_op["torque_nm"], bus_v)
        e_cruise = m.electrical(cruise_op["rpm"], cruise_op["torque_nm"], bus_v)
        # Dash is short: allow 2x the continuous altitude heat limit there.
        ok = (e_dash["feasible"] and e_cruise["feasible"]
              and e_cruise["loss_w"] <= m.dissipation_limit_w(air)
              and e_dash["loss_w"] <= 2.0 * m.dissipation_limit_w(air))
        if ok:
            chosen = (key, m, e_dash, e_cruise)
            break
    flags = []
    if chosen is None:
        key = "8108-100kv"
        m = MOTORS[key]
        chosen = (key, m, m.electrical(dash_op["rpm"], dash_op["torque_nm"], bus_v),
                  m.electrical(cruise_op["rpm"], cruise_op["torque_nm"], bus_v))
        flags.append("no catalogue motor meets dash point within bus voltage/thermal limit")
    key, m, e_dash, e_cruise = chosen
    if dash_op["tip_mach"] > 0.7:
        flags.append(f"propeller tip Mach {dash_op['tip_mach']:.2f} at dash")
    # Propeller mass: thin carbon/foam blade, scales with D^2.5 [estimate
    # anchored on 30 in carbon multirotor props at ~0.09 kg].
    prop_mass = 0.18 * prop_diameter_m**2.5
    esc_mass = 0.035
    mount_mass = 0.12 + 0.05 * prop_diameter_m
    return {
        "n_props": n_props, "prop_diameter_m": prop_diameter_m, "motor": key,
        "dash": dash_op, "cruise": cruise_op,
        "dash_electrical_w": n_props * e_dash["input_w"] / ESC_EFFICIENCY,
        "cruise_electrical_w": n_props * e_cruise["input_w"] / ESC_EFFICIENCY,
        "motor_efficiency_cruise": e_cruise["efficiency"],
        "motor_loss_cruise_w": e_cruise["loss_w"],
        "motor_heat_limit_w": m.dissipation_limit_w(air),
        "mass_kg": n_props * (m.mass_kg + prop_mass + esc_mass + mount_mass),
        "usd": n_props * (m.usd + 45.0 * prop_diameter_m**2 + 25.0 + 30.0),
        "flags": flags,
    }


def _energy(mission: Mission, av: Avionics, air, cruise_w: float, dash_w: float,
            night_propulsion_w: float, series: int, array_key: str,
            cell_key: str) -> dict:
    heater = bay_heater_power_w(av.power_w, 273.15 + av.bay_target_c,
                                air.temperature_k, av.bay_area_m2, av.bay_insulation_m)
    hotel_w = av.power_w + mission.payload_w + heater
    day_w = cruise_w + hotel_w
    cell = CELLS[cell_key]
    array = ARRAYS[array_key]
    ascent_wh = 3.0 * hotel_w  # ~3 h launch-to-float on hotel load
    dash_wh = 0.25 * max(0.0, dash_w - cruise_w)  # 15 min of dash in reserve
    out = {"hotel_w": hotel_w, "heater_w": heater, "day_load_w": day_w,
           "array_m2": 0.0, "array_kg": 0.0, "array_usd": 0.0}
    if mission.energy_mode == "battery":
        need = day_w * mission.powered_hours + ascent_wh + dash_wh
    else:
        per_m2, lit_h = daily_array_energy_wh_per_m2(
            array, mission.float_altitude_m, mission.latitude_deg, mission.day_of_year)
        out["array_wh_per_m2_day"] = per_m2
        out["lit_hours"] = lit_h
        if mission.energy_mode == "solar-day":
            # Array carries the load across the usable day; battery buffers.
            usable_h = max(lit_h - 3.0, 1.0)
            area = day_w * usable_h / (per_m2 * 0.85)
            need = ascent_wh + dash_wh + 1.0 * day_w
        elif mission.energy_mode == "diurnal":
            night_h = 24.0 - lit_h + 1.5
            night_w = night_propulsion_w + hotel_w
            night_wh = night_w * night_h
            area = (day_w * (24.0 - night_h) + night_wh / 0.92) / (per_m2 * 0.85)
            need = night_wh + dash_wh
            out["night_load_w"] = night_w
            out["night_hours"] = night_h
        else:
            raise ValueError(f"unknown energy mode {mission.energy_mode!r}")
        out["array_m2"] = area
        out["array_kg"] = area * array.areal_density_kg_m2 + 0.05
        out["array_usd"] = area * array.usd_per_m2
    pack = pack_for_energy(cell, series, need)
    out.update({
        "battery_need_wh": need, "pack": f"{pack.series}S{pack.parallel}P {cell.name}",
        "pack_cells": pack.cells, "pack_kg": pack.mass_kg,
        "pack_usable_wh": pack.usable_wh(), "pack_usd": pack.usd,
        "bus_v": pack.nominal_v,
    })
    return out


def air_beam(moment_nm: float, length_m: float, fabric_ultimate_n_per_m: float = 9000.0,
             fabric_kg_m2: float = 0.070, safety: float = 4.0,
             wrinkle_margin: float = 1.5) -> dict:
    """Lightest inflated fabric tube that carries a bending moment unwrinkled.

    Wrinkling moment of a pressurised tube is M = pi p r^3 / 2 and hoop load
    is p r [physics].  Working the fabric at its allowable hoop load,
    p r = N_allow, gives r = sqrt(2 M / (pi N_allow)): the radius is set by
    the moment and the fabric, and the pressure follows.  A fatter, softer
    tube is always lighter per unit moment - the limit of that argument is
    the hull itself, which is why the hull is the primary structure here and
    beams are used only where there is no hull to lean on (fins, booms).
    """

    n_allow = fabric_ultimate_n_per_m / safety
    m = moment_nm * wrinkle_margin
    r = math.sqrt(2.0 * m / (math.pi * n_allow))
    p = n_allow / r
    mass = 2.0 * math.pi * r * length_m * fabric_kg_m2 * 1.10 + 2 * math.pi * r * r * fabric_kg_m2
    return {"radius_m": r, "gauge_pressure_pa": p, "mass_kg": mass,
            "ei_nm2": 0.0, "kind": "air-beam"}


_TUBE_CATALOGUE = [(0.012, 0.001), (0.016, 0.001), (0.020, 0.001), (0.025, 0.001),
                   (0.030, 0.001), (0.030, 0.0015), (0.040, 0.0015), (0.050, 0.002),
                   (0.060, 0.002), (0.080, 0.002)]


def carbon_boom(moment_nm: float, length_m: float, safety: float = 2.0) -> dict:
    for od, wall in _TUBE_CATALOGUE:
        t = Tube(od, wall)
        if t.allowable_moment_nm >= moment_nm * safety:
            return {"od_m": od, "wall_m": wall, "mass_kg": t.mass_per_m * length_m * 1.08,
                    "ei_nm2": t.ei_nm2, "kind": "carbon tube",
                    "usd": t.usd_per_m * length_m * (od / 0.025)}
    t = Tube(0.08, 0.002)
    return {"od_m": 0.08, "wall_m": 0.002, "mass_kg": t.mass_per_m * length_m * 1.08,
            "ei_nm2": t.ei_nm2, "kind": "carbon tube (catalogue exceeded)",
            "usd": t.usd_per_m * length_m * 3.2}


def sealed_beam_pressure_at_altitude(gauge_ground_pa: float, altitude_m: float,
                                     ground_temp_k: float = 288.15) -> float:
    """Gauge pressure of a beam sealed on the ground, once at altitude.

    The ambient falls away faster than the sealed gas cools, so a sealed
    air-beam gets *stiffer* as it climbs [physics].  This is the property that
    makes inflated fins attractive for a flaccid-launch vehicle: they are
    soft and packable on the ground and rigid by the time they are needed.
    It is also why they need a relief valve.
    """

    a = isa(altitude_m)
    absolute = (101_325.0 + gauge_ground_pa) * a.temperature_k / ground_temp_k
    return absolute - a.pressure_pa


# --- hull architecture -------------------------------------------------------

#: A flat-gored film hull is a polygon in section, not a circle: 12 gores
#: enclose 2.2 % less than the smooth hull.  Widening each gore by 1.1 %
#: recovers it; the budget carries that film.  [patterns.py lobing table]
LOBING_FILM_FACTOR = 1.011
#: UHMWPE tendon: specific strength (N m / kg) and a working safety factor.
TENDON_SPECIFIC_STRENGTH = 3.0e9 / 970.0
TENDON_SAFETY = 5.0


def _hull_budget(volume: float, mission: Mission, film_key: str, fineness: float,
                 av: Avionics, fin_ratio: float, n_props: int, superpressure: bool,
                 array_key: str, cell_key: str, series: int, netted: bool = False) -> DesignPoint:
    air = isa(mission.float_altitude_m)
    gas = GASES[mission.gas]
    film = FILMS[film_key]
    hull = Hull(volume, fineness)
    optics = FilmOptics(film.solar_absorptance, film.ir_emittance)
    dp = DesignPoint("hull", asdict(mission), closed=False)
    flags = dp.flags

    # --- drag and propulsion
    length, radius = hull.length_m, hull.radius_m
    # Fins, spine pods, rigging and film wrinkles: published sizing studies
    # take total drag as 1.8x hull-alone [cited: ICAS 2016-0703]; a slack
    # film hull with inflated fins earns no better.
    extra_cda = 0.8 * hull.drag_coefficient(1e6) * hull.reference_area_m2 + 0.03
    drag = lambda v: hull.drag_n(air.density_kg_m3, v, air.viscosity_pa_s, extra_cda)
    prop_d = max(0.6, min(1.8, 0.05 * length))
    bus_v = series * 3.6
    prop = _propulsion(air, drag(mission.dash_airspeed_m_s), mission.dash_airspeed_m_s,
                       drag(mission.cruise_airspeed_m_s), mission.cruise_airspeed_m_s,
                       n_props, prop_d, bus_v)
    flags.extend(prop["flags"])
    night_prop = _propulsion(air, drag(mission.dash_airspeed_m_s), mission.dash_airspeed_m_s,
                             drag(mission.night_airspeed_m_s), mission.night_airspeed_m_s,
                             n_props, prop_d, bus_v)["cruise_electrical_w"]
    energy = _energy(mission, av, air, prop["cruise_electrical_w"],
                     prop["dash_electrical_w"], night_prop, series, array_key, cell_key)

    # --- thermal excursion and required envelope pressure
    day_dt = equilibrium_supertemperature_k(air, optics, length, mission.cruise_airspeed_m_s, 60.0)
    night_env = RadiativeEnvironment(earth_ir_w_m2=150.0, sky_ir_w_m2=10.0)
    night_dt = equilibrium_supertemperature_k(air, optics, length, mission.night_airspeed_m_s,
                                              -30.0, env=night_env)
    q_dash = air.dynamic_pressure_pa(mission.dash_airspeed_m_s)
    dp_min = max(20.0, 3.0 * q_dash)
    if superpressure:
        dp_design = dp_min + air.pressure_pa * (day_dt - night_dt) / air.temperature_k
    else:
        dp_design = dp_min
    gas_head = (air.density_kg_m3 - gas.density(air.pressure_pa, air.temperature_k)) * G0 * 2 * radius
    hoop = (dp_design + gas_head) * radius
    net = {}
    m_net = 0.0
    if netted:
        # Tendon-netted hull, the airship form of a pumpkin balloon: a mesh of
        # UHMWPE tendons carries the pressure load and the film only spans
        # between tendons, bulging to a radius about equal to the mesh pitch.
        # Film stress then depends on the pitch, not on the hull radius, so
        # cheap film can hold superpressure it could never hold as a monolith.
        pitch = min(radius, max(0.08, film.allowable_n_per_m / (dp_design + gas_head)))
        area0 = hull.surface_area_m2
        # Hoop rings carry p*R per metre of length, meridional tendons p*R/2
        # per metre of girth: total load-length is 1.5 p R * area.  [physics]
        load_length = 1.5 * (dp_design + gas_head) * radius * area0
        m_tendon = load_length * TENDON_SAFETY / TENDON_SPECIFIC_STRENGTH
        tendon_m = 2.0 * area0 / pitch
        # Sleeve tape that bonds each tendon to the film: 1.2 g per metre.
        m_net = 1.6 * m_tendon + 0.0012 * tendon_m
        plies = 1.0
        net = {"mesh_pitch_m": pitch, "tendon_length_m": tendon_m, "tendon_kg": m_tendon,
               "net_kg": m_net, "film_bulge_load_n_per_m": (dp_design + gas_head) * pitch}
    else:
        plies = max(1.0, hoop / film.allowable_n_per_m)
    if plies > 1.0 and not superpressure:
        flags.append("film hoop load exceeds allowable even at relief pressure")

    # --- masses
    area = hull.surface_area_m2
    m_film = film.areal_density_kg_m2 * plies * area * LOBING_FILM_FACTOR \
        * (1.04 if netted else 1.0)  # bulged panels are longer than their chord
    m_seams = 0.10 * m_film + 0.004 * area  # seam overlap, tapes, load patches
    m_fittings = 0.30 + 0.0015 * area       # relief/vent valve, fill port, nose cap
    fin_area = fin_ratio * hull.reference_area_m2
    # Film skin + air-beam spars + valves.  0.115 kg/m2 is from the cut
    # patterns with spars filled to 10 kPa on the ground; the first guess of
    # 0.085 was 40 % light, because spar diameter is set by wrinkling under
    # launch loads, not by fabric strength.  [patterns.py]
    m_fins = 0.115 * fin_area + 0.20
    m_spine = 0.018 * length + 0.10         # UHMWPE webbing spine + load lines
    m_term = (0.04 if mission.recoverable else 0.0)  # filled in below
    lift_per_m3 = gas.lift_per_m3(air, superpressure_pa=dp_min)
    lift = volume * lift_per_m3

    masses = {
        "envelope_film": m_film, "seams_patches": m_seams, "fittings_valves": m_fittings,
        "fins": m_fins, "spine_rigging": m_spine, "tendon_net": m_net,
        "propulsion": prop["mass_kg"], "battery": energy["pack_kg"],
        "solar_array": energy["array_kg"],
        "avionics": av.mass_kg, "avionics_bay": av.bay_mass_kg,
        "harness": 0.0, "payload": mission.payload_kg,
    }
    masses["harness"] = 0.06 * (masses["propulsion"] + masses["battery"] + masses["avionics"]) \
        + 0.004 * length
    sub = sum(masses.values())
    # Recovery: parachute for the suspended equipment (not the film), 6 m/s.
    if mission.recoverable:
        suspended = sub - m_film - m_seams
        masses["recovery"] = 0.035 * suspended + 0.08
    else:
        masses["recovery"] = 0.03
    # Ballast for a zero-pressure hull that must survive the night.
    if mission.energy_mode == "diurnal" and not superpressure:
        frac = max(0.0, (day_dt - night_dt)) / air.temperature_k
        masses["ballast"] = frac * (sum(masses.values())) * 1.15
    else:
        # Trim ballast: a slack cell has no altitude stiffness, so every
        # vehicle carries a little to arrest a sink (ascent model finding).
        masses["ballast"] = TRIM_BALLAST_FRACTION * sum(masses.values())
    dry = sum(masses.values()) - mission.payload_kg
    masses["margin"] = mission.dry_margin * dry
    gross_no_gas = sum(masses.values())
    # The gas itself is carried: lift_per_m3 is already net of gas mass.
    masses["gross"] = gross_no_gas
    dp.mass_kg = {k: round(v, 4) for k, v in masses.items()}
    dp.lift = {
        "net_lift_kg": lift, "lift_per_m3": lift_per_m3,
        "margin_kg": lift - gross_no_gas,
        "gas_mass_kg": volume * gas.density(air.pressure_pa + dp_min, air.temperature_k),
    }
    dp.geometry = {
        "volume_m3": volume, "length_m": length, "diameter_m": 2 * radius,
        "fineness": fineness, "surface_area_m2": area, "fin_area_total_m2": fin_area,
        "film": film.name, "film_plies_equiv": plies,
    }
    dp.propulsion = {k: v for k, v in prop.items() if k != "flags"}
    dp.propulsion["drag_dash_n"] = drag(mission.dash_airspeed_m_s)
    dp.propulsion["drag_cruise_n"] = drag(mission.cruise_airspeed_m_s)
    dp.propulsion["reynolds_cruise"] = (air.density_kg_m3 * mission.cruise_airspeed_m_s
                                        * length / air.viscosity_pa_s)
    dp.propulsion["cdv_cruise"] = hull.drag_coefficient(dp.propulsion["reynolds_cruise"])
    dp.energy = energy
    wrinkle_moment = math.pi * dp_min * radius**3 / 2.0
    suspended_n = (gross_no_gas - m_film - m_seams) * G0
    dp.structure = {
        "relief_pressure_pa": dp_min, "design_pressure_pa": dp_design,
        "hoop_load_n_per_m": hoop, "film_allowable_n_per_m": film.allowable_n_per_m,
        "hull_wrinkle_moment_nm": wrinkle_moment,
        "distributed_bending_nm": suspended_n * length / 32.0,
        "day_supertemp_k": day_dt, "night_supertemp_k": night_dt,
        "superpressure": superpressure, "net": net,
    }
    if dp.structure["distributed_bending_nm"] > wrinkle_moment:
        flags.append("hull wrinkles under suspended load at relief pressure: raise pressure or spread load")
    dp.stability = _hull_stability(hull, air, gross_no_gas + dp.lift["gas_mass_kg"],
                                   mission.cruise_airspeed_m_s, fin_area,
                                   prop["dash"]["thrust_n"] * n_props)
    return dp


def _hull_stability(hull: Hull, air, mass_kg: float, airspeed: float, fin_area: float,
                    max_thrust_n: float) -> dict:
    """Yaw-plane static derivatives at cruise: who wins, Munk or the fins."""

    k1, k2, kp = hull.lamb_factors()
    q = air.dynamic_pressure_pa(airspeed)
    munk = (k2 - k1) * 2.0 * q * hull.volume_m3              # N m / rad, destabilising
    tail_arm = hull.length_m * 0.86 - hull.centre_of_volume_m
    fin_cla = 2.2  # per rad on fin pair area, incl. hull carry-over 0.6 [estimate]
    fin = q * 0.5 * fin_area * fin_cla * tail_arm              # one pair acts in yaw
    # Hull viscous crossflow lift acts aft of the CV [Allen-Perkins], small at
    # small sideslip; linearised contribution ~ 0.15 of Munk [estimate].
    hull_visc = 0.15 * munk
    n_beta = munk - fin - hull_visc
    m_disp = air.density_kg_m3 * hull.volume_m3
    izz = (mass_kg + kp * m_disp) * hull.displaced_inertia_coeff()
    vector_moment = max_thrust_n * math.sin(math.radians(25.0)) * (hull.length_m - hull.centre_of_volume_m)
    out = {
        "munk_nm_per_rad": munk, "fin_nm_per_rad": fin, "n_beta_nm_per_rad": n_beta,
        "static_stability_ratio": (fin + hull_visc) / munk if munk else float("inf"),
        "yaw_inertia_kg_m2": izz,
        "thrust_vector_moment_nm": vector_moment,
        "controllable_sideslip_deg": (math.degrees(vector_moment / n_beta)
                                      if n_beta > 0 else float("inf")),
        "divergence_time_s": math.sqrt(izz / n_beta) if n_beta > 0 else float("inf"),
        "lamb_k1": k1, "lamb_k2": k2, "lamb_kprime": kp, "tail_arm_m": tail_arm,
    }
    return out


def size_hull(mission: Mission, film_key: str = "lldpe-20um", fineness: float = 4.0,
              av: Avionics = Avionics(), fin_ratio: float = 0.50, n_props: int = 1,
              superpressure: bool = False, array_key: str = "mono-si-laminate",
              cell_key: str = "21700-5.0Ah", series: int = 6,
              volume_limit_m3: float = 200_000.0, netted: bool = False) -> DesignPoint:
    """Smallest hull whose lift carries its own budget."""

    def margin(v: float) -> float:
        return _hull_budget(v, mission, film_key, fineness, av, fin_ratio, n_props,
                            superpressure, array_key, cell_key, series, netted).lift["margin_kg"]

    lo, hi = 2.0, volume_limit_m3
    if margin(hi) < 0.0:
        dp = _hull_budget(hi, mission, film_key, fineness, av, fin_ratio, n_props,
                          superpressure, array_key, cell_key, series, netted)
        dp.reason = f"no closure below {volume_limit_m3:.0f} m3"
        return dp
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if margin(mid) >= 0.0:
            hi = mid
        else:
            lo = mid
    dp = _hull_budget(hi, mission, film_key, fineness, av, fin_ratio, n_props,
                      superpressure, array_key, cell_key, series, netted)
    dp.closed = True
    _launch(dp, mission)
    return dp


def _launch(dp: DesignPoint, mission: Mission) -> None:
    gas = GASES[mission.gas]
    ground = isa(0.0)
    gross = dp.mass_kg["gross"]
    lift_needed = gross * (1.0 + mission.free_lift_fraction)
    v_ground = lift_needed / gas.lift_per_m3(ground)
    dp.lift.update({
        "launch_gas_nm3": v_ground,
        "launch_fill_fraction": v_ground / dp.geometry["volume_m3"],
        "launch_gas_usd": v_ground * gas.usd_per_nm3,
        "free_lift_n": gross * mission.free_lift_fraction * G0,
    })


# --- tandem architecture -----------------------------------------------------

def size_tandem(mission: Mission, balloon_key: str = "1600g", av: Avionics = Avionics(),
                n_props: int = 2, boom: str = "carbon", cell_key: str = "21700-5.0Ah",
                series: int = 6, array_key: str = "mono-si-laminate") -> DesignPoint:
    """Two latex cells on a boom.  Fixed-point on gross mass."""

    air = isa(mission.float_altitude_m)
    gas = GASES[mission.gas]
    balloon = LATEX[balloon_key]
    dp = DesignPoint("tandem", asdict(mission), closed=False)
    gross = 6.0
    masses: dict = {}
    for _ in range(80):
        lift_per_m3 = gas.lift_per_m3(air, superpressure_pa=balloon.skin_pressure_pa)
        cell_volume = gross / (2.0 * lift_per_m3)
        cell_d = (6.0 * cell_volume / math.pi) ** (1.0 / 3.0)
        boom_len = 1.12 * cell_d + 1.2
        # Drag: two spheres through the drag crisis, plus boom and gondola.
        def drag(v: float) -> float:
            re = air.density_kg_m3 * v * cell_d / air.viscosity_pa_s
            cda = 2.0 * sphere_drag_coefficient(re) * math.pi * cell_d**2 / 4.0
            cda += 1.1 * boom_len * 0.03 + 0.05
            return air.dynamic_pressure_pa(v) * cda
        prop_d = max(0.5, min(1.4, 0.12 * boom_len))
        prop = _propulsion(air, drag(mission.dash_airspeed_m_s), mission.dash_airspeed_m_s,
                           drag(mission.cruise_airspeed_m_s), mission.cruise_airspeed_m_s,
                           n_props, prop_d, series * 3.6)
        night_prop = _propulsion(air, drag(mission.dash_airspeed_m_s), mission.dash_airspeed_m_s,
                                 drag(mission.night_airspeed_m_s), mission.night_airspeed_m_s,
                                 n_props, prop_d, series * 3.6)["cruise_electrical_w"]
        energy = _energy(mission, av, air, prop["cruise_electrical_w"],
                         prop["dash_electrical_w"], night_prop, series, array_key, cell_key)
        central = (prop["mass_kg"] + energy["pack_kg"] + av.mass_kg + av.bay_mass_kg
                   + mission.payload_kg + energy["array_kg"])
        moment = central * G0 * boom_len / 4.0
        beam = carbon_boom(moment, boom_len) if boom == "carbon" else air_beam(moment, boom_len)
        masses = {
            "latex_cells": 2 * balloon.mass_kg, "neck_valves": 2 * 0.11,
            "boom": beam["mass_kg"], "rigging": 0.15,
            "propulsion": prop["mass_kg"], "battery": energy["pack_kg"],
            "solar_array": energy["array_kg"], "avionics": av.mass_kg,
            "avionics_bay": av.bay_mass_kg, "payload": mission.payload_kg,
        }
        masses["harness"] = 0.06 * (masses["propulsion"] + masses["battery"]
                                    + masses["avionics"]) + 0.006 * boom_len
        masses["recovery"] = 0.035 * (sum(masses.values()) - masses["latex_cells"]) + 0.08
        masses["ballast"] = TRIM_BALLAST_FRACTION * sum(masses.values())
        dry = sum(masses.values()) - mission.payload_kg
        masses["margin"] = mission.dry_margin * dry
        new = sum(masses.values())
        if abs(new - gross) < 1e-5:
            gross = new
            break
        gross = 0.5 * (gross + new)
    masses["gross"] = gross
    dp.mass_kg = {k: round(v, 4) for k, v in masses.items()}
    dp.geometry = {"cell_diameter_m": cell_d, "cell_volume_m3": cell_volume,
                   "boom_length_m": boom_len, "balloon": balloon.name,
                   "burst_diameter_m": balloon.burst_diameter_m,
                   "diameter_fraction_of_burst": cell_d / balloon.burst_diameter_m,
                   "volume_m3": 2 * cell_volume}
    dp.lift = {"net_lift_kg": gross, "lift_per_m3": lift_per_m3, "margin_kg": 0.0,
               "gas_mass_kg": 2 * cell_volume * gas.density(air.pressure_pa, air.temperature_k)}
    dp.propulsion = {k: v for k, v in prop.items() if k != "flags"}
    dp.propulsion["drag_dash_n"] = drag(mission.dash_airspeed_m_s)
    dp.propulsion["drag_cruise_n"] = drag(mission.cruise_airspeed_m_s)
    dp.energy = energy
    dp.structure = {"boom": beam, "boom_moment_nm": moment}
    dp.flags.extend(prop["flags"])
    dp.closed = cell_d <= 0.80 * balloon.burst_diameter_m
    if not dp.closed:
        dp.reason = (f"cells at {cell_d:.1f} m are within 20 % of the "
                     f"{balloon.burst_diameter_m:.1f} m burst diameter at float")
    _launch(dp, mission)
    return dp


# --- availability ------------------------------------------------------------

def station_keeping_availability(sustained_airspeed_m_s: float, altitude_m: float) -> dict:
    """Which climatological cases the vehicle can hold station in."""

    out = {}
    for name in ("midlat-summer-p50", "midlat-summer-p90", "midlat-turnaround-p50",
                 "midlat-winter-p50", "midlat-winter-p90"):
        w = WindProfile(name).speed(altitude_m)
        out[name] = {"wind_m_s": round(w, 1), "holds": sustained_airspeed_m_s >= w}
    return out


# --- the ladder --------------------------------------------------------------

MISSIONS = {
    # SP1: the low-altitude trainer.  Reusable ripstop, helium, flown at a
    # few tens of metres to learn ground handling, inflation and control
    # before anything is sent to the stratosphere.
    "SP1-trainer": Mission("SP1-trainer", 150.0, payload_kg=0.3, payload_w=2.0,
                           cruise_airspeed_m_s=3.0, dash_airspeed_m_s=6.0,
                           energy_mode="battery", powered_hours=0.75, gas="helium",
                           free_lift_fraction=0.02, recoverable=False),
    # S1: the cheapest thing that is honestly a powered airship in the
    # stratosphere.  One hour of powered, controlled flight at float.
    "S1-touch": Mission("S1-touch", 20_000.0, payload_kg=0.5, payload_w=3.0,
                        cruise_airspeed_m_s=3.0, dash_airspeed_m_s=5.0,
                        energy_mode="battery", powered_hours=1.0),
    # S2: a real hull.  All daylight at float, holding the summer median wind.
    "S2-dayloiter": Mission("S2-dayloiter", 20_000.0, payload_kg=2.0, payload_w=10.0,
                            cruise_airspeed_m_s=6.0, dash_airspeed_m_s=10.0,
                            energy_mode="solar-day"),
    # S3: through the night.  This is where "persistent" starts.
    "S3-diurnal": Mission("S3-diurnal", 20_000.0, payload_kg=3.0, payload_w=15.0,
                          cruise_airspeed_m_s=7.0, dash_airspeed_m_s=12.0,
                          night_airspeed_m_s=4.0, energy_mode="diurnal"),
    # S4: the carrier.  Payload includes release-only aircraft and relay radios.
    "S4-carrier": Mission("S4-carrier", 20_000.0, payload_kg=10.0, payload_w=40.0,
                          cruise_airspeed_m_s=8.0, dash_airspeed_m_s=14.0,
                          night_airspeed_m_s=5.0, energy_mode="diurnal"),
}


def ladder() -> dict:
    out = {}
    out["SP1-trainer/hull"] = size_hull(MISSIONS["SP1-trainer"], "nylon-tpu-70gsm")
    out["S1-touch/tandem"] = size_tandem(MISSIONS["S1-touch"], "1600g")
    out["S1-touch/hull"] = size_hull(MISSIONS["S1-touch"], "lldpe-20um")
    out["S2-dayloiter/hull"] = size_hull(MISSIONS["S2-dayloiter"], "lldpe-20um")
    out["S3-diurnal/hull-zp-ballast"] = size_hull(MISSIONS["S3-diurnal"], "lldpe-38um")
    out["S3-diurnal/hull-superpressure"] = size_hull(MISSIONS["S3-diurnal"], "dcf-18gsm",
                                                     superpressure=True)
    out["S3-diurnal/hull-netted"] = size_hull(MISSIONS["S3-diurnal"], "lldpe-20um",
                                              superpressure=True, netted=True)
    out["S4-carrier/hull-superpressure"] = size_hull(MISSIONS["S4-carrier"], "dcf-34gsm",
                                                     superpressure=True)
    return out


def summarise(name: str, dp: DesignPoint) -> str:
    g = dp.geometry
    lines = [f"=== {name}  [{'CLOSED' if dp.closed else 'NOT CLOSED: ' + dp.reason}]"]
    if dp.architecture == "hull":
        lines.append(f"  hull {g['length_m']:.1f} m x {g['diameter_m']:.1f} m, "
                     f"{g['volume_m3']:.0f} m3, {g['surface_area_m2']:.0f} m2 of {g['film']}"
                     f" (x{g['film_plies_equiv']:.2f})")
    else:
        lines.append(f"  2 x {g['balloon']} at {g['cell_diameter_m']:.1f} m "
                     f"({100*g['diameter_fraction_of_burst']:.0f} % of burst), "
                     f"boom {g['boom_length_m']:.1f} m")
    m = dp.mass_kg
    lines.append(f"  gross {m['gross']:.2f} kg: " + ", ".join(
        f"{k} {v:.2f}" for k, v in m.items() if k != "gross" and v > 0.005))
    p, e = dp.propulsion, dp.energy
    lines.append(f"  propulsion {p['n_props']} x {p['prop_diameter_m']:.2f} m on {p['motor']}: "
                 f"cruise {p['cruise']['airspeed_m_s']:.0f} m/s {p['cruise_electrical_w']:.0f} W "
                 f"(eta {p['cruise']['efficiency']:.2f}, {p['cruise']['rpm']:.0f} rpm), "
                 f"dash {p['dash']['airspeed_m_s']:.0f} m/s {p['dash_electrical_w']:.0f} W")
    lines.append(f"  energy: hotel {e['hotel_w']:.1f} W (heater {e['heater_w']:.1f}), "
                 f"{e['pack']} {e['pack_kg']:.2f} kg / {e['pack_usable_wh']:.0f} Wh, "
                 f"array {e['array_m2']:.2f} m2")
    if "launch_gas_nm3" in dp.lift:
        lines.append(f"  launch: {dp.lift['launch_gas_nm3']:.1f} Nm3 "
                     f"({100*dp.lift['launch_fill_fraction']:.1f} % full), "
                     f"gas ${dp.lift['launch_gas_usd']:.0f}")
    if dp.stability:
        s = dp.stability
        lines.append(f"  yaw: fins+hull cancel {100*s['static_stability_ratio']:.0f} % of Munk, "
                     f"divergence {s['divergence_time_s']:.1f} s, vector trims "
                     f"{s['controllable_sideslip_deg']:.1f} deg sideslip")
    for f in dp.flags:
        lines.append(f"  ! {f}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    points = ladder()
    if "--json" in argv:
        print(json.dumps({k: asdict(v) for k, v in points.items()}, indent=2, sort_keys=True))
        return 0
    for name, dp in points.items():
        print(summarise(name, dp))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
