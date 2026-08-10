# Wildfire response support vertical

Status: exploratory concept study — no funded milestone. CARRIER-P0 remains the only funded article.

Scope is strictly support/ISR: thermal hotspot mapping adjacent to a fire, overnight perimeter watch, crew-position and escape-route monitoring, and comms relay. The carrier never enters the convection column. No fire-suppression payloads, no ignition payloads.

The value proposition is persistence at night and comms relay, not speed. Crewed air attack is faster, more capable, and better in wind at everything it does; it is mostly grounded at night. That gap is the entire case for this vertical.

## Mission profiles

**1. Overnight perimeter watch.**

- Operator: agency UAS module attached to a Type 1/2 incident management team, under the incident air operations branch.
- Cadence: nightly, from crewed-aviation stand-down to morning resumption; every operational period of a multi-day incident.
- Payload: micro-UAV radiometric thermal core (engineering target ≤20 g); carrier carries relay radio and dock power.
- Carrier: launches from ICP or spike camp, holds an assigned altitude block 1–3 km from the perimeter, offset laterally/upwind of the column; provides station, power, relay, and the dock cycle.
- Sorties: thermal transects over assigned perimeter segments on a 20–30 min revisit cadence; recover, recharge, repeat all night.
- Product: geo-registered hotspot/perimeter map delivered before the morning operational briefing.

**2. Comms relay over burned infrastructure.**

- Operator: same UAS module or the incident communications unit.
- Cadence: continuous while crews work areas where repeaters and cell sites have burned.
- Payload: relay radio on the carrier; micro-UAV thermal core used only for spot checks.
- Carrier: persistent radio/data relay node at station; endurance and link availability are the whole product.
- Sorties: occasional — spot checks of specific drainages or ridgelines on request.

**3. Crew-position and escape-route watch.**

- Operator: division-assigned UAS module during night work or mop-up.
- Cadence: continuous relay of crew tracker positions; imaging sorties every 30–60 min over pre-briefed routes.
- Payload: relay for crew trackers on the carrier; thermal core on the micro-UAV.
- Carrier: feeds crew positions into the incident common operating picture.
- Sorties: image escape routes and safety zones for new heat; alerting latency matters more than map quality.

The P0 Crazyflie is a control-and-docking stand-in, not the sortie aircraft for this vertical. A useful thermal payload plus outdoor wind margin implies a larger micro-UAV class (engineering target: 100–500 g with a radiometric thermal core ≤20 g).

Aircraft scaling is an open delta, not an assumption; it re-opens dock geometry, probe mass, and the capture-envelope model.

## Why persistent airborne infrastructure

- **Vs quadcopter-only UAS modules (current practice).** Quads win on cost, deployment speed, agency familiarity, and existing NWCG integration. They lose on endurance: 20–40 min per battery means a crew hand-swapping batteries all night to sustain watch, and no persistent relay altitude. The carrier turns the same class of sortie into a continuous service by keeping launch/recover/recharge aloft.
- **Vs fixed-wing (contracted large UAS or crewed FLIR aircraft).** Fixed-wing wins on speed, sensor size, wind tolerance, and coverage rate — for periodic mapping passes it is simply better. It loses on continuous station-keeping cost over one division all night and cannot host/recharge close-in assets. If the incident can task a nightly fixed-wing IR flight, that alternative wins for perimeter product; the carrier case then rests on relay plus sub-hour revisit.
- **Vs satellite.** VIIRS/GOES-class products win on synoptic coverage and cost (free to the incident). They lose on resolution (hundreds of m per pixel), revisit (hours), and cloud/smoke sensitivity. Satellite complements rather than competes.
- **Vs ground camera networks and lookouts.** Cameras win on cost and 24/7 coverage of what they can see; they lose to terrain masking and cannot follow a moving perimeter. Ground crews win on judgment; they should not be walking a night perimeter to find heat a sortie can find.
- **Where every alternative wins:** wind. Strong-wind events drive the worst fire behavior and are exactly when a slow buoyant carrier is grounded. This vertical is honest about serving the moderate-wind, nighttime phase of an incident, not the wind-driven run.

## Concept of operations

