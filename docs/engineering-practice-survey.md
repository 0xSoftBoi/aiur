# How established hardware organizations do this

Status: research survey, 2026-08-08. Sources are cited where verified;
practices are industry description, not aiur commitments.

Seven domains surveyed: aerospace SE, automotive, consumer hardware, space
mechanisms, electronics, safety, and the hardware-rich school. Industry claims
resolve to cited sources or are marked name-only; aiur assessments are opinion.

## The short version

Every surveyed industry runs the same shape under different names: a staged
fidelity ladder (model → real code → real processor → real hardware →
flight-like environment → fleet) with promotion gated on evidence, not demos.
Models earn authority only through scored credibility and correlation against
measurement — NASA-STD-7009B forces disclosure of validation level and
uncertainty. Fault injection is first-class and repeated at every level,
physically on the bench, not only in simulation. Mechanisms and electrical
people trust nothing without factored force margins, derived life tests, and
worst-case stress inside derated limits. Safety people accept no residual risk
anonymously and treat every independence claim as unproven until a
common-cause analysis says otherwise. Where articles are cheap, the
hardware-rich school (SpaceX, Anduril, Zipline) inverts the emphasis: build
and break instrumented hardware fast, and let simulation decide what to test
next. Verdict on aiur: the cultural spine — evidence-gated promotion, a
deterministic twin running the real controller, fault quotas with absolute
safety zeros, a provenance-tracked calibration ledger — is unusually strong
for a pre-alpha program. What is missing is the physical half of each practice
(bench fault insertion, loaded releases, force margins, harness workmanship),
a few cheap formalizations (signed hazard log, closure matrix, credibility
scoring) — and, per the iteration school, the hardware itself: zero P0-A
cycles have run while SIL gates close in CI.

## The fidelity ladder everywhere

Three industries independently converged on the same ladder. NASA hangs it on
the V-model: life-cycle reviews with published entrance/success criteria
(NPR 7123.1D Appendix G: PDR, CDR, TRR, FRR and 17 more) and a
qualification/acceptance split with codified margins (GSFC-STD-7000A GEVS:
qual = max expected + 3 dB, thermal ±10 °C beyond flight). Automotive runs
MIL → SIL → PIL → HIL, reusing test vectors up the ladder, with back-to-back
equivalence rated highly recommended for ASIL C/D by ISO 26262-6. Consumer
hardware runs EVT → DVT → PVT at the contract manufacturer, each build
answering one question (design / tools / line yield). TRL vocabulary
(NPR 7123.1D Appendix E) names the rungs: laboratory (TRL 4), relevant
(TRL 5-6), operational (TRL 7+) environment.

| Rung | NASA/space | Automotive | Consumer hw | aiur today |
| --- | --- | --- | --- | --- |
| Model only | analysis/M&S under NASA-STD-7009B | MIL | works-like prototype + sim | twin campaigns, SIL-B in CI |
| Real code, simulated plant | FSW in sim | SIL | — | real `DockController` + `TerminalGuidance` in the twin |
| Real processor | — | PIL (back-to-back vs SIL) | EP build | none — firmware port has no defined rung |
| Real electrical hardware | qualification test (GEVS) | HIL + fault-insertion unit | EVT | P0-A bench (defined, not yet run) |
| Flight-like environment | protoflight, test-like-you-fly | in-vehicle calibration (XCP/A2L) | DVT | P0-B suspended rig, P0-C tethered carrier |
| Fleet / production | per-article acceptance | 24/7 HIL regression | PVT, AQL lots, ORT | P0-D sequencing; no per-article acceptance |

Mapped to TRL: P0-A is TRL 4, P0-B approaches TRL 5, P0-C is the TRL 6
relevant-environment demonstration. Two rungs are absent rather than merely
unexecuted: PIL (nothing proves the eventual MCU port behaves like the Python
that earned the SIL evidence) and per-article acceptance (nothing says dock #2
is the dock the evidence was earned on) — the classic escape routes for bugs
that campaign statistics launder.

## Model credibility

