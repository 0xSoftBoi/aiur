"""Tests for the carrier-wake air disturbance.

Wake is the air disturbance in the exact volume where capture happens, and
historically the effect that decided aerial recovery. The twin was silent on
it; these guard the model that fills that gap. Two layers: the wake field
geometry (a unit test, no episodes), and that it is genuinely off by default
(a recovery episode is unchanged) and bites when enabled.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiur.sim.disturbances import CarrierWakeParams
from aiur.sim.engine import EpisodeOutcome, run_episode
from aiur.sim.scenarios import carrier_wake_case, sil_p0b
from aiur.sim.vec import Vec3


class WakeField(unittest.TestCase):
    def test_disabled_wake_is_zero_everywhere(self):
        wake = CarrierWakeParams()  # downwash 0 -> off
        self.assertFalse(wake.enabled)
        dock = Vec3(0.0, 0.0, 2.0)
        for pos in (dock, Vec3(0.1, 0.0, 1.9), Vec3(1.0, 1.0, 0.5)):
            self.assertEqual(wake.velocity_at(pos, dock), Vec3())

    def test_downwash_is_downward_and_peaks_at_the_dock(self):
        wake = CarrierWakeParams(downwash_m_s=0.3)
        dock = Vec3(0.0, 0.0, 2.0)
        at_dock = wake.velocity_at(dock, dock)
        self.assertAlmostEqual(at_dock.z, -0.3)  # full downwash at the throat
        self.assertEqual(at_dock.x, 0.0)
        self.assertEqual(at_dock.y, 0.0)

    def test_wake_falls_off_with_distance(self):
        wake = CarrierWakeParams(downwash_m_s=0.3, radius_m=0.3, vertical_scale_m=0.4)
        dock = Vec3(0.0, 0.0, 2.0)
        near = abs(wake.velocity_at(Vec3(0.05, 0.0, 2.0), dock).z)
        far_horizontal = abs(wake.velocity_at(Vec3(0.6, 0.0, 2.0), dock).z)
        far_below = abs(wake.velocity_at(Vec3(0.0, 0.0, 1.2), dock).z)
        self.assertGreater(near, far_horizontal)
        self.assertGreater(near, far_below)

    def test_validation_rejects_bad_parameters(self):
        with self.assertRaises(ValueError):
            CarrierWakeParams(downwash_m_s=-0.1)
        with self.assertRaises(ValueError):
            CarrierWakeParams(downwash_m_s=0.3, radius_m=0.0)
        with self.assertRaises(ValueError):
            CarrierWakeParams(downwash_m_s=0.3, vertical_scale_m=-1.0)


class WakeInEpisodes(unittest.TestCase):
    def test_wake_off_reproduces_the_baseline_episode_exactly(self):
        # The default CarrierWakeParams() must leave a recovery episode
        # byte-identical: same outcome, duration, and event trace. This is
        # the guarantee that adding wake changed nothing already committed.
        for seed in (1, 2, 3):
            base = run_episode(sil_p0b(seed), seed)
            with_default = run_episode(
                carrier_wake_case(seed, 0.0), seed
            )
            self.assertEqual(base.outcome, with_default.outcome)
            self.assertEqual(base.duration_s, with_default.duration_s)
            self.assertEqual(base.captures, with_default.captures)

    def test_strong_wake_collapses_capture_without_going_unsafe(self):
        # A downwash well past the terminal approach-speed budget pushes the
        # drone away faster than it closes, so capture collapses — but the
        # supervisor aborts rather than crashes, so no episode is unsafe.
        # Wake costs capture rate, not safety; that distinction is the point.
        captured = unsafe = 0
        for seed in range(1, 11):
            r = run_episode(carrier_wake_case(seed, 0.4), seed)
            if r.outcome is EpisodeOutcome.SUCCESS:
                captured += 1
            if r.unsafe_events:
                unsafe += 1
        self.assertLessEqual(captured, 2)  # collapsed
        self.assertEqual(unsafe, 0)  # but safe

    def test_capture_is_monotone_nonincreasing_in_downwash(self):
        def rate(downwash: float) -> int:
            return sum(
                run_episode(carrier_wake_case(s, downwash), s).outcome
                is EpisodeOutcome.SUCCESS
                for s in range(1, 9)
            )

        calm, mild, strong = rate(0.0), rate(0.15), rate(0.4)
        self.assertGreaterEqual(calm, mild)
        self.assertGreaterEqual(mild, strong)


if __name__ == "__main__":
    unittest.main()
