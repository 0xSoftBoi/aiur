# P0-A bench test card

Status: printable run card, not measured hardware
Gate: P0-A — bench capture ([`aiur/loop_graph.py`](../../aiur/loop_graph.py))
Article: Rev-A A1 instrumented dock ([`p0a-bench.md`](p0a-bench.md),
[`p0a-fabrication.md`](p0a-fabrication.md))
Flight condition: **no flight; propellers removed**

This is the template in [`docs/test-cards.md`](../../docs/test-cards.md) filled
in for the P0-A bench campaign. Print it, fill it by hand, file it with the run
logs.

One card per session. The P0-A cycle count does not fit in one session: run-in,
life cycling, emergency-release trials, and fault insertion span several, and
each session gets its own card carrying the same `run_id` and the same
configuration identity. If the article is modified, re-shimmed, or reprinted
between sessions, the identity is new and the cycle evidence restarts
([`p0a-bench.md`](p0a-bench.md) stop conditions).

The success criteria below are transcribed from `GATES["P0-A"]` at the git SHA
recorded in the identity block. If the gate definition changes, re-transcribe
before the run — the card, not memory, is what the crew works to.

## 1. Run identity

| Field | Value |
| --- | --- |
| `run_id` | |
| Gate | P0-A |
| Session number / cumulative cycles at session start | |
| Configuration/calibration hash | |
| Git commit SHA | |
| Dock revision | Rev-A / A1, serial ________ |
| Probe revision | Rev-A, serial ________ (coupon / aircraft with battery removed) |
| Actuator | DYNAMIXEL XL330-M288-T, ID ____, position limits set ____ / ____ |
| Bench controller / supply | OpenRB-150 (or equivalent), 5 V bench supply, current limit ____ A |
| Fault-insertion unit fitted (S1 / S2 / servo lines) | yes / no |
| Date | |
| Location | |

Article masses and force margins, per-cycle results, screening loads, and fault
trials are logged under this same `run_id` in
[`p0a-article-template.csv`](p0a-article-template.csv),
[`p0a-run-template.csv`](p0a-run-template.csv),
[`p0a-load-template.csv`](p0a-load-template.csv), and
[`p0a-fault-template.csv`](p0a-fault-template.csv).

## 2. Crew

| Role | Name | Notes |
| --- | --- | --- |
| Test Conductor | | reads the card; commands keeper motion; applies loads |
| Safety Observer | | independent; holds the bench-supply master kill switch; touches nothing on the article while it is live |
| Recorder | | fills the four CSVs and this card; operates nothing |
| Operator (if separate from TC) | | |
| TRR chair | | not the person who built or printed the article |

Safety glasses on everyone within 2 m of the fixture whenever a load is applied
or the actuator is powered. The Safety Observer confirms this before step 4.

## 3. Objective

Establish that the Rev-A A1 dock retains the Ø12 mm probe head positively under
the P0 screening loads, that capture indication cannot be produced by a single
signal, that the probe can be released on demand — loaded and unloaded — every
time, and that the mechanism survives a derived life test without structural
damage or a drifting force signature.

## 4. Success criteria

Numeric, from `aiur.loop_graph.GATES` P0-A. The campaign closes the gate only
when the reducer verdict passes on every row; a metric with no evidence is a
failed gate, never an implied pass.

| Metric | Limit | Meaning on this bench |
| --- | ---: | --- |
| `run_in_cycles` | ≥ 15 | run-in completed before life cycling starts |
| `run_in_force_trend_stabilized` | = 1 | per-cycle insertion/release force leveled off during run-in |
| `life_test_cycles` | ≥ 600 | derived life test: expected cycles through P0-D × life factor |
| `dock_mass_g` | ≤ 180 | dock assembly mass budget |
| `probe_mass_g` | ≤ 8 | drone-side probe mass budget |
| `axial_screen_load_held_n` | ≥ 5.0 N | keeper holds the axial screening load, pre and post |
| `lateral_screen_load_held_n` | ≥ 1.0 N | keeper holds the lateral screening load, all four directions, pre and post |
| `keeper_close_force_margin` | ≥ 2.0 | keeper closes with demonstrated margin at minimum supply voltage |
| `keeper_open_force_margin` | ≥ 2.0 | keeper opens with demonstrated margin at minimum supply voltage |
| `structural_failures` | = 0 | no structural failures |
| `ambiguous_capture_confirmations` | = 0 | capture confirmation is unambiguous |
| `emergency_release_trials` | ≥ 10 | unloaded emergency-release trials |
| `emergency_release_failures` | = 0 | unloaded emergency release always works |
| `loaded_emergency_release_trials` | ≥ 10 | emergency releases under the 5 N axial screening load |
| `loaded_emergency_release_failures` | = 0 | emergency release works while the mechanism is loaded |
| `fault_insertion_trials` | ≥ 8 | every insertable electrical fault mode exercised on hardware |
| `fault_insertion_unsafe_responses` | = 0 | every inserted fault produced its required safe response |
| `propellers_installed` | = 0 | propellers are removed |

