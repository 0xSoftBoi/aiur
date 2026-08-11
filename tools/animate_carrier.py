"""Animate the CARRIER-P0 vehicle: an assembly breakdown, then a live capture.

Two acts, one continuous camera move:

* **Assembly** - the bare envelope, then each subassembly flying into place in
  the order it would actually be installed: tail surfaces, keel, gondola,
  propulsion, belly dock, and finally the aircraft the whole thing exists to
  recover.
* **Capture** - the finished vehicle, with a micro-UAV flying the approach and
  the Rev-B keeper closing over the probe head.  This is the manoeuvre
  CARRIER-P0 was funded to prove, so it is the one that gets the long lens.

Every position here comes from `carrier_model`, which in turn derives the dock
geometry from the Rev-B fabrication manifest.  The capture altitude is not
art-directed: the probe head stops where the funnel throat actually is.

Run headless:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/animate_carrier.py
"""

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import carrier_model as cm  # noqa: E402

FPS = 30
END_FRAME = 720

#: Assembly order: (group name, start frame, travel frames, explode offset).
#: `None` as an offset means "derive it per object from which side it is on",
#: which is how the two nacelles separate outboard instead of moving together.
#: Each install lands inside the shot that covers it - see SHOTS.
ASSEMBLY = [
    ("Tail surfaces", 80, 62, (2.60, 0.0, 0.0)),
    ("Keel structure", 160, 58, (0.0, 0.0, -1.35)),
    ("Gondola", 230, 58, (0.0, -1.75, -0.85)),
    ("Propulsion", 300, 58, None),
    ("Belly dock", 370, 56, (0.0, 0.0, -1.60)),
    ("Micro-UAV", 442, 50, (0.90, 1.30, -1.30)),
]

#: Coverage, not a single move.  The first version of this was one unbroken
#: 32-second dolly, which no one shoots: it gives every beat the same size, the
#: same lens and the same energy.  These are ten discrete shots, each with its
#: own framing and a move inside it, cut hard at the boundaries.
#:
#: (start, end, cam_start, cam_end, aim_start, aim_end, lens_start, lens_end)
SHOTS = [
    # -- assembly --------------------------------------------------------
    # Establish the hall first, so the vehicle has somewhere to be.
    (1, 74, (-6.2, -9.0, 2.9), (-5.1, -8.1, 2.1),
     (3.0, 0.0, -1.30), (2.8, 0.0, -0.55), 20.0, 23.0),
    # Low and long on the tail as the surfaces arrive.
    (75, 154, (6.8, -6.6, 1.7), (5.5, -5.7, 1.1),
     (3.95, 0.0, 0.10), (3.90, 0.0, -0.05), 55.0, 62.0),
    # Belly track for the keel.
    (155, 224, (0.1, -4.6, -2.15), (2.7, -4.1, -1.90),
     (2.15, 0.0, -0.88), (2.65, 0.0, -0.86), 40.0, 44.0),
    (225, 294, (-1.7, -4.3, -1.55), (-0.5, -3.7, -1.20),
     (1.45, 0.0, -1.02), (1.75, 0.0, -0.95), 58.0, 66.0),
    # Aimed at the port nacelle itself, not the vehicle centreline.  Framed on
    # the centreline the pylon sat square between lens and duct and hid the one
    # component the shot is named after.
    (295, 364, (0.15, -4.7, -1.45), (1.15, -4.05, -1.10),
     (2.24, -0.90, -0.64), (2.30, -0.87, -0.58), 58.0, 68.0),
    # Wider and aimed low at the start: the dock flies up from 1.6 m below its
    # station, and framed on its final position it spent most of the shot
    # under the bottom edge.
    (365, 434, (5.3, -3.9, -2.20), (3.9, -3.0, -1.92),
     (2.55, 0.0, -1.52), (2.50, 0.0, -1.06), 46.0, 60.0),
    # -- capture ---------------------------------------------------------
    (435, 504, (0.3, -5.1, -2.65), (1.3, -4.4, -2.40),
     (2.15, 0.0, -1.45), (2.40, 0.0, -1.35), 34.0, 39.0),
    (505, 574, (0.9, -3.1, -2.35), (1.9, -2.5, -2.00),
     (2.40, 0.0, -1.52), (2.46, 0.0, -1.24), 54.0, 63.0),
    # Tight on the throat, level with it - the keeper closes at the top of the
    # funnel and a camera under the cone cannot see it.
    (575, 648, (2.85, -1.65, -1.52), (3.00, -1.36, -1.14),
     (2.47, 0.0, -1.12), (2.47, 0.0, -1.00), 78.0, 92.0),
    (649, 720, (3.05, -1.24, -1.00), (2.55, -1.95, -0.92),
     (2.47, 0.0, -0.99), (2.47, 0.0, -1.02), 95.0, 84.0),
]

