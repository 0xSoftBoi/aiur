"""The indoor test hall CARRIER-P0 actually flies in.

The vehicle renders were shot against a grey gradient, which is the visual
equivalent of a spec sheet with no units: nothing establishes scale, nothing
grounds the aircraft, and the lighting comes from nowhere.  P0 is not an
abstract object.  The programme scope is explicit about what it is - helium
lift, one belly dock, tethered and prop-guarded indoor operations, and
"high-precision externally referenced positioning".  Every one of those is a
thing you can see in a room.

So this module builds the room: a hall floored and walled at a size that suits
a 4.5 m airship, an overhead truss grid carrying the fixtures that actually
light the scene, the external motion-capture cameras that provide the
positioning reference, painted floor markings for the operating box, and the
tether.  The haze is not decoration either - it is what makes a 20 m room read
as 20 m deep instead of a flat backdrop.

Everything here is set dressing and is labelled as such.  No dimension in this
file feeds anything but the render.
"""

import math

import bpy

from carrier_model import (
    DOCK_BAY_X, HULL_RADIUS_M, active, hull_radius, pbr, put, shade_smooth,
)

# --- hall envelope -----------------------------------------------------------
#: Sized so the camera path stays inside the room.  The widest camera station
#: sits at y = -7.8, so the walls have to be beyond that or the lens flies
#: through them.
HALL_X0, HALL_X1 = -7.5, 13.5
HALL_Y = 9.5
FLOOR_Z = -3.6
CEILING_Z = 4.4

TRUSS_Z = 3.55
TRUSS_LINES = (-4.6, 0.0, 4.6)
#: Fixtures hang on every truss line, not just the outer pair.  Eight lamps
#: could not light a 20 m hall: the subject sits 3 m under the rig and the
#: floor 6.7 m under it, so inverse-square alone leaves the floor at a fifth of
#: the vehicle's exposure and the room read as an empty grey box.
FIXTURES_X = (-4.0, -0.5, 3.0, 6.5, 10.0)


def box(name, centre, size, material, coll, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre,
                                    rotation=rotation)
    obj = active()
    obj.name = name
    obj.scale = size
    obj.data.materials.append(material)
    return put(obj, coll)


def build_materials():
    return {
        "floor": pbr("hall_floor", (0.055, 0.058, 0.062, 1.0), roughness=0.42,
                     specular=0.5),
        "paint": pbr("floor_paint", (0.36, 0.37, 0.30, 1.0), roughness=0.65),
        "paint_hot": pbr("floor_paint_hot", (0.52, 0.28, 0.06, 1.0),
                         roughness=0.62),
        "wall": pbr("hall_wall", (0.042, 0.045, 0.050, 1.0), roughness=0.80),
        "truss": pbr("truss_steel", (0.14, 0.145, 0.155, 1.0), roughness=0.42,
                     metallic=0.75),
        "fixture": pbr("hall_fixture", (0.8, 0.8, 0.8, 1.0), roughness=0.3,
                       emission=(1.0, 0.94, 0.84, 1.0), emission_strength=9.0),
        "fixture_body": pbr("fixture_body", (0.10, 0.105, 0.11, 1.0),
                            roughness=0.45, metallic=0.6),
        "mocap": pbr("mocap_body", (0.085, 0.09, 0.095, 1.0), roughness=0.40),
        "mocap_ring": pbr("mocap_ring", (0.35, 0.05, 0.05, 1.0), roughness=0.35,
                          emission=(1.0, 0.10, 0.06, 1.0),
                          emission_strength=3.5),
        "tether": pbr("tether_line", (0.30, 0.31, 0.30, 1.0), roughness=0.7),
        "anchor": pbr("tether_anchor", (0.22, 0.23, 0.24, 1.0), roughness=0.45,
                      metallic=0.6),
    }


