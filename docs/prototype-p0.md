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

- 34 g takeoff weight with legs and 37 g with guards;
- ~10 min stock flight time;
- 40 g maximum recommended stock payload;
- contact pads for onboard charging;
- open-source software, swarm and ROS support;
- Bitcraze publishes both `(CN)` and `(VN)` SKU variants; P0 procurement requires the VN variant with COO/lot verified at order.

Sources:

- https://www.bitcraze.io/products/crazyflie-2-1-brushless/
- https://store.bitcraze.io/products/crazyflie-2-1-brushless
- https://github.com/bitcraze/hardware/releases

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
5. A physical seat switch (`S1`) confirms the probe reached the seat.
6. A servo moves a positive mechanical keeper underneath the probe head.
7. A second physical switch (`S2`) independently confirms keeper-closed position.
8. Capture is confirmed only when `S1 AND S2` is true; only then may the flight controller disarm the drone.

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

See [hardware/dock/README.md](../hardware/dock/README.md) and the [P0-A Rev-A bench article](../hardware/dock/p0a-bench.md).

## Mass budget

Use the vendor's 1.0 kg rated payload as the P0 payload ceiling. Do not substitute theoretical helium lift for rated usable payload.

Baseline carried mass target:

| Item | Mass |
| --- | ---: |
| 2 × guard-equipped Crazyflie Brushless | 74.0 g |
| 2 × Lighthouse decks | 5.4 g |
| 2 × drone-side capture probe allocations | ≤16.0 g |
| One active recovery dock | ≤180 g |
| Carrier localization + telemetry allocation | ≤50 g |
| Wiring/mounting reserve | ≤100 g |
| Total baseline allocation | ≤425.4 g |
| Rated-payload reserve | ≥574.6 g |

That reserve is deliberate. The prototype should not be engineered against its last gram.

The executable budget lives in [aiur/p0.py](../aiur/p0.py).

## Test gates

### P0-A — bench capture

Carrier dock is rigidly mounted to a bench.

Pass:

- at least 15 run-in cycles whose per-cycle insertion/release force levels off;
- 600 life-test cycles without structural failure (derived: ~300 expected cycles through P0-D × a 2.0 life factor);
- keeper close and open force margin ≥2.0 against worst-case resistance at minimum supply voltage;
- complete dock mass ≤180 g and complete probe mass ≤8 g;
- capture confirmation is unambiguous and requires independent seat + keeper feedback;
- positive keeper holds a 5 N axial screening load for 10 s;
- positive keeper holds a 1 N lateral screening load for 10 s in ±X and ±Y;
- at least 10 unloaded emergency-release trials with zero failures;
- at least 10 emergency-release trials **under the 5 N axial screening load** with zero failures;
- every required electrical fault mode inserted on hardware, each producing its pre-declared safe response.

No propellers installed.

The screening loads are prototype engineering gates, not certification/airworthiness loads. Full fixture geometry, procedure, and stop conditions are defined in [hardware/dock/p0a-bench.md](../hardware/dock/p0a-bench.md).

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
