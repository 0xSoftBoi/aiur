# STRATO winds: radiosonde statistics

Status: measured climatology, intended to replace the hand-estimated
`WIND_PROFILES` in [`aiur/strato/atmosphere.py`](../../aiur/strato/atmosphere.py).
The tables in the code have **not** been changed; the replacement tuples are
at the end of this page.

```
python tools/strato_winds.py --station UPM00033345 --cache <dir outside the repo>
```

Source: NOAA NCEI Integrated Global Radiosonde Archive v2, period-of-record
station files
(`https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/data-por/<id>-data.txt.zip`).
Results, with per-bin sample counts and per-month tables, are in
[`aiur/strato/data/winds_<id>.json`](../../aiur/strato/data/). Everything
below is computed from 00Z and 12Z soundings from January 2005 on.

| Station | IGRA id | Lat, lon | Period | Soundings | reach 20 km | reach 26 km | reach 30 km | Median top |
|---|---|---|---|---:|---:|---:|---:|---:|
| Kyiv | UPM00033345 | 50.39, 30.54 | 2005-01 to 2022-02 | 10331 | 7895 | 2100 | 107 | 23.1 km |
| Lindenberg | GMM00010393 | 52.21, 14.12 | 2005-01 to 2026-11 | 15932 | 15345 | 14866 | 14261 | 34.4 km |
| Praha-Libus | EZM00011520 | 50.01, 14.45 | 2005-01 to 2026-11 | 15923 | 15712 | 15386 | 14620 | 33.3 km |
| Legionowo | PLM00012374 | 52.41, 20.96 | 2005-01 to 2026-11 | 15743 | 14643 | 13614 | 11177 | 31.6 km |
| Dodge City | USM00072451 | 37.76, -99.97 | 2005-01 to 2026-11 | 15590 | 15276 | 14850 | 13388 | 32.3 km |
| Bismarck | USM00072764 | 46.77, -100.76 | 2005-01 to 2026-11 | 15338 | 14977 | 14525 | 12959 | 32.4 km |

"Europe" below means the unweighted mean of the four European stations
(Kyiv, Lindenberg, Praha-Libus, Legionowo); the range in brackets is the
lowest and highest of the four. They agree to within about ±10 %, so the
choice of site inside central/eastern Europe barely matters. The two US
sites are a different climate and are listed separately. Dodge City is at
38°N, not 50°N.

## What the data says

1. **Summer at 20 km is calmer than estimated.** June–August median 4.5 m/s,
   90th percentile 7.2 m/s, 99th percentile 11 m/s. The existing tables say
   6 and 12.
2. **Winter at 20 km over Europe is worse than estimated.** Median 20 m/s,
   90th percentile 37 m/s, 99th percentile 48 m/s. The existing tables say 15
   and 28. There is no minimum-wind layer at all: speed is flat at about
   18 m/s from 13 to 19 km and rises above. The README's "20 km winter median
   is ~15 m/s" should read ~20 m/s.
3. **The jet over Europe is weaker and lower than estimated**, most of all in
   winter: the strongest level is 9 km with median 24 m/s and 90th percentile
   46 m/s, against 36 and 62 m/s at 11 km in the existing table. A fixed site
   is under the jet core only some of the time, so the site median is well
   below a jet-core speed.
4. **The calm season is May to September, not a short "turnaround".** At
   20 km the monthly median is 4–6 m/s for five consecutive months. March,
   April, October and November are transitional and have a long tail
   (90th percentile 17–28 m/s). Season-wide spring and autumn statistics are
   40–65 % windier at 20 km than `midlat-turnaround-p50`; May and September
   alone match it.
5. **The calm layer is thin and moves.** In summer the per-sounding calmest
   level sits at 19–22 km and its speed is 1.5 m/s median, 3.8 m/s at the
   90th percentile. A vehicle that can choose its altitude within 18–22 km
   finds wind below 3 m/s in 67 % of summer soundings, against 29 % at a
   fixed 20 km.
6. **The US Great Plains are a different trade.** The winter polar vortex is
   displaced towards Eurasia, so winter 20–22 km winds are well below the
   European values (22 km median: Dodge City 8 m/s, Bismarck 13 m/s, Europe
   23 m/s). The jet is far stronger
   (Dodge City winter peak 38 / 61 m/s), so the ascent drifts further.

## Existing tables against the data

Speeds in m/s. "Existing" is the current `WindProfile` evaluated at that
altitude: `midlat-summer-*` against JJA, `midlat-winter-*` against DJF,
`midlat-turnaround-p50` against MAM, SON, and May + September. A ratio above
1 means the existing table is pessimistic (too windy), below 1 optimistic.

