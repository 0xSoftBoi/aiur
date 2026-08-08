# Dock electrical evidence packet

Status: pre-power-on analysis; no rail, contact, or transient on this article
has been measured yet
Applies to: P0-A1 dock article, its S1/S2 sensing harness, the XL330 keeper
actuator, the OpenRB-150 bench controller, and the bench fault-insertion unit
Closes: the electrical half of the P0-A1 entry condition — the pack that has to
exist before the first rail is energised

## Why this document exists

Everywhere else in this program, an article earns the next step by producing
evidence. Electrical hardware is the one place where the first attempt is also
the destructive one: a mis-set current limit, a swapped connector, or a rail
that collapses under the servo will damage parts or, worse, produce an article
that works today and lies in three weeks. High-reliability practice therefore
gates power-on on two things that cost nothing before the parts arrive —
a worst-case analysis showing every part inside a stated derated limit, and a
rail-by-rail power-on checklist run against a current table written in advance.

This packet is those two things, plus the three findings that fall out of doing
them: the switch contact metallurgy is a safety item, the servo and the
controller must not share a rail, and one of the switch datasheet parameters
(operating force) does not currently close against the aircraft.

Power-on and first motion are gated on this document and its checklist, not on
optimism.

## What this analysis is and is not

This is a **WCCA-lite for a bench prototype**, not a worst-case circuit
analysis. A formal WCCA propagates component tolerance, temperature
coefficient, and end-of-life drift through every node by extreme-value, RSS, or
Monte Carlo methods and reports the resulting distribution. Nothing of the sort
is done here. What is done:

- one worst-case corner per part — maximum current at stall, minimum supply
  voltage, maximum bench ambient — evaluated by hand;
- resistor tolerance carried only where it changes a decision (the pull-up
  sizing);
- no aging model, no temperature-coefficient math, no statistical stack-up.

Every rating below is either read from a datasheet fetched for this program and
attributed, or written as **target, verify at order** and carried as an open
item. The derating fractions themselves are this program's choices, stated
plainly so they can be argued with:

| Quantity | Fraction held | Note |
| --- | --- | --- |
| Current rating | ≤0.50 | applied to conductors, contacts, connectors, supplies |
| Voltage rating (passive parts) | ≤0.80 | |
| Absolute maximum supply band (servo) | 0.5 V standoff from each endpoint | the recommended point is already well inside the band |
| Cycle-life rating | ≤0.10 | switches, connector mating cycles |
| Temperature span to the upper limit | ≤0.70 | |

These fractions are not drawn from NAVSEA SD-18, ECSS-Q-ST-30-11C, or NASA
EEE-INST-002. Those designations are reported in the
[practice survey](engineering-practice-survey.md); none of them was read for
this packet, and this document does not claim compliance with any of them. This
is a civilian indoor prototype borrowing the shape of the practice, at a scale
where one engineer with a datasheet and a scope is the whole electrical
organisation.

## Worst-case and derating table

Worst-case applied conditions assume: keeper commanded closed into a jam
(`SERVO_STALL`), bench supply at its low tolerance, room at the upper end of the
target ambient band, and every conductor carrying its maximum credible current
at once.

