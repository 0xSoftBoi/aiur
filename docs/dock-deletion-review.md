# Dock deletion review before Rev-B

Status: decision memo, opened 2026-08-08
Ticket: ADOPT-013
Scope: the Rev-A recovery dock and the Rev-B keeper-discrimination candidate
in [digital-twin.md](digital-twin.md) finding 5

## Why this review exists

The findings ratchet has only ever turned one way. Five twin findings are on
the books: three produced software requirements, one produced an accepted
residual, and the fifth — a confirmed capture on an empty throat under a
stuck seat switch plus a masked navigation bias — produced a proposal to
add a sensor. No part has ever been removed from the dock. The P0
exclusions list in hardware/dock/README.md is a list of deferred
*additions*, which is a different thing. A mechanism that only accumulates
parts accumulates failure modes at the same rate, and the P0 dock is the
article whose failure modes the entire program exists to expose.

The iterative-hardware practice surveyed in
[engineering-practice-survey.md](engineering-practice-survey.md) puts two
steps ahead of "add sensing": make the requirement less dumb, then delete
the part. The warning attached to that ordering is the relevant one here —
the most common error is optimizing something that should not exist. Rev-B
is the last cheap moment to ask the question, because Rev-A is printed
plastic and Rev-B is the revision that freezes switch brackets, wiring, and
the compliant insert.

The rule this memo applies, stated so it can be checked:

- the best part is no part; the second best is a part that already exists
  doing a second job;
- every requirement is attributed to a named person, not a document and not
  a department, so it can be argued with;
- a part survives only if deleting it breaks something that can be named,
  measured, or modeled.

## The first thing the rule catches

No requirement interrogated below resolves to a named human. Every one of
them resolves to a document that inherited it from another document. The
Ø180 mm funnel is the clearest case: it appears as a target in
[prototype-p0.md](prototype-p0.md), as `capture_radius_m = 0.090` in
`aiur/p0.py`, and as `funnel_entrance_radius_m = 0.090` in
`aiur/sim/dock_physics.py`, with no derivation anywhere in the repository.
An assumption propagated into three files with no owner is exactly the
failure mode the attribution rule exists to catch.

This memo therefore uses role placeholders in the "whose requirement"
column. Replacing them with names is a standing action on the program lead
and is a precondition for the next deletion review being worth running.

## Part-by-part interrogation

### (a) Passive spring collet / first-capture insert

**Requirement served.** "Spring collet provides passive first capture"
(p0a-bench.md, mechanical stack step 2); "spring-loaded terminal collet"
(hardware/dock/README.md); modeled as
`DockGeometry.collet_pullout_speed_m_s = 0.05` in the twin.

**Whose.** Dock mechanism owner (unnamed), inherited from the docking
architecture list in prototype-p0.md step 4.

**What fails if deleted.** Not retention: the controller disarms the
aircraft only after `capture_confirmed and seat_confirmed`
(`aiur/sim/guidance.py`), which requires the keeper already closed, so the
collet is never the sole retention path for an unpowered aircraft in the
nominal sequence. What fails is *registration*. The Ø16 mm throat leaves a
Ø12 mm head 2.0 mm of radial freedom; the keeper's 4.2 mm slot accepts only
0.6 mm of Ø3 mm mast offset. The throat alone permits a probe position the
fork cannot close on, by a factor of 3.3. Today the collet is the only part
that closes that gap.

**Evidence.** No bench evidence exists: P0-A inserts the probe by hand, so
the life-test cycling measures the insert's wear, not its function. Twin
evidence is in the study below — deleting the modeled retention changes no
capture outcome and produces no probe-withdrawal event at all in indoor
calm air. The registration problem is invisible to the twin, whose dock
model has no throat and no slot.

**Merge candidate.** Yes. Registration merges into two parts that already
exist: the funnel throat and the keeper slot.

**Disposition: MERGE** — delete the retention function, merge registration
into throat and slot geometry, conditioned on the A0 measurement in the
evidence table. Reasoning in full below.

### (b) S1 seat switch

