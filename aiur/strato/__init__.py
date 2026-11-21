"""STRATO: the stratospheric article of the Aiur carrier programme.

CARRIER-P0 answers one question indoors: can a buoyant carrier recover an
aircraft.  This package answers the next one on paper before any film is cut:
what is the smallest, cheapest powered airship that reaches the stratosphere,
flies there under control, and can be built in quantity.

Everything here is a model.  It is stdlib-only and deterministic so it runs in
the same dependency-free CI as the P0 twin, and every coefficient carries its
provenance: ``[physics]`` (a law or standard), ``[cited]`` (a published
figure, see docs/strato/references.md), or ``[estimate]`` (an engineering
number that a bench or flight measurement must replace).

Modules, in the order a design flows through them:

* ``atmosphere`` — 1976 standard atmosphere, wind climatology, gust model;
* ``gas`` / ``materials`` — lift gases and envelope films;
* ``hull`` — body-of-revolution geometry, added mass, aerodynamic derivatives;
* ``thermal`` — film/gas radiative balance (superheat, supercooling);
* ``propulsion`` / ``energy`` — propeller, motor, solar, cold battery;
* ``sizing`` — the mass/energy closure that turns a mission into a vehicle;
* ``ascent`` — launch-to-float trajectory with venting, ballast and drift;
* ``flight6dof`` + ``guidance`` — rigid-body flight with added mass, and the
  station-keeping law the ROS 2 stack runs unchanged;
* ``link`` — radio link budgets from float altitude;
* ``harness`` — the avionics netlist checker;
* ``cost`` — unit cost and the production learning curve;
* ``campaign`` — Monte Carlo over winds, tolerances and failures.
"""
