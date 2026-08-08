# CARRIER-P0 dock common-mode analysis

Status: analysis only; no article built, no lot procured, no beta measured
Scope: the independence claim behind `capture_confirmed = S1 AND S2`, and every
other place in the recovery interface where two things are being counted as two

`capture_confirmed = S1 AND S2` is not a wiring detail. It is a claim that two
sensors fail for unrelated reasons, and the whole value of the second switch
rests on it. The [dock FMECA](dock-fmeca.md) shows what that claim buys: apart
from the shared firmware path, TOP-2 — capture confirmed with no aircraft
retained — has no single-point failure. Every route to a false confirmation
needs two basic events.

An order-2 cut set is only worth its order if the two events are independent.
This document checks that, and the answer is that they are not: S1 and S2
currently share a part number, a probable lot, a supply rail, a bracket region,
a harness route, a debounce implementation, an MCU, and an operator. Independence
has to be *verified*, not asserted, and where it cannot be verified it has to be
priced.

Companion documents: the [FMECA](dock-fmeca.md) supplies the cut sets;
[electrical-evidence.md](electrical-evidence.md) supplies the physical
separation rules (H5, H6) this analysis assumes and extends; the
[hazard log](hazard-log.md) carries HAZ-001, the mishap this converges on.

## What a common-cause analysis is asked to do

SAE ARP4761 packages independence verification as a Common Cause Analysis with
three constituent parts. The one-line descriptions below are **paraphrases from
a secondary source, not quotations from the standard** — ARP4761/ARP4761A is
SAE-paywalled and was not read for this program, and the same secondary source
is the one cited in the [practice survey](engineering-practice-survey.md). They
are used here for the shape of the method, and nothing in this document is a
compliance claim against ARP4761.

| Analysis | Paraphrased purpose | Scaled to a 180 g dock |
| --- | --- | --- |
| Zonal Safety Analysis (ZSA) | Looks at each compartment and asks what hazards affect every component in it, such as loss of cooling air or a bursting fluid line | The dock **is** one zone. There is no second compartment to separate anything into: one bracket plate, one dust field from the funnel, one vibration path from the servo and the rotors. Anything that fills the zone reaches both switches |
| Particular Risks Analysis (PRA) | Looks for external events that create a hazard, such as a birdstrike or an engine turbine burst | The credible external events indoors: a dropped article or a person bumping the rig between sessions, HVAC airflow, the tether snagging, a mis-mate during a battery or harness change, and the servo's own 1.47 A stall transient propagating into whatever shares its rail |
| Common Mode Analysis (CMA) | Looks at redundant critical components for failure modes that can make all of them fail at about the same time | The subject of the rest of this document: S1 and S2, their pull-up rail, their debounce path, their MCU, and the single navigation source everything downstream of it inherits |

At this scale ZSA and PRA collapse into short observations, which is itself the
finding: a mechanism small enough to hold in one hand has no zonal separation to
analyse, so *every* zonal coupling is present by default and separation has to
be bought deliberately rather than inherited from the airframe layout.

## Coupling factors

NUREG/CR-5485 section 4.1.2 defines the object under analysis, verbatim:

> "A coupling factor is a characteristic of a group of components or piece parts
> that identifies them as susceptible to the same causal mechanisms of failure.
> Such factors include similarity in design, location, environment, mission and
> operational, maintenance, and test procedures."

Its taxonomy has three classes — hardware based (identical physical
characteristics), operation based (identical operational characteristics), and
environment based (identical external or internal environmental
characteristics) — and notes that more than one coupling factor can be assigned
to a single common-cause event. The eight sections below walk the taxonomy over
this dock. Each ends in a verdict, and the verdicts are the input to the beta
argument that follows.

### 1. Same part design

S1 and S2 are the same switch model. The [electrical evidence
packet](electrical-evidence.md) baselines both on the Omron D2F-01 family —
gold alloy, minimum applicable load 1 mA at 5 VDC — because that is the family
whose floor a logic pull-up can actually reach. Both are SPDT snap-action
switches with the same crossbar contact form, the same 0.25 mm contact gap, the
same plunger geometry, and the same failure physics.

**Verdict: coupled.** This is the strongest coupling on the list and the
empirically most important one: in the shuttle data (Rutledge and Mosleh, 64
dependent failures among 473 in-flight anomalies over forty flights after
Challenger), *same part design* was the leading coupling factor at 17 events —
27% — ahead of same location, same system design, and same supporting systems.
A design defect, a contact-material limitation, or a plunger-jam mechanism in a
D2F-01 is a property of every D2F-01 on the article at once.

