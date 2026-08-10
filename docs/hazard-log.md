# CARRIER-P0 hazard log

Status: machinery built, zero residuals signed
Scope: CARRIER-P0 through P0-D, indoor tethered operation

The log is `aiur/hazards.py`. This document explains the rules it enforces
and prints the current state; the module is the authority, and every table
below is generated from it.

MIL-STD-882E w/Change 1 puts every hazard on a severity x probability
matrix, but the matrix is not the part worth copying at this scale. The
part worth copying is section 4.3.7: "Before exposing people, equipment, or
the environment to known system-related hazards, the risks shall be accepted
by the appropriate authority", with Task 106.2.q requiring the record to
carry the accepting authority by title and organization, the date of
acceptance, and where the signed document lives. A program that writes
"documented residual accepted" and moves on has not accepted anything — it
has described a risk and left it unowned.

This log exists because CARRIER-P0 had exactly that sentence in
[digital-twin.md](digital-twin.md) finding 5.

## Tailoring: why the dollar thresholds are gone

Table I scores severity on three limbs — death/injury, environmental impact,
and monetary loss. The monetary limb is DoD-scale: Catastrophic starts at
"monetary loss equal to or exceeding $10M". Scored on money, every hazard
on this program is Negligible, the matrix returns Low for everything, and
the tool is inert.

CARRIER-P0 therefore keeps the injury limb of Table I verbatim and replaces
the monetary limb with a program-scaled system-loss limb. Tables II and III
are used unmodified.

| Category | # | MIL-STD-882E Table I mishap result criteria | Program reading of the non-injury limb |
| --- | ---: | --- | --- |
| Catastrophic | 1 | death, permanent total disability, irreversible significant environmental impact, or monetary loss >= $10M | loss of the gas envelope with an uncontrolled descent onto occupied floor space, or a fire that leaves the test room |
| Critical | 2 | permanent partial disability, injuries or occupational illness that may result in hospitalization of at least three personnel, reversible significant environmental impact, or monetary loss >= $1M and < $10M | loss of the carrier or of the only dock article, which stops the program |
| Marginal | 3 | injury or occupational illness resulting in one or more lost work day(s), reversible moderate environmental impact, or monetary loss >= $100K and < $1M | damage costing a rebuild and a schedule slip: a destroyed aircraft, funnel, keeper, or actuator |
| Negligible | 4 | injury or occupational illness not resulting in a lost work day, minimal environmental impact, or monetary loss < $100K | damage repaired from the spares already on the bench |

882E 4.3.3.d allows tailored alternate definitions "derived from Tables I
through III" when they are "formally approved in accordance with DoD
Component policy". There is no DoD Component here and this is not a DoD
program. What is above is documented program tailoring, not an approved
alternate, and this document is not a compliance claim.

The injury limb is where the severity calls actually come from. At this
scale that means: a spinning 55 mm propeller at face height or a lithium
fire is Critical because permanent partial disability is credible;
asphyxiation is Catastrophic; a disarmed 37 g aircraft falling three metres
is Marginal.

## Probability levels

Table II, "Specific Individual Item" column, verbatim. The single-item
column is the right one: there is one dock, one carrier, and two aircraft —
the fleet column describes a population that does not exist.

| Description | Level | Specific individual item |
| --- | :---: | --- |
| Frequent | A | Likely to occur often in the life of an item. |
| Probable | B | Will occur several times in the life of an item. |
| Occasional | C | Likely to occur sometime in the life of an item. |
| Remote | D | Unlikely, but possible to occur in the life of an item. |
| Improbable | E | So unlikely, it can be assumed occurrence may not be experienced in the life of an item. |
| Eliminated | F | Incapable of occurrence. This level is used when potential hazards are identified and later eliminated. |

Level F is reachable only by design. Per 4.3.3.b, "No amount of doctrine,
training, warning, caution, or Personal Protective Equipment (PPE) can move
a mishap probability to level F." Nothing in this log is at F.

Every probability in the log is a qualitative judgement, not a measured
rate. No hardware article exists and no gate campaign has been run; these
are engineering estimates that P0-A and P0-B evidence is meant to replace.

## Risk assessment matrix

