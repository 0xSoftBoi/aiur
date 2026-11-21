# STRATO references

Status: source list for the numbers in `aiur/strato`, gathered 2026-11-21.
Most figures are press reports of maker claims or vendor data, not
independent tests. Each code constant is tagged `[physics]`, `[cited]` or
`[estimate]`; the "could not verify" list at the end is as important as the
rest.

## Ukraine: what has been proven in service

**Aerostats.** Aerobavovna is the reference maker. Small model: ~10 m³ of
helium, 5.6 kg payload, up to 700 m, up to 72 h, two-person crew, one day of
training, 7 minutes from vehicle to 500 m; kit ~UAH 700k–1M with winch,
cylinders and transport. 2–3 % helium loss per day (~$15). Wind limit 15 m/s
(20 survival), up to 45° tilt; the maker calls stability the main unsolved
problem. Larger model lifts 25–30 kg and needs a team. Production split over
three sites: sewing, electronics, winches. A repeater at 500 m gives ~80 km
coverage radius.
[AIN photo essay](https://en.ain.ua/2024/04/03/aerobavovna-aerostats-photo-essay) ·
[IEEE Spectrum](https://spectrum.ieee.org/airships-drones-ukraine) ·
[Militarnyi](https://militarnyi.com/en/news/aerobavovna-develops-aerostat-capable-of-lifting-30-kg-payloads/) ·
[Nasha Niva / BBC](https://nashaniva.com/en/406548)

**Free balloons.** Over 1,000 untethered launches, some beyond 10 km and
4,000 km; latex, nylon or polyethylene envelopes; a team launches in ~15
minutes. Recovered hardware: near-zero-pressure polyethylene envelopes, a
satellite tracker, hot-wire cut-down, water-bottle ballast.
[Euromaidan Press](https://euromaidanpress.com/2026/05/15/weaponizing-the-westerlies-ukrainian-balloons-sow-havoc-over-russia/) ·
[TWZ](https://www.twz.com/news-features/ukraines-explosive-laden-balloon-operations-against-russia)

**Carriers.** Dovbush T10 (fixed wing, up to six small aircraft, acts as
their relay, ~$12k), GOGOL-M (two aircraft to 300 km, ~$10k per mission),
Queen Hornet (multirotor carrier/relay). All release-only; no documented
recovery of an aircraft back onto a carrier. Aerostat-launched fixed-wing
drones are reported in service. Known weakness: lose the relay and the
released aircraft are lost with it.
[TWZ](https://www.twz.com/air/watch-a-ukrainian-uncrewed-aerial-mothership-launch-kamikaze-drones) ·
[Euromaidan Press](https://euromaidanpress.com/2025/05/29/forbes-ukraines-10k-drone-motherships-with-laser-vision-replace-5m-missiles) ·
[TWZ on relay motherships](https://www.twz.com/air/fpv-drone-motherships-that-also-relay-their-signals-offer-huge-advantages)

**Avionics practice.** ArduPilot in long-range types; ExpressLRS and
Betaflight forks (MILELRS/MILBETA) with frequency reconfiguration and
redundant RF chains; bands move constantly. Sine.Link exposes CRSF on one
UART and MAVLink on another. Board prices: Matek H743-WING V3 30 g ~$135;
SpeedyBee F405 WING 35 g ~$50; RadioMaster DBR4 5.3 g $30; OpenIPC Thinker
8.8 g $55. Starlink Mini 1.10 kg, 25–40 W, and subject to no-notice speed
restrictions in 2026 — a secondary link, never the primary.
[GIS Reports](https://www.gisreportsonline.com/r/ukraine-diy-drones/) ·
[404 Media](https://www.404media.co/ukraines-massive-drone-attack-was-powered-by-open-source-software/) ·
[Auterion Sine.Link docs](https://docs.auterion.com/hardware-integration/skynode-s/connectivity/sine.link) ·
[ArduPilot Blimp boards](https://ardupilot.org/blimp/docs/common-speedybeef405wing.html) ·
[Militarnyi on Starlink limits](https://militarnyi.com/en/news/restrictions-on-starlink-ukraine-drones/)

**Production.** 2.2M drones in 2024, at least 4M in 2025. Parts are up to
90 % of unit cost; state-contract margin capped at 25 %. Packs are 21700
cells in 6S2P/6S3P, spot-welded in-house for ~$65–90. Motor-G passes
100,000 motors a month. Brave1 is pushing a unified connector for swap-in
radio cartridges; none chosen yet. Raspberry Pi prices rose three times in
2026.
[DOU cost breakdown](https://dou.ua/lenta/articles/how-much-drone-cost/) ·
[Kyiv Independent](https://kyivindependent.com/little-by-little-away-from-china-ukraines-new-mass-production-of-drone-parts) ·
[Militarnyi on the connector](https://militarnyi.com/en/news/modular-drones-and-a-unified-vtx-standard-ukraine-seeks-solutions-for-more-efficient-fpv-logistics/) ·
[Isegoria (Forbes) on packs](https://www.isegoria.net/?p=53404)

## Stratospheric prior art

| Vehicle | Numbers used here | Source |
| --- | --- | --- |
| JP Aerospace Tandem (2011) | 9.1 m carbon keel, two balloons, two 1.8 m propellers, 6 kt, 36 kg, 29.3 km; ~$30k and five years | [Lobner compilation](https://lynceans.org/wp-content/uploads/2022/03/JP-Aerospace_High-altitude-airships-compressed.pdf) · [Space.com](https://www.space.com/13433-balloon-airship-altitude-record.html) |
| HiSentinel80 (2010) | 6,800 m³, 60 × 14 m, ~500 kg, 36 kg payload, flaccid launch, 7.2 m/s ascent, 8 h | [arXiv 1402.6706](https://arxiv.org/pdf/1402.6706) · [US Army](https://www.army.mil/article/48484/) |
| Sceye SE2 (2026) | 12-day flight, >88 h station-keeping, Li-S 400–425 Wh/kg, flies under an N-number | [StratoCat](https://www.stratocat.com.ar/fichas-e/2026/RIC-20260325.htm) |
| Loon | Pumpkin superpressure envelopes; zero-pressure Kestrel used 0.8 mil PE at 7–20 kg; 312-day record | [NOAA data doc](https://star.nesdis.noaa.gov/data/sawc/wind_datasets/docs/Loon_Stratospheric_Balloon_Data.pdf) |
| Stanford ValBal | 3 kg, under $1,000, 79 h, latex with vent + ballast | [paper](https://stanfordasl.github.io/wp-content/papercite-data/pdf/Suskho.Tedjarati.ea.AERO2017.pdf) |
| WindBorne | Zero-pressure, ballast + vent control, ~7-day mean life | [arXiv 2602.02714](https://arxiv.org/pdf/2602.02714) |

## Physics and sizing data

- **Added mass.** Lamb factors for prolate spheroids, tabulated by Munk in
  [NACA Report 184](https://ntrs.nasa.gov/api/citations/19930091249/downloads/19930091249.pdf);
  `hull.lamb_factors` reproduces the table.
- **Drag.** Cheeseman/Hoerner volumetric form and the 1.8× total/hull factor:
  [ICAS 2016-0703](https://www.icas.org/icas_archive/ICAS2016/data/papers/2016_0703_paper.pdf).
  NASA HALE concepts: total C_D 0.024–0.029.
- **Hull mass allowances** (+15 % seams, +40 % ballonet) and coated Vectran
  at 146–170 g/m²:
  [NASA TM-2007-214861](https://ntrs.nasa.gov/api/citations/20070017849/downloads/20070017849.pdf).
  Colozza's sizing report:
  [NASA CR-2003-212724](https://ntrs.nasa.gov/api/citations/20040021326/downloads/20040021326.pdf).
- **Winds.** <a id="winds"></a>Typically 5–15 m/s at 18–22 km; 95th
  percentile under ~26 m/s outside winter; 99th percentile at 21 km from
  35 m/s (tropics, August) to 53 m/s (Maine, January).
  [NASA 1980 wind study](https://ntrs.nasa.gov/api/citations/19800004408/downloads/19800004408.pdf) ·
  [Keck study, arXiv 1508.06527](https://arxiv.org/pdf/1508.06527)
- **Thermal.** Earth IR 64–594 W/m², albedo 0.1–0.9, solar 1,358 W/m²:
  [NASA balloon environment](https://asd.gsfc.nasa.gov/archive/balloon/ULDB_study/balloon_environment.html).
  Day/night lift swing ~10 % on latex (ValBal).
- **Lift gas.** Helium Grade-A ~$12/m³ base in 2025
  ([USGS](https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-helium.pdf)),
  retail $25–42/m³, supply shock in 2026. Hydrogen €2–5/kg at production.
  Most US upper-air sites fly hydrogen
  ([NWS](https://weather.gov/bou/HeliumShortageandBalloonLaunches)).
- **Components at altitude.** u-blox M10 airborne mode to 80 km; MS5611
  rated 10–1200 mbar, BMP388/390 only to 300 hPa; LoRa 832 km at 25 mW from
  38 km; ArduPilot hardware flown from 30 km with bays kept near 0 °C.
  [MS5607 datasheet](https://pages.hmc.edu/spjut/AdvRoc/PDF/MS5607-02BA03DataSheet.pdf) ·
  [TTN record](https://www.thethingsnetwork.org/article/lorawan-world-record-broken-twice-in-single-experiment-1)
- **Regulation.** [14 CFR 101.1](https://www.law.cornell.edu/cfr/text/14/101.1),
  [101.35](https://www.law.cornell.edu/cfr/text/14/101.35);
  [Part 101 Modernization ARC final report](https://www.faa.gov/sites/faa.gov/files/Part_101_Modernization_ARC_Final_Report.pdf);
  [SERA Appendix 2](https://regulatorylibrary.caa.co.uk/923-2012/Content/Regs/04250_1._CLASSIFICATION_OF_UNMANNED_FREE_BALLOONS.htm).
- **Simulation.** Gazebo
  [`LighterThanAirDynamics`](https://gazebosim.org/api/sim/9/classgz_1_1sim_1_1systems_1_1LighterThanAirDynamics.html)
  (Li & Nahon 2007);
  [ArduPilot Blimp scope](https://ardupilot.org/blimp/docs/getting-started.html);
  [Tawhiri predictor](https://tawhiri.readthedocs.io/en/latest/api.html).

## Could not verify — treat as estimates

- Tensile strength, cold seam strength and price per m² of balloon-grade
  polyethylene; hydrogen permeance of any film here.
- Measured gas superheat/supercooling for clear polyethylene.
- Modern (ERA5) wind percentiles by latitude and season; the tables in
  `atmosphere.py` are an envelope drawn from the ranges above.
- Li-ion capacity at −40 °C; motor cooling and propeller data at 5 kPa.
- Fin lift-curve slopes and tail-volume practice for inflated fins.
- The Paschen minimum (~327 V) is from memory, not a fetched source.
- Which regulatory path Sceye, Aerostar and JP Aerospace actually used.
- Any Ukrainian aerostat's envelope material, volume beyond the 10 m³ fill,
  or use of hydrogen; which ArduPilot boards Ukrainian makers standardise on.
- Masses and prices marked `estimate` in `components.csv`.
