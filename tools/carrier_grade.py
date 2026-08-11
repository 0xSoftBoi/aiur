"""Look pipeline: baked indirect light, surface breakup, and the comp stack.

Three separate problems, in the order they have to be solved.

**Indirect light.**  Cycles is not available here - this machine exposes no GPU
to it, and a 720p frame at 48 samples measured 53 s, which is fourteen hours
for the sequence and thirty-two at 1080p.  So the renderer stays EEVEE, and
EEVEE's answer to global illumination is a baked irradiance volume.  It is not
path tracing, but it is the difference between a hall where light bounces off
the floor and one where every surface facing away from a lamp is dead black.

**Surface breakup.**  A material that is one flat colour reads as CG at any
resolution.  Production lookdev layers wear: dirt collected in crevices,
scuffing on exposed faces, and low-contrast variation at a scale well above
either.  The crevice term here is a real ambient-occlusion lookup, which EEVEE
does support, so grime accumulates where geometry actually traps it rather
than wherever a noise texture happened to be dark.

**The comp stack.**  Lens distortion, chromatic aberration, glare, vignette,
grain: these are lens and film artefacts, and they are almost never rendered in
3D.  Order matters and is not arbitrary - distortion and aberration belong at
the front because they are optical, happening in the lens before the sensor;
grain belongs at the very end because it is the recording medium, after
everything the lens did.  Grain also breaks up colour banding in the smooth
gradients this scene is full of.
"""

import bpy


# --- baked indirect light ----------------------------------------------------
def add_irradiance_volume(centre=(2.6, 0.0, -0.4), size=(22.0, 19.0, 8.0),
                          resolution=(10, 9, 5)):
    """An irradiance grid over the hall, for EEVEE's baked bounce light."""

    bpy.ops.object.lightprobe_add(type="GRID", location=centre)
    probe = bpy.context.view_layer.objects.active
    probe.name = "hall_irradiance"
    probe.scale = (size[0] / 2.0, size[1] / 2.0, size[2] / 2.0)
    grid = probe.data
    grid.grid_resolution_x, grid.grid_resolution_y, grid.grid_resolution_z = resolution
    grid.influence_distance = 3.0
    grid.falloff = 0.4
    # One bounce is enough for a room this simple and keeps the bake short.
    return probe


def add_reflection_probe(centre=(2.5, 0.0, -0.9), radius=3.2):
    """A reflection cubemap around the dock, so metal there has something to
    reflect other than the world gradient."""

    bpy.ops.object.lightprobe_add(type="CUBEMAP", location=centre)
    probe = bpy.context.view_layer.objects.active
    probe.name = "dock_reflection"
    probe.data.influence_distance = radius
    probe.data.falloff = 0.35
    probe.data.clip_start = 0.05
    return probe


def bake_indirect():
    scene = bpy.context.scene
    scene.eevee.gi_diffuse_bounces = 2
    scene.eevee.gi_cubemap_resolution = "512"
    scene.eevee.gi_visibility_resolution = "32"
    scene.eevee.gi_irradiance_smoothing = 0.2
    bpy.ops.scene.light_cache_bake()
    return scene.eevee


