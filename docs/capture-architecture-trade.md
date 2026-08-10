# Capture-architecture trade study

Status: decision memo, opened 2026-08-10
Scope: the CARRIER-P0 capture interface, before Rev-B is printed
Executable source: [`aiur/sim/design_study.py`](../aiur/sim/design_study.py),
candidates in [`aiur/sim/architectures.py`](../aiur/sim/architectures.py)

## Why this study exists

The programme had one capture architecture and was about to commit it to
plastic. Every twin result so far has been a verification of that article:
does the funnel-and-fork dock meet its gates. None of it asked the prior
question — whether the funnel-and-fork dock is the right article at all.

Changing a design on disk costs nothing. Changing one on a bench costs a
build, and by Rev-B the switch brackets, harness and compliant insert are
frozen. This is the last cheap moment to run the comparison, so it was run.

Four alternatives were entered against the baseline on the same axes:

| candidate | idea |
| --- | --- |
| **Funnel + probe + sliding fork keeper (Rev-B)** | the incumbent, entered as a competitor rather than a presider |
| **Three-jaw iris keeper** | same funnel; three jaws close radially under the head, so retention senses a mast rather than a linkage |
| **Passive snap-detent** | delete the keeper and its servo; a sprung detent holds, the aircraft flies itself out |
| **V-trough + over-centre latch** | a cross-bar drops into a V that centres by geometry; a bistable bail holds with no power |
| **Deep cup + over-top latch bar** | swallow the whole airframe; trade ±2.0 mm of throat for ±72.5 mm of bore |

## What is ranked, and why it is not capture rate

Every mechanism captures when the probe arrives centred with honest
sensors. That measures the scenario, not the design. What separates the
candidates is how much *terminal positioning error* each absorbs, because
that error budget sets the sensor the programme has to buy — and
[SHARED-001](verticals/README.md), GNSS-independent terminal relative
navigation, is the hardest requirement every non-laboratory vertical
inherits. An architecture that still captures at ten times the positioning
noise does not improve a percentage; it changes which sensor exists, which
changes which verticals are reachable.

So the ranking is: safety first, then positioning-noise tolerance, then
nominal capture rate. Cost terms — parts, actuators, sensed channels, mass
— are printed alongside and never folded into a score. Collapsing "captures
at ten times the noise" and "has no actuators" and "weighs 380 g more" into
one number would bury exactly the trade a human has to make, and would let
a weighting chosen in a Python file decide a hardware programme.

The noise axis retunes FDIR with the sensor, exactly as the degraded-sensor
sweep in [digital-twin.md](digital-twin.md) does. Without that the study
ranks architectures by how well each happens to suit the default guidance
tuning, which is a fact about the defaults and not about the mechanism.

## Result

24 episodes per condition, seed 1
(`python -m aiur.sim.design_study --episodes 24 --seed 1 | python tools/report_study.py`):

| architecture | safe | noise | wind | nom% | act | sens | parts | dock g |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Funnel + probe + sliding fork keeper (Rev-B) | yes | 30x | 1.0 | 100.0 | 1 | 2 | 5 | 75 |
| Three-jaw iris keeper | yes | 30x | 1.0 | 100.0 | 1 | 2 | 23* | 106 |
| Passive snap-detent (no actuator) | yes | — | — | 0.0 | 0 | 1 | 3 | 57 |
| V-trough with over-centre latch | **NO** | 30x | 1.0 | 100.0 | 1 | 2 | 10 | 58 |
| Deep cup + single over-top latch bar | **NO** | 30x | 0.5 | 95.8 | 1 | 2 | 8 | 454 |

`noise` is the highest positioning-noise multiple still capturing above the
50% collapse threshold — the sensor each design lets you get away with.
`safe` means no injected fault and no condition produced an unsafe outcome.

\* Part counts are **not on a common convention** and must not be read
across the table as they stand. The iris entry counts every discrete piece
a technician handles (23); the baseline counts distinct part types (5). At
the baseline's granularity the iris is about 10. Neither is a BOM. This is
recorded rather than silently normalised because the mismatch is a finding
about the study, and the study is what a build decision would read.

## What it says

**The baseline survives the comparison, and that is a result, not a
formality.** It was not protected: it ranked on the same axes as everything
else, and it happens to top the table on the axis the verticals hinge on
while being the cheapest thing on it. Printing Rev-B is now a decision with
four measured alternatives behind it instead of an absence of alternatives.

