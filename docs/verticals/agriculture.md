# Agriculture vertical

Status: exploratory concept study — no funded milestone. CARRIER-P0 remains the only funded article.

This document extends the CARRIER-P0 architecture on paper only. Nothing here is a claimed capability. Every number below is an engineering target or an open question routed to the digital twin.

## Mission profiles

### 1. Persistent crop scouting (high-value crops)

- Operator: grower or agronomy service over vineyards, orchards, berries, seed production; blocks of 10–100 ha.
- Cadence: daily during disease-pressure windows; sub-daily during outbreak response.
- Carrier: loiters over the block for hours, carries the dock, recharge power, comms relay, and coarse survey imaging.
- Micro-UAV sorties: close-inspection flights at 0.3–1.0 m standoff — leaf-level imaging, pest-trap photo checks, canopy probes — then re-dock and recharge. Payload budget is grams; the sortie product is imagery and detections, nothing dispensed.

### 2. Livestock and infrastructure patrol

- Operator: rancher; water troughs, fence lines, gates, tanks over 100–5,000 ha.
- Cadence: 1–2 patrol circuits/day.
- Carrier: slow transit along a fixed patrol route; long-range comms relay back to the homestead.
- Micro-UAV sorties: short verification hops when the carrier's coarse imagery flags an anomaly (trough level, downed fence section, stationary animal).

### 3. Targeted intervention support

- Operator: grower running a ground or aerial spot-spray rig.
- Carrier + micro-UAVs produce a georeferenced target list (weed patches, infestation loci) at leaf-level resolution; the spray rig executes.
- Micro-UAVs never spray. A 30–40 g aircraft with a grams-scale payload budget cannot carry useful liquid; claiming otherwise would violate the repo design rule. Dispensing also triggers a different regulatory regime (see below).

## Why persistent airborne infrastructure

Honest comparison. The alternatives win in most current agricultural use today.

| Alternative | Where it wins | Where the carrier concept could win |
| --- | --- | --- |
| Manual quadcopter (~$2k) + operator | Capex, simplicity, no helium logistics, works today | Cadence without labor; an operator will not fly 20 sorties/day, every day |
| Fixed ground dock (DJI Dock class) | Fixed-site automated cadence, weatherproof, proven | Dock moves with the work; no per-block ground installation, power, or vehicle access in wet fields |
| Fixed-wing mapping | ha/hour, cm-class GSD orthomosaics | Cannot hover at a leaf; sub-mm GSD close inspection requires rotorcraft at short standoff |
| Satellite / high-altitude imagery | $/ha at coarse GSD, zero ops burden | 3–10 m class GSD detects stress, not the pest; revisit and cloud gating |
| Human ground scouting | Ground truth, tissue sampling, judgment | Coverage per labor-hour; humans sample sparsely |

The carrier's only defensible niche: leaf-level inspection at high cadence needs short-standoff rotorcraft flight; micro-UAV endurance is ~10 min; therefore the recharge/relaunch infrastructure must be near the crop. The carrier is that infrastructure, airborne and mobile. If a $2k quadcopter flown 20 min/day answers the grower's question, this vertical loses. That economic threshold is a kill criterion, not a footnote.

## Concept of operations

Canonical mission: fungal-pressure scouting over a 40 ha vineyard block. All phases assume the outdoor-scaled carrier, not the 4.5 m P0 article.

1. Pre-flight: carrier on mooring mast at farmstead; helium top-up check, mass audit, config identity recorded per the promotion contract.
2. Launch and transit to the block; cruise 2–4 km at low altitude.
3. On-station loiter over the block; coarse survey imaging flags candidate vines.
4. Dock cycle — release: keeper opens, micro-UAV arms, drops from the belly dock, clears the carrier keep-out volume.
5. Sortie: 6–8 min of leaf-level imaging at flagged locations within ~500 m of the carrier.
6. Return: micro-UAV closes to the carrier on coarse navigation, then hands over to GNSS-independent terminal relative navigation for the final meters.
7. Dock cycle — capture: funnel entry, probe seat (`S1`), keeper closed (`S2`); disarm only on `S1 AND S2`, identical to P0 semantics.
8. Dock cycle — recharge: contact-pad charging while docked; next sortie when charge and queue allow.
9. Repeat phases 4–8 for the on-station window; carrier relays detections to the farm network continuously.
10. Return to mast, moor, download evidence packet, disposition per the engineering loop.

