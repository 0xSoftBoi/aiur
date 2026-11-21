"""Simulated vehicle that speaks MAVLink, the way the real autopilot does.

`aiur.strato.mission6.UnifiedSim` (buoyancy + 6-DoF, attitude inner loop
included, as it is inside the autopilot) sits behind a MAVLink 2 UDP port.
Nothing reaches the flight nodes except through `mavlink_bridge`, so the
bridge and the message mapping are exercised on the wire format, not on a
Python shortcut.

Out: HEARTBEAT, GLOBAL_POSITION_INT, ATTITUDE, VFR_HUD, SCALED_PRESSURE,
     SYS_STATUS, NAMED_VALUE_FLOAT (gas_temp, amb_temp, fill, dp, ballast, gas_kg)
In:  SET_ATTITUDE_TARGET  (heading + pitch as a quaternion, thrust = airspeed / dash)
     COMMAND_LONG MAV_CMD_DO_SET_ACTUATOR  (param1 vent, param2 ballast rate kg/s)

Two things are deliberately NOT on MAVLink: /clock (simulation only) and the
cut-down, which belongs to the termination unit and arrives on cmd/terminate.
"""

import math

import rclpy
from geometry_msgs.msg import Vector3Stamped
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as mav
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import Bool

from aiur.strato.flight6dof import euler_from_quat
from aiur.strato.mission6 import MissionOptions, UnifiedSim
from aiur.strato.sizing import ladder

EARTH_R = 6_371_000.0


