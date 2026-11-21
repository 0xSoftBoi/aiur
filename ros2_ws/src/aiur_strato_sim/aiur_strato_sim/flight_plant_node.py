"""Float-phase plant: `aiur.strato.flight6dof` behind ROS topics.

Where `plant` flies the whole mission with no attitude, this node flies the
hull at float with full rigid-body + added-mass dynamics, wind and gust
gradients.  It takes the actuator-level command the stern pod would receive
and publishes what the autopilot's estimator would: odometry (ENU / FLU),
IMU rates, airspeed and the gimbal joint states.
"""

import math

import rclpy
from geometry_msgs.msg import Vector3Stamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Imu, JointState
from std_msgs.msg import Float32

from aiur.strato.atmosphere import Gust
from aiur.strato.flight6dof import (Airframe, Controls, State, _mat_t_vec, euler_from_quat,
                                    quat_from_euler, quat_to_matrix, step)
from aiur.strato.sizing import ladder
from aiur_msgs.msg import PropulsionCommand


class FlightPlant(Node):
    def __init__(self) -> None:
        super().__init__("flight_plant")
        p = self.declare_parameter
        design = p("design", "S2-dayloiter/hull").value
        self.dt = float(p("dt", 0.05).value)
        self.steps_per_tick = int(p("steps_per_tick", 20).value)
        self.wind = (float(p("wind_north_m_s", 0.0).value), float(p("wind_east_m_s", -4.0).value), 0.0)
        self.gust = Gust(float(p("gust_sigma_m_s", 0.5).value), 20.0, seed=int(p("seed", 3).value))
        start_e = float(p("start_east_m", -1500.0).value)
        start_n = float(p("start_north_m", 0.0).value)
        self.af = Airframe.from_design(ladder()[design])
        hdg = math.atan2(-self.wind[1], -self.wind[0]) if any(self.wind[:2]) else 0.0
        self.st = State(pos=(start_n, start_e, 0.0), quat=quat_from_euler(0.0, 0.0, hdg),
                        vel=(2.0, 0.0, 0.0))
        self.cmd = Controls()
        self.t = 0.0
        self.pub_clock = self.create_publisher(Clock, "/clock", 10)
        self.pub_odom = self.create_publisher(Odometry, "odom", 10)
        self.pub_imu = self.create_publisher(Imu, "imu/data", 10)
        self.pub_air = self.create_publisher(Float32, "airspeed", 10)
        self.pub_js = self.create_publisher(JointState, "joint_states", 10)
        self.pub_wind = self.create_publisher(Vector3Stamped, "wind/truth", 10)
        self.create_subscription(PropulsionCommand, "cmd/propulsion", self.on_cmd, 10)
        self.create_timer(1.0 / 50.0, self.tick,
                          clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))
        self.get_logger().info(f"6-DoF plant {design}: {self.af.hull.length_m:.1f} m hull, "
                               f"wind N{self.wind[0]:+.1f} E{self.wind[1]:+.1f} m/s")

    def on_cmd(self, m: PropulsionCommand) -> None:
        self.cmd = Controls(m.thrust_n, m.gimbal_yaw_rad, m.gimbal_pitch_rad)

    def tick(self) -> None:
        for _ in range(self.steps_per_tick):
            g = self.gust.step(self.dt)
            w = (self.wind[0] + g[0], self.wind[1] + g[1], g[2])
            gb = _mat_t_vec(quat_to_matrix(self.st.quat), tuple(self.gust.rate))
            speed = max(2.0, math.sqrt(sum(c * c for c in self.st.vel)))
            self.af.gust_rot = (gb[2] / speed, -gb[1] / speed)
            self.st = step(self.af, self.st, self.cmd, w, self.dt)
            self.t += self.dt
        self.publish(w)

    def publish(self, wind) -> None:
        st = self.st
        clock = Clock()
        clock.clock.sec = int(self.t)
        clock.clock.nanosec = int((self.t - int(self.t)) * 1e9)
        self.pub_clock.publish(clock)
        now = clock.clock
        roll, pitch, yaw = euler_from_quat(st.quat)
        # NED/FRD -> ENU/FLU
        q = quat_from_euler(roll, -pitch, math.pi / 2.0 - yaw)
        rot = quat_to_matrix(st.quat)
        ground_ned = tuple(a + b for a, b in zip(
            tuple(rot[i][0] * st.vel[0] + rot[i][1] * st.vel[1] + rot[i][2] * st.vel[2]
                  for i in range(3)), wind))
        gb = _mat_t_vec(rot, ground_ned)
        od = Odometry()
        od.header.stamp = now
        od.header.frame_id = "map"
        od.child_frame_id = "base_link"
        od.pose.pose.position.x, od.pose.pose.position.y = st.pos[1], st.pos[0]
        od.pose.pose.position.z = -st.pos[2]
        (od.pose.pose.orientation.w, od.pose.pose.orientation.x,
         od.pose.pose.orientation.y, od.pose.pose.orientation.z) = q
        od.twist.twist.linear.x, od.twist.twist.linear.y, od.twist.twist.linear.z = gb[0], -gb[1], -gb[2]
        od.twist.twist.angular.x, od.twist.twist.angular.y = st.rate[0], -st.rate[1]
        od.twist.twist.angular.z = -st.rate[2]
        self.pub_odom.publish(od)
        imu = Imu()
        imu.header.stamp = now
        imu.header.frame_id = "base_link"
        imu.orientation = od.pose.pose.orientation
        imu.angular_velocity = od.twist.twist.angular
        self.pub_imu.publish(imu)
        self.pub_air.publish(Float32(data=float(st.vel[0])))
        js = JointState()
        js.header.stamp = now
        js.name = ["gimbal_yaw_joint", "gimbal_pitch_joint"]
        js.position = [float(-st.gimbal_yaw), float(-st.gimbal_pitch)]
        self.pub_js.publish(js)
        wv = Vector3Stamped()
        wv.header.stamp = now
        wv.header.frame_id = "map"
        wv.vector.x, wv.vector.y = wind[1], wind[0]
        self.pub_wind.publish(wv)


def main() -> None:
    rclpy.init()
    node = FlightPlant()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
