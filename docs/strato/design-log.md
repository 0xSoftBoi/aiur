# STRATO design log

Each entry is one loop: a design, the model that broke it, and the change.
Commands reproduce the numbers. Nothing here has been measured on hardware;
every coefficient tagged `[estimate]` in the code is a bench test waiting to
happen (listed at the end).

## Rev A — scale up the P0 blimp

*Design.* The obvious move: the P0 indoor airship is a TPU envelope with an
air ballonet. Make it bigger.

*What broke.* Air at 20 km is 7.3 % of sea-level density. A ballonet that
keeps the hull taut all the way up must fill 93 % of it at launch, and
published allowances put a ballonet at +40 % of hull mass.

```
python -m aiur.strato.trades      # rev_a_scaled_p0
```

| Envelope | Volume | Length | Gross | Film |
| --- | ---: | ---: | ---: | ---: |
| TPU 50 µm + ballonet | 912 m³ | 30.4 m | 75 kg | 49 kg |
| TPU-coated ripstop + ballonet | 1,297 m³ | 34.2 m | 107 kg | 72 kg |
| **LLDPE 20 µm, flaccid launch** | **106 m³** | **14.8 m** | **8.7 kg** | **2.5 kg** |

Two thirds of Rev A is envelope, and TPU's glass transition is near −40 °C
in a −56 °C environment.

*Change.* Drop the ballonet. Launch 10 % full and let the gas fill the hull
(HiSentinel flew six times this way). Use balloon-grade polyethylene, the
only cheap film that is ductile at −80 °C.

## Rev B — what carries the bending?

*Question.* The brief calls for an air-framed airship. Should there be an
inflated keel?

```
python -m aiur.strato.trades      # airframe
```

For the S2 hull with all equipment in one gondola the bending moment is
227 N·m. An air-beam keel that carries it weighs 2.7 kg; a carbon tube,
5.5 kg. The hull itself, at 21 Pa, carries it for nothing — wrinkling moment
goes as p·r³, so the fattest tube on the vehicle wins by orders of
magnitude. Spreading the equipment along a spine cuts the moment to 51 N·m
against a 324 N·m capacity at the 20 Pa relief setting.

*Change.* The hull is the air frame. Air-beams are used where there is no
hull to lean on: the four fins. A fin beam sealed at 3 kPa on the ground
sits at 73 kPa gauge at 20 km, so each gets a relief valve — and the fins
are stiffest exactly when the hull has finally taken shape.

## Rev C — the float controller sank the vehicle

*Design.* Vent gas approaching the target altitude to arrive without
overshoot.

*What broke.*

```
python -m aiur.strato.ascent
```

The first runs reached 19.6 km and then sank to 16.6 km within the hour.
Trace: the controller vented while the gas was 9 K warmer than the air in
still conditions; at float the vehicle started flying at 3 m/s, forced
convection cooled the gas by 2 K, lift fell 0.9 %, and a slack cell has no
restoring force at all — it just keeps sinking.

*Change.* A zero-pressure hull is never vented early; it fills and spills,
which is self-regulating. Altitude is held by tilting the stern thrust
vector (`FloatController.trim`), with a 3 % droppable ballast reserve for
when trim saturates. Float then holds within ±30–80 m. Cost: the S1 hull
runs trim near full authority most of its hour at float, which is in the
energy budget but is the first thing to measure on a real flight.

## Rev D — the hull would not point

*Design.* Fins at 0.30 V^(2/3), the conventional airship ratio. One
gimballed stern thruster for control; no moving surfaces.

*What broke.*

```
python -m aiur.strato.flight6dof
```

![Handling vs fin size](img/handling-vs-fins.png)

| Fins / V^(2/3) | Open-loop time to 10° yaw | Gimbal saturated in 90° turn | Trim pitch |
| ---: | ---: | ---: | ---: |
| 0.30 | 5 s | 77 % | 36° |
| 0.45 | 7 s | 71 % | 33° |
| **0.60** | **14 s** | **25 %** | **6°** |
| 0.45 + ruddervators | 7 s | 1 % | 0° |

