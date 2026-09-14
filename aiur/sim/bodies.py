"""Vehicle dynamics for the CARRIER-P0 digital twin.

Two flight articles are modeled:

* ``DroneBody`` — a Crazyflie-class micro-UAV flown by velocity setpoints,
  as the real vehicle is commanded during terminal approach.  The closed
  outer loop is abstracted to a first-order response with an acceleration
  limit; wind enters as a linearized drag disturbance the controller must
  fight, which reproduces the realistic steady-state tracking offset.
* ``CarrierBody`` — the buoyant carrier as a neutrally trimmed point mass
  with large effective (physical + added) mass, linear drag, a thrust-limited
  station-keeping PD controller, and an optional ground tether.

``KinematicRig`` stands in for the carrier during SIL-P0-B, matching the
moving suspended-dock bench article: the dock moves on a programmed path and
has no gas envelope to strike.

Parameter provenance: masses marked "vendor" come from published Bitcraze
figures already cited in docs/prototype-p0.md; the carrier's length and
helium volume come from the vendor article selected in ``aiur.envelope``.
Every dynamic coefficient is an engineering estimate pending calibration
against measured flight data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

from ..envelope import (
    P0_ARTICLE,
    P0_SEMI_MAJOR_M,
    P0_SEMI_MINOR_M,
    ROOM_TEMPERATURE_C,
    air_density_kg_m3,
    spheroid_semi_minor_m,
)
from .vec import Vec3, ZERO


@dataclass(frozen=True)
class DroneParams:
    """Crazyflie 2.1 Brushless surrogate parameters."""

    #: Vendor figure: 37 g takeoff mass with guards.
    mass_kg: float = 0.037
    #: Closed-loop velocity-tracking time constant.  Engineering estimate.
    velocity_tau_s: float = 0.25
    #: Acceleration ceiling used for precision approach.  Engineering estimate,
    #: deliberately far below the vehicle's aerobatic capability.
    max_accel_m_s2: float = 2.0
    #: Linearized drag coupling to relative wind, 1/s.  Engineering estimate.
    wind_coupling_per_s: float = 0.9
    #: Usable sortie endurance.  Vendor stock figure is ~10 min; the twin
    #: reserves margin.  Engineering estimate.
    endurance_s: float = 480.0
    #: Radius used for envelope-strike and separation checks (guarded prop
    #: footprint).  Engineering estimate.
    body_radius_m: float = 0.055


class DroneBody:
    """Point-mass micro-UAV tracked by velocity setpoints."""

    def __init__(self, params: DroneParams, position: Vec3) -> None:
        self.params = params
        self.position = position
        self.velocity = ZERO
        self.armed = True
        self.remaining_flight_s = params.endurance_s
        #: Scaled down by the battery-sag fault; 1.0 is nominal.
        self.performance_scale = 1.0
        #: Scaled up by the battery-sag fault; 1.0 is nominal.
        self.drain_multiplier = 1.0

    def step(self, dt_s: float, commanded_velocity: Vec3, air_velocity: Vec3) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        if not self.armed:
            # A disarmed (captured or landed) aircraft is carried by whatever
            # holds it; the engine moves it explicitly.
            return

        p = self.params
        scale = self.performance_scale
        tracking = (commanded_velocity - self.velocity) * (1.0 / p.velocity_tau_s)
        tracking = tracking.clamped(p.max_accel_m_s2 * scale)
        disturbance = (air_velocity - self.velocity) * p.wind_coupling_per_s
        accel = tracking + disturbance

        self.velocity = self.velocity + accel * dt_s
        self.position = self.position + self.velocity * dt_s
        self.remaining_flight_s = max(
            0.0, self.remaining_flight_s - dt_s * self.drain_multiplier
        )

    def disarm(self) -> None:
        self.armed = False
        self.velocity = ZERO


#: Vertical distance from the hull's lowest point to the funnel mouth: keel
#: rail, dock bay, and the funnel itself.  Fixed hardware, so it does not
#: scale with the hull.  Engineering estimate.
DOCK_STANDOFF_BELOW_HULL_M = 0.286

#: Effective mass over displaced air mass.  A buoyant hull accelerates the
#: air around it, so the mass the station-keeping loop pushes against is the
#: vehicle plus an added-mass allowance of roughly a third.  Engineering
#: estimate, unchanged from the 4.5 m calibration (9.0 kg on 5.5 m3).
ADDED_MASS_FACTOR = 1.34

#: Linear drag coefficient the 4.5 m calibration carried, and the frontal
#: area it was set at; drag on a hull scales with frontal area, so a smaller
#: hull inherits the coefficient through this ratio.  Engineering estimate.
_REFERENCE_DRAG_N_PER_M_S = 1.5
_REFERENCE_SEMI_MINOR_M = spheroid_semi_minor_m(4.5, 5.5)


def _carrier_effective_mass_kg() -> float:
    return ADDED_MASS_FACTOR * P0_ARTICLE.helium_volume_m3 * air_density_kg_m3(ROOM_TEMPERATURE_C)


def _carrier_linear_drag_n_per_m_s() -> float:
    return _REFERENCE_DRAG_N_PER_M_S * (P0_SEMI_MINOR_M / _REFERENCE_SEMI_MINOR_M) ** 2


@dataclass(frozen=True)
class CarrierParams:
    """Indoor helium carrier surrogate parameters for the P0 article.

    Geometry comes from ``aiur.envelope.P0_ARTICLE`` (3.5 m, ~4 m^3 as the
    vendor quotes it): the envelope semi-axes are the volume-matched prolate
    spheroid (1.75 x 0.739 x 0.739 m), the dock hangs a fixed standoff under
    the hull, and effective mass and drag are scaled from the 4.5 m
    calibration by displaced volume and frontal area.  Thrust is the vendor's
    motor set and does not change with the hull.  All dynamic values are
    engineering estimates.

    Known omission: the model assumes neutral trim in every configuration.
    Physically, capturing or releasing a ~48 g aircraft (airframe, deck and
    probe) changes dead weight by ~0.47 N — more than the 0.3 N vertical
    thrust budget — so the real carrier must re-trim (ballast/thrust bias)
    across a launch/recovery cycle.  The twin does not model that transient;
    it is flagged in docs/digital-twin.md for bench correlation.
    """

    effective_mass_kg: float = field(default_factory=_carrier_effective_mass_kg)
    linear_drag_n_per_m_s: float = field(default_factory=_carrier_linear_drag_n_per_m_s)
    station_kp_n_per_m: float = 0.4
    station_kd_n_per_m_s: float = 1.2
    max_lateral_thrust_n: float = 0.4
    max_vertical_thrust_n: float = 0.3
    envelope_semi_axes_m: Vec3 = field(
        default_factory=lambda: Vec3(P0_SEMI_MAJOR_M, P0_SEMI_MINOR_M, P0_SEMI_MINOR_M)
    )
    #: Dock funnel entrance sits on the structural rail below the hull.
    dock_offset_m: Vec3 = field(
        default_factory=lambda: Vec3(0.0, 0.0, -(P0_SEMI_MINOR_M + DOCK_STANDOFF_BELOW_HULL_M))
    )
    #: Ground tether for P0-C style operations; slack below this length.
    tether_length_m: float = 3.4
    tether_stiffness_n_per_m: float = 5.0


class CarrierBody:
    """Neutrally buoyant carrier with station-keeping and optional tether."""

    def __init__(
        self,
        params: CarrierParams,
        position: Vec3,
        *,
        station_setpoint: Vec3 | None = None,
        tether_anchor: Vec3 | None = None,
    ) -> None:
        self.params = params
        self.position = position
        self.velocity = ZERO
        self.station_setpoint = station_setpoint if station_setpoint is not None else position
        self.tether_anchor = tether_anchor

    def _station_force(self) -> Vec3:
        p = self.params
        error = self.station_setpoint - self.position
        force = error * p.station_kp_n_per_m - self.velocity * p.station_kd_n_per_m_s
        lateral = force.lateral().clamped(p.max_lateral_thrust_n)
        vertical = max(-p.max_vertical_thrust_n, min(p.max_vertical_thrust_n, force.z))
        return lateral.with_z(vertical)

    def _tether_force(self) -> Vec3:
        if self.tether_anchor is None:
            return ZERO
        p = self.params
        offset = self.position - self.tether_anchor
        stretch = offset.norm() - p.tether_length_m
        if stretch <= 0.0 or offset.norm() == 0.0:
            return ZERO
        return offset * (-p.tether_stiffness_n_per_m * stretch / offset.norm())

    def step(self, dt_s: float, air_velocity: Vec3) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        p = self.params
        drag = (air_velocity - self.velocity) * p.linear_drag_n_per_m_s
        force = self._station_force() + self._tether_force() + drag
        accel = force * (1.0 / p.effective_mass_kg)
        self.velocity = self.velocity + accel * dt_s
        self.position = self.position + self.velocity * dt_s

    def dock_center(self) -> Vec3:
        return self.position + self.params.dock_offset_m

    def dock_velocity(self) -> Vec3:
        return self.velocity

    def envelope_normalized_distance(self, point: Vec3, inflate_m: float = 0.0) -> float:
        """Return the normalized ellipsoid coordinate of ``point``.

        Values below 1.0 mean the point is inside the (inflated) envelope —
        a strike.  The inflation absorbs the striking body's own radius.
        """

        a = self.params.envelope_semi_axes_m
        rel = point - self.position
        return math.sqrt(
            (rel.x / (a.x + inflate_m)) ** 2
            + (rel.y / (a.y + inflate_m)) ** 2
            + (rel.z / (a.z + inflate_m)) ** 2
        )


@dataclass(frozen=True)
class RigParams:
    """Programmed motion for the suspended moving dock of SIL-P0-B."""

    lateral_amplitude_m: float = 0.05
    lateral_period_s: float = 8.0
    vertical_amplitude_m: float = 0.02
    vertical_period_s: float = 11.0


class KinematicRig:
    """Bench rig that drives the dock on a deterministic programmed path."""

    def __init__(self, params: RigParams, center: Vec3, rng: random.Random) -> None:
        self.params = params
        self.center = center
        self._phase_x = rng.uniform(0.0, 2.0 * math.pi)
        self._phase_z = rng.uniform(0.0, 2.0 * math.pi)
        self._t = 0.0

    def step(self, dt_s: float, air_velocity: Vec3) -> None:
        if dt_s <= 0:
            raise ValueError("dt must be positive")
        self._t += dt_s

    def _angular(self) -> tuple[float, float]:
        p = self.params
        return (
            2.0 * math.pi / p.lateral_period_s,
            2.0 * math.pi / p.vertical_period_s,
        )

    def dock_center(self) -> Vec3:
        p = self.params
        wx, wz = self._angular()
        return self.center + Vec3(
            p.lateral_amplitude_m * math.sin(wx * self._t + self._phase_x),
            0.0,
            p.vertical_amplitude_m * math.sin(wz * self._t + self._phase_z),
        )

    def dock_velocity(self) -> Vec3:
        p = self.params
        wx, wz = self._angular()
        return Vec3(
            p.lateral_amplitude_m * wx * math.cos(wx * self._t + self._phase_x),
            0.0,
            p.vertical_amplitude_m * wz * math.cos(wz * self._t + self._phase_z),
        )

    def envelope_normalized_distance(self, point: Vec3, inflate_m: float = 0.0) -> float:
        """A bench rig has no gas envelope; nothing can be struck."""

        return math.inf