One carrier + 2 aircraft + 1 dock yields a sortie roughly every recharge interval. Fleet-scale cadence (P0-D and beyond) multiplies aircraft, not docks, until a second dock is justified by queueing data.

## Requirement deltas vs P0

All rows Status = engineering target. None are measured. Wind and noise targets are placeholders whose real values come out of the twin campaigns below.

| ID | Observable | Target | Driver |
| --- | --- | --- | --- |
| AGR-001 | Carrier station-keeping error in sustained wind | hold ≤10 m radius in W m/s sustained; W to be established, placeholder ≥8 m/s | 4.5 m P0 envelope is unflyable outdoors above light breeze; outdoor carrier is a scaling milestone |
| AGR-002 | Capture success rate vs wind level at the dock | ≥90% at the declared operating wind limit; collapse wind level to be found | outdoor-gust-sweep exists to find where capture collapses |
| AGR-003 | Terminal relative position error, GNSS-independent | ≤30 mm 1σ lateral at funnel entry (180 mm funnel) | shared derived requirement: no Lighthouse outdoors; vision/UWB/IR beacon trade open |
| AGR-004 | Carrier on-station endurance | ≥6 h loiter incl. dock + recharge power | daily scouting window; P0 reference endurance is 45–60 min |
| AGR-005 | Recover→recharge→relaunch turnaround | ≤45 min per aircraft | sortie cadence; sets aircraft count per carrier |
| AGR-006 | Docked contact-charging function | charge to flight-ready through dock contact pads, zero manual handling | P0 defers charging; agriculture cadence is impossible without it |
| AGR-007 | Micro-UAV imaging product | ≤5 g sensor; sub-mm GSD at ≤1.0 m standoff | leaf-level detection is the vertical's only differentiated product |
| AGR-008 | Sortie radius from carrier | ≥500 m with link margin and return reserve | block coverage per loiter position |
| AGR-009 | Dock mechanism function after field exposure | ≥50 capture cycles without cleaning after dust/pollen soak trial | collet, keeper, and switches are precision parts in a dirty environment |
| AGR-010 | Envelope helium loss and weather exposure | top-up interval ≥14 days; UV/temperature cycling survival defined by envelope vendor spec | farm logistics; helium cost and handling labor |
| AGR-011 | Operating temperature envelope | −5 to +45 °C for dock, aircraft, charging | field seasons; P0 is indoor-ambient only |

## What the digital twin must simulate

The twin (aiur/sim, deterministic dependency-free Python, Monte Carlo campaign runner) is the cheapest place to kill this vertical. Mapping:

- AGR-001, AGR-002 → `outdoor-gust-sweep`: inject gust and carrier-motion disturbance into the dock frame, sweep wind level, output capture rate vs wind. The deliverable is the collapse curve — the wind level where capture rate falls off — as an open question the twin answers, not a solved one. This number decides whether an agricultural operating window exists at all.
- AGR-003 → `degraded-sensor-sweep`: capture success vs positioning noise from Lighthouse-grade mm noise up to GNSS/RTK-grade cm noise. Known result to build on: the 180 mm funnel is sized for mm-grade relative positioning. The sweep quantifies how much a terminal beacon/vision system must beat RTK before outdoor capture is credible, and sets the AGR-003 accuracy number.
- AGR-004, AGR-005, AGR-008 → energy and queueing model: sortie schedule, charge model, carrier power draw, sorties/day per aircraft count. Extends the two-aircraft sequencing logic exercised in `sil-p0d`.
- AGR-006 → charge-state and contact-fault injection on the docked state machine; no new gate, an overlay on `sil-p0b` scenarios.
- AGR-009, AGR-011 → parameter degradation runs (friction growth, switch bounce, servo torque loss) against the existing dock controller fault set.
- Gate regression: `sil-p0b`, `sil-p0c`, `sil-p0d` remain the SIL gates mirroring P0-B/C/D. Agriculture scenarios are parameter overlays on those scenarios, never replacements. A change that passes an agriculture sweep but regresses a SIL gate does not advance.

