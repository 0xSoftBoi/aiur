# P0-A build plan

Status: build sequence, not an assembled article
Article: Rev-B dock + probe, A0 then A1
Flight condition: **no flight; propellers removed**

This is the order of operations from nothing ordered to an article eligible
to attempt the [P0-A test card](p0a-test-card.md). It does not restate the
geometry ([bench article](p0a-bench.md)), the electrical interface
([fabrication](p0a-fabrication.md)), the build order
([assembly](assembly.md)), or the acceptance criteria
([execution gate](../../docs/P0_EXECUTION_GATE.md)). It sequences them, and
it names the point at which each open decision has to close.

## The shape of the problem

A0 is not a rehearsal for A1. A0 is a measurement article whose outputs are
the inputs to several A1 purchases, and the fabrication pack already says so
in the notes: the switch operating-force variant waits on the A0 S1
actuation-force measurement, the pull-up value waits on the as-built contact
current, the fault-insertion relay board waits on both of those freezing, the
controller-side hold-up island waits on a rail-transient capture, the probe
mast is cut from physical fit, and the sacrificial breakaway feature is TBD
by physical test.

So the critical path is not procurement lead time. It is:

```
order the unblocked parts -> print -> measure A0 -> freeze -> order the rest
```

Money spent on A1-dependent parts before A0 measures is money spent on
guesses, and the guesses are exactly the ones Rev-A already got wrong once.

## Stage 0 — order what A0 cannot change

These do not depend on any A0 measurement. The purchasing sheet is
[`p0a-stage0-order.csv`](p0a-stage0-order.csv): one row per line item, with
what has to be verified at order, and the blocked lines carried in the same
sheet with their blocker named so they cannot be ordered by accident. Fill
`po_ref`, `ordered_date`, `received_date` and `coo_lot` as they land — the
COO/lot column is the supply-chain evidence the fabrication pack asks for,
and it is unrecoverable after parts are mixed into a bin.

| Item | Qty | Note |
| --- | ---: | --- |
| Print feedstock (PETG baseline, PA12 alternative) | — | Record material source; the funnel wall is a printable starting section, and the real part gets weighed |
| Ø3 mm GFRP/CFRP mast stock | 1 length | Cut to length later, from fit; buy stock, not a cut part |
| M3 fasteners, metal inserts, washers | assortment | Inserts where print bearing stress requires them |
| Keeper guide stock | — | Rigid guides and the end stop react retention load, not the servo |
| Ø3 mm dowel pins + positive retention (clip, e-ring, or shouldered screw) | 2 + spares | A plain press fit is not acceptable: P0-DRIVE-006 exists because a press fit that migrates over 600 cycles is a mid-campaign failure |
| DYNAMIXEL XL330-M288-T | 1 + 1 spare | Baseline on a swappable bracket so it cannot become an architecture decision |
| OpenRB-150 | 1 | Ground equipment |
| Current-limited 5 V ≥3 A bench supply | 1 | Ground equipment; the XL330 stalls at ~1.5 A, above the OpenRB USB limit |
| Servo-rail bulk capacitor, 1000 µF ≥16 V low-ESR | 1 + spare | Fitted at the servo connector, not at the supply |
| Dial indicator | 1 | Stroke is measured at the keeper, never at the servo |
| Calipers / micrometer | 1 | Every as-built dimension is recorded before assembly |
| Force gauge covering 0–20 N | 1 | Must resolve the 1 N lateral screen and the 5 N axial screen with margin, and read insertion/release force per run-in cycle |

**Buy the switch as an assortment, not a decision.** The gold-contact
requirement is frozen — gold alloy or gold crosspoint, published minimum
applicable load ≤1 mA at 5 VDC, silver variants prohibited on logic-level
sensing. What is open is the operating force and actuator style, because the
0.468 N docked static weight sits below even the 0.74 N variant. Buying two
each of the 1.47 N, 0.74 N and lever variants of the qualified family costs
less than one blocked week. Order the 1.0 kΩ and 680 Ω pull-ups together for
the same reason.

**Do not order yet:** the fault-insertion relay board, the controller-side
hold-up island, the flight probe base, or any second-source switch that has
not had its minimum applicable load and gold order-code digit confirmed with
the vendor.

## Stage 1 — print and measure (A0)

Regenerate from `cad/generate_rev_a.py`, which builds Rev-B as `CURRENT` and
writes the revision into the manifest. Print the funnel, keeper, probe head,
crank, and link. Drill crank and link pin holes after printing, from
`p0a_linkage_template_rev_b.svg`.

Print at least two of every load-bearing part in the same session and on the
same material lot. The second set is not a spare for later — it is what lets
a rejected part be replaced without reopening the question of whether the
replacement came from the same process.

Then measure, before anything is screwed together, into
[`as-built-template.csv`](as-built-template.csv), and run the measured set
back through `aiur.tolerance`. An article whose measured retention ledge does
not close is a reject.

A0 exits when it has produced, per the fabrication pack:

- actual funnel, keeper and coupon-head masses;
- throat/head and slot/mast fit measurements;
- manual keeper travel and force measurements;
- photographs of the closed load path and keeper guides;
- a disposition for any hand-work performed on load-bearing geometry.

Add three measurements that A1 purchases depend on. These are not part of the
original A0 list, and they are the reason Stage 2 can close at all — each one
decides a purchase that is otherwise a guess. Record them in
[`p0a-a0-measurements-template.csv`](p0a-a0-measurements-template.csv), which
is pre-populated with the three rows so they cannot be quietly skipped.

