# Flight-termination unit firmware

The FTU is the third of the three avionics systems in
[hardware.md](hardware.md): its own processor, GNSS, barometer, radio and
primary cells, and no conductor shared with the autopilot. Its firmware does
one thing: decide that the flight must end, and then end it by firing two
hot-wire cutters. This page says what it decides, how that was checked, and
what has not been checked.

Source: [`firmware/ftu/`](../../firmware/ftu/). Nothing here has run on
hardware. Every statement below is either the output of a command run in this
repository or is marked **unverified**.

## What it decides

Any one of these, while ARMED, latches termination:

| Reason (wire code) | Condition | Source of the rule |
| --- | --- | --- |
| `commanded` (1) | authenticated TERMINATE uplink | `guidance.Geofence` |
| `range` (2) | distance from home > 150 km, for 5 s | `guidance.Geofence` + confirmation |
| `altitude` (3) | altitude > 27 km, for 5 s | `guidance.Geofence` + confirmation |
| `flight time` (4) | flight clock > 16 h | `guidance.Geofence` |
| `link loss` (5) | no authenticated uplink for > 3 h | `guidance.Geofence` |
| `heartbeat loss` (6) | autopilot heartbeat absent for 10 min | firmware only |

The first five are `aiur.strato.guidance.Geofence.must_terminate`, ported
statement for statement to `must_terminate()` in
[`geofence.cpp`](../../firmware/ftu/src/geofence.cpp): same thresholds, same
strict `>`, same precedence, same strings. The decision the unit acts on is
one call to that function, so the precedence of reasons is the reference's.

What the firmware adds around it, and why:

- **Arming.** DISARMED until either altitude source is more than 300 m above
  its own ground reference for 30 s continuously. Nothing fires while
  DISARMED, and TERMINATE is refused until ARM has been sent. *Either* source
  arms, deliberately: a unit that is armed on the ground still needs a second
  condition to become true before it fires, whereas a unit that fails to arm
  in flight has no autonomous criteria at all.
- **Heartbeat loss is a timer, not a trigger.** A missing heartbeat has causes
  that clear by themselves (autopilot reboot, brown-out, an intermittent
  connector), a cut-down cannot be taken back, and a vehicle with a dead
  autopilot is still tracked and still fenced by this unit. Ten minutes lets
  the autopilot return and lets the ground choose where the descent happens.
  The heartbeat must be back for 30 s continuously to cancel the timer, so an
  autopilot in a reboot loop does not hold it off for ever.
- **Altitude source.** GNSS when valid (it is geometric, like the limit, and
  good to tens of metres); barometer otherwise (pressure altitude; ±2.5 hPa is
  about ±0.9 km at 27 km). If both are valid and differ by more than 2 km,
  one is wrong and the unit cannot tell which, so the ceiling test — and only
  the ceiling test — uses the higher. That turns a GNSS receiver frozen low
  into an on-time termination, at the price of an early termination if the
  barometer fails towards low pressure. Early ends a mission on a parachute
  inside the planned area; never leaves a vehicle above its approved ceiling.
  No ground-level offset is applied to the barometer: it would be worth
  < 300 m, and one learned from mismatched references would feed a
  kilometre-scale error straight into that rule.
- **Confirmation.** Range and altitude come from sensors; one bad fix must
  not be enough for an irreversible action, so each must stay tripped for
  5 s. Flight time, link loss and command cannot glitch and are not delayed.
  This is the one place the unit's behaviour differs in time from calling
  the Python once per sample.
- **Latch.** There is no transition out of TERMINATED, and it survives a
  reset (flash).
- **Cutter sequencer.** A for 4 s, 3 s off, B for 4 s, 3 s off, three times.
  The output is a single enum (none / A / B), so both-on cannot be expressed.
  A first: the equipment string is on its parachute before the hull is
  opened. A pulse is cut short if the cells fall below 3.0 V under load, and
  no further pulse starts if they rest below 3.6 V. The pulse count is
  written to flash before each gate opens, so a unit that browns out on every
  pulse still stops after six. A further authenticated TERMINATE after the
  sequence has stopped gives one more A/B cycle.

## State machine

```
            alt > ref + 300 m for 30 s            any criterion
            or ARM command                        (table above)
 DISARMED ───────────────────────────▶ ARMED ───────────────────▶ TERMINATED
     ▲                                   │                          (latched)
     └───────────────────────────────────┘                   A,gap,B,gap ×3
       DISARM command (hold ≤ 1 h, then                      then gates off
       the arming rule applies again)
```

- Power-on with a stored ARMED or TERMINATED state resumes that state with
  the stored home position, ground references, flight clock and pulse count.
  A reset in flight therefore does not return the unit to DISARMED with a
  "ground" reference taken at 20 km.
