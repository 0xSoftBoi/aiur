# Carrier sizing: the smallest airship that recovers this aircraft

Status: sizing study and decision, opened 2026-09-14  
Executable: `python -m aiur.envelope`, `python -m aiur.p0`; tests in
`tests/test_envelope.py` and `tests/test_p0.py`

## Decision

The CARRIER-P0 reference article moves from the 4.5 m RC-Zeppelin
B100-I-450-VT (~5.5 m³, vendor-rated up to 1.0 kg) to the **RC-Zeppelin
3.5 m indoor blimp (~4 m³, vendor-rated up to 500 g)**. It is the smallest
article in the vendor's catalog whose rated payload closes the two-aircraft
P0 mass budget under the reserve rule below, and the selection is computed
from the live budget rather than declared, so a budget that outgrows the
vehicle fails a test.

| | 4.5 m (previous) | 3.5 m (reference) |
| --- | ---: | ---: |
| Helium volume (vendor) | ~5.5 m³ | ~4 m³ |
| Rated payload (vendor) | 750 g – 1.0 kg | 400 – 500 g |
| P0 carried allocation | 425.4 g | 425.4 g |
| Reserve remaining | 574.6 g | 74.6 g |
| Reserve required (rule) | 100 g | 50 g |
| RTF price, 2026 | $2,820 | $2,644 |
| Volume-matched diameter | 1.53 m | 1.48 m |
| Fineness ratio (drawn profile) | 2.9 | 2.4 |

The 4.5 m article stays in the catalog as the fallback. The executable
selection returns it automatically if the vendor's *lower* payload figure
for the 3.5 m article (400 g) turns out to be the real rating, or if the
dock and probe masses measured at P0-A push the allocation past the rule.

## Why the 4.5 m article was oversized

"Size the carrier for this drone" reads as if the aircraft drives the
budget. It does not. A guarded Crazyflie 2.1 Brushless is 37 g; with its
Lighthouse deck and capture probe it is 47.7 g as flown, and two of them are
95.4 g, under a quarter of the 425.4 g P0 allocation. The other three
quarters are carrier-side: the 180 g active dock, 50 g of localization and
telemetry, and a 100 g wiring and mounting reserve. **A carrier sized for
this aircraft is sized for its dock.** The previous article carried a 575 g
reserve on top of that — more spare lift than the entire payload — which is
comfortable but is also a bigger envelope, more helium per fill, a larger
hall, and a vehicle two people cannot easily walk through a door.

What smaller buys, for the program that has to run P0-C in a real room:

- **Helium.** ~4 m³ per fill instead of ~5.5, a 27% smaller consumable on
  every top-up, and a smaller inventory in the room for HAZ-009.
- **Room.** A 3.5 m hull on a 3.4 m tether needs a hall roughly a metre
  shorter in every direction; the keep-out ellipsoid the twin enforces
  shrinks with it.
- **Handling.** Envelope area falls from ~17.7 m² to ~13.6 m². The
  envelope is the part that gets damaged on the ground.
- **Honesty of the budget.** A reserve five times the largest single step
  the vehicle sees was hiding the fact that nobody had written down what the
  reserve is *for*. It now has a rule.

What smaller costs:

- **Payload halves.** The vendor rates the 3.5 m article at half the 4.5 m
  figure while its volume is only 27% less; envelope skin scales with length
  squared and gas with length cubed, and the vendor's own systems do not
  shrink at all. The reserve is 74.6 g, not 574.6 g. It still clears the
  rule with margin, but it no longer absorbs a careless allocation.
- **Trim step.** Capturing or releasing one aircraft changes dead weight by
  ~0.47 N against a modelled 0.3 N vertical thrust budget. That was already
  true on the 4.5 m article (the number is the aircraft's, not the hull's);
  it is relatively larger on a lighter vehicle and remains the flagged
  correlation item for P0-C (TLYF-B-02).
- **Gust response.** A smaller hull has less inertia per unit drag, so it
  answers a gust faster. The twin's outdoor sweep below says this does not
  move the collapse point at P0 scale.

## The reserve rule

