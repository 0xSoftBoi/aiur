# Composites shop-floor records

Templates for the records the composites process specifications require.
Every column exists because something in
[`aiur/composites/`](../../aiur/composites/) reads it or because a
[process specification](../../docs/composites/README.md) names it.

| template | filled in at | read by |
| --- | --- | --- |
| [`traveler-template.csv`](traveler-template.csv) | every step of every part | `aiur.composites.traveler.evaluate_traveler` |
| [`out-time-log-template.csv`](out-time-log-template.csv) | every freezer issue and return | the out-time controls in PS-100 |
| [`panel-record-template.csv`](panel-record-template.csv) | after demould and inspection | `aiur.composites.process.evaluate_panel` |
| [`cure-run-template.csv`](cure-run-template.csv) | every oven run | PS-200 acceptance, and DOE-1 |
| [`tool-log-template.csv`](tool-log-template.csv) | tool build, then every cure | the spring-in compensation loop |
| [`coupon-log-template.csv`](coupon-log-template.csv) | every test specimen | `aiur.composites.allowables.evaluate_coupon_set` |
| [`defect-log-template.csv`](defect-log-template.csv) | every nonconformance | `aiur.composites.disposition.disposition` |

`traveler-template.csv` is generated from the step list in
`aiur.composites.traveler`, so the paper and the executable definition cannot
drift apart. Regenerate it rather than editing it:

```
python -m aiur.composites.traveler   # prints the authoritative step list
```

## The ply book

[`plybook/`](plybook/) holds the generated 1:1 flat patterns and layup
sequences — the sheets a laminator actually works from. They are generated
from the laminate schedules and the flat-pattern development, and a test
fails if the committed sheets have gone stale against the analysis:

```
python hardware/composites/plybook/generate_plybook.py
```

Print at 1:1 and **measure the check line before cutting**. A printer that
silently scales to fit turns a controlled drawing into a confident lie.

## The tooling package

[`tooling/`](tooling/) holds the four aluminium moulds as a package a machine
shop can quote and cut: a solid model and an A3 sheet per tool, one RFQ line
each, and a manifest giving every dimension its tolerance, its feature class
and the analysis it came from.

```
python hardware/composites/tooling/generate_tools.py
```

**These tools are deliberately not cut to the part dimensions.** Every
moulding dimension carries the thermal-expansion compensation, and every
corner is cut open by its predicted spring-in. The sheets say so in red.
[Read the package notes](tooling/README.md) before sending anything out.

The layup sheets list plies in **lay-down order, ply 1 against the tool**.
That is the reverse of the design stack, which is written top-surface-first;
the sheet prints the reversal so nobody has to perform it at the cutting
table.

## One column that decides a disposition

**`plies_above`.** A delamination's depth, not just its size. The plies
above a delamination buckle as a small plate, and a sublaminate one ply
thick has almost no bending stiffness — so a 4 mm delamination one ply down
needs repair while the same 4 mm at mid-thickness is acceptable. A defect
record without a depth cannot be dispositioned at all, and the evaluator
says so rather than guessing.

## Two columns that look like bureaucracy and are not

**`cumulative_out_time_h`.** Prepreg advances at room temperature and the
clock does not reset when the roll goes back in the freezer. Exceeding the
limit gives a resin that no longer flows to specification: the part comes
out porous and starved, the cure looks normal, and nothing in the finished
part records why. It is the most commonly falsified number in composites
manufacturing precisely because it is inconvenient.

**`cut_scale_factor`.** Tools in this programme are cut away from nominal to
compensate for thermal expansion — an aluminium tool for a 300 mm part is
cut 0.97 mm larger than the part drawing. A machinist who works to the part
drawing produces a tool wrong by six times the tolerance, and it will
measure correct against every dimension he was given.
