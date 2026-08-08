# Oil and gas / energy infrastructure vertical

Status: exploratory concept study — no funded milestone. CARRIER-P0 remains the only funded article.

This document explores whether the P0 carrier/dock architecture extends to energy-infrastructure monitoring. It leads with the reasons it might not: hazardous-location electrical classification is an unsolved, possibly disqualifying constraint for the entire system, and helium logistics at remote sites may kill the economics before certification does.

Nothing here is a claimed capability. Every number below is an engineering target or an open trade routed to the digital twin.

## Mission profiles

### Profile 1 — continuous methane leak detection, well pads and tank farms

- Operator: producer LDAR team or contracted emissions-monitoring service; remote supervision from a control room, one visiting technician per site cluster.
- Cadence: carrier on station over a pad cluster for multi-day periods; micro-UAV sorties every 1–4 h per pad, plus event-triggered sorties on anomaly.
- Payload: micro-UAV carries a lightweight point gas sensor (TDLAS or metal-oxide class; sensor selection is an open trade, all masses are engineering targets) close to flanges, thief hatches, and tank vents. Point sensing requires proximity a standoff platform cannot provide.
- Carrier: persistence, sortie scheduling, recharge dock, telemetry backhaul. Carrier itself never approaches classified equipment — it holds a standoff position (see ENG-001) and sends the small article in.

### Profile 2 — remote-site communications relay plus inspection

- Operator: midstream/upstream operations at sites with no cellular coverage.
- Cadence: carrier is the persistent node — elevated comms relay for ground sensors, crews, and its own micro-UAVs. Inspection sorties (flare stack tips, tank shells, cellar checks) are scheduled or on-demand.
- Payload: relay radio on the carrier; camera/thermal on the micro-UAV.
- Carrier: this is the profile where the buoyant platform earns its keep independent of sorties — an elevated antenna that holds station for days (ENG-005, engineering target), which battery-limited platforms cannot sustain.

### Profile 3 — pipeline right-of-way patrol (weakest profile)

- Operator: pipeline integrity-management group.
- Cadence: slow drift patrol along ROW segments; micro-UAV sorties for close-up look at encroachment, exposed pipe, or leak indications.
- Honest note: fixed-wing aircraft likely win long linear corridors outright (see below). This profile only survives where a segment needs dwell rather than transit — river crossings, active construction encroachment, compressor stations.

## Why persistent airborne infrastructure

Vs quadcopter-only (drone-in-a-box):

- Ground dock wins: certification path (the ignition-source problem is confined to a fenced ground enclosure), capital cost per site, weather tolerance (the drone shelters between sorties), and maintenance access.
- Carrier wins: coverage per dock (one carrier serves a pad cluster instead of one box per pad), elevated comms relay, and persistence at sites with no ground power or infrastructure.

Vs fixed-wing:

- Fixed-wing wins: pipeline transit. km/h and km-per-dollar over long linear corridors are not contestable; Profile 3 concedes this.
- Carrier wins: dwell — hours over one pad, repeated close-approach sorties, hosting the recharge cycle, and hover-capable sortie aircraft.

Vs ground continuous monitors:

- Fixed sensors win: unit cost, HAZLOC certification maturity, and 24/7 coverage of a single pad.
- Carrier wins: localization (a sortie walks the plume to a component; a fence-line sensor cannot) and covering many pads with one asset.

Vs satellite methane detection:

- Satellite wins: basin-scale screening cadence with zero site infrastructure.
- Carrier wins: component-level detection threshold, revisit on demand, and localization to a specific flange. The relationship is complementary — satellite flags, carrier confirms — not competitive.

## Concept of operations

Canonical mission: confirm and localize a suspected methane leak on an unmanned well pad, flagged by a satellite/aerial screening pass.

1. Carrier transits to the pad cluster and establishes station at the standoff position: outside every classified-area boundary by the policy margin (ENG-001), upwind-biased, altitude per ENG-004.
2. Carrier establishes relay link to the operations center; site has no cellular coverage. Link becomes the mission's command path.
3. Carrier deploys one micro-UAV from the belly dock (P0 launch sequence, unchanged semantics).
4. Micro-UAV flies a downwind transect at sensor height, sampling for elevated concentration; carrier holds standoff and relays telemetry.
5. On detection, micro-UAV steps upwind along the concentration gradient to component level, logging geotagged readings near flanges, hatches, and vents.
6. Sortie ends on battery reserve threshold; micro-UAV returns to the carrier terminal-approach corridor.
7. Terminal relative navigation is GNSS-independent (ENG-002): funnel capture, S1 seat confirmation, keeper close, S2 confirmation — identical dual-switch capture truth to P0.
8. Docked micro-UAV recharges via the contact interface (P0.1 lineage, ENG-007); carrier holds station or repositions to the next pad.
9. Repeat sorties per cadence until evidence packet (concentration map, imagery, timestamps) is complete; operator dispositions the leak; carrier releases to the next tasking or recovery point.
10. Any loss of link, position validity, or wind exceedance triggers the same fail-safe controller semantics as P0: abort/hold, never continue-blind.

