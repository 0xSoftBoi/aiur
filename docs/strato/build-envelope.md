# Building the first envelope

How to turn `hardware/strato/patterns/<design>/` into a sealed hull with cheap
tools. Written for the S1 hull (12 gores of 20 µm LLDPE, about 15.5 m × 0.99 m
each); the same steps apply to any design the generator emits. Regenerate
before cutting — the sizing moves:

```
python -m aiur.strato.patterns --design S1-touch/hull --roll-width 2.0
```

Numbers below are from the S1 run of 2026-11-21 and are examples; the files
are the authority.

**Provenance.** Each step is tagged:

- **[practice]** — documented in a source cited at the end.
- **[judgement]** — our engineering choice, not checked against a build.
- **[unverified]** — looked for a source and did not find one.

Nobody on this project has built this hull yet. Expect the first one to be a
training article, not a flight article.

## 1. What you are building

| Item | S1 value | File |
| --- | --- | --- |
| Gores | 12 identical, 15.48 m long, 957 mm net / 987 mm cut at the widest | `gore.svg`, `gore.dxf`, `gore_stations.csv` |
| Seam | fin seam: two gores face to face, sealed 15 mm in from the edge | SEAL layer |
| Nose cap | flat disc R 145 mm over the gore tips (gores stop where they are 60 mm wide) | `gore.svg` |
| Tail disc | flat disc R 145 mm with collar | `gore.svg` |
| Keel gore | 9 load patches at 1.5 m pitch, relief/fill port 100 mm | KEEL_GORE_ONLY layer |
| Crown gore | rip line 0.73 m for the hot-wire cutter | CROWN_GORE_ONLY layer |
| Fins | 4, each two film skins over two 280 mm TPU-nylon tubes | `fin.svg`, `fin.dxf` |
| Everything | quantities and sizes | `cutlist.csv`, `summary.json` |

The built hull is a 12-sided polygon in section, not a circle, until pressure
and film stretch round it out. Worst case it holds 2.2 % less gas than sized
(`summary.json` → `lobing`). Sixteen gores halve that for a third more seam.
[physics; see the module docstring]

## 2. Space, people, tools

- **Floor.** A clean, smooth indoor floor at least 18 m × 4 m for S1 (gore
  length + 2 m, two gore widths + walkway). Sweep, then mop: grit is what
  holes 20 µm film. The Sandia heliotrope guide asks for 40 × 20 ft for a
  5.8 m balloon and recommends a basketball court. [practice]
- **Socks, no shoes; nothing sharp on clothing** (badges, belt buckles,
  watches). [practice]
- **Two people** for every film-handling step. [practice]
- **Sealer**, one of:
  - Hand impulse sealer, 300–400 mm bar, 2–3 mm flat element, with timer. The
    seam is made bar-length by bar-length with ~20 mm overlap between bites.
    [judgement; travelling impulse/band sealers are the industrial equivalent,
    practice]
  - Temperature-controlled clothes iron or a hobby film-covering iron, PTFE
    (baking/"Teflon") sheet between iron and film, run along a straight-edge
    jig: a 2 m aluminium bar or planed batten as the fence, a strip of
    silicone or PTFE-glass tape on a wooden base as the anvil. A dry clothes
    iron used on its edge is reported to work on thin polyethylene. [practice
    for the iron; the jig is judgement]
- **Seam samples first.** Before touching a gore, make twenty 300 mm test
  seams on offcuts, vary temperature/dwell, and pull them by hand in peel
  (opening the fin) and in shear. A good seam tears the *film next to* the
  seam, not the seam. Too cold peels cleanly; too hot thins and necks the film
  at the seam edge, which is worse because it looks fine. Record the setting
  that works for this roll of film; it changes with batch and room
  temperature. [judgement; the failure modes are standard heat-seal lore, the
  20-sample number is ours]
