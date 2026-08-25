"""Builds the CARRIER-P0 SIL-P0-B stage in Isaac Sim.

**Unexecuted.** Written against the Isaac Sim 4.5 / 5.0 ``isaacsim.core.api``
namespace (the current package layout at
https://developer.nvidia.com/isaac/sim as of this writing). Nobody has run
this against a real install — every call tagged ``# VERIFY:`` is the
highest-risk guess in this file and is exactly where a first run is likely
to need a patch. If you're on an older install still using the
``omni.isaac.core`` namespace (pre-4.5), the ``objects``/``World`` symbols
below moved from ``omni.isaac.core`` -> ``isaacsim.core.api`` and
``omni.isaac.core.utils`` -> ``isaacsim.core.utils``; swap the import roots
and the rest should hold.

Geometry and mass are not invented here — they are read from the same
dataclasses the analytic twin uses (``aiur.sim.bodies``,
``aiur.sim.dock_physics``), so this scene and ``aiur/sim`` cannot silently
drift apart on what P0-B's dimensions are.

Contact-ownership contract: the funnel and keeper prims are **visual only**
(no ``UsdPhysics.CollisionAPI``). ``aiur.sim.dock_physics.DockAssembly``
(driven through ``bridge.IsaacTwinBridge``) is the sole contact authority —
see bridge.py's module docstring before changing this.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sim.bodies import DroneParams
from ..sim.dock_physics import DockGeometry

#: Isaac Sim stage paths used by run_p0b.py. Centralized so scene.py and the
#: run loop cannot silently disagree on where a prim lives.
GROUND_PATH = "/World/ground"
RIG_PATH = "/World/dock_rig"
FUNNEL_PATH = "/World/dock_rig/funnel"
KEEPER_PATH = "/World/dock_rig/keeper"
PROBE_PATH = "/World/probe"


@dataclass(frozen=True)
class SceneHandles:
    """Prim paths the run loop needs each step. Returned by :func:`build_stage`."""

    rig_path: str = RIG_PATH
    keeper_path: str = KEEPER_PATH
    probe_path: str = PROBE_PATH


def build_stage(
    *,
    drone_params: DroneParams = DroneParams(),
    geometry: DockGeometry = DockGeometry(),
) -> SceneHandles:
    """Create ground, dock rig (funnel + keeper), and probe prims.

    SIL-P0-B has no carrier hull to model: it mirrors the P0-B bench
    article, a moving suspended dock rig with no gas envelope (see
    ``aiur.sim.bodies.KinematicRig``). A P0-C/P0-D scene builder would add a
    carrier hull sized from ``aiur.sim.bodies.CarrierParams``; out of scope
    here.

    Must be called after ``SimulationApp`` has been constructed (Isaac Sim
    requires the app/renderer to exist before ``omni``/``pxr`` extension
    modules are imported), which is why every Isaac/omni/pxr import in this
    module is local to this function rather than at module scope.
    """

    # VERIFY: exact import roots against the installed Isaac Sim version.
    import numpy as np
    from pxr import Gf, UsdGeom
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import DynamicSphere, GroundPlane
    from isaacsim.core.utils.stage import get_current_stage

    world = World.instance() if World.instance() is not None else World()
    stage = get_current_stage()

    # VERIFY: GroundPlane's constructor signature (prim_path, z_position, ...)
    # across versions; some releases expose this as world.scene.add_default_ground_plane().
    GroundPlane(prim_path=GROUND_PATH, z_position=0.0)

    # Dock rig root: a plain Xform, not a rigid body — its pose is written
    # kinematically every step from bodies.KinematicRig, matching the
    # analytic twin's SIL-P0-B bench-rig model (no gas envelope, no physics
    # integration of its own).
    rig_xform = UsdGeom.Xform.Define(stage, RIG_PATH)
    UsdGeom.XformCommonAPI(rig_xform).SetTranslate(Gf.Vec3d(0.0, 0.0, 0.0))

    # Funnel: a visual cone sized from the real geometry, entrance-down.
    # Visual only (see module docstring) — no CollisionAPI applied.
    funnel = UsdGeom.Cone.Define(stage, FUNNEL_PATH)
    funnel.CreateRadiusAttr(geometry.funnel_entrance_radius_m)
    funnel.CreateHeightAttr(geometry.seat_travel_m)
    funnel.CreateAxisAttr("Z")
    UsdGeom.XformCommonAPI(funnel).SetTranslate(
        Gf.Vec3d(0.0, 0.0, geometry.seat_travel_m / 2.0)
    )

    # Keeper: a thin visual box standing in for the sliding-fork keeper arm.
    # Its pose (open/closed) is written every step from
    # bridge.IsaacTwinBridge.keeper_fraction() — see run_p0b.py. Visual only.
    keeper = UsdGeom.Cube.Define(stage, KEEPER_PATH)
    keeper.CreateSizeAttr(1.0)
    UsdGeom.XformCommonAPI(keeper).SetScale(
        Gf.Vec3f(
            2.0 * geometry.funnel_entrance_radius_m,
            0.01,
            geometry.probe_height_m,
        )
    )

    # Probe (micro-UAV): the one prim with real rigid-body physics. Radius
    # and mass are the vendor/estimate figures from aiur.sim.bodies, not
    # invented for the scene.
    probe = DynamicSphere(
        prim_path=PROBE_PATH,
        name="probe",
        radius=drone_params.body_radius_m,
        mass=drone_params.mass_kg,
        color=np.array([0.9, 0.2, 0.2]),
    )
    world.scene.add(probe)

    # The probe keeps DynamicSphere's default UsdPhysics.CollisionAPI so it
    # collides with the ground outside the funnel; the funnel/keeper prims
    # above were deliberately never given CollisionAPI, so there is no
    # collision to exclude rather than one to suppress via a collision group.

    # aiur.sim.bodies.DroneBody's velocity-tracking law (which
    # flight.ApproachController mirrors) models a closed-loop-controlled
    # quadrotor that already rejects gravity through its own attitude/thrust
    # loop — it has no gravity term at all. A PhysX DynamicSphere does not
    # get that for free, so gravity is disabled on the probe here; otherwise
    # ApproachController's force law (ported from a gravity-free model)
    # cannot hold the vehicle up and run_p0b.py would just watch it fall.
    # VERIFY: PhysxSchema.PhysxRigidBodyAPI is the right schema/attribute
    # name for this on the installed Isaac Sim version.
    from pxr import PhysxSchema

    physx_rigid_body = PhysxSchema.PhysxRigidBodyAPI.Apply(probe.prim)
    physx_rigid_body.CreateDisableGravityAttr(True)

    return SceneHandles()
