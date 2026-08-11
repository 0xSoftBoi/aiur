# Fleet-throughput study

Status: decision memo, opened 2026-08-10
Scope: what a carrier costs to operate N aircraft, before any scaling work is funded
Executable source: [`aiur/sim/fleet.py`](../aiur/sim/fleet.py) —
`python -m aiur.sim.fleet | python tools/report_fleet.py`

## Why this study exists

Every result the programme has produced so far is about **one** recovery:
one aircraft, one dock, one approach. That is the right first question and
it is what P0 gates on. It is also silent on the question that decides
whether the architecture is worth scaling at all: one dock recovering one
aircraft says nothing about a carrier recovering a hundred.

The gap matters because the intuitive answer is wrong in both directions.
The obvious worry — mass — is not the constraint. The constraints that do
bind are ones nobody had written down.

## The architecture being sized

The design move under test is the **separation of capture from storage**.

One actuated dock per aircraft does not scale: 180 g each is 36 kg at
N=200, plus 200 sensed, actuated, FMECA'd channels. So instead:

- a small number of **capture heads** — expensive, sensed, actuated, where
  aircraft arrive;
- a large number of **magazine slots** — passive detents, grams each, no
  actuator and no sensed channel, where aircraft wait and charge;
- an **indexer** that moves a captured aircraft off the head into a slot,
  freeing the head for the next arrival.

Head count is then set by arrival rate and slot count by fleet size, and
the two stop multiplying. How small "a small number" is was unknown, and
it is a number, so it was simulated.

## How it is calibrated

The queue is not fed by an assumed service time. `calibrate_service` runs
seeded `run_episode` calls against the **real twin** — the same
`DockController`, guidance, sensing and dock mechanics the SIL gates use —
and reduces them to a per-attempt capture probability and an empirical
distribution of head-occupancy times, which the fleet model samples with
replacement. When the twin's physics changes, this study changes with it.

Occupancy samples are resampled rather than fitted to a distribution: the
twin's durations are bimodal (a capture on the first pass costs about half
what one after a re-alignment does) and a mean would erase exactly the tail
a queue is sensitive to.

## Result

40 calibration episodes, 3 seeds per configuration, 4-hour horizon,
Crazyflie-class duty cycle (600 s endurance, 420 s sortie, 3600 s
recharge), 5 s launch spacing on one lane:

| fleet | min heads | throughput/h | demand/h | mean airborne | binding constraint at the minimum |
| ---: | ---: | ---: | ---: | ---: | --- |
| 10 | 1 | 8.8 | 8.9 | 1.1 | none, queue empty |
| 50 | 1 | 44.1 | 44.5 | 5.4 | recharge |
| 100 | 1 | 87.4 | 88.9 | 10.8 | recharge |
| 200 | 2 | 177.5 | 177.8 | 21.9 | recharge |
| 400 | 3 | 353.8 | 355.6 | 44.8 | capture heads (94% utilisation) |

## What it says

**Two capture heads serve 200 aircraft. Three serve 400.** The
head-per-aircraft assumption was wrong by two orders of magnitude, and so
was the "3–6 heads" estimate that opened this work. Capture hardware is
simply not where the difficulty lives.

**The fleet is far smaller in the air than on paper.** With 10 minutes of
endurance against an hour of recharge, only ~11% of the fleet is airborne
at any moment. **200 aircraft is 22 aircraft overhead.** Anyone specifying
"hundreds of drones" needs to say whether they mean owned or airborne,
because the two differ by an order of magnitude and the second is the one
that does anything. Getting 200 *airborne* on this duty cycle needs ~1,350
aircraft — or a shorter charge, which is the highest-leverage change
available: at a 900 s recharge the same 200 airborne needs a fleet of 450.

**Recharge, not recovery, is the dominant constraint** at every fleet size
that the dock can serve at all. The programme's engineering attention is
currently on the capture mechanism, and this says the next marginal hour is
worth more spent on charge rate and slot power delivery.

**Launch capacity is a separate ceiling that fails silently.** One release
lane at 5 s spacing caps the vehicle at 720 sorties/hour regardless of head
count — and it does so with an empty recovery queue, zero losses, and
comfortable head utilisation. Every recovery metric reads healthy while the
carrier is capped. A diagnosis that only looks at heads and slots calls
this configuration fine, which is why the model now names it explicitly.

