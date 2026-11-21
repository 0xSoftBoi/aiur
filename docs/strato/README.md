# STRATO: the stratospheric article

Status: executable design definition, opened 2026-11-21. Nothing here has flown.
Scope: the smallest, cheapest powered airship that reaches the stratosphere,
flies there under control, and can be built in quantity.

CARRIER-P0 answers one question indoors: can a buoyant carrier recover an
aircraft. STRATO is the next article, and it answers a different one: can we
put the carrier *where a carrier is worth having* — above weather, above
air traffic, with a 500 km radio horizon — for the price of a mid-range
drone. Every number below is a model output; the models are in
[`aiur/strato`](../../aiur/strato/) and every one of them runs from the
command line.

## The answer in one table

| Step | What it proves | Vehicle | Gross | Unit cost (first / 1000th) | Gas per launch |
| --- | --- | --- | ---: | ---: | ---: |
| **SP1 trainer** | ground handling, inflation, control - at 30 m, not 20 km | 5.1 m ripstop hull, 4.2 m3, helium, reusable | 4.4 kg | $1,975 / $840 | $120 of helium |
| **S1 touch** | a powered airship reaches 20 km and flies under control for an hour | 15.0 m film hull, 111 m3, *or* two 1600 g latex cells on a 6.4 m boom | 9.1 kg | $2,330 / $980 | $19 of hydrogen |
| **S2 day loiter** | holds station all daylight against the summer median wind, 2 kg payload | 17.6 m film hull, 177 m3, 0.4 m2 solar | 14.6 kg | $2,840 / $1,250 | $30 |
| **S3 diurnal** | survives the night | 21.2 m tendon-netted film hull, 308 m3 | 25.3 kg | $4,260 / $1,890 | $52 |
| **S4 carrier** | 10 kg of payload: release-only aircraft and relay radios | 27 m class superpressure hull | 51 kg | not costed | - |

SP1, S1 and S2 are the funded definition. S3 closes on paper with a cheap
envelope (see the [design log](design-log.md), Rev L) but its net is
unbuilt and untested.

![Launch to landing](img/ascent-profiles.png)

## The vehicle

**The hull is the air frame.** A 20 µm polyethylene film hull, launched
about 10 % full and filled by its own gas expanding fourteen-fold on the way
up (the HiSentinel launch). At float it is a pressure vessel at 20 Pa — and
at that pressure its wrinkling moment is six times the bending the equipment
puts on it, so there is no keel. Fins are sealed air-beams that are soft on
the ground and stiffen as the outside pressure falls away. Equipment hangs
on a webbing spine: payload forward, heated avionics bay amidships, and a
self-contained propulsion pod at the stern with one slow 0.75–0.88 m
propeller on a two-axis gimbal.

**Avionics are the Ukrainian FPV parts bin**, on purpose: an ArduPilot H7
board, a u-blox M10, a 1 W sub-GHz MAVLink link, in-house 6SnP 21700 packs,
a $40 arm64 companion running ROS 2 — about $620 of avionics and termination electronics, 0.31 kg,
6 W. The one thing that is not negotiable is the flight-termination unit:
its own processor, cells, GNSS, barometer and radio, with no conductor
shared with the autopilot. See [hardware.md](hardware.md).

**Hydrogen, not helium.** At this scale it is a $19 launch instead of a $370
one, it is what most weather services already fly, and nobody is underneath.

## What the models found

Fourteen findings changed or tested the design. Each is reproducible; the commands are
in the [design log](design-log.md).

1. **Scaling the indoor P0 blimp does not work.** A TPU envelope with a
   ballonet closes at 30 m and 75 kg; a flaccid-launched film hull does the
   same mission at 15 m and 9 kg.
2. **A slack gas cell has no altitude stiffness.** The hull is never vented
   early; it fills and spills, and is then held from where it settled.
3. **Thin air makes the hull Munk-unstable**, and fins are sized against it.
4. **Free lift had to triple** to 45 %: small vehicles climb slowly and the
   jet stream carries them away.
5. **Copper down the spine was the wrong answer.** The stern pod has its own
   pack and a CAN bus.
6. **The radio needed 1 W**, not 100 mW.
7. **Altitude trim was three times weaker than assumed.** Joining the ascent
   and 6-DoF models showed vertical force has to come from pitching the
   whole hull.