| Season | Alt | Existing p50 | Real p50 (range) | Existing/real | Existing p90 | Real p90 (range) | Existing/real | Real p99 | Dodge City p50/p90 | Bismarck p50/p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| JJA | 12 km | 20 | 17.8 (15.8–19.0) | 1.13 | 37 | 32.9 (29.5–35.3) | 1.12 | 46 | 19 / 34 | 29 / 44 |
| JJA | 18 km | 6 | 5.8 (5.7–6.0) | 1.03 | 12 | 10.6 (10.3–10.8) | 1.13 | 15 | 5 / 10 | 7 / 12 |
| JJA | 20 km | 6 | 4.5 (4.0–4.8) | 1.33 | 12 | 7.2 (6.9–7.7) | 1.66 | 11 | 6 / 10 | 4 / 8 |
| JJA | 22 km | 8 | 4.8 (4.2–5.0) | 1.68 | 14 | 8.0 (7.3–8.3) | 1.76 | 11 | 8 / 12 | 4 / 8 |
| DJF | 12 km | 32 | 20.1 (18.7–21.1) | 1.59 | 55 | 37.1 (33.6–39.3) | 1.47 | 53 | 37 / 58 | 28 / 45 |
| DJF | 18 km | 15 | 18.6 (17.0–19.4) | 0.81 | 27 | 33.0 (31.6–33.6) | 0.82 | 44 | 16 / 28 | 17 / 32 |
| DJF | 20 km | 15 | 20.2 (18.4–21.3) | 0.74 | 28 | 36.8 (35.0–37.9) | 0.76 | 48 | 10 / 20 | 14 / 31 |
| DJF | 22 km | 18 | 22.6 (20.3–24.4) | 0.80 | 32 | 42.0 (40.5–43.0) | 0.76 | 54 | 8 / 19 | 13 / 32 |
| MAM | 12 km | 26 | 15.1 (14.9–15.4) | 1.70 | — | 28.4 (27.0–29.0) | — | 41 | 31 / 49 | 24 / 40 |
| MAM | 18 km | 6 | 8.0 (7.6–8.2) | 0.75 | — | 19.2 (18.0–20.2) | — | 36 | 12 / 22 | 11 / 20 |
| MAM | 20 km | 5 | 6.9 (6.6–7.0) | 0.72 | — | 19.5 (18.2–20.9) | — | 39 | 6 / 14 | 7 / 17 |
| MAM | 22 km | 5 | 6.6 (6.3–7.0) | 0.76 | — | 20.9 (19.7–22.1) | — | 44 | 5 / 11 | 6 / 15 |
| SON | 12 km | 26 | 20.0 (18.8–20.6) | 1.28 | — | 36.8 (33.7–38.6) | — | 52 | 29 / 50 | 30 / 49 |
| SON | 18 km | 6 | 9.6 (8.8–10.3) | 0.63 | — | 18.1 (17.4–18.8) | — | 27 | 11 / 20 | 13 / 22 |
| SON | 20 km | 5 | 8.3 (7.5–9.1) | 0.60 | — | 17.8 (17.2–18.2) | — | 29 | 6 / 14 | 9 / 18 |
| SON | 22 km | 5 | 8.2 (7.3–9.0) | 0.61 | — | 19.4 (18.5–20.2) | — | 31 | 6 / 12 | 7 / 17 |
| May+Sep | 12 km | 26 | 15.7 (14.2–16.6) | 1.64 | — | 31.0 (27.9–32.9) | — | 45 | 25 / 41 | 25 / 43 |
| May+Sep | 18 km | 6 | 6.5 (6.3–6.7) | 0.92 | — | 12.2 (11.9–12.4) | — | 18 | 8 / 14 | 9 / 16 |
| May+Sep | 20 km | 5 | 5.3 (5.1–5.4) | 0.94 | — | 9.8 (9.6–10.0) | — | 16 | 4 / 8 | 6 / 11 |
| May+Sep | 22 km | 5 | 5.0 (4.8–5.0) | 1.01 | — | 9.2 (8.9–9.4) | — | 15 | 4 / 8 | 5 / 9 |

The 12 km row understates the jet because the real peak is lower. Peak
level, 7–14 km:

| Season | Existing peak (alt, p50 / p90) | Real peak level, Europe (p50 / p90 / p99) | Dodge City | Bismarck |
|---|---|---|---|---|
| JJA | 11.5 km, 22 / 40 | 11 km, 19 / 37 / 50 | 12 km, 19 / 34 / 46 | 12 km, 29 / 44 / 56 |
| DJF | 11 km, 36 / 62 | 9 km, 24 / 46 / 65 | 11 km, 38 / 61 / 77 | 9 km, 31 / 54 / 72 |
| MAM | 11.5 km, 28 / — | 10 km, 20 / 38 / 55 | 11 km, 31 / 50 / 68 | 10 km, 27 / 48 / 64 |
| SON | 11.5 km, 28 / — | 10 km, 22 / 42 / 59 | 12 km, 29 / 50 / 70 | 11 km, 31 / 52 / 66 |

Verdict on each existing entry (Europe):

| Entry | Jet (9–12 km) | 18 km | 20 km | 22 km |
|---|---|---|---|---|
| `midlat-summer-p50` | 15 % too high | right | 33 % too high | 68 % too high |
| `midlat-summer-p90` | 10 % too high | 13 % too high | 66 % too high | 76 % too high |
| `midlat-winter-p50` | 50 % too high (36 vs 24 at peak) | 19 % too low | 26 % too low | 20 % too low |
| `midlat-winter-p90` | 35 % too high (62 vs 46 at peak) | 18 % too low | 24 % too low | 24 % too low |
| `midlat-turnaround-p50` vs May + Sep | 50 % too high (28 vs 19 at peak) | right | right | right |
| `midlat-turnaround-p50` vs all of MAM | 40 % too high | 25 % too low | 28 % too low | 24 % too low |
| `midlat-turnaround-p50` vs all of SON | 27 % too high | 37 % too low | 40 % too low | 39 % too low |

