#!/usr/bin/env python3
"""Cross-check: does Gazebo's stock LTA model agree with the in-repo 6-DoF?

Listens to the Gazebo odometry bridged into ROS while the generated model is
pushed by its cruise thrust, and compares three things that do not depend on
anyone's sign conventions: that the hull is neutrally buoyant, the initial
acceleration (rigid + added mass), and the terminal airspeed (axial drag).
"""
import json
import sys

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node


class Check(Node):
    def __init__(self, expect: dict, duration: float) -> None:
        super().__init__("gz_drag_check")
        self.expect, self.duration = expect, duration
        self.samples = []
        self.create_subscription(Odometry, "/model/aiur/odometry", self.cb, 50)

    def cb(self, m: Odometry) -> None:
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        self.samples.append((t, m.pose.pose.position.x, m.pose.pose.position.z,
                             m.twist.twist.linear.x))
        if t >= self.duration:
            raise SystemExit(0)


def main() -> None:
    expect = json.loads(sys.argv[1])
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    rclpy.init()
    node = Check(expect, duration)
    try:
        rclpy.spin(node)
    except (SystemExit, KeyboardInterrupt):
        pass
    s = node.samples
    early = [x for x in s if 1.0 <= x[0] <= 6.0]
    accel = (early[-1][3] - early[0][3]) / (early[-1][0] - early[0][0]) if len(early) > 2 else None
    out = {
        "samples": len(s), "sim_time_s": s[-1][0] if s else 0,
        "terminal_airspeed_m_s": round(s[-1][3], 3) if s else None,
        "expected_airspeed_m_s": expect["expected_airspeed_m_s"],
        "altitude_drift_m": round(s[-1][2] - s[0][2], 3) if s else None,
        "initial_accel_m_s2": None if accel is None else round(accel, 5),
        "expected_initial_accel_m_s2": round(
            expect["cruise_thrust_n"] / (expect["mass_kg"] + expect["added_mass_x_kg"]), 5),
    }
    print("GZ_CHECK " + json.dumps(out))
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
