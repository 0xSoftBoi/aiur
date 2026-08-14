# Dual-use verticals

Status: exploratory concept studies — no funded milestone in this directory. CARRIER-P0 remains the only funded article. Every number in these studies is an engineering target or an open question routed to the digital twin.

Studies:

- [Agriculture](agriculture.md) — crop scouting, ranch patrol (AGR-001…011)
- [Energy infrastructure](energy.md) — methane LDAR, remote-site relay (ENG-001…012)
- [Wildfire response support](wildfire.md) — night perimeter watch, crew safety relay (FIRE-001…014)
- [Consumer toy / STEM](toys.md) — mothership playset, dock cost-down driver (TOY-001…014)
- [Counter-UAS airspace awareness](counter-uas.md) — persistent site airspace picture, close-look sorties (CUAS-001…014)

Scope is sensing, monitoring, mapping and relay. No vertical in this directory specifies an effector: no interceptors, no one-way attack aircraft, no kinetic or directed defeat payloads, no jamming or spoofing. The counter-UAS study stops at publishing a track picture and hands off to whatever the customer is separately authorised to operate; that boundary is recorded as its defining commercial risk rather than as a footnote.

## One core, many payloads

The thesis: the product core is identical across every vertical. What is being sold changes; what is being engineered does not.

Core, invariant by design:

- buoyant carrier with belly-mounted infrastructure, never envelope-mounted;
- mechanically positive dock: funnel + probe + spring collet + servo keeper;
- capture truth = `S1 AND S2` dual independent switches; disarm only after both;
- fail-safe controller semantics: safety supervisor over guidance, abort/hold on invalid estimate, physical kill and release-inhibit paths outside software;
- recovery autonomy: velocity-limited terminal approach onto a moving dock;
- evidence-gated engineering loop: requirement → SIL → bench → tethered flight → debrief, immutable configuration identity per run;
- digital twin: deterministic dependency-free Python, Monte Carlo campaigns, SIL-B/C/D gates mirroring P0-B/C/D.

Verticals differ in payload, environment, and ops concept — sensor vs relay vs curriculum vs airspace picture, still lab air vs gusts vs smoke, engineer vs LDAR tech vs child vs security operator. A vertical study is a parameter overlay on the core, never a fork of it.

## Commonality matrix

| Core capability | Agriculture | Energy | Wildfire | Toys | Counter-UAS |
| --- | --- | --- | --- | --- | --- |
| Dock mechanism (funnel/probe/collet/keeper) | identical + environmental hardening (AGR-009) | identical + environmental hardening | new work: resized for 100–500 g aircraft class (FIRE) | parameter change: rescaled funnel, molded (TOY-003/004/011) | new work: resized for 250–800 g aircraft class, shared with FIRE |
| Capture-truth semantics (`S1 AND S2`) | identical | identical | identical | identical | identical |
| Terminal guidance + safety supervisor | semantics identical; sensor new work (SHARED-001) | semantics identical + geofence extension (ENG-001); sensor new work | semantics identical + clearance/lost-link extension (FIRE-001/012); sensor new work | identical at kit tier (Lighthouse); sensor new work at toy tier (TOY-001) | semantics identical + authorisation/lost-link extension (CUAS-001/012); sensor new work incl. GNSS-denial case |
| Evidence/promotion contract | identical | identical | identical | identical (kit sessions emit the same run-record shape) | identical, extended outward to published track provenance (CUAS-011) |
| Twin gate scenarios (`sil-p0b`/`sil-p0c`/`sil-p0d`) | parameter overlays | overlays + new geofence SIL scenario | overlays + new deconfliction/lost-link SIL scenario | overlays with toy geometry; `sil-p0d` out of scope for one-drone SKU | overlays + new authorisation/lost-link SIL scenario; adds `aiur.sim.fleet` as a readiness instrument |
| Energy/recharge cycle (deferred in P0) | new work (AGR-005/006) | new work (ENG-007) | new work (FIRE-014) | deferred, mirrors P0.1 | new work (CUAS-010); readiness-bound rather than throughput-bound |

No vertical removes a switch, softens a gate threshold, or bypasses a loop stage. Environmental difficulty raises re-entry stage; it never lowers the pass bar.

## Shared derived requirements

Requirements that multiple verticals generated independently. Owning them once prevents four divergent solutions to one problem. All rows Status = engineering target.

| ID | Requirement | Subsumes | Shared instrument |
| --- | --- | --- | --- |
| SHARED-001 | GNSS-independent terminal relative navigation for every non-Lighthouse environment. Anchor result: the 180 mm funnel is sized for mm-grade relative positioning. Trade (vision/UWB/IR beacon) open and common — whichever modality wins is inherited, not re-derived | AGR-003, ENG-002, FIRE-007, TOY-001/002, CUAS-009 | `degraded-sensor-sweep`: capture success vs positioning noise, mm through toy-grade and GNSS/RTK-grade cm |
| SHARED-002 | Outdoor wind envelope: a scaled carrier that station-keeps and captures in real wind. The 4.5 m P0 article is unflyable outdoors above light breeze; this is a scaling milestone with its own envelope, propulsion, and gate ladder — none funded | AGR-001/002, ENG-003/004, FIRE-003, CUAS-003 | `outdoor-gust-sweep`: capture-collapse wind level; wildfire extends with convective spectra |
| SHARED-003 | Dock cost-down via toy-volume injection molding of funnel/keeper (10⁴–10⁵ units); tooling, unit cost, and cycle-life statistics feed every other vertical | TOY-011, with TOY-003/012 as inputs | funnel-size-vs-noise curve from `degraded-sensor-sweep` before any tooling spend |
| SHARED-004 | Docked contact recharge with turnaround ≤ sortie-sustaining time; P0 defers charging, but no persistent vertical closes without it | AGR-005/006, ENG-007, FIRE-014, CUAS-010 | charge/contact-fault overlays on `sil-p0b`; sortie-cycle Monte Carlo extending `sil-p0d` |
| SHARED-005 | Multi-day helium retention and field logistics: top-up interval and lift loss compatible with each vertical's deployment model | AGR-010, ENG-005/009, FIRE-009, TOY-006/007 | deterministic leakage/ballast bookkeeping model; no test article to calibrate against yet |
| SHARED-006\* | Onboard mission and terminal autonomy sufficient that one radio channel supervises many airborne aircraft, not one continuous link per aircraft. Anchor result: in the fleet-throughput model, radio is the tightest resource that scales one-for-one with airborne count — a continuous-link fleet needs 10 radios for 200 airborne where a lightly-supervised one needs 1–2 — and it is the ceiling that battery-swap or any other throughput fix runs into next | FIRE-011/012, CUAS-008/012 (readiness and lost-link rows each vertical wrote separately, without naming the shared radio-budget cause) | [`aiur.sim.fleet`](../fleet-throughput.md): `size_for_airborne`/`size_carrier` report `radio_channels` and flag it in `taut_constraints`; `--scouts` shows a video-heavy scout wing eating the budget a supervisory-link recovery fleet needs |

