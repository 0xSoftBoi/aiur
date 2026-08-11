# Prior art: how others solve airborne launch, recovery, and swarm logistics

Status: literature and programme survey, opened 2026-08-11
Scope: what has actually been built or demonstrated for the three problems
CARRIER-P0 and the fleet model touch — aerial recovery, swarm launch/autonomy,
and fleet logistics (charge, storage, one-operator scale) — and what it means
for our architecture and the [fleet-throughput](fleet-throughput.md) findings.

This is a survey of public work. It is cited, and it marks what is
*demonstrated* against what is *concept*. Its job is to stop the programme
re-deriving what is already known and to check the model's conclusions
against reality.

## The short version

- **Aerial drone-to-carrier recovery has been done exactly once at maturity**
  (DARPA Gremlins, C-130, 2021) and it was hard — years of work, nine
  near-miss contacts, and turbulence as the defining enemy. Recovery is the
  hard-won *capability*.
- **Launch and swarm autonomy are comparatively solved** at demonstration
  scale: 103 drones from fighters (Perdix), 30 from a tube (LOCUST), 250
  under one operator (OFFSET).
- **The fleet-logistics half — few capture points, many charge bays, a gantry
  indexer, one operator for dozens — is a fielded commercial product on the
  ground** (Sentien Hive-XL: 80 drones, 80 bays). It is almost exactly the
  architecture our model sizes, which is strong outside validation.
- **Nobody has put the three together on a persistent lighter-than-air
  carrier.** Airships recovered fixed-wing in the 1930s; balloons launch
  drones today but do not recover them; mothership UAVs carry swarms but
  recover the *carrier* to reload, not the drones to the carrier. The
  specific combination CARRIER-P0 targets is still open.

## 1. Aerial recovery — the hard part, and history agrees

