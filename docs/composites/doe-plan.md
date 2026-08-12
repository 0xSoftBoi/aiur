# Experiment plan

Status: plan, opened 2026-08-12
Scope: the designed experiments that convert this package's engineering
targets into measurements
Executable source: [`aiur/composites/doe.py`](../../aiur/composites/doe.py) —
`python -m aiur.composites.doe`

Every model in the composites package leans on at least one number that is
an engineering target rather than a measurement, and each of those targets
is named where it is used. This is the plan that converts them: four
experiments, 54 runs, ordered so the assumption blocking the most work is
settled first.

Each experiment names **the specific assumption in the code that it
replaces**. `validate_experiments` rejects one that does not, because an
experiment with no consumer is a hobby.

## Why factorials

A shop faced with a porosity problem naturally changes one thing at a time —
more debulks this week, higher vacuum next. One-factor-at-a-time has two
defects that matter here.

It cannot see interactions, and porosity is *made of* interactions: the
effect of pressure timing depends entirely on how much air the debulks left
behind. And it is inefficient — a factorial estimates every main effect
using every run, so a sixteen-run factorial resolves three factors and their
interactions more precisely than forty-eight runs of one-at-a-time.

Two disciplines separate a designed experiment from a batch of parts.

**Randomised run order.** Tool wear, ambient humidity, operator learning and
the ageing of a prepreg roll all drift over the days a campaign takes. Run
the low settings on Monday and the high settings on Friday and the
experiment measures the week. The order here is generated from a recorded
seed, so it is reproducible and cannot be quietly "improved" on the floor.

**Stated power.** An experiment that cannot resolve an effect worth acting
on is worth neither the material nor the oven time. Every experiment carries
its minimum detectable effect.

## DOE-1 — cure kinetics and thermal survey

> What are this lot's cure kinetics, and how far does a part on its tool lag
> the oven?

**Replaces:** the handbook kinetic, DiBenedetto and viscosity constants in
`materials.py`, and the assumed oven film coefficient in `cure.py`.

| factor | low | high |
| --- | --- | --- |
| heating rate | 1 °C/min | 5 °C/min |
| tool thermal mass | bare panel | 6 mm aluminium tool |

Responses: degree of cure (DSC residual exotherm), glass transition (DSC or
DMA), part-to-air lag (instrumented panel, part thermocouples), minimum
viscosity and gel time (rheometer).

8 runs. Minimum detectable effect 0.028 in degree of cure.

This runs first because everything else is downstream of it. Until it does,
every cure cycle in the package is a starting point for a trial rather than
a qualified process, and the conversion-ceiling finding that set the cure
acceptance criteria rests on published constants for the resin *class*.

## DOE-2 — what controls porosity

> What actually controls porosity in this cell?

**Replaces:** the debulk model constants in `process.py`, and the assumption
that the computed pressure window is the right one.

| factor | low | high |
| --- | --- | --- |
| debulk cycles | 1 | 3 |
| pressure application | at 60 °C | at the computed flow window |
| vacuum level | −70 kPa | −95 kPa |

Responses: void fraction (D2734), cured ply thickness, short-beam strength
(D2344).

18 runs including 2 centre points, blocked one panel set per day to absorb
ambient humidity. Minimum detectable effect 0.0037 in void fraction —
against a 0.02 acceptance limit, so it can resolve a fifth of the limit.

**The interaction between debulk count and pressure timing is the result
this experiment exists for.** If pressure timing only matters when the stack
is under-debulked, the cheap fix is debulks, and the traveler's hardest
instruction can be relaxed. A one-factor-at-a-time campaign cannot answer
that question at any run count.

Short-beam strength is included so a void fraction can be converted into a
strength consequence. Without it the void limit stays an industry convention
this programme has adopted rather than a limit it has derived.

## DOE-3 — distortion

> How much does a moulded corner move, and what moves it?

**Replaces:** the zero tool-interaction allowance in `springin.py` and the
assumed post-gel shrinkage fraction in `schedules.py`.

| factor | low | high |
| --- | --- | --- |
| cure temperature | 120 °C | 180 °C |
| tool material | aluminium | carbon tooling laminate |
| release system | semi-permanent | film |

Responses: moulded angle deviation (CMM against the compensated nominal),
flat-panel warp (surface plate and feeler).

16 runs. Minimum detectable effect 0.078° against a 0.25° tolerance.

The temperature factor is what separates the thermal component of spring-in
from the chemical one — no single-temperature experiment can do that, and
the two components respond to completely different fixes.

The two responses are separated deliberately. Radford's model predicts
corner angle and says nothing about warp in a flat panel, so **warp is the
clean measurement of the tool-interaction term** that the model currently
carries as zero.

## DOE-4 — ply placement repeatability

> How repeatable is ply placement, and does it matter?

**Replaces:** the assumption implicit in every laminate schedule that a ply
laid at 45° is at 45°.

| factor | low | high |
| --- | --- | --- |
| cutting method | hand shears to a marked pattern | template |
| operator | operator A | operator B |

Responses: fibre orientation error (photographed ply against a reference
grid), tensile modulus (D3039).

12 runs. Minimum detectable effect 0.91° in orientation.

A two-degree mean orientation error is worth about one percent of modulus
and is not the point. **The point is the spread.** Scatter drives coupon
count, coupon count is what a qualification campaign costs, and
operator-to-operator variation is a real component of scatter that is almost
never measured.

## Reading the results

`main_effects` and `interaction_effect` reduce a coded design and a response
vector to effects directly. An interaction that rivals a main effect means
the two factors cannot be set independently — which is the finding, not a
complication.

Centre points in DOE-2 detect curvature. A factorial alone assumes the
response is planar between its levels, and porosity against vacuum level is
one of the places that assumption is least safe.

`assumed_sigma` on each experiment is itself an engineering target. The
first replicate set measures the real run-to-run variation, and the plan is
re-sized against it before the campaign continues.
