"""Tests for the fleet-throughput model's queue and its reduction.

These do not run the twin.  Calibration is covered by one test that checks
the contract at the seam; everything else drives the discrete-event queue
with a synthetic :class:`ServiceModel`, because what needs guarding here is
not the capture physics — the mechanism suites own that — but the layer
that turns a service time into a head count.

That layer is where a mistake is quiet.  The model already produced one:
losses were counted only inside the measurement window, so a configuration
that destroyed four fifths of its fleet during warm-up reported a 0% loss
rate and a healthy throughput for the survivors.  The result was
well-formed, plausible, and would have sized a carrier wrong.  Several
tests below exist specifically to keep that class of failure loud.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiur.sim.fleet import (
    LOSS_THRESHOLD_PCT,
    FleetParams,
    ServiceModel,
    calibrate_service,
    run_study,
    simulate_fleet,
    sweep_heads,
)
from tools.report_fleet import render


def service(p_capture: float = 1.0, occupancy: float = 20.0) -> ServiceModel:
    return ServiceModel(
        p_capture=p_capture,
        ci_low=max(0.0, p_capture - 0.05),
        ci_high=min(1.0, p_capture + 0.05),
        occupancy_samples_s=(occupancy,),
        episodes=40,
        source="synthetic",
    )


class ParameterValidation(unittest.TestCase):
    def test_sortie_must_leave_a_reserve(self):
        with self.assertRaises(ValueError):
            simulate_fleet(
                FleetParams(endurance_s=600.0, sortie_s=600.0), service()
            )

    def test_rejects_unknown_queue_policy(self):
        with self.assertRaises(ValueError):
            simulate_fleet(FleetParams(queue_policy="lifo"), service())

    def test_rejects_empty_carrier(self):
        for bad in (
            FleetParams(capture_heads=0),
            FleetParams(fleet_size=0),
            FleetParams(magazine_slots=0),
        ):
            with self.assertRaises(ValueError):
                simulate_fleet(bad, service())

    def test_slots_default_to_one_per_aircraft(self):
        self.assertEqual(FleetParams(fleet_size=17).slots, 17)
        self.assertEqual(FleetParams(fleet_size=17, magazine_slots=4).slots, 4)


class Determinism(unittest.TestCase):
    def test_same_seed_reproduces_the_run(self):
        params = FleetParams(fleet_size=60, capture_heads=2)
        first = simulate_fleet(params, service(0.9), seed=7)
        second = simulate_fleet(params, service(0.9), seed=7)
        self.assertEqual(first, second)

    def test_different_seeds_are_not_forced_to_agree(self):
        params = FleetParams(fleet_size=200, capture_heads=1)
        runs = {
            simulate_fleet(params, service(0.85), seed=s).recoveries
            for s in (1, 2, 3, 4)
        }
        self.assertGreater(len(runs), 1, "seeding is not reaching the queue")


class LossAccounting(unittest.TestCase):
    """The regression suite for the warm-up-blindness bug."""

    def test_attrition_is_visible_even_when_it_happens_during_warmup(self):
        # One head, a large fleet, and a service time far too slow for it:
        # the queue overruns the reserve and aircraft come down.  Whenever
        # that happens it must appear in the loss rate, not be hidden by
        # the measurement window.
        result = simulate_fleet(
            FleetParams(fleet_size=200, capture_heads=1, recharge_s=600.0),
            service(occupancy=90.0),
            seed=1,
        )
        self.assertGreater(result.loss_pct, LOSS_THRESHOLD_PCT)
        self.assertGreater(result.losses_reserve_exhausted, 0)
        self.assertLess(result.fleet_remaining, 200)
        self.assertFalse(result.serves_fleet)

    def test_fleet_remaining_tracks_losses_exactly(self):
        result = simulate_fleet(
            FleetParams(fleet_size=120, capture_heads=1, recharge_s=600.0),
            service(occupancy=75.0),
            seed=3,
        )
        lost = result.losses_reserve_exhausted + result.losses_retries_exhausted
        self.assertEqual(result.fleet_remaining, 120 - lost)

    def test_a_well_served_fleet_loses_nothing(self):
        result = simulate_fleet(
            FleetParams(fleet_size=50, capture_heads=4), service(), seed=1
        )
        self.assertEqual(result.loss_pct, 0.0)
        self.assertEqual(result.fleet_remaining, 50)
        self.assertTrue(result.serves_fleet)

    def test_retry_exhaustion_is_reported_separately_from_reserve(self):
        # A mechanism that misses most of the time burns retries rather
        # than reserve; the two are different hardware problems and must
        # not be summed into one number.
        result = simulate_fleet(
            FleetParams(fleet_size=40, capture_heads=6, retry_limit=2),
            service(p_capture=0.05, occupancy=5.0),
            seed=1,
        )
        self.assertGreater(result.losses_retries_exhausted, 0)


class BindingConstraint(unittest.TestCase):
    def test_storage_starvation_is_named_and_measured(self):
        # Far more heads than needed, but almost nowhere to put a captured
        # aircraft: the carrier must report slots, not heads.
        result = simulate_fleet(
            FleetParams(
                fleet_size=100,
                capture_heads=6,
                magazine_slots=3,
                recharge_s=1800.0,
            ),
            service(),
            seed=1,
        )
        self.assertIn("magazine slots", result.binding_constraint)
        self.assertGreater(
            result.head_blocked_fraction,
            0.0,
            "heads blocked by full storage must be measured, not inferred",
        )

    def test_head_saturation_is_named(self):
        result = simulate_fleet(
            FleetParams(fleet_size=200, capture_heads=1, recharge_s=900.0),
            service(occupancy=45.0),
            seed=1,
        )
        self.assertIn("capture heads", result.binding_constraint)
        self.assertGreaterEqual(result.head_utilisation, 0.85)

    def test_launch_capacity_is_named_even_though_the_queue_looks_healthy(self):
        # The failure mode this check exists for: a launch-limited carrier
        # has an *empty* recovery queue and zero losses, because it cannot
        # get aircraft airborne fast enough to build one. Every recovery
        # metric reads as healthy while the vehicle is capped, so a
        # diagnosis that only looks at heads and slots calls it fine.
        result = simulate_fleet(
            FleetParams(
                fleet_size=1200,
                capture_heads=12,
                launch_lanes=1,
                launch_interval_s=5.0,
            ),
            service(),
            seed=1,
        )
        self.assertEqual(result.loss_pct, 0.0)
        self.assertLess(result.head_utilisation, 0.85)
        self.assertGreaterEqual(result.launch_utilisation, 0.85)
        self.assertIn("launch lanes", result.binding_constraint)
        # One lane at 5 s spacing is 720 sorties/hour and nothing else.
        self.assertLessEqual(result.throughput_per_hour, 720.0 * 1.02)

    def test_adding_lanes_lifts_a_launch_limited_carrier(self):
        common = dict(fleet_size=1200, capture_heads=12)
        one = simulate_fleet(FleetParams(**common, launch_lanes=1), service(), seed=1)
        two = simulate_fleet(FleetParams(**common, launch_lanes=2), service(), seed=1)
        self.assertGreater(two.throughput_per_hour, one.throughput_per_hour)
        self.assertGreater(two.mean_airborne, one.mean_airborne)
        self.assertNotIn("launch lanes", two.binding_constraint)

    def test_a_charge_limited_fleet_is_not_blamed_on_the_dock(self):
        result = simulate_fleet(
            FleetParams(fleet_size=100, capture_heads=8, recharge_s=7200.0),
            service(),
            seed=1,
        )
        self.assertNotIn("capture heads", result.binding_constraint)
        self.assertLess(result.head_utilisation, 0.85)


class BuoyantTrim(unittest.TestCase):
    """The coupling the twin has never represented.

    A buoyant carrier that releases mass without landing gains lift.  The
    fleet is therefore not just something the carrier serves — it is a
    disturbance input to the carrier's own trim, and the failure is silent:
    losses stay at zero and every utilisation looks comfortable while the
    dock drifts vertically under aircraft on final approach.
    """

    def test_slow_ballast_cannot_follow_the_fleet(self):
        result = simulate_fleet(
            FleetParams(
                fleet_size=200,
                capture_heads=3,
                ballast_rate_g_s=0.5,
                trim_authority_g=100.0,
            ),
            service(),
            seed=1,
        )
        self.assertGreater(result.peak_trim_error_g, 100.0)
        self.assertGreater(result.trim_exceedance_fraction, 0.0)
        self.assertIn("buoyant trim", result.binding_constraint)

    def test_a_drifting_carrier_does_not_count_as_serving_its_fleet(self):
        # The point of folding trim into serves_fleet: without it, this
        # configuration recovers every single aircraft and reports itself
        # healthy while spending half its time outside trim authority.
        result = simulate_fleet(
            FleetParams(
                fleet_size=200,
                capture_heads=3,
                ballast_rate_g_s=0.5,
                trim_authority_g=100.0,
            ),
            service(),
            seed=1,
        )
        self.assertEqual(result.loss_pct, 0.0)
        self.assertFalse(result.serves_fleet)

    def test_faster_ballast_monotonically_reduces_peak_trim_error(self):
        peaks = [
            simulate_fleet(
                FleetParams(fleet_size=200, capture_heads=3, ballast_rate_g_s=rate),
                service(),
                seed=1,
            ).peak_trim_error_g
            for rate in (0.5, 1.0, 2.0, 5.0, 20.0)
        ]
        self.assertEqual(peaks, sorted(peaks, reverse=True))

    def test_trim_error_floors_at_the_discreteness_of_one_aircraft(self):
        # Even with effectively unlimited ballast rate the error cannot go
        # to zero: each release is a step of one aircraft's mass, so the
        # floor is set by aircraft mass and launch spacing, not by the
        # ballast system.  Sizing ballast past that point buys nothing.
        result = simulate_fleet(
            FleetParams(fleet_size=200, capture_heads=3, ballast_rate_g_s=1e6),
            service(),
            seed=1,
        )
        self.assertGreaterEqual(result.peak_trim_error_g, 37.0)
        self.assertEqual(result.trim_exceedance_fraction, 0.0)

    def test_ballast_capacity_binds_independently_of_rate(self):
        # Unlimited rate, far too small a tank: the carrier simply cannot
        # hold enough ballast to offset the fleet it puts in the air.
        result = simulate_fleet(
            FleetParams(
                fleet_size=200,
                capture_heads=3,
                ballast_rate_g_s=1e6,
                ballast_capacity_g=200.0,
                trim_authority_g=100.0,
            ),
            service(),
            seed=1,
        )
        self.assertGreater(result.trim_exceedance_fraction, 0.0)
        self.assertIn("buoyant trim", result.binding_constraint)

    def test_capacity_defaults_to_the_whole_fleet(self):
        self.assertAlmostEqual(
            FleetParams(fleet_size=200, aircraft_mass_g=37.0).ballast_capacity,
            7400.0,
        )

    def test_a_small_fleet_needs_no_mass_exchange_system(self):
        # P0 scale: two aircraft is 74 g, inside any plausible trim
        # authority, which is why the problem has not shown up yet and why
        # it will not be discovered on the P0 article.
        result = simulate_fleet(
            FleetParams(fleet_size=2, capture_heads=1, ballast_rate_g_s=0.0),
            service(),
            seed=1,
        )
        self.assertLessEqual(result.peak_trim_error_g, 74.0)
        self.assertEqual(result.trim_exceedance_fraction, 0.0)


class BatterySwap(unittest.TestCase):
    """Hot-swap replaces slot-hours of charging with a mechanical exchange.

    The point the model must make honestly: swap does not create energy. The
    fleet still consumes packs at its flight rate, so the pool has to supply
    them at that rate. The bottleneck moves from idle airframes to packs and
    chargers — a good trade only because airframes are the expensive, few,
    FMECA'd resource and packs are cheap. If the tests only showed the
    airborne-count win without the pool cost, the model would be lying.
    """

    def test_validate_rejects_bad_energy_mode(self):
        with self.assertRaises(ValueError):
            simulate_fleet(FleetParams(energy_mode="teleport"), service())

    def test_swap_needs_a_charger(self):
        with self.assertRaises(ValueError):
            simulate_fleet(
                FleetParams(energy_mode="swap", charger_channels=0), service()
            )

    def test_a_generous_pool_beats_charge_in_place_on_airborne_count(self):
        base = dict(fleet_size=200, capture_heads=3)
        cip = simulate_fleet(FleetParams(**base), service(), seed=1)
        swap = simulate_fleet(
            FleetParams(
                **base,
                energy_mode="swap",
                swap_s=12.0,
                spare_packs=1000,
                charger_channels=1000,
                pack_charge_s=3600.0,
            ),
            service(),
            seed=1,
        )
        self.assertGreater(swap.mean_airborne, 2.0 * cip.mean_airborne)

    def test_the_win_is_paid_for_in_packs_a_stingy_pool_starves(self):
        # Same swap mechanism, no spare packs, one charger: the pool cannot
        # supply packs at the flight rate, so recovered aircraft wait and
        # the airborne count is no better than charge-in-place. This is the
        # honest counterweight to the previous test.
        result = simulate_fleet(
            FleetParams(
                fleet_size=200,
                capture_heads=3,
                energy_mode="swap",
                spare_packs=0,
                charger_channels=1,
                pack_charge_s=3600.0,
            ),
            service(),
            seed=1,
        )
        self.assertTrue(result.pack_starved)
        self.assertIn("battery pool", result.binding_constraint)

    def test_pack_starvation_is_diagnosed_even_with_an_empty_recovery_queue(self):
        # Pool starvation holds aircraft in slots, not in the recovery
        # queue, so losses are zero and the queue is empty. Without the
        # dedicated check this reads as "none — serves the fleet".
        result = simulate_fleet(
            FleetParams(
                fleet_size=200,
                capture_heads=8,
                energy_mode="swap",
                spare_packs=0,
                charger_channels=1,
                pack_charge_s=3600.0,
            ),
            service(),
            seed=1,
        )
        self.assertEqual(result.loss_pct, 0.0)
        self.assertNotIn("none", result.binding_constraint)
        self.assertIn("battery pool", result.binding_constraint)

    def test_more_spare_packs_never_reduce_airborne_count(self):
        airborne = [
            simulate_fleet(
                FleetParams(
                    fleet_size=200,
                    capture_heads=4,
                    energy_mode="swap",
                    spare_packs=n,
                    charger_channels=n if n else 1,
                    pack_charge_s=3600.0,
                ),
                service(),
                seed=1,
            ).mean_airborne
            for n in (0, 200, 600, 1200)
        ]
        self.assertEqual(airborne, sorted(airborne))

    def test_keeper_cycles_count_every_recovery_including_warmup(self):
        # The keeper servo is the dock's one unavoidable moving mechanism,
        # and it actuates once per recovery over the WHOLE run — warm-up
        # included — because a mechanism life test does not get to ignore
        # the cycles that happened before the measurement window opened.
        for mode, extra in (
            ("charge_in_place", {}),
            ("swap", dict(spare_packs=1000, charger_channels=1000)),
        ):
            result = simulate_fleet(
                FleetParams(fleet_size=100, capture_heads=3, energy_mode=mode, **extra),
                service(),
                seed=1,
            )
            self.assertGreater(result.keeper_cycles, result.recoveries)
            self.assertGreater(result.recoveries, 0)

    def test_swap_cycles_are_zero_without_swap_and_positive_with_it(self):
        cip = simulate_fleet(FleetParams(fleet_size=100, capture_heads=2), service(), seed=1)
        self.assertEqual(cip.swap_cycles, 0)
        swap = simulate_fleet(
            FleetParams(
                fleet_size=100,
                capture_heads=2,
                energy_mode="swap",
                spare_packs=500,
                charger_channels=500,
            ),
            service(),
            seed=1,
        )
        self.assertGreater(swap.swap_cycles, 0)

    def test_swap_is_deterministic(self):
        params = FleetParams(
            fleet_size=200,
            capture_heads=3,
            energy_mode="swap",
            spare_packs=400,
            charger_channels=400,
        )
        a = simulate_fleet(params, service(0.9), seed=7)
        b = simulate_fleet(params, service(0.9), seed=7)
        self.assertEqual(a, b)


class QueueBehaviour(unittest.TestCase):
    def test_adding_heads_never_increases_losses(self):
        base = FleetParams(fleet_size=200, capture_heads=1, recharge_s=900.0)
        svc = service(occupancy=40.0)
        losses = [
            simulate_fleet(
                FleetParams(**{**base.__dict__, "capture_heads": h}), svc, seed=1
            ).loss_pct
            for h in (1, 2, 3, 4, 6)
        ]
        self.assertEqual(losses, sorted(losses, reverse=True))

    def test_energy_priority_beats_arrival_order_when_the_mechanism_misses(self):
        # The whole reason the policy is a parameter: serving the aircraft
        # with the least reserve first should save aircraft that first-come
        # first-served drops.  It can only do so once the queue holds
        # aircraft with *different* reserves, which is what go-arounds
        # create — so the comparison is run against a mechanism that misses.
        common = dict(fleet_size=200, capture_heads=1, recharge_s=900.0)
        svc = service(p_capture=0.85, occupancy=25.0)
        for seed in (1, 2, 3, 4, 5):
            energy = simulate_fleet(
                FleetParams(**common, queue_policy="energy"), svc, seed=seed
            )
            fcfs = simulate_fleet(
                FleetParams(**common, queue_policy="fcfs"), svc, seed=seed
            )
            self.assertLess(energy.loss_pct, fcfs.loss_pct, f"seed {seed}")

    def test_the_two_policies_coincide_for_a_homogeneous_queue(self):
        # A property worth pinning rather than a curiosity: when every
        # aircraft arrives with the same reserve, ranking by remaining
        # reserve *is* ranking by arrival time, so the policies must agree
        # exactly.  If they diverge here, the energy key is reading
        # something other than remaining reserve — which is precisely the
        # bug that made this policy order by aircraft index.
        common = dict(fleet_size=200, capture_heads=1, recharge_s=900.0)
        svc = service(p_capture=1.0, occupancy=30.0)
        energy = simulate_fleet(
            FleetParams(**common, queue_policy="energy"), svc, seed=1
        )
        fcfs = simulate_fleet(FleetParams(**common, queue_policy="fcfs"), svc, seed=1)
        self.assertEqual(energy.loss_pct, fcfs.loss_pct)
        self.assertEqual(energy.recoveries, fcfs.recoveries)

    def test_throughput_cannot_exceed_demand(self):
        result = simulate_fleet(
            FleetParams(fleet_size=100, capture_heads=8), service(), seed=1
        )
        self.assertLessEqual(result.throughput_per_hour, result.demand_per_hour * 1.05)

    def test_queue_wait_is_zero_when_heads_are_never_contended(self):
        result = simulate_fleet(
            FleetParams(fleet_size=10, capture_heads=10), service(), seed=1
        )
        self.assertEqual(result.mean_queue_wait_s, 0.0)
        self.assertLessEqual(result.max_queue_depth, 1)


class CostTerms(unittest.TestCase):
    def test_dock_mass_separates_heads_from_slots(self):
        # The architectural claim the module exists to test: slots must be
        # cheap enough that fleet size stops driving dock mass.  If both
        # terms scaled together the separation would buy nothing.
        few = simulate_fleet(
            FleetParams(fleet_size=100, capture_heads=2, magazine_slots=100),
            service(),
            seed=1,
        )
        many = simulate_fleet(
            FleetParams(fleet_size=100, capture_heads=20, magazine_slots=100),
            service(),
            seed=1,
        )
        self.assertLess(few.dock_mass_g, many.dock_mass_g)
        self.assertAlmostEqual(
            many.dock_mass_g - few.dock_mass_g, 18 * 180.0, places=1
        )

    def test_payload_margin_goes_negative_when_the_carrier_is_overloaded(self):
        result = simulate_fleet(
            FleetParams(fleet_size=200, capture_heads=4, payload_ceiling_g=1000.0),
            service(),
            seed=1,
        )
        self.assertLess(result.payload_margin_g, 0.0)


class HeadSweep(unittest.TestCase):
    def test_minimum_heads_is_the_first_count_passing_every_seed(self):
        sweep = sweep_heads(
            FleetParams(fleet_size=200, recharge_s=900.0),
            service(occupancy=40.0),
            head_counts=range(1, 13),
            seeds=(1, 2, 3),
        )
        self.assertIsNotNone(sweep.minimum_heads)
        for row in sweep.rows:
            if row["capture_heads"] < sweep.minimum_heads:
                self.assertFalse(row["serves_fleet"])
        passing = next(
            r for r in sweep.rows if r["capture_heads"] == sweep.minimum_heads
        )
        self.assertTrue(passing["serves_fleet"])

    def test_unserviceable_fleet_reports_none_rather_than_a_guess(self):
        sweep = sweep_heads(
            FleetParams(fleet_size=400, recharge_s=300.0),
            service(p_capture=0.3, occupancy=120.0),
            head_counts=(1, 2),
            seeds=(1,),
        )
        self.assertIsNone(sweep.minimum_heads)

    def test_the_reported_minimum_serves_the_fleet_at_every_seed(self):
        # Guards the multi-seed requirement itself.  A head count that
        # serves the fleet at one seed and drops aircraft at another has
        # not been shown to work, and reporting it would put a marginal
        # configuration into a build document as a sized one.
        params = FleetParams(fleet_size=200, recharge_s=900.0)
        svc = service(p_capture=0.9, occupancy=40.0)
        seeds = (1, 2, 3, 4, 5)
        sweep = sweep_heads(params, svc, head_counts=range(1, 13), seeds=seeds)
        self.assertIsNotNone(sweep.minimum_heads)
        for seed in seeds:
            run = simulate_fleet(
                FleetParams(**{**params.__dict__, "capture_heads": sweep.minimum_heads}),
                svc,
                seed=seed,
            )
            self.assertTrue(
                run.serves_fleet,
                f"reported minimum {sweep.minimum_heads} fails at seed {seed}",
            )
        self.assertGreater(
            sum(1 for row in sweep.rows if not row["serves_fleet"]),
            0,
            "sweep never rejected a head count; the pass rule is untested",
        )


class Calibration(unittest.TestCase):
    def test_refuses_to_invent_a_service_time(self):
        from aiur.sim.engine import EpisodeConfig

        def never_captures(seed: int) -> EpisodeConfig:
            raise AssertionError("should not be reached")

        with self.assertRaises(ValueError):
            calibrate_service(episodes=0, scenario=never_captures)

    def test_calibrates_from_the_real_twin(self):
        model = calibrate_service(episodes=4)
        self.assertGreater(len(model.occupancy_samples_s), 0)
        self.assertTrue(0.0 <= model.p_capture <= 1.0)
        self.assertIn("sil_p0b", model.source)
        self.assertGreater(model.mean_occupancy_s, 0.0)


class Report(unittest.TestCase):
    def test_report_carries_the_fields_a_decision_reads(self):
        report = run_study(
            fleet_sizes=(20,),
            base=FleetParams(recharge_s=900.0),
            service=service(occupancy=30.0),
            head_counts=(1, 2),
            seeds=(1,),
        )
        self.assertEqual(len(report["sweeps"]), 1)
        row = report["sweeps"][0]["rows"][0]
        for key in (
            "capture_heads",
            "serves_fleet",
            "worst_loss_pct",
            "throughput_per_hour",
            "demand_per_hour",
            "head_utilisation",
            "binding_constraint",
            "dock_mass_g",
        ):
            self.assertIn(key, row)
        self.assertTrue(report["caveats"])

    def test_renderer_states_the_head_count_and_keeps_the_caveats(self):
        report = run_study(
            fleet_sizes=(20,),
            base=FleetParams(recharge_s=900.0),
            service=service(occupancy=30.0),
            head_counts=(1, 2),
            seeds=(1,),
        )
        text = render(report)
        self.assertIn("MINIMUM CAPTURE HEADS", text)
        self.assertIn("20 aircraft ->", text)
        # The lower-bound caveat is the one a reader most needs and the one
        # most easily lost in a reformat.
        self.assertIn("LOWER bound", text)


if __name__ == "__main__":
    unittest.main()
