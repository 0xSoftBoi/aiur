# P0-A assembly

Status: build definition, not an assembled article
Article: Rev-B dock + probe
Prerequisite: every part measured into
[`as-built-template.csv`](as-built-template.csv) before anything is screwed
together

This is the order of operations and, more importantly, the three
adjustments that decide whether the article works: where `S1` sits, where
`S2` sits, and where the keeper stops. Each has a failure mode the program
already knows about, and each is set by adjustment rather than by geometry,
so none of them can be guaranteed by the CAD.

Nothing here is powered until section 6.

## 1. Incoming inspection

Measure and record before assembly, because after assembly most of these
are unreachable:

| Feature | Nominal | Reject if |
| --- | ---: | --- |
| Funnel throat | Ø16.0 mm | outside the stack's assumed ±0.3 mm |
| Probe belt | Ø12.0 mm | outside ±0.3 mm |
| Probe seat | Ø9.0 mm | undersize beyond −0.3 mm — this is the retention ledge |
| Keeper slot | 5.2 mm | undersize beyond −0.5 mm, or it binds on the mast |
| Keeper thickness | 2.5 mm | thin enough to flex visibly under thumb load |

Run the measured set back through the stack before proceeding:

```
python -c "from aiur.tolerance import as_built, measured_dimensions, evaluate_stack, KEEPER_HEAD_OVERLAP; \
print(evaluate_stack(as_built(KEEPER_HEAD_OVERLAP, measured_dimensions({...}))))"
```

An article whose measured retention ledge does not close is a reject, not a
part to build with and watch. The whole point of measuring is to find that
out before it holds an aircraft.

## 2. Fit checks, dry

1. Slide the keeper through its guides by hand across the full intended
   travel. It must move without binding and without perceptible rock.
2. Pass the probe head up through the funnel throat by hand. It must enter
   without catching. A press fit here shows up later as insertion force on
   the cycle sheet, where the capture logic cannot see it and the approach
   controller cannot fly it.
3. With the probe seated, close the keeper by hand. The tines must pass
   **under the Ø9 seat**, not against the Ø12 belt. If they contact the
   belt, the keeper is mounted at the wrong height — stop, because this is
   the coupled dimension pair from the tolerance stack and no amount of
   adjustment elsewhere fixes it.

## 3. Keeper travel and hard stops

Set the mechanical stops before the servo is connected.

1. Set the closed stop so the tines sit fully under the seat with the slot
   centred on the mast.
2. Set the open stop so the keeper retracts **≥13.0 mm** from closed.
3. Measure delivered travel with a dial indicator against the keeper, not
   by counting servo units, and record it in the as-built set.
4. Verify the stops are hard: the keeper must not be able to reach the
   funnel or leave its guides even if driven fully in either direction.

Requirement P0-DRIVE-001 to P0-DRIVE-003 in
[keeper-drive.md](keeper-drive.md). Under 13.0 mm of measured travel the
article cannot release a captured aircraft, which is what forced Rev-B.

## 4. S1 — the seat switch

**This adjustment is the one most likely to be got wrong**, and getting it
wrong produces a fault on every otherwise good capture (FMECA FM-SN-05,
requirement P0-DOCK-010).

`S1` must be actuated by **probe position with over-travel**, not by
maintained contact force. The docked aircraft weighs about 0.47 N; a
subminiature switch needs 0.74 N or more to operate. So the aircraft's
weight cannot hold the switch made, and once the aircraft disarms and its
weight transfers from thrust to the keeper tines, a force-actuated switch
opens. The controller correctly reads that as sensor disagreement and fails
locked — every time.

Set it this way:

1. Seat the probe fully by hand and hold it at the seat.
2. Adjust the switch so it operates **before** the probe reaches the seat,
   leaving visible over-travel at the fully seated position.
3. Release the probe so it rests down on the keeper tines, as it will when
   the aircraft is captured and disarmed.
4. **`S1` must still read made.** If it opens, the switch is force-actuated
   at this position and the mounting is wrong. Move it, do not compensate
   in software.
5. Record the over-travel achieved.

## 5. S2 — the keeper-closed switch

`S2` senses the keeper itself at its closed stop. It must not be mounted
where a servo horn can claim "closed" while the keeper is obstructed —
which is the entire reason `S2` exists as an independent channel.

1. With the keeper at its closed hard stop, adjust `S2` to operate with
   over-travel remaining.
2. Drive the keeper closed against a deliberate obstruction (a shim in the
   throat). `S2` must **not** make. If it does, it is sensing the drive and
   not the keeper.
3. Mount `S1` and `S2` on **separate connectors**, per the common-mode
   analysis: a shared connector makes the two channels a single failure.

## 6. Wiring and first power

Follow [electrical-evidence.md](../../docs/electrical-evidence.md).

1. Continuity and pull-test every crimp before connecting anything.
2. Verify the `S1`/`S2` dual-contact decode with a meter — before the
   controller is connected to the mechanism.
3. First power on a current-limited supply, rails checked against the
   expected-current table, keeper de-energised, no probe present.
4. Confirm `S2` reads open with the keeper physically open. A closed
   reading here is the condition the controller now treats as "possibly
   holding something", and it should be resolved on the bench rather than
   discovered in a campaign.
5. First commanded motion at reduced travel limits, working out to the
   stops.

## 7. Before the gate

- Weigh the complete dock and the complete probe; both budgets are gate
  criteria.
- Freeze the configuration identity (revision, commit, calibration) per the
  promotion contract.
- Run the [readiness review](../../docs/test-cards.md) with someone who did
  not build the article.
- On P0-A pass, freeze this article as the
  [golden article](golden-article.md).

## What this procedure does not cover

The keeper drive linkage is not designed yet — see
[keeper-drive.md](keeper-drive.md). Sections 3 and 6 assume a drive exists
that delivers the stroke; building one is the open task, and every step
here that references travel becomes executable only once it does.
