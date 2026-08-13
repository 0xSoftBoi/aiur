# Tooling package — for the machine shop

Four aluminium moulds for the CARRIER-P0 composite parts. This directory is
the whole quote-and-cut package: a solid model per tool, an A3 sheet per
tool, one RFQ line per tool, and a manifest that says where every dimension
came from.

Regenerate it — never edit `generated/` by hand:

```
python hardware/composites/tooling/generate_tools.py
python hardware/composites/tooling/generate_tools.py --check   # CI runs this
```

## Read this before you cut anything

**These tools are deliberately not cut to the part dimensions.**

A part is moulded at 180 °C and inspected at 20 °C. Aluminium expands about
23.6 µm/m/K; the laminates here are 2.0–2.5 µm/m/K. Over that 160 K cooldown
the tool moves roughly ten times as far as the part does, so a tool cut to
the part drawing makes a part that lands 0.34 % small. On the throat cup's
Ø40 throat that is **0.135 mm — 2.7 times the ±0.05 mm the moulding surface
is toleranced to**, from nothing but temperature.

Every moulding dimension in this package already carries the correction. The
scale factor is printed in red on every sheet and repeated in
`tooling_manifest.json`. A machinist who spots the discrepancy against a part
drawing and helpfully corrects it back scraps the tool — so the part drawings
are deliberately *not* in this directory.

The corners carry a second, separate correction. A laminate corner closes as
it cools, because the laminate contracts more through its thickness than
along its fibres, so each moulded corner is cut **open** by the predicted
spring-in: 0.379° on the throat cone, 0.795° on the tine root. The tine die
is therefore a 90.795° corner, not a 90° one. That is not a mistake either.

## What is in `generated/`

| file | what it is |
| --- | --- |
| `t100.stl` `t100_sheet.svg` | throat cup mould — female, revolved cavity |
| `t200.stl` `t200_sheet.svg` | boom mandrel — male, extruded crown |
| `t300.stl` `t300_sheet.svg` | keeper tine die, cavity half |
| `t301.stl` `t301_sheet.svg` | keeper tine die, punch half |
| `rfq.csv` | one quotable line per tool: stock, removal fraction, tolerances, finish |
| `tooling_manifest.json` | every dimension with its tolerance, feature class and basis |

**The STL is the master geometry.** The sheet carries tolerances, feature
classes, secondary operations and notes; it does not redefine the surface.
Where a sheet dimension and the model disagree, the sheet governs — the model
is faceted, and each sheet states by how much (2–12 µm, always *inside* the
true surface).

The sheets are A3 landscape, 420 × 297 mm, and each states its scale ratio.
Print at 100 %.

## Material and sequence

Aluminium 6061-T651 tooling plate, for all four tools.

1. **Rough** all faces, leaving 1 mm.
2. **Stress relieve.** Machining rolled plate releases the residual stress
   rolling put in it, and a tool that moves after finishing has to be cut
   again. This step is not optional on the throat cup, which removes 43 % of
   its billet.
3. **Finish.** Moulding surfaces 0.4 Ra, all other machined faces 1.6 Ra.

The tools see 200 °C under 690 kPa, repeatedly. 6061 is stable there; it was
selected over P20 tool steel and Invar in a documented trade
([`docs/composites/tooling.md`](../../../docs/composites/tooling.md)) because
after compensation the residual dimensional error is not what separates the
candidates, and mass and lead time are.

## Three rules that are not negotiable

**No marks on a moulding surface.** A moulded face is a cast of the tool. It
reproduces every scribe, stamp, engraving and raster cusp in it. Identify the
tools on an outside face only, and machine cavities with a radial or helical
toolpath — a raster cusp pattern prints straight through a 0.4 mm laminate.

**The seal land is a functional surface.** A scratch across T-100's land is a
vacuum leak, and a leak during cure makes a porous part that no inexpensive
inspection afterwards separates from a good one.

**T-300 and T-301 are a matched pair.** The gap between the two moulding
faces *is* the part thickness, 1.592 mm nominal ±0.03. It matters more than
either half on its own: cut both, close them dry, and shim-check the gap
before either half is accepted. Bore the dowels and closing-bolt holes with
the halves clamped together so they close in register.

## Inspection deliverable

A CMM report covering every dimension the manifest classes as a *moulding
surface* or a *datum* — the free-class dimensions do not need one. Plus a
surface-finish witness on each moulding face.

Secondary-operation features (dowel holes, tapped holes, thermocouple
grooves) are listed on the sheets and are **not** in the solid models.

## What this hardware is for, honestly

The tools are real and quotable. The laminates they mould are a design study:
the programme holds no measured material allowables yet, and the coupon plan
that converts them is written down in
[`docs/composites/allowables.md`](../../../docs/composites/allowables.md).
Cutting tooling before allowables exist is a deliberate sequencing choice —
the tools are needed to make the coupons — not an oversight.
