"""Build the CARRIER-P0 vehicle as a proper model rather than scaled primitives.

`render_carrier.py` draws the vehicle with a scaled UV sphere, flat plate fins
and a cube gondola.  That is enough for a schematic still and not enough for
anything that has to survive a close camera.  This module rebuilds the same
vehicle as real geometry: a body-of-revolution hull on a low-drag airship
profile, airfoil-section tail surfaces, a lofted gondola fairing, and vectored
propulsion nacelles with actual duct and blade geometry.

The dimensioned parts stay dimensioned.  Envelope length and helium volume are
still the published 4.5 m / 5.5 m3, the dock is still the real Rev-B
fabrication STL, and the micro-UAV still carries the 110 mm probe standoff.
What changes is everything the old file left as a placeholder.

Hull form
---------
A prolate spheroid is the wrong shape for an airship and reads as a balloon.
Real hulls put the maximum section forward - the GNVR family developed at NAL
India parametrizes exactly this: position of maximum section, nose and tail
radii, prismatic coefficient and fineness ratio.  This module uses a
GNVR-style profile rather than published GNVR coefficients: an elliptical nose
with the maximum section at 0.25 L, and an aft body that leaves the maximum
section with zero slope and tapers to a fine tail.

The exponents in `AFT_*` are shape parameters chosen to read correctly, not
values from a drag study, and nothing downstream treats them as aerodynamic.
The envelope *diameter*, though, is not a free parameter: it is solved so the
body of revolution encloses the published 5.5 m3.  `render_carrier` derives its
diameter by assuming a spheroid, so the two files disagree by the difference
between the two prismatic coefficients - this one is the shape actually drawn.

Axis convention matches render_carrier: Blender Z-up, vehicle nose toward +X.
"""

import math

import bpy


# --- context shim ------------------------------------------------------------
# The MCP bridge executes inside an application timer, where `bpy.context` has
# no `active_object`.  Everything else about the context works, so rather than
# spelling `view_layer.objects.active` at every call site we resolve the active
# object through one helper that is correct in both contexts.
def active():
    return bpy.context.view_layer.objects.active


# --- published spec ----------------------------------------------------------
ENVELOPE_LENGTH_M = 4.5
HELIUM_VOLUME_M3 = 5.5

#: Fraction of length at which the hull reaches maximum diameter.  Forward of
#: mid-body is what separates an airship from a balloon.
MAX_SECTION_X = 0.25

#: Aft-body shape: r = R * (1 - k * t**AFT_POWER) ** AFT_FULLNESS, t in [0, 1].
#: AFT_POWER > 1 makes the curve leave the maximum section flat; AFT_FULLNESS
#: below 1 keeps volume in the mid-body while still closing to a fine tail.
#: These two were tuned so the hull lands at a prismatic coefficient of 0.66,
#: inside the 0.6-0.7 band real airship hulls occupy.  An earlier pair taped the
#: tail off far too fast: Cp fell to 0.40, and holding 5.5 m3 at that fullness
#: forced the diameter out to 1.97 m - the hull got fatter to pay for a tail
#: that had no volume in it.
AFT_POWER = 2.5
AFT_FULLNESS = 0.70

#: The tail does not close to a mathematical point - there is a tail cone
#: fitting there.  Radius as a fraction of maximum radius.
TAIL_RADIUS_FRAC = 0.035


def hull_radius(x, radius, length=ENVELOPE_LENGTH_M):
    """Hull radius at station `x`, measured aft from the nose."""

    x_max = MAX_SECTION_X * length
    if x <= 0.0 or x >= length:
        return 0.0
    if x < x_max:
        # Elliptical nose: blunt at the tip, tangent-continuous at the shoulder.
        u = (x_max - x) / x_max
        return radius * math.sqrt(max(0.0, 1.0 - u * u))
    t = (x - x_max) / (length - x_max)
    # `k` is set so the curve lands exactly on TAIL_RADIUS_FRAC at t = 1: the
    # tail cone fitting gets a real radius to attach to without the taper being
    # scaled down along its whole length to get there.
    k = 1.0 - TAIL_RADIUS_FRAC ** (1.0 / AFT_FULLNESS)
    return radius * (max(0.0, 1.0 - k * t ** AFT_POWER)) ** AFT_FULLNESS


#: Number of gores the envelope is built from.  Real fabric envelopes are cut
#: and welded from tapered panels; the seams are the strongest read of scale on
#: an otherwise featureless surface.
GORE_COUNT = 12

#: Quilting: an inflated fabric envelope is not a surface of revolution.  It is
#: pressurised cloth restrained at the welded seams, so each gore bulges outward
#: between its seams and the cross-section is scalloped rather than circular.
#: This is the single strongest cue that a hull is fabric and not moulded
#: plastic, and it costs one term in the radius function.  Expressed as a
#: fraction of local radius at the bulge centre.
QUILT_AMPLITUDE = 0.013


def quilt(x, theta, length=ENVELOPE_LENGTH_M):
    """Outward bulge of the fabric between gore seams, at station `x`.

    Zero on the seams themselves and maximum mid-gore, faded out toward nose
    and tail where the gores converge and the fabric has little free span.
    """

    if x <= 0.0 or x >= length:
        return 0.0
    span = math.sin(math.pi * x / length) ** 0.6
    across = (1.0 - math.cos(GORE_COUNT * theta)) * 0.5
    return QUILT_AMPLITUDE * across * span


def hull_surface(x, theta, radius=None, length=ENVELOPE_LENGTH_M):
    """Radius of the quilted envelope at station `x`, azimuth `theta`."""

    if radius is None:
        radius = HULL_RADIUS_M
    return hull_radius(x, radius, length) * (1.0 + quilt(x, theta, length))


def solve_hull_radius(volume=HELIUM_VOLUME_M3, length=ENVELOPE_LENGTH_M, steps=4000):
    """Maximum hull radius that makes the quilted envelope enclose `volume`.

    The profile is fixed in shape, so volume scales with radius squared and one
    numerical integration at unit radius gives the answer directly.  The
    quilting has to be integrated too: bulging every gore outward adds real
    volume, and ignoring it would quietly inflate the envelope past the
    published 5.5 m3 while still claiming to hit it.

    Averaged over azimuth, (1 + q)^2 has mean 1 + A*span + 0.375*(A*span)^2,
    using mean(across) = 1/2 and mean(across^2) = 3/8 for the raised cosine.
    """

    dx = length / steps
    total = 0.0
    for i in range(steps):
        x = (i + 0.5) * dx
        span = math.sin(math.pi * x / length) ** 0.6 if 0.0 < x < length else 0.0
        a = QUILT_AMPLITUDE * span
        total += hull_radius(x, 1.0, length) ** 2 * (1.0 + a + 0.375 * a * a) * dx
    return math.sqrt(volume / (math.pi * total))


HULL_RADIUS_M = solve_hull_radius()
FINENESS_RATIO = ENVELOPE_LENGTH_M / (2.0 * HULL_RADIUS_M)

#: Hull mesh density.  Dense enough that smooth shading carries the silhouette
#: without a subdivision modifier, which would soften the seam geometry sitting
#: on top of it.
#: A multiple of GORE_COUNT, so every seam lands exactly on a mesh edge loop
#: and the scallop valleys stay crisp instead of being averaged across a face.
HULL_SEGMENTS = 144
HULL_STATIONS = 150


# --- scene plumbing ----------------------------------------------------------
def collection(name):
    """Fetch or create a top-level collection, so the outliner stays legible."""

    existing = bpy.data.collections.get(name)
    if existing is None:
        existing = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(existing)
    return existing


def put(obj, name):
    """Move `obj` into collection `name`, unlinking it from everything else."""

    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection(name).objects.link(obj)
    return obj


def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                  bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            if item.users == 0:
                block.remove(item)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def pbr(name, base_color, roughness=0.5, metallic=0.0, specular=0.5,
        sheen=0.0, clearcoat=0.0, emission=None, emission_strength=1.0,
        anisotropic=0.0):
    """A Principled BSDF material.

    Wrapping this rather than using the render_dock helper because the vehicle
    needs sheen (fabric), clearcoat (painted fairings) and anisotropy (brushed
    metal), none of which that helper exposes.
    """

    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]

    def put_input(key, value):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = value

    put_input("Base Color", base_color)
    put_input("Roughness", roughness)
    put_input("Metallic", metallic)
    put_input("Specular", specular)
    put_input("Sheen", sheen)
    put_input("Clearcoat", clearcoat)
    put_input("Anisotropic", anisotropic)
    if emission is not None:
        put_input("Emission", emission)
        put_input("Emission Strength", emission_strength)
    return mat


