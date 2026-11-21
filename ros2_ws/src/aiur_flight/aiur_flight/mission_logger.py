"""Mission logger: writes a CSV track and a JSON summary, exits on landing.

Its exit is what ends a headless simulation run (the launch file shuts down
when this process does), so a mission is a command that returns.
"""

import csv
import json
import math
import os

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import BatteryState
from std_msgs.msg import String

from aiur_msgs.msg import BuoyancyState, FlightStatus


class MissionLogger(Node):
    def __init__(self) -> None:
        super().__init__("mission_logger")
        self.out_dir = self.declare_parameter("output_dir", "/tmp/aiur_mission").value
        self.period = float(self.declare_parameter("log_period_s", 30.0).value)
        os.makedirs(self.out_dir, exist_ok=True)
        self.rows = []
        self.status = None
        self.buoy = None
        self.batt = None
        self.reason = ""
        self.next_log = 0.0
        self.max_alt = 0.0
        self.float_alts = []
        self.float_err = []
        self.phases = []
        self.done = False
        self.create_subscription(FlightStatus, "status", self.on_status, 10)
        self.create_subscription(BuoyancyState, "buoyancy", lambda m: setattr(self, "buoy", m), 10)
        self.create_subscription(BatteryState, "battery", lambda m: setattr(self, "batt", m), 10)
        self.create_subscription(String, "termination/reason",
                                 lambda m: setattr(self, "reason", m.data), 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)

    def on_status(self, msg: FlightStatus) -> None:
        if self.status is None or msg.phase != self.status.phase:
            self.phases.append({"phase": msg.phase, "t_s": round(msg.flight_time_s, 0),
                                "alt_m": round(msg.altitude_m, 0),
                                "range_km": round(msg.range_from_launch_m / 1000.0, 1)})
        self.status = msg
        self.max_alt = max(self.max_alt, msg.altitude_m)
        if msg.phase == "STATION_KEEP":
            self.float_alts.append(msg.altitude_m)
            self.float_err.append(msg.station_error_m)
        if msg.phase == "LANDED" and not self.done:
            self.finish()

    def on_odom(self, msg: Odometry) -> None:
        if self.status is None or self.status.flight_time_s < self.next_log:
            return
        self.next_log = self.status.flight_time_s + self.period
        s, b = self.status, self.buoy
        self.rows.append({
            "t_s": round(s.flight_time_s, 0), "phase": s.phase,
            "alt_m": round(s.altitude_m, 1), "climb_m_s": round(s.climb_rate_m_s, 3),
            "east_m": round(msg.pose.pose.position.x, 0),
            "north_m": round(msg.pose.pose.position.y, 0),
            "fill": round(b.fill_fraction, 4) if b else "",
            "supertemp_k": round(b.supertemperature_k, 2) if b else "",
            "ballast_kg": round(b.ballast_remaining_kg, 3) if b else "",
            "trim": round(s.trim_command, 3),
            "battery": round(self.batt.percentage, 3) if self.batt else "",
        })

    def finish(self) -> None:
        self.done = True
        s = self.status
        mean = sum(self.float_alts) / len(self.float_alts) if self.float_alts else None
        summary = {
            "phases": self.phases,
            "reached_float": bool(self.float_alts),
            "max_altitude_m": round(self.max_alt, 0),
            "float_mean_m": None if mean is None else round(mean, 0),
            "float_sd_m": None if mean is None else round(math.sqrt(
                sum((a - mean) ** 2 for a in self.float_alts) / len(self.float_alts)), 0),
            "station_error_at_float_end_km": None if not self.float_err else round(
                self.float_err[-1] / 1000.0, 1),
            "landing_range_km": round(s.range_from_launch_m / 1000.0, 1),
            "flight_time_h": round(s.flight_time_s / 3600.0, 2),
            "termination_reason": self.reason,
            "battery_remaining": None if self.batt is None else round(self.batt.percentage, 3),
            "ballast_remaining_kg": None if self.buoy is None else round(
                self.buoy.ballast_remaining_kg, 3),
        }
        with open(os.path.join(self.out_dir, "summary.json"), "w") as fh:
            json.dump(summary, fh, indent=2)
        if self.rows:
            with open(os.path.join(self.out_dir, "track.csv"), "w", newline="") as fh:
                w = csv.DictWriter(fh, list(self.rows[0].keys()))
                w.writeheader()
                w.writerows(self.rows)
        self.get_logger().info("mission summary: " + json.dumps(summary))
        raise SystemExit(0)


def main() -> None:
    rclpy.init()
    node = MissionLogger()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
