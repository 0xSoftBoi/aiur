# Consumer toy / STEM education vertical

Status: exploratory concept study — no funded milestone. CARRIER-P0 remains the only funded article.

The plain observation first: the P0 article already **is** nearly a toy. An indoor helium blimp that launches and recovers a tiny autonomous drone is a "mothership playset" without any concept work. The engineering question is not "can this be fun" — it is whether the P0 architecture survives three subtractions: subtract Lighthouse ($ hundreds of positioning infrastructure), subtract room-scale helium volume, and subtract an engineer from the operating loop.

This vertical also carries a program-level role: it is the mass-manufacturing cost-down driver for the dock. An injection-molded funnel/keeper at toy volumes (10⁴–10⁵ units) feeds tooling, unit cost, and reliability statistics back into every other vertical. No other vertical plausibly reaches those volumes.

## Mission profiles

### Profile 1 — STEM / maker kit (first market)

- Operator: educator, university lab, hobbyist already inside the Crazyflie ecosystem.
- Cadence: bench and classroom sessions, tens of capture cycles per session.
- Payload: 1 Crazyflie-class micro-UAV (~30–40 g), open firmware, loggable telemetry.
- Carrier: small tethered or free-flying indoor blimp holds station; the kit's teaching content **is** the launch/recover/dock cycle — students instrument S1/S2, tune terminal approach, run the same evidence loop as P0.
- Sorties: short autonomous hops (waypoint, follow, return-to-dock) programmed by the user.
- Positioning: Lighthouse acceptable at this tier — labs and schools can amortize base stations. This is the bridge market while toy-grade terminal navigation is developed.

### Profile 2 — mass-market toy (later)

- Operator: consumer, indoor, zero calibration tolerance, no external infrastructure.
- Cadence: play sessions of 10–20 min flight, weeks of shelf time between sessions.
- Payload: 1 micro-UAV, tens of grams, fully prop-guarded.
- Carrier: living-room-scale blimp (≤2 m class, not 4.5 m) loiters; the core interaction is the drone autonomously returning to the belly dock. Recharge-on-dock is the eventual play-cycle closer (P0 explicitly defers charging; same here).
- Sorties: pre-canned behaviors (launch, orbit, photo pass, return) triggered from a phone.

### Profile 3 — museum / science-center demonstrator

- Operator: exhibit staff; daily scripted cycles in a controlled hall.
- Effectively a ruggedized P0-C running continuously. Highest cycle count of any profile — useful dock-wear data source. Lighthouse acceptable (fixed venue).

## Why persistent airborne infrastructure

- vs quadcopter-only toys: a $40 toy quadcopter wins on price, robustness, and zero logistics — it needs no helium, no envelope, no dock. It loses on flight time (minutes) and on narrative: it is one aircraft, not a system. The carrier adds persistence (buoyant loiter rather than powered hover; no measured power model yet) and the launch/recover/recharge cycle, which is the actual product.
- vs RC blimp toys (existing category): a bare toy blimp wins on simplicity and has existed for decades; it carries nothing and recovers nothing. The dock is the differentiator, and it is also the entire added cost and risk.
- vs ground "mothership" playsets (truck/carrier + small vehicles): win on price and safety, lose on the aerial cycle. They are the correct benchmark for retail price expectations, which is sobering.
- vs simulator/app-only STEM products: win on cost and classroom logistics; lose on teaching real estimation, contact mechanics, and evidence discipline. The kit's value is that the twin and the bench article are the same lesson.

Honest summary: for pure play value per dollar, the quadcopter toy wins. This vertical only works if the system narrative (mothership + autonomous return) commands the premium, and if positioning cost collapses.

## Concept of operations

Canonical STEM-kit session, single micro-UAV:

1. Setup: user inflates or tops off envelope, clips ballast trim, mounts dock on the gondola rail. Target ≤15 min from box to neutral buoyancy (TOY-010).
2. Reference up: at kit tier, Lighthouse or printed floor markers; at toy tier, carrier-mounted terminal-nav beacon only (TOY-002). Self-check must pass before arming.
3. Launch: micro-UAV releases from the dock (keeper opens, S2 confirms open, drone arms, drops/climbs clear). Carrier holds station.
4. Sortie: drone flies a user-programmed or pre-canned pattern, 5–8 min.
5. Return: drone acquires the carrier terminal-nav reference and flies the same terminal approach law as P0 — closing speed limited, abort on invalid estimate.
6. Capture: funnel accepts lateral error, probe seats, S1 closes, keeper drives, S2 closes. Capture is true only on S1 AND S2 — identical semantics to P0.
7. Secured: drone disarms only after S1 AND S2. Session data (approach error, closing speed, outcome) is loggable in the kit tier — the classroom debrief mirrors the program's evidence loop.
8. Recharge (deferred, mirrors P0.1): dock contact charging closes the play cycle so the next launch needs no handling. Not assumed for the first kit.
9. Stow: envelope stays inflated between sessions; lift loss over shelf weeks is a hard requirement (TOY-006), not a nice-to-have.

