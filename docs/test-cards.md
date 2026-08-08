# Test cards, readiness review, and abort phraseology

Status: working program contract
Scope: every CARRIER-P0 hardware run set (P0-A through P0-D)

[`engineering-loop.md`](engineering-loop.md) governs a campaign: what evidence
closes a gate, when the whole run set stops, and which disposition the run set
receives. It says nothing about the next hour of work — who is holding what,
what the third step of the procedure is supposed to look like, or what word
stops the vehicle. This document adds that run-level layer:

| Layer | Artifact | Question it answers |
| --- | --- | --- |
| Campaign | gate ladder, stop rules, disposition taxonomy | may this article advance? |
| Run | test card, TRR checklist, phraseology | may this run start, and how does it stop? |

The practice basis is conventional flight test: a written card carrying its own
hazard analysis, pre-briefed calls with a named caller, an emergency-procedure
dress rehearsal, and a short readiness review chaired by someone other than the
builder. The specific checklist items, wording, and timings below are
CARRIER-P0 engineering targets, not a reproduction of any organization's
published procedure.

The filled card for the first hardware campaign is
[`hardware/dock/p0a-test-card.md`](../hardware/dock/p0a-test-card.md).

## Crew roles

Three roles, three people. Roles are not combined, and a run with fewer than
three people present does not start.

| Role | Runs the card | Operates the article | Authority |
| --- | --- | --- | --- |
| Test Conductor (TC) | yes | may | authorizes each step; declares the run complete |
| Safety Observer (SO) | no | never | abort and kill authority; final word on both calls |
| Recorder (R) | no | never | owns the log; may call abort like anyone else |

- **Test Conductor** reads the card aloud step by step and authorizes progress.
  Nothing happens between steps that is not on the card. The TC may operate the
  vehicle, actuator, or load personally, or delegate to a fourth person; either
  way the TC owns the sequence.
- **Safety Observer** watches the article, the crew, and the volume — not the
  card. The SO is the person who is free to look up. The SO holds the physical
  kill path and does not fly the aircraft, drive the dock actuator, apply loads,
  or handle the article while it is live.
- **Recorder** keeps the run log: step times, every call made and by whom,
  anomalies as they happen rather than as reconstructed afterwards, and the
  post-run block. The Recorder does not operate anything, because a person
  operating something stops writing at exactly the moment worth writing about.

**Abort authority is independent of the operator.** The person who can stop the
run is deliberately not the person whose hands are on the vehicle: an operator
inside a manoeuvre is the worst-placed person on the crew to judge whether it
should continue. Any crew member may call a stop; the SO's call is final and is
never overruled by the TC, by the builder, or by the fact that the run was
nearly finished.

## Phraseology

Exactly two calls exist. They mean different things, they demand different
actions, and neither substitutes for the other. There is no third, softer call.

Each call is spoken three times — "ABORT, ABORT, ABORT" — so that it survives
propeller noise, ventilation, and cross-talk, and so it can never be confused
with someone discussing an abort. During a live run the bare words "abort" and
"kill" are not used conversationally; if the crew needs to talk about stopping,
they say "we may need to stop the approach."

| Call | Who may call | Required action | Who confirms |
| --- | --- | --- | --- |
| **"ABORT, ABORT, ABORT"** — stop the approach or manoeuvre now. The article stays powered. Autonomy is commanded to the safe state named on this card. | any crew member; the Safety Observer's call is final | operator commands the abort path immediately, without finishing the current step; aircraft goes to its carded safe state; dock/rig motion stops; nobody moves toward the article | operator reads back "ABORT" and states the resulting state aloud ("aborted, holding at 1 m"); Recorder logs the time and the caller |
| **"KILL, KILL, KILL"** — physical kill path. Propulsion de-energised, actuator power removed, release inhibited. | any crew member; the Safety Observer's call is final | Safety Observer actuates the physical kill path at the SO station; no software involvement, no autonomy-computer dependency; everyone freezes in place | Safety Observer announces "KILL COMPLETE, POWER OFF"; nobody approaches the article until the SO announces "SAFE TO APPROACH"; Recorder logs both times |