Directions: the existing summer table reverses from 300° to 80° between 18
and 20 km. The data puts the reversal at 19–21 km (vector mean from 245° at
18 km, 105° at 22 km), and at 20 km the vector-mean wind is only about
1 m/s: direction there is not predictable from climatology. Winter is from
280–285° at 18–22 km, not 270°.

## Monthly view, 20 km

| 20 km, by month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p50 speed, Europe (m/s) | 22 | 18 | 11 | 7 | 5 | 5 | 4 | 5 | 6 | 9 | 12 | 20 |
| p90 speed, Europe (m/s) | 40 | 37 | 28 | 18 | 9 | 7 | 7 | 7 | 10 | 17 | 23 | 34 |
| < 3 m/s, Europe | 1 % | 2 % | 6 % | 10 % | 21 % | 27 % | 33 % | 28 % | 15 % | 7 % | 2 % | 1 % |
| < 6 m/s, Europe | 5 % | 10 % | 24 % | 37 % | 65 % | 79 % | 84 % | 78 % | 56 % | 27 % | 14 % | 4 % |
| < 6 m/s, Kyiv only | 3 % | 7 % | 20 % | 34 % | 70 % | 86 % | 89 % | 80 % | 48 % | 20 % | 8 % | 3 % |
| < 6 m/s, best of 18–22 km, Europe | 11 % | 18 % | 41 % | 58 % | 89 % | 98 % | 99 % | 98 % | 83 % | 45 % | 27 % | 10 % |
| < 6 m/s, Dodge City | 25 % | 18 % | 29 % | 40 % | 68 % | 67 % | 40 % | 58 % | 77 % | 44 % | 20 % | 21 % |
| < 6 m/s, Bismarck | 12 % | 13 % | 21 % | 38 % | 64 % | 72 % | 80 % | 75 % | 45 % | 23 % | 12 % | 13 % |
| Ascent drift p50 / p90, Europe (km) | 89 / 149 | 78 / 141 | 70 / 121 | 56 / 106 | 48 / 90 | 50 / 93 | 54 / 96 | 57 / 102 | 57 / 108 | 71 / 124 | 75 / 130 | 85 / 144 |

## Minimum-wind layer, 14–26 km

"Calmest level" is the 1 km bin with the lowest median. "Per-sounding" finds
the calmest bin in each sounding separately (soundings covering at least
14–24 km), which is what a vehicle able to change altitude would see.

| Season | Station | Calmest level (lowest p50) | p50 / p90 there | Per-sounding calmest level, p25–p50–p75 | Speed at it, p50 / p90 | n |
|---|---|---:|---:|---:|---:|---:|
| JJA | Kyiv | 20 km | 4.0 / 6.9 | 20–20–22 km | 2.2 / 4.0 | 1495 |
| JJA | Lindenberg | 21 km | 4.4 / 7.9 | 19–20–22 km | 1.5 / 3.8 | 3916 |
| JJA | Praha-Libus | 21 km | 4.4 / 7.7 | 19–20–22 km | 1.5 / 3.8 | 3969 |
| JJA | Legionowo | 21 km | 4.3 / 7.7 | 19–20–22 km | 1.5 / 3.7 | 3596 |
| JJA | Dodge City | 19 km | 4.8 / 8.9 | 18–19–20 km | 2.4 / 4.6 | 3795 |
| JJA | Bismarck | 20 km | 4.1 / 7.6 | 20–21–22 km | 1.9 / 3.7 | 3696 |
| SON | Kyiv | 22 km | 9.0 / 19.6 | 18–21–23 km | 6.0 / 14.0 | 1269 |
| SON | Lindenberg | 21 km | 7.8 / 18.7 | 18–21–23 km | 4.0 / 13.0 | 3841 |
| SON | Praha-Libus | 22 km | 7.3 / 18.5 | 19–21–23 km | 3.8 / 11.6 | 3895 |
| SON | Legionowo | 21 km | 8.5 / 19.1 | 18–21–23 km | 4.9 / 13.6 | 3564 |
| SON | Dodge City | 22 km | 5.6 / 12.4 | 20–22–24 km | 2.4 / 8.1 | 3736 |
| SON | Bismarck | 24 km | 6.7 / 17.6 | 21–23–25 km | 3.3 / 12.1 | 3613 |
| DJF | Kyiv | 14 km | 17.3 / 29.5 | 14–16–19 km | 12.9 / 24.0 | 705 |
| DJF | Lindenberg | 16 km | 18.4 / 31.3 | 15–17–20 km | 12.8 / 25.9 | 3549 |
| DJF | Praha-Libus | 18 km | 17.0 / 31.6 | 15–17–20 km | 11.2 / 24.6 | 3688 |
| DJF | Legionowo | 15 km | 18.2 / 31.0 | 14–16–19 km | 13.3 / 26.0 | 3265 |
| DJF | Dodge City | 22 km | 8.1 / 18.7 | 21–22–24 km | 4.3 / 13.9 | 3649 |
| DJF | Bismarck | 22 km | 12.9 / 31.6 | 19–22–24 km | 8.3 / 23.8 | 3475 |
| MAM | Kyiv | 23 km | 6.4 / 20.0 | 17–21–23 km | 3.6 / 15.0 | 933 |
| MAM | Lindenberg | 22 km | 6.6 / 21.9 | 18–21–24 km | 2.8 / 12.3 | 3754 |
| MAM | Praha-Libus | 22 km | 6.3 / 19.7 | 18–21–23 km | 2.5 / 11.2 | 3963 |
| MAM | Legionowo | 21 km | 7.0 / 21.3 | 18–21–23 km | 3.3 / 14.1 | 3612 |
| MAM | Dodge City | 22 km | 5.1 / 10.9 | 21–22–24 km | 2.1 / 6.6 | 3751 |
| MAM | Bismarck | 22 km | 5.7 / 15.0 | 21–23–24 km | 2.5 / 9.7 | 3713 |