**Requirement served.** Physical proof that a probe reached the seat;
the trigger for `OPEN -> LOCKING`; the plausibility anchor the supervisor
compares its own relative estimate against (finding 2).

**Whose.** Flight-software and safety owner (unnamed), via
hardware/dock/README.md.

**What fails if deleted.** Two things, in increasing severity. The keeper
loses its physical closing trigger, so closure would have to be commanded
off the navigation estimate — which moves the dock *toward* the single
navigation source that finding 3 and finding 5 both indict. And capture
confirmation collapses to one channel, putting the irreversible action
(disarm) behind a single switch.

**Evidence.** Finding 2 shows S1 is the weaker of the two channels: stuck
closed, it defeats `S1 AND S2` on its own. That is an argument for
distrusting S1's authority, not for deleting the sensor — the mitigation
finding 2 prescribes (compare S1 against the independent estimate) is only
possible because S1 exists to disagree with.

**Merge candidate.** No. A keeper-side sensor cannot report seat arrival
before the keeper moves.

**Disposition: KEEP**, with its requirement rewritten. S1's job becomes
*trigger and disagreement detector*; confirmation authority moves to the
keeper channel (see question 2). This is the review deleting a requirement
while keeping a part, which is the normal outcome and should be recorded as
such.

### (c) S2 keeper-closed switch

**Requirement served.** "`S2` physical keeper-closed switch independent of
the servo command" (hardware/dock/README.md). It exists because a commanded
servo position is not evidence, and because status must be sensed on the
latch element rather than the drivetrain.

**Whose.** Flight-software and safety owner (unnamed).

**What fails if deleted.** Everything: the servo command becomes the only
keeper evidence, which is the specific thing the architecture forbids.

**Evidence.** S2's current sensed fact — "the fork reached its closed
stop" — is true whether or not a mast is in the slot, because the 4.2 mm
slot clears the Ø3 mm mast on every side. That is the mechanical reason
finding 5 exists.

**Merge candidate.** Yes, in place. Change the fact S2 senses, not the
number of sensors.

**Disposition: MERGE** — replace S2 with S2′, sensing "keeper closed with a
mast in the slot". Same part count, same channel count, same switch class.

### (d) Sliding fork keeper

**Requirement served.** Positive mechanical retention: tines under the
Ø12 mm head, rigid guides and a closed end-stop reacting the 5 N axial
screening load, servo out of the structural path
(p0a-fabrication.md).

**Whose.** Dock mechanism owner (unnamed).

**What fails if deleted.** The dock becomes passive-only, retained by
friction of unknown magnitude, and — decisively — loses commanded release.
The release state machine and the ≥10 emergency-release trials in the P0-A
gate both require a mechanism that can be told to let go.

**Evidence.** It is the only retention element whose holding capability is
provable by the existing gate (5 N axial, 1 N lateral, held 10 s, pre- and
post-cycle). The collet's is not, and is not scheduled to be.

**Merge candidate.** It is the merge *target*: it absorbs the collet's
registration function via slot geometry and the discrimination function via
the detent/cam geometry discussed under question 2.

**Disposition: KEEP.** When two retention paths exist and only one is
provable, the provable one is the one that survives.

### (e) Proposed Rev-B keeper-discrimination sensor

**Requirement served.** Finding 5: one signal that no navigation fault can
spoof, distinguishing closed-on-probe from closed-on-empty-throat.

**Whose.** Twin, via digital-twin.md finding 5; owner unnamed. The practice
survey's assessment is that this should be promoted from candidate to gated
requirement.

**What fails if deleted.** The double-fault cut set (S1 stuck actuated plus
a masked navigation bias) stays open, accepted as residual for the
single-fault indoor regime.

**Evidence.** The requirement is sound. The *part* is not: it was proposed
as an addition because the review that asks whether it can be an
in-place change had not been run. It can be.

**Merge candidate.** Yes — entirely absorbed by row (c).

**Disposition: DELETE as a separate part.** Net parts added to close
finding 5: zero.

### (f) The funnel at Ø180 mm