- **Other:** 30 m steel tape, 2 m straight edge, fine permanent marker (marks
  go in the seam allowance or on the outside only), sharp long scissors,
  25–50 mm clear polypropylene packing tape, 48 mm polyester filament tape for
  load patches, paper masking tape for temporary holds on the *floor only*,
  smooth weights (books, sand socks), a 100–150 mm inline duct fan, a
  manometer (§7).
- **Tape rule.** Never peel tape off film; if tape lands in the wrong place,
  leave it or cut it free and cover any exposed adhesive. [practice]

## 3. Film: what to buy, what to ask

Order by roll area, not hull area. For S1 on a 2.0 m single-ply roll the
generator needs 93 m of roll (186 m²) for the gores and 18 m (36 m²) for fin
skins: 1.39× the hull area for the hull alone, against the 1.18× the cost
model assumes (`summary.json` → `nesting`). Add 15 % for seam samples and one
spoiled gore. A roll whose width is not a near-multiple of the gore cut width
wastes far more (S1 on 1.5 m: 2.08×); either pick the roll to suit or change
`--gores` to suit the roll — the table prints the best gore count per width.

Ask the supplier:

1. Resin and structure: LLDPE or LLDPE-rich co-extrusion, **no** HDPE layer
   (HDPE is stiffer and splits along the machine direction), no recycled
   content, no slip/antiblock loading beyond what winding needs (slip agents
   bloom to the surface and weaken both heat seals and tape). [judgement]
2. Thickness 20 µm nominal and the gauge tolerance (±10 % is typical for
   blown film; ask). [unverified figure]
3. Tensile strength and elongation in machine and transverse directions, and
   dart impact, from the data sheet. `materials.py` assumes 500 N/m ultimate
   for 20 µm; that is 25 MPa, the low end for LLDPE. [estimate in the model]
4. Cold behaviour: brittleness temperature. LLDPE is normally ductile below
   −70 °C; purpose-made balloon film is specified for it, commodity film is
   not tested. If the supplier cannot state it, do a freezer/dry-ice crumple
   test on a sample before committing. [judgement]
5. Supplied as **single-wound sheet** or **lay-flat tube**. Lay-flat tube of
   width W is two plies: cutting through both gives two gores per pass (halve
   the roll length), or slit one edge for a 2 W sheet. Centre-folded sheet
   works the same way. [judgement]
6. Corona treatment: none needed for heat sealing; treated film takes tape
   and marker better. Ask which side is treated.
7. Clear, natural film. Pigment changes the thermal model (`thermal.py`
   assumes α 0.03 / ε 0.18).

Painter's drop film (the Sandia balloon uses 0.31 mil ≈ 8 µm HDPE) is the
cheap practice material for a training article. It is not the flight film.
[practice for its use in solar balloons]

Fin spars are a different material (70 g/m² TPU-coated nylon, hot-air or
iron welded, 20 mm lap); see `cutlist.csv`.

## 4. Marking out

By hand from `gore_stations.csv`; this is how the first one gets made.

1. Roll out one gore length plus 0.5 m. Weight it flat; do not stretch it —
   film marked under tension springs back short. Let it relax 10 minutes.
2. Snap or rule a **centreline** the full length. All widths are measured
   from it, never from the film edge.
3. Mark the **datum** (`s = 0`, the theoretical nose apex) 0.2 m in from the
   end. The gore itself starts at the `nose_cut` row (s = 115 mm).
4. Lay the steel tape along the centreline, zero on the datum, and tape it to
   the floor at both ends. Mark every `s_mm` in the table on the centreline
   without moving the tape (chained measurements accumulate error; one tape
   does not).
5. At each station square off both sides and mark `half_width_mm` (seal line)
   and `half_width_with_allowance_mm` (cut line). Rows marked `infill` are
   extra stations near the nose where the edge curves too fast for 0.5 m
   spacing.
