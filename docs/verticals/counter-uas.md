# Counter-UAS airspace awareness vertical

Status: exploratory concept study — no funded milestone. CARRIER-P0 remains the only funded article.

Scope is **detection, tracking, classification, and airspace picture**: knowing what is in the air over a protected site, where it came from, and where it is going. The carrier is a persistent elevated sensor and compute node that also launches and recovers close-look aircraft.

**Out of scope, deliberately and permanently for this study: effectors.** No interceptors, no one-way attack aircraft, no kinetic or directed defeat payloads, no jamming or spoofing. Those are weapons engineering; this study does not size, trade, or specify them, and the requirement deltas below contain no effector row. A customer who needs defeat pairs this sensing layer with a defeat system they procure and authorise separately, under their own legal authority.

That boundary is also the vertical's biggest commercial risk, and it is named as such in the risk section rather than hidden.

## Why this is a plausible vertical at all

Detection is where counter-UAS actually fails. Published incident after incident at airports and large venues comes down to nobody having a reliable picture: intermittent tracks, terrain-masked radar, RF sensors that lose the target when it flies a pre-programmed route with the link off. Persistence and elevation are the two things that fix picture quality, and they are exactly what a buoyant carrier is good at.

The honest counterweight is in the alternatives section: **tethered aerostats carrying surveillance radar are a fielded, mature product.** The novel part of this architecture is not "sensor on a lighter-than-air platform" — that exists. It is the dock cycle: hosting, launching, recovering and recharging close-look aircraft from the same persistent node.

## Mission profiles

**1. Fixed-site persistent airspace watch.**

- Operator: site security operations centre — airport, stadium, refinery, substation, data centre, correctional facility.
- Cadence: continuous, or continuous during defined risk windows (event days, shift changes).
- Payload: carrier hosts the detection sensor suite (radar and/or passive RF and/or EO-IR) plus classification compute; micro-UAVs carry a close-look EO payload.
- Carrier: holds an assigned altitude block over or adjacent to the site; provides station, power, compute, and the dock cycle.
- Product: continuous track picture into the site's existing security system — track ID, position, altitude, heading, classification confidence, and where available the launch point.

**2. Close-look sorties (the reason the dock exists here).**

- Trigger: the carrier's wide-area sensor produces a track that its own sensors cannot classify — too small, too distant, too much clutter, or an ambiguous RF signature.
- Sortie: release a micro-UAV to close the range and return imagery sufficient for a human to classify the object and its payload, then recover and recharge.
- Value: converts an ambiguous radar contact into a decision-grade observation without launching anything crewed and without the site needing a second aircraft on standby.
- This is the profile that distinguishes the architecture from an aerostat with a radar on it. If it is not worth doing, the vertical collapses into the incumbent product.

**3. Rapid-deploy temporary coverage.**

- Operator: event security or a mobile protective detail.
- Cadence: hours to days, at a site with no fixed sensor infrastructure.
- Carrier: trucked in, inflated, mast-moored, providing a picture where none exists.
- Honest limit: setup time for a helium vehicle is hours, not minutes. This profile loses outright to a trailer-mounted radar for anything short-notice.

The P0 Crazyflie is a control-and-docking stand-in, not the sortie aircraft. A useful close-look EO payload with outdoor wind margin implies a larger micro-UAV class (engineering target: 250–800 g), which re-opens dock geometry, probe mass, and the capture-envelope model — the same delta the wildfire study carries.

## Why persistent airborne infrastructure

- **Vs ground radar and RF sensor networks (current practice).** Ground sensors win on cost, maturity, certification path, and needing no airspace approval at all. They lose to terrain masking and to the radar horizon: a sensor at 4 m sees a low-flying small drone for a fraction of the range that the same sensor sees at 300 m. Elevation is worth more than sensor upgrades for low-altitude targets, and it is the one thing a mast cannot buy past its own height.
- **Vs tethered aerostats (the real incumbent).** Aerostats already deliver persistent elevated sensing and are fielded for exactly this. They win on maturity, endurance, and payload mass. They lose on mobility, on tether-length altitude limits, and on the thing this architecture adds: they cannot host, launch, recover, or recharge close-look aircraft. **If the close-look sortie profile does not carry real value, buy an aerostat instead** — that is the correct recommendation and the study should say so.
- **Vs multirotor UAS on standby.** Quads win on cost, response agility, and being able to chase. They lose on endurance: they cannot maintain a picture, only respond to one someone else produced.
- **Vs crewed aircraft.** No contest on cost per hour for persistent watch.
- **Where every alternative wins:** wind, and speed of response. A buoyant carrier is slow, cannot chase anything, and is grounded in the conditions a determined operator would choose. This vertical is honest about being a *picture* system for permissive airspace, not a response system and not a contested-environment system.

