# Dual-use verticals

Status: exploratory concept studies — no funded milestone in this directory. CARRIER-P0 remains the only funded article. Every number in these studies is an engineering target or an open question routed to the digital twin.

Studies:

- [Agriculture](agriculture.md) — crop scouting, ranch patrol (AGR-001…011)
- [Energy infrastructure](energy.md) — methane LDAR, remote-site relay (ENG-001…012)
- [Wildfire response support](wildfire.md) — night perimeter watch, crew safety relay (FIRE-001…014)
- [Consumer toy / STEM](toys.md) — mothership playset, dock cost-down driver (TOY-001…014)

Scope is strictly civilian. Support/ISR-style roles (mapping, monitoring, relay) only.

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

Verticals differ in payload, environment, and ops concept — sensor vs relay vs curriculum, still lab air vs gusts vs smoke, engineer vs LDAR tech vs child. A vertical study is a parameter overlay on the core, never a fork of it.

## Commonality matrix

| Core capability | Agriculture | Energy | Wildfire | Toys |
| --- | --- | --- | --- | --- |
| Dock mechanism (funnel/probe/collet/keeper) | identical + environmental hardening (AGR-009) | identical + environmental hardening | new work: resized for 100–500 g aircraft class (FIRE) | parameter change: rescaled funnel, molded (TOY-003/004/011) |
| Capture-truth semantics (`S1 AND S2`) | identical | identical | identical | identical |
| Terminal guidance + safety supervisor | semantics identical; sensor new work (SHARED-001) | semantics identical + geofence extension (ENG-001); sensor new work | semantics identical + clearance/lost-link extension (FIRE-001/012); sensor new work | identical at kit tier (Lighthouse); sensor new work at toy tier (TOY-001) |
| Evidence/promotion contract | identical | identical | identical | identical (kit sessions emit the same run-record shape) |
| Twin gate scenarios (`sil-p0b`/`sil-p0c`/`sil-p0d`) | parameter overlays | overlays + new geofence SIL scenario | overlays + new deconfliction/lost-link SIL scenario | overlays with toy geometry; `sil-p0d` out of scope for one-drone SKU |
| Energy/recharge cycle (deferred in P0) | new work (AGR-005/006) | new work (ENG-007) | new work (FIRE-014) | deferred, mirrors P0.1 |

No vertical removes a switch, softens a gate threshold, or bypasses a loop stage. Environmental difficulty raises re-entry stage; it never lowers the pass bar.

## Shared derived requirements

Requirements that multiple verticals generated independently. Owning them once prevents four divergent solutions to one problem. All rows Status = engineering target.

| ID | Requirement | Subsumes | Shared instrument |
| --- | --- | --- | --- |
| SHARED-001 | GNSS-independent terminal relative navigation for every non-Lighthouse environment. Anchor result: the 180 mm funnel is sized for mm-grade relative positioning. Trade (vision/UWB/IR beacon) open and common — whichever modality wins is inherited, not re-derived | AGR-003, ENG-002, FIRE-007, TOY-001/002 | `degraded-sensor-sweep`: capture success vs positioning noise, mm through toy-grade and GNSS/RTK-grade cm |
| SHARED-002 | Outdoor wind envelope: a scaled carrier that station-keeps and captures in real wind. The 4.5 m P0 article is unflyable outdoors above light breeze; this is a scaling milestone with its own envelope, propulsion, and gate ladder — none funded | AGR-001/002, ENG-003/004, FIRE-003 | `outdoor-gust-sweep`: capture-collapse wind level; wildfire extends with convective spectra |
| SHARED-003 | Dock cost-down via toy-volume injection molding of funnel/keeper (10⁴–10⁵ units); tooling, unit cost, and cycle-life statistics feed every other vertical | TOY-011, with TOY-003/012 as inputs | funnel-size-vs-noise curve from `degraded-sensor-sweep` before any tooling spend |
| SHARED-004 | Docked contact recharge with turnaround ≤ sortie-sustaining time; P0 defers charging, but no persistent vertical closes without it | AGR-005/006, ENG-007, FIRE-014 | charge/contact-fault overlays on `sil-p0b`; sortie-cycle Monte Carlo extending `sil-p0d` |
| SHARED-005 | Multi-day helium retention and field logistics: top-up interval and lift loss compatible with each vertical's deployment model | AGR-010, ENG-005/009, FIRE-009, TOY-006/007 | deterministic leakage/ballast bookkeeping model; no test article to calibrate against yet |

## Program sequencing

Honest ordering. Later steps are gated, not scheduled.

1. **CARRIER-P0 (funded, indoor).** Gates P0-A…D; SIL mirrors `sil-p0b`/`sil-p0c`/`sil-p0d`. Nothing in any vertical advances until repeated autonomous recovery is boring. A toy of a mechanism that has not worked once is concept art.
2. **Toys/STEM kit (first unfunded candidate).** Shares the indoor envelope — no wind milestone required. STEM tier keeps Lighthouse, so it inherits P0 hardware nearly unchanged. Gate to enter: P0-C closed. Gate to tool: `degraded-sensor-sweep` funnel-size curve at TOY-002 noise plus a closing mass/lift model at ≤2 m scale (TOY-004/005). Pays SHARED-003 back to the whole program.
3. **Wind-envelope scaling milestone (SHARED-002, unfunded).** The single gate in front of every outdoor vertical. `outdoor-gust-sweep` produces the capture-collapse wind level before any outdoor envelope is bought; `degraded-sensor-sweep` bounds SHARED-001 accuracy for the candidate sensor. If the collapse level lands below routine outdoor winds, all three outdoor verticals die together — cheaply, in the twin.
4. **Outdoor verticals, in order of non-engineering friction.** Agriculture first (fewest external approvals; killed or kept by SHARED-002 plus an economics model that does not yet exist). Energy behind HAZLOC resolution (ENG-012/ENG-001). Wildfire behind agency airspace integration (FIRE-001). The latter two have prerequisite approvals that no amount of engineering evidence substitutes for.

## Portfolio risk table

Top killer per vertical, from the studies. Each is a kill criterion, not a caveat.

| Vertical | Killer risk |
| --- | --- |
| Agriculture | Outdoor wind tolerance: if the `outdoor-gust-sweep` capture-collapse wind level lands below typical daytime agricultural winds, the vertical dies; economics vs a $2k quadcopter flown 20 min/day is the second, unmodeled killer |
| Energy | Ignition-source certification: no identified HAZLOC route for a free-flying electric aircraft in a Class I area; the ENG-001 standoff mitigation directly conflicts with the close-approach sensing mission |
| Wildfire | Airspace deconfliction inside fire TFRs: an uncoordinated drone grounds all air attack; if air-attack integration (FIRE-001) is never granted, the vertical does not exist |
| Toys | Positioning cost: terminal nav at ≤$10 BOM, where toy-grade cm noise forces a funnel a ≤2 m envelope may not be able to carry; helium retention over shelf weeks is the second killer |

Portfolio-level observation: SHARED-001 appears in every vertical's top-five risks and SHARED-002 in every outdoor one. The two twin campaigns that resolve them — `degraded-sensor-sweep` and `outdoor-gust-sweep` — are the highest-leverage unfunded work in the program.
