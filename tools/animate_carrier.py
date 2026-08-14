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
END_FRAME = 930

#: Assembly order: (group name, start frame, travel frames, explode offset).
#: `None` as an offset means "derive it per object from which side it is on",
#: which is how the two nacelles separate outboard instead of moving together.
#: Each install lands inside the shot that covers it - see SHOTS.
ASSEMBLY = [
    # 1.25 m of travel, not 2.6.  At the longer offset the fins spent the
    # middle of their shot floating a clear body-length behind the hull, which
    # reads as a modelling error rather than as an install.
    ("Tail surfaces", 80, 62, (1.25, 0.0, 0.0)),
    ("Keel structure", 160, 58, (0.0, 0.0, -1.35)),
    ("Gondola", 230, 58, (0.0, -1.75, -0.85)),
    ("Propulsion", 300, 58, None),
    ("Belly dock", 370, 56, (0.0, 0.0, -1.60)),
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
    # -- cutaway ---------------------------------------------------------
    # The envelope sections away and the interior is on screen.  Everything
    # inside the hull is representative, not vendor-specified, and shot 11's
    # caption says so.
    (721, 800, (-2.6, -6.6, 1.35), (0.6, -5.6, 0.75),
     (2.05, 0.0, 0.05), (2.35, 0.0, -0.10), 34.0, 40.0),
    # The bay opens up and the keeper drive runs through its stroke.
    # From the throat side, near the drive plane.  Viewed from above, the
    # servo's 34 mm case sits squarely over a 6.5 mm crank and hides the whole
    # linkage; from here the keeper is nearest the lens and the crank and link
    # stand clear under the servo's standoff.
    (801, 870, (2.5321, -0.0816, -0.9274), (2.5032, -0.0722, -0.9254),
     (2.4430, 0.0, -0.9595), (2.4455, 0.0, -0.9600), 50.0, 62.0),
    # Tight on the keeper closing over the probe head.
    (871, 930, (2.4972, -0.0585, -0.9375), (2.4890, -0.0468, -0.9420),
     (2.4560, 0.0, -0.9600), (2.4560, 0.0, -0.9600), 60.0, 75.0),
]

#: The capture is flown by the digital twin, not by hand.  `aiur/sim` is the
#: same deterministic model CI gates the SIL runs against, so the approach in
#: this film is a real episode's telemetry rather than an art-directed spline -
#: which matters, because the hand-keyed version moved the aircraft at roughly
#: 0.22 m/s and the twin says a precision capture closes at a fiftieth of that.
SIM_SCENARIO = "sil-p0b"
SIM_SEED = 7

#: Film frames the episode is mapped onto.  The episode runs 26.6 s and the
#: window is 200 frames, so it plays at about 4x.  Real time would be nearly
#: motionless on screen; the speed-up is stated in the shot's caption rather
#: than hidden.
SIM_WINDOW = (468, 668)

#: Filled in by `main()` so the captions can quote the episode's own numbers.
SIM_RESULT = None


def run_sim_episode(seed=SIM_SEED):
    """Run one SIL recovery episode and return its result."""

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from aiur.sim.engine import run_episode
    from aiur.sim.scenarios import sil_p0b

    return run_episode(sil_p0b(seed=seed, record_telemetry=True), seed)


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


