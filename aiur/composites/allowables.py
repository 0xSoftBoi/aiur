"""Material allowables: turning coupon data into a number a design may use.

A lamina strength from a handbook is a *typical* value — the middle of a
distribution whose width nobody has told you.  Designing to it means half of
all coupons would fail below the design load.  A structural allowable is a
statistical lower bound on that distribution, computed from this program's
own coupons, at a stated confidence and population fraction:

``B-basis``
    The value below which no more than 10 % of the population is expected to
    fall, with 95 % confidence.  The normal allowable for redundant
    structure, and what almost every composite part is designed to.
``A-basis``
    The 1 % / 95 % value.  Reserved for single-load-path structure whose
    failure is catastrophic — in this program, only the keeper tine's
    retention path is a candidate.

The k-factors are one-sided tolerance limit factors for a normal
distribution.  Exact values are non-central t quantiles; the standard
closed form used here sits about 1.5 % below the published exact factors at
n = 10, closing to 0.2 % by n = 100.  Being below the exact factor is
*non-conservative* — it returns a slightly higher allowable — so the
direction is stated rather than left for a reader to work out.  At a
coefficient of variation of 5 % it moves the allowable by under 0.2 %, which
is an order of magnitude inside the scatter of the data being reduced; if
this program ever computes an allowable that a part depends on, it should
substitute the published table value at that sample size.

The point of this module is not the arithmetic — it is the **cost of an
allowable**, made explicit before the program commits to it.  Reaching a
B-basis value costs coupons, and coupon count climbs steeply as scatter
grows: the same requirement that needs 6 coupons at 4 % coefficient of
variation needs 30 at 12 %.  That is the real argument for process control.
Scatter is not a property of the material; it is a property of the shop, and
every void, every out-time excursion and every hand-cut ply widens the
distribution that the allowable is then computed from the bottom of.

The program currently holds **no** measured allowables.  Everything in
``materials`` is handbook-representative, every schedule is therefore a
design study, and :func:`program_status` says so in one line rather than
letting a reader infer otherwise from the precision of the outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Sequence

#: Environmental knockdowns applied to a room-temperature-dry allowable.
#: Matrix-dominated properties lose most; fibre-dominated tension loses
#: little.  Engineering targets until this program runs its own hot/wet
#: coupons, and deliberately conservative because a knockdown that turns out
#: to be too small is discovered by a part failing.
ENVIRONMENTAL_KNOCKDOWNS: dict[str, float] = {
    "rtd": 1.00,
    "etw_fibre_dominated": 0.90,
    "etw_matrix_dominated": 0.65,
    "cold_dry": 0.95,
}

#: Additional knockdown for barely visible impact damage on a thin skin.
#: Engineering target; the compression-after-impact coupon replaces it.
BVID_KNOCKDOWN = 0.65

#: Coefficient of variation above which a data set is treated as being
#: driven by the process rather than by the material.
CV_PROCESS_LIMIT = 0.10


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("no values")
    return sum(values) / len(values)


def standard_deviation(values: Sequence[float]) -> float:
    """Sample standard deviation, Bessel-corrected."""

    if len(values) < 2:
        raise ValueError("standard deviation needs at least two values")
    average = mean(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / (len(values) - 1))


def coefficient_of_variation(values: Sequence[float]) -> float:
    average = mean(values)
    if average <= 0:
        raise ValueError("coefficient of variation needs a positive mean")
    return standard_deviation(values) / average


#: Standard normal deviate for the population fraction each basis covers.
_Z_B_BASIS = 1.281552  # 90 % of the population above
_Z_A_BASIS = 2.326348  # 99 % of the population above
#: Standard normal deviate for the 95 % confidence level.
_Z_CONFIDENCE = 1.644854

#: Smallest sample the tolerance-factor expression is defined for.  Below
#: this the confidence correction term goes negative and the factor is
#: meaningless — which is the arithmetic agreeing that three specimens
#: cannot support a statement about 90 % of a population.
MIN_SPECIMENS_FOR_FACTOR = 4


def tolerance_factor(n: int, z_population: float) -> float:
    """One-sided normal tolerance factor at 95 % confidence.

    The exact factor is a non-central t quantile.  This is the standard
    closed-form approximation (Natrella), which agrees with the exact tables
    to a few tenths of a percent over every sample size a coupon programme
    will use — well inside the scatter of the data it is applied to:

        k = (z_p + sqrt(z_p^2 - a b)) / a
        a = 1 - z_c^2 / (2 (n - 1))
        b = z_p^2 - z_c^2 / n
    """

    if n < MIN_SPECIMENS_FOR_FACTOR:
        raise ValueError(
            f"a tolerance factor needs at least {MIN_SPECIMENS_FOR_FACTOR} specimens"
        )
    a = 1.0 - _Z_CONFIDENCE ** 2 / (2.0 * (n - 1))
    b = z_population ** 2 - _Z_CONFIDENCE ** 2 / n
    if a <= 0.0:  # pragma: no cover - guarded by MIN_SPECIMENS_FOR_FACTOR
        raise ValueError("sample too small for a tolerance factor")
    return (z_population + math.sqrt(z_population ** 2 - a * b)) / a


def b_basis_factor(n: int) -> float:
    """One-sided 90 % / 95 % tolerance factor for a normal distribution."""

    return tolerance_factor(n, _Z_B_BASIS)


def a_basis_factor(n: int) -> float:
    """One-sided 99 % / 95 % tolerance factor for a normal distribution."""

    return tolerance_factor(n, _Z_A_BASIS)


def basis_value(values: Sequence[float], *, basis: str = "B") -> float:
    """Compute a basis value from a coupon set, assuming normality.

    Normality is an *assumption*, not a fact, and for strength data with a
    weak-link failure mode a Weibull fit is often the better model.  The
    assumption is stated rather than tested here because testing it needs
    more specimens than this program will have for some time; when the data
    exists, an Anderson-Darling check belongs in front of this function.
    """

    factor = b_basis_factor(len(values)) if basis.upper() == "B" else a_basis_factor(len(values))
    return mean(values) - factor * standard_deviation(values)


def coupons_required(
    *,
    coefficient_of_variation: float,
    max_knockdown_fraction: float = 0.20,
    basis: str = "B",
    limit: int = 200,
) -> int:
    """Fewest coupons whose basis value stays within a knockdown of the mean.

    Answers the question a program actually asks — "how many coupons do I
    have to cut?" — and shows how sharply the answer depends on scatter.
    """

    if not 0.0 < max_knockdown_fraction < 1.0:
        raise ValueError("knockdown fraction must be in (0, 1)")
    for n in range(MIN_SPECIMENS_FOR_FACTOR, limit + 1):
        factor = b_basis_factor(n) if basis.upper() == "B" else a_basis_factor(n)
        if factor * coefficient_of_variation <= max_knockdown_fraction:
            return n
    return limit


@dataclass(frozen=True)
class CouponSet:
    """One property, one environment, one material, several specimens."""

    material: str
    property_name: str
    environment: str
    values_mpa: tuple[float, ...]
    #: Distinct material lots represented. A basis value computed from a
    #: single lot describes that lot, not the material, whatever the
    #: arithmetic says.
    lots: int = 1
    note: str = ""


@dataclass(frozen=True)
class AllowableResult:
    material: str
    property_name: str
    environment: str
    specimens: int
    lots: int
    mean_mpa: float
    standard_deviation_mpa: float
    coefficient_of_variation: float
    b_basis_mpa: float
    a_basis_mpa: float
    knockdown_applied: float
    design_allowable_mpa: float
    #: Whether this may be quoted as a statistical basis value at all.
    qualifies_as_basis_value: bool
    warnings: tuple[str, ...]


#: Minimum specimens and lots for a value to be called a basis value.
MIN_SPECIMENS_FOR_BASIS = 6
MIN_LOTS_FOR_BASIS = 3


def evaluate_coupon_set(coupons: CouponSet) -> AllowableResult:
    values = coupons.values_mpa
    warnings: list[str] = []
    if len(values) < MIN_SPECIMENS_FOR_BASIS:
        warnings.append(
            f"{len(values)} specimens; a basis value needs at least {MIN_SPECIMENS_FOR_BASIS}"
        )
    if coupons.lots < MIN_LOTS_FOR_BASIS:
        warnings.append(
            f"{coupons.lots} lot(s); a basis value needs at least {MIN_LOTS_FOR_BASIS} "
            "so that lot-to-lot variation is inside the distribution"
        )
    cv = coefficient_of_variation(values)
    if cv > CV_PROCESS_LIMIT:
        warnings.append(
            f"coefficient of variation {cv:.3f} exceeds {CV_PROCESS_LIMIT:.2f}; the "
            "scatter is process-driven and the process should be fixed before the "
            "allowable is lowered to accommodate it"
        )
    knockdown = ENVIRONMENTAL_KNOCKDOWNS.get(coupons.environment, 1.0)
    if coupons.environment not in ENVIRONMENTAL_KNOCKDOWNS:
        warnings.append(f"unknown environment {coupons.environment!r}; no knockdown applied")

    b_value = basis_value(values, basis="B")
    a_value = basis_value(values, basis="A")
    return AllowableResult(
        material=coupons.material,
        property_name=coupons.property_name,
        environment=coupons.environment,
        specimens=len(values),
        lots=coupons.lots,
        mean_mpa=round(mean(values), 2),
        standard_deviation_mpa=round(standard_deviation(values), 3),
        coefficient_of_variation=round(cv, 4),
        b_basis_mpa=round(b_value, 2),
        a_basis_mpa=round(a_value, 2),
        knockdown_applied=knockdown,
        design_allowable_mpa=round(max(b_value, 0.0) * knockdown, 2),
        qualifies_as_basis_value=(
            len(values) >= MIN_SPECIMENS_FOR_BASIS and coupons.lots >= MIN_LOTS_FOR_BASIS
        ),
        warnings=tuple(warnings),
    )


#: The coupon campaign this program has to run before any schedule can be
#: called a design rather than a design study.  Test methods are named so the
#: plan can be quoted to a lab as-is.
@dataclass(frozen=True)
class PlannedCoupon:
    test_id: str
    method: str
    property_name: str
    material: str
    environment: str
    specimens: int
    purpose: str


COUPON_PLAN: tuple[PlannedCoupon, ...] = (
    PlannedCoupon("CP-01", "ASTM D3039", "tension 0", "PW-C-193", "rtd", 6,
                  "fibre-dominated tension modulus and strength; anchors the CLT model"),
    PlannedCoupon("CP-02", "ASTM D6641", "compression 0", "PW-C-193", "rtd", 6,
                  "compression governs thin skins after impact; never assume it from tension"),
    PlannedCoupon("CP-03", "ASTM D3518", "in-plane shear", "PW-C-193", "rtd", 6,
                  "+-45 tension for G12 and shear strength; the critical mode in every "
                  "45-degree skin in this program"),
    PlannedCoupon("CP-04", "ASTM D2344", "short-beam strength", "PW-C-193", "rtd", 10,
                  "interlaminar strength is the property porosity attacks; this is the "
                  "coupon that makes the void limit mean something"),
    PlannedCoupon("CP-05", "ASTM D3039", "tension 0", "PW-C-80", "rtd", 6,
                  "the thin-ply skin material; its in-situ transverse strength is "
                  "expected to exceed the thick-ply value and the model does not predict that"),
    PlannedCoupon("CP-06", "ASTM D7137", "compression after impact", "PW-C-193", "rtd", 6,
                  "sets the BVID knockdown that is currently an engineering target"),
    PlannedCoupon("CP-07", "ASTM D2344", "short-beam strength", "PW-C-193", "etw_matrix_dominated", 6,
                  "hot/wet knockdown on the matrix-dominated property; the assumed 0.65 "
                  "is the least defensible number in this package"),
    PlannedCoupon("CP-08", "ASTM D5528", "mode I interlaminar toughness", "PW-C-193", "rtd", 6,
                  "delamination resistance for the bonded joints and the tine root"),
    # The bonded joint had no coupon at all until PS-400 was written, which
    # is how a whole failure mode goes unqualified: every other coupon here
    # characterises a laminate, and a bond is not a laminate.
    PlannedCoupon("CP-09", "ASTM D5868", "adhesive lap shear", "PW-C-193", "rtd", 12,
                  "the adhesive shear strength every bonded joint is sized against. "
                  "Twelve specimens rather than six because surface preparation is a "
                  "factor in this test, not a fixed condition: half peel-ply, half "
                  "abraded. The question is not how strong the adhesive is, it is how "
                  "strong it is on a surface this shop prepared"),
    PlannedCoupon("CP-10", "ASTM D3167", "floating roller peel", "PW-C-193", "rtd", 6,
                  "peel is what actually fails composite bonded joints, and the "
                  "shear-lag model used to size them does not predict it"),
)


def program_status() -> dict[str, object]:
    """One-line honest statement of where the allowables stand."""

    return {
        "measured_allowables": 0,
        "planned_coupons": sum(coupon.specimens for coupon in COUPON_PLAN),
        "statement": (
            "This program holds no measured allowables. Every laminate schedule is "
            "sized against handbook-representative lamina values and is therefore a "
            "design study, not a design. The coupon plan below is what converts it."
        ),
    }


def snapshot() -> dict[str, object]:
    return {
        "status": program_status(),
        "basis_definitions": {
            "B": "90 % of the population exceeds this value, at 95 % confidence",
            "A": "99 % of the population exceeds this value, at 95 % confidence",
        },
        "minimum_specimens_for_basis": MIN_SPECIMENS_FOR_BASIS,
        "minimum_lots_for_basis": MIN_LOTS_FOR_BASIS,
        "environmental_knockdowns": ENVIRONMENTAL_KNOCKDOWNS,
        "bvid_knockdown": BVID_KNOCKDOWN,
        "tolerance_factors": {
            str(n): {"b": round(b_basis_factor(n), 4), "a": round(a_basis_factor(n), 4)}
            for n in (4, 6, 10, 20, 30, 50, 100)
        },
        # The cost of scatter, in the only currency a shop cares about.
        "coupons_required_for_20pc_knockdown": {
            f"cv_{int(cv * 100):02d}pc": {
                "b_basis": coupons_required(coefficient_of_variation=cv),
                "a_basis": coupons_required(coefficient_of_variation=cv, basis="A"),
            }
            for cv in (0.04, 0.06, 0.08, 0.10, 0.12)
        },
        "coupon_plan": [asdict(coupon) for coupon in COUPON_PLAN],
    }


def main() -> int:
    print(json.dumps(snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