class UnifiedPlant(Node):
    def __init__(self) -> None:
        super().__init__("unified_plant")
        p = self.declare_parameter
        design = p("design", "S2-dayloiter/hull").value
        self.steps_per_tick = int(p("steps_per_tick", 1).value)
        self.lat0 = float(p("launch_latitude_deg", 50.0).value)
        self.lon0 = float(p("launch_longitude_deg", 30.0).value)
        url = p("mavlink_url", "udpout:127.0.0.1:14560").value
        opts = MissionOptions(external=True, gust_sigma_m_s=float(p("gust_sigma_m_s", 0.5).value),
                              gimbal_jam_at_s=self._opt(p("gimbal_jam_at_s", -1.0).value),
                              motor_fail_at_s=self._opt(p("motor_fail_at_s", -1.0).value))
        self.gps_out_at = self._opt(p("gps_dropout_at_s", -1.0).value)
        self.gps_out_for = float(p("gps_dropout_duration_s", 1200.0).value)
        self.dp = ladder()[design]
        self.sim = UnifiedSim(self.dp, opts, wind=p("wind_profile", "midlat-summer-p50").value,
                              wind_scale=float(p("wind_scale", 1.0).value))
        self.dash = float(self.dp.mission["dash_airspeed_m_s"])
        e = self.dp.energy
        self.capacity_wh, self.used_wh = float(e["pack_usable_wh"]), 0.0
        self.hotel_w, self.bus_v = float(e["hotel_w"]), float(e["bus_v"])
        self.ext = {"vent": False, "ballast_kg_s": 0.0, "trim": 0.0, "pitch_cmd": 0.0,
                    "heading": 0.0, "airspeed": 0.0}
        self.link = mavutil.mavlink_connection(url, source_system=1, source_component=1,
                                               dialect="ardupilotmega")
        self.rx = 0
        self.pub_clock = self.create_publisher(Clock, "/clock", 10)
        self.pub_wind = self.create_publisher(Vector3Stamped, "wind/truth", 10)
        self.create_subscription(Bool, "cmd/terminate", self.on_term, 10)
        self.create_timer(1.0 / 50.0, self.tick,
                          clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))
        self.get_logger().info(f"unified plant {design} on MAVLink {url}")

    @staticmethod
    def _opt(v):
        return None if v is None or float(v) < 0.0 else float(v)

    def on_term(self, m: Bool) -> None:
        if m.data:
            self.sim.terminate("cut-down")

    def read_mavlink(self) -> None:
        while True:
            msg = self.link.recv_match(blocking=False)
            if msg is None:
                return
            self.rx += 1
            t = msg.get_type()
            if t == "SET_ATTITUDE_TARGET":
                w, x, y, z = msg.q
                pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
                yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
                self.ext["airspeed"] = max(0.0, min(1.0, msg.thrust)) * self.dash
                self.ext["pitch_cmd"] = pitch
                if not (msg.type_mask & mav.ATTITUDE_TARGET_TYPEMASK_ATTITUDE_IGNORE):
                    self.ext["heading"] = yaw
            elif t == "COMMAND_LONG" and msg.command == mav.MAV_CMD_DO_SET_ACTUATOR:
                self.ext["vent"] = msg.param1 > 0.5
                self.ext["ballast_kg_s"] = max(0.0, msg.param2)
                self.ext["trim"] = max(-1.0, min(1.0, msg.param3))

    def tick(self) -> None:
        sim = self.sim
        self.read_mavlink()
        if sim.phase.value != "LANDED":
            for _ in range(self.steps_per_tick):
                sim.step_second(self.ext)
                thrust_w = 0.0
                if sim.mode == "hull":
                    thrust_w = sim.st.thrust_n * max(sim.st.vel[0], 0.0) / 0.45
                self.used_wh += (self.hotel_w + thrust_w) / 3600.0
        self.send()

    def send(self) -> None:
        sim, mv = self.sim, self.link.mav
        t = sim.t
        ms = int(t * 1000) & 0xFFFFFFFF
        clock = Clock()
        clock.clock.sec, clock.clock.nanosec = int(t), int((t - int(t)) * 1e9)
        self.pub_clock.publish(clock)
        if sim.mode == "hull":
            roll, pitch, yaw = euler_from_quat(sim.st.quat)
            p, q, r = sim.st.rate
            airspeed = sim.st.vel[0]
            rot_n = (sim.st.pos[0], sim.st.pos[1])
        else:
            roll = pitch = p = q = r = airspeed = 0.0
            yaw = self.ext["heading"]
        north, east, z, climb = sim.north, sim.east, sim.z, sim.climb
        vn = (north - getattr(self, "_pn", north)) / max(self.steps_per_tick, 1)
        ve = (east - getattr(self, "_pe", east)) / max(self.steps_per_tick, 1)
        self._pn, self._pe = north, east
        lat = self.lat0 + math.degrees(north / EARTH_R)
        lon = self.lon0 + math.degrees(east / (EARTH_R * math.cos(math.radians(self.lat0))))
        launch = sim.cfg.launch_altitude_m
        mv.heartbeat_send(mav.MAV_TYPE_AIRSHIP, mav.MAV_AUTOPILOT_ARDUPILOTMEGA,
                          mav.MAV_MODE_FLAG_GUIDED_ENABLED | mav.MAV_MODE_FLAG_SAFETY_ARMED, 0,
                          mav.MAV_STATE_ACTIVE)
        clamp = lambda v, lim: int(max(-lim, min(lim, v)))
        gps_ok = self.gps_out_at is None or not (
            self.gps_out_at <= t < self.gps_out_at + self.gps_out_for)
        if gps_ok:
            mv.global_position_int_send(ms, int(lat * 1e7), int(lon * 1e7), int(z * 1000),
                                        int((z - launch) * 1000), clamp(vn * 100, 32767),
                                        clamp(ve * 100, 32767), clamp(-climb * 100, 32767),
                                        int(math.degrees(yaw) % 360 * 100))
        mv.attitude_send(ms, roll, pitch, yaw, p, q, r)
        mv.vfr_hud_send(airspeed, math.hypot(vn, ve), int(math.degrees(yaw) % 360),
                        0, z, climb)
        air = sim.asc.air
        mv.scaled_pressure_send(ms, air.pressure_pa / 100.0, 0.0,
                                clamp((air.temperature_k - 273.15) * 100, 32767))
        frac = max(0.0, 1.0 - self.used_wh / self.capacity_wh)
        mv.sys_status_send(0, 0, 0, 0, int(self.bus_v * (0.86 + 0.28 * frac) * 1000), -1,
                           int(frac * 100), 0, 0, 0, 0, 0, 0)
        a = sim.asc
        for name, val in ((b"gas_temp", a.t_gas), (b"amb_temp", air.temperature_k),
                          (b"fill", a.fill), (b"dp", a.dp), (b"ballast", a.ballast),
                          (b"gas_kg", a.m_gas), (b"burst", 1.0 if a.burst else 0.0),
                          (b"cut", 1.0 if sim.mode == "descent" else 0.0)):
            mv.named_value_float_send(ms, name, float(val))
        wv = a.wind.at(z)
        w = Vector3Stamped()
        w.header.stamp = clock.clock
        w.header.frame_id = "map"
        w.vector.x, w.vector.y = wv.east_m_s, wv.north_m_s
        self.pub_wind.publish(w)


def main() -> None:
    rclpy.init()
    node = UnifiedPlant()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