## Concept of operations

1. Pre-deployment: airspace authorisation for a large lighter-than-air vehicle over the site, altitude block assignment, spectrum coordination for the sensor payload, and a written legal review of RF detection (see safety and regulatory). No authorisation, no deployment.
2. Deployment: carrier inflated and mast-moored at the site; configuration identity recorded per the engineering-loop promotion contract.
3. Climb to assigned block; wide-area sensing and track publication begin; tracks flow into the site's existing security picture, not a parallel one.
4. Station-keeping with continuous track service. Envelope status, wind, and link availability monitored against abort limits.
5. Close-look cycle (the dock cycle): ambiguous track → release micro-UAV → transit and image → return → terminal approach on GNSS-independent relative navigation → funnel capture → `S1 AND S2` confirmed → disarm → charge on dock → ready for next tasking.
6. Handoff: classification and imagery go to a human operator. **The system publishes a picture and stops there.** Any response is the customer's decision under the customer's authority, executed with systems this programme does not build.
7. Contingency: authorisation revoked, wind above limit, or lost link → carrier holds/descends per pre-briefed procedure; airborne micro-UAV recovers or terminates at a pre-briefed point.

## Requirement deltas vs P0

All rows are engineering targets. None are measured, modeled, or cited.

| ID | Observable | Target | Driver |
| --- | --- | --- | --- |
| CUAS-001 | Airspace authorisation state before any climb | climb inhibited without current authorisation token; revocation → hold/descend ≤60 s | a large LTA vehicle over a populated site is an airspace participant first and a sensor second |
| CUAS-002 | Geofence/altitude-block containment, enforced independently of the autonomy computer | zero excursions from assigned block | operating adjacent to controlled airspace, often near an airport |
| CUAS-003 | Carrier station-keeping wind envelope | holds station in 8 m/s sustained, 12 m/s gust; auto-descend above | inherits SHARED-002; a picture system that is down on windy days has a coverage gap an adversary can read off a forecast |
| CUAS-004 | Carrier on-station persistence | ≥168 h per deployment (one week) between servicing | fixed-site watch is only a product if it is continuous |
| CUAS-005 | Wide-area detection range for a 0.01 m² RCS target | engineering target only; must be set by the sensor trade, not assumed | the entire value proposition is picture quality; this row is deliberately unresolved |
| CUAS-006 | Track continuity | ≥95% track retention through a 60 s engagement window within the coverage volume | intermittent tracks are the observed failure mode of deployed systems |
| CUAS-007 | Classification handoff latency | ambiguous track → close-look imagery at operator ≤5 min within 3 km | if this is slower than the event, the sortie profile has no value |
| CUAS-008 | Close-look sortie readiness | ≥1 aircraft launch-ready at all times, sustained across a deployment | derived from the fleet-throughput model, not assumed |
| CUAS-009 | GNSS-independent terminal relative navigation (shared) | capture-grade relative position ≤1/3 funnel radius (≤30 mm, 3σ), including under GNSS interference | inherits SHARED-001; a site experiencing drone incursion is a site where GNSS may be degraded |
| CUAS-010 | Dock turnaround incl. charge | recovery-to-next-release ≤ sortie flight time | inherits SHARED-004 |
| CUAS-011 | Track data integrity and provenance | every published track carries sensor, time, and configuration identity; tamper-evident record | security customers act on this data; unattributable tracks are not evidence |
| CUAS-012 | Lost-link/flyaway behaviour | deterministic hold-then-descend; zero uncommanded transit toward the protected asset | the system must never become the incursion it was bought to detect |
| CUAS-013 | Carrier self-reporting | carrier and micro-UAVs continuously identify themselves to the site picture and per Remote ID | a counter-drone system that shows up as an unknown track on its own display is a defect |
| CUAS-014 | Privacy-constrained sensing | EO payload operation bounded by a written data-retention and pointing policy enforced in software | fixed-site persistent EO over populated areas has a legal and reputational surface independent of the mission |

## What the digital twin must simulate

Primary outputs per campaign: capture success rate, closing-speed distribution, contact/violation counts, and abort statistics — the same observables the P0 gates score.

