# Test-like-you-fly exception ledger

Status: ledger opened 2026-08-08; nothing retired, because no article is built  
Scope: SIL twin, P0-A bench, P0-B suspended rig, P0-C tethered carrier  
Practice source: Aerospace TOR-2010(8591)-6, cited in
[engineering-practice-survey.md](engineering-practice-survey.md). The
document itself is not quoted here; what is adopted is its discipline —
enumerate what a test article fails to reproduce about the mission, classify
each gap, and give each one a closing gate.

Every test article differs from the mission it stands in for. The failure
mode this ledger prevents is the silent waiver: a gate that passes while the
condition that later breaks the vehicle was never present, and nobody wrote
down that it was absent.

The model side of this ledger already exists — the known-missing-physics list
and credibility block in [digital-twin.md](digital-twin.md) and
`aiur/sim/credibility.py`, which forces every campaign report to carry its
own caveats. This file is the hardware side, plus the twin's own entry, so
the two halves are read together.

## How to read the ledger

| Column | Meaning |
| --- | --- |
| ID | Stable key, cited by the gate evidence that retires it |
| Not reproduced | What the article does not do that the mission does |
| Critical | `yes` if the absent condition could hide a failure that ends a sortie, damages the carrier or an aircraft, or injures a person |
| Impact | What the passing gate therefore does not prove |
| Retirement gate | The named later article or test that reproduces the condition |

Classification is deliberately blunt. `no` does not mean "ignore" — it means
the exception can wait for its gate without changing what the current gate is
allowed to claim. An exception whose retirement gate is `none in P0` does not
disappear at the end of the program: it is either signed into the
[hazard log](hazard-log.md) as an accepted residual with a named acceptor, or
it becomes a requirement in the next program.

## SIL twin (`aiur/sim`)

The twin is a test article too, and it is the one currently producing the
most numbers. Its credibility block scores the same gaps as
NASA-STD-7009B factors; this table states them as mission exceptions.

| ID | Not reproduced | Critical | Impact | Retirement gate |
| --- | --- | --- | --- | --- |
| TLYF-SIL-01 | Any hardware. Every switch, servo, harness, and printed part is a model with estimated parameters | yes | No campaign result is evidence about a mechanism; the twin has zero empirical referent points (validation factor level 1) | P0-A: fault insertion mode by mode plus the cycle campaign, then the calibration-ledger replay in [digital-twin.md](digital-twin.md) |
| TLYF-SIL-02 | Aircraft attitude dynamics | yes | Funnel-lip to rotor-plane clearance under tilt is a geometry sanity check, never a simulated outcome | P0-B with the real guarded aircraft |
| TLYF-SIL-03 | Propeller downwash recirculating off the hull | yes | Terminal-approach disturbance is optimistic by an unquantified amount | P0-C (first article with a hull above the dock) |
| TLYF-SIL-04 | Carrier trim transient on capture and release | yes | A 37 g aircraft is a ~0.36 N dead-weight step against a modeled 0.3 N vertical thrust budget; the twin assumes a re-trim the vehicle must actually perform every cycle | P0-C |
| TLYF-SIL-05 | Wear, friction growth, galling, and as-built tolerance | yes | The twin's keeper never degrades; loaded release and force margin cannot be predicted from it | P0-A run-in, 600-cycle life test, post-cycle screening loads, teardown |
| TLYF-SIL-06 | Correlated and simultaneous faults; campaigns inject at most one fault per episode | yes | The double-fault finding (stuck seat switch plus masked navigation bias) is reasoned, not sampled; campaign statistics describe a single-fault world | ADOPT-005 correlated-pair injection in the twin, then the insertable pairs at P0-A |
| TLYF-SIL-07 | Electrical reality: contact bounce beyond the modeled debounce, wetting-current contact failure, rail transients, EMI, brownout below the controller's detector | yes | Switch behaviour is an ideal debounced contact with stuck faults; the physical failure modes that make dual-contact decode necessary are absent | P0-A fault insertion ([fault-insertion.md](../hardware/dock/fault-insertion.md)) against the [electrical evidence packet](electrical-evidence.md) |
| TLYF-SIL-08 | Thermal effects, battery ageing, and duty-cycle heating | no | Endurance and repeated-cycle behaviour are outside the model's claims | P0-C day-in-the-life below |

## P0-A rigid bench

The bench answers whether the mechanism is mechanically and electrically
true. It answers nothing about flight, by design — every entry below is a
condition the bench deliberately removes so that a failure is attributable.

