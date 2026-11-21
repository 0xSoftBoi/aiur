#!/usr/bin/env python3
"""Cross-check: fins on Gazebo's stock LiftDrag against the in-repo 6-DoF.

Flies every case in ``worlds/fins/cases.json`` in Gazebo (one headless server
per case, started by gz_fins_run.py from the same initial state and thrust as
the Python run), listens to the odometry bridged into ROS, and prints one
GZ_FINS line per case with both models' numbers side by side.

"turn" is the angle the nose has moved away from where the velocity vector
pointed at the start: positive is divergence (the Munk moment winning),
for yaw and pitch alike.
"""
import json
import math
import os
import subprocess
import sys
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy


def fin_case_metrics(samples):
    """Copy of tools/strato_export.py fin_case_metrics(); keep identical."""

    t10 = next((t for t, a, _ in samples if abs(a) >= 10.0), None)
    t_end, a_end, v_end = samples[-1]
    a_prev = min(samples, key=lambda s: abs(s[0] - (t_end - 10.0)))[1]
    drift = (a_end - a_prev + 180.0) % 360.0 - 180.0
    peak = max((a for _, a, _ in samples), key=abs)
    verdict = "diverges" if t10 is not None else ("settles" if abs(drift) < 0.5 else "drifting")
    return {"t10_s": None if t10 is None else round(t10, 2), "peak_turn_deg": round(peak, 2),
            "turn_end_deg": round(a_end, 2), "drift_last10s_deg": round(drift, 2),
            "airspeed_end_m_s": round(v_end, 3), "verdict": verdict}


class Check(Node):
    def __init__(self) -> None:
        super().__init__("gz_fins_check")
        self.samples = []
        qos = QoSProfile(depth=2000, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(Odometry, "/model/aiur/odometry", self.cb, qos)

    def cb(self, m: Odometry) -> None:
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        if self.samples and t < self.samples[-1][0] - 1.0:
            self.samples.clear()            # a new server has started
        q = m.pose.pose.orientation
        # Nose direction in the world (ENU) from the link's x axis.
        nx = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        ny = 2.0 * (q.x * q.y + q.w * q.z)
        nz = 2.0 * (q.x * q.z - q.w * q.y)
        v = m.twist.twist.linear
        self.samples.append((t, math.degrees(-math.atan2(ny, nx)),          # yaw, + starboard
                             math.degrees(math.asin(max(-1.0, min(1.0, nz)))),  # pitch, + up
                             math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)))


def main() -> None:
    cases_path, worlds, runner = sys.argv[1:4]
    select = sys.argv[4] if len(sys.argv) > 4 else ""
    rtf = float(sys.argv[5]) if len(sys.argv) > 5 else 10.0
    csv_dir = sys.argv[6] if len(sys.argv) > 6 else ""
    with open(cases_path) as fh:
        cases = [c for c in json.load(fh)
                 if not select or select in c["id"] or select == c["group"]]
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
    rclpy.init()
    node = Check()
    for c in cases:
        node.samples.clear()
        cmd = [sys.executable, runner, os.path.join(worlds, c["world"]),
               "--vel-frd", *map(str, c["vel_frd"]), "--thrust", str(c["thrust_n"]),
               "--duration", str(c["duration_s"]), "--mass", str(c["mass_kg"]),
               "--added-mass", *map(str, c["added_mass_kg"]),
               "--com", *map(str, c["com_link_m"]), "--rtf", str(rtf), "--wait", "2"]
        if csv_dir:
            cmd += ["--csv", os.path.join(csv_dir, c["id"] + ".csv")]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        while proc.poll() is None:
            rclpy.spin_once(node, timeout_sec=0.05)
        end = time.time() + 1.0
        while time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        out = {"case": c["id"], "axis": c["axis"], "thrust_n": round(c["thrust_n"], 3),
               "samples": len(node.samples)}
        if proc.returncode or len(node.samples) < 10:
            out["error"] = (proc.stderr.read() or "no odometry received")[-300:]
        else:
            # Gazebo: sideslip to starboard is -y, so divergence is yaw to port;
            # nose-up incidence diverges nose-up.  Same sign rule as the generator.
            col, sign = (2, 1.0) if c["axis"] == "pitch" else (1, -1.0)
            out["sim_time_s"] = round(node.samples[-1][0], 2)
            out["gazebo"] = fin_case_metrics([(s[0], sign * s[col], s[3]) for s in node.samples])
            out["python"] = c["python"]
            g, p = out["gazebo"]["t10_s"], c["python"]["t10_s"]
            if g is not None and p is not None:
                out["t10_gazebo_over_python"] = round(g / p, 3)
        print("GZ_FINS " + json.dumps(out), flush=True)
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
