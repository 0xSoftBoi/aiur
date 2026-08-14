"""What is inside the vehicle: the keeper drive, envelope internals, equipment.

Three groups, and they do not have the same standing - which is the whole
point of separating them here.

**The keeper drive is real.**  `hardware/dock/keeper-drive.md` specifies an
in-line slider-crank with a 6.5 mm crank, a 19.5 mm link, a Ø3 pin at both
joints and the servo axis at x = -40 mm, and `generate_rev_a.py` emits the
crank and link as printable meshes.  Nothing in this section is invented: the
parts are the generated STLs, and `keeper_pin_x` below is the same in-line
slider-crank equation the requirement is written against.

**The gondola equipment is real** in the sense that it is the BOM: the
DYNAMIXEL XL330-M288-T that drives the keeper, the flight battery, the
Lighthouse deck.  Sizes are the vendors' published envelopes.

**The envelope internals are not.**  CARRIER-P0 flies a COTS RC-Zeppelin
B100-I-450-VT, and the vendor publishes length, helium volume and a payload
rating - nothing about ballonets, gas-cell layout or internal rigging.  What
is drawn here is representative geometry so a cutaway reads as an airship
instead of an empty bag, and every piece of it is tagged
`VISUALIZATION_ONLY` and captioned as such on screen.  This is the same
caveat `render_carrier.py` already carries for the tail surfaces, applied to
the one part of the model where it would otherwise be easy to mistake a guess
for a specification.
"""

import math

import bpy

from carrier_model import (
    D, DOCK_BAY_X, DOCK_MOUTH_Z, ENVELOPE_LENGTH_M, GONDOLA_X, GONDOLA_LENGTH,
    HULL_RADIUS_M, MM, active, hull_radius, hull_surface, import_dock_part,
    loft_sections, mesh_object, pbr, put, shade_smooth, streamlined_sections,
)

#: Objects whose geometry is representative rather than specified.  The
#: breakdown captions this on screen; nothing else in the model is allowed to
#: quietly acquire the same status.
VISUALIZATION_ONLY = set()


# --- linkage kinematics ------------------------------------------------------
CRANK_R = D["crank_radius_mm"]
LINK_L = D["link_length_mm"]
KEEPER_PIN_X = D["keeper_pin_x_mm"]
SERVO_AXIS_X = KEEPER_PIN_X - (LINK_L + CRANK_R)
PIN_D = D["drive_pin_diameter_mm"]
PLATE_T = D["drive_plate_thickness_mm"]
KEEPER_T = D["keeper_thickness_mm"]
OPEN_TRAVEL = D["keeper_open_travel_mm"]


def crank_pin(theta):
    """Crank pin position (mm) in the dock frame, for crank angle `theta`."""

    return (SERVO_AXIS_X + CRANK_R * math.cos(theta), CRANK_R * math.sin(theta))


def keeper_pin_x(theta):
    """Keeper pin x (mm) for crank angle `theta`: the in-line slider-crank.

    theta = 0 puts the pin at ``servo + L + R`` - the keeper fully extended,
    tines over the throat, which is how the part is authored.  theta = pi
    retracts it to ``servo + L - R``, exactly ``2R`` = 13 mm away.
    """

    cx, cy = crank_pin(theta)
    return cx + math.sqrt(max(0.0, LINK_L * LINK_L - cy * cy))


def keeper_offset_m(theta):
    """Keeper displacement from its authored (closed) position, in metres."""

    return (keeper_pin_x(theta) - KEEPER_PIN_X) * MM


def link_angle(theta):
    """Link inclination from the x axis (radians), positive counter-clockwise."""

    _, cy = crank_pin(theta)
    return math.asin(max(-1.0, min(1.0, -cy / LINK_L)))


#: Crank angle with the keeper closed and fully open.  Closed is theta = 0
#: because that is the position the parts are authored in.
THETA_CLOSED = 0.0
THETA_OPEN = math.pi


# --- dock frame helpers ------------------------------------------------------
def flange_z():
    """Top of the funnel - the plane the keeper slides on.

    Not depth + flange: the throat bore runs to `funnel_total_height_mm`, and
    the probe head comes up through it.
    """

    return DOCK_MOUTH_Z + D["funnel_total_height_mm"] * MM


def dock_point(x_mm, y_mm, z_offset_m=0.0):
    """Dock-local millimetres to world metres."""

    return (DOCK_BAY_X + x_mm * MM, y_mm * MM, flange_z() + z_offset_m)


