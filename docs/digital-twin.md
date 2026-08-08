# CARRIER-P0 digital twin

Status: executable SIL stage, uncalibrated against flight hardware
Scope: CARRIER-P0 through P0-D, plus vertical concept studies

The engineering loop's first stage — "SIL / model + fault injection" — is now
software, not a diagram box. `aiur/sim` is a deterministic, dependency-free
simulation of the carrier, aircraft, sensing, and recovery dock that runs
Monte Carlo campaigns and closes SIL gates before an article revision earns
bench time.

Everything here is a statement about the model until the calibration ledger
below says otherwise. A SIL pass is necessary to proceed, never sufficient.

## What is real and what is modeled

The twin's value depends on where the simulation boundary sits.

Real code, identical to what the article will run:

- `aiur.dock_controller.DockController` — the twin drives the actual latch
  state machine through simulated switches and servo. It is never mocked.
- `aiur.loop_graph.evaluate_gate_definition` — SIL gates are evaluated by
  the same missing-evidence-fails evaluator as the hardware gates.
- `aiur.sim.guidance.TerminalGuidance` — the terminal guidance and safety
  supervisor are written as the flight-software candidate, not as test
  scaffolding. Porting them to the vehicle is the intent.

Modeled (all parameters are engineering estimates until calibrated):

| Model | Module | Approach |
| --- | --- | --- |
| Micro-UAV | `sim/bodies.py` | velocity-command tracking, accel limit, linearized wind drag, battery countdown |
| Carrier | `sim/bodies.py` | neutrally buoyant point mass, added-mass allowance, thrust-limited station-keeping PD, ground tether, envelope keep-out ellipsoid |
| Bench rig | `sim/bodies.py` | programmed dock motion (SIL-P0-B article) |
| Air motion | `sim/disturbances.py` | mean flow + per-axis Ornstein-Uhlenbeck fluctuation |
| Positioning | `sim/sensors.py` | Gaussian noise, latency buffer, dropouts, injectable bias |
| Switches/servo | `sim/sensors.py` | debounce, stuck faults, finite travel, jam |
| Dock mechanics | `sim/dock_physics.py` | funnel acceptance/taper, rim-annulus prop contact, overspeed bounce, collet pull-out, keeper cam/blocking window |

Known missing physics, flagged for bench correlation: vehicle attitude
dynamics, propeller downwash recirculating off the hull during terminal
approach, aero interaction between aircraft, envelope deformation, any
systematic (non-white) positioning error structure, and the carrier trim
transient on capture/release — a 37 g aircraft changes carrier dead weight
by ~0.36 N, more than the modeled 0.3 N vertical thrust budget, so the real
vehicle must re-trim across every cycle while the twin assumes it already
has.

## Determinism contract

Identical `(config, seed)` pairs produce identical episodes, byte for byte.
All randomness flows from per-subsystem children of the episode seed; the
engine never reads the wall clock. This is what makes a campaign an evidence
packet: any episode in a report can be replayed exactly from its seed.

## SIL gate ladder

SIL gates mirror the hardware gate ladder and are evaluated through the same
evaluator (`aiur/sim/gates.py`). They deliberately demand more than the
bench: simulation is cheap, so the sample sizes are larger and every gate
carries a fault-injection quota.

| Gate | Mirrors | Scenario | Key criteria |
| --- | --- | --- | --- |
| SIL-B | P0-B | `sil-p0b` moving suspended dock | ≥200 episodes; ≥95% nominal captures; ≥50 fault episodes; zero strikes/contacts/unsafe outcomes |
| SIL-C | P0-C | `sil-p0c` tethered carrier, full launch/sortie/recovery cycle | same, over the complete cycle |
| SIL-D | P0-D | `sil-p0d` two aircraft, sequential dock use | ≥50 sequences; ≥90% success; zero separation violations or simultaneous approaches |

Fault episodes inject one drawn fault per episode (aircraft or dock pose
dropout, pose bias, stuck seat switch open/closed, keeper servo jam, gust,
battery sag). A fault episode is not required to capture; it is required to
end safely. The safety metrics are absolute zeros at any campaign size.
Only episodes whose fault actually activated count toward the fault quota —
a window that never opened tested nothing — and the reducer additionally
reports `false_capture_confirmations` (the controller announcing a capture
with no aircraft in the mechanism) for dock-integrity visibility.

Run them:

```
python -m aiur.sim.campaign --scenario sil-p0b --episodes 200 --seed 1
python -m aiur.sim.campaign --scenario sil-p0c --episodes 200 --seed 1
python -m aiur.sim.campaign --scenario sil-p0d --episodes 80  --seed 1
```

Exit code 0 is a passing gate. CI runs SIL-B at full size on every push.

## Vertical concept studies

Two sweep studies feed the dual-use concept work in `docs/verticals/`:

```
python -m aiur.sim.campaign --scenario outdoor-gust-sweep   --episodes-per-bin 30
python -m aiur.sim.campaign --scenario degraded-sensor-sweep --episodes-per-bin 30
```