At 6 m/s the dynamic pressure is 1.6 Pa. The Munk moment scales with it and
so do the fins, but thrust-vector authority does not — it is 31 N·m, and
the Munk moment is about 430 N·m per radian. With small fins the pitch axis is
unstable too: the pendulum (CG about a metre below the hull axis) loses to Munk
above about 4 m/s.

*Change.* Fixed fins at 0.60. Ruddervators at 0.45 handle better, but they
put servos and hinges on inflated film at −60 °C; fixed fins keep every
actuator in the heated stern pod. Ruddervators stay on the list for S3.

*Also found.* A uniform gust does nothing to a neutrally buoyant hull — the
air accelerates the vehicle with it. The first gust test reported exactly
zero heading error. The disturbance is the gust *gradient* along the hull;
with that modelled, RMS heading error is 2° in 0.5 m/s turbulence and 7° in
1.5 m/s.

## Rev E — the first netlist failed thirteen checks

```
python -m aiur.strato.harness
```

- **Spine copper.** 5 V servo leads dropped 8 % over 4.5 m, and the real run
  from an amidships bay to the stern is 9.5 m. The ESC lead alone would have
  been ~0.9 kg of 12 AWG. *Change:* the stern pod carries its own pack,
  regulator and power monitor, and a DroneCAN node turns three PWM runs and
  two sense lines into one twisted pair. The pod is now a module on one
  connector, and losing propulsion power cannot brown out the autopilot.
  The autopilot moved from an F405 to an H743 board for the CAN port.
- **Cold.** DS18B20 probes stop at −55 °C. Outside probes are PT1000 RTDs
  read by amplifiers inside the heated bay.
- **Barometer.** The SPL06/BMP-class barometers on these boards are rated to
  300 hPa — about 9 km. An external MS5611 (rated to 10 mbar, 31 km) is the
  primary.
- **Termination cells.** Two cutters firing together exceeded what three AA
  lithium cells deliver. Six cells, 3S2P.
- **Independence.** The checker walks the conductive graph from the
  termination unit and must reach nothing else. It reaches nothing; the one
  crossing is an opto-isolated heartbeat.

## Rev F — the radio and the range fence

```
python -m aiur.strato.link
python -m aiur.strato.campaign --design S1-touch/hull --flights 120 --free-lift 0.15
```

- A 100 mW ELRS receiver has 10 dB of margin out to ~130 km. The vehicle is
  routinely 100 km away. *Change:* 1 W sub-GHz MAVLink module (589 km, i.e.
  to the horizon). The termination unit's LoRa link reaches the horizon at
  22 dBm. 5.8 GHz video does not close at 100 km without a tracking dish.
- At 15 % free lift the climb averages 2.4 m/s and takes over two hours. In
  the summer Monte Carlo 23–26 % of flights hit the 150 km range fence
  inside the jet stream and were cut down before float.

![Monte Carlo free lift](img/montecarlo-free-lift.png)

| Free lift | Reach float | Time to float (p50) | Landing range p50 / p90 |
| ---: | ---: | ---: | ---: |
| 15 % | 74 % | 126 min | 123 / 193 km |
| 30 % | 95 % | 98 min | 92 / 150 km |
| **45 %** | **99 %** | **86 min** | **80 / 130 km** |
| 60 % | 99 % | 79 min | 74 / 118 km |

*Change:* 45 %. The extra hydrogen is cents and spills at float. Winter
stays at ~20 % regardless — that is wind, not ascent rate.

## Rev G — overnight

```
python -m aiur.strato.trades      # overnight
```

The gas runs ~5 K warm by day and ~6 K cold at night. Sealed, that is a
450–600 Pa swing on a 5,500 Pa ambient.