#: The drive plate rides just clear of the keeper's top face.
DRIVE_PLANE_Z = (KEEPER_T + 0.6) * MM

#: Gap between the drive plane and the underside of the servo case.
SERVO_STANDOFF = 11.0 * MM


def build_dock_mechanism(materials, carrier=None, appear_frame=None):
    """Servo, crank, link, pins and guides - the mechanism inside the bay.

    `carrier` is the object the mechanism is bolted to (the funnel).  Parenting
    to it makes the whole drive fly in with the dock during assembly without
    any of these parts needing fly-in keyframes of their own, which would
    collide with the linkage bake on the same channels.
    """

    made = {}
    plate_mat = materials["drive"]

    # Crank and link are the generated Rev-B parts, not stand-ins.  Both are
    # authored centred, with their two pin centres at +/- half the bar length.
    crank = import_dock_part("p0a_crank", plate_mat, coll="Mechanism")
    crank.name = "p0a_crank"
    # Origin to the servo axis: the bar's own centre sits half a crank radius
    # from it, so shifting by +R/2 in local x puts the rotation axis on a pin.
    shift_local_x(crank, CRANK_R / 2.0)
    crank.location = dock_point(SERVO_AXIS_X, 0.0, DRIVE_PLANE_Z)
    made["crank"] = crank

    link = import_dock_part("p0a_link", plate_mat, coll="Mechanism")
    link.name = "p0a_link"
    shift_local_x(link, LINK_L / 2.0)
    made["link"] = link  # positioned per-frame by the animation

    # Pins at both joints.
    for name in ("crank_pin", "keeper_pin"):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=PIN_D / 2.0 * MM, depth=(PLATE_T + KEEPER_T + 2.0) * MM,
            vertices=16, location=(0.0, 0.0, 0.0))
        pin = active()
        pin.name = name
        pin.data.materials.append(materials["pin"])
        made[name] = shade_smooth(put(pin, "Mechanism"))

    # Servo: DYNAMIXEL XL330-M288-T, 20 x 34 x 26 mm published envelope, 18 g.
    # Stood off above the drive plane on its output shaft.  Sitting directly on
    # the plane its 34 mm body completely covered a 6.5 mm crank - the servo is
    # larger than the entire linkage it drives.
    servo_bottom = DRIVE_PLANE_Z + SERVO_STANDOFF
    body = loft_sections(
        "keeper_servo",
        [(DOCK_BAY_X + (SERVO_AXIS_X - 17.0 + i * 34.0 / 6) * MM,
          10.0 * MM, 13.0 * MM, 0.0,
          flange_z() + servo_bottom + 13.0 * MM, 6.0)
         for i in range(7)],
        materials["servo"], "Mechanism", segments=16, smooth_angle=18.0)
    made["servo"] = body

    # Output shaft, drive plane up to the servo case.
    bpy.ops.mesh.primitive_cylinder_add(
        radius=2.6 * MM, depth=SERVO_STANDOFF, vertices=16,
        location=dock_point(SERVO_AXIS_X, 0.0,
                            DRIVE_PLANE_Z + SERVO_STANDOFF / 2.0))
    shaft = active()
    shaft.name = "servo_shaft"
    shaft.data.materials.append(materials["pin"])
    made["shaft"] = shade_smooth(put(shaft, "Mechanism"))

    bpy.ops.mesh.primitive_cylinder_add(
        radius=5.5 * MM, depth=4.0 * MM, vertices=20,
        location=dock_point(SERVO_AXIS_X, 0.0, DRIVE_PLANE_Z - 2.0 * MM))
    horn = active()
    horn.name = "servo_horn"
    horn.data.materials.append(materials["servo_horn"])
    made["horn"] = shade_smooth(put(horn, "Mechanism"))

    # Keeper guides: the pair of rails the keeper slides between.  Hard travel
    # stops at both ends are a requirement (P0-DRIVE-003), so they are drawn.
    for side in (-1, 1):
        rail = box_mm(
            f"keeper_guide_{'l' if side < 0 else 'r'}",
            centre=(-9.0, side * (D["keeper_width_mm"] / 2.0 + 1.6), 0.0),
            size=(30.0, 2.6, KEEPER_T + 1.4),
            material=materials["guide"], z_offset=KEEPER_T / 2.0 * MM)
        made[rail.name] = rail
    for x_mm in (-27.5, 3.5):
        stop = box_mm(f"travel_stop_{int(x_mm)}", centre=(x_mm, 0.0, 0.0),
                      size=(2.0, D["keeper_width_mm"] + 6.0, KEEPER_T + 2.0),
                      material=materials["guide"],
                      z_offset=KEEPER_T / 2.0 * MM)
        made[stop.name] = stop

    if carrier is not None:
        inverse = carrier.matrix_world.inverted()
        for obj in made.values():
            obj.parent = carrier
            obj.matrix_parent_inverse = inverse
            if appear_frame is not None:
                for frame, visible in ((1, False), (appear_frame, True)):
                    obj.hide_viewport = not visible
                    obj.hide_render = not visible
                    obj.keyframe_insert("hide_viewport", frame=frame)
                    obj.keyframe_insert("hide_render", frame=frame)
                for curve in obj.animation_data.action.fcurves:
                    if curve.data_path.startswith("hide"):
                        for point in curve.keyframe_points:
                            point.interpolation = "CONSTANT"
    return made


