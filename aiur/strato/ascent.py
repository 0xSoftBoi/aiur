"""Launch-to-landing trajectory of a buoyant vehicle.

One vertical degree of freedom plus wind drift, with the gas treated
thermodynamically: it expands and cools as the vehicle climbs, exchanges heat
with a film that sees the sun and the Earth, vents when the cell fills, and
loses lift when it cools.  That is the minimum physics that reproduces what
real balloon flights do - the float overshoot, the sunset descent, the burst
of a cell that was never vented - and it is what the float controller in
``guidance`` has to cope with.

Three cell types:

``zero-pressure``  open duct; excess gas spills when full (thin film hulls)
``superpressure``  sealed with a relief valve; holds gas and altitude overnight
``latex``          elastic; never fills, climbs until vented or burst

Run ``python -m aiur.strato.ascent`` for the reference flights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import sys

from .atmosphere import (G0, WindProfile, direct_irradiance_w_m2, isa,
                         solar_elevation_deg)
from .gas import GASES
from .guidance import FlightPhase, FloatController, Geofence, StationKeeper
from .thermal import FilmOptics, RadiativeEnvironment, external_h_w_m2k, film_temperature_k


@dataclass
class AscentConfig:
    name: str
    cell_type: str                      # zero-pressure | superpressure | latex
    dry_mass_kg: float                  # everything except gas and ballast
    max_volume_m3: float                # full hull, or total burst volume (latex)
    full_surface_m2: float
    length_m: float
    cross_area_full_m2: float           # broadside area when full (vertical drag)
    optics: FilmOptics
    gas: str = "hydrogen"
    n_cells: int = 1
    free_lift_fraction: float = 0.15
    ballast_kg: float = 0.0
    relief_pa: float = 30.0
    burst_pa: float = 400.0
    skin_pressure_pa: float = 120.0     # latex only
    valve_area_m2: float = 7.1e-4       # 30 mm bore
    valve_cd: float = 0.6
    ascent_cd: float = 0.65
    target_float_m: float = 20_000.0
    float_duration_s: float = 3600.0
    cruise_airspeed_m_s: float = 3.0
    wind: str = "midlat-summer-p50"
    wind_scale: float = 1.0
    wind_veer_deg: float = 0.0
    latitude_deg: float = 50.0
    day_of_year: int = 172
    launch_hour: float = 5.0
    launch_altitude_m: float = 150.0
    descent_rate_sea_level_m_s: float = 6.0
    descent_mass_kg: float = 0.0        # 0 -> dry mass (film stays attached)
    earth_ir_w_m2: float = 220.0
    gas_fill_error: float = 0.0         # fractional error in launch gas mass
    valve_fail_closed: bool = False
    max_time_s: float = 20 * 3600.0
    dt_s: float = 1.0
    use_station_keeping: bool = True
    #: Vertical force available from the vectored propulsor(s), N.
    trim_thrust_n: float = 0.0


@dataclass
class AscentResult:
    name: str
    summary: dict
    series: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"name": self.name, "summary": self.summary,
                           "events": self.events}, indent=2)


def simulate(cfg: AscentConfig, record_every_s: float = 30.0) -> AscentResult:
    gas = GASES[cfg.gas]
    wind = WindProfile(cfg.wind, cfg.wind_scale, cfg.wind_veer_deg)
    env = RadiativeEnvironment(earth_ir_w_m2=cfg.earth_ir_w_m2)
    ctl = FloatController(cfg.target_float_m, vent_enabled=cfg.cell_type != "zero-pressure")
    keeper = StationKeeper(cfg.cruise_airspeed_m_s)
    fence = Geofence(max_flight_s=cfg.max_time_s)

    z = cfg.launch_altitude_m
    air = isa(z)
    lift_per_kg = gas.lift_per_kg_gas(air)
    m_gas = (cfg.dry_mass_kg + cfg.ballast_kg) * (1.0 + cfg.free_lift_fraction) / lift_per_kg
    m_gas *= 1.0 + cfg.gas_fill_error
    m_gas0 = m_gas
    t_gas = air.temperature_k
    ballast = cfg.ballast_kg
    w = 0.0
    north = east = 0.0
    t = 0.0
    phase = FlightPhase.ASCENT
    events: list = []
    series: list = []
    float_entry_t = None
    float_alts: list = []
    max_alt = z
    max_dp = 0.0
    min_supertemp = 0.0
    max_supertemp = 0.0
    vented = 0.0
    burst = False
    energy_wh = 0.0
    trim_energy = 0.0
    next_rec = 0.0
    max_range = 0.0
    descent_mass = cfg.descent_mass_kg or cfg.dry_mass_kg
    # Parachute sized for the stated sea-level descent rate.
    chute_cda = 2.0 * descent_mass * G0 / (1.225 * cfg.descent_rate_sea_level_m_s**2)
    vmax_cell = cfg.max_volume_m3
    dt = cfg.dt_s

    def log(msg: str) -> None:
        events.append({"t_s": round(t, 1), "alt_m": round(z, 1), "event": msg})

    log(f"launch with {m_gas:.3f} kg {cfg.gas} "
        f"({m_gas * gas.gas_constant * 288.15 / 101325:.1f} Nm3)")

    while t < cfg.max_time_s + 4 * 3600.0:
        air = isa(z)
        hour = (cfg.launch_hour + t / 3600.0) % 24.0
        sun_el = solar_elevation_deg(cfg.latitude_deg, cfg.day_of_year, hour)
        wv = wind.at(z)

        if phase in (FlightPhase.DESCENT,):
            # Under parachute: quasi-steady terminal velocity.
            w = -math.sqrt(2.0 * descent_mass * G0 / (air.density_kg_m3 * chute_cda))
            z += w * dt
            north += wv.north_m_s * dt
            east += wv.east_m_s * dt
            t += dt
            if z <= cfg.launch_altitude_m:
                z = cfg.launch_altitude_m
                phase = FlightPhase.LANDED
                log(f"landed {math.hypot(north, east)/1000:.1f} km from launch, "
                    f"{abs(w):.1f} m/s")
                break
            if t >= next_rec:
                series.append(_row(t, z, w, 0.0, 0.0, 0.0, north, east, phase, sun_el, 0.0))
                next_rec += record_every_s
            continue

        # --- gas state
        p_gas_ambient = air.pressure_pa + (cfg.skin_pressure_pa if cfg.cell_type == "latex" else 0.0)
        v_free = m_gas * gas.gas_constant * t_gas / p_gas_ambient
        dp = 0.0
        if cfg.cell_type == "zero-pressure":
            if v_free > vmax_cell:
                new_m = p_gas_ambient * vmax_cell / (gas.gas_constant * t_gas)
                vented += m_gas - new_m
                m_gas = new_m
                v_free = vmax_cell
            volume = v_free
        elif cfg.cell_type == "superpressure":
            if v_free > vmax_cell:
                dp = m_gas * gas.gas_constant * t_gas / vmax_cell - air.pressure_pa
                if dp > cfg.relief_pa and not cfg.valve_fail_closed:
                    new_m = (air.pressure_pa + cfg.relief_pa) * vmax_cell / (gas.gas_constant * t_gas)
                    vented += m_gas - new_m
                    m_gas = new_m
                    dp = cfg.relief_pa
                if dp > cfg.burst_pa:
                    burst = True
                volume = vmax_cell
            else:
                volume = v_free
        else:  # latex
            volume = v_free
            dp = cfg.skin_pressure_pa
            if volume > vmax_cell:
                burst = True
        max_dp = max(max_dp, dp)
        fill = min(1.0, volume / vmax_cell)

        if burst:
            log(f"BURST at {z:.0f} m (volume {volume:.0f} m3, dp {dp:.0f} Pa)")
            phase = FlightPhase.DESCENT
            continue

        # --- control
        cmd = ctl.command(z, w, dt)
        vent_open = cmd.vent_open and not cfg.valve_fail_closed and phase != FlightPhase.TERMINATED
        if vent_open:
            if cfg.cell_type == "latex":
                dpv = cfg.skin_pressure_pa
            elif cfg.cell_type == "superpressure":
                dpv = max(dp, 2.0)
            else:
                # Apex valve on a zero-pressure cell sees the gas head.
                head = (volume / max(cfg.n_cells, 1) * 6.0 / math.pi) ** (1.0 / 3.0)
                dpv = (air.density_kg_m3 - gas.density(air.pressure_pa, t_gas)) * G0 * head
            rho_g = gas.density(p_gas_ambient, t_gas)
            mdot = cfg.n_cells * cfg.valve_cd * cfg.valve_area_m2 * math.sqrt(2.0 * rho_g * max(dpv, 0.0))
            dm = min(mdot * dt, 0.02 * m_gas)
            m_gas -= dm
            vented += dm
        if cmd.ballast_kg_s > 0.0 and ballast > 0.0:
            drop = min(ballast, cmd.ballast_kg_s * dt)
            ballast -= drop

        # --- vertical dynamics
        mass = cfg.dry_mass_kg + ballast + m_gas
        buoy = air.density_kg_m3 * volume * G0
        cell_v = volume / max(cfg.n_cells, 1)
        a_sphere = cfg.n_cells * math.pi * (3.0 * cell_v / (4.0 * math.pi)) ** (2.0 / 3.0)
        if cfg.cell_type == "latex":
            area = a_sphere
        else:
            area = (1.0 - fill**2) * a_sphere + fill**2 * cfg.cross_area_full_m2
        drag = -0.5 * air.density_kg_m3 * cfg.ascent_cd * area * abs(w) * w
        virtual = mass + 0.5 * air.density_kg_m3 * volume
        trim_n = cmd.trim * cfg.trim_thrust_n if phase in (
            FlightPhase.FLOAT_ENTRY, FlightPhase.STATION_KEEP) else 0.0
        trim_energy += abs(cmd.trim) * dt / 3600.0 if trim_n else 0.0
        accel = (buoy - mass * G0 + drag + trim_n) / virtual
        w += accel * dt
        w = max(-40.0, min(40.0, w))
        z_new = z + w * dt
        if z_new < cfg.launch_altitude_m and t > 60.0:
            z = cfg.launch_altitude_m
            log("returned to ground without termination")
            phase = FlightPhase.LANDED
            break
        # --- gas thermodynamics
        s_eff = cfg.n_cells * 4.0 * math.pi * (3.0 * cell_v / (4.0 * math.pi)) ** (2.0 / 3.0)
        if cfg.cell_type != "latex":
            s_eff = (1.0 - fill) * s_eff + fill * cfg.full_surface_m2
        rel_speed = math.hypot(w, cfg.cruise_airspeed_m_s if phase == FlightPhase.STATION_KEEP else 0.0)
        h_ext = external_h_w_m2k(air, cfg.length_m, rel_speed, t_gas - air.temperature_k)
        h_int = 2.5
        sun = direct_irradiance_w_m2(z, sun_el)
        t_film = film_temperature_k(air, cfg.optics, t_gas, sun, sun_el, h_ext, h_int, env)
        q = h_int * s_eff * (t_film - t_gas)
        dp_amb = -air.density_kg_m3 * G0 * w * dt
        expanding = cfg.cell_type != "superpressure" or fill < 1.0
        dt_adiabatic = (gas.gas_constant * t_gas / (gas.cp_j_kgk * air.pressure_pa)) * dp_amb \
            if expanding else 0.0
        t_gas += q * dt / (m_gas * gas.cp_j_kgk) + dt_adiabatic
        supertemp = t_gas - air.temperature_k
        min_supertemp = min(min_supertemp, supertemp)
        max_supertemp = max(max_supertemp, supertemp)

        # --- horizontal
        if phase == FlightPhase.STATION_KEEP and cfg.use_station_keeping:
            ac = keeper.command(-north, -east, wv.north_m_s, wv.east_m_s)
            north += (wv.north_m_s + ac.north_m_s) * dt
            east += (wv.east_m_s + ac.east_m_s) * dt
            energy_wh += (ac.airspeed_m_s / max(cfg.cruise_airspeed_m_s, 0.1)) ** 3 * dt / 3600.0
        else:
            north += wv.north_m_s * dt
            east += wv.east_m_s * dt
        z = z_new
        t += dt
        max_alt = max(max_alt, z)
        rng = math.hypot(north, east)
        max_range = max(max_range, rng)

        # --- phase logic
        if phase == FlightPhase.ASCENT and z > cfg.target_float_m - ctl.approach_m:
            phase = FlightPhase.FLOAT_ENTRY
            log(f"float entry, climb {w:.2f} m/s, gas {supertemp:+.1f} K vs air")
        if phase == FlightPhase.FLOAT_ENTRY and abs(w) < 0.3 and \
                abs(z - cfg.target_float_m) < 1500.0 or \
                (phase == FlightPhase.FLOAT_ENTRY and fill >= 0.999 and abs(w) < 0.3):
            phase = FlightPhase.STATION_KEEP
            float_entry_t = t
            log(f"at float, {rng/1000:.1f} km downrange, fill {100*fill:.0f} %")
        if phase == FlightPhase.STATION_KEEP:
            float_alts.append(z)
        term, why = fence.must_terminate(rng, z, t)
        if phase == FlightPhase.STATION_KEEP and float_entry_t is not None and \
                t - float_entry_t >= cfg.float_duration_s:
            term, why = True, "mission complete"
        if term and phase not in (FlightPhase.DESCENT, FlightPhase.LANDED):
            log(f"terminate: {why}")
            phase = FlightPhase.DESCENT
        if t >= next_rec:
            series.append(_row(t, z, w, supertemp, fill, dp, north, east, phase, sun_el, m_gas))
            next_rec += record_every_s

    mean_float = sum(float_alts) / len(float_alts) if float_alts else float("nan")
    sd_float = (math.sqrt(sum((a - mean_float) ** 2 for a in float_alts) / len(float_alts))
                if float_alts else float("nan"))
    summary = {
        "reached_float": float_entry_t is not None,
        "time_to_float_min": None if float_entry_t is None else round(float_entry_t / 60.0, 1),
        "mean_ascent_rate_m_s": None if float_entry_t is None else round(
            (cfg.target_float_m - cfg.launch_altitude_m) / float_entry_t, 2),
        "max_altitude_m": round(max_alt, 0),
        "float_mean_m": None if not float_alts else round(mean_float, 0),
        "float_sd_m": None if not float_alts else round(sd_float, 0),
        "min_gas_supertemp_k": round(min_supertemp, 1),
        "max_gas_supertemp_k": round(max_supertemp, 1),
        "max_superpressure_pa": round(max_dp, 1),
        "gas_launch_kg": round(m_gas0, 3),
        "gas_vented_kg": round(vented, 3),
        "ballast_used_kg": round(cfg.ballast_kg - ballast, 3),
        "burst": burst,
        "max_range_km": round(max_range / 1000.0, 1),
        "landing_range_km": round(math.hypot(north, east) / 1000.0, 1),
        "landing_bearing_deg": round(math.degrees(math.atan2(east, north)) % 360.0, 0),
        "flight_time_h": round(t / 3600.0, 2),
        "final_phase": phase.value,
        "station_keep_cube_hours": round(energy_wh, 3),
        "trim_full_thrust_hours": round(trim_energy, 3),
    }
    return AscentResult(cfg.name, summary, series, events)


def _row(t, z, w, supertemp, fill, dp, north, east, phase, sun_el, m_gas) -> dict:
    return {"t_s": round(t, 1), "alt_m": round(z, 1), "climb_m_s": round(w, 3),
            "supertemp_k": round(supertemp, 2), "fill": round(fill, 4),
            "superpressure_pa": round(dp, 1), "north_m": round(north, 0),
            "east_m": round(east, 0), "phase": phase.value,
            "sun_el_deg": round(sun_el, 1), "gas_kg": round(m_gas, 4)}


# --- configuration from a sized design ---------------------------------------

def config_from_design(dp, **overrides) -> AscentConfig:
    """Build an ascent configuration from a ``sizing.DesignPoint``."""

    from .materials import FILMS, LATEX
    m = dp.mission
    if dp.architecture == "tandem":
        balloon = next(b for b in LATEX.values() if b.name == dp.geometry["balloon"])
        cfg = AscentConfig(
            name=m["name"] + "/tandem", cell_type="latex",
            dry_mass_kg=dp.mass_kg["gross"] - dp.mass_kg.get("ballast", 0.0),
            ballast_kg=dp.mass_kg.get("ballast", 0.0),
            max_volume_m3=2 * balloon.burst_volume_m3,
            full_surface_m2=2 * math.pi * balloon.burst_diameter_m**2,
            length_m=dp.geometry["cell_diameter_m"],
            cross_area_full_m2=2 * math.pi * balloon.burst_diameter_m**2 / 4,
            optics=FilmOptics(0.35, 0.85), n_cells=2,
            skin_pressure_pa=balloon.skin_pressure_pa,
        )
    else:
        film = next(f for f in FILMS.values() if f.name == dp.geometry["film"])
        sp = dp.structure["superpressure"]
        cfg = AscentConfig(
            name=m["name"] + "/hull", cell_type="superpressure" if sp else "zero-pressure",
            dry_mass_kg=dp.mass_kg["gross"] - dp.mass_kg.get("ballast", 0.0),
            ballast_kg=dp.mass_kg.get("ballast", 0.0),
            max_volume_m3=dp.geometry["volume_m3"],
            full_surface_m2=dp.geometry["surface_area_m2"],
            length_m=dp.geometry["length_m"],
            cross_area_full_m2=0.8 * dp.geometry["length_m"] * dp.geometry["diameter_m"],
            optics=FilmOptics(film.solar_absorptance, film.ir_emittance),
            relief_pa=dp.structure["design_pressure_pa"] if sp else dp.structure["relief_pressure_pa"],
            burst_pa=film.ultimate_n_per_m * dp.geometry["film_plies_equiv"] * 0.6
            / (dp.geometry["diameter_m"] / 2.0),
        )
    cfg.trim_thrust_n = 0.6 * dp.propulsion["dash"]["thrust_n"] * dp.propulsion["n_props"]
    cfg.gas = m["gas"]
    cfg.free_lift_fraction = m["free_lift_fraction"]
    cfg.target_float_m = m["float_altitude_m"]
    cfg.cruise_airspeed_m_s = m["cruise_airspeed_m_s"]
    cfg.latitude_deg = m["latitude_deg"]
    cfg.day_of_year = m["day_of_year"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def main(argv: list[str]) -> int:
    from .sizing import ladder
    pts = ladder()
    out = {}
    for key in ("S1-touch/tandem", "S1-touch/hull", "S2-dayloiter/hull"):
        res = simulate(config_from_design(pts[key]))
        out[key] = res
        print(f"=== {key}")
        for k, v in res.summary.items():
            print(f"  {k:28s} {v}")
        for e in res.events:
            print(f"  [{e['t_s']/60:7.1f} min {e['alt_m']:8.0f} m] {e['event']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