### 2. Same manufacturer and lot

Two switches for one dock will be bought in one order, from one distributor,
off one reel. Nothing in the current procurement stops that, and everything
about ordering two of a part encourages it. The
[fabrication packet](../hardware/dock/p0a-fabrication.md) already requires at
least two qualified alternates for the commodity parts and requires recording
manufacturer part number and country of origin and lot on the build sheet —
which makes the coupling *visible* but does not break it.

**Verdict: coupled unless procured differently.** NUREG's hardware-quality
subcategory — same manufacturing staff, quality control procedure,
manufacturing method, and material — is exactly one reel of switches. A plating
excursion or a contamination event in one lot arrives on both channels
simultaneously and silently.

### 3. Shared power rail

Both switches are read through external pull-ups sized above the datasheet
minimum applicable load, and both pull-up networks currently hang on the
OpenRB-150's single 3.3 V rail, with the switch COM terminals tied to a common
controller ground. Four pull-ups, one node.

**Verdict: coupled.** A rail excursion, a regulator fault, or a lost common
return moves all four inputs at once. The [FMECA](dock-fmeca.md) rows FM-CH-03
and FM-CH-04 are exactly this, and both are Class II. The dual-contact NC+NO
decode is what saves them: a rail collapse or a lost return produces an
*invalid pair*, not a plausible state, and is detected. That is a genuine
defence, and it is worth being precise about its limit — it converts a shared-rail
common-cause failure from an undetected wrong answer into a detected loss of
both channels. The dock still stops; it just stops honestly.

### 4. Shared physical location and environment

One dock body, one bracket region, one dust field. S1 sits at the throat where
the probe seats; S2 sits at the keeper's closed stop, a few tens of millimetres
away. Both live in the debris shed by a printed funnel and a printed fork, both
see the same servo vibration, both see the same rotor wash during an approach,
and both see the same hands during every adjustment.

**Verdict: coupled.** NUREG's environment-based class — same component location
covering vibration, ventilation, heat from other components, and accidental
human actions — describes the whole assembly. The specific mechanism that
matters most here is mechanical rather than electrical: **the bracket that
locates the S2 datum also locates the keeper guide.** One displacement moves
the datum and binds the guide, which is TOP-2 cut set 8 and correlated pair CP-3
below.

### 5. Shared harness and connector

Two runs of wire from the same bracket region to the same controller, dressed
along the same path, tied under the same tie, and — unless it is prevented by
design — landing in the same connector housing.

**Verdict: coupled, and the one already being defended.**
[electrical-evidence.md](electrical-evidence.md) rules H5 (keying by different
position counts) and H6 (separate connectors for S1 and S2, never a shared
housing, and not bundled under a single tie for their whole length) exist for
this reason, and `S1_S2_BOTH_OPEN` is on the required hardware fault-insertion
list precisely because a shared interconnection is the credible route to losing
both channels in one event. This document does not re-derive those rules; it
records that they are the correct defence and that the coupling is not closed
until the harness is built to them and the keying check has actually been
performed.

### 6. Shared software

Both channels are debounced by the same code, decoded by the same truth table,
and evaluated by the same `DockController` running on the same SAMD21. There is
one implementation and one processor.

**Verdict: coupled, and accepted with a stated rationale.** Software diversity —
two debounce implementations, two decoders, two processors voting — is the
textbook defence and it is the wrong purchase at this scale. Two implementations
of twenty lines produce two sets of bugs and one integration problem, and the
program has no way to validate the second one that it is not already applying to
the first. The rationale for accepting the coupling is specific: the shared path
is small, it is the *real* controller rather than a re-implementation, and the
digital twin drives that real controller under fault injection rather than
driving a mock. That is not diversity, and it is not claimed as diversity. It is
a reason the shared path is unusually well exercised.

The residual is FMECA row FM-CH-10, the only order-1 cut set of TOP-2. It is
irreducible without redundant computation, and it is accepted.

### 7. Shared calibration and maintenance

One operator sets the S1 datum and the S2 datum, in the same session, with the
same feeler stack or shim, to the same personal standard, and re-sets both after
any bracket work. NUREG's operation-based class names this directly: same
maintenance/test/calibration staff, same procedures, same schedule, with
simultaneous or sequential activities on multiple components.

