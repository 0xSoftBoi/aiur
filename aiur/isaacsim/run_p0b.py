"""Standalone Isaac Sim launcher: SIL-P0-B (moving suspended dock) demo.

**Unexecuted.** Read ``aiur/isaacsim/__init__.py`` and
docs/isaac-sim-integration.md before treating anything this script prints as
a result — nobody has run it against a real Isaac Sim install. Every call
tagged ``# VERIFY:`` below is a guess at the installed API surface most
likely to need a one-line patch on a first run.

Run it from Isaac Sim's own bundled interpreter, not the system Python
(``isaacsim`` only importable there):

    ./python.sh -m aiur.isaacsim.run_p0b [--headless] [--duration 30]

This is one scripted episode for visual/physical inspection of the P0-B
bench-rig recovery, not a Monte Carlo evidence run — it is not one of the
``aiur.sim.campaign`` scenarios and closes no SIL gate. The real
``aiur.dock_controller.DockController`` and ``aiur.sim.dock_physics``
mechanism drive the outcome; ``ApproachController`` (flight.py) is a
scripted stand-in for the guidance stack, not flight software.
"""

from __future__ import annotations

import argparse
import random


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--duration", type=float, default=30.0, help="seconds of simulated time"
    )
    args = parser.parse_args(argv)

    # SimulationApp must exist before any other isaacsim/omni/pxr import.
    from isaacsim import SimulationApp  # VERIFY: import root for the installed version.

    simulation_app = SimulationApp({"headless": args.headless})
    try:
        _run(args, simulation_app)
    finally:
        simulation_app.close()
    return 0


def _run(args: argparse.Namespace, simulation_app) -> None:
    import numpy as np
    from pxr import Gf, UsdGeom
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim  # VERIFY: module path for this version.
    from isaacsim.core.utils.stage import get_current_stage

    from . import scene
    from .bridge import IsaacTwinBridge, ProbeState
    from .flight import ApproachController
    from ..sim.bodies import KinematicRig, RigParams
    from ..sim.dock_physics import DockCommands, DockGeometry
    from ..sim.vec import Vec3

    dt_s = 0.02
    geometry = DockGeometry()
    handles = scene.build_stage(geometry=geometry)

    world = World.instance() if World.instance() is not None else World()
    world.reset()

    stage = get_current_stage()
    keeper_prim = stage.GetPrimAtPath(handles.keeper_path)
    rig_prim = stage.GetPrimAtPath(handles.rig_path)
    probe_rigid = RigidPrim(handles.probe_path)

    # Same starting point aiur.sim.scenarios.sil_p0b uses (unjittered — this
    # is one deterministic demo run, not a sampled episode).
    rig = KinematicRig(RigParams(), Vec3(0.0, 0.0, 2.0), random.Random(1))
    bridge = IsaacTwinBridge(geometry=geometry, dt_s=dt_s)
    approach = ApproachController()

    start = Vec3(0.45, -0.35, 0.90)
    # VERIFY: plural batched pose/velocity API (set_world_poses,
    # get_linear_velocities) vs an older singular per-body API
    # (set_world_pose, get_linear_velocity) depending on the installed
    # RigidPrim/RigidPrimView implementation.
    probe_rigid.set_world_poses(positions=np.array([[start.x, start.y, start.z]]))
    bridge.attach_probe(ProbeState(position=start, velocity=Vec3()))

    now_s = 0.0
    captured_at_s: float | None = None
    result = None

    while now_s < args.duration and simulation_app.is_running():
        rig.step(dt_s, air_velocity=Vec3())
        dock_center = rig.dock_center()
        dock_velocity = rig.dock_velocity()

        # 1. Let PhysX's last integration stand as this step's "flight" —
        #    mirrors DroneBody.step running unconditionally before
        #    mechanism.step in the analytic twin's engine loop.
        positions, _orientations = probe_rigid.get_world_poses()
        velocities = probe_rigid.get_linear_velocities()
        probe_position = Vec3(*positions[0])
        probe_velocity = Vec3(*velocities[0])

        # 2. Hand it to the real mechanism + controller, then adopt the
        #    correction unconditionally — a no-op while probe_phase is FREE.
        #    See bridge.py's module docstring for why this must not branch
        #    on phase and must not toggle the rigid body kinematic.
        bridge.attach_probe(ProbeState(position=probe_position, velocity=probe_velocity))
        commands = DockCommands(capture_enable=True)
        result = bridge.step(now_s, dock_center, dock_velocity, commands)

        corrected = bridge.corrected_probe_state()
        probe_rigid.set_world_poses(
            positions=np.array(
                [[corrected.position.x, corrected.position.y, corrected.position.z]]
            )
        )
        probe_rigid.set_linear_velocities(
            np.array(
                [[corrected.velocity.x, corrected.velocity.y, corrected.velocity.z]]
            )
        )

        # 3. Command the next physics step's force from the corrected state.
        #    Harmless once seated: _hold_at_seat clamps any further forward
        #    push, so this never needs to stop just because the probe caught.
        setpoint = approach.velocity_setpoint(corrected.position, dock_center, dock_velocity)
        force = approach.commanded_force_n(corrected.velocity, setpoint)
        probe_rigid.apply_forces(np.array([[force.x, force.y, force.z]]))

        # Animate the keeper visual (open <-> closed) from the real servo
        # position; the funnel/keeper prims carry no collider (see scene.py).
        keeper_lateral_m = geometry.funnel_entrance_radius_m * (1.0 - bridge.keeper_fraction())
        UsdGeom.XformCommonAPI(UsdGeom.Cube(keeper_prim)).SetTranslate(
            Gf.Vec3d(
                keeper_lateral_m,
                0.0,
                geometry.seat_travel_m - geometry.keeper_capture_window_m / 2.0,
            )
        )
        UsdGeom.XformCommonAPI(UsdGeom.Xform(rig_prim)).SetTranslate(
            Gf.Vec3d(dock_center.x, dock_center.y, dock_center.z)
        )

        world.step(render=not args.headless)
        now_s += dt_s

        if result.controller.capture_confirmed and captured_at_s is None:
            captured_at_s = now_s
            print(f"capture_confirmed at t={now_s:.2f}s")

    final_state = result.controller.state if result is not None else "no_step_ran"
    print(f"done: t={now_s:.2f}s captured_at_s={captured_at_s} final_state={final_state}")


if __name__ == "__main__":
    raise SystemExit(main())