# --- surface breakup ---------------------------------------------------------
def add_surface_wear(material, dirt_strength=0.35, dirt_color=(0.16, 0.155, 0.14),
                     scuff=0.10, rough_break=0.12, ao_distance=0.25):
    """Layer crevice dirt and broad scuffing onto an existing Principled setup.

    Deliberately additive: it rewires whatever Base Color and Roughness the
    material already had rather than replacing them, so a part keeps its
    intended colour and just stops being uniform.
    """

    if material is None or not material.use_nodes:
        return material
    nt = material.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        return material

    base = bsdf.inputs["Base Color"].default_value[:]
    roughness = bsdf.inputs["Roughness"].default_value

    coord = nt.nodes.new("ShaderNodeTexCoord")

    # Crevice dirt, driven by real ambient occlusion.
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = ao_distance
    ao.only_local = True
    ao.samples = 8

    cavity = nt.nodes.new("ShaderNodeMapRange")
    cavity.inputs["From Min"].default_value = 0.35
    cavity.inputs["From Max"].default_value = 0.95
    cavity.inputs["To Min"].default_value = dirt_strength
    cavity.inputs["To Max"].default_value = 0.0
    cavity.clamp = True
    nt.links.new(ao.outputs["AO"], cavity.inputs["Value"])

    # Broad scuffing so large flat faces are not one value.
    grime = nt.nodes.new("ShaderNodeTexNoise")
    grime.inputs["Scale"].default_value = 2.6
    grime.inputs["Detail"].default_value = 6.0
    grime.inputs["Roughness"].default_value = 0.62
    nt.links.new(coord.outputs["Object"], grime.inputs["Vector"])

    scuff_fac = nt.nodes.new("ShaderNodeMapRange")
    scuff_fac.inputs["From Min"].default_value = 0.42
    scuff_fac.inputs["From Max"].default_value = 0.72
    scuff_fac.inputs["To Min"].default_value = 0.0
    scuff_fac.inputs["To Max"].default_value = scuff
    scuff_fac.clamp = True
    nt.links.new(grime.outputs["Fac"], scuff_fac.inputs["Value"])

    total = nt.nodes.new("ShaderNodeMath")
    total.operation = "ADD"
    nt.links.new(cavity.outputs["Result"], total.inputs[0])
    nt.links.new(scuff_fac.outputs["Result"], total.inputs[1])

    tint = nt.nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MIX"
    tint.inputs[1].default_value = base
    tint.inputs[2].default_value = (*dirt_color, 1.0)
    nt.links.new(total.outputs[0], tint.inputs[0])

    # If something already drives Base Color, leave it alone.
    if not bsdf.inputs["Base Color"].is_linked:
        nt.links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])

    if not bsdf.inputs["Roughness"].is_linked:
        rough = nt.nodes.new("ShaderNodeMapRange")
        rough.inputs["From Min"].default_value = 0.35
        rough.inputs["From Max"].default_value = 0.70
        rough.inputs["To Min"].default_value = max(0.02, roughness - rough_break)
        rough.inputs["To Max"].default_value = min(1.0, roughness + rough_break)
        rough.clamp = True
        nt.links.new(grime.outputs["Fac"], rough.inputs["Value"])
        nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return material


def weather_scene(skip=("callout_text", "callout_sub", "nav_red", "nav_green",
                        "nav_white", "nav_beacon", "uav_light_m",
                        "hall_fixture", "mocap_ring", "glazing")):
    """Apply wear to every material that is not a light source or glass."""

    touched = 0
    for material in bpy.data.materials:
        if material.name in skip or not material.use_nodes:
            continue
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        # Emissive things are lights; dirtying them makes no sense.  Test the
        # emission colour, not just the strength: Principled ships with
        # strength 1.0 and a black colour, so a strength-only check treats
        # every material in the scene as a lamp and weathers nothing.
        colour = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        strength = bsdf.inputs.get("Emission Strength")
        emissive = (
            colour is not None
            and sum(colour.default_value[:3]) > 0.02
            and (strength is None or strength.default_value > 0.0)
        )
        if emissive:
            continue
        add_surface_wear(material)
        touched += 1
    return touched


