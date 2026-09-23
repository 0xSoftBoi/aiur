"""Launch-day landing prediction for STRATO-P0 from a measured wind sounding.

The launch checklist commits a predicted landing point, an ellipse, and a
geofence before the balloon is filled, and S0-C judges the flown landing
against that commitment (S0-FLT-003).  This module is the tool that makes
the commitment: it integrates the constant-gas-mass ascent from
``aiur.strato`` and the parachute descent through a wind profile the crew
supplies, then perturbs the things a sounding does not pin down — free
lift, burst diameter, wind speed and direction — in a seeded ensemble to
size the ellipse and the geofence.

Conventions
-----------
* The sounding gives wind *from* a bearing, meteorological style: 270°
  means a westerly, blowing toward the east.
* Landing offsets are east (x) and north (y) in kilometres from the launch
  point, the same axes ``aiur.strato_sim`` logs.
* The ellipse is the 2-sigma spread of the ensemble; the geofence is the
  larger of 1.5x the mean range and the farthest ensemble member plus a
  margin, so a nominal flight never breaches its own fence.

A prediction is a model result in a reference atmosphere with the day's
wind; it is what the crew commits, not what the balloon will do.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .strato import SoundingBalloon, parachute_descent_rate_m_s

SOUNDING_FIELDS = ("altitude_m", "wind_speed_m_s", "wind_from_deg")


@dataclass(frozen=True)
class WindSample:
    altitude_m: float
    speed_m_s: float
    from_deg: float

    def vector(self) -> tuple[float, float]:
        """(east, north) velocity the air is moving *toward*."""

        rad = math.radians(self.from_deg)
        return (-self.speed_m_s * math.sin(rad), -self.speed_m_s * math.cos(rad))


def read_sounding(path: Path) -> tuple[WindSample, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path}: empty sounding")
    missing = [f for f in SOUNDING_FIELDS if f not in rows[0]]
    if missing:
        raise ValueError(f"{path}: missing columns {', '.join(missing)}")
    samples = []
    for index, row in enumerate(rows):
        try:
            sample = WindSample(
                float(row["altitude_m"]), float(row["wind_speed_m_s"]), float(row["wind_from_deg"])
            )
        except ValueError as exc:
            raise ValueError(f"{path} row {index + 1}: non-numeric value") from exc
        samples.append(sample)
    return validate_sounding(tuple(samples))


def validate_sounding(samples: tuple[WindSample, ...]) -> tuple[WindSample, ...]:
    if len(samples) < 2:
        raise ValueError("a sounding needs at least two levels")
    altitudes = [s.altitude_m for s in samples]
    if altitudes != sorted(altitudes) or len(set(altitudes)) != len(altitudes):
        raise ValueError("sounding levels must be strictly increasing in altitude")
    if any(s.speed_m_s < 0 for s in samples):
        raise ValueError("wind speed must be non-negative")
    if any(not 0.0 <= s.from_deg <= 360.0 for s in samples):
        raise ValueError("wind direction must be in [0, 360]")
    return samples


def wind_at(samples: tuple[WindSample, ...], altitude_m: float) -> tuple[float, float]:
    """Linear interpolation of the (east, north) components; clamped at the ends.

    Components are interpolated rather than speed and bearing so a veer
    through north does not produce a spurious calm between levels.
    """

    if altitude_m <= samples[0].altitude_m:
        return samples[0].vector()
    if altitude_m >= samples[-1].altitude_m:
        return samples[-1].vector()
    for low, high in zip(samples, samples[1:]):
        if low.altitude_m <= altitude_m <= high.altitude_m:
            f = (altitude_m - low.altitude_m) / (high.altitude_m - low.altitude_m)
            lu, lv = low.vector()
            hu, hv = high.vector()
            return (lu + f * (hu - lu), lv + f * (hv - lv))
    raise AssertionError("unreachable: altitude inside the sounding was not bracketed")


@dataclass(frozen=True)
class Prediction:
    landing_east_km: float
    landing_north_km: float
    range_km: float
    bearing_deg: float
    burst_altitude_m: float
    ascent_s: float
    descent_s: float
    #: (t_s, altitude_m, east_km, north_km) every ``track_every_s``.
    track: tuple[tuple[float, float, float, float], ...]


def predict(
    sounding: tuple[WindSample, ...],
    balloon: SoundingBalloon = SoundingBalloon(),
    *,
    canopy_area_m2: float = 0.73,
    launch_altitude_m: float = 0.0,
    step_s: float = 10.0,
    track_every_s: float = 60.0,
) -> Prediction:
    """Integrate one flight through the sounding."""

    if step_s <= 0 or track_every_s <= 0:
        raise ValueError("steps must be positive")
    if launch_altitude_m < 0:
        raise ValueError("launch altitude must be non-negative")
    burst = balloon.burst_altitude_m()
    if burst <= launch_altitude_m:
        raise ValueError("balloon bursts below the launch altitude")

    t = 0.0
    altitude = launch_altitude_m
    east = 0.0
    north = 0.0
    track = [(0.0, altitude, 0.0, 0.0)]
    next_track = track_every_s

    def drift(dt: float) -> None:
        nonlocal east, north
        u, v = wind_at(sounding, altitude)
        east += u * dt / 1000.0
        north += v * dt / 1000.0

    while altitude < burst:
        dt = min(step_s, (burst - altitude) / balloon.ascent_rate_at_m_s(altitude))
        drift(dt)
        altitude = min(burst, altitude + balloon.ascent_rate_at_m_s(altitude) * dt)
        t += dt
        if t >= next_track:
            track.append((round(t, 1), round(altitude, 1), round(east, 3), round(north, 3)))
            next_track += track_every_s
    ascent_s = t

    while altitude > launch_altitude_m:
        rate = parachute_descent_rate_m_s(balloon.payload_mass_kg, canopy_area_m2, altitude_m=altitude)
        dt = min(step_s, (altitude - launch_altitude_m) / rate)
        drift(dt)
        altitude = max(launch_altitude_m, altitude - rate * dt)
        t += dt
        if t >= next_track:
            track.append((round(t, 1), round(altitude, 1), round(east, 3), round(north, 3)))
            next_track += track_every_s
    track.append((round(t, 1), round(altitude, 1), round(east, 3), round(north, 3)))

    return Prediction(
        landing_east_km=east,
        landing_north_km=north,
        range_km=math.hypot(east, north),
        bearing_deg=math.degrees(math.atan2(east, north)) % 360.0,
        burst_altitude_m=burst,
        ascent_s=ascent_s,
        descent_s=t - ascent_s,
        track=tuple(track),
    )


@dataclass(frozen=True)
class Ensemble:
    nominal: Prediction
    mean_east_km: float
    mean_north_km: float
    #: 2-sigma semi-axes of the landing scatter and the orientation of the
    #: major axis, degrees clockwise from north.
    semi_major_km: float
    semi_minor_km: float
    major_axis_bearing_deg: float
    max_range_km: float
    geofence_km: float
    samples: int
    seed: int


def _perturbed(
    rng: random.Random,
    sounding: tuple[WindSample, ...],
    balloon: SoundingBalloon,
    *,
    lift_sigma: float,
    burst_sigma: float,
    speed_sigma: float,
    direction_sigma_deg: float,
) -> tuple[tuple[WindSample, ...], SoundingBalloon]:
    lift = max(0.2, 1.0 + rng.gauss(0.0, lift_sigma))
    burst = max(0.5, 1.0 + rng.gauss(0.0, burst_sigma))
    speed = max(0.0, 1.0 + rng.gauss(0.0, speed_sigma))
    turn = rng.gauss(0.0, direction_sigma_deg)
    wind = tuple(
        WindSample(s.altitude_m, s.speed_m_s * speed, (s.from_deg + turn) % 360.0) for s in sounding
    )
    return wind, replace(
        balloon,
        free_lift_kg=balloon.free_lift_kg * lift,
        burst_diameter_m=balloon.burst_diameter_m * burst,
    )


def ensemble(
    sounding: tuple[WindSample, ...],
    balloon: SoundingBalloon = SoundingBalloon(),
    *,
    canopy_area_m2: float = 0.73,
    samples: int = 64,
    seed: int = 1,
    lift_sigma: float = 0.15,
    burst_sigma: float = 0.04,
    speed_sigma: float = 0.15,
    direction_sigma_deg: float = 8.0,
    geofence_factor: float = 1.5,
    geofence_margin_km: float = 10.0,
) -> Ensemble:
    """Seeded perturbation ensemble; sizes the ellipse and the geofence.

    The sigmas are engineering assumptions about what a sounding and a
    neck-lift measurement leave uncertain; the first flights replace them
    with measured scatter (S0-FLT-003 is the check).
    """

    if samples < 8:
        raise ValueError("an ensemble needs at least 8 samples")
    rng = random.Random(seed)
    nominal = predict(sounding, balloon, canopy_area_m2=canopy_area_m2)
    points = []
    for _ in range(samples):
        wind, perturbed = _perturbed(
            rng,
            sounding,
            balloon,
            lift_sigma=lift_sigma,
            burst_sigma=burst_sigma,
            speed_sigma=speed_sigma,
            direction_sigma_deg=direction_sigma_deg,
        )
        p = predict(wind, perturbed, canopy_area_m2=canopy_area_m2)
        points.append((p.landing_east_km, p.landing_north_km))

    n = len(points)
    mean_e = sum(p[0] for p in points) / n
    mean_n = sum(p[1] for p in points) / n
    see = sum((p[0] - mean_e) ** 2 for p in points) / (n - 1)
    snn = sum((p[1] - mean_n) ** 2 for p in points) / (n - 1)
    sen = sum((p[0] - mean_e) * (p[1] - mean_n) for p in points) / (n - 1)
    # Eigen-decomposition of the 2x2 covariance.
    trace = see + snn
    det = see * snn - sen * sen
    disc = math.sqrt(max(0.0, trace * trace / 4.0 - det))
    lam_major = trace / 2.0 + disc
    lam_minor = max(0.0, trace / 2.0 - disc)
    if abs(sen) > 1e-12:
        vec_e, vec_n = lam_major - snn, sen
    else:
        vec_e, vec_n = (1.0, 0.0) if see >= snn else (0.0, 1.0)
    bearing = math.degrees(math.atan2(vec_e, vec_n)) % 180.0
    max_range = max(math.hypot(*p) for p in points)
    geofence = max(geofence_factor * nominal.range_km, max_range + geofence_margin_km)
    return Ensemble(
        nominal=nominal,
        mean_east_km=mean_e,
        mean_north_km=mean_n,
        semi_major_km=2.0 * math.sqrt(lam_major),
        semi_minor_km=2.0 * math.sqrt(lam_minor),
        major_axis_bearing_deg=bearing,
        max_range_km=max_range,
        geofence_km=geofence,
        samples=samples,
        seed=seed,
    )


def commitment(ens: Ensemble, *, sounding_path: str) -> dict[str, object]:
    """The fields the launch checklist commits into the flight manifest."""

    return {
        "sounding": sounding_path,
        "predicted_landing_x_km": round(ens.nominal.landing_east_km, 3),
        "predicted_landing_y_km": round(ens.nominal.landing_north_km, 3),
        "predicted_range_km": round(ens.nominal.range_km, 2),
        "predicted_bearing_deg": round(ens.nominal.bearing_deg, 1),
        "predicted_burst_altitude_m": round(ens.nominal.burst_altitude_m, 0),
        "predicted_ascent_min": round(ens.nominal.ascent_s / 60.0, 1),
        "predicted_descent_min": round(ens.nominal.descent_s / 60.0, 1),
        "ellipse_2sigma": {
            "center_x_km": round(ens.mean_east_km, 3),
            "center_y_km": round(ens.mean_north_km, 3),
            "semi_major_km": round(ens.semi_major_km, 2),
            "semi_minor_km": round(ens.semi_minor_km, 2),
            "major_axis_bearing_deg": round(ens.major_axis_bearing_deg, 1),
        },
        "ensemble_max_range_km": round(ens.max_range_km, 2),
        "geofence_km": round(ens.geofence_km, 1),
        "ensemble": {"samples": ens.samples, "seed": ens.seed},
        "axes": "x east, y north, km from the launch point",
        "evidence_kind": "model",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Predict the STRATO-P0 landing from a wind sounding.")
    parser.add_argument("--sounding", type=Path, required=True, help="CSV: altitude_m, wind_speed_m_s, wind_from_deg")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--payload-kg", type=float, default=None)
    parser.add_argument("--free-lift-kg", type=float, default=None)
    parser.add_argument("--canopy-m2", type=float, default=0.73)
    parser.add_argument("--out", type=Path, default=None, help="write the commitment JSON here")
    parser.add_argument("--track", action="store_true", help="include the nominal track")
    args = parser.parse_args(argv)

    balloon = SoundingBalloon()
    if args.payload_kg is not None:
        balloon = replace(balloon, payload_mass_kg=args.payload_kg)
    if args.free_lift_kg is not None:
        balloon = replace(balloon, free_lift_kg=args.free_lift_kg)
    sounding = read_sounding(args.sounding)
    ens = ensemble(sounding, balloon, canopy_area_m2=args.canopy_m2, samples=args.samples, seed=args.seed)
    result = commitment(ens, sounding_path=str(args.sounding))
    if args.track:
        result["track"] = [list(point) for point in ens.nominal.track]
    text = json.dumps(result, indent=2)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