def fabric_material(name, base_color, weave_scale=420.0, bump=0.055,
                    sheen=0.6, roughness=0.62):
    """Envelope fabric: woven bump plus roughness break-up.

    A flat Principled surface on a 4.5 m envelope reads as vinyl no matter how
    good the lighting is, because there is nothing at all between the silhouette
    and the pixel level.  Two noise textures fix that: a fine one driving a bump
    for the weave, and a coarse one breaking up roughness so the highlight
    travels unevenly across the panels the way real coated fabric does.
    """

    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Sheen" in bsdf.inputs:
        bsdf.inputs["Sheen"].default_value = sheen

    coord = nt.nodes.new("ShaderNodeTexCoord")

    weave = nt.nodes.new("ShaderNodeTexNoise")
    weave.inputs["Scale"].default_value = weave_scale
    weave.inputs["Detail"].default_value = 2.0
    weave.inputs["Roughness"].default_value = 0.75
    nt.links.new(coord.outputs["Object"], weave.inputs["Vector"])

    bump_node = nt.nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = bump
    bump_node.inputs["Distance"].default_value = 0.004
    nt.links.new(weave.outputs["Fac"], bump_node.inputs["Height"])
    nt.links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])

    coarse = nt.nodes.new("ShaderNodeTexNoise")
    coarse.inputs["Scale"].default_value = 5.5
    coarse.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], coarse.inputs["Vector"])

    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.30
    rough.inputs["From Max"].default_value = 0.70
    rough.inputs["To Min"].default_value = roughness - 0.09
    rough.inputs["To Max"].default_value = roughness + 0.09
    rough.clamp = True
    nt.links.new(coarse.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def shade_smooth(obj, angle_deg=35.0):
    """Smooth shading with an auto-smooth crease, so folds stay sharp."""

    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(angle_deg)
    return obj


def mesh_object(name, verts, faces, material, coll):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    put(obj, coll)
    return obj


# --- envelope ----------------------------------------------------------------
def hull_stations(count=HULL_STATIONS, length=ENVELOPE_LENGTH_M):
    """Station positions clustered toward nose and tail.

    Cosine spacing puts mesh density where the curvature is, which is the
    difference between a clean nose and a faceted one.
    """

    return [0.5 * length * (1.0 - math.cos(math.pi * i / (count - 1)))
            for i in range(count)]


def build_envelope(material):
    """The hull, as a body of revolution on the solved profile.

    Nose closes to a pole with a triangle fan; the tail closes on the finite
    tail-cone radius with an n-gon, because that is where a real tail fitting
    bolts on.
    """

    stations = hull_stations()
    seg = HULL_SEGMENTS
    # Nose pole, then one ring per interior station, then the tail ring.
    verts = [(0.0, 0.0, 0.0)]
    for x in stations[1:]:
        for j in range(seg):
            a = 2.0 * math.pi * j / seg
            r = hull_surface(x, a)
            verts.append((x, r * math.cos(a), r * math.sin(a)))

    faces = []
    # Nose fan.
    for j in range(seg):
        faces.append((0, 1 + j, 1 + (j + 1) % seg))
    # Quad bands between successive rings.
    rings = len(stations) - 1
    for i in range(rings - 1):
        base_a = 1 + i * seg
        base_b = 1 + (i + 1) * seg
        for j in range(seg):
            k = (j + 1) % seg
            faces.append((base_a + j, base_b + j, base_b + k, base_a + k))
    # Tail cap.
    last = 1 + (rings - 1) * seg
    faces.append(tuple(range(last, last + seg))[::-1])

    hull = mesh_object("envelope", verts, faces, material, "Envelope")
    return shade_smooth(hull)


def surface_curve(name, theta, x0, x1, material, coll, offset=0.006,
                  bevel=0.006, samples=120, taper_ends=True):
    """A tube lying on the hull surface along a constant-azimuth line.

    Used for gore seams and nose battens.  `offset` lifts the tube centre off
    the surface so it reads as applied tape rather than an intersecting rod.
    """

    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 4
    curve.use_fill_caps = True

    spline = curve.splines.new("POLY")
    spline.points.add(samples - 1)
    for i in range(samples):
        x = x0 + (x1 - x0) * i / (samples - 1)
        r = hull_surface(x, theta) + offset
        spline.points[i].co = (x, r * math.cos(theta), r * math.sin(theta), 1.0)
        if taper_ends:
            # Fade the tube out at both ends instead of stopping dead.
            s = i / (samples - 1)
            spline.points[i].radius = min(1.0, min(s, 1.0 - s) * 8.0)

    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(material)
    return put(obj, coll)


def surface_band(name, x, width, offset, thickness, material, coll,
                 segments=None):
    """A circumferential tape lying on the quilted hull at station `x`."""

    seg = segments or HULL_SEGMENTS
    x0, x1 = x - width * 0.5, x + width * 0.5
    verts = []
    for station in (x0, x1):
        for extra in (offset, offset + thickness):
            for j in range(seg):
                a = 2.0 * math.pi * j / seg
                r = hull_surface(station, a) + extra
                verts.append((station, r * math.cos(a), r * math.sin(a)))

    faces = []

    def band(base_a, base_b, flip=False):
        for j in range(seg):
            k = (j + 1) % seg
            quad = (base_a + j, base_b + j, base_b + k, base_a + k)
            faces.append(quad[::-1] if flip else quad)

    s = seg
    band(s, 3 * s)            # outer face
    band(0, 2 * s, True)      # inner face, against the envelope
    band(0, s, True)          # forward edge
    band(2 * s, 3 * s)        # aft edge
    return shade_smooth(mesh_object(name, verts, faces, material, coll), 30.0)


def build_envelope_detail(seam_mat, batten_mat):
    """Gore seams, circumferential tapes, nose battens and the tail fitting."""

    made = []
    length = ENVELOPE_LENGTH_M

    # Longitudinal gore seams, running most of the hull length.
    for g in range(GORE_COUNT):
        theta = 2.0 * math.pi * g / GORE_COUNT
        made.append(surface_curve(
            f"gore_seam_{g:02d}", theta, 0.012 * length, 0.988 * length,
            seam_mat, "Envelope", offset=0.004, bevel=0.005))

    # Circumferential tapes at the load stations.  These have to be built on
    # the quilted section rather than dropped on as toruses: a circular ring
    # around a scalloped hull rides above every valley and sinks into every
    # bulge.
    for frac in (0.16, 0.25, 0.40, 0.56, 0.72):
        made.append(surface_band(
            f"hoop_tape_{int(frac * 100):02d}", frac * length,
            width=0.030, offset=0.0035, thickness=0.004,
            material=seam_mat, coll="Envelope"))

    # Nose battens: the radial reinforcement strips every real airship carries
    # where the mooring loads come in.  Kept short and fine - at twice the gore
    # count and 13% of the length they stopped reading as reinforcement and
    # turned the nose into a beach ball, because the blunt end projects far
    # larger than its share of the hull length suggests.
    for g in range(GORE_COUNT):
        theta = 2.0 * math.pi * (g + 0.5) / GORE_COUNT
        made.append(surface_curve(
            f"nose_batten_{g:02d}", theta, 0.004 * length, 0.048 * length,
            batten_mat, "Envelope", offset=0.003, bevel=0.0045,
            samples=32, taper_ends=True))

    # Nose mooring cone.
    bpy.ops.mesh.primitive_cone_add(
        vertices=48, radius1=0.052, radius2=0.022, depth=0.10,
        location=(0.028, 0.0, 0.0), rotation=(0.0, -math.pi / 2.0, 0.0))
    nose = active()
    nose.name = "nose_cone_fitting"
    nose.data.materials.append(batten_mat)
    made.append(shade_smooth(put(nose, "Envelope")))

    # Tail cone fitting, sized on the profile's finite tail radius.
    tail_r = hull_radius(length * 0.999, HULL_RADIUS_M)
    bpy.ops.mesh.primitive_cone_add(
        vertices=48, radius1=tail_r * 1.25, radius2=tail_r * 0.55, depth=0.11,
        location=(length - 0.03, 0.0, 0.0), rotation=(0.0, math.pi / 2.0, 0.0))
    tail = active()
    tail.name = "tail_cone_fitting"
    tail.data.materials.append(batten_mat)
    made.append(shade_smooth(put(tail, "Envelope")))
    return made


# --- tail surfaces -----------------------------------------------------------
#: Fins are set in an X rather than a cross.  The belly dock is the whole point
#: of the vehicle, and a bottom-centre fin would sit in the approach corridor
#: the aircraft has to fly up.  X-config keeps the ventral centreline clear.
FIN_ROLL_DEG = (45.0, 135.0, 225.0, 315.0)
FIN_ROOT_LE_X = 3.16
FIN_ROOT_CHORD = 1.10
FIN_TIP_CHORD = 0.54
FIN_SWEEP = 0.38
FIN_SPAN = 0.60
#: Fraction of chord where the fixed fin ends and the moving surface begins.
FIN_HINGE = 0.68
FIN_THICKNESS = 0.12


def naca_thickness(xc, thickness=FIN_THICKNESS):
    """Half-thickness of a symmetric NACA 00xx section at chord fraction `xc`."""

    xc = min(max(xc, 0.0), 1.0)
    return 5.0 * thickness * (
        0.2969 * math.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2
        + 0.2843 * xc ** 3 - 0.1015 * xc ** 4
    )


def airfoil_loop(frac0, frac1, count=44):
    """Closed (chord, half-thickness) loop for the slice [frac0, frac1].

    Slicing the section lets the fixed fin and the moving control surface be
    separate objects that still share one aerodynamic outline, so the hinge
    line is a real gap rather than a painted stripe.
    """

    # Cosine spacing again: the leading edge is where the curvature lives.
    xs = [frac0 + (frac1 - frac0) * 0.5 * (1.0 - math.cos(math.pi * i / (count - 1)))
          for i in range(count)]
    upper = [(x, naca_thickness(x)) for x in xs]
    lower = [(x, -naca_thickness(x)) for x in reversed(xs[1:-1])]
    return upper + lower


def build_fin(name, roll_deg, frac0, frac1, material, coll):
    """One lofted tail surface, conformal to the hull at its root.

    A straight root line would either float off the envelope or bury itself in
    it, because the hull radius falls away steeply across the root chord.  The
    root section therefore rides the hull profile and the loft blends to a
    planar tip.
    """

    loop = airfoil_loop(frac0, frac1)
    span_steps = 14
    roll = math.radians(roll_deg)

    # Radius the tip sits at: hull radius under the fin centre, plus span.
    centre_x = FIN_ROOT_LE_X + FIN_ROOT_CHORD * 0.5
    tip_radius = hull_radius(centre_x, HULL_RADIUS_M) + FIN_SPAN

    verts = []
    for i in range(span_steps + 1):
        s = i / span_steps
        chord = FIN_ROOT_CHORD + (FIN_TIP_CHORD - FIN_ROOT_CHORD) * s
        le_x = FIN_ROOT_LE_X + FIN_SWEEP * s
        for xc, half_t in loop:
            x = le_x + chord * xc
            # Root rides the envelope; tip is a flat planar section.
            root_r = max(0.02, hull_radius(x, HULL_RADIUS_M) - 0.025)
            radial = root_r * (1.0 - s) + tip_radius * s
            lateral = chord * half_t
            # Rotate the (radial, lateral) pair into the fin's roll plane.
            y = radial * math.cos(roll) - lateral * math.sin(roll)
            z = radial * math.sin(roll) + lateral * math.cos(roll)
            verts.append((x, y, z))

    n = len(loop)
    faces = []
    for i in range(span_steps):
        a, b = i * n, (i + 1) * n
        for j in range(n):
            k = (j + 1) % n
            faces.append((a + j, b + j, b + k, a + k))
    # Cap root and tip.
    faces.append(tuple(range(0, n)))
    faces.append(tuple(range(span_steps * n, span_steps * n + n))[::-1])

    obj = mesh_object(name, verts, faces, material, coll)
    return shade_smooth(obj, angle_deg=28.0)


def build_tail(fin_mat, control_mat):
    """Four fins, each split into a fixed surface and a moving control surface.

    The control surfaces are separate objects with their origin on the hinge
    line, so an animation can deflect them directly.
    """

    fixed, controls = [], []
    for index, roll in enumerate(FIN_ROLL_DEG):
        fixed.append(build_fin(
            f"fin_{index}_fixed", roll, 0.0, FIN_HINGE, fin_mat, "Tail"))
        surface = build_fin(
            f"fin_{index}_control", roll, FIN_HINGE + 0.012, 1.0,
            control_mat, "Tail")

        # Put the origin on the hinge so rotation is a pure deflection.
        centre_x = FIN_ROOT_LE_X + FIN_SWEEP * 0.5
        chord = (FIN_ROOT_CHORD + FIN_TIP_CHORD) * 0.5
        hinge_x = centre_x + chord * FIN_HINGE
        hinge_r = hull_radius(hinge_x, HULL_RADIUS_M) + FIN_SPAN * 0.5
        roll_rad = math.radians(roll)
        pivot = (hinge_x,
                 hinge_r * math.cos(roll_rad),
                 hinge_r * math.sin(roll_rad))
        set_origin(surface, pivot)
        controls.append(surface)
    return fixed, controls


# --- lofted bodies -----------------------------------------------------------
def loft_sections(name, sections, material, coll, segments=40, close=True,
                  smooth_angle=40.0):
    """Loft a tube through a list of super-elliptical cross sections.

    Each section is ``(x, half_width, half_height, y, z, exponent)``.  The
    exponent squares off the section as it rises above 2.0, which is how a
    gondola gets a flat floor and rounded shoulders in the same sweep.
    """

    verts, faces = [], []
    for (x, hw, hh, y0, z0, e) in sections:
        for j in range(segments):
            a = 2.0 * math.pi * j / segments
            ca, sa = math.cos(a), math.sin(a)
            # Superellipse: |c|^(2/e) keeps the corners controllable.
            px = math.copysign(abs(ca) ** (2.0 / e), ca)
            pz = math.copysign(abs(sa) ** (2.0 / e), sa)
            verts.append((x, y0 + hw * px, z0 + hh * pz))

    rings = len(sections)
    for i in range(rings - 1):
        a, b = i * segments, (i + 1) * segments
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((a + j, b + j, b + k, a + k))
    if close:
        faces.append(tuple(range(0, segments)))
        last = (rings - 1) * segments
        faces.append(tuple(range(last, last + segments))[::-1])

    obj = mesh_object(name, verts, faces, material, coll)
    return shade_smooth(obj, angle_deg=smooth_angle)


def streamlined_sections(x0, length, max_hw, max_hh, count=26, nose_frac=0.3,
                         y0=0.0, z0=0.0, exponent=2.0, tail_frac=0.12):
    """Section list for a streamlined pod: round nose, long tapering tail."""

    out = []
    for i in range(count):
        s = i / (count - 1)
        if s < nose_frac:
            u = 1.0 - s / nose_frac
            k = math.sqrt(max(0.0, 1.0 - u * u))
        else:
            t = (s - nose_frac) / (1.0 - nose_frac)
            k = (max(0.0, 1.0 - 0.97 * t ** 2.2)) ** 0.65
            k = max(k, tail_frac)
        out.append((x0 + length * s, max(1e-4, max_hw * k),
                    max(1e-4, max_hh * k), y0, z0, exponent))
    return out


def build_strut(name, x, y, z0, z1, chord, material, coll, thickness=0.16):
    """A vertical structural member with a streamwise airfoil section.

    Swept along z with the section in the x-y plane, which is the opposite of
    what `loft_sections` does.
    """

    loop = airfoil_loop(0.0, 1.0, count=20)
    steps = 6
    verts, faces = [], []
    for i in range(steps + 1):
        s = i / steps
        z = z0 + (z1 - z0) * s
        # Slight taper toward the hull so the member does not read as extrusion.
        c = chord * (1.0 - 0.14 * s)
        for xc, half_t in loop:
            verts.append((x - c * 0.35 + c * xc,
                          y + half_t * c * (thickness / FIN_THICKNESS), z))
    n = len(loop)
    for i in range(steps):
        a, b = i * n, (i + 1) * n
        for j in range(n):
            k = (j + 1) % n
            faces.append((a + j, b + j, b + k, a + k))
    faces.append(tuple(range(0, n)))
    faces.append(tuple(range(steps * n, steps * n + n))[::-1])
    return shade_smooth(mesh_object(name, verts, faces, material, coll), 24.0)


# --- ventral structure -------------------------------------------------------
#: The belly carries a keel rail; the gondola hangs off its forward end and the
#: dock bay sits aft of it.  The old layout put the gondola directly on top of
#: the dock's approach corridor, which is the one volume on the vehicle that has
#: to stay empty.
KEEL_X0 = 1.28
KEEL_X1 = 3.02
DOCK_BAY_X = 2.47

GONDOLA_X = 1.44
GONDOLA_LENGTH = 0.88
GONDOLA_HALF_WIDTH = 0.16
GONDOLA_HALF_HEIGHT = 0.12


def build_keel(rail_mat, frame_mat):
    """Longitudinal keel rail plus the transverse frames that hang off it."""

    made = []
    # The rail follows the hull's belly line rather than running dead straight,
    # so it stays a constant standoff from a curved envelope.
    steps = 26
    loop = airfoil_loop(0.0, 1.0, count=18)
    verts, faces = [], []
    for i in range(steps + 1):
        s = i / steps
        x = KEEL_X0 + (KEEL_X1 - KEEL_X0) * s
        z = -hull_radius(x, HULL_RADIUS_M) - 0.045
        for xc, half_t in loop:
            verts.append((x, (xc - 0.5) * 0.13, z + half_t * 0.30))
    n = len(loop)
    for i in range(steps):
        a, b = i * n, (i + 1) * n
        for j in range(n):
            k = (j + 1) % n
            faces.append((a + j, b + j, b + k, a + k))
    faces.append(tuple(range(0, n)))
    faces.append(tuple(range(steps * n, steps * n + n))[::-1])
    made.append(shade_smooth(mesh_object("keel_rail", verts, faces,
                                         rail_mat, "Keel"), 24.0))

    # Transverse frames tying the rail into the envelope.
    for frac in (0.06, 0.30, 0.54, 0.78, 0.96):
        x = KEEL_X0 + (KEEL_X1 - KEEL_X0) * frac
        r = hull_radius(x, HULL_RADIUS_M)
        for side in (-1, 1):
            made.append(build_strut(
                f"keel_frame_{int(frac * 100)}_{'l' if side < 0 else 'r'}",
                x, side * 0.055, -r - 0.05, -r + 0.03,
                chord=0.075, material=frame_mat, coll="Keel"))
    return made


def build_gondola(shell_mat, glass_mat, strut_mat):
    """Streamlined gondola fairing with glazing, struts and a landing skid."""

    made = []
    belly = -hull_radius(GONDOLA_X + GONDOLA_LENGTH * 0.5, HULL_RADIUS_M)
    # Hung just clear of the keel rail rather than floating in space.
    z0 = belly - 0.045 - GONDOLA_HALF_HEIGHT - 0.045

    sections = streamlined_sections(
        GONDOLA_X, GONDOLA_LENGTH, GONDOLA_HALF_WIDTH, GONDOLA_HALF_HEIGHT,
        count=30, nose_frac=0.26, z0=z0, exponent=2.6, tail_frac=0.10)
    made.append(loft_sections("gondola_shell", sections, shell_mat, "Gondola"))

    # Glazing: a slightly proud loft over the forward upper flank, following
    # the fairing's own taper so it reads as a wrapped windscreen rather than a
    # decal on a slab.
    glass = streamlined_sections(
        GONDOLA_X + 0.015, GONDOLA_LENGTH * 0.52,
        GONDOLA_HALF_WIDTH * 1.02, GONDOLA_HALF_HEIGHT * 0.66,
        count=20, nose_frac=0.30, z0=z0 + GONDOLA_HALF_HEIGHT * 0.30,
        exponent=2.8, tail_frac=0.55)
    made.append(loft_sections("gondola_glazing", glass, glass_mat, "Gondola"))

    # Struts up to the hull.  These are vertical members with a streamwise
    # airfoil section, so they are swept along z with the section drawn in the
    # x-y plane - `loft_sections` sweeps along x and cannot express that.
    for sx in (0.20, 0.78):
        x = GONDOLA_X + GONDOLA_LENGTH * sx
        bottom = z0 + GONDOLA_HALF_HEIGHT * 0.55
        top = -hull_radius(x, HULL_RADIUS_M) + 0.03
        made.append(build_strut(
            f"gondola_strut_{int(sx * 100)}", x, 0.0, bottom, top,
            chord=0.16, material=strut_mat, coll="Gondola"))

    # Landing skids, each on two legs.  Without the legs the skid rails hang in
    # space a few centimetres under the fairing and read as stray rods.
    skid_len = GONDOLA_LENGTH * 0.58
    skid_x = GONDOLA_X + GONDOLA_LENGTH * 0.44
    skid_y = GONDOLA_HALF_WIDTH * 0.66
    skid_z = z0 - GONDOLA_HALF_HEIGHT - 0.055
    for side in (-1, 1):
        tag = "l" if side < 0 else "r"
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.009, depth=skid_len, vertices=16,
            location=(skid_x, side * skid_y, skid_z),
            rotation=(0.0, math.pi / 2.0, 0.0))
        skid = active()
        skid.name = f"landing_skid_{tag}"
        skid.data.materials.append(strut_mat)
        made.append(shade_smooth(put(skid, "Gondola")))

        for end in (-0.34, 0.34):
            lx = skid_x + skid_len * end
            # Leg runs from the skid rail up into the fairing underside.
            top = z0 - GONDOLA_HALF_HEIGHT * 0.55
            bpy.ops.mesh.primitive_cylinder_add(
                radius=0.005, depth=abs(top - skid_z), vertices=12,
                location=(lx, side * skid_y * 0.92, (top + skid_z) * 0.5),
                rotation=(0.0, side * 0.10, 0.0))
            leg = active()
            leg.name = f"skid_leg_{tag}_{int((end + 0.5) * 100)}"
            leg.data.materials.append(strut_mat)
            made.append(shade_smooth(put(leg, "Gondola")))
    return made, z0


