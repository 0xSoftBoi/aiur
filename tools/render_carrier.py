"""Render the CARRIER-P0 vehicle: envelope, belly dock, and a micro-UAV on final.

Run headless:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/render_carrier.py
    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/render_carrier.py -- carrier-approach --draft

Every dimension here is read from web/lib/carrier-spec.ts or reproduces the
layout in web/components/carrier-scene.tsx, so the still render and the live
Three.js model on the page are the same vehicle rather than two drawings that
happen to look alike.  Where the site draws the dock as a plain cone, this
imports the actual Rev-B fabrication geometry through render_dock, because the
dock is the one part of the vehicle that has real CAD behind it.

Two things are honestly not measured, and the caption on the page has to say
so: the envelope diameter is derived from published length and helium volume
(the vendor does not publish diameter), and the tail surfaces are visual
geometry chosen to read as an airship.  The dock, the probe standoff and the
UAV rotor geometry are the dimensioned parts.

Axis convention: Three.js is Y-up, Blender is Z-up.  A site coordinate
(x, y, z) becomes (x, z, y) here, and `site()` is the only place that
conversion happens.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# render_dock only renders under __main__, so importing it is safe and gives us
# its materials, STL loader, framing and render configuration unchanged.
import render_dock as dock

REPO = dock.REPO
OUT_DIR = dock.OUT_DIR
MM = dock.MM

# --- carrier-spec.ts ---------------------------------------------------------
ENVELOPE_LENGTH_M = 4.5
HELIUM_VOLUME_M3 = 5.5
DOCK_MOUTH_M = 0.18
DOCK_DEPTH_M = 0.065
DRONE_MOTOR_DIAGONAL_M = 0.1
DRONE_PROP_DIAMETER_M = 0.055
DRONE_PROBE_STANDOFF_M = 0.11

#: The vendor publishes length and helium volume but not envelope diameter, so
#: the renderer uses a volume-matched prolate spheroid.  This is a
#: visualization parameter, not a frozen airframe dimension — the same caveat
#: carrier-spec.ts carries.
_SEMI_MAJOR_M = ENVELOPE_LENGTH_M / 2.0
EQUIVALENT_ENVELOPE_DIAMETER_M = 2.0 * math.sqrt(
    HELIUM_VOLUME_M3 / ((4.0 / 3.0) * math.pi * _SEMI_MAJOR_M)
)

# Site palette.
WHITE = (0.86, 0.87, 0.84, 1.0)
GRAPHITE = (0.055, 0.062, 0.065, 1.0)
BLACK = (0.016, 0.018, 0.018, 1.0)
AMBER = (1.0, 0.24, 0.06, 1.0)
STRUCTURAL = (0.055, 0.066, 0.070, 1.0)


def site(x, y, z):
    """Convert a Three.js (Y-up) site coordinate into Blender's Z-up frame."""

    return Vector((x, z, y))


def box(name, size_xyz, location, material, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size_xyz
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    return obj


def cylinder(name, radius, depth, location, material, rotation=(0.0, 0.0, 0.0), verts=48):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=verts, location=location
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, major, minor, location, material, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=64,
        minor_segments=10,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def build_micro_uav(materials, origin, heading=0.0, name="uav"):
    """One P0 micro-UAV, built to the same metric scale as the site model.

    Rotor diameter and probe standoff are dimensioned values: the 110 mm
    standoff is the number that keeps the rotor plane clear of the funnel lip,
    which is the whole reason the aircraft can approach a dock at all.
    """

    parts = []
    half_axis = DRONE_MOTOR_DIAGONAL_M / (2.0 * math.sqrt(2.0))
    arm_length = half_axis * 2.35

    for index, angle in enumerate((math.pi / 4.0, -math.pi / 4.0)):
        parts.append(
            box(
                f"{name}_arm_{index}",
                (arm_length, 0.008, 0.006),
                origin,
                materials["carbon"],
                rotation=(0.0, 0.0, angle),
            )
        )
    parts.append(box(f"{name}_body", (0.032, 0.025, 0.014), origin, materials["carbon"]))

    for index, (dx, dy) in enumerate(
        ((half_axis, half_axis), (half_axis, -half_axis),
         (-half_axis, half_axis), (-half_axis, -half_axis))
    ):
        motor_at = origin + Vector((dx, dy, 0.007))
        parts.append(
            cylinder(f"{name}_motor_{index}", 0.006, 0.012, motor_at, materials["metal"], verts=16)
        )
        parts.append(
            torus(
                f"{name}_rotor_{index}",
                DRONE_PROP_DIAMETER_M / 2.0,
                0.00065,
                origin + Vector((dx, dy, 0.015)),
                materials["rotor"],
            )
        )

    # Nav light: the one emissive thing in the frame, so the eye finds the
    # aircraft before it finds the airship.
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.003, location=origin + Vector((0.014, 0.0, 0.008))
    )
    light = bpy.context.active_object
    light.name = f"{name}_navlight"
    light.data.materials.append(materials["light"])
    bpy.ops.object.shade_smooth()
    parts.append(light)

    # The P0 probe, tip 110 mm above the prop plane.
    parts.append(
        cylinder(f"{name}_probe", 0.0015, 0.1, origin + Vector((0.0, 0.0, 0.058)),
                 materials["metal"], verts=12)
    )
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.006, location=origin + Vector((0.0, 0.0, DRONE_PROBE_STANDOFF_M))
    )
    head = bpy.context.active_object
    head.name = f"{name}_probe_head"
    head.scale.z = 0.7
    head.data.materials.append(materials["metal"])
    bpy.ops.object.shade_smooth()
    parts.append(head)

    if heading:
        for part in parts:
            part.rotation_euler.z += heading
    return parts