## Station-keeping availability

Fraction of soundings with wind speed below the given airspeed. Fixed 20 km:

| Season | Station | n | <3 | <6 | <9 | <12 | <15 m/s |
|---|---|---:|---:|---:|---:|---:|---:|
| JJA | Kyiv | 1992 | 33 % | 85 % | 98 % | 100 % | 100 % |
| JJA | Lindenberg | 3953 | 26 % | 77 % | 96 % | 99 % | 100 % |
| JJA | Praha-Libus | 3999 | 30 % | 80 % | 97 % | 100 % | 100 % |
| JJA | Legionowo | 3680 | 28 % | 80 % | 97 % | 100 % | 100 % |
| JJA | Dodge City | 3831 | 16 % | 55 % | 85 % | 98 % | 100 % |
| JJA | Bismarck | 3764 | 30 % | 76 % | 96 % | 100 % | 100 % |
| SON | Kyiv | 2113 | 5 % | 25 % | 48 % | 69 % | 83 % |
| SON | Lindenberg | 3905 | 9 % | 35 % | 56 % | 72 % | 82 % |
| SON | Praha-Libus | 3923 | 10 % | 38 % | 60 % | 75 % | 85 % |
| SON | Legionowo | 3687 | 8 % | 31 % | 53 % | 69 % | 81 % |
| SON | Dodge City | 3803 | 17 % | 47 % | 70 % | 84 % | 92 % |
| SON | Bismarck | 3701 | 7 % | 26 % | 50 % | 69 % | 81 % |
| DJF | Kyiv | 1918 | 0 % | 4 % | 10 % | 19 % | 31 % |
| DJF | Lindenberg | 3691 | 1 % | 6 % | 13 % | 22 % | 32 % |
| DJF | Praha-Libus | 3783 | 2 % | 9 % | 18 % | 28 % | 39 % |
| DJF | Legionowo | 3515 | 1 % | 5 % | 12 % | 20 % | 30 % |
| DJF | Dodge City | 3748 | 6 % | 21 % | 42 % | 62 % | 76 % |
| DJF | Bismarck | 3574 | 3 % | 13 % | 26 % | 40 % | 53 % |
| MAM | Kyiv | 1866 | 14 % | 42 % | 62 % | 74 % | 82 % |
| MAM | Lindenberg | 3791 | 12 % | 42 % | 65 % | 76 % | 83 % |
| MAM | Praha-Libus | 4000 | 13 % | 45 % | 67 % | 78 % | 85 % |
| MAM | Legionowo | 3751 | 11 % | 40 % | 62 % | 74 % | 81 % |
| MAM | Dodge City | 3835 | 16 % | 46 % | 71 % | 85 % | 93 % |
| MAM | Bismarck | 3795 | 14 % | 41 % | 64 % | 78 % | 86 % |

Europe mean by level. "Best of 18–22 km" takes the lowest of the five 1 km
bins in each sounding:

| Season | Level | <3 | <6 | <9 | <12 | <15 m/s |
|---|---|---:|---:|---:|---:|---:|
| JJA | 18 km | 14 % | 53 % | 81 % | 95 % | 99 % |
| JJA | 20 km | 29 % | 80 % | 97 % | 100 % | 100 % |
| JJA | 22 km | 21 % | 72 % | 95 % | 99 % | 100 % |
| JJA | best of 18–22 km | 67 % | 98 % | 100 % | 100 % | 100 % |
| SON | 18 km | 6 % | 23 % | 46 % | 66 % | 81 % |
| SON | 20 km | 8 % | 32 % | 54 % | 71 % | 83 % |
| SON | 22 km | 10 % | 35 % | 56 % | 70 % | 79 % |
| SON | best of 18–22 km | 23 % | 52 % | 70 % | 83 % | 91 % |
| DJF | 18 km | 1 % | 6 % | 14 % | 24 % | 36 % |
| DJF | 20 km | 1 % | 6 % | 13 % | 22 % | 33 % |
| DJF | 22 km | 1 % | 6 % | 12 % | 20 % | 29 % |
| DJF | best of 18–22 km | 4 % | 13 % | 23 % | 35 % | 46 % |
| MAM | 18 km | 9 % | 34 % | 57 % | 72 % | 82 % |
| MAM | 20 km | 12 % | 42 % | 64 % | 76 % | 83 % |
| MAM | 22 km | 13 % | 45 % | 65 % | 76 % | 82 % |
| MAM | best of 18–22 km | 34 % | 63 % | 76 % | 83 % | 88 % |