6. Join the cut-line marks with a flexible batten (a 3 m length of 20 mm PVC
   conduit or a fibreglass tent pole) held by weights, and draw the curve.
   Join the seal-line marks the same way with a different colour, dashed.
7. Cut the first gore, check its length and its width at three stations, and
   keep it as the **master**.
8. Cut the rest from the master. The Sandia method folds and stacks all the
   sheets and cuts through the stack in one pass, weights holding the stack.
   [practice] For 20 µm LLDPE at 15 m we suggest stacks of at most four with
   the master on top, because thin film creeps under scissors. [judgement]
   On each gore transfer the station ticks at the edge (in the allowance) —
   they are the registration marks for sealing.
9. On one gore (keel) mark the load-patch centres and the port; on one other
   (crown) the rip line. Positions are in `summary.json` → `marks` and on the
   drawing layers. Mark the fin-root start and end stations on the four seams
   that carry fins (with 12 gores the 45° fin lines fall exactly on seams).
10. Number the gores 1–12 at the tail end, in the allowance. Gore 1 = crown,
    gore 7 = keel.

If a plotter or cutting table is available, `gore.dxf` is 1:1 in millimetres,
layers CUT / SEAL / STATION. [unverified on any real plotter; it parses in
ezdxf]

## 5. Do the flat work first

Everything that is easier on a flat single gore is done before any long seam.
[judgement]

- **Load patches (keel gore).** At each mark, on the *outside* face: a
  150 mm disc of film as a doubler, then four 200 mm strips of filament tape
  in a star through a webbing loop or a taped-down D-ring, then a covering
  disc of packing tape so no adhesive edge is exposed. S1 carries 5.5 N per
  patch against 47 N of film allowable around the patch edge. [judgement —
  scientific balloons instead seal load tapes into the gore seams, practice;
  our patch detail is untested: pull-test three samples to 5× load at room
  temperature, and one cold, before trusting it]
- **Port (keel gore).** Seal or tape a doubler ring (two plies, 100 mm wider
  than the port) around the mark, then cut the hole inside it. Fit the
  weighted flap later.
- **Rip line (crown gore).** Tape the hot-wire carrier along the marked line
  on the outside, ends anchored to doubler patches. Do not fit the wire
  itself until integration.

## 6. Sealing order

The fin seam is made with two gores lying flat, face to face, edges aligned.
That makes every seam, including the last, a flat seam on the table.
[practice: fin seals made gore-on-gore are the standard gored-balloon joint]

1. Lay gore 1 flat, inside face up. Lay gore 2 on it, inside face down, edges
   and station ticks matched; hold with weights every metre. Do not tape the
   film to hold it.
2. Seal the **right-hand** edge along the dashed seal line, working from the
   **nose toward the tail** so mismatch accumulates at the tail where the
   gore is narrow and is cut off anyway. [practice: Sandia tapes from one
   pole for the same reason] Stop 150 mm short of each cut end.
3. Lay gore 3 on the pile and seal it to the one free edge of gore 2, which
   is now the **left-hand** edge. Each new gore goes on the pile and is
   sealed to the free edge of the previous one, alternating sides, so the
   pile builds as an accordion. Only the top two plies go under the sealer:
   slide a strip of cardboard or PTFE sheet under them so a hot pass cannot
   tack the seam to the gore below.
4. Check each seam as it is made: hold it to a lamp and run a finger along
   it. A seam that is clear and uniform is sealed; milky or patchy is cold;
   thinned and glossy at the edge is hot. Mark defects with a tape flag in
   the allowance; fix them with a second pass 3 mm inboard or, for hot spots,
   with a packing-tape patch over both faces. A backup strip of tape over
   heat-sealed seams is used by at least one university programme (HABET).
   [practice]
5. **The last seam** joins the free edge of gore 12 to the free edge of gore
   1. With the pile accordion-folded these two edges are the top and bottom
   of the stack: pull the bottom edge out to the side, lay it on the top edge,
   and seal it flat like the others. Nothing has to be reached from inside.