# --- propulsion --------------------------------------------------------------
NACELLE_X = 2.30
NACELLE_LENGTH = 0.30
DUCT_RADIUS = 0.115
BLADE_COUNT = 5

#: Nacelles are positioned in polar terms about the hull axis, not in raw
#: Cartesian offsets.  The first pass set y = 0.62 at a station where the hull
#: radius is 0.725, which quietly buried both fans inside the envelope.
NACELLE_ANGLE_DEG = -34.0
NACELLE_CLEARANCE = 0.20


def nacelle_origin(side):
    """Centre of one duct, standing off the hull surface by the clearance."""

    ang = math.radians(NACELLE_ANGLE_DEG)
    r = hull_radius(NACELLE_X, HULL_RADIUS_M) + NACELLE_CLEARANCE + DUCT_RADIUS
    return (NACELLE_X, side * r * math.cos(ang), r * math.sin(ang))


def build_ducted_fan(name, origin, materials, blade_angle=0.0):
    """A vectored ducted fan: shroud, centrebody, blades and a mounting pylon.

    P0 is a prop-guarded indoor article, so a duct is the honest choice - and
    it gives the propulsion something to read as at close range, which a bare
    cylinder and a torus never did.
    """

    from mathutils import Vector

    made = []
    ox, oy, oz = origin

    # Shroud: an annular duct with a rounded intake lip and a flared exit.
    profile = [
        (-0.5, 1.00), (-0.42, 0.93), (-0.30, 0.90), (-0.10, 0.90),
        (0.10, 0.91), (0.30, 0.94), (0.46, 0.99), (0.50, 1.03),
    ]
    seg = 56
    verts, faces = [], []
    wall = 0.016
    for (fx, fr) in profile:
        for j in range(seg):
            a = 2.0 * math.pi * j / seg
            r = DUCT_RADIUS * fr
            verts.append((ox + fx * NACELLE_LENGTH,
                          oy + r * math.cos(a), oz + r * math.sin(a)))
    for (fx, fr) in reversed(profile):
        for j in range(seg):
            a = 2.0 * math.pi * j / seg
            r = DUCT_RADIUS * fr - wall
            verts.append((ox + fx * NACELLE_LENGTH,
                          oy + r * math.cos(a), oz + r * math.sin(a)))
    rings = len(profile) * 2
    for i in range(rings - 1):
        a, b = i * seg, (i + 1) * seg
        for j in range(seg):
            k = (j + 1) % seg
            faces.append((a + j, b + j, b + k, a + k))
    # Close the annulus back onto itself at both open ends.
    a, b = (rings - 1) * seg, 0
    for j in range(seg):
        k = (j + 1) % seg
        faces.append((a + j, b + j, b + k, a + k))
    made.append(shade_smooth(mesh_object(
        name + "_shroud", verts, faces, materials["duct"], "Propulsion"), 32.0))

    # Centrebody.
    hub = streamlined_sections(
        ox - NACELLE_LENGTH * 0.34, NACELLE_LENGTH * 0.78, 0.036, 0.036,
        count=18, nose_frac=0.34, y0=oy, z0=oz, tail_frac=0.16)
    made.append(loft_sections(name + "_hub", hub, materials["hub"],
                              "Propulsion", segments=28))

    # Blades: twisted, tapered, symmetric section.
    for b_i in range(BLADE_COUNT):
        phase = 2.0 * math.pi * b_i / BLADE_COUNT + blade_angle
        steps, chord_root, chord_tip = 9, 0.072, 0.044
        bverts, bfaces = [], []
        loop = airfoil_loop(0.0, 1.0, count=24)
        for i in range(steps + 1):
            s = i / steps
            r = 0.036 + (DUCT_RADIUS - wall - 0.040) * s
            chord = chord_root + (chord_tip - chord_root) * s
            twist = math.radians(34.0 - 26.0 * s)
            for xc, half_t in loop:
                lx = (xc - 0.35) * chord
                lt = half_t * chord
                # Twist about the blade's spanwise axis.
                px = lx * math.cos(twist) - lt * math.sin(twist)
                pt = lx * math.sin(twist) + lt * math.cos(twist)
                # Local to the duct centre, so the object can be spun about its
                # own X axis instead of orbiting the world origin.
                bverts.append((px,
                               r * math.cos(phase) - pt * math.sin(phase),
                               r * math.sin(phase) + pt * math.cos(phase)))
        n = len(loop)
        for i in range(steps):
            a, b = i * n, (i + 1) * n
            for j in range(n):
                k = (j + 1) % n
                bfaces.append((a + j, b + j, b + k, a + k))
        bfaces.append(tuple(range(0, n)))
        bfaces.append(tuple(range(steps * n, steps * n + n))[::-1])
        blade = shade_smooth(mesh_object(
            f"{name}_blade_{b_i}", bverts, bfaces, materials["blade"],
            "Propulsion"), 26.0)
        blade.location = (ox, oy, oz)
        made.append(blade)

    return made


