"""MAVLink <-> ROS 2 bridge for the companion computer.

One UART to the autopilot (a UDP port in simulation).  Inbound MAVLink
becomes the standard topics the flight nodes read; their setpoints go back
as the two messages a custom ArduPilot frame needs to accept:

    cmd/air_velocity + cmd/float.pitch_cmd_rad -> SET_ATTITUDE_TARGET
        quaternion from (0, pitch, heading); thrust = airspeed / dash airspeed
    cmd/float (vent, ballast, trim)            -> COMMAND_LONG MAV_CMD_DO_SET_ACTUATOR

That is the contract with the repo's own simulated autopilot
(`autopilot:=sim`, the default).  With `autopilot:=ardurover` the bridge talks
to a real ArduRover (SITL or hardware) instead, and does what a companion
has to do with one:

    * wait for the heartbeat, request the telemetry streams it needs, wait
      for GPS + EKF, switch to GUIDED and arm (`auto_arm`), send its own
      heartbeat at 1 Hz;
    * encode the setpoint the way Rover accepts it: SET_ATTITUDE_TARGET with
      the heading in the quaternion and thrust = SIGNED GROUND SPEED along
      that heading / WP_SPEED.  The air-velocity demand is converted with
      the wind estimate on `wind/estimate`.  (Rover ignores pitch; Rover's
      SET_POSITION_TARGET_LOCAL_NED yaw+velocity form has a sign quirk -
      docs/strato/ardupilot-sitl.md.)
    * not send the float actuator command: stock Rover has nothing to
      receive it, and no buoyancy telemetry comes back, so `buoyancy` and the
      gas/ambient temperature topics are simply not published;
    * republish the autopilot's actual outputs (SERVO_OUTPUT_RAW) as
      `cmd/propulsion`, the topic the reporters read.

Time: every stamp is the autopilot's time_boot_ms, in both modes.  Against
SITL that is simulated time, so the nodes downstream, which take dt from
message stamps, run correctly at any SITL speed without /clock.

MAVROS would do the transport half of this.  It is written directly on
pymavlink because the mapping, not the transport, is the part that is
specific to this vehicle, and because it then runs anywhere Python does.
"""

import math
import time

import rclpy
from geometry_msgs.msg import TwistStamped, Vector3Stamped
from nav_msgs.msg import Odometry
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mav
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, FluidPressure, NavSatFix, Temperature
from std_msgs.msg import Float32

from aiur_msgs.msg import BuoyancyState, FloatCommand, PropulsionCommand

EARTH_R = 6_371_000.0
ROVER_GUIDED = 15
EKF_OK = 0x001 | 0x002 | 0x010     # attitude, horizontal velocity, absolute horizontal position