def build_shell(m):
    """Floor, walls and ceiling."""

    made = []
    cx = (HALL_X0 + HALL_X1) * 0.5
    length = HALL_X1 - HALL_X0

    made.append(box("hall_floor", (cx, 0.0, FLOOR_Z - 0.1),
                    (length, HALL_Y * 2.0, 0.2), m["floor"], "Stage"))
    made.append(box("hall_ceiling", (cx, 0.0, CEILING_Z + 0.1),
                    (length, HALL_Y * 2.0, 0.2), m["wall"], "Stage"))
    for side in (-1, 1):
        made.append(box(f"hall_wall_y{side}", (cx, side * (HALL_Y + 0.1), 0.4),
                        (length, 0.2, CEILING_Z - FLOOR_Z), m["wall"], "Stage"))
    made.append(box("hall_wall_far", (HALL_X1 + 0.1, 0.0, 0.4),
                    (0.2, HALL_Y * 2.0, CEILING_Z - FLOOR_Z), m["wall"], "Stage"))
    made.append(box("hall_wall_near", (HALL_X0 - 0.1, 0.0, 0.4),
                    (0.2, HALL_Y * 2.0, CEILING_Z - FLOOR_Z), m["wall"], "Stage"))
    return made


def build_floor_markings(m):
    """Painted operating box and a dock-station cross under the belly dock.

    The cross sits directly under the dock rather than under the vehicle
    centre, because the thing being marked on a real floor is the capture
    station, not the airship.
    """

    made = []
    z = FLOOR_Z + 0.006

    def stripe(name, centre, size, material=None):
        made.append(box(name, (centre[0], centre[1], z), (size[0], size[1], 0.01),
                        material or m["paint"], "Stage"))

    # Operating box outline.
    x0, x1, y0, y1 = -2.0, 8.0, -4.4, 4.4
    w = 0.09
    stripe("ops_box_n", ((x0 + x1) / 2, y1), (x1 - x0, w))
    stripe("ops_box_s", ((x0 + x1) / 2, y0), (x1 - x0, w))
    stripe("ops_box_e", (x1, (y0 + y1) / 2), (w, y1 - y0))
    stripe("ops_box_w", (x0, (y0 + y1) / 2), (w, y1 - y0))

    # Dock station cross, directly under the capture point.  At 75 mm wide it
    # was invisible from any camera far enough away to show the hall.
    stripe("dock_station_x", (DOCK_BAY_X, 0.0), (2.2, 0.14), m["paint_hot"])
    stripe("dock_station_y", (DOCK_BAY_X, 0.0), (0.14, 2.2), m["paint_hot"])
    for dx, dy in ((0.85, 0.85), (0.85, -0.85), (-0.85, 0.85), (-0.85, -0.85)):
        stripe(f"dock_corner_{dx}_{dy}", (DOCK_BAY_X + dx, dy), (0.40, 0.10),
               m["paint_hot"])

    # Hazard hatching along the near edge of the box.
    for i in range(14):
        stripe(f"hazard_{i:02d}", (x0 + 0.35 + i * 0.72, y0 - 0.55),
               (0.42, 0.16))
    return made


def build_truss_rig(m):
    """Overhead truss grid and the fixtures that light the hall.

    The fixture positions are returned so the lighting rig can be hung exactly
    where the geometry says the lights are.  Lighting a scene from lamps that
    do not correspond to anything visible is the thing that makes an interior
    look like a model on a table.
    """

    made, fixtures = [], []
    length = HALL_X1 - HALL_X0
    cx = (HALL_X0 + HALL_X1) * 0.5

    for line_y in TRUSS_LINES:
        # Main chord pair plus a web, read as a truss without the vertex cost.
        for dz in (-0.16, 0.16):
            made.append(box(f"truss_chord_{line_y}_{dz}",
                            (cx, line_y, TRUSS_Z + dz),
                            (length, 0.09, 0.09), m["truss"], "Stage"))
        for i in range(int(length / 0.8)):
            x = HALL_X0 + 0.4 + i * 0.8
            made.append(box(f"truss_web_{line_y}_{i}", (x, line_y, TRUSS_Z),
                            (0.05, 0.05, 0.34), m["truss"], "Stage"))

    # Cross beams tying the lines together.
    for x in (-4.0, 1.0, 6.0, 11.0):
        made.append(box(f"truss_cross_{x}", (x, 0.0, TRUSS_Z + 0.22),
                        (0.08, (TRUSS_LINES[-1] - TRUSS_LINES[0]), 0.08),
                        m["truss"], "Stage"))

    # Hanging fixtures.
    for line_y in TRUSS_LINES:
        for x in FIXTURES_X:
            z = TRUSS_Z - 0.42
            made.append(box(f"fixture_body_{x}_{line_y}", (x, line_y, z + 0.10),
                            (0.68, 0.34, 0.16), m["fixture_body"], "Stage"))
            made.append(box(f"fixture_lens_{x}_{line_y}", (x, line_y, z + 0.01),
                            (0.62, 0.30, 0.03), m["fixture"], "Stage"))
            for dx in (-0.22, 0.22):
                made.append(box(f"fixture_drop_{x}_{line_y}_{dx}",
                                (x + dx, line_y, z + 0.34),
                                (0.03, 0.03, 0.34), m["truss"], "Stage"))
            fixtures.append((x, line_y, z))
    return made, fixtures


