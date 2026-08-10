# P0-A bench article

Status: build definition, not measured hardware  
Gate: P0-A — bench capture  
Flight condition: **propellers removed**

P0-A proves the mechanical and electrical truth of the recovery interface before any live approach. The result is not “the latch worked once.” The result is a repeatable evidence packet showing that the probe can enter, the keeper can positively retain it, capture indication cannot lie trivially, and an operator can release it every time.

![P0-A dimensioned cross-section](p0a-rev-a.svg)

The drawing predates Rev-B: its funnel, throat, belt, and mast dimensions
are unchanged and correct, but it does not show the Ø9 seat, the 5.2 mm
slot, the 5.0 mm tine reach, or the 13.0 mm stroke. Build from the table
below.

## Rev-B geometry

Build Rev-B. These dimensions are a first article for fit testing, not
production interface control dimensions, but they are not arbitrary either:
the four marked **Rev-B** were derived together in
[`aiur/tolerance.py`](../../aiur/tolerance.py) and changing any one of them
in isolation reopens a stack that Rev-A failed. Regenerate parts from
[`cad/generate_rev_a.py`](cad/generate_rev_a.py), which holds these as
`REV_B` and prints them into the manifest.

| Feature | Target | Why |
| --- | ---: | --- |
| Funnel mouth | Ø180 mm | Existing P0 capture-envelope target |
| Funnel throat | Ø16 mm | Guides the Ø12 mm probe belt into the keeper |
| Funnel depth | 65 mm | Keeps the funnel shallow enough to preserve rotor-plane standoff |
| Funnel wall | 1.2 mm nominal | Printable starting section; weigh the real part |
| Probe belt | Ø12 mm rounded | What the funnel taper guides; never touches the keeper |
| **Probe seat** | **Ø9 mm** (Rev-B) | The lower cylinder the keeper actually bears on. Rev-A used Ø6 and the retention ledge vanished at worst case |
| Probe mast | Ø3 mm nominal | Keeper slot surrounds the mast; the ledge does the retaining, not friction |
| **Keeper slot** | **5.2 mm** (Rev-B) | Clears the mast at worst case. Rev-A's 4.2 mm could bind |
| **Keeper tine reach** | **5.0 mm** (Rev-B) | Past the dock axis. Sets the stroke needed to release; still fully bears the Ø9 seat |
| **Keeper open travel** | **13.0 mm** (Rev-B) | Rev-A commanded 11.0 mm while its geometry needed 13.62 mm and could not release at all |
| Keeper thickness | 2.5 mm | Bearing face under the seat |
| Probe tip above prop plane | 110 mm nominal | Creates vertical separation between funnel lip and rotors |
| Dock-side assembly | ≤180 g | Existing carrier mass allocation |
| Drone-side probe assembly | ≤8 g | Existing aircraft-side allocation |
| Bench adapter | 4 × M3 on 40 mm square | Bench fixture interface only; not the final carrier rail ICD |

Two diameters on the probe head do different jobs and are easy to conflate.
The **belt** is the widest point and is what the funnel guides. The **seat**
is the lower cylinder, and it is the only part the keeper touches. Growing
the seat is what bought the retention margin; the belt did not change, so
the funnel interface is unaffected.

Rev-A remains constructible from the same generator (`REV_A`) so its
failures stay reproducible. Do not build it.

The probe base must contain a deliberately sacrificial feature so a bad side-load damages a replaceable probe part before the Crazyflie PCB. The breakaway load is **TBD by physical test**; do not invent a production value from CAD.

## Clearance sanity check

Bitcraze currently specifies the Crazyflie 2.1 Brushless at a 100 mm diagonal motor-center frame size with 55 mm propellers. The current guard-equipped takeoff weight is 37 g.

Source: https://www.bitcraze.io/products/crazyflie-2-1-brushless/

Using the motor-center radius plus prop radius gives a conservative radial swept extent of approximately:

`50 mm + 27.5 mm = 77.5 mm`

The Ø180 mm funnel has a 90 mm mouth radius, leaving only 12.5 mm of coplanar radial clearance. **Therefore the design must not rely on the drone fitting through the funnel mouth.** The probe standoff keeps the propeller plane below the lip.

With a 65 mm funnel depth and 110 mm probe-tip standoff, the centered seated geometry has about 45 mm nominal vertical separation between the funnel lip and propeller plane. At 15° vehicle tilt, a 77.5 mm radial extent can rise roughly 20 mm, leaving about 25 mm nominal clearance. This is a geometry sanity check only. P0-B must verify the actual aircraft including prop guards, probe flex, manufacturing tolerance, and attitude excursions before live capture.

## Mechanical stack