def build_carrier(collect=False):
    """Envelope, tail, gondola, propulsion and the belly dock.

    With `collect`, also returns every object created, so a caller can parent
    the vehicle to an empty and scale it — the mission renders reuse this same
    geometry at the 40 m production size.
    """

    existing = set(bpy.data.objects)

    hull_mat = dock.material("hull", GRAPHITE, roughness=0.34, metallic=0.04)
    structural_mat = dock.material("structural", STRUCTURAL, roughness=0.42, metallic=0.62)
    dark_mat = dock.material("dark", BLACK, roughness=0.52, metallic=0.32)
    seam_mat = dock.material("seam", (0.03, 0.035, 0.036, 1.0), roughness=0.6)

    semi_minor = EQUIVALENT_ENVELOPE_DIAMETER_M / 2.0

    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=1.0)
    hull = bpy.context.active_object
    hull.name = "envelope"
    hull.scale = (_SEMI_MAJOR_M, semi_minor, semi_minor)
    hull.data.materials.append(hull_mat)
    bpy.ops.object.shade_smooth()

    # Circumferential construction seams: they make the volume readable without
    # a sci-fi wireframe, and they follow the same spheroid the hull does.
    for station in (-1.55, -0.78, 0.0, 0.78, 1.55):
        radius = semi_minor * math.sqrt(1.0 - (station ** 2) / (_SEMI_MAJOR_M ** 2))
        torus(f"seam_{station}", radius, 0.004, site(station, 0.0, 0.0), seam_mat,
              rotation=(0.0, math.pi / 2.0, 0.0))

    box("fin_horizontal", (0.62, 1.1, 0.025), site(-1.83, 0.0, 0.0), dark_mat,
        rotation=(0.0, -0.09, 0.0))
    box("fin_vertical", (0.62, 0.025, 0.9), site(-1.82, 0.16, 0.0), dark_mat,
        rotation=(0.0, -0.13, 0.0))

    box("rail", (1.62, 0.09, 0.035), site(0.0, -0.79, 0.0), structural_mat)
    box("gondola", (0.82, 0.32, 0.17), site(0.1, -0.87, 0.0), dark_mat)

    # Dual vector-motor platform, kept visually subordinate to the envelope.
    for offset in (-0.42, 0.42):
        pod_at = site(-0.08, -0.81, offset)
        cylinder("pod", 0.085, 0.19, pod_at, structural_mat,
                 rotation=(0.0, math.pi / 2.0, 0.0), verts=24)
        torus("pod_rotor", 0.074, 0.006, pod_at + Vector((0.1, 0.0, 0.0)), dark_mat,
              rotation=(0.0, math.pi / 2.0, 0.0))

    # The dock, as the real Rev-B geometry rather than the site's stand-in cone.
    # The funnel part is authored mouth-down with its mouth at part z=0, so
    # placing it at the mouth plane puts the throat where the site draws it.
    mouth_plane = site(0.22, -1.005 - DOCK_DEPTH_M / 2.0, 0.0)
    funnel_mat = dock.material("dock_funnel", WHITE, roughness=0.5)
    funnel = dock.import_part("p0a_funnel", funnel_mat)
    funnel.location = mouth_plane

    keeper_mat = dock.material("dock_keeper", AMBER, roughness=0.38)
    keeper = dock.import_part("p0a_keeper", keeper_mat)
    keeper.location = mouth_plane + Vector(
        (0.0, 0.0, (dock.D["funnel_depth_mm"] + dock.D["funnel_flange_thickness_mm"]) * MM)
    )

    if collect:
        return mouth_plane, [o for o in bpy.data.objects if o not in existing]
    return mouth_plane


