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

## Repository map

- [Prototype specification](docs/prototype-p0.md)
- [Docking mechanism](hardware/dock/README.md)
- [Prototype BOM](hardware/bom.csv)
- [Mass and capture-envelope model](aiur/p0.py)
- [Engineering tests](tests/test_p0.py)

## Design rule

Every claimed capability must resolve to one of:

1. a measured requirement,
2. an executable model/test,
3. a cited component specification, or
4. an explicitly labeled engineering target.

Concept art is not evidence.

## Status

Pre-alpha. CARRIER-P0 definition and bench-test tooling.
