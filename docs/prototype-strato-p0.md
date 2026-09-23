# STRATO-P0 prototype specification

Status: pre-alpha engineering definition  
Source review: 2026-09-19

## Objective

STRATO-P0 is a flight-test article, not a scale model of a persistent
observation platform.

It exists to answer the program's new highest-risk question:

**Can a small, cheap, legally exempt package climb into the stratosphere,
observe the ground from there with a stated resolution, report what it sees,
and come back — twice, in the same configuration?**

There are no aircraft, no dock, no release, and no deployable payload. The
package observes and returns. Everything that made CARRIER-P0 hard — the
recovery interface, the two aircraft, the belly dock — is out of scope, and
the machinery built for it (executable gates, requirement closure, hazard
log, evidence contract) is kept and re-pointed at the new article.

## Two regimes, one model

The program distinguishes two ways to be in the stratosphere, and P0 uses
the cheap one:

| Regime | Envelope | What it does | Program stage |
| --- | --- | --- | ---: |
| Sounding | latex, constant gas mass | climbs at ~4–5 m/s until it bursts at ~30 km; ~1.5 h aloft; ~30 min above 20 km | **STRATO-P0 (funded)** |
| Float | fixed-volume superpressure or zero-pressure | stops where its buoyancy runs out and stays for days | STRATO-P1 (gated on P0) |

Both are in the executable model, [aiur/strato.py](../aiur/strato.py), so
the float article is sized from the same atmosphere the sounding flight is
predicted with. `python -m aiur.strato` regenerates every number below.

## Reference flight article

| Property | Reference value | Nature |
| --- | --- | --- |
| Balloon | 1200 g latex, ~8.6 m burst diameter | vendor figure for the size class; the lot sheet governs |
| Lifting gas | helium only | program rule |
| Payload package | ≤ 1.0 kg allocation; 850 g baseline | engineering allocation |
| Regulatory ceiling | 1.814 kg (4 lb single package) | program's reading of 14 CFR 101.1(a)(4) |
| Free lift | 0.9 kg | engineering target |
| Predicted launch ascent rate | ~4.5 m/s | model, C_d = 0.3 assumption |
| Predicted burst altitude | ~33.8 km | model, standard atmosphere |
| Predicted time to burst | ~90 min | model |
| Ambient at 20 km | −56.5 °C, 55 hPa, 0.089 kg/m³ | 1976 standard atmosphere |

Vendor figures are design inputs, not Aiur test results. The standard
atmosphere is a reference condition, not a forecast: a launch-day sounding
replaces it for the pre-launch prediction.

## Observation

"Pure observation" is a geometry statement before it is a sensor choice.
From the 20 km threshold:

| Quantity | Value |
| --- | ---: |
| Straight-line horizon | 505 km |
| Visible cap area | ~800,000 km² |
| Reference optic | Sony IMX477 1/2.3-inch sensor (1.55 µm pixels, published) behind a 16 mm M12 lens |
| Nadir ground sample distance | 1.94 m |
| GSD at 45° off-nadir | 3.88 m |
| Single-frame swath | 7.9 km × 5.9 km |

The reference optic is the Rev-A BOM candidate
([hardware/strato/bom.csv](../hardware/strato/bom.csv)). The point of
checking it in the model is that the obvious cheap choice fails: a stock
Camera Module 3 (1.4 µm pixels, 4.74 mm lens) gives ~5.9 m at 20 km and
misses the ≤ 3.0 m target (S0-OBS-002). Resolution is then *measured* on a
ground target after the first flight rather than quoted from the lens sheet.

Observation frames only count toward a gate when they carry a valid
position tag and were captured above the threshold (S0-OBS-001). A pretty
picture with no altitude is concept art.

## The prototype

The Rev-A flight package is defined in
[hardware/strato/](../hardware/strato/README.md): a six-panel XPS foam
box from a [generated cut sheet](../hardware/strato/cad/generated/strato_package_rev_a_cut_sheet.svg)
with the load line running around it, an IMX477 imager behind a Ø30 mm
port, a GNSS patch under a foam-only lid, a LoRa telemetry radio, four
lithium AA cells on the main bus, and — on their own cells — an
independent tracker, a hardware termination timer, and a nichrome cutdown.
The [BOM](../hardware/strato/bom.csv) marks every figure as published or
allocated; nominal masses sum to roughly 430 g against the 850 g baseline.

The package's logic is [aiur/flight_supervisor.py](../aiur/flight_supervisor.py),
flown in [aiur/strato_sim.py](../aiur/strato_sim.py) through the ascent
model with the hazard log's fault menu, and reduced to the S0 gate
metrics by [aiur/s0_evidence.py](../aiur/s0_evidence.py). The
[S0-A test card](../hardware/strato/s0a-test-card.md) and the
[launch checklist](../hardware/strato/launch-checklist.md) are the
procedures that turn the same reducer's inputs from simulated into flown.

## Payload package mass budget

Use the program's own 1.0 kg allocation as the ceiling and the 4 lb
regulatory limb as a hard stop the package must never approach.

