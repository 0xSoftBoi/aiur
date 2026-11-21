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


class AscentSim:
    """The plant, one step at a time.

    ``simulate`` wraps this with the flight-software controllers for batch
    runs; the ROS 2 plant node steps the very same object and takes its
    commands from topics instead.  There is one set of physics.
    """

    def __init__(self, cfg: AscentConfig) -> None:
        self.cfg = cfg
        self.gas = GASES[cfg.gas]
        self.wind = WindProfile(cfg.wind, cfg.wind_scale, cfg.wind_veer_deg)
        self.env = RadiativeEnvironment(earth_ir_w_m2=cfg.earth_ir_w_m2)
        self.z = cfg.launch_altitude_m
        air = isa(self.z)
        lift_per_kg = self.gas.lift_per_kg_gas(air)
        self.m_gas = ((cfg.dry_mass_kg + cfg.ballast_kg) * (1.0 + cfg.free_lift_fraction)
                      / lift_per_kg) * (1.0 + cfg.gas_fill_error)
        self.m_gas0 = self.m_gas
        self.t_gas = air.temperature_k
        self.ballast = cfg.ballast_kg
        self.w = 0.0
        self.north = self.east = 0.0
        self.vel_north = self.vel_east = 0.0
        self.t = 0.0
        self.volume = self.m_gas * self.gas.gas_constant * self.t_gas / air.pressure_pa
        self.fill = self.volume / cfg.max_volume_m3
        self.dp = 0.0
        self.supertemp = 0.0
        self.sun_el = 0.0
        self.vented = 0.0
        self.burst = False
        self.descending = False
        self.landed = False
        self.landing_speed = 0.0
        self.powered = False
        self.air_speed_cmd = 0.0
        self.descent_mass = cfg.descent_mass_kg or cfg.dry_mass_kg
        self.chute_cda = (2.0 * self.descent_mass * G0
                          / (1.225 * cfg.descent_rate_sea_level_m_s**2))

    @property
    def air(self):
        return isa(self.z)

    def terminate(self) -> None:
        self.descending = True

    def step(self, dt: float, vent_open: bool = False, ballast_kg_s: float = 0.0,
             trim: float = 0.0, air_velocity_ne: tuple = (0.0, 0.0)) -> None:
        if self.landed:
            return
        cfg, gas = self.cfg, self.gas
        air = isa(self.z)
        hour = (cfg.launch_hour + self.t / 3600.0) % 24.0
        self.sun_el = solar_elevation_deg(cfg.latitude_deg, cfg.day_of_year, hour)
        wv = self.wind.at(self.z)

        if self.descending:
            # Under parachute: quasi-steady terminal velocity.
            self.w = -math.sqrt(2.0 * self.descent_mass * G0
                                / (air.density_kg_m3 * self.chute_cda))
            self.z += self.w * dt
            self.vel_north, self.vel_east = wv.north_m_s, wv.east_m_s
            self.north += wv.north_m_s * dt
            self.east += wv.east_m_s * dt
            self.t += dt
            self.fill = self.dp = self.supertemp = 0.0
            if self.z <= cfg.launch_altitude_m:
                self.z = cfg.launch_altitude_m
                self.landing_speed = abs(self.w)
                self.w = 0.0
                self.vel_north = self.vel_east = 0.0
                self.landed = True
            return

        self.update_gas(air)
        if self.burst:
            self.descending = True
            return
        self.apply_buoyancy_commands(air, dt, vent_open, ballast_kg_s)

        # --- vertical dynamics
        latex = cfg.cell_type == "latex"
        volume, fill = self.volume, self.fill
        mass = self.mass_kg
        buoy = air.density_kg_m3 * volume * G0
        cell_v = volume / max(cfg.n_cells, 1)
        a_sphere = cfg.n_cells * math.pi * (3.0 * cell_v / (4.0 * math.pi)) ** (2.0 / 3.0)
        area = a_sphere if latex else (1.0 - fill**2) * a_sphere + fill**2 * cfg.cross_area_full_m2
        w = self.w
        drag = -0.5 * air.density_kg_m3 * cfg.ascent_cd * area * abs(w) * w
        virtual = mass + 0.5 * air.density_kg_m3 * volume
        trim_n = max(-1.0, min(1.0, trim)) * cfg.trim_thrust_n
        w += (buoy - mass * G0 + drag + trim_n) / virtual * dt
        w = max(-40.0, min(40.0, w))
        z_new = self.z + w * dt
        if z_new < cfg.launch_altitude_m and self.t > 60.0:
            self.z = cfg.launch_altitude_m
            self.w = 0.0
            self.landed = True
            return

        an, ae = air_velocity_ne
        self.air_speed_cmd = math.hypot(an, ae)
        self.update_thermal(air, dt, w, self.air_speed_cmd)

        # --- horizontal: the vehicle moves with the air plus its own airspeed
        self.vel_north = wv.north_m_s + an
        self.vel_east = wv.east_m_s + ae
        self.north += self.vel_north * dt
        self.east += self.vel_east * dt
        self.z = z_new
        self.w = w
        self.t += dt

    # The three pieces below are the buoyancy model proper.  ``step`` uses
    # them with its own one-dimensional dynamics; ``mission6.UnifiedSim``
    # uses them with the 6-DoF model supplying altitude and climb rate.

    @property
    def mass_kg(self) -> float:
        return self.cfg.dry_mass_kg + self.ballast + self.m_gas

    def update_gas(self, air) -> None:
        """Cell volume, pressure, spill and burst at the present altitude."""

        cfg, gas = self.cfg, self.gas
        latex = cfg.cell_type == "latex"
        p_gas = air.pressure_pa + (cfg.skin_pressure_pa if latex else 0.0)
        v_free = self.m_gas * gas.gas_constant * self.t_gas / p_gas
        vmax = cfg.max_volume_m3
        dp = 0.0
        if cfg.cell_type == "zero-pressure":
            if v_free > vmax:
                new_m = p_gas * vmax / (gas.gas_constant * self.t_gas)
                self.vented += self.m_gas - new_m
                self.m_gas = new_m
                v_free = vmax
            volume = v_free
        elif cfg.cell_type == "superpressure":
            if v_free > vmax:
                dp = self.m_gas * gas.gas_constant * self.t_gas / vmax - air.pressure_pa
                if dp > cfg.relief_pa and not cfg.valve_fail_closed:
                    new_m = (air.pressure_pa + cfg.relief_pa) * vmax / (gas.gas_constant * self.t_gas)
                    self.vented += self.m_gas - new_m
                    self.m_gas = new_m
                    dp = cfg.relief_pa
                if dp > cfg.burst_pa:
                    self.burst = True
                volume = vmax
            else:
                volume = v_free
        else:
            volume = v_free
            dp = cfg.skin_pressure_pa
            if volume > vmax:
                self.burst = True
        self.volume, self.dp = volume, dp
        self.fill = min(1.0, volume / vmax)

    def apply_buoyancy_commands(self, air, dt: float, vent_open: bool,
                                ballast_kg_s: float) -> None:
        cfg, gas = self.cfg, self.gas
        if vent_open and not cfg.valve_fail_closed:
            latex = cfg.cell_type == "latex"
            p_gas = air.pressure_pa + (cfg.skin_pressure_pa if latex else 0.0)
            if latex:
                dpv = cfg.skin_pressure_pa
            elif cfg.cell_type == "superpressure":
                dpv = max(self.dp, 2.0)
            else:
                # Apex valve on a zero-pressure cell sees the gas head.
                head = (self.volume / max(cfg.n_cells, 1) * 6.0 / math.pi) ** (1.0 / 3.0)
                dpv = (air.density_kg_m3 - gas.density(air.pressure_pa, self.t_gas)) * G0 * head
            rho_g = gas.density(p_gas, self.t_gas)
            mdot = cfg.n_cells * cfg.valve_cd * cfg.valve_area_m2 * math.sqrt(
                2.0 * rho_g * max(dpv, 0.0))
            dm = min(mdot * dt, 0.02 * self.m_gas)
            self.m_gas -= dm
            self.vented += dm
        if ballast_kg_s > 0.0 and self.ballast > 0.0:
            self.ballast -= min(self.ballast, ballast_kg_s * dt)

    def update_thermal(self, air, dt: float, climb_m_s: float, airspeed_m_s: float) -> None:
        """Advance gas temperature: film heat exchange plus adiabatic work."""

        cfg, gas = self.cfg, self.gas
        fill = self.fill
        cell_v = self.volume / max(cfg.n_cells, 1)
        s_eff = cfg.n_cells * 4.0 * math.pi * (3.0 * cell_v / (4.0 * math.pi)) ** (2.0 / 3.0)
        if cfg.cell_type != "latex":
            s_eff = (1.0 - fill) * s_eff + fill * cfg.full_surface_m2
        rel_speed = math.hypot(climb_m_s, airspeed_m_s)
        h_ext = external_h_w_m2k(air, cfg.length_m, rel_speed, self.t_gas - air.temperature_k)
        h_int = 2.5
        sun = direct_irradiance_w_m2(self.z, self.sun_el)
        t_film = film_temperature_k(air, cfg.optics, self.t_gas, sun, self.sun_el,
                                    h_ext, h_int, self.env)
        q = h_int * s_eff * (t_film - self.t_gas)
        dp_amb = -air.density_kg_m3 * G0 * climb_m_s * dt
        expanding = cfg.cell_type != "superpressure" or fill < 1.0
        dt_ad = (gas.gas_constant * self.t_gas / (gas.cp_j_kgk * air.pressure_pa)) * dp_amb \
            if expanding else 0.0
        self.t_gas += q * dt / (self.m_gas * gas.cp_j_kgk) + dt_ad
        self.supertemp = self.t_gas - air.temperature_k

    @property
    def range_m(self) -> float:
        return math.hypot(self.north, self.east)


