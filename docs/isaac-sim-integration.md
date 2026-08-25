# Isaac Sim integration scaffold

Status: **unexecuted**. Everything below describes code that has never run
against a real NVIDIA Isaac Sim install — this program's CI, and the sandbox
this scaffold was written in, have no GPU/Omniverse runtime to run it on.
Per the repository's [design rule](../README.md#design-rule), nothing here
is evidence of anything until someone with a licensed Isaac Sim workstation
runs it, records what happened, and this document is updated with the
outcome — the same discipline [digital-twin.md](digital-twin.md) applies to
the analytic twin before calibration, one step further removed: that twin
has run millions of episodes in CI; this has run zero.

## What this is, and is not

[developer.nvidia.com/isaac/sim](https://developer.nvidia.com/isaac/sim) is
NVIDIA's GPU-accelerated, PhysX/Omniverse-based robotics simulator —
photorealistic rendering, more complete rigid-body and contact physics than
a hand-rolled analytic model, and (beyond what this scaffold touches)
synthetic sensor data and a ROS 2 bridge.

It is **not** a replacement for `aiur/sim`, the dependency-free analytic
twin that closes SIL gates in CI (see [digital-twin.md](digital-twin.md)).
Isaac Sim needs a licensed NVIDIA GPU workstation; it will never run in the
free-of-external-dependencies CI this project deliberately built, and nobody
should try to make `sil-gates.yml` depend on it. Its plausible role is
narrower and additive:

- a higher-fidelity rigid-body/contact sandbox to stress the mechanism
  design against physics the analytic funnel/collet/keeper model
  simplifies away (see "Known missing physics" in digital-twin.md);
- photorealistic renders for reviews, presentations, and — eventually —
  synthetic training data if a vision-based terminal sensor is ever
  explored;
- a bench-in-the-loop or HIL-adjacent target once real bench telemetry
  exists to compare against.

None of those roles is claimed as delivered here. What exists today is a
scaffold: enough wiring to get one scripted SIL-P0-B-shaped episode running
in an Isaac Sim scene, built so the parts that can be validated without
Isaac Sim (the bridge logic) are, and the parts that can't (the actual Isaac
Sim calls) are clearly marked as unverified.

## What's real and what's modeled

Same table shape as digital-twin.md, because the same discipline applies —
here it also has to distinguish "real code" from "code nobody has run":

| Piece | Module | Status |
| --- | --- | --- |
| Dock latch logic | `aiur.dock_controller.DockController` | Real, unmocked — the same production code the analytic twin and the bench article run. Reached through the same call shape either way. |
| Funnel/collet/keeper mechanics, switches, servo | `aiur.sim.dock_physics.DockAssembly`, `aiur.sim.sensors.Switch`/`KeeperServo` | Real, unmodified — reused wholesale rather than reimplemented in PhysX. This is the twin's existing, tested contact model; Isaac Sim is not asked to also own funnel contact (see "Contact ownership" below). |
| Bridge glue (`aiur/isaacsim/bridge.py`, `flight.py`) | New | Pure Python, no Isaac Sim dependency, **unit-tested** in `tests/test_isaacsim_bridge.py` with a scripted probe trajectory standing in for a correctly-wired Isaac Sim rigid body. This is the one part of the scaffold with any CI-checked evidence behind it, and it says nothing about the two rows below. |
| Stage construction (`scene.py`) | New | Isaac Sim API calls, **unexecuted**. Every `# VERIFY:` comment in the file is a guess at the installed API surface. |
| Run loop (`run_p0b.py`) | New | Isaac Sim API calls, **unexecuted**, same caveat. |

## Requirements (untested — see the checklist)

- A workstation with a supported NVIDIA GPU and driver, per NVIDIA's
  published Isaac Sim system requirements.
- Isaac Sim installed via the Omniverse launcher or a pip/container install,
  under whatever license terms apply — this project takes no position on
  licensing and the reader must check NVIDIA's current terms themselves.
- Isaac Sim's own bundled Python interpreter (`python.sh` / `python.bat`),
  **not** the interpreter this repository's dependency-free suite runs
  under. `isaacsim` is only importable there.
- This repository on `PYTHONPATH` (or run from the repo root) so
  `aiur.isaacsim.*` and `aiur.sim.*` are importable from Isaac Sim's
  interpreter.

## How it's organized

```
aiur/isaacsim/
  __init__.py    status/scope note
  bridge.py      IsaacTwinBridge — pure Python, no Isaac Sim dependency, unit-tested
  flight.py      ApproachController — pure Python, scripted approach force law
  scene.py       build_stage() — Isaac Sim API calls, unexecuted
  run_p0b.py     standalone launcher — Isaac Sim API calls, unexecuted
```