| Item | Allocation |
| --- | ---: |
| Imager module + lens | 120 g |
| Flight computer + IMU + GNSS | 60 g |
| Telemetry: primary radio + independent tracker | 90 g |
| Lithium primary battery | 150 g |
| Enclosure + insulation | 180 g |
| Parachute + rigging | 120 g |
| Flight termination (cutdown) | 40 g |
| Wiring + mounting reserve | 90 g |
| **Total baseline allocation** | **850 g** |
| Allocation reserve | 150 g |

Every figure is an allocation to be replaced by a scale reading against
the article identity. The GNSS receiver must be one that reports above the
altitude limits consumer receivers impose; that is a procurement
requirement, not an assumption.

## Survival

| Concern | Model | Gate |
| --- | --- | --- |
| Cold | −56.5 °C at 20 km; −40 °C at burst | S0-A cold soak ≤ −55 °C for ≥ 3 h, zero dropouts |
| Power | 4 W × 3 h × 1.5 margin ÷ 0.6 cold derate = 30 Wh | S0-PWR-001; the derate is measured on S0-A |
| Landing | canopy sized for ≤ 5 m/s at sea level (0.73 m² for 850 g) | S0-A drop test; S0-B deployment aloft |
| Termination | independent timer/radio path on its own power | S0-A/B/C: ≥ 10 trials, 0 failures, works with the computer off |

## Airspace and law

The program's reading of 14 CFR 101.1(a)(4) is that an unmanned free
balloon whose single payload package weighs 4 lb or less, whose combined
packages weigh 12 lb or less, and whose suspension separates below 50 lbf,
is outside Part 101 Subpart D. The program uses the 4 lb limb as its hard
ceiling and deliberately does not use the weight/size-ratio limb that would
permit heavier packages.

That reading is not legal advice and it applies to U.S. airspace only.
Whatever the launch jurisdiction requires — notice, NOTAM, authorisation —
is on file before release, with the launch window and predicted trajectory
attached (S0-SAFE-005). No coordination, no release. The launch site is
chosen so the predicted landing ellipse is over open ground, and the
prediction file is committed before the balloon is filled.

## Test gates

### S0-A — payload bench and cold chamber

The complete flight package, on a bench and then in a cold chamber.

Pass:

- measured package mass ≤ 1.814 kg;
- ≥ 3 h cold soak reaching ≤ −55 °C internal, with zero imaging, tracking,
  or termination dropouts;
- ≥ 100 end-to-end image captures stored and thumbnailed during the soak;
- ≥ 10 telemetry link trials with zero failures;
- ≥ 10 flight-termination trials with zero failures, and termination
  demonstrated with the payload computer powered off;
- drop-tested descent rate ≤ 5.0 m/s under the flight canopy.

### S0-B — tethered ascent

The flight configuration on a tether at the height the site and the
jurisdiction permit.

Pass:

- ≥ 3 tethered ascents;
- ≥ 30 images captured aloft and received on the ground;
- no position-report gap longer than 60 s;
- termination fired aloft with the parachute deploying, zero failures;
- zero contacts between the balloon, line, or package and a person;
- termination criteria repeated in the flight configuration.

### S0-C — stratospheric sounding

Free flight. Only after S0-B passes.

Pass:

- ≥ 2 free flights of the same configuration;
- maximum altitude ≥ 20,000 m by GNSS;
- ≥ 50 geotagged observation frames above the threshold per flight;
- no telemetry gap longer than 300 s;
- package recovered with its imagery intact;
- landing within 15 km of the pre-launch prediction;
- airspace coordination on file before release;
- zero third-party contacts;
- termination criteria repeated in the flight configuration.

The executable form of these gates is `STRATO_GATES` in
[aiur/loop_graph.py](../aiur/loop_graph.py), the requirements they close
are `S0-*` in [aiur/requirements.py](../aiur/requirements.py), and the
hazards they mitigate are `HAZ-013` through `HAZ-017` in
[aiur/hazards.py](../aiur/hazards.py). CI validates all three on every push.

## STRATO-P1 — float

After S0-C, the observation becomes persistent. The model already sizes it:
a 3 kg gross float article at 20 km needs a ~39 m³ envelope and ~0.5 kg of
helium, and a 12 W continuous load closes its day/night power balance with
0.5 m² of 20 % cells and a 300 Wh battery at a mid-latitude equinox — and
does not close in a 6 h winter day with a 120 Wh battery. Those are the
first two trades P1 has to win, and they are already executable.

P1 is gated, not scheduled. It gets no envelope until S0-C is boring.

## Explicit non-goals

STRATO-P0 does **not** attempt float, station-keeping, propulsion, hydrogen
lift, a deployable payload, any aircraft, real-time video, onboard
autonomy beyond termination logic, or operation outside daylight and a
coordinated launch window.

## Exit criterion

STRATO-P0 is complete when reaching the stratosphere, observing from it,
and coming back are boring — two flights, one configuration, every gate
row green.
