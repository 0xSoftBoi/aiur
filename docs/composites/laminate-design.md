# Laminate design

Status: design study, opened 2026-08-12
Scope: the four composite parts of the CARRIER-P0 dock and capture ring
Executable source: [`aiur/composites/schedules.py`](../../aiur/composites/schedules.py),
[`aiur/composites/clt.py`](../../aiur/composites/clt.py) —
`python -m aiur.composites.schedules`

## What sizes these parts, and what does not

The obvious sizing case for a recovery dock is the capture event. It is not
the sizing case for anything here, and it is worth being precise about how
far it is from being one.

A 48 g aircraft closes at 0.20 m/s and is arrested over roughly 5 mm. That
is 4 m/s² — less than half a g — and about 0.2 N of contact force. The
retention path, sized at a 6 g limit load factor on the same aircraft,
carries 2.8 N. The keeper tine's strength ratio against its own retention
case is 106: it could carry a hundred times its design load.

That number is a statement about how small the load is, not about how good
the design is, and reporting it as a margin would be misleading. What
actually sizes these parts is:

| part | governing case | why |
| --- | --- | --- |
| CS-100 throat cup | handling load | a 0.33 mm skin is destroyed by a thumb before it is troubled by an aircraft |
| CS-200 boom | stowed strain | the laminate spends its life rolled to 16 mm radius |
| CS-300 keel rail | axial stiffness, then cooldown residual stress | deflection sets the ply count; residual stress rejected the first material |
| CS-400 keeper tine | retention-ledge geometry | thickness comes from the [capture-chain tolerance stack](../../aiur/tolerance.py), not from load |

The load-case report marks each case `sizing` or not, so attention stays on
the two or three that drive the design.

## The handling load, and why it became a support pitch

The first version of this analysis carried a 50 N handling load over a 25 mm
footprint on a 100 mm unsupported span. Nothing survived it. A 0.33 mm
laminate reaches about 2 % surface strain under that load — roughly twice
any allowable in the material set — and thickening the skin until it passes
costs more mass than the entire dock structural allocation.

That is the correct answer to the wrong question. A part this light is not
handled bare; it is handled in a fixture. So two things changed:

1. the load case became a defensible **inadvertent-contact** load, 15 N over
   a 25 mm footprint, explicitly labeled as an engineering target;
2. the **support pitch became a design output**. Instead of asking whether a
   skin passes, the model solves for the largest span that carries the
   handling load with a factor of 1.5, and the part's designed support pitch
   has to fit inside it.

The handling fixture is now a requirement in [PS-100](ps-100-layup.md)
rather than an assumption hidden inside a load case.

One modelling detail moved this answer by a factor of two and is worth
stating. A narrow strip with free edges curls anticlastically under bending,
which releases the transverse curvature and halves the effective bending
stiffness. A skin panel that is long between line supports cannot do that —
the surrounding material prevents it. Each schedule therefore declares its
edge condition, and a schedule that claims the stiffer `cylindrical`
condition must carry a written rationale, checked in CI.

## The funnel trade

The capture funnel was originally a composite skin. Sizing it honestly
against the handling load at the deployable boom pitch gives:

| option | stack | thickness | areal mass | max span | mass over the 0.068 m² funnel |
| --- | --- | --- | --- | --- | --- |
| A | `[G/45/0/45/G]` thin ply | 0.334 mm | 540 g/m² | 30.5 mm | 36.7 g |
| B | `[G/45/0/45/0/45/G]` thin ply | 0.494 mm | 789 g/m² | 81.6 mm | 53.6 g |

With twelve booms on a 260 mm rim the pitch is about 68 mm, so option A
needs supports at less than half the available spacing and option B costs
54 g — a third of the whole 180 g dock allocation, spent on a part whose
only function is to guide an aircraft into a cup.

**Decision: the funnel is a tensioned membrane between the deployable
booms.** It is lighter by an order of magnitude, it is more tolerant of a
scuffing airframe than a thin brittle skin, and its compliance absorbs
capture energy rather than reflecting it. The composite content retreats to
the throat cup, where spans are short and the moulded surface genuinely
feeds the tolerance stack.

Deciding that a part should not be composite is part of owning the composite
structures.

## The keel rail and residual stress

Cooldown from a 180 °C cure is a 155 K temperature drop, and post-gel cure
shrinkage adds to it. In a laminate with a large CTE mismatch between
adjacent orientations, that is enough to crack transverse plies on the tool,
before any external load.

The first keel rail was high-modulus tape at 0/90 — the obvious choice for a
stiffness-driven part, and 20 g lighter than what shipped:

| candidate | Ex | areal mass | cooldown strength ratio |
| --- | --- | --- | --- |
| `[45w/0/90/0]s` high-modulus tape, 180 °C cure | 164 GPa | 1137 g/m² | **0.56** — microcracks on the tool |
| same laminate, 120 °C cure | 164 GPa | 1137 g/m² | 0.75 — still cracks |
| `[45w/0HM/w0/0HM]s` fabric transverse, 120 °C cure | 180 GPa | 1089 g/m² | 1.21 — passes, needs a second resin system |
| `[45w/0/w0/0]s` intermediate-modulus, 180 °C cure | 92.6 GPa | 2113 g/m² | **1.41** — selected |

The selected rail is the heaviest of the four. It wins because the three
lighter options all require either accepting predicted microcracking or
qualifying a second resin system, and a second resin system means a second
freezer, a second out-time log, a second cure spec and — the real cost — a
second allowables campaign. For a programme that holds zero measured
allowables today, doubling the qualification cost to save 20 g is the wrong
trade.

This is recorded as a **deferred opportunity**, not a closed question. If
the programme ever qualifies the 120 °C system for another reason, the
high-modulus rail is 20 g of free mass.

Two secondary choices in that stack are deliberate and easy to misread as
padding. Fabric plies sit on both faces and at the mid-plane for handling,
drilled-hole bearing and transverse residual stress — bare unidirectional
tape splits along the fibre at a fastener and frays at a trimmed edge. And
because a woven ply carries half its fibre crosswise, it *breaks* a
same-orientation run for the purposes of the contiguous-ply rule, which is
why the rail can carry four tape plies at 0° without violating it.

## Design rules

Enforced in CI, not suggested:

| rule | limit | what it prevents |
| --- | --- | --- |
| symmetric | required, **never waivable** | an unsymmetric laminate warps off the tool |
| balanced | required | an unbalanced laminate shears when pulled and twists on cooldown |
| 10 % rule | every one of the 0 / 90 / 45 families ≥ 10 % of thickness | a direction carried by resin alone |
| contiguous plies | ≤ 4 same-orientation unidirectional plies | transverse cracks linking into a delamination |
| surface ply off-axis | outer plies at 45° | surface-parallel splitting where handling damage starts |

A schedule that breaks a rule must carry a written **waiver**. The validator
checks both directions: a rule broken without a waiver fails, and a waiver
that outlived the rule break it was written for also fails, so paperwork
cannot drift away from the design in either direction. The
[capture-chain tolerance stack](../../aiur/tolerance.py) uses the same
two-way check for the same reason.

One waiver is live. **CS-200's boom breaks the 10 % rule**, carrying no 0°
or 90° fibre at all, and the rationale is that a tape spring is deliberately
shear-dominated: ±45 fabric is what lets the section flatten elastically and
snap back, and adding a 0/90 ply to satisfy the rule would raise the
longitudinal stiffness that resists flattening and push the stowed strain
past allowable.

## The deployable, and why thin ply is not a preference

Stowage reduces to one line: a laminate rolled to radius `R` sees a surface
strain of `t / 2R`. The boom stows at 16 mm, so at 0.16 mm thickness it sits
at 0.50 % strain against an allowable of 0.64 % — the material's 1.28 %
ultimate with a factor of two for the creep and stress relaxation of sitting
stowed between packing and deployment.

At 0.20 mm ply thickness the same two-ply laminate cannot reach that radius
without exceeding its allowable. Thin ply is the enabling choice, not an
optimisation. And high-modulus fibre, whose strain allowable is less than
half the woven material's, is the right choice for the keel rail and the
wrong choice for anything that gets rolled — the same property that makes it
stiff makes it brittle.

## Mass rollup

Areal-mass limits are not chosen; they are the mass allocated to a part from
a named P0 mass budget line, divided by that part's area. A laminate that
grows cannot quietly exceed the dock's allocation.

| budget line | budget | allocated | actual |
| --- | --- | --- | --- |
| active recovery dock allocation | 180.0 g | 44.5 g | 38.6 g |
| wiring + mounting reserve | 100.0 g | 45.0 g | 42.3 g |

## Where the model runs out

Classical laminate theory is a thin-plate theory. It has no interlaminar
stress, no free-edge effect and no through-thickness strength, and it does
not know that a thin ply's in-situ transverse strength is higher than a
thick one's — which means the cooldown check above is *conservative* for the
thin-ply parts by an amount this model cannot quantify.

Where that matters — the bonded throat flange, the trimmed boom edge, the
tine root — the answer is a coupon, and [the experiment plan](doe-plan.md)
names which one.
