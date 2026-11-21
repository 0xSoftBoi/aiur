# Flight-termination unit firmware

The FTU is the third of the three avionics systems in
[hardware.md](hardware.md): its own processor, GNSS, barometer, radio and
primary cells, and no conductor shared with the autopilot. Its firmware does
one thing: decide that the flight must end, and then end it by firing two
hot-wire cutters. This page says what it decides, how that was checked, and
what has not been checked.

Source: [`firmware/ftu/`](../../firmware/ftu/). Nothing here has run on
hardware. Every statement below is the output of a command run in this
repository, is cited to a vendor document, or is marked **unverified**.

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
- BOOT pressed within 1.5 s *after* power-on (or RST) and held for 3 s clears
  the stored flight state. Not before: BOOT is GPIO0, and held through a
  reset it puts the ESP32-S3 in download mode. **This must be done before
  every flight and before bench work on a recovered unit.**
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
  `pio run -e ftu_bench` both link with the board definition
  `boards/t-beams3-supreme.json`; 439 kB flash, 26 kB static RAM, no
  warnings from the FTU sources. `pio run -e ftu` without
  `src/ftu_secrets.h` fails on purpose.

## Board, pins and power

Checked against the vendor's schematics and pin definitions — documents, not
a board. Buzz out every harness pin on the board in hand before connecting a
cutter. Sources:

- **SC** — LilyGO `T-Beam-S3-Core.pdf` (p1 Power, p2 ESP32S3, p3 Radio & GNSS)
- **SS** — LilyGO `T-Beam-S3-Supreme-V3.1.pdf` (carrier; headers PN1 / PM1)
- **LU** — LilyGO `examples/ArduinoLoRa/LoRaReceiver/utilities.h` L480–552
- **LB** — LilyGO `.../LoRaReceiver/LoRaBoards.cpp` L172–224
- **LH** — LilyGO `docs/en/t_beam_supreme/t_beam_supreme_hw.md`
- **LF** — LilyGO `examples/Factory/Factory.ino`

  (all in `github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series` at `5f537f1`;
  schematics under `schematic/T-Beam-S3-Supreme/`)
- **M** — `github.com/meshtastic/firmware` at `fe89ac1`,
  `variants/esp32s3/tbeam-s3-core/variant.h`; **MP** — its `src/Power.cpp`
- **DS** — Espressif *ESP32-S3 Series Datasheet* v2.2, Tables 2-1, 2-2, 3-1

### Variant

`components.csv` row `FTU` says "ESP32-S3 + SX1262 + u-blox M10": that is the
**T-Beam S3 Supreme "Ublox"** build (MAX-M10S) with the SX1262 radio
(LH L18–24). The firmware supports only that build.

