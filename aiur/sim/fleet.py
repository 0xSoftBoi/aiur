"""Fleet-throughput model: what a carrier costs to run N aircraft.

Everything in ``aiur.sim`` so far asks a question about *one* recovery: does
this aircraft, arriving at this dock under this noise, get captured safely.
That is the right first question and it is the one P0 gates on.  It is also
silent on the question that decides whether the architecture scales past a
laboratory: **one dock recovering one aircraft says nothing about a carrier
recovering a hundred.**

The scaling argument that motivates this module is short enough to state.
Payload mass is not the wall: a guarded Crazyflie Brushless is 37 g, so two
hundred of them is 7.4 kg of airframe.

Do not reach that conclusion by scaling envelope skin off a 4.5 m indoor
blimp, which flatters the answer badly.  The honest anchor is a real
vehicle: Flying Whales' LCA60T is 200 m long, ~200,000 m³ of helium in 14
cells, ~210 t of gross lift, 100 t of structure and 60 t of payload — a
payload fraction near 28%, not the ~90% a skin-mass extrapolation suggests,
because a real airship also carries a rigid frame, gas cells, 32 electric
motors and turbogenerators.  Applied downward (and small vehicles do
*worse* on structure fraction, not better), a 40 m vehicle is in the
few-hundred-kilogram payload class.  The fleet still fits, with room; the
margin is just far smaller than the naive number implies.

Flying Whales has not flown — first flight is expected 2027, service 2029,
against an original plan of 2024 and 2026 — so it is a design under
certification, not a proven capability.  It is cited here for its mass
fractions and its loading architecture, both of which are engineering
inputs regardless of whether the vehicle flies on schedule.

The walls are elsewhere:

  * **dock mass is linear in fleet size.**  One 180 g actuated dock per
    aircraft is 36 kg and 200 sensed, actuated, FMECA'd channels at N=200.
  * **recovery throughput is a queue.**  A fleet with 10 min of endurance
    and an hour of recharge presents an arrival every few tens of seconds,
    forever.  A dock that turns one aircraft a minute does not serve it,
    and the aircraft that cannot be served is not delayed — it is on
    reserve fuel, and then it is on the floor.
  * **launch capacity is its own ceiling.**  One release lane at 5 s
    spacing caps a vehicle at 720 sorties/hour however many capture heads
    it carries, and it does so with an empty recovery queue.
  * **the fleet is a disturbance to the carrier that carries it.**  A
    buoyant vehicle that releases mass without landing gains lift.  The
    LCA60T answers this with a mass-exchange system that swaps payload for
    ~60 t of water ballast, and with a load-exchange officer as one of only
    two crew.  A drone carrier has the same problem in a harder form:
    cargo goes down and stays down, but aircraft come back, one at a time,
    at whatever rate the queue delivers.  The load-exchange problem never
    closes.

So the design move this module exists to size is the separation of
**capture** from **storage**: a small number of expensive, sensed, actuated
capture *heads* where aircraft arrive, indexing each captured aircraft off
the head into a large number of cheap passive *slots* where it waits and
charges.  Head count is then set by arrival rate and slot count by fleet
size, and the two stop multiplying.  How small is "a small number" is
precisely what nobody in this programme knows, and it is a number, so it
can be simulated.

What is modelled
----------------

A discrete-event model of the aircraft cycle:

    ready -> launch -> sortie -> recovery queue -> capture attempt
          -> stow (indexed off the head into a slot) -> charge -> ready

against finite capture heads, magazine slots, launch lanes, and a
rate- and capacity-limited ballast system chasing the mass currently off
the vehicle,

with capture attempts drawn from the **real twin**.  ``calibrate_service``
runs seeded ``run_episode`` calls and reduces them to a per-attempt capture
probability and an empirical distribution of head-occupancy times; the
fleet model then samples that distribution.  The queue is therefore fed by
measured twin behaviour rather than by an assumed service time, and when
the twin's physics changes this model changes with it.

What is deliberately *not* modelled, because assuming it away is the way
this kind of model lies
-----------------------------------------------------------------------

  * **Terminal traffic interaction — modelled, but as an overlay and off by
    default.**  The twin episode flies one aircraft at one dock, so it
    cannot produce this effect; the fleet model adds it on top
    (``approach_corridors``, ``traffic_holds_s``, ``traffic_miss_penalty``)
    rather than pretending the twin measured it.  The defaults reproduce the
    independent-corridor case exactly, so **a head count from a default run
    is still a lower bound** — it becomes a real bound only once the traffic
    parameters are set, and those parameters are estimates calibrated to a
    belly layout this scalar model cannot itself represent.
  * **Carrier flight mechanics beyond static trim.**  Net buoyant trim and
    the ballast chase *are* modelled.  What is not: where in the magazine
    an aircraft is stowed, and therefore pitch and roll moments — a
    magazine that fills from one end trims the vehicle nose-down long
    before the total mass becomes a problem.  Only the scalar is here.
  * **Radio.**  Crazyradio addresses dozens, not hundreds.  Comms capacity
    is a real ceiling and it is not in here.
  * **Energy in anything but seconds.**  Endurance and recharge are times,
    not a battery model; the battery SOP is a separate document with real
    chemistry in it.

Entry point: ``python -m aiur.sim.fleet --help``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import heapq
import json
import random
from typing import Callable, Iterable, Sequence

from .campaign import run_episode
from .credibility import wilson_interval
from .engine import EpisodeConfig, EpisodeOutcome
from .scenarios import degraded_sensor_case, sil_p0b

#: Head occupancy that the twin does not simulate: releasing the keeper,
#: indexing the captured aircraft off the head into a free slot, and
#: returning the head to its accept state.  An engineering estimate for a
#: mechanism that does not exist yet, not a measurement — it is a parameter
#: precisely so the sweep can show how much the answer depends on it.
DEFAULT_STOW_S = 8.0

#: Go-around cost after a failed attempt: fly clear, re-enter the corridor,
#: re-acquire.  Estimate.
DEFAULT_GO_AROUND_S = 25.0

#: Time to mechanically exchange a depleted battery pack for a charged one.
#: Estimate for a mechanism that does not exist; it is a parameter so the
#: sweep can show how much the answer depends on it.
DEFAULT_SWAP_S = 12.0

#: Loss rate above which a configuration is judged not to serve its fleet.
#: A "loss" is an aircraft that ran its reserve out in the queue or
#: exhausted its retries — on hardware that is a crash, so the threshold is
#: set at a level that is already unacceptable rather than at one that
#: looks tolerable.
LOSS_THRESHOLD_PCT = 1.0

#: Fraction of time a carrier may spend outside its trim authority before
#: the configuration is judged not to hold station.  Set low deliberately:
#: the exceedance windows coincide with launch and recovery waves, which is
#: exactly when aircraft are near the dock.
TRIM_EXCEEDANCE_THRESHOLD = 0.02


# --------------------------------------------------------------------------
# Service model: the twin's answer to "what does one recovery cost a head"
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceModel:
    """Per-attempt capture behaviour, reduced from real twin episodes."""

    p_capture: float
    ci_low: float
    ci_high: float
    #: Empirical head-occupancy samples, seconds, one per twin episode.
    #: Sampled with replacement rather than fitted to a distribution: the
    #: twin's durations are bimodal (a capture on the first pass costs
    #: about half what one after a re-alignment does) and a mean would
    #: erase exactly the tail the queue is sensitive to.
    occupancy_samples_s: tuple[float, ...]
    episodes: int
    source: str

    @property
    def mean_occupancy_s(self) -> float:
        return sum(self.occupancy_samples_s) / len(self.occupancy_samples_s)

    def sample_occupancy_s(self, rng: random.Random) -> float:
        return rng.choice(self.occupancy_samples_s)


def noise_scenario(noise_scale: float) -> Callable[[int], EpisodeConfig]:
    """A calibration scenario at ``noise_scale`` times Lighthouse noise.

    Worth using deliberately.  At nominal laboratory noise the twin
    captures on essentially every episode, so ``p_capture`` is 1.0 and the
    fleet model's go-around and divert paths never execute — the queue is
    then being sized against a mechanism that never misses, which is not
    the mechanism any fleet outside a motion-capture volume will have.
    """

    def scenario(seed: int) -> EpisodeConfig:
        return degraded_sensor_case(seed, noise_scale)

    scenario.__name__ = f"degraded_sensor_case(noise={noise_scale:g})"
    return scenario


def calibrate_service(
    *,
    episodes: int = 40,
    seed: int = 1,
    scenario: Callable[[int], EpisodeConfig] = sil_p0b,
) -> ServiceModel:
    """Run the twin and reduce it to a service model for the queue.

    Only successful episodes contribute occupancy samples.  A failed
    approach occupies the head too, but for a different and shorter time
    (the abort path), and folding the two together would understate the
    cost of the case the queue actually waits on.  Failures are carried
    separately, as ``p_capture``.
    """

    captures = 0
    durations: list[float] = []
    for offset in range(episodes):
        episode_seed = seed + offset
        result = run_episode(scenario(episode_seed), episode_seed)
        if result.outcome is EpisodeOutcome.SUCCESS:
            captures += 1
            durations.append(result.duration_s)
    if not durations:
        raise ValueError(
            "calibration produced no successful episodes; the fleet model "
            "has no service time to sample and must not guess one"
        )
    low, high = wilson_interval(captures, episodes)
    return ServiceModel(
        p_capture=captures / episodes,
        ci_low=low,
        ci_high=high,
        occupancy_samples_s=tuple(round(d, 3) for d in durations),
        episodes=episodes,
        source=f"{scenario.__name__} seeds {seed}..{seed + episodes - 1}",
    )


# --------------------------------------------------------------------------
# Fleet configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetParams:
    """One carrier configuration and the fleet it is asked to serve."""

    fleet_size: int = 100
    #: Sensed, actuated capture interfaces.  The expensive thing.
    capture_heads: int = 1
    #: Passive magazine positions.  A stowed aircraft holds one while it
    #: charges.  ``None`` means "one per aircraft", i.e. never binding.
    magazine_slots: int | None = None

    #: Airborne energy, expressed as time.
    endurance_s: float = 600.0
    #: Useful mission time before the aircraft turns for the carrier.  The
    #: remainder of ``endurance_s`` is the reserve it holds in the queue.
    sortie_s: float = 420.0
    recharge_s: float = 3600.0

    # ---- energy replenishment ---------------------------------------------
    #
    # "charge_in_place": the recovered aircraft holds its slot for the full
    # recharge — the P0-style assumption, and the reason every large fleet
    # in this model is charge-bound.
    #
    # "swap": the aircraft exchanges its depleted pack for a charged one in
    # swap_s and relaunches; the depleted pack then recharges in a shared
    # pool of charger channels while spare packs keep aircraft flying.
    #
    # Swap does not create energy.  The fleet still consumes packs at its
    # flight rate, so the pool must supply them at that rate: the bottleneck
    # moves from *idle airframes* to *packs and chargers*.  That is the whole
    # point — airframes are the expensive, few, FMECA'd resource, and packs
    # are cheap.  Swap buys airborne count per airframe, paid for in spare
    # packs, charger channels, and an actuated mechanism that cycles hundreds
    # of times per deployment (reported as lifetime actuations, never folded
    # into a score; cf. NASA-STD-5017 mechanism life-with-margin practice).
    energy_mode: str = "charge_in_place"
    swap_s: float = DEFAULT_SWAP_S
    #: Packs in circulation beyond one per airframe.  Zero spares means an
    #: aircraft can only relaunch once its own pack is charged, which is
    #: charge-in-place with extra steps.
    spare_packs: int = 0
    #: Packs that can charge simultaneously in the pool.  ``None`` means one
    #: per airframe, i.e. charger capacity never binds and only pack count
    #: and swap rate do.
    charger_channels: int | None = None
    #: Time for one pooled pack to recharge.  ``None`` inherits recharge_s.
    pack_charge_s: float | None = None

    stow_s: float = DEFAULT_STOW_S
    go_around_s: float = DEFAULT_GO_AROUND_S
    #: Attempts before the aircraft is diverted rather than re-queued.
    retry_limit: int = 3
    #: Minimum spacing between releases from one launch lane.
    launch_interval_s: float = 5.0
    launch_lanes: int = 1

    #: ``energy`` serves the aircraft with the least reserve remaining
    #: first; ``fcfs`` serves in arrival order.
    queue_policy: str = "energy"

    horizon_s: float = 4 * 3600.0
    #: Metrics ignore this leading transient, during which the fleet is
    #: still spreading out from an all-charged start.
    warmup_s: float | None = None

    # Cost terms the queue cannot compute, reported beside the result.
    head_mass_g: float = 180.0
    slot_mass_g: float = 12.0
    payload_ceiling_g: float = 1000.0
    aircraft_mass_g: float = 37.0

    # ---- buoyant trim -----------------------------------------------------
    #
    # A buoyant carrier that releases mass without landing gains lift
    # immediately.  Flying Whales' LCA60T — 60 t payload, hover load and
    # unload by winch — carries a dedicated mass-exchange system that swaps
    # payload for about 60 t of water ballast, and staffs a load-exchange
    # officer as one of only two crew.  That is a well-funded programme
    # saying the problem is first-order.
    #
    # A drone carrier has the same problem in a harder form.  Cargo goes
    # down and stays down; aircraft come back, one at a time, at whatever
    # rate the recovery queue happens to deliver.  So fleet throughput is
    # not merely constrained by the carrier — it is a *disturbance input*
    # to the carrier's trim, and the two have to be sized together.

    #: Rate at which the mass-exchange system can take on or shed ballast.
    #: The number that matters: releasing 200 aircraft over 1000 s sheds
    #: 7.4 kg, and ballast that cannot follow that leaves the carrier light.
    ballast_rate_g_s: float = 5.0
    #: Ballast the carrier can hold.  ``None`` means "enough for the whole
    #: fleet", i.e. capacity never binds and only rate does.
    ballast_capacity_g: float | None = None
    #: Static heaviness/lightness the carrier can hold on propulsion alone
    #: without drifting off station.  Trim error beyond this is not a
    #: comfort problem — the dock is moving vertically while aircraft are
    #: trying to land on it.
    trim_authority_g: float = 100.0

    # ---- terminal-traffic interaction -------------------------------------
    #
    # The twin flies one aircraft at one dock, so nothing above sees
    # converging traffic: every head count elsewhere in this model is a lower
    # bound for exactly this reason.  These parameters overlay the missing
    # effect, and all default to the no-interaction case, so a default run
    # reproduces the independent-corridor numbers byte for byte.
    #
    # Two distinct real effects, kept as separate parameters:
    #
    #   approach_corridors caps how many aircraft may be on final at once,
    #   independent of head count.  A belly that cannot spatially separate
    #   its heads has fewer corridors than heads, and the surplus heads then
    #   idle behind the airspace rather than behind their own throughput.
    #
    #   traffic_holds_s and traffic_miss_penalty are the interaction *cost* an
    #   aircraft pays per other aircraft simultaneously on final: added
    #   deconfliction hold time, and capture probability lost to wake and
    #   avoidance manoeuvres.  These are estimates for an effect the twin does
    #   not contain.  All concurrent finals are treated as mutually
    #   interfering, which is conservative for heads spread well apart around
    #   a large belly — a spacing this scalar model cannot represent, so the
    #   parameters must be calibrated to a specific layout before they are
    #   believed.
    #: Max aircraft on final approach at once. ``None`` = one corridor per
    #: head, i.e. the independent-corridor assumption (no extra airspace
    #: limit), which is today's behaviour.
    approach_corridors: int | None = None
    #: Deconfliction hold added to an attempt per other aircraft on final.
    traffic_holds_s: float = 0.0
    #: Capture probability lost per other aircraft on final.
    traffic_miss_penalty: float = 0.0

    @property
    def approach_corridors_effective(self) -> int:
        return (
            self.capture_heads
            if self.approach_corridors is None
            else self.approach_corridors
        )

    @property
    def traffic_enabled(self) -> bool:
        return (
            self.approach_corridors is not None
            or self.traffic_holds_s > 0.0
            or self.traffic_miss_penalty > 0.0
        )

    @property
    def ballast_capacity(self) -> float:
        if self.ballast_capacity_g is not None:
            return self.ballast_capacity_g
        return self.fleet_size * self.aircraft_mass_g

    @property
    def reserve_s(self) -> float:
        return self.endurance_s - self.sortie_s

    @property
    def slots(self) -> int:
        return self.fleet_size if self.magazine_slots is None else self.magazine_slots

    @property
    def pack_charge_effective_s(self) -> float:
        return self.recharge_s if self.pack_charge_s is None else self.pack_charge_s

    @property
    def charger_channels_effective(self) -> int:
        return (
            self.fleet_size
            if self.charger_channels is None
            else self.charger_channels
        )

    @property
    def turnaround_s(self) -> float:
        """Airframe-side time from recovery to relaunch-ready.

        In swap mode this is the mechanical exchange, not the recharge —
        that is the entire benefit, and it is what the demand and warm-up
        estimates must use so the pool constraint shows up as unmet demand
        rather than being baked into the demand figure itself.
        """

        return self.recharge_s if self.energy_mode == "charge_in_place" else self.swap_s

    @property
    def effective_warmup_s(self) -> float:
        if self.warmup_s is not None:
            return self.warmup_s
        slow_s = (
            self.recharge_s
            if self.energy_mode == "charge_in_place"
            else self.pack_charge_effective_s
        )
        return min(slow_s + self.endurance_s, 0.5 * self.horizon_s)

    def validate(self) -> None:
        if self.fleet_size < 1:
            raise ValueError("fleet_size must be >= 1")
        if self.capture_heads < 1:
            raise ValueError("capture_heads must be >= 1")
        if self.slots < 1:
            raise ValueError("magazine_slots must be >= 1")
        if self.sortie_s >= self.endurance_s:
            raise ValueError(
                "sortie_s must leave a reserve: an aircraft that turns for "
                "the carrier with no energy left cannot queue at all"
            )
        if self.queue_policy not in ("energy", "fcfs"):
            raise ValueError(f"unknown queue_policy {self.queue_policy!r}")
        if self.energy_mode not in ("charge_in_place", "swap"):
            raise ValueError(f"unknown energy_mode {self.energy_mode!r}")
        if self.energy_mode == "swap":
            if self.spare_packs < 0:
                raise ValueError("spare_packs must be >= 0")
            if self.charger_channels_effective < 1:
                raise ValueError("swap mode needs at least one charger channel")
        if self.approach_corridors is not None and self.approach_corridors < 1:
            raise ValueError("approach_corridors must be >= 1")
        if self.traffic_holds_s < 0.0:
            raise ValueError("traffic_holds_s must be >= 0")
        if self.traffic_miss_penalty < 0.0:
            raise ValueError("traffic_miss_penalty must be >= 0")


@dataclass(frozen=True)
class FleetResult:
    params: dict[str, object]
    #: Recoveries per hour, measured after warm-up.
    throughput_per_hour: float
    #: The rate the fleet *demands*, from its own cycle time.  Throughput
    #: below demand means the queue is growing and aircraft are falling out
    #: of the bottom of it.
    demand_per_hour: float
    recoveries: int
    losses_reserve_exhausted: int
    losses_retries_exhausted: int
    loss_pct: float
    mean_queue_wait_s: float
    p95_queue_wait_s: float
    max_queue_depth: int
    #: Aircraft still flyable at the horizon.  Below ``fleet_size`` means
    #: the configuration ate its own fleet.
    fleet_remaining: int
    head_utilisation: float
    #: Release rate as a fraction of what the launch lanes can pass.  A
    #: carrier can be recovery-rich and launch-poor: one lane at 5 s
    #: spacing caps the whole vehicle at 720 sorties/hour no matter how
    #: many capture heads it carries.
    launch_utilisation: float
    #: Fraction of head-busy time spent blocked waiting for a free slot.
    head_blocked_fraction: float
    peak_slots_used: int
    mean_airborne: float
    sorties: int
    binding_constraint: str
    dock_mass_g: float
    payload_margin_g: float
    #: Keeper servo actuations over the run — one per recovery. The dock's
    #: single unavoidable moving mechanism; its cycle count is what a
    #: mechanism life test must cover with margin (NASA-STD-5017: qualify to
    #: at least 2x expected life, more for life-limited mechanisms).
    keeper_cycles: int
    #: Battery-swap actuations over the run, zero in charge-in-place mode.
    #: A second life-limited mechanism the swap architecture adds, and the
    #: reliability price of trading a passive charge contact for an active
    #: exchange.
    swap_cycles: int
    #: Swap mode only: recovered aircraft had to wait for a charged pack.
    #: The pool, not the dock, is then the limit.
    pack_starved: bool
    #: Mean and peak number of aircraft simultaneously on final approach.
    #: The measure of terminal-traffic density; zero interaction cost only
    #: when this stays at or below one.
    mean_on_final: float
    peak_on_final: int
    #: Largest buoyant trim error the mass-exchange system failed to
    #: cancel, in grams of static lightness or heaviness.
    peak_trim_error_g: float
    #: Fraction of measured time spent beyond ``trim_authority_g`` — time
    #: during which the carrier is drifting vertically while aircraft are
    #: trying to land on a dock attached to it.
    trim_exceedance_fraction: float

    @property
    def serves_fleet(self) -> bool:
        """Serving the fleet means recovering it *and* holding station.

        Trim is not a secondary comfort metric here.  A carrier outside its
        trim authority is moving the dock vertically under aircraft on
        terminal approach, which is the one thing the whole capture
        architecture is built to avoid — so a configuration that recovers
        every aircraft while drifting has not served the fleet, it has
        moved the failure somewhere the loss counter cannot see it.
        """

        return (
            self.loss_pct <= LOSS_THRESHOLD_PCT
            and self.trim_exceedance_fraction <= TRIM_EXCEEDANCE_THRESHOLD
        )


# --------------------------------------------------------------------------
# Discrete-event simulation
# --------------------------------------------------------------------------

_READY, _LAUNCHING, _SORTIE, _QUEUED, _ON_HEAD, _CHARGING, _GONE = range(7)


@dataclass
class _Aircraft:
    index: int
    state: int = _READY
    #: Airborne seconds remaining before the aircraft is out of energy.
    energy_s: float = 0.0
    attempts: int = 0
    queued_at: float = 0.0
    holds_slot: bool = True


def simulate_fleet(
    params: FleetParams,
    service: ServiceModel,
    *,
    seed: int = 1,
) -> FleetResult:
    """Run one fleet configuration to the horizon.

    The event queue holds ``(time, sequence, callback)``; ``sequence`` is a
    monotonic counter so that simultaneous events resolve in insertion
    order and the run is fully deterministic under ``seed``.
    """

    params.validate()
    rng = random.Random(seed)
    warmup = params.effective_warmup_s

    events: list[tuple[float, int, Callable[[float], None]]] = []
    counter = 0

    def schedule(at: float, callback: Callable[[float], None]) -> None:
        nonlocal counter
        heapq.heappush(events, (at, counter, callback))
        counter += 1

    fleet = [_Aircraft(index=i, state=_CHARGING) for i in range(params.fleet_size)]
    queue: list[_Aircraft] = []
    free_heads = params.capture_heads
    used_slots = params.fleet_size  # every aircraft starts stowed
    lane_free_at = [0.0] * params.launch_lanes

    recoveries = 0
    #: Every recovery, warm-up included, so the loss rate below has a
    #: denominator drawn from the same span as its numerator.
    recoveries_total = 0
    sorties = 0

    # Battery-swap pool. Packs are fungible tokens: charged ones sit ready,
    # depleted ones charge in a finite set of channels, and an aircraft that
    # lands with no charged pack available waits (holding its slot) until one
    # is. Spares start charged and ready.
    charged_packs = params.spare_packs
    charging_count = 0
    depleted_queue = 0
    waiting_for_pack: list[_Aircraft] = []
    swaps_total = 0
    pack_wait_events = 0
    lost_reserve = 0
    lost_retries = 0
    waits: list[float] = []
    max_depth = 0
    # Measured after warm-up only: every aircraft starts stowed, so the
    # initial occupancy is an artefact of the initial condition and would
    # otherwise pin the peak at the fleet size in every run.
    peak_slots = 0
    head_busy_s = 0.0
    head_blocked_s = 0.0
    # Airborne count integrated over time, for a time-weighted mean.
    airborne = 0
    airborne_integral = 0.0
    last_t = 0.0
    measured_from = warmup
    #: When the "a head is free, the queue is not empty, and storage is
    #: full" condition became true, or ``None``.  Instrumented rather than
    #: derived from idle time, because head idleness has two causes and
    #: only one of them is a reason to build more magazine.
    blocked_since: float | None = None

    #: Ballast currently held, in grams.  The carrier is trimmed neutral
    #: with the whole fleet stowed, so the ballast the mass-exchange system
    #: must be holding at any moment equals the mass of the aircraft that
    #: are not aboard.
    ballast_g = 0.0
    peak_trim_error_g = 0.0
    trim_exceeded_s = 0.0

    # Terminal-traffic state: aircraft currently between the start of an
    # attempt and its resolution, i.e. on final approach and contending for
    # the shared airspace below the carrier.
    on_final = 0
    on_final_integral = 0.0
    peak_on_final = 0

    def advance(t: float) -> None:
        """Integrate time-weighted metrics forward to ``t``.

        The airborne count only changes at events, so between events the
        ballast target is constant and the first-order chase has an exact
        solution — no fixed-step integration and no step-size error.
        """

        nonlocal last_t, airborne_integral, head_blocked_s, on_final_integral
        nonlocal ballast_g, peak_trim_error_g, trim_exceeded_s
        if t <= last_t:
            return
        span_total = t - last_t
        measured = t > measured_from
        span = t - max(last_t, measured_from) if measured else 0.0

        if measured:
            airborne_integral += airborne * span
            on_final_integral += on_final * span
            if blocked_since is not None:
                head_blocked_s += span

        # Ballast chases the mass that is currently off the carrier, rate
        # limited and capped.  Error is worst at the start of the span and
        # decays from there, so the peak is the opening error.
        # Demand is what the carrier needs to stay neutral; the target is
        # what its tank can actually reach.  Trim error is measured against
        # *demand*, not target — capping the target instead would make a
        # carrier with a tank ten times too small report perfect trim, on
        # the grounds that it had filled the tank it has.
        demand = airborne * params.aircraft_mass_g
        target = min(demand, params.ballast_capacity)
        error = target - ballast_g
        magnitude = abs(error)
        shortfall = abs(demand - ballast_g)
        if measured:
            peak_trim_error_g = max(peak_trim_error_g, shortfall)
            if shortfall > params.trim_authority_g:
                # Time to bring the error inside authority, if it can be
                # brought inside at all: a capacity-bound carrier never
                # closes it and is outside for the whole span.
                closable = max(0.0, demand - params.ballast_capacity)
                if closable >= params.trim_authority_g:
                    trim_exceeded_s += span
                else:
                    closing_s = (
                        shortfall - params.trim_authority_g
                    ) / max(1e-9, params.ballast_rate_g_s)
                    trim_exceeded_s += min(span, closing_s)
        travel = min(magnitude, params.ballast_rate_g_s * span_total)
        ballast_g += travel if error > 0 else -travel

        last_t = t

    def update_block(t: float) -> None:
        """Open or close a storage-blocked interval at the current state."""

        nonlocal blocked_since
        blocked = free_heads > 0 and bool(queue) and used_slots >= params.slots
        if blocked and blocked_since is None:
            blocked_since = t
        elif not blocked and blocked_since is not None:
            blocked_since = None

    # ---- state transitions -------------------------------------------------

    def try_launch(t: float) -> None:
        """Release every ready aircraft a free lane can take."""

        for aircraft in fleet:
            if aircraft.state is not _READY:
                continue
            lane = min(range(params.launch_lanes), key=lambda i: lane_free_at[i])
            release = max(t, lane_free_at[lane])
            if release >= params.horizon_s:
                return
            lane_free_at[lane] = release + params.launch_interval_s
            aircraft.state = _LAUNCHING
            schedule(release, lambda now, a=aircraft: launch(now, a))

    def launch(t: float, aircraft: _Aircraft) -> None:
        nonlocal airborne, sorties, used_slots
        advance(t)
        aircraft.state = _SORTIE
        aircraft.energy_s = params.endurance_s
        aircraft.attempts = 0
        if aircraft.holds_slot:
            aircraft.holds_slot = False
            used_slots -= 1
        airborne += 1
        if t >= measured_from:
            sorties += 1
        schedule(t + params.sortie_s, lambda now, a=aircraft: arrive(now, a))

    def arrive(t: float, aircraft: _Aircraft) -> None:
        nonlocal max_depth
        advance(t)
        aircraft.energy_s -= params.sortie_s
        aircraft.state = _QUEUED
        aircraft.queued_at = t
        queue.append(aircraft)
        max_depth = max(max_depth, len(queue))
        pump(t)

    def next_served(t: float) -> _Aircraft | None:
        if not queue:
            return None
        if params.queue_policy == "energy":
            # Remaining reserve *now*, not the reserve the aircraft arrived
            # with.  ``energy_s`` is only debited when the aircraft is
            # served, so ranking on it directly compares stale values that
            # are identical across a homogeneous fleet — which silently
            # degenerates to ordering by aircraft index and makes the
            # policy parameter meaningless.
            chosen = min(
                queue, key=lambda a: (a.energy_s - (t - a.queued_at), a.index)
            )
        else:
            chosen = min(queue, key=lambda a: (a.queued_at, a.index))
        queue.remove(chosen)
        return chosen

    def pump(t: float) -> None:
        """Fill every free head from the queue, if a slot is available."""

        nonlocal free_heads, on_final, peak_on_final
        while free_heads > 0 and queue:
            # A head that cannot unload cannot accept: with no free slot
            # the aircraft it captures has nowhere to go.  The queue backs
            # up behind storage, which is the whole point of separating
            # heads from slots and is invisible if you model heads alone.
            if used_slots >= params.slots:
                break
            # Airspace, not the head, can be the limit: a head is useless if
            # there is no free corridor to fly the approach in. With traffic
            # disabled this never binds before free_heads does, so the
            # default path is unchanged.
            if params.traffic_enabled and on_final >= params.approach_corridors_effective:
                break
            aircraft = next_served(t)
            if aircraft is None:
                break
            free_heads -= 1
            aircraft.state = _ON_HEAD
            # Count the approach the instant the aircraft is committed to a
            # head, not when its attempt event later fires: several are
            # admitted at the same timestamp, and counting only at attempt()
            # would let a whole burst slip past the corridor cap before any
            # of them incremented it.
            on_final += 1
            if t >= measured_from:
                peak_on_final = max(peak_on_final, on_final)
            wait = t - aircraft.queued_at
            # Holding costs energy at the same rate as flying: the aircraft
            # is airborne the whole time it is in the queue.
            aircraft.energy_s -= wait
            if t >= measured_from:
                waits.append(wait)
            schedule(t, lambda now, a=aircraft: attempt(now, a))
        update_block(t)

    def attempt(t: float, aircraft: _Aircraft) -> None:
        advance(t)
        aircraft.attempts += 1
        # This aircraft was counted into on_final at admission, so its
        # neighbours — the other aircraft simultaneously inbound — are
        # on_final minus itself. The two RNG draws below keep their order
        # (occupancy, then capture) so a traffic-disabled run reproduces the
        # exact sequence of the earlier model: the traffic branch draws no
        # randomness of its own.
        neighbours = max(0, on_final - 1)
        occupancy = service.sample_occupancy_s(rng)
        p_capture = service.p_capture
        if params.traffic_enabled and neighbours > 0:
            occupancy += params.traffic_holds_s * neighbours
            p_capture = max(0.0, p_capture - params.traffic_miss_penalty * neighbours)
        captured = rng.random() < p_capture
        schedule(
            t + occupancy,
            lambda now, a=aircraft, ok=captured, cost=occupancy: resolve(
                now, a, ok, cost
            ),
        )

    def resolve(t: float, aircraft: _Aircraft, captured: bool, occupancy: float) -> None:
        nonlocal free_heads, head_busy_s, airborne, recoveries, used_slots
        nonlocal recoveries_total, on_final
        nonlocal lost_reserve, lost_retries, max_depth, peak_slots
        advance(t)
        # The corridor frees the moment the approach resolves, even though a
        # captured aircraft still occupies its head through the stow.
        on_final -= 1
        aircraft.energy_s -= occupancy
        if t >= measured_from:
            head_busy_s += occupancy

        if captured:
            # The head is held through the stow: it cannot accept the next
            # aircraft until this one has been indexed off it.
            aircraft.state = _CHARGING
            aircraft.holds_slot = True
            used_slots += 1
            airborne -= 1
            recoveries_total += 1
            if t >= measured_from:
                recoveries += 1
                peak_slots = max(peak_slots, used_slots)
            schedule(t + params.stow_s, lambda now: release_head(now))
            if params.energy_mode == "swap":
                schedule(t + params.stow_s, lambda now, a=aircraft: begin_swap(now, a))
            else:
                schedule(
                    t + params.stow_s + params.recharge_s,
                    lambda now, a=aircraft: recharged(now, a),
                )
            # A corridor just freed; a queued aircraft may now start its
            # approach on another free head even though this head is still in
            # its stow. Only relevant, and only invoked, when airspace is a
            # modelled constraint, so the default path is untouched.
            if params.traffic_enabled:
                pump(t)
            return

        free_heads += 1
        if aircraft.energy_s <= params.go_around_s:
            # Not enough left to fly the pattern again.
            lose(t, aircraft, reserve=True)
        elif aircraft.attempts >= params.retry_limit:
            lose(t, aircraft, reserve=False)
        else:
            aircraft.state = _QUEUED
            schedule(t + params.go_around_s, lambda now, a=aircraft: requeue(now, a))
        pump(t)

    def requeue(t: float, aircraft: _Aircraft) -> None:
        nonlocal max_depth
        advance(t)
        aircraft.energy_s -= params.go_around_s
        if aircraft.energy_s <= 0.0:
            lose(t, aircraft, reserve=True)
            return
        aircraft.queued_at = t
        queue.append(aircraft)
        max_depth = max(max_depth, len(queue))
        pump(t)

    def release_head(t: float) -> None:
        nonlocal free_heads, head_busy_s
        advance(t)
        free_heads += 1
        if t >= measured_from:
            head_busy_s += params.stow_s
        pump(t)

    def lose(t: float, aircraft: _Aircraft, *, reserve: bool) -> None:
        nonlocal airborne, lost_reserve, lost_retries
        aircraft.state = _GONE
        airborne -= 1
        # Counted over the whole run, not just the measurement window.  A
        # loss is an aircraft on the floor; it permanently shrinks the
        # fleet the rest of the run measures, so hiding warm-up losses
        # would report a rate for a fleet that no longer exists.
        if reserve:
            lost_reserve += 1
        else:
            lost_retries += 1

    def recharged(t: float, aircraft: _Aircraft) -> None:
        advance(t)
        aircraft.state = _READY
        try_launch(t)

    # ---- battery-swap pool -------------------------------------------------

    def deposit_depleted(t: float) -> None:
        """A just-removed depleted pack enters the charger pool."""

        nonlocal charging_count, depleted_queue
        if charging_count < params.charger_channels_effective:
            charging_count += 1
            schedule(t + params.pack_charge_effective_s, pack_ready)
        else:
            depleted_queue += 1

    def acquire_charged(t: float, aircraft: _Aircraft) -> None:
        """Hand the aircraft a charged pack now, or make it wait for one."""

        nonlocal charged_packs, pack_wait_events
        if charged_packs > 0:
            charged_packs -= 1
            schedule(t + params.swap_s, lambda now, a=aircraft: swapped(now, a))
        else:
            if t >= measured_from:
                pack_wait_events += 1
            waiting_for_pack.append(aircraft)

    def pack_ready(t: float) -> None:
        """A pooled pack finished charging."""

        nonlocal charging_count, depleted_queue, charged_packs
        charging_count -= 1
        if waiting_for_pack:
            aircraft = waiting_for_pack.pop(0)
            schedule(t + params.swap_s, lambda now, a=aircraft: swapped(now, a))
        else:
            charged_packs += 1
        if depleted_queue > 0:
            depleted_queue -= 1
            charging_count += 1
            schedule(t + params.pack_charge_effective_s, pack_ready)

    def begin_swap(t: float, aircraft: _Aircraft) -> None:
        deposit_depleted(t)
        acquire_charged(t, aircraft)

    def swapped(t: float, aircraft: _Aircraft) -> None:
        nonlocal swaps_total
        advance(t)
        swaps_total += 1
        aircraft.state = _READY
        try_launch(t)

    # ---- the reserve-exhaustion watchdog ----------------------------------
    #
    # An aircraft sitting in the queue burns reserve in wall-clock time, not
    # at events, so nothing above would ever notice it running out.  A
    # periodic sweep catches it.  The tick is short relative to the reserve
    # so the loss time is accurate to a few seconds.

    tick = max(1.0, params.reserve_s / 60.0)

    def watchdog(t: float) -> None:
        advance(t)
        for aircraft in list(queue):
            if t - aircraft.queued_at >= aircraft.energy_s:
                queue.remove(aircraft)
                lose(t, aircraft, reserve=True)
        update_block(t)
        if t + tick < params.horizon_s:
            schedule(t + tick, watchdog)

    # ---- run ---------------------------------------------------------------

    # Initial condition: a *desynchronised* fleet.
    #
    # Starting every aircraft ready and launching as fast as the lanes
    # allow is not a conservative assumption, it is a different scenario —
    # 200 aircraft released together arrive together, and the resulting
    # massacre is a fact about the initial condition rather than about the
    # carrier.  Each aircraft instead becomes ready at a uniformly random
    # point in one full cycle, which is the phase distribution a fleet
    # settles into anyway, and lets the free-running launch policy express
    # steady-state demand rather than a thundering herd.
    cycle_estimate_s = (
        params.sortie_s
        + params.turnaround_s
        + service.mean_occupancy_s
        + params.stow_s
    )
    for aircraft in fleet:
        schedule(
            rng.uniform(0.0, cycle_estimate_s),
            lambda now, a=aircraft: recharged(now, a),
        )
    schedule(0.0, watchdog)

    while events:
        t, _, callback = heapq.heappop(events)
        if t > params.horizon_s:
            break
        callback(t)
    advance(params.horizon_s)

    measured_span = max(1e-9, params.horizon_s - measured_from)
    losses = lost_reserve + lost_retries
    attempted = recoveries_total + losses
    head_capacity_s = params.capture_heads * measured_span
    launch_capacity = params.launch_lanes * measured_span / params.launch_interval_s
    cycle_s = params.sortie_s + params.turnaround_s + service.mean_occupancy_s + params.stow_s
    demand_per_hour = 3600.0 * params.fleet_size / cycle_s

    result = FleetResult(
        params={**asdict(params), "slots": params.slots, "seed": seed},
        throughput_per_hour=round(3600.0 * recoveries / measured_span, 2),
        demand_per_hour=round(demand_per_hour, 2),
        recoveries=recoveries,
        losses_reserve_exhausted=lost_reserve,
        losses_retries_exhausted=lost_retries,
        loss_pct=round(100.0 * losses / attempted, 2) if attempted else 0.0,
        mean_queue_wait_s=round(sum(waits) / len(waits), 2) if waits else 0.0,
        p95_queue_wait_s=round(_percentile(waits, 95.0), 2) if waits else 0.0,
        max_queue_depth=max_depth,
        fleet_remaining=sum(1 for a in fleet if a.state is not _GONE),
        head_utilisation=round(min(1.0, head_busy_s / head_capacity_s), 4),
        launch_utilisation=round(min(1.0, sorties / max(1e-9, launch_capacity)), 4),
        head_blocked_fraction=round(min(1.0, head_blocked_s / measured_span), 4),
        peak_slots_used=peak_slots,
        mean_airborne=round(airborne_integral / measured_span, 2),
        sorties=sorties,
        binding_constraint="",
        keeper_cycles=recoveries_total,
        swap_cycles=swaps_total,
        pack_starved=pack_wait_events > 0,
        mean_on_final=round(on_final_integral / measured_span, 2),
        peak_on_final=peak_on_final,
        peak_trim_error_g=round(peak_trim_error_g, 1),
        trim_exceedance_fraction=round(trim_exceeded_s / measured_span, 4),
        dock_mass_g=round(
            params.capture_heads * params.head_mass_g + params.slots * params.slot_mass_g,
            1,
        ),
        payload_margin_g=0.0,
    )
    carried = result.dock_mass_g + params.fleet_size * params.aircraft_mass_g
    result = replace(
        result,
        payload_margin_g=round(params.payload_ceiling_g - carried, 1),
        binding_constraint=_diagnose(result, params),
    )
    return result


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (pct / 100.0) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _diagnose(result: FleetResult, params: FleetParams) -> str:
    """Name what is actually limiting this configuration.

    A number without a cause invites the wrong fix: adding heads to a
    magazine-bound carrier buys nothing and costs actuators.
    """

    # Trim is checked first because it is the only constraint here that
    # fails silently: the recovery queue can be healthy, losses zero, and
    # every utilisation comfortable, while the carrier is drifting under
    # the aircraft trying to land on it.
    if result.trim_exceedance_fraction > TRIM_EXCEEDANCE_THRESHOLD:
        return (
            f"buoyant trim ({result.peak_trim_error_g:.0f} g peak error vs "
            f"{params.trim_authority_g:.0f} g authority, "
            f"{100.0 * result.trim_exceedance_fraction:.0f}% of the time "
            f"outside it): ballast at {params.ballast_rate_g_s:.1f} g/s "
            "cannot follow the launch and recovery waves"
        )
    # Launch is checked before the empty-queue case on purpose.  A
    # launch-limited carrier has an empty recovery queue precisely because
    # it cannot get aircraft into the air fast enough to fill one, so
    # "queue empty" reads as health when it is the symptom.
    if result.launch_utilisation >= 0.85:
        return (
            f"launch lanes ({params.launch_lanes} at "
            f"{params.launch_interval_s:.0f}s spacing = "
            f"{3600.0 * params.launch_lanes / params.launch_interval_s:.0f} "
            "sorties/h): the carrier can recover faster than it can release"
        )
    # Pack starvation is checked here, before the empty-queue case, for the
    # same reason trim and launch are: a pool-limited carrier holds its
    # recovered aircraft in slots waiting for charged packs, so the recovery
    # queue is empty and "none" would read as health while airborne count is
    # suppressed. The fix is spare packs or chargers, not more heads.
    if params.energy_mode == "swap" and result.pack_starved:
        return (
            f"battery pool ({params.spare_packs} spare packs, "
            f"{params.charger_channels_effective} chargers): recovered "
            "aircraft wait for a charged pack before they can relaunch"
        )
    if result.loss_pct <= LOSS_THRESHOLD_PCT and result.max_queue_depth <= 1:
        return "none — the carrier serves this fleet with the queue empty"
    if result.peak_slots_used >= params.slots and params.slots < params.fleet_size:
        return (
            f"magazine slots ({params.slots} filled): heads idle while "
            "captured aircraft have nowhere to be indexed to"
        )
    # Approach airspace is named before capture heads: when corridors are
    # tighter than heads, the airspace is the true limit and the surplus
    # heads sit idle behind it, so blaming the heads would send the fix to
    # the wrong place (more heads buy nothing).
    if (
        params.traffic_enabled
        and params.approach_corridors_effective < params.capture_heads
        and result.mean_on_final >= 0.85 * params.approach_corridors_effective
    ):
        return (
            f"approach airspace ({params.approach_corridors_effective} "
            f"corridors for {params.capture_heads} heads): converging "
            "aircraft contend for the volume below the carrier and the "
            "surplus heads idle behind deconfliction"
        )
    if result.head_utilisation >= 0.85:
        return (
            f"capture heads ({params.capture_heads} at "
            f"{100.0 * result.head_utilisation:.0f}% utilisation): arrivals "
            "outrun the interfaces that can accept them"
        )
    if result.loss_pct > LOSS_THRESHOLD_PCT:
        return (
            "arrival burstiness: heads are not saturated on average, but "
            "the fleet arrives in a wave and the reserve runs out inside it"
        )
    if params.energy_mode == "swap":
        return (
            "pack-charge throughput: airframes cycle freely, the pool "
            "recharges packs as fast as it can and that is the limit"
        )
    return "recharge time: the fleet is charge-limited, not recovery-limited"


# --------------------------------------------------------------------------
# The question the module exists to answer
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadSweepResult:
    fleet_size: int
    #: Fewest heads that served the fleet within the loss threshold at every
    #: seed tried, or ``None`` if no tested count did.
    minimum_heads: int | None
    tested_heads: tuple[int, ...]
    seeds: tuple[int, ...]
    rows: tuple[dict[str, object], ...]


def sweep_heads(
    params: FleetParams,
    service: ServiceModel,
    *,
    head_counts: Iterable[int] = range(1, 13),
    seeds: Sequence[int] = (1, 2, 3),
) -> HeadSweepResult:
    """Find the fewest capture heads that serve a fleet.

    Every head count is run at several seeds and must pass at all of them.
    A configuration that serves the fleet at one seed and drops aircraft at
    another has not been shown to work; it has been shown to be marginal,
    and marginal is the answer, not the passing seed.
    """

    tested = tuple(head_counts)
    rows: list[dict[str, object]] = []
    minimum: int | None = None
    for heads in tested:
        runs = [
            simulate_fleet(replace(params, capture_heads=heads), service, seed=seed)
            for seed in seeds
        ]
        # "Worst" must rank on both failure modes: a run that recovers
        # everything while drifting is worse than one with a rounding-error
        # loss rate and solid trim, and ranking on loss alone would pick
        # the wrong run to report.
        worst = max(runs, key=lambda r: (r.loss_pct, r.trim_exceedance_fraction))
        served = all(run.serves_fleet for run in runs)
        rows.append(
            {
                "capture_heads": heads,
                "serves_fleet": served,
                "worst_loss_pct": worst.loss_pct,
                "throughput_per_hour": round(
                    sum(r.throughput_per_hour for r in runs) / len(runs), 2
                ),
                "demand_per_hour": worst.demand_per_hour,
                "mean_queue_wait_s": round(
                    sum(r.mean_queue_wait_s for r in runs) / len(runs), 2
                ),
                "p95_queue_wait_s": worst.p95_queue_wait_s,
                "head_utilisation": round(
                    sum(r.head_utilisation for r in runs) / len(runs), 4
                ),
                "launch_utilisation": round(
                    sum(r.launch_utilisation for r in runs) / len(runs), 4
                ),
                "mean_airborne": round(
                    sum(r.mean_airborne for r in runs) / len(runs), 2
                ),
                "peak_trim_error_g": max(r.peak_trim_error_g for r in runs),
                "trim_exceedance_fraction": max(
                    r.trim_exceedance_fraction for r in runs
                ),
                "max_queue_depth": max(r.max_queue_depth for r in runs),
                "dock_mass_g": worst.dock_mass_g,
                "keeper_cycles": max(r.keeper_cycles for r in runs),
                "swap_cycles": max(r.swap_cycles for r in runs),
                "peak_on_final": max(r.peak_on_final for r in runs),
                "mean_on_final": round(
                    sum(r.mean_on_final for r in runs) / len(runs), 2
                ),
                "binding_constraint": worst.binding_constraint,
            }
        )
        if served and minimum is None:
            minimum = heads
    return HeadSweepResult(
        fleet_size=params.fleet_size,
        minimum_heads=minimum,
        tested_heads=tested,
        seeds=tuple(seeds),
        rows=tuple(rows),
    )


def run_study(
    *,
    fleet_sizes: Sequence[int] = (10, 50, 100, 200),
    base: FleetParams | None = None,
    service: ServiceModel | None = None,
    head_counts: Iterable[int] = range(1, 13),
    seeds: Sequence[int] = (1, 2, 3),
    calibration_episodes: int = 40,
    noise_scale: float = 1.0,
) -> dict[str, object]:
    """Size capture heads across a range of fleets and report the result."""

    base = base or FleetParams()
    if service is None:
        service = calibrate_service(
            episodes=calibration_episodes,
            scenario=sil_p0b if noise_scale == 1.0 else noise_scenario(noise_scale),
        )
    sweeps = [
        sweep_heads(
            replace(base, fleet_size=size),
            service,
            head_counts=head_counts,
            seeds=seeds,
        )
        for size in fleet_sizes
    ]
    return {
        "study": "fleet throughput",
        "service_model": asdict(service),
        "base_params": asdict(base),
        "seeds": list(seeds),
        "loss_threshold_pct": LOSS_THRESHOLD_PCT,
        "sweeps": [
            {
                "fleet_size": sweep.fleet_size,
                "minimum_heads": sweep.minimum_heads,
                "tested_heads": list(sweep.tested_heads),
                "rows": list(sweep.rows),
            }
            for sweep in sweeps
        ],
        "caveats": [
            "Terminal-traffic interaction is an optional overlay (approach "
            "corridors, deconfliction holds, wake miss-penalty), OFF by "
            "default. With it off the twin's one-aircraft-one-dock behaviour "
            "stands and every head count is a LOWER bound; with it on the "
            "count tightens, but the traffic parameters are estimates for a "
            "belly layout this scalar model cannot represent.",
            "Stow and go-around times are engineering estimates for "
            "mechanisms that do not exist. The sweep is sensitive to them; "
            "vary them before believing a head count.",
            "Endurance and recharge are times, not a battery model, and no "
            "capacity fade or temperature effect is represented.",
            "Buoyant trim is modelled only as a scalar: net lightness and "
            "the ballast chase. Where in the magazine an aircraft is "
            "stowed, and therefore pitch and roll moments, is not — a "
            "magazine that fills from one end trims the vehicle long "
            "before total mass matters.",
            "Radio capacity and airspace deconfliction are absent entirely.",
            "Trim authority, ballast rate and ballast capacity are "
            "estimates for a mass-exchange system that has not been "
            "designed. They set the trim verdict, so vary them before "
            "believing it.",
            "No hardware has recovered a single aircraft yet. This sizes an "
            "architecture; it does not validate one.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fleet-throughput study: how many capture heads serve N aircraft"
    )
    parser.add_argument(
        "--fleet",
        type=int,
        nargs="+",
        default=[10, 50, 100, 200],
        help="fleet sizes to size heads for",
    )
    parser.add_argument("--max-heads", type=int, default=12)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--episodes", type=int, default=40, help="calibration episodes")
    parser.add_argument("--endurance", type=float, default=600.0)
    parser.add_argument("--sortie", type=float, default=420.0)
    parser.add_argument("--recharge", type=float, default=3600.0)
    parser.add_argument("--stow", type=float, default=DEFAULT_STOW_S)
    parser.add_argument("--slots", type=int, default=None)
    parser.add_argument("--policy", choices=("energy", "fcfs"), default="energy")
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument(
        "--noise",
        type=float,
        default=1.0,
        help=(
            "calibrate against this multiple of Lighthouse-grade positioning "
            "noise; >1 is what exercises the go-around and divert paths"
        ),
    )
    parser.add_argument(
        "--energy",
        choices=("charge_in_place", "swap"),
        default="charge_in_place",
        help="how recovered aircraft regain energy",
    )
    parser.add_argument("--swap-s", type=float, default=DEFAULT_SWAP_S)
    parser.add_argument(
        "--spare-packs",
        type=int,
        default=0,
        help="swap mode: packs in circulation beyond one per airframe",
    )
    parser.add_argument(
        "--charger-channels",
        type=int,
        default=None,
        help="swap mode: packs that can charge at once (default: one per airframe)",
    )
    parser.add_argument(
        "--pack-charge-s",
        type=float,
        default=None,
        help="swap mode: time for one pooled pack to recharge (default: --recharge)",
    )
    parser.add_argument(
        "--corridors",
        type=int,
        default=None,
        help=(
            "max aircraft on final at once (default: one per head, i.e. no "
            "airspace limit). Set below --max-heads to model a belly that "
            "cannot separate its heads"
        ),
    )
    parser.add_argument(
        "--traffic-holds-s",
        type=float,
        default=0.0,
        help="deconfliction hold added per other aircraft on final",
    )
    parser.add_argument(
        "--traffic-miss",
        type=float,
        default=0.0,
        help="capture probability lost per other aircraft on final",
    )
    args = parser.parse_args(argv)

    base = FleetParams(
        endurance_s=args.endurance,
        sortie_s=args.sortie,
        recharge_s=args.recharge,
        stow_s=args.stow,
        magazine_slots=args.slots,
        queue_policy=args.policy,
        horizon_s=args.hours * 3600.0,
        energy_mode=args.energy,
        swap_s=args.swap_s,
        spare_packs=args.spare_packs,
        charger_channels=args.charger_channels,
        pack_charge_s=args.pack_charge_s,
        approach_corridors=args.corridors,
        traffic_holds_s=args.traffic_holds_s,
        traffic_miss_penalty=args.traffic_miss,
    )
    print(
        json.dumps(
            run_study(
                fleet_sizes=args.fleet,
                base=base,
                head_counts=range(1, args.max_heads + 1),
                seeds=args.seeds,
                calibration_episodes=args.episodes,
                noise_scale=args.noise,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
