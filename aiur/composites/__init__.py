"""Composite structures engineering for CARRIER-P0.

The dock's flight structure is thin, ultra-light, deployable, and made of
prepreg carbon.  That puts a composites discipline in the middle of the
program: laminate design, cure process development, tooling, manufacturing
control, and the statistics that decide when any of it may be called
evidence.  This package is that discipline in executable form, on the same
terms as the rest of ``aiur`` — dependency-free, run in CI, and refusing to
state a result more precisely than its basis supports.

The modules, in the order the work happens:

:mod:`aiur.composites.materials`
    Lamina and resin properties, each carrying the basis it came from.
:mod:`aiur.composites.clt`
    Classical laminate theory: ABD stiffness, thermal and cure-shrinkage
    response, ply-by-ply stress, and failure criteria.
:mod:`aiur.composites.schedules`
    The four part laminates, their load cases, and the design rules they are
    checked against.
:mod:`aiur.composites.flatpattern`
    Flat-pattern development, the fibre-angle drift a cone imposes, and the
    rotational stiffness envelope that decides whether it matters.
:mod:`aiur.composites.cure`
    Cure kinetics, vitrification, exotherm, viscosity, and the acceptance
    criteria a cure cycle has to pass.
:mod:`aiur.composites.bonding`
    Bonded joints: shear-lag sizing, why overlap length saturates, and the
    two routes by which an unverifiable bond can be qualified.
:mod:`aiur.composites.springin`
    Corner distortion prediction and the tool compensation loop.
:mod:`aiur.composites.tooling`
    Tool material trade and thermal-expansion compensation.
:mod:`aiur.composites.process`
    Fibre volume fraction, void content, debulk schedule, panel acceptance.
:mod:`aiur.composites.traveler`
    Travelers, hold points, prepreg out-time, and computed nonconformances.
:mod:`aiur.composites.allowables`
    Basis values, the coupon plan, and the cost of scatter.
:mod:`aiur.composites.spc`
    Process capability, control charts, and rolled throughput yield.
:mod:`aiur.composites.doe`
    The experiments that replace this package's engineering targets.

Run the whole discipline as one gate::

    python -m aiur.composites

Every number here is one of the four things the program's design rule
allows: a measured requirement, an executable model, a cited specification,
or an explicitly labeled engineering target.  Today the composites work is
almost entirely the third and fourth of those, and
``aiur.composites.allowables.program_status`` says so in one sentence rather
than leaving a reader to infer it from four significant figures.
"""

from .clt import Laminate, Ply
from .materials import Basis, MATERIALS, PlyMaterial
from .schedules import SCHEDULES, LaminateSchedule, schedule

__all__ = [
    "Basis",
    "Laminate",
    "LaminateSchedule",
    "MATERIALS",
    "PlyMaterial",
    "Ply",
    "SCHEDULES",
    "schedule",
]