def build_propulsion(materials):
    """Two vectored ducted fans on pylons, one per side."""

    made, units = [], []
    for side in (-1, 1):
        origin = nacelle_origin(side)
        _, oy, oz = origin
        tag = "port" if side < 0 else "stbd"
        parts = build_ducted_fan(f"fan_{tag}", origin, materials,
                                 blade_angle=0.3 * side)

        # Pylon from the hull out to the duct: airfoil section, swept.
        steps = 10
        pverts, pfaces = [], []
        loop = airfoil_loop(0.0, 1.0, count=20)
        for i in range(steps + 1):
            s = i / steps
            # Ride the hull surface at the root, meet the duct at the tip.
            ang = math.atan2(oz, oy)
            r_hull = hull_radius(NACELLE_X, HULL_RADIUS_M) - 0.02
            ry = r_hull * math.cos(ang)
            rz = r_hull * math.sin(ang)
            py = ry + (oy - ry) * s
            pz = rz + (oz - rz) * s
            chord = 0.30 - 0.09 * s
            for xc, half_t in loop:
                pverts.append((NACELLE_X - 0.10 + chord * xc,
                               py, pz + half_t * chord * 1.6))
        n = len(loop)
        for i in range(steps):
            a, b = i * n, (i + 1) * n
            for j in range(n):
                k = (j + 1) % n
                pfaces.append((a + j, b + j, b + k, a + k))
        pfaces.append(tuple(range(0, n)))
        pfaces.append(tuple(range(steps * n, steps * n + n))[::-1])
        made.append(shade_smooth(mesh_object(
            f"pylon_{tag}", pverts, pfaces, materials["pylon"],
            "Propulsion"), 26.0))
        made.extend(parts)
        units.append((tag, origin, parts))
    return made, units