The carrier-side mechanism has four jobs, in order:

1. Funnel converts lateral error into probe centering.
2. `S1` independently detects that the probe is physically seated.
3. Servo moves a positive keeper underneath the probe head's Ø9 seat.
4. `S2` independently detects the keeper's closed position.

The spring collet that used to sit between steps 1 and 2 is **deleted**. A
passive backstop would need 0.468 N to hold the docked aircraft while
staying under 0.074 N so it does not fight an abort — 6.3× apart, so no
single spring is both. Its useful function was registration, and that
merges into the throat and slot geometry. See the
[deletion review](../../docs/dock-deletion-review.md); reinstate only if A0
measures free-probe wander above 0.60 mm, which is what the Rev-B 5.2 mm
slot tolerates.

`capture_confirmed = S1 AND S2`.

Servo command is **not** keeper feedback. `S2` must sense the mechanism itself with a limit switch or equivalent physical position sensor.

The positive keeper owns retention outright; nothing passive backs it up, which is why the keeper's own force margin and its stroke are both gate criteria rather than nice-to-haves. An electromagnet is not part of the primary load path.

## Controller behavior

The reference state machine is [`aiur/dock_controller.py`](../../aiur/dock_controller.py).

| Situation | Required behavior |
| --- | --- |
| Probe not seated | keeper commanded open |
| `S1` seats while capture is enabled | command keeper closed; do not claim capture yet |
| `S1` + `S2` true | capture confirmed |
| Probe lost before confirmed capture | fail open so the approach can abort |
| Sensor disagreement after confirmed capture | fail locked; software must not drop a docked aircraft |
| Normal release | command open, then wait for physical separation |
| Emergency release | commands open from every software state |

The 1.0 s lock/release timeouts in the reference controller are initial bench configuration, not certified limits. Measure the actuator distribution across the cycle test and tune before P0-B.

## Bench fixture

Mount the dock vertically with the funnel facing down from a rigid plate. The plate reacts load; nothing in P0-A is attached to the helium envelope.

Use a probe coupon or the real aircraft with battery removed and propellers removed. Manual insertion is sufficient for P0-A. The later P0-B rig introduces relative motion.

Instrument at minimum:

- `S1` probe-seat state;
- `S2` keeper-closed state;
- keeper command;
- controller state and fault reason;
- monotonic timestamp;
- applied retention screening load;
- measured dock mass and probe mass.

Record article identity/mass/force-margins in [`p0a-article-template.csv`](p0a-article-template.csv), every capture/release cycle in [`p0a-run-template.csv`](p0a-run-template.csv), the pre/post screening loads in [`p0a-load-template.csv`](p0a-load-template.csv), and every inserted electrical fault in [`p0a-fault-template.csv`](p0a-fault-template.csv). Keep one `run_id`, hardware revision, and Git commit across the evidence set.

Run the campaign against a printed [test card](p0a-test-card.md); the [test-card rules](../../docs/test-cards.md) define crew roles, abort phraseology, and the readiness review that gates run 1.

## Why the cycle count is what it is

The life-test requirement is derived, not chosen. `aiur/loop_graph.py`
itemizes the capture/release cycles the Rev-A article must survive to carry
the program through P0-D (bench development, P0-B and P0-C run sets with
retries, P0-D sequences, contingency ≈ 300 cycles) and multiplies by a life
factor of 2.0, giving **600 life-test cycles**. Mechanism practice treats an
un-multiplied count as a demonstration rather than a life test.

Run-in comes first and is separate: a fresh printed mechanism wears in, so
the first cycles are recorded as `phase=run_in` with per-cycle insertion and
release force. The gate requires that force trend to level off before life
cycling starts — a mechanism still bedding in has not shown its steady-state
behavior, and cycling it is measuring the wrong thing.

## Force margin

Holding a load proves retention. It does not prove the actuator can still
work when everything is against it. Before cycling, measure keeper
breakaway/running force at worst case — minimum supply voltage, worst
expected side load on the probe — and record:

```
keeper_close_force_margin = available drive force / worst-case resistance
keeper_open_force_margin  = available release force / worst-case resistance
```

Both must be ≥2.0. An actuator that closes at margin 1.1 works on the bench
and fails on the vehicle when the battery sags or the funnel is dirty.

## P0-A procedure

