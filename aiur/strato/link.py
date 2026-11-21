"""Radio link budgets from float altitude.

From 20 km the radio horizon is ~500 km and every link is line-of-sight, so
range is set by free-space loss and receiver sensitivity alone - which is why
25 mW LoRa trackers are routinely heard at 500-800 km from balloons, and why
a stratospheric relay is worth building at all.

Sensitivities are [cited] vendor figures for the stated modes; antenna gains
and the fade margin are [estimate].
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sys

R_EARTH_RADIO = 6_371_000.0 * 4.0 / 3.0  #: 4/3-earth refraction model [physics]


@dataclass(frozen=True)
class Radio:
    name: str
    freq_mhz: float
    tx_dbm: float
    rx_sensitivity_dbm: float
    air_antenna_dbi: float
    ground_antenna_dbi: float
    data_rate: str
    role: str
    losses_db: float = 3.0


RADIOS = {
    "elrs-900-50hz": Radio("ExpressLRS 900 MHz, 50 Hz, 100 mW", 915.0, 20.0, -117.0, 2.0, 8.0,
                           "~2 kbit/s MAVLink", "C2 + telemetry"),
    "elrs-2g4-50hz": Radio("ExpressLRS 2.4 GHz, 50 Hz, 100 mW", 2440.0, 20.0, -115.0, 2.0, 14.0,
                           "~2 kbit/s MAVLink", "C2 + telemetry (second band)"),
    "mlrs-868-19hz": Radio("mLRS 868 MHz, 19 Hz, 1 W", 868.0, 30.0, -122.0, 2.0, 8.0,
                           "~1.5 kbit/s MAVLink", "C2 alternative"),
    "lora-sf10": Radio("LoRa SF10/125 kHz, 22 dBm", 868.0, 22.0, -132.0, 0.0, 6.0,
                       "~1 kbit/s", "termination unit: position + cut-down"),
    "wfb-5g8-mcs1": Radio("wfb-ng / OpenIPC 5.8 GHz MCS1, 500 mW", 5800.0, 27.0, -88.0, 3.0, 24.0,
                          "~6 Mbit/s video", "payload downlink"),
    "iridium-sbd": Radio("Iridium SBD", 1621.0, 32.0, -117.0, 3.0, 3.0,
                         "340-byte messages", "beyond-horizon tracking", 2.0),
}


def horizon_km(altitude_m: float, ground_antenna_m: float = 2.0) -> float:
    return (math.sqrt(2.0 * R_EARTH_RADIO * altitude_m)
            + math.sqrt(2.0 * R_EARTH_RADIO * ground_antenna_m)) / 1000.0


def slant_range_km(altitude_m: float, ground_range_km: float) -> float:
    return math.hypot(altitude_m / 1000.0, ground_range_km)


def fspl_db(distance_km: float, freq_mhz: float) -> float:
    return 20.0 * math.log10(distance_km) + 20.0 * math.log10(freq_mhz) + 32.44


def margin_db(radio: Radio, altitude_m: float, ground_range_km: float) -> float:
    d = slant_range_km(altitude_m, ground_range_km)
    rx = (radio.tx_dbm + radio.air_antenna_dbi + radio.ground_antenna_dbi
          - radio.losses_db - fspl_db(d, radio.freq_mhz))
    return rx - radio.rx_sensitivity_dbm


def max_range_km(radio: Radio, altitude_m: float, fade_margin_db: float = 10.0) -> float:
    """Largest ground range with ``fade_margin_db`` in hand, capped at the horizon."""

    hz = horizon_km(altitude_m)
    lo, hi = 0.1, hz
    if margin_db(radio, altitude_m, hi) >= fade_margin_db:
        return hz
    if margin_db(radio, altitude_m, lo) < fade_margin_db:
        return 0.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if margin_db(radio, altitude_m, mid) >= fade_margin_db:
            lo = mid
        else:
            hi = mid
    return lo


def relay_coverage(altitude_m: float) -> dict:
    """Ground footprint of the vehicle as a relay, by elevation mask."""

    out = {}
    for mask in (0.0, 5.0, 10.0, 20.0):
        # Ground range at which the vehicle sits ``mask`` degrees above the horizon.
        e = math.radians(mask)
        r = 6_371_000.0
        central = math.acos(r * math.cos(e) / (r + altitude_m)) - e
        out[f"{mask:g} deg"] = round(r * central / 1000.0, 0)
    return out


def table(altitude_m: float = 20_000.0) -> dict:
    out = {"altitude_m": altitude_m, "radio_horizon_km": round(horizon_km(altitude_m), 0),
           "coverage_radius_km_by_elevation_mask": relay_coverage(altitude_m), "links": {}}
    for key, r in RADIOS.items():
        if key == "iridium-sbd":
            continue
        out["links"][key] = {
            "name": r.name, "role": r.role, "rate": r.data_rate,
            "margin_db_at_100km": round(margin_db(r, altitude_m, 100.0), 1),
            "margin_db_at_300km": round(margin_db(r, altitude_m, 300.0), 1),
            "range_km_with_10db_margin": round(max_range_km(r, altitude_m), 0),
        }
    return out


def main(argv: list[str]) -> int:
    t = table()
    if "--json" in argv:
        print(json.dumps(t, indent=2))
        return 0
    print(f"links from {t['altitude_m']/1000:g} km: radio horizon {t['radio_horizon_km']:.0f} km, "
          f"coverage radius {t['coverage_radius_km_by_elevation_mask']}")
    for k, v in t["links"].items():
        print(f"  {v['name']:42s} {v['margin_db_at_100km']:6.1f} dB @100 km  "
              f"{v['margin_db_at_300km']:6.1f} dB @300 km  "
              f"{v['range_km_with_10db_margin']:5.0f} km w/ 10 dB   {v['role']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