## Requirement deltas vs P0

All rows: Status = engineering target.

| ID | Observable | Target | Driver |
| --- | --- | --- | --- |
| ENG-001 | Carrier distance to nearest classified-area boundary | ≥ 50 m lateral, geofence-enforced, supervisor-audited | Standoff-distance operating policy: near-term mitigation for unresolved HAZLOC status — a policy, not a certification |
| ENG-002 | Terminal relative-navigation error at funnel entry, GNSS-independent | ≤ 30 mm lateral (1σ) via vision/UWB/IR beacon — trade open | 180 mm funnel is sized for mm-grade relative positioning; Lighthouse does not exist outdoors; shared derived requirement across all non-lab verticals |
| ENG-003 | Capture success in gusts at dock | ≥ 9/10 at sustained 5 m/s, gusting 8 m/s | Outdoor dock motion; P0 dock motion is rig/tether-bounded |
| ENG-004 | Carrier station-keeping radius | ≤ 25 m in sustained 8 m/s wind | Standoff geometry and relay pointing both assume a bounded station |
| ENG-005 | Time on station without resupply | ≥ 72 h | Persistence is the value proposition; below ~24 h a drone-in-a-box wins |
| ENG-006 | Micro-UAV sortie radius with gas-sensor payload | ≥ 500 m from carrier, return with reserve ≥ 20% | Pad-cluster coverage from one standoff station |
| ENG-007 | Recharge turnaround, capture to launch-ready | ≤ 45 min | Sortie cadence of 1–4 h per pad with 1–2 aircraft |
| ENG-008 | Relay link availability, carrier to ops center | ≥ 99% over any 24 h on station | Profile 2 is a comms product; sortie command path depends on it |
| ENG-009 | Helium top-off interval at operating site | ≥ 30 days between resupply | Remote-site helium logistics; drives envelope permeability and makeup-gas carriage |
| ENG-010 | Point-sensor methane detection at component standoff | detect leak-representative concentration at ≤ 1 m from source; threshold TBD against EPA Method 21 practice | Mission exists only if the sortie sensor outperforms fixed monitors on localization |
| ENG-011 | Operating temperature envelope, full system | −20 °C to +45 °C | Basin climates (Permian summer, Bakken winter); P0 is indoor-ambient only |
| ENG-012 | Micro-UAV surface-temperature and spark-source audit | documented ignition-source inventory per hazardous-area review; pass criteria TBD by classification | The micro-UAV, not the carrier, enters the classified area — LiPo cells, brushless motors, and any brushed servo are ignition risks until reviewed |

## What the digital twin must simulate

- ENG-002: `degraded-sensor-sweep` — capture success vs positioning noise from Lighthouse-grade mm noise up to GNSS/RTK-grade cm noise. This vertical's viability threshold is where the curve crosses 9/10 for the candidate terminal-nav modality. Extend the sweep with dropout bursts (vision loss in glare/dust).
- ENG-003, ENG-004: `outdoor-gust-sweep` — capture success vs wind level with the dock on a station-keeping carrier instead of a rig. Add a coupled mode: carrier displacement feeding dock motion during terminal approach.
- ENG-001: new scenario — geofence-enforced standoff in the safety supervisor; fault-inject position drift and confirm abort/hold before boundary penetration. Gate against `sil-p0c` semantics (abort authority at every phase).
- ENG-006, ENG-007: campaign-level sortie-cycle model — sortie radius, reserve margin, recharge time, and cadence as a Monte Carlo over wind and battery dispersion; determines whether 1–2 aircraft sustain the Profile 1 cadence.
- ENG-005, ENG-009: endurance/leakage bookkeeping model — envelope permeability, ballast/makeup budget vs days on station. Deterministic model first; no test article exists to calibrate against, so outputs are labeled model predictions.
- Gate mirrors: `sil-p0b` (moving-dock capture), `sil-p0c` (full cycle with aborts), `sil-p0d` (two-aircraft sequencing) rerun under the outdoor wind and sensor-noise conditions above before any bench article for this vertical is proposed.

## Safety and regulatory considerations

Considerations to verify with counsel and certification bodies — none of the following is a legal conclusion.