**Energy-priority queueing only earns its place once the mechanism misses.**
With a perfect capture, ranking the queue by remaining reserve is provably
identical to first-come-first-served — every aircraft arrives with the same
reserve, so reserve order *is* arrival order. The policies diverge only
when go-arounds put aircraft of differing energy in the queue together, and
then energy priority is consistently better (32.1% vs 33.3% losses at
p_capture 0.85, across five seeds). This is worth stating because the
opposite is easy to assume: the policy is not free insurance, it is a
response to an unreliable mechanism.

## The buoyant-trim coupling

The largest finding is one the study was not originally built to make.

A buoyant carrier that releases mass without landing gains lift. This is
not a subtlety: [Flying Whales](https://www.flying-whales.com/en/faq/)'
LCA60T answers it with a dedicated mass-exchange system that swaps payload
for ~60 t of water ballast during hover loading, and staffs a
**load-exchange officer as one of only two crew**. A well-funded programme
with Safran, Thales and Evolito as suppliers considers this first-order.

A drone carrier has the same problem in a harder form. Cargo goes down and
stays down; aircraft come back, one at a time, at whatever rate the queue
delivers. **The load-exchange problem never closes.** Fleet throughput is
therefore not merely constrained by the carrier — it is a *disturbance
input* to the carrier's trim.

The model now carries a rate- and capacity-limited ballast system chasing
the mass currently off the vehicle. Two results:

**Ballast rate is a hard requirement derived from launch rate.** Releasing
an aircraft every 5 s at 37 g demands 7.4 g/s of ballast just to keep up
with the launch wave. Below ~3 g/s a 200-aircraft carrier spends 9–52% of
its time outside a 100 g trim authority; at 5 g/s it holds. The floor is
set by the discreteness of a single aircraft, not by the ballast system —
past ~5 g/s, more capability buys nothing.

**More capture heads make trim worse.** Peak uncorrected trim error for a
200-aircraft fleet rises from 70 g at one head to 140 g at eight, because
faster recovery means sharper mass transients. Heads and ballast have to be
sized together; sizing heads alone moves the failure somewhere the loss
counter cannot see it.

That last point is why trim was folded into the pass criterion rather than
reported alongside it. A configuration that recovers every aircraft while
drifting vertically has not served its fleet — it is moving the dock under
aircraft on terminal approach, which is the one thing the entire capture
architecture exists to avoid.

## What this does not say

- **Capture heads are modelled as independent corridors.** The twin flies
  one aircraft at one dock, so no aircraft ever sees another on approach.
  Real converging traffic adds wake, deconfliction holds, and go-arounds
  caused by other aircraft. **Every head count here is a lower bound.**
- **Stow, go-around, ballast rate, ballast capacity and trim authority are
  estimates** for mechanisms that do not exist. The trim verdict in
  particular is only as good as the authority figure behind it.
- **Trim is a scalar.** Where in the magazine an aircraft is stowed — and
  therefore pitch and roll moments — is absent. A magazine that fills from
  one end trims the vehicle long before total mass matters.
- **Radio is absent.** Crazyradio addresses dozens, not hundreds. This is a
  real ceiling on fleet size and it is not represented.
- **Energy is seconds, not chemistry.** No capacity fade, no temperature.
- **No hardware has recovered a single aircraft.** This sizes an
  architecture; it does not validate one.

## What it changes

1. **Do not build a dock per aircraft.** Build few heads and many passive
   slots. The study puts numbers on "few": 2 for 200, 3 for 400.
2. **Charge rate is the scaling lever, not capture rate.** Every fleet the
   dock can serve is recharge-bound.
3. **Size a mass-exchange system now, as a requirement, not later as an
   integration surprise.** Minimum ballast rate ≈ launch rate × aircraft
   mass, and it must be sized against head count, not just fleet size.
4. **Specify "airborne", never "fleet size".** They differ by ~9× on the
   current duty cycle.
5. **The next modelling work is terminal traffic interaction**, because it
   is the one unmodelled effect that moves the headline number in the
   unsafe direction.