6. Where a seam carries a fin root, sandwich the two fin-skin root flanges
   into the seam between the marks so one pass seals four plies. Test this
   four-ply seam on samples first; it needs more dwell. If it will not seal
   reliably, seal the hull seam alone and tape the flanges to the standing
   fin of the seam. [judgement, untested]
7. **Tail.** Gather the twelve tail ends over the tail-disc collar, pleat
   evenly, bind with packing tape, then tape the disc over the end.
8. **Nose.** The nose is closed last and is the access hole until then (arm
   through it to reach the inside of any patch). Lay the cap disc over the
   gore tips on a bowl or ball of about 0.9 m radius, and tape the ring. A cap
   over the pole is standard on taped solar balloons. [practice] Double the
   cap if a nose line or fitting attaches there.

Expected bar time is the seam length over the sealing rate: S1 has 188 m of
hull seam and 60 m of fin seam, 3.4 h at 1.2 m/min. That rate is the cost
model's assumption for a bar sealer including handling; a first build with an
iron will be several times slower. [estimate, unmeasured]

## 7. Leak test with air at 20 Pa

20 Pa is 2.0 mm of water. It is the relief pressure; do not exceed it — the
hoop load at 20 Pa is already 40 % of the film's sustained allowable.

- **Manometer.** A water U-tube cannot resolve 2 mm usefully. Use an inclined
  tube manometer (clear 6 mm tube on a board at 1:10 slope with dyed water
  reads 20 mm of travel for 20 Pa), or the flight Sensirion differential
  pressure sensor on a laptop. Tap the hull through a 6 mm tube taped into
  the port doubler, away from the fan jet. [judgement]
- **Fill.** Indoors, no draughts, floor swept again. Duct fan into the port
  through a film sleeve; S1 is 101 m³, so a 150 m³/h fan takes about 40
  minutes. Watch the hull rise; walk the seams and lift folds so nothing is
  trapped. Throttle the fan as the hull rounds out and stop at 15–20 Pa.
  Never leave the fan running unattended on a full hull.
- **Hold test.** Close the port. Log pressure and room temperature every
  minute for 30 minutes. Room temperature drift matters: 0.1 K changes the
  pressure of a sealed full hull by tens of pascals in principle, but a
  slack-capable hull shows it as shape, so judge by both pressure and
  wrinkles.
- **What a leak costs** [physics, orifice flow with C_d 0.6]: 1 mm² of hole at
  20 Pa passes about 12 L/h of air on the floor, and about 0.17 m³/h of
  hydrogen at float (lower density, same pressure). For S1, 10 mm² total is
  about 1.7 % of the gas per hour. Set the acceptance from the mission
  length; for a two-hour S1 flight we suggest: the fan-off hull still holds
  more than 5 Pa after 30 minutes. [judgement]
- **Finding leaks.** Seams: wet a sponge with dilute washing-up liquid and
  wipe; bubbles show at 20 Pa only for holes above about 0.5 mm, so also
  listen and feel with a wet cheek along every seam, and darken the room and
  put a lamp inside the nose to look for pinholes in the panels. Mark with a
  tape flag, deflate, patch with packing tape on a flat surface, both faces
  for a seam, outside only for a panel pinhole. [judgement]
- **Measure it while it is up.** Length, maximum diameter, and the depth of
  the flats between seams. This is the only check of the lobing estimate and
  of the real volume.

Hydrogen is never used indoors. Air on the floor says nothing about cold
behaviour; a cold-soak seam test on samples (dry ice box, pull while cold) is
the cheap partial check. [judgement]

## 8. Spine and fins

