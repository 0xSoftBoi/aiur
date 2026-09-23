# S0-B tethered ascent and S0-C free-flight checklist

Status: procedure template; no flight has been made  
Gates: S0-B (tethered ascent), S0-C (stratospheric sounding)  
Precondition: S0-A `PASS` on the exact package identity being flown

This is the evidence contract of [`docs/engineering-loop.md`](../../docs/engineering-loop.md)
applied to a balloon. Every item is either a gate metric, a hazard
mitigation from [`aiur/hazards.py`](../../aiur/hazards.py), or a stop
condition. Nothing here is optional because the day is nice.

## A. Before the launch window (S0-C only)

- [ ] **Jurisdiction check written down.** Which rule the launch falls under,
      what notice or authorisation it requires, and who was contacted. The
      program's reading of 14 CFR 101 is in the spec; it is not legal advice
      and it is U.S.-only.
- [ ] **Airspace coordination on file** (`airspace_authorisation_on_file`,
      S0-SAFE-005): reference number, authority, time, launch window and
      predicted trajectory attached. No reference, no release.
- [ ] **Prediction committed** (S0-FLT-003): run the day's sounding through
      the ascent model, commit the predicted landing point and ellipse to the
      flight manifest *before* the fill. The geofence is set at ≥ 1.5× the
      predicted range and written into `FlightLimits.max_range_km`.
- [ ] Predicted landing ellipse is over open, accessible ground; not water,
      not a town, not an airport approach. If it is not, the day is a no-go.
- [ ] Recovery crew briefed with the ellipse, the beacon frequency, and
      landowner contact plan.
- [ ] Package identity, image hash, timer setting, and cell lots recorded in
      the manifest; match the S0-A card.

## B. At the site (S0-B and S0-C)

- [ ] Surface wind ≤ 4 m/s at fill; gusts logged. Above that, no fill (HAZ-017).
- [ ] Cylinder chained upright; regulator checked; gloves on the fill crew.
- [ ] Balloon and package restrained to a ground anchor until the release call.
- [ ] Neck lift measured with a spring scale, not estimated from volume:
      target = package mass + balloon mass + free lift (0.9 kg). Record it.
- [ ] Parachute rigged on its own line above the package; load line runs
      around the box in its grooves; weak link fitted.
- [ ] Ground station receiving: position packets decoding at 30 s.
- [ ] Independent beacon heard on its own receiver.
- [ ] **Arming pin pulled only at the anchor, with a valid fix on the ground
      station display.** The supervisor will not arm without one.
- [ ] Timer heartbeat seen after arming.

## C. S0-B tethered ascents (criteria `tethered_flights ≥ 3`, `end_to_end_images_downlinked ≥ 30`, `position_report_gap_max_s ≤ 60`, `parachute_deployments ≥ 1`, `parachute_failures = 0`, `crew_contacts = 0`)

Tether to the height the site and the jurisdiction allow. Three ascents,
each logged as its own run under the flight identity:

1. Ascent 1: full chain — frames captured aloft, thumbnails received on the
   ground, position every 30 s. Recover by winch.
2. Ascent 2: repeat; log any position gap.
3. Ascent 3: **command termination aloft.** The cutdown fires, the package
   separates from the balloon (which stays on the tether), the parachute
   deploys, the package lands. Film it. One deployment with zero failures
   is the criterion.

Any contact between the line, the balloon, or the package and a person is
a stop and a hazard-log entry, not a note.

## D. S0-C release

- [ ] Wind, coordination reference, prediction file, and neck lift re-read
      aloud by the recorder.
- [ ] Release on the test director's call only. Time recorded.
- [ ] Ground station logs every received packet with receive time; this log,
      not the package's transmit log, is the telemetry evidence.

## E. In flight

- [ ] Track against the prediction every 5 min. If the track diverges toward
      airspace or ground the prediction did not cover, **terminate** (ground
      command). Early is cheap.
- [ ] A telemetry gap approaching 300 s is a finding even if the flight
      passes; note it.

## F. Recovery

- [ ] Package located by beacon; recovery position recorded from the crew's
      GNSS, not the package's last packet.
- [ ] Landowner contacted where applicable; any contact with property or a
      person recorded as `third_party_contacts` and taken to the hazard log.
- [ ] Storage checksum verified before the package is powered off.
- [ ] Balloon remnant and line recovered where found.
- [ ] Manifest completed: `recovered`, recovery coordinates, checksum,
      `third_party_contacts`, and the coordination reference.

Reduce:

```
python -m aiur.s0_evidence flight --log <flight-1.csv> --manifest <flight-1.json> \
                                   --log <flight-2.csv> --manifest <flight-2.json> \
                                   --trials <pre-flight-trials.csv>
```

Two flights of one configuration close S0-C. One good flight is a good
flight, not a gate.

## G. Stop conditions (any stage)

- no coordination reference on file;
- neck lift outside ±10 % of target;
- surface wind above limit at fill;
- arming pin pulled without a fix;
- loss of the beacon before release;
- any person in contact with the line or balloon;
- a configuration change made without a new identity.