def shift_local_x(obj, delta_mm):
    """Slide a mesh along local x without moving its origin."""

    for vert in obj.data.vertices:
        vert.co.x += delta_mm
    obj.data.update()
    return obj


def box_mm(name, centre, size, material, z_offset=0.0, coll="Mechanism"):
    cx, cy, cz = centre
    sx, sy, sz = size
    bpy.ops.mesh.primitive_cube_add(
        size=1.0, location=dock_point(cx, cy, z_offset + cz * MM))
    obj = active()
    obj.name = name
    obj.scale = (sx * MM, sy * MM, sz * MM)
    obj.data.materials.append(material)
    return put(obj, coll)


def place_linkage(mechanism, theta):
    """Pose crank, link and pins for a crank angle.  Returns keeper offset (m)."""

    from mathutils import Vector

    cx, cy = crank_pin(theta)
    kx = keeper_pin_x(theta)

    mechanism["crank"].rotation_euler = (0.0, 0.0, theta)

    link = mechanism["link"]
    link.location = dock_point(cx, cy, DRIVE_PLANE_Z + PLATE_T * MM)
    link.rotation_euler = (0.0, 0.0, link_angle(theta))

    mechanism["crank_pin"].location = dock_point(cx, cy, DRIVE_PLANE_Z)
    mechanism["keeper_pin"].location = dock_point(kx, 0.0, DRIVE_PLANE_Z)
    return Vector(((kx - KEEPER_PIN_X) * MM, 0.0, 0.0))


# --- envelope internals (representative) -------------------------------------
def build_envelope_internals(materials):
    """Ballonets, gas volume boundary and suspension rigging.

    None of this is vendor-specified.  It is drawn so a cutaway reads as an
    airship rather than an empty bag, and it is tagged so the breakdown can
    caption it honestly.
    """

    made = []
    length = ENVELOPE_LENGTH_M

    # Fore and aft ballonets: air bags inside the helium volume that trim the
    # ship as gas expands.  Sized as a plausible fraction of envelope volume.
    for tag, x0, x1 in (("fore", 0.10, 0.30), ("aft", 0.62, 0.84)):
        sections = []
        count = 20
        for i in range(count):
            s = i / (count - 1)
            x = length * (x0 + (x1 - x0) * s)
            # Sits in the lower half of the envelope, as air is heavier.
            r = hull_radius(x, HULL_RADIUS_M) * 0.62
            taper = math.sin(math.pi * s) ** 0.6
            sections.append((x, r * taper, r * 0.62 * taper, 0.0,
                             -hull_radius(x, HULL_RADIUS_M) * 0.30, 2.4))
        bag = loft_sections(f"ballonet_{tag}", sections, materials["ballonet"],
                            "Internals", segments=28, smooth_angle=40.0)
        VISUALIZATION_ONLY.add(bag.name)
        made.append(bag)

    # Gas volume boundary: a shrunken shell standing in for the lifting gas.
    verts, faces = [], []
    seg, stations = 72, 60
    for i in range(stations):
        s = i / (stations - 1)
        x = 0.04 * length + s * 0.92 * length
        for j in range(seg):
            a = 2.0 * math.pi * j / seg
            r = hull_surface(x, a) * 0.955
            verts.append((x, r * math.cos(a), r * math.sin(a)))
    for i in range(stations - 1):
        a0, b0 = i * seg, (i + 1) * seg
        for j in range(seg):
            k = (j + 1) % seg
            faces.append((a0 + j, b0 + j, b0 + k, a0 + k))
    gas = mesh_object("gas_volume", verts, faces, materials["gas"], "Internals")
    shade_smooth(gas)
    VISUALIZATION_ONLY.add(gas.name)
    made.append(gas)

    # Internal suspension rigging: the curtains that hang the keel load into
    # the envelope fabric instead of into a point.
    for frac in (0.34, 0.46, 0.58, 0.70):
        x = frac * length
        top = hull_radius(x, HULL_RADIUS_M) * 0.86
        for side in (-1, 1):
            curve = bpy.data.curves.new(f"rigging_{int(frac*100)}_{side}", "CURVE")
            curve.dimensions = "3D"
            curve.bevel_depth = 0.004
            spline = curve.splines.new("POLY")
            spline.points.add(2)
            spline.points[0].co = (x, 0.0, -hull_radius(x, HULL_RADIUS_M) - 0.02, 1.0)
            spline.points[1].co = (x, side * top * 0.42, 0.0, 1.0)
            spline.points[2].co = (x, side * top * 0.30, top, 1.0)
            obj = bpy.data.objects.new(curve.name, curve)
            obj.data.materials.append(materials["rigging"])
            put(obj, "Internals")
            VISUALIZATION_ONLY.add(obj.name)
            made.append(obj)
    return made


