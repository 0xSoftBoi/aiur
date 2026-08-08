# Golden article

Status: rule in force from the first P0-A pass; no article has been built yet  
Scope: CARRIER-P0 dock and probe articles, Rev-A onward  
Executable form: [`aiur/tolerance.py`](../../aiur/tolerance.py), [`as-built-template.csv`](as-built-template.csv)

A P0-A pass is evidence about one physical article, not about a drawing. The
Rev-A CAD is deterministic; the parts that come off the printer are not. Two
articles from the same STL and the same slicer profile differ by more than the
capture chain's smallest clearance — the keeper ledge is 0.8 mm at nominal and
the assumed printed tolerance is 0.15 mm per surface. So the article that closes
P0-A becomes the reference, and every later article is measured against it before
it is allowed to carry gate evidence.

Without this rule the program silently assumes single-article behaviour: a
second dock prints, works once, and inherits the 600 derived life-test cycles
(`aiur.loop_graph.DERIVED_LIFE_TEST_CYCLES`) that the first article earned. It
has earned none of them.

The rule has no article to freeze yet. `python -m aiur.tolerance` currently
reports three open findings against Rev-A — the keeper/mast slot clearance, the
keeper/head retention ledge, and the keeper release travel — and the third is
negative at nominal, so no Rev-A article can pass P0-A as drawn. The freeze
procedure below is written now because it has to be in force *before* the first
article that closes the gate, not written afterwards about it.

## What gets frozen on a P0-A pass

| Item | Definition | Where it lives |
| --- | --- | --- |
| The article | The physical dock and probe that closed the gate, bagged and labelled, not cannibalised for the next build | Bench custody, labelled `<article_rev>-<article_serial>` |
| As-built set | Every feature in [`as-built-template.csv`](as-built-template.csv), measured pre-cycle and post-cycle | `hardware/dock/as-built/<article_rev>-<article_serial>.csv` |
| Photographs | Funnel throat, keeper closed on the probe, keeper fully open, probe head underside, every fastener | `hardware/dock/as-built/<article_rev>-<article_serial>/` |
| Config identity | `run_id`, Git commit, article revision and serial, printer/process, material lot | Identity columns of the as-built and P0-A sheets |
| Stack re-run | `python -m aiur.tolerance` output for the commit, plus the as-built re-run for this article | Attached to the P0-A evidence packet |
| Evidence packet | The P0-A article, cycle, and load sheets that closed the gate | `hardware/dock/` per [p0a-bench.md](p0a-bench.md) |
| Process record | Slicer profile, nozzle, layer height, material lot, print orientation | `printer_or_process` and `material_lot` in [`p0a-article-template.csv`](p0a-article-template.csv) |

The physical article is retained because a measurement disagreement between
article N and the record is only resolvable against the part itself.

`article_serial` is defined by the as-built record. The P0-A sheets identify a
run by `run_id` and `article_rev`, so the as-built rows carrying that `run_id`
are what resolve which physical article produced a given result. Two articles
of the same revision are two articles; the revision is not the identity.

## The as-built record

One row per measured feature. Header only ships in the template; no example
values, because an example value in a measurement sheet eventually gets
committed as data.

| Column | Meaning |
| --- | --- |
| `run_id` | Same identity as the P0-A evidence set the article belongs to |
| `article_rev` | Design revision, e.g. `Rev-A` |
| `article_serial` | Which physical article of that revision; the golden-article rule needs article identity, not revision identity |
| `git_commit` | Commit the CAD and the stack were generated from |
| `part` | `funnel`, `keeper`, `probe_head`, `mast`, or `assembly` |
| `feature` | One of the `AS_BUILT_FEATURES` names in `aiur.tolerance` |
| `nominal_mm` | Rev-A nominal for that feature, from the same table |
| `measured_mm` | What the instrument read |
| `instrument` | Instrument and technique, not just "caliper" |
| `operator` | Who measured |
| `date` | Measurement date |
| `notes` | Measurement pass (`pre-cycle` / `post-cycle`), reworks, anything anomalous |

Features are operator-facing: diameters and lengths, measured where a caliper or
pin gauge actually reaches. `aiur.tolerance.measured_dimensions` converts them
into the radial terms the stack uses, so nobody halves a number by hand.