**Verdict: coupled.** This one is easy to underrate because it looks like
diligence rather than risk. A systematic error in how the datum is judged — a
shim that is 0.2 mm thicker than believed, a habit of setting the switch at
first click rather than at guaranteed over-travel — lands on both switches in
the same afternoon, and the shuttle data ranks *same component calibration
characteristics* at 5 of 64 dependent events (8%).

### 8. Same navigation source

Everything downstream of one Lighthouse system: the aircraft pose, the dock
pose, the relative estimate, the supervisor's seat-plausibility gate, and the
jump detector that is supposed to catch the estimate going wrong. Twin finding
3 states the consequence — a slowly ramping bias is invisible from inside one
positioning system — and HAZ-002 carries it.

**Verdict: coupled, with no defence in P0, and it is not really a beta problem.**
This is the important distinction in this section. A beta factor describes a
redundant *group* of components that sometimes fail together. Here there is no
group: the estimate and the check on the estimate are one measurement used
twice. The effective coupling is 1.0, not 0.1. Calling the plausibility gate an
independent check of the navigation solution is a category error, and no
tuning of the gate changes it. The only defences are a second sensing modality
or a mechanical signal that navigation cannot reach — which is the Rev-B
discriminating sensor, defence D5.

### Summary

| # | Coupling factor | NUREG class | Verdict today | Defence | Status |
| ---: | --- | --- | --- | --- | --- |
| 1 | Same part design | Hardware | Coupled | D1 different manufacturers | Not procured |
| 2 | Same manufacturer/lot | Hardware quality | Coupled unless procured apart | D1 different lots, recorded | Build-sheet field exists |
| 3 | Shared power rail | Hardware | Coupled | D3 separate pull-up feeds and returns | Target |
| 4 | Shared location/environment | Environment | Coupled | D4 separate brackets, S2 datum off the keeper-guide bracket | Not designed |
| 5 | Shared harness/connector | Hardware | Coupled | D2 separate connectors, keyed, separately routed | Specified (H5, H6), not built |
| 6 | Shared software and MCU | Hardware, system design | Coupled | Accepted with rationale; D6 keeps the path small and twin-exercised | Accepted |
| 7 | Shared calibration/maintenance | Operation | Coupled | D7 independent go/no-go gauges, two-step verification | Not written |
| 8 | Same navigation source | System design | Coupled at 1.0, not a beta group | D5 Rev-B discriminating sensor | Candidate only |

Seven of eight are coupled and one is a shared input masquerading as a
redundant pair. That is the whole argument for what follows.

## What the coupling costs: beta factors

NUREG/CR-5485 Appendix A defines the model this program should use, verbatim:

> "The beta factor model is a single parameter model; that is, it uses one
> parameter in addition to the total component failure probability to calculate
> the common cause failure probabilities. It was the first model to be applied
> to common cause events in risk and reliability studies. The model assumes that
> a constant fraction (beta) of the component failure probability can be
> associated with common cause events shared by other components in that group.
> Another assumption is that whenever a common cause event occurs, all
> components within the common cause component group fail."

For a group of m components with total single-component failure probability
`Qt`: the independent term is `Q1 = (1 - beta) * Qt`, the intermediate terms
`Qk` are zero for `m > k > 1`, and the common-cause term is `Qm = beta * Qt`.
Equivalently `beta = Qcc / (Qi + Qcc)` — the fraction of a component's total
failure rate attributable to common cause. The document notes the model is
"reasonably accurate (only slightly conservative)" for redundancy levels up to
about three or four, which covers a two-switch interlock exactly.

### Published ranges

Collated in the NASA review of common-cause failures and ultra reliability:

| Source | Beta range |
| --- | --- |
| IEC 61508 survey of electrical equipment | 0.01 best, 0.30 worst |
| IAEA, thirteen nuclear component types | 0.03 to 0.22, average 0.10 |
| Rutledge and Mosleh, nuclear industry | 0.01 to 0.20 |
| Summers and Gentile, safety systems | 0.001 to 0.05 with good engineering practice in design, installation, inspection and maintenance; **up to 0.25 with poor engineering** |
| Borcsok et al., hardware failures | 0.001 to 0.10 |

The review's synthesis: "The consensus appears to be that beta is 0.01 to 0.10
with good common cause failure prevention, and up to 0.25 for inadequate
engineering." And the observation that makes it usable here: "The values of beta
factors are remarkably similar across totally different systems and
environments." A program with no reliability data of its own can still borrow a
band.

### The empirical anchor

