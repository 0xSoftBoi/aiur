# Tooling and dimensional control

Status: decision memo, opened 2026-08-12
Scope: tool material selection, thermal-expansion compensation, and
spring-in compensation for the CARRIER-P0 composite parts
Executable source: [`aiur/composites/tooling.py`](../../aiur/composites/tooling.py),
[`aiur/composites/springin.py`](../../aiur/composites/springin.py)

A mould is a machine for holding a shape at a temperature the part will
never see again. Everything difficult about tooling for thin high-precision
laminates follows from that sentence.

## 1. A tool cut to the drawing makes a part that is not on the drawing

The tool defines the part at **cure** temperature. The part is inspected at
room temperature. The difference is the CTE mismatch times the cooldown:

| tool material | CTE | error on a 300 mm part | compensation factor |
| --- | --- | --- | --- |
| aluminium 6061 | 23.6 ×10⁻⁶/K | 0.974 mm | 0.996763 |
| tool steel P20 | 12.8 | 0.472 mm | 0.998428 |
| invar 36 | 1.6 | 0.048 mm | 1.000161 |
| carbon tooling laminate | 3.0 | 0.017 mm | 0.999944 |
| epoxy tooling board | 45.0 | 1.969 mm | 0.993479 |

Against a 0.15 mm in-plane tolerance, an uncompensated aluminium tool is
wrong by six times the tolerance and an uncompensated tooling board by
thirteen times.

