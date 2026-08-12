# PS-200 — Cure process specification

Status: process specification, issue A, opened 2026-08-12
Scope: cure cycles, pressure application, and cure acceptance for all
CARRIER-P0 composite parts
Executable source: [`aiur/composites/cure.py`](../../aiur/composites/cure.py) —
`python -m aiur.composites.cure`

Written down, every cure cycle looks equally plausible. Run against the
resin's kinetics they stop being equally plausible, and the four failures a
cycle can hide become visible and testable.

## 1. What a cure cycle can get wrong

**Undercure.** The part reaches the end of the recipe below the degree of
cure its service temperature needs. It looks perfect, passes a visual and an
ultrasonic inspection, and fails hot/wet.

**Vitrification.** A subtler undercure: the reaction does not run out of
time, it *stops*, because the partially cured resin's glass transition
climbs past the cure temperature and the molecules can no longer move.
Holding longer at that temperature buys nothing at all. The fix is a higher
hold, and no amount of patience substitutes for it.

**Exotherm.** The reaction is strongly exothermic. In a thick part or on a
thermally insulating tool, generated heat outruns removed heat, the part
overshoots its own oven, and the overshoot accelerates the reaction further.

**A missed pressure window.** Resin viscosity falls as the part heats, then
climbs steeply as the reaction takes hold, and gelation ends flow entirely.
Apply consolidation pressure too early and the resin bleeds out, leaving a
starved laminate; too late and trapped volatiles and interply air have
nowhere to go, leaving voids.

## 2. Qualified cycles

### CC-180-STD — 180 °C two-dwell (baseline)

| segment | target | rate | hold |
| --- | --- | --- | --- |
| flow dwell | 110 °C | 2 °C/min | 60 min |
| cure dwell | 180 °C | 2 °C/min | 120 min |
| cooldown | 60 °C | 2.5 °C/min max | — |

Vacuum: full (≤ 5 kPa absolute) for the whole cycle.
Pressure: 300 kPa applied when the **part** reaches 100 °C.
Predicted: 308 min total, degree of cure 0.83, Tg 163 °C,
service margin 103 K, thermal lag 11.3 K, exotherm 3.0 K.

The intermediate dwell is not tradition. It holds the part at the viscosity
minimum long enough for interply air to be drawn out under vacuum before the
reaction thickens the resin.

### CC-120-OVEN — 120 °C oven cure (alternative)

| segment | target | rate | hold |
| --- | --- | --- | --- |
| flow dwell | 80 °C | 1.5 °C/min | 45 min |
| cure dwell | 120 °C | 1.5 °C/min | 180 min |
| cooldown | 50 °C | 2 °C/min max | — |

Vacuum bag only, no press. Service temperature limited to **35 °C**.
Predicted: 327 min, degree of cure 0.73, Tg 70.5 °C, service margin 35.5 K.

Halving the cooldown roughly halves residual stress and spring-in, which is
why the lighter high-modulus keel rail is only viable with this system. It
is not the baseline because it limits service temperature and, more
importantly, because a second resin system means a second qualification
campaign.

## 3. Acceptance criteria

| criterion | limit | catches |
| --- | --- | --- |
| cure completeness | ≥ 0.95 of the hold temperature's ceiling | a hold that is too **short** |
| service margin | Tg − T_service ≥ 30 K | a hold that is too **cold** |
| not vitrified | required | a reaction stalled below where it needs to be |
| exotherm overshoot | ≤ 8 K above the oven set point | self-heating outrunning the oven |
| thermal lag | ≤ 15 K on the way up | hold time counted against a temperature the part never had |
| pressure window | ≥ 10 min | a window too short for a technician to hit reliably |
| pressure step | inside the flow window | early bleeds resin out, late traps voids |

### Why not "degree of cure ≥ 0.90"

Because it is unachievable, and a spec that demands the unachievable gets
ignored rather than met.

The diffusion-limited kinetics impose a **conversion ceiling** that rises
with hold temperature. At 180 °C it is about 0.80, and no hold length passes
it by a meaningful margin because the resin vitrifies there. Reaching 0.90
requires roughly **199 °C** — a freestanding postcure above the cure
temperature. At 120 °C the ceiling is 0.68, so the 120 °C system would fail
a 0.90 spec forever while making perfectly serviceable parts.

So completeness is measured against the ceiling the hold can actually reach,
and the glass-transition margin carries the question of whether that cure is
*enough*. Between them they separate the two distinct ways a cycle goes
wrong.

If service temperature ever rises above what a 180 °C cure supports, the
lever is a freestanding postcure at ~200 °C, not a longer hold.

## 4. Thermocouples

**Thermocouples go on the part, not on the oven air.** Every ramp rate and
hold time in this specification is a *part* rate and a *part* time.

This is not pedantry. With a 6 mm aluminium tool at 2 °C/min the part runs
11 K behind the oven; at 5 °C/min it runs 28 K behind. A recipe that counts
its dwell from the oven controller gives the part substantially less time at
temperature than the recipe says.

The rejected candidate cycle makes the point:

### CC-180-FAST — rejected

A single 180 °C dwell at 5 °C/min, saving 162 minutes per part. It fails on
thermal lag at 28.1 K. Its 90-minute dwell is nothing of the sort, because
the part spends much of it climbing. It is kept in the register precisely
because it is tempting, so that what it costs is measured rather than
argued about.

## 5. Pressure application

For CC-180-STD the computed flow window is **34 to 155 minutes** into the
cycle: it opens when resin viscosity falls below 100 Pa·s and closes at
gelation. Minimum viscosity, 0.83 Pa·s, occurs at 138 minutes.

The specification triggers full pressure on a part temperature of 100 °C,
which lands inside that window with margin at both ends. This is usually the
only genuinely time-critical instruction on the traveler, and it is the one
most often written as "apply pressure at 100 °C" by someone who never
computed where the window was. Here the trigger is checked against the
computed window in CI.

DOE-2 tests whether the computed window is the right one, by running
pressure application early against pressure application at the window and
measuring the void fraction that results.

## 6. Basis and limitations

The kinetic, glass-transition and viscosity constants are
**handbook-representative for the resin class**, not measured on this
programme's lot. Until DOE-1 runs its DSC and instrumented-panel campaign,
every cure cycle here is a starting point for a trial, not a qualified
process, and the word "qualified" in this document means "passes the
model's acceptance criteria", not "demonstrated on hardware".

The thermal model is **lumped** — one temperature for the part — which is
right for the 0.16–1.6 mm laminates in this programme and wrong for a thick
part, where a through-thickness gradient is the whole problem.
