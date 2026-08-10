# Kill path

Status: requirements and verification procedure; no hardware built
Applies to: every gate that flies an aircraft (P0-B, P0-C, P0-D)

The kill path disables carrier propulsion and inhibits release. It exists
for the case where the autonomy computer is confused, wedged, or lying, so
its one non-negotiable property is that **it does not depend on the thing it
protects against**.

Range-safety practice holds the termination path to a higher standard than
the vehicle it terminates: independent power, independent command path, and
demonstrated function before every session. P0 is an indoor tethered
prototype, not a launch vehicle, and the numbers below are scaled to that —
but the structure is deliberately the same, because the failure being
guarded against is identical.

## Requirements

| ID | Requirement | Why |
| --- | --- | --- |
| P0-KILL-001 | The kill path shall disable carrier propulsion without any action by the autonomy computer. | The autonomy computer is the suspect. |
| P0-KILL-002 | The kill path shall inhibit aircraft release independently of flight software state. | A release commanded during an emergency is the worst case. |
| P0-KILL-003 | The kill path shall be powered independently of the autonomy computer and its supply rail. | A brownout that takes the computer must not take the kill path. |
| P0-KILL-004 | The kill path shall be demonstrated end-to-end before every run set, with the result recorded. | An untested safety path is an assumption. |
| P0-KILL-005 | The kill path shall be demonstrated to work with the autonomy computer powered off. | This is the case it exists for, and it is the only way to prove independence rather than assert it. |
| P0-KILL-006 | Kill actuation shall be physically distinct from, and require a different action than, an abort command. | Confusing the two under stress is a known flight-test failure mode. |
| P0-KILL-007 | The kill path shall fail safe: loss of its own power, link, or command shall result in propulsion disabled and release inhibited. | A safety device that fails permissive is worse than none. |

These are engineering requirements for an indoor prototype, not
certification requirements. They are tracked in `aiur/requirements.py` and
gated by the `kill_path_*` criteria in `aiur/loop_graph.py`.

## Gate criteria

Every flying gate (P0-B, P0-C, P0-D) carries the same three criteria:

| Metric | Pass | Meaning |
| --- | ---: | --- |
| `kill_path_preflight_checks` | ≥1 | the end-to-end check was run this session |
| `kill_path_failures` | 0 | it never failed to act when commanded |
| `kill_path_verified_with_autonomy_off` | 1 | independence was demonstrated, not assumed |

Missing evidence fails the gate, as everywhere else in this program.

## Pre-session check

Run before the first attempt of every session, with the aircraft on the
ground and the carrier restrained:

1. Power the system normally. Confirm propulsion responds to a commanded
   input, so the check that follows is meaningful.
2. Actuate the kill path. Confirm propulsion is de-energised and release is
   inhibited. Record the time from actuation to observed effect.
3. Restore, then **power off the autonomy computer** and actuate the kill
   path again. Confirm the same result. This is P0-KILL-005 and it is the
   step most likely to be skipped when the session is running late; it is
   therefore a line on the [test card](test-cards.md) rather than a habit.
4. Disconnect the kill path's own command link (or its power, per the
   implementation) and confirm the system falls to propulsion-disabled and
   release-inhibited rather than continuing to fly. This is P0-KILL-007.
5. Confirm the kill actuator is physically distinct from the abort control
   and reachable by the Safety Observer without moving from their station.
6. Record all five results in the run log before attempt 1.

## Injected-fault exercise

Once per gate campaign, not merely once per session, verify the kill path
against a fault rather than a healthy system:

- actuate the kill path while the autonomy computer is mid-approach and
  actively commanding velocity — it must win;
- actuate it while the dock controller is in a fault state;
- actuate it during a simulated communications loss to the aircraft.

A kill path only ever demonstrated on a healthy system is evidence about
healthy systems.

## What is not covered

The aircraft's own arming state is separate: `S1 AND S2` capture truth and
the disarm logic live in the dock controller and the guidance supervisor.
The kill path does not disarm an aircraft in flight — an unpowered aircraft
falls. It removes carrier propulsion and prevents new releases. Bringing a
flying aircraft down safely is the guidance stack's abort behavior, which is
verified separately by the `safety_abort_failures` and `abort_path_failures`
criteria.
