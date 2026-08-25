"""Isaac Sim <-> real dock-controller bridge.

Pure Python, no Isaac Sim dependency — importable and unit-tested
(``tests/test_isaacsim_bridge.py``) without an Isaac Sim install.

This module is deliberately thin. It does not reimplement the funnel/collet/
keeper mechanics: it hands Isaac Sim's rigid-body state to the *same*
``aiur.sim.dock_physics.DockAssembly`` the analytic twin already uses, which
in turn drives the *same*, unmocked ``aiur.dock_controller.DockController``
plus the same debounced-switch and finite-travel-servo primitives
(``aiur.sim.sensors``). Isaac Sim's job is narrowly scoped to what it adds
over the analytic twin — PhysX rigid-body dynamics and rendering for the
carrier and micro-UAV — not to re-derive mechanism truth from scratch.

Ownership handoff (read before wiring this to a scene): ``DockAssembly.step``
*corrects* whatever position/velocity it is handed — funnel-wall clamp,
seat pin, seat hold — the same way ``aiur.sim.dock_physics`` corrects
``DroneBody`` after ``DroneBody.step`` has already advanced it in the
analytic twin's engine loop (``aiur/sim/engine.py``). It never advances the
probe forward on its own. So the scaffold's contract mirrors that same
two-phase order every step, regardless of ``probe_phase``:

1. Let Isaac Sim's PhysX integrate the probe rigid body one step (gravity +
   whatever force ``flight.ApproachController`` applied) — a dynamic body,
   never toggled kinematic.
2. Read the resulting pose/velocity, call :meth:`IsaacTwinBridge.step`, then
   write :meth:`IsaacTwinBridge.corrected_probe_state` straight back onto the
   rigid body (``set_world_poses`` / ``set_linear_velocities``) before the
   next physics step — a per-frame position/velocity correction, not a
   kinematic-mode switch. During ``ProbePhase.FREE`` the correction is a
   no-op (the mechanism has not touched the state), so this is safe to do
   unconditionally rather than branching on phase.

The funnel/keeper meshes must stay visual-only (no ``UsdPhysics.CollisionAPI``)
so PhysX's own collision response never contests this mechanism's contact
model with a second, disagreeing answer for where the probe is.

This design was made without ever running it — flag any alternative (e.g.
real PhysX funnel collision, with this mechanism only supplying switch/servo
truth from proximity) as an open question in
docs/isaac-sim-integration.md rather than silently changing it here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..dock_controller import DockController
from ..sim.bodies import DroneBody, DroneParams
from ..sim.dock_physics import DockAssembly, DockCommands, DockGeometry, DockStepResult
from ..sim.vec import Vec3, ZERO


@dataclass(frozen=True)
class ProbeState:
    """Minimal state the bridge needs out of an Isaac Sim rigid body per step."""

    position: Vec3
    velocity: Vec3
    armed: bool = True


class IsaacTwinBridge:
    """Feeds Isaac Sim rigid-body state through the real mechanism + controller.

    One instance per dock. The probe is a plain ``DroneBody`` used only as a
    mutable state container — its own ``.step()`` (the twin's analytic flight
    dynamics) is never called here, because Isaac Sim owns dynamics.
    """

    def __init__(
        self,
        *,
        geometry: DockGeometry = DockGeometry(),
        dt_s: float = 0.02,
        controller: DockController | None = None,
        drone_params: DroneParams = DroneParams(),
    ) -> None:
        self.mechanism = DockAssembly(geometry, dt_s=dt_s, controller=controller)
        self._probe = DroneBody(drone_params, position=ZERO)
        self._has_probe = False

    def attach_probe(self, state: ProbeState) -> None:
        """Register a probe as present this step (a launched, un-recovered aircraft)."""

        self._probe.position = state.position
        self._probe.velocity = state.velocity
        self._probe.armed = state.armed
        self._has_probe = True

    def detach_probe(self) -> None:
        """No probe present — mirrors passing ``drone=None`` to the mechanism."""

        self._has_probe = False

    def step(
        self,
        now_s: float,
        dock_center: Vec3,
        dock_velocity: Vec3,
        commands: DockCommands,
    ) -> DockStepResult:
        drone = self._probe if self._has_probe else None
        return self.mechanism.step(now_s, dock_center, dock_velocity, drone, commands)

    def corrected_probe_state(self) -> ProbeState:
        """Post-step probe position/velocity, after any mechanism contact correction.

        Write this back to the Isaac Sim rigid body every step — see the
        module docstring. A no-op while ``probe_phase`` is ``FREE``.
        """

        return ProbeState(
            position=self._probe.position,
            velocity=self._probe.velocity,
            armed=self._probe.armed,
        )

    def keeper_fraction(self) -> float:
        """0.0 = keeper fully open, 1.0 = fully closed. Drive the joint target with this."""

        return self.mechanism.servo.position

    def seed_seated(self, dock_center: Vec3, dock_velocity: Vec3) -> None:
        """Start captured, for scenarios that begin with an aircraft already docked."""

        self._has_probe = True
        self.mechanism.seed_seated(self._probe, dock_center, dock_velocity)

    def reset_controller(self) -> None:
        """Model a controller brownout: mechanism state survives, controller state does not."""

        self.mechanism.reset_controller()