# --- gondola equipment (BOM) -------------------------------------------------
def build_gondola_equipment(materials, gondola_z):
    """Battery, flight controller and radio deck, at published envelopes."""

    made = []
    base_x = GONDOLA_X + GONDOLA_LENGTH * 0.30

    for name, (dx, w, d, h), mat in (
            ("battery_pack", (0.00, 0.085, 0.055, 0.030), materials["battery"]),
            ("flight_controller", (0.14, 0.050, 0.045, 0.012), materials["pcb"]),
            ("radio_deck", (0.24, 0.045, 0.040, 0.010), materials["pcb"]),
    ):
        bpy.ops.mesh.primitive_cube_add(
            size=1.0, location=(base_x + dx, 0.0, gondola_z + 0.012))
        obj = active()
        obj.name = name
        obj.scale = (w, d, h)
        obj.data.materials.append(mat)
        made.append(put(obj, "Internals"))
    return made


# --- cutaway -----------------------------------------------------------------
def bake_section(name, targets, centre, size, window, coll="Internals"):
    """Cut each target once, keep the result as a static mesh, and swap to it.

    The section never changes shape, so evaluating a boolean every frame is
    paying for the same answer 80 times: a live EXACT boolean on the 21k-vertex
    envelope measured 58 s per frame, against about 5 s without.  Cutting once
    and swapping visibility between the intact object and the sectioned copy
    costs nothing at render time.

    `window` is the (first, last) frame over which the section is on screen.
    """

    first, last = window
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    cutter = bpy.context.view_layer.objects.active
    cutter.name = f"cutter_{name}"
    cutter.scale = size
    put(cutter, coll)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    made = []
    for target in targets:
        if target is None or target.type != "MESH":
            continue
        mod = target.modifiers.new(f"section_{name}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        mod.solver = "EXACT"

        depsgraph.update()
        evaluated = target.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated)
        section = bpy.data.objects.new(f"{target.name}_section", mesh)
        section.matrix_world = target.matrix_world.copy()
        put(section, coll)

        target.modifiers.remove(mod)

        # The intact object steps aside for the window; the section steps in.
        for frame, target_on in ((1, True), (first, False), (last + 1, True)):
            _key_hide(target, frame, not target_on)
            _key_hide(section, frame, target_on)
        made.append(section)

    bpy.data.objects.remove(cutter, do_unlink=True)
    return made


def _key_hide(obj, frame, hidden):
    obj.hide_viewport = hidden
    obj.hide_render = hidden
    obj.keyframe_insert("hide_viewport", frame=frame)
    obj.keyframe_insert("hide_render", frame=frame)
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return
    for curve in action.fcurves:
        if curve.data_path.startswith("hide"):
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"


