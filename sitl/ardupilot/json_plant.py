#!/usr/bin/env python3
"""ArduPilot SITL JSON physics backend for the aiur stratospheric airship.

ArduPilot SITL (``--model JSON:127.0.0.1``) sends one binary servo packet per
simulation frame to UDP port 9002 and blocks until a JSON state line comes
back.  This process is that backend: the physics is
``aiur.strato.flight6dof`` unchanged (same ``Airframe``, same ``step``), so
whatever ArduPilot flies here is the vehicle the in-repo controller flies.

Protocol (libraries/SITL/examples/JSON/readme.md, ArduPilot Rover-4.7.3):

    SITL -> plant   struct { uint16 magic=18458; uint16 frame_rate;
                             uint32 frame_count; uint16 pwm[16]; }   (40 bytes)
                    magic 29569 and pwm[32] when SERVO_32_ENABLE=1   (72 bytes)
    plant -> SITL   "\n" + JSON + "\n" with timestamp (s, absolute physics
                    time), imu.gyro, imu.accel_body, position (NED m),
                    quaternion, velocity (NED m/s); optionally airspeed
                    (true airspeed, m/s), which is sent here

Lock-step: exactly one physics step of ``--dt`` seconds per *new* frame_count
and exactly one reply per packet.  ArduPilot advances its clock by the
difference between consecutive timestamps, so simulated time is whatever the
plant says it is, at any wall-clock speed.  A repeated frame_count (ArduPilot
re-sends after 1 s of silence) is answered with the previous state and no
step; a frame_count that goes backwards means SITL restarted, and the plant
resets.

Channel mapping (see aiur_s2.parm):

    SERVO1  GroundSteering  -> gimbal yaw.  PWM 1500 +/- 500 is -/+ the gimbal
            limit: ArduPilot "steer right" (PWM > 1500) must yaw the nose to
            starboard, and flight6dof's positive gimbal_yaw pushes the stern
            to starboard (nose to port), hence the sign flip.
    SERVO3  Throttle        -> thrust, 1000..2000 -> 0..max_thrust_n
            (unidirectional propeller; anything below 1000 is zero).
    SERVO4  (not a Rover function; driven by Lua or DO_SET_SERVO)
                            -> gimbal pitch.  PWM 1500 +/- 500 is +/- the
            gimbal limit; positive pushes the stern down = nose up.
            PWM 0 (channel unused) is treated as centred.

Accelerometer.  An accelerometer measures specific force: kinematic
acceleration minus gravity.  For a neutrally buoyant vehicle floating level
and still that is (0, 0, -g) in body axes (z down) - one g "upward", supplied
by buoyancy - not zero.  It is computed kinematically, which is exact
whatever the split between rigid and added mass:

    f_b = v_dot + w x v + R^T wind_dot + w_dot x r + w x (w x r) - R^T (0,0,g)

with v the body-axis velocity relative to the air (the flight6dof state),
w the body rate, r the IMU position from the centre of volume, R body->NED.
``R^T wind_dot`` is there because flight6dof carries the hull with the air
mass: when the wind changes, the inertial velocity changes with it.

Standard library only.  Run with Python >= 3.10.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import socket
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aiur.strato import flight6dof as f6  # noqa: E402
from aiur.strato.atmosphere import G0, Gust  # noqa: E402
from aiur.strato.sizing import ladder  # noqa: E402

MAGIC_16 = 18458
MAGIC_32 = 29569
GUST_DT = 0.05  # the in-repo scenarios draw the gust at 20 Hz; keep its statistics


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class Plant:
    def __init__(self, args) -> None:
        self.args = args
        dp = ladder()[args.design]
        self.af = f6.Airframe.from_design(dp)
        self.dt = args.dt
        self.imu_r = (args.imu_x, 0.0, self.af.rg[2] if args.imu_z is None else args.imu_z)
        self.log = open(args.log, "w") if args.log else None
        if self.log:
            self.log.write("t,n,e,d,roll_deg,pitch_deg,yaw_deg,u,v,w,r_deg_s,thrust_n,"
                           "gimbal_yaw_deg,gimbal_pitch_deg,pwm1,pwm3,pwm4,wind_n,wind_e,"
                           "vn,ve,vd,az\n")
        self.reset()

    def reset(self) -> None:
        a = self.args
        self.t = 0.0
        self.steps = 0
        self.st = f6.State(pos=(0.0, 0.0, 0.0),
                           quat=f6.quat_from_euler(0.0, 0.0, math.radians(a.yaw_deg)),
                           vel=(a.airspeed0, 0.0, 0.0))
        self.gust = Gust(a.gust, 20.0, seed=a.gust_seed) if a.gust > 0.0 else None
        self.g0 = (0.0, 0.0, 0.0)
        self.g1 = self.gust.step(GUST_DT) if self.gust else (0.0, 0.0, 0.0)
        self.gust_phase = 0.0
        self.next_log = 0.0
        self.last_pwm = (1500, 0, 1000, 1500)
        self.reply = self.pack(self.wind_at(0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    # --- wind -----------------------------------------------------------
    def wind_at(self, t: float):
        """Mean wind (NED) and its time derivative; ramped in so that an EKF
        that is still aligning does not see the platform being carried off."""

        a = self.args
        if a.wind_ramp_s <= 0.0:
            k, kd = (1.0 if t >= a.wind_start_s else 0.0), 0.0
        else:
            x = (t - a.wind_start_s) / a.wind_ramp_s
            k = max(0.0, min(1.0, x))
            kd = 1.0 / a.wind_ramp_s if 0.0 < x < 1.0 else 0.0
        w = tuple(k * c for c in a.wind)
        wd = tuple(kd * c for c in a.wind)
        return w, wd

    def gust_at(self):
        """Gust drawn every GUST_DT and interpolated linearly between draws,
        so its rate is piecewise constant and the accelerometer sees the same
        gust accelerations as the 20 Hz in-repo scenarios."""

        if not self.gust:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        f = self.gust_phase / GUST_DT
        val = tuple(self.g0[i] + (self.g1[i] - self.g0[i]) * f for i in range(3))
        rate = tuple((self.g1[i] - self.g0[i]) / GUST_DT for i in range(3))
        return val, rate

    # --- one frame ------------------------------------------------------
    def controls(self, pwm) -> f6.Controls:
        af, a = self.af, self.args
        lim = af.gimbal_limit_rad
        steer = (pwm[a.ch_steer - 1] - 1500) / 500.0
        thr = (pwm[a.ch_throttle - 1] - 1000) / 1000.0
        p4 = pwm[a.ch_pitch - 1]
        pit = 0.0 if p4 < 800 else (p4 - 1500) / 500.0
        steer = max(-1.0, min(1.0, steer))
        thr = max(0.0, min(1.0, thr))
        pit = max(-1.0, min(1.0, pit))
        self.last_pwm = (pwm[a.ch_steer - 1], 0, pwm[a.ch_throttle - 1], p4)
        return f6.Controls(thrust_n=thr * af.max_thrust_n, gimbal_yaw=-steer * lim,
                           gimbal_pitch=pit * lim)

    def advance(self, pwm) -> None:
        af, dt = self.af, self.dt
        ctl = self.controls(pwm)
        w_mean, w_mean_dot = self.wind_at(self.t)
        g, g_dot = self.gust_at()
        wind = (w_mean[0] + g[0], w_mean[1] + g[1], w_mean[2] + g[2])
        wind_dot = (w_mean_dot[0] + g_dot[0], w_mean_dot[1] + g_dot[1], w_mean_dot[2] + g_dot[2])
        if self.gust:
            # Frozen-turbulence rotational gust, as flight6dof.station_keep does.
            gb = f6._mat_t_vec(f6.quat_to_matrix(self.st.quat), g_dot)
            speed = math.sqrt(sum(c * c for c in self.st.vel))
            af.gust_rot = (gb[2] / max(speed, 2.0), -gb[1] / max(speed, 2.0))
        self.st = f6.step(af, self.st, ctl, wind, dt)
        self.t += dt
        self.steps += 1
        if self.gust:
            self.gust_phase += dt
            if self.gust_phase >= GUST_DT - 1e-9:
                self.gust_phase -= GUST_DT
                self.g0, self.g1 = self.g1, self.gust.step(GUST_DT)
        # State derivative at the new state gives the accelerations the IMU sees.
        _, _, v_dot, w_dot = f6.derivative(af, self.st, ctl, wind)
        self.reply = self.pack((wind, wind_dot), v_dot, w_dot)

    def pack(self, wind_pair, v_dot, w_dot) -> bytes:
        wind, wind_dot = wind_pair
        st = self.st
        rot = f6.quat_to_matrix(st.quat)
        v, om, r = st.vel, st.rate, self.imu_r
        g_b = f6._mat_t_vec(rot, (0.0, 0.0, G0))
        wd_b = f6._mat_t_vec(rot, wind_dot)
        c1 = _cross(om, v)
        c2 = _cross(w_dot, r)
        c3 = _cross(om, _cross(om, r))
        acc = tuple(v_dot[i] + c1[i] + wd_b[i] + c2[i] + c3[i] - g_b[i] for i in range(3))
        v_ned = f6._mat_vec(rot, v)
        v_ned = (v_ned[0] + wind[0], v_ned[1] + wind[1], v_ned[2] + wind[2])
        msg = {
            "timestamp": round(self.t, 6),
            "imu": {"gyro": [round(c, 7) for c in om], "accel_body": [round(c, 6) for c in acc]},
            "position": [round(c, 4) for c in st.pos],
            "quaternion": [round(c, 8) for c in st.quat],
            "velocity": [round(c, 5) for c in v_ned],
            # TRUE airspeed along the body x axis, for ArduPilot's SITL airspeed
            # sensor (ARSPD_TYPE 100); SITL converts it to equivalent airspeed
            # and a differential pressure itself.  Ignored unless ARSPD is set.
            "airspeed": round(max(v[0], 0.0), 5),
        }
        if self.log and self.t >= self.next_log:
            self.next_log += self.args.log_dt
            roll, pitch, yaw = f6.euler_from_quat(st.quat)
            p = self.last_pwm
            self.log.write(
                f"{self.t:.3f},{st.pos[0]:.2f},{st.pos[1]:.2f},{st.pos[2]:.2f},"
                f"{math.degrees(roll):.3f},{math.degrees(pitch):.3f},{math.degrees(yaw):.3f},"
                f"{v[0]:.3f},{v[1]:.3f},{v[2]:.3f},{math.degrees(om[2]):.4f},{st.thrust_n:.3f},"
                f"{math.degrees(st.gimbal_yaw):.2f},{math.degrees(st.gimbal_pitch):.2f},"
                f"{p[0]},{p[2]},{p[3]},{wind[0]:.3f},{wind[1]:.3f},"
                f"{v_ned[0]:.3f},{v_ned[1]:.3f},{v_ned[2]:.3f},{acc[2]:.4f}\n")
            if self.steps % 2000 == 0:
                self.log.flush()
        return ("\n" + json.dumps(msg, separators=(",", ":")) + "\n").encode()


def serve(args) -> int:
    plant = Plant(args)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    af = plant.af
    print(f"json_plant: {args.design} mass {af.mass_kg:.2f} kg, displaced {af.m_disp:.2f} kg, "
          f"L {af.hull.length_m:.1f} m, rho {af.air.density_kg_m3:.4f} kg/m3, "
          f"max thrust {af.max_thrust_n:.2f} N, gimbal +/-{math.degrees(af.gimbal_limit_rad):.0f} deg, "
          f"dt {args.dt} s, wind {args.wind} gust {args.gust}; listening on udp {args.bind}:{args.port}",
          flush=True)
    last_frame = None
    connected = False
    while True:
        data, addr = sock.recvfrom(256)
        if len(data) == 40:
            magic, _rate, frame = struct.unpack_from("<HHI", data)
            if magic != MAGIC_16:
                continue
            pwm = struct.unpack_from("<16H", data, 8)
        elif len(data) == 72:
            magic, _rate, frame = struct.unpack_from("<HHI", data)
            if magic != MAGIC_32:
                continue
            pwm = struct.unpack_from("<32H", data, 8)
        else:
            continue
        if not connected:
            connected = True
            print(f"json_plant: ArduPilot connected from {addr}", flush=True)
        if last_frame is not None and frame < last_frame:
            print("json_plant: frame counter went backwards, resetting physics", flush=True)
            plant.reset()
            last_frame = None
        if last_frame is None or frame > last_frame:
            plant.advance(pwm)
            last_frame = frame
        sock.sendto(plant.reply, addr)
        if args.duration and plant.t >= args.duration:
            break
    if plant.log:
        plant.log.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--design", default="S2-dayloiter/hull", help="key into sizing.ladder()")
    ap.add_argument("--dt", type=float, default=0.005, help="physics step per SITL frame, s")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9002)
    ap.add_argument("--wind", type=float, nargs=3, default=(0.0, 0.0, 0.0),
                    metavar=("N", "E", "D"), help="mean wind velocity, NED m/s (direction it blows TO)")
    ap.add_argument("--wind-start-s", type=float, default=0.0)
    ap.add_argument("--wind-ramp-s", type=float, default=0.0)
    ap.add_argument("--gust", type=float, default=0.0, help="gust sigma m/s (0 = none)")
    ap.add_argument("--gust-seed", type=int, default=3)
    ap.add_argument("--yaw-deg", type=float, default=0.0, help="initial heading")
    ap.add_argument("--airspeed0", type=float, default=0.0, help="initial airspeed m/s")
    ap.add_argument("--imu-x", type=float, default=0.0, help="IMU forward of centre of volume, m")
    ap.add_argument("--imu-z", type=float, default=None,
                    help="IMU below centre of volume, m (default: at the CG height)")
    ap.add_argument("--ch-steer", type=int, default=1)
    ap.add_argument("--ch-throttle", type=int, default=3)
    ap.add_argument("--ch-pitch", type=int, default=4)
    ap.add_argument("--log", default="", help="truth CSV path")
    ap.add_argument("--log-dt", type=float, default=0.2)
    ap.add_argument("--duration", type=float, default=0.0, help="stop after this much physics time")
    return serve(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
