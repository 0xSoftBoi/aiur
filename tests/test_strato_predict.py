import json
import math
import tempfile
import unittest
from pathlib import Path

from aiur.strato import SoundingBalloon
from aiur.strato_predict import (
    WindSample,
    commitment,
    ensemble,
    main,
    predict,
    read_sounding,
    validate_sounding,
    wind_at,
)

TEMPLATE = Path(__file__).resolve().parents[1] / "hardware" / "strato" / "s0-sounding-template.csv"


def calm() -> tuple[WindSample, ...]:
    return (WindSample(0.0, 0.0, 0.0), WindSample(40_000.0, 0.0, 0.0))


def westerly(speed: float = 10.0) -> tuple[WindSample, ...]:
    return (WindSample(0.0, speed, 270.0), WindSample(40_000.0, speed, 270.0))


class WindConventionTests(unittest.TestCase):
    def test_a_westerly_blows_east(self) -> None:
        u, v = WindSample(0.0, 10.0, 270.0).vector()
        self.assertAlmostEqual(u, 10.0, places=9)
        self.assertAlmostEqual(v, 0.0, places=9)
        u, v = WindSample(0.0, 10.0, 0.0).vector()
        self.assertAlmostEqual(v, -10.0, places=9)

    def test_components_interpolate_through_north(self) -> None:
        samples = (WindSample(0.0, 10.0, 350.0), WindSample(1000.0, 10.0, 10.0))
        u, v = wind_at(samples, 500.0)
        self.assertAlmostEqual(u, 0.0, places=9)
        self.assertLess(v, -9.0, "a veer through north must not produce a calm")

    def test_clamped_outside_the_sounding(self) -> None:
        samples = westerly()
        self.assertEqual(wind_at(samples, -10.0), samples[0].vector())
        self.assertEqual(wind_at(samples, 99_000.0), samples[-1].vector())

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            validate_sounding((WindSample(0.0, 1.0, 0.0),))
        with self.assertRaises(ValueError):
            validate_sounding((WindSample(1000.0, 1.0, 0.0), WindSample(0.0, 1.0, 0.0)))
        with self.assertRaises(ValueError):
            validate_sounding((WindSample(0.0, -1.0, 0.0), WindSample(1.0, 1.0, 0.0)))
        with self.assertRaises(ValueError):
            validate_sounding((WindSample(0.0, 1.0, 400.0), WindSample(1.0, 1.0, 0.0)))


class PredictionTests(unittest.TestCase):
    def test_calm_air_lands_at_the_launch_point(self) -> None:
        p = predict(calm())
        self.assertAlmostEqual(p.range_km, 0.0, places=9)
        self.assertAlmostEqual(p.burst_altitude_m, SoundingBalloon().burst_altitude_m(), places=6)
        self.assertGreater(p.ascent_s, 60 * 60)
        self.assertGreater(p.descent_s, 0.0)

    def test_uniform_westerly_drifts_east_by_speed_times_time(self) -> None:
        p = predict(westerly(10.0))
        expected_km = 10.0 * (p.ascent_s + p.descent_s) / 1000.0
        self.assertAlmostEqual(p.landing_east_km, expected_km, delta=0.05 * expected_km)
        self.assertAlmostEqual(p.landing_north_km, 0.0, places=6)
        self.assertAlmostEqual(p.bearing_deg, 90.0, places=3)

    def test_track_is_monotonic_in_time_and_ends_on_the_ground(self) -> None:
        p = predict(read_sounding(TEMPLATE))
        times = [point[0] for point in p.track]
        self.assertEqual(times, sorted(times))
        self.assertEqual(p.track[-1][1], 0.0)
        self.assertGreater(max(point[1] for point in p.track), 30_000.0)

    def test_heavier_package_shorter_flight(self) -> None:
        light = predict(westerly(), SoundingBalloon(payload_mass_kg=0.5))
        heavy = predict(westerly(), SoundingBalloon(payload_mass_kg=1.5))
        self.assertLess(heavy.burst_altitude_m, light.burst_altitude_m)

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            predict(calm(), step_s=0.0)
        with self.assertRaises(ValueError):
            predict(calm(), launch_altitude_m=-1.0)


class EnsembleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ens = ensemble(read_sounding(TEMPLATE), samples=32, seed=3)

    def test_ellipse_is_positive_and_the_fence_contains_every_member(self) -> None:
        self.assertGreater(self.ens.semi_major_km, 0.0)
        self.assertGreaterEqual(self.ens.semi_major_km, self.ens.semi_minor_km)
        self.assertGreaterEqual(self.ens.geofence_km, 1.5 * self.ens.nominal.range_km)
        self.assertGreater(self.ens.geofence_km, self.ens.max_range_km)
        self.assertTrue(0.0 <= self.ens.major_axis_bearing_deg < 180.0)

    def test_is_deterministic_for_a_seed(self) -> None:
        again = ensemble(read_sounding(TEMPLATE), samples=32, seed=3)
        self.assertEqual(again.geofence_km, self.ens.geofence_km)
        self.assertEqual(again.semi_major_km, self.ens.semi_major_km)

    def test_calm_ensemble_has_no_scatter(self) -> None:
        ens = ensemble(calm(), samples=16, seed=1)
        self.assertAlmostEqual(ens.semi_major_km, 0.0, places=9)
        self.assertGreaterEqual(ens.geofence_km, 10.0)

    def test_too_few_samples_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ensemble(calm(), samples=4)

    def test_commitment_carries_the_manifest_fields(self) -> None:
        data = commitment(self.ens, sounding_path="x.csv")
        for field in ("predicted_landing_x_km", "predicted_landing_y_km", "geofence_km", "ellipse_2sigma"):
            self.assertIn(field, data)
        self.assertEqual(data["evidence_kind"], "model")
        self.assertAlmostEqual(
            math.hypot(data["predicted_landing_x_km"], data["predicted_landing_y_km"]),
            data["predicted_range_km"],
            places=1,
        )


class CliTests(unittest.TestCase):
    def test_writes_the_commitment_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "prediction.json"
            code = main(["--sounding", str(TEMPLATE), "--samples", "16", "--out", str(out), "--track"])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text())
            self.assertIn("track", data)
            self.assertGreater(data["geofence_km"], data["predicted_range_km"])


if __name__ == "__main__":
    unittest.main()