## Safety and regulatory considerations

Considerations to verify with counsel/FAA engagement, not legal conclusions.

- 14 CFR Part 107: small-UAS baseline for the micro-UAVs and possibly the carrier; the 55 lb limit is a hard question for any outdoor-scaled carrier and must be checked against actual gross weight including helium structure.
- BVLOS: persistent scouting beyond the operator's line of sight requires a waiver today; the FAA's proposed BVLOS rulemaking (widely referenced as "Part 108") is not final and must not be assumed.
- 14 CFR Part 89: Remote ID applies to the aircraft; carrier + docked micro-UAV broadcast behavior needs a defined answer.
- 14 CFR Part 137: agricultural aircraft operations governs dispensing. This concept dispenses nothing, which is a deliberate scope choice; verify that scouting-only operations stay outside Part 137.
- 14 CFR Part 101: moored-balloon rules may apply to the carrier while on the mast/tether; verify.
- Non-regulatory: livestock disturbance (noise/shadow), chemical-exposure windows for ground crew coordination, helium cylinder handling on farm sites, and the P0 physical kill path retained unchanged — carrier kill and release inhibit must work with the autonomy computer dead.

## Open engineering risks

Ranked. Killers first.

1. Outdoor wind tolerance. A 4.5 m envelope is unflyable outdoors in more than light breeze; drag scales with frontal area while control authority is thrust-limited. The outdoor carrier is a scaling milestone with its own envelope, propulsion, and gate ladder — none of it funded. If the `outdoor-gust-sweep` collapse wind level lands below typical daytime agricultural winds, the vertical dies here.
2. Economics vs manual quadcopter. A grower flying a $2k quadcopter 20 min/day covers most current scouting needs at near-zero marginal cost. The carrier concept only pays when required cadence × labor cost exceeds carrier capex + helium + maintenance. No cost model exists yet; building one is prerequisite to any funding ask.
3. GNSS-independent terminal navigation. mm-grade relative positioning outdoors, on a moving carrier, in gusts, against sun glare and dust, with a grams-scale sensor budget on the aircraft. Trade (vision/UWB/IR beacon) is open; `degraded-sensor-sweep` bounds the requirement but does not produce the sensor.
4. Capture dynamics in turbulence. P0 closes at ≤0.20 m/s against a quasi-static dock. A gust-excited dock is a moving target with its own spectrum; relative-motion capture may need funnel, probe, or control-law redesign — which re-enters the loop at P0-A, not at flight.
5. Contact charging in the field. Unproven even indoors (deferred from P0); outdoors adds oxidation, dust on pads, and thermal limits on charge rate.
6. Mechanism contamination. Spring collet, keeper, and switches S1/S2 are precision parts operating in dust, pollen, and spray drift. AGR-009 is a bench trial, and it may fail.
7. Helium logistics and envelope life. Loss rate, UV degradation, hail, and mooring in weather define an operating cost floor that no simulation removes.
8. Regulatory timeline. Persistent BVLOS over farmland is waiver-by-waiver today; the business case assumes a rule that does not yet exist.

## Commonality with core

Identical to P0 by design; agriculture changes the environment, not the truth model.

- Dock mechanism: funnel + probe + spring collet + servo keeper, unchanged.
- Capture truth: `S1 AND S2` dual independent switches; disarm only on confirmed capture.
- Fail-safe semantics: safety supervisor over guidance, abort/hold on invalid estimate, physical kill and release-inhibit paths outside software.
- Evidence-gated loop: same promotion contract, disposition taxonomy, and stop rules; agriculture work re-enters at the lowest stage that exposes the new failure mode.
- Twin scenarios: `sil-p0b`/`sil-p0c`/`sil-p0d` remain the regression gates; vertical studies are parameter overlays on the same deterministic scenario set.
