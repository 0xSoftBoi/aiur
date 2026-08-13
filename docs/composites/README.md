# Composite structures

Status: discipline definition, opened 2026-08-12
Scope: the composite content of the CARRIER-P0 recovery dock and its
deployable capture ring
Executable source: [`aiur/composites/`](../../aiur/composites/) —
`python -m aiur.composites`

The P0 dock has a 180 g mass allocation, a capture envelope of ±90 mm, and a
deployable ring that has to stow against the keel and spring back to shape.
Those three sentences put a composites discipline in the middle of the
programme: nothing else gets a structure that light, that precise, and that
foldable.

This directory is that discipline. It follows the same rule as the rest of
the repository — every claimed capability resolves to a measured
requirement, an executable model, a cited specification, or an explicitly
labeled engineering target — and it is honest about which of those it is
standing on today, which is mostly the last two.

## The one-line status

**The programme holds no measured allowables.** Every laminate here is sized
against handbook-representative lamina values, so every schedule is a
*design study*, not a design. [`allowables.py`](../../aiur/composites/allowables.py)
says so in its own output, the coupon plan that converts it is written down,
and the [experiment plan](doe-plan.md) is sequenced so the assumption
blocking the most work is settled first.

## What the analysis changed

Six results came out of building the models, and every one of them changed
the design or the specification rather than confirming it.