| ID | Not reproduced | Critical | Impact | Retirement gate |
| --- | --- | --- | --- | --- |
| TLYF-A-01 | Dock compliance. The bench plate is rigid; the flight dock hangs from a carrier structure that deflects and rings | yes | Insertion force, keeper alignment, and `S1`/`S2` timing are measured against a stiffness the vehicle does not have | P0-B (dock on the suspended rig), confirmed at P0-C on the carrier mount |
| TLYF-A-02 | Motion coupling. Insertion is manual into a stationary dock, and capture reacts nothing back into the mount | yes | Closing speed, off-axis entry, and bounce-out are untested; the collet's job is asserted, not demonstrated | P0-B moving dock with a live aircraft |
| TLYF-A-03 | Downwash. Propellers are removed by gate rule | yes | The funnel never sees rotor flow, and prop-guard interaction with the funnel lip is unknown | P0-B (free-field downwash), P0-C (recirculation off the hull) |
| TLYF-A-04 | Envelope proximity. Nothing in P0-A attaches to or sits near the gas envelope | yes | Keep-out geometry, static discharge path, and puncture risk are untested | P0-C |
| TLYF-A-05 | Aircraft attitude dynamics. A coupon or battery-less aircraft is inserted by hand along a near-ideal axis | yes | Real approaches arrive with tilt and lateral rate; the ~25 mm lip-to-rotor clearance estimated at 15° tilt stays an estimate | P0-B |
| TLYF-A-06 | Autonomous command timing. Capture enable and release are commanded by an operator, not by the guidance stack | yes | The latched capture-enable requirement (twin finding 1) and the seat-plausibility gate (finding 2) are exercised only in the twin | P0-B, with SIL-B evidence carrying the claim until then |
| TLYF-A-07 | Flight electrical environment: carrier harness lengths, shared rails, vehicle EMI, and vibration | yes | Partially retired at P0-A — the fault-insertion unit inserts brownout, interrupt, open, and short — but the vehicle's own noise is absent | P0-A fault insertion (partial), P0-C (full) |
| TLYF-A-08 | Thermal range and article-to-article variation. One new article at room temperature | no | Indoor P0 sees no thermal excursion; build variation is bounded instead by the [golden article](../hardware/dock/golden-article.md) comparison | Golden-article comparison per build; no P0 thermal gate |

## P0-B suspended rig

The rig adds relative motion and a live aircraft. It does not add a vehicle.

| ID | Not reproduced | Critical | Impact | Retirement gate |
| --- | --- | --- | --- | --- |
| TLYF-B-01 | Hull downwash recirculation. Downwash exits freely instead of reflecting off a 4.5 m envelope above the dock | yes | The terminal-approach disturbance measured on the rig is a lower bound on the vehicle's | P0-C |
| TLYF-B-02 | Carrier trim transient. Rig dock motion is programmed and does not react to the ~0.36 N dead-weight step at capture, which exceeds the modeled 0.3 N vertical thrust budget | yes | The rig cannot show whether the carrier holds station through capture and release, which is the actual recovery question | P0-C |
| TLYF-B-03 | Gas envelope. There is nothing to strike | yes | The `envelope_strikes == 0` criterion is untestable here, and prop-guard adequacy near a thin film is unknown | P0-C |
| TLYF-B-04 | Carrier dynamics. Dock motion follows a script; real dock motion is produced by air, tether, and station-keeping, and is disturbed by the aircraft being caught | yes | Closing-speed statistics come from a motion profile chosen by the test, not by the vehicle | P0-C |
| TLYF-B-05 | Buoyancy and ballast state: helium loss, ballast shift, attitude change with load | no | Single-capture results are unaffected; the sortie-set behaviour is not | P0-C day-in-the-life below |
| TLYF-B-06 | Vehicle power. The rig dock runs from bench supply, not a shared carrier rail | yes | Servo inrush against a flight rail, and its effect on the controller, is not exercised | P0-C, informed by the [electrical evidence packet](electrical-evidence.md) |
| TLYF-B-07 | Outdoor air. Indoor calm only | no | Consistent with P0 scope; the twin's sweep puts capture collapse near 1.0 m/s mean wind | none in P0 — carried to the outdoor milestone in [docs/verticals](verticals/README.md) |

## P0-C tethered carrier

The closest article to the mission, and still not the mission.