## Requirement deltas vs P0

All rows Status: engineering target. Cost figures are assumptions, not quotes.

| ID | Observable | Target | Driver |
| --- | --- | --- | --- |
| TOY-001 | Terminal relative navigation without external infrastructure | Capture-grade relative pose from carrier-mounted beacon/camera + drone sensor, added BOM ≤$10 | Lighthouse base stations cost more than the whole toy; shared derived requirement with all non-lab verticals (GNSS-independent terminal relative nav; vision/UWB/IR trade open) |
| TOY-002 | Terminal-nav relative position error (RMS, capture volume) | ≤3 cm at ≤1.5 m range | Funnel resizing input; toy-grade sensor class, per degraded-sensor-sweep axis |
| TOY-003 | Funnel entrance diameter at toy-grade noise | Sized by twin for ≥90% capture at TOY-002 noise; expect >180 mm | 180 mm funnel is sized for mm-grade positioning; cm-grade noise likely forces a larger funnel — twin quantifies before any tooling |
| TOY-004 | Toy-scale dock assembly mass | ≤50 g complete (funnel, collet, keeper, servo, switches) | A ≤2 m envelope lifts ~200–600 g gross; the 180 g P0 dock does not scale down for free |
| TOY-005 | Carrier envelope length / lift budget | ≤2.0 m envelope; positive margin with dock + drone + avionics at ~1.0 g/L helium net lift (physics estimate; balloon-grade gas mixtures lift less — assumption to verify) | Living-room ceilings, doorways, and retail box size |
| TOY-006 | Envelope helium retention | ≤10% lift loss over 14 days shelf-inflated | Consumer helium logistics; a toy that needs weekly refills is returned |
| TOY-007 | Consumer refill path | Refill from retail balloon-grade cylinder, ≤$15/fill, no regulator skill required | Helium cost/availability is a purchase-decision input, not an ops detail |
| TOY-008 | Micro-UAV all-up mass | ≤60 g with mandatory full prop guards (P0 reference: 37 g guarded) | Injury energy, small-UAS registration threshold headroom (tens of grams vs 250 g — consideration to verify) |
| TOY-009 | Small-parts and mechanical safety | No detachable component fails small-parts gauge; no accessible pinch >X N at keeper (X set by standard) | ASTM F963 consideration to verify; keeper is a powered pinch point |
| TOY-010 | Out-of-box setup time | ≤15 min, non-expert, no tools | Toy-tier operator model |
| TOY-011 | Dock mechanism unit cost at volume | ≤$4 molded funnel + keeper set at 50k units (assumption) | The cost-down feedback this vertical owes the rest of the program |
| TOY-012 | Dock cycle life, unattended handling | ≥1,000 capture/release cycles, ≥200 crash-adjacent probe insertions off-axis | Children are a worst-case load spectrum vs the P0-A 50-cycle gate |
| TOY-013 | Battery cell compliance path | Cells with UN 38.3-style transport test documentation; charge only while docked or in cradle | Consumer shipping and household charging; consideration to verify |
| TOY-014 | Single-action kill | One physical control drops carrier propulsion and inhibits release, reachable by an adult | Same fail-safe philosophy as P0 physical kill path, consumer-shaped |

## What the digital twin must simulate

The twin (aiur/sim, deterministic dependency-free Python) is the gate between this concept and any tooling spend.

- TOY-001/002/003 — run `degraded-sensor-sweep` across the full noise axis, Lighthouse-grade mm up to toy-grade and GNSS/RTK-grade cm noise, and report capture probability vs funnel entrance diameter. Output is the funnel-size curve: the single number this vertical needs before injection-mold tooling. Known starting point: 180 mm assumes mm-grade positioning.
- TOY-004/005 — extend the p0.py mass/lift model to a ≤2 m envelope parameter sweep; kill the vertical on paper if no (envelope, dock mass, drone mass) triple closes with margin.
- Indoor disturbance — reuse `outdoor-gust-sweep` at its low wind levels as an HVAC-draft proxy; a living room with forced air is not still air, and a 2 m blimp has less control authority than the 4.5 m article.
- Capture logic — `sil-p0b` and `sil-p0c` rerun unchanged except for the toy-scale funnel geometry and TOY-002 noise model; the S1 AND S2 state machine and abort semantics are identical, so the same SIL-B/SIL-C gates apply.
- TOY-012 — Monte Carlo off-axis insertion campaign (angle/velocity distributions from a child-handling assumption set, labeled as such) to drive keeper and collet fatigue load cases.
- Sequencing — `sil-p0d` is out of scope for a one-drone toy; applies only if a two-drone SKU is ever considered.

