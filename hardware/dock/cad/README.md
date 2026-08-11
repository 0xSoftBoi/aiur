# P0-A Rev-A fabrication CAD

This directory contains the reproducible first fabrication geometry for the CARRIER-P0 recovery dock. It is deliberately simple enough to regenerate with stock Python; the STL files are outputs, not the source of truth.

**Requires Python 3.9 or newer.** The generator uses builtin generic
subscripting (`tuple[float, float, float]`) and `X | None` annotations, so on
an older interpreter it fails at import with
`TypeError: 'type' object is not subscriptable` rather than with a version
message. macOS still ships 3.8 as `python3` in some environments; check with
`python3 --version` before printing anything.

Generate and validate the pack from the repository root:

```bash
python hardware/dock/cad/generate_rev_a.py
python -m unittest discover -s tests -v
```

The generator emits:

- `p0a_funnel_rev_b.stl` — Ø180 mm thin-wall funnel, Ø16 mm throat, Ø70 mm drill-after-print flange;
- `p0a_probe_head_rev_b.stl` — rounded coupon head: Ø12 mm belt (what the funnel guides), **Ø9 mm seat** (the only surface the keeper bears on), Ø3.2 mm bore for a Ø3 mm mast;
- `p0a_keeper_rev_b.stl` — 2.5 mm sliding fork with a **5.2 mm** slot around the nominal Ø3 mm mast, tines reaching 5.0 mm past the dock axis. The slot was widened from Rev-A's 4.2 mm and must not be reworked back toward it: it sets both the mast clearance and, with the seat, the retention ledge;
- `p0a_drill_template_rev_b.svg` — 1:1 four-hole M3 template on a 40 mm square;
- `p0a_cross_section_rev_b.svg` — dimensioned cross-section, every callout derived from the revision parameters;
- `p0a_linkage_template_rev_b.svg` — 1:1 pin-hole template for the crank and link, with a 50 mm check line;
- `p0a_rev_b_manifest.json` — dimensions, mesh checks, volume, and a solid-PETG mass estimate.

Every emitted STL is checked for degenerate faces and non-manifold edges before it is written.

## Build order

### A0 — geometry coupon

1. Print the funnel in PETG or PA12. For FDM, start at 0.20 mm layers and at least three effective wall lines at the 1.2 mm mouth section. Record printer, nozzle, material, orientation, slicer profile, and finished mass.
2. Print the keeper flat in PETG/PA12 with a solid section. Deburr the slot; do not enlarge it until the actual Ø3 mm mast is measured.
3. Print the probe head as a solid part. Bond it to a sacrificial Ø3 mm GFRP/CFRP mast for the bench coupon only.
4. Print `p0a_drill_template_rev_b.svg` at exactly 100%. Measure the 50 mm check line with calipers before using it. Drill the four flange holes Ø3.2 mm only after the funnel is printed.
5. Install the keeper in rigid guides and translate it manually through at least **13 mm** of travel (10.41 mm is the bare geometric clearance; 13.0 mm is the commanded Rev-B stroke and carries the ±0.4 mm delivered-stroke tolerance — see hardware/dock/keeper-drive.md). The guides and closed stop react load; the actuator must never be the structural retention path.
6. Confirm the Ø12 mm head enters the throat without a hard catch and that the keeper positively traps the neck under the head.

A0 is a fit article. It cannot pass P0-A and it must not be flown.

### A1 — instrumented P0-A article

Add the actuator, passive first-capture element, `S1`, `S2`, wiring, fasteners, and a swappable actuator bracket. Then weigh the complete dock and probe and execute [`../p0a-bench.md`](../p0a-bench.md). A design revision or hand-modified load-bearing part starts a new evidence set.

## Material and mass rules

- Do not use a brittle PLA print as P0-A load evidence. PETG is the starting FDM material; PA12 is a reasonable printed alternative.
- The generated mass figure assumes the modelled solid material is PETG at 1.27 g/cm³. It is an estimate, not measured evidence.
- Keep the printed carrier-side geometry under a **110 g development sub-budget**. That leaves 70 g inside the existing 180 g dock allocation for the 18 g actuator, guides, sensors, bracket, wiring, and fasteners.
- The complete flight-side probe remains ≤8 g. The generated probe head is only one component of that allocation.

## Interfaces intentionally not frozen

The Rev-A STL pack does **not** invent:

- a Crazyflie flight-probe base or PCB fastener pattern;
- a final spring collet/compliant throat insert;
- an XL330 mounting bracket or linkage geometry;
- a carrier structural-rail interface.

Those dimensions close from physical parts and measured fit. The bench adapter's 4×M3/40 mm-square pattern exists only to make the first article fixtureable.

## Inspection before load screening

Reject the print before testing if the funnel has a through-crack, incomplete wall, delamination, a sharp approach-volume edge, or a damaged flange. Reject the keeper for a cracked tine, warped guide surface, or a slot that can pass the Ø12 mm head. Keep propellers removed for all P0-A work.
