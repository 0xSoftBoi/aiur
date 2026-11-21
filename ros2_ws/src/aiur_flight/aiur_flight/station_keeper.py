"""Station keeper: `aiur.strato.guidance.StationKeeper` on ROS topics.

The wind is not measured, it is inferred: ground velocity from odometry
minus the air velocity the vehicle was last commanded to fly, low-passed.
That is the estimator a GNSS-only vehicle with no usable pitot has, and at a
dynamic pressure of 1-4 Pa that is this vehicle.
"""

import math

import rclpy
from geometry_msgs.msg import TwistStamped, Vector3Stamped
from nav_msgs.msg import Odometry
from rclpy.node import Node

from aiur.strato.guidance import FlightPhase, StationKeeper
from aiur_msgs.msg import FlightStatus


class StationKeeperNode(Node):
    def __init__(self) -> None:
        super().__init__("station_keeper")
        p = self.declare_parameter
        self.keeper = StationKeeper(float(p("max_airspeed_m_s", 3.0).value),
                                    loiter_radius_m=float(p("loiter_radius_m", 500.0).value))
        self.station = (float(p("station_east_m", 0.0).value),
                        float(p("station_north_m", 0.0).value))
        self.tau = float(p("wind_filter_s", 60.0).value)
        self.airspeed_lag_s = float(p("airspeed_lag_s", 20.0).value)
        self.phase = FlightPhase.PRELAUNCH.value
        self.wind = [0.0, 0.0]          # east, north
        self.air_est = [0.0, 0.0]       # achieved air velocity estimate
        self.cmd = [0.0, 0.0]
        self.last_t = None
        self.pub = self.create_publisher(TwistStamped, "cmd/air_velocity", 10)
        self.pub_wind = self.create_publisher(Vector3Stamped, "wind/estimate", 10)
        self.create_subscription(FlightStatus, "status", self.on_status, 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)

    def on_status(self, msg: FlightStatus) -> None:
        self.phase = msg.phase

    def on_odom(self, msg: Odometry) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        dt = 1.0 if self.last_t is None else max(1e-3, t - self.last_t)
        self.last_t = t
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        vx, vy = msg.twist.twist.linear.x, msg.twist.twist.linear.y
        ve = math.cos(yaw) * vx - math.sin(yaw) * vy
        vn = math.sin(yaw) * vx + math.cos(yaw) * vy
        a = min(1.0, dt / self.airspeed_lag_s)
        self.air_est[0] += a * (self.cmd[0] - self.air_est[0])
        self.air_est[1] += a * (self.cmd[1] - self.air_est[1])
        b = min(1.0, dt / self.tau)
        self.wind[0] += b * ((ve - self.air_est[0]) - self.wind[0])
        self.wind[1] += b * ((vn - self.air_est[1]) - self.wind[1])

        out = TwistStamped()
        out.header.stamp = msg.header.stamp
        out.header.frame_id = "map"
        if self.phase == FlightPhase.STATION_KEEP.value:
            err_e = self.station[0] - msg.pose.pose.position.x
            err_n = self.station[1] - msg.pose.pose.position.y
            c = self.keeper.command(err_n, err_e, self.wind[1], self.wind[0])
            self.cmd = [c.east_m_s, c.north_m_s]
        else:
            self.cmd = [0.0, 0.0]
        out.twist.linear.x, out.twist.linear.y = self.cmd
        self.pub.publish(out)
        w = Vector3Stamped()
        w.header = out.header
        w.vector.x, w.vector.y = self.wind
        self.pub_wind.publish(w)


def main() -> None:
    rclpy.init()
    node = StationKeeperNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
