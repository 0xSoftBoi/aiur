# Defect disposition and repair

Status: engineering procedure, opened 2026-08-12
Scope: what to do with a CARRIER-P0 composite part that came out wrong
Executable source: [`aiur/composites/disposition.py`](../../aiur/composites/disposition.py) —
`python -m aiur.composites.disposition`

Some parts come out of the bag wrong. A shop's answer to that is usually a
conversation, and the conversation usually turns on how the part looks and
how far behind schedule the programme is. This makes it an arithmetic
question instead: given a defect of a stated kind, size and location, what
does it cost the part, and does the part still meet its requirements.

## 1. A shallow delamination is worse than a deep one

This is the result that inverts the intuition the defect's name invites, and
it is the reason the acceptance limits here are depth-dependent.

The plies above a delamination form a small plate, bonded to the parent all
the way round its edge. Under in-plane compression that plate buckles, and
once it buckles the delamination grows. A clamped circular plate buckles at
`N_cr = 14.68 D / a²`, so the critical radius follows from the
**sublaminate's own bending stiffness** — and a sublaminate one thin ply
thick has almost none.

Critical radius at each part's governing compressive strain:

| part | governing strain | 1 ply above | mid-thickness |
| --- | --- | --- | --- |
| CS-100 throat cup | 0.0046 | **0.8 mm** | 3.3 mm |
| CS-300 keel rail | 0.0010 | 6.9 mm | 23.3 mm |
| CS-400 keeper tine | 0.0007 | 8.6 mm | 30.9 mm |

A 4 mm delamination under the throat cup's outer glass ply needs repair. The
same 4 mm delamination at mid-thickness is acceptable. The dangerous case is
the one hardest to detect and easiest to write off as cosmetic, so the
inspector records **depth as well as size**, and a record without a depth
cannot be dispositioned at all.

## 2. A 2° wrinkle costs 42 % of compressive strength

Compressive failure of a fibre composite is microbuckling into a kink band,
and it is driven by fibres that are *already* slightly misaligned. Strength
scales roughly as `1/(γ_y + θ)`, so an added wave adds directly to the
misalignment already present:

| added wave | compressive strength remaining |
| --- | --- |
| 0.5° | 85 % |
| 1° | 74 % |
| 2° | **58 %** |
| 3° | 48 % |
| 5° | 36 % |

These numbers are brutal and they are correct. It is why an out-of-plane
wrinkle is a structural defect rather than a cosmetic one, why it cannot be
repaired — the fibre is already where it is — and why a shop that "rolls
them out" after cure is doing something other than fixing it.

## 3. A misplaced ply costs what the laminate's anisotropy says

The same 8° orientation error:

| part | laminate | stiffness moved by |
| --- | --- | --- |
| CS-100 throat cup | near in-plane isotropic | **0.5 %** |
| CS-300 keel rail | unidirectional-dominated | **8.8 %** |

Computed per part from the rotational stiffness envelope — the same
calculation the [conical throat cup is designed around](laminate-design.md#the-cone-will-not-hold-a-fibre-angle)
— rather than tabulated, because the answer depends entirely on the stack.

The metric is the largest **deviation**, not the loss. A misplaced ply that
happens to stiffen the axial direction has still moved the part away from
what was analysed, and reporting a one-sided loss would return a reassuring
zero for exactly that case.

## 4. The dispositions

| disposition | meaning |
| --- | --- |
| accept | inside a stated limit |
| accept with analysis | acceptable once the named analysis is run and **recorded against the part** |
| repair | a defined repair scheme restores it |
| scrap | no route back |

Worked examples, all illustrative rather than findings against hardware:

| defect | part | disposition | turned on |
| --- | --- | --- | --- |
| 4 mm delamination, 3 plies deep | CS-100 | accept with analysis | 2.0 mm vs 3.3 mm buckling radius |
| 4 mm delamination, 1 ply deep | CS-100 | **repair** | 2.0 mm vs 0.8 mm |
| 2° wrinkle | CS-300 | **scrap** | 58 % strength remaining |
| 8° ply misorientation | CS-100 | accept with analysis | 0.5 % stiffness deviation |
| 2 mm delamination | CS-400 | **scrap** | critical part |
| 3.1 % porosity | CS-300 | **scrap** | 2.0 % limit |

## 5. Two rules that are not about strength

**No delamination is accepted on the retention path.** The sublaminate on
CS-400 would not buckle below a 31 mm radius, so this is not a strength
decision. A delamination is evidence of a process escape on a part whose
failure drops a captured aircraft, and one found is not evidence that the
others are absent.

**A misplaced ply found after cure on a critical part is a reject even when
the stiffness cost is negligible.** The rejection is not for the 0.5 %. It
is that the error was not caught at the layup hold point, so nothing
establishes what else the stack contains.

Both are the same principle: on a single-load-path part, a defect is
information about the process, and the calculated margin on *this* defect
does not speak to the ones nobody found.

## 6. Repair

A scarf repair's required taper follows from the same shear-lag physics as
any bonded joint — the parent laminate's stress divided by the adhesive's
shear strength:

| part | parent stress | computed | specified | scarf length |
| --- | --- | --- | --- | --- |
| CS-100 | 404 MPa | 1:11.5 | 1:20 | 8.3 mm |
| CS-300 | 953 MPa | 1:27.2 | 1:27.2 | 36.9 mm |
| CS-400 | 458 MPa | 1:13.1 | 1:20 | 31.8 mm |

Shear alone asks for 1:11.5 on the throat cup. Shops cut 1:20 to 1:50, and the gap is not
conservatism for its own sake: it is peel, which the shear calculation does
not see; the outer plies of a scarf carrying more than their share; and a
repair being made by hand in worse conditions than the original part. The
specified ratio is the larger of the computed requirement and the practice
minimum, so a thicker or more highly loaded part gets a longer scarf rather
than a rule-of-thumb one.

**A repair to a critical part needs the same qualification the original part
needed.** A bonded repair to the retention path is a bonded joint on the
retention path, and inherits every control in [PS-400](ps-400-bonding.md)
including the proof test. Programmes that treat repair as a shop activity
rather than an engineering one discover this the hard way.

## 7. Basis

The buckling coefficient is the standard clamped circular plate value, and
clamped is the *less* conservative of the two standard edge conditions —
stated here rather than left implicit. The initial fibre misalignment behind
the waviness knockdown is an engineering target of 1.5°. Neither has been
measured on this programme's laminates.

What would replace them: a compression-after-impact coupon (CP-06, already
planned) anchors the delamination model against a real damage state, and a
deliberately wrinkled panel would anchor the waviness model. The second one
is not in the [experiment plan](doe-plan.md) yet, and should be if any part
ever comes out wrinkled.
