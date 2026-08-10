# Bench fault-insertion unit

Status: build definition, not built hardware
Applies to: P0-A (bench) and P0-B (suspended rig)

The digital twin injects stuck switches, servo jams, and power faults, and
those injections produced the program's most useful findings — the latched
capture-enable, the seat-plausibility gate, the double-fault residual. None
of that is evidence about hardware until the same faults are inserted into
the real wiring and the real mechanism answers.

This is the physical counterpart to `aiur/sim/faults.py`. It exists so a
twin finding and a bench trial can be compared directly, mode by mode.

## Principle

A fault-insertion unit sits **between** the mechanism and the controller and
can electrically break or force each signal on command, without anyone
touching the article mid-test. Unplugging a connector by hand is not fault
insertion: it is slow, unrepeatable, changes contact state, and cannot be
done while the mechanism is loaded.

Three rules:

1. The unit inserts faults; it must never be able to *cause* motion. Servo
   drive is interrupted, never commanded, by this board.
2. Every fault is commanded, logged, and timestamped against the same clock
   as the dock telemetry, so cause and response are unambiguous.
3. The required response is written down **before** the trial. A fault that
   produces "something reasonable" that is not the required response is a
   failure, not a pass.

## Signals under fault control

| Line | From | To | Insertable faults |
| --- | --- | --- | --- |
| `S1` seat switch (NC + NO) | switch | controller input | open, short to GND, short to rail |
| `S2` keeper-closed switch (NC + NO) | switch | controller input | open, short to GND, short to rail |
| Servo power | supply | XL330 | interrupt (power loss) |
| Servo signal | controller | XL330 | open |
| Controller supply | supply | OpenRB-150 | brownout to a set voltage, momentary interrupt |

The dual-contact decode already specified in
[p0a-fabrication.md](p0a-fabrication.md) is what makes open-vs-short
distinguishable at the controller; this board is what lets it be tested.

## Implementation

Signal-level relays or analog switches, one per fault path, driven from a
separate microcontroller that also logs the command stream. Engineering
targets for the build:

- relay/switch contacts rated well above the logic-level currents they carry
  and specified for low-level (dry-circuit) switching — the same
  minimum-current concern that applies to `S1`/`S2` themselves;
- the insertion board is powered separately from the dock controller, so a
  controller brownout trial does not also disable the fault injector;
- a hardware master-enable that opens every relay to the pass-through state,
  so a confused injector cannot hold a fault in;
- fault command and dock telemetry share a monotonic time base.

Exact part numbers follow from the electrical evidence packet
([electrical-evidence.md](../../docs/electrical-evidence.md)); nothing here should be
ordered before the switch and pull-up choices are frozen.

## Required fault modes

These modes are the P0-A quota and are enumerated once, in
`aiur/loop_graph.py` (`REQUIRED_FAULT_MODES`); the gate criterion counts that
list rather than a literal, and the reducer refuses a gate verdict if any mode
was never exercised. Both were briefly out of step after a mode was added,
which is why the number now lives in one place.

| Mode | Physical meaning | Required response |
| --- | --- | --- |
| `S1_OPEN` | seat switch never reports a seated probe | no capture confirmation; approach aborts or the operator sees an unambiguous no-seat state; the aircraft is never disarmed |
| `S1_SHORT` | seat switch reports seated permanently | capture is refused unless the supervisor's own estimate also places the probe at the seat; the aircraft is never disarmed on the switch alone |
| `S2_OPEN` | keeper-closed switch never reports closed | no capture confirmation; controller times out to a fault state; keeper is commanded open |
| `S2_SHORT` | keeper-closed switch reports closed permanently | dual-contact decode flags the wiring fault; capture is not confirmed on `S2` alone |
| `S1_S2_BOTH_OPEN` | both channels lost (shared harness/connector) | controller reaches a fault state and stays there; no capture claim; emergency release still works |
| `SERVO_POWER_LOSS` | keeper actuator loses power mid-motion | mechanism does not claim capture; an already-captured probe stays mechanically retained (the keeper is not the load path); state is reported, not guessed |
| `SERVO_STALL` | keeper blocked by an obstruction | lock times out to a fault state within the configured timeout; no capture confirmation; no repeated stall drive |
| `CONTROLLER_RESET_DURING_LOCK` | controller browns out or resets while locking | on restart the controller does not assume a capture it cannot observe; it re-reads `S1`/`S2` and reports the true state; a latched capture-enable does not survive a reset as a capture claim |

| `CONTROLLER_RESET_WHILE_CAPTURED` | controller browns out or resets while an aircraft hangs from the closed keeper | the restarted controller does not command the keeper open; it holds, reports the ambiguous state, and waits for an operator decision. A dummy mass stands in for the aircraft; nothing falls |

`CONTROLLER_RESET_DURING_LOCK` is on this list because of a twin finding:
the guidance stack must latch the capture enable once seating is confirmed,
so the reset that erases that latch is exactly the case worth inserting.

## Procedure per trial

1. Bring the article to the state the fault targets (probe seated, keeper
   mid-travel, captured, or free — recorded per trial).
2. Write the required response in the fault log row before inserting.
3. Insert the fault; hold it for the trial duration.
4. Record the observed response verbatim, and whether an unsafe state was
   entered (uncommanded release, a capture claim with no probe, a drop, or a
   lost emergency release).
5. Clear the fault and confirm the mechanism returns to a known state before
   the next trial.

Log rows go in [`p0a-fault-template.csv`](p0a-fault-template.csv).

## Comparison to the twin

After the campaign, compare each hardware trial against the twin's
corresponding fault kind. Agreement raises the twin's validation standing
for that submodel; disagreement is a `FAIL_MODEL` disposition under the
engineering loop, and the model is corrected before the next SIL result is
trusted. See [digital-twin.md](../../docs/digital-twin.md).