**The iris ties the baseline on every simulated axis and loses on cost.**
Its argument was never capture rate — it was that S2' senses "a Ø3 mm mast
is between three jaws" instead of "a linkage reached its stop", which
narrows the empty-throat cut set the deletion review's finding 5 left open.
The twin cannot see that benefit, because the benefit is in a fault space
the shared injector does not reach. What the twin *does* show is that the
benefit is not free: roughly double the part count, and an empty-throat
discrimination that is a *timing* property (1.76x margin at nominal
actuator stroke, shrinking linearly with a sagging servo) rather than a
geometric one. That coupling ties a switch datum, an actuator stroke time
and a software timeout across three subsystems whose owners would each see
only their own document. Not adopted for P0; kept in the registry.

**The passive detent is dead, and the reason is arithmetic, not tuning.**
The aircraft hangs from the detent, so retention must exceed its weight,
while the most force it can apply to escape is that same weight unloaded
off its propellers. Hold needs `R·f > W`, release needs `R·f ≤ W`. No
retention force satisfies both, at any friction factor. It captures 0% at
every condition because at its own honest sizing the probe cannot get in.
This is the cheapest possible way to have learned that: the deletion review
proposed deleting the keeper, and the answer is now a closed-form
impossibility rather than an opinion. It stays in the registry **with its
result recorded** — a rejected architecture with a measured reason is a
finding; a quietly deleted one is a gap somebody re-proposes in six months.

**Two candidates are unsafe on this model, and both failures are about the
mouth, not the latch.** The V-trough's opening is 110 × 150 mm against the
funnel's 180 mm circle, so arrivals the funnel swallows become propeller
contacts: 2 unsafe episodes at 1.0 m/s wind, against zero for the baseline
over the same seeds. The deep cup is worse — 11 unsafe episodes at 1.0 m/s
— because every wall of a deep bore is a rotor wall, and the mouth swallows
the crown cap 40 mm before the rotor plane reaches the rim, so a bad
approach is committed before it can be rejected. The funnel's 60 mm rim
annulus rejects early, and that turns out to be a safety property nobody
had written down as one.

**The deep cup produced the most important finding despite losing.** Its
mass is disqualifying on its own (454 g dock-side against a 180 g
allocation), but the reason it cannot cash its ±72.5 mm acceptance is
software: `GuidanceParams.seat_confirm_m` gates capture-enable and disarm
off the navigation estimate at 15 mm, so the shared supervisor caps *any*
candidate at the baseline's positioning requirement however wide its mouth
is. **The programme's terminal-positioning requirement is currently set by
a guidance constant, not by the mechanism.** Widening a mouth buys nothing
until that constant moves, and moving it weakens the plausibility gate that
stops a stuck seat switch disarming an aircraft in free air. No mechanism
choice can resolve that; it is a software trade, and it would have stayed
invisible if the study had only ever simulated the design already chosen.

## Standing caveats

- **Simulation only.** No candidate has been built or measured. The twin's
  NASA-STD-7009B validation factor is level 1 for all of them equally.
- Alternatives carry surrogate physics of the same fidelity as the
  baseline's, so a comparison *between* them is fairer than any single
  absolute number from it.
- Cost terms are engineering estimates supplied by each candidate, on
  inconsistent counting conventions (above). They are not measurements.
- The shared fault injector reaches `seat_switch`, `keeper_switch` and
  `servo` only. Per-candidate failure modes — per-jaw binds, actuator power
  loss, detent set — are exercised by each module's own tests and by
  nothing in the campaign, so campaign fault statistics under-sample every
  alternative's specific failure space. Compare per fault kind, not per
  campaign.
- The study harness runs the bench-rig `sil_p0b` scenario, which has no
  hull and no carrier-proximity reflex. The deep cup's launch-departure
  unsafe result was found outside that harness and would not appear in the
  table above.

## Decision

Print Rev-B as the baseline funnel + probe + sliding fork keeper. The
alternatives stay in the registry with their results, and the study is
re-runnable against any candidate added later.

The open action this study creates is not mechanical:
`GuidanceParams.seat_confirm_m` sets the programme's terminal-positioning
requirement, and SHARED-001 is written against it. Whether that constant
can move — and what it costs the finding-2 plausibility gate — is the
question worth answering before any wider-mouth architecture is proposed
again.