- Power-on with the BOOT button held for 3 s clears the stored flight state.
  **This must be done before every flight and before bench work on a
  recovered unit.**
- DISARM is bounded (≤ 1 h hold) and self-healing: when the hold ends, a unit
  still above the arming height re-arms. It is refused once TERMINATED.

## Radio

LoRa SF10, 125 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on,
22 dBm. Default 869.525 MHz (build flag; the band is chosen per site).

| Packet | Bytes | Time on air | Rate | Duty cycle |
| --- | ---: | ---: | --- | ---: |
| Telemetry (down) | 24 | 370.7 ms | every 30 s | 1.24 % |
| Telemetry, after termination | 24 | 370.7 ms | every 10 s | 3.71 % |
| Command (up) | 19 | 329.7 ms | on demand | — |

Time on air is computed by `lora_time_on_air_ms()` and checked on the host
against a hand calculation (symbol 8.192 ms; 45.25 and 40.25 symbols). The
payload moves in 5-byte steps at this setting, so 24 bytes costs the same as
20 and 25 would cost 41 ms more. Whether these duty cycles are lawful depends
on the band and country and is **unverified** here.

Telemetry (little-endian):

| Offset | Field | Coding |
| ---: | --- | --- |
| 0 | version, type | high nibble 1, low nibble 1 |
| 1 | vehicle id | |
| 2–4 | latitude | int24, degrees × (2²³−1)/90 (1.2 m) |
| 5–7 | longitude | int24, degrees × (2²³−1)/180 (2.4 m at the equator) |
| 8–9 | GNSS altitude | uint16, metres + 1000, saturating |
| 10–11 | barometric altitude | uint16, same |
| 12 | status | bits 7–6 gate (0 none, 1 A, 2 B), 5–4 state, 3–0 reason |
| 13 | flags | GNSS valid, baro valid, home set, heartbeat, altitude disagree, GNSS airborne model confirmed, disarm hold, under-voltage stop |
| 14–15 | cell voltage | uint16 mV (0 = no measurement) |
| 16–17 | flight clock | uint16, units of 2 s |
| 18–19 | ack | low 16 bits of the last accepted command counter |
| 20 | boot count mod 16 (high nibble), cutter pulses started (low nibble) | |
| 21 | uplinks rejected since boot | saturating |
| 22–23 | CRC-16/CCITT-FALSE | over bytes 0–21 |

Command:

| Offset | Field | Coding |
| ---: | --- | --- |
| 0 | version, type | high nibble 1, low nibble 2 |
| 1 | vehicle id | |
| 2–5 | counter | uint32, strictly increasing |
| 6 | command | 1 PING, 2 ARM, 3 DISARM, 4 TERMINATE |
| 7–8 | argument | DISARM: hold seconds; TERMINATE: must be `0x7E4D` |
| 9–16 | MAC | SipHash-2-4 (128-bit pre-shared key) over bytes 0–8 |
| 17–18 | CRC-16/CCITT-FALSE | over bytes 0–16 |

A command is accepted only if, in this order, length, CRC, version, vehicle,
MAC and command code are right and the counter is greater than the last one
accepted. The counter is stored in flash before the command is acted on. A
packet that fails the MAC cannot advance the counter. The ground station
should send `max(UTC seconds, last + 1)` as the counter so that it needs no
memory of its own. Telemetry is neither encrypted nor authenticated. SipHash
is not a certified MAC and the key is in the flash of a payload that a
stranger may find: one key per article, and a new one after any loss.

## Evidence

Run here, g++ 13.3.0, Python 3.13:

```
$ make -C firmware/ftu/host clean test
29318 vectors -> firmware/ftu/host/build/vectors.csv
by expected reason: (none)=6102, altitude=6128, commanded=1210, flight time=3924, link loss=1615, range=10339
== (a) parity with aiur.strato.guidance.Geofence ==
  defaults checked:   7, mismatches 0
  vectors replayed:   29318, mismatches 0
  barometer altitude: 400 points vs atmosphere.pressure_altitude_m, 0 outside 5 m, worst 0.020 m
  PARITY PASS
== (b) firmware-only scenarios ==
  SCENARIOS PASS: 20 of 20 passed, 8418052 checks, 0 failed
== ALL PASS ==
```

- **Parity.** [`tools/ftu_vectors.py`](../../tools/ftu_vectors.py) imports
  the real `Geofence`, calls it on 29,318 inputs — each limit and its two
  neighbouring doubles, all 32 combinations of the five criteria, NaN /
  ±infinity / signed zero / denormals in every position, random draws around
  the thresholds, random limits — and writes inputs and results as exact hex
  floats. The host binary replays them with the same number of arguments
  (so default arguments are compared too) and must agree on the flag and the
  reason string for every one. The seven Python defaults are read by
  introspection and compared with the C++ defaults, so a threshold changed in
  `guidance.py` and not in the firmware fails the build.