| Approach | Closes? | Size | Note |
| --- | --- | --- | --- |
| Zero-pressure LLDPE 38 µm + ballast | yes | 390 m³, 32 kg | 1.9 kg of ballast per night; $3,840 |
| Superpressure, monolithic LLDPE/EVOH/PET | **no** | — | film would need 35–45 plies |
| Superpressure UHMWPE laminate | yes | 233 m³, 19 kg | envelope alone ~$10,500 |

*Decision.* S3 is not funded. The cheap way through is the one Loon took —
a tendon-reinforced (pumpkin) polyethylene envelope where load tapes, not
film, carry the pressure — and that is its own structural model and its own
test article. S1 and S2 are day flights and do not need it.

## Rev H — join the two models, and four things break

*Design.* Two simulations, each with a blind spot: the ascent model had
buoyancy physics but no attitude, the 6-DoF model had attitude but no
buoyancy. The ascent model held altitude with an abstract "trim thrust".

```
python -m aiur.strato.mission6
```

`mission6.UnifiedSim` flies launch to landing as one plant. The first run
stalled 500 m short of float, pitched to 24 degrees, saturated the gimbal
62 % of the time and spent all its ballast. Four separate causes:

| What the joined model showed | Cause | Change |
| --- | --- | --- |
| Hull held down at 19.3 km against 1 kg of free lift | Float controller braking the climb of a hull that had not finished spilling | Hold is disabled until the spill is over, then one-sided (lift only) against a reference that ratchets up with the hull |
| Altitude trim far weaker than assumed | Vertical force comes from pitching the whole hull: 8 degrees at cruise is worth ~0.25 of dash thrust, not the 0.6 assumed | Recalibrated; sustained up-trim is offloaded to ballast |
| Pitch diverging nose-up with the gimbal pinned | **Sign error**: stern side-force gives yaw moment -arm*Fy but pitch moment +arm*Fz, and the controller used the same sign for both. Pendulum stability hid it at zero pitch command | Fixed. Every earlier handling number for pitch was contaminated |
| Hull flying itself downward during float entry | Powered flight while still climbing at 3 m/s puts the hull at 45 degrees of incidence | Idle until climb < 1.2 m/s, then fly the flight-path angle |
| 9 degrees of standing pitch error | Munk, fins and pendulum nearly cancel in pitch at cruise: the airframe has no stiffness and a PD loop has no reason to return | Integrator on pitch only (one on yaw overshot 38 degrees on a turn) |

With the sign fixed the fin study changes its answer:

| Fins / V^(2/3) | Gimbal saturated in 90 degree turn | Overshoot | Same, fin lift slope 27 % lower |
| ---: | ---: | ---: | --- |
| 0.30 | 45 % | 83 deg | - |
| 0.45 | 2 % | 13 deg | 9 % / 22 deg |
| **0.50** | **1 %** | **8 deg** | **3 % / 19 deg** |
| 0.60 | 2 % | 2 deg | 3 % / 13 deg |

*Change.* Fins 0.50. S2 now holds 19.6-19.9 km at about 2 degrees mean pitch
with no ballast used.

## Rev I — measure the wind instead of estimating it

```
python tools/strato_winds.py --station GMM00010393 --cache <dir>
```

NOAA IGRA v2, 2005 onward, six stations, 88,857 soundings
([winds.md](winds.md)). Against the estimated tables:

| | Estimated p50 / p90 | Measured p50 / p90 |
| --- | ---: | ---: |
| Summer, 20 km | 6 / 12 m/s | 4.5 / 7.2 m/s |
| Summer, 12 km (jet) | 20 / 37 | 17.8 / 32.9 |
| Winter, 20 km | 15 / 28 | 20.2 / 36.8 |
| Winter jet peak | 36 / 62 at 11 km | 24 / 46 at 9 km |

Wind at 20 km is below 6 m/s on 80 % of summer days and 6 % of winter days.
The calm season is five months long, not a brief turnaround. Over Europe
there is no winter minimum-wind layer at all. *Change:* `WIND_PROFILES` is
the measured data. S2's 6 m/s is confirmed as the right airspeed for
summer; nothing at this size works in winter.