#: Handheld micro-movement.  A camera locked to a mathematically perfect path
#: is one of the loudest tells in CG; even a rig on rails breathes.
SHAKE_STRENGTH = 0.013
SHAKE_SCALE = 16.0

#: Housings that go translucent for the capture, so the mechanism is visible.
#: The keeper closes inside the funnel throat, behind both the funnel wall and
#: the bay fairing - opaque, the money shot is a cone with a drone under it.
GHOSTED = ("funnel", "bay", "ring")


def centroid(obj):
    """World-space centre of an object's bounding box."""

    box = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(box, Vector()) / 8.0


def key_location(obj, frame, location, interp="BEZIER"):
    obj.location = Vector(location)
    obj.keyframe_insert("location", frame=frame)
    for curve in obj.animation_data.action.fcurves:
        if curve.data_path != "location":
            continue
        for point in curve.keyframe_points:
            if abs(point.co.x - frame) < 0.5:
                point.interpolation = interp
                point.handle_left_type = point.handle_right_type = "AUTO_CLAMPED"


def key_visible(obj, frame, visible):
    """Constant-interpolated visibility, so parts pop rather than fade."""

    obj.hide_viewport = not visible
    obj.hide_render = not visible
    obj.keyframe_insert("hide_viewport", frame=frame)
    obj.keyframe_insert("hide_render", frame=frame)
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            if curve.data_path in ("hide_viewport", "hide_render"):
                for point in curve.keyframe_points:
                    point.interpolation = "CONSTANT"


def animate_assembly(groups):
    """Fly each subassembly into place, staggered in installation order."""

    by_name = dict(groups)
    for name, start, travel, offset in ASSEMBLY:
        members = by_name[name]
        # Parented objects ride their parent; animating both double-counts.
        movers = [o for o in members if o.parent is None]
        for obj in movers:
            if offset is None:
                # Propulsion: separate outboard, each nacelle to its own side.
                side = 1.0 if centroid(obj).y >= 0.0 else -1.0
                delta = Vector((0.0, side * 1.55, 0.10))
            else:
                delta = Vector(offset)
            base = Vector(obj.location)

            key_visible(obj, 1, False)
            key_visible(obj, start, True)
            key_location(obj, start, base + delta)
            key_location(obj, start + travel, base)

        # Children of an animated root still need to appear on cue.
        for obj in members:
            if obj.parent is not None:
                key_visible(obj, 1, False)
                key_visible(obj, start, True)


def animate_capture(scene_data):
    """The approach and the keeper closing over the probe head."""

    mouth = Vector(scene_data["mouth"])
    root = scene_data["uav_root"]
    keeper = scene_data["keeper"]

    # Where the probe head actually ends up: the funnel throat, which is
    # `funnel_depth` above the mouth plane.  Everything else is flying to it.
    throat_z = mouth.z + cm.D["funnel_depth_mm"] * cm.MM
    captured_z = throat_z - cm.UAV_PROBE_STANDOFF
    on_final_z = mouth.z - 0.13 - cm.UAV_PROBE_STANDOFF

    path = [
        (500, (mouth.x - 0.72, mouth.y + 0.60, mouth.z - 0.92)),
        (552, (mouth.x - 0.30, mouth.y + 0.24, mouth.z - 0.52)),
        (596, (mouth.x - 0.03, mouth.y + 0.04, on_final_z - 0.07)),
        (628, (mouth.x, mouth.y, on_final_z)),
        (668, (mouth.x, mouth.y, captured_z)),
        (720, (mouth.x, mouth.y, captured_z)),
    ]
    for frame, position in path:
        key_location(root, frame, position)

    # A little roll authority on the way in, levelling off for the final.
    for frame, rot in ((500, (0.0, 0.10, 0.58)), (552, (0.0, 0.05, 0.24)),
                       (596, (0.0, 0.0, 0.05)), (628, (0.0, 0.0, 0.0)),
                       (720, (0.0, 0.0, 0.0))):
        root.rotation_euler = rot
        root.keyframe_insert("rotation_euler", frame=frame)

    # Keeper: 13 mm of travel, closing once the head is seated.
    base = Vector(keeper.location)
    travel = Vector((cm.D["keeper_open_travel_mm"] * cm.MM, 0.0, 0.0))
    key_location(keeper, 662, base)
    key_location(keeper, 686, base + travel)
    key_location(keeper, 720, base + travel)


