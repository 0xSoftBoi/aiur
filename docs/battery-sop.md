# Battery standard operating procedure

Status: engineering-target procedure for an indoor prototype lab; no pack has
been received or logged against it yet
Scope: 1S LiPo packs for the Crazyflie micro-UAVs, plus any battery pack used
to power the dock, the bench controller, or a fault-insertion unit
Precedence: the institution's own safety rules override every line below

## Why this document exists

Everything else in this program is analytical. A gate is closed by a number, a
model claim is killed by a campaign, a residual risk is signed. Battery safety
does not work that way: nobody analyses their way out of a pack fire. The
control is the routine — the same inspection, the same containment, the same
log line, every time — and a routine that is not written down is not a routine.

The energy is small in absolute terms and large in context. The Bitcraze 250
mAh pack that ships with a Crazyflie is 3.7 V nominal at 7.1 g:

```
0.250 Ah x 3.7 V = 0.925 Wh = 3.33 kJ  ->  469 J/g at the pack level
```

Source for capacity, nominal voltage and mass: Bitcraze 250 mAh LiPo battery
datasheet Rev 1 (https://www.bitcraze.io/documentation/hardware/250mah_battery/250mah_battery-datasheet.pdf).
The arithmetic is ours.

Per gram, that is the highest stored energy routinely handled at this bench,
and it is the only item on the bench that can release its energy with no
external input — the AMA safety handbook's phrasing for damaged cells is
"Physically damaged cells can erupt into flames." The bench it would burn on
holds printed polymer parts, envelope film, and hundreds of unattended cycles'
worth of work; hazard row 3 of the [P0-A test card](../hardware/dock/p0a-test-card.md)
already says so. A compressed helium cylinder stores far more total energy than
any pack here — it is outside this SOP and has no written procedure yet, which
is a recorded gap, not an omission.

## Scope boundaries

In scope: every rechargeable lithium pack in the lab — Crazyflie flight packs,
any pack powering the dock or OpenRB-150 in place of the current-limited bench
supply, spare packs, packs in transit, packs awaiting disposal.

Out of scope, and each needs its own procedure or an explicit deferral: the
helium cylinder, mains wiring and the bench supply itself (ground equipment per
[p0a-fabrication.md](../hardware/dock/p0a-fabrication.md)), and any non-lithium
chemistry.

The dock's normal power source is a current-limited 5 V bench supply, not a
pack. If anyone substitutes a pack — for portability, for a brownout trial, for
a demo — that pack enters this SOP with a pack ID before it is connected.

## Pack population

The verified pack in hand is the Bitcraze 250 mAh 1S: 3.7 V nominal, 15C
discharge, 2C charge, charging window 0–45 °C, discharge window 0–60 °C, Molex
51005-2P connector (pin 1 positive), 7.1 g, 20 x 7 x 30 mm (datasheet Rev 1,
cited above).

The Crazyflie 2.1 Brushless is commonly described with a larger pack (the ~300
mAh class). **No datasheet for that pack has been verified for this program.**
Until one is filed, treat any non-250 mAh pack as unknown: its charge C-rate,
temperature windows, and connector polarity are assumptions, and the receiving
step below does not complete without the manufacturer's own numbers. Do not
carry the 250 mAh datasheet's limits across to a different pack.

## Receiving

No pack is charged, flown, or connected to anything before this is complete.

1. **Assign a pack ID** and write it on the pack (see pack identity, below).
2. **Record the receiving row** — every field in the receiving log template. A
   pack whose chemistry, cell count, or nominal capacity is unknown is not
   accepted; unlabelled cells from a marketplace listing are not acceptance
   evidence.
3. **Obtain and file the UN 38.3 test summary** for the cell/battery type (next
   section). File it with the program's hardware documents and record the
   filename in the receiving row.
4. **Ask the vendor whether the pack is tested to IEC 62133-2** (portable
   sealed secondary lithium cells and batteries; designation reported in
   [docs/engineering-practice-survey.md](engineering-practice-survey.md) and
   not independently verified for this program). Record the answer, including
   "vendor did not answer". Absence is not a blocker for an indoor prototype;
   an unrecorded absence is.
5. **Visual and dimensional acceptance**, all of which must pass:

| Check | Accept | Reject |
| --- | --- | --- |
| Pouch | flat, no bulge, no soft spot | any visible swelling, dent, or crease in the foil |
| Film | intact, no punctures, no abrasion | punctured, torn, or peeling film; exposed foil |
| Leads and connector | insulation intact, connector undamaged, polarity matches the datasheet | nicked or stiff insulation, loose crimp, wrong or reversed connector |
| Labelling | chemistry, capacity, nominal voltage legible | unmarked pack |
| Baseline thickness | measured with calipers at the pack centre, recorded | — |
| Baseline mass | measured to 0.1 g, recorded | — |
| Arrival OCV | 3.60–3.90 V/cell (shipping SoC) | below 3.00 V/cell — quarantine, do not charge, retire |

Baseline thickness and mass exist so that "swollen" is later a measurement
rather than an opinion. Measure one known-good pack three times at receiving to
establish caliper repeatability on a soft pouch; if the spread exceeds 0.1 mm,
fix the technique before trusting the swelling criterion.

A rejected pack is marked, logged as rejected, and returned or retired the same
day. It never sits on the bench "to look at later".

## UN 38.3 test summary

Lithium cells and batteries are transport-tested as a *type*, not as
individual units. UN Manual of Tests and Criteria sub-section 38.3 defines
eight tests:

| Test | Name |
| --- | --- |
| T.1 | Altitude simulation |
| T.2 | Thermal test |
| T.3 | Vibration |
| T.4 | Shock |
| T.5 | External short circuit |
| T.6 | Impact/Crush |
| T.7 | Overcharge |
| T.8 | Forced discharge |

"Tests T.1 to T.5 shall be conducted in sequence on the same cell or battery.
Tests T.6 and T.8 shall be conducted using not otherwise tested cells or
batteries." All cell types get T.1–T.6 and T.8; rechargeable batteries get
T.1–T.5 and T.7 (UN Manual of Tests and Criteria, 6th Revised Edition,
sub-section 38.3).

The **test summary** is the one-page document proving a given cell/battery type
passed those tests. Sub-section 38.3.5 requires manufacturers and distributors
to make it available; secondary guidance (CHEMTREC summarising PHMSA) puts the
availability requirement in force from 1 January 2020 for transport under the
ICAO Technical Instructions and the IMDG Code, for cells manufactured after 30
June 2003. That date and scope come from a secondary source, not from the UN
text this program fetched — verify before relying on it commercially.

A test summary is acceptable only if it carries all eight elements (per PHMSA
guidance quoted by CHEMTREC):

1. name and contact information (address, phone, email, website) of the cell,
   battery, or product manufacturer;
2. name and contact information of the test laboratory;
3. a unique test report identification number;
4. date of the test report;
5. description of the cell or battery — lithium ion or lithium metal, mass,
   watt-hour rating or lithium content, physical description, model numbers;
6. list of tests conducted and results (pass or fail);
7. reference to assembled-battery testing requirements where applicable
   (38.3.3(f) and 38.3.3(g));
8. signature with the name and title of the signatory.

Why the lab cares, given that nothing here is being shipped for sale: the test
summary is the only cheap evidence that the cell type has been abuse-tested at
all. A vendor who cannot produce one is telling you something about the pack.
It is also required the first time a pack leaves the lab in a courier's hands
(see transport).

## Pack identity, cycle count, and the promotion contract

Every pack carries a physical ID label — `BAT-nnn`, written on the pouch with a
permanent marker and, if the marker does not survive, on a thin adhesive label
that does not cover the pouch's swelling area. No ID, no flight.

Every pack has a row in the receiving log and a cycle log of its own. **One
cycle = one charge.** The cycle count is incremented when the charge line is
written, not at some later reconciliation.

This is where the SOP joins the rest of the program.
[docs/test-cards.md](test-cards.md) already puts battery pack IDs into the
frozen configuration identity at the TRR, and the TRR checklist already demands
"pack ID, cycle count, resting voltage" before a pack goes on the article. Those
lines are only meaningful if the pack log exists and is current.

Requirement: **`battery_pack_id` and `battery_cycle_count` appear in the run
record for every run that flies a pack**, alongside the promotion-contract
fields in [docs/engineering-loop.md](engineering-loop.md). A run that produced a
bad capture, an early abort, or an anomalous sag must be traceable to the
specific pack that flew it, and a pack that is later retired must be traceable
to every run it touched. Without the pack ID in telemetry, "battery sag" is a
story; with it, it is a queryable subset of runs.

Field names are an engineering target until the run templates carry them. P0-A
correctly has no battery columns in
[`p0a-run-template.csv`](../hardware/dock/p0a-run-template.csv) because P0-A
runs with the pack removed; the columns are added for P0-B, where a live
aircraft flies.

## Charging

Charging is when packs burn. Every rule below is a rule because the alternative
has started fires in model-aircraft practice.

**Rate.** Default charge rate **1C** — 0.25 A for a 250 mAh pack — regardless
of a higher manufacturer figure, unless the manufacturer states a *lower*
maximum, in which case the manufacturer wins. The Bitcraze pack is rated 2C; we
charge at 1C anyway. The reasoning: Battery University's advised charge rate for
an energy cell is 0.5C–1C with a 2–3 h complete charge, higher rates buy
turnaround at the cost of heat and cycle life, and this program has no turnaround
requirement at P0 that 1C fails to meet. This is a target; revisit it with
measured pack temperature data, not with impatience.

**Terminate at 4.20 V/cell.** Li-ion with conventional cathodes charges to
4.20 V/cell with a tolerance of ±50 mV; "Li-ion cannot absorb overcharge ... a
continuous trickle charge would cause plating of metallic lithium and compromise
safety" (Battery University BU-409). No trickle, no top-off, no leaving a pack
on a finished charger.

**Charger settings are checked before every charge, out loud if someone else is
present:** chemistry LiPo, cell count 1S, rate ≤1C, terminate 4.20 V/cell. A 2S
setting on a 1S pack is the classic single-action lab fire.

**One charger channel per pack.** Never two packs on one channel, never packs in
parallel or series on a single-channel charger. Multi-cell packs are balance
charged — the charging system must cut off as each cell reaches proper voltage
(AMA safety handbook). One channel per pack also means a charge fault is
attributable to one pack and one channel.

**Never unattended.** AMA, verbatim: "Never plug in a battery and leave it to
charge unattended; serious fires have resulted from this practice." Attended
means a named person is in the room, awake, with line of sight to the
containment and able to reach the charger's disconnect without moving anything.
Leaving the room to get coffee ends the charge; unplug it. Set a timer for the
expected charge duration so an overrun is noticed rather than assumed.

**Containment and surface.** Charge inside a LiPo containment bag placed inside
the metal containment bin, on a non-combustible surface, at least 1 m from
combustibles (printed parts, envelope film, foam, paper, the aircraft itself).
AMA: "Store and charge in a fireproof container—never in your model" and "Charge
in a protected area that is devoid of combustibles." Never charge a pack while
it is installed in the aircraft.

**Never charge:**

- a swollen pack, or one that has grown against its receiving baseline;
- a pack with any physical damage, punctured film, or damaged leads;
- a pack whose resting OCV is below **3.00 V/cell** (target floor — quarantine
  and retire instead);
- a pack outside **0–45 °C** (Bitcraze datasheet charging window; do not charge
  at freezing temperature, per BU-409). A pack straight off a sortie is warm —
  let it cool below **40 °C** (target) before connecting a charger;
- a pack that has been crashed, dropped hard, or side-loaded until it has sat
  in containment under observation for at least 30 minutes (AMA: "carefully
  move the battery pack to a safe place for at least a half hour to observe").

**Write the charge line.** One row in the pack's cycle log per charge:
date, pack ID, cycle number, start OCV, rate, charger/channel, mAh accepted,
end voltage, pack temperature at end of charge, operator. The mAh-accepted
number is the capacity-fade trend; without it, retirement criterion 3 below
cannot be evaluated.

## Storage

| Item | Rule | Type |
| --- | --- | --- |
| Storage voltage | 3.80 V/cell | target, from BU-702 (3.82 V/cell ≈ 40% SoC) and AMA ("roughly 3.8 volts") |
| Trigger window | any pack not flown within **7 days** goes to storage charge | target |
| Never stored full | a pack left at 4.20 V/cell loses capacity — 80% remaining after a year at 25 °C stored full, vs 96% stored at 40% (BU-702) | verified |
| Never stored empty | "Discard Li-ion if kept below 2.00 V/cell for more than a week" (BU-702) | verified |
| Container | metal containment bin with a lid, packs individually bagged, terminals unshorted | target |
| Location | designated battery station, non-combustible surface, not on or under a bench holding printed parts or envelope film, not in the same cabinet as the helium cylinder | target |
| Temperature | 15–25 °C, never above 45 °C, never in direct sun or next to a heater; BU-702's recommended storage temperature is 15 °C | target around a verified recommendation |
| Separation from ignition sources | ≥1 m from soldering irons, hot-air stations, 3D printers, the bench supply, and any powered actuator | target |
| Segregation | flight pool, quarantine, and retired packs live in three physically separate containers, labelled | target |

Storage-charge a pack by charging or discharging to the storage voltage with
the charger's storage function; do not "leave it to self-discharge down".

## Retirement criteria

A pack is retired when **any one** of these is true. These are deliberately
measurable so that retirement is a reading, not a judgement call, and so that
nobody has to argue with the pack's owner.

| # | Criterion | Threshold | Basis |
| --- | --- | --- | --- |
| 1 | Visible swelling | **any** visible bulge or soft spot, or measured thickness ≥0.5 mm above the receiving baseline | AMA: any sign of swelling removes a pack from service; the 0.5 mm figure is a target sized above caliper repeatability |
| 2 | Physical damage | punctured or torn film, exposed foil, crushed corner, damaged lead insulation, damaged connector | AMA: physically damaged cells can erupt into flames |
| 3 | Capacity fade | mAh accepted on a full charge <**70%** of nominal (i.e. <175 mAh for a 250 mAh pack) on two consecutive cycles from a comparable post-sortie state | BU-808 defines end of test at 70% capacity; the charge-accepted proxy is ours |
| 4 | Resting voltage floor | resting OCV <**3.00 V/cell** measured ≥30 min after removal from the aircraft, at any time | target, conservative against BU-702's 2.00 V/cell discard rule |
| 5 | Heat in normal use | pack surface >**45 °C** after a normal sortie or at the end of a normal charge; >**60 °C** at any time is an immediate retire and an incident | 45 °C is a target trigger; 60 °C is the Bitcraze datasheet's discharge-temperature limit |
| 6 | Repeat post-flight failure | fails the post-flight voltage check (resting OCV ≥**3.50 V/cell** at 30 min after a normal sortie) **twice** within its last 10 cycles | target; replace 3.50 V with the measured distribution from the first 20 logged sorties |
| 7 | Self-discharge | loses >0.10 V/cell over 7 days at storage voltage | target |
| 8 | Age or cycles | reaching **200 cycles**, or 24 months from the receiving date, without criteria 1–7 triggering, prompts a mandatory capacity check and a documented keep/retire decision | target; BU-808 gives 300–500 cycles to 70% for cells charged to 4.20 V/cell, so 200 is a deliberately early review point |

Criterion 6's threshold is provisional on purpose. Flying twenty sorties and
plotting the 30-minute resting OCV gives the real number; until then 3.50 V/cell
is an engineering target and a pack failing it gets investigated, not
automatically condemned on the first failure.

**On retirement, the same day:**

1. Strike the pack from the flight pool register and mark the pack body
   `RETIRED` with a permanent marker.
2. If the pack is **undamaged and not swollen**: discharge it on the charger's
   discharge function or a resistive load to the discharger's floor, insulate
   the terminals with tape, bag it, and place it in the retired-pack container.
3. If the pack is **damaged, swollen, or has been hot**: do **not** connect a
   charger or a discharger. Containment first. AMA's stated method for a
   damaged or puffy pack is to submerge it in salt water; this program has no
   verified guidance on vessel, duration, or disposal of the resulting liquid,
   so confirm the method with the institution's EHS before using it, and
   otherwise hand the pack to a licensed recycler in a non-conductive,
   non-combustible container.
4. Recycle rather than bin — AMA points at Call2Recycle.
5. Write the retirement row: pack ID, date, criterion number, measured value,
   final disposition, operator.

A retired pack does not stay on the bench overnight. The failure mode being
guarded against is the pack that everybody knows is bad and that somebody
picks up anyway.

## Incident response

Read this before the first charge, not during the first incident. The ladder is
by observable state, because "how bad is it" is not observable.

**Ground truth for this lab:** a lithium cell in runaway is a self-heating
event. Extinguishing the visible flame does not stop the cell, and a hand
extinguisher's discharge onto a venting pack cannot be relied on to end it —
what it can do is keep the *surrounding* material from catching. So the primary
control here is **containment and fuel removal, not extinguishment**, and
"pour water on it" is not the plan: bulk water cooling is a large-pack
technique and a beaker's worth on a bench is neither cooling nor suppression.
This is the lab's operating assumption for a ≤2 Wh 1S pack, stated as an
assumption because this program has not verified a suppression test result. If
the institution's fire authority says otherwise, they are right and this
paragraph is wrong.

| State | Actions, in order |
| --- | --- |
| **Swelling noticed, pack cool, not charging** | Stop handling it. Log it. Move it to the metal containment bin with gloved hands or tongs. Observe ≥30 min. Retire per criterion 1. |
| **Swelling or unusual heat during charge** | Cut charger power at the wall or the charger's own switch — do not unplug the pack by hand. Leave the pack in its containment. Clear people to ≥3 m. Observe ≥30 min before touching it. Retire. |
| **Pack venting or smoking** | Do not pick it up. If it is already in the containment bin, close the lid and leave it closed. If it is not, move it there only with tongs and a face shield, and only if you can do so without passing it near your face — otherwise leave it and clear the area. Everyone ≥3 m and upwind of the room's airflow. Kill power to the bench. Do not breathe the smoke. Start the evacuation criteria below. |
| **Flame** | Evacuate the room. Close the door behind the last person out. Activate the fire alarm, call the institution's emergency number from outside, account for everyone. Do not re-enter for equipment, notes, or other packs. Tell the fire service it is a lithium battery, how many packs, and where they are stored. |

**Evacuation criteria — any one of these evacuates the room, not just the
bench:** flame; smoke that has not stopped within 60 s; more than one pack
involved; smoke reaching head height or spreading beyond the bench; any pack
involved that is not inside containment; anyone feeling unwell from the smoke;
or any doubt at all. Nobody re-enters until the fire service or the
institution's safety officer says so.

**Ventilation.** Vented electrolyte smoke is an irritant and should be treated
as toxic. Get people out first, then ventilate — the room's normal extraction,
windows if the building allows it, door closed toward occupied corridors. Do
not use a desk fan to "blow it away" across the room.

**Afterwards.** Every event above, including a swelling found at inspection, is
written up the same day: pack ID, cycle count, what was observed, what was
done, elapsed times. If a pack was in a run when it misbehaved, the run gets
`FAIL_HARDWARE` or `ABORTED_SAFETY` per
[docs/engineering-loop.md](engineering-loop.md) and the pack ID goes in the
disposition.

**Lab equipment that must exist before the first charge** (all engineering
targets for this lab, to be confirmed against the institution's rules):

| Item | Requirement |
| --- | --- |
| Metal containment bin | closable steel box, ≥5 L, no plastic latch or seal, dedicated to batteries, at the battery station |
| Charging bag | LiPo containment bag used *inside* the bin, not instead of it |
| Extinguisher | within 3 m of the battery station, type selected by the institution's fire authority for the surrounding materials. Do not assume a lithium-specific extinguisher is present — check, and record what is actually there |
| Handling tools | insulated tongs and heat-resistant gloves, plus a face shield, stored at the battery station |
| Instruments | multimeter, calipers, 0.1 g scale, non-contact or contact thermometer |
| Detection | working smoke detector in the room |
| Egress | briefed route from the battery station to an outside door, kept clear — AMA's response to a swelling pack is to move it outside |
| Signage | the emergency number and this SOP's incident ladder printed and posted at the station |

## Transport

Hand-carrying a pack across the lab is not transport. The rules below bite the
moment a pack goes to a courier, onto an aircraft, or into a vehicle in
someone's bag on the way to a demo.

- **Type approval.** Cells and batteries offered for transport must be of a type
  that passed UN 38.3 T.1–T.8 as applicable. This is a property of the type,
  established by the manufacturer — it is not something the lab can do or
  claim. Keep the test summary filed at receiving; it is the document a
  shipper or a customer will ask for.
- **Test summary availability.** Sub-section 38.3.5 requires manufacturers and
  distributors to make the summary available; the in-force date and scope this
  program holds come from a secondary source (see above). Verify before relying
  on it for a shipment.
- **State of charge.** A SoC cap applies to lithium-ion batteries shipped by
  air. **This program has no verified citation for the number.** Treat it as an
  open item: before any shipment, verify the current limit against the carrier's
  dangerous-goods rules and the current edition of the ICAO Technical
  Instructions / IATA DGR, record what you were told and by whom, and ship to
  that. Do not ship packs at full charge on the strength of a remembered figure.
- **Terminal protection.** Every pack individually bagged with terminals taped
  or capped so nothing can bridge them, packed so packs cannot move, chafe, or
  press against each other. UN 38.3 T.5 (external short circuit) is a *type
  test*; it is not permission to let a pack short in a box.
- **Configuration matters.** Cells alone, packed with equipment, and installed
  in equipment are treated differently. Determine which case applies and verify
  the rules for that case, per shipment.
- **Never ship** a swollen, damaged, quarantined, or retired pack. Retired packs
  go to a recycler by the recycler's own route, not by courier.
- Log the movement: pack IDs, date out, destination, date back, condition on
  return, and a fresh visual inspection before the pack rejoins the flight pool.

## Log templates

Copy these. Two files, one row per event, no free-text-only entries.

### Receiving log

| pack_id | chemistry | cells | nominal_mah | nominal_v | manufacturer | model_sku | lot | arrival_date | arrival_ocv_v | base_thickness_mm | base_mass_g | un383_ts_file | iec62133_2 | visual_pass | accepted_by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BAT-001 | LiPo | 1 | 250 | 3.7 | Bitcraze | 114992766 | | | | 7.0 | 7.1 | | unknown | | |
| | | | | | | | | | | | | | | | |

`un383_ts_file` is the filename of the filed test summary, or `MISSING` with a
date the vendor was asked. `iec62133_2` is `yes` / `no` / `unknown — vendor did
not answer`.

### Per-pack cycle log

| pack_id | cycle | date | run_id | pre_charge_ocv_v | rate_a | charger_ch | mah_accepted | end_v | pack_temp_c | post_run_rest_ocv_v | thickness_mm | state | operator |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BAT-001 | 1 | | | | 0.25 | | | 4.20 | | | | flight | |
| | | | | | | | | | | | | | |

`state` is one of `flight`, `storage`, `quarantine`, `retired`.
`post_run_rest_ocv_v` is measured ≥30 min after removal from the aircraft and is
the input to retirement criteria 4 and 6. `thickness_mm` is measured at least
every 10 cycles and whenever anything looks off; it is the input to criterion 1.

### Incident and retirement log

| pack_id | date | event | criterion | measured_value | actions_taken | run_id | disposition | operator |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

## Basis and provenance

Per the program design rule, every number above resolves to a citation or is
labelled a target.

| Rule | Value | Basis | Type |
| --- | --- | --- | --- |
| Pack energy | 0.925 Wh, 3.33 kJ, 7.1 g | Bitcraze 250 mAh datasheet Rev 1 + arithmetic | cited spec |
| Charge/discharge temperature windows | 0–45 °C / 0–60 °C | Bitcraze 250 mAh datasheet Rev 1 | cited spec |
| Manufacturer charge rate | 2C | Bitcraze 250 mAh datasheet Rev 1 | cited spec |
| Program charge rate | 1C | BU-409 advises 0.5C–1C for an energy cell; the 1C choice is ours | target on a cited range |
| Charge termination | 4.20 V/cell ±50 mV, no trickle | BU-409 | cited practice |
| Storage voltage | 3.80 V/cell | BU-702 (3.82 V ≈ 40% SoC), AMA ("roughly 3.8 volts") | cited practice |
| Storage temperature | 15 °C recommended, 15–25 °C accepted | BU-702 recommendation; the accepted band is ours | target on a cited value |
| Storage-window trigger | 7 days | none | target |
| Capacity-fade retirement | 70% of nominal | BU-808 end of test | cited practice |
| Cycle review point | 200 cycles | BU-808 gives 300–500 cycles to 70% at 4.20 V/cell | target, deliberately early |
| Low-voltage discard | 2.00 V/cell for a week | BU-702 | cited practice |
| Program voltage floor | 3.00 V/cell resting | conservative against the above | target |
| Post-flight check | 3.50 V/cell at 30 min, two failures in 10 cycles | none | target, to be replaced by measurement |
| Swelling threshold | any visible bulge; ≥0.5 mm over baseline | AMA (any swelling removes a pack from service); the 0.5 mm figure is ours | target on a cited rule |
| Heat retirement | >45 °C trigger, >60 °C immediate | 60 °C is the datasheet discharge limit; 45 °C is ours | mixed |
| Unattended charging, containment, combustibles, damaged-pack observation, swelling response, salt-water disposal, Call2Recycle | as quoted | AMA safety handbook, lithium battery section | cited practice |
| UN 38.3 test list and sequencing | T.1–T.8 | UN Manual of Tests and Criteria, 6th Revised Edition, sub-section 38.3 | cited standard |
| Test-summary elements (8) | as listed | PHMSA guidance as quoted by CHEMTREC | cited, secondary source |
| Test-summary in-force date and scope | 2020-01-01; cells manufactured after 30 June 2003 | CHEMTREC summarising PHMSA | secondary, verify before commercial reliance |
| IEC 62133-2 relevance | pack-level safety standard to ask the vendor about | designation reported in the program survey; not independently verified | reported designation |
| Shipping SoC cap | not stated | none held | open item — verify against the carrier |
| Containment bin, extinguisher, tools, 3 m clear distance, 60 s smoke rule, ≥1 m ignition separation | as stated | none | targets, to be reconciled with the institution |

The in-force date row above reproduces the boundary as this program's research
recorded it; the UN text is usually rendered "manufactured after 30 June 2003"
while the secondary source phrases it "as of July 1, 2003". Same boundary,
different phrasing, and neither was read from the primary document here.

## Standing on this document

This is an engineering-target SOP for an indoor prototype lab running one dock,
one to two 37 g aircraft, and a handful of sub-watt-hour packs. It is scaled to
that: it borrows the *intent* of transport-test and pack-safety standards
without claiming compliance with any of them, and it says so wherever the
provenance is thin.

It is not a substitute for the institution's own battery, fire, chemical
storage, or waste rules. Where this document and the institution disagree, the
institution wins, this document is corrected the same day, and the correction is
recorded. Reconcile it with the institution's safety office before the first
pack is received — not after the first incident.