8. **The pitch gimbal sign was wrong**, hidden by pendulum stability. With
   it fixed, fins shrink from 0.60 to 0.50 V^(2/3).
9. **Do not fly while still climbing fast** - the hull ends up at 45 degrees
   of incidence driving itself downward. Entry guidance flies the
   flight-path angle.
10. **The wind tables were wrong in both directions.** 89,000 real soundings:
    summer at 20 km is calmer than estimated (median 4.5 m/s), winter is
    worse (20 m/s), and the calm season runs May to September.
11. **Cutting patterns corrected the budget:** 38 % film waste not 18 %, fins
    35 % heavier, 2.2 % of volume lost to flat gores.
13. **A full day closes with margin.** Ten hours at float on the unified
    plant: S2 flies 48 km back to its station and holds it, the battery
    never drops below 64 %, and it lands 22 km from launch.
14. **One estimate can break the hull, and it is not the one expected.**
    Seam strength and creep in the cold, then film optics. Propeller
    efficiency moves the design by half a percent.
12. **Overnight is a net, not a laminate.** Tendons carry the day-night
    pressure swing and 20 um film only spans between them: $4,260 against
    $17,600.

## What it cannot do

- **Winter.** Measured at four European stations, the 20 km winter median is
  20 m/s and wind is below 6 m/s on 6 % of days. In June-August it is below
  6 m/s on 80 % of days (98 % if the vehicle can pick its level between 18
  and 22 km). This is a May-September vehicle. See [winds.md](winds.md).
- **Come home.** It lands 55-75 km downrange in median wind and ~135 km at
  the 90th percentile. Recovery is a chase, and cost per flight assumes 70 %
  of hardware comes back.
- **Fly as a free balloon, as far as anyone has ruled.** By mass S1 fits the
  Part 101 exempt class (3.6 kg hangs from the hull; the limit is 12 lb),
  but a *powered* airship is not a free balloon, and that question is
  unanswered. See [prototype-ladder.md](prototype-ladder.md).
- **Recover aircraft at altitude.** A quadcopter cannot hover at 0.089 kg/m3.
  The stratospheric carrier is release-only.
- **Claim any of this is tested on hardware.** No film has been sealed, no
  motor run in a chamber, no firmware flashed. The real ArduPilot firmware
  has flown the simulated hull, but only at float and only in software.

## Run it

```
python -m aiur.strato.sizing        # the design ladder
python -m aiur.strato.trades        # every trade study
python -m aiur.strato.ascent        # launch-to-landing reference flights
python -m aiur.strato.flight6dof    # handling and station-keeping
python -m aiur.strato.mission6      # launch to landing on the unified plant (buoyancy + 6-DoF)
python -m aiur.strato.faults        # nine fault cases, all must end safe
python -m aiur.strato.robustness    # which unmeasured estimate could break it
python -m aiur.strato.patterns      # gore and fin cut patterns (SVG, DXF, station tables)
make -C firmware/ftu/host test      # termination firmware vs the Python reference
python -m aiur.strato.campaign --design S1-touch/hull --flights 200 --seed 1
python -m aiur.strato.harness --check-budget
python -m aiur.strato.link
python -m aiur.strato.cost
python tools/strato_export.py       # URDF, STL, Gazebo models, design-point JSON, BOMs
python tools/strato_plots.py        # figures (needs matplotlib)
```

ROS 2 (Jazzy): see [ros.md](ros.md).

## Map

- [Design log](design-log.md) — the iterations and what each one changed
- [Hardware](hardware.md) — structure, components, every connection
- [Building the envelope](build-envelope.md) — from cut patterns to a leak-tested hull
- [ArduPilot in the loop](ardupilot-sitl.md) — stock ArduRover flying the simulated hull
- [Gazebo fin cross-check](gazebo-fins.md)
- [Flight-termination unit](ftu.md) — firmware, packet format, bench procedure
- [Winds](winds.md) — measured statistics from 89,000 soundings
- [Prototype ladder](prototype-ladder.md) — what to build first, gates, regulation
- [ROS 2](ros.md) — workspace, topics, running a mission, Gazebo cross-check
- [References](references.md) — sources, and what could not be verified
- [`hardware/strato/`](../../hardware/strato/) — netlist, BOMs, sized design points
