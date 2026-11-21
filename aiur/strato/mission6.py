"""One plant from launch to landing: buoyancy model + 6-DoF flight.

``ascent`` flies the whole mission as a point with no attitude; ``flight6dof``
flies the hull at float with no buoyancy physics.  Each made an assumption
the other could have tested.  This module joins them:

* while the hull is a slack bubble (fill below ``handoff_fill``) the vehicle
  is the ascent model's point mass - there is no hull shape to fly;
* once the hull has taken shape the rigid-body model takes over all six
  degrees of freedom, with weight and buoyancy supplied every second by the
  gas model (expansion, spill, superheat, ballast) and air density following
  altitude;
* after cut-down the equipment string descends under parachute.

The assumption this was built to test: the ascent model holds altitude with
an abstract "trim thrust".  Here that demand becomes a pitch command, and
the vertical force has to come from tilting the whole hull - thrust
component plus aerodynamic lift - through one gimballed propeller.

    python -m aiur.strato.mission6
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sys

from .ascent import AscentSim, config_from_design
from .atmosphere import G0, Gust, isa, solar_elevation_deg
from .energy import ARRAYS, array_power_w_per_m2
from .propulsion import ESC_EFFICIENCY, MOTORS, Propeller
from .flight6dof import (Airframe, FlightController, State, _mat_t_vec, euler_from_quat,
                         quat_from_euler, quat_to_matrix, step)
from .guidance import EntryGuidance, FlightPhase, FloatController, Geofence, StationKeeper
from .hull import Hull


@dataclass
class MissionOptions:
    handoff_fill: float = 0.85
    #: True when guidance arrives from outside (the ROS flight nodes); the
    #: attitude inner loop stays here, as it would inside the autopilot.
    external: bool = False
    gust_sigma_m_s: float = 0.5
    float_duration_s: float = 3600.0
    dt_flight_s: float = 0.05
    seed: int = 1
    max_time_s: float = 8 * 3600.0
    record_every_s: float = 20.0
    #: Fault hooks (see ``faults``): time-keyed overrides applied by the caller.
    gimbal_jam_at_s: float | None = None
    motor_fail_at_s: float | None = None


class UnifiedSim:
    def __init__(self, dp, opts: MissionOptions | None = None, **cfg_over) -> None:
        self.dp = dp
        self.o = opts or MissionOptions()
        self.cfg = config_from_design(dp, float_duration_s=self.o.float_duration_s, **cfg_over)
        self.asc = AscentSim(self.cfg)
        self.hull = Hull(dp.geometry["volume_m3"], dp.geometry["fineness"])
        g = dp.mass_kg["gross"]
        film = dp.mass_kg["envelope_film"] + dp.mass_kg["seams_patches"] + dp.mass_kg["fins"]
        self.cg_ratio = (g - film) * (self.hull.radius_m + 0.25)
        self.max_thrust = dp.propulsion["dash"]["thrust_n"] * dp.propulsion["n_props"]
        self.cruise = float(dp.mission["cruise_airspeed_m_s"])
        self.mode = "bubble"
        self.phase = FlightPhase.ASCENT
        self.af: Airframe | None = None
        self.st: State | None = None
        self.fc: FlightController | None = None
        self.z0 = 0.0
        self.af_alt = self.af_mass = 0.0
        zero_p = self.cfg.cell_type == "zero-pressure"
        self.zero_p = zero_p
        self.max_alt = 0.0
        self._quiet_s = 0.0
        self.float_ctl = FloatController(self.cfg.target_float_m, vent_enabled=not zero_p,
                                         hold_enabled=not zero_p)
        self.keeper = StationKeeper(self.cruise)
        self.entry = EntryGuidance(self.cruise)
        self.ext = None
        self.fence = Geofence(max_flight_s=self.o.max_time_s)
        self.gust = Gust(self.o.gust_sigma_m_s, 20.0, seed=self.o.seed)
        self.wind_est = [0.0, 0.0]
        self.t = 0.0
        self.events: list = []
        self.rows: list = []
        self.float_entry_t = None
        self.stats = {"float_alts": [], "station_err": [], "pitch": [], "sat_s": 0.0,
                      "thrust_j": 0.0, "hull_s": 0.0, "max_pitch": 0.0, "max_roll": 0.0}
        self.rebuilds = 0
        # --- energy: one bus, array in, hotel and propulsion out
        e = dp.energy
        self.batt_wh = self.batt_full_wh = float(e["pack_usable_wh"])
        self.hotel_w = float(e["hotel_w"])
        self.array_m2 = float(e["array_m2"])
        self.array = ARRAYS["mono-si-laminate"]
        self.prop = Propeller(dp.propulsion["prop_diameter_m"])
        self.motor = MOTORS[dp.propulsion["motor"]]
        self.n_props = dp.propulsion["n_props"]
        self.energy = {"min_soc": 1.0, "prop_wh": 0.0, "hotel_wh": 0.0, "solar_wh": 0.0,
                       "spilled_wh": 0.0, "brownout_s": 0.0, "peak_prop_w": 0.0}
        self.brownout = False

    def _energy_second(self, thrust_n: float, airspeed: float) -> None:
        """One second of the power bus.  Propulsion is cut on brown-out."""

        air = isa(self.z)
        prop_w = 0.0
        if thrust_n > 0.02:
            op = self.prop.operating_point(air, thrust_n / self.n_props, max(airspeed, 0.0))
            el = self.motor.electrical(op["rpm"], op["torque_nm"], self.dp.energy["bus_v"])
            prop_w = self.n_props * el["input_w"] / ESC_EFFICIENCY
        hour = (self.cfg.launch_hour + self.t / 3600.0) % 24.0
        el_sun = solar_elevation_deg(self.cfg.latitude_deg, self.cfg.day_of_year, hour)
        solar_w = self.array_m2 * array_power_w_per_m2(self.array, self.z, el_sun) \
            if self.array_m2 > 0 and self.mode == "hull" else 0.0
        en = self.energy
        net = (solar_w - self.hotel_w - prop_w) / 3600.0
        new = self.batt_wh + net
        if new > self.batt_full_wh:
            en["spilled_wh"] += new - self.batt_full_wh
            new = self.batt_full_wh
        self.batt_wh = max(0.0, new)
        self.brownout = self.batt_wh <= 0.02 * self.batt_full_wh
        en["brownout_s"] += 1.0 if self.brownout else 0.0
        en["prop_wh"] += prop_w / 3600.0
        en["hotel_wh"] += self.hotel_w / 3600.0
        en["solar_wh"] += solar_w / 3600.0
        en["peak_prop_w"] = max(en["peak_prop_w"], prop_w)
        en["min_soc"] = min(en["min_soc"], self.batt_wh / self.batt_full_wh)

    # --- plumbing -------------------------------------------------------------
    @property
    def z(self) -> float:
        return self.asc.z if self.mode != "hull" else self.z0 - self.st.pos[2]

    @property
    def climb(self) -> float:
        if self.mode != "hull":
            return self.asc.w
        rot = quat_to_matrix(self.st.quat)
        return -(rot[2][0] * self.st.vel[0] + rot[2][1] * self.st.vel[1] + rot[2][2] * self.st.vel[2])

    @property
    def north(self) -> float:
        return self.asc.north if self.mode != "hull" else self.st.pos[0]

    @property
    def east(self) -> float:
        return self.asc.east if self.mode != "hull" else self.st.pos[1]

    def log(self, msg: str) -> None:
        self.events.append({"t_s": round(self.t, 0), "alt_m": round(self.z, 0), "event": msg})

    def _build_airframe(self, z: float) -> None:
        mass = self.asc.mass_kg
        self.af = Airframe(hull=self.hull, mass_kg=mass, altitude_m=z,
                           cg_below_cv_m=self.cg_ratio / mass,
                           fin_area_total_m2=self.dp.geometry["fin_area_total_m2"],
                           max_thrust_n=self.max_thrust)
        self.af_alt, self.af_mass = z, mass
        self.rebuilds += 1
        if self.fc is None:
            self.fc = FlightController.for_airframe(self.af)
        else:
            self.fc.yaw_inertia = self.af.inertia[2] + self.af.a22[2]
            self.fc.pitch_inertia = self.af.inertia[1] + self.af.a22[1]

    def _handoff(self) -> None:
        a = self.asc
        wv = a.wind.at(a.z)
        hdg = math.atan2(-wv.east_m_s, -wv.north_m_s) if wv.speed_m_s > 0.2 else 0.0
        self.z0 = a.z
        self._build_airframe(a.z)
        # The bubble was drifting with the air and climbing: zero airspeed,
        # body-axis vertical velocity equal to the climb rate (z is down).
        self.st = State(pos=(a.north, a.east, 0.0), quat=quat_from_euler(0.0, 0.0, hdg),
                        vel=(0.0, 0.0, -a.w))
        self.wind_est = [wv.north_m_s, wv.east_m_s]
        self.mode = "hull"
        self.log(f"hull has shape (fill {100*a.fill:.0f} %): 6-DoF takes over, climb {a.w:.1f} m/s")

    # --- one second of mission ------------------------------------------------
    def step_second(self, ext: dict | None = None) -> None:
        """Advance one second.  ``ext`` carries outside guidance when
        ``external``: vent, ballast_kg_s, trim, pitch_cmd, heading, airspeed."""

        a, o = self.asc, self.o
        if self.mode == "bubble":
            if ext is not None:
                a.step(1.0, ext["vent"], ext["ballast_kg_s"], 0.0)
            else:
                cmd = self.float_ctl.command(a.z, a.w, 1.0)
                a.step(1.0, cmd.vent_open, cmd.ballast_kg_s, 0.0)
            self.t = a.t
            self._energy_second(0.0, 0.0)
            if a.burst or a.landed:
                self.mode = "descent"
            elif a.fill >= o.handoff_fill and self.dp.architecture == "hull":
                self._handoff()
            self._phases()
            return
        if self.mode == "descent":
            a.step(1.0)
            self.t = a.t
            if a.landed and self.phase != FlightPhase.LANDED:
                self.phase = FlightPhase.LANDED
                self.log(f"landed {a.range_m/1000:.1f} km from launch")
            return

        # --- hull mode: gas model for one second at the 6-DoF altitude
        z, w_up = self.z, self.climb
        air = isa(z)
        a.z, a.w = z, w_up
        a.north, a.east = self.st.pos[0], self.st.pos[1]
        hour = (self.cfg.launch_hour + self.t / 3600.0) % 24.0
        from .atmosphere import solar_elevation_deg
        a.sun_el = solar_elevation_deg(self.cfg.latitude_deg, self.cfg.day_of_year, hour)
        a.update_gas(air)
        if ext is not None:
            vent, ballast, trim = ext["vent"], ext["ballast_kg_s"], ext["trim"]
        else:
            fcmd = self.float_ctl.command(z, w_up, 1.0)
            vent, ballast, trim = fcmd.vent_open, fcmd.ballast_kg_s, fcmd.trim
        a.apply_buoyancy_commands(air, 1.0, vent, ballast)
        airspeed = math.sqrt(sum(c * c for c in self.st.vel))
        a.update_thermal(air, 1.0, w_up, airspeed)
        a.t += 1.0
        if abs(z - self.af_alt) > 250.0 or abs(a.mass_kg - self.af_mass) > 0.005 * self.af_mass:
            self._build_airframe(z)
        af = self.af
        af.weight_n = a.mass_kg * G0
        af.buoyancy_n = air.density_kg_m3 * a.volume * G0

        # --- guidance
        wv = a.wind.at(z)
        if ext is not None:
            heading, speed, pitch_cmd = ext["heading"], ext["airspeed"], ext["pitch_cmd"]
        else:
            keeper_speed = 0.0
            heading = math.atan2(-self.wind_est[1], -self.wind_est[0]) \
                if math.hypot(*self.wind_est) > 0.2 else 0.0
            if self.phase == FlightPhase.STATION_KEEP:
                ac = self.keeper.command(-self.st.pos[0], -self.st.pos[1],
                                         self.wind_est[0], self.wind_est[1])
                heading, keeper_speed = ac.heading_rad, ac.airspeed_m_s
            speed = self.entry.airspeed_command(self.phase.value, trim, w_up, keeper_speed)
            pitch_cmd = self.entry.pitch_command_rad(self.phase.value, trim, w_up, self.st.vel[0])

        # --- twenty 6-DoF steps
        n = int(round(1.0 / o.dt_flight_s))
        for _ in range(n):
            g = self.gust.step(o.dt_flight_s)
            wind = (wv.north_m_s + g[0], wv.east_m_s + g[1], g[2])
            gb = _mat_t_vec(quat_to_matrix(self.st.quat), tuple(self.gust.rate))
            sp = max(2.0, airspeed)
            af.gust_rot = (gb[2] / sp, -gb[1] / sp)
            rpy = euler_from_quat(self.st.quat)
            c = self.fc.command(heading, speed, pitch_cmd, rpy, self.st.rate, self.st.vel[0],
                                self.st.thrust_n, o.dt_flight_s)
            if (o.motor_fail_at_s is not None and self.t >= o.motor_fail_at_s) or self.brownout:
                c.thrust_n = 0.0
            if o.gimbal_jam_at_s is not None and self.t >= o.gimbal_jam_at_s:
                c.gimbal_yaw, c.gimbal_pitch = self.st.gimbal_yaw, self.st.gimbal_pitch
            self.st = step(af, self.st, c, wind, o.dt_flight_s)
            self.stats["thrust_j"] += self.st.thrust_n * max(self.st.vel[0], 0.0) * o.dt_flight_s
        self._energy_second(self.st.thrust_n, self.st.vel[0])
        self.stats["sat_s"] = self.fc.saturated_s
        self.stats["hull_s"] += 1.0
        rpy = euler_from_quat(self.st.quat)
        self.stats["max_pitch"] = max(self.stats["max_pitch"], abs(math.degrees(rpy[1])))
        self.stats["max_roll"] = max(self.stats["max_roll"], abs(math.degrees(rpy[0])))
        # wind estimate: ground velocity minus air velocity, 60 s low-pass
        rot = quat_to_matrix(self.st.quat)
        air_n = rot[0][0] * self.st.vel[0] + rot[0][1] * self.st.vel[1] + rot[0][2] * self.st.vel[2]
        air_e = rot[1][0] * self.st.vel[0] + rot[1][1] * self.st.vel[1] + rot[1][2] * self.st.vel[2]
        self.wind_est[0] += (wv.north_m_s - self.wind_est[0]) / 60.0
        self.wind_est[1] += (wv.east_m_s - self.wind_est[1]) / 60.0
        self.t += 1.0
        self._air_ne = (air_n, air_e)
        if a.burst:
            self.log("BURST")
            self._terminate("burst")
            return
        if abs(rpy[1]) > math.radians(75.0):
            self.log(f"LOSS OF CONTROL: pitch {math.degrees(rpy[1]):.0f} deg")
            self._terminate("loss of control")
            return
        self._phases()

    def terminate(self, why: str = "commanded") -> None:
        if self.mode in ("bubble", "hull"):
            self._terminate(why)

    def _terminate(self, why: str) -> None:
        a = self.asc
        a.z = self.z
        if self.mode == "hull":
            a.north, a.east = self.st.pos[0], self.st.pos[1]
        a.t = self.t
        self.log(f"terminate: {why}")
        a.terminate()
        self.mode = "descent"
        self.phase = FlightPhase.DESCENT

    def _phases(self) -> None:
        z, w = self.z, self.climb
        self.max_alt = max(self.max_alt, z)
        ctl = self.float_ctl
        if self.phase == FlightPhase.ASCENT and z > self.cfg.target_float_m - ctl.approach_m:
            self.phase = FlightPhase.FLOAT_ENTRY
            self.log(f"float entry, climb {w:.2f} m/s")
        # A zero-pressure hull is at float when it has filled, not merely slowed.
        if self.zero_p:
            settled = self.phase == FlightPhase.FLOAT_ENTRY and \
                self.float_ctl.spill_finished(self.asc.fill, w, 1.0)
        else:
            settled = abs(z - self.cfg.target_float_m) < 1500.0
        if self.phase == FlightPhase.FLOAT_ENTRY and settled and (abs(w) < 0.3 or self.zero_p):
            self.phase = FlightPhase.STATION_KEEP
            self.float_entry_t = self.t
            if self.zero_p:
                self.float_ctl.settle(self.max_alt)
            self.log(f"at float, {math.hypot(self.north, self.east)/1000:.1f} km downrange")
        rng = math.hypot(self.north, self.east)
        if self.phase == FlightPhase.STATION_KEEP:
            self.stats["float_alts"].append(z)
            self.stats["station_err"].append(rng)
            if self.mode == "hull":
                self.stats["pitch"].append(math.degrees(euler_from_quat(self.st.quat)[1]))
        if self.mode in ("bubble", "hull") and not self.o.external:
            term, why = self.fence.must_terminate(rng, z, self.t)
            if self.phase == FlightPhase.STATION_KEEP and self.float_entry_t is not None and \
                    self.t - self.float_entry_t >= self.o.float_duration_s:
                term, why = True, "mission complete"
            if term:
                self._terminate(why)

    def run(self) -> dict:
        next_rec = 0.0
        while self.phase != FlightPhase.LANDED and self.t < self.o.max_time_s + 4 * 3600:
            self.step_second()
            if self.t >= next_rec:
                row = {"t_s": self.t, "alt_m": round(self.z, 1), "climb": round(self.climb, 3),
                       "north_m": round(self.north), "east_m": round(self.east),
                       "phase": self.phase.value, "mode": self.mode,
                       "fill": round(self.asc.fill, 4)}
                if self.mode == "hull":
                    r, p, y = euler_from_quat(self.st.quat)
                    row.update(pitch_deg=round(math.degrees(p), 2), roll_deg=round(math.degrees(r), 2),
                               yaw_deg=round(math.degrees(y), 1), airspeed=round(self.st.vel[0], 2),
                               thrust_n=round(self.st.thrust_n, 2),
                               gimbal_pitch_deg=round(math.degrees(self.st.gimbal_pitch), 1))
                self.rows.append(row)
                next_rec += self.o.record_every_s
        return self.summary()

    def summary(self) -> dict:
        s = self.stats
        fa = s["float_alts"]
        mean = sum(fa) / len(fa) if fa else None
        return {
            "design": self.dp.mission["name"],
            "reached_float": self.float_entry_t is not None,
            "time_to_float_min": None if self.float_entry_t is None else round(self.float_entry_t / 60, 1),
            "float_mean_m": None if mean is None else round(mean),
            "float_sd_m": None if mean is None else round(math.sqrt(
                sum((x - mean) ** 2 for x in fa) / len(fa))),
            "float_min_m": None if not fa else round(min(fa)),
            "station_error_end_km": None if not s["station_err"] else round(s["station_err"][-1] / 1000, 1),
            "station_error_start_km": None if not s["station_err"] else round(s["station_err"][0] / 1000, 1),
            "mean_abs_pitch_at_float_deg": None if not s["pitch"] else round(
                sum(abs(p) for p in s["pitch"]) / len(s["pitch"]), 1),
            "max_pitch_deg": round(s["max_pitch"], 1), "max_roll_deg": round(s["max_roll"], 1),
            "gimbal_saturated_fraction": round(s["sat_s"] / max(s["hull_s"], 1.0), 3),
            "mean_thrust_power_w": round(s["thrust_j"] / max(s["hull_s"], 1.0), 1),
            "ballast_used_kg": round(self.cfg.ballast_kg - self.asc.ballast, 3),
            "battery_min_soc": round(self.energy["min_soc"], 3),
            "battery_end_soc": round(self.batt_wh / self.batt_full_wh, 3),
            "propulsion_wh": round(self.energy["prop_wh"], 1),
            "hotel_wh": round(self.energy["hotel_wh"], 1),
            "solar_wh": round(self.energy["solar_wh"], 1),
            "solar_unused_wh": round(self.energy["spilled_wh"], 1),
            "peak_propulsion_w": round(self.energy["peak_prop_w"], 1),
            "brownout_min": round(self.energy["brownout_s"] / 60.0, 1),
            "gas_vented_kg": round(self.asc.vented, 3),
            "landing_range_km": round(self.asc.range_m / 1000, 1),
            "flight_time_h": round(self.t / 3600, 2),
            "airframe_rebuilds": self.rebuilds, "final_phase": self.phase.value,
            "events": self.events,
        }


def main(argv: list[str]) -> int:
    from .sizing import ladder
    pts = ladder()
    keys = [a for a in argv if not a.startswith("--")] or ["S1-touch/hull", "S2-dayloiter/hull"]
    hours = next((float(a.split("=")[1]) for a in argv if a.startswith("--float-hours=")), 1.0)
    for key in keys:
        res = UnifiedSim(pts[key], MissionOptions(float_duration_s=hours * 3600.0,
                                                  max_time_s=(hours + 6) * 3600.0)).run()
        if "--json" in argv:
            print(json.dumps(res, indent=2))
            continue
        print(f"=== {key}")
        for k, v in res.items():
            if k != "events":
                print(f"  {k:30s} {v}")
        for e in res["events"]:
            print(f"  [{e['t_s']/60:6.1f} min {e['alt_m']:7.0f} m] {e['event']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