| ID | Not reproduced | Critical | Impact | Retirement gate |
| --- | --- | --- | --- | --- |
| TLYF-C-01 | Free flight. The ground tether caps excursion and changes the carrier's low-frequency response to a capture impulse and to drafts | yes | Recovery is demonstrated on a constrained vehicle; a free carrier's response to the same impulse is not measured | none in P0 — P1 free-flight article |
| TLYF-C-02 | Outdoor air: wind, thermals, solar heating of the envelope | yes | Capture is demonstrated only in an environment the twin says is the easy one | none in P0 — outdoor milestone (`SHARED-002`) in [docs/verticals](verticals/README.md) |
| TLYF-C-03 | Endurance limits. Runs end at battery exchange or crew fatigue, not at the vehicle's limits: helium diffusion, trim drift, servo duty heating, and telemetry growth are never seen at their limits | yes | Turnaround time and repeatability are measured over short sets, so wear-in-a-session failures are invisible | Day-in-the-life below (partial); P1 soak (full) |
| TLYF-C-04 | Unsupervised autonomy. A safety pilot holds abort authority at all times | yes | The autonomy's own failure rate is masked by human intervention; every abort is a joint result | none in P0 — P1 supervised-autonomy soak with logged non-intervention |
| TLYF-C-05 | Carried relative sensing. Positioning is ground-referenced (Lighthouse-class), not carried by the vehicle | yes | The recovery loop demonstrated is not the one an operational vehicle would fly (`SHARED-001`) | none in P0 — P1 sensing milestone |
| TLYF-C-06 | Full flight envelope. Prop guards fitted, closing speed capped at 0.20 m/s, conservative approach geometry | no | Claims stay inside the P0 capture envelope, which is what P0 claims | P1 envelope expansion |
| TLYF-C-07 | Fleet operations. One active dock, at most two aircraft | no | Sequencing beyond two aircraft and dock contention are unexercised | P0-D (two aircraft, partial); P1 (full) |
| TLYF-C-08 | Airborne recharging. Recovered aircraft are not charged on the dock | no | Explicit P0 non-goal; the turnaround measured is a manual one | P1, gated on repeatable mechanical recovery |

## Day in the life (required before P0-C sign-off)

Every gate above tests a capture. None of them tests a **day**. Sequence-
dependent failures — state that survives one cycle and breaks the next — do
not appear in ten isolated attempts, and they are the failures that make a
system unusable rather than unsafe.

Before P0-C is signed off, run repeated full launch/sortie/recover cycles
back to back, continuing through at least one aircraft battery exchange
performed per the [battery SOP](battery-sop.md).

| Observable | Requirement | Why |
| --- | --- | --- |
| Consecutive full cycles per aircraft pack | run until the SOP low-voltage limit, no early stop for convenience | The last cycle on a sagging pack is the one that reveals brownout-sensitive behaviour |
| Battery exchanges spanned | ≥1, with cycles continuing afterwards on the same carrier session | Exchange is a state discontinuity for the aircraft and an operator-load spike for the crew |
| Unplanned interventions | 0 tolerated silently; each is a finding with a disposition | A dock controller power-cycle, software restart, or manual mechanism nudge between cycles is a failure of the sequence, not a reset |
| Per-cycle turnaround time | recorded for every cycle, capture-confirmed to next launch | A trend, not a number: turnaround that grows across the session is a wear or thermal signal |
| Carrier trim state per cycle | recorded before and after each capture and release | The ~0.36 N step is applied and removed once per cycle; drift accumulates across a session |

Suspects this test is written to catch, none of which a single capture can
show: capture-enable latch or fault state not cleared between cycles;
controller uptime counters and timeout behaviour after long runs; keeper
servo heating at duty; buoyancy and ballast drift across repeated captures;
battery sag deepening cycle over cycle; telemetry log growth; and crew error
under repetition.

The result is a run set like any other: it produces an evidence packet, a
disposition from [engineering-loop.md](engineering-loop.md), and either a
retired TLYF-C-03 or a finding.

## Exception summary

| Article | Exceptions | Mission-critical | Retired |
| --- | ---: | ---: | ---: |
| SIL twin | 8 | 7 | 0 |
| P0-A bench | 8 | 7 | 0 |
| P0-B rig | 7 | 5 | 0 |
| P0-C tethered carrier | 8 | 5 | 0 |

Five exceptions have no retirement gate inside P0 (TLYF-B-07, TLYF-C-01,
TLYF-C-02, TLYF-C-04, TLYF-C-05). Four of those five are mission-critical.
That is the honest shape of this program: P0 buys mechanical recovery
repeatability indoors on a constrained vehicle, and nothing else.

## Ledger rules

1. An exception is retired only by an article that reproduces the condition,
   run through its gate with the condition present, with the exception ID
   cited in that gate's evidence packet. Argument does not retire anything.
2. A `FAIL_MODEL` or `FAIL_HARDWARE` disposition on a retiring run reopens
   the exception and any claim that leaned on it.
3. A new exception is added whenever a test setup differs from the mission in
   a way not already listed — including test-only fixtures, safety
   restraints, and reduced envelopes. The ledger grows; it does not get
   tidied.
4. A mission-critical exception reaching a sign-off unretired requires a
   signed residual-risk acceptance in the [hazard log](hazard-log.md). No
   signature means the article is not signed off.
5. Every campaign or run set that leans on an exception states it. The twin
   does this automatically through the `[M&S 32]` warning list in its
   credibility block; hardware run sets do it in the test card.
