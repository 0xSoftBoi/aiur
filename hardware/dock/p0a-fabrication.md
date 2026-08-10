# P0-A fabrication and bench electrical interface

Status: Rev-A build packet  
Applies to: CARRIER-P0 dock P0-A0 / P0-A1  
Flight condition: **no flight; propellers removed**

The fabrication pack closes only dimensions we can justify before hardware arrives. A0 is a manual fit article. A1 adds instrumented actuation and is the first article eligible to attempt the P0-A bench gate.

## Mechanical stack

The generated parts are in [`cad/generated/`](cad/generated/) and regenerate from [`cad/generate_rev_a.py`](cad/generate_rev_a.py), which builds **Rev-B** (`CURRENT`); the manifest names the revision it produced, so a printed part can always be traced back to its geometry. The keeper is a sliding fork: its 5.2 mm slot surrounds the Ø3 mm probe mast and its tines bear beneath the **Ø9 mm seat** — the head's lower cylinder, not the Ø12 mm belt, which is a funnel-guidance diameter the keeper never touches. Rigid guides and a closed end-stop react retention load. The servo translates the keeper but does not carry the 5 N screening load through its geartrain.

Closed geometry is mechanically stable. Do not count commanded servo position, motor torque, or motor current as retention evidence.

The compliant first-capture element remains a fit-derived part. A0 is where we measure the force needed to pass and retain the real probe head before freezing a spring/TPU/O-ring geometry.

## Actuator choice for A1

Rev-A uses a **ROBOTIS DYNAMIXEL XL330-M288-T** as the baseline actuator, mounted on a removable bracket.

Current official ROBOTIS data lists:

- 18 g; 20 × 34 × 26 mm;
- 3.7–6.0 V input, 5 V recommended;
- 0.52 N·m stall torque and approximately 1.5 A stall current at 5 V;
- TTL half-duplex Protocol 2.0 with position/current/velocity/temperature/voltage feedback;
- country of origin: Korea.

Sources: [ROBOTIS store](https://en.robotis.com/shop_en/item.php?it_id=902-0163-000) and [XL330 e-manual](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/).

Stall torque is not a design operating point. Measure keeper breakaway/running force in A0, size the linkage with margin from that measurement, and set motion limits before cycling. The actuator mount stays swappable so this servo cannot become a supply-chain architecture decision.

## Bench controller and power

Use an OpenRB-150 or equivalent bench controller for A1. The OpenRB provides dedicated TTL DYNAMIXEL ports. Its documentation limits USB input current to 500 mA, which is below the XL330's approximately 1.5 A 5 V stall current, so use a current-limited external 5 V bench supply through the documented power input for actuator tests.

Source: [ROBOTIS OpenRB-150 e-manual](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/).

Before the first powered keeper motion:

1. set the bench supply current limit;
2. verify common ground and actuator voltage with a meter;
3. run the keeper disconnected from the probe;
4. establish software position limits from the physical open/closed stops;
5. reconnect the probe only after the mechanism cannot over-travel into either stop.

The OpenRB and bench supply are ground equipment and do not count against the 180 g carried dock budget.

## S1 / S2 physical truth

Use two physically separate SPDT snap-action switches. S1 is actuated by a seated probe. S2 is actuated by the keeper itself at its closed stop. S2 is not mounted where the servo horn can claim “closed” while the keeper is obstructed.

For bench wiring, use both contacts of each SPDT switch so wiring faults can be detected:

| Mechanical state | NC input | NO input | Decode |
| --- | --- | --- | --- |
| released | low | high | valid released |
| actuated | high | low | valid actuated |
| any other pair | — | — | wiring/switch fault |

This assumes switch COM is tied to controller ground and each NC/NO input has an independent pull-up. Validate the electrical truth table with a meter before connecting it to the dock state machine.

`capture_confirmed = S1_valid_and_actuated AND S2_valid_and_actuated`.

The actuator's encoder is useful telemetry, but it does not enter that Boolean.

## Supply-chain rule

The carried actuator baseline is explicitly Korea-origin. The switches, guides, fasteners, probe mast, and print feedstock use commodity interfaces and should have at least two qualified alternates; record manufacturer part number and COO/lot on the build sheet rather than trusting brand headquarters.

For the Crazyflie itself, Bitcraze's hardware releases now identify both `(CN)` and `(VN)` SKU variants. P0 procurement therefore requires the **VN variant plus lot/COO verification at order**. “Bitcraze” alone is not an origin assertion.

Source: [Bitcraze hardware releases](https://github.com/bitcraze/hardware/releases).

## A0 exit / A1 entry

Do not power an actuator until A0 produces:

- actual funnel, keeper, and coupon-head masses;
- throat/head and slot/mast fit measurements;
- manual keeper travel and force measurements;
- photographs of the closed load path and keeper guides;
- a disposition for any hand-work performed on load-bearing geometry.

A1 then freezes the actuator linkage, passive first-capture insert, switch brackets, and wiring revision. Only the complete A1 article can run the run-in/600-cycle/5 N/1 N P0-A procedure.