def animate_capture(scene_data, result):
    """Fly the aircraft along a real SIL episode's telemetry.

    Telemetry carries the dock-relative position, so the trajectory is anchored
    on the geometric capture pose and offset backwards from there: the aircraft
    ends exactly where the probe head seats, and every earlier sample is placed
    relative to that.  Nothing about the path is drawn by hand.

    Attitude comes out of the same data.  A multirotor accelerates by tilting,
    so pitch and roll are `atan(a / g)` on the differentiated relative
    velocity - which is why the aircraft leans into the rendezvous and stands
    back up as it decelerates onto the dock, instead of flying around flat.
    """

    telemetry = result.telemetry
    if not telemetry:
        raise ValueError("episode recorded no telemetry")

    mouth = Vector(scene_data["mouth"])
    root = scene_data["uav_root"]

    seat_plane = mouth.z + cm.D["funnel_total_height_mm"] * cm.MM
    head_offset = cm.UAV_PROBE_STANDOFF - cm.D["probe_head_seat_diameter_mm"] * cm.MM
    captured = Vector((mouth.x, mouth.y, seat_plane - head_offset))

    # Telemetry is dock-minus-drone, so drone = captured + (rel_final - rel).
    final = telemetry[-1]
    first_frame, last_frame = SIM_WINDOW
    span = last_frame - first_frame
    duration = telemetry[-1].t_s
    step = telemetry[1].t_s - telemetry[0].t_s

    keeper_close_frame = last_frame
    for index, row in enumerate(telemetry):
        frame = first_frame + int(round(span * row.t_s / duration))
        key_location(root, frame, (
            captured.x + (final.rel_x_m - row.rel_x_m),
            captured.y + (final.rel_y_m - row.rel_y_m),
            captured.z + (final.rel_z_m - row.rel_z_m),
        ))

        if 0 < index < len(telemetry) - 1:
            ahead, behind = telemetry[index + 1], telemetry[index - 1]
            ax = (ahead.rel_vx_m_s - behind.rel_vx_m_s) / (2.0 * step)
            ay = (ahead.rel_vy_m_s - behind.rel_vy_m_s) / (2.0 * step)
        else:
            ax = ay = 0.0
        # rel is dock-minus-drone, so the drone's own acceleration is -a.
        root.rotation_euler = (math.atan2(ay, 9.81), math.atan2(-ax, 9.81), 0.0)
        root.keyframe_insert("rotation_euler", frame=frame)

        if row.keeper_command == "close" and keeper_close_frame == last_frame:
            keeper_close_frame = frame

    # Hold the seated pose to the end of the film.
    key_location(root, END_FRAME, captured)
    root.rotation_euler = (0.0, 0.0, 0.0)
    root.keyframe_insert("rotation_euler", frame=END_FRAME)

    # The aircraft appears on cue rather than being flown in from off-stage.
    for obj in [root] + list(scene_data["uav_parts"]):
        key_visible(obj, 1, False)
        key_visible(obj, first_frame, True)
    return keeper_close_frame


#: (frame, crank angle).  The capture close at 686 is the real event; the two
#: later cycles are the cutaway demonstrating the drive with its housing
#: sectioned away.
def keeper_schedule(close_frame=666):
    """Crank angle over time.

    The capture close is where the controller actually commanded it - the twin
    issues `close` once the seat switch S1 makes, not on a frame chosen to look
    right.  The stroke itself takes 24 frames, which is the servo's business.
    """

    import carrier_interior as ci

    return [
        (1, ci.THETA_OPEN),
        (close_frame - 1, ci.THETA_OPEN),
        (close_frame + 24, ci.THETA_CLOSED),
        (806, ci.THETA_CLOSED),
        (824, ci.THETA_OPEN),        # cutaway: reopen to show the stroke
        (858, ci.THETA_CLOSED),
        (884, ci.THETA_OPEN),        # inside the funnel: one more close
        (918, ci.THETA_CLOSED),
        (930, ci.THETA_CLOSED),
    ]


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
        # Solid again before the cutaway: from 721 the housings are sectioned
        # geometry, and leaving them translucent as well turned the lower half
        # of the mechanism shot into overlapping ghosts.
        for frame, value in ((opaque_until, 1.0), (clear_by, alpha),
                             (SHOTS[10][0] - 1, alpha), (SHOTS[10][0], 1.0)):
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
#: Captions sit at a fraction of the shot's own subject distance, not at a
#: fixed standoff.  Parked at a flat 1.2 m the caption ended up *behind* the
#: dock on the close cutaway shot, where the subject is 0.35 m away, and the
#: bay fairing simply occluded half of it.  Screen position is unaffected by
#: distance, so pulling it in front costs nothing.
CALLOUT_SUBJECT_FRACTION = 0.45
CALLOUT_DISTANCE_LIMITS = (0.05, 1.2)
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


#: Depth of field runs over the capture shots only.  It earns its keep there
#: and costs nothing but blurred captions everywhere else - and every caption
#: lives in the assembly and cutaway shots at either end of that window.
DOF_SHOT_WINDOW = (6, 9)