For the 3–6 m/s airspeed range at 20 km over Europe: summer 29 % (3 m/s) to
80 % (6 m/s); autumn 8 % to 32 %; winter 1 % to 6 %; spring 12 % to 42 %.
Reaching float and holding station are different questions: in winter a
6 m/s vehicle can hold station at 20 km on 6 % of soundings.

## Ascent drift against the 150 km range fence

Each sounding's own wind profile is integrated from its lowest level to
20 km at a constant 3.9 m/s climb (about 85 min). Distance in km from the
launch point at the moment of reaching 20 km. This is ascent only: drift at
float and during descent comes on top. Drift scales inversely with climb
rate; for another rate v multiply by 3.9 / v.

| Season | Station | n | p50 | p90 | p95 | p99 | max | > 100 km | > 150 km | Mean bearing (toward) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| JJA | Kyiv | 1988 | 48 | 88 | 102 | 122 | 140 | 6 % | 0.0 % | 84° |
| JJA | Lindenberg | 3943 | 58 | 106 | 118 | 136 | 161 | 13 % | 0.1 % | 80° |
| JJA | Praha-Libus | 3983 | 55 | 98 | 111 | 132 | 164 | 9 % | 0.1 % | 86° |
| JJA | Legionowo | 3666 | 54 | 97 | 109 | 129 | 157 | 9 % | 0.1 % | 81° |
| JJA | Dodge City | 3818 | 44 | 79 | 88 | 106 | 151 | 2 % | 0.0 % | 96° |
| JJA | Bismarck | 3724 | 77 | 112 | 122 | 141 | 182 | 21 % | 0.5 % | 95° |
| SON | Kyiv | 2109 | 63 | 115 | 128 | 155 | 196 | 19 % | 1.5 % | 101° |
| SON | Lindenberg | 3900 | 70 | 127 | 144 | 173 | 224 | 24 % | 3.9 % | 95° |
| SON | Praha-Libus | 3901 | 65 | 120 | 136 | 161 | 210 | 20 % | 2.4 % | 96° |
| SON | Legionowo | 3684 | 69 | 126 | 140 | 169 | 210 | 22 % | 3.1 % | 97° |
| SON | Dodge City | 3776 | 83 | 138 | 153 | 183 | 244 | 33 % | 5.9 % | 91° |
| SON | Bismarck | 3657 | 96 | 149 | 164 | 184 | 212 | 45 % | 9.5 % | 101° |
| DJF | Kyiv | 1918 | 77 | 131 | 148 | 177 | 231 | 30 % | 4.3 % | 104° |
| DJF | Lindenberg | 3688 | 89 | 155 | 174 | 208 | 261 | 42 % | 11.8 % | 111° |
| DJF | Praha-Libus | 3779 | 84 | 148 | 165 | 196 | 256 | 37 % | 9.4 % | 111° |
| DJF | Legionowo | 3507 | 85 | 147 | 164 | 204 | 245 | 37 % | 9.0 % | 109° |
| DJF | Dodge City | 3698 | 116 | 168 | 183 | 206 | 257 | 65 % | 20.1 % | 93° |
| DJF | Bismarck | 3528 | 105 | 167 | 186 | 214 | 271 | 55 % | 17.8 % | 113° |
| MAM | Kyiv | 1863 | 55 | 106 | 123 | 145 | 181 | 13 % | 0.6 % | 93° |
| MAM | Lindenberg | 3785 | 58 | 109 | 126 | 162 | 231 | 14 % | 1.5 % | 103° |
| MAM | Praha-Libus | 3977 | 54 | 105 | 120 | 152 | 217 | 12 % | 1.2 % | 105° |
| MAM | Legionowo | 3742 | 59 | 112 | 127 | 157 | 263 | 16 % | 1.4 % | 104° |
| MAM | Dodge City | 3796 | 91 | 138 | 155 | 180 | 218 | 39 % | 6.2 % | 85° |
| MAM | Bismarck | 3740 | 77 | 130 | 145 | 173 | 224 | 28 % | 4.0 % | 97° |

- **Summer, Europe:** median 54 km, 90th percentile 97 km, 95th 110 km. One
  sounding in a thousand exceeds 150 km on ascent alone. The fence leaves
  about 40 km for float and descent at the 95th percentile.
- **Winter, Europe:** median 84 km, 90th percentile 145 km, 95th 163 km. 9–12 %
  of soundings at the three long-record stations cross 150 km before
  reaching float.
- **Shoulder seasons:** 1–4 % cross 150 km on ascent.
- **Great Plains:** winter is worse (18–20 % over the fence), and Bismarck is
  worse than Europe in every season; Dodge City in summer is the best case in
  the set (95th percentile 88 km).
