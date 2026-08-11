"""Render the P0-A Rev-B capture chain from the generated fabrication geometry.

Run headless:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/render_dock.py

The renders on the website are build documents like every other artifact here.
They import the same STLs the printer gets and place them using the same
manifest the tolerance stack reads, so a marketing image cannot drift from the
article the way a hand-modelled one silently would: change a dimension in
generate_rev_a.py, regenerate, re-render, and the picture moves with it.

Assembly placement is derived, not eyeballed.  The funnel is authored mouth-down
with its throat at the top; the keeper rides on the flange face; the probe head
sits with its seat resting on the keeper's upper face, which is the one contact
the whole capture chain is about.  Those three relationships are computed from
manifest values below rather than typed as coordinates, because a coordinate
typed once is a coordinate nobody re-derives when the geometry moves.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = os.path.join(REPO, "hardware", "dock", "cad", "generated")
OUT_DIR = os.path.join(REPO, "web", "public", "renders")

MANIFEST = json.load(open(os.path.join(GENERATED, "p0a_rev_b_manifest.json")))
D = MANIFEST["design"]

#: Blender works in metres; the fabrication geometry is in millimetres.
MM = 0.001

# Site palette, so a render dropped onto the page does not arrive with its own
# opinion about what colour the product is.
INK = (0.012, 0.014, 0.014, 1.0)
WHITE = (0.86, 0.87, 0.84, 1.0)
SIGNAL = (1.0, 0.24, 0.06, 1.0)
STEEL = (0.32, 0.35, 0.36, 1.0)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, base_color, roughness=0.45, metallic=0.0, emission=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        # Blender renamed the emission socket between 3.x and 4.x; look it up
        # rather than assuming, so this script survives a Blender upgrade.
        for socket in ("Emission Color", "Emission"):
            if socket in bsdf.inputs:
                bsdf.inputs[socket].default_value = emission
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 1.0
    return mat


def import_part(stem, mat, z_mm=0.0, rotation_z=0.0):
    """Import one generated STL at its authored scale and place it."""

    path = os.path.join(GENERATED, f"{stem}_rev_b.stl")
    before = set(bpy.data.objects)
    bpy.ops.import_mesh.stl(filepath=path)
    obj = (set(bpy.data.objects) - before).pop()
    obj.name = stem
    # STL units are millimetres and the importer takes them as Blender units.
    obj.scale = (MM, MM, MM)
    obj.location = (0.0, 0.0, z_mm * MM)
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    # Flat-shading the printed facets back onto the funnel cone: the lathe is
    # 64-segment and smooth shading it would render a part rounder than the one
    # that comes off the printer.
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(30.0)
    return obj


def add_mast(top_z_mm, length_mm, mat):
    """The Ø3 mast below the head, which is aircraft-side and not a printed part."""

    radius = D["probe_mast_diameter_mm"] / 2.0 * MM
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=length_mm * MM,
        vertices=48,
        location=(0.0, 0.0, (top_z_mm - length_mm / 2.0) * MM),
    )
    obj = bpy.context.active_object
    obj.name = "probe_mast"
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return obj


def build_assembly():
    """Place the capture chain, deriving every height from the manifest."""

    funnel_mat = material("funnel", WHITE, roughness=0.52)
    keeper_mat = material("keeper", SIGNAL, roughness=0.38)
    # Metal at 0.85 in an unlit world is a mirror of nothing, and the mast
    # rendered as a black stick.  Brushed-aluminium numbers instead.
    probe_mat = material("probe", STEEL, roughness=0.38, metallic=0.55)

    parts = {}
    parts["funnel"] = import_part("p0a_funnel", funnel_mat)

    # The keeper slides across the flange face, which sits directly above the
    # throat: flange top = throat plane + flange thickness.
    flange_top_mm = D["funnel_depth_mm"] + D["funnel_flange_thickness_mm"]
    parts["keeper"] = import_part("p0a_keeper", keeper_mat, z_mm=flange_top_mm)

    # The one contact the capture chain exists to make: the probe's seat rests
    # on the keeper's upper face.  Everything about the probe hangs off this.
    seat_plane_mm = flange_top_mm + D["keeper_thickness_mm"]
    parts["probe_head"] = import_part("p0a_probe_head", probe_mat, z_mm=seat_plane_mm)
    parts["mast"] = add_mast(seat_plane_mm, D["probe_tip_height_above_prop_plane_mm"], probe_mat)

    # Drive linkage.  It lies in the keeper's own plane rather than stacked
    # above it — the crank drives the keeper pin, so anything else is a picture
    # of a mechanism that could not transmit the stroke.
    linkage_z_mm = flange_top_mm - D["drive_plate_thickness_mm"]
    parts["link"] = import_part("p0a_link", probe_mat, z_mm=linkage_z_mm)
    parts["link"].location.x = (D["keeper_pin_x_mm"] - D["link_length_mm"] / 2.0) * MM
    parts["crank"] = import_part("p0a_crank", probe_mat, z_mm=linkage_z_mm)
    parts["crank"].location.x = (D["keeper_pin_x_mm"] - D["link_length_mm"]) * MM

    return parts, seat_plane_mm


def add_lighting():
    """Three-point rig. Key is large and soft; the rim is what reads the edge."""

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = INK
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    def area(name, location, energy, size, target=(0.0, 0.0, 0.06)):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.active_object
        light.name = name
        light.data.energy = energy
        light.data.size = size
        direction = Vector(target) - Vector(location)
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return light

    # Energies are sized for an object about 0.2 m across.  The first pass used
    # studio-for-a-person numbers and clipped the funnel to paper white, which
    # on a near-black page reads as a hole rather than a part.
    area("key", (0.55, -0.50, 0.55), 26.0, 0.60)
    area("fill", (-0.62, -0.28, 0.18), 7.0, 0.80)
    area("rim", (-0.28, 0.62, 0.42), 20.0, 0.45)


def configure_render(samples=192, width=2400, height=1500):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"


def assembly_bounds():
    """World-space bounding box of every mesh in the scene, in metres."""

    # The boolean cutter is a mesh too, and it is much larger than the article.
    # Counting it framed the dock at 3 m and rendered it as a speck.
    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in bpy.data.objects
        if obj.type == "MESH" and not obj.hide_render
        for corner in obj.bound_box
    ]
    low = Vector((min(c[i] for c in corners) for i in range(3)))
    high = Vector((max(c[i] for c in corners) for i in range(3)))
    return low, high


def section_cut():
    """Remove the +Y half of every part, exposing the capture chain.

    The dock is a belly dock: it hangs mouth-down, so an exterior view is a
    cone with everything that matters hidden inside it.  The cross-section
    drawing exists for the same reason, and this is that drawing in three
    dimensions — the seat, the throat and the closed keeper in one frame.
    """

    # Cut the half FACING the camera away.  Removing the far half leaves the
    # intact near wall between the viewer and everything worth seeing, which
    # renders as an ordinary cone and hides the cut entirely.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -0.30, 0.0))
    cutter = bpy.context.active_object
    cutter.name = "section_cutter"
    cutter.scale = (0.6, 0.6, 0.6)

    for obj in [o for o in bpy.data.objects if o.type == "MESH" and o is not cutter]:
        modifier = obj.modifiers.new(name="section", type="BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.object = cutter
        # EXACT keeps the cut faces clean on the thin keeper plate; FAST leaves
        # shards on a 2.5 mm part.
        modifier.solver = "EXACT"

    cutter.hide_render = True
    cutter.hide_viewport = True
    return cutter


#: Each shot is a viewing direction and how much room to leave around the
#: subject, so framing survives a geometry change instead of needing camera
#: coordinates retyped every time a dimension moves.  Negative Z looks up into
#: the mouth, which is the only direction the capture is visible from.
SHOTS = {
    # The approach the aircraft actually flies: up into the mouth.
    "dock-hero": dict(direction=(0.62, -1.0, -0.46), focal_mm=80.0, margin=1.20),
    # The cross-section drawing, in three dimensions.
    "dock-section": dict(
        direction=(0.30, -1.0, 0.10), focal_mm=90.0, margin=1.15, section=True
    ),
    # Close on the throat, where the capture actually happens.
    "dock-capture-detail": dict(
        direction=(0.55, -1.0, 0.16), focal_mm=115.0, margin=0.55,
        aim="seat", section=True,
    ),
}


def place_camera(shot, aim_z_m):
    """Frame a shot.  A shot with an `aim` looks at aim_z_m on the axis rather
    than at the bounding-box centre, which is how a detail shot gets to point
    at one feature instead of at the average of everything in the scene."""

    low, high = assembly_bounds()
    centre = (low + high) / 2.0
    if shot.get("aim"):
        # A float aims at a height on the axis; a Vector aims at a point, which
        # a detail shot on an off-axis feature needs.
        centre = (
            Vector(aim_z_m)
            if hasattr(aim_z_m, "__len__")
            else Vector((centre.x, centre.y, aim_z_m))
        )

    extent = max((high - low).x, (high - low).z)
    direction = Vector(shot["direction"]).normalized()

    # Distance that fits `extent * margin` across the sensor at this focal
    # length: the sensor is 36 mm wide by default and the frame is landscape,
    # so the vertical extent is the binding one.
    scene = bpy.context.scene
    sensor_h = 36.0 * scene.render.resolution_y / scene.render.resolution_x
    distance = (extent * shot["margin"]) * shot["focal_mm"] / sensor_h

    location = centre + direction * distance
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.active_object
    cam.data.lens = shot["focal_mm"]
    cam.rotation_euler = (centre - location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    return cam


def render(name, out_dir):
    scene = bpy.context.scene
    scene.render.filepath = os.path.join(out_dir, name + ".png")
    bpy.ops.render.render(write_still=True)
    return scene.render.filepath


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = argv[0] if argv else None
    # A draft flag, because iterating on framing at 192 samples is a way to
    # spend an afternoon looking at a progress bar.
    samples = 48 if "--draft" in argv else 192

    clear_scene()
    parts, seat_plane_mm = build_assembly()
    add_lighting()
    configure_render(samples=samples)

    os.makedirs(OUT_DIR, exist_ok=True)

    written = []
    cutter = None
    for name, shot in SHOTS.items():
        if only and not only.startswith("--") and only != name:
            continue
        for cam in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(cam, do_unlink=True)

        # The cut is applied once and left in place; shots are ordered so the
        # solid views render before the sectioned ones.
        if shot.get("section") and cutter is None:
            cutter = section_cut()

        place_camera(shot, seat_plane_mm * MM)
        written.append(render(name, OUT_DIR))

    for path in written:
        print(f"[render] wrote {path}")


if __name__ == "__main__":
    main()
