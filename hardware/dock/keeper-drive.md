# Keeper drive

Status: requirement and trade study; **the drive interface is not in the
generated CAD**. This is the top open item blocking a P0-A build.
Applies to: Rev-B keeper, 13.0 mm open travel

Rev-B needs 13.0 mm of linear keeper stroke. The actuator is a rotary servo.
Nothing in the repository currently converts one into the other: the
generated keeper is a plain fork with no drive feature, and
[p0a-fabrication.md](p0a-fabrication.md) says only that the actuator mount
stays swappable. That gap is deliberate rather than hidden — this document
records what the stroke demands and what the candidates cost, so the
remaining work is a bounded design task instead of an unexamined assumption.

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

## What remains to be designed

1. Crank geometry on the servo horn: hole at R = 6.5 mm, retained pin.
2. Link, ~19.5 mm between pin centres, printed or cut, with clearance fits.
3. Pin boss on the keeper, placed in the solid back region behind the fork
   so it does not intrude on the bearing face.
4. Keeper guides and hard stops on the bracket, setting the 13.0 mm travel.
5. Bracket geometry locating the servo relative to the funnel flange.

None of these are in `cad/generate_rev_a.py`. Adding them is the next CAD
task, and the acceptance test is arithmetic that already exists:
`release_travel_shortfall_mm()` must stay negative for the built article
with its **measured** stroke substituted, not its commanded one.

## Force sizing note

The gate's ≥2.0 force margin is against *resistance*, and the dominant
resistance here is friction in the guides plus any side load on the probe —
not the 5 N screening load, which the guides and end stop react. Size the
linkage after measuring keeper breakaway force on the assembled article at
minimum supply voltage, per the [bench procedure](p0a-bench.md). Sizing it
from a servo torque figure alone would be a calculation about a datasheet
rather than about this mechanism.
