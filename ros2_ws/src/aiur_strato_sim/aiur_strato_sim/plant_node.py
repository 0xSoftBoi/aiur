"""Simulated vehicle: the `aiur.strato.ascent.AscentSim` plant behind ROS topics.

The node owns simulated time and publishes ``/clock``.  Everything it
publishes uses a standard message on the topic a real vehicle would use, so
the flight nodes cannot tell this plant from MAVROS + sensors:

    odom                 nav_msgs/Odometry      map (ENU, origin at launch) -> base_link (FLU)
    gps/fix              sensor_msgs/NavSatFix
    baro/pressure        sensor_msgs/FluidPressure
    temperature/ambient  sensor_msgs/Temperature
    temperature/gas      sensor_msgs/Temperature
    battery              sensor_msgs/BatteryState
    buoyancy             aiur_msgs/BuoyancyState
    wind/truth           geometry_msgs/Vector3Stamped   (simulation only)

and it accepts

    cmd/air_velocity     geometry_msgs/TwistStamped     ENU velocity through the air
    cmd/float            aiur_msgs/FloatCommand
    cmd/terminate        std_msgs/Bool
"""

import math

import rclpy
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped, TwistStamped, Vector3Stamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import BatteryState, FluidPressure, NavSatFix, NavSatStatus, Temperature
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from aiur.strato.ascent import AscentSim, config_from_design
from aiur.strato.sizing import ladder
from aiur_msgs.msg import BuoyancyState, FloatCommand

EARTH_R = 6_371_000.0