def animate_rotors(fan_start=306, uav_start=448):
    """Spin the ducted fans and the aircraft's rotors.

    The aircraft's rotors spin down after capture, because a docked aircraft
    with its props still turning would undercut the entire point of a
    mechanically positive recovery.
    """

    fans = [o for o in bpy.data.objects if "_blade_" in o.name]
    props = [o for o in bpy.data.objects if "_prop_" in o.name]

    for index, obj in enumerate(fans):
        direction = 1.0 if centroid(obj).y >= 0.0 else -1.0
        for frame, turns in ((fan_start, 0.0), (END_FRAME, 21.0)):
            obj.rotation_euler.x = direction * turns * 2.0 * math.pi
            obj.keyframe_insert("rotation_euler", index=0, frame=frame)
        linear(obj)

    for index, obj in enumerate(props):
        direction = 1.0 if index % 2 == 0 else -1.0
        spin = [(uav_start, 0.0), (668, 48.0), (702, 52.5), (END_FRAME, 52.5)]
        for frame, turns in spin:
            obj.rotation_euler.z = direction * turns * 2.0 * math.pi
            obj.keyframe_insert("rotation_euler", index=2, frame=frame)
        linear(obj, only_last_eased=True)


def linear(obj, only_last_eased=False):
    action = obj.animation_data.action
    for curve in action.fcurves:
        points = curve.keyframe_points
        for i, point in enumerate(points):
            if only_last_eased and i >= len(points) - 2:
                point.interpolation = "BEZIER"
            else:
                point.interpolation = "LINEAR"


def animate_control_surfaces(controls):
    """Small, unsynchronised deflections so the tail is not a dead prop."""

    for index, surface in enumerate(controls):
        phase = index * 0.9
        for frame in range(1, END_FRAME + 1, 120):
            angle = math.radians(7.0) * math.sin(frame / 190.0 + phase)
            surface.rotation_euler = (angle, 0.0, 0.0)
            surface.keyframe_insert("rotation_euler", frame=frame)


def animate_ghosting(materials, opaque_until=614, clear_by=658, alpha=0.20):
    """Fade the dock housings to translucent for the capture.

    Standard technical-animation move: the part that matters is inside the
    housing, so the housing stops being opaque exactly when the mechanism
    starts doing something.
    """

    for key in GHOSTED:
        mat = materials[key]
        mat.blend_method = "BLEND"
        mat.shadow_method = "HASHED"
        mat.use_backface_culling = False
        socket = mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"]
        for frame, value in ((opaque_until, 1.0), (clear_by, alpha),
                             (END_FRAME, alpha)):
            socket.default_value = value
            socket.keyframe_insert("default_value", frame=frame)


#: Callouts, in assembly order.  Every number here is read from the model or
#: the Rev-B manifest rather than typed in, because a breakdown that labels
#: parts with invented dimensions is worse than one that labels nothing.
#: Lower-third geometry, in camera-local space.
#:
#: These sit close to the lens, ahead of all scene geometry.  Putting them on
#: the focal plane instead - which is what keeps them sharp under DOF - drops
#: them physically into the set, and they intersected the gondola and ghosted
#: through it.  Captions are 2D and belong in front of everything, so instead
#: the assembly shots run with DOF off (see DOF_FROM_SHOT) and the captions
#: stay sharp because nothing is defocusing them.
CALLOUT_DISTANCE = 1.2
CALLOUT_LEFT = -0.86            # fraction of half-frame width
CALLOUT_TITLE_Y = -0.60         # fraction of half-frame height
CALLOUT_SUB_Y = -0.72
CALLOUT_TITLE_HEIGHT = 0.040    # fraction of frame height
CALLOUT_SUB_HEIGHT = 0.022
SENSOR_HALF_W = 18.0            # 36 mm sensor, fit horizontal
SENSOR_HALF_H = 10.125          # 16:9