Table III, transcribed as data in `aiur/hazards.py` so it can be diffed
against the printed table rather than reverse-engineered out of an if-chain.
A risk assessment code (RAC) is one severity category plus one probability
level: a RAC of 2C is Critical severity at Occasional probability.

| Probability | 1 Catastrophic | 2 Critical | 3 Marginal | 4 Negligible |
| --- | --- | --- | --- | --- |
| A Frequent | High | High | Serious | Medium |
| B Probable | High | High | Serious | Medium |
| C Occasional | High | Serious | Medium | Low |
| D Remote | Serious | Medium | Medium | Low |
| E Improbable | Medium | Medium | Medium | Low |
| F Eliminated | Eliminated | Eliminated | Eliminated | Eliminated |

## Acceptance authority ladder

882E does not name acceptance authorities; it defers to the DoDI 5000
series. The DoD mapping (DoDI 5000.88, section 3.6.e(1)(b)1) sends High
risks to the CAE or DAE, Serious to program executive officer level, and
Medium and Low to the PM, with user-representative concurrence before every
Serious and High acceptance.

A three-person indoor test crew has no CAE and no PEO. What CARRIER-P0
copies is the structure — authority rises with risk, and above a line nobody
may accept at all — not the mapping. The ladder below is program-defined.

| Residual risk | Who may accept | Note |
| --- | --- | --- |
| High | nobody | must be mitigated before exposure |
| Serious | program lead, with written rationale | the rationale is part of the record, not a conversation |
| Medium | safety observer + test conductor | both, by name |
| Low | test conductor | no separate record required; runs on the standing test-card rules |
| Eliminated | nobody | the hazard cannot occur in the current design |

This program is stricter than the DoD model at the top. DoDI 5000.88 lets a
High risk be accepted by the CAE; here a High residual is a stop. There is
no authority on this program with the standing to accept a High risk, and no
reason to run an indoor prototype that still carries one. Two hazards
(`HAZ-005`, `HAZ-008`) were assessed High initially; both were designed down
rather than signed off.

The ladder is reported by the tooling, not string-matched against the `role`
field. With three people and no org chart, an automated title check would be
theatre; a reviewer reading the open-items list sees the required authority
next to every unsigned residual.

## No residual is accepted anonymously

This is the whole point of the file. An acceptance record carries five
fields, and the validator rejects a record missing any of them:

| Field | Why it exists |
| --- | --- |
| `accepted_by` | a name. "The team accepted it" is not an acceptance |
| `role` | the standing the name is acting under |
| `date` | ISO-8601. Acceptances go stale; an undated one cannot be re-reviewed |
| `scope` | the regime the acceptance covers, e.g. "indoor tethered P0 single-fault regime" |
| `rationale` | why the residual is tolerable, in writing, so a later reviewer can disagree with the reasoning instead of guessing at it |

`scope` is the field that does the real work. It stops an indoor signature
from quietly authorising outdoor flight: leaving the regime re-opens every
hazard signed under it, which is exactly the transition the vertical studies
describe as a scaling milestone rather than a software patch.

## How a hazard closes

It does not. The DoD Systems Engineering Guidebook records that "[i]n
accordance with MIL-STD-882, a risk is never closed nor is the term
'residual' risk used". This log keeps the rule and breaks the vocabulary:
"residual" is used because it names the thing the program keeps forgetting
to sign for, but no hazard has a closed state.

A hazard moves through four statuses and then stays in the log for the life
of the article:

| Status | Meaning |
| --- | --- |
| `identified` | in the log; no mitigation selected |
| `mitigation_selected` | mitigation present in the design, software, or procedure; the named verification has not produced evidence |
| `mitigation_verified` | the named verification has run and produced evidence |
| `eliminated` | residual probability is F; the hazard cannot occur in the current design |

Every hazard in the log is `mitigation_selected` today. None can reach
`mitigation_verified` until a hardware gate campaign runs, because that is
where the evidence comes from.

Each hazard's `verification` field must name a real gate id, gate criterion,
or requirement id; a verification note that points at nothing is a validator
error. Where nothing measures a hazard — `HAZ-006`, `HAZ-007`, `HAZ-009` —
the field says so explicitly rather than implying coverage.

## Current hazards

Generated from `HAZARDS` in `aiur/hazards.py`.

