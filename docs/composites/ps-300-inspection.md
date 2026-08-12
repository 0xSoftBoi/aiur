# PS-300 — Inspection and acceptance specification

Status: process specification, issue A, opened 2026-08-12
Scope: dimensional, constituent-content and defect acceptance for all
CARRIER-P0 composite parts
Executable source: [`aiur/composites/process.py`](../../aiur/composites/process.py),
[`aiur/composites/spc.py`](../../aiur/composites/spc.py)

Every limit in this specification names what it is protecting. A limit
without a stated consequence gets negotiated away the first time the shop is
behind schedule, and the person negotiating is usually right that *this*
part is fine — which is exactly why the argument has to be about the
mechanism rather than about the part.

## 1. What gets measured, and why these three

Three numbers decide whether a cured panel is the laminate the stress model
assumed. They are not independent — they are three views of the same
consolidation — and all three are cheap.

| measurement | method | what it tells you |
| --- | --- | --- |
| thickness | micrometer map | fibre volume fraction, in the units a drawing uses |
| density | ASTM D792 immersion | void content, by difference against the constituents |
| mass | balance | resin content, and the mass budget |

A shop that measures nothing else still knows whether it is in control.

## 2. Acceptance limits

| characteristic | limit | consequence of exceeding |
| --- | --- | --- |
| void content, general parts | ≤ 2.0 % | interlaminar and compression strength fall with porosity |
| void content, critical parts (CS-400) | ≤ 1.0 % | a void-driven interlaminar failure in the retention path drops an aircraft |
| fibre volume fraction | 0.50 – 0.62 | resin-rich is heavy and soft; starved hides dry fibre that no inspection reliably finds |
| cured ply thickness | nominal ± 10 % | feeds the capture-chain tolerance stack and the mass budget |
| moulded angle | nominal ± 0.25° | see [tooling](tooling.md); a closed throat angle eats lateral capture margin |
| void content, negative | ≥ −0.2 % | negative porosity is impossible; the inputs disagree and must be re-checked |

That last row is not a joke. Void content is computed as a *difference*
between a measured density and a theoretical one, so an error in the assumed
fibre content or in the fluid density shows up as impossible porosity. A
panel record that produces one is telling the shop to re-check its inputs,
not to celebrate.

Using 1.0000 g/cm³ for water instead of 0.9970 at 25 °C introduces a 0.3 %
density error, which reads as 0.3 % of spurious void content — a fifth of
the whole acceptance limit, produced by a rounding nobody records.

## 3. Constituent content

Fibre volume fraction comes free with a caliper. For `n` plies of known
fibre areal weight `W`:

```
Vf = n W / (rho_fibre * t)
```

A panel that measures thick is a panel with less fibre in it, and its
stiffness is down in exactly that proportion. This is the cheapest process
measurement in composites and the most neglected.

Void content follows ASTM D2734: compare the panel's measured density
against the void-free density its constituents imply, and the deficit is
air.

Where a matrix digestion (ASTM D3171) is available it replaces the assumed
fibre content in the void calculation, which removes the dependence on an
assumed areal weight and is the more defensible route.

### Report the stiffness knockdown, not just the pass

A panel can sit inside every limit above and still be several percent softer
than the model assumed. `evaluate_panel` reports
`stiffness_ratio_vs_nominal` for exactly this reason — the stress analyst
needs to hear "accepted, and 4 % soft", not just "accepted".

## 4. Inspection points

Attached to the traveler where the evidence still exists:

| step | inspection | why here |
| --- | --- | --- |
| OP-35, before bagging | **HOLD** ply count and every ply's orientation | after the bag goes on this is unverifiable for the life of the part |
| OP-40, before the oven | **HOLD** bag leak rate | a leak cannot be detected after the cure |
| OP-70, after demould | thickness map, moulded angle, mass, density coupon from the trim offcut | the part exists and the offcut is still attached to its history |
| OP-80 | **HOLD** constituent reduction and disposition | a part is not released to assembly on an operator's signature alone |

The OP-35 hold is the one that matters most, and it is the one most often
skipped. No cured-part inspection method distinguishes a ply laid at 0° from
one laid at 45°. Ultrasonic inspection finds porosity and delamination; it
cannot read fibre angles. Once the bag is on, the only record of what is
inside the part is a signature.

## 5. Defect disposition

| defect | disposition |
| --- | --- |
| porosity above limit | reject; investigate against the debulk and pressure-window controls |
| out-time exceedance | reject — the material was wrong before the part was made |
| ply count or orientation error found before cure | rework |
| ply count or orientation error suspected after cure | reject; it cannot be disproved |
| moulded angle out of tolerance | first article: correct the tool. Subsequently: reject |
| surface porosity or dry fibre on a moulded face | reject on CS-100 (aircraft-contact surface), review elsewhere |

A nonconformance is *computed* from the traveler record rather than
asserted, and the evaluator distinguishes critical findings — which reject
the part — from minor ones, which route it to review.

## 6. Statistical control

Conformance answers "did this part work". It cannot answer "will the next
twenty", and only the second question lets a programme commit to a build
schedule.

| target | value |
| --- | --- |
| Cpk, general characteristics | ≥ 1.33 |
| Cpk, critical characteristics | ≥ 1.67 |

Control charts come **before** capability. Capability describes a stable
process; a drifting process has no single capability, so the chart detects
the drift and only then does the number mean anything.

The most useful diagnostic in the set is the gap between Cp and Cpk. High Cp
with low Cpk is a process that is precise and mis-aimed — half a day of
adjustment. Low Cp is a process that is simply too variable — weeks of work.
Telling them apart before starting is the point.

Yield is tracked as **rolled throughput yield**, not final yield. A cell
with five 95 %-yielding steps reports 95 % five times and delivers 77 %, and
the difference is rework nobody budgeted. The illustrative cell in `spc.py`
shows a 95 % final yield hiding a 65.5 % rolled throughput yield — 29.5 % of
parts going through a step twice.

## 7. Basis

Every limit here is an explicitly labeled engineering target, chosen from
ordinary aerospace practice, except the moulded-angle tolerance, which comes
from what the [capture-chain tolerance stack](../../aiur/tolerance.py) can
absorb.

The void limits will not become meaningful until CP-04 in the
[coupon plan](allowables.md) measures short-beam strength as a function of
porosity on this programme's own laminates. Until then, "≤ 2 %" is an
industry convention this programme has adopted, not a limit it has derived.
