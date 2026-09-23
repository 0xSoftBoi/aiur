# STRATO-P0 build plan

Status: build sequence, not an assembled article  
Article: Rev-A flight package, A0 (bench article) then A1 (flight article)  
Flight condition: **no flight until S0-B; no free flight until S0-C**

This is the order of operations from nothing ordered to a package eligible
to attempt the [S0-A test card](s0a-test-card.md). It does not restate the
package ([README](README.md)), the parts ([BOM](bom.csv)), the enclosure
([generated drawings](cad/generated/)), or the gates
([spec](../../docs/prototype-strato-p0.md)). It sequences them, and it
names the point at which each open decision has to close.

The readiness graph (`python -m aiur.s0_readiness`) is the authority on
what is open; this plan is how the open items get closed in the right
order.

## The shape of the problem

Two things gate the bench, and neither is engineering:

1. **Jurisdiction** (`DEC-JURISDICTION`): which rule the first flight is
   made under decides the notice procedure, whether a radar reflector is
   carried, and which radio the independent tracker may use.
2. **Tracker** (`DEC-TRACKER`): APRS needs an amateur licence in the
   crew; a satellite beacon needs a subscription and a plan. The choice
   changes one BOM row and 40 g.

Everything else in the package is the same in every jurisdiction. So the
critical path is:

```
order the jurisdiction-independent parts -> bring up A0 on the bench ->
cut the enclosure -> decide jurisdiction + tracker -> order the tracker ->
assemble A1 -> weigh -> S0-A card
```

A0 is the package without its independent tracker, on a bench, running the
real flight program against replayed and simulated inputs. It exists so the
imaging chain, the GNSS airborne-mode configuration, the LoRa link, the
timer, and the cutdown are all proven before the one part that waits on a
decision arrives. Money spent waiting on the decision is spent on nothing.

## Stage 0 — order what the decisions cannot change

The purchasing sheet is [`s0-stage0-order.csv`](s0-stage0-order.csv): one
row per line item, what to verify at order, and the blocked lines carried
in the same sheet with their blocker named so they cannot be ordered by
accident.

Unblocked: flight computer and storage, IMX477 module and 16 mm lens, GNSS
module and patch, LoRa module pair (one flies, one is the ground station),
lithium AA cells, cutdown MOSFET and nichrome, timer board parts, arming
pin, XPS sheet and window acrylic, load line, parachute, silicone wire,
and the bench instruments: a scale that reads to 1 g, a spring scale for
neck lift, and a thermistor logger for the chamber.

Blocked on `DEC-TRACKER`: the independent tracker and its cells. Blocked
on `DEC-JURISDICTION`: the radar reflector line and the balloon itself, only
because balloon size may change if the rule caps the package differently.

## Stage 1 — A0 bench bring-up

Goal: the flight program runs on the flight computer against real devices,
without a balloon, and writes the same log the twin does.

1. Flash the flight computer; install the repository; run
   `python -m aiur.flight_main --backend sim --log a0-sim.csv` on the Pi
   itself. Confirm the log reduces:
   the same command the CI chain runs, on the target hardware.
2. Implement the Pi backend against the contract `--backend pi` prints:
   arming-pin GPIO, u-blox receiver in the airborne dynamic model (read the
   setting back), bus ADC, thermistor, LoRa inbox, timer fired line;
   burn-wire MOSFET gate, capture-to-storage, LoRa transmit.
3. Run `--backend replay` with a twin log as the sensor stream and confirm
   the states and cutdown decisions match the twin's (the replay test does
   this in CI on the desk; do it on the Pi).
4. Ten cutdown trials on a sacrificial loop, then the timer path with the
   Pi unpowered. These are rehearsals; the S0-A card repeats them for the
   record on A1.
5. Link trials at ≥ 500 m with the ground-station LoRa and record RSSI.

Exit: a bench log from the real devices that `python -m aiur.s0_evidence`
reads without error. It closes nothing; it proves the chain.

## Stage 2 — enclosure

Cut six panels from the generated cut sheet; drill the camera port; groove
the line loops; fit the acrylic window inside the port; dry-fit A0's
boards, cells, and the tracker's volume (an empty 40 g mass in its place).
Weigh the empty enclosure and compare with the manifest estimate; the
difference goes in the build sheet.

## Stage 3 — decisions close

`DEC-JURISDICTION` and `DEC-TRACKER` close in that order, in
[`../../docs/decisions/strato-decisions.md`](../../docs/decisions/strato-decisions.md).
Order the tracker. Update the BOM row from candidate to part and the
flight manifest template's `jurisdiction_rule`.

## Stage 4 — A1 assembly and weigh-in

Assemble the flight package with the tracker fitted, the flight image
hashed, the timer set to `FlightLimits.max_mission_s` and read back. Weigh
complete. The number is `payload_package_mass_kg` in the bench manifest;
every allocation in the BOM is replaced by the scale reading that day.

Exit: A1 assembled, weighed, identity recorded. Eligible for the
[S0-A test card](s0a-test-card.md).

## What this plan does not do

It does not schedule. It orders. A stage that starts before the previous
one exits is the way the carrier lineage got a keeper stroke and its
geometry to disagree by 2.6 mm without noticing.
