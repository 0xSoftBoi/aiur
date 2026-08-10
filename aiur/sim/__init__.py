"""CARRIER-P0 digital twin.

Executable form of the engineering loop's SIL stage: deterministic,
dependency-free simulation of the carrier, aircraft, sensing, and the
recovery dock — running the **real** ``DockController`` and the real gate
evaluator — plus fault injection and Monte Carlo campaigns that close the
SIL-B/SIL-C/SIL-D gates before hardware is touched.

Entry points:

* ``aiur.sim.campaign`` — CLI campaign runner (see ``--help``);
* :func:`aiur.sim.engine.run_episode` — one seeded episode;
* ``aiur.sim.scenarios`` — scenario builders and sweep cases;
* ``aiur.sim.gates`` — SIL gate definitions and evaluation.
"""

from .engine import EpisodeConfig, EpisodeOutcome, EpisodeResult, run_episode
from .gates import SIL_GATES, evaluate_sil_gate, validate_sil_gates


def __getattr__(name: str):
    # Lazy so `python -m aiur.sim.campaign` does not import the CLI module
    # twice (runpy would warn about aiur.sim.campaign already in sys.modules).
    if name in ("run_campaign", "run_sweep"):
        from . import campaign

        return getattr(campaign, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "EpisodeConfig",
    "EpisodeOutcome",
    "EpisodeResult",
    "SIL_GATES",
    "evaluate_sil_gate",
    "run_campaign",
    "run_episode",
    "run_sweep",
    "validate_sil_gates",
]