# --- belly dock --------------------------------------------------------------
import json  # noqa: E402  (kept next to the code that needs the manifest)
import os  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = os.path.join(REPO, "hardware", "dock", "cad", "generated")
MANIFEST = json.load(open(os.path.join(GENERATED, "p0a_rev_b_manifest.json")))
D = MANIFEST["design"]
MM = 0.001

#: Mouth plane of the funnel, matching the site model's ventral station.  The
#: dock hangs below the keel on a bay, which is the volume the bay fairing fills.
DOCK_MOUTH_Z = -1.0375


def import_dock_part(stem, material, coll="Dock"):
    """Import one generated Rev-B STL at its authored millimetre scale.

    This is the one assembly on the vehicle with real CAD behind it, so it is
    imported rather than modelled - nothing here is allowed to drift from the
    fabrication geometry.
    """

    path = os.path.join(GENERATED, f"{stem}_rev_b.stl")
    before = set(bpy.data.objects)
    bpy.ops.import_mesh.stl(filepath=path)
    obj = (set(bpy.data.objects) - before).pop()
    obj.name = stem
    obj.scale = (MM, MM, MM)
    obj.data.materials.append(material)
    # Flat-ish shading: the funnel is a 64-segment lathe and smoothing it would
    # render a part rounder than the one that comes off the printer.
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(30.0)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return put(obj, coll)


def annulus_plate(name, centre, r_in, r_out, thickness, material, coll,
                  segments=48):
    """A flat ring with a real bore through it."""

    cx, cy, cz = centre
    verts, faces = [], []
    half = thickness * 0.5
    for z in (cz - half, cz + half):
        for r in (r_in, r_out):
            for j in range(segments):
                a = 2.0 * math.pi * j / segments
                verts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))

    def band(base_a, base_b, flip=False):
        for j in range(segments):
            k = (j + 1) % segments
            quad = (base_a + j, base_b + j, base_b + k, base_a + k)
            faces.append(quad[::-1] if flip else quad)

    s = segments
    band(0, s)              # bottom face
    band(2 * s, 3 * s, True)  # top face
    band(s, 3 * s)          # outer wall
    band(0, 2 * s, True)    # inner bore
    return shade_smooth(mesh_object(name, verts, faces, material, coll), 20.0)


def build_dock(bay_mat, funnel_mat, keeper_mat, ring_mat):
    """The dock bay fairing plus the real Rev-B funnel and keeper."""

    made = []
    keel_z = -hull_radius(DOCK_BAY_X, HULL_RADIUS_M) - 0.055
    # The keeper plane is the top of the funnel, not the top of its flange.
    # The lathe profile runs the O16 throat bore from z=65 up to z=73, and the
    # probe head emerges above 73 - so a keeper at 68 sits inside the throat
    # collar, and the drive plate above it was buried in the same 5 mm.
    flange_z = DOCK_MOUTH_Z + D["funnel_total_height_mm"] * MM

    # Bay fairing bridging the keel down to the funnel flange.
    count = 16
    sections = []
    for i in range(count):
        s = i / (count - 1)
        # Rounded in plan, tapering slightly toward the bottom mounting face.
        k = math.sqrt(max(0.0, 1.0 - (2.0 * s - 1.0) ** 2 * 0.86))
        sections.append((DOCK_BAY_X - 0.19 + 0.38 * s,
                         0.125 * k, (keel_z - flange_z) * 0.5 * max(k, 0.55),
                         0.0, (keel_z + flange_z) * 0.5, 2.6))
    made.append(loft_sections("dock_bay_fairing", sections, bay_mat, "Dock",
                              segments=40, smooth_angle=38.0))

    # Mounting plate the funnel flange bolts to (Ø70 flange, 4x M3 on a 40
    # square).  It has to be an annulus, not a disc: the keeper works directly
    # under it at the throat, and a solid plate hides the one mechanism the
    # capture shot exists to show.
    # Below the keeper, not above it.  At flange +5 mm this plate occupied the
    # same millimetres as the drive plate at flange +3.1 mm and hid the whole
    # linkage from any camera above the dock.  The real stack is funnel flange,
    # then keeper, then drive plate; the mounting plate belongs under all three.
    made.append(annulus_plate(
        "dock_mounting_ring", (DOCK_BAY_X, 0.0, flange_z - 0.005),
        r_in=D["funnel_throat_diameter_mm"] * 0.5 * MM * 2.4,
        r_out=D["funnel_flange_diameter_mm"] * 0.5 * MM * 1.22,
        thickness=0.006, material=ring_mat, coll="Dock"))

    for hx in (-1, 1):
        for hy in (-1, 1):
            half = D["flange_hole_square_mm"] * 0.5 * MM
            bpy.ops.mesh.primitive_cylinder_add(
                radius=D["flange_hole_diameter_mm"] * 0.5 * MM * 1.6,
                depth=0.012, vertices=16,
                location=(DOCK_BAY_X + hx * half, hy * half, flange_z - 0.005))
            bolt = active()
            bolt.name = "dock_flange_bolt"
            bolt.data.materials.append(ring_mat)
            made.append(shade_smooth(put(bolt, "Dock")))

    funnel = import_dock_part("p0a_funnel", funnel_mat)
    funnel.location = (DOCK_BAY_X, 0.0, DOCK_MOUTH_Z)
    made.append(funnel)

    keeper = import_dock_part("p0a_keeper", keeper_mat)
    keeper.location = (DOCK_BAY_X, 0.0, flange_z)
    # The keeper rides the funnel rather than being animated alongside it.
    # Left unparented it lands in the assembly group, gets fly-in keyframes on
    # `location`, and then the slider-crank bake fights them for the same
    # channel - which showed up as 10.9 mm of stroke instead of 13.0.
    keeper.parent = funnel
    keeper.matrix_parent_inverse = funnel.matrix_world.inverted()
    made.append(keeper)

    return made, (DOCK_BAY_X, 0.0, DOCK_MOUTH_Z), keeper