| ID | Hazard | Initial | Residual | Acceptance required from | State |
| --- | --- | --- | --- | --- | --- |
| `HAZ-001` | Confirmed capture on an empty dock after a correlated double fault | 3C medium | 3D medium | safety observer + test conductor | unsigned |
| `HAZ-002` | Undetectable navigation bias walks the aircraft into the dock rim | 3B serious | 3C medium | safety observer + test conductor | unsigned |
| `HAZ-003` | Gas-envelope strike by a powered aircraft | 2C serious | 2D medium | safety observer + test conductor | unsigned |
| `HAZ-004` | Captured aircraft is dropped by the dock | 3B serious | 3D medium | safety observer + test conductor | unsigned |
| `HAZ-005` | Propeller contact with the funnel, dock structure, or a person | 2B high | 2C serious | program lead, with written rationale | unsigned |
| `HAZ-006` | Keeper closes on a finger during bench work | 4B medium | 4D low | none required at LOW | n/a |
| `HAZ-007` | Lithium-polymer thermal event during charge or storage | 2C serious | 2D medium | safety observer + test conductor | unsigned |
| `HAZ-008` | Loss of the physical kill path | 2B high | 2D medium | safety observer + test conductor | unsigned |
| `HAZ-009` | Helium asphyxiation in a small enclosed test room | 1D serious | 1E medium | safety observer + test conductor | unsigned |
| `HAZ-010` | Keeper servo stalls and overheats | 3B serious | 3D medium | safety observer + test conductor | unsigned |
| `HAZ-011` | Uncommanded release over a person | 2C serious | 2D medium | safety observer + test conductor | unsigned |
| `HAZ-012` | Carrier overruns its own aircraft or drifts into the crew | 3B serious | 3D medium | safety observer + test conductor | unsigned |

`HAZ-001` is twin finding 5 and `HAZ-002` is twin finding 3. `HAZ-001` is
the one the log was built for: a stuck-closed seat switch plus a masked
navigation bias walks the real controller to a confirmed capture on an empty
dock, and no supervisor built on the same measurements can tell. Software
cannot close it. The Rev-B keeper discrimination sensor can, and it does not
exist, so the residual is real and it needs a name on it.

`HAZ-009` is on the list because helium asphyxiation is the hazard indoor
lighter-than-air programs forget. It is the only Catastrophic severity in
the log, it has no instrument and no gate criterion, and its probability is
a judgement.

## The signatures are missing, and that is the honest state

Every acceptance record in the registry is absent. Nobody has signed
anything, so nothing is signed here. Writing plausible names and dates into
the file would defeat the only thing it is for.

The tooling therefore runs in two modes:

| Call | Question | Current answer |
| --- | --- | --- |
| `validate_hazards()` | is the log structurally sound? | yes, no errors; this is what CI runs |
| `validate_hazards(require_acceptance=True)` | may a person be exposed to this article? | no: 11 residuals above LOW have no signed acceptance |
| `open_items()` | who has to decide what? | the same 11, each with its required authority |

The structural mode checks unique sorted ids, populated fields, a
verification note that names something real, a residual that is not worse
than the initial assessment, that any acceptance present is complete, and
that no High residual has been accepted at all. The pre-exposure mode adds
4.3.7: every residual above LOW must already be signed. It fails today, on
purpose.

Run either:

```
python -m aiur.hazards
```

The JSON carries the matrix, the ladder, the open items, and both error
lists, so a readiness review can read the current state without opening the
source.

## What closing the gap looks like

For each of the 11 open items: the named authority reads the hazard, the
mitigations, and the verification note; writes a rationale; and records name,
role, ISO date, and scope. `scope` should be the standing P0 sentence
(`indoor tethered P0 single-fault regime, propeller-guarded`) unless the
decision genuinely covers something else — a wider scope is a different
decision.

Two of the eleven should probably not be signed at all in their current
form. `HAZ-005` is Serious because zero propeller-contact evidence exists;
the honest move is to run P0-B and let `prop_funnel_contacts` replace the
probability judgement. `HAZ-001` is the residual that a Rev-B design change
removes rather than a signature tolerates. An acceptance is a decision to
proceed with a known risk, not a substitute for the mitigation that was
already identified.