- **Spine.** 12 mm UHMWPE webbing under the keel. Tie it to each load-patch
  loop with a short dropper of 1 mm line, each dropper cut to length so the
  webbing hangs straight when the hull is inflated; set the lengths during
  the air test, when the hull is at shape. Leave 2 % slack in the webbing
  between droppers: the hull must take pressure load, the webbing only
  payload. Pods hang from the webbing, not from the film. [judgement]
- **Fins.** Weld each spar tube (lap seam, pillow ends, one valve), leak
  test at 3 kPa overnight, and fit the 10 kPa relief valve — a sealed tube
  would reach about 73 kPa gauge at float. Slide the spars between the two
  skins and seal the skin perimeter. The spar diameter in the patterns
  (280 mm for S1) is set by not wrinkling at the 3 kPa ground pressure under
  a 15° gust at launch; that is a cantilever with no bracing. Three or four
  guy lines from the fin tip and mid-span to taped patches on the hull would
  cut the root moment several-fold and allow thinner spars; blimp fins are
  commonly braced this way. [judgement; bracing practice not checked against
  a source]

## 9. Folding for launch

The hull launches about 10 % full: a bubble at the nose, the rest hanging.

1. Deflate through the port by walking the air from the nose to the tail and
   back to the port; do not roll or kneel on it.
2. With the hull flat, keel gore down and centred, fold both sides in to make
   a strip about 0.6 m wide with the keel line, patches and spine on the
   outside bottom and the crown rip line on the outside top. Do not twist: a
   twisted hull does not fill.
3. Flake (zig-zag) the strip from the **tail** into a clean bag or tub in
   0.8 m folds, so the nose comes out first. Never crease the same line
   twice in rehearsals; thin film pinholes at repeated fold lines.
4. Fins go on top, spars deflated and folded along their length.
5. At the field, pull the nose out, fill through a sleeve at the port (or a
   dedicated fill tube near the nose, to be decided with the launch
   procedure), and pay the rest out of the bag as the bubble lifts. Restraint
   of the bubble during fill is not designed yet.

Flaking from a box and launching bubble-first is how zero-pressure
polyethylene balloons are laid out in general; the specifics here are ours.
[judgement; not rehearsed]

## 10. Not verified

- No seam made, no film bought, no patch pulled: every strength figure is
  from `materials.py` estimates.
- The four-ply fin-root seam and the taped load-patch detail are untested.
- The inclined-manometer and leak-rate acceptance numbers are calculations.
- Supplier questions on gauge tolerance and cold brittleness are from general
  film knowledge, not a quoted data sheet.
- The Public Lab heat-seaming instructions were found only as search-result
  summaries (the page returned 404 on fetch); the iron-on-edge advice is
  quoted second-hand.
- The NASA/CSBF balloon design handbook was not retrieved; the statements
  about fin seals and load tapes rest on the patents below.

## Sources

- D. C. Bowman, *How to build a heliotrope solar hot air balloon*, Sandia
  SAND2020-3763R — stack cutting, tape seams from one pole, pole cap, socks,
  never peel tape, floor size, 0.31 mil HDPE painter's film.
  <https://www.osti.gov/servlets/purl/1608516>
- Public Lab solar-balloon notes — clothes iron heat seams versus tape (seen
  via search summary only). <https://publiclab.org/n/24324>,
  <https://publiclab.org/sites/default/files/thekissballoon2_2012_annotated.pdf>
- Iowa State HABET — tape over heat-sealed polyethylene seams as backup.
  <https://iastatedigitalpress.com/ahac/article/5594/galley/5459/view>
- Fin seals, travelling impulse sealers and load tapes at gore seams in
  industrial balloon manufacture: US 9,371,123
  <https://patents.justia.com/patent/9371123>, US 3,109,611
  <https://patents.google.com/patent/US3109611>, US 2,767,941
  <https://patents.google.com/patent/US2767941>.
- Polyethylene creep and seal behaviour in balloon films: NASA CR, 1967
  <https://ntrs.nasa.gov/api/citations/19670009435/downloads/19670009435.pdf>.
