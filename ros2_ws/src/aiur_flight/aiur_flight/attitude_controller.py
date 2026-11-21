"""Inner loop: `aiur.strato.flight6dof.FlightController` as a ROS node.

Turns the station keeper's air-velocity demand into thrust and gimbal
angles.  Inputs are what the autopilot's estimator provides - attitude and
rates from odometry/IMU, airspeed from the pitot - and the output is the
actuator command the stern pod's CAN node executes.
"""

import math

import rclpy
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Float32

from aiur.strato.flight6dof import Airframe, FlightController
from aiur.strato.sizing import ladder
from aiur_msgs.msg import PropulsionCommand


class AttitudeController(Node):
    def __init__(self) -> None:
        super().__init__("attitude_controller")
        design = self.declare_parameter("design", "S2-dayloiter/hull").value
        self.fc = FlightController.for_airframe(Airframe.from_design(ladder()[design]))
        self.heading = None
        self.airspeed_cmd = 0.0
        self.airspeed = 0.0
        self.thrust = 0.0
        self.last_t = None
        self.pub = self.create_publisher(PropulsionCommand, "cmd/propulsion", 10)
        self.create_subscription(TwistStamped, "cmd/air_velocity", self.on_cmd, 10)
        self.create_subscription(Float32, "airspeed", lambda m: setattr(self, "airspeed", m.data), 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)

    def on_cmd(self, m: TwistStamped) -> None:
        e, n = m.twist.linear.x, m.twist.linear.y
        self.airspeed_cmd = math.hypot(e, n)
        if self.airspeed_cmd > 0.2:
            self.heading = math.atan2(e, n)      # NED heading, clockwise from north

    def on_odom(self, m: Odometry) -> None:
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        dt = 0.05 if self.last_t is None else max(1e-3, t - self.last_t)
        self.last_t = t
        q = m.pose.pose.orientation
        yaw_enu = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        pitch_flu = math.asin(max(-1.0, min(1.0, 2 * (q.w * q.y - q.z * q.x))))
        yaw_ned = math.pi / 2.0 - yaw_enu
        w = m.twist.twist.angular
        heading = yaw_ned if self.heading is None else self.heading
        c = self.fc.command(heading, self.airspeed_cmd, 0.0, (0.0, -pitch_flu, yaw_ned),
                            (w.x, -w.y, -w.z), self.airspeed, self.thrust, dt)
        # First-order estimate of achieved thrust, matching the pod's response.
        self.thrust += (c.thrust_n - self.thrust) * min(1.0, dt / 0.6)
        out = PropulsionCommand()
        out.header.stamp = m.header.stamp
        out.thrust_n = float(c.thrust_n)
        out.gimbal_yaw_rad = float(c.gimbal_yaw)
        out.gimbal_pitch_rad = float(c.gimbal_pitch)
        self.pub.publish(out)


def main() -> None:
    rclpy.init()
    node = AttitudeController()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