**Requirement served.** Convert lateral position error into probe
centering, so the control system never needs millimeter coincidence in free
flight. It is also the named mechanical mitigation for finding 3, the slow
navigation bias no single-source estimator can detect.

**Whose.** Program lead (unnamed); inherited from prototype-p0.md, where it
appears as a target with no derivation.

**What fails if deleted.** The program. Deleting the funnel moves the whole
alignment problem into the estimator that finding 3 says cannot be trusted
at the millimeter scale.

**Evidence, and the uncomfortable part.** The degraded-sensor sweep captures
100% at 10× Lighthouse noise and ~63% at 30× (σ ≈ 90 mm, the funnel radius
itself), so for the indoor P0 mission the funnel is not the binding
constraint — navigation is well inside it. That is an argument for a
*smaller* funnel on mass grounds, and the mass is real: the CAD manifest's
geometry-derived solid-PETG estimate is 52.58 g, 29% of the entire 180 g
dock allocation. It is refused anyway, for two reasons that are not about
mass. The 90 mm mouth radius sits only 12.5 mm outside the aircraft's
77.5 mm swept radius (p0a-bench.md clearance check), so shrinking the mouth
shrinks the margin against the rim strike that the twin scores as an unsafe
event; and the funnel is the declared finding-3 mitigation, which is a
claim about faults, not about nominal capture rate.

**Merge candidate.** The throat end already is a merge target (row (a)).
The mouth is not.

**Disposition: KEEP at Ø180 mm for Rev-B; DEFER the requirement.** The
number itself is unattributed and underived. Re-derive it from the entry
dispersion measured at P0-B, and record whoever owns the answer.

## Does the spring collet earn its place next to a positive keeper?

### The case for keeping it

The strongest statement of the pro-collet argument is that the aircraft is
mechanically retained during the keeper's travel, before the servo has
finished moving, and that this decouples capture from the guidance loop at
the moment the vehicle is closest to the dock.

That statement is half wrong, and the half that survives is the interesting
half. It is wrong that the aircraft is unpowered during keeper travel: the
guidance stack asserts disarm only on `capture_confirmed and
seat_confirmed`, which cannot be true before S2, so throughout the keeper's
modeled 0.35 s travel (11 mm of nominal travel, about 31 mm/s) the aircraft
is armed and holding itself against the seat. The collet is not catching a
falling aircraft; it is helping a flying one hold station.

The half that survives: holding station is not free. The twin's
precision-approach acceleration ceiling is 2.0 m/s² on a 37 g body, which
is 0.074 N of control force, against Lighthouse-grade estimates and a dock
that is moving. Under disturbance, the collet visibly does work — see the
withdrawal counts below.

And there is a second, better argument that has nothing to do with
retention: registration. The Ø16 mm throat allows 2.0 mm of radial head
offset; the 4.2 mm keeper slot accepts 0.6 mm of mast offset. Something has
to close that 3.3× gap before the fork advances, or the fork jams against
the mast instead of surrounding it. The twin cannot see this, and in fact
encodes the wider number: `_funnel_allowed_radius` floors at 0.002 m, which
is precisely the throat's 2.0 mm, while its keeper is a scalar with no
slot. The model permits a seated state the real fork cannot close on, and
scores no jam, because the jam is not in the model. That belongs on the
missing-physics ledger regardless of what happens to the collet.

### The case for deleting it

It is a second retention path in a mechanism whose entire safety argument
is that retention is positive, provable, and commandable. It adds mass, a
jam mode, a wear surface, and pull-out behavior the twin had to model. It
is the only part in the dock whose function is asserted in five documents
and the BOM while its geometry, material, and force are all "TBD".

The quantitative objection is the one that decides it. For the collet to be
a meaningful backstop — to hold an aircraft that the keeper failed to
retain — it must hold more than the aircraft's weight: 47.7 g nominal
(p0a-bench.md) is 0.468 N. For the collet not to fight an abort inside the
approach envelope the safety supervisor is built around, it must be well
under the 0.074 N of precision-approach control force above. Those two
requirements differ by 6.3×. No single passive spring satisfies both. A
collet sized as a backstop is a collet that resists every abort and every
release; a collet sized to be abort-transparent is a collet that holds
about a tenth of an aircraft, which is not a retention path at all.