`bridge.py` and `flight.py` import nothing from Isaac Sim at module scope —
they are ordinary dependency-free Python and importable (and tested) in the
same CI as the rest of the project. `scene.py` and `run_p0b.py` import
`isaacsim`/`omni`/`pxr` only inside functions, so importing them does not
fail without Isaac Sim installed; *calling* `build_stage()` or running
`run_p0b.main()` does require it.

Run it (from Isaac Sim's interpreter, once someone validates the
`# VERIFY:` calls against their install):

```
./python.sh -m aiur.isaacsim.run_p0b --headless --duration 30
```

This runs one scripted SIL-P0-B-shaped episode — not a Monte Carlo
campaign, not one of the `aiur.sim.campaign` scenarios, and it closes no SIL
gate. Its value, once it runs, is visual/physical inspection: does the
mechanism-plus-controller sequence look right against PhysX contact and
rendering, not "does it pass."

## Contact ownership: the one design decision worth arguing about

`aiur.sim.dock_physics.DockAssembly.step` corrects whatever
position/velocity it's handed — funnel-wall clamp, seat pin, seat hold — the
same way it corrects `DroneBody` in the analytic twin's engine loop
(`aiur/sim/engine.py`: `drone.step(...)` runs first, `mechanism.step(...)`
corrects after). The scaffold's contract mirrors that, every step,
regardless of mechanism phase:

1. Let PhysX integrate the probe one step (gravity disabled — see
   `scene.py` — plus whatever force `ApproachController` applied).
2. Feed the resulting pose/velocity to `IsaacTwinBridge.step`, then write
   `corrected_probe_state()` straight back onto the rigid body before the
   next physics step. During free flight this is a no-op; during
   funnel/seat engagement it's the constraint correction.

The probe rigid body is never toggled kinematic, and the funnel/keeper
meshes carry no `UsdPhysics.CollisionAPI` — so PhysX's own collision
response never produces a second, disagreeing answer for where the probe
is during capture. `aiur/isaacsim/bridge.py`'s module docstring has the
full rationale.

This was a design decision made without ever running it. The honest
alternative — give the funnel/keeper real PhysX colliders and have this
mechanism only supply switch/servo truth from proximity thresholds, closer
to how a real optical/mechanical sensor would be built — is a legitimate
different scaffold, not an obviously wrong one, and it is not implemented
here. Anyone picking this up should treat the choice as open, not settled.

## Known gaps and simplifications

- **No guidance stack.** `flight.ApproachController` is a minimal
  velocity-setpoint tracker for the demo, not
  `aiur.sim.guidance.TerminalGuidance`. It has none of the abort/evasion/FDIR
  logic the analytic twin's findings (digital-twin.md, "Twin-derived
  engineering findings") depend on. Do not read anything into how this
  scaffold's approach behaves.
- **No carrier hull.** SIL-P0-B has none in the analytic twin either (see
  `aiur.sim.bodies.KinematicRig`'s docstring) — it mirrors the P0-B bench
  rig, not the full airship. A P0-C/P0-D scene is future work and would need
  a carrier hull sized from `aiur.sim.bodies.CarrierParams`.
- **No disturbances, sensors, or faults.** `aiur.sim.disturbances`,
  `aiur.sim.sensors.PoseSensor`, and `aiur.sim.faults` are not wired in.
  Every episode this scaffold can currently run is the nominal case.
- **Gravity compensation is a blunt instrument.** `scene.py` disables
  gravity on the probe outright, because `DroneBody`'s tracking law (which
  `ApproachController` mirrors) models a closed-loop-controlled quadrotor
  that already rejects gravity through its own attitude/thrust loop and has
  no gravity term to fight it with. A more faithful scaffold would give the
  probe real weight and a real hover-thrust term; this one does not.
- **API surface is unverified.** Every `# VERIFY:` in `scene.py` and
  `run_p0b.py` is a specific, nameable risk — not a general disclaimer.

## Validation checklist

Before any claim from this scaffold is cited anywhere in this repository as
a result (not a model claim), whoever runs it first should:

1. Confirm the `# VERIFY:` calls in `scene.py` and `run_p0b.py` against the
   installed Isaac Sim version; patch import roots/method names as needed
   and note the version tested against at the top of this document.
2. Run `./python.sh -m aiur.isaacsim.run_p0b --duration 30` (windowed, not
   headless, for the first run) and confirm visually: the probe descends
   into the funnel, the keeper visual closes, and the console prints
   `capture_confirmed`.
3. Confirm `result.controller.state` ends `CAPTURED` and matches what
   `tests/test_isaacsim_bridge.py`'s scripted-descent test already predicts
   for the same starting geometry — if it doesn't, the mismatch is between
   Isaac Sim's real physics and the bridge's assumptions, which is exactly
   the kind of finding this scaffold exists to produce.
4. Record the outcome (pass/fail, what had to be patched, Isaac Sim
   version) in this document, replacing "unexecuted" in the status line
   above.

Until step 4 happens, this document and the code it describes are a
proposal, not a capability.