- **Scenarios.** Twenty, in
  [`ftu_host_test.cpp`](../../firmware/ftu/host/ftu_host_test.cpp): 24 h on
  the bench without arming; dwell; arming on one source; TERMINATE refused
  while DISARMED; heartbeat timer, recovery and reboot loop; single bad fix;
  the altitude disagreement cases; flight time and link loss to the step;
  latch; sequencer order, pulse length, gaps and under-voltage; resets in
  flight, after termination, and on every pulse; DISARM hold; CRC, MAC and
  replay rejection (every single-bit error, and every single-bit forgery with
  the CRC repaired). On every simulated step of every scenario the rig also
  checks: never both gates, no gate before the latch, state and reason never
  change after the latch.
- **The checks bite.** Eleven deliberate faults were injected one at a time
  into a scratch copy (`>=` for `>`, a changed default, confirmation removed,
  the heartbeat recovery time removed, the gap removed, MAC check removed,
  replay comparison off by one, and others); each made the suite fail.
- **Clean under** `-Wall -Wextra -Werror -Wshadow -Wconversion` and under
  AddressSanitizer + UBSan (`make sanitize`).
- **Target build.** PlatformIO Core 6.2.0, platform espressif32 8.0.0,
  Arduino-ESP32 3.3.12, RadioLib 7.8.1, SparkFun u-blox GNSS v3 3.1.15,
  XPowersLib 0.2.9: `pio run -e ftu` (with a key file) and
  `pio run -e ftu_bench` both link; 439 kB flash, 26 kB static RAM, no
  warnings from the FTU sources. `pio run -e ftu` without
  `src/ftu_secrets.h` fails on purpose.

## Pins

**None of these has been checked against a board.** "Board" pins are the
T-Beam Supreme pin map as remembered; "harness" pins are a choice of
supposedly free GPIOs, and whether they are broken out on the Supreme's
headers is not known. Check all of them against the schematic of the board
revision in hand before connecting a cutter.

| Signal | GPIO | Origin | Net |
| --- | ---: | --- | --- |
| SX1262 SCK / MISO / MOSI / CS | 12 / 13 / 11 / 10 | board | — |
| SX1262 RST / DIO1 / BUSY | 5 / 1 / 4 | board | — |
| GNSS UART RX / TX | 9 / 8 | board | — |
| Sensor I²C SDA / SCL (MS5611 at 0x77) | 17 / 18 | board | `I2C_FTU` |
| PMU I²C SDA / SCL (AXP2101) | 42 / 41 | board | — |
| BOOT button (clear flight state) | 0 | board | — |
| Cutter A gate | 15 | harness | `CUT_A_GATE` |
| Cutter B gate | 16 | harness | `CUT_B_GATE` |
| Heartbeat in (opto to ground, pull-up) | 21 | harness | `HEARTBEAT` |
| Cell voltage (100 k / 47 k divider) | 2 | harness | not in the netlist |

Also from memory and unverified: TCXO 1.8 V, DIO2 as RF switch, GNSS at
9600 baud, PMU rails ALDO1 (sensors), ALDO3 (radio), ALDO4 (GNSS).

## Not verified, and known gaps

Not run on hardware — all of it:

- every pin, rail and radio setting above;
- that the u-blox accepts and reports the airborne < 1 g dynamic model (the
  firmware reads it back and reports it as a telemetry flag; without it the
  receiver stops reporting above 12 km);
- MS5611 behaviour below −40 °C (outside its rated range; the compensation
  is checked only against the datasheet example and one cold point);
- pulse length and gap against a real cutter in the cold (4 s and 3 s are
  placeholders until SP0-B), and both under-voltage thresholds;
- brown-out behaviour with real cells at −40 °C;
- the parity result on the ESP32-S3 itself: it was obtained on x86-64. The
  S3 computes `double` in software; the logic uses only comparisons on the
  reference path, but this has not been replayed on the target;
- radio range, and the legality of the duty cycle and power at any site.

Gaps in the design that firmware cannot close:

- **Cell-voltage sensing is not in the netlist.** `connections.csv` has no
  net from `FTU_RAW` to an ADC pin. Without the divider the firmware treats
  the reading as absent and fires without under-voltage checks.
- **Gate pull-downs.** The gate pins are high-impedance during reset and
  boot. Each MOSFET needs a gate-to-source pull-down in the FTU box.
- **No physical safe plug.** The software arming rule is the only thing
  between a powered FTU and a hot wire. A remove-before-flight link in
  `FTU_RAW` to the cutters would be the hardware barrier.
- **Power path.** The netlist feeds the board at `3V3_IN`. On this board
  family the radio and GNSS are supplied through PMU regulators; whether they
  are powered when the board is fed at 3.3 V is unverified.