## Safety and regulatory considerations

All items are considerations to verify with counsel/test labs, not legal conclusions.

- ASTM F963 (US toy safety standard): small parts, sharp edges, battery access, motor/pinch hazards. The keeper servo and propellers are the obvious review items. EU equivalent EN 71 if sold there.
- Battery transport and handling: UN 38.3-style transport testing for lithium cells, plus consumer-product battery requirements (e.g., button/coin-cell rules do not apply, but charging-system requirements may).
- Aircraft rules: micro-UAV mass is tens of grams, far under the 250 g US registration threshold, and operations are indoor — but "indoor toy" vs regulated small-UAS boundaries (14 CFR Part 107 vs recreational exception) must be verified, not assumed. Outdoor marketing claims would change the analysis entirely; this concept is indoor-only.
- RF: Crazyflie-class radios and any camera/beacon link fall under FCC Part 15-style device authorization.
- Helium: inert asphyxiant, not flammable; consumer messaging about balloon-gas handling still required. Hydrogen remains excluded here exactly as in P0.
- Mandatory prop guards and blade-contact energy limits: treat as a design requirement (TOY-008/009) regardless of which standard formally forces it.

## Open engineering risks

Ranked; killers first.

1. Positioning cost kills the toy tier. Lighthouse is instrumentation, not a product architecture — two base stations exceed a defensible toy retail price on their own. The toy lives or dies on TOY-001 terminal nav at ≤$10 BOM, and `degraded-sensor-sweep` already implies the price of cheap sensing is a larger funnel. If the required funnel exceeds what a ≤2 m envelope can carry and box constraints allow, there is no product.
2. Helium logistics kill the consumer tier. Refill cost, balloon-grade gas lift shortfall, and envelope leakage over shelf weeks (TOY-006/007) are unforgiving; a deflated toy in week two is a return. The STEM tier tolerates this; the mass market may not.
3. Safety compliance is a schedule and BOM tax. ASTM F963-class review of a powered keeper, spinning props, and a lithium cell in a child-adjacent product is real engineering, not paperwork. Assume it reshapes the drone-side hardware.
4. Lift budget at toy scale may not close. Envelope volume falls with length cubed; dock mass does not. 5.5 m³ → ~0.2 m³ at 1/3 scale is a ~200 g gross-lift class vehicle, which the current 180 g dock alone nearly consumes. TOY-004/005 must close in the model before anything is built.
5. Durability under child handling. The P0-A gate is 50 careful cycles; TOY-012 asks for 1,000 careless ones. The collet/keeper may need a materials change that then propagates back into the core program.
6. Price/value vs the $40 quadcopter. Even with everything solved, the system premium must survive a retail shelf next to cheaper, tougher, logistics-free alternatives.

## Commonality with core

Identical, by design:

- Dock mechanism topology: funnel + probe + spring collet + servo-driven positive keeper. The toy article rescales it; it does not redesign it.
- Capture truth: S1 AND S2 dual independent switches; disarm only after both. No cost-down removes the second switch.
- Fail-safe controller semantics: abort/hold on invalid estimate, physical kill and release-inhibit outside the autonomy loop (TOY-014 is the consumer form of the P0 kill path).
- Evidence-gated loop: kit-tier sessions produce the same run-record shape (config identity, S1/S2 states, approach telemetry, outcome) — which is also the STEM curriculum.
- Twin scenarios: SIL-B/SIL-C gates and the `sil-p0b`/`sil-p0c` presets rerun with toy parameters; `degraded-sensor-sweep` is the shared tool for every non-Lighthouse vertical's terminal-nav requirement.
- Feedback to core: toy-volume injection molding of the funnel/keeper is the intended cost-down path for the dock in every other vertical.

Nothing in this vertical advances until P0-C closes (per program sequencing; P0-D two-aircraft sequencing is out of scope for a one-drone SKU). A toy of a mechanism that has not yet worked once is concept art.
