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

`traveler-template.csv` is generated from the step list in
`aiur.composites.traveler`, so the paper and the executable definition cannot
drift apart. Regenerate it rather than editing it:

```
python -m aiur.composites.traveler   # prints the authoritative step list
```

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