The twin's own parameterization has already conceded this without anyone
noticing: `collet_pullout_speed_m_s = 0.05` is a threshold an unpowered
aircraft crosses 5.1 ms and 0.13 mm into free fall. The modeled collet
cannot hold an unpowered aircraft even in principle, and the model never
tests whether it could, because a disarmed aircraft is pinned to the seat
by fiat (`dock_physics.py`, seated branch). The twin has never produced
evidence for the collet's claimed function; it has produced a parameter
that quietly contradicts it.

### What the twin says when asked directly

Sensitivity study run for this memo: `sil-p0b` nominal episodes, seeds
1–80, sweeping `DockGeometry.collet_pullout_speed_m_s`. 0.0005 m/s stands
in for "collet deleted" (any relative descent unseats the probe); 0.05 m/s
is the repo baseline. Keeper travel time is not a config field, so the
0.80 s cells substitute the servo constructor. Model results, not vehicle
performance — the twin remains uncalibrated, and every number below is a
statement about `aiur/sim`.

```python
from dataclasses import replace
from aiur.sim import dock_physics
from aiur.sim.disturbances import outdoor_breeze
from aiur.sim.dock_physics import DockGeometry
from aiur.sim.engine import run_episode
from aiur.sim.scenarios import sil_p0b
from aiur.sim.sensors import KeeperServo

dock_physics.KeeperServo = lambda: KeeperServo(travel_time_s=0.80)  # 0.80 s cells
geom = DockGeometry(collet_pullout_speed_m_s=0.0005)                # collet deleted
config = sil_p0b(seed, air=outdoor_breeze(0.5))                     # wind cells
result = run_episode(replace(config, dock_geometry=geom), seed)
```

| Air | Keeper travel (s) | Pull-out (m/s) | Captures | Probe-withdrawal events |
| --- | ---: | ---: | ---: | ---: |
| indoor calm | 0.35 | 0.0005 | 80/80 | 0 |
| indoor calm | 0.35 | 0.05 | 80/80 | 0 |
| indoor calm | 0.80 | 0.0005 | 80/80 | 0 |
| indoor calm | 0.80 | 0.05 | 80/80 | 0 |
| 0.5 m/s wind | 0.35 | 0.0005 | 80/80 | 13 |
| 0.5 m/s wind | 0.35 | 0.05 | 80/80 | 0 |
| 0.5 m/s wind | 0.80 | 0.0005 | 80/80 | 25 |
| 0.5 m/s wind | 0.80 | 0.05 | 80/80 | 0 |

Three readings, and one discarded experiment.

1. In the air P0-A and P0-B actually run in, the collet's retention path
   never activates. Not "activates rarely" — zero withdrawal events across
   160 episodes, at both keeper speeds.
2. Under 0.5 m/s wind the collet does real work, suppressing 13 to 25
   withdraw-and-reseat cycles per 80 episodes. It changes no outcome:
   80/80 captures with and without. The guidance stack re-approaches and
   the keeper catches the probe on a later attempt.
3. The keeper's own cam-under-the-head path (`keeper_cam` seating) fired
   zero times in every cell, because the keeper only moves after S1 seats.
   Neither the collet nor the keeper is performing "first capture" in the
   model; the funnel and the seat are.
4. Discarded: a 1.5 s keeper-travel cell returned 0/40 captures with and
   without the collet. That cell measured the `DockController`'s 1.0 s lock
   timeout, not the mechanism, and is reported only so nobody re-runs it.
   The real finding underneath it stands — keeper travel time against the
   lock timeout is what sets capture rate in this model, and the collet is
   not close to being the sensitive parameter.

An injected-fault cell (40 episodes, one drawn fault each) returned 27/40
with and without. The collet is irrelevant to fault handling.

### Disposition

**MERGE.** Delete the spring collet as a retention element. Merge its
registration function into geometry that already exists: widen the keeper
slot so the throat's own clearance guarantees fork acceptance, and let the
throat do the centering it is already shaped to do.