| Feature | Part | Instrument | Stacks it feeds |
| --- | --- | --- | --- |
| `funnel_throat_diameter` | funnel | caliper, two orthogonal readings | entry clearance |
| `probe_head_max_diameter` | probe_head | caliper at the Ø12 belt | entry clearance, release clearance |
| `probe_head_seat_diameter` | probe_head | caliper on the lower cylinder | keeper head overlap |
| `probe_head_bore_diameter` | probe_head | pin gauge, post-ream | keeper head overlap (via head-to-mast float) |
| `probe_mast_diameter` | mast | micrometer, three stations | slot/mast clearance, head-to-mast float |
| `keeper_slot_width` | keeper | pin gauge at mouth and round end | slot/mast clearance, keeper head overlap |
| `keeper_tine_reach` | keeper | caliper from slot round-end centre to tine tip | release clearance |
| `keeper_open_travel` | keeper | dial indicator between the closed and open stops | release clearance |
| `seated_probe_lateral_offset` | assembly | dial indicator on the seated mast, worst of two orthogonal axes | slot/mast clearance, keeper head overlap |

The last row is an assembly measurement, not a part measurement. It is the one
number the Rev-A CAD does not define, and it drives two of the three critical
stacks.

## Comparing a later article

Before article N carries any gate evidence:

1. Print the as-built set for article N, pre-cycle.
2. Re-run the capture-chain stacks against those numbers.
3. Compare feature by feature against the golden article's set.
4. Record the disposition against the deviation classes below.

```python
from aiur.tolerance import STACKS, as_built, evaluate_stack, measured_dimensions

measured = measured_dimensions({...})  # feature -> measured_mm, from the CSV
for stack in STACKS:
    print(evaluate_stack(as_built(stack, measured)))
```

The as-built stack replaces assumed process tolerance with measurement
uncertainty, so a real article usually shows more margin than the predicted
stack. Two rules keep that from becoming optimism: a feature that was not
measured keeps its assumed, wider tolerance, and a fit derived from two
readings — the probe-head bore on the mast — carries both readings'
uncertainty.

That is the point of the as-built record, and it is also its limit:
measurement can rescue a stack that fails on assumed tolerance, and it cannot
rescue one that fails on geometry. `keeper_release_clearance` is negative at
nominal and stays negative for every article of Rev-A.

## Deviation classes

| Class | Trigger | Cost |
| --- | --- | --- |
| A — acceptance screen | Every feature inside its Rev-A tolerance, every critical stack's as-built worst case above its minimum, same printer, process, slicer profile, and material lot as the golden article | As-built set, stack re-run, and a five-cycle functional check against the golden article's insertion and release force band. No new gate evidence needed |
| B — screened deviation | Material lot change, printer change, slicer profile change, or any repair or rework of a load-path part, with every feature still inside tolerance | Class A, plus a run-in before the article is used for gate evidence and an explicit note in the P0-A evidence packet naming what changed |
| C — re-qualification | Any critical stack's as-built worst case at or below its minimum; any feature outside its tolerance; any geometry, material, or fastener change; a new revision | New article revision and a fresh P0-A run set. The new article becomes the golden article only if it passes |

Class C is the default when the class is ambiguous. A deviation whose class is
argued rather than measured is a Class C.

The boundary between A and B is deliberately narrow: FDM output tracks the
machine and the spool, not the STL. A lot change is not a paperwork event.

## Re-measurement and wear

The as-built set is taken twice for each article: pre-cycle and post-cycle,
distinguished by the `notes` column. The delta is the wear record and it is the
only quantitative evidence P0-A produces about whether the mechanism degrades —
the cycle sheet records outcomes, not dimensions.

Any post-cycle feature that has moved outside its tolerance is a Class C event
for that article and a finding against the design, even if the article passed
every functional criterion. A keeper slot that has widened 0.2 mm across the
600-cycle life test has taken 0.1 mm per side off a 0.9 mm retention ledge and
will keep taking it through P0-B and P0-C, which is a design finding whether or
not the article held every load on the day.

## Custody and retirement

The golden article is not flight hardware and not a spare. It is not cycled
again after its P0-A run set, and it is only unbagged to resolve a measurement
disagreement or to re-measure with a better instrument. A reference whose
dimensions keep moving is not a reference.

It is retired when its revision is superseded. The record is not retired: the
as-built set, photographs, and evidence packet stay in the repository, because a
later article's deviation is measured against numbers, not against a part in a
drawer.

## What the golden article is not

- It is not a qualification unit. P0-A is a screening gate, and the 5 N and 1 N
  loads are screening loads, not qualification loads.
- It is not an acceptance datum for production. One article establishes no
  process capability; the as-built sets accumulate toward that, and until they
  do, the tolerances in `aiur/tolerance.py` stay labelled as engineering targets.
- It is not a substitute for the stack. An article that measures well can still
  sit inside a stack that fails at worst case, which is exactly the state Rev-A
  is in today.