class Plant(Node):
    def __init__(self) -> None:
        super().__init__("plant")
        p = self.declare_parameter
        self.design_key = p("design", "S1-touch/hull").value
        self.dt = float(p("dt", 1.0).value)
        self.steps_per_tick = int(p("steps_per_tick", 2).value)
        self.tick_hz = float(p("tick_hz", 50.0).value)
        self.lat0 = float(p("launch_latitude_deg", 50.0).value)
        self.lon0 = float(p("launch_longitude_deg", 30.0).value)
        wind = p("wind_profile", "midlat-summer-p50").value
        wind_scale = float(p("wind_scale", 1.0).value)
        self.airspeed_lag_s = float(p("airspeed_lag_s", 20.0).value)
        self.gps_sigma_m = float(p("gps_sigma_m", 0.0).value)

        self.dp = ladder()[self.design_key]
        cfg = config_from_design(self.dp, wind=wind, wind_scale=wind_scale, dt_s=self.dt)
        self.sim = AscentSim(cfg)
        self.max_airspeed = float(self.dp.mission["dash_airspeed_m_s"])
        self.cruise = float(self.dp.mission["cruise_airspeed_m_s"])
        e = self.dp.energy
        self.capacity_wh = float(e["pack_usable_wh"])
        self.used_wh = 0.0
        self.hotel_w = float(e["hotel_w"])
        self.cruise_w = float(self.dp.propulsion["cruise_electrical_w"])
        self.dash_w = float(self.dp.propulsion["dash_electrical_w"])
        self.bus_v = float(e["bus_v"])

        self.cmd_air = (0.0, 0.0)      # north, east
        self.air = [0.0, 0.0]
        self.float_cmd = FloatCommand()
        self.terminated = False
        self.heading_ned = 0.0

        self.pub_clock = self.create_publisher(Clock, "/clock", 10)
        self.pub_odom = self.create_publisher(Odometry, "odom", 10)
        self.pub_fix = self.create_publisher(NavSatFix, "gps/fix", 10)
        self.pub_baro = self.create_publisher(FluidPressure, "baro/pressure", 10)
        self.pub_tamb = self.create_publisher(Temperature, "temperature/ambient", 10)
        self.pub_tgas = self.create_publisher(Temperature, "temperature/gas", 10)
        self.pub_batt = self.create_publisher(BatteryState, "battery", 10)
        self.pub_buoy = self.create_publisher(BuoyancyState, "buoyancy", 10)
        self.pub_wind = self.create_publisher(Vector3Stamped, "wind/truth", 10)
        self.tf = TransformBroadcaster(self)
        self.create_subscription(TwistStamped, "cmd/air_velocity", self.on_air, 10)
        self.create_subscription(FloatCommand, "cmd/float", self.on_float, 10)
        self.create_subscription(Bool, "cmd/terminate", self.on_term, 10)
        # The plant drives simulated time, so its own timer is wall-clock.
        self.create_timer(1.0 / self.tick_hz, self.tick,
                          clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))
        self.get_logger().info(
            f"plant {self.design_key}: gross {self.dp.mass_kg['gross']:.2f} kg, "
            f"launch gas {self.sim.m_gas:.3f} kg, {self.steps_per_tick * self.tick_hz * self.dt:.0f}x real time")

    def on_air(self, msg: TwistStamped) -> None:
        # ENU: x east, y north.
        n, e = msg.twist.linear.y, msg.twist.linear.x
        s = math.hypot(n, e)
        if s > self.max_airspeed:
            n, e = n * self.max_airspeed / s, e * self.max_airspeed / s
        self.cmd_air = (n, e)

    def on_float(self, msg: FloatCommand) -> None:
        self.float_cmd = msg

    def on_term(self, msg: Bool) -> None:
        if msg.data and not self.terminated:
            self.terminated = True
            self.sim.terminate()
            self.get_logger().warn(f"TERMINATE received at {self.sim.z:.0f} m, t={self.sim.t:.0f} s")

    def stamp(self) -> Time:
        t = Time()
        t.sec = int(self.sim.t)
        t.nanosec = int((self.sim.t - int(self.sim.t)) * 1e9)
        return t

    def tick(self) -> None:
        sim = self.sim
        if sim.landed:
            self.publish()
            return
        for _ in range(self.steps_per_tick):
            a = min(1.0, self.dt / self.airspeed_lag_s)
            self.air[0] += a * (self.cmd_air[0] - self.air[0])
            self.air[1] += a * (self.cmd_air[1] - self.air[1])
            powered = sim.fill > 0.5 or sim.cfg.cell_type == "latex"
            air = (self.air[0], self.air[1]) if powered and not sim.descending else (0.0, 0.0)
            fc = self.float_cmd
            sim.step(self.dt, fc.vent_open, fc.ballast_rate_kg_s, fc.trim, air)
            speed = math.hypot(*air)
            if speed > 0.3:
                self.heading_ned = math.atan2(air[1], air[0])
            power = self.hotel_w + self.cruise_w * (speed / max(self.cruise, 0.1)) ** 3 \
                + abs(fc.trim) * 0.6 * self.dash_w * (0.0 if sim.descending else 1.0) * 0.5
            self.used_wh += power * self.dt / 3600.0
            self.power_w = power
        self.publish()

    def publish(self) -> None:
        sim = self.sim
        now = self.stamp()
        self.pub_clock.publish(Clock(clock=now))
        yaw_enu = math.pi / 2.0 - self.heading_ned
        qz, qw = math.sin(yaw_enu / 2.0), math.cos(yaw_enu / 2.0)
        up = sim.z - sim.cfg.launch_altitude_m

        od = Odometry()
        od.header.stamp = now
        od.header.frame_id = "map"
        od.child_frame_id = "base_link"
        od.pose.pose.position.x = sim.east
        od.pose.pose.position.y = sim.north
        od.pose.pose.position.z = up
        od.pose.pose.orientation.z = qz
        od.pose.pose.orientation.w = qw
        # Twist in the child frame per REP-105 / nav_msgs convention.
        vn, ve = sim.vel_north, sim.vel_east
        c, s = math.cos(yaw_enu), math.sin(yaw_enu)
        od.twist.twist.linear.x = c * ve + s * vn
        od.twist.twist.linear.y = -s * ve + c * vn
        od.twist.twist.linear.z = sim.w
        self.pub_odom.publish(od)

        tfm = TransformStamped()
        tfm.header = od.header
        tfm.child_frame_id = "base_link"
        tfm.transform.translation.x = sim.east
        tfm.transform.translation.y = sim.north
        tfm.transform.translation.z = up
        tfm.transform.rotation.z = qz
        tfm.transform.rotation.w = qw
        self.tf.sendTransform(tfm)

        fix = NavSatFix()
        fix.header.stamp = now
        fix.header.frame_id = "gnss_link"
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = NavSatStatus.SERVICE_GPS
        fix.latitude = self.lat0 + math.degrees(sim.north / EARTH_R)
        fix.longitude = self.lon0 + math.degrees(
            sim.east / (EARTH_R * math.cos(math.radians(self.lat0))))
        fix.altitude = sim.z
        self.pub_fix.publish(fix)

        air = sim.air
        baro = FluidPressure()
        baro.header.stamp = now
        baro.header.frame_id = "baro_link"
        baro.fluid_pressure = air.pressure_pa
        self.pub_baro.publish(baro)
        for pub, kelvin, frame in ((self.pub_tamb, air.temperature_k, "ambient_probe"),
                                   (self.pub_tgas, sim.t_gas, "gas_probe")):
            tm = Temperature()
            tm.header.stamp = now
            tm.header.frame_id = frame
            tm.temperature = kelvin - 273.15
            pub.publish(tm)

        b = BatteryState()
        b.header.stamp = now
        frac = max(0.0, 1.0 - self.used_wh / self.capacity_wh)
        b.voltage = self.bus_v * (0.86 + 0.28 * frac) / 1.0
        b.current = -getattr(self, "power_w", self.hotel_w) / max(b.voltage, 1.0)
        b.percentage = frac
        b.capacity = self.capacity_wh / self.bus_v
        b.design_capacity = b.capacity
        b.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        b.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LION
        b.present = True
        self.pub_batt.publish(b)

        bs = BuoyancyState()
        bs.header.stamp = now
        bs.gas_mass_kg = float(sim.m_gas)
        bs.gas_temperature_k = float(sim.t_gas)
        bs.ambient_temperature_k = float(air.temperature_k)
        bs.supertemperature_k = float(sim.supertemp)
        bs.fill_fraction = float(sim.fill)
        bs.superpressure_pa = float(sim.dp)
        bs.ballast_remaining_kg = float(sim.ballast)
        bs.vent_open = bool(self.float_cmd.vent_open)
        bs.burst = bool(sim.burst)
        self.pub_buoy.publish(bs)

        wv = sim.wind.at(sim.z)
        w = Vector3Stamped()
        w.header.stamp = now
        w.header.frame_id = "map"
        w.vector.x, w.vector.y = wv.east_m_s, wv.north_m_s
        self.pub_wind.publish(w)


def main() -> None:
    rclpy.init()
    node = Plant()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