The old text said "the prototype should not be engineered against its last
gram" and left it there. The rule is now explicit and executable
(`aiur.envelope.ReservePolicy`, `aiur.p0.reserve_policy`):

> Rated payload minus carried allocation must be at least **10% of the
> rating** *and* at least **one aircraft's dead-weight step as flown**
> (airframe + deck + probe, 47.7 g).

The fraction absorbs ballast-trim granularity and the vendor's rounding.
The floor is physics: the carrier must be ballast-trimmable through a full
release/recovery cycle, so it has to be able to give up one aircraft's
weight and still be trimmed. On the 3.5 m article the required reserve is
50 g (the fraction governs) against 74.6 g remaining.

The minimum rating that closes the current budget is 473 g. That is why the
3 m article (300–400 g) does not close and the 3.5 m one does, and why the
vendor's two figures for the 3.5 m article matter: 500 g closes, 400 g does
not. Two procurement actions follow, and both are in the BOM row:

1. Obtain the payload rating for the specific delivered article in writing
   before ordering.
2. Re-run `python -m aiur.p0` against the dock and probe masses measured at
   P0-A before ordering. The article is bought for P0-C; the masses exist
   after P0-A.

A third check closes the loop on the vehicle itself: **P0-MASS-004**
requires the free lift of the delivered carrier to be measured at neutral
trim with the P0 payload fitted, with helium purity and room temperature
recorded, before the recovery campaign flies.

## What was researched

### The vendor ladder

