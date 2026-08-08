# CARRIER-P0 execution gate

CARRIER-P0 exists to answer one question with physical evidence:

> Can a buoyant carrier repeatedly recover a small autonomous aircraft onto a moving belly dock?

Everything below is structured around producing a defensible yes/no answer rather than demonstrating a one-off capture.

## P0-A — bench capture article

Before integrating the airship, prove the dock mechanics on a controlled moving-target rig.

### Required hardware state

- mechanically positive capture feature installed;
- actuator/controller running the repository fail-safe state machine;
- instrumented target or micro-UAV surrogate with repeatable relative approach;
- camera or external tracking sufficient to reconstruct approach error and capture timing;
- hard emergency stop and protected test volume.

### Minimum test matrix

Run at least 30 attempts across the matrix below, with raw logs retained for every attempt.

| variable | levels |
|---|---|
| lateral error | centered, moderate offset, edge of intended capture envelope |
| vertical error | centered, moderate offset |
| closing speed | low, nominal, upper intended P0 speed |
| dock motion | static, representative carrier translation |
| outcome | capture, reject/miss, unsafe contact |

Do not tune the mechanism between individual trials without starting a new configuration ID.

### Acceptance criteria

The bench article passes P0-A only when:

- >= 90% successful capture inside the declared nominal capture envelope;
- 0 unsafe contacts in the acceptance set;
- every failed capture transitions to a safe state without entanglement or uncontrolled actuation;
- capture outcome, approach error, closing speed, controller state, and configuration ID are logged for every attempt;
- the same hardware/configuration completes 10 consecutive nominal captures.

If those thresholds are not met, the result is still useful: publish the failure distribution and revise the geometry/controller against the measured miss modes.

## P0-B — integrated carrier recovery

Only after P0-A passes, mount the dock to the buoyant carrier.

### Configuration

- indoor ~4.5 m helium platform;
- one dock only;
- one micro-UAV initially;
- externally referenced positioning;
- prop guards / tethering appropriate to the test volume;
- no airborne charging hardware.

### Required measurements

For every attempt record:

- carrier pose and velocity;
- vehicle pose and velocity;
- relative position at final approach;
- relative closing velocity;
- controller mode transitions;
- contact time;
- latch/capture confirmation;
- turnaround time until the aircraft is mechanically secure and the system is ready for another cycle.

Use synchronized timestamps. Video is supporting evidence, not the primary measurement source.

### Pass gate

CARRIER-P0 passes only when one unchanged integrated configuration demonstrates:

1. **20 consecutive autonomous recovery attempts** without manual intervention during final approach/capture;
2. >= 90% capture success over at least 50 total attempts inside the declared operating envelope;
3. 0 unsafe contacts;
4. repeatability on at least two separate test sessions;
5. a committed machine-readable dataset and script that regenerate the headline plots/table.

## Evidence package

The repository should ultimately contain:

```text
results/p0/
  manifest.json
  attempts.csv
  raw/
  video-index.csv
  plots/
  report.md
```

`manifest.json` should pin the git SHA, hardware revision, dock CAD revision, firmware/controller configuration, tracking system, and calibration date.

`attempts.csv` should contain one row per attempt. Do not discard misses.

## Headline plots

The P0 report should be reproducible from saved data and include:

- capture success vs. lateral/vertical approach error;
- capture success vs. closing speed;
- scatter of final relative position colored by outcome;
- turnaround-time distribution;
- failure-mode counts;
- session-to-session comparison.

## Kill criteria

Stop scaling the carrier if any of the following remains true after two meaningful dock revisions:

- no stable capture envelope emerges;
- safe misses cannot be guaranteed;
- required approach precision is tighter than the chosen positioning/control stack can repeatedly deliver;
- carrier motion makes the nominal capture rate materially worse than the bench result with no credible control fix;
- docking mass/power grows enough to invalidate the P0 lift budget.

The purpose of P0 is to kill a bad architecture cheaply if the recovery mechanism does not work.

## What comes after a pass

A successful P0 does **not** validate a 40 m vehicle, hydrogen lift, BVLOS operation, swarm-scale traffic, airborne charging, or DGX-class compute. It validates only the recovery primitive strongly enough to justify the next prototype.