1. Pre-incident: agency operating approval, deconfliction procedures written into the incident air operations plan, assigned altitude block and frequencies, positive two-way coordination path to air attack established. No approval, no deployment.
2. Deployment: carrier trucked in deflated, inflated and mast-moored at ICP/spike camp; helium logistics staged; configuration identity recorded per the engineering-loop promotion contract.
3. Evening launch: after crewed aviation stands down and air attack acknowledges the operation, carrier climbs to its assigned block and transits to the standoff loiter point (1–3 km from perimeter, upwind/lateral of the column, outside pre-briefed tanker/helicopter routes).
4. Station-keeping: carrier holds the loiter box; continuous relay service starts; envelope skin temperature, particulate load, and wind are monitored against abort limits.
5. Sortie cycle (the dock cycle): release micro-UAV → thermal transect of assigned perimeter segment → return to carrier → terminal approach on GNSS-independent relative navigation (IR beacon candidate; trade open) → funnel capture → `S1 AND S2` confirmed → disarm → charge on dock → next release. Cycle repeats through the operational period.
6. Product/alerting: hotspot map segments and crew-position picture pushed to the incident common operating picture as produced; escape-route heat alerts pushed immediately.
7. Contingency: loss of the deconfliction link, TFR status change, or wind above limit → carrier immediately holds/descends per pre-briefed procedure and notifies air attack; airborne micro-UAV recovers or terminates at a pre-briefed point. The system never negotiates for airspace.
8. Morning recovery: carrier descends and moors before crewed aviation resumes; helium top-off, battery swap, evidence packet reduced and dispositioned.

## Requirement deltas vs P0

All rows are engineering targets. None are measured, modeled, or cited.

| ID | Observable | Target | Driver |
| --- | --- | --- | --- |
| FIRE-001 | Positive air-attack clearance state before any launch/climb | launch inhibited without current clearance token; revocation → hold/descend ≤60 s | uncoordinated UAS grounds all air attack; integration is a prerequisite, not a feature |
| FIRE-002 | Geofence/altitude-block containment, enforced independently of the autonomy computer | zero excursions from assigned block; hard ceiling and lateral bounds | TFR operations alongside tankers/helicopters |
| FIRE-003 | Carrier station-keeping wind envelope | holds loiter box in 8 m/s sustained, 12 m/s gust; auto-descend above | night drainage winds and convective gusts near fire |
| FIRE-004 | Standoff from fire front / convection column | ≥1 km lateral, never downwind-overhead of active front | thermal turbulence, ember lofting, column updrafts |
| FIRE-005 | Envelope skin temperature | ≤60 °C sustained (PU envelope softening limit — assumption, verify with envelope vendor) | radiant/convective heat exposure |
| FIRE-006 | Sensor and propulsion function under smoke particulates | full function at PM2.5 ≥500 µg/m³ for ≥8 h; bounded terminal-nav degradation | smoke is the operating environment, not an exception |
| FIRE-007 | GNSS-independent terminal relative navigation (shared derived requirement, all non-lab verticals) | capture-grade relative position ≤1/3 funnel radius (≤30 mm, 3σ) in smoke and 0 lux | 180 mm funnel is sized for mm-grade positioning; Lighthouse does not exist over a fire |
| FIRE-008 | Night capture operation | full dock cycle at 0 lux ambient; anti-collision lighting per applicable rule | crewed aviation gap at night is the mission |
| FIRE-009 | Carrier on-station persistence | ≥72 h per deployment across operational periods | multi-day incident coverage without daily teardown |
| FIRE-010 | Perimeter segment revisit cadence | ≤30 min per assigned segment, sustained ≥10 h | overnight perimeter watch product |
| FIRE-011 | Relay service continuity | ≥95% link availability over an operational period within relay footprint | burned comms infrastructure |
| FIRE-012 | Lost-link/flyaway behavior | deterministic hold-then-descend; zero transit toward briefed air-attack routes | failure must be predictable to other aircraft |
| FIRE-013 | Crew-alert latency | heat detection near escape route → alert at IC ≤60 s | crew safety monitoring is only useful if fast |
| FIRE-014 | Dock turnaround incl. charge | recovery-to-next-release ≤ sortie flight time (sustained cadence with 2 aircraft) | continuous watch from a finite fleet |

## What the digital twin must simulate

Primary outputs per campaign: capture success rate, closing-speed distribution, contact/violation counts, and abort statistics — the same observables the P0 gates score.

- **FIRE-003/004 — `outdoor-gust-sweep`:** extend the wind axis with thermal-convective gust spectra (higher vertical component, shorter correlation time than neutral boundary-layer gusts) and report capture success and loiter-box containment vs gust level. Output feeds the FIRE-003 wind limit.
- **FIRE-006/007 — `degraded-sensor-sweep`:** model smoke as positioning-noise growth plus dropout bursts on the terminal-nav sensor, sweeping from Lighthouse-grade mm noise through cm-grade noise. The existing result that the 180 mm funnel needs mm-grade relative positioning is the anchor; this sweep bounds how much smoke degradation the funnel geometry tolerates before capture rate collapses.
- **FIRE-008 — `sil-p0b`, `sil-p0c`:** rerun the gate scenarios with the night/smoke sensor model substituted for Lighthouse and gust forcing on the dock. Same pass thresholds (≥9/10, closing speed ≤0.20 m/s, zero contacts) — the gates do not soften because the environment got harder.
- **FIRE-010/014 — `sil-p0d`:** extend the two-aircraft sequencing scenario into a sustained-cadence campaign: one aircraft flying while one charges, Monte Carlo over sortie duration and turnaround time, reporting achieved revisit cadence vs FIRE-010.
- **FIRE-001/012 — new SIL scenario (deterministic state machine, no new physics):** clearance-token revocation and lost-link injection at every phase of the dock cycle; pass requires hold/descend within limit and zero geofence excursions. This is fail-safe supervisor logic and belongs in SIL-B before any hardware exists.
- FIRE-005 (envelope thermal) and FIRE-011 (RF link) are outside the current twin's capture-physics scope; they need separate models before any claim is made.