# --- comp stack --------------------------------------------------------------
def build_comp(mist_strength=0.30, mist_color=(0.16, 0.19, 0.24),
               dispersion=0.008, glare_threshold=1.05, vignette=0.15,
               grain=0.014, exposure=-0.35, streaks=False):
    """Assemble the compositor: atmosphere, lens, grade, vignette, grain.

    Tuned down from the first pass, which stacked a hard S-curve, a heavy
    vignette and two glare nodes and produced a blown-white vehicle against a
    black rectangle - it threw away both the envelope quilting and the hall.
    The exposure offset protects the highlights at source, which is the right
    place to do it, rather than trying to pull them back with a curve.

    `streaks` is off by default: anamorphic flares are a strong stylistic
    claim, and the second glare node roughly doubled comp cost.
    """

    scene = bpy.context.scene
    scene.view_settings.exposure = exposure
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()

    layers = nt.nodes.new("CompositorNodeRLayers")
    node_x = 0

    def place(node):
        nonlocal node_x
        node_x += 220
        node.location = (node_x, 0)
        return node

    # 1. Atmosphere.  This is in-world depth haze, so it goes before anything
    #    the lens does to the image.
    gain = place(nt.nodes.new("CompositorNodeMath"))
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = mist_strength
    fog = place(nt.nodes.new("CompositorNodeMixRGB"))
    fog.inputs[2].default_value = (*mist_color, 1.0)
    nt.links.new(layers.outputs["Mist"], gain.inputs[0])
    nt.links.new(gain.outputs[0], fog.inputs[0])
    nt.links.new(layers.outputs["Image"], fog.inputs[1])
    head = fog.outputs[0]

    # 2. Lens: distortion and chromatic aberration happen in the glass, so they
    #    come before every downstream effect.
    lens = place(nt.nodes.new("CompositorNodeLensdist"))
    lens.use_projector = False
    lens.use_jitter = False
    lens.use_fit = True
    lens.inputs["Distort"].default_value = 0.006
    lens.inputs["Dispersion"].default_value = dispersion
    nt.links.new(head, lens.inputs["Image"])
    head = lens.outputs["Image"]

    # 3. Glare: veiling glow off the bright fixtures, plus a restrained streak.
    # LOW quality, not MEDIUM: on veiling glare this soft the difference is
    # invisible and MEDIUM cost about 20 s a frame, which is four hours over
    # the sequence.
    fog_glow = place(nt.nodes.new("CompositorNodeGlare"))
    fog_glow.glare_type = "FOG_GLOW"
    fog_glow.quality = "LOW"
    fog_glow.threshold = glare_threshold
    fog_glow.size = 6
    fog_glow.mix = -0.86
    nt.links.new(head, fog_glow.inputs["Image"])
    head = fog_glow.outputs["Image"]

    if streaks:
        streak = place(nt.nodes.new("CompositorNodeGlare"))
        streak.glare_type = "STREAKS"
        streak.quality = "LOW"
        streak.threshold = 1.25
        streak.streaks = 6
        streak.angle_offset = 0.20
        streak.fade = 0.88
        streak.mix = -0.90
        nt.links.new(head, streak.inputs["Image"])
        head = streak.outputs["Image"]

    # 4. Grade: cool the shadows, warm the highlights, then an S-curve.
    balance = place(nt.nodes.new("CompositorNodeColorBalance"))
    balance.correction_method = "LIFT_GAMMA_GAIN"
    balance.lift = (0.982, 0.995, 1.020)
    balance.gamma = (1.0, 1.0, 0.995)
    balance.gain = (1.030, 1.008, 0.978)
    nt.links.new(head, balance.inputs["Image"])
    head = balance.outputs["Image"]

    curves = place(nt.nodes.new("CompositorNodeCurveRGB"))
    combined = curves.mapping.curves[3]
    combined.points[0].location = (0.0, 0.0)
    combined.points[-1].location = (1.0, 1.0)
    combined.points.new(0.27, 0.245)
    combined.points.new(0.73, 0.762)
    curves.mapping.update()
    nt.links.new(head, curves.inputs["Image"])
    head = curves.outputs["Image"]

    # 5. Vignette: an elliptical mask, heavily blurred, multiplied back.
    mask = nt.nodes.new("CompositorNodeEllipseMask")
    mask.location = (node_x - 200, -420)
    mask.width = 0.95
    mask.height = 1.00
    mask.mask_type = "ADD"
    blur = nt.nodes.new("CompositorNodeBlur")
    blur.location = (node_x, -420)
    blur.filter_type = "FAST_GAUSS"
    blur.size_x = blur.size_y = 220
    blur.use_relative = False
    nt.links.new(mask.outputs["Mask"], blur.inputs["Image"])

    vig_mix = place(nt.nodes.new("CompositorNodeMixRGB"))
    vig_mix.blend_type = "MULTIPLY"
    vig_mix.inputs[0].default_value = vignette
    nt.links.new(head, vig_mix.inputs[1])
    nt.links.new(blur.outputs["Image"], vig_mix.inputs[2])
    head = vig_mix.outputs[0]

    # 6. Grain, last.  It is the recording medium, so it sits after everything
    #    the lens did - and it is what keeps the smooth gradients in this scene
    #    from banding.
    noise = bpy.data.textures.get("film_grain")
    if noise is None:
        noise = bpy.data.textures.new("film_grain", "NOISE")
    grain_tex = nt.nodes.new("CompositorNodeTexture")
    grain_tex.location = (node_x - 200, -700)
    grain_tex.texture = noise
    # Drift the grain per frame; a fixed pattern reads as sensor dirt.
    driver = grain_tex.inputs["Offset"].driver_add("default_value", 0).driver
    driver.type = "SCRIPTED"
    driver.expression = "frame * 0.191"

    grain_mix = place(nt.nodes.new("CompositorNodeMixRGB"))
    grain_mix.blend_type = "OVERLAY"
    grain_mix.inputs[0].default_value = grain
    nt.links.new(head, grain_mix.inputs[1])
    nt.links.new(grain_tex.outputs["Color"], grain_mix.inputs[2])
    head = grain_mix.outputs[0]

    output = place(nt.nodes.new("CompositorNodeComposite"))
    nt.links.new(head, output.inputs["Image"])
    return nt