Sizing, as an engineering target pending A0: the slot must absorb the
mast's full throat-allowed excursion, 3.0 mm mast + 2 × 2.0 mm = 7.0 mm,
plus print variation — target ≥7.5 mm. Retention geometry is unaffected
because a Ø12 mm head cannot pass a 7.5 mm slot; what changes is bearing
area, from 2.25 mm of tine overlap per side when centered to 0.25 mm on the
far side at worst-case offset. That asymmetry is the new thing to measure,
and it is why the 5 N axial screen must be applied with the probe at the
throat wall rather than centered. Trading a compliant part for a tolerance
band is only a good trade if the tolerance band is measured.

The deletion is conditional, and the condition is numeric: A0 measures free
probe wander at the fork plane with no insert fitted, and the insert stays
deleted only if measured wander + 0.5 mm ≤ (slot width − 3.0 mm) / 2. If it
fails, the insert returns as a centering-only feature with a retention
force target ≤0.05 N — explicitly below the abort-transparency bound, never
sized as a backstop, and never in the keeper's travel path.

That last clause deserves emphasis because the tempting alternative is
worse. A compliant throat insert that blocks the fork unless a probe
displaces it would give discrimination for free with an unchanged S2. It
also puts an unmeasured compliant part in series with the primary retention
mechanism, which converts the dock's one provable load path into a load
path gated by a spring nobody has characterized. Rejected.

Mass is not the argument, and the memo should not pretend otherwise: the
insert is a few grams against a 180 g dock allocation that currently has
107 g unassigned after the printed parts and the actuator, inside a payload
budget with ≥574.6 g of rated reserve. The argument is that it is a second
retention path that cannot be sized, cannot be gated, and is not needed.

## Could one discriminating sensor replace S2 and close finding 5?

### What S1 AND S2 actually claims today

Before answering, the claim being protected has to be stated accurately,
because it is easy to over-read. `capture_confirmed = S1 AND S2` is two
switches sensing two different physical facts, and it is single-fault
tolerant against a lying servo command. It is **not** two-of-two voting on
the question anyone cares about. Against the top event "capture confirmed
with no aircraft retained", the cut sets are:

| Cut set | Faults | Currently detected by |
| --- | ---: | --- |
| S1 stuck actuated, keeper closes on an empty throat | 1 | supervisor plausibility gate (finding 2) — defeated by a correlated navigation bias (finding 5) |
| S2 actuated while the keeper is open, jammed, or short of engagement; probe genuinely seated; aircraft disarms | 1 | nothing |

The second row is worth pausing on. A misadjusted S2 — actuating before the
fork tines are meaningfully under the head — is a single latent fault that
produces a confirmed capture on an unretained aircraft, and it is the
failure mode the practice survey's mechanisms section names directly, along
with the rule that a status indicator must never double as an end stop. The
twin cannot find it: `aiur/sim/faults.py` injects `SEAT_SWITCH_STUCK_OPEN`,
`SEAT_SWITCH_STUCK_CLOSED`, and `KEEPER_SERVO_JAM`, but no stuck or
misadjusted keeper switch. P0-A step 3 checks S2 false at the open stop and
nothing about where it trips. So the honest current claim is: capture
confirmation is single-fault tolerant against the servo and against no
switch.

### The answer

**Yes for S2, no for S1 — and the saving is not a deleted part, it is an
un-added one.**

Replace S2 in place with S2′, sensing "keeper closed with a mast in the
slot" rather than "keeper reached its stop". Confirmation stays
`S1 AND S2′`. Part count is unchanged, channel count is unchanged, mass is
unchanged, and finding 5's Rev-B addition is deleted before it is ever
built.

The collapse-to-one version — a single discriminating sensor replacing both
S1 and S2 — is rejected outright, and not on part count. A single sensor
cannot be two independent channels; that is arithmetic, not engineering
judgment. Under `capture_confirmed = D`, one stuck-actuated D produces a
confirmed capture and authorizes disarm, in *both* cut sets above, with no
second opinion anywhere in the system. No part-count saving justifies
putting the program's only irreversible action behind one switch.