| Item | Parameter | Rating (source) | Worst-case applied | Derated limit held | Status |
| --- | --- | --- | --- | --- | --- |
| XL330-M288-T | input voltage | 3.7 V min / 5.0 V recommended / 6.0 V max (ROBOTIS e-manual) | 5.0 V nominal, unmeasured sag during stall | 4.75–5.25 V at the servo connector; hard ceiling 5.5 V (0.92 of max) | scope capture outstanding |
| XL330-M288-T | stall current | 1.47 A at 5.0 V (e-manual) | keeper jammed, commanded closed | supply limit 2.0 A; every conductor and contact in the servo path rated ≥3 A → ≤0.49 | conductor/contact ratings are targets |
| XL330-M288-T | standby current | 17 mA (e-manual) | continuous while powered | budget line, no derate needed | held |
| XL330-M288-T | operating temperature | −5 to +70 °C (e-manual) | 18–28 °C target ambient; case temperature after repeated stall unmeasured | case ≤50 °C (0.71 of the upper limit) | target, no thermal measurement exists |
| S1/S2 switch | contact rating (ceiling) | 30 VDC 0.1 A, gold alloy — D2F-01 (Omron D2F datasheet B036-E1-12) | 3.3 mA at 3.3 V through the pull-up | 0.033 of the rating | held by design |
| S1/S2 switch | **minimum applicable load (floor)** | 1 mA at 5 VDC — D2F-01 (same datasheet) | 3.3 mA at 3.3 V; the boundary extrapolates to ≈1.5 mA at 3.3 V (see below) | ≥2.0× the extrapolated floor at worst-case tolerance | held by design; verified as built at power-on step 6 |
| S1/S2 switch | electrical durability | 100,000 operations min at 30 ops/min — D2F-01 (same datasheet) | ~5,000 operations across run-in, 600 P0-A life cycles, P0-B/C/D and run-to-failure | ≤10,000 operations (0.10 of the rating) | held; recount if run-to-failure is extended |
| S1/S2 switch | mechanical durability | 1,000,000 operations min at 60 ops/min (same datasheet) | as above | ≤0.01 of the rating | held |
| S1/S2 switch | initial contact resistance | 100 mΩ max — D2F-01 (same datasheet) | in series with a 1.0 kΩ pull-up | 0.1 Ω / 1000 Ω = 1×10⁻⁴ of the divider; 0.33 mV at 3.3 mA | decode is insensitive to in-spec resistance; the failure mode is out-of-spec film |
| S1/S2 switch | max operating force | 1.47 N standard, 0.74 N for the `F` variant (D2F model-number legend) | docked aircraft + probe static weight ≈47.7 g = 0.468 N | actuation force ≥2× the switch max operating force | **not held — open item, see below** |
| S1/S2 switch | ambient / sealing | −40 to +85 °C, IP40 (same datasheet) | bench ambient; solvent or flux near the switch during rework | no liquid cleaning anywhere near S1/S2; IP40 offers no liquid protection | procedural |
| Pull-up resistor | resistance / power | 1.0 kΩ ±1%, ≥0.125 W (target part; value derived below) | 3.3 V across R with the contact closed → 10.9 mW | 0.087 of the part rating | held by design |
| Pull-up resistor | working voltage | ≥50 V (target, typical chip-resistor rating) | 3.3 V | ≤0.07 | target, verify at order |
| Harness, servo pair | continuous current | ≥3 A conductor (target, verify at order) | 1.47 A stall | ≤0.49 | target |
| Harness, signal conductors | continuous current | ≥1 A conductor (target) | 3.3 mA per contact | ≤0.004 | target |
| Harness, all conductors | insulation voltage | ≥30 V (target) | 5 V | ≤0.17 | target |
| Connector, servo path | contact current | JST EHR-03 on the OpenRB DYNAMIXEL ports (OpenRB e-manual); contact current rating **target, verify at order** | 1.47 A stall | ≤0.5 of the contact rating | target |
| Connector, S1 and S2 | contact current | target, verify at order | 3.3 mA | negligible | target |
| Connector, all | mating cycles | ≥50 (target, verify at order) | one demate per fault-insertion trial plus rework | ≤0.10 of the rated cycles; demates logged on the build sheet | target |
| Fault-insertion relays | contact rating and switching regime | target: rated ≥10× the carried current **and** specified for low-level/dry-circuit switching ([fault-insertion.md](../hardware/dock/fault-insertion.md)) | 3.3 mA on the signal paths; 1.47 A on the servo interrupt | ≤0.10 of the rating | target, part not selected |
| 5 V servo rail | supply current | ≥3 A current-limited bench supply (BOM) | 1.47 A stall | ≤0.49 | held **only if the rail is dedicated** |
| Controller rail | pin/port current | OpenRB-150: input 3.7–12.6 V or 5 V USB; 3.3 V pin ≤300 mA; 5 V pin ≤300 mA; DYNAMIXEL ports ≤3,000 mA (OpenRB e-manual) | 13.2 mA of pull-up current worst case, plus the MCU | ≤0.05 of the 300 mA pin limits | held |
| Shared servo + controller rail | supply current | as above | 1.47 A stall + 0.6 A of pin budget = 2.07 A against a 3 A supply | 0.69 — above the 0.50 fraction held everywhere else | **rejected; see rail split** |

### What the table decides

Two rows are not bookkeeping.

**The shared-rail row fails its own derate**, and steady-state current is the
weaker of the two objections. The transient is the real one, and it has its own
section below. The design consequence is a rail split: the servo runs from the
dedicated ≥3 A bench supply, the controller runs from its own source, and the
two share exactly one ground point at the controller.

Whether the OpenRB-150 can be fed that way — MCU from USB, DYNAMIXEL port power
from the bench supply — is **not established here**. The e-manual confirms
DYNAMIXEL port power is switched by a FET independently of MCU power, which is
encouraging and is also what makes the kill-path check meaningful, but it is not
a statement that the two can be sourced separately. Verify from the OpenRB
documentation at build; if they cannot be separated, the split requires driving
the servo through a power injector on the TTL bus or a second controller-side
supply. Open item.

**The switch operating-force row does not close.** A docked aircraft plus its
probe allocation is about 47.7 g ([p0a-bench.md](../hardware/dock/p0a-bench.md)),
i.e. 0.468 N hanging weight. The lowest-force D2F variant in the legend has a
*maximum* operating force of 0.74 N. So:

```
docked static weight            0.468 N
D2F     max operating force     1.47 N   -> 0.32x the force needed
D2F-01F max operating force     0.74 N   -> 0.63x the force needed
```

Two consequences, both mechanical, both flagged here because the number came
out of an electrical datasheet:

1. S1 cannot be actuated by the aircraft's weight. Seating force must come from
   the approach stroke and climb thrust, from the collet insertion force, or
   from mechanical advantage (a hinge-lever actuator such as the `L` variants
   trades travel for force at the plunger).
2. More seriously, S1 must not *depend on a maintained force* to stay actuated.
   Once the keeper is closed and the aircraft is disarmed, the probe hangs from
   the keeper tines and the only downward force available is 0.468 N. If S1 is
   held actuated by insertion force rather than by probe *position*, it releases
   under the hanging load, the controller sees `seat_switch` go false in
   `CAPTURED`, and `aiur/dock_controller.py` transitions to `FAULT_LOCKED` with
   `capture_sensor_disagreement` — the safe direction, but a spurious fault on
   every capture.

Both are A0 fit measurements, not analysis: measure the actual force available
at the S1 plunger at the seated position and at the hanging position before the
switch variant is frozen. Until then, the actuator style (plunger vs lever) and
the operating-force code stay open on the BOM line.

## Switch contact wetting current

This is the most consequential section in the packet, and the whole of it
resolves to one BOM line.

### The mechanism

A switch contact is a metal-to-metal interface with a surface. On silver and
silver-alloy contacts that surface grows films — sulphides, oxides, and
adsorbed organics — continuously, from ordinary room air. In a circuit carrying
useful current the film is destroyed as fast as it forms: the arc and the
localised heating at make and break disrupt it. That is what "wetting current"
means. It is not a property of the switch; it is a property of the *circuit the
switch is in*.