- **CUAS-008/010 — [`aiur.sim.fleet`](../fleet-throughput.md):** readiness and turnaround are a queueing question, and the fleet model already answers it. A one- or two-aircraft close-look fleet with a demanding readiness requirement is the *opposite* regime from the 200-aircraft sweeps: readiness, not throughput, is binding, and the study's recharge-limited finding applies directly.
- **CUAS-003 — `outdoor-gust-sweep`:** inherited unchanged from SHARED-002. Coverage-availability-vs-wind is the output this vertical needs, expressed as expected hours per year on station for a candidate site's wind climatology.
- **CUAS-009 — `degraded-sensor-sweep`:** extend with a GNSS-denial case rather than only a noise-growth case. The existing anchor result — the 180 mm funnel is sized for mm-grade relative positioning — is what makes this a real constraint.
- **CUAS-002/012 — new SIL scenario (deterministic state machine, no new physics):** authorisation-token revocation and lost-link injection at every phase of the dock cycle; pass requires hold/descend within limit, zero geofence excursions, and zero transit toward the protected asset.
- **CUAS-005/006 (detection and tracking) are outside the twin's scope entirely.** The twin models capture physics; it has nothing to say about radar range or track continuity, and must not be quoted as if it does. Those need a sensor model that does not exist and a sensor trade that has not been run.

## Safety and regulatory considerations

Considerations to verify with counsel — none of this is a legal conclusion.

- **Airspace authorisation for the carrier itself.** A large LTA vehicle station-keeping over a populated site, frequently near an airport, is the hardest approval in this study. It is a prerequisite to test planning, not a feature.
- **RF detection may be legally constrained.** Passive detection of drone control links can implicate communications-interception and privacy statutes depending on jurisdiction and on what is decoded rather than merely detected. This needs a written legal review before a sensor trade selects an RF modality, not after.
- **No defeat capability is authorised by detection.** In most jurisdictions the authority to interfere with an aircraft — including a small drone — rests with specific government entities and not with a site operator. This is a further reason the study stops at the picture.
- **Persistent EO over populated areas** carries data-protection obligations and a reputational surface that is independent of whether the system works.
- **Remote ID and self-identification** apply to the carrier and micro-UAVs (CUAS-013).
- **Spectrum coordination** for any active sensor, particularly near airport surveillance and weather radar.
- **Export control.** Counter-UAS sensing hardware and software can attract export-control classification even without an effector. Route this before any international discussion.

## Open engineering risks

Ranked. The first three are killers: any one of them, unresolved, ends the vertical.

1. **The customer may not buy the picture alone.** Most counter-UAS procurement is written around detect-*and-defeat*. A sensing-only product may be a component sale into someone else's system rather than a system sale, which is a materially worse business with a stronger incumbent field. This is the vertical's defining commercial risk and it follows directly from the scope boundary at the top of this document.
2. **The incumbent is real and fielded.** Tethered aerostats with surveillance radar already deliver persistent elevated sensing. The entire differentiator is the close-look sortie cycle (profile 2). If a customer does not value converting ambiguous tracks into imagery, the correct recommendation is an aerostat, and this study should be closed rather than defended.
3. **Airspace authorisation over populated sites may never be granted** for a vehicle of this class. No engineering evidence substitutes for it.
4. **Wind availability is a coverage gap with an adversary-visible schedule.** SHARED-002 governs. Unlike agriculture, where a windy day costs a scouting pass, here a predictable down-day is a hole in a security service, and that asymmetry should be priced into the requirement rather than treated as inherited.
5. **The carrier is a large, slow, cooperative object.** In any environment where someone is willing to act against it, it is trivially removable. This bounds the vertical to permissive, protective, domestic-style airspace — it is not a contested-environment system and must not be marketed as one.
6. **Sensor payload mass and power** for a genuinely useful wide-area radar may exceed what a carrier in the scaling class this programme can plausibly build will lift, which would push the whole vertical to a vehicle no one has funded.
7. **Sortie aircraft gap.** Crazyflie-class aircraft cannot carry a useful EO payload with outdoor wind margin; a new micro-UAV class and a resized dock interface are real engineering.
8. **GNSS degradation at exactly the moment of use.** A site experiencing an incursion is a plausible site for GNSS interference, and recovery depends on relative navigation that has not been selected (SHARED-001).

## Commonality with core

- Dock mechanism unchanged: funnel + probe + spring collet + servo keeper, mounted to structure, never to the envelope.
- Capture truth unchanged: `S1 AND S2` dual independent switches; disarm only after confirmed capture.
- Fail-safe controller semantics unchanged: safety supervisor outside the docking state machine; invalid estimate → abort/hold; physical kill and release-inhibit paths independent of the autonomy computer. CUAS-001/012 extend the abort taxonomy; they do not replace it.
- Evidence-gated loop unchanged: requirement + kill criterion → SIL → bench → flight; immutable configuration identity; no gate closes on a demo. CUAS-011 extends the provenance requirement outward to published tracks.
- Twin scenarios reused: `sil-p0b`/`sil-p0c`/`sil-p0d` remain the gate mirrors; this vertical parameterizes their environment and sensors rather than forking them, and adds the fleet-throughput model as a readiness instrument.
- Shared derived requirements inherited: SHARED-001 (CUAS-009), SHARED-002 (CUAS-003), SHARED-004 (CUAS-010).
