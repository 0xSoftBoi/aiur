"""MAVLink <-> ROS 2 bridge for the companion computer.

One UART to the autopilot (a UDP port in simulation).  Inbound MAVLink
becomes the standard topics the flight nodes read; their setpoints go back
as the two messages a custom ArduPilot frame needs to accept:

    cmd/air_velocity + cmd/float.pitch_cmd_rad -> SET_ATTITUDE_TARGET
        quaternion from (0, pitch, heading); thrust = airspeed / dash airspeed
    cmd/float (vent, ballast, trim)            -> COMMAND_LONG MAV_CMD_DO_SET_ACTUATOR

MAVROS would do the transport half of this.  It is written directly on
pymavlink because the mapping, not the transport, is the part that is
specific to this vehicle, and because it then runs anywhere Python does.
"""

import math

import rclpy
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mav
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, FluidPressure, NavSatFix, Temperature
from std_msgs.msg import Float32

from aiur_msgs.msg import BuoyancyState, FloatCommand

EARTH_R = 6_371_000.0


class Bridge(Node):
    def __init__(self) -> None:
        super().__init__("mavlink_bridge")
        p = self.declare_parameter
        url = p("mavlink_url", "udpin:127.0.0.1:14560").value
        self.dash = float(p("dash_airspeed_m_s", 10.0).value)
        self.link = mavutil.mavlink_connection(url, source_system=1, source_component=191,
                                               dialect="ardupilotmega")
        self.home = None
        self.att = None
        self.named = {}
        self.pitch_cmd = 0.0
        self.heading = 0.0
        self.airspeed_cmd = 0.0
        self.float_cmd = FloatCommand()
        self.rx = self.tx = 0
        self.pub_odom = self.create_publisher(Odometry, "odom", 10)
        self.pub_fix = self.create_publisher(NavSatFix, "gps/fix", 10)
        self.pub_baro = self.create_publisher(FluidPressure, "baro/pressure", 10)
        self.pub_tamb = self.create_publisher(Temperature, "temperature/ambient", 10)
        self.pub_tgas = self.create_publisher(Temperature, "temperature/gas", 10)
        self.pub_batt = self.create_publisher(BatteryState, "battery", 10)
        self.pub_buoy = self.create_publisher(BuoyancyState, "buoyancy", 10)
        self.pub_air = self.create_publisher(Float32, "airspeed", 10)
        self.create_subscription(TwistStamped, "cmd/air_velocity", self.on_air, 10)
        self.create_subscription(FloatCommand, "cmd/float", self.on_float, 10)
        self.create_timer(0.005, self.poll,
                          clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))

    # --- ROS -> MAVLink --------------------------------------------------------
    def on_air(self, m: TwistStamped) -> None:
        e, n = m.twist.linear.x, m.twist.linear.y
        self.airspeed_cmd = math.hypot(e, n)
        if self.airspeed_cmd > 0.2:
            self.heading = math.atan2(e, n)

    def on_float(self, m: FloatCommand) -> None:
        self.float_cmd = m
        self.pitch_cmd = m.pitch_cmd_rad

    def send_setpoints(self, ms: int) -> None:
        cp, sp = math.cos(self.pitch_cmd / 2), math.sin(self.pitch_cmd / 2)
        cy, sy = math.cos(self.heading / 2), math.sin(self.heading / 2)
        q = [cp * cy, -sp * sy, sp * cy, cp * sy]      # roll = 0, ZYX
        mv = self.link.mav
        mv.set_attitude_target_send(ms, 1, 1, mav.ATTITUDE_TARGET_TYPEMASK_BODY_ROLL_RATE_IGNORE
                                    | mav.ATTITUDE_TARGET_TYPEMASK_BODY_PITCH_RATE_IGNORE
                                    | mav.ATTITUDE_TARGET_TYPEMASK_BODY_YAW_RATE_IGNORE,
                                    q, 0.0, 0.0, 0.0, min(1.0, self.airspeed_cmd / self.dash))
        f = self.float_cmd
        mv.command_long_send(1, 1, mav.MAV_CMD_DO_SET_ACTUATOR, 0,
                             1.0 if f.vent_open else 0.0, float(f.ballast_rate_kg_s),
                             float(f.trim), 0.0, 0.0, 0.0, 0.0)
        self.tx += 2

    # --- MAVLink -> ROS --------------------------------------------------------
    def poll(self) -> None:
        for _ in range(200):
            msg = self.link.recv_match(blocking=False)
            if msg is None:
                return
            self.rx += 1
            t = msg.get_type()
            if t == "ATTITUDE":
                self.att = msg
            elif t == "NAMED_VALUE_FLOAT":
                name = msg.name if isinstance(msg.name, str) else msg.name.decode()
                self.named[name.rstrip("\x00")] = msg.value
            elif t == "VFR_HUD":
                self.pub_air.publish(Float32(data=float(msg.airspeed)))
            elif t == "SCALED_PRESSURE":
                stamp = self.stamp(msg.time_boot_ms)
                b = FluidPressure()
                b.header.stamp, b.header.frame_id = stamp, "baro_link"
                b.fluid_pressure = msg.press_abs * 100.0
                self.pub_baro.publish(b)
            elif t == "SYS_STATUS":
                bs = BatteryState()
                bs.voltage = msg.voltage_battery / 1000.0
                bs.percentage = msg.battery_remaining / 100.0
                bs.present = True
                self.pub_batt.publish(bs)
            elif t == "GLOBAL_POSITION_INT":
                self.on_position(msg)

    def stamp(self, ms: int):
        from builtin_interfaces.msg import Time
        return Time(sec=ms // 1000, nanosec=(ms % 1000) * 1_000_000)

    def on_position(self, msg) -> None:
        lat, lon, alt = msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0
        if self.home is None:
            self.home = (lat, lon, alt - msg.relative_alt / 1000.0)
        stamp = self.stamp(msg.time_boot_ms)
        north = math.radians(lat - self.home[0]) * EARTH_R
        east = math.radians(lon - self.home[1]) * EARTH_R * math.cos(math.radians(self.home[0]))
        roll = pitch = 0.0
        yaw_ned = math.radians(msg.hdg / 100.0)
        p = q = r = 0.0
        if self.att is not None:
            roll, pitch, yaw_ned = self.att.roll, self.att.pitch, self.att.yaw
            p, q, r = self.att.rollspeed, self.att.pitchspeed, self.att.yawspeed
        # NED/FRD -> ENU/FLU (REP-103)
        yaw, pit = math.pi / 2.0 - yaw_ned, -pitch
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pit / 2), math.sin(pit / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        od = Odometry()
        od.header.stamp, od.header.frame_id, od.child_frame_id = stamp, "map", "base_link"
        od.pose.pose.position.x, od.pose.pose.position.y = east, north
        od.pose.pose.position.z = msg.relative_alt / 1000.0
        o = od.pose.pose.orientation
        o.w = cr * cp * cy + sr * sp * sy
        o.x = sr * cp * cy - cr * sp * sy
        o.y = cr * sp * cy + sr * cp * sy
        o.z = cr * cp * sy - sr * sp * cy
        vn, ve, vu = msg.vx / 100.0, msg.vy / 100.0, -msg.vz / 100.0
        c, s = math.cos(yaw), math.sin(yaw)
        od.twist.twist.linear.x = c * ve + s * vn
        od.twist.twist.linear.y = -s * ve + c * vn
        od.twist.twist.linear.z = vu
        od.twist.twist.angular.x, od.twist.twist.angular.y, od.twist.twist.angular.z = p, -q, -r
        self.pub_odom.publish(od)
        fix = NavSatFix()
        fix.header.stamp, fix.header.frame_id = stamp, "gnss_link"
        fix.latitude, fix.longitude, fix.altitude = lat, lon, alt
        self.pub_fix.publish(fix)
        n = self.named
        if "fill" in n:
            b = BuoyancyState()
            b.header.stamp = stamp
            b.gas_mass_kg = float(n.get("gas_kg", 0.0))
            b.gas_temperature_k = float(n.get("gas_temp", 0.0))
            b.ambient_temperature_k = float(n.get("amb_temp", 0.0))
            b.supertemperature_k = b.gas_temperature_k - b.ambient_temperature_k
            b.fill_fraction = float(n["fill"])
            b.superpressure_pa = float(n.get("dp", 0.0))
            b.ballast_remaining_kg = float(n.get("ballast", 0.0))
            b.vent_open = bool(self.float_cmd.vent_open)
            b.burst = n.get("burst", 0.0) > 0.5 or n.get("cut", 0.0) > 0.5
            self.pub_buoy.publish(b)
            for pub, kelvin in ((self.pub_tamb, b.ambient_temperature_k),
                                (self.pub_tgas, b.gas_temperature_k)):
                tm = Temperature()
                tm.header.stamp = stamp
                tm.temperature = kelvin - 273.15
                pub.publish(tm)
        self.send_setpoints(msg.time_boot_ms)


def main() -> None:
    rclpy.init()
    node = Bridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.get_logger().info(f"MAVLink frames: {node.rx} received, {node.tx} sent")
        node.destroy_node()
        rclpy.try_shutdown()
