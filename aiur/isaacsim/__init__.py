"""NVIDIA Isaac Sim integration scaffold for CARRIER-P0.

Status: **unexecuted**. Nothing under this package has been run inside an
actual Isaac Sim install — this sandbox has no GPU/Omniverse runtime to run
it on. Per the repository's design rule (README.md, "Design rule"), no
claim from this package is evidence of anything until someone with a real
Isaac Sim install runs it and records the outcome. Treat it the same way
``docs/digital-twin.md`` treats the analytic twin before calibration: a
model claim, not a result.

Scope: this is an *additional*, higher-fidelity visualization/rigid-body
layer, not a replacement for ``aiur.sim`` — the dependency-free analytic
twin remains the thing that runs in CI and closes SIL gates. Isaac Sim
requires a licensed NVIDIA GPU workstation and is never going to run in the
free-of-dependencies CI this project deliberately built. See
docs/isaac-sim-integration.md for scope, requirements, and the validation
checklist that must be completed before this package's output is cited
anywhere as a result.

Two kinds of module live here, deliberately kept apart:

* Pure Python, no Isaac Sim dependency, importable and unit-tested in the
  normal CI (``bridge.py``, ``flight.py``): the logic that decides what the
  real ``aiur.dock_controller.DockController`` sees and does, reusing the
  same mechanism model (``aiur.sim.dock_physics``) and actuator/switch
  primitives (``aiur.sim.sensors``) the analytic twin already uses and has
  test coverage for.
* Isaac Sim-dependent modules (``scene.py``, ``run_p0b.py``): import
  ``isaacsim``/``omni`` lazily, inside functions, so importing this package
  never fails in an environment without Isaac Sim installed. These are the
  parts nobody has run yet.
"""