# --- micro-UAV ---------------------------------------------------------------
UAV_MOTOR_DIAGONAL = 0.10
UAV_PROP_DIAMETER = 0.055
UAV_PROBE_STANDOFF = 0.110


def build_prop(name, centre, radius, material, coll, blades=2, phase=0.0,
               hub_r=0.0045):
    """A small twisted two-blade rotor with real section geometry."""

    loop = airfoil_loop(0.0, 1.0, count=18)
    steps = 7
    verts, faces = [], []
    n = len(loop)
    for b in range(blades):
        ph = phase + 2.0 * math.pi * b / blades
        base = len(verts)
        for i in range(steps + 1):
            s = i / steps
            r = hub_r + (radius - hub_r) * s
            chord = 0.011 - 0.004 * s
            twist = math.radians(24.0 - 15.0 * s)
            for xc, half_t in loop:
                lx = (xc - 0.35) * chord
                lt = half_t * chord
                tang = lx * math.cos(twist) - lt * math.sin(twist)
                vz = lx * math.sin(twist) + lt * math.cos(twist)
                # Local to the hub, so the rotor spins about its own Z axis.
                verts.append((r * math.cos(ph) - tang * math.sin(ph),
                              r * math.sin(ph) + tang * math.cos(ph),
                              vz))
        for i in range(steps):
            a, bb = base + i * n, base + (i + 1) * n
            for j in range(n):
                k = (j + 1) % n
                faces.append((a + j, bb + j, bb + k, a + k))
        faces.append(tuple(range(base, base + n)))
        faces.append(tuple(range(base + steps * n, base + steps * n + n))[::-1])
    rotor = shade_smooth(mesh_object(name, verts, faces, material, coll), 26.0)
    rotor.location = centre
    return rotor


def build_uav(materials, origin, name="uav", heading=0.0, coll="UAV"):
    """One P0 micro-UAV: X frame, guarded rotors, probe mast and head.

    The 110 mm probe standoff is the dimensioned number that keeps the rotor
    plane clear of the funnel lip, and the guards are not decoration - P0 is a
    prop-guarded indoor article.
    """

    from mathutils import Vector

    parts = []
    half = UAV_MOTOR_DIAGONAL / (2.0 * math.sqrt(2.0))
    prop_r = UAV_PROP_DIAMETER * 0.5
    ox, oy, oz = origin

    # Frame arms: flat carbon plate, tapering outboard.
    for idx, ang in enumerate((math.pi / 4.0, -math.pi / 4.0)):
        L = UAV_MOTOR_DIAGONAL * 0.5 * 1.02
        ca, sa = math.cos(ang), math.sin(ang)
        verts, faces = [], []
        # Tapered rectangular-section arm: three stations along the diagonal.
        for u, w, hz in ((-1.0, 0.010, 0.0028), (0.0, 0.008, 0.0026),
                         (1.0, 0.006, 0.0022)):
            px, py = ca * L * u, sa * L * u
            for dy, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                verts.append((ox + px - sa * w * dy, oy + py + ca * w * dy,
                              oz + hz * dz))
        for i in range(2):
            a, b = i * 4, (i + 1) * 4
            for j in range(4):
                k = (j + 1) % 4
                faces.append((a + j, b + j, b + k, a + k))
        faces.append((0, 1, 2, 3))
        faces.append((8, 9, 10, 11)[::-1])
        parts.append(mesh_object(f"{name}_arm_{idx}", verts, faces,
                                 materials["carbon"], coll))

    # Body: stacked flight controller and battery, with a canopy.
    body = streamlined_sections(ox - 0.021, 0.042, 0.014, 0.011, count=14,
                                nose_frac=0.34, y0=oy, z0=oz + 0.002,
                                exponent=3.2, tail_frac=0.42)
    parts.append(loft_sections(f"{name}_body", body, materials["carbon"], coll,
                               segments=24, smooth_angle=34.0))

    for idx, (dx, dy) in enumerate(((half, half), (half, -half),
                                    (-half, half), (-half, -half))):
        mx, my = ox + dx, oy + dy
        # Motor can.
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.0058, depth=0.013, vertices=20,
            location=(mx, my, oz + 0.0085))
        motor = active()
        motor.name = f"{name}_motor_{idx}"
        motor.data.materials.append(materials["metal"])
        parts.append(shade_smooth(put(motor, coll)))

        parts.append(build_prop(
            f"{name}_prop_{idx}", (mx, my, oz + 0.0165), prop_r,
            materials["rotor"], coll, phase=idx * 0.7))

        # Prop guard: the ring plus two ties back to the arm.
        bpy.ops.mesh.primitive_torus_add(
            major_radius=prop_r + 0.005, minor_radius=0.0018,
            major_segments=40, minor_segments=8,
            location=(mx, my, oz + 0.0165))
        guard = active()
        guard.name = f"{name}_guard_{idx}"
        guard.data.materials.append(materials["guard"])
        parts.append(shade_smooth(put(guard, coll)))

        for tie in (-1, 1):
            ang = math.atan2(-my + oy, -mx + ox) + tie * 0.55
            bpy.ops.mesh.primitive_cylinder_add(
                radius=0.0013, depth=prop_r + 0.006, vertices=8,
                location=(mx + math.cos(ang) * (prop_r + 0.006) * 0.5,
                          my + math.sin(ang) * (prop_r + 0.006) * 0.5,
                          oz + 0.0125),
                rotation=(0.0, math.pi / 2.0, ang))
            strut = active()
            strut.name = f"{name}_guard_tie_{idx}_{tie}"
            strut.data.materials.append(materials["guard"])
            parts.append(shade_smooth(put(strut, coll)))

    # Probe: Ø3 mast and the real Rev-B probe head at 110 mm.
    bpy.ops.mesh.primitive_cylinder_add(
        radius=D["probe_mast_diameter_mm"] * 0.5 * MM,
        depth=UAV_PROBE_STANDOFF - 0.012, vertices=20,
        location=(ox, oy, oz + 0.006 + (UAV_PROBE_STANDOFF - 0.012) * 0.5))
    mast = active()
    mast.name = f"{name}_probe_mast"
    mast.data.materials.append(materials["metal"])
    parts.append(shade_smooth(put(mast, coll)))

    head = import_dock_part("p0a_probe_head", materials["metal"], coll)
    head.name = f"{name}_probe_head"
    head.location = (ox, oy, oz + UAV_PROBE_STANDOFF
                     - D["probe_head_seat_diameter_mm"] * MM)
    parts.append(head)

    # Nav light: the only emissive thing on the aircraft.
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.0035, segments=16, ring_count=8,
        location=(ox + 0.020, oy, oz + 0.004))
    lamp = active()
    lamp.name = f"{name}_navlight"
    lamp.data.materials.append(materials["light"])
    parts.append(shade_smooth(put(lamp, coll)))

    # Parent everything to an empty so the aircraft flies as one rigid body.
    bpy.ops.object.empty_add(type="PLAIN_AXES", radius=0.03, location=origin)
    root = active()
    root.name = f"{name}_root"
    put(root, coll)
    for part in parts:
        part.parent = root
        part.matrix_parent_inverse = root.matrix_world.inverted()
    root.rotation_euler = (0.0, 0.0, heading)
    return root, parts