A contact carrying only logic-level current has no such mechanism. Nothing
disrupts the film, so contact resistance climbs — not to a clean open, but to a
noisy, load-dependent, temperature-dependent, position-dependent value. The
resulting failure has three properties that make it worse than an outright
break:

- **Delayed onset.** The mechanism works perfectly on the day it is built, and
  for days or weeks after, because the film needs time to grow. A P0-A campaign
  can pass cleanly on a switch that will fail at P0-C.
- **Intermittency.** It appears and clears. It clears especially readily when
  someone actuates the switch by hand a few times while debugging, which is
  precisely what an engineer does when investigating it.
- **No event.** There is no moment to correlate against, no shock, no command,
  nothing in the log. It presents as "the dock is flaky."

Omron's own precaution note is the primary statement of the rule, verbatim from
the D2F datasheet: *"Using a model for ordinary loads to open or close the
contact of a micro load circuit may result in faulty contact. Use models that
operate in the following range."*

### What the datasheet actually promises

The minimum applicable load is not a warning label; it is the boundary of the
vendor's reliability claim. Omron defines it verbatim:

> "The minimum applicable load is the N-level reference value. This value
> indicates the malfunction reference level for the reliability level of 60%
> (λ60). (JIS C5003) The equation, λ60=0.5×10⁻⁶/operation, indicates that the
> estimated malfunction rate is less than 1/2,000,000 operations with a
> reliability level of 60%."

Read that precisely. Above the minimum applicable load, the vendor asserts a
malfunction rate below 1 in 2,000,000 operations. Below it, the vendor asserts
**nothing at all**. A design that runs a silver contact at 1 mA is not a design
with a known small failure rate; it is a design with no failure rate.

| Variant | Contact material | Minimum applicable load | Rated resistive load |
| --- | --- | --- | ---: |
| D2F, D2F-5 | silver alloy | 100 mA at 5 VDC | 125 VAC 3 A / 30 VDC 2 A (D2F) |
| **D2F-01** | **gold alloy** | **1 mA at 5 VDC** | 30 VDC 0.1 A |

Source for both rows: Omron D2F datasheet B036-E1-12.

### Why this is a hardware fix and not a software one

The twin's fault menu injects a stuck seat switch, open or closed, and two of
its five standing findings turn on that fault:

- Finding #2 — a stuck seat switch defeats `S1 AND S2` unless the supervisor
  refuses to enable capture on its own relative estimate.
- Finding #5 — a stuck-closed seat switch combined with a masked navigation
  bias walks the real controller to a confirmed capture on an empty dock, and
  no supervisor built on the same measurements can tell. That one is carried as
  an accepted residual, not a solved problem.

Film is the physical mechanism behind the **open and intermittent** members of
that family. It maps directly onto `S1_OPEN` and `S2_OPEN` on the required
fault-insertion list, and onto the twin's stuck-open switch fault. It is not the
mechanism behind `S1_SHORT` — a stuck-*closed* read comes from a jammed plunger,
a bent lever, a probe left seated, or a harness short, and film cannot cause it.
This packet does not claim otherwise.

What the two directions share is the property that matters for a BOM decision:
once the supervisor is trusting the switch, software has already lost. The
dual-contact decode in
[p0a-fabrication.md](../hardware/dock/p0a-fabrication.md) does catch a filmed
contact — a contact that should read low reading high makes the NC/NO pair
invalid, and the decode calls it a wiring fault — but detection is not
prevention. It converts a silent lie into a stopped campaign, which is the right
trade and still costs the campaign. The only pre-emptive control available at
P0 is the metallurgy, and it costs the same as the wrong part.

Everything else in this program is fixed by an analysis, a gate, or a line of
code. This one is fixed by ordering a different part number.

### Specification: contact metallurgy

S1 and S2 shall be gold-alloy or gold-crosspoint contact variants specified for
micro-load switching, with a published minimum applicable load reachable by a
logic pull-up.

- Baseline: **Omron D2F-01 family** — gold alloy, minimum applicable load 1 mA
  at 5 VDC, rated 30 VDC 0.1 A, electrical durability 100,000 operations
  minimum. Actuator style and operating-force code stay open pending the A0
  force measurement above; the `01` ratings code does not.
- Second source: **ZF (Cherry) DB3** — the 0.1 A low-energy series of a family
  that lists `AuAgPt (Crosspoint)` among its contact materials. Two caveats
  before this counts as a qualified alternate: the ZF datasheets do not publish
  a minimum applicable load in the material read for this packet, and the
  order-code digit that selects gold crosspoint exists only as an image that
  could not be text-verified. Obtain both from ZF or a distributor parametric
  listing before ordering; an unconfirmed second source is not a second source.

### Pull-up sizing, with the arithmetic

Ohm's law, one contact, contact closed to ground:

```
I_contact = V_logic / R_pullup
```

The OpenRB-150 circuit operates at 3.3 V (OpenRB e-manual), so `V_logic` = 3.3 V.

The datasheet floor is quoted at 5 V, and the boundary is voltage-dependent: the
micro-load chart bounds the D2F-01 range at 1 mA at 5 V and 0.16 mA at 30 V.
Those two points are a constant-power line to within the resolution of the
chart —

```
5 V  x 1.00 mA = 5.0 mW
30 V x 0.16 mA = 4.8 mW
```

— which means the required *current* rises as the voltage falls. Extrapolating
that ≈5 mW boundary down to the 3.3 V logic rail:

```
I_min(3.3 V) = 5.0 mW / 3.3 V = 1.5 mA
```

The extrapolation is ours, not Omron's; the datasheet chart is not drawn below
5 V. It is the conservative reading, so the design holds to it.