1. Photograph and weigh the complete dock and complete aircraft-side probe.
2. Measure and record every as-built dimension in [`as-built-template.csv`](as-built-template.csv) before assembly.
3. Verify propellers are removed and the fixture cannot fall onto a person.
4. Measure keeper close/open force margin at minimum supply voltage and record both ratios.
5. Power the keeper with no probe present. Confirm `S2=false` when physically open.
6. Insert the probe without capture enabled; the keeper must remain open.
7. Enable capture, seat the probe, and verify `S1` alone does not report capture.
8. Close the keeper and verify capture is reported only when both `S1` and `S2` are true.
9. Apply a **5 N axial downward screening load for 10 s**. No release or structural damage is allowed.
10. Apply a **1 N lateral screening load for 10 s in +X, −X, +Y, and −Y**. No release or structural damage is allowed.
11. Complete **≥15 run-in cycles** logged as `phase=run_in` with insertion and release force per cycle. Confirm the force trend has leveled off before continuing.
12. Complete **600 life-test cycles** logged as `phase=life`. Every 25th cycle is an emergency-release trial; alternate them between unloaded and **loaded with the 5 N axial screening load applied**, giving ≥10 of each.
13. Run the [fault-insertion](p0a-fabrication.md) sequence: exercise every required fault mode (`S1_OPEN`, `S1_SHORT`, `S2_OPEN`, `S2_SHORT`, `S1_S2_BOTH_OPEN`, `SERVO_POWER_LOSS`, `SERVO_STALL`, `CONTROLLER_RESET_DURING_LOCK`, `CONTROLLER_RESET_WHILE_CAPTURED`), writing the required response **before** each trial and recording what actually happened.
14. Repeat the 5 N axial and 1 N four-direction lateral screening loads after life cycling.
15. Inspect the funnel, probe base, keeper, fasteners, switches, wiring, and mount for cracks, looseness, permanent deformation, or intermittent indication.
16. Reduce the raw run: `python -m aiur.p0a_evidence --article ... --cycles ... --loads ... --faults ...`.
17. On pass, freeze the article as the [golden article](golden-article.md).

The 5 N and 1 N loads are **P0 screening targets, not airworthiness/qualification loads**. A nominal guard-equipped aircraft with Lighthouse deck and the full 8 g probe allocation is about 47.7 g, so 5 N is roughly 10.7× its static weight. Future aircraft and outdoor operation require a real loads program.

## Loaded release

Ten unloaded emergency releases prove the servo moves. They do not prove the
mechanism releases when it matters, because galling, binding, and friction
lock appear under load. The gate therefore requires ≥10 emergency releases
performed with the 5 N axial screening load applied, with zero failures, and
records the applied load per trial so an unloaded release can never be
counted toward the loaded quota.

## Run to failure

After the gate closes, keep cycling the Rev-A article until something breaks
and record what broke and at what cycle. Nothing in P0 depends on this
result, and it is the cheapest way to learn the wear-out mode before it
appears on a vehicle. A printed article is a consumable; the knowledge is
not.

## Gate evidence

P0-A passes only when every executable criterion passes:

| Metric | Pass |
| --- | ---: |
| `run_in_cycles` | ≥15 |
| `run_in_force_trend_stabilized` | 1 |
| `life_test_cycles` | ≥600 |
| `dock_mass_g` | ≤180 |
| `probe_mass_g` | ≤8 |
| `axial_screen_load_held_n` | ≥5.0 N |
| `lateral_screen_load_held_n` | ≥1.0 N |
| `keeper_close_force_margin` | ≥2.0 |
| `keeper_open_force_margin` | ≥2.0 |
| `structural_failures` | 0 |
| `ambiguous_capture_confirmations` | 0 |
| `emergency_release_trials` | ≥10 |
| `emergency_release_failures` | 0 |
| `loaded_emergency_release_trials` | ≥10 |
| `loaded_emergency_release_failures` | 0 |
| `fault_insertion_trials` | ≥8 |
| `fault_insertion_unsafe_responses` | 0 |
| `propellers_installed` | 0 |

Use all four raw sheets above, then reduce them with:

```bash
python -m aiur.p0a_evidence \
  --article p0a-article.csv \
  --cycles p0a-cycles.csv \
  --loads p0a-loads.csv \
  --faults p0a-faults.csv
```

The reducer requires both pre-cycle and post-cycle screens for `AXIAL`, `+X`, `-X`, `+Y`, and `-Y`. A load is credited only when it is retained without structural damage for at least 10 s. Missing evidence is an evidence error, never an implied pass.

## Stop conditions

Stop the run and disposition the failure before continuing if:

- the keeper opens under a screening load;
- the probe or base shows cracking/permanent deformation;
- either switch flickers or contradicts visible mechanism state;
- the keeper moves without a command;
- emergency release fails once;
- a fastener loosens;
- wiring enters the funnel/probe load path.

After a design change, issue a new hardware revision and restart the relevant screening/cycle evidence. Do not append changed hardware to the same life-test run.