The 5 N and 1 N values are P0 screening targets, not airworthiness or
qualification loads ([`p0a-bench.md`](p0a-bench.md)).

## 5. Run sequence

Loads are applied as hanging dead weight through a lanyard with a catch tray
beneath, never as a hand-held pull: a hand-held pull cannot be released quickly
and puts a person on the load path. Announce "KEEPER MOVING" before every
commanded actuator motion and "LOAD DROPPING" before every loaded release.

Steps 1–4 are once per campaign; steps 5–8 open every session; steps 9–15 are
the work, and a session may end at any step boundary.

| # | Action | Expected observable | Obs. | Pass |
| --- | --- | --- | --- | --- |
| 1 | Weigh and photograph the complete dock and the complete probe assembly | `dock_mass_g` ≤ 180, `probe_mass_g` ≤ 8, recorded in the article CSV | | |
| 2 | Verify propellers removed; shake-test the fixture and mount | `propellers_installed` = 0; no fixture movement; nothing above a person | | |
| 3 | Measure keeper close and open force demand against the delivered actuator force at the minimum supply voltage on the card | both margins ≥ 2.0 at the recorded `margin_supply_voltage_v`; a margin below 2.0 stops the campaign before cycling | | |
| 4 | Kill-path check with the bench controller powered **off**: actuate the master kill switch, meter the servo connector | 0 V at the servo connector with the controller dead; call-to-de-energised time recorded in the TRR block | | |
| 5 | Restore power. Command the keeper open with no probe present | keeper visibly at its open stop; `S2` = false; controller state `open` | | |
| 6 | Insert the probe with capture disabled | keeper stays open; `S1` = true, `S2` = false; **no** capture reported | | |
| 7 | Enable capture with the probe seated | controller commands close; capture **not** claimed on `S1` alone | | |
| 8 | Keeper reaches its closed stop | `S1` and `S2` both true; capture confirmed; keeper tines under the Ø12 mm head, 4.2 mm slot around the Ø3 mm mast | | |
| 9 | Pre-cycle screens: 5 N axial for 10 s, then 1 N for 10 s in each of +X, −X, +Y, −Y | no release, no visible damage; five `pre_cycle` rows in the load CSV with `retained` = 1 | | |
| 10 | Run-in cycling, `phase` = `run_in`, ≥ 15 cycles, logging `insertion_force_n` and `release_force_n` every cycle | per-cycle force trend levels off across the back half of run-in; if it is still trending, extend run-in — do not start life cycles on a moving baseline | | |
| 11 | Life cycling, `phase` = `life`, to ≥ 600 cumulative cycles across sessions | every cycle logged; capture reported only with `S1` AND `S2`; forces stay on the run-in baseline | | |
| 12 | Unloaded emergency-release trials interleaved through cycling: ≥ 10 with `emergency_release_load_n` = 0 | keeper opens from whatever state it is in and the probe frees on the first command, every time | | |
| 13 | Loaded emergency-release trials: ≥ 10 with the 5 N axial load hung, `emergency_release_load_n` = 5.0 | drop zone called and clear; keeper opens under load and the probe frees on the first command; weight lands in the tray | | |
| 14 | Fault insertion, one row per trial, required response written **before** each insertion: `S1_OPEN`, `S1_SHORT`, `S2_OPEN`, `S2_SHORT`, `S1_S2_BOTH_OPEN`, `SERVO_POWER_LOSS`, `SERVO_STALL`, `CONTROLLER_RESET_DURING_LOCK` | each trial produces its written required response; `unsafe_state_entered` = 0 on every row; no capture is ever reported through an inserted fault | | |
| 15 | Post-cycle screens (repeat step 9 as `post_cycle`), then inspect funnel, probe base and mast, collet, keeper tines and guides, fasteners, switches, wiring, mount | screens identical to step 9; no cracks, permanent deformation, loosened fasteners, or intermittent indication | | |
| 16 | Reduce the four sheets: `python -m aiur.p0a_evidence --article … --cycles … --loads … --faults …` | verdict JSON; every P0-A criterion passes or the failing rows are named | | |