def frame_metrics(lens, distance):
    """Half-width, half-height and full height of the frame at `distance`."""

    half_w = distance * SENSOR_HALF_W / lens
    half_h = distance * SENSOR_HALF_H / lens
    return half_w, half_h, half_h * 2.0


#: Depth of field is switched on from this shot index onward.  It earns its
#: keep on the tight capture shots and costs nothing but blurred captions on
#: the assembly ones, which is exactly where every caption lives.
DOF_FROM_SHOT = 6


def lens_at(shot, frame):
    start, end = shot[0], shot[1]
    lens_a, lens_b = shot[6], shot[7]
    span = max(1, end - start)
    return lens_a + (lens_b - lens_a) * (frame - start) / span


def callout_specs():
    """(title, detail) per callout, in shot order - callout i covers SHOTS[i].

    Every number is read from the model or the Rev-B manifest.  A breakdown
    that labels parts with invented dimensions is worse than one that labels
    nothing at all.
    """

    dock = cm.D
    return [
        ("ENVELOPE", "%.1f m  /  %.1f m3 helium"
         % (cm.ENVELOPE_LENGTH_M, cm.HELIUM_VOLUME_M3)),
        ("TAIL SURFACES", "NACA 00%02d  /  X-config"
         % round(cm.FIN_THICKNESS * 100)),
        ("KEEL RAIL", "dock and gondola hardpoints"),
        ("GONDOLA", "avionics  /  ballast  /  skids"),
        ("PROPULSION", "2 x ducted fan  /  prop-guarded"),
        ("BELLY DOCK", "Rev-B  /  %.0f mm mouth  /  %.0f mm throat"
         % (dock["funnel_mouth_diameter_mm"],
            dock["funnel_throat_diameter_mm"])),
        ("MICRO-UAV", "%.0f mm probe standoff"
         % dock["probe_tip_height_above_prop_plane_mm"]),
    ]


def build_callouts(camera):
    """Billboarded text callouts that appear as each subassembly installs."""

    body = cm.pbr("callout_text", (0.86, 0.88, 0.90, 1.0), roughness=0.4,
                  emission=(0.80, 0.84, 0.90, 1.0), emission_strength=1.6)
    # The subtitle has to hold up against the white envelope as well as against
    # the dark hall, so it runs brighter than a grey caption normally would.
    sub = cm.pbr("callout_sub", (0.74, 0.78, 0.84, 1.0), roughness=0.4,
                 emission=(0.70, 0.76, 0.86, 1.0), emission_strength=2.2)

    # Parented to the camera, so these are a screen-space overlay - which is
    # what a caption is.  In world space they only framed correctly for one
    # camera position: after the recut half sat outside the frame and the
    # dock's caption ended up a metre from the lens with two words filling the
    # screen.  The catch is that a camera-parented object changes apparent size
    # with focal length, and these shots run 20 mm to 95 mm, so position and
    # scale are both keyed against the shot's own lens curve.
    from mathutils import Matrix

    made = []
    for index, (title, detail) in enumerate(callout_specs()):
        shot = SHOTS[index]
        appear, vanish = shot[0] + 8, shot[1] - 5

        for row, (text, mat, y_frac, height) in enumerate((
                (title, body, CALLOUT_TITLE_Y, CALLOUT_TITLE_HEIGHT),
                (detail, sub, CALLOUT_SUB_Y, CALLOUT_SUB_HEIGHT))):
            curve = bpy.data.curves.new(f"callout_{index}_{row}", "FONT")
            curve.body = text
            curve.size = 1.0
            curve.align_x = "LEFT"
            curve.align_y = "CENTER"
            obj = bpy.data.objects.new(f"callout_{index}_{row}", curve)
            obj.data.materials.append(mat)
            cm.put(obj, "Callouts")

            obj.parent = camera
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.rotation_euler = (0.0, 0.0, 0.0)

            for frame in (appear, vanish):
                lens = lens_at(shot, frame)
                half_w, half_h, full_h = frame_metrics(lens, CALLOUT_DISTANCE)
                # Text size 1.0 gives roughly 0.7 units of cap height.
                scale = height * full_h / 0.7
                obj.location = (CALLOUT_LEFT * half_w, y_frac * half_h,
                                -CALLOUT_DISTANCE)
                obj.scale = (scale, scale, scale)
                obj.keyframe_insert("location", frame=frame)
                obj.keyframe_insert("scale", frame=frame)

            key_visible(obj, 1, False)
            key_visible(obj, appear, True)
            key_visible(obj, vanish, False)
            made.append(obj)
    return made


