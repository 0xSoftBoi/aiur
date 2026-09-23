# S0-A bench and cold-chamber test card

Status: printable run card, not measured hardware  
Gate: S0-A — payload bench and cold chamber ([`aiur/loop_graph.py`](../../aiur/loop_graph.py) `STRATO_GATES`)  
Article: Rev-A flight package ([`README.md`](README.md), [`bom.csv`](bom.csv))  
Flight condition: **no flight; no balloon; arming pin in except where a step says otherwise**

Print it, fill it by hand, file it with the logs. One card per session;
the soak, the termination trials, the link trials, and the drop tests can
span several sessions under one `run_id` as long as nothing about the
package changes between them. If the package is opened, re-wired, or a
part is swapped, the identity is new and the evidence restarts.

The success criteria below are transcribed from `GATES["S0-A"]` at the git
SHA in the identity block. If the gate changes, re-transcribe before the
session — the card, not memory, is what the crew works to.

## 1. Run identity

| Field | Value |
| --- | --- |
| `run_id` | |
| Gate | S0-A |
| Session number | |
| Git commit SHA | |
| Package revision / serial | Rev-A, serial ________ |
| Flight computer image hash | |
| Termination timer setting | ________ s (must equal `FlightLimits.max_mission_s`) |
| Cells fitted (lot, count, main / termination) | |
| Chamber | make / model ________, calibrated ________ |
| Date / location | |

Results are logged under this `run_id` in
[`s0-chamber-log-template.csv`](s0-chamber-log-template.csv),
[`s0-trials-template.csv`](s0-trials-template.csv),
[`s0-drop-template.csv`](s0-drop-template.csv), and the measured package
mass in [`s0-bench-manifest-template.json`](s0-bench-manifest-template.json).
Reduce with:

```
python -m aiur.s0_evidence chamber --soak <chamber.csv> --trials <trials.csv> --drops <drops.csv> --manifest <bench.json>
```

## 2. Crew

| Role | Name | Notes |
| --- | --- | --- |
| Test director (holds stop authority) | | |
| Package operator | | |
| Chamber operator | | |
| Recorder | | keeps the paper log in step with the files |

Minimum two people. Nobody handles a live burn-wire alone.

## 3. Pre-session checks

- [ ] Package weighed complete and flight-ready, on a scale zeroed with the
      cradle: `payload_package_mass_kg` = ________ (limit 1.814; allocation 1.0)
- [ ] Arming pin in; cutdown MOSFET gate measured low
- [ ] Main cells and termination cells open-circuit voltage recorded
- [ ] GNSS receiver reports the airborne dynamic model (read back, not assumed)
- [ ] Chamber can reach ≤ −60 °C and hold; probe on the electronics, not the wall
- [ ] Stop condition list below read aloud

## 4. Cold soak (criteria `cold_soak_hours ≥ 3`, `cold_soak_min_temp_c ≤ −55`, `cold_soak_functional_dropouts = 0`, `imaging_chain_captures ≥ 100`)

1. Package powered and imaging at the 10 s cadence with a GNSS repeater or a
   window view; telemetry to the bench receiver at 30 s.
2. Chamber to −60 °C over ≤ 60 min, then hold. Log every minute: internal
   temperature, chamber temperature, imaging ok, tracking ok, termination
   circuit ok (timer heartbeat visible), frame stored.
3. Hold until the internal probe has been at or below −55 °C for at least
   3 h *and* the total soak is at least the predicted flight duration.
4. Every 30 min: a thumbnail must arrive at the bench receiver from a frame
   taken inside the last minute. A missing thumbnail is a dropout.
5. At the end, warm at the chamber's rate and confirm the stored frame index
   matches the count logged.

A dropout is any minute in which imaging, tracking, or the termination
heartbeat is not seen. Zero is the criterion. One is a defect to fix, then
a new identity and a new soak.

## 5. Termination trials (criteria `termination_command_trials ≥ 10`, `termination_failures = 0`, `termination_verified_with_payload_computer_off = 1`)

Burn-wire on a sacrificial line loop under 5 N tension, package on the bench,
crew clear of the loop.

| Trial | Path | Computer | Pin | Expected | Fired (y/n) | Time to separation (s) |
| --- | --- | --- | --- | --- | --- | --- |
| T01–T10 | ground command via the primary radio | on | pulled | fires, line separates | | |
| T-OFF | hardware timer (set to 60 s for the trial) | **unpowered** | pulled | fires at 60 s | | |
| T-INH | ground command | on | **in** | does **not** fire | | |

`T-INH` is recorded but is not a gate metric: it confirms the hardware
inhibit. If it fires with the pin in, stop the session.

After the trials, the timer is re-set to the flight value and the setting
is read back and recorded in the identity block.

## 6. Link trials (criteria `telemetry_link_trials ≥ 10`, `telemetry_link_failures = 0`)

Ten transmissions from the package to the ground station at ≥ 500 m line
of sight, ground-station antenna as flown. A trial passes when the packet
decodes with the correct sequence number and position. Record RSSI per
trial; it is the only link-margin evidence the program has until S0-B.

## 7. Drop tests (criterion `parachute_descent_rate_m_s ≤ 5.0`)

Flight package on the flight canopy and flight rigging, dropped from a
height that allows ≥ 3 s of steady descent, filmed against a measured
reference. Descent rate from the last steady second before touchdown, at
least two drops. Record the worst.

Wind at the drop site ≤ 2 m/s; otherwise the rate is not a measurement.

## 8. Stop conditions

Stop the session and file a disposition on any of:

- cutdown fires with the arming pin in;
- cutdown fails to fire on any commanded trial;
- any dropout during the soak;
- smoke, swelling, or a cell below 1.0 V under load;
- the package mass over 1.814 kg;
- a configuration change made without a new identity.

## 9. Disposition

`PASS` / `FAIL_REQUIREMENT` / `FAIL_MODEL` / `FAIL_SOFTWARE` /
`FAIL_HARDWARE` / `INVALID_TEST` / `ABORTED_SAFETY` (one only), signed by
the test director, with the reducer's JSON verdict attached.