## Rev J — cut patterns correct the budget

```
python -m aiur.strato.patterns
```

Developing the hull into flat gores (area agrees with the smooth hull to
0.001 %) and nesting them on a film roll showed three budget errors:

- **Film purchased is 1.38x hull area**, not 1.18x. A gore fills 73 % of
  its bounding rectangle and nests badly.
- **Fins weigh 0.115 kg/m2**, not 0.085. Spar diameter is set by wrinkling
  under launch loads, not by fabric strength.
- **Twelve flat gores enclose 2.2 % less volume** than the smooth hull. Each
  gore is cut 1.1 % wider to recover it.

Net effect: S1 grew from 8.3 to 9.1 kg and $2,250 to $2,330.

## Rev K — the termination unit becomes firmware

```
make -C firmware/ftu/host clean test
```

`firmware/ftu` is C++ for an ESP32-S3 LoRa board. Its decision function
replays 29,318 test vectors generated from the Python `Geofence` with zero
mismatches, and an ESP32-S3 build links (nothing flashed). Writing it found
gaps in the hardware data, now fixed in the netlist:

- no cell-voltage sense line, so the under-voltage stop would have fired blind;
- no pull-downs on the cutter gates, which float through reset;
- no remove-before-flight plug in the cutter supply.

It also found that the documents claimed a heartbeat-loss criterion the
reference did not have. The firmware implements one (loss starts a 10 minute
timer rather than an immediate cut); see [ftu.md](ftu.md).

## Rev L — overnight is a net, not a laminate

```
python -m aiur.strato.trades      # overnight
```

Rev G concluded that monolithic film cannot hold the day-night pressure
swing. A tendon net can: UHMWPE lines carry the load and the film only
spans between them, so film stress depends on the mesh pitch (0.35 m), not
the hull radius.

| Approach | Size | Net | First unit |
| --- | --- | --- | ---: |
| Zero-pressure + 2 kg ballast per night | 404 m3, 33 kg | - | $4,060 |
| UHMWPE laminate | 241 m3, 20 kg | - | $17,600 |
| **Tendon-netted LLDPE 20 um** | **308 m3, 25 kg** | **1.6 km of line, 2.8 kg** | **$4,260** |

This is a sizing result, not a design: the net is 1.6 km of line to lay and
tape, the film-to-tendon bond is unspecified, and the lobed surface will
cost drag that is not yet modelled.

## Rev M — fault cases

```
python -m aiur.strato.faults
```

Nine cases on the unified plant (motor fails, gimbal jams, 3x turbulence,
fill errors, 90th-percentile wind). All end under parachute inside the
fence. One exposed a logic gap: in 3x turbulence the raw climb rate never
went quiet, the float manager never declared float, and the flight ran to
its time limit. The test is now on climb rate filtered over a minute, with
a ten-minute fallback.

## Rev N — fly the whole day, on a power bus

```
python -m aiur.strato.mission6 S2-dayloiter/hull --float-hours=10
```

Until now S2's "all daylight" was a sizing claim: one hour at float had been
flown, and energy was a budget line. The unified plant now carries a power
bus (array in from sun elevation and altitude; hotel and propulsion out,
propulsion from the propeller and motor models at the thrust actually
commanded) and flies ten hours at float.

| | Result |
| --- | --- |
| Station error | 48.2 km at float entry, 0.1 km at the end: it flies home and stays |
| Altitude | 19,849 m mean, 124 m sd; no ballast used |
| Battery | never below 64 %; full at the end |
| Energy | propulsion 287 Wh, hotel 295 Wh, array 923 Wh, of which 340 Wh had nowhere to go |
| Landing | 21.9 km from launch, against 60 km for the one-hour flight |

Two things follow. The array is about 35 % larger than this day needed,
which is the margin for a 90th-percentile wind day rather than an error.
And a long flight is *easier* to recover than a short one, because the
float-level wind in summer is weak enough to fly home in.