| Measurement | Threshold | Decides |
| --- | --- | --- |
| S1 actuation force available from a seated probe | Compare against 1.47 N / 0.74 N / lever | Which switch variant is built in — the docked static weight is 0.468 N, below even the 0.74 N variant |
| Free-probe wander, keeper open, worst direction | >0.60 mm reinstates the deleted backstop | Whether the deletion review's disposition still holds, and therefore what gets built |
| Closed-contact current with the candidate pull-up | <3.0 mA fits 680 Ω rather than 1.0 kΩ; must stay above the ~1.5 mA micro-load boundary | The pull-up value, which in turn releases the fault-insertion relay board |

A measurement recorded without its decision is half-done: the `decision` column
is what Stage 2 reads.

## Stage 2 — freezes

Nothing in this table can be deferred past this point without the article
becoming untraceable.

| Decision | Closed by | Releases |
| --- | --- | --- |
| Switch variant and actuator style | A0 S1 actuation-force measurement | S1/S2 brackets, harness build |
| Pull-up value | As-built contact-current measurement | Fault-insertion relay board order |
| Passive backstop in or out | A0 free-probe wander vs 0.60 mm | Keeper region geometry |
| Mast length | Physical fit | Probe head bond, standoff verification |
| Actuator linkage geometry | A0 keeper breakaway/running force | Crank/link pin centres, motion limits |
| Sacrificial breakaway feature | Physical test | Flight probe base — **not required for the P0-A gate**; do not let it block the bench campaign |
| Hold-up island | Rail-transient scope capture | Conditional order, or a recorded decision not to fit |

Each freeze is a hardware revision entry, not a note. A design change after
this point starts the relevant screening and cycle evidence again — changed
hardware is never appended to an existing life-test run.

## Stage 3 — order the rest

Fault-insertion relay board, the confirmed switch variant in build quantity
plus spares, harness connectors (S1 three-position, S2 four-position with one
blanked — the differing position count is the keying, and colour coding does
not count), and the hold-up island if the transient capture calls for it.

## Stage 4 — assemble

Follow [assembly.md](assembly.md). Its three adjustments — where S1 sits,
where S2 sits, and where the keeper stops — are the ones the CAD cannot
guarantee, and they are set by hand.

The one to slow down on is the keeper height: if the tines contact the Ø12 mm
belt rather than passing under the Ø9 mm seat, the keeper is mounted wrong,
and no adjustment elsewhere fixes it.

Measure delivered stroke at the keeper with the dial indicator and confirm it
against the 13.0 mm the crank geometry should produce. A stroke measured at
the servo is not the stroke the mechanism has.

## Stage 5 — first power

Per the fabrication pack, in this order, with the mechanism disconnected from
the probe until the last step: set the supply current limit, verify common
ground and actuator voltage with a meter, run the keeper free, establish
software position limits from the physical stops, then reconnect.

Before this, validate the S1/S2 electrical truth table with a meter — both
contacts of each switch, four states, wiring faults distinguishable — while
it is still disconnected from the dock state machine. The whole
`capture_confirmed = S1 AND S2` claim rests on that table being true in
hardware rather than assumed in software.

## Stage 6 — readiness review, then run

The campaign starts at the readiness review defined in
[docs/test-cards.md](../../docs/test-cards.md), against the printed
[test card](p0a-test-card.md). Crew roles, abort phraseology and stop
conditions are settled before run 1, not during it.

Force margins come before cycling: keeper close and open force margin at
minimum supply voltage, both ≥2.0. An actuator at margin 1.1 works on the
bench and fails on the vehicle when the battery sags.

Then run-in (≥15 cycles, force trend must level off), then the 600 life-test
cycles with an emergency-release trial every 25th, alternating unloaded and
loaded so ≥10 of each accumulate.

## Duration

Working days, as engineering estimates. Replace each with a quoted date at
order; none of these are commitments.

| Stage | Estimate | Driven by |
| --- | ---: | --- |
| 0 — order unblocked | 1 d to place | Vendor lead time dominates and is unknown until quoted |
| 1 — print and measure A0 | 3–5 d | Print time is hours; the measurement discipline is the work |
| 2 — freeze | 1 d | Only slow if A0 measurements were skipped |
| 3 — order remainder | 1 d to place | Second lead-time exposure; this is why Stage 0 buys assortments |
| 4 — assemble | 2–3 d | The three adjustments |
| 5 — first power | 1 d | Stop-and-check sequence, not a schedule item to compress |
| 6 — campaign | 5–10 d | 600 cycles plus 24 emergency-release trials plus 9 fault modes, at a rate no one has measured yet |

The cycle rate is the largest unknown in this table. Measure it during run-in
and revise Stage 6 from data, rather than defending an estimate made before
the mechanism existed.

## Spares policy

The printed article is a consumable and the knowledge is not. Print spares of
every load-bearing part in the Stage 1 session, keep one complete unbuilt set,
and after the gate closes, keep cycling the article until something breaks and
record what broke and at what cycle. Nothing in P0 depends on that number, and
it is the cheapest available warning about the wear-out mode.

## What would make this plan wrong

- A0 free-probe wander above 0.60 mm reinstates the deleted backstop, which changes Stage 2 and Stage 3 rather than delaying them.
- No qualified gold-contact switch in the required operating force pushes S1/S2 into a different sensing approach, and the independence argument has to be re-made rather than re-used.
- A measured cycle rate far below expectation makes 600 cycles the schedule, at which point the derivation in `aiur/loop_graph.py` is the thing to revisit — with argument, not with a smaller number.