Of 473 space shuttle in-flight anomalies during the first forty flights after
the Challenger accident, 54 — **11%** — were judged common-cause failures, plus
6 due to functional interaction and 4 due to spatial interaction, giving 64
(14%) dependent failures. The review notes the frequency "is not significantly
different from that found in nuclear power plants". The leading coupling factor
among those 64 was *same part design* at 17 events, 27%.

Two switches of the same model number, off the same reel, on the same rail, in
the same dust, adjusted by the same person, are the shuttle's top coupling
factor implemented as thoroughly as a two-channel system permits.

### The arithmetic

Treating S1 and S2 as independent gives `P(both wrong) = Qt^2`. The beta model
gives `P(both wrong) = ((1-beta) * Qt)^2 + beta * Qt`, which for small `Qt` is
dominated by `beta * Qt`. The ratio between the two estimates is therefore
`beta / Qt`:

| Single-channel `Qt` per demand | Independent estimate `Qt^2` | Beta model at `beta = 0.10` | Independence assumption is wrong by |
| ---: | ---: | ---: | ---: |
| 1e-2 | 1e-4 | 1e-3 | 10x |
| 1e-3 | 1e-6 | 1e-4 | 100x |
| 1e-4 | 1e-8 | 1e-5 | 1000x |

These are illustrative values on the model, not predictions: no `Qt` has been
measured for a D2F-01-class switch in this application, and none will exist
before P0-A cycling. What survives regardless of `Qt` is the shape of the
error — **at least an order of magnitude, and worse the better each individual
channel gets.** That is the counter-intuitive part and the reason the
independence claim cannot be left implicit: improving the switches without
breaking the coupling widens the gap between what the design promises and what
it delivers.

### What beta this program should assume

Engineering targets, not measurements, and labelled as such:

| Case | Beta | Basis |
| --- | ---: | --- |
| S1/S2 as currently designed | **0.10** | Seven of eight coupling factors present, including the shuttle's top-ranked one. This sits at the top of the published "good prevention" band and below the 0.25 "inadequate engineering" figure, which is defensible only because the dual-contact decode already converts the shared-rail and shared-return cases into detected faults |
| S1/S2 after defences D1–D4 and D7 | **0.05** target | Different manufacturers, different lots, separate connectors and routing, separate pull-up feeds and returns, separate brackets, independently gauged datums. Mid-band of "good prevention" |
| Floor this program may ever claim | **0.01** | The bottom of every published band, and unclaimable without failure data this program will never collect |
| Anything downstream of one Lighthouse system | **1.0** | Not a redundant group. One measurement used twice |

The practical consequence for the twin: correlated pairs must be *sampled*, at a
rate reflecting beta = 0.10, rather than left to the product of two independent
single-fault draws. A one-fault-per-episode Monte Carlo campaign draws
zero correlated pairs at any sample size, which is why the double fault in twin
finding 5 was found by accident rather than by search.

## Correlated fault pairs

The pairs the twin must draw together, with what makes each one a pair. Column
"Why together" separates the two distinct reasons — **coupling**, meaning the
joint probability is higher than the product, and **defencelessness**, meaning
the joint probability may be tiny but nothing in the design stands between the
pair and the mishap.