Sizing, nominal:

```
R = 1.0 kohm  ->  I = 3.3 V / 1000 ohm = 3.30 mA
                  3.30 / 1.0 = 3.3x the datasheet floor stated at 5 V
                  3.30 / 1.5 = 2.2x the extrapolated floor at 3.3 V
                  P = 3.3^2 / 1000 = 10.9 mW  (0.087 of a 0.125 W part)
```

Sizing, worst case — logic rail at −5 %, resistor at +1 %, contact and harness
resistance negligible against 1 kΩ:

```
I = 3.135 V / 1010 ohm = 3.10 mA  ->  2.07x the extrapolated floor
```

The margin factor held by the design is therefore **≥2.0× at worst-case
tolerance against the extrapolated 3.3 V boundary, ≥3.1× against the datasheet's
stated 1 mA at 5 VDC**. If the as-built measurement at power-on step 6 comes in
below 3.0 mA, drop to 680 Ω (4.85 mA, 3.2× extrapolated, 16 mW).

Total sink current: four pull-ups, one per contact, two contacts per SPDT
switch. In any valid decode state exactly one contact per switch is closed, so
the nominal load is 2 × 3.3 = **6.6 mA**; a both-contacts-closed fault state
gives 13.2 mA. Both are negligible against the OpenRB's 300 mA pin limits, and
the current flows to ground through the switch COM, not into a high-impedance
MCU input.

**Internal MCU pull-ups are not acceptable here.** SAMD21-class internal
pull-ups are in the tens of kilohms, which puts the contact current in the tens
to low hundreds of microamps at 3.3 V — an order of magnitude below the floor,
in the region where the vendor makes no claim. The exact internal value is not
read for this packet; verify it from the SAMD21 datasheet at build, then disable
the internal pull-ups and use external resistors regardless of what it says.

### Why silver contacts cannot be rescued by a resistor

The arithmetic that closes the argument. For a silver-alloy D2F at its 100 mA
minimum applicable load, on a 3.3 V logic rail:

```
R = 3.3 V / 0.100 A = 33 ohm
P = 3.3^2 / 33 = 0.33 W per contact, continuous while the contact is closed
    x4 contacts = 1.3 W of pull-up dissipation
```

A third of a watt per contact, continuously, on a carried dock, through a signal
harness, so that a logic input can be read. That is not a logic interface. The
metallurgy is the fix; the resistor only sizes it.

### Contact protection and inrush

The same datasheet adds a second-order warning, verbatim: *"even when using
micro load models within the following operating range, if inrush current occurs
when the contact is opened or closed, it may increase the contact wear and so
decrease durability. Therefore, insert a contact protection circuit where
necessary."* The inrush source in this circuit is the harness and input
capacitance discharging through the contact at make. Keep the S1/S2 runs short,
and if the as-built rise time at the MCU input suggests significant capacitive
discharge, add a small series resistance at the contact end. Target, conditional
on measurement; not fitted by default.

## Rail transient and controller brownout

### Why a multimeter reads 5.00 V while the controller resets

The XL330 stalls at 1.47 A at 5.0 V; it idles at 17 mA. A keeper close is a
step of roughly two orders of magnitude in load, delivered in whatever time the
supply's control loop and the harness inductance permit. If the controller
shares that rail, the sag lands on the MCU. The event is milliseconds or shorter,
and a DC multimeter averages over hundreds of milliseconds — so it reads
nominal, every time, while the controller resets.

The existence proof, from a different circuit and cited as such: on a shared 5 V
rail with an ATtiny88 and a hobby servo, the rail *"typically dips to 3.5 VDC or
so"* on servo inrush, and the worst transient recorded sagged to 1.3 V for a few
hundred nanoseconds then stayed below 2.5 V — timescales the write-up explicitly
notes are invisible to a DC multimeter. That is a different MCU, a different
servo, and a different supply; it is evidence that the mechanism is real and
that the instrument matters, not a prediction for this rail.

The failure it produces on a SAMD21 is documented and specific: without the
brown-out detector enabled, the part can start up, switch to 48 MHz, configure
the NVM for one wait state, and run below the voltage that configuration
requires — corrupting NVM, with the first flash page erased. (From a
practitioner write-up; Microchip's application note is reported to corroborate
it and was not read here.)

### Why this program cares more than most

Twin finding #1 is that the guidance stack must **latch** the capture enable
once seating is confirmed, because gating it on a noisy per-sample seat estimate
flaps the controller into `FAULT_OPEN`. A reset erases exactly that latch. A
brownout during `LOCKING` therefore destroys the state that a twin campaign
proved necessary, at the one moment in the cycle when an aircraft is committed
to the funnel.

`CONTROLLER_RESET_DURING_LOCK` is on the required fault-insertion list
([fault-insertion.md](../hardware/dock/fault-insertion.md)) for precisely this
reason, and its required response is written: on restart the controller does not
assume a capture it cannot observe, re-reads S1/S2, reports the true state, and
a latched capture-enable does not survive a reset as a capture claim. The
mitigations below reduce how often the fault occurs. The fault-insertion trial
proves the response is right when it occurs anyway. Both are required.

### Measurement specification

Run this before any loaded motion, and again after any change to the power
architecture. It produces one number per trial: the minimum rail excursion.

