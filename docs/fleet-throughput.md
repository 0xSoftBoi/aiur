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

## Battery swap: moving the bottleneck, not removing it

Recharge dominates because a recovered aircraft holds a slot for the full
charge — an hour against a ten-minute sortie. The obvious attack is to stop
charging airframes in place and instead swap the depleted pack for a charged
one in seconds, letting the dead pack recharge in a shared pool while the
airframe flies again. The model now carries this as an energy mode
(`--energy swap`), with a pool of spare packs and charger channels.

It works, and the result is more honest than the pitch:

```
python -m aiur.sim.fleet --fleet 200 --energy swap \
    --spare-packs 1000 --charger-channels 1000 | python tools/report_fleet.py
```

**Swap does not create energy — it converts idle airframes into idle
batteries.** With a 12 s exchange, the per-airframe cycle drops from ~4000 s
to ~460 s, so the same 200 airframes want to fly ~9× as often. Airborne
count rises from ~22 to ~82. But the fleet still burns energy at its flight
rate, so the pool must supply packs at that rate: sustaining it needs on the
order of **1,000 spare packs and 1,000 charger channels** — roughly the
charge-in-place slot count, now filled with batteries instead of airframes.

That is the actual trade, and it is a good one *if and only if* airframes
are the expensive, few, individually-qualified resource and packs are cheap.
You buy airborne-count-per-airframe and pay in battery inventory and charger
mass. If packs are not cheap, swap buys nothing.

**Swap also re-exposes capture heads as the bottleneck.** Once the fleet is
no longer charge-bound, its demand jumps past what a few heads can recover:
at 200 aircraft in swap mode, 4 heads still do not serve the fleet. The
constraint chain is recharge → (swap) → heads → launch, and fixing one
promotes the next. There is no single lever.

### Fewer moving parts is the reliability position, and swap costs there

The dock already has one unavoidable moving mechanism: the keeper servo,
which actuates once per recovery. Battery swap adds a second life-limited
mechanism that also cycles once per recovery. The model reports both as
lifetime actuations, because that — not part count alone — is what a
mechanism qualification gates on: NASA-STD-5017 requires moving mechanical
assemblies to be life-tested to at least twice expected life (more for
life-limited or high-cycle mechanisms), with torque/force margin held across
the whole range.

The numbers make the cost concrete. A 200-aircraft carrier runs on the order
of **2,000 keeper cycles and 2,000 swap cycles in a four-hour window**.
Extrapolated to a continuous deployment that is millions of cycles per
mechanism per year, each of which must be qualified with margin. Swap
doubles the count of life-limited actuated mechanisms in the recovery path
and drives both hard. A passive charge contact has no such qualification
burden — it is the fewer-moving-parts option, and it is why charge-in-place
is not simply the loser here.

The design rule that falls out: **add an actuated mechanism only when a
passive alternative cannot meet the requirement, and when you do, its cycle
count is a first-class cost carried next to the benefit — never folded into
a score.** The trade study module already applies exactly this rule to the
capture mechanism (actuators and sensed channels are printed, never scored);
the fleet model now applies it to the energy architecture.

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

## Terminal traffic: why "2 heads serve 200" has a condition attached

Every head count above assumes each head owns an independent approach
corridor — the twin flies one aircraft at one dock, so nothing in it sees
converging traffic. The model now carries the missing effect as an overlay,
**off by default** (so the numbers above are unchanged), with two knobs:

- `--corridors N` caps how many aircraft may be on final at once, whatever
  the head count. It models a belly that cannot spatially separate its
  heads: the surplus heads then idle behind the airspace, and the model
  names "approach airspace" as the binding constraint instead of the heads.
- `--traffic-holds-s` and `--traffic-miss` are the interaction *cost* an
  aircraft pays per other aircraft simultaneously on final — deconfliction
  hold time, and capture probability lost to wake and avoidance.

Turned on, it produces the finding that most qualifies the headline:

**Under shared-airspace interference, adding capture heads does not rescue
the fleet.** With a 25 s deconfliction hold per neighbour, a 200-aircraft
carrier loses ~19–21% of its fleet at *every* head count from 2 to 12 — the
losses barely move, because each head added is one more aircraft in the same
contested volume, so concurrency and hold time rise together. A fleet that
"2 heads serve" in the independent-corridor model is not served at any head
count once its heads share one approach volume.

The design consequence is sharp: **the way to scale recovery is more
independent corridors, not more heads in one corridor.** Heads must be
spatially separated around the belly into genuinely non-interfering approach
volumes; co-locating them buys throughput on paper and congestion collapse
in the air. "2 heads serve 200" is true *if and only if* those two heads
are in separate corridors — which is a belly-geometry requirement the
earlier result silently assumed.

The overlay is deliberately conservative and cannot substitute for a real
airspace model: all concurrent finals are treated as mutually interfering (a
single shared volume), which over-charges heads that are in fact well
separated, and the interference is a scalar with no geometry. The two knobs
bracket the truth — independent corridors (off) at one end, one shared
volume (penalty on) at the other — and a real belly sits between them, to be
calibrated to a specific layout. What the model now refuses to let you do is
assume the optimistic end for free.

## What this does not say

- **Terminal-traffic interaction is an overlay, off by default.** With it
  off, the twin's one-aircraft-one-dock behaviour stands and **every head
  count is a lower bound**; with it on, the count tightens, but the traffic
  parameters are estimates for a belly layout this scalar model cannot
  itself represent (see the section above).
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
   dock can serve is recharge-bound — until you break that with battery
   swap, which then promotes capture heads to the bottleneck. There is no
   single lever; the chain is recharge → heads → launch.
3. **Prefer passive; price every actuated mechanism in cycles, not count.**
   Battery swap roughly doubles airborne-count-per-airframe but adds a
   second life-limited mechanism running millions of cycles a year, on top
   of the keeper servo. Whether that trade is worth it depends entirely on
   whether airframes are dearer than the pack-and-charger inventory swap
   demands — a number this study frames but cannot decide for you.
4. **Size a mass-exchange system now, as a requirement, not later as an
   integration surprise.** Minimum ballast rate ≈ launch rate × aircraft
   mass, and it must be sized against head count, not just fleet size.
5. **Specify "airborne", never "fleet size".** They differ by ~9× on the
   current duty cycle.
6. **Scale recovery with independent corridors, not more heads.** Terminal
   traffic makes co-located heads collapse under their own congestion; the
   belly must separate them into non-interfering approach volumes, and the
   head counts above hold only when it does.
7. **The remaining unmodelled effects that move the number the unsafe way**
   are magazine geometry (pitch/roll trim from where aircraft stow) and
   radio capacity. Both are next.