| ID | Pair | Coupling factor | Why together | Twin action | Hardware action |
| --- | --- | --- | --- | --- | --- |
| CP-1 | S1 open + S2 open | Shared harness, connector, or common return (#5) | Coupling. One housing, one tie, one return conductor; a single retention failure or mis-mate takes both | Needs a keeper-switch fault channel first (FMECA W1), then a joint plan | `S1_S2_BOTH_OPEN`, already required |
| CP-2 | S1 stuck closed + S2 stuck closed | Same part design, same lot, same dust field (#1, #2, #4) | Coupling. One contamination or plating mechanism acting on two identical contacts in the same environment | Joint plan after W1 | Insert `S1_SHORT` and `S2_SHORT` simultaneously, not only in sequence |
| CP-3 | S2 indicates closed early + keeper binds short of engagement | Shared bracket and mount (#4) | Coupling. The bracket that locates the S2 datum also locates the keeper guide; one displacement produces both. This is TOP-2 cut set 8 | Needs partial-travel keeper fault plus an S2 datum offset (FMECA W5) | Loosen and re-shim the bracket deliberately as an inserted mechanical fault |
| CP-4 | Servo stall or inrush + controller reset | Shared 5 V rail (#3) | Coupling, and a true common cause across two different subsystems rather than a redundant pair. The XL330 draws about 1.47 A at 5 V stalled; the measured analogue in the literature sagged a shared rail to 1.3 V for hundreds of nanoseconds | Needs a controller-reset fault kind (FMECA W2) | `SERVO_STALL` and `CONTROLLER_RESET_DURING_LOCK` in one trial, with the rail on a scope |
| CP-5 | Aircraft pose dropout + dock pose dropout | Same navigation source (#8) | Coupling at 1.0. One base-station occlusion or one system fault takes both; drawing them independently understates the case that matters | `POSE_DROPOUT` and `DOCK_POSE_DROPOUT` in one plan | None — this is a sensing-architecture item |
| CP-6 | Navigation bias + plausibility-gate agreement | Same navigation source (#8) | Not two faults at all. One fault whose check is computed from the same input. Modelling it as two independent draws is the error | Ensure the gate is evaluated on the biased estimate, never on truth | None |
| CP-7 | S1 stuck closed + navigation bias masking the position error | **None** | **Defencelessness, not coupling.** See below | Draw as an explicit pair despite the independence, because single-fault sampling cannot reach it | `S1_SHORT` with the supervisor fed a biased estimate |

### CP-7 is not a coupling, and the difference matters

A jammed switch plunger and a slowly ramping Lighthouse bias have no shared
part, no shared manufacturing process, no shared environment, and no shared
maintenance action. There is no causal mechanism that produces both, so there is
no coupling factor to name and no beta to apply. Assigning one would be
modelling theatre: it would inflate a joint probability with a number invented
for the purpose and then claim the inflated number as rigour.

What makes CP-7 the program's headline residual is a different property.
`capture_confirmed = S1 AND S2` is defended against a single stuck switch by the
supervisor's seat-plausibility gate — and that gate is computed from the
navigation estimate the bias is in. So the pair passes through every barrier the
design has, not because the pair is likely, but because **no barrier exists that
is sensitive to both**. The FMECA records it as TOP-2 order-2 cut set 1;
HAZ-001 carries the mishap.

The two situations call for different responses, and conflating them wastes
both:

| | Coupled pair (CP-1 to CP-5) | Defenceless pair (CP-7) |
| --- | --- | --- |
| What is wrong | The joint probability is `beta * Qt`, not `Qt^2` | The joint probability may genuinely be `Qt * Qn`, and it does not matter |
| Right response | Break the coupling: diversity, separation, different supporting systems | Add a barrier sensitive to at least one of the two, on a physical principle neither fault can reach |
| Wrong response | Assume the redundancy and move on | Argue the probability down |
| Twin's job | Sample the pair at a rate reflecting beta | Sample the pair at all, because single-fault sampling structurally cannot produce it |

Both belong in the twin's plan generator. Only one of them belongs in a beta
factor.

## Defences

The published defence set, from the same shuttle review: use diverse components
in redundant sets; use separate locations for redundant components; connect
components in a redundant set to different supporting systems using diverse
interconnection configurations. NUREG frames the same choice as defending
against the proximate cause, against the coupling factor, or both. Applied
here:

| ID | Defence | Breaks coupling | Concrete form | Status |
| --- | --- | --- | --- | --- |
| D1 | Diverse parts | #1, #2 | S1 and S2 from **different manufacturers**, not merely different lots: the Omron D2F-01 family on one channel and the ZF/Cherry DB3 low-energy family on the other are both gold-family, low-energy, logic-compatible parts with published cycle lives, so diversity costs a second line on the BOM and nothing else. At minimum, if one manufacturer is kept, require **different lot codes recorded on the build sheet** and refuse a build that has one lot on both channels | Engineering target. The DB3 contact-material order code could not be text-verified from the datasheet and must be confirmed with the distributor before it is a real alternate |
| D2 | Separate interconnections | #5 | One connector per channel, different position counts so they cannot be cross-mated, routed apart rather than bundled under one tie | Already specified as H5/H6 in electrical-evidence.md; not built |
| D3 | Different supporting systems | #3 | Separate pull-up networks per channel, fed through separate series elements with separate returns to the controller ground star, and — where the controller permits it — from different regulators. The honest limit: there is one MCU and one board, so this reduces the shared node, it does not remove it | Engineering target; depends on the open item about whether the OpenRB rails can be separated |
| D4 | Separate locations | #4 | The S2 switch bracket must not be the bracket that locates the keeper guide. One displacement should be able to break the datum or bind the guide, not both. Separate fasteners, separate reference surfaces | Not designed. Closes CP-3 and TOP-2 cut set 8 |
| D5 | Diversity of measurement principle — the Rev-B discriminating sensor | #8, and the FMECA's whole undetected sensing group | A keeper closed-position or motor-current signal that separates "closed on probe" from "closed on empty throat". This is diverse in *principle*, not just in part number: it answers "is there a head under the fork" by a mechanism no navigation fault can reach and no switch datum can fake. It is the only defence on this list that touches CP-7 | Rev-B candidate; does not exist. Highest-leverage item in both this document and the FMECA (action A1) |
| D6 | Bounded shared software | #6 | Keep the confirmation path small, keep it the real controller rather than a re-implementation, and keep the twin driving it under fault injection. Do **not** build a second debounce implementation | Accepted coupling with a stated rationale, not a defence |
| D7 | Independent calibration | #7 | S1 and S2 datums set and verified as two separate operations with independent go/no-go gauges, each recorded with adjuster and date, and never adjusted in one operation without re-running the decode check | Not written. Folds into FMECA action A3 |
| D8 | Sample the couplings | all | Correlated-pair episodes in the twin drawn at a rate reflecting `beta = 0.10`, from the CP table above, with the safety zeros unchanged | ADOPT-005 |

D1 through D4 and D7 are cheap, and together they are what moves the assumed
beta from 0.10 to the 0.05 target. D5 is the expensive one and the only one that
changes the fault trees rather than the probabilities in them.

## What this changes in the fault trees

The [FMECA](dock-fmeca.md) lists nine order-2 cut sets for TOP-2. Three carry a
coupling and should not be scored as products:

| TOP-2 cut set | Coupling | Effective scoring |
| --- | --- | --- |
| 8: {FM-SN-11 bracket shift, FM-KP-01 keeper binds} | Shared bracket (#4) | `beta * Qt`, not `Q1 * Q2`. CP-3 |
| 4–7: the S2-datum and keeper-motion pairs | Shared location, shared calibration (#4, #7) | Partly coupled; the S2 datum error and the keeper stoppage are separate mechanisms, but the maintenance action that produces the first often produces the second |
| 1: {FM-SN-03 S1 stuck closed, BE-N1 navigation bias} | None | Genuinely a product — and undefended, which is worse. CP-7 |

And TOP-2's one order-1 cut set, {FM-CH-10}, is a coupling too: it exists
because one code path on one MCU computes the confirmation. It is listed under
coupling factor #6 and accepted, because the alternative purchase is worse at
this scale.

TOP-1 is barely touched by this analysis, and that is the correct result. A
single positive mechanical latch has sixteen order-1 cut sets by design; there
is no redundancy claim to falsify. Common-cause analysis has nothing to say
about a mechanism that never claimed independence in the first place.

## How the independence claim gets closed

Nothing in this document is measured. The claim moves from asserted to verified
only through evidence that does not yet exist:

| Step | Evidence | Where it lands |
| ---: | --- | --- |
| 1 | Build sheet showing two manufacturers or, failing that, two lot codes for S1 and S2 | P0-A article record |
| 2 | Power-on checklist showing separate connectors, a failed cross-mate attempt, and separate pull-up feeds and returns measured | Electrical power-on checklist |
| 3 | `S1_S2_BOTH_OPEN` inserted with the required response written first | P0-A fault log |
| 4 | The CP table's coupled pairs inserted as pairs on hardware, not only in sequence | P0-A and P0-B fault logs |
| 5 | Correlated-pair episodes in the twin, safety zeros unchanged | ADOPT-005 campaign output |
| 6 | Bracket-displacement trial: shift the switch bracket by a measured amount and record what S2 and the keeper do | A0/A1 bench measurement |

Until steps 1 through 6 exist, `capture_confirmed = S1 AND S2` should be read as
a **detected**-fault interlock rather than a redundant one: the dual-contact
decode makes shared-rail, shared-return, and shared-connector failures visible,
which is a real and verifiable property, while genuine independence between the
two channels is not yet claimable at all.

## What is not claimed

- No beta factor here is measured. Every number is either quoted from the
  published sources named above or is an explicitly labelled engineering target.
- This is not an ARP4761 compliance claim. The standard was not read; the CCA
  structure is borrowed from a secondary description and scaled to a prototype.
- The dual-contact decode is a detection mechanism, not an independence
  mechanism. It converts several common-cause failures into detected faults; it
  does not make two switches fail for unrelated reasons.
- CP-7 is not made safer by anything in this document. It is made *visible*, and
  the only thing that would make it safer is defence D5, which does not exist.