def callout_distance(shot):
    """How far in front of the lens a shot's caption sits."""

    cam = Vector(shot[2])
    aim = Vector(shot[4])
    low, high = CALLOUT_DISTANCE_LIMITS
    return max(low, min(high, (aim - cam).length * CALLOUT_SUBJECT_FRACTION))


def lens_at(shot, frame):
    start, end = shot[0], shot[1]
    lens_a, lens_b = shot[6], shot[7]
    span = max(1, end - start)
    return lens_a + (lens_b - lens_a) * (frame - start) / span


def sim_caption():
    """One line describing the episode the capture is flown from."""

    if SIM_RESULT is None or not SIM_RESULT.telemetry:
        return "%.0f mm probe standoff" % cm.D["probe_tip_height_above_prop_plane_mm"]
    duration = SIM_RESULT.telemetry[-1].t_s
    window = (SIM_WINDOW[1] - SIM_WINDOW[0]) / float(FPS)
    closing = SIM_RESULT.max_contact_closing_m_s or 0.0
    return ("SIL %s seed %d  /  %.1f s at %.0fx  /  contact %.0f mm/s"
            % (SIM_SCENARIO, SIM_SEED, duration, duration / window, closing * 1000.0))


def callout_specs():
    """(shot index, title, detail) - a callout names the shot it belongs to.

    Every number is read from the model or the Rev-B manifest.  A breakdown
    that labels parts with invented dimensions is worse than one that labels
    nothing at all - which is also why the cutaway carries an explicit
    not-specified caption rather than letting representative geometry pass as
    vendor data.
    """

    dock = cm.D
    return [
        (0, "ENVELOPE", "%.1f m  /  %.1f m3 helium"
         % (cm.ENVELOPE_LENGTH_M, cm.HELIUM_VOLUME_M3)),
        (1, "TAIL SURFACES", "NACA 00%02d  /  X-config"
         % round(cm.FIN_THICKNESS * 100)),
        (2, "KEEL RAIL", "dock and gondola hardpoints"),
        (3, "GONDOLA", "avionics  /  ballast  /  skids"),
        (4, "PROPULSION", "2 x ducted fan  /  prop-guarded"),
        (5, "BELLY DOCK", "Rev-B  /  %.0f mm mouth  /  %.0f mm throat"
         % (dock["funnel_mouth_diameter_mm"],
            dock["funnel_throat_diameter_mm"])),
        # Quote the episode, not a design intent: this is what the run did.
        (6, "MICRO-UAV", sim_caption()),
        (10, "INTERIOR  \u2014  SECTION", "ballonets and rigging representative,"
         " not vendor-specified"),
        (11, "KEEPER DRIVE", "slider-crank  /  R%.1f  /  L%.1f  /  %.1f mm stroke"
         % (dock["crank_radius_mm"], dock["link_length_mm"],
            dock["keeper_open_travel_mm"])),
        (12, "CAPTURE", "keeper closes over the \u00d8%.0f mm probe head"
         % dock["probe_head_diameter_mm"]),
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
    for index, (shot_index, title, detail) in enumerate(callout_specs()):
        shot = SHOTS[shot_index]
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

            distance = callout_distance(shot)
            for frame in (appear, vanish):
                lens = lens_at(shot, frame)
                half_w, half_h, full_h = frame_metrics(lens, distance)
                # Text size 1.0 gives roughly 0.7 units of cap height.
                scale = height * full_h / 0.7
                obj.location = (CALLOUT_LEFT * half_w, y_frac * half_h,
                                -distance)
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

    # On for the capture window only; off for assembly and for the cutaway.
    first, last = DOF_SHOT_WINDOW
    for frame, enabled in ((1, False),
                           (SHOTS[first][0], True),
                           (SHOTS[last][1] + 1, False)):
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
    cm.add_camera("cam_hero", SHOTS[0][2], SHOTS[0][4], focal_mm=SHOTS[0][6])

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = END_FRAME
    scene.render.fps = FPS

    animate_assembly(scene_data["groups"])
    global SIM_RESULT
    SIM_RESULT = run_sim_episode()
    scene_data["sim"] = SIM_RESULT
    scene_data["keeper_close_frame"] = animate_capture(scene_data, SIM_RESULT)
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