def build_mocap(m, target=(2.25, 0.0, -0.4)):
    """External motion-capture cameras on the truss corners.

    P0's positioning is externally referenced, and this is what that looks
    like: a ring of cameras on the rig, all pointed at the operating volume.
    """

    from mathutils import Vector

    made = []
    stations = []
    for x in (-2.6, 2.4, 7.4):
        for y in (TRUSS_LINES[0] - 0.35, TRUSS_LINES[-1] + 0.35):
            stations.append((x, y, TRUSS_Z - 0.30))
    for x in (0.2, 5.6):
        for y in (-HALL_Y + 0.6, HALL_Y - 0.6):
            stations.append((x, y, 1.5))

    for index, station in enumerate(stations):
        aim = (Vector(target) - Vector(station)).to_track_quat("-Z", "Y").to_euler()
        body = box(f"mocap_{index:02d}", station, (0.14, 0.10, 0.11),
                   m["mocap"], "Stage", rotation=aim)
        made.append(body)

        # IR ring on the front face.
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.055, minor_radius=0.012,
            major_segments=18, minor_segments=6, location=station)
        ring = active()
        ring.name = f"mocap_ring_{index:02d}"
        ring.rotation_euler = aim
        ring.data.materials.append(m["mocap_ring"])
        offset = Vector((0.0, 0.0, -0.07))
        offset.rotate(aim)
        ring.location = Vector(station) + offset
        made.append(shade_smooth(put(ring, "Stage")))

        # Mounting arm back up to the truss where the station hangs from one.
        if station[2] > 1.0:
            made.append(box(f"mocap_arm_{index:02d}",
                            (station[0], station[1], station[2] + 0.22),
                            (0.04, 0.04, 0.34), m["truss"], "Stage"))
    return made, stations