Instrumentation confirmed logging before step 5 (see the TRR block): `S1`, `S2`,
keeper command, controller state and fault reason, per-cycle insertion and
release force, applied screening load, bench kill state, and synchronized
monotonic timestamps. The relative-position, commanded-velocity, and aircraft
arm/disarm channels of the promotion contract do not exist at P0-A — insertion
is manual and there is no live aircraft. They are marked N/A here deliberately
and are first verified at P0-B; they are not quietly dropped.

## 6. Hazard analysis for this run

| # | Hazard | Cause | Worst credible outcome | Mitigation | Watched by |
| --- | --- | --- | --- | --- | --- |
| 1 | Stored energy released toward a person | spring collet unloading; a screening load released by keeper failure or during disassembly; the loaded emergency-release trials of step 13, which drop the 5 N weight **by design** | ejected part or falling weight strikes an eye or a hand | safety glasses within 2 m; loads hung on a lanyard over a padded catch tray, never hand-held, rigged with the shortest drop the fixture allows; "LOAD DROPPING" called and the drop zone confirmed clear before every loaded release; nobody in line with the keeper slot axis or under the weight while loaded; collet compressed only with the fixture bolted down | Safety Observer |
| 2 | Keeper crush / pinch, or actuator stall against a stop | fingers in the throat while powered; software position limits not set from the physical stops; commanded travel past the end stop; the deliberate `SERVO_STALL` and `SERVO_POWER_LOSS` fault trials (0.52 N·m stall, ≈1.5 A at 5 V) | crushed fingertip; stripped keeper guides or a burned actuator mid-campaign, ending the life test | bench supply current-limited before first motion; software limits established from the physical open/closed stops with the probe disconnected ([`p0a-fabrication.md`](p0a-fabrication.md)); "KEEPER MOVING" called before every motion; hands out of the funnel throat whenever the actuator rail is live; stall trials time-boxed and terminated by the supply limit, not by the actuator's thermal protection | Test Conductor |
| 3 | LiPo thermal event | Crazyflie pack left in the article, charged on the bench, or damaged in handling | fire on a bench holding printed polymer parts and hundreds of unattended cycles' worth of work | P0-A runs with the pack **removed** — coupon or aircraft with battery out; any charging happens off the test bench, attended, in a containment bag; pack ID, cycle count, and resting voltage logged before the session | Recorder logs; Safety Observer watches during powered periods |

Also carried, below the top three: a dropped fixture or dock assembly during
mount changes (mitigation — the fixture is bolted, changes happen unpowered and
unloaded), sharp printed edges in the approach volume (mitigation — the
print-acceptance inspection in [`cad/README.md`](cad/README.md)), and fatigue on
a long cycling session (mitigation — cycling stops at the end of the carded
session rather than "just finishing the hundred").

## 7. Abort criteria

ABORT safe state for P0-A: **the keeper holds its current state.** The TC stops
actuator motion, and any applied load is removed from the catch side before
anything else happens. A loaded keeper is never commanded open on an abort —
that converts a mechanism problem into a falling weight. The sole exception is
step 13, where release under load is the commanded test and is called in
advance.

KILL at P0-A: the Safety Observer opens the bench-supply master switch. The
servo rail de-energises, so the keeper cannot move in either direction; release
is therefore inhibited by construction. Closed keeper geometry is mechanically
stable and does not depend on servo holding torque, so a de-energised keeper
under load stays closed ([`p0a-fabrication.md`](p0a-fabrication.md)). Loads are
removed by hand before power is restored.

| Observation | Call | Required action |
| --- | --- | --- |
| Keeper moves without a command | KILL | de-energise; the run set stops (campaign stop rule: uncommanded keeper motion) |
| `S1` or `S2` flickers, or contradicts the visible mechanism, outside a fault-insertion trial | ABORT | stop the cycle set; log the cycle number; treat as ambiguous capture until explained |
| Keeper releases under a screening load outside step 13 | ABORT | stop; clear the catch tray; disposition before any further cycles |
| An inserted fault produces anything other than its written required response | ABORT | stop the trial series; `unsafe_state_entered` is a zero criterion, not a retry |
| Emergency release fails once, loaded or unloaded | ABORT | stop the run set; both failure counts are gate criteria at zero |
| Per-cycle insertion or release force departs from the run-in baseline | ABORT | stop cycling; the mechanism is changing; inspect before continuing |
| Visible crack, permanent deformation, or a loosened fastener | ABORT | stop; photograph in place before disturbing anything |
| Bench supply hits its current limit outside a `SERVO_STALL` trial, or the actuator is hot / smells | KILL | de-energise; do not re-power to "check"; inspect cold |
| Smoke, heat, or swelling from supply, actuator, or a battery pack | KILL | de-energise; clear the area; containment |
| A hand enters the funnel throat while the actuator rail is live | KILL | de-energise before anything else is discussed |
| Master kill switch fails its check, or the servo rail is not measurably dead | — | the session does not start; no run |
| Any campaign stop rule in [`engineering-loop.md`](../../docs/engineering-loop.md) is met | ABORT, then KILL if unresolved | stop the run set; return to the lowest stage that can expose the failure |