Rules that go with the two calls:

- ABORT does not require a KILL, and KILL does not require a prior ABORT. A
  hazard that a powered vehicle cannot be trusted to fly out of is called
  straight to KILL.
- The safe state that ABORT commands is **gate-specific and written on the
  card**. It is not always "open" or "back off": a keeper holding a load must
  hold, not release, and a card that says otherwise is wrong.
- Release inhibit is part of the kill path, not a consequence of it. After a
  KILL the mechanism must be unable to drop a captured aircraft.
- Either call ends the run. Work does not resume on the same card entry without
  TC and SO agreement plus a re-brief, and the call is written into the post-run
  block whether or not anything was actually wrong. A call that turns out to be
  unnecessary is free; the crew that hesitates because a call feels like an
  accusation is the failure mode this rule exists to prevent.
- A correctly triggered stop dispositions as `ABORTED_SAFETY`
  ([`engineering-loop.md`](engineering-loop.md)), which is safety evidence and
  not a bad result. It still does not count as a successful capture.

## Test card template

One card per run set per session. Printed, filled by hand, filed with the run
logs as part of the evidence packet. The identity block must match the run logs
exactly; if any of it changes, the card is void and a new configuration identity
is issued.

### 1. Run identity

| Field | Value |
| --- | --- |
| `run_id` | |
| Gate | |
| Configuration/calibration hash | |
| Git commit SHA | |
| Article revision (dock / probe) | |
| Date | |
| Location | |

The remaining promotion-contract fields — carrier and aircraft identifiers,
measured carried mass, battery pack IDs, operator/observer names — are carried
in the run logs and referenced here, not duplicated.

### 2. Crew

| Role | Name | Notes |
| --- | --- | --- |
| Test Conductor | | |
| Safety Observer | | not the operator |
| Recorder | | |
| Operator (if separate) | | |
| TRR chair | | not the builder of the article |

### 3. Objective

One sentence: the question this run answers. If it cannot be written in one
sentence, the run is two runs.

### 4. Success criteria

Numeric only. Every row resolves to a gate criterion in
[`aiur/loop_graph.py`](../aiur/loop_graph.py) or to a requirement ID. No
adjectives.

| Metric | Limit | Source |
| --- | --- | --- |
| | | |

### 5. Run sequence

Every step has an expected observable — the thing the crew will actually see or
read. A step whose expected observable is "it works" is not written yet.

| # | Action | Expected observable | Obs. | Pass |
| --- | --- | --- | --- | --- |
| 1 | | | | |

### 6. Hazard analysis for this run

Top three hazards for *this* run in *this* configuration, not the program
hazard log. Each one names the person who is watching for it; a hazard nobody
is assigned to watch is not mitigated.

| # | Hazard | Cause | Worst credible outcome | Mitigation | Watched by |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

### 7. Abort criteria

Written before the run so the judgement is made cold. Anything that appears in
the campaign stop rules is automatically an abort criterion and does not need
re-deriving here.

| Observation | Call | Required action |
| --- | --- | --- |
| | ABORT / KILL | |

### 8. Post-run

| Field | Value |
| --- | --- |
| Outcome (counts against success criteria) | |
| Disposition (exactly one, per the taxonomy in `engineering-loop.md`) | |
| Calls made (call, time, caller, cause) | |
| Anomalies (including ones that did not stop the run) | |
| Evidence files written | |
| Next action (re-entry stage in the engineering loop) | |
| TC signature / SO signature | |

Anomalies are recorded even when the run passed. An unexplained observation on
a successful run is the cheapest failure the program will ever get.

## Test readiness review

One page, chaired at the start of each gate campaign and re-run after any change
to the configuration identity. It is a walk-through with the article in front of
the crew, not a form filled in afterwards.

