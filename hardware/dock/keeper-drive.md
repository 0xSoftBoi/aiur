# Keeper drive

Status: designed and in the generated CAD; not built
Applies to: Rev-B keeper, 13.0 mm open travel

Rev-B needs 13.0 mm of linear keeper stroke from a rotary servo. The
selected mechanism is an in-line slider-crank, and it is now in
`generate_rev_a.py` as parameters, meshes, and a pin-hole template:

| Parameter | Value | Why |
| --- | ---: | --- |
| Crank radius | 6.5 mm | In-line slider-crank gives stroke = 2R exactly, so this is the requirement halved, not a packaging choice |
| Link length | 19.5 mm | L/R = 3 bounds obliquity at 19.5°, so the guides carry about 0.35× the axial force sideways |
| Pin diameter | Ø3 mm | Both joints; drilled after print |
| Keeper pin | x = −14 mm | In the solid back. `keeper_mesh` **raises** if it would break into the slot or out of the back edge |
| Servo axis | x = −40 mm | L + R behind the keeper pin at full extension; this is what the dock footprint grows by |

Both halves of the stroke chain are now checked in code, which is the point:
`drive_stroke_shortfall_mm()` asks whether the linkage can deliver the
commanded stroke, and `release_travel_shortfall_mm()` asks whether the
commanded stroke clears the probe head. Rev-A's defect was a stroke number
that nothing downstream had to honour; a linkage sized by eye would have
recreated it one level up.

Pin holes are **not modelled**. This generator has no boolean geometry, and
a slot open to an edge would let a pin walk out under 600 life cycles
(P0-DRIVE-006). They are drilled after print from
`p0a_linkage_template_rev_b.svg`, exactly as the funnel flange holes are —
the template carries a 50 mm check line because getting the link centres
wrong changes the delivered stroke directly.

## What the stroke has to be

Not a free parameter. The keeper must retract until its tines clear the
widest part of the probe head, and `DockRevision.exact_release_travel_mm()`
computes that from the tine reach and the belt diameter:

```
tine reach 5.0 mm + sqrt(6.0^2 - 2.6^2) = 10.41 mm required
commanded stroke                        = 13.0 mm
margin                                  = 2.59 mm
```

The commanded 13.0 mm also carries the ±0.4 mm delivered-stroke tolerance
the tolerance stack assumes, leaving `keeper_release_clearance` at +1.15 mm
worst case. Delivering **less** than about 11 mm reopens the Rev-A defect in
which a captured aircraft cannot be released, and emergency release —
loaded and unloaded — is a P0-A gate criterion. Treat the stroke as a
safety requirement, not a convenience.

## Trade

| Mechanism | Crank radius for 13 mm | Cost |
| --- | ---: | --- |
| Scotch yoke (pin in a transverse slot in the keeper) | 6.5 mm | Slot must accept ±6.5 mm of pin travel across an 18 mm keeper: 16 mm of slot leaves **1.0 mm of material each side**. Rejected — the drive feature becomes the weakest part of a retention component |
| Horn arc driving a slot, 90° swing | 9.19 mm | Large horn; lateral pin travel still needs a wide slot |
| Horn arc driving a slot, 180° swing | 6.50 mm | Degenerates to the scotch yoke |
| **Slider-crank (crank + link to a pin on the keeper)** | **6.5 mm, link 19.5 mm** | Link absorbs the lateral motion, so the keeper needs only a pin boss, not a slot. Max obliquity 19.5° at L/R = 3. **Recommended** |

The slider-crank wins for one reason: it puts no long slot through a part
whose job is to carry retention load. The keeper keeps a solid section and
gains a single pin boss.

## Requirements

| ID | Requirement | Why |
| --- | --- | --- |
| P0-DRIVE-001 | Delivered keeper stroke ≥ 13.0 mm measured at the keeper, not commanded at the servo | Commanded angle is not delivered travel; Rev-A's whole defect was a declared number nothing verified |
| P0-DRIVE-002 | Stroke measured with a dial indicator on the built article and recorded in the as-built set | The tolerance stack assumes ±0.4 mm; that assumption has never been measured |
| P0-DRIVE-003 | Hard travel stops at both ends, independent of servo position limits | A servo that loses its configuration must not drive the keeper into the funnel or past its guides |
| P0-DRIVE-004 | The 5 N axial screening load reacts through the keeper guides and end stop, never through the geartrain | Already the stated architecture; the linkage must not quietly become the load path |
| P0-DRIVE-005 | Close and open force margin ≥ 2.0 against worst-case resistance at minimum supply voltage | Existing P0-A gate criterion; the linkage ratio is what converts servo torque into keeper force, so it is sized here |
| P0-DRIVE-006 | Pin joints retained so they cannot walk out under cycling | 600 life cycles; a press-fit pin that migrates is a mid-campaign failure |

## What remains

The crank, the link, and the keeper pin location are generated. Two items
are still bench work rather than CAD, because both are set by adjustment
against the built article:

1. **Keeper guides and hard stops** on the bracket, setting the travel. The
   [assembly procedure](assembly.md) section 3 sets and measures them.
2. **Bracket geometry** locating the servo axis at x = −40 mm relative to
   the funnel flange. The dock footprint grows accordingly.

The acceptance test is arithmetic that already exists, run against the
article rather than the drawing: `release_travel_shortfall_mm()` must stay
negative with the **measured** stroke substituted, not the commanded one.

## Force sizing note

The gate's ≥2.0 force margin is against *resistance*, and the dominant
resistance here is friction in the guides plus any side load on the probe —
not the 5 N screening load, which the guides and end stop react. Size the
linkage after measuring keeper breakaway force on the assembled article at
minimum supply voltage, per the [bench procedure](p0a-bench.md). Sizing it
from a servo torque figure alone would be a calculation about a datasheet
rather than about this mechanism.