- Drift is towards 80–115° (east to east-south-east) in every season. Over Europe only
  50–66 % of soundings fall within ±45° of the mean bearing (67–87 % at the
  US sites), so a recovery team cannot pre-position on one road.

The same integral applied to the existing profiles:

| Existing profile | Drift if integrated the same way | Real, Europe mean |
|---|---:|---|
| `midlat-summer-p50` | 58 km | JJA p50 54 km |
| `midlat-summer-p90` | 108 km | JJA p90 97 km |
| `midlat-winter-p50` | 109 km | DJF p50 84 km |
| `midlat-winter-p90` | 188 km | DJF p90 145 km |
| `midlat-turnaround-p50` | 75 km | MAM p50 57 km |
| `midlat-turnaround-p50` | 75 km | SON p50 67 km |

The existing summer tables reproduce the real ascent drift well, because the
troposphere dominates it and the overestimated jet is partly offset by
underestimated low-level winds. The existing winter tables overstate ascent
drift by 30 %.

## Persistence of the 20 km wind

Europe mean. Correlations are of anomalies from the calendar-month mean,
between soundings exactly 1, 2 and 3 days apart. "P(still <6)" is the
probability that speed is below 6 m/s N days after a sounding in which it
was.

| Season | r(u) 1/2/3 d | r(v) 1/2/3 d | r(speed) 1/2/3 d | RMS vector change 1/2/3 d (m/s) | P(<6 m/s) | P(still <6) after 1/2/3 d | P(<9) | P(still <9) after 1/2/3 d |
|---|---|---|---|---|---:|---|---:|---|
| JJA | 0.57 / 0.48 / 0.37 | 0.50 / 0.38 / 0.26 | 0.31 / 0.22 / 0.14 | 4.4 / 4.9 / 5.3 | 80 % | 85 % / 83 % / 82 % | 97 % | 97 % / 97 % / 97 % |
| SON | 0.75 / 0.61 / 0.50 | 0.62 / 0.42 / 0.29 | 0.71 / 0.57 / 0.45 | 5.8 / 7.3 / 8.3 | 32 % | 65 % / 59 % / 53 % | 54 % | 82 % / 77 % / 73 % |
| DJF | 0.86 / 0.72 / 0.60 | 0.70 / 0.45 / 0.28 | 0.84 / 0.70 / 0.57 | 9.1 / 12.7 / 14.9 | 6 % | 53 % / 44 % / 39 % | 13 % | 67 % / 57 % / 49 % |
| MAM | 0.86 / 0.75 / 0.64 | 0.76 / 0.61 / 0.46 | 0.85 / 0.75 / 0.64 | 5.7 / 7.5 / 8.8 | 42 % | 75 % / 70 % / 66 % | 64 % | 89 % / 86 % / 84 % |

- Summer: the wind is weak and nearly uncorrelated day to day (speed r = 0.3
  at one day), but it does not matter: any day has an 80 % chance of being
  under 6 m/s, and a good day is followed by another with 85 %.
- Spring and autumn: strongly persistent. A day under 6 m/s is still under
  6 m/s three days later in 53–66 % of cases, against a 32–42 % base rate: a
  launch window found in a shoulder month is more likely than not still open
  three days later.
- Winter: the regime is persistent (r = 0.84 at one day) but good days are
  rare (6 %) and half of them are gone the next day.

## Recommended replacement tables

Speed at each level is the Europe mean of the per-station percentile;
direction is the vector-mean direction rounded to 5°. Summer is JJA, winter
DJF. `midlat-turnaround-*` is May and September only, which is what that key
has meant in practice; `midlat-spring-*` (MAM) and `midlat-autumn-*` (SON)
are new keys for the full shoulder seasons. `midlat-turnaround-p90` is also
new. Paste into `WIND_PROFILES`:

```python
    "midlat-summer-p50": (
        (0, 2.2, 275), (1, 5.9, 275), (2, 7.2, 270), (3, 8.6, 270), (5, 10.8, 265),
        (7, 13.5, 265), (9, 17.1, 265), (10, 18.9, 265), (11, 19.4, 265),
        (12, 17.8, 265), (13, 15.1, 265), (14, 13, 260), (15, 11, 255), (16, 9.2, 255),
        (17, 7.4, 250), (18, 5.8, 245), (19, 4.9, 225), (20, 4.5, 170), (21, 4.3, 120),
        (22, 4.8, 105), (24, 6.1, 100), (26, 7.7, 95), (28, 8.2, 100), (30, 9, 95),
    ),
    "midlat-summer-p90": (
        (0, 4.2, 275), (1, 11.6, 275), (2, 13.2, 270), (3, 15.7, 270), (5, 20.4, 265),
        (7, 26.4, 265), (9, 33.9, 265), (10, 36.7, 265), (11, 36.8, 265),
        (12, 32.9, 265), (13, 27.7, 265), (14, 23.9, 260), (15, 20.1, 255),
        (16, 16.6, 255), (17, 13.7, 250), (18, 10.6, 245), (19, 8.3, 225),
        (20, 7.2, 170), (21, 7.6, 120), (22, 8, 105), (24, 10.2, 100), (26, 11.8, 95),
        (28, 12.5, 100), (30, 13.8, 95),
    ),
    "midlat-winter-p50": (
        (0, 3, 245), (1, 9.6, 270), (2, 10.4, 280), (3, 11.8, 285), (5, 15.7, 285),
        (7, 20.2, 290), (9, 23.6, 295), (10, 23.5, 295), (11, 22, 295), (12, 20.1, 295),
        (13, 18.9, 290), (14, 18.1, 290), (15, 18, 290), (16, 18.1, 285),
        (17, 18.1, 285), (18, 18.6, 285), (19, 19.1, 285), (20, 20.2, 285),
        (21, 21.2, 280), (22, 22.6, 280), (24, 26.5, 280), (26, 30.8, 280),
        (28, 36.2, 275), (30, 42.1, 275),
    ),
    "midlat-winter-p90": (
        (0, 5.8, 245), (1, 18.9, 270), (2, 19.7, 280), (3, 21.9, 285), (5, 29.1, 285),
        (7, 38.5, 290), (9, 45.7, 295), (10, 45.8, 295), (11, 42.7, 295),
        (12, 37.1, 295), (13, 32.8, 290), (14, 30.9, 290), (15, 30.7, 290),
        (16, 30.8, 285), (17, 31.6, 285), (18, 33, 285), (19, 34.7, 285),
        (20, 36.8, 285), (21, 39.2, 280), (22, 42, 280), (24, 48.2, 280),
        (26, 55.9, 280), (28, 63.3, 275), (30, 73.3, 275),
    ),
    "midlat-turnaround-p50": (
        (0, 2.2, 270), (1, 6.7, 265), (2, 7.5, 265), (3, 8.6, 270), (5, 11, 270),
        (7, 14.2, 270), (9, 17.6, 270), (10, 18.9, 275), (11, 18.1, 275),
        (12, 15.7, 275), (13, 13.2, 275), (14, 11.3, 270), (15, 9.8, 270),
        (16, 8.5, 265), (17, 7.5, 265), (18, 6.5, 265), (19, 5.8, 265), (20, 5.3, 265),
        (21, 5.1, 265), (22, 5, 270), (24, 5.1, 140), (26, 5.5, 115), (28, 6.4, 200),
        (30, 7.3, 240),
    ),
    "midlat-turnaround-p90": (
        (0, 4.6, 270), (1, 12.8, 265), (2, 14.2, 265), (3, 16.2, 270), (5, 21.3, 270),
        (7, 28.1, 270), (9, 35.4, 270), (10, 37.1, 275), (11, 35.9, 275), (12, 31, 275),
        (13, 25.5, 275), (14, 21.5, 270), (15, 18.4, 270), (16, 15.9, 265),
        (17, 13.9, 265), (18, 12.2, 265), (19, 10.8, 265), (20, 9.8, 265),
        (21, 9.5, 265), (22, 9.2, 270), (24, 9.8, 140), (26, 10.7, 115),
        (28, 12.2, 200), (30, 14, 240),
    ),
    "midlat-spring-p50": (
        (0, 2.5, 275), (1, 7, 275), (2, 7.9, 275), (3, 9.4, 280), (5, 12.3, 280),
        (7, 15.9, 280), (9, 19.5, 285), (10, 19.7, 285), (11, 17.9, 285),
        (12, 15.1, 285), (13, 13, 280), (14, 11.6, 280), (15, 10.6, 280),
        (16, 9.7, 280), (17, 8.9, 280), (18, 8, 280), (19, 7.4, 280), (20, 6.9, 280),
        (21, 6.8, 285), (22, 6.6, 285), (24, 7.3, 285), (26, 8, 280), (28, 9.5, 280),
        (30, 10.4, 275),
    ),
    "midlat-spring-p90": (
        (0, 5.2, 275), (1, 14.1, 275), (2, 15.3, 275), (3, 17.8, 280), (5, 24.1, 280),
        (7, 32, 280), (9, 38, 285), (10, 38, 285), (11, 34, 285), (12, 28.4, 285),
        (13, 23.9, 280), (14, 21.7, 280), (15, 20.4, 280), (16, 19.8, 280),
        (17, 19.3, 280), (18, 19.2, 280), (19, 19, 280), (20, 19.5, 280),
        (21, 20.1, 285), (22, 20.9, 285), (24, 22.1, 285), (26, 24.9, 280),
        (28, 28.6, 280), (30, 32.1, 275),
    ),
    "midlat-autumn-p50": (
        (0, 2.2, 235), (1, 7.6, 260), (2, 8.7, 265), (3, 10, 270), (5, 13.1, 275),
        (7, 16.6, 275), (9, 20.6, 280), (10, 21.8, 280), (11, 21.8, 280), (12, 20, 280),
        (13, 17.4, 280), (14, 15, 280), (15, 13.3, 280), (16, 11.8, 280),
        (17, 10.5, 280), (18, 9.6, 280), (19, 8.8, 280), (20, 8.3, 280), (21, 8.2, 280),
        (22, 8.2, 280), (24, 9, 280), (26, 10, 275), (28, 12.5, 275), (30, 16.1, 270),
    ),
    "midlat-autumn-p90": (
        (0, 4.8, 235), (1, 15.3, 260), (2, 16.6, 265), (3, 18.8, 270), (5, 25, 275),
        (7, 32.7, 275), (9, 40.2, 280), (10, 42.2, 280), (11, 41.1, 280),
        (12, 36.8, 280), (13, 31.1, 280), (14, 26.8, 280), (15, 23.6, 280),
        (16, 21.1, 280), (17, 19.3, 280), (18, 18.1, 280), (19, 17.7, 280),
        (20, 17.8, 280), (21, 18.4, 280), (22, 19.4, 280), (24, 23, 280),
        (26, 27.1, 275), (28, 33.2, 275), (30, 39.6, 270),
    ),
```

