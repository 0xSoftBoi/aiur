# STRATO-P0 decisions

Status: two open decisions; neither is engineering, and no commit can close them  
Register: `DEC-JURISDICTION`, `DEC-TRACKER` in [`aiur/s0_readiness.py`](../../aiur/s0_readiness.py)

A decision here is recorded the way a hazard acceptance is: by name, with
a date, a rationale, and the scope it covers. An undated decision cannot
be re-reviewed when the scope changes.

Nothing in this file is legal advice. It frames the questions the founder
has to answer and states what each answer changes in the repository.

## DEC-JURISDICTION — where the first flight launches, and under which rule

**Question.** In which country, and under which rule for unmanned free
balloons, will S0-B and S0-C be conducted?

**What the answer changes.**

| If the rule… | Then… |
| --- | --- |
| exempts packages under a mass or density threshold (the program's reading of 14 CFR 101.1(a)(4) is one such rule) | the 4 lb ceiling and the weight/size ratio in the generated manifest stay as the hard limits; `S0-MASS-002` is unchanged |
| caps the package lower than 1.814 kg | `S0-MASS-002`, the S0-A criterion `payload_package_mass_kg`, and the balloon size on `s0-stage0-order.csv` line S0-22 change before anything is ordered |
| requires a notice or authorisation before release | the reference goes in the flight manifest's `airspace_coordination_ref`; the checklist already refuses release without one |
| requires a radar reflector | order line S0-21 unblocks; the reflector's mass and its smallest face go into the BOM and the manifest |
| restricts the tracker's radio band | it decides `DEC-TRACKER` below |

**Record.**

| Field | Value |
| --- | --- |
| Decided by | |
| Date | |
| Country / rule | |
| Notice procedure and who files it | |
| Rationale | |
| Scope | S0-B and S0-C of STRATO-P0; a different site or rule is a new decision |

## DEC-TRACKER — the independent tracker

**Question.** Which second position source flies on its own cells:
an APRS tracker on the amateur 2 m band, or a satellite short-burst beacon?

**What each answer implies.**

| Option | Needs | Changes |
| --- | --- | --- |
| APRS 2 m tracker (LightAPRS class) | an amateur licence held by a crew member, valid in the launch country; the band and power permitted for airborne use there | BOM row "Independent tracker" becomes a part; ~40 g stays; the ground crew needs a 2 m receiver or an APRS gateway in range |
| Iridium SBD beacon (RockBLOCK class) | a subscription and a plan that covers the flight window; a clear-sky antenna placement under the lid | BOM row becomes a part; mass may rise, re-check against the 1.0 kg allocation; no ground station dependency, which is the point for `HAZ-015` |
| Both | both of the above | mass and cost rise; only worth it if the first flights show the LoRa link is marginal |

**Record.**

| Field | Value |
| --- | --- |
| Decided by | |
| Date | |
| Option | |
| Licence / subscription reference | |
| Rationale | |
| Scope | STRATO-P0 Rev-A package; a change of tracker is a new package identity |

## After both close

1. Update `hardware/strato/bom.csv` rows from candidate to part.
2. Unblock lines S0-20…S0-23 in `hardware/strato/s0-stage0-order.csv`.
3. Fill `jurisdiction_rule` in `hardware/strato/s0-flight-manifest-template.json`.
4. Mark `DEC-JURISDICTION` and `DEC-TRACKER` closed in `aiur/s0_readiness.py`
   with this file as evidence — the validator accepts a decision closed by
   a commit only when this document carries a name and a date.