**DARPA Gremlins (X-61A).** The most mature aerial drone-recovery system in
the world. A C-130 trails a **stabilised docking "bullet" on a towed line,
below and away from the aircraft**; the Gremlin flies up the wake-quieted
zone, latches the bullet, **folds its wings**, and a **robotic arm** draws it
into the cargo bay. First successful in-flight recovery October 2021, after a
2020 campaign that came *within inches on nine attempts* but was defeated by
relative motion in the wake. The final experiment recovered, refurbished, and
reflew a vehicle within **24 working hours** — the turnaround number that
matters for persistence.
[DARPA](https://www.darpa.mil/news/2021/gremlins-airborne-recovery) ·
[Air & Space Forces](https://www.airandspaceforces.com/c-130-catches-x-61-gremlins-vehicle-airborne-recovery/) ·
[FlightGlobal, the nine near-misses](https://www.flightglobal.com/military-uavs/2020/12/excess-movement-prevents-c-130-from-retrieving-gremlins-in-mid-air-test/141565.article)

**The lesson every source repeats: wake is the enemy, and launch is cheap
while recovery is not.** The 1930s Navy airships USS *Akron* and *Macon*
launched and recovered Curtiss F9C Sparrowhawk biplanes on a trapeze hook —
proving buoyant carriers *can* recover aircraft — while the McDonnell XF-85
Goblin parasite fighter failed precisely because aligning its hook in a
bomber's turbulent slipstream was unmanageable. Modern patents exist purely
to **control the airflow behind a carrier during recovery**
([US 9,878,777](https://patents.google.com/patent/US9878777)).

**Academic docking mechanisms mirror our dock exactly.** A 2026 *Drones*
paper builds a fixed-wing mothership recovering a quadrotor with a
**V-shaped docking plate** (geometry that converts alignment error into
centring — our funnel), **staged GPS-then-vision guidance with an ArUco
marker array** for terminal relative pose (our SHARED-001), and an **NMPC**
rendezvous controller, validated in simulation
([MDPI Drones 10(3):212](https://www.mdpi.com/2504-446X/10/3/212)).
GPS-denied variants fuse **UWB + vision** in a hover→approach→dock state
machine
([Zhang et al., J. Franklin Inst.](https://www.sciencedirect.com/science/article/abs/pii/S0016003222001569)).

**What this means for us.** Two things, one comforting and one a gap:

- A **slow buoyant carrier is the right platform for the recovery problem**,
  not a workaround. Gremlins spent its whole difficulty budget on C-130 wake;
  an indoor helium airship at <0.2 m/s closing speed has a fraction of that
  disturbance. The thing that beat everyone is the thing our platform has
  least of. This is the strongest external argument for the LTA approach.
- But **our model does not represent carrier wake at all.** Terminal-traffic
  interaction models aircraft-on-aircraft; it does not model the carrier's
  own downwash/recirculation over the belly dock. Given that wake is *the*
  historical killer, this is the most important unmodelled physics, and it
  belongs in the twin (or on the P0 bench) before any outdoor claim. The
  Gremlins pattern — **dock on a stabilised line below and away from the
  hull, not flush to the belly** — is a design option worth carrying.

## 2. Launch and swarm autonomy — comparatively solved

- **ONR LOCUST**: a tube launcher puts **30 Coyote-class UAVs** airborne in
  quick succession; they share information and collaborate autonomously once
  up ([ONR](https://www.onr.navy.mil/media-center/news-releases/locust-autonomous-swarming-uavs-fly-future)).
- **Perdix**: **103 micro-drones released from three F/A-18 flare
  dispensers** (2016), demonstrating collective decision-making, adaptive
  formation, and self-healing — an expendable-launch, autonomous-swarm
  proof at exactly the scale under discussion
  ([Defense One](https://www.defenseone.com/technology/2016/09/these-swarming-drones-launch-fighter-jets-flare-dispensers/131414/)).
- **DARPA OFFSET**: swarms of **250 air/ground systems**, and in the final
  field experiment a **single operator drove 130–174 platforms** via
  "swarm tactics" and human-swarm teaming
  ([DARPA](https://www.darpa.mil/research/programs/offensive-swarm-enabled-tactics) ·
  [Army/Fort Campbell](https://www.army.mil/article/252556/fort_campbell_hosts_final_field_experiment_for_large_scale_drone_program)).

**What this validates.** The fleet model's verdict — that the swarm's wall is
per-aircraft comms, and the escape is **onboard autonomy so one operator/radio
supervises many** — is exactly what OFFSET fielded (one operator, ~170
platforms) and what LOCUST/Perdix assume (autonomous collaboration, not
per-aircraft piloting). This is direct outside support for making autonomy,
not the dock, the funded scaling priority. Launch being cheap (drop, tube,
dispenser) matches the model treating launch as lanes-and-detents, not a
closed loop.

## 3. Fleet logistics — the proven few-heads-many-slots machine

**Sentien Robotics Hive-XL** is, on the ground, almost exactly the
architecture our model sizes: a trailer with **parallel landing zones (the
few capture points), 80 charge bays (the many passive slots), a gantry
retrieval system that moves drones between pads and bays (the indexer)**, an
11 kW power plant, and **one operator running 80 drones across ~30
simultaneous missions**
([Sentien Hive-XL](https://www.sentien.com/hive-xl) ·
[Forbes / Hambling](https://www.forbes.com/sites/davidhambling/2024/05/16/hives-for-us-drone-swarms-ready-to-deploy-this-year/)).
Automated **battery-swap and swap-and-recharge** stations are a mature
research and product line
([BECS and multirotor swap systems](https://www.researchgate.net/publication/259741070_Automated_Battery_Swap_and_Recharge_to_Enable_Persistent_UAV_Missions)).

**What this validates, and corrects.**

- **Validates the architecture wholesale.** Few sensed capture points, many
  passive charge bays, a gantry indexer, one operator for dozens — the
  separation of capture from storage that the fleet model exists to size is a
  shipping product. We are not inventing the logistics; we are moving a proven
  ground template onto a buoyant carrier.
- **Validates "airborne, not owned".** Hive-XL sustains ~30 missions from 80
  drones — a ~37% airborne fraction, higher than our ~10% Crazyflie figure
  because its drones have a friendlier duty cycle, but the same shape: the
  fleet on the pads always outnumbers the fleet in the air.
- **Battery swap is real, not speculative.** The model's swap mode has
  fielded precedent; the honest cost it flags (a large charged-pack/charger
  inventory) is what a Hive's 80 bays physically are.

## 4. Lighter-than-air motherships — launched, rarely recovered

- **HALE balloons as drone motherships**: Aerostar high-altitude balloons are
  being turned into launch platforms, and the US Army launched an **Apollo-R
  loitering munition from an Urban Sky balloon at Valiant Shield 2026**
  ([TWZ](https://www.twz.com/news-features/aerostar-high-altitude-balloons-being-turned-into-drone-motherships)).
  These **launch**; they do not recover.
- **China's Jiutian** mothership UAV is designed to carry and release a
  **swarm of 100+ small drones**, then **recover the carrier to reload** —
  i.e. the drones are one-way or land elsewhere; the reusable asset is the
  mothership, not the swarm
  ([Aerospace Global News](https://aerospaceglobalnews.com/news/china-jiutian-drone-mothership-maiden-flight/)).
- **US Air Force / DARPA "flying aircraft carrier"** concepts recur but the
  recovery half is repeatedly flagged as the unsolved-in-general problem
  ([Air Force Technology](https://www.airforce-technology.com/features/featurethe-mothership-uav-swarms-inspire-research-into-flying-aircraft-carriers-4505474/)).

**The unclaimed combination.** Persistent **buoyant carrier + repeated
belly recovery + recharge + relaunch of the *same* small aircraft** is the
one nobody has fielded. Balloons launch-only; Jiutian recovers the carrier,
not the drones; Gremlins recovers drones but from a fuel-burning C-130 that
cannot loiter for days. CARRIER-P0's specific bet — recovery onto a
persistent LTA node — sits in the gap between them. That is a genuine reason
to build it, and it is exactly the highest-risk interaction P0 is scoped to
prove.

## What the survey changes in our own conclusions

1. **Soften "recovery is the easy part".** The fleet model is right that
   recovery *amortises* — two capture heads serve two hundred aircraft, so it
   is not the *scaling* wall. But the survey is a reminder that a single aerial
   capture is the hard-won *capability*: it took DARPA years and nine
   near-misses, and it is exactly why P0 is funded on the dock. Both are true
   and the memo should hold both: **recovery is the hard engineering problem
   and the cheap scaling resource.** Do not let the second sentence retire the
   first.
2. **Add carrier wake to the risk register.** It is the historical killer of
   aerial recovery and the twin does not model it. The LTA platform mitigates
   it (slow, low prop wash) but does not remove it, and the outdoor verticals
   cannot be believed until it is quantified. Consider the Gremlins
   below-and-away stabilised-dock pattern.
3. **Autonomy is externally confirmed as the scaling pivot.** OFFSET's one
   operator over ~170 platforms is the verdict's claim, fielded. Fund it.
4. **The logistics are de-risked by Hive.** The magazine/indexer/charge
   architecture is a shipping ground product; the novel work is putting it on
   a carrier that flies and trims, not the logistics themselves.

## What to steal

- **Gremlins**: towed, stabilised capture point *below and away* from the
  hull to escape wake; wings-fold-then-grip for dense stow; the 24-hour
  refurbish-and-refly turnaround as a persistence benchmark.
- **Academic docking**: V-plate/funnel + ArUco-vision + NMPC is a concrete,
  published instantiation of SHARED-001 and the capture geometry — a starting
  point for the terminal sensor trade, not a blank sheet.
- **Hive-XL**: the ground template for the belly magazine — parallel capture
  pads, many charge bays, a gantry indexer, one-operator scale.
- **OFFSET / LOCUST / Perdix**: swarm-tactics autonomy and expendable launch
  as the model for breaking the comms wall and for cheap release.

## Sources

Programmes and products: DARPA Gremlins, ONR LOCUST, DARPA OFFSET, DoD
Perdix, Sentien Hive-XL, China Jiutian, Aerostar/Urban Sky HALE balloons.
Academic: *Design of an Autonomous Airborne Recovery System* (MDPI Drones
10(3):212, 2026); UWB-vision GPS-denied docking (J. Franklin Institute,
2022). Historical: USS Akron/Macon Sparrowhawk trapeze; McDonnell XF-85
Goblin. Patents: US 9,878,777 (recovery airflow control), US 10,179,648
(airborne launch/recovery apparatus). Links inline above.
