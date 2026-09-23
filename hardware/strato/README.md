# STRATO-P0 flight package, Rev-A

Status: first-article definition — nothing built, nothing weighed, nothing flown  
Gate it is built for: S0-A ([`aiur/loop_graph.py`](../../aiur/loop_graph.py) `STRATO_GATES`)  
Specification: [`docs/prototype-strato-p0.md`](../../docs/prototype-strato-p0.md)

The package is the whole vehicle. It is a foam box under a latex balloon
with one job — climb past 20 km, take position-tagged pictures, tell the
ground where it is, and come down under a parachute inside the predicted
ellipse. There is no dock, no aircraft, no deployable anything.

## What is in this directory

| File | What it is |
| --- | --- |
| [`bom.csv`](bom.csv) | Rev-A bill of materials: candidate parts, nominal masses, and which figures are published versus allocated |
| [`cad/generate_package_rev_a.py`](cad/generate_package_rev_a.py) | Generator for the enclosure cut sheet, cross-section, and manifest; outputs in [`cad/generated/`](cad/generated/) |
| [`s0a-test-card.md`](s0a-test-card.md) | Printable run card for the S0-A bench, cold-chamber, termination, and drop-test sessions |
| [`launch-checklist.md`](launch-checklist.md) | S0-B tethered ascent and S0-C free-flight procedure, from coordination to recovery |
| `s0-*.csv`, `s0-*.json` | Log and manifest templates the evidence reducer reads |

The evidence chain is executable end to end before a balloon is bought:

```
python -m aiur.strato_sim --scenario nominal --flights 2 --out /tmp/s0   # simulated flights, real supervisor
python -m aiur.s0_evidence flight \
  --log /tmp/s0/nominal-1-flight-log.csv --manifest /tmp/s0/nominal-1-flight-manifest.json \
  --log /tmp/s0/nominal-2-flight-log.csv --manifest /tmp/s0/nominal-2-flight-manifest.json \
  --trials /tmp/s0/sim-termination-trials.csv                             # S0-C verdict
```

A simulated pass is software evidence. The reducer carries
`evidence_kind: simulated` into the verdict and refuses to mark
requirements closed on it. The real package writes the same files.

## Architecture

```
            balloon (1200 g latex, helium)
                 |
            load line, weak link <= 40 lbf
                 |
            parachute (48 in round class), rigged on its own line
                 |
   +-------------+---------------------------+
   |  XPS foam box 170 x 140 x 120 mm         |   <- generated; line runs AROUND it
   |                                         |
   |  [GNSS patch]  under a foam-only lid    |
   |  flight computer + IMU                  |   Pi Zero 2 W class
   |  imager ------- Ø30 port, +x wall ----> |   IMX477 + 16 mm M12: 1.94 m GSD at 20 km
   |  primary radio (LoRa) ---- wire antenna |   30 s telemetry, thumbnails
   |  4 x L91 lithium AA (main bus)          |
   |  ------------------------------------   |
   |  INDEPENDENT: tracker + timer + cutdown |   own 2 x L91; fires with the computer off
   +-----------------------------------------+
```

Three design rules, each traceable to a hazard:

1. **The line carries the package; the foam only locates it** (HAZ-013).
   Two loops of line run in grooves around the box. The enclosure is never
   in the tensile path, so a cracked corner cannot drop the package.
2. **Termination has its own timer, its own cells, and its own MOSFET**
   (HAZ-014, HAZ-016). The nichrome burn-wire fires from the flight
   computer's command *or* from a hardware timer that started when the
   arming pin was pulled. S0-A demonstrates the timer path with the
   computer unpowered. `IndependentTimer` in
   [`aiur/flight_supervisor.py`](../../aiur/flight_supervisor.py) is its model.
3. **Two trackers on separate power** (HAZ-015). The LoRa link carries
   telemetry and thumbnails; a separate beacon on the termination cells
   reports position without a ground station in range.

## Flight logic

[`aiur/flight_main.py`](../../aiur/flight_main.py) is the program the
payload computer runs: a 1 Hz loop that reads a `Sensors` backend, steps
the supervisor, drives the cutdown line from its latched output every
tick, captures and transmits at the commanded cadence, and flushes one
flight-log row per second in the shape the reducer reads. The simulated
backend flies it to landing in the twin (`--backend sim`), the replay
backend feeds a recorded log back through it on the bench
(`--backend replay`), and `--backend pi` prints the contract the S0-A
build has to meet instead of pretending hardware exists.

[`aiur/flight_supervisor.py`](../../aiur/flight_supervisor.py) is the
package's state machine: SAFE → ARMED (only on a valid fix) → ASCENT →
STRATOSPHERE → DESCENT → LANDED, with TERMINATING entered from any
in-flight state on ground command, mission clock, ceiling (a balloon that
did not burst), geofence, or position unknown for 10 minutes. Cutdown is
latched: nothing withdraws it. Imaging runs at 10 s below 20 km and 5 s
above; frames are geotagged only with a valid fix; low bus voltage drops
the package to beacon-only and leaves termination untouched.

[`aiur/strato_sim.py`](../../aiur/strato_sim.py) flies that supervisor
through the ascent model with seeded gusts and the fault menu the hazard
log cares about. The tests assert what the hazard log expects:

| Scenario | Outcome the tests require |
| --- | --- |
| `nominal` | burst near 33.8 km, ≥ 50 geotagged frames above 20 km, landing inside the geofence, no termination |
| `gnss-dropout` (4 min) | survived; no termination |
| `gnss-lost` (1 h) | terminated at 10 min of unknown position, below 20 km |
| `float-off` | balloon never bursts; mission clock ends the flight; timer fires |
| `computer-freeze` | supervisor stops; the independent timer brings it down |
| `ground-terminate` | ends on command |
| `blackout` | shows up as a telemetry gap the reducer measures |

## Enclosure

The box is six panels of 20 mm XPS cut from one 600 × 1250 mm sheet
([cut sheet](cad/generated/strato_package_rev_a_cut_sheet.svg),
[section](cad/generated/strato_package_rev_a_section.svg)). The generator's
manifest reports the exterior dimensions, the smallest face (26 in²), and
the weight/size ratio at the 1.0 kg allocation (1.36 oz/in², against the
3 oz/in² limb of 14 CFR 101.1(a)(4)(i)). Foam mass estimate: 58 g.

The camera port is a Ø30 mm hole in the +x wall at 40 mm above the floor,
covered by a thin acrylic window on the inside face. The GNSS patch sits
under the lid with foam only above it. Nothing conductive goes on the lid.

## Mass

Nominal masses in the BOM sum to roughly 430 g against the 850 g baseline
allocation and the 1.0 kg program ceiling. That gap is deliberate and
should survive the first weigh-in; the article is not engineered against
its last gram. `payload_package_mass_kg` on S0-A is the measured value
that replaces every allocation.

## What this is not

Not a flight-qualified article, not a float platform, not a design for
any jurisdiction's rules but the one it is launched in. Vendor figures in
the BOM are design inputs; the lot sheet and the scale govern.
