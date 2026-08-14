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
bind are ones nobody had written down. The conclusion the sections below
build to is in [The verdict](#the-verdict-recovery-is-the-easy-part-to-scale):
recovery, the funded article, is the easy part; the swarm is gated by the
two resources that do not amortise — radio and energy — and the pivot that
unlocks "hundreds" is onboard autonomy, not a bigger dock.

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

### Pitch and roll: where you stow them, not just how many

The ballast term above is a scalar — total mass off the carrier against a
heave chase. It says nothing about *where* the stowed aircraft sit, and a
magazine is a grid of slots: a partially-filled one is only balanced if its
occupied slots are symmetric about the neutral point on both axes. The model
now optionally carries that geometry (`--magazine-span-m`, plus
`--magazine-width-m` / `--magazine-columns` for the lateral axis, off by
default so the numbers above are unchanged), tracks the longitudinal pitch
**and** lateral roll moments of the stow distribution, and folds both
exceedances into the pass criterion the same way heave is.

The finding is that **the stow policy is a free pitch-trim control input,
and getting it wrong fails the carrier on identical hardware.** For a
200-aircraft carrier over a 30 m magazine, held to a 2000 g·m pitch
authority:

- a **balanced** policy — index each recovered aircraft into the free slot
  that pulls the centroid back toward neutral — peaks at ~1,600 g·m and
  holds;
- an **edge** policy — the naive revolver or belt that just uses the next
  physical slot — peaks at ~12,800 g·m and is outside authority essentially
  all the time.

Same aircraft, same fleet, same dock; the only difference is which slot the
indexer chooses, and one serves the fleet while the other pitches the
vehicle continuously under the aircraft trying to land on it. Stowing is not
a filing problem, it is attitude control, and it costs nothing to get right
if the indexer is told to.

The same holds on the lateral axis. Give the magazine width and columns and
a side-biased fill rolls the vehicle exactly as an end-biased fill pitches
it; the balanced policy minimises the 2-D moment vector, so one indexer rule
holds both axes at once. Which axis actually binds is geometry: a long thin
keel magazine pitches far more easily than it rolls (roll stays small for
the 200-aircraft case above), while a short wide one is the reverse — with a
30 m-wide magazine the edge policy blows roll past authority 90% of the time
and balanced pulls it back. Roll authority on a keel-hung magazine is
usually the tighter of the two, so it is worth checking, not assuming.

The pitch and roll authorities are estimates for a moment budget (vectored
thrust, movable or distributed ballast) that has not been designed, and the
discreteness of a single aircraft sets a floor the indexer cannot beat.

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

## Radio: the ceiling battery swap runs into

Every airborne aircraft needs a supervisory link and every aircraft on final
needs a tight control link, and radios are finite — Crazyradio addresses
dozens, not hundreds. The model carries this as a link budget
(`--radio-channels` × `--links-per-channel`), off by default. The safe design
refuses to launch an aircraft it cannot talk to, so radio shows up as a **hard
ceiling on concurrent airborne aircraft**, never as a lost-link loss.

That ceiling is independent of heads, slots, charge and launch, which is
exactly why it matters: it is the wall battery swap hits. Swap removes the
charge limit and wants ~60 aircraft airborne from a 200-airframe fleet — but
at 20 links per radio, one radio holds the sky at 20, two at 40, three at 60.
The airborne count tracks the link budget almost exactly until enough radios
are added that heads become the limit again. So the full chain a "hundreds of
drones" claim has to answer is:

> recharge → (battery swap) → radio links → capture heads → launch lanes → corridors → trim,

and every one of them is a real resource that has to be bought. There is no
single bottleneck to fix, and "airborne" — the number that does anything —
is set by whichever of these is scarcest.

The link budget is a scalar: it does not model channel contention, packet
loss, interference, or the mesh/broadcast schemes a real hundred-aircraft
system would need instead of unicast control. It says only "you cannot fly
more than you can talk to", which is the floor of the problem, not its
ceiling.

## A worked design point: what "hundreds airborne" actually costs

The sections above each size one resource. That is how the effects were
found, but it is not an answer — the binding constraint walks the chain, so
the only honest cost is with every constraint on at once. The
`size_for_airborne` solver does that: it takes a target **airborne** count
(the number that does something, not the number owned), seeds a
configuration from the duty cycle, then repairs it against the integrated
simulation — reading the binding constraint each run reports and buying down
exactly that resource until the carrier both serves its fleet and holds the
target overhead.

```
python -m aiur.sim.fleet --target-airborne 50 100 | python tools/report_fleet.py
python -m aiur.sim.fleet --target-airborne 50 100 --energy swap | python tools/report_fleet.py
```

For a Crazyflie-class duty cycle (600 s endurance, 420 s sortie, 3600 s
recharge), the bill for **100 aircraft airborne** is:

| resource | charge-in-place | battery swap |
| --- | ---: | ---: |
| airframes owned | ~965 | ~110 |
| capture heads | 10 | 10 |
| magazine slots | ~965 | ~110 |
| launch lanes | 2 | 2 |
| radios (×20 links) | 5 | 5 |
| ballast rate | ~12 g/s | ~12 g/s |
| charger channels | — | ~1,030 |
| binding constraint | radio | radio |

The two columns are the whole argument in one table. **Charge-in-place
turns "100 airborne" into a 965-airframe programme** — the ~10% airborne
fraction, paid in aircraft. **Battery swap cuts that to ~110 airframes** but
moves the cost into ~1,030 charger channels and their spare packs: the same
energy throughput, held in batteries instead of airframes. Which is cheaper
is the real procurement question, and it is now a number, not a hand-wave.

Radio is the taut constraint at both points because the link budget scales
linearly with airborne count and the solver sizes it to exactly meet the
target — so "buy radios for the aircraft you intend to fly" is not a caveat,
it is line one of the bill. Capture heads, the thing the programme currently
worries about, are ten either way and never the wall.

The solver leaves terminal-traffic interaction off (independent corridors),
so its head and airspace counts are lower bounds; and it sizes trim, pitch,
roll and pack authorities as *requirements the vehicle must meet*, not as
things known to exist. It is a sizing tool, not a validation.

## Two aircraft classes: scouts are radio-expensive

The carrier does not fly one kind of aircraft. A Crazyflie-class article
proves the dock; a WHOOP-class scout — a ducted 65–75 mm airframe, ~25 g,
short-legged — flies ahead to look. They are different airframes with
different docks and duty cycles, but they share the things the carrier has
only one of: the radio, the launch airspace, and the lift. `size_carrier`
sizes each class's recovery subsystem on its own duty cycle, then sums the
shared budgets.

```
python -m aiur.sim.fleet --target-airborne 20 --scouts 10 | python tools/report_fleet.py
```

The result is a warning about the cheap aircraft, not the expensive one.
**A scout wing dominates the radio budget out of all proportion to its
size.** Ten video scouts, at ~4 links each for an FPV stream, draw 40 links
— *twice* the 20 links of a full 20-aircraft recovery fleet, for a third of
the airborne count. Push the video link to 8 and the scouts alone need more
radios than the entire recovery fleet. Radio was already the taut wall for
the recovery fleet; scouts are the thing that makes it taut sooner, and it
is their comms payload, not their airframe, that does it.

The short legs bite too. A scout on a three-minute sortie recovers far more
often than a Crazyflie on ten, so it needs *more* capture heads than the
recovery class per aircraft airborne — the small cheap drone is the
cycle-expensive one. None of this is visible if scouts are treated as
"extra aircraft"; they are a different resource profile, and the number they
turn on is the radio.

Heads and docks are not shared between the classes — a whoop and a Crazyflie
need different capture geometry — so those counts are per class. Radio and
lift are exact sums because a link budget and a mass budget genuinely add.
Scout endurance, mass and per-link video cost are estimates for an airframe
that has not been built; the radio verdict is only as good as the per-link
cost behind it.

## The verdict: recovery is the easy part *to scale*

One clarification before the argument, because [prior art](prior-art.md)
insists on it: a single aerial capture is a genuinely hard *capability* — it
took DARPA Gremlins years and nine near-miss contacts, and turbulence has
defeated every attempt back to the 1930s Goblin. That is exactly why P0 is
funded on the dock. What follows is *not* that recovery is easy to build. It
is that recovery is cheap to **scale**: it amortises, and the scaling walls
are elsewhere. Hold both — the hard engineering problem is also the cheap
scaling resource.

Put every section above together and the model reaches a conclusion the
programme is not currently organised around. Size the whole carrier, all
constraints on, across the range, and one pattern dominates every row:

| airborne | airframes (charge / swap) | capture heads | radios | taut set (reduce any → target breaks) |
| ---: | ---: | ---: | ---: | --- |
| 20 | 193 / 22 | 2 | 2 | heads, ballast, airframes |
| 50 | 482 / 55 | 5 | 3 | radio, airframes |
| 100 | 964 / 110 | 10 | 6 | launch, ballast, airframes |
| 200 | 1,928 / 219 | 19 | 12 | launch, ballast, airframes |

The taut set is found by probing — reducing each resource one step and
seeing if the target survives — so it reports what genuinely binds, not
whichever check happens to fire first. The lesson is in how each resource
*scales*:

- **The dock amortises.** Two capture heads serve 200 aircraft; nineteen
  serve two thousand. Capture is a shared, reused resource, so it has slack
  and almost never appears in the taut set — which is exactly why the
  programme's engineering attention, aimed squarely at the dock, is aimed at
  the cheap corner of the problem. (It shows up only at 20 airborne, where
  integer rounding makes two heads tight; that is a rounding artefact, not a
  scaling wall.)
- **The taut set is precisely the resources that scale one-for-one with the
  swarm.** Airframes (or their charger equivalent) are taut in every row;
  launch lanes, ballast, and radio rotate through as the tightest of the
  1:1 resources. Every airborne aircraft needs its own share of each — a
  link, a launch slot in time, a gram of ballast, a joule — and none of it
  amortises the way a head does.

So what makes a swarm hard is everything that scales one-for-one — **links,
launch, ballast, and above all joules** — and recovery, the funded article,
is none of them. Recovery has to be proven, but it is being treated as the
scaling risk when it is the one part with room to spare.

Among those 1:1 walls, radio is the one with a known escape, which is why it
matters out of proportion to its rank in the taut set. **The pivot that
unlocks "hundreds" is onboard autonomy** — the one lever that turns a
one-for-one resource back into an amortising one. Radio binds per-aircraft
*only if every aircraft needs a continuous control link*. Break that —
aircraft that fly the mission and only check in periodically — and one radio
supervises many:

| aircraft per radio | radios for 200 airborne |
| ---: | ---: |
| 20 (continuous link) | 10 |
| 100 (light supervision) | 2 |
| 200 (autonomous) | 1 |

Autonomy is the enabling technology for a real swarm, and it draws on the
same GNSS-independent relative navigation (SHARED-001) the verticals already
need. This finding is now its own inheritable requirement —
[SHARED-006](verticals/README.md#shared-derived-requirements), onboard
mission/terminal autonomy sufficient that one radio channel supervises many
aircraft — filed with the honest note that it runs top-down from this model,
not bottom-up from vertical pressure: no vertical has yet flown enough
aircraft to feel the wall this memo is describing. The scout finding is the
mirror image: a video-streaming whoop re-imposes a fat continuous link and
eats the budget, so the architecture wants **autonomy out, not video back**.

**And one carrier is the wrong unit.** A single vehicle tops out on radio,
lift, and being a single point of failure. Hundreds airborne over a region
is not one impossible mothership; it is a **mesh of carriers, each cycling a
few dozen autonomous aircraft, tiled geographically.** This model sizes one
node; the region is N nodes.

But the mesh is not an *economy* — and the sizer says so. Slice a 200-airborne
region across nodes of different size and the aggregate airframe count is
invariant (~1,930 whether it is ten nodes of 20 or two of 100): the duty
cycle is linear, so distributing the swarm neither creates nor destroys the
bill. Worse, the per-node quantised resources — radios, capture heads — get
*mildly dearer* with many small nodes, because each node wastes a fractional
minimum (20 radios across ten small nodes versus 12 across two large ones).
So the number of carriers is not chosen for efficiency; there is none to
find in the aircraft bill. It is chosen for the things this model does not
carry: what one vehicle can physically lift and power, resilience against
losing a node, geographic coverage, and inter-node relay and handoff for
range. Those terms — carrier structure and crew favouring fewer big nodes,
coverage and relay favouring more small ones — are where the vehicle-count
decision actually lives.

The sizer confirms this by probing, not by which check fires first. For each
converged design point it reduces every resource one step and reports the
set that actually breaks the target. Given equal design margin, that taut
set is striking: at 100 airborne it is **launch lanes, ballast, and airframes
— every one a resource that scales one-for-one with the swarm — while capture
heads, the amortising resource, carries slack and never appears.** Radio
joins the set at smaller targets and drops out when it is given the same
headroom every other resource gets; it was never uniquely the wall, only the
one the first draft sized tightest. The finding is not "radio" — it is the
asymmetry itself: **the binding set is exactly the non-amortising resources,
and the dock, the funded focus, is the one with room to spare.**

## What this does not say

- **Terminal-traffic interaction is an overlay, off by default.** With it
  off, the twin's one-aircraft-one-dock behaviour stands and **every head
  count is a lower bound**; with it on, the count tightens, but the traffic
  parameters are estimates for a belly layout this scalar model cannot
  itself represent (see the section above).
- **Stow, go-around, ballast rate, ballast capacity and trim authority are
  estimates** for mechanisms that do not exist. The trim verdict in
  particular is only as good as the authority figure behind it.
- **Trim geometry covers pitch and roll, not vertical stacking.** Both
  moments from the stow distribution are modelled (off by default); the
  authorities are estimates for an undesigned moment budget, and the slot
  grid is a single layer — a magazine stacked in height would add a third
  term this does not carry.
- **Radio is a scalar link budget, off by default.** It caps concurrent
  airborne aircraft at a link count; it does not model channel contention,
  packet loss, interference, or the mesh/broadcast schemes a real
  hundred-aircraft system needs. It is the floor of the comms problem.
- **Energy is seconds, not chemistry.** No capacity fade, no temperature.
- **No hardware has recovered a single aircraft.** This sizes an
  architecture; it does not validate one.

## What it changes

0. **Fund the things that do not amortise: energy cycling and onboard
   autonomy.** The dock amortises and is the funded article; links and
   joules scale one-for-one with the swarm and are not funded as the
   scaling risk they are. Autonomy — the aircraft flying without a
   continuous link — is the single change that moves the radio wall, and it
   reuses SHARED-001. This is the first priority; everything below is
   downstream of it.
1. **Do not build a dock per aircraft.** Build few heads and many passive
   slots. The study puts numbers on "few": 2 for 200, 3 for 400.
2. **There is no single bottleneck — size the whole chain.** The binding
   constraint walks: recharge → (battery swap) → radio links → capture heads
   → launch lanes → corridors → trim. Fix one and the next takes over.
   "Airborne", the number that does anything, is set by whichever is
   scarcest, so a credible fleet plan budgets all of them, not the cheapest.
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
7. **Make the indexer balance the magazine — it is free attitude control.**
   A balanced stow policy holds pitch and roll on the same hardware an
   edge-filling revolver tips out of authority. Specify it as a requirement
   on the indexer, not an emergent property of whatever slot is nearest, and
   check roll as well as pitch — on a keel magazine roll authority is the
   tighter axis.
8. **Buy radios per aircraft you intend to fly, not per aircraft you own.**
   The link budget hard-caps concurrent airborne; it is the ceiling battery
   swap runs into, so a swap investment is wasted without the radios to use
   the aircraft it frees. And keep scouts autonomous and store-and-forward,
   not live-FPV, unless a mission pays for the link: a video wing eats the
   budget that would otherwise fly the recovery fleet.
9. **Plan a mesh of carriers, not a bigger one.** Lift and radio both punish
   the monolith. A region of hundreds airborne is N nodes each cycling a few
   dozen; this study sizes one node.