- **L76K GNSS instead:** no UBX protocol, so the receiver is never detected,
  there is no position and no airborne dynamic model. The unit would fly with
  barometer, flight time, link loss and command only. Reject the board.
  (The L76K's own altitude ceiling is **unverified**.)
- **LR1121 radio instead:** different chip and driver (TCXO 3.0 V, RF switch
  on its DIO5/DIO6, M L36–46; LF L1479–1498). `radio.begin()` fails: no
  telemetry, no command, and link loss terminates at 3 h. Reject the board.
- **Carrier V3.0 vs V3.1:** same nets; V3.1 adds battery protection and the
  BME280 address resistor (LH L275–283). Header pin positions below are V3.1;
  V3.0 positions are **unverified**.

### Pins

| Signal | GPIO | Was | Where | Source |
| --- | ---: | ---: | --- | --- |
| SX1262 SCK / MISO / MOSI / NSS | 12 / 13 / 11 / 10 | same | on module | SC p2–3; LU L513–516; M L61–64 |
| SX1262 RST / DIO1 / BUSY | 5 / 1 / 4 | same | on module | SC p2–3; LU L518–520; M L19–21 |
| SX1262 DIO2 (RF switch), DIO3 (TCXO) | — | — | inside the radio can | M L22, L30–31; LF L1476 |
| GNSS UART: ESP RX / ESP TX | 9 / 8 | same | on module, 100 Ω each | SC p2–3; LU L503–504; M L66–67 |
| GNSS PPS (unused) / pin 5 wake (driven high) | 6 / 7 | not set | PPS also PN1-11 | SC p3; LU L505–506; LH L109–110, L125 |
| GNSS reset | none | — | RESET_N not routed to the ESP32 | SC p3 |
| I²C bus 0 SDA / SCL: OLED, magnetometer, BME280, **MS5611** | 17 / 18 | same | PN1-1 / PN1-2 | SS; LU L496–497; LH L134–139 |
| I²C bus 1 SDA / SCL: AXP2101 0x34, RTC 0x51 | 42 / 41 | same | on module | SC p1; LU L499–500; M L3–4 |
| BOOT button | 0 | same | button | SC p2; LU L508; M L9 |
| Cutter A gate `CUT_A_GATE` | **38** | 15 | PN1-8 | SS; DS |
| Cutter B gate `CUT_B_GATE` | **21** | 16 | PN1-12 | SS; DS |
| Heartbeat in `HEARTBEAT` (opto to ground) | **39** | 21 | PN1-7 | SS; DS |
| Cell voltage `FTU_VBAT_SENSE` | **3** (ADC1_CH2) | 2 | PN1-10 | SS; DS |

Why the harness pins moved:

- GPIO15 / 16 are the 32.768 kHz crystal (SC p2) and reach no header. The old
  cutter pins could not have been wired.
- The carrier breaks out only GPIO48, 21, 3, 38, 39, 45, 46, GPIO2
  (`RADIO_RETAIN`, also wired to radio module pin 6), GPS_PPS, bus 0, and
  UART0 (43 / 44) (SS). Of these, 45 and 46 are strapping pins, 43 prints the
  ROM boot log, 39 has a pull-up from reset (pad JTAG), and 2 is shared with
  the radio. 38 and 21 are the two that come out of reset high-impedance with
  no pull and no power-up glitch (DS Tables 2-1, 2-2, 3-1); they are not
  adjacent on PN1. 48 is spare.
- GPIO3 is the only unshared ADC pin on the headers. It is ADC1 (no ADC2
  restriction). It is the JTAG-select strapping pin, read only if eFuse
  `STRAP_JTAG_SEL` is burnt, which is not the factory state (DS §3).

Radio and GNSS settings:

| Setting | Value | Was | Source |
| --- | --- | --- | --- |
| DIO2 as RF switch | yes | yes | M L30; LF L1476 |
| TCXO on DIO3 | 1.8 V | 1.8 V | M L31. LilyGO's example uses RadioLib's default 1.6 V (LF L1421). Rated TCXO supply **unverified** (no module datasheet) |
| PA current limit | 140 mA | 140 mA | LF L1617 |
| GNSS baud | 9600 | 9600 | LU L539. A receiver reconfigured by earlier firmware may differ (LB L841 probes) |
| MS5611 address | **0x76** | 0x77 | the on-board BME280 is at 0x77 on the same bus (SS: SDO pulled high; LH L139) |

### Power rails (AXP2101)

| Rail | Feeds | Firmware | Source |
| --- | --- | --- | --- |
| DCDC1 → `VDD3V3` | ESP32-S3; PM1-10 | default on, untouched | SC p1; LH L173 |
| ALDO1 | OLED, magnetometer, BME280, bus 0 pull-ups; PN1-4 | 3.3 V, on (before bus 0 is used: LH L143–147) | SS; LH L179; LB L193; MP L1287–1289 |
| ALDO2 | "sensor" (IMU) | 3.3 V, on (**new**) | LH L180; LB L196; MP L1278–1285 |
| ALDO3 | SX1262 VCC | 3.3 V, on | SC p3; LH L181; LB L180; MP L1270–1272 |
| ALDO4 | GNSS VCC | 3.3 V, on | SC p3; LH L182; LB L176; MP L1262–1268 |
| BLDO1 | SD card | off | LH L183 |
| BLDO2, DCDC3–5 | M.2 / PM1 header | off | LH L175–177, L184 |
| VRTC | GNSS V_BCKP | — | SC p1, p3 |

All LDO inputs (`ALDOIN`, `BLDOIN`) and all DCDC inputs are `VSYS` (SC p1).
`VSYS` exists only when the PMU is fed at `VBUS` or `BAT`.

### Power feed — the netlist is wrong

`connections.csv` feeds 3.3 V from `FTU_REG` to an FTU port `3V3_IN`. The only
3.3 V pin on the board is `VDD3V3` (PM1-10), which is the *output* of DCDC1.
Back-feeding it runs the ESP32-S3 but leaves `VSYS` at zero, so the PMU is
unpowered, ALDO3 and ALDO4 cannot turn on, and **the radio and GNSS are
dead** (SC p1, p3). The firmware would log "no AXP2101" and fly without them.

The supported inputs are (LH L163–167; SC p1; SS):

- `VBUS` (USB-C, or PM1-2): 3.9–6 V. **Use this**, from a regulated 5 V.
- `VBAT` (18650 holder, or PY1 / PM1-1): a single 3.7 V Li-ion, behind a
  charger. Carrier V3.1 puts a 5.0 V TVS and a Li-ion protector on it (SS).
  Primary cells must never be connected here: the PMU would charge them, and
  3S L91 (up to 5.4 V) exceeds a one-cell input.

`components.csv` gives the 3S L91 pack as 3.3–5.4 V, which falls below the
3.9 V `VBUS` minimum, so the pack cannot feed `VBUS` directly either; it needs
a buck-boost to 5 V. Required
change (not made here; `hardware/` is not this page's to edit):

| File, row | Field | Now | Should be |
| --- | --- | --- | --- |
| `components.csv` `FTU_REG` | name / part | FTU 3.3 V buck / Pololu S7V8F3 class | FTU 5 V buck-boost / Pololu S7V8F5 class (5 V out; its input range is from memory, **unverified**) |
| `connections.csv` `FTU_3V3,FTU_REG,3V3,FTU,3V3_IN` | net, ports | `FTU_3V3`, `3V3` → `3V3_IN` | `FTU_5V`, `5V` → `VBUS` (PM1-2; ground PM1-3) |
| `connections.csv` `FTU_3V3,FTU_REG,3V3,FTU_BARO,VCC` | net, from | `FTU_3V3`, `FTU_REG` `3V3` | `FTU_ALDO1`, `FTU` `A_LDO1` (PN1-4, 3.3 V; ground PN1-3) |
| `connections.csv` `I2C_FTU` | `i2c_addr` | `0x77` | `0x76` (MS5611 CSB tied high) |
| `components.csv` `FTU` | `v_min`, `v_max` | 3.0, 4.3 | 3.9, 6.0 (the `VBUS` range) |

The barometer moves to ALDO1 because the bus pull-ups are on ALDO1 and a
sensor powered from another rail can hang the bus (LH L143–147); a bare
MS5611 cannot take 5 V.

## Not verified, and known gaps

Checked against documents only, not on a board: every pin, rail and radio
setting above. Not found in any primary source:

- the TCXO's rated supply voltage (1.8 V and 1.6 V are both in use upstream);
- the AXP2101's own limits and defaults — absolute maximum on `VBUS` and
  `BAT`, default input current and voltage limits, behaviour with no cell on
  `BAT` (no datasheet obtained; only LilyGO's "3.9–6 V" figure);
- header pin positions on carrier V3.0;
- the GNSS baud rate of a board that arrives with other firmware on it, and
  whether the MAX-M10S ignores the level on its pin 5 (the vendor code drives
  it high on both GNSS builds, and so does this firmware);
- flash size and mode on the actual module (read the esptool banner).

Not run on hardware — all of it:

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

- **Cell-voltage divider.** Resolved in the netlist: `FTU_VSENSE` is now
  100 k over 47 k (divide by 3.13), which is what `kVbatDivider` assumes.
  The first netlist had 2 x 100 k, with which the firmware would have read
  1.56x high and fired without under-voltage checks.
- **Power feed.** Resolved in the netlist: the board is fed 5 V at VBUS from
  a buck-boost, not 3.3 V back-fed into its regulator output (which leaves
  the radio and GNSS rails dead). The barometer is powered from the board's
  ALDO1 rail. The regulator's input range is still to be confirmed.
- **Barometer address.** The MS5611 must be strapped to 0x76 (see Pins).
- **Gate pull-downs.** The gate pins are high-impedance during reset and
  boot. Each MOSFET needs a gate-to-source pull-down in the FTU box.
- **No physical safe plug.** The software arming rule is the only thing
  between a powered FTU and a hot wire. A remove-before-flight link in
  `FTU_RAW` to the cutters would be the hardware barrier.
- **Power path.** The netlist's 3.3 V feed leaves the radio and GNSS
  unpowered; see "Power feed" above for the required change.
- **PMU power key.** With no cell on `BAT`, the PMU starts when `VBUS`
  appears; that it always does so unattended is **unverified**. The firmware
  sets the longest power-key off time (10 s) and masks PMU interrupts.
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
threshold; press BOOT just after power-on and hold it 3 s to clear stored
state.

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