**Process control that follows directly:** the tool drawing must state its
own scale factor, and it must be obvious on the drawing. A machinist who
works to the part drawing by mistake produces a tool that is wrong by six
times the tolerance and looks correct against every dimension he was given.
This is in [PS-100 §2](ps-100-layup.md#2-tool-preparation) as a verification
step before layup, not as a note.

## 2. The trade, and why the aerospace answer loses

Invar is the aerospace answer to tooling for precision composites. It comes
last here.

Two criteria that belong in an obvious version of this trade are absent, and
their absence is the point. **Temperature capability and durability are
thresholds, not scores.** A tool that survives the cure with headroom to
spare is not better than one that merely survives it, and a tool good for
5000 cures is not better than one good for 500 when the programme will run
forty. Scoring them on a normalised scale is how a trade study elects the
heaviest, slowest, most expensive candidate on the strength of margin nobody
needs — which is exactly what the first version of this study did, returning
tool steel. They are screens now.

Screens: survives a 180 °C cure with ≥ 10 K headroom, and lasts ≥ 40 cures.
Epoxy tooling board is screened out at −60 K of headroom.

Scored, on what actually differentiates:

| criterion | weight | how it is computed |
| --- | --- | --- |
| dimensional robustness | 0.35 | residual error after compensation, from CTE **uncertainty** |
| thermal responsiveness | 0.25 | part-to-oven lag at a 2 °C/min ramp |
| cost | 0.20 | relative, stated judgement |
| lead time | 0.20 | relative, stated judgement |

| tool | residual error | lag at 2 °C/min | score |
| --- | --- | --- | --- |
| **aluminium 6061** | 0.037 mm | 10.8 K | **0.683** |
| tool steel P20 | 0.023 mm | 20.2 K | 0.581 |
| carbon tooling laminate | 0.046 mm | 6.2 K | 0.478 |
| invar 36 | 0.014 mm | 23.3 K | 0.350 |

The dimensional criterion is scored on the residual error *after*
compensation, not the raw mismatch, and that is the substantive choice in
this study. Compensation removes the mismatch the model knows about and
leaves behind the part the model has wrong, so what matters is not how large
a tool's CTE is but how well it is known. That is why a carbon tooling
laminate — CTE-matched to the part, and therefore apparently ideal — scores
worst on robustness: its CTE is the least certain in the set, because it is
itself a laminate whose layup and fibre content vary, and because it must be
moulded off a master whose error it inherits.

**Selected: machined aluminium, with a computed compensation factor.** It is
the worst dimensional performer of the metals and it wins because its error
is *compensable* and the compensation is arithmetic. Invar's 65 kg/m² of
tool roughly doubles the part's thermal lag — which the
[cure specification](ps-200-cure.md) then has to absorb — and quadruples the
lead time, in a programme whose whole point is iteration speed.

The tool's areal heat capacity is not a separate concern from the cure
model; it is an *input* to it, and the same number feeds both.

## 3. Spring-in

A cured part does not come off its tool at the angle it was moulded at.
Every enclosed corner closes up, and the part is not defective — the tool
is.

Two mechanisms, both from the same asymmetry: a laminate is fibre-dominated
in plane and resin-dominated through the thickness. On cooldown the corner's
arc shrinks by the in-plane CTE (about 2.6 ×10⁻⁶/K) while its thickness
shrinks by the through-thickness CTE (about 40 ×10⁻⁶/K), and a shorter
radius across a nearly constant arc is a smaller angle. Cure shrinkage after
gelation does the same thing, and does it whatever the cure temperature —
which is why a low-temperature cure reduces spring-in but never removes it,
and why a programme that switches resins to fix a distortion problem is
often disappointed.

Predicted, from Radford's expression:

| part | feature | angle | thermal | chemical | total | tool cut to |
| --- | --- | --- | --- | --- | --- | --- |
| CS-100 | throat cone half-angle | 45° | 0.260° | 0.107° | 0.367° | 45.367° |
| CS-100 | flange to cone | 90° | 0.520° | 0.214° | 0.734° | 90.734° |
| CS-300 | rail web to cap | 90° | 0.457° | 0.226° | 0.684° | 90.684° |
| CS-400 | tine root bend | 90° | 0.553° | 0.224° | 0.777° | 90.777° |

Every one of these exceeds the 0.25° tolerance, so every one needs
compensation. That is the expected state, not a problem: it means the model
did its job before the tool was cut.

Each corner's consequence is recorded with it. A closed throat angle narrows
the funnel and eats lateral capture margin straight out of the tolerance
stack. A closed flange corner opens a gap at the bond line, which the
adhesive fills with a thick bondline and a weak joint. A closed tine root
moves the retention ledge, which is the critical dimension in the whole
capture chain.

### The third mechanism, and why it is carried as zero

**Tool-part interaction** is real, is often larger than either mechanism
above on a thin part, and has no closed form. The tool grips the laminate as
it heats and shears the outer plies, locking in a stress that releases on
demould — as warp in flat regions as well as angle change at corners. It
depends on the release agent, the tool surface, the bag pressure and the
ramp rate: which is to say it depends on the shop, not on the material.

It is carried as an explicit allowance of **zero**, with DOE-3 to measure
it, rather than being folded into a fudged CTE where it would silently
corrupt the physics. The model therefore reports an incomplete prediction
honestly instead of an apparently complete one.

## 4. The compensation loop is the deliverable

The prediction sizes the first tool. The first article measures what the
prediction got wrong. `update_from_measurement` returns the tool angle that
makes the second article nominal:

```python
>>> springin.update_from_measurement(
...     tool_angle_deg=90.75, measured_part_angle_deg=90.15, nominal_angle_deg=90.0)
{'measured_spring_in_deg': 0.6, 'corrected_tool_angle_deg': 90.6, 'residual_error_deg': 0.15}
```

A shop that runs this loop needs a good prediction *once* and an accurate
measurement *every time*. A shop that runs only the prediction needs the
prediction to be right — which it will not be until DOE-3 measures the term
that is currently zero.

That loop, not the equation, is what makes moulded angles repeatable.

## 5. The package a shop can quote

The trade, the scale factor and the corner compensation converge on four
tools, and those are generated as a machine-shop package rather than
described:

```
python hardware/composites/tooling/generate_tools.py
```

| tool | moulds | type | what it costs |
| --- | --- | --- | --- |
| T-100 | CS-100 throat cup | female, revolved cavity | 187 × 187 × 56 mm plate, 43 % removed |
| T-200 | CS-200 boom | male mandrel | 66 × 36 × 296 mm plate |
| T-300 | CS-400 tine | matched die, cavity half | 85 × 66 × 34 mm plate |
| T-301 | CS-400 tine | matched die, punch half | 66 × 46 × 34 mm plate |

Each tool ships a binary STL, an A3 sheet, and a row in `rfq.csv` carrying
its stock, removal fraction, tolerances and inspection deliverable. Nothing
in it is drawn by hand: the moulding surfaces are built from the part shapes
in `flatpattern` and `schedules`, scaled by `compensation_factor`, and their
corners opened by `spring_in_deg`. A laminate change moves the tools and a
test fails if the committed drawings have not moved with it.

Three things came out of generating it rather than drafting it.

**The tolerance has to be classed, not quoted.** A single tolerance across a
whole tool is what makes tooling expensive for no structural return. Each
dimension carries a class — moulding surface, datum, sealing, free — and only
the first two buy a CMM report. On T-100 that is four dimensions out of nine.

**A part rule is not a tool rule.** The keeper tine's inner corner has to be
at least two laminate thicknesses, or the outer plies thin over it. The tool
is cut 0.011 mm *under* that, because the compensation shrinks it — and the
part still lands compliant, because it grows back on demould. Checking a tool
dimension against a part rule is exactly the confusion that scraps tools, so
the test that guards this rule converts before it compares.

**The drawing has to know it is a section.** The throat cup mould is an
annulus about a central bore. Sectioned through the axis it is *two* regions,
and drawing it as one closes the bore up and shows solid metal where the
demould push-rod goes. It is the kind of quiet lie that a generated drawing
exists to make impossible, so the generator splits the section and a test
checks that it did.

[The package and the rules that go with it](../../hardware/composites/tooling/README.md)
are written for the shop, not for this document.