- **GNSS loss.** With no fix, range holds its last value and cannot trip.
  Flight time, link loss and ground command remain.
- **Reset loops.** Link-loss and heartbeat timers restart at a reset (the
  flight clock does not; it is saved every minute). A unit resetting more
  often than those timers is caught by flight time only.
- **Late first fix.** Home is the mean of the first ten valid fixes after a
  DISARMED power-on. If the first fix arrives after launch, home is wherever
  that was. The "home set" flag must be seen before release.

## Bench procedure (gate SP0-B)

SP0-B in [prototype-ladder.md](prototype-ladder.md) asks for: cold soak to
−60 °C outside / 0 °C inside for 4 h; both cutters fired from the FTU with
the autopilot powered off; cut-down on heartbeat loss. Use the `ftu_bench`
build and a ground station that speaks the command packet. Cutters are
fitted with sacrificial line and nothing else flammable is near them.

Before anything: check the pin table against the board; scope both gate pins
through a power-on and a reset and confirm they stay below the MOSFET
threshold; hold BOOT for 3 s at power-on to clear stored state.

1. **Idle.** Power the FTU alone, outdoors or at a window. Within a few
   minutes telemetry shows state DISARMED, flags GNSS valid, baro valid,
   home set, *GNSS airborne*; cell voltage plausible. Leave it 1 h: still
   DISARMED, no pulses.
2. **Refusal.** Send TERMINATE. Expect: ack counter advances, state stays
   DISARMED, no pulse.
3. **Cutters, autopilot off.** Autopilot unpowered and its heartbeat lead
   connected. Send ARM (state ARMED), then TERMINATE. Expect: reason
   `commanded`; A parts its line; B parts its line; gate bits show A and B
   alternately and never together (confirm on a two-channel scope: no
   overlap, ≥ 3 s between pulses); pulses = 6; cell voltage under load
   stays above 3.0 V. Record the time each line parts — that sets the real
   pulse length.
4. **Latch and reset.** During step 3, cycle FTU power once mid-sequence.
   Expect: it returns TERMINATED with the same reason and finishes the
   remaining pulses, not six new ones. Send DISARM: refused.
5. **Heartbeat loss.** Clear state (BOOT), power the autopilot, confirm the
   heartbeat flag, send ARM. Send PING every few minutes. Power the autopilot
   off. Expect: heartbeat flag clears within 5 s; no pulse for 10 min; then
   reason `heartbeat loss` and the full sequence. Repeat, restoring autopilot
   power after 5 min: no termination.
6. **Link loss.** Build with `link_timeout_s` shortened to 10 min (a config
   field; note the change in the test record). ARM, autopilot running, then
   switch the ground station off. Expect reason `link loss` at 10 min.
7. **Cold soak.** Box closed, −60 °C outside, 0 °C inside on the heater, 4 h.
   Telemetry throughout; note any reset (boot count), barometer dropout, GNSS
   loss and the cell voltage. At the end of the soak, still cold, repeat step
   3. This is the measurement that sets pulse length, gap and the
   under-voltage thresholds; change them in `Config` and re-run
   `make -C firmware/ftu/host`.
8. **Arming rule** (optional, needs a vacuum jar): after a clean power-on,
   lower the pressure at the barometer by 40 hPa or more (300 m is about
   35 hPa near sea level) and hold it for more than 30 s. Expect ARMED with
   no command sent.

Pass: steps 1–7 as described, on the as-built harness, with no pulse at any
time other than those called for.

## Where the reference and the firmware differ

Not changed; listed for whoever owns `guidance.py` and the hardware files.

- `hardware.md` lists loss of heartbeat among the `Geofence` criteria;
  `Geofence` has no such criterion. The firmware supplies it (reason 6).
- `Geofence.min_descent_altitude_m` is read by nothing.
- A NaN input never trips its own criterion in the reference (`nan > x` is
  false). A sensor fault that yields NaN silently disables that test. The
  firmware relies on exactly this to mean "unknown", and covers the case
  with validity flags.
- `link_timeout_s` is an argument, not a field, so the limit lives in each
  caller. `aiur_flight/termination.py` never passes `link_lost_s`: link loss
  is not exercised in simulation.
- The reference has no confirmation, arming or latch. `termination.py` adds
  its own latch; neither it nor `ascent.py` would notice a single-sample
  range glitch because the simulation does not produce one.
- `termination.py` honours `terminate_requested` from the autopilot, and
  `ascent.py` terminates on "mission complete". On the vehicle there is no
  channel for the autopilot to ask the FTU for anything (the heartbeat is the
  only crossing), so a planned end of mission must come from the ground as
  TERMINATE, or from flight time.
- `components.csv` says of `FTU_BAT`: "2P so both cutters can fire
  together". The firmware never fires both, on the instruction that the
  cells are sized for sequential 5 W pulses. One of the two statements
  should be corrected.
