# aiur

Persistent airborne infrastructure for autonomous drone fleets.

Aiur is an engineering project for a lighter-than-air carrier that can deploy, coordinate, recover, and eventually recharge autonomous aircraft while keeping compute, communications, and energy aloft.

## Current milestone: CARRIER-P0

We are deliberately **not** starting with the 40 m vehicle.

CARRIER-P0 exists to answer the architecture's highest-risk question:

> Can a buoyant carrier repeatedly launch a small autonomous aircraft and recover it onto a moving belly dock?

The first flight article is an indoor helium platform built around a ~4.5 m airship, one active recovery dock, and one to two micro-UAVs.

### P0 scope

- helium lift only;
- one mechanically positive belly dock;
- 1–2 micro-UAVs before swarm expansion;
- high-precision externally referenced positioning;
- tethered/prop-guarded indoor operations;
- measured approach error, closing speed, capture outcome, and turnaround time;
- no airborne charging until mechanical recovery is repeatable.

### Explicit non-goals

P0 does **not** attempt hydrogen lift, outdoor/BVLOS operations, eight full-size drones, a 40 m envelope, or DGX-class airborne compute. Those are downstream scaling problems.

## Digital twin

The engineering loop's SIL stage is executable. `aiur/sim` is a
deterministic, dependency-free digital twin — carrier, aircraft, sensing,
disturbances, fault injection, and the dock mechanics wrapped around the
**real** `DockController` — with a Monte Carlo campaign runner that closes
SIL-B/SIL-C/SIL-D gates mirroring the P0-B/C/D hardware gates:

```
python -m aiur.sim.campaign --scenario sil-p0b --episodes 200 --seed 1
```

Architecture, current model findings, and the sim-to-real calibration
contract: [docs/digital-twin.md](docs/digital-twin.md). CI runs the SIL
gates on every push.

## Dual-use verticals

The product core (buoyant carrier + mechanically positive dock + recovery
autonomy + evidence-gated loop + twin) is vertical-agnostic. Exploratory
concept studies with derived requirement deltas live in
[docs/verticals/](docs/verticals/README.md): agriculture, energy
infrastructure, wildfire response support, and toys/STEM. CARRIER-P0
remains the only funded article; the twin's `outdoor-gust-sweep` and
`degraded-sensor-sweep` studies quantify the two milestones every non-lab
vertical shares.

## Engineering practice

The program is benchmarked against how established hardware organizations
run model-to-hardware programs — aerospace, automotive, consumer hardware,
space mechanisms, electronics, safety, and the hardware-rich iteration
school. The [survey](docs/engineering-practice-survey.md) is the baseline
assessment; the [adoption plan](docs/adoption-plan.md) is what is being
done about it, tracked in an executable register:

```
python -m aiur.adoption_loop
```

## Repository map

Program definition:

- [Prototype specification](docs/prototype-p0.md)
- [Closed-loop engineering graph](docs/engineering-loop.md)
- [Requirement closure matrix](aiur/requirements.py) — `python -m aiur.requirements`
- [Engineering practice survey](docs/engineering-practice-survey.md)
- [Practice-adoption plan](docs/adoption-plan.md)
- [Dual-use vertical studies](docs/verticals/README.md)

Analysis and models:

- [Digital twin](docs/digital-twin.md) and the [package](aiur/sim/)
- [Mass and capture-envelope model](aiur/p0.py)
- [Capture-chain tolerance stack](aiur/tolerance.py) — `python -m aiur.tolerance`
- [Dock FMECA and fault trees](docs/dock-fmeca.md)
- [Common-mode analysis](docs/common-mode.md)
- [Test-like-you-fly exception ledger](docs/tlyf-exceptions.md)

Safety:

- [Hazard log](docs/hazard-log.md) and its [registry](aiur/hazards.py)
- [Kill path](docs/kill-path.md)
- [Battery SOP](docs/battery-sop.md)
- [Test cards, crew roles, and readiness review](docs/test-cards.md)

Hardware:

- [Docking mechanism](hardware/dock/README.md)
- [P0-A Rev-A bench article](hardware/dock/p0a-bench.md) and its [test card](hardware/dock/p0a-test-card.md)
- [P0-A fabrication packet](hardware/dock/p0a-fabrication.md)
- [Electrical evidence packet](docs/electrical-evidence.md)
- [Bench fault-insertion unit](hardware/dock/fault-insertion.md)
- [Golden-article rule](hardware/dock/golden-article.md)
- [Dock deletion review](docs/dock-deletion-review.md)
- [Reproducible Rev-A CAD](hardware/dock/cad/README.md)
- [Prototype BOM](hardware/bom.csv)

Executable core:

- [Fail-safe dock controller](aiur/dock_controller.py)
- [P0-A evidence reducer](aiur/p0a_evidence.py)
- [Engineering tests](tests/)

## Design rule

Every claimed capability must resolve to one of:

1. a measured requirement,
2. an executable model/test,
3. a cited component specification, or
4. an explicitly labeled engineering target.

Concept art is not evidence.

## Status

Pre-alpha. CARRIER-P0 definition, bench-test tooling, and an executable
digital twin closing SIL gates ahead of hardware.
