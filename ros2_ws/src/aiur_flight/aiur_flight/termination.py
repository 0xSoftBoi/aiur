"""Termination: `aiur.strato.guidance.Geofence`, and nothing else.

On the vehicle this logic runs on the flight-termination unit, a separate
processor on separate cells with its own GNSS, barometer and radio.  It is a
ROS node here so the same criteria are exercised in simulation; it reads
position only, never the autopilot's opinion of its own health.
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Bool, String

from aiur.strato.guidance import Geofence
from aiur_msgs.msg import FlightStatus


class Termination(Node):
    def __init__(self) -> None:
        super().__init__("termination")
        p = self.declare_parameter
        self.fence = Geofence(
            max_range_m=float(p("max_range_m", 150_000.0).value),
            max_altitude_m=float(p("max_altitude_m", 27_000.0).value),
            max_flight_s=float(p("max_flight_s", 16.0 * 3600.0).value))
        self.launch_alt = float(p("launch_altitude_m", 150.0).value)
        self.honour_requests = bool(p("honour_mission_complete", True).value)
        self.t0 = None
        self.fired = False
        self.requested = False
        self.pub = self.create_publisher(Bool, "cmd/terminate", 10)
        self.pub_reason = self.create_publisher(String, "termination/reason", 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)
        self.create_subscription(FlightStatus, "status", self.on_status, 10)
        self.create_subscription(Bool, "termination/command", self.on_command, 10)

    def on_status(self, msg: FlightStatus) -> None:
        if msg.terminate_requested and self.honour_requests:
            self.requested = True

    def on_command(self, msg: Bool) -> None:
        if msg.data:
            self.requested = True

    def on_odom(self, msg: Odometry) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.t0 is None:
            self.t0 = t
        rng = math.hypot(msg.pose.pose.position.x, msg.pose.pose.position.y)
        alt = msg.pose.pose.position.z + self.launch_alt
        term, why = self.fence.must_terminate(rng, alt, t - self.t0, commanded=self.requested)
        if term and not self.fired:
            self.fired = True
            self.get_logger().warn(f"CUT-DOWN: {why} (range {rng/1000:.1f} km, alt {alt:.0f} m)")
            self.pub_reason.publish(String(data=why))
        if self.fired:
            self.pub.publish(Bool(data=True))


def main() -> None:
    rclpy.init()
    node = Termination()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