**The funnel stopped being a laminate.** Sized honestly against a handling
load across the boom pitch, a monolithic funnel skin needs 789 g/m², which
is 54 g over the funnel area — a third of the entire dock allocation, spent
on a part whose only job is to guide an aircraft. The funnel became a
tensioned membrane between the deployable booms and the laminate content
retreated to the throat cup, where the spans are short and the precision
requirement is real. [The numbers are here](laminate-design.md#the-funnel-trade).

**Cooldown chose the keel rail's material.** The first rail — high-modulus
tape at 0/90 — was predicted to microcrack on the tool at a strength ratio
of 0.56, from residual stress alone, before it ever saw a load. The fix was
not a thicker part. It was intermediate-modulus tape with fabric carrying
the transverse direction, which closes at 1.41 and costs 20 g. The lighter
high-modulus rail stays available if the programme ever qualifies a second,
lower-temperature resin system, and that is recorded as a deferred
opportunity rather than quietly dropped.

**A cone will not hold a fibre angle.** The throat cup's flat pattern spans
255° of sector, and a straight fibre's angle to the local meridian drifts one
degree for every degree of that. Holding ±3° would need 43 gores. So the cup
is built in-plane isotropic instead: its predecessor stack varied 47 % in
axial stiffness around its own circumference, and the stack that shipped
varies 7 %. [The numbers are here](laminate-design.md#the-cone-will-not-hold-a-fibre-angle).

**A bonded joint cannot always be designed to fail its adherend.** The
standard rule for an unverifiable bond is to out-strength what it joins, so
an overload fails the laminate instead of the bondline. It is achievable for
a thin adherend and arithmetically impossible for a thick one — the keeper
tine would need a 4.8 mm bondline. Written unconditionally it would have
left two of three joints permanently non-compliant, so there are two
qualification routes and the second one — load margin plus a proof test on
every article — is always available.
[PS-400](ps-400-bonding.md) carries it.

**A shallow delamination is worse than a deep one.** The plies above a
delamination buckle as a small plate, so the critical size follows from the
sublaminate's own bending stiffness — and one thin ply has almost none. A
4 mm delamination under the throat cup's outer ply needs repair; the same
4 mm delamination at mid-thickness is acceptable. The dangerous case is the
one hardest to detect, so acceptance limits are depth-dependent and an
inspection record without a depth cannot be dispositioned.
[The numbers are here](defect-disposition.md).

**Full cure is not reachable at the cure temperature.** The resin's
diffusion-limited kinetics impose a conversion ceiling that rises with hold
temperature: about 0.86 at 180 °C, no matter how long the hold. Reaching
0.90 needs roughly 199 °C — a freestanding postcure. So the cure acceptance
criteria are not "degree of cure ≥ 0.90"; they are cure *completeness*
against the achievable ceiling, which catches a hold that is too short, plus
glass-transition margin over service temperature, which catches a hold that
is too cold.

## The parts

| id | part | stack | thickness | mass | what sizes it |
| --- | --- | --- | --- | --- | --- |
| CS-100 | capture throat cup | `[45/45/0]s` glass-faced thin ply | 0.414 mm | 7.8 g | handling load, and the fibre drift a cone imposes |
| CS-200 | deployable capture-ring boom | `[45]s` thin-ply fabric | 0.160 mm | 26.2 g (×12) | stowed strain at 16 mm radius |
| CS-300 | keel rail web | `[45/0/0/0]s` tape and fabric | 1.356 mm | 42.3 g | axial stiffness, then cooldown |
| CS-400 | keeper tine | `[45/0/0/45]s` fabric | 1.592 mm | 5.9 g (×2) | retention-ledge geometry, not load |

Masses roll up against the P0 mass budget lines they charge to, and the
rollup is checked in CI: a laminate that grows cannot quietly exceed the
dock's 180 g allocation, because the areal-mass limit *is* the allocation
divided by the part's area.

## Documents

| document | what it is |
| --- | --- |
| [Laminate design](laminate-design.md) | the schedules, the load cases, the design rules, and the trades |
| [PS-100 layup process specification](ps-100-layup.md) | material control, kitting, layup, debulk, bagging |
| [PS-200 cure process specification](ps-200-cure.md) | qualified cycles, the pressure window, thermocouple placement |
| [PS-300 inspection specification](ps-300-inspection.md) | acceptance limits, methods, and what each one is protecting |
| [PS-400 bonding specification](ps-400-bonding.md) | joint sizing, the two qualification routes, and the kissing bond |
| [Tooling](tooling.md) | tool material trade, compensation, and the spring-in loop |
| [Experiment plan](doe-plan.md) | the four designed experiments that replace this package's targets |
| [Defect disposition and repair](defect-disposition.md) | what a defect costs, and accept / repair / scrap |
| [Allowables and the coupon plan](allowables.md) | what a basis value costs and why scatter is the driver |

The programme's site publishes a
[structures page](https://github.com/0xSoftBoi/aiur/blob/main/web/app/structures/page.tsx)
built from these models: every figure on it is exported by
`tools/export_composites_web.py`, and a test fails if the published data has
drifted from what the models now produce.

Shop-floor templates live in
[`hardware/composites/`](../../hardware/composites/), the generated
1:1 ply book — flat patterns and layup sequences — in
[`hardware/composites/plybook/`](../../hardware/composites/plybook/), and the
machine-shop tooling package — solid models, A3 sheets and an RFQ for the
four aluminium moulds — in
[`hardware/composites/tooling/`](../../hardware/composites/tooling/).

## Executable entry points

```
python -m aiur.composites               # the whole discipline, as one gate
python -m aiur.composites.schedules     # laminate schedules and their checks
python -m aiur.composites.flatpattern   # flat patterns, fibre drift, nesting
python -m aiur.composites.cure          # cure cycles against acceptance criteria
python -m aiur.composites.bonding       # bonded joints and their qualification routes
python -m aiur.composites.springin      # spring-in and tool compensation
python -m aiur.composites.tooling       # tool material trade
python -m aiur.composites.process       # constituent content and debulk model
python -m aiur.composites.disposition   # defect disposition and repair sizing
python -m aiur.composites.traveler      # traveler definition and evaluation
python -m aiur.composites.allowables    # basis values and the coupon plan
python -m aiur.composites.spc           # capability, control charts, yield
python -m aiur.composites.doe           # experiment plan and run sheets
```

The gate returns non-zero when the record and the arithmetic disagree — a
design rule broken without a waiver, a waiver that outlived its rule break,
a qualified cure cycle failing its own criteria — or when a critical
structural check fails. Advisory failures are recorded as findings and stay
green, because a programme that cannot carry a written-down shortfall ends
up hiding it instead.

## What this is not

There is no finite-element model here. Every part in the set is a thin skin
whose behaviour classical laminate theory describes correctly, and a
plate-theory model that runs in CI in under a second is worth more to this
programme than a mesh that runs once. Where the idealisation runs out —
interlaminar stress at a ply drop, the free edge of a trimmed boom, the
bonded joint at the throat flange — the answer is a coupon, and the
[experiment plan](doe-plan.md) names which one.
