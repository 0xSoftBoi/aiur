"""Runs for a fixed simulated time, then reports station-keeping and exits.

`relative_time` (default False): count `duration_s` from the first odometry
message instead of from stamp zero, for an autopilot that has been up for a
while before the companion takes over (ArduPilot SITL).
"""

import json
import math
import os

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node

from aiur_msgs.msg import PropulsionCommand


class StationReport(Node):
    def __init__(self) -> None:
        super().__init__("station_report")
        self.duration = float(self.declare_parameter("duration_s", 1800.0).value)
        self.out = self.declare_parameter("output", "/tmp/aiur_station.json").value
        self.relative = bool(self.declare_parameter("relative_time", False).value)
        self.t0 = None
        self.rows, self.thrust, self.sat, self.n = [], 0.0, 0, 0
        self.create_subscription(PropulsionCommand, "cmd/propulsion", self.on_cmd, 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)

    def on_cmd(self, m: PropulsionCommand) -> None:
        self.n += 1
        self.thrust += m.thrust_n
        self.sat += abs(m.gimbal_yaw_rad) > 0.43 or abs(m.gimbal_pitch_rad) > 0.43

    def on_odom(self, m: Odometry) -> None:
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        if self.relative:
            if self.t0 is None:
                self.t0 = t
            t -= self.t0
        p = m.pose.pose.position
        self.rows.append((t, math.hypot(p.x, p.y), p.z))
        if t >= self.duration:
            half = [r for r in self.rows if r[0] > self.duration / 2]
            res = {"sim_time_s": round(t, 0), "start_distance_m": round(self.rows[0][1], 0),
                   "final_distance_m": round(self.rows[-1][1], 0),
                   "rms_distance_second_half_m": round(math.sqrt(
                       sum(r[1] ** 2 for r in half) / len(half)), 0),
                   "altitude_excursion_m": round(max(abs(r[2]) for r in self.rows), 1),
                   "mean_thrust_n": round(self.thrust / max(self.n, 1), 2),
                   "gimbal_saturated_fraction": round(self.sat / max(self.n, 1), 3)}
            os.makedirs(os.path.dirname(self.out) or ".", exist_ok=True)
            with open(self.out, "w") as fh:
                json.dump(res, fh, indent=2)
            self.get_logger().info("STATION_REPORT " + json.dumps(res))
            raise SystemExit(0)


def main() -> None:
    rclpy.init()
    node = StationReport()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