## Safety and regulatory considerations

Considerations to verify with counsel and the operating agency — none of this is a legal conclusion.

- **Fire TFRs (14 CFR 91.137):** essentially all target operations occur inside a TFR. Operating there requires authorization and procedural integration with the incident; the public messaging is blunt — an unauthorized drone grounds all air attack.
- **Incident airspace procedures:** fire traffic area conventions, altitude-block assignment, and coordination with the air tactical group supervisor. NWCG standards for interagency fire UAS operations (PMS 515-family documents) define how UAS modules integrate; this system must fit those procedures, not invent parallel ones.
- **14 CFR Part 107 vs public aircraft operations:** agency operations may run under Part 107 with waivers or as public aircraft under a COA. Night operations (107.29) are now allowed with anti-collision lighting; BVLOS, operations over people, and the airship carrier itself (unusual aircraft category for a UAS rule built around small multirotors/fixed-wing) each need explicit regulatory paths.
- **Remote ID (14 CFR Part 89):** applies to carrier and micro-UAVs; broadcast behavior inside a TFR should be coordinated, not just compliant.
- **Helium handling and mast-mooring** at an ICP: ground-crew procedures, ember fallout on a moored envelope, and evacuation of the mooring site if the fire moves.
- **Spectrum:** relay payload frequencies must be coordinated with the incident communications unit; interfering with fire tactical channels is disqualifying.

## Open engineering risks

Ranked. The first three are killers: any one of them, unresolved, ends the vertical regardless of how well the rest performs.

1. **Airspace integration may simply not be granted.** An uncoordinated drone grounds all air attack; agencies are correctly conservative. If air-attack command integration (FIRE-001) — procedural, technical, and institutional — cannot be achieved, this vertical does not exist. This is a prerequisite to test planning, not a feature to add later.
2. **Wind and thermal turbulence vs a slow buoyant carrier.** Convective gusts near a fire can exceed a small airship's total airspeed capability. If `outdoor-gust-sweep` with fire-convection spectra shows no usable standoff loiter envelope at night, the carrier architecture is wrong for this environment and no dock or sensor work rescues it.
3. **Heat and particulate exposure.** Envelope material limits (FIRE-005, currently an assumption), ember contact on a large slow surface, and smoke fouling of motors/optics/terminal-nav sensors. Helium is inert, but envelope loss over an incident is a falling-mass hazard onto the people the system claims to protect.
4. **Terminal navigation in smoke at night.** Capture needs mm-grade relative positioning (established P0 result) with no Lighthouse, no reliable optical contrast, and degraded GNSS geometry near terrain. If `degraded-sensor-sweep` shows the smoke-noise level sits past the capture-rate cliff, the funnel or the sensor concept must change.
5. **Sortie aircraft gap.** Crazyflie-class aircraft cannot carry a radiometric thermal payload with outdoor wind margin. The vertical requires a new micro-UAV class and a resized dock interface — real engineering, not a configuration change.
6. **Field logistics.** Helium supply at remote incidents, mooring a multi-meter envelope in fire weather, and crewing a 24 h operation from a UAS module that already has a full job.
7. **Competition on the product.** If nightly contracted fixed-wing IR mapping plus satellite products satisfy the incident, only the relay and sub-hour-revisit cases remain. The vertical must win on cadence and relay, or not at all.

## Commonality with core

- Dock mechanism unchanged: funnel + probe + spring collet + servo keeper, mounted to structure, never to the envelope.
- Capture truth unchanged: `S1 AND S2` dual independent switches; disarm only after confirmed capture.
- Fail-safe controller semantics unchanged: safety supervisor outside the docking state machine; invalid estimate → abort/hold; physical kill and release-inhibit paths independent of the autonomy computer. FIRE-001/012 extend the abort taxonomy; they do not replace it.
- Evidence-gated loop unchanged: requirement + kill criterion → SIL → bench → flight; immutable configuration identity; disposition taxonomy; no gate closes on a demo.
- Twin scenarios reused: `sil-p0b`/`sil-p0c`/`sil-p0d` remain the gate mirrors; this vertical parameterizes their environment and sensors rather than forking them, and inherits `outdoor-gust-sweep` and `degraded-sensor-sweep` as its primary feasibility instruments.
- Shared derived requirement inherited: GNSS-independent terminal relative navigation (FIRE-007) is the same requirement every non-lab vertical carries; the sensor trade (vision/UWB/IR beacon) stays open and common.
