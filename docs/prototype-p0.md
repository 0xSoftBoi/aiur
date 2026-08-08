# CARRIER-P0 prototype specification

Status: pre-alpha engineering definition  
Source review: 2026-08-08

## Objective

CARRIER-P0 is a flight-test article, not a scale model of the eventual carrier.

It exists to test the system's highest-risk interaction:

**release a small aircraft from a buoyant carrier, fly a sortie, then autonomously recover that aircraft onto a moving belly dock.**

P0 succeeds before the program spends engineering time on hydrogen, a large envelope, eight heavy aircraft, airborne charging, or data-center-class compute.

## Reference flight article

The baseline carrier is a 4.5 m indoor helium airship.

A current commercial reference platform is RC-Zeppelin B100-I-450-VT:

| Property | Reference value |
| --- | ---: |
| Envelope length | 4.5 m |
| Helium volume | ~5.5 m³ |
| Rated payload | up to 1.0 kg |
| Envelope | 100 μm polyurethane |
| Advertised endurance | 45–60 min |
| 2026 RTF price | $2,820 |

Source: https://www.rc-zeppelin.com/4.5m-indoor-RC-Blimp.html  
Pricing: https://www.rc-zeppelin.com/price-list.html

Vendor figures are design inputs, not Aiur test results. They must be verified on the delivered vehicle.

## Aircraft

P0 uses one Crazyflie 2.1 Brushless first, then two.

Published reference figures:

- 32 g stock vehicle mass;
- ~10 min stock flight time;
- 40 g maximum recommended stock payload;
- contact pads for onboard charging;
- open-source software, swarm and ROS support;
- listed country of origin: Vietnam.

Source: https://store.bitcraze.io/products/crazyflie-2-1-brushless

P0 does not use charging during first recovery testing. The contact interface is a P0.1 concern.

## Positioning

Early indoor tests use Bitcraze Lighthouse positioning because it decouples docking-control work from an unsolved perception stack.

The Lighthouse deck is 2.7 g and calculates pose onboard. V2 base stations provide the external optical reference.

Sources:

- https://www.bitcraze.io/products/lighthouse-positioning-deck/
- https://store.bitcraze.io/products/lighthouse-v2-base-station

This is test instrumentation, not the intended production navigation architecture.

## Docking architecture

The first dock is mounted to the carrier structural rail, never to the gas envelope.

The interface is intentionally passive during alignment:

1. A wide polymer capture funnel accepts lateral position error.
2. A lightweight probe on top of the drone enters the funnel.
3. Tapered geometry converts lateral error into probe centering.
4. A spring collet/keeper provides first capture.
5. A servo moves a positive mechanical lock.
6. A physical switch independently confirms capture.
7. Only after capture confirmation may the flight controller disarm the drone.

No electromagnet is required to keep the aircraft attached.

Initial engineering targets:

| Requirement | Target |
| --- | ---: |
| Funnel entrance diameter | 180 mm |
| Maximum commanded closing speed | 0.20 m/s |
| Initial terminal-approach speed | ≤0.10 m/s |
| Dock assembly mass | ≤180 g |
| Drone-side docking hardware | ≤8 g |
| Live recovery attempts for first gate | 10 |
| Passing recoveries | ≥9/10 |
| Envelope/propulsion strikes | 0 |

These are **targets**, not measured performance.

See [hardware/dock/README.md](../hardware/dock/README.md).

## Mass budget

Use the vendor's 1.0 kg rated payload as the P0 payload ceiling. Do not substitute theoretical helium lift for rated usable payload.

Baseline carried mass target:

| Item | Mass |
| --- | ---: |
| 2 × stock Crazyflie Brushless | 64.0 g |
| 2 × Lighthouse decks | 5.4 g |
| One active recovery dock | ≤180 g |
| Carrier localization + telemetry allocation | ≤50 g |
| Wiring/mounting reserve | ≤100 g |
| Total baseline allocation | ≤399.4 g |
| Rated-payload reserve | ≥600.6 g |

That reserve is deliberate. The prototype should not be engineered against its last gram.

The executable budget lives in [aiur/p0.py](../aiur/p0.py).

## Test gates

### P0-A — bench capture

Carrier dock is rigidly mounted to a bench.

Pass:

- 50 manual insertion/removal cycles without structural failure;
- capture confirmation is unambiguous;
- positive lock cannot release from simple vibration or probe side-load;
- manual emergency release works every time.

No propellers installed.

### P0-B — suspended moving dock

Suspend the dock on a low-speed moving rig before putting it on the airship.

Pass:

- autonomous terminal approach using Lighthouse;
- at least 9 successful captures in 10 consecutive attempts;
- closing speed remains within configured limit;
- no propeller/funnel contact.

### P0-C — tethered carrier recovery

Carrier is helium-filled, piloted conservatively, physically tethered, and flown in a controlled indoor volume.

Pass:

- autonomous launch/recovery cycle completes;
- ≥9/10 consecutive recovery attempts succeed;
- zero envelope strikes;
- pilot can abort release or recovery at any point;
- vehicle remains controllable with the complete P0 payload.

### P0-D — two-aircraft sequencing

Only after P0-C passes:

- release two aircraft sequentially;
- maintain positive separation;
- recover one at a time;
- no simultaneous approach to the active dock.

This is the earliest point where "fleet" behavior is demonstrated.

## P0.5 — put compute aloft

After recovery works, migrate coordination/perception onboard.

Candidate compute families include NVIDIA Jetson Orin Nano (7–25 W) and Orin NX (10–40 W). Carrier-board, cooling, mass, and power measurements determine the exact module.

NVIDIA reference: https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/

A lightweight flight-control candidate is the active 3DR Control Zero OEM H7; 3DR lists it at 3.5 g with eight PWM outputs.

Reference: https://docs.3dr.com/autopilots/

ArduPilot has a dedicated Blimp vehicle stack, but its current getting-started material is centered on fin-driven blimps. Vector-thrust integration must therefore be treated as engineering work, not assumed capability.

Reference: https://ardupilot.org/blimp/

## Safety envelope

P0 uses helium only.

Initial tests are indoors, tethered, prop-guarded, and conducted with no person beneath the flight volume. A physical kill path must disable carrier propulsion and inhibit release. Battery handling follows the cell/vendor requirements.

Hydrogen is explicitly outside P0. It adds a hazard without helping answer the release/recovery question.

## Exit criterion

CARRIER-P0 is complete when repeated autonomous airborne recovery is boring.

Only then expand the program to multiple docks, airborne charging, onboard perception, outdoor station-keeping, larger aircraft, or alternate lift gas.