| Parameter | Specification |
| --- | --- |
| Instrument | ≥20 MHz two-channel oscilloscope, 10× probe, spring-tip or short pigtail ground — not the alligator lead (target instrument; a long ground lead will manufacture the ringing it is meant to measure) |
| Probe point | the controller's own supply pins, at the controller — not the bench supply terminals. Record which node (5 V input or 3.3 V rail) was probed; the brownout-relevant node is whichever one the BOD monitors |
| Channel 2 | servo supply current via current probe or a 0.1 Ω shunt (target part); if neither exists, the servo command line as a timing reference |
| Coupling | DC on both channels — absolute level is the measurement, not ripple |
| Timebase | 2 ms/div for the full keeper motion (≈20 ms window), plus a 20 µs/div capture of the leading edge |
| Trigger | single-shot, falling edge on the rail at nominal −5 % (3.13 V on a 3.3 V rail, 4.75 V on a 5 V rail), pre-trigger ≥20 % of the record so the intact rail is visible before the event |
| Measurements recorded | minimum rail voltage over the record (scope minimum measurement, not eyeball), duration below the BOD threshold, and time from servo command to minimum |
| Conditions, ≥20 trials each | keeper close from open; keeper open from closed; commanded close into a blocked keeper (`SERVO_STALL`); servo power-on inrush; and the worst case, stall at the minimum supply voltage used for the force-margin measurement |
| Logged with | `run_id`, git SHA, hardware revision, and the power architecture in force, into the P0-A evidence set |

Acceptance, all targets until the controller's own numbers are read: the minimum
rail excursion stays above the configured brown-out reset level by ≥0.3 V, and
above the minimum operating voltage for the configured clock frequency. **The
SAMD21 BOD33 level encoding and the OpenRB-150's own minimum are not reproduced
here — read them from the controller documentation at build and write the two
numbers into this table before the first capture.**

### Mitigations to design in

1. **Rail split.** Dedicated supply for the servo; separate source for the
   controller; a single common ground point at the controller. This is the
   primary mitigation and the one the derating table already forces. Subject to
   the open item above about whether the OpenRB can be fed that way.
2. **Bulk capacitance on the servo rail**, at the servo connector, not at the
   supply. Sizing is `C = I·Δt/ΔV`, and running it honestly is the point:

   ```
   1.47 A held for 1 ms within 0.25 V  ->  C = 5,880 uF
   1.47 A held for 100 us within 0.25 V ->  C =   588 uF
   ```

   Bulk capacitance is therefore an **inrush-edge** measure, not a
   sustained-stall measure. No practical bench capacitor holds a 1.47 A stall.
   A sustained stall is handled by the supply's current capability and by not
   sharing the rail. Specify 1,000 µF, ≥16 V (3.2× voltage derate on a 5 V
   rail), low ESR — covering roughly 170 µs at full stall within 0.25 V.
   Engineering target; resize from the measured transient.
3. **A local energy island for the controller**, if the measurement shows it is
   needed: a Schottky diode in series with the controller feed and bulk
   capacitance after the diode, so the controller cannot be pulled down by the
   servo rail. Same arithmetic, controller-side current:

   ```
   100 mA held for 1 ms within 0.3 V  ->  C = 333 uF   (fit 470 uF)
   100 mA held for 5 ms within 0.3 V  ->  C = 1,667 uF
   ```

   The 100 mA figure is a target — measure the controller's actual draw at
   power-on checklist step 3 and resize. The Schottky drop costs 0.3–0.4 V of headroom,
   which the OpenRB's 3.7–12.6 V input range absorbs comfortably on the VIN
   path and does not absorb on a 5 V USB feed. Conditional part; do not order
   before the scope capture.
4. **Brown-out detector configured to reset, not to run undervolt.** Enable
   BOD33 with the reset action, at or above the minimum operating voltage for
   the configured clock, with hysteresis enabled for a noisy supply, and set via
   fuses where possible so it holds from the first instruction rather than from
   whenever application code gets around to it. A detector configured to
   interrupt, or left at its default disabled state, converts a clean reset into
   silent undervolt execution — the NVM-corruption case above.
5. **Separate supply for the fault-insertion unit**, already required by
   [fault-insertion.md](../hardware/dock/fault-insertion.md), so a commanded
   brownout trial does not also disable the injector that commanded it.
6. **No capture state in non-volatile memory.** The controller re-derives its
   state from S1/S2 after every reset. This is already the required response for
   `CONTROLLER_RESET_DURING_LOCK` and is restated here because it is the
   mitigation that costs nothing.

## Harness workmanship rules

### Why a half page of workmanship rules earns its place

Field data concentrates reliability effort on interconnect, not on parts:
intermittent connector and harness failures under vibration dominate avionics
no-fault-found removals, and the industry answer is workmanship standards
(NASA-STD-8739.4A, IPC/WHMA-A-620) rather than more analysis. Those designations
come from the [practice survey](engineering-practice-survey.md); neither
document was read for this packet, and nothing below claims conformance to
either. What follows is an A-620-*informed* half page, scaled to a bench
prototype.

The sequencing problem is worse than the general case. Environmental screening
doctrine says: measure your own platform's vibration, then screen against it
before flight. On this program the dock's harness, crimps, and switch brackets
get their **first vibration exposure on the flying carrier at P0-C** — the
article's most expensive test is also its first shake test. That is backwards.
Until a PSD is measured on the P0-B rig and a screen is run against it (target,
carried as an open item), the only defence is that the harness is built
correctly the first time and inspected after every session.

### Rules