Model findings as of 2026-08-08 (seed 1, 30 episodes/bin; simulation
results, not vehicle performance):

- **Outdoor wind**: capture rate for the P0-scale article is 100% in calm
  air, ~90% at 0.5 m/s mean wind, ~10% at 1.0 m/s, and 0% at 1.5 m/s and
  above — where the tethered carrier also becomes a hazard to its own
  aircraft, drifting faster than the evasion reflex can escape. This is the
  executable form of the claim that outdoor operation is a scaling
  milestone (SHARED-002 in the verticals portfolio), not a software patch.
- **Degraded sensing**: with FDIR thresholds retuned to the sensor spec,
  capture survives 10× Lighthouse-grade noise at 100%, and degrades to
  ~63% with heavy abort churn at 30× (σ ≈ 90 mm, the scale of the funnel
  radius). Toy-grade or GNSS-grade terminal navigation therefore demands
  either a better relative sensor or a larger capture funnel (SHARED-001).

## Twin-derived engineering findings

Findings the twin has already produced that constrain the hardware program:

1. **Latch the capture enable.** The dock controller treats a de-asserted
   `capture_enable` during LOCKING as a lost probe (correctly). A guidance
   stack that gates the enable on a noisy per-sample seat estimate will flap
   the controller into `FAULT_OPEN`. The enable must be edge-gated by a
   tight seat confirm and then latched. This is a firmware requirement for
   the bench article, discovered as a 9% capture-rate loss in SIL-B.
2. **A stuck seat switch defeats S1 AND S2 without a plausibility gate.**
   With S1 stuck closed, the controller will confirm a capture the moment
   the keeper closes, regardless of where the probe is. The supervisor must
   refuse to enable capture — and above all refuse to disarm — unless its
   own relative estimate places the probe at the seat. With the gate in
   place, every stuck-switch campaign ends in a safe abort or a genuine
   capture.
3. **Single-source relative navigation cannot detect a persistent bias.**
   The jump detector catches step anomalies — including across measurement
   gaps, where the threshold widens by plausible own-motion so a bias that
   arises during a dropout is still caught on recovery — and quarantines
   the approach. But a bias that ramps slowly, or hides under a long gap at
   transit speed, is invisible from inside one positioning system and can
   walk the aircraft toward the funnel rim. Residual risk for P0 as
   instrumented; a second terminal sensing modality (or the funnel's
   mechanical tolerance) is the mitigation. Carried in the risk register,
   not waved away.
4. **The carrier can overrun its own aircraft.** Under wind, a tethered
   buoyant carrier sweeps through nearby airspace faster than a
   station-holding micro-UAV expects. Guidance needs the hull-proximity
   evasion reflex even indoors, and outdoor station placement is a real
   planning constraint, not a nicety.
5. **A double fault defeats every software gate.** A stuck-closed seat
   switch combined with a masked navigation bias can walk the real
   controller to a confirmed capture on an empty dock, and no supervisor
   built on the same biased measurements can tell. Software cannot close
   this; the dock can. Rev-B candidate: make the keeper's closed position
   discriminate "closed on probe" from "closed on empty throat" (position
   or current sensing), giving the system one signal that no navigation
   fault can spoof. Until then this is a documented residual accepted for
   the single-fault P0 test regime.

## Calibration ledger and sim-to-real contract

Every model parameter carries one of three provenance states:

- `vendor` — from a published component specification (cited in
  docs/prototype-p0.md);
- `estimate` — engineering estimate, the default for every dynamic
  coefficient today;
- `measured` — replaced by a measurement from a bench or flight campaign,
  with the run identity recorded.

The promotion rule that keeps the twin honest:

1. Each hardware gate campaign (P0-A onward) records the promotion-contract
   telemetry defined in docs/engineering-loop.md.
2. After the campaign, the matching twin scenario is replayed with measured
   parameters substituted (switch debounce and timing from P0-A cycling,
   servo travel time, dock mass properties, draft levels, positioning
   residuals, funnel entry dispersion and closing speeds from P0-B).
3. The twin must reproduce the hardware campaign's outcome statistics —
   capture rate, abort rate, closing-speed distribution — within tolerances
   declared before the replay.
4. Divergence is a `FAIL_MODEL` disposition in the engineering loop: the
   model is corrected before the next SIL gate result is trusted.

Until step 3 has happened at least once, every number in this document is a
model claim. The twin's current role is to kill unsafe software and absurd
concepts cheaply — it has already done both — not to predict hardware
success rates.

## Interpretation notes

- The SIL-P0-D scenario encodes a specific interpretation of the P0-D gate
  for a single active dock (launch, hand off, recover one at a time, ground
  the surplus aircraft); see `aiur/sim/scenarios.py`. Revisit when a second
  dock exists.
- Fault menus and windows live in `aiur/sim/faults.py`; extending the fault
  set (comms loss between carrier and aircraft, partial servo travel,
  simultaneous faults) is standing work, and every new fault kind must keep
  the unsafe-outcome zeros.
