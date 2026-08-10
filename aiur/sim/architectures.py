"""Registry of capture architectures entered into the trade study.

The baseline is listed alongside the alternatives rather than treated as
the incumbent that others must displace.  It earns its place on the same
axes as everything else, and if it loses on the axis the verticals hinge
on, that is a finding rather than an embarrassment — the whole reason to
run this before printing is that changing a design on disk costs nothing
and changing one on a bench costs a build.

Candidates that fail to capture at all are kept in the registry with their
result recorded.  A rejected architecture with a measured reason is a
result; a quietly deleted one is a gap that somebody re-proposes in six
months.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dock_physics import DockAssembly, DockGeometry


@dataclass(frozen=True)
class BaselineSpec:
    """The funnel, probe and sliding fork keeper the programme is building."""

    key: str = "baseline"
    name: str = "Funnel + probe + sliding fork keeper (Rev-B)"
    summary: str = (
        "180 mm funnel narrows to a Ø16 mm throat; a Ø12 mm belt guides the "
        "probe in, a sliding fork closes under its Ø9 mm seat, and two "
        "independent switches report seat and keeper-closed."
    )
    part_count: int = 5
    actuator_count: int = 1
    sensed_channels: int = 2
    est_dock_mass_g: float = 75.0
    est_probe_mass_g: float = 2.0
    known_weaknesses: tuple[str, ...] = (
        "Acceptance is set by a Ø16 mm throat, so terminal positioning has "
        "to be millimetre-grade — the requirement every non-laboratory "
        "vertical inherits as SHARED-001.",
        "Slot width is caught between clearing the mast and retaining the "
        "head; Rev-A failed both and the pair had to be resized together.",
        "Retention depends on a powered actuator holding position, so the "
        "safety case leans on fail-locked controller logic.",
        "Both sensed channels are the same switch type on the same "
        "mechanism, so their independence is a claim, not a property.",
    )

    def build(self, dt_s: float) -> DockAssembly:
        return DockAssembly(DockGeometry(), dt_s=dt_s)


BASELINE = BaselineSpec()


def _optional(module_name: str, attribute: str = "SPEC"):
    """Import a candidate if it exists, so the registry degrades gracefully."""

    try:
        module = __import__(f"aiur.sim.{module_name}", fromlist=[attribute])
    except ImportError:
        return None
    return getattr(module, attribute, None)


#: Every candidate under evaluation.  Alternatives are optional imports so
#: the study still runs — reporting exactly which candidates were present —
#: rather than failing wholesale because one module is missing.
CANDIDATES: tuple = tuple(
    spec
    for spec in (
        BASELINE,
        _optional("mech_iris"),
        _optional("mech_vgroove"),
        _optional("mech_passive"),
        _optional("mech_deepcup"),
    )
    if spec is not None
)