**A TRR is chaired by someone who is not the person who built the article.**
The builder presents and answers questions; the chair signs. This is the whole
mechanism: the builder knows what the article is supposed to do and is therefore
the worst available reader of what it actually does. If nobody independent is
present, the session does not run — a self-signed checklist supplies no second
pair of eyes, which is the only thing it was for.

Gate: _____   `run_id`: _____   Chair: _____   Date: _____

- [ ] **Objectives and numeric success criteria** are written on the card, every
      one traceable to a gate criterion or requirement ID.
- [ ] **Procedure approved**: the run sequence is written, each step has an
      expected observable, and the chair has read it.
- [ ] **Configuration identity frozen and recorded**: git SHA, configuration/
      calibration hash, dock and probe revisions, battery pack IDs. Nothing
      changes after this point without a new identity and a new TRR.
- [ ] **Instrumentation verified live before run 1** — each promotion-contract
      channel observed changing in the log, not merely present in the schema:
  - [ ] relative `x/y/z` position and estimate validity
  - [ ] relative velocity and commanded velocity
  - [ ] `S1` probe-seat switch state
  - [ ] keeper/servo command and independent `S2` keeper-closed state
  - [ ] drone arm/disarm state
  - [ ] carrier control/kill state
  - [ ] state-machine state and abort reason
  - [ ] synchronized monotonic timestamps across all sources
- [ ] **Campaign stop rules briefed** from `engineering-loop.md`, read aloud, and
      acknowledged by every crew member.
- [ ] **Hazard analysis reviewed**: the card's top three hazards, their
      mitigations, and the named watcher for each.
- [ ] **Abort phraseology briefed**: both calls, their different meanings, the
      carded safe state, and that anyone may call. Every crew member says both
      calls aloud once so the words have been spoken before they are needed.
- [ ] **Emergency-procedure dress rehearsal** completed for this gate (see
      below), with the elapsed call-to-de-energised time recorded.
- [ ] **Kill path checked end-to-end this session**, including with the autonomy
      computer powered off, and confirmed de-energised by measurement rather
      than by an indicator light.
- [ ] **Crew roles assigned by name** and written on the card; the Safety
      Observer is not the operator.
- [ ] **Area cleared**: nobody under the flight volume, bystander line marked,
      egress path clear, no unbriefed person in the room.
- [ ] **Batteries logged and inspected**: pack ID, cycle count, resting voltage;
      no swollen, damaged, or unlogged pack goes on the article.

Any unchecked box stops the session. The chair does not sign a checklist with a
box carried "to be done during the run" — that is the box that will be skipped.

## Dress rehearsal

Before the first run of each new gate, and again after any crew change, the crew
rehearses the emergency procedures **with the vehicle unpowered and the article
de-energised**:

1. the ABORT call, with the operator physically performing the abort action and
   reading back the resulting state;
2. the KILL call, with the Safety Observer physically actuating the kill path to
   the de-energised state and making the "KILL COMPLETE" and "SAFE TO APPROACH"
   calls;
3. manual recovery — releasing a captured probe by hand and retrieving the
   aircraft from under the carrier, in the positions the crew will actually be
   standing in.

Everyone performs their own action with their own hands. A briefing in which one
person describes the procedure is not a rehearsal; the point is to find that the
kill switch is behind the Safety Observer, or under a laptop, before it matters.

Record the elapsed time from the first word of the KILL call to the measured
de-energised state on the card. Engineering target: ≤3 s on the bench and ≤5 s
at the flight gates, both provisional until measured — if the rehearsal exceeds
the target, the fix is the physical layout of the kill path, not a faster crew.

## How this feeds the loop

The card's post-run block is the input to the debrief stage of the engineering
loop: outcome, disposition, anomalies, and the re-entry stage. Cards are filed
with the run logs, so a gate's evidence packet contains not only what was
measured but what the crew intended to do, what they were watching for, and
every call made while doing it. A run whose card cannot be produced afterwards
is `INVALID_TEST`.