Read these before using them:

- **A p90 profile is the 90th percentile at every level at once.** No real
  day looks like that. Integrated the same way as the soundings, the
  recommended profiles overstate ascent drift by 5–8 % (p50) and 10–14 %
  (p90); see the table below. A Monte Carlo that draws a p90 profile 30 % of
  the time (`campaign.py`) is drawing a day rarer than one in ten 30 % of
  the time. Sampling real soundings, or scaling the p50 profile to match the
  drift distribution in the JSON, would be more faithful.
- **Direction near the reversal is weakly defined.** In the summer profiles
  at 19–22 km and in the turnaround profiles above 22 km the vector-mean
  wind is 1–3 m/s against a 4–5 m/s median speed, so the listed direction is
  the least-bad single value, not a forecast. `WindProfile.at` interpolates
  vectors, so speed between two nodes with different directions dips below
  both; with 1 km nodes the dip is under 20 %.
- The turnaround directions at 24–30 km average an easterly month (May)
  with a westerly one (September) and mean nothing.
- Values at 28–30 km exclude Kyiv (too few soundings reach it), as do winter
  values at 26 km.
- Level 0 is the surface wind at stations 100–300 m above sea level.

| Profile | Drift if integrated | Observed (Europe mean) |
|---|---:|---|
| `midlat-summer-p50` | 57 km | JJA p50 54 km |
| `midlat-summer-p90` | 107 km | JJA p90 97 km |
| `midlat-winter-p50` | 89 km | DJF p50 84 km |
| `midlat-winter-p90` | 165 km | DJF p90 145 km |
| `midlat-turnaround-p50` | 57 km | May/Sep p50 52 km |
| `midlat-turnaround-p90` | 111 km | May/Sep p90 99 km |
| `midlat-spring-p50` | 62 km | MAM p50 57 km |
| `midlat-spring-p90` | 123 km | MAM p90 108 km |
| `midlat-autumn-p50` | 71 km | SON p50 67 km |
| `midlat-autumn-p90` | 134 km | SON p90 122 km |

## Limits of the data

- **Survivorship.** A sounding ends when the balloon bursts or the signal is
  lost, and both are more likely in strong wind and cold. The upper bins are
  therefore biased towards calmer days. The bias is small where almost all
  soundings arrive (Lindenberg, Praha, Legionowo and the US sites: 93–99 %
  reach 20 km and 71–92 % reach 30 km) and real at Kyiv, where 76 % reach
  20 km (73 % in winter), 20 % reach 26 km and 1 % reach 30 km. Kyiv numbers above 24 km should not be used;
  Kyiv winter values at 20–22 km and Kyiv ascent-drift percentiles are
  probably a few percent low. The per-bin `n` is in the JSON.
- **Kyiv's record ends on 24 February 2022** and has gaps (370–720 soundings
  per year against a possible 730). Its winds are reported in whole m/s on
  standard and significant levels only.
- **Vertical resolution.** Archived levels in the stratosphere are 1–3 km
  apart for much of the record. Each bin is a linear vector interpolation
  between the neighbouring levels, which smooths thin shear layers and
  biases speed slightly low where the wind reverses between two levels.
  Kyiv's summer 20 km median (4.0 m/s) against the denser stations (4.6–4.8)
  shows the size of the effect. Gaps wider than 3.5 km are not interpolated.
- **Not a vertical profile.** A sonde drifts 50–150 km downwind while it
  climbs; the "profile" is a slant path, which is also what an ascending
  airship flies.
- **Two samples a day** (00Z, 12Z). Nothing here resolves gravity waves,
  turbulence or diurnal variation; gust statistics still need another source.
- **Heights are geopotential metres above sea level**, not above ground. Dodge
  City is at 790 m and Bismarck at 506 m, so their ascent columns are
  shorter.
- **Interannual variability is not separated.** Twenty-two winters include
  several sudden stratospheric warmings and both QBO phases, pooled. A
  single winter can differ from the percentiles here by more than the spread
  between stations.
- **Percentiles pooled across stations are means of station percentiles**,
  not percentiles of a pooled sample. The difference is below the
  station-to-station spread.
- **Launch-site bias.** None of these stations is the launch site. Within
  central and eastern Europe the four agree closely; for anywhere else, run
  the tool on the nearest IGRA station.
- No reanalysis (ERA5) was used; this is observation only.
