"""Flight-software candidates: float control and station-keeping.

These classes are written to be flown, not just simulated.  The ascent model,
the 6-DoF model and the ROS 2 nodes in ``ros2_ws`` all call the same objects,
so a law that passes in simulation is the law the vehicle runs - the same
rule the P0 twin applies to ``DockController``.

Nothing here reads a clock, a random source or the atmosphere model: inputs
are measurements, outputs are commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class FlightPhase(str, Enum):
    PRELAUNCH = "PRELAUNCH"
    ASCENT = "ASCENT"
    FLOAT_ENTRY = "FLOAT_ENTRY"
    STATION_KEEP = "STATION_KEEP"
    DESCENT = "DESCENT"
    TERMINATED = "TERMINATED"
    LANDED = "LANDED"


@dataclass(frozen=True)
class FloatCommand:
    vent_open: bool
    ballast_kg_s: float
    #: Vertical thrust-vector demand, -1 (full down) .. +1 (full up).
    trim: float = 0.0


@dataclass
class FloatController:
    """Hold a float altitude with a vent valve and droppable ballast.

    A buoyant vehicle has no altitude stiffness of its own once the cell is
    slack, so the controller acts on a *predicted* altitude: where the vehicle
    will be in ``lead_s`` seconds at the present climb rate.  Venting is
    irreversible and ballast is finite, so both act only outside a deadband
    and only when the vehicle is actually moving the wrong way.
    """

    target_m: float
    band_m: float = 250.0
    lead_s: float = 120.0
    #: Do not vent while climbing slower than this: the cell is settling.
    vent_min_climb_m_s: float = 0.25
    sink_trigger_m_s: float = -0.25
    ballast_rate_kg_s: float = 0.004
    #: Begin shedding free lift this far below the target.
    approach_m: float = 2500.0
    approach_climb_m_s: float = 1.5
    #: A zero-pressure cell regulates itself by spilling when full; venting
    #: it early leaves a slack cell with no altitude stiffness at all.  Set
    #: False for such cells and the valve is reserved for termination.
    vent_enabled: bool = True
    #: Vertical thrust trim: full authority at this altitude error / sink rate.
    trim_error_m: float = 400.0
    trim_rate_m_s: float = 0.8
    #: Seconds of saturated up-trim before ballast is spent instead.
    trim_patience_s: float = 90.0
    _saturated_s: float = 0.0

    def command(self, altitude_m: float, climb_m_s: float, dt_s: float = 1.0) -> FloatCommand:
        predicted = altitude_m + climb_m_s * self.lead_s
        vent = False
        ballast = 0.0
        trim = 0.0
        if altitude_m > self.target_m - self.approach_m:
            trim = ((self.target_m - altitude_m) / self.trim_error_m
                    - climb_m_s / self.trim_rate_m_s)
            trim = max(-1.0, min(1.0, trim))
        self._saturated_s = self._saturated_s + dt_s if trim >= 0.999 else 0.0
        if self._saturated_s > self.trim_patience_s and climb_m_s < 0.0:
            ballast = self.ballast_rate_kg_s
        if not self.vent_enabled:
            if predicted < self.target_m - self.band_m and climb_m_s < self.sink_trigger_m_s \
                    and altitude_m < self.target_m - self.band_m:
                ballast = self.ballast_rate_kg_s
            return FloatCommand(False, ballast, trim)
        if altitude_m > self.target_m - self.approach_m:
            # Inside the approach band: bleed climb rate down so the vehicle
            # arrives at the target instead of flying through it.
            remaining = self.target_m - altitude_m
            allowed = self.approach_climb_m_s * max(0.0, remaining / self.approach_m) + 0.1
            if climb_m_s > max(allowed, self.vent_min_climb_m_s):
                vent = True
        if predicted > self.target_m + self.band_m and climb_m_s > self.vent_min_climb_m_s:
            vent = True
        if predicted < self.target_m - self.band_m and climb_m_s < self.sink_trigger_m_s \
                and altitude_m < self.target_m:
            ballast = self.ballast_rate_kg_s
            vent = False
        return FloatCommand(vent, ballast, trim)


@dataclass(frozen=True)
class AirVelocityCommand:
    """Commanded velocity *through the air*, North-East, m/s."""

    north_m_s: float
    east_m_s: float
    saturated: bool

    @property
    def airspeed_m_s(self) -> float:
        return math.hypot(self.north_m_s, self.east_m_s)

    @property
    def heading_rad(self) -> float:
        """Heading to fly, radians clockwise from North."""

        return math.atan2(self.east_m_s, self.north_m_s)


@dataclass
class StationKeeper:
    """Hold a ground position against the wind.

    The vehicle wants a ground velocity that closes the position error; the
    air velocity that produces it is that minus the wind.  When the wind
    exceeds the airspeed limit the vehicle cannot hold, and the least-bad
    action is to point straight into the wind at full speed and lose ground
    as slowly as possible - not to chase the station sideways.

    Inside ``loiter_radius_m`` the gain is cut so the vehicle idles rather
    than hunting, which is where the propulsion energy is saved.
    """

    max_airspeed_m_s: float
    position_gain_per_s: float = 0.004
    max_closing_speed_m_s: float = 3.0
    loiter_radius_m: float = 500.0

    def command(self, error_north_m: float, error_east_m: float,
                wind_north_m_s: float, wind_east_m_s: float) -> AirVelocityCommand:
        dist = math.hypot(error_north_m, error_east_m)
        gain = self.position_gain_per_s
        if dist < self.loiter_radius_m:
            gain *= dist / self.loiter_radius_m
        gn, ge = gain * error_north_m, gain * error_east_m
        gs = math.hypot(gn, ge)
        if gs > self.max_closing_speed_m_s:
            gn *= self.max_closing_speed_m_s / gs
            ge *= self.max_closing_speed_m_s / gs
        an, ae = gn - wind_north_m_s, ge - wind_east_m_s
        speed = math.hypot(an, ae)
        if speed <= self.max_airspeed_m_s:
            return AirVelocityCommand(an, ae, False)
        wind = math.hypot(wind_north_m_s, wind_east_m_s)
        if wind >= self.max_airspeed_m_s:
            # Cannot hold: weathercock into the wind at the limit.
            s = self.max_airspeed_m_s / wind
            return AirVelocityCommand(-wind_north_m_s * s, -wind_east_m_s * s, True)
        # Can hold but not close at the requested rate: cancel the wind fully
        # and spend what is left along the error direction.
        spare = math.sqrt(self.max_airspeed_m_s**2 - wind**2 * 0.999)
        spare = min(spare, gs)
        un, ue = (gn / gs, ge / gs) if gs > 1e-9 else (0.0, 0.0)
        an, ae = un * spare - wind_north_m_s, ue * spare - wind_east_m_s
        sp = math.hypot(an, ae)
        if sp > self.max_airspeed_m_s:
            an *= self.max_airspeed_m_s / sp
            ae *= self.max_airspeed_m_s / sp
        return AirVelocityCommand(an, ae, True)


@dataclass
class Geofence:
    """Independent termination criteria.  Any one true means cut down.

    This runs on the termination controller, which shares no power, no
    processor and no radio with the autopilot (see hardware/strato).
    """

    max_range_m: float = 150_000.0
    max_altitude_m: float = 27_000.0
    max_flight_s: float = 16.0 * 3600.0
    min_descent_altitude_m: float = 0.0

    def must_terminate(self, range_m: float, altitude_m: float, flight_s: float,
                       commanded: bool = False, link_lost_s: float = 0.0,
                       link_timeout_s: float = 3.0 * 3600.0) -> tuple[bool, str]:
        if commanded:
            return True, "commanded"
        if range_m > self.max_range_m:
            return True, "range"
        if altitude_m > self.max_altitude_m:
            return True, "altitude"
        if flight_s > self.max_flight_s:
            return True, "flight time"
        if link_lost_s > link_timeout_s:
            return True, "link loss"
        return False, ""
