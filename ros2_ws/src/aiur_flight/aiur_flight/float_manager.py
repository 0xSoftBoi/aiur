"""Float manager: phase logic plus `aiur.strato.guidance.FloatController`.

Subscribes to odometry and the buoyancy state, decides which phase the flight
is in, and drives the vent valve, the ballast hopper and the vertical
thrust-vector trim.  It also *requests* termination when the mission is
complete; the decision to cut down belongs to the termination node alone.
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node

from aiur.strato.guidance import FlightPhase, FloatController
from aiur_msgs.msg import BuoyancyState, FlightStatus, FloatCommand


class FloatManager(Node):
    def __init__(self) -> None:
        super().__init__("float_manager")
        p = self.declare_parameter
        self.target = float(p("target_altitude_m", 20_000.0).value)
        self.launch_alt = float(p("launch_altitude_m", 150.0).value)
        self.float_duration = float(p("float_duration_s", 3600.0).value)
        vent_enabled = bool(p("vent_enabled", False).value)
        self.ctl = FloatController(self.target, vent_enabled=vent_enabled)
        self.phase = FlightPhase.PRELAUNCH
        self.fill = 0.0
        self.burst = False
        self.float_entry = None
        self.last_t = None
        self.t0 = None
        self.pub_cmd = self.create_publisher(FloatCommand, "cmd/float", 10)
        self.pub_status = self.create_publisher(FlightStatus, "status", 10)
        self.create_subscription(BuoyancyState, "buoyancy", self.on_buoy, 10)
        self.create_subscription(Odometry, "odom", self.on_odom, 10)

    def on_buoy(self, msg: BuoyancyState) -> None:
        self.fill = msg.fill_fraction
        self.burst = msg.burst

    def on_odom(self, msg: Odometry) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.t0 is None:
            self.t0 = t
        dt = 1.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t
        alt = msg.pose.pose.position.z + self.launch_alt
        climb = msg.twist.twist.linear.z
        rng = math.hypot(msg.pose.pose.position.x, msg.pose.pose.position.y)
        request, reason = False, ""

        prev = self.phase
        if self.phase == FlightPhase.PRELAUNCH and alt > self.launch_alt + 20.0:
            self.phase = FlightPhase.ASCENT
        elif self.phase == FlightPhase.ASCENT and alt > self.target - self.ctl.approach_m:
            self.phase = FlightPhase.FLOAT_ENTRY
        elif self.phase == FlightPhase.FLOAT_ENTRY and abs(climb) < 0.3 and (
                abs(alt - self.target) < 1500.0 or self.fill >= 0.999):
            self.phase = FlightPhase.STATION_KEEP
            self.float_entry = t
        if self.phase in (FlightPhase.ASCENT, FlightPhase.FLOAT_ENTRY, FlightPhase.STATION_KEEP):
            # A falling vehicle with an empty cell has been cut down or has burst.
            if self.burst or (climb < -3.0 and self.fill < 0.01):
                self.phase = FlightPhase.DESCENT
        if self.phase == FlightPhase.DESCENT and alt <= self.launch_alt + 1.0 and abs(climb) < 0.1:
            self.phase = FlightPhase.LANDED
        if self.phase != prev:
            self.get_logger().info(f"phase {prev.value} -> {self.phase.value} at {alt:.0f} m, "
                                   f"t={t - self.t0:.0f} s, range {rng/1000:.1f} km")

        cmd = FloatCommand()
        cmd.header.stamp = msg.header.stamp
        if self.phase in (FlightPhase.ASCENT, FlightPhase.FLOAT_ENTRY, FlightPhase.STATION_KEEP):
            c = self.ctl.command(alt, climb, dt)
            cmd.vent_open = c.vent_open
            cmd.ballast_rate_kg_s = float(c.ballast_kg_s)
            if self.phase != FlightPhase.ASCENT:
                cmd.trim = float(c.trim)
        self.pub_cmd.publish(cmd)

        if self.phase == FlightPhase.STATION_KEEP and self.float_entry is not None \
                and t - self.float_entry >= self.float_duration:
            request, reason = True, "mission complete"

        st = FlightStatus()
        st.header.stamp = msg.header.stamp
        st.phase = self.phase.value
        st.altitude_m = float(alt)
        st.climb_rate_m_s = float(climb)
        st.target_altitude_m = self.target
        st.range_from_launch_m = float(rng)
        st.station_error_m = float(rng)
        st.flight_time_s = float(t - self.t0)
        st.trim_command = float(cmd.trim)
        st.terminate_requested = request
        st.terminate_reason = reason
        self.pub_status.publish(st)


def main() -> None:
    rclpy.init()
    node = FloatManager()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
