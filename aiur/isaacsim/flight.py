"""Scripted terminal-approach force law for the ``run_p0b`` Isaac Sim demo.

Pure Python, no Isaac Sim dependency. Isaac Sim owns rigid-body dynamics for
the micro-UAV during free flight (``ProbePhase.FREE`` — see bridge.py); this
module only decides what force to command each step, using the same
tracking-law constants ``aiur.sim.bodies.DroneBody.step`` already uses
(``velocity_tau_s``, ``max_accel_m_s2``), so the demo is not free to fly the
Isaac Sim body faster or harder than the analytic twin says the real vehicle
can.

This is a minimal scripted approach for the demo scene, not a port of
``aiur.sim.guidance.TerminalGuidance``. It has none of the supervisor's
abort/evasion/FDIR logic and must never be mistaken for flight software or
cited as a guidance result.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sim.bodies import DroneParams
from ..sim.vec import Vec3


@dataclass(frozen=True)
class ApproachParams:
    #: Commanded closing speed relative to the dock. Held at the terminal
    #: approach target from docs/digital-twin.md (<=0.10 m/s target,
    #: 0.20 m/s ceiling) rather than the funnel's bounce-speed limit.
    close_speed_m_s: float = 0.08
    #: Lateral station-hold gain, 1/s. Engineering estimate for the demo,
    #: not calibrated against anything.
    lateral_kp_per_s: float = 1.0


class ApproachController:
    """Commands a velocity setpoint toward the dock throat, then a force to track it."""

    def __init__(
        self,
        params: ApproachParams = ApproachParams(),
        drone_params: DroneParams = DroneParams(),
    ) -> None:
        self.params = params
        self.drone_params = drone_params

    def velocity_setpoint(
        self,
        probe_position: Vec3,
        dock_center: Vec3,
        dock_velocity: Vec3,
    ) -> Vec3:
        """Station-hold laterally on the dock axis, close steadily along it."""

        rel = probe_position - dock_center
        lateral_cmd = -rel.lateral() * self.params.lateral_kp_per_s
        vertical_cmd = dock_velocity.z + self.params.close_speed_m_s
        return lateral_cmd.with_z(vertical_cmd) + dock_velocity.lateral()

    def commanded_force_n(
        self,
        current_velocity: Vec3,
        setpoint_velocity: Vec3,
    ) -> Vec3:
        """First-order velocity tracking with an acceleration ceiling.

        Same form as ``DroneBody.step``'s tracking term, minus the wind-drag
        disturbance term — Isaac Sim's own aerodynamics (if any) supply that
        instead of a linearized surrogate.
        """

        p = self.drone_params
        tracking = (setpoint_velocity - current_velocity) * (1.0 / p.velocity_tau_s)
        accel = tracking.clamped(p.max_accel_m_s2)
        return accel * p.mass_kg