Caveat: the wind is a fixed profile for the whole day and the sky is clear.

## Rev O — which estimate could break it?

```
python -m aiur.strato.robustness
```

Each `[estimate]` pushed to a pessimistic bound, one at a time, on S2:

| Estimate | Pessimistic bound | Effect |
| --- | --- | --- |
| **Film sustained allowable** (seams, cold, creep) | 10 % of ultimate instead of 20 % | **Hoop margin 0.96: the hull fails.** The only single estimate that breaks the design |
| **Film solar absorptance** | 0.12 (dusty, sealant haze) instead of 0.03 | Gas runs 30 K warm instead of 8 K; all trim ballast is spent |
| Fin areal mass | 0.17 kg/m2 | +12 % gross (16.4 kg, 199 m3) |
| Film areal density | +20 % | +11 % gross |
| Fin lift slope | 1.4/rad instead of 2.2 | Turn overshoot 22 deg, gimbal saturated 12 %: flies, less tidily |
| Appendage drag | doubled | Cruise 64 W instead of 41 W; +2 % gross |
| Propeller low-Re L/D | x0.6 | Cruise 48 W; +0.5 % gross |
| Ascent drag of the slack hull | Cd 1.1 | 102 min to float instead of 79; lands 74 km out |
| Avionics mass and power | x1.5 | +2 % gross |

So the bench order is not the one guessed in Rev A-G. Seam strength and
creep at -60 C is first by a distance, film optics second, and both are
coupon tests costing almost nothing (SP0-A). Propeller efficiency, which
looked like the scary unknown, moves the design by half a percent because
propulsion is a small share of a vehicle that is mostly envelope.

## Rev P — smaller corrections

- **GNSS outage.** The bridge dead-reckons on barometric altitude and last
  ground velocity; a mission with a 20 minute outage at float completes
  (1,197 s dead-reckoned). Altitude hold never needed GNSS.
- **Suspended mass was over-counted.** The regulatory comparison counted
  fins and hull fittings as payload. The envelope is the balloon; what hangs
  from it is 3.6 kg (7.9 lb) on the S1 hull and 5.4 kg (11.9 lb) on the S1
  tandem. An `S1-lite` tandem at 4.25 kg (9.4 lb) is in the ladder for the
  regulatory conversation. None of this changes the fact that a powered
  airship is not a free balloon.
- **Netted hull drag.** +15 % on hull drag for the lobed surface, until a
  model is measured: S3 netted is 26.6 kg.

## Rev Q — the termination board, checked against its schematic

The firmware's pins had been written from memory. Checked against LilyGO's
schematics and pin files ([ftu.md](ftu.md) has the citations), four things
were wrong, three of them in the netlist rather than the firmware:

| Was | Is | Consequence if built as drawn |
| --- | --- | --- |
| Cutter gates on GPIO15/16 | GPIO38 and GPIO21 | 15/16 are the board's 32 kHz crystal and reach no header: unwireable |
| 3.3 V fed into the board's 3V3 pin | 5 V buck-boost into VBUS | That pin is a regulator *output*. The processor would run with the radio and GNSS rails dead: a termination unit with no position and no link |
| Barometer at I2C 0x77 | 0x76 | Collides with the BME280 already on the board |
| Sense divider 2 x 100 k | 100 k over 47 k | Firmware reads 1.56x high, rejects the reading and fires with no under-voltage stop |

Also: "hold BOOT at power-on" to clear flight state could never have worked
(GPIO0 held through reset enters the bootloader); the firmware now waits
for the press after reset. The BOM names the exact board build, because the
two other builds sold under the same name have a GNSS or radio the firmware
does not support. Both firmware environments build against the corrected
board definition. Nothing has been checked on a physical board.

## Rev R — fins in Gazebo

```
ros2 launch aiur_description gz_fins.launch.py
```