| # | Rule | Why |
| --- | --- | --- |
| H1 | Strain relief at every termination: the conductor is anchored to structure within 25 mm (target) of the connector so that no handling load reaches the crimp or solder joint. | The joint is the stress riser; anything that loads it is a future intermittent. |
| H2 | Service loop of ≥30 mm (target) of dressed, tied slack at each end. | A connector must be mateable and a switch bracket shimmable without tensioning the harness. Slack that is not dressed and tied is a flail hazard, not a service loop. |
| H3 | No unsupported wire at a connector. Every run is clamped or tied to structure within 50 mm (target) of the connector body; nothing hangs on the contacts. | An unsupported run turns every vibration cycle into a cycle on the contact interface. |
| H4 | Crimp inspection, every crimp: correct contact/tool/die combination; conductor barrel closed on all strands with no strays outside; insulation support closed on insulation; conductor visible in the inspection window per the contact vendor's instruction; no nicked or cut strands. Every crimp gets a pull test to the contact vendor's stated force (target — obtain from the contact datasheet at order). One sample per lot and per tool setup is destructively pulled before production crimping. A crimp is never re-crimped: cut it off and start with fresh wire and a fresh contact. | A visual pass on a crimp with two strands outside the barrel is the classic delayed-onset interconnect failure. The destructive sample is what qualifies the tool setup, not the operator's confidence. |
| H5 | Keying and polarisation: S1 and S2 use connector arrangements that **cannot** be mated to each other's mate — different position counts are the strongest form (for example S1 on a 3-position housing, S2 on a 4-position with one position blanked), keying or housing series next. Colour coding alone does not count. | Swapping S1 and S2 exchanges "probe seated" with "keeper closed". The dual-contact decode does not catch it — both channels decode as valid — and the controller then confirms captures on the wrong evidence. This must be prevented by geometry, not by care. |
| H6 | **Separate connectors for S1 and S2.** One connector per channel, never a shared housing, and the two runs are not bundled under a single tie for their whole length. | This is a common-mode defence, not tidiness — see below. |
| H7 | Labelling at both ends of every conductor and on both halves of every connector, using the same signal names that appear in the telemetry and in the fault-insertion table (`S1_COM`, `S1_NC`, `S1_NO`, `S2_COM`, `S2_NC`, `S2_NO`, `SERVO_V+`, `SERVO_GND`, `SERVO_DATA`). Printed heat-shrink or laminated flags; not marker on insulation. | A log row and a physical wire should be the same object. A label that rubs off during the campaign takes the traceability with it. |
| H8 | No wiring in the funnel or probe load path, ever. | Already a P0-A stop condition in [p0a-bench.md](../hardware/dock/p0a-bench.md); repeated because it is a wiring rule that gets broken at assembly time. |
| H9 | Acceptance before first power-on (below) is a signed step, and any harness change after acceptance issues a new hardware revision and re-runs it. | The engineering loop's re-entry rule applied to copper: changed hardware does not inherit the old article's evidence. |
| H10 | After every P0-B session and before every P0-C session, inspect harness, crimps, connector retention, and switch brackets, and record the inspection. | Standing compensation for the missing vibration screen. Delete this rule when the PSD screen exists. |

### Why S1 and S2 get their own connectors

`capture_confirmed = S1 AND S2` is an independence claim. A shared connector
falsifies it in one part: a single housing carries both channels, so a single
retention failure, a single unseated latch, or a single mis-mate takes out both
interlocks at once. `S1_S2_BOTH_OPEN` is already on the required fault-insertion
list, described there as "shared harness/connector", because that is the
credible physical route to a both-channels loss.

In common-cause terms this is a hardware and environment coupling factor — same
component location, same connector, same mating event — of exactly the kind
NUREG/CR-5485 enumerates, and the published defences are the ones being applied
here: diversity, separation, and separate interconnections. It matters because
common-cause fractions are large: the synthesis in the NASA review puts β at
0.01–0.10 with good common-cause prevention and up to 0.25 with poor
engineering, and 11 % of 473 shuttle in-flight anomalies were judged common
cause. A redundant pair whose β is 0.25 is not the pair the multiplied
probabilities describe.

Two connectors, different position counts, separated routing, and (where the
supply chain permits) switches from different lots are the cheap end of "good
engineering" on that scale. The full treatment of correlated pairs — including
which pairs the twin should draw — belongs to the common-mode analysis
([common-mode.md](common-mode.md), ADOPT-004); this document supplies the
physical separation it will assume.

### Harness acceptance step

Run with the harness disconnected from both the controller and the switches.
Record pass/fail per conductor on the build sheet and keep the wire list with
the article.

1. Point-to-point continuity against the written wire list, every conductor,
   both directions of the list (list-to-hardware and hardware-to-list) so a
   missing wire is caught as well as a wrong one.
2. Adjacent-contact isolation ≥1 MΩ (target) on every connector.
3. Pull test on every termination to the contact vendor's stated force (H4).
4. Wiggle test: flex each termination and each service loop by hand while
   watching continuity on a meter with a continuity beeper or a fast display. A
   reading that flickers once is a reject, not a retest.
5. Keying check: physically attempt to mate the S1 harness connector to the S2
   mating half. It must not go together. Record the attempt.
6. Sign the acceptance line on the build sheet. No rail is energised before
   this signature exists.

## First power-on checklist

Preconditions, all of them: harness acceptance signed; keeper de-energised and
at its open stop; **no probe present**; the servo mechanically free to move
without hitting a stop; the state machine **not** connected to the switch
inputs; the article's configuration identity (`run_id`, git SHA, hardware
revision, actuator ID) recorded; the kill path checked per the P0-A test card.

The current table is written *before* the supply is switched on. Every value in
it is an engineering target until first measurement; a measured value that
differs is dispositioned and recorded, never quietly overwritten.