def add_shake(obj, strength=SHAKE_STRENGTH, scale=SHAKE_SCALE):
    """Noise F-modifiers on an object's location channels."""

    if not obj.animation_data or not obj.animation_data.action:
        return obj
    for curve in obj.animation_data.action.fcurves:
        if curve.data_path != "location":
            continue
        noise = curve.modifiers.new("NOISE")
        noise.strength = strength
        noise.scale = scale
        # A different phase per axis, or all three move together and it reads
        # as a bounce rather than as a hand.
        noise.phase = 11.0 * (curve.array_index + 1)
        noise.blend_type = "ADD"
    return obj


def animate_camera():
    """Ten shots, cut hard, each with a move and a handheld component."""

    bpy.ops.object.empty_add(type="PLAIN_AXES", radius=0.12,
                             location=SHOTS[0][4])
    aim = bpy.context.view_layer.objects.active
    aim.name = "camera_aim"
    cm.put(aim, "Lighting")

    camera = bpy.data.objects["cam_hero"]
    camera.rotation_euler = (0.0, 0.0, 0.0)
    for constraint in list(camera.constraints):
        camera.constraints.remove(constraint)
    track = camera.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # Depth of field, focused on the aim empty so focus tracks the subject for
    # free.  A pinhole camera that holds a 4.5 m vehicle and a 100 mm aircraft
    # in equal focus is the other thing that reads as computer output.
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = aim
    # f/9, not f/4.  At 95 mm and 1.3 m the tight capture shot has about 47 mm
    # of depth of field wide open - the keeper lands sharp and the funnel it
    # closes inside goes to mush, which loses the mechanism the shot is for.
    # f/9 gives roughly 130 mm: funnel and keeper both readable, hull still soft.
    camera.data.dof.aperture_fstop = 9.0
    camera.data.dof.aperture_blades = 7

    # Off through the captioned assembly shots, on for the capture.
    for frame, enabled in ((1, False),
                           (SHOTS[DOF_FROM_SHOT][0], True)):
        camera.data.dof.use_dof = enabled
        camera.data.dof.keyframe_insert("use_dof", frame=frame)
    for curve in camera.data.animation_data.action.fcurves:
        if curve.data_path.endswith("use_dof"):
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"

    for start, end, cam_a, cam_b, aim_a, aim_b, lens_a, lens_b in SHOTS:
        key_location(camera, start, cam_a)
        key_location(camera, end, cam_b)
        key_location(aim, start, aim_a)
        key_location(aim, end, aim_b)
        for frame, focal in ((start, lens_a), (end, lens_b)):
            camera.data.lens = focal
            camera.data.keyframe_insert("lens", frame=frame)

    # Hold each shot's last key until the next shot begins, so the boundary is
    # a cut rather than a one-frame whip between two unrelated framings.
    for obj in (camera, aim, camera.data):
        action = obj.animation_data.action if obj.animation_data else None
        if action is None:
            continue
        ends = {end for _, end, *_ in SHOTS}
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                if round(point.co.x) in ends:
                    point.interpolation = "CONSTANT"

    add_shake(camera)
    add_shake(aim, strength=SHAKE_STRENGTH * 0.5, scale=SHAKE_SCALE * 0.7)
    return camera, aim


def main():
    scene_data = cm.build_scene()
    cm.add_camera("cam_hero", CAMERA_PATH[0][1], CAMERA_PATH[0][2],
                  focal_mm=CAMERA_PATH[0][3])

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = END_FRAME
    scene.render.fps = FPS

    animate_assembly(scene_data["groups"])
    animate_capture(scene_data)
    animate_rotors()
    animate_control_surfaces(scene_data["controls"])
    animate_ghosting(scene_data["materials"])
    camera, _ = animate_camera()
    scene_data["callouts"] = build_callouts(camera)

    cm.configure_render(samples=32, width=1920, height=1080)

    # Motion blur, mostly for the rotors.  A propeller frozen mid-turn is the
    # single most artificial thing a still frame of a flying machine can show.
    scene.eevee.use_motion_blur = True
    scene.eevee.motion_blur_shutter = 0.5
    # One accumulation step.  Going to three costs 3.5x the render time for a
    # difference invisible at 30 fps on rotors this small.
    scene.eevee.motion_blur_steps = 1
    return scene_data


if __name__ == "__main__":
    main()