def build_materials():
    return {
        "carbon": dock.material("uav_carbon", (0.02, 0.022, 0.023, 1.0), roughness=0.45),
        "metal": dock.material("uav_metal", (0.32, 0.35, 0.36, 1.0), roughness=0.38, metallic=0.55),
        "rotor": dock.material("uav_rotor", (0.05, 0.055, 0.058, 1.0), roughness=0.6),
        "light": dock.material("uav_light", AMBER, roughness=0.4, emission=AMBER),
    }


def add_lighting():
    """Rig sized for a 4.5 m vehicle, not the 0.18 m dock."""

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = dock.INK
    background.inputs["Strength"].default_value = 0.22

    def area(name, location, energy, size, target=(0.0, 0.0, -0.4)):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.active_object
        light.name = name
        light.data.energy = energy
        light.data.size = size
        light.rotation_euler = (
            (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        )
        return light

    # Inverse-square puts a 4.5 m subject at ~6 m in the low thousands of watts.
    # The first pass used 24 kW and rendered a graphite envelope as paper white,
    # which loses both the seams and the material.
    area("key", (5.0, -6.5, 5.5), 3200.0, 5.0)
    area("fill", (-6.0, -3.0, 0.5), 700.0, 6.0)
    area("rim", (-3.0, 6.5, 3.5), 2600.0, 4.0)
    # The dock is on the belly, which a key light from above puts in full
    # shadow: the one frame that shows a capture was the one frame lit worst.
    # This is a soft bounce from below-front, not a second key.
    area("belly", (1.6, -2.4, -2.6), 260.0, 2.2, target=(0.22, 0.0, -1.05))


#: v1 is the article the programme is actually building: a 4.5 m indoor helium
#: platform, one belly dock, one to two micro-UAVs, tethered and prop-guarded.
#: Nothing in these frames is aspirational — the dock is the real Rev-B
#: fabrication geometry and the probe standoff is the dimensioned 110 mm.  The
#: v2/v3 scaling concepts are separate files and are labelled as concepts.
SHOTS = {
    # The vehicle, three-quarter, dock side toward camera.
    "carrier-v1-hero": dict(direction=(0.55, -1.0, 0.20), focal_mm=55.0, margin=1.04),
    # Tight on the belly: dock, gondola, and the aircraft on final approach.
    "carrier-v1-approach": dict(
        direction=(0.75, -1.0, -0.16), focal_mm=105.0, margin=0.30, aim_offset=-0.16, aim="dock"
    ),
    # Long lens broadside — the silhouette, and the frame that carries scale.
    "carrier-v1-profile": dict(direction=(0.10, -1.0, 0.06), focal_mm=85.0, margin=1.02),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = next((a for a in argv if not a.startswith("--")), None)
    samples = 48 if "--draft" in argv else 256

    dock.clear_scene()
    mouth_plane = build_carrier()
    materials = build_materials()

    # One aircraft on final: probe tip a short distance below the funnel mouth,
    # which is the moment the whole programme exists to make repeatable.
    approach_gap = 0.13
    build_micro_uav(
        materials,
        mouth_plane + Vector((0.0, 0.0, -(approach_gap + DRONE_PROBE_STANDOFF_M))),
        name="uav_final",
    )
    # A second aircraft standing off, because P0 is a 1–2 aircraft article and
    # one drone in frame reads as a toy rather than a fleet.
    build_micro_uav(
        materials,
        mouth_plane + Vector((-0.95, 0.55, -0.75)),
        heading=math.radians(35.0),
        name="uav_standoff",
    )

    add_lighting()
    dock.configure_render(samples=samples)

    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for name, shot in SHOTS.items():
        if only and only != name:
            continue
        for cam in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(cam, do_unlink=True)
        # aim_offset drops the aim point below the dock so the frame holds both
        # the funnel and the aircraft under it, rather than centring the funnel
        # and letting the approach fall out of shot.
        aim = mouth_plane + Vector((0.0, 0.0, shot.get("aim_offset", 0.0)))
        dock.place_camera(shot, aim if shot.get("aim") == "dock" else 0.0)
        bpy.context.scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
        bpy.ops.render.render(write_still=True)
        written.append(bpy.context.scene.render.filepath)

    for path in written:
        print(f"[render] wrote {path}")


if __name__ == "__main__":
    main()
