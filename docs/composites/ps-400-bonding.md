# PS-400 — Bonding process specification

Status: process specification, issue A, opened 2026-08-12
Scope: adhesive bonding of CARRIER-P0 composite structure
Executable source: [`aiur/composites/bonding.py`](../../aiur/composites/bonding.py) —
`python -m aiur.composites.bonding`

A bonded joint is the only kind that does not put a hole through the fibre.
It is also the only structural feature in this programme whose strength
cannot be verified after the fact, and this specification exists because of
the second sentence rather than the first.

## 1. What the analysis found

### Overlap length saturates

Load transfers into a bonded joint over a length of about `1/ω`, where

```
ω = sqrt( (Ga / ta) · (1/S₁ + 1/S₂) )
```

Past roughly `6/ω` the middle of the overlap carries essentially nothing.

| joint | `1/ω` | saturates at | drawing overlap | inert |
| --- | --- | --- | --- | --- |
| BJ-100 throat flange | 1.51 mm | 9.1 mm | 12 mm | 3 mm |
| BJ-200 boom root | 0.72 mm | 4.3 mm | 15 mm | 10.7 mm |
| BJ-300 tine root | 3.18 mm | 19.1 mm | 18 mm | 0 mm |

A 40 mm overlap on the boom root would carry exactly what a 5 mm one does.
**No overlap on any drawing in this programme is sized by strength**, and
each one records what did size it — flange width, fit-up tolerance, or the
mating part's geometry. A drawing note claiming a long overlap is "for
strength" would be describing something that does not happen.

### A thicker bondline can be stronger

`ω` falls as the square root of bondline thickness, so a slightly thicker
adhesive layer spreads the load transfer and lowers the peak. The boom root
uses this: at the film adhesive's 0.20 mm nominal it reaches only 1.29 times
its adherend's capacity, against a 1.5 requirement; at **0.30 mm** it
reaches 1.58.

This is bounded, not a free lunch. Past about 0.4 mm the bondline traps
voids and loses peel strength faster than it gains shear, which is why the
process band is 0.10–0.40 mm and why a bondline is *controlled* rather than
minimised.

### Bond to a rigid fitting and the peak doubles

When one adherend is much stiffer than the other, all of the strain mismatch
lands at one end of the overlap and the peak shear is twice what a balanced
joint of the same `ω` would see. Every bond here is composite-to-fitting, so
every one pays this penalty. It is in the model, not a footnote.

## 2. Two qualification routes

The standard rule for an unverifiable bond is to make it stronger than what
it joins, so an overload fails the laminate — visible, inspectable — rather
than the bondline. That rule is achievable for a thin adherend and
**arithmetically impossible** for a thick one:

| joint | adherend capacity | bondline needed for adherend-first | achievable? |
| --- | --- | --- | --- |
| BJ-100 | 167 N/mm | 1.13 mm | no |
| BJ-200 | 32 N/mm | 0.27 mm | **yes** |
| BJ-300 | 729 N/mm | 4.82 mm | no |

Writing "the bond shall be stronger than the adherend" as an unconditional
requirement would have left two of three joints permanently non-compliant
with no route to compliance, which is how a design rule gets quietly
ignored. So a joint qualifies by **either**:

1. **adherend-first** — capacity ≥ 1.5 × the adherend's own capacity; or
2. **load margin plus proof test** — capacity ≥ 2.0 × design load, *and* a
   proof test on every article.

A **critical** joint carries a proof test whichever route it qualifies on,
because a calculated margin is not evidence about a particular bondline.

## 3. The governing risk is a kissing bond

Every joint here carries hundreds of times its actual load. Strength is not
what threatens them.

A **kissing bond** is two surfaces in full intimate contact with no adhesion
across them. It has near-zero strength. It looks perfect. And it returns a
clean ultrasonic inspection, because ultrasound detects a *gap* and there
isn't one — the surfaces are touching. No amount of overlap protects against
it, and no inspection method available to this programme finds it reliably.

What protects against it:

1. surface preparation, controlled and verified;
2. bondline thickness, controlled by scrim or beads rather than by hand;
3. a proof test on every article.

## 4. Surface preparation

| method | durability | repeatability | contamination risk |
| --- | --- | --- | --- |
| peel ply, removed immediately before bonding | 0.85 | 0.90 | **high** if the ply carries release agent |
| abrasion and solvent wipe | 0.90 | 0.60 | moderate; operator-dependent |
| atmospheric plasma | 1.00 | 0.95 | low |

**Peel ply must be qualified as a bonding surface, not assumed to be one.**
A peel ply treated with release agent so it peels easily transfers that
agent to the surface it just exposed. This is the single most common cause
of bonding failures in composite shops, and it is invisible: the surface
looks textured and clean and is chemically contaminated.

Water-break test before bonding: a properly prepared surface holds a
continuous water film. A film that beads is contaminated. It is crude, it is
free, and it is the only in-process check this programme currently has.

Plasma treatment is the upgrade path if bond yield becomes the constraint,
because it is the only method whose result is measurable in process.

## 5. Process requirements

1. **Bond within the surface-preparation window.** Prepared surfaces
   re-contaminate from the air. Prepare and bond in the same shift.
2. **Control the bondline.** Film adhesive carries a scrim; paste adhesive
   requires glass beads. Without one of the two, an operator's clamping
   force sets the bondline, and it will be different on every joint.
3. **Record the bondline.** Measured stack-up before and after, on the
   traveler. It is the only evidence of what was built.
4. **No single-lap joints on critical structure.** A single lap's load path
   is eccentric, so it bends and peels — and the shear-lag model here does
   not predict peel, which makes its results non-conservative for that
   configuration. The answer is a better joint, not a better model.
5. **Proof test every article** whose joint qualifies by route 2, and every
   critical joint. Proof factors: 1.2 × limit for BJ-100 and BJ-200, 1.5 ×
   limit for BJ-300 on the retention path.

## 6. Basis and limitations

Adhesive properties are **handbook-representative for the adhesive class**,
not measured.

Writing this specification exposed a gap in the [coupon plan](allowables.md):
it had no bonded-joint coupon at all. Every coupon in it characterised a
laminate, and a bond is not a laminate — CP-08's mode I interlaminar
toughness was the closest thing, and it measures the adherend. Two coupons
now close it:

* **CP-09, lap shear (ASTM D5868)** — twelve specimens, not six, because
  surface preparation is a *factor* in this test rather than a fixed
  condition: half peel-ply, half abraded. The question worth answering is
  not how strong the adhesive is, it is how strong it is on a surface this
  shop prepared.
* **CP-10, floating roller peel (ASTM D3167)** — peel is what actually fails
  composite bonded joints, and the shear-lag model used to size them does
  not predict it.

Volkersen's model assumes the adhesive carries shear only and the adherends
do not bend. It is used here for double-lap configurations where the
eccentricity is designed out. For a single lap it is non-conservative, and
the specification forbids single laps on critical structure rather than
relying on a model that does not describe them.