| Step | Configuration | Supply limit | Expected current | Stop if |
| --- | --- | ---: | --- | --- |
| 1 | Controller rail only; servo disconnected; pull-ups not connected | 0.5 A | ≤150 mA (target) | >0.3 A, any current-limit trip, or any heat |
| 2 | Pull-ups energised, S1/S2 connected, keeper de-energised | 0.5 A | step 1 + 6.6 mA in any valid decode state; 0 mA or 13.2 mA indicate an invalid pair | deviation >2 mA from the state the mechanism is visibly in |
| 3 | Servo rail energised, servo connected, not commanded | 2.0 A | 17 mA standby (e-manual) plus supply idle | >100 mA |
| 4 | First commanded motion, reduced travel and reduced current/torque limit, keeper disconnected from the probe | 2.0 A | <0.5 A peak (target) | limit trip, stall, audible binding, or any motion beyond the reduced limits |

Steps, in order:

1. Set the bench supply voltage **and** current limit with the output off, and
   read both back before enabling. Set the limit for the step, not for the
   campaign.
2. Verify common ground between the controller and the servo supply with a
   meter, per [p0a-fabrication.md](../hardware/dock/p0a-fabrication.md).
3. Energise the controller rail alone, servo disconnected. Compare against
   table row 1. Any deviation stops the power-on.
4. Connect S1/S2 and the pull-ups, with the state machine still disconnected.
   Compare against table row 2.
5. **Verify the S1/S2 decode with a meter, by hand actuation, before the state
   machine is connected**: released reads NC low / NO high, actuated reads
   NC high / NO low, and any other pair is a fault. This requirement already
   exists in [p0a-fabrication.md](../hardware/dock/p0a-fabrication.md) — this
   checklist is where it is executed and recorded, once per channel, for both
   S1 and S2.
6. Measure the **closed-contact current** on each of the four contacts and
   confirm ≥3.0 mA (design), floor 1.5 mA (extrapolated boundary). This is the
   wetting-current design verified as built rather than assumed. Record all four
   values; if any is below 3.0 mA, fit 680 Ω pull-ups and re-measure.
7. Energise the servo rail with the servo connected but not commanded. Compare
   against table row 3.
8. Run the rail-transient scope capture above **before** any loaded motion.
   Record the minimum excursion for keeper close, keeper open, and a deliberate
   stall.
9. First commanded motion: reduced travel limits established from the physical
   open and closed stops (already required by
   [p0a-fabrication.md](../hardware/dock/p0a-fabrication.md)), reduced velocity
   and current limit, keeper disconnected from the probe, a hand on the kill
   switch, and "KEEPER MOVING" called per the test card.
10. Only after both directions run clean at reduced limits, restore the full
    travel limits, re-run step 8, and then connect the state machine.
11. Record every measured value against the pre-written table in the article
    record, with the run identity.

## EMI self-compatibility check

The twin injects aircraft and dock pose dropouts as **exogenous** faults —
something that happens to the system from outside. Nothing has ever asked
whether the dock produces them. The XL330 is a PWM-driven motor stepping from
17 mA to as much as 1.47 A — a factor of about 86 — on a harness a few
centimetres from the aircraft's radio link and its optical positioning receiver,
at the exact moment of the cycle when the aircraft most needs both. If the dock
is a source,
then a fault the twin models as independent is actually correlated with keeper
motion, and the twin's fault model is wrong in a way that matters — a
`FAIL_MODEL` disposition, not a nuisance.

The test is an A/B, because absolute link statistics in one room on one
afternoon mean nothing.

| Element | Specification |
| --- | --- |
| Configurations | **A**: servo powered, idle, not commanded. **B**: servo cycling close/open continuously at the P0-A cycle rate. Identical in every other respect — same aircraft position, same radio channel, same lighting, same base-station geometry, same room, same session |
| Article state | Aircraft on a fixture at the docked or near-dock position (minimum separation is the worst case), propellers removed, battery installed only if the link requires it |
| Blocks | ≥5 alternating A/B blocks of ≥3 minutes each, so slow drift in the room cannot be read as an effect |
| Metrics | Crazyradio packet loss (link statistics from the client), Lighthouse pose validity fraction, dropout count, and dropout duration distribution — the same quantities the twin's sensor model parameterises |
| Coupled-noise check | With the scope still connected from the rail-transient work, watch S1/S2 for coupled noise during keeper motion; note whether the servo run is routed parallel to the switch harness |
| Control | Repeat one block with the DYNAMIXEL port power switched off, to separate motor emission from anything else in the enclosure |
| Analysis | Compare dropout and packet-loss rates between block sets against a noise band declared **before** the run. Any difference outside it is a dock-caused dropout term that goes into the twin as a keeper-correlated fault, replacing an exogenous one |
| If an effect exists | Shorten and separate the servo run from the switch harness; twist the servo power pair; decouple at the servo connector; single-point-ground the metal fixture. All targets; retest, do not assume |

This check belongs to the electrical packet rather than the sensing work because
its answer changes a BOM and a routing rule, not a filter constant.

## Basis and provenance

Per the program design rule, every number above resolves to a citation, an
executable model, a measurement, or a labelled target. Nothing here is measured
yet; the "measurement" column of this program's evidence for the dock harness is
empty by construction until P0-A1 is powered.

