# P0 belly recovery dock

The P0 dock is a mechanically positive capture interface for recovering a micro-UAV beneath a slowly moving buoyant carrier.

It is mounted to the carrier's structural payload rail. **No recovery load is reacted through the gas envelope.**

## Why this geometry

The control system should not need millimeter-perfect coincidence in free flight. The hardware absorbs the last part of the alignment problem.

```text
carrier structural rail
        │
  compliant mount
        │
  ┌─────────────┐
  │  180 mm     │  capture mouth
   \           /
    \         /
     \       /     passive tapered funnel
      \     /
       [ ○ ]       spring collet / probe seat
       [ ─ ]       servo positive keeper
         │
         ●         drone-top capture probe
      ───────
       drone
```

## Carrier-side assembly

P0 targets:

- 180 mm funnel entrance diameter;
- compliant structural mounting;
- low-friction polymer funnel surface;
- spring-loaded terminal collet;
- independent servo keeper;
- physical capture-confirmation switch;
- total dock mass ≤180 g;
- no exposed sharp edge within the drone approach volume.

The servo is not the primary alignment mechanism. The funnel and collet should hold the probe before the keeper closes.

## Drone-side probe

Target mass: ≤8 g including fasteners.

The probe sits on the top side of the aircraft so the vehicle can remain upright underneath the carrier. It should have:

- a light mast tied into the drone frame rather than a cosmetic shell;
- a rounded terminal feature that cannot hook the funnel during an abort;
- a sacrificial/breakaway feature before loads can damage the flight controller PCB;
- enough vertical clearance to keep propellers outside the funnel.

Final dimensions follow physical fit testing; do not lock a production interface from CAD alone.

## Capture state machine

```text
IDLE
  -> APPROACH
  -> FUNNEL_CONTACT
  -> PROBE_SEATED
  -> KEEPER_CLOSED
  -> CAPTURE_CONFIRMED
  -> DRONE_DISARMED
```

Any timeout before `CAPTURE_CONFIRMED` commands an abort, not a forced latch.

Capture confirmation should be based on the physical interface. Position estimate alone is not proof of capture.

## Release state machine

```text
DOCKED
  -> RELEASE_ARMED
  -> KEEPER_OPEN
  -> PHYSICAL_SEPARATION
  -> FLIGHT_CONTROL_ACTIVE
```

The exact rotor-start/release timing is a test result. P0 does not encode an unvalidated free-fall or powered-release maneuver as doctrine.

## P0 exclusions

Do not add these until mechanical recovery passes:

- charging contacts;
- battery swap robotics;
- doors or an internal hangar;
- electromagnets as the primary retention mechanism;
- simultaneous multi-drone recovery;
- deployment through the lifting envelope.

## Bench test fixture

Before flight, construct a fixture that can translate the dock laterally at low speed while the aircraft approaches it. Instrument at minimum:

- relative position estimate;
- commanded velocity;
- capture switch state;
- servo command/state;
- aircraft arm/disarm state;
- timestamped success/abort reason.

The test rig is the place to break docking hardware, not the airship.