class Bridge(Node):
    def __init__(self) -> None:
        super().__init__("mavlink_bridge")
        p = self.declare_parameter
        url = p("mavlink_url", "udpin:127.0.0.1:14560").value
        self.dash = float(p("dash_airspeed_m_s", 10.0).value)
        #: "sim": the repo's simulated autopilot.  "ardurover": a real ArduRover.
        self.autopilot = str(p("autopilot", "sim").value)
        self.rover = self.autopilot == "ardurover"
        if self.autopilot not in ("sim", "ardurover"):
            raise ValueError(f"autopilot must be sim or ardurover, not {self.autopilot!r}")
        self.auto_arm = bool(p("auto_arm", True).value)
        #: ardurover: publish nothing and send nothing before this autopilot time.
        self.activate_ms = int(1000 * float(p("activate_after_s", 0.0).value))
        #: ardurover: map position of the vehicle at activation (station at the origin).
        self.start_offset = (float(p("start_offset_east_m", 0.0).value),
                             float(p("start_offset_north_m", 0.0).value))
        self.stream_hz = float(p("stream_rate_hz", 5.0).value)
        self.max_thrust_n = float(p("max_thrust_n", 7.55).value)
        self.gimbal_limit = math.radians(float(p("gimbal_limit_deg", 25.0).value))
        if self.rover:
            self.link = self.connect_rover(url)
        else:
            self.link = mavutil.mavlink_connection(url, source_system=1, source_component=191,
                                                   dialect="ardupilotmega")
        self.ap_seen = self.ap_armed = False
        self.ap_mode = -1
        self.ap_ekf = self.ap_fix = 0
        self.ap_ready = False
        self.ap_next = 0.0              # wall time of the next start-up action
        self.ap_hb = 0.0
        self.ap_streams = 0.0
        self.wind = [0.0, 0.0]          # east, north; from the station keeper
        self.home = None
        self.att = None
        self.named = {}
        self.pitch_cmd = 0.0
        self.heading = 0.0
        self.airspeed_cmd = 0.0
        self.float_cmd = FloatCommand()
        self.rx = self.tx = 0
        # Dead reckoning for GNSS outages: barometric altitude, last ground
        # velocity for the horizontal.  Altitude control must not depend on
        # GNSS - the barometer is the better altitude sensor at float anyway.
        self.last_fix_ms = None
        self.last = None            # (north, east, vn, ve, launch_alt)
        self.baro_alt = None
        self.baro_prev = None
        self.dr_fixes = 0
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
        if self.rover:
            self.pub_prop = self.create_publisher(PropulsionCommand, "cmd/propulsion", 10)
            self.create_subscription(Vector3Stamped, "wind/estimate", self.on_wind, 10)
            self.get_logger().info("ArduRover mode: no buoyancy telemetry exists; buoyancy and "
                                   "temperature topics will not be published, cmd/float is not sent")
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

    def on_wind(self, m: Vector3Stamped) -> None:
        self.wind = [m.vector.x, m.vector.y]

    def send_setpoints(self, ms: int) -> None:
        if self.rover:
            self.send_setpoints_rover(ms)
            return
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

    # --- ArduRover -------------------------------------------------------------
    def connect_rover(self, url: str):
        """SITL opens its MAVLink port a moment after it starts; keep trying."""

        last = None
        for _ in range(60):
            try:
                return mavutil.mavlink_connection(url, source_system=1, source_component=191,
                                                  dialect="ardupilotmega")
            except OSError as exc:
                last = exc
                time.sleep(0.5)
        raise RuntimeError(f"could not connect to ArduRover at {url}: {last}")

    def send_setpoints_rover(self, ms: int) -> None:
        """Heading + signed ground speed.  Rover's speed loop (and the Lua
        inner loop) work on ground speed along the commanded heading; the
        guidance law asks for an air velocity; the difference is the wind."""

        if not self.ap_ready:
            return
        h = self.heading
        ground = self.airspeed_cmd + self.wind[0] * math.sin(h) + self.wind[1] * math.cos(h)
        q = [math.cos(h / 2), 0.0, 0.0, math.sin(h / 2)]
        self.link.mav.set_attitude_target_send(
            ms, 1, 1, mav.ATTITUDE_TARGET_TYPEMASK_BODY_ROLL_RATE_IGNORE
            | mav.ATTITUDE_TARGET_TYPEMASK_BODY_PITCH_RATE_IGNORE
            | mav.ATTITUDE_TARGET_TYPEMASK_BODY_YAW_RATE_IGNORE,
            q, 0.0, 0.0, 0.0, max(-1.0, min(1.0, ground / self.dash)))
        self.tx += 1

    def rover_startup(self) -> None:
        """Called from poll(): heartbeat, streams, GUIDED, arm.  Wall-clock
        paced retries; nothing here blocks."""

        now = time.monotonic()
        mv = self.link.mav
        if now - self.ap_hb >= 1.0:
            self.ap_hb = now
            mv.heartbeat_send(mav.MAV_TYPE_ONBOARD_CONTROLLER, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        if not self.ap_seen or self.ap_ready or now < self.ap_next:
            return
        # Short steps: against SITL at 15x, a 2 s wall-clock retry is 30 s of flight.
        self.ap_next = now + 0.25
        ok = self.ap_fix >= 3 and (self.ap_ekf & EKF_OK) == EKF_OK
        if not ok:
            if now < self.ap_streams:
                return
            self.ap_streams = now + 2.0
            for mid, hz in ((mav.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, self.stream_hz),
                            (mav.MAVLINK_MSG_ID_ATTITUDE, 2.0 * self.stream_hz),
                            (mav.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, self.stream_hz),
                            (mav.MAVLINK_MSG_ID_VFR_HUD, 1.0), (mav.MAVLINK_MSG_ID_SCALED_PRESSURE, 1.0),
                            (mav.MAVLINK_MSG_ID_SYS_STATUS, 1.0), (mav.MAVLINK_MSG_ID_GPS_RAW_INT, 1.0),
                            (mav.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 1.0)):
                mv.command_long_send(1, 1, mav.MAV_CMD_SET_MESSAGE_INTERVAL, 0, mid, 1e6 / hz,
                                     0, 0, 0, 0, 0)
        elif self.ap_mode != ROVER_GUIDED:
            mv.set_mode_send(1, mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, ROVER_GUIDED)
        elif not self.ap_armed and self.auto_arm:
            # SET_ATTITUDE_TARGET thrust is a fraction of WP_SPEED: make that the dash speed.
            mv.param_set_send(1, 1, b"WP_SPEED", self.dash, mav.MAV_PARAM_TYPE_REAL32)
            mv.command_long_send(1, 1, mav.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        elif self.ap_armed:
            self.ap_ready = True
            self.get_logger().info("ArduRover: GPS + EKF ok, GUIDED, armed; setpoints flowing")

    def on_rover_msg(self, t: str, msg) -> None:
        if t == "HEARTBEAT":
            if msg.get_srcComponent() == 1 and msg.type != mav.MAV_TYPE_GCS:
                self.ap_seen = True
                self.ap_armed = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
                self.ap_mode = msg.custom_mode
        elif t == "GPS_RAW_INT":
            self.ap_fix = msg.fix_type
        elif t == "EKF_STATUS_REPORT":
            self.ap_ekf = msg.flags
        elif t == "STATUSTEXT":
            self.get_logger().info(f"AP: {msg.text}")
        elif t == "SERVO_OUTPUT_RAW" and self.ap_ready:
            # What the autopilot is actually driving, in the pod node's units.
            pc = PropulsionCommand()
            pc.header.stamp = self.stamp(msg.time_usec // 1000)
            pc.thrust_n = max(0.0, min(1.0, (msg.servo3_raw - 1000) / 1000.0)) * self.max_thrust_n
            pc.gimbal_yaw_rad = -(msg.servo1_raw - 1500) / 500.0 * self.gimbal_limit
            pc.gimbal_pitch_rad = ((msg.servo4_raw - 1500) / 500.0 * self.gimbal_limit
                                   if msg.servo4_raw >= 800 else 0.0)
            self.pub_prop.publish(pc)

    # --- MAVLink -> ROS --------------------------------------------------------
    def poll(self) -> None:
        if self.rover:
            self.rover_startup()
        for _ in range(200):
            msg = self.link.recv_match(blocking=False)
            if msg is None:
                return
            self.rx += 1
            t = msg.get_type()
            if self.rover:
                self.on_rover_msg(t, msg)
            if t == "ATTITUDE":
                self.att = msg
                if self.last_fix_ms is not None and msg.time_boot_ms - self.last_fix_ms > 3000 \
                        and self.baro_alt is not None and msg.time_boot_ms % 1000 == 0:
                    self.dead_reckon(msg.time_boot_ms)
            elif t == "NAMED_VALUE_FLOAT":
                name = msg.name if isinstance(msg.name, str) else msg.name.decode()
                self.named[name.rstrip("\x00")] = msg.value
                if self.rover and name.startswith("AIN_ASPD") and self.ap_ready:
                    # True airspeed from aiur_inner.lua (ARSPD sensor x EAS2TAS).  Rover's
                    # own VFR_HUD.airspeed is equivalent airspeed, or ground speed
                    # when there is no sensor - not usable as an air velocity.
                    self.pub_air.publish(Float32(data=float(msg.value)))
            elif t == "VFR_HUD":
                if not (self.rover and "AIN_ASPD" in self.named):
                    self.pub_air.publish(Float32(data=float(msg.airspeed)))
            elif t == "SCALED_PRESSURE":
                stamp = self.stamp(msg.time_boot_ms)
                b = FluidPressure()
                b.header.stamp, b.header.frame_id = stamp, "baro_link"
                b.fluid_pressure = msg.press_abs * 100.0
                self.pub_baro.publish(b)
                from aiur.strato.atmosphere import pressure_altitude_m
                self.baro_prev = (self.baro_alt, getattr(self, "_baro_ms", msg.time_boot_ms))
                self.baro_alt = pressure_altitude_m(msg.press_abs * 100.0)
                self._baro_ms = msg.time_boot_ms
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

    def dead_reckon(self, ms: int) -> None:
        north, east, vn, ve, launch, t0 = self.last
        dt = (ms - t0) / 1000.0
        self.last = (north + vn * dt, east + ve * dt, vn, ve, launch, ms)
        prev_alt, prev_ms = self.baro_prev
        climb = 0.0
        if prev_alt is not None and self._baro_ms > prev_ms:
            climb = (self.baro_alt - prev_alt) / ((self._baro_ms - prev_ms) / 1000.0)
        yaw = math.pi / 2.0 - self.att.yaw
        od = Odometry()
        od.header.stamp, od.header.frame_id, od.child_frame_id = self.stamp(ms), "map", "base_link"
        od.pose.pose.position.x, od.pose.pose.position.y = self.last[1], self.last[0]
        od.pose.pose.position.z = self.baro_alt - launch
        od.pose.pose.orientation.z, od.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        od.pose.covariance[0] = od.pose.covariance[7] = (50.0 + 5.0 * (ms - self.last_fix_ms) / 1000.0) ** 2
        c, s = math.cos(yaw), math.sin(yaw)
        od.twist.twist.linear.x, od.twist.twist.linear.y = c * ve + s * vn, -s * ve + c * vn
        od.twist.twist.linear.z = climb
        self.pub_odom.publish(od)
        self.dr_fixes += 1
        self.send_setpoints(ms)

    def on_position(self, msg) -> None:
        lat, lon, alt = msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0
        if self.rover:
            if not self.ap_ready or msg.time_boot_ms < self.activate_ms:
                return
            if self.home is None and any(self.start_offset):
                # Put the map origin (the station) so that the vehicle is at
                # start_offset now.
                e0, n0 = self.start_offset
                self.home = (lat - math.degrees(n0 / EARTH_R),
                             lon - math.degrees(e0 / (EARTH_R * math.cos(math.radians(lat)))),
                             alt - msg.relative_alt / 1000.0)
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
        self.last_fix_ms = msg.time_boot_ms
        self.last = (north, east, vn, ve, self.home[2], msg.time_boot_ms)
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
        node.get_logger().info(f"MAVLink frames: {node.rx} received, {node.tx} sent; "
                               f"{node.dr_fixes} s dead-reckoned")
        node.destroy_node()
        rclpy.try_shutdown()