NASA-STD-7009B (2024) is the standard written for exactly the authority aiur's
twin claims — models informing program decisions. It scores eleven capability
and results factors 0-4 (data pedigree, verification, validation, input
pedigree, uncertainty characterization, robustness, reviews, process), with
the validation ladder keyed to referent quality: level 1 is conceptually
validated only; level 3 requires measurements of the real system spanning the
operational domain. It sets no pass thresholds — it forces disclosure so the
decision maker, not the analyst, weighs the simulation; [M&S 31]-[M&S 34]
oblige every result set to carry an uncertainty estimate (or an explicit
statement that none exists) and warnings whenever assumptions were violated.
The same pre-declared-correlation pattern governs structural models
(NASA-STD-5002: modal frequencies within 5%, cross-orthogonality >0.9;
MIL-STD-1540C: 3%/0.95), and automotive HIL labs refuse a plant model until
correlated against test-bench measurement (dSPACE ASM ships the workflow).

Aiur already has the substance most programs lack: the calibration ledger's
provenance states are a data-pedigree system, the replay contract with
pre-declared tolerances and `FAIL_MODEL` disposition is a genuine validation
plan, and running the real controller un-mocked is strong verification. What
7009B adds is the forced statement: today the twin's validation factor is
level 1 — zero empirical referent points — and no SIL report says so in a
structured way. Campaign reports also emit point estimates (100%, ~90%, ~63%)
with no confidence intervals, though seeded Monte Carlo makes binomial (Wilson)
intervals free, and a 30-episode bin's interval is wide enough to move
conclusions near a ≥95% gate threshold. A scored credibility block per report,
re-scored after each hardware gate, makes the docs' honest prose impossible to
forget at decision time.

Test Like You Fly practice (Aerospace TOR-2010(8591)-6) adds the mirror-image
ledger: enumerate what each *test article* fails to reproduce about flight,
each gap a criticality-analyzed exception, never a silent waiver. The twin's
known-missing-physics list is the model-side version; the hardware-side list —
the bench omits dock compliance and motion coupling, the rig omits hull
downwash and the trim transient known to exceed the 0.3 N vertical thrust
budget — is not written anywhere.

## Mechanisms practice