### The resulting safety claim, stated precisely

With S1 AND S2′:

- No navigation fault of any magnitude can produce a confirmed capture on
  an empty throat. The empty-throat path now requires a sensor to lie, not
  an estimator. Finding 5's specific cut set is broken, and it is broken
  mechanically, which is the only place it can be broken.
- Single-fault tolerance against the empty-throat top event: achieved. S1
  stuck actuated no longer suffices, because S2′ cannot actuate on an empty
  throat.
- Single-fault tolerance against the seated-but-unretained top event: **not
  achieved**, unchanged from Rev-A. S2′ stuck or misadjusted actuated, with
  a genuinely seated probe, still confirms. The residual moves from a
  navigation residual to a mechanism residual, which is progress — a
  mechanism residual is bounded by a trip-point measurement and an
  inspection, whereas the navigation residual was bounded by nothing.
- "Two channels" is not "two independent channels" and this memo does not
  claim it. Shared switch lot, shared harness, shared pull-up rail, shared
  debounce code, and one MCU are common causes that ADOPT-004's common-mode
  analysis must price before any independence number is asserted.

The claim to write down is therefore: *no single navigation fault and no
single sensor fault produces a confirmed capture on an empty dock;
confirmed capture on a seated-but-unretained probe remains reachable by a
single keeper-switch fault, bounded by the measured S2′ trip point and
signed as residual under ADOPT-003.*

### Implementations, none frozen here

| Candidate | Added parts | Weakness |
| --- | ---: | --- |
| Compliant detent printed into the keeper slot end, deflected by the mast; S2′ cam senses the deflected member | 0 | detent must work across the mast's ±2.0 mm throat freedom |
| S2′ cam reads a keeper travel-stop difference between empty and mast-present | 0 | the same ±2.0 mm freedom smears the stop position across ~4 mm of an 11 mm travel |
| Separate mast-presence switch at the fork plane | +1 | adds the part this review exists to avoid; also correlates with S1's failure story |
| XL330 current or position signature | 0 carried | shares the servo's supply and controller, is threshold inference rather than physical position, and a jam looks like engagement; forbidden from the Boolean by p0a-fabrication.md |

The first two are the live candidates and the choice between them is a
geometry decision that needs A0 numbers, not a memo. The fourth stays where
it is: corroborating telemetry, never a term in the capture Boolean.

## Deletion candidates scorecard

| Part | Requirement served | Whose requirement | If deleted | Disposition | Net mass change (g) |
| --- | --- | --- | --- | --- | ---: |
| Passive spring collet / first-capture insert | passive first capture; in practice, probe registration at the fork plane | dock mechanism owner (unnamed), inherited from prototype-p0.md | no modeled capture-rate change in indoor calm; loses the only part closing the 2.0 mm throat / 0.6 mm slot gap | MERGE into throat + slot geometry; delete as a retention path | −4 (target) |
| S1 seat switch | physical seat proof; `OPEN -> LOCKING` trigger; disagreement detector for finding 2 | flight-software and safety owner (unnamed) | closure decision moves onto the navigation estimate; confirmation collapses to one channel | KEEP, requirement rewritten to trigger + diagnostic | 0 |
| S2 keeper-closed switch | keeper position sensed on the latch element, independent of servo command | flight-software and safety owner (unnamed) | servo command becomes the only keeper evidence — forbidden by the architecture | MERGE: replace in place with discriminating S2′ | 0 |
| Sliding fork keeper | positive retention of the 5 N axial / 1 N lateral screen; commandable release | dock mechanism owner (unnamed) | dock becomes passive-only and cannot be commanded to let go; P0-A release criteria unclosable | KEEP | 0 (slot widening and detent geometry net out; target) |
| Proposed Rev-B keeper-discrimination sensor | finding 5: a capture signal no navigation fault can spoof | twin finding 5; owner unnamed | finding 5 stays open as accepted residual | DELETE as a separate part; absorbed by S2′ | −3 vs. the added-sensor Rev-B (target) |
| Funnel at Ø180 mm | converts lateral error into centering; declared mitigation for finding 3 | program lead (unnamed); underived in the repo | terminal navigation must deliver millimeter coincidence, which finding 3 says it cannot be trusted to do | KEEP the part; DEFER the number for re-derivation from P0-B entry dispersion | 0 (52.58 g today, 29% of the dock allocation) |