| Item | Value | Basis | Type |
| --- | --- | --- | --- |
| XL330 input voltage band | 3.7 / 5.0 / 6.0 V | ROBOTIS XL330-M288-T e-manual | cited spec |
| XL330 stall current, standby current | 1.47 A at 5.0 V; 17 mA | ROBOTIS XL330-M288-T e-manual | cited spec |
| XL330 operating temperature | −5 to +70 °C | ROBOTIS XL330-M288-T e-manual | cited spec |
| OpenRB-150 rails and port limits | 3.7–12.6 V or 5 V USB; 3.3 V circuit; 300 mA pin limits; 3,000 mA DXL ports; FET-switched port power; JST EHR-03 | ROBOTIS OpenRB-150 e-manual | cited spec |
| D2F contact material by variant | D2F/D2F-5 silver alloy; D2F-01 gold alloy | Omron D2F datasheet B036-E1-12 | cited spec |
| D2F minimum applicable load | 100 mA at 5 VDC (silver); 1 mA at 5 VDC (gold) | Omron D2F datasheet B036-E1-12 | cited spec |
| Minimum-applicable-load definition (λ60, JIS C5003) | as quoted | Omron D2F datasheet, "Using Micro Loads" precaution | cited spec, verbatim |
| Micro-load usage rule and inrush warning | as quoted | Omron D2F datasheet, same precaution | cited spec, verbatim |
| D2F ratings, durability, contact resistance, ambient, IP40 | 30 VDC 0.1 A; 100,000 / 1,000,000 operations; 100 mΩ; −40 to +85 °C | Omron D2F datasheet B036-E1-12 | cited spec |
| D2F operating-force codes | 1.47 N standard, 0.74 N `F` | Omron D2F model-number legend | cited spec |
| ≈5 mW micro-load boundary, 1.5 mA floor at 3.3 V | derived | constant-power fit through the datasheet's two chart bounds (5 V/1 mA, 30 V/0.16 mA); the extrapolation is ours | derived arithmetic on a cited spec |
| Pull-up value and margins | 1.0 kΩ; 3.30 mA nominal; 3.10 mA worst case; 2.07–3.3× | Ohm's law on the values above | derived arithmetic |
| Silver-contact pull-up infeasibility | 33 Ω, 0.33 W per contact | Ohm's law on the 100 mA figure | derived arithmetic |
| ZF/Cherry DB3 as second source | 0.1 A low-energy series; `AuAgPt (Crosspoint)` listed among family contact materials | ZF Subminiature DB datasheet 2024-11 | cited spec, incomplete |
| ZF minimum applicable load; gold order-code digit | not established | not published in the material read; order code exists only as an unreadable image | open item, verify before ordering |
| Internal MCU pull-up magnitude | "tens of kilohms" | reported in the program research; the SAMD21 datasheet was not read | reported, verify at build |
| Servo-brownout existence proof | 3.5 V typical dip; 1.3 V worst transient; invisible to a DC meter | NeuroBytes project log (ATtiny88 + hobby servo, shared 5 V rail) | cited practitioner measurement on a different circuit |
| SAMD21 BOD33 behaviour and the NVM-corruption case | reset or interrupt action, configurable level, hysteresis; first flash page erased when run undervolt at 48 MHz | practitioner write-up (blog.thea.codes); Microchip AT03789 reported to corroborate, not read | secondary source |
| BOD33 level encoding, OpenRB minimum operating voltage | not established | not read for this packet | open item, required before first capture |
| Capacitor sizing | `C = I·Δt/ΔV`; 5,880 µF / 588 µF / 333 µF results | arithmetic on the cited stall current and target Δt/ΔV | derived arithmetic on targets |
| Common-cause β range; shuttle 11 % | 0.01–0.10 with good prevention, up to 0.25 with poor engineering; 54 of 473 anomalies | NASA review collating IEC 61508, IAEA, Rutledge & Mosleh, Summers, Borcsok | cited synthesis |
| Coupling-factor taxonomy | hardware / operation / environment based | NUREG/CR-5485 §4.1.2 | cited standard |
| Docked aircraft weight | 47.7 g → 0.468 N | [p0a-bench.md](../hardware/dock/p0a-bench.md) mass allocation × 9.81 m/s² | repo value + arithmetic |
| Life-cycle count driving switch durability | 600 life cycles + run-in | `aiur/loop_graph.py` derivation, via [p0a-bench.md](../hardware/dock/p0a-bench.md) | executable model |
| NASA-STD-8739.4A, IPC/WHMA-A-620, MIL-STD-810H, NAVSEA SD-18, ECSS-Q-ST-30-11C, NASA EEE-INST-002, TOR-2012(8960)-4 | designations only | reported in [engineering-practice-survey.md](engineering-practice-survey.md); none read for this packet | reported designation, no compliance claimed |
| Derating fractions (0.50 current, 0.80 voltage, 0.10 cycles, 0.70 temperature) | as stated | this program's choice | engineering target |
| Every dimension marked "target" in the tables — wire gauge, connector ratings, crimp pull force, isolation resistance, strain-relief and service-loop distances, scope instrument, ambient band, expected currents, acceptance margins | as stated | none held | engineering target |

## Open items

These are the things this packet does not close. They are listed so that a
reader does not mistake a complete-looking document for a complete analysis.

1. No rail, contact current, or transient on this article has been measured.
   Every "held by design" entry above is analysis awaiting confirmation.
2. The SAMD21 BOD33 level encoding and the OpenRB-150's own brownout behaviour
   are not read here. Required before first capture.
3. Whether the OpenRB-150 permits separately sourced MCU and DYNAMIXEL port
   power — the rail split depends on it.
4. Wire gauge, connector part numbers, contact current ratings, mating-cycle
   ratings, and crimp pull-test forces are all targets pending vendor selection.
5. The second-source switch (ZF DB3) is not qualified: its minimum applicable
   load and its gold-contact order code are both unconfirmed.
6. S1 operating force does not close against the docked aircraft's static
   weight. Actuator style and force code stay open pending the A0 force
   measurement.
7. No vibration environment exists for the dock. The PSD screen against a
   P0-B-measured spectrum is a target; rule H10 is the interim compensation.
8. A formal WCCA over tolerance, temperature, and aging is not done and is not
   planned for P0. If this dock design is ever carried outdoors or scaled, that
   decision is revisited, not inherited.