Space mechanisms run on two quantitative disciplines aiur has not adopted.
First, factored force/torque margins: AIAA S-114A-2020 ("Moving Mechanical
Assemblies for Space and Launch Vehicles") requires ≥100% test-verified margin
(drive ≥ 2× worst-case resistance); NASA-STD-5017B applies maturity-graded
factors (3.0 on friction from analysis, 2.0 once measured) under worst-case
temperature, voltage, and tolerance combinations, and explicitly prohibits
analysis-only verification; ECSS-E-ST-33-01C Rev.2 demands a 2× motorization
factor. Second, derived life testing: life cycles = (all operational + all
ground/test/installation cycles) × 2.0-4.0, preceded by a ≥15-cycle run-in
whose per-cycle metrics must level off, followed by teardown — increasingly
extended to run-to-failure on a spare to learn the wear-out mode. Status
sensing follows hard-won rules: sense the latch element itself, not the
drivetrain (written after Voyager/DMSP microswitch failures and Magellan's
misadjusted latch switch), and indicators never double as end stops. The
closest flight analog to aiur's dock, the NASA Docking System capture latch,
demonstrated release *while loaded* to maximum expected load — and both of
that program's major failures surfaced in test (free play, wear, galling),
not analysis.

Concrete verdict on P0-A: the 5 N axial / 1 N lateral holds are holding-load
screens, not margin demonstrations — nothing shows the keeper servo has 2× the
force needed to close or emergency-open against a side-loaded probe at minimum
battery voltage. The 50-cycle count is a round number at run-in scale;
counting every capture/release through P0-D and applying the ×2 factor implies
a 400-600-cycle life test, an afternoon on a printed article. All 10 emergency
releases are unloaded — the case latch practice says proves nothing, since
loaded release is where galling lives. And the capture chain (Ø16 throat, Ø12
head, Ø3 neck, S1 trip point) has nominal dimensions only, on FDM parts with
±0.2-0.5 mm typical variation — up to 15% of the probe neck. Aiur's strengths
are real: dual independent switches with S2 sensing the keeper itself, and
finding #5 independently rediscovered the direct/indirect distinction —
industry would promote the Rev-B keeper-discrimination candidate to a gated
requirement.

## Electrical practice

High-reliability electronics gates power-on on analysis and checklists:
worst-case circuit analysis (Aerospace TOR-2012(8960)-4 Rev A —
extreme-value/RSS/Monte Carlo over tolerance, temperature, aging) showing every
part inside published derating limits (NAVSEA SD-18, ECSS-Q-ST-30-11C Rev.2,
NASA EEE-INST-002); rail-by-rail first power on current-limited supplies
against a pre-written expected-current table (NVIDIA ships a literal Jetson
checklist); SPICE treated as first-order because vendor macromodels capture
50-75% of datasheet behavior — the datasheet wins. Field
data concentrates reliability effort on interconnect: intermittent
connector/harness failures under vibration dominate avionics no-fault-found
removals, answered by workmanship standards (NASA-STD-8739.4A, IPC/WHMA-A-620),
not analysis. Environmental screening is tailored (MIL-STD-810H): measure your
own platform's vibration, then screen against it before flight. Battery
practice is procedural: UN 38.3-tested cells, IEC 62133-2 packs, written
charge/storage/log SOPs.

Dock harness implications, in order of exposure. S1/S2 carry no
contact-material or minimum-current requirement; below the wetting threshold,
silver-alloy contacts oxidize and fail intermittently weeks after working —
the real-world delayed-onset mechanism behind the twin's stuck-switch fault,
the one finding #2 says defeats both interlocks. The fix is a BOM line:
gold-contact variants plus pull-ups sized to datasheet minimum contact current.
Second, the XL330's ~1.5 A stall shares a bench with the controller reading
S1/S2; servo inrush collapsing a shared 5 V rail resets the controller while a
multimeter still reads 5.00 V, and a reset during LOCKING silently destroys the
latched capture-enable finding #1 proved necessary — neither the scope
measurement nor the fault exists yet. Third, the harness, crimps, and switch
brackets see their first-ever vibration on the flying airship at P0-C —
backwards from 810H doctrine; a half-page A-620-informed harness rule plus a
shake screen against a PSD measured on the P0-B rig closes it. Fourth, an EMI
self-compatibility A/B check (Crazyradio packet loss and Lighthouse validity,
servo cycling vs idle) tests whether the dock causes the pose dropouts the twin
injects as exogenous. Aiur's dual-contact decode already converts
intermittents into detected faults — but detection is not prevention.

## Safety practice

MIL-STD-882E tracks every hazard on a severity × probability matrix and — the
load-bearing mechanism — never accepts residual risk anonymously: acceptance
authority scales with risk level, with signature, date, and scope. NASA states
fault tolerance as a policy sentence (NPR 8705.2: catastrophic hazards get
two-failure tolerance), and its own waiver logic concedes the reason redundancy
fails: common cause. Completeness comes from paired FMECA (bottom-up,
MIL-STD-1629A lineage) and FTA (top-down, NASA Fault Tree Handbook) so the
fault campaign covers an enumerated space, not a curated list. SAE ARP4761A
makes independence a claim requiring verification — zonal, particular-risk, and
common-mode analysis — because measured common-cause fractions (beta 0.01-0.25;
11% of shuttle in-flight anomalies) make redundant channels 10-100× worse than
the multiplied-probabilities math promises. Range safety holds the termination
path to *higher* assurance than the vehicle: RCC 319-25 requires 0.999
reliability at 95% confidence, independence from every other vehicle system,
dedicated power, and injected-fault testing of the fail-safe logic; abort
authority is a named role independent of the test team (NPR 8715.5B).
Post-G650 flight-test practice adds run-level artifacts: test cards with
attached hazard analyses, pre-briefed abort phraseology with a named caller,
dress rehearsals, and grey-beard boards accepting elevated risk.

The twin's double-fault finding (#5) is the textbook common-cause case:
everything downstream of the single Lighthouse source is correlated, so no
supervisor on the same measurements can tell. Industry framing sharpens it
three ways. The finding was found by accident — one-fault-per-episode Monte
Carlo structurally cannot search for correlated doubles; an FTA on "capture
confirmed with no aircraft retained" enumerates whether other two-event cut
sets remain, and a common-mode analysis (same switch lot, shared harness,
shared debounce code, shared MCU, single nav source) tells `faults.py` which
correlated pairs to draw. The Rev-B keeper-discrimination sensor becomes a
justified diversity defense — the fix shuttle data ranks highest-leverage —
not a candidate. And the residual needs a signature: "documented residual
accepted" becomes "accepted by <role> on <date> for the single-fault indoor P0
regime only," forcing re-acceptance when scope changes. On execution, the
campaign stop rules say when to stop, not who calls it with what word within
what reaction time, and nothing verifies the kill path works with the autonomy
computer dead. For the verticals, SORA 2.5 / Part 107 waiver cases reward
exactly the quantified hazard-mitigation-evidence pairs the loop produces.

## The hardware-rich school

SpaceX's stated process is five steps in strict order — make requirements less
dumb, delete the part, simplify, accelerate, automate — warning that the most
common error is optimizing something that should not exist, backed by a
production cadence that makes destroyed articles cheap data. Kelly Johnson's
Rule 9 says the designer must test the product in the initial stages or
"rapidly loses his competency to design"; Rules 5 and 10 (thorough records,
explicit non-compliance lists) are close to aiur's existing culture. Anduril
designs for producibility from day one and iterates test infrastructure at
product cadence; Zipline pairs hundreds of thousands of sim edge-case tests
with tens of thousands of physical flights; PX4/ArduPilot made SITL-in-CI the
default with HITL on real silicon before flight; Skydio inserts logged-data
replay between sim and flight. The school's boundary condition — iterate where
articles are cheap, analyze where failure is expensive (the Bloomberg critique
of Starship) — endorses aiur's gate ladder gradient.

Where the reports disagree: the aerospace/automotive/safety domains prescribe
more analysis artifacts; the iteration school says aiur is already
analysis-heavy at its cheapest, safest tier — SIL gates close in CI while the
twin's own missing-physics list names phenomena only hardware can measure. The
tension is mostly false: the recommended artifacts are hours-to-days of paper
that plug into existing machinery, and none gate printing a funnel this week.
For a $3k carrier and $500 drones the split is: fly-first below the envelope —
print Rev-A now, cycle it, print 3-5 competing funnel/probe/spring variants
and let the bench kill four — and sim-first at the envelope boundary, where a
strike ends the program's only funded flight article and its safety
credibility. Two school-specific additions: a deletion review before Rev-B
adds keeper sensing (does the spring collet earn its place beside a positive
keeper? could one discriminating sensor replace S2 and the Rev-B addition?),
and instrumenting the loop's own requirement-to-evidence-packet latency, since
by aiur's own rule what is unmeasured does not exist.

## Adoption table

Ordered by leverage; "What aiur has" is this survey's assessment.

| Practice | Source discipline | What aiur has | Adopt? | Effort |
| --- | --- | --- | --- | --- |
| Build P0-A bench hardware now; print 3-5 competing dock geometry variants in parallel with sim work | iterative-hw (Skunk Works R9, Starship, Zipline) | twin + evidence machinery ready; zero hardware cycles run | yes | days |
| Upgrade P0-A: loaded emergency releases (5 N applied), factored force-margin budget for keeper at Vmin, derive cycle count as ×2 life test with 15-cycle run-in trending, then run Rev-A to failure | mechanisms (AIAA S-114A-2020, NASA-STD-5017B, NDS latch) | unloaded releases, holding screens, arbitrary 50 cycles | yes | days |
| Bench fault-insertion relay board on S1/S2/servo lines + per-gate hardware fault quotas, each fault paired with a written expected-safe-response requirement | automotive (ISO 26262, dSPACE/NI/Vector FIU) | SIL-only fault quotas | yes | days |
| Hazard log: ~10 hazards on a severity × probability matrix, every residual signed with name, date, scope — starting with the double fault | safety (MIL-STD-882E) | findings + risk-register prose, anonymous acceptance | yes | hours |
| Dock FMECA + FTA on the two catastrophic top events + common-mode analysis of the capture chain; add correlated-pair fault episodes to the sim | safety (MIL-STD-1629A, NASA FTA handbook, ARP4761A) | curated fault menu, one double fault found by accident | yes | days |
| Machine-checked requirement closure matrix (VCRM/DVP&R): every shall → method, stage, closing run_id, open/closed status, evaluated in CI | aero-se (NASA/SP-2016-6105, ECSS-E-ST-10-02C Rev.1) + automotive DVP&R | five-field schema, gate evaluator, no closure index | yes | days |
| Credibility + uncertainty block per SIL report (NASA-STD-7009B factors, binomial CIs) and a TLYF exception ledger per hardware article | aero-se (NASA-STD-7009B, TOR-2010(8591)-6) | prose caveats, calibration ledger, model-side gap list only | yes | days |
| Electrical evidence packet: WCCA-lite derating table, gold-contact S1/S2 variants, scoped rail transient + reset-during-LOCKING fault in sim, A-620-informed harness rules | electrical (SD-18, TOR-2012(8960)-4 Rev A, NASA-STD-8739.4A) | vendor specs cited, DC meter checks, jumper-grade harness | yes | days |
| Battery SOP: UN 38.3 summaries filed, charge/storage/containment/retirement rules, pack ID + cycle count in promotion telemetry | electrical (UN 38.3, IEC 62133-2) | one sentence | yes | hours |
| Kill-path independence: dedicated power, demonstrated function with autonomy computer off, pre-session end-to-end check, injected-fault exercise | range safety (RCC 319-25, NPR 8715.5B) | architecture statement, healthy-path releases only | yes | days |
| Run-level test cards with mini-THA, pre-briefed abort phraseology ("abort" vs "kill") with named caller, emergency-procedure dress rehearsal, short TRR with an independent reviewer before P0-B/C/D | flight test (FTSC post-G650), aero-se (NPR 7123.1D TRR) | campaign-level stop rules only | yes | days |
| Tolerance stack of the capture chain + as-built caliper dims per printed article + golden-article freeze on P0-A pass | mechanisms (ASME Y14.5-2018) + consumer-hw (golden sample) | nominal CAD, config identity, single-article assumption | yes | hours |
| Deletion review of the dock before Rev-B adds sensing (collet vs keeper, S1/S2 vs one discriminating sensor) | iterative-hw (Musk step 2, Anduril "no part") | findings ratchet only adds mechanism | yes | hours |
| PIL rung: freeze twin episode vectors now; require signal-level back-to-back equivalence from the future MCU port before it earns bench time | automotive (ISO 26262-6), PX4/ArduPilot HITL | real code in sim, Python only | later | weeks |
| DFM/moldability review, should-cost per BOM line, EVT/DVT framing; tailored vibration screen against measured P0-B PSD before P0-C | consumer-hw, MIL-STD-810H | printed articles, BOM without cost, rigid bench only | later | days |
| Full NPR 7123.1D review ladder; AQL lot sampling; qualification/acceptance split | aero-se, consumer-hw | gate ladder covers the need at this scale | no | — |

The "no" row is a scale judgment: a delta-CDR before Rev-B fab and the TRR
checklist suffice; AQL and the qual/acceptance split wait for multiple docks.

## Sources

All URLs below were fetched or returned by search on 2026-08-08.
Aerospace SE:
- NASA-STD-7009B, Standard for Models and Simulations — https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf
- NPR 7123.1D Appendix G (review criteria) and Appendix E (TRL) — https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixG and https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixE
- NASA/SP-2016-6105 Rev 2, NASA Systems Engineering Handbook — https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf
- Aerospace TOR-2010(8591)-6, Test Like You Fly — https://s3vi.ndc.nasa.gov/ssri-kb/static/resources/TOR-20108591-6-Test-Like-You-Fly-Assessment-and-Implementation-Process.pdf
- GSFC-STD-7000A (GEVS) — https://explorers.larc.nasa.gov/2019APSMEX/MO/pdf_files/gsfc-std-7000a_final_3-28-18.pdf
- ECSS-E-ST-10-02C Rev.1, Verification — https://ecss.nl/standard/ecss-e-st-10-02c-rev-1-verification-1-february-2018/

Automotive:
- MathWorks, SIL/PIL/HIL tests and back-to-back equivalence — https://www.mathworks.com/help/sltest/sil-pil-and-hil-tests.html and https://www.mathworks.com/help/sltest/ug/back-to-back-equivalence-testing.html
- NI, fault insertion units for electronic testing — https://www.ni.com/en/solutions/transportation/hardware-in-the-loop/using-fault-insertion-units--fius--for-electronic-testing.html
- dSPACE, HIL testing and Automotive Simulation Models — https://www.dspace.com/en/inc/home/applicationfields/foo/hil-testing.cfm and https://www.dspace.com/en/pub/home/products/sw/automotive_simulation_models.cfm
- Vector vCDM — https://www.vector.com/int/en/products/products-a-z/software/vcdm/
- Quality-One, DVP&R and AIAG & VDA FMEA — https://quality-one.com/dvpr/ and https://quality-one.com/aiag-vda-fmea/
- HEICON, ISO 26262 fault injection — https://heicon-ulm.de/en/iso26262-fault-injection-test-do-you-really-need-it/

Consumer hardware:
- Instrumental, EVT/DVT/PVT stage gates — https://instrumental.com/build-better-handbook/evt-dvt-pvt
- Bolt, Illustrated Guide to Product Development and Juicero teardown — https://blog.bolt.io/engineering/ and https://blog.bolt.io/juicero/
- Super Ingenuity, injection mold development process — https://super-ingenuity.cn/injection-mold-development-process/
- Sofeast / China Manufacturing Decoded, tooling timelines — https://chinamanufacturingdecoded.podbean.com/e/8-to-12-weeks-injection-mold-tooling-timelines-exposed/
- Insight Quality, golden samples — https://insight-quality.com/what-is-a-golden-sample/
- ESPEC, HALT/HASS — https://espec.com/na/chamber_faq/answer/halt_hass_testing
- Accendo Reliability, ongoing reliability testing — https://accendoreliability.com/introduction-ongoing-reliability-testing/
- ASQ, ANSI/ASQ Z1.4 & Z1.9 — https://asq.org/quality-resources/z14-z19

Mechanisms:
- Postma, force/torque margins (37th AMS) and Dick et al., NDS capture latch (44th AMS) — https://esmats.eu/amspapers/pastpapers/pdfs/2004/postma.pdf and https://esmats.eu/amspapers/pastpapers/pdfs/2018/dick.pdf
- NASA-STD-5017B (final draft, NTRS) — https://ntrs.nasa.gov/api/citations/20220014671/downloads/NASA-STD-5017B%20Final%20Draft%20for%20EMB%20for%20Export%20Control%20review.pdf
- ECSS-E-ST-33-01C Rev.2, Mechanisms — https://ecss.nl/wp-content/uploads/2019/05/ECSS-E-ST-33-01C-Rev.2(1March2019).pdf
- NASA mechanisms lessons-learned and GRC Space Mechanisms Project — https://ntrs.nasa.gov/api/citations/20050192114/downloads/20050192114.pdf and https://www1.grc.nasa.gov/research-and-engineering/space-mechanisms-project/
- SAE tolerance-stack course (ASME Y14.5) — https://saemobilus.sae.org/courses/critical-concepts-tolerance-stacks-asme-y145-1994-2009-2018-advanced-level-et2111
- NASA X-59 GVT methodology (NASA-STD-5002 / MIL-STD-1540C correlation criteria) — https://ntrs.nasa.gov/api/citations/20200000416/downloads/20200000416.pdf
- GSFC duplex-bearing life test to failure, 43rd AMS — https://ntrs.nasa.gov/api/citations/20160008122/downloads/20160008122.pdf

Electrical:
- WCCA overview and NASA-STD-8739.4A workmanship (NASA S3VI) — https://s3vi.ndc.nasa.gov/ssri-kb/static/resources/wcca.pdf and https://s3vi.ndc.nasa.gov/ssri-kb/static/resources/nasa-std-8739.4a.pdf
- NAVSEA SD-18 (NSWC Crane) — https://www.navsea.navy.mil/Home/Warfare-Centers/NSWC-Crane/Resources/SD-18/
- Analog Devices RAQ-47, datasheet vs SPICE macromodel — https://www.analog.com/en/analog-dialogue/raqs/raq-issue-47.html
- NVIDIA Jetson bring-up checklists — https://docs.nvidia.com/jetson/archives/r35.6.2/DeveloperGuide/HR/JetsonModuleAdaptationAndBringUp/Checklists.html
- NeuroBytes, servo-induced brownouts — https://hackaday.io/project/3339-neurobytes/log/37589-dealing-with-pesky-servo-induced-brownouts
- Tekbox, spectrum analyzers for EMC testing — https://www.tekbox.com/product/AN_spectrum_analyzers_for_EMC_testing.pdf
- MIL-STD-810H Method 514.8 (CVG Strategy mirror) — https://cvgstrategy.com/wp-content/uploads/2019/08/MIL-STD-810H-Method-514.8-Vibration.pdf
- All About Circuits, switch contact design — https://www.allaboutcircuits.com/textbook/digital/chpt-4/switch-contact-design/
- TÜV SÜD, UN/DOT 38.3 testing — https://www.tuvsud.com/en-us/industries/mobility-and-automotive/automotive-and-oem/automotive-testing-solutions/battery-testing/un-dot-38-3

Safety:
- MIL-STD-882E w/Change 1 — https://safety.army.mil/Portals/0/Documents/ON-DUTY/SYSTEMSAFETY/Standard/MIL-STD-882E-change-1.pdf
- NPR 8705.2B, human-rating requirements — https://nodis3.gsfc.nasa.gov/displayAll.cfm?Internal_ID=N_PR_8705_002B_&page_name=all
- MIL-STD-1629A (everyspec) — https://everyspec.com/MIL-STD/MIL-STD-1600-1699/MIL_STD_1629A_1556/
- SAE ARP4761 overview — https://en.wikipedia.org/wiki/ARP4761
- Jones (NASA Ames), common cause failures and ultra reliability — https://ntrs.nasa.gov/api/citations/20160005837/downloads/20160005837.pdf
- RCC 319-25, flight termination systems — https://www.trmc.osd.mil/wiki/download/attachments/113019893/319-25_FTS_Commonality.pdf
- FTSC, flight test operational guidance — http://www.flighttestsafety.org/images/Flight_Test_Operational_Guidance_v7_FTSC_020717.pdf
- JARUS SORA v2.5 main body — http://jarus-rpas.org/wp-content/uploads/2024/06/SORA-v2.5-Main-Body-Release-JAR_doc_25.pdf

Iterative hardware:
- Everyday Astronaut, Starbase interview (five-step process) — https://everydayastronaut.com/starbase-tour-and-interview-with-elon-musk/
- FutureBlind, Take the Iterative Path — https://futureblind.com/p/take-the-iterative-path
- Lockheed Martin, Kelly's 14 Rules — https://www.lockheedmartin.com/content/dam/lockheed-martin/aero/photo/skunkworks/kellys-14-rules.pdf
- Breaking Defense, Anduril Arsenal-1 production — https://breakingdefense.com/2026/03/as-fury-production-starts-anduril-pledging-a-different-production-approach-at-arsenal-1/
- Zipline, testing program — https://www.zipline.com/newsroom/testing-program-zipline-flight
- ArduPilot, SITL testing — https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html
- IEEE Spectrum (Skydio-authored), neural pilot — https://spectrum.ieee.org/deep-neural-pilot-skydio-2
- Bloomberg Opinion, SpaceX blow-it-up testing critique — https://www.bloomberg.com/opinion/articles/2026-07-15/spacex-s-blow-it-up-testing-won-t-fly-on-starship

Name-only, not independently verified this session (designations as reported):
AIAA S-114A-2020; Aerospace TOR-2012(8960)-4 Rev A; NASA EEE-INST-002
(NASA/TP-2003-212242); ECSS-Q-ST-30-11C Rev.2; IPC/WHMA-A-620; AIAG & VDA FMEA
Handbook (2019); ISO 26262:2018 series; IEC 62133-2:2017; NASA-STD-5002;
MIL-STD-1540C; ASME Y14.5-2018; NASA/TP-1999-206988 (Space Mechanisms
Handbook); NASA Fault Tree Handbook v1.1; NPR 8715.5B; NUREG/CR-5485; FAA
Part 107 waiver application instructions; PX4 SITL/HITL documentation
(docs.px4.io); dSPACE external failure insertion unit.
