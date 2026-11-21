# STRATO prototype ladder

Status: plan. What to build, in what order, and what each article must show
before the next one is cut. Same rule as P0: a gate is evidence, not a date.

## The ladder

| Article | What it is | Cost | Gate to pass |
| --- | --- | ---: | --- |
| **SP0-A film coupons** | 20 µm LLDPE seam strips, sealed on the production bar sealer | <$100 | Seam ≥ 80 % of parent film at room temperature and at −60 °C (dry ice + isopropanol bath); 24 h creep at 100 N/m with no growth |
| **SP0-B avionics on the bench** | Bay + stern pod + FTU wired per the netlist | ~$900 | `harness` review matches the as-built; cold soak to −60 °C outside / 0 °C inside for 4 h on the heater; both cutters fire from the FTU with the autopilot powered off; cut-down on heartbeat loss after its timer; procedure in [ftu.md](ftu.md) |
| **SP0-C thin-air propulsion** | Motor + propeller in a vacuum chamber or bell jar at 5.5 kPa | ~$300 + chamber time | Thrust and shaft power within 20 % of the model at 3 operating points; motor steady-state temperature at cruise power |
| **SP1 low-altitude hull** | 5.1 m, 4.2 m3 hull in TPU-coated ripstop (reusable), 4.4 kg, helium, tethered then free at <120 m; patterns and BOM generated | ~$1,975 | Fin sizing confirmed: heading hold and 90° turns without gimbal saturation; flaccid-to-full inflation on a rope; ROS stack flown end to end |
| **SP2 tandem to float (S1)** | Two latex cells on a boom, full avionics | ~$2,150 | Reach ≥18 km; hold ±500 m for 30 min on vent + trim; powered heading changes on command; both terminations exercised; recover |
| **SP3 film hull to float (S1)** | 15.0 m LLDPE hull | ~$2,330 | Reach 20 km; hull takes shape; station-keep 30 min in ≤3 m/s; land within the Monte Carlo footprint |
| **SP4 day loiter (S2)** | 17.6 m hull, solar, 2 kg payload | ~$2,840 | All daylight at float; hold station inside 2 km in ≤5 m/s wind |

Why the tandem flies before the hull: it removes the two least-known things
— hull inflation and fin aerodynamics — from the first stratospheric flight,
and exercises everything else (avionics in the cold, the float controller,
termination, the chase). JP Aerospace took the same route.

Why SP1 is ripstop and helium: it is a ground-handling and control trainer
that will be inflated dozens of times around people. Film and hydrogen are
for articles that leave.

## Flight day (S1/S2)

1. Forecast: run `aiur.strato.campaign` with the day's sounding in place of
   the climatology (and a Tawhiri/SondeHub prediction as an independent
   check). No-go if the 90th-percentile landing is outside the recovery area
   or the float-level wind exceeds the vehicle's sustained airspeed.
2. Lay out the hull on a ground sheet, spine down. Power the FTU first and
   confirm its link and GNSS before anything else is switched on.
2a. Pull the remove-before-flight plug only when the vehicle is ready to release.
3. Fill to measured free lift (45 %) with a spring scale on the fill bubble.
   Hydrogen handling per the weather-service practice: earth the hull and
   the cylinder, no electronics within 1.5 m of the fill point, nobody
   downwind.
4. Release nose-first; the equipment chain lifts off the ground in order,
   stern pod last.
5. Chase. The FTU cuts down on range, altitude, time, link loss or command.

## Regulation — read before buying film

This is the item most likely to stop the programme, and it is not an
engineering problem.

- **United States.** 14 CFR Part 101 covers unmanned *free balloons*. Its
  exempt class ends at any package over 6 lb or 12 lb total; S1 carries
  5.6–6.5 kg (12–14 lb) below the cells, so it is in Subpart D at best: two
  independent payload cut-downs, two envelope terminations, a radar
  reflector, lights at night below 60,000 ft, ATC notification 6–24 h ahead,
  position reports every 2 h. The design already carries all of these. But
  a *powered, steerable* airship is not a free balloon; Sceye and JP
  Aerospace fly under aircraft registration (N-numbers). Part 107 stops at
  400 ft and 55 lb. Expect to need an experimental certificate or a
  44807 exemption, and to be asked for ADS-B Out — the 2025 Part 101
  modernisation committee recommended it for the heavier balloon class.
- **Europe.** SERA Appendix 2: under 4 kg payload is a *light* balloon;
  ≥6 kg or any 3 kg package is *heavy* (two terminations, radar
  reflector/tracking, transponder where SSR is used, 7 days' notice).
  A 3.9 kg-payload variant of the tandem is worth designing for exactly
  this reason.
- **Ukraine.** Airspace is closed to civil flight in wartime; any flight is
  a military-coordinated operation. Friendly fire is a documented loss
  cause for aerostats there, and coordination is part of the system.
- **Everywhere.** The vehicle crosses controlled airspace twice. The first
  conversation is with the national aviation authority, before SP2.

Open action: a written determination from the relevant authority on how a
powered sub-25 kg stratospheric airship is classified. Until that exists,
SP2 onward is unscheduled.

## What is deliberately not in the ladder

- Overnight flight (S3): the tendon-netted envelope closes in the sizing
  model, but the net needs its own coupon tests (film-to-tendon bond,
  lobe shape under pressure) before it is an article.
- Winter flight: measured winds rule it out at this size.
- Aircraft recovery at altitude: not physically available to a quadcopter.
- Any effector. The payload bay carries sensors, radios and release-only
  aircraft for sensing and relay, as in every other vertical in this repo.