RC-Zeppelin's indoor range, read 2026-09-14
([catalog](https://www.rc-zeppelin.com/indoor-rc-blimps.html),
[prices](https://www.rc-zeppelin.com/price-list.html)):

| Article | Volume | Vendor payload | Film | RTF |
| --- | ---: | ---: | ---: | ---: |
| 1.5 m | ~1 m³ | up to 100 g | 50 µm PU | $1,640 |
| 2 m | ~2.5 m³ | not quoted | PU | $1,880 |
| 3 m | ~4 m³ (shared) | 300–400 g | 100 µm PU | $2,450 |
| **3.5 m** | ~4 m³ (shared) | 400–500 g, "up to 500 g" | 100 µm PU | $2,644 |
| 4.5 m | ~5.5 m³ | 750 g (catalog) / up to 1 kg (product page) | 100 µm PU | $2,820 |
| 5 m | ~6.5 m³ | 1.2 kg | 100 µm PU | $3,230 |

Three things to notice. The vendor does not publish diameter for any
article. The volumes are rounded and the 3 m and 3.5 m articles share one
figure, so the volume is a design input with perhaps ±15% on it. And the
vendor's own pages disagree about the 4.5 m rating by a third, which is why
the catalog in `aiur/envelope.py` carries a high and a low figure per
article and the selection can be run against either.

Every article is a fat hull. Solving the drawn profile (prismatic
coefficient 0.66) for the vendor's volume gives fineness ratios of 1.3 (the
1.5 m article, which is nearly a sphere and whose vendor volume is probably
the roundest of the lot) through 2.4 (3.5 m) to 3.2 (5 m). Airship drag
minima sit near a fineness of 3–4 and large airships run higher still (the
Hindenburg was ~6). For an indoor vehicle that station-keeps at walking
pace the drag penalty of a fat hull is irrelevant and the shorter length is
worth having; it is one more reason the program should not carry an
outdoor design's instincts into P0.

### The physics, and how far the vendor rating sits below it

`aiur/envelope.py` computes net lift from first principles: ideal-gas air
and helium densities (1.204 and 0.166 kg/m³ at 20 °C, so 1.04 kg/m³ of
pure-helium net lift per cubic metre; 1.01 at the 97% fill purity assumed),
a body-of-revolution hull on the same profile `tools/carrier_model.py`
draws (so volume, wetted area, and the renders share one curve), 100 µm
polyurethane film at 120 g/m² with a 15% construction factor for seams,
tapes and fittings, fins at a tenth of the hull area, and a 600 g allocation
for the vendor's gondola, motors, battery and radio.

| Article | Gross lift | Physics net lift | Vendor rating | Rating ÷ physics |
| --- | ---: | ---: | ---: | ---: |
| 2 m | 2.5 kg | 0.41 kg | (0.2 kg) | (0.5) |
| 3 m | 4.0 kg | 1.27 kg | 0.4 kg | 0.32 |
| 3.5 m | 4.0 kg | 1.17 kg | 0.5 kg | 0.43 |
| 4.5 m | 5.5 kg | 2.00 kg | 1.0 kg | 0.50 |
| 5 m | 6.5 kg | 2.60 kg | 1.2 kg | 0.46 |

The vendor rates every article at 30–50% of what the gas can lift after
the envelope, consistently across the ladder. That consistency is the
useful finding: it says the physics model is not missing a term that scales
strangely, and that the rating carries the vendor's ballast, trim and margin
policy, which the program does not get to see. It is also why the repository
rule stands: **flight hardware is budgeted against the rated payload, never
against theoretical lift.** The physics is the sanity bound that catches a
transcription error (a test asserts every rating sits below its physics
ceiling), and it is the only tool available for sizes the vendor does not
sell.

### Where the skin wins: the length sweep

Skin scales with length squared, gas with length cubed, and the systems do
not scale at all, so there is a length below which a hull cannot lift
itself. At fineness 3 on 100 µm film with the vendor's 600 g of systems:

| Length | Volume | Net lift |
| ---: | ---: | ---: |
| 2.0 m | 0.46 m³ | −0.70 kg |
| 3.0 m | 1.56 m³ | −0.31 kg |
| 3.5 m | 2.48 m³ | +0.16 kg |
| 4.0 m | 3.69 m³ | +0.85 kg |
| 4.5 m | 5.26 m³ | +1.83 kg |

That is why the vendor's small articles are fat (fineness 1.3–2.4: a fatter
hull at the same length holds far more gas for a little more skin) and why
the 1.5 m article carries 50 µm film. It is also the executable answer to
TOY-004/005 in [verticals/toys.md](verticals/toys.md): a 2 m toy hull only
goes positive on 50 µm film with ~150 g of systems, netting ~115 g gross
for dock, aircraft and avionics. The 180 g P0 dock does not fit in that
number and a 50 g toy dock does. The toy vertical's lift budget now closes
or fails in the same model as the P0 article.

### Airship design references used

- **Hull form.** The drawn profile is GNVR-style (NAL India's parametric
  airship family: nose radius, position of maximum section, prismatic
  coefficient, fineness). Cp 0.66 sits inside the 0.6–0.7 band real hulls
  occupy. Hoerner's volumetric drag relations and later refinements put the
  pressure-drag minimum for bodies of revolution near a fineness of 3, with
  friction drag pushing the practical optimum toward 4; stratospheric and
  conventional design studies (Alam & Pant; the tri-lobed comparison in the
  *Aeronautical Journal*, 2021) use exactly these relations at concept
  stage. None of that changes P0's decision; it explains why the vendor's
  indoor hulls are fatter than a textbook airship and why that is fine
  indoors.
- **Envelope materials.** 100 µm polyurethane at ~120 g/m² is the vendor's
  standard film; TPU has the lowest helium permeability of the practical
  film options (vendor and industry figures: under 1% of volume per day),
  which is why the program has never contemplated Mylar or coated nylon at
  this scale. Multilayer laminates for large hulls run 150–480 g/m² and are
  not relevant below 5 m.
- **Lift.** Standard lift tables and airship practice: pure helium at
  sea level lifts ~1.05 kg/m³; practical purity, warm rooms and top-ups
  all reduce it, and historical designers conservatively planned on ~88% of
  the ideal. The module's 97% fill purity is an allocation to be replaced by
  the P0-MASS-004 measurement.
- **Small research blimps.** The Georgia Tech Miniature Autonomous Blimp
  (a ~0.7 m saucer envelope carrying under 80 g of gondola) and the RGBlimp
  family (125 L of helium for ~152 gf of buoyancy, i.e. ~1.2 g/L) are the
  indoor-robotics reference points at the toy end of the sweep; both sit
  exactly where the model says a sub-metre envelope must live, with a
  payload of tens of grams and nothing resembling an actuated dock.
- **Docking on blimps.** Goldschmid & Ahmad (Stuttgart, 2025,
  [arXiv 2511.19135](https://arxiv.org/abs/2511.19135)) is the first
  multi-rotor docking on a blimp shown outside simulation. Its central
  finding is the one this study has to respect: the blimp's gust response
  is slow, long-lived and hard to predict, the hull is an obstacle the
  multirotor must avoid except at the port, and the approach corridor has to
  close when a gust is detected. A smaller hull responds faster; the twin's
  hull-proximity evasion reflex and its wind sweep are the program's answer
  and they are re-run below.

## What the digital twin says about the smaller carrier

`CarrierParams` in `aiur/sim/bodies.py` now derives from the article:
semi-axes 1.75 × 0.739 × 0.739 m (volume-matched spheroid), effective mass
6.5 kg (displaced air at 20 °C times the same 1.34 added-mass factor the
4.5 m calibration used), linear drag scaled by frontal area to 1.40 N per
m/s, thrust unchanged (the vendor's motor set does not shrink with the
hull), and the dock hanging the same 0.286 m fixed standoff under the hull
at z = −1.025 m.

Re-run at seed 1 on 2026-09-14, against the previous 4.5 m parameters on
the same commit:

| Study | 4.5 m | 3.5 m |
| --- | --- | --- |
| SIL-B / SIL-C / SIL-D gates (200/200/80 episodes) | pass | pass, 100% capture, 0 strikes, 0 unsafe fault outcomes |
| Outdoor wind, capture rate at 0 / 0.5 / 1.0 / 1.5 m/s | 100 / 90 / 10 / 0 % | 100 / 93 / 3 / 0 % |
| Carrier wake, capture at 0.05 / 0.10 / 0.15 / 0.20 / 0.40 m/s downwash | 100 / 97 / 73 / 67 / 0 % | identical |
| Degraded sensing, 10× / 30× Lighthouse noise | 100 / 63 % | 100 / 63 % |

The wind collapse stays between 0.5 and 1.0 m/s mean wind, inside sampling
noise of the 4.5 m result; the smaller hull's lower inertia is matched by
its lower drag, and the collapse is set by the aircraft's tracking against
carrier drift, not by the hull's size. The wake sweep is identical because
the downwash model acts on the aircraft, not the carrier. Nothing the twin
gates on moves. What the twin still does not model is unchanged and now
matters slightly more on a lighter vehicle: the trim transient on capture
and release (TLYF-B-02).

## What this changes elsewhere

- `aiur/p0.py`: `CarrierSpec` reads the article; `selected_article` and
  `reserve_policy` are new and tested; P0-MASS-003 in the requirement
  matrix names the rule, and P0-MASS-004 (measured free lift) is added.
- `aiur/sim/bodies.py`: carrier parameters derived as above.
- `aiur/hazards.py`: HAZ-003, HAZ-009 (helium inventory ~4 m³), HAZ-012.
- `docs/prototype-p0.md`, `README.md`, `docs/P0_EXECUTION_GATE.md`,
  `docs/tlyf-exceptions.md`, the verticals, `hardware/bom.csv`.
- `web/lib/carrier-spec.ts` and the live Three.js model, whose layout is
  now placed relative to the hull rather than at coordinates composed for
  4.5 m.
- `tools/carrier_model.py`, `render_carrier.py`, `carrier_stage.py`,
  `animate_carrier.py`: the vehicle is built from the article, with stations
  as fractions of length (the fractions reproduce the 4.5 m layout to the
  millimetre, checked by importing the module against a stub `bpy`). **The
  rendered stills in `web/public/renders/` and the breakdown film were
  produced for the 4.5 m article and have not been re-rendered**; the film's
  camera keyframes follow the dock station but have not been re-framed for
  the shorter hull. Both are flagged in the tool docstrings.

## Open items

1. Vendor rating in writing for the delivered 3.5 m article (BOM).
2. Re-run selection against measured P0-A masses before ordering (BOM,
   P0-MASS-003).
3. Measure free lift on delivery (P0-MASS-004).
4. Re-render the site stills and re-frame the film on the 3.5 m vehicle.
5. The carrier trim transient across a capture/release cycle remains
   unmodelled in the twin and is the first thing P0-C should measure.
