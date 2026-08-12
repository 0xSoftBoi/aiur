# Allowables and the coupon plan

Status: plan, opened 2026-08-12
Scope: what a structural allowable costs this programme, and the coupon
campaign that produces one
Executable source: [`aiur/composites/allowables.py`](../../aiur/composites/allowables.py) —
`python -m aiur.composites.allowables`

## The one-line status

**This programme holds no measured allowables.** Every laminate is sized
against handbook-representative lamina values, so every schedule in
[`schedules.py`](../../aiur/composites/schedules.py) is a design study rather
than a design. The package reports this in its own output rather than
leaving a reader to infer it from four significant figures.

## Typical is not allowable

A lamina strength from a handbook is a *typical* value — the middle of a
distribution whose width nobody has told you. Designing to it means half of
all coupons would fail below the design load.

A structural allowable is a statistical lower bound on that distribution,
from this programme's own coupons, at a stated confidence and population
fraction:

| basis | meaning | used for |
| --- | --- | --- |
| **B** | 90 % of the population exceeds it, at 95 % confidence | redundant structure — almost everything |
| **A** | 99 % of the population exceeds it, at 95 % confidence | single-load-path structure whose failure is catastrophic |

In this programme only the keeper tine's retention path is an A-basis
candidate, because it is the only part whose failure drops a captured
aircraft.

## Scatter is the whole cost

The point of this analysis is not the arithmetic. It is that the price of an
allowable is set by the shop, not by the material.

Coupons needed to keep a basis value within 20 % of the mean:

| coefficient of variation | B-basis | A-basis |
| --- | --- | --- |
| 4 % | 4 | 7 |
| 6 % | 6 | 19 |
| 8 % | 9 | >200 |
| 10 % | 17 | >200 |
| 12 % | 45 | >200 |

Between 4 % and 12 % scatter, the B-basis coupon count goes up elevenfold.
A-basis becomes unreachable at any realistic budget above about 6 %.

Scatter is not a property of the material. It is a property of the process:
every void, every out-time excursion and every hand-cut ply widens the
distribution that the allowable is then computed from the bottom of. **This
table is the real argument for the controls in
[PS-100](ps-100-layup.md) and [PS-300](ps-300-inspection.md)** — process
discipline is not paperwork, it is the difference between a nine-coupon
qualification and a forty-five-coupon one.

It is also why DOE-4 measures operator-to-operator variation in ply
placement. Scatter that comes from the shop can be removed from the shop.

## What qualifies as a basis value

| requirement | value | why |
| --- | --- | --- |
| specimens | ≥ 6 | below this the tolerance factor dominates the answer |
| **lots** | ≥ 3 | a value from a single lot describes that lot, not the material |
| coefficient of variation | ≤ 10 % | above this the scatter is process-driven; fix the process, do not lower the allowable |

The lot requirement is the one most often skipped and the one that matters
most. Lot-to-lot variation is a real and substantial part of the
distribution a design is supposed to be protected against, and a beautifully
reduced dataset from a single roll of prepreg silently excludes it.

`evaluate_coupon_set` warns on all three, and refuses to call a value a
basis value when specimens or lots fall short, whatever the arithmetic says.

## The coupon plan

| id | method | property | material | environment | n |
| --- | --- | --- | --- | --- | --- |
| CP-01 | ASTM D3039 | tension 0° | PW-C-193 | RTD | 6 |
| CP-02 | ASTM D6641 | compression 0° | PW-C-193 | RTD | 6 |
| CP-03 | ASTM D3518 | in-plane shear | PW-C-193 | RTD | 6 |
| CP-04 | ASTM D2344 | short-beam strength | PW-C-193 | RTD | 10 |
| CP-05 | ASTM D3039 | tension 0° | PW-C-80 | RTD | 6 |
| CP-06 | ASTM D7137 | compression after impact | PW-C-193 | RTD | 6 |
| CP-07 | ASTM D2344 | short-beam strength | PW-C-193 | ETW | 6 |
| CP-08 | ASTM D5528 | mode I interlaminar toughness | PW-C-193 | RTD | 6 |
| CP-09 | ASTM D5868 | adhesive lap shear | PW-C-193 | RTD | 12 |
| CP-10 | ASTM D3167 | floating roller peel | PW-C-193 | RTD | 6 |

70 specimens. Notes on the ones that are not obvious:

**CP-03, in-plane shear.** The critical failure mode in every 45° skin in
this programme is shear in the surface ply — it is what the throat cup's
handling case fails on. A shear allowable is not optional here.

**CP-04, short-beam strength.** Interlaminar strength is the property
porosity attacks. This is the coupon that makes the void limit mean
something; ten specimens rather than six because DOE-2 needs it as a
response across a range of void contents.

**CP-05, thin ply.** The thin-ply material's in-situ transverse strength is
expected to exceed the thick-ply value, and the laminate model does not
predict that — it treats strength as thickness-independent. This coupon
measures how conservative the cooldown residual-stress check is on the
thin-ply parts.

**CP-07, hot/wet short beam.** The assumed 0.65 matrix-dominated hot/wet
knockdown is the least defensible number in the package, and it is applied
to the property that porosity already attacks.

**CP-09 and CP-10, the bonded joint.** These were added after
[PS-400](ps-400-bonding.md) was written, because writing it exposed that the
plan had no bonded-joint coupon at all — every other coupon here
characterises a laminate, and a bond is not a laminate. CP-09 carries twelve
specimens because surface preparation is a factor in it rather than a fixed
condition: half peel-ply, half abraded. The coupon that matters is not "how
strong is this adhesive" but "how strong is it on a surface this shop
prepared".

## Environmental knockdowns

| environment | knockdown | applies to |
| --- | --- | --- |
| room temperature dry | 1.00 | reference |
| elevated temperature wet, fibre-dominated | 0.90 | tension along the fibre |
| elevated temperature wet, matrix-dominated | 0.65 | shear, compression, interlaminar |
| cold dry | 0.95 | all |
| barely visible impact damage | 0.65 | compression on thin skins |

All engineering targets, deliberately conservative, because a knockdown that
turns out to be too small is discovered by a part failing.

## A note on the statistics

The tolerance factors use the standard closed form rather than the exact
non-central t quantile. It sits about 1.5 % *below* the published exact
factors at n = 10, closing to 0.2 % by n = 100. Below is
**non-conservative** — it returns a slightly higher allowable — so the
direction is stated rather than left to be worked out. At 5 % coefficient of
variation it moves the allowable by under 0.2 %, an order of magnitude
inside the scatter of the data being reduced. If this programme ever
computes an allowable that a part depends on, it should substitute the
published table value at that sample size.

Normality is an *assumption*, not a fact. For strength data with a weak-link
failure mode a Weibull fit is often the better model. Testing the assumption
needs more specimens than this programme will have for some time; when the
data exists, an Anderson-Darling check belongs in front of the reduction.