def build_cutaway(name, targets, centre, size, coll="Internals"):
    """Boolean-difference cutter, applied to every target, off by default.

    A section is the only honest way to show an interior: hiding the outer
    skin instead would leave the parts floating with no indication of what
    encloses them, and half the point of a cutaway is the wall thickness.
    """

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    cutter = active()
    cutter.name = name
    cutter.scale = size
    cutter.display_type = "WIRE"
    cutter.hide_render = True
    put(cutter, coll)

    modifiers = []
    for target in targets:
        if target is None or target.type != "MESH":
            continue
        mod = target.modifiers.new(f"cut_{name}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.object = cutter
        # EXACT, not FAST.  FAST silently returned the mesh unchanged on the
        # envelope - it wants clean manifold input and the hull closes on a
        # 144-vertex n-gon at the tail.  EXACT costs more per frame and
        # actually cuts.
        mod.solver = "EXACT"
        mod.show_render = False
        mod.show_viewport = False
        modifiers.append((target, mod))
    return cutter, modifiers


def key_cutaway(modifiers, frame, enabled):
    """Switch a cutaway on or off, held constant between keys."""

    for target, mod in modifiers:
        mod.show_render = enabled
        mod.show_viewport = enabled
        mod.keyframe_insert("show_render", frame=frame)
        mod.keyframe_insert("show_viewport", frame=frame)
        action = target.animation_data.action if target.animation_data else None
        if action is None:
            continue
        for curve in action.fcurves:
            if mod.name in curve.data_path:
                for point in curve.keyframe_points:
                    point.interpolation = "CONSTANT"


# --- linkage animation -------------------------------------------------------
def animate_keeper_drive(mechanism, keeper, schedule):
    """Drive the keeper from the crank, not by sliding it.

    The keeper's motion is an output of the linkage, so it is baked from
    `keeper_pin_x` frame by frame.  Sliding it linearly - which is what the
    first version did - is wrong by up to 15% of travel at mid-stroke, and it
    also started the keeper in its authored *closed* position and drove it a
    further 13 mm, straight through the throat it is supposed to close over.
    """

    from mathutils import Vector

    base = Vector(keeper.location)
    posed = []

    def pose(frame, theta):
        offset = place_linkage(mechanism, theta)
        keeper.location = base + offset
        keeper.keyframe_insert("location", frame=frame)
        mechanism["crank"].keyframe_insert("rotation_euler", frame=frame)
        for key in ("link",):
            mechanism[key].keyframe_insert("location", frame=frame)
            mechanism[key].keyframe_insert("rotation_euler", frame=frame)
        for key in ("crank_pin", "keeper_pin"):
            mechanism[key].keyframe_insert("location", frame=frame)
        posed.append(frame)

    for index, (frame, theta) in enumerate(schedule):
        if index == 0:
            pose(frame, theta)
            continue
        prev_frame, prev_theta = schedule[index - 1]
        if abs(theta - prev_theta) < 1e-9:
            pose(frame, theta)
            continue
        # Bake every frame across a transition: the relationship between crank
        # angle and keeper position is not linear, so keyframe interpolation
        # between the endpoints would silently straighten it back out.
        for f in range(prev_frame + 1, frame + 1):
            s = (f - prev_frame) / (frame - prev_frame)
            eased = 0.5 - 0.5 * math.cos(math.pi * s)
            pose(f, prev_theta + (theta - prev_theta) * eased)
    return posed


def build_materials():
    return {
        # Dark, because these read against the mounting plate and the funnel
        # flange, both of which are near-white.
        "drive": pbr("drive_plate", (0.085, 0.09, 0.10, 1.0), roughness=0.40,
                     clearcoat=0.3),
        "pin": pbr("drive_pin", (0.62, 0.64, 0.68, 1.0), roughness=0.25,
                   metallic=0.95),
        "servo": pbr("servo_body", (0.10, 0.11, 0.13, 1.0), roughness=0.45),
        "servo_horn": pbr("servo_horn_m", (0.80, 0.78, 0.20, 1.0),
                          roughness=0.38),
        "guide": pbr("keeper_guide", (0.34, 0.35, 0.37, 1.0), roughness=0.40,
                     metallic=0.6),
        "ballonet": pbr("ballonet_skin", (0.42, 0.52, 0.68, 1.0),
                        roughness=0.55),
        "gas": pbr("gas_volume_m", (0.55, 0.72, 0.86, 1.0), roughness=0.30),
        "rigging": pbr("rigging_line", (0.55, 0.56, 0.58, 1.0), roughness=0.6),
        "battery": pbr("battery_m", (0.16, 0.17, 0.20, 1.0), roughness=0.45),
        "pcb": pbr("pcb_m", (0.05, 0.24, 0.14, 1.0), roughness=0.5),
    }