- 14 CFR Part 107: baseline sUAS rules for the micro-UAV; visual-line-of-sight default conflicts with the remote-supervision profiles.
- BVLOS: Profiles 1–3 as described require waivers/exemptions to Part 107 (or a future normalized BVLOS rule); the persistent-carrier concept does not close without them.
- Carrier airworthiness category: a station-keeping unmanned airship over industrial sites does not map cleanly onto Part 107 weight classes; the applicable certification path for the carrier itself must be identified, not assumed.
- Hazardous-location electrical classification: NEC Article 500/505 class/division and zone concepts, and industry practice for classified-area extents around wellheads, tanks, and separators (API recommended practices), define the boundaries ENG-001 stands off from. Whether any national scheme currently offers a certification route for a free-flying electric aircraft inside a classified area must be verified; assume none does until shown otherwise.
- Emissions-monitoring context: EPA methane rules for the oil and gas sector and Method 21 component-screening practice set what a leak-detection product must demonstrate to count as an LDAR instrument; sensor equivalence to accepted methods is a regulatory question, not only a technical one.
- Pipeline ROW operations cross PHMSA-regulated assets; operator integrity-management programs constrain what an external platform may overfly and record.
- Site owner permitting: refinery/terminal operators impose their own hot-work and airspace rules stricter than any of the above.

## Open engineering risks

Ranked. The first two are potential program killers for this vertical.

1. Ignition-source certification near potentially explosive atmospheres. Electric motors, LiPo batteries, and brushed servos are ignition risks. Hazardous-location classification of the whole system — carrier and micro-UAV — is unsolved and possibly disqualifying: no identified certification route covers a free-flying electric multirotor inside a Class I area. The standoff-distance operating policy (ENG-001) is the near-term mitigation and must be labeled as such: it is an operating restriction, not a certification, and it directly conflicts with the mission's core requirement that the sensor get close to equipment (ENG-010/ENG-012). If close approach inside classified boundaries is never certifiable, Profile 1 collapses to sampling outside boundaries, and the concept must be re-scored against fixed monitors on that basis.
2. Helium logistics at remote sites. Helium is expensive, supply-constrained, and heavy to truck to sites without infrastructure; ENG-009 may be unachievable at acceptable cost. The irony constraint is explicit and permanent: hydrogen lift is off the table for this vertical, forever — a flammable, leaking lift gas over a methane facility is indefensible regardless of what other verticals decide. This vertical pays full helium cost with no hydrogen escape hatch.
3. Weather. An airship's aeroshape is its liability: gust response scales with envelope area, and ENG-003/ENG-004 targets may be unreachable at the envelope size that also meets ENG-005 endurance. Basin weather (Permian dust, plains wind, winter icing) may cap availability below what a monitoring-service contract can tolerate.
4. Sensor performance vs incumbents (ENG-010). If a micro-UAV point sensor cannot beat fixed continuous monitors plus periodic OGI surveys on detection-per-dollar, the sortie architecture is unnecessary complexity.
5. Terminal navigation outdoors (ENG-002). The shared GNSS-independent relative-nav requirement is unproven; dust, glare, and precipitation attack every candidate modality (vision/UWB/IR beacon).
6. Sortie-cycle economics (ENG-006/ENG-007). 1–2 micro-UAVs with sub-hour endurance may not sustain the cadence; more aircraft means more docks, mass, and sequencing complexity beyond anything P0-D demonstrates.
7. Regulatory sequencing. BVLOS relief, carrier certification path, and LDAR instrument acceptance are three independent approval chains; any one stalling stalls the product.

## Commonality with core

- Dock mechanism: funnel + probe + spring collet + servo keeper, unchanged. Environmental hardening (dust, temperature) is a variant, not a redesign.
- Capture truth: S1 AND S2 dual independent switches remain the only capture confirmation; disarm only after both.
- Fail-safe controller semantics: safety supervisor with abort/hold on invalid state, physical kill and release-inhibit paths outside the autonomy loop — identical contract, extended with the ENG-001 geofence.
- Evidence-gated loop: requirement → SIL → bench → tethered flight → debrief, with immutable configuration identity per run; this vertical adds gates, it does not bypass any.
- Twin scenarios: `sil-p0b`, `sil-p0c`, `sil-p0d` remain the gate mirrors; `outdoor-gust-sweep` and `degraded-sensor-sweep` are shared with every non-lab vertical, not forked.
- Shared derived requirement: GNSS-independent terminal relative navigation (ENG-002 here) is common property of all outdoor verticals; whichever modality wins the trade is inherited, not re-derived.