\* SHARED-006 has different provenance from SHARED-001…005 above, and the
difference matters. The first five bubbled up bottom-up: independent
verticals hit the same wall and this table exists to own it once. SHARED-006
runs top-down, from a fleet-scale finding no vertical has reached the scale
to hit yet — no vertical has flown enough aircraft at once to feel a radio
ceiling. It is included here anyway because the fleet model states it as a
hard, falling-out-of-arithmetic constraint (every airborne aircraft draws a
link; links do not amortise the way capture heads do — see the
[fleet-throughput verdict](../fleet-throughput.md#the-verdict-recovery-is-the-easy-part-to-scale)),
not because a vertical asked for it. Treat it as a requirement to design for
before any vertical scales past a handful of aircraft, not as evidence of
present demand.

## Program sequencing

Honest ordering. Later steps are gated, not scheduled.

1. **CARRIER-P0 (funded, indoor).** Gates P0-A…D; SIL mirrors `sil-p0b`/`sil-p0c`/`sil-p0d`. Nothing in any vertical advances until repeated autonomous recovery is boring. A toy of a mechanism that has not worked once is concept art.
2. **Toys/STEM kit (first unfunded candidate).** Shares the indoor envelope — no wind milestone required. STEM tier keeps Lighthouse, so it inherits P0 hardware nearly unchanged. Gate to enter: P0-C closed. Gate to tool: `degraded-sensor-sweep` funnel-size curve at TOY-002 noise plus a closing mass/lift model at ≤2 m scale (TOY-004/005). Pays SHARED-003 back to the whole program.
3. **Wind-envelope scaling milestone (SHARED-002, unfunded).** The single gate in front of every outdoor vertical. `outdoor-gust-sweep` produces the capture-collapse wind level before any outdoor envelope is bought; `degraded-sensor-sweep` bounds SHARED-001 accuracy for the candidate sensor. If the collapse level lands below routine outdoor winds, all four outdoor verticals die together — cheaply, in the twin.
4. **Outdoor verticals, in order of non-engineering friction.** Agriculture first (fewest external approvals; killed or kept by SHARED-002 plus an economics model that does not yet exist). Energy behind HAZLOC resolution (ENG-012/ENG-001). Wildfire behind agency airspace integration (FIRE-001). The latter two have prerequisite approvals that no amount of engineering evidence substitutes for. Counter-UAS sits behind the hardest approval of the four — a large LTA vehicle station-keeping over a populated site, often near an airport (CUAS-001) — and behind a commercial question the other verticals do not face: whether a sensing-only product sells at all against a fielded aerostat incumbent. That question should be answered by talking to buyers, not by engineering, and answered before any of this is funded.

## Portfolio risk table

Top killer per vertical, from the studies. Each is a kill criterion, not a caveat.

| Vertical | Killer risk |
| --- | --- |
| Agriculture | Outdoor wind tolerance: if the `outdoor-gust-sweep` capture-collapse wind level lands below typical daytime agricultural winds, the vertical dies; economics vs a $2k quadcopter flown 20 min/day is the second, unmodeled killer |
| Energy | Ignition-source certification: no identified HAZLOC route for a free-flying electric aircraft in a Class I area; the ENG-001 standoff mitigation directly conflicts with the close-approach sensing mission |
| Wildfire | Airspace deconfliction inside fire TFRs: an uncoordinated drone grounds all air attack; if air-attack integration (FIRE-001) is never granted, the vertical does not exist |
| Counter-UAS | Buying the picture alone: procurement is written around detect-*and-defeat*, and this study specifies no effector — so it may be a component sale into someone else's system. Tethered aerostats with surveillance radar are the fielded incumbent; the sole differentiator is the close-look sortie cycle |
| Toys | Positioning cost: terminal nav at ≤$10 BOM, where toy-grade cm noise forces a funnel a ≤2 m envelope may not be able to carry; helium retention over shelf weeks is the second killer |

Portfolio-level observation: SHARED-001 appears in every vertical's top-five risks and SHARED-002 in every outdoor one. The two twin campaigns that resolve them — `degraded-sensor-sweep` and `outdoor-gust-sweep` — are the highest-leverage unfunded work in the program. SHARED-006 appears in no vertical's risk table today, for the reason given at the table above: none has flown enough aircraft to hit it. That absence is not evidence it is low-priority — it is evidence every vertical's risk table was written at single-digit fleet sizes, and none of them has reasoned about what their own scaling story costs in radios.
