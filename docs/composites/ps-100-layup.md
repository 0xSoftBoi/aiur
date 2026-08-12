# PS-100 — Layup process specification

Status: process specification, issue A, opened 2026-08-12
Scope: material control, kitting, layup, debulk and bagging for all
CARRIER-P0 composite parts
Executable source: [`aiur/composites/process.py`](../../aiur/composites/process.py),
[`aiur/composites/traveler.py`](../../aiur/composites/traveler.py)

This specification is written to be followed by a technician and checked by
a program. The traveler in `aiur.composites.traveler` is the executable form
of it: a completed traveler record is *evaluated* against these rules, and a
missing signature, an out-of-sequence step or an expired material becomes a
computed nonconformance rather than something a reviewer might notice.

## 1. Material control

### 1.1 Storage and out-time

Prepreg is stored sealed at −18 °C. Room-temperature exposure advances the
resin, slowly but irreversibly, and **the clock does not reset when the roll
goes back in the freezer**.

| control | limit | basis |
| --- | --- | --- |
| cumulative out-time, structural use | 240 h | engineering target standing in for a supplier limit |
| cumulative out-time, restriction point | 200 h | above this, non-structural use only |
| minimum thaw before opening the bag | 8 h | condensation control |

Out-time is logged cumulatively per roll on every issue and return. It is
the single most commonly falsified number in composites manufacturing,
precisely because it is inconvenient, and the consequence of exceeding it is
invisible: the resin no longer flows to specification, the part comes out
porous and resin-starved, the cure looks normal, and nothing in the finished
part records why.

### 1.2 Thaw

A sealed roll is thawed to room temperature **before** the bag is opened.
Opening a cold roll condenses atmospheric water onto the prepreg, and that
water becomes steam-driven porosity at cure — a defect whose cause is
invisible in the finished part and unarguable in the traveler.

### 1.3 Traceability

Lot and roll are recorded on the traveler at issue. A part with no recorded
lot cannot be tied to any allowable and is not traceable; the traveler
evaluator treats a missing lot as a critical nonconformance.

## 2. Tool preparation

1. Clean the moulding surface and inspect it against the criteria in
   [PS-300](ps-300-inspection.md). A moulded face is a cast of the tool and
   reproduces every scratch in it.
2. Apply the release system per the tool log, and record cures since the
   last full strip.
3. **Verify the tool drawing's scale factor is the one in use.** Tools in
   this programme are cut away from nominal to compensate for thermal
   expansion and spring-in — an aluminium tool for a 300 mm part is cut
   0.97 mm larger than the part drawing. A machinist who works to the part
   drawing by mistake produces a tool wrong by six times the tolerance. See
   [tooling](tooling.md).

## 3. Kitting

Plies are cut to the flat patterns with the fibre direction indexed to the
pattern's zero mark, and kitted in lay-down order with the top ply last.

Ply orientation error is currently uncontrolled and unmeasured. DOE-4 in the
[experiment plan](doe-plan.md) measures whether a template earns its cost,
and the response that matters is not the mean orientation error — a two
degree mean error is worth about one percent of modulus — but the *spread*,
because scatter is what drives coupon count and coupon count is what a
qualification campaign costs.

## 4. Layup

Lay up to the part's laminate schedule, which is authoritative and
machine-readable:

```
python -m aiur.composites.schedules
```

Plies are listed **top surface first** — the order they are laid into a
female tool and the order the traveler is signed in.

### 4.1 Debulk schedule

Debulk under full vacuum after the first ply and every three plies
thereafter, and once more before bagging for cure. For an eight-ply part
that is after plies 1, 3, 6 and 8.

The debulk after the *first* ply is not tradition. The first ply against the
tool decides the moulded surface, and an unbagged first ply bridges every
radius in the tool.

Predicted entrapped air, from the model in `process.py`:

| debulks | entrapped air |
| --- | --- |
| 0 | 5.5 % |
| 1 | 2.7 % |
| 2 | 1.4 % |
| 3 | 0.9 % |
| 4 | 0.6 % |

Two debulks meet the 2 % general void limit and three meet the 1 % critical
limit. The shape of that table matters more than its constants: the first
debulk does most of the work, the third does little, and **no number of
debulks reaches zero**. Room-temperature debulking cannot remove the last
of it, because that needs the resin to be mobile — which is what the flow
dwell in the [cure cycle](ps-200-cure.md) is for. "Debulk more" is not the
answer to a porosity problem.

These constants are engineering targets. DOE-2 replaces them.

### 4.2 Handling

Parts in this programme are sized against a 15 N inadvertent-contact load,
not a grab or step load, and that is only defensible because they are not
handled bare.

**A handling fixture is required** for every part from demould through
inspection. This is a design requirement flowing directly out of the
laminate sizing, not a shop preference: the alternative, sizing the skins to
survive bare handling, costs more mass than the entire dock structural
allocation.

Support pitch limits from the sizing analysis:

| part | designed support pitch | capacity at 15 N |
| --- | --- | --- |
| CS-100 throat cup | 25 mm | 30.5 mm |
| CS-300 keel rail | 120 mm | 852 mm |
| CS-400 keeper tine | 25 mm | 886 mm |

## 5. Layup verification — HOLD POINT

**A second person verifies ply count, orientation of every ply against the
schedule, and the absence of foreign object debris, before the bag goes on.**

This hold exists because the next step destroys the evidence. Once the part
is bagged and cured, ply count and orientation are unverifiable for the life
of the part: no cured-part inspection method distinguishes a ply laid at 0°
from one laid at 45°. Ultrasonic inspection finds porosity and
delamination; it does not read fibre angles.

The verifier may not be the person who performed the layup. The traveler
evaluator rejects a self-signed hold point.

## 6. Bagging and leak check — HOLD POINT

Bag with the specified bleeder and breather stack, pull full vacuum, and
verify the leak rate against the limit before the oven is loaded.

A bag that leaks during cure produces a porous part, and the leak cannot be
detected afterwards. The check is worthless once the cure has started, which
is exactly what makes it a hold point rather than a step.

## 7. Records

Every step records something. A step that records nothing cannot contribute
to a yield investigation later, and the traveler definition check rejects
one that tries.

Minimum records per step are defined in `aiur.composites.traveler` and
printed by:

```
python -m aiur.composites.traveler
```
