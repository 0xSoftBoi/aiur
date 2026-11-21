#!/usr/bin/env python3
"""Fly the aiur airship plant under ArduRover SITL and measure it.

Connects over MAVLink, waits for the EKF and GPS, switches to GUIDED, arms,
and runs one of:

  turn     hold heading H0 at a commanded speed, then step the heading by 90
           degrees.  Reports rise time (to 90 % of the step), overshoot,
           steering saturation and sideslip - the same definitions as
           aiur.strato.flight6dof.handling_report's "step90" block.
  station  constant wind in the plant; fly to a point --upwind-m metres
           upwind of the start and hold it for --duration seconds.  Reports
           final distance and RMS distance over the second half - the same
           definitions as aiur.strato.flight6dof.station_keep.
  hold     arm, sit in GUIDED (boat loiter) for --duration seconds.

All timing is in *simulated* time, taken from time_boot_ms in the telemetry,
so the script behaves the same at any SITL speedup.  Metrics are computed
twice where possible: from ArduPilot's own estimate (EKF, over MAVLink) and
from the plant's truth log (--truth, the CSV json_plant.py writes).

Needs pymavlink (python3.12 in this repo's environment).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time

from pymavlink import mavutil

GUIDED = 15  # Rover custom mode number
EKF_OK = 0x001 | 0x002 | 0x010  # attitude, horizontal velocity, absolute horizontal position
M = mavutil.mavlink


def wrap180(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


class Vehicle:
    def __init__(self, url: str) -> None:
        self.m = mavutil.mavlink_connection(url, source_system=255, autoreconnect=True)
        self.sim_t = 0.0
        self.att = None
        self.pos = None
        self.servo = None
        self.gps_fix = 0
        self.ekf_flags = 0
        self.armed = False
        self.mode = -1
        self.rows = []
        self.texts = []
        self._last_hb = 0.0
        self.recording = False

    def heartbeat(self) -> None:
        now = time.time()
        if now - self._last_hb > 0.5:
            self._last_hb = now
            self.m.mav.heartbeat_send(M.MAV_TYPE_GCS, M.MAV_AUTOPILOT_INVALID, 0, 0, 0)

    def pump(self, timeout: float = 0.5) -> bool:
        """Read one message; return True if it was an ATTITUDE (the tick)."""

        self.heartbeat()
        msg = self.m.recv_match(blocking=True, timeout=timeout)
        if msg is None:
            return False
        t = msg.get_type()
        if hasattr(msg, "time_boot_ms"):
            self.sim_t = max(self.sim_t, msg.time_boot_ms * 1e-3)
        if t == "HEARTBEAT" and msg.get_srcSystem() == self.m.target_system and msg.type != M.MAV_TYPE_GCS:
            self.armed = bool(msg.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED)
            self.mode = msg.custom_mode
        elif t == "ATTITUDE":
            self.att = msg
            if self.recording and self.pos is not None and self.servo is not None:
                p, s = self.pos, self.servo
                self.rows.append((msg.time_boot_ms * 1e-3, math.degrees(msg.yaw), math.degrees(msg.pitch),
                                  math.degrees(msg.roll), math.degrees(msg.yawspeed),
                                  p.x, p.y, p.z, p.vx, p.vy, p.vz,
                                  s.servo1_raw, s.servo3_raw, s.servo4_raw))
            return True
        elif t == "LOCAL_POSITION_NED":
            self.pos = msg
        elif t == "SERVO_OUTPUT_RAW":
            self.servo = msg
        elif t == "GPS_RAW_INT":
            self.gps_fix = msg.fix_type
        elif t == "EKF_STATUS_REPORT":
            self.ekf_flags = msg.flags
        elif t == "STATUSTEXT":
            self.texts.append((round(self.sim_t, 1), msg.text))
            print(f"  [{self.sim_t:8.1f}] AP: {msg.text}", flush=True)
        return False

    def set_rate(self, msg_id: int, hz: float) -> None:
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                     M.MAV_CMD_SET_MESSAGE_INTERVAL, 0, msg_id, 1e6 / hz, 0, 0, 0, 0, 0)

    def wait(self, cond, what: str, wall_timeout: float = 120.0) -> None:
        t0 = time.time()
        while not cond():
            self.pump(0.2)
            if time.time() - t0 > wall_timeout:
                raise TimeoutError(f"timed out waiting for {what} (sim t={self.sim_t:.1f} s, "
                                   f"ekf=0x{self.ekf_flags:x}, gps fix={self.gps_fix}, texts={self.texts[-5:]})")

    def run_until(self, t_end: float, on_tick=None, wall_timeout: float = 3600.0) -> None:
        t0 = time.time()
        while self.sim_t < t_end:
            if self.pump() and on_tick:
                on_tick()
            if time.time() - t0 > wall_timeout:
                raise TimeoutError(f"wall timeout at sim t={self.sim_t:.1f} s")

    def start(self, rate_hz: float) -> None:
        self.m.wait_heartbeat(timeout=60)
        print(f"heartbeat from system {self.m.target_system}", flush=True)
        for mid in (M.MAVLINK_MSG_ID_ATTITUDE, M.MAVLINK_MSG_ID_LOCAL_POSITION_NED,
                    M.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW):
            self.set_rate(mid, rate_hz)
        for mid in (M.MAVLINK_MSG_ID_GPS_RAW_INT, M.MAVLINK_MSG_ID_EKF_STATUS_REPORT):
            self.set_rate(mid, 1.0)
        self.wait(lambda: self.gps_fix >= 3 and (self.ekf_flags & EKF_OK) == EKF_OK and self.pos is not None,
                  "GPS 3D fix and EKF attitude/velocity/position")
        print(f"[{self.sim_t:8.1f}] EKF ok (flags 0x{self.ekf_flags:x}), GPS fix {self.gps_fix}", flush=True)
        self.m.mav.set_mode_send(self.m.target_system, M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, GUIDED)
        self.wait(lambda: self.mode == GUIDED, "GUIDED mode")
        t_arm = 0.0

        def armed() -> bool:
            nonlocal t_arm
            if not self.armed and time.time() - t_arm > 2.0:
                t_arm = time.time()
                self.m.mav.command_long_send(self.m.target_system, self.m.target_component,
                                             M.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
            return self.armed
        self.wait(armed, "arming")
        print(f"[{self.sim_t:8.1f}] armed in GUIDED", flush=True)

    def set_param(self, name: str, value: float) -> None:
        got = [None]
        t_send = 0.0

        def done() -> bool:
            nonlocal t_send
            if time.time() - t_send > 1.0:
                t_send = time.time()
                self.m.mav.param_set_send(self.m.target_system, self.m.target_component,
                                          name.encode(), value, M.MAV_PARAM_TYPE_REAL32)
            msg = self.m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.2)
            if msg is not None and msg.param_id == name:
                got[0] = msg.param_value
            return got[0] is not None
        self.wait(done, f"PARAM_VALUE {name}", 20.0)
        print(f"  param {name} = {got[0]:g}", flush=True)

    # --- setpoints ------------------------------------------------------
    def heading_speed(self, heading_deg: float, speed: float) -> None:
        """Rover GUIDED 'heading and speed': a velocity vector, no position.
        Rover stops if this is not refreshed every 3 s (simulated)."""

        h = math.radians(heading_deg)
        mask = 0b0000_1101_1100_0111  # velocity only
        self.m.mav.set_position_target_local_ned_send(
            int(self.sim_t * 1e3), self.m.target_system, self.m.target_component,
            M.MAV_FRAME_LOCAL_NED, mask, 0, 0, 0,
            speed * math.cos(h), speed * math.sin(h), 0, 0, 0, 0, 0, 0)

    def heading_groundspeed(self, heading_deg: float, ground_speed: float, speed_default: float) -> None:
        """Explicit heading plus a *signed* ground speed, via SET_ATTITUDE_TARGET
        (yaw from the quaternion, speed = thrust x WP_SPEED).  Signed matters:
        "fall back with the wind, bow first" is a negative ground speed.

        SET_POSITION_TARGET_LOCAL_NED with yaw + velocity cannot be used for
        this: Rover 4.7.3 takes the sign of the speed from the sign of the
        NORTH velocity component (GCS_MAVLink_Rover.cpp, "we are using the
        x-axis velocity to determine direction"), so any easterly heading
        with a rounding-negative vx is flown in reverse.  Found the hard way
        (tuning log, c1)."""

        h = math.radians(heading_deg)
        q = (math.cos(h / 2), 0.0, 0.0, math.sin(h / 2))
        thrust = max(-1.0, min(1.0, ground_speed / speed_default))
        self.m.mav.set_attitude_target_send(
            int(self.sim_t * 1e3), self.m.target_system, self.m.target_component,
            0b0000_0111, q, 0, 0, 0, thrust)

    def goto_local(self, north: float, east: float) -> None:
        mask = 0b0000_1101_1111_1000  # position only
        self.m.mav.set_position_target_local_ned_send(
            int(self.sim_t * 1e3), self.m.target_system, self.m.target_component,
            M.MAV_FRAME_LOCAL_NED, mask, north, east, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def load_truth(path: str, t0: float, t1: float, offset: float):
    out = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            try:
                t = float(row["t"]) + offset
            except (TypeError, ValueError):
                continue
            if t0 <= t <= t1:
                try:
                    out.append({k: float(v) for k, v in row.items()} | {"t": t})
                except (TypeError, ValueError):
                    pass  # a line still being written
    return out


def step_metrics(ts, yaws, h0, step, t_step):
    """rise time to 90 % of the step, overshoot, settling (within 5 deg)."""

    target = h0 + step
    sgn = 1.0 if step >= 0 else -1.0
    prog = [sgn * wrap180(y - h0) for y in yaws]  # progress along the step, deg
    rise = next((t - t_step for t, p in zip(ts, prog) if t >= t_step and p >= 0.9 * abs(step)), None)
    over = max((p for t, p in zip(ts, prog) if t >= t_step), default=float("nan")) - abs(step)
    settle = None
    for t, y in zip(reversed(ts), reversed(yaws)):
        if abs(wrap180(y - target)) > 5.0:
            settle = t - t_step
            break
    final_err = wrap180(yaws[-1] - target) if yaws else float("nan")
    return {"rise_time_s": None if rise is None else round(rise, 1), "overshoot_deg": round(over, 1),
            "settle_5deg_s": None if settle is None else round(max(settle, 0.0), 1),
            "final_error_deg": round(final_err, 2)}


def test_turn(v: Vehicle, a) -> dict:
    h0, h1 = a.heading0, a.heading0 + a.step
    t0 = v.sim_t
    last = [0.0]

    def tick(h):
        def f():
            if v.sim_t - last[0] >= 0.5:
                last[0] = v.sim_t
                v.heading_speed(h, a.speed)
        return f
    print(f"[{v.sim_t:8.1f}] turn test: heading {h0:g} deg at {a.speed:g} m/s for {a.settle:g} s", flush=True)
    v.recording = True
    v.run_until(t0 + a.settle, tick(h0))
    t_step = v.sim_t
    pre = [r for r in v.rows if r[0] >= t_step - 60.0]
    print(f"[{v.sim_t:8.1f}] step to {h1:g} deg", flush=True)
    v.run_until(t_step + a.duration, tick(h1))
    t_end = v.sim_t
    rows = [r for r in v.rows if r[0] >= t_step]
    ts = [r[0] for r in rows]
    res = {"test": "turn", "speed_cmd_m_s": a.speed, "heading0_deg": h0, "step_deg": a.step,
           "t_step_s": round(t_step, 1), "t_end_s": round(t_end, 1)}
    res["pre_step"] = {
        "rms_heading_error_deg": round(math.sqrt(sum(wrap180(r[1] - h0) ** 2 for r in pre) / max(len(pre), 1)), 2),
        "mean_ground_speed_m_s": round(sum(math.hypot(r[8], r[9]) for r in pre) / max(len(pre), 1), 2),
        "mean_throttle_pct": round(sum((r[12] - 1000) / 10.0 for r in pre) / max(len(pre), 1), 1)}
    ekf = step_metrics(ts, [r[1] for r in rows], h0, a.step, t_step)
    ekf["steering_saturated_fraction"] = round(sum(1 for r in rows if abs(r[11] - 1500) >= 490) / max(len(rows), 1), 3)
    ekf["max_abs_steer_pwm_offset"] = max((abs(r[11] - 1500) for r in rows), default=0)
    ekf["max_turn_rate_deg_s"] = round(max((abs(r[4]) for r in rows), default=0.0), 2)
    res["ekf"] = ekf
    if a.truth:
        time.sleep(0.5)
        tr = load_truth(a.truth, t_step, t_end, a.truth_offset)
        if tr:
            tm = step_metrics([r["t"] for r in tr], [r["yaw_deg"] for r in tr], h0, a.step, t_step)
            tm["gimbal_saturated_fraction"] = round(
                sum(1 for r in tr if abs(r["gimbal_yaw_deg"]) >= 24.5) / len(tr), 3)
            tm["max_sideslip_deg"] = round(max(abs(math.degrees(math.atan2(r["v"], max(abs(r["u"]), 0.05))))
                                               for r in tr), 1)
            tm["min_airspeed_m_s"] = round(min(r["u"] for r in tr), 2)
            tm["max_thrust_n"] = round(max(r["thrust_n"] for r in tr), 2)
            tm["altitude_change_m"] = round(-(tr[-1]["d"] - tr[0]["d"]), 1)
            tm["max_abs_pitch_deg"] = round(max(abs(r["pitch_deg"]) for r in tr), 2)
            res["truth"] = tm
    return res


def test_station(v: Vehicle, a) -> dict:
    # wait for the plant's wind ramp to finish, holding in boat loiter
    if v.sim_t < a.start_after:
        print(f"[{v.sim_t:8.1f}] holding until t={a.start_after:g} s (wind ramp)", flush=True)
        v.run_until(a.start_after)
    wn, we = a.wind[0], a.wind[1]
    wmag = math.hypot(wn, we)
    un, ue = ((-wn / wmag, -we / wmag) if wmag > 0 else (1.0, 0.0))
    n0, e0 = v.pos.x, v.pos.y
    tn, te = n0 + un * a.upwind_m, e0 + ue * a.upwind_m
    t0 = v.sim_t
    print(f"[{t0:8.1f}] station test: from N {n0:.0f} E {e0:.0f} to N {tn:.0f} E {te:.0f} "
          f"({a.upwind_m:g} m upwind), {a.duration:g} s", flush=True)
    v.recording = True
    last = [0.0, 0.0]

    keeper = None
    if a.guidance == "companion":
        # The in-repo outer loop, unchanged, standing in for the companion
        # computer: position error + wind estimate -> heading and airspeed.
        # Rover's speed loop works on ground speed, so the airspeed demand
        # is converted with the same wind estimate.  The estimate is the
        # plant's mean wind (flight6dof.station_keep uses the truth wind
        # low-passed over 60 s; neither is a real estimator).
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
        from aiur.strato.guidance import StationKeeper
        keeper = StationKeeper(a.max_airspeed)
        # SET_ATTITUDE_TARGET thrust is a fraction of WP_SPEED
        v.set_param("WP_SPEED", a.max_airspeed)

    def tick():
        if keeper is not None:
            if v.sim_t - last[0] >= 1.0:
                last[0] = v.sim_t
                c = keeper.command(tn - v.pos.x, te - v.pos.y, wn, we)
                h = c.heading_rad
                gs = c.airspeed_m_s + wn * math.cos(h) + we * math.sin(h)
                v.heading_groundspeed(math.degrees(h), gs, a.max_airspeed)
        # stock guidance: the target is sent once (re-sent rarely if asked)
        elif last[0] == 0.0 or v.sim_t - last[0] >= 300.0 and v.mode == GUIDED and a.resend:
            last[0] = v.sim_t
            v.goto_local(tn, te)
        if v.sim_t - last[1] >= 120.0:
            last[1] = v.sim_t
            d = math.hypot(v.pos.x - tn, v.pos.y - te)
            print(f"  [{v.sim_t:8.1f}] dist {d:7.1f} m  yaw {math.degrees(v.att.yaw):6.1f}  "
                  f"thr {(v.servo.servo3_raw - 1000) / 10:5.1f}%  steer {v.servo.servo1_raw}  "
                  f"alt {-v.pos.z:7.1f} m", flush=True)
    v.run_until(t0 + a.duration, tick, wall_timeout=7200.0)
    t1 = v.sim_t
    rows = [r for r in v.rows if r[0] >= t0]
    half = [r for r in rows if r[0] >= t0 + 0.5 * a.duration]
    dist = lambda r: math.hypot(r[5] - tn, r[6] - te)  # noqa: E731
    res = {"test": "station", "guidance": a.guidance, "wind_ned": list(a.wind), "upwind_m": a.upwind_m, "duration_s": a.duration,
           "t_start_s": round(t0, 1), "t_end_s": round(t1, 1), "target_ne": [round(tn, 1), round(te, 1)]}
    arrive = next((r[0] - t0 for r in rows if dist(r) <= 50.0), None)
    res["ekf"] = {
        "final_distance_m": round(dist(rows[-1]), 1),
        "rms_distance_second_half_m": round(math.sqrt(sum(dist(r) ** 2 for r in half) / max(len(half), 1)), 1),
        "max_distance_second_half_m": round(max(dist(r) for r in half), 1),
        "time_to_within_50m_s": None if arrive is None else round(arrive, 0),
        "altitude_excursion_m": round(max(abs(r[7] - rows[0][7]) for r in rows), 1),
        "steering_saturated_fraction": round(sum(1 for r in rows if abs(r[11] - 1500) >= 490) / len(rows), 3),
        "throttle_saturated_fraction": round(sum(1 for r in rows if r[12] >= 1990) / len(rows), 3),
        "mean_throttle_pct": round(sum((r[12] - 1000) / 10.0 for r in rows) / len(rows), 1)}
    if a.truth:
        time.sleep(0.5)
        tr = load_truth(a.truth, t0, t1, a.truth_offset)
        if tr:
            # Truth position is in the plant's frame.  The EKF origin is
            # wherever the vehicle was when the EKF set it (it drifts with
            # the gust before that), so shift the target by the offset
            # between the two frames measured at the start of the test.
            on, oe = n0 - tr[0]["n"], e0 - tr[0]["e"]
            td = lambda r: math.hypot(r["n"] - (tn - on), r["e"] - (te - oe))  # noqa: E731
            th = [r for r in tr if r["t"] >= t0 + 0.5 * a.duration]
            res["truth"] = {
                "final_distance_m": round(td(tr[-1]), 1),
                "rms_distance_second_half_m": round(math.sqrt(sum(td(r) ** 2 for r in th) / max(len(th), 1)), 1),
                "max_distance_second_half_m": round(max(td(r) for r in th), 1),
                "altitude_excursion_m": round(max(abs(r["d"] - tr[0]["d"]) for r in tr), 1),
                "mean_thrust_power_w": round(sum(r["thrust_n"] * max(r["u"], 0.0) for r in tr) / len(tr), 2),
                "mean_airspeed_m_s": round(sum(r["u"] for r in tr) / len(tr), 2),
                "max_airspeed_m_s": round(max(r["u"] for r in tr), 2),
                "gimbal_saturated_fraction": round(
                    sum(1 for r in tr if abs(r["gimbal_yaw_deg"]) >= 24.5) / len(tr), 3),
                "max_abs_pitch_deg": round(max(abs(r["pitch_deg"]) for r in tr), 2),
                "ekf_origin_offset_ne_m": [round(on, 1), round(oe, 1)],
                "ekf_position_error_final_m": round(math.hypot(rows[-1][5] - on - tr[-1]["n"],
                                                               rows[-1][6] - oe - tr[-1]["e"]), 2)}
    return res


def test_hold(v: Vehicle, a) -> dict:
    t0 = v.sim_t
    v.recording = True
    v.run_until(t0 + a.duration)
    rows = v.rows
    return {"test": "hold", "duration_s": a.duration,
            "drift_m": round(math.hypot(rows[-1][5] - rows[0][5], rows[-1][6] - rows[0][6]), 1),
            "altitude_excursion_m": round(max(abs(r[7] - rows[0][7]) for r in rows), 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("test", choices=("turn", "station", "hold"))
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    ap.add_argument("--rate", type=float, default=5.0, help="telemetry rate, Hz of simulated time")
    ap.add_argument("--truth", default="", help="json_plant.py truth CSV")
    ap.add_argument("--truth-offset", type=float, default=0.0,
                    help="time_boot_ms minus plant time, s (measured ~0)")
    ap.add_argument("--out", default="", help="write the result JSON here")
    ap.add_argument("--series", default="", help="write the recorded EKF time series CSV here")
    # turn
    ap.add_argument("--speed", type=float, default=6.0, help="commanded ground speed, m/s")
    ap.add_argument("--heading0", type=float, default=0.0)
    ap.add_argument("--step", type=float, default=90.0)
    ap.add_argument("--settle", type=float, default=240.0)
    # station
    ap.add_argument("--wind", type=float, nargs=3, default=(0.0, -4.0, 0.0), metavar=("N", "E", "D"),
                    help="the wind the plant was started with (to find 'upwind')")
    ap.add_argument("--upwind-m", type=float, default=1500.0)
    ap.add_argument("--start-after", type=float, default=0.0, help="sim time at which the plant wind is steady")
    ap.add_argument("--guidance", choices=("rover", "companion"), default="rover",
                    help="rover: one GUIDED position target, then Rover's boat loiter.  companion: "
                         "aiur.strato.guidance.StationKeeper here, sending heading+speed at 1 Hz")
    ap.add_argument("--max-airspeed", type=float, default=6.0, help="companion guidance airspeed limit")
    ap.add_argument("--resend", action="store_true", help="re-send the position target every 300 s")
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="set an ArduPilot parameter after arming (repeatable)")
    a = ap.parse_args(argv)

    v = Vehicle(a.connect)
    v.start(a.rate)
    for item in a.set:
        name, _, val = item.partition("=")
        v.set_param(name, float(val))
    res = {"turn": test_turn, "station": test_station, "hold": test_hold}[a.test](v, a)
    res["statustext"] = v.texts
    print(json.dumps(res, indent=2))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(res, fh, indent=2)
    if a.series:
        with open(a.series, "w") as fh:
            fh.write("t,yaw_deg,pitch_deg,roll_deg,yawrate_deg_s,n,e,d,vn,ve,vd,servo1,servo3,servo4\n")
            for r in v.rows:
                fh.write(",".join(f"{c:.3f}" if isinstance(c, float) else str(c) for c in r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