Net: about −7 g, all of it engineering target. Deltas marked (target) are
targets, not measurements — no dock part has been weighed. The only vendor
mass in the dock is the 18 g XL330; the 52.58 g funnel, 1.47 g keeper, and
0.87 g probe head are geometry-derived solid-PETG estimates from the CAD
manifest, not weights. Against a 180 g dock allocation with 107 g still
unassigned after printed parts and actuator, and ≥574.6 g of rated-payload
reserve, the mass column is the least important column in this table. It is
included because the review is required to produce it and because it is
useful to see, in numbers, that mass is not why any of these decisions
should be made.

## What this review does not decide

- **Rev-B geometry.** Slot width, detent form, S2′ cam profile, and trip
  point are sized from A0 measurements. The targets above are inputs to
  that sizing, not drawings.
- **Whether the collet is actually deleted.** This memo sets a numeric
  criterion and hands it to A0. A deletion review that deletes parts on
  argument alone is the same error it was written to prevent.
- **The P0-A gate criteria.** Adding worst-case-offset load application and
  loaded releases belongs to ADOPT-001; this memo only names why they
  matter here.
- **The twin's fault menu.** A stuck or misadjusted keeper switch, and the
  correlated pairs behind finding 5, belong to ADOPT-005.
- **Independence.** The common-mode analysis that would let anyone put a
  number on S1/S2′ independence belongs to ADOPT-004.
- **Residual acceptance.** The seated-but-unretained residual needs a name,
  a date, and a scope under ADOPT-003. This memo does not accept it.

## Evidence that settles it

All of this is P0-A work, most of it in A0, none of it requiring hardware
the program has not already specified.

| # | Measurement | Method | Decides |
| ---: | --- | --- | --- |
| 1 | Free-probe lateral wander at the fork plane, no insert fitted | seat the coupon head in the Ø16 mm throat, drive it to the wall in 8 directions, measure mast offset at the fork plane; ≥10 repeats | collet MERGE vs. return, against `wander + 0.5 mm ≤ (slot − 3.0)/2` |
| 2 | Candidate insert axial retention force at the seat, pre- and post-50-cycle | 0–2 N gauge pull on the coupon; ≥10 repeats | whether any insert can sit between the 0.468 N backstop threshold and the 0.074 N abort-transparency bound; the prediction is that none can |
| 3 | S2 trip point expressed as tine engagement under the head | measure fork overlap at the instant S2 changes state, both directions, 10 actuations, record hysteresis | the seated-but-unretained cut set, and whether an S2′ position band is manufacturable |
| 4 | Keeper closed-stop position, empty throat vs. mast present | 10 repeats each, calipers against a datum on the guide | which S2′ implementation is viable, and how wide the discrimination band is |
| 5 | Keeper travel time distribution, ≥50 cycles at nominal and minimum bus voltage | A1 instrumented cycling | whether the modeled 0.35 s is real and whether the 1.0 s lock timeout has margin — the parameter the twin says actually sets capture rate |
| 6 | 5 N axial screen with the probe driven to the throat wall, not centered | existing P0-A load procedure, worst-case offset | whether a widened slot still has bearing area at worst-case offset |
| 7 | Emergency release under 0.468 N and under 5 N | loaded release trials | whether any retained insert hangs up on release; also closes an ADOPT-001 gap |
| 8 | Weigh every dock part to 0.1 g | A0 exit step | converts this memo's entire mass column from target to evidence |

Measurements 1 and 2 are the ones that close the central question, and both
are an afternoon with a force gauge and a set of calipers. That is the
whole point of running the deletion review before Rev-B rather than after:
the argument costs a memo, and the evidence that settles it costs less than
the part it might delete.
