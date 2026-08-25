"""Tests for aiur/isaacsim/bridge.py and aiur/isaacsim/flight.py.

These exercise the Isaac Sim integration scaffold's *logic* — a scripted
probe trajectory standing in for what a correctly wired Isaac Sim rigid body
should report each step — against the real, unmocked
``aiur.dock_controller.DockController`` and the real
``aiur.sim.dock_physics`` mechanism. This is the part of
``aiur/isaacsim/`` that can be evidence without an Isaac Sim install; it
says nothing about ``scene.py`` or ``run_p0b.py``, which call the actual
Isaac Sim API and remain unexecuted (see docs/isaac-sim-integration.md).
"""

import unittest

from aiur.dock_controller import DockState
from aiur.isaacsim.bridge import IsaacTwinBridge, ProbeState
from aiur.isaacsim.flight import ApproachController
from aiur.sim.dock_physics import DockCommands, DockGeometry, ProbePhase
from aiur.sim.vec import Vec3

DT = 0.02


class IsaacTwinBridgeTests(unittest.TestCase):
    def test_step_without_probe_stays_free(self) -> None:
        bridge = IsaacTwinBridge()
        bridge.detach_probe()
        result = bridge.step(0.0, Vec3(0.0, 0.0, 2.0), Vec3(), DockCommands())
        self.assertEqual(result.probe_phase, ProbePhase.FREE)
        self.assertEqual(result.controller.state, DockState.OPEN)

    def test_scripted_descent_reaches_capture(self) -> None:
        """A slow, centered, scripted approach should still end CAPTURED.

        Each iteration integrates one step of flight (a stand-in for what a
        correctly wired Isaac Sim rigid body — or ``DroneBody.step`` in the
        analytic twin — does every step regardless of mechanism phase), then
        hands the result to the bridge and adopts its corrected state as the
        new current state. That "integrate, then adopt the correction" order
        is what run_p0b.py's real loop must also do: the mechanism only ever
        *corrects* a position/velocity handed to it (funnel-wall clamp,
        seat pin, seat hold) — nothing in it advances the probe forward on
        its own, exactly like ``aiur.sim.dock_physics.DockAssembly`` does not
        replace ``DroneBody.step`` in the analytic twin's engine loop.
        """

        geometry = DockGeometry()
        bridge = IsaacTwinBridge(geometry=geometry, dt_s=DT)
        dock_center = Vec3(0.0, 0.0, 2.0)
        dock_velocity = Vec3()

        closing_speed = 0.05  # well below the 0.30 m/s bounce threshold
        position = dock_center + Vec3(0.0, 0.0, -geometry.probe_height_m - 0.02)
        velocity = Vec3(0.0, 0.0, closing_speed)

        result = None
        now_s = 0.0
        for _ in range(3000):  # 60 s ceiling; capture should land well inside it
            position = position + velocity * DT
            bridge.attach_probe(ProbeState(position=position, velocity=velocity))
            result = bridge.step(
                now_s, dock_center, dock_velocity, DockCommands(capture_enable=True)
            )
            now_s += DT

            corrected = bridge.corrected_probe_state()
            position, velocity = corrected.position, corrected.velocity

            if result.controller.capture_confirmed:
                break

        assert result is not None
        self.assertTrue(result.controller.capture_confirmed)
        self.assertEqual(result.controller.state, DockState.CAPTURED)
        self.assertEqual(result.probe_phase, ProbePhase.SEATED)
        self.assertAlmostEqual(bridge.keeper_fraction(), 1.0, places=2)


class ApproachControllerTests(unittest.TestCase):
    def test_velocity_setpoint_centers_and_closes(self) -> None:
        controller = ApproachController()
        dock_center = Vec3(1.0, -1.0, 2.0)
        probe_position = dock_center + Vec3(0.2, -0.1, -0.3)
        dock_velocity = Vec3(0.01, 0.0, 0.0)

        setpoint = controller.velocity_setpoint(probe_position, dock_center, dock_velocity)

        kp = controller.params.lateral_kp_per_s
        self.assertAlmostEqual(setpoint.x, -0.2 * kp + dock_velocity.x)
        self.assertAlmostEqual(setpoint.y, 0.1 * kp + dock_velocity.y)
        self.assertAlmostEqual(setpoint.z, dock_velocity.z + controller.params.close_speed_m_s)

    def test_commanded_force_respects_acceleration_ceiling(self) -> None:
        controller = ApproachController()
        # A large setpoint jump should saturate, never exceed, the ceiling.
        force = controller.commanded_force_n(Vec3(), Vec3(10.0, 0.0, 0.0))
        max_force_n = controller.drone_params.mass_kg * controller.drone_params.max_accel_m_s2
        self.assertLessEqual(force.norm(), max_force_n + 1e-9)
        self.assertAlmostEqual(force.norm(), max_force_n, places=6)

    def test_commanded_force_is_zero_at_setpoint(self) -> None:
        controller = ApproachController()
        v = Vec3(0.03, -0.02, 0.05)
        force = controller.commanded_force_n(v, v)
        self.assertAlmostEqual(force.norm(), 0.0)


if __name__ == "__main__":
    unittest.main()