The fin size came from one model. Gazebo now has fins too (four `LiftDrag`
surfaces on the stock lighter-than-air hull), and 23 open-loop cases were
compared ([gazebo-fins.md](gazebo-fins.md)).

- **Where the two share hull assumptions they agree within 7-15 %**, and
  the gap is attributed: Gazebo's hull plugin has no yaw-rate damping and
  double-counts an added-mass term. The fin models themselves agree to
  0.5 %. With drag off, the in-repo integrator matches Gazebo's physics
  engine to 1 %.
- **Where they differ in kind, the in-repo model is the conservative one.**
  It applies the full Munk moment; the plugin's hull model lets separation
  remove about a quarter of it, and with that the 0.50 hull holds heading
  with no control at all.
- **0.30 diverges in every model.** Nothing argues for bigger fins than
  0.50 and nothing would justify smaller.

The check found errors in my first Gazebo generator, none of which touched
the published rail comparison: one coefficient had the wrong sign, the
separation station was a guess (0.4 L against 0.83 L from Hopkins' rule),
and inertia was written about the wrong point. All corrected.

What it does not do: both models use the same assumed fin lift slope, so it
is still unmeasured; and whether 0.50 holds heading unaided depends on how
much of the Munk moment is real, with a thin margin (75 % by the rule, 80 %
at the edge). An open-loop sideslip release on the SP1 trainer measures
both at once.

## Where the model was checked

- **Lamb added-mass factors** reproduce Munk's NACA Report 184 table to
  three figures (k1 0.082, k2 0.860, k′ 0.608 at fineness 4).
- **Hull drag** matches the Cheeseman/Hoerner form within 3 % at Re 1.5×10⁶;
  the 1.8× appendage factor is the published one.
- **JP Aerospace Tandem** flew two 1.8 m propellers and managed 6 kt at
  ~29 km. The tandem model needs 100 W to sustain 3 m/s at 20 km with
  0.77 m propellers. Same regime.
- **Gazebo with fins**: open-loop yaw divergence times within 7-15 % of the
  in-repo model for three fin sizes, differences attributed term by term.
- **Gazebo** (`ros2 launch aiur_description gz_check.launch.py`): the stock
  `LighterThanAirDynamics` + `Buoyancy` systems give a terminal airspeed of
  6.18 m/s against 6.00 expected (S2) and 3.14 against 3.00 (S1), and an
  initial acceleration within 1 %. Off its rail, the finless Gazebo hull
  tumbles, as Munk says it must.
- **ROS 2 vs batch.** The first mission through the ROS nodes reached float
  at 5,168 s and landed 64.5 km out against 5,172 s and 64.6 km in batch.
- **Over MAVLink.** The unified plant behind a MAVLink UDP port, the flight
  nodes on the other side of a bridge: 164,220 frames in, 23,460 out, float
  held at 19,870 m, landing 59.3 km out.
- **Firmware vs reference.** 29,318 vectors, zero mismatches; 11 injected
  faults all caught.
- **Patterns vs hull.** Flat gore area matches the smooth hull to 0.001 %.

## Estimates that a bench must replace

In rough order of how much they could move the design:

1. Fin lift-curve slope on an inflated low-aspect fin at Re ~10⁵ (2.2/rad
   assumed). Decides whether 0.60 is enough. *Tow test or car-top rig.*
2. Film optical properties — solar absorptance 0.03, IR emittance 0.18 for
   20 µm polyethylene. Sets superheat, hence spill and night behaviour.
3. Propeller efficiency at blade Re ~2–3×10⁴ (0.43–0.53 modelled).
   *Vacuum-chamber thrust stand.*
4. Ascent drag coefficient of a 10 %-full hull (0.65 assumed).
5. Seam strength and creep of heat-sealed 20 µm film at −60 °C.
6. Wind at the actual launch site on the actual day. The climatology is
   now measured; the forecast is not part of the model.
7. Motor heat rejection at 5.5 kPa (a third of sea level assumed).
8. Li-ion capacity in the bay as actually insulated.