## 8. Post-run

| Field | Value |
| --- | --- |
| Run-in cycles this session / cumulative; force trend stabilized (y/n) | |
| Life cycles this session / cumulative | |
| Emergency-release trials, unloaded: trials / failures | |
| Emergency-release trials, loaded at 5 N: trials / failures | |
| Fault-insertion trials this session: modes exercised / unsafe responses | |
| Keeper close / open force margins at `margin_supply_voltage_v` | |
| Screens complete this session (`pre_cycle` / `post_cycle`; AXIAL, +X, −X, +Y, −Y) | |
| Reducer verdict (`aiur.p0a_evidence`) | |
| Outcome | |
| Disposition (exactly one, per `engineering-loop.md`) | |
| Calls made (call, time, caller, cause) | |
| Anomalies, including ones that did not stop the run | |
| Evidence files written | |
| Next action / re-entry stage | |
| TC signature / SO signature | |

Measurements the twin wants back from this campaign, if the session produced
them: keeper travel time distribution, switch debounce and bounce duration,
per-cycle insertion/release force trend, and the as-built throat/head and
slot/mast fits ([`docs/digital-twin.md`](../../docs/digital-twin.md)).

## Test readiness review — P0-A

Chaired by someone who is not the person who built or printed the article. Run
at the start of the campaign and again after any change to the configuration
identity; the shortened per-session form is the same list re-walked with the
article in front of the crew.

Gate: P0-A   `run_id`: ______   Chair: ______   Date: ______

- [ ] Objective and every numeric criterion in section 4 written on this card,
      transcribed from `GATES["P0-A"]` at the git SHA in the identity block and
      checked against it today.
- [ ] Run sequence read through by the chair; every step has an expected
      observable; the fault-insertion required responses are written **before**
      the trials, not after.
- [ ] Configuration identity frozen: git SHA, config hash, dock/probe serials,
      material lot, actuator ID and position limits, cumulative cycle count.
- [ ] Instrumentation verified live before cycle 1 — each channel seen changing
      in the log, not merely present:
  - [ ] `S1` probe-seat state
  - [ ] `S2` keeper-closed state, independent of the servo command
  - [ ] keeper/servo command
  - [ ] controller state and fault reason
  - [ ] per-cycle insertion and release force
  - [ ] applied screening load and duration
  - [ ] bench kill/rail state
  - [ ] synchronized monotonic timestamps across controller, force, and load logs
  - [ ] N/A at P0-A, first verified at P0-B: relative `x/y/z` and validity,
        relative and commanded velocity, drone arm/disarm
- [ ] Force margins measured and recorded (step 3); both ≥ 2.0 at the recorded
      minimum supply voltage.
- [ ] Campaign stop rules read aloud from `engineering-loop.md`; the P0-A stop
      conditions in [`p0a-bench.md`](p0a-bench.md) read aloud.
- [ ] Section 6 hazards reviewed with the named watcher for each; safety glasses
      present for everyone; lanyard, catch tray, and drop zone rigged and clear.
- [ ] Abort phraseology briefed, including the P0-A safe state ("keeper holds,
      load comes off first") and its step 13 exception; every crew member says
      both calls aloud once.
- [ ] Dress rehearsal done this gate, unpowered: ABORT response, KILL actuation,
      manual release of a captured probe by hand.
- [ ] Kill path checked end-to-end this session with the bench controller
      powered off, confirmed dead by meter, not by an indicator LED.
      Call-to-de-energised time: ______ s (engineering target ≤ 3 s).
- [ ] Fault-insertion unit checked on the bench before it is connected to the
      article: each insertion point does what its label says.
- [ ] Crew roles assigned by name in section 2; the Safety Observer is not the
      operator and is not holding the load.
- [ ] Bench area clear: nothing overhead, egress clear, no unbriefed person in
      the room, fixture bolted down.
- [ ] Batteries logged and inspected — for P0-A this means confirming the pack
      is **out of the article** and that no pack is charging on the test bench.

Any unchecked box stops the session.