def build_tether(m, attach=(1.30, 0.0, None), anchor=(0.10, 1.55, None),
                 segments=28):
    """The safety tether, hanging as a catenary between anchor and keel.

    P0 is a tethered article.  A straight line would read as a wire; a real
    tether under its own weight sags, and the sag is most of what tells you it
    is a rope and not a strut.
    """

    made = []
    ax, ay, _ = attach
    attach_z = -hull_radius(ax, HULL_RADIUS_M) - 0.075
    gx, gy, _ = anchor
    ground_z = FLOOR_Z + 0.06

    # Floor anchor plate and cleat.
    made.append(box("tether_anchor_plate", (gx, gy, ground_z - 0.03),
                    (0.34, 0.34, 0.05), m["anchor"], "Stage"))
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.035, depth=0.16, vertices=16,
        location=(gx, gy, ground_z + 0.07))
    cleat = active()
    cleat.name = "tether_cleat"
    cleat.data.materials.append(m["anchor"])
    made.append(shade_smooth(put(cleat, "Stage")))

    curve = bpy.data.curves.new("tether", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.009
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(segments - 1)

    span = math.dist((ax, ay), (gx, gy))
    #: Slack as a fraction of span; a taut tether looks like scaffolding.
    sag = span * 0.16
    for i in range(segments):
        s = i / (segments - 1)
        x = gx + (ax - gx) * s
        y = gy + (ay - gy) * s
        z = ground_z + (attach_z - ground_z) * s
        # Catenary approximated by a parabola: exact enough at this span, and
        # the shape is what matters, not the hyperbolic cosine.
        z -= sag * 4.0 * s * (1.0 - s)
        spline.points[i].co = (x, y, z, 1.0)

    obj = bpy.data.objects.new("tether", curve)
    obj.data.materials.append(m["tether"])
    made.append(put(obj, "Stage"))
    return made


def build_atmosphere(strength=0.30, start=13.0, depth=26.0,
                     color=(0.16, 0.19, 0.24)):
    """Depth haze, composited from the mist pass rather than ray-marched.

    True volumetric scatter looks better - it throws real shafts from the
    ceiling fixtures - and it was measured at roughly ten seconds a frame on
    top of everything else, which is four and a half hours across the sequence,
    and it segfaulted the renderer under heavy sampling.  The mist pass buys
    the thing that actually matters here, aerial perspective telling the eye
    the far wall is twenty metres away, for effectively no render cost and no
    stability risk.  What it does not buy is light shafts; bloom on the
    emissive fixtures stands in for those.
    """

    scene = bpy.context.scene
    scene.view_layers[0].use_pass_mist = True

    mist = scene.world.mist_settings
    mist.use_mist = True
    mist.start = start
    mist.depth = depth
    mist.falloff = "QUADRATIC"

    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    layers = nt.nodes.new("CompositorNodeRLayers")
    output = nt.nodes.new("CompositorNodeComposite")
    blend = nt.nodes.new("CompositorNodeMixRGB")
    blend.inputs[2].default_value = (*color, 1.0)
    gain = nt.nodes.new("CompositorNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = strength

    nt.links.new(layers.outputs["Mist"], gain.inputs[0])
    nt.links.new(gain.outputs[0], blend.inputs[0])
    nt.links.new(layers.outputs["Image"], blend.inputs[1])
    nt.links.new(blend.outputs[0], output.inputs["Image"])

    scene.eevee.use_volumetric_lights = False
    return blend


def stage_lighting(fixtures, dock=(DOCK_BAY_X, 0.0, -1.05), scale=1.0):
    """Hang the practical lights on the fixtures, plus one belly bounce.

    The overhead rig is motivated: every lamp sits inside a fixture you can
    see.  The belly bounce is not, and cannot be - the dock faces the floor,
    and no ceiling rig will ever light it.  On a real shoot that is a bounce
    card, which is exactly what this is.
    """

    from carrier_model import area_light

    made = []
    for index, (x, y, z) in enumerate(fixtures):
        lamp = area_light(
            f"practical_{index:02d}", (x, y, z - 0.06), 250.0 * scale, 0.55,
            (x, y * 0.25, -0.6))
        # Only the lamps over the operating box cast shadows.  Fifteen
        # shadow-casting practicals is a shadow map per lamp per frame for
        # almost no visible gain - the rest are fill, which is how a real rig
        # is run too.
        lamp.data.use_shadow = abs(x - DOCK_BAY_X) < 4.5 and abs(y) < 1.0
        made.append(lamp)

    made.append(area_light("belly_bounce", (3.2, -2.6, FLOOR_Z + 0.5),
                           220.0 * scale, 3.2, dock))
    made.append(area_light("dock_accent", (1.4, -1.5, -2.4), 45.0 * scale, 0.9,
                           dock))
    # The rake is now a shaping light, not a key - the rig above does that job.
    made.append(area_light("key_rake", (7.6, -7.2, 2.6), 180.0 * scale, 3.0,
                           (2.4, 0.0, -0.2)))

    # Wall wash.  The tight shots push in until the floor and truss fall
    # outside the frame, and with nothing lit behind the subject the whole
    # background collapsed to black - which threw away the hall in exactly the
    # shots that matter most.  Washing the far walls puts a lit surface behind
    # the action and gives the vehicle an edge to separate against, without
    # moving a single camera off the mechanism.
    # Kept low.  At 620 W the far wall came up bright enough to compete with a
    # white envelope, trading a black background for a flat one; the job here
    # is a dim gradient to separate against, not a second key.
    made.append(area_light("wall_wash_far", (2.6, 5.6, -0.4), 240.0 * scale,
                           4.5, (2.6, 9.4, -0.6)))
    made.append(area_light("wall_wash_end", (10.4, -1.0, 0.2), 170.0 * scale,
                           4.0, (13.3, -1.0, 0.0)))
    return made


def build_stage(vehicle_lighting=None):
    """Build the whole hall.  Returns handles the animation may want."""

    m = build_materials()
    made = []
    made += build_shell(m)
    made += build_floor_markings(m)
    truss, fixtures = build_truss_rig(m)
    made += truss
    mocap, stations = build_mocap(m)
    made += mocap
    tether = build_tether(m)
    made += tether

    # The vehicle's own studio rig is replaced by the hall's practicals.
    for obj in list(vehicle_lighting or []):
        bpy.data.objects.remove(obj, do_unlink=True)

    lights = stage_lighting(fixtures)
    build_atmosphere()
    return {"objects": made, "fixtures": fixtures, "mocap": stations,
            "tether": tether, "lights": lights, "materials": m}