# --- environment -------------------------------------------------------------
def build_world(horizon=(0.030, 0.036, 0.042), zenith=(0.012, 0.016, 0.022),
                floor=(0.006, 0.007, 0.008), strength=1.0):
    """A gradient studio environment rather than a flat grey background.

    A constant background lights every surface identically and is why an
    untextured hull reads as a paper cutout.  A vertical gradient gives the
    envelope a different ambient top to bottom, which is most of what sells a
    large curved surface before any lamp is switched on.
    """

    world = bpy.data.worlds.get("carrier_world") or bpy.data.worlds.new("carrier_world")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mapping = nt.nodes.new("ShaderNodeMapRange")
    coord = nt.nodes.new("ShaderNodeTexCoord")

    mapping.inputs["From Min"].default_value = -0.55
    mapping.inputs["From Max"].default_value = 0.75

    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*floor, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (*zenith, 1.0)
    mid = ramp.color_ramp.elements.new(0.45)
    mid.color = (*horizon, 1.0)

    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], mapping.inputs["Value"])
    nt.links.new(mapping.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def area_light(name, location, energy, size, target, coll="Lighting"):
    from mathutils import Vector

    bpy.ops.object.light_add(type="AREA", location=location)
    light = active()
    light.name = name
    light.data.energy = energy
    light.data.size = size
    light.data.shape = "SQUARE"
    light.rotation_euler = (
        (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler())
    return put(light, coll)


def build_lighting(centre=(2.25, 0.0, -0.2), dock=(DOCK_BAY_X, 0.0, -1.05),
                   scale=1.0):
    """Key, fill, rim and a dedicated belly bounce.

    The belly bounce is not optional.  The dock hangs underneath, so any rig
    lit from above puts the one assembly the programme cares about into full
    shadow - the previous renderer hit exactly this and had to bolt a bounce on
    afterwards.

    On exposure: the wattages here are roughly a tenth of that renderer's, and
    that is not a disagreement about the rig.  It lit a graphite envelope at
    0.055 base colour; this one is a light fabric at 0.80, some fourteen times
    more reflective, so the same lamps blow it to paper white - which is
    exactly what the first pass at this scene did.  `scale` retunes the whole
    rig together if the envelope palette changes again.
    """

    return [
        area_light("key", (6.2, -6.0, 4.6), 430.0 * scale, 5.0, centre),
        area_light("fill", (-5.4, -4.2, 0.6), 110.0 * scale, 6.5, centre),
        area_light("rim", (-1.2, 6.8, 3.4), 380.0 * scale, 4.0, centre),
        # The belly group carries the entire second act.  At a tenth of these
        # values the dock bay rendered as a black mass with a lit funnel
        # hanging out of it - technically shadowed correctly, and useless.
        area_light("belly_bounce", (3.4, -2.6, -3.0), 135.0 * scale, 2.6, dock),
        area_light("dock_accent", (1.5, -1.4, -2.2), 42.0 * scale, 0.9, dock),
        area_light("keel_fill", (2.4, -3.2, -1.5), 75.0 * scale, 2.0,
                   (2.3, 0.0, -0.80)),
    ]


def add_camera(name, location, target, focal_mm=70.0, coll="Lighting"):
    from mathutils import Vector

    bpy.ops.object.camera_add(location=location)
    cam = active()
    cam.name = name
    cam.data.lens = focal_mm
    cam.rotation_euler = (
        (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler())
    bpy.context.scene.camera = cam
    return put(cam, coll)


def configure_render(samples=64, width=1920, height=1080, engine="BLENDER_EEVEE"):
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    if engine == "BLENDER_EEVEE":
        ev = scene.eevee
        ev.taa_render_samples = samples
        ev.taa_samples = 16
        ev.use_gtao = True                 # contact shadow in the seams
        ev.gtao_distance = 0.4
        ev.use_ssr = True                  # the glazing and metal need it
        ev.use_ssr_refraction = True
        ev.use_bloom = True                # nav light reads as a light source
        ev.bloom_intensity = 0.035
        ev.bloom_threshold = 1.2
        ev.use_soft_shadows = True
        ev.shadow_cube_size = "2048"
        ev.shadow_cascade_size = "2048"
    else:
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"
    return scene


def set_origin(obj, world_point):
    """Move an object's origin to `world_point` without moving its geometry."""

    from mathutils import Vector

    delta = Vector(world_point) - obj.location
    for vert in obj.data.vertices:
        vert.co -= delta
    obj.location = Vector(world_point)
    obj.data.update()
    return obj


def add_bevel(obj, width=0.0025, segments=2, angle_deg=44.0):
    """Put a small bevel on a hard-surface part.

    Nothing in the physical world has a zero-radius edge, so a perfectly sharp
    edge catches no highlight at all and reads as computer output.  A fraction
    of a millimetre is enough - the point is the specular line along the edge,
    not the visible radius.
    """

    if obj.type != "MESH":
        return obj
    mod = obj.modifiers.new("edge_bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle_deg)
    mod.miter_outer = "MITER_ARC"
    return obj


def build_fin_fairings(material):
    """Root fillets where the tail surfaces meet the envelope.

    A fin that intersects the hull along a hard line looks stuck on.  Real
    surfaces carry a fillet that grows through the mid-chord and fades out at
    both ends, which is what the per-point curve radius does here.
    """

    made = []
    for index, roll_deg in enumerate(FIN_ROLL_DEG):
        roll = math.radians(roll_deg)
        for side in (-1, 1):
            name = f"fin_fillet_{index}_{'a' if side < 0 else 'b'}"
            curve = bpy.data.curves.new(name, "CURVE")
            curve.dimensions = "3D"
            curve.bevel_depth = 0.015
            curve.bevel_resolution = 3
            curve.use_fill_caps = True

            samples = 40
            spline = curve.splines.new("POLY")
            spline.points.add(samples - 1)
            for i in range(samples):
                s = i / (samples - 1)
                xc = s
                x = FIN_ROOT_LE_X + FIN_ROOT_CHORD * xc
                r = hull_surface(x, roll)
                # Offset sideways by the local half-thickness of the section.
                lateral = FIN_ROOT_CHORD * naca_thickness(xc) + 0.004
                theta = roll + side * (lateral / max(r, 0.05))
                rr = hull_surface(x, theta) + 0.004
                spline.points[i].co = (x, rr * math.cos(theta),
                                       rr * math.sin(theta), 1.0)
                # Fat through the middle, vanishing at leading and trailing edge.
                spline.points[i].radius = math.sin(math.pi * s) ** 0.7

            obj = bpy.data.objects.new(name, curve)
            obj.data.materials.append(material)
            made.append(put(obj, "Tail"))
    return made


def build_nav_lights(materials):
    """Port red, starboard green, white tail and a top anti-collision beacon."""

    made = []
    specs = [
        ("nav_port", 1.62, math.radians(200.0), materials["nav_red"]),
        ("nav_stbd", 1.62, math.radians(-20.0), materials["nav_green"]),
        ("nav_top", 2.10, math.radians(90.0), materials["nav_beacon"]),
    ]
    for name, x, theta, mat in specs:
        r = hull_surface(x, theta) + 0.004
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.021, segments=20, ring_count=10,
            location=(x, r * math.cos(theta), r * math.sin(theta)))
        lamp = active()
        lamp.name = name
        lamp.scale = (1.0, 1.0, 0.55)
        lamp.rotation_euler = (0.0, 0.0, 0.0)
        lamp.data.materials.append(mat)
        made.append(shade_smooth(put(lamp, "Envelope")))

    # Tail light on the cone fitting.
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.016, segments=16, ring_count=8,
        location=(ENVELOPE_LENGTH_M + 0.035, 0.0, 0.0))
    tail = active()
    tail.name = "nav_tail"
    tail.data.materials.append(materials["nav_white"])
    made.append(shade_smooth(put(tail, "Envelope")))
    return made


def build_hull_marking(text, material, x=1.55, size=0.20):
    """Programme marking on the envelope flank, wrapped onto the hull.

    Built as text, converted to a mesh and shrink-wrapped radially onto the
    envelope, so it follows the quilting instead of floating as a flat plate.
    Guarded: a marking is a nice-to-have and must never take the build down.
    """

    try:
        curve = bpy.data.curves.new("hull_marking", "FONT")
        curve.body = text
        curve.size = size
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.extrude = 0.002
        obj = bpy.data.objects.new("hull_marking", curve)
        put(obj, "Envelope")

        # Stand the text up in the X-Z plane, outboard on the port flank.
        obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
        obj.location = (x, -(HULL_RADIUS_M + 0.35), 0.10)

        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.convert(target="MESH")
        obj = bpy.context.view_layer.objects.active

        wrap = obj.modifiers.new("wrap", "SHRINKWRAP")
        wrap.target = bpy.data.objects["envelope"]
        # Nearest-surface, not project.  Projection leaves any vertex that
        # misses the hull sitting at its original offset, and those strays
        # rendered as a second ghost marking floating beside the real one.
        wrap.wrap_method = "NEAREST_SURFACEPOINT"
        wrap.offset = 0.005
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.select_set(False)
        return [obj]
    except Exception:
        return []


# --- whole vehicle -----------------------------------------------------------
#: Site palette, so this model and the Three.js page stay the same vehicle.
AMBER = (1.0, 0.24, 0.06, 1.0)


def build_materials():
    return {
        "fabric": fabric_material("envelope_fabric", (0.62, 0.64, 0.65, 1.0)),
        "seam": pbr("seam_tape", (0.40, 0.42, 0.44, 1.0), roughness=0.55),
        "fitting": pbr("fitting_alu", (0.52, 0.54, 0.57, 1.0), roughness=0.34,
                       metallic=0.85, anisotropic=0.4),
        # Tail surfaces are fabric over a frame on a real airship, so they sit
        # close to the envelope in tone.  Near-black fins against a light hull
        # read as a plastic toy with stick-on tailplanes, which is what the
        # first pass looked like.  The control surfaces stay a step darker so
        # the hinge line is still legible in the breakdown.
        "fin": pbr("fin_composite", (0.50, 0.52, 0.53, 1.0), roughness=0.46,
                   specular=0.45, sheen=0.3),
        "control": pbr("fin_control", (0.34, 0.355, 0.37, 1.0), roughness=0.42,
                       specular=0.5, clearcoat=0.2),
        "rail": pbr("keel_rail_m", (0.22, 0.23, 0.25, 1.0), roughness=0.38,
                    metallic=0.55),
        "strut": pbr("strut_alu", (0.46, 0.48, 0.51, 1.0), roughness=0.30,
                     metallic=0.9, anisotropic=0.45),
        "shell": pbr("gondola_shell_m", (0.14, 0.15, 0.165, 1.0),
                     roughness=0.28, specular=0.6, clearcoat=0.5),
        "glass": pbr("glazing", (0.02, 0.035, 0.045, 1.0), roughness=0.06,
                     specular=0.95, clearcoat=0.85),
        "duct": pbr("duct_shell", (0.26, 0.275, 0.29, 1.0), roughness=0.32,
                    specular=0.6, clearcoat=0.4),
        "hub": pbr("fan_hub", (0.50, 0.52, 0.55, 1.0), roughness=0.28,
                   metallic=0.9),
        "blade": pbr("fan_blade", (0.065, 0.07, 0.075, 1.0), roughness=0.30,
                     specular=0.55, clearcoat=0.4),
        # The dock bay is the reason the vehicle exists; at 0.13 it vanished
        # into the belly shadow in every frame that was supposed to show it.
        "bay": pbr("dock_bay", (0.30, 0.315, 0.33, 1.0), roughness=0.34,
                   clearcoat=0.45),
        "funnel": pbr("dock_funnel_m", (0.84, 0.85, 0.82, 1.0), roughness=0.50),
        "keeper": pbr("dock_keeper_m", AMBER, roughness=0.38),
        "ring": pbr("dock_ring", (0.17, 0.18, 0.20, 1.0), roughness=0.34,
                    metallic=0.75),
        "carbon": pbr("uav_carbon_m", (0.030, 0.033, 0.037, 1.0),
                      roughness=0.36, clearcoat=0.5),
        "metal": pbr("uav_metal_m", (0.53, 0.55, 0.58, 1.0), roughness=0.30,
                     metallic=0.9),
        "rotor": pbr("uav_rotor_m", (0.06, 0.065, 0.07, 1.0), roughness=0.42),
        "guard": pbr("uav_guard_m", (0.11, 0.12, 0.13, 1.0), roughness=0.5),
        "light": pbr("uav_light_m", AMBER, roughness=0.4, emission=AMBER,
                     emission_strength=26.0),
        "marking": pbr("hull_marking_m", (0.10, 0.11, 0.12, 1.0),
                       roughness=0.45),
        "nav_red": pbr("nav_red", (0.55, 0.02, 0.02, 1.0), roughness=0.25,
                       emission=(1.0, 0.05, 0.03, 1.0), emission_strength=14.0),
        "nav_green": pbr("nav_green", (0.02, 0.5, 0.12, 1.0), roughness=0.25,
                         emission=(0.06, 1.0, 0.25, 1.0), emission_strength=14.0),
        "nav_white": pbr("nav_white", (0.7, 0.72, 0.75, 1.0), roughness=0.25,
                         emission=(1.0, 0.95, 0.88, 1.0), emission_strength=4.5),
        "nav_beacon": pbr("nav_beacon", (0.6, 0.18, 0.04, 1.0), roughness=0.25,
                          emission=(1.0, 0.35, 0.06, 1.0), emission_strength=16.0),
    }


def build_scene():
    """Build the whole vehicle and return the handles an animation needs."""

    clear()
    m = build_materials()

    envelope = build_envelope(m["fabric"])
    envelope_detail = build_envelope_detail(m["seam"], m["fitting"])
    envelope_detail += build_nav_lights(m)
    envelope_detail += build_hull_marking("CARRIER-P0", m["marking"])
    fins, controls = build_tail(m["fin"], m["control"])
    fairings = build_fin_fairings(m["fin"])
    keel = build_keel(m["rail"], m["strut"])
    gondola, _ = build_gondola(m["shell"], m["glass"], m["strut"])
    propulsion, fan_units = build_propulsion({
        "duct": m["duct"], "hub": m["hub"], "blade": m["blade"],
        "pylon": m["strut"]})
    dock, mouth, keeper = build_dock(m["bay"], m["funnel"], m["keeper"],
                                     m["ring"])

    uav_mats = {k: m[k] for k in
                ("carbon", "metal", "rotor", "guard", "light")}
    approach = mouth[2] - 0.13 - UAV_PROBE_STANDOFF
    uav_root, uav_parts = build_uav(
        uav_mats, (mouth[0], mouth[1], approach), name="uav_final")

    # Bevel the fabricated hard surfaces.  Deliberately excluded: the envelope
    # (already a smooth lofted surface, and a bevel would fight the quilting)
    # and the imported Rev-B parts - those are fabrication geometry, and
    # rounding their edges to flatter a render would put the model out of step
    # with the article that actually gets printed.
    protected = {"p0a_funnel", "p0a_keeper", "envelope"}
    for group in (fins, controls, keel, gondola, propulsion, dock):
        for obj in group:
            if obj.type == "MESH" and obj.name not in protected \
                    and not obj.name.startswith("p0a_"):
                add_bevel(obj, width=0.0022)
    for obj in uav_parts:
        if obj.type == "MESH" and not obj.name.startswith("p0a_") \
                and "probe_head" not in obj.name:
            add_bevel(obj, width=0.00035, segments=1)

    build_world()
    lights = build_lighting()
    configure_render()

    return {
        "materials": m,
        "mouth": mouth,
        "keeper": keeper,
        "uav_root": uav_root,
        "uav_parts": uav_parts,
        "controls": controls,
        "fan_units": fan_units,
        "lights": lights,
        # Subassembly groups, in the order a breakdown should reveal them.
        "groups": [
            ("Envelope", [envelope] + envelope_detail),
            ("Tail surfaces", fins + controls + fairings),
            ("Keel structure", keel),
            ("Gondola", gondola),
            ("Propulsion", propulsion),
            ("Belly dock", dock),
            ("Micro-UAV", [uav_root] + uav_parts),
        ],
    }