def simulate(cfg: AscentConfig, record_every_s: float = 30.0) -> AscentResult:
    sim = AscentSim(cfg)
    zero_p = cfg.cell_type == "zero-pressure"
    ctl = FloatController(cfg.target_float_m, vent_enabled=not zero_p, hold_enabled=not zero_p)
    keeper = StationKeeper(cfg.cruise_airspeed_m_s)
    fence = Geofence(max_flight_s=cfg.max_time_s)
    phase = FlightPhase.ASCENT
    events: list = []
    series: list = []
    float_entry_t = None
    float_alts: list = []
    max_alt = sim.z
    max_dp = 0.0
    min_st = max_st = 0.0
    energy_cube_h = 0.0
    trim_h = 0.0
    next_rec = 0.0
    max_range = 0.0
    dt = cfg.dt_s

    def log(msg: str) -> None:
        events.append({"t_s": round(sim.t, 1), "alt_m": round(sim.z, 1), "event": msg})

    log(f"launch with {sim.m_gas:.3f} kg {cfg.gas} "
        f"({sim.m_gas * sim.gas.gas_constant * 288.15 / 101325:.1f} Nm3)")

    while sim.t < cfg.max_time_s + 4 * 3600.0 and not sim.landed:
        if phase == FlightPhase.DESCENT:
            sim.step(dt)
        else:
            cmd = ctl.command(sim.z, sim.w, dt)
            trim = cmd.trim if phase in (FlightPhase.FLOAT_ENTRY, FlightPhase.STATION_KEEP) else 0.0
            air_vel = (0.0, 0.0)
            if phase == FlightPhase.STATION_KEEP and cfg.use_station_keeping:
                wv = sim.wind.at(sim.z)
                ac = keeper.command(-sim.north, -sim.east, wv.north_m_s, wv.east_m_s)
                air_vel = (ac.north_m_s, ac.east_m_s)
                energy_cube_h += (ac.airspeed_m_s / max(cfg.cruise_airspeed_m_s, 0.1)) ** 3 * dt / 3600.0
            if trim and cfg.trim_thrust_n:
                trim_h += abs(trim) * dt / 3600.0
            was_burst = sim.burst
            sim.step(dt, cmd.vent_open, cmd.ballast_kg_s, trim, air_vel)
            if sim.burst and not was_burst:
                log(f"BURST (volume {sim.volume:.0f} m3, dp {sim.dp:.0f} Pa)")
                phase = FlightPhase.DESCENT
                continue
        max_alt = max(max_alt, sim.z)
        max_dp = max(max_dp, sim.dp)
        min_st, max_st = min(min_st, sim.supertemp), max(max_st, sim.supertemp)
        max_range = max(max_range, sim.range_m)
        if sim.landed:
            if phase == FlightPhase.DESCENT:
                log(f"landed {sim.range_m/1000:.1f} km from launch, {sim.landing_speed:.1f} m/s")
            else:
                log("returned to ground without termination")
            phase = FlightPhase.LANDED
            break
        if phase == FlightPhase.ASCENT and sim.z > cfg.target_float_m - ctl.approach_m:
            phase = FlightPhase.FLOAT_ENTRY
            log(f"float entry, climb {sim.w:.2f} m/s, gas {sim.supertemp:+.1f} K vs air")
        settled = sim.fill >= 0.999 if zero_p else abs(sim.z - cfg.target_float_m) < 1500.0
        if phase == FlightPhase.FLOAT_ENTRY and abs(sim.w) < 0.3 and settled:
            phase = FlightPhase.STATION_KEEP
            float_entry_t = sim.t
            if zero_p:
                ctl.settle(max_alt)
            log(f"at float, {sim.range_m/1000:.1f} km downrange, fill {100*sim.fill:.0f} %")
        if phase == FlightPhase.STATION_KEEP:
            float_alts.append(sim.z)
        if phase != FlightPhase.DESCENT:
            term, why = fence.must_terminate(sim.range_m, sim.z, sim.t)
            if phase == FlightPhase.STATION_KEEP and float_entry_t is not None and \
                    sim.t - float_entry_t >= cfg.float_duration_s:
                term, why = True, "mission complete"
            if term:
                log(f"terminate: {why}")
                sim.terminate()
                phase = FlightPhase.DESCENT
        if sim.t >= next_rec:
            series.append(_row(sim.t, sim.z, sim.w, sim.supertemp, sim.fill, sim.dp, sim.north,
                               sim.east, phase, sim.sun_el, sim.m_gas))
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
        "min_gas_supertemp_k": round(min_st, 1),
        "max_gas_supertemp_k": round(max_st, 1),
        "max_superpressure_pa": round(max_dp, 1),
        "gas_launch_kg": round(sim.m_gas0, 3),
        "gas_vented_kg": round(sim.vented, 3),
        "ballast_used_kg": round(cfg.ballast_kg - sim.ballast, 3),
        "burst": sim.burst,
        "max_range_km": round(max_range / 1000.0, 1),
        "landing_range_km": round(sim.range_m / 1000.0, 1),
        "landing_bearing_deg": round(math.degrees(math.atan2(sim.east, sim.north)) % 360.0, 0),
        "flight_time_h": round(sim.t / 3600.0, 2),
        "final_phase": phase.value,
        "station_keep_cube_hours": round(energy_cube_h, 3),
        "trim_full_thrust_hours": round(trim_h, 3),
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
    # Vertical force from pitching the hull at cruise.  0.25 of dash thrust is
    # what the unified 6-DoF run (mission6) delivers at 8 degrees of pitch;
    # the 0.6 first assumed here was about three times too generous.
    cfg.trim_thrust_n = 0.25 * dp.propulsion["dash"]["thrust_n"] * dp.propulsion["n_props"]
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
