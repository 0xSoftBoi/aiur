"""Executable engineering checks for CARRIER-P0.

The model intentionally separates theoretical buoyancy from the vendor-rated
usable payload. Flight hardware is budgeted against the rated payload.

The reference article is the smallest catalog airship that closes the
two-aircraft budget under an explicit reserve policy; ``aiur.envelope`` holds
the catalog, the reserve rule, and the physics, and ``selected_article``
re-derives the choice from the live budget so a budget change that outgrows
the vehicle fails a test instead of being discovered on a scale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Iterable

from .envelope import (
    P0_ARTICLE,
    RC_ZEPPELIN_INDOOR,
    ReservePolicy,
    VendorArticle,
    select_article,
)

SEA_LEVEL_AIR_DENSITY_KG_M3 = 1.225
HELIUM_DENSITY_KG_M3 = 0.164


@dataclass(frozen=True)
class CarrierSpec:
    """Reference carrier values for the first flight article.

    Defaults are the vendor figures for ``aiur.envelope.P0_ARTICLE``.
    """

    envelope_length_m: float = P0_ARTICLE.length_m
    envelope_volume_m3: float = P0_ARTICLE.helium_volume_m3
    rated_payload_kg: float = P0_ARTICLE.rated_payload_kg


@dataclass(frozen=True)
class PayloadItem:
    """One carried item in the P0 mass budget."""

    name: str
    mass_kg_each: float
    quantity: int = 1

    @property
    def total_mass_kg(self) -> float:
        if self.mass_kg_each < 0:
            raise ValueError("mass must be non-negative")
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")
        return self.mass_kg_each * self.quantity


@dataclass(frozen=True)
class DockEnvelope:
    """Geometric/kinematic limits for the terminal docking attempt."""

    capture_radius_m: float = 0.090
    max_closing_speed_m_s: float = 0.20

    def can_attempt_capture(
        self,
        lateral_x_m: float,
        lateral_y_m: float,
        closing_speed_m_s: float,
    ) -> bool:
        """Return True when the terminal state is inside the P0 capture envelope."""

        if closing_speed_m_s < 0:
            raise ValueError("closing speed must be non-negative")

        lateral_error = math.hypot(lateral_x_m, lateral_y_m)
        return (
            lateral_error <= self.capture_radius_m
            and closing_speed_m_s <= self.max_closing_speed_m_s
        )


def gross_static_lift_kg(
    volume_m3: float,
    *,
    air_density_kg_m3: float = SEA_LEVEL_AIR_DENSITY_KG_M3,
    lifting_gas_density_kg_m3: float = HELIUM_DENSITY_KG_M3,
) -> float:
    """Return ideal static mass lift before envelope/structure/propulsion.

    This is a physics sanity check, not the usable payload rating.
    """

    if volume_m3 < 0:
        raise ValueError("volume must be non-negative")
    if air_density_kg_m3 <= lifting_gas_density_kg_m3:
        raise ValueError("lifting gas must be less dense than ambient air")

    return volume_m3 * (air_density_kg_m3 - lifting_gas_density_kg_m3)


def payload_mass_kg(items: Iterable[PayloadItem]) -> float:
    return sum(item.total_mass_kg for item in items)


def payload_margin_kg(
    carrier: CarrierSpec,
    items: Iterable[PayloadItem],
) -> float:
    """Return rated payload remaining after the provided carried items."""

    return carrier.rated_payload_kg - payload_mass_kg(items)


def baseline_p0_budget() -> tuple[PayloadItem, ...]:
    """Baseline carried mass allocation.

    Published masses:
      * Crazyflie 2.1 Brushless with guards: 37 g each.
      * Lighthouse deck: 2.7 g each.

    Dock, probe, carrier-localization, and wiring figures are engineering allocations.
    """

    return (
        PayloadItem("Crazyflie 2.1 Brushless + guards", 0.037, 2),
        PayloadItem("Lighthouse positioning deck", 0.0027, 2),
        PayloadItem("drone-side capture probe allocation", 0.008, 2),
        PayloadItem("active recovery dock allocation", 0.180),
        PayloadItem("carrier localization + telemetry allocation", 0.050),
        PayloadItem("wiring + mounting reserve", 0.100),
    )


def aircraft_dead_weight_step_kg(
    items: Iterable[PayloadItem] | None = None,
) -> float:
    """Mass of one aircraft as flown: the dead-weight step the carrier sees
    when one aircraft is released or captured.

    Everything in the budget that is carried per aircraft (quantity 2 on the
    two-aircraft baseline) counts; the carrier-side items do not.
    """

    if items is None:
        items = baseline_p0_budget()
    per_aircraft = [item for item in items if item.quantity == 2]
    return sum(item.mass_kg_each for item in per_aircraft)


def reserve_policy(items: Iterable[PayloadItem] | None = None) -> ReservePolicy:
    """The P0 reserve rule: 10% of the rating, and never less than one
    aircraft's dead-weight step, so the vehicle can be trimmed through a
    complete release/recovery cycle on ballast alone."""

    return ReservePolicy(fraction_of_rating=0.10,
                         floor_kg=aircraft_dead_weight_step_kg(items))


def selected_article(
    items: Iterable[PayloadItem] | None = None,
    *,
    conservative: bool = False,
) -> VendorArticle | None:
    """Smallest catalog article that closes the budget under the reserve rule.

    ``conservative`` selects against the lowest payload figure the vendor
    quotes.  P0 procurement must obtain the rating in writing for the
    delivered article; until then the two answers bracket the decision.
    """

    if items is None:
        items = baseline_p0_budget()
    items = tuple(items)
    return select_article(
        payload_mass_kg(items), reserve_policy(items), RC_ZEPPELIN_INDOOR,
        conservative=conservative,
    )


def _summary() -> dict[str, object]:
    carrier = CarrierSpec()
    items = baseline_p0_budget()
    dock = DockEnvelope()
    policy = reserve_policy(items)
    chosen = selected_article(items)
    fallback = selected_article(items, conservative=True)
    return {
        "carrier": asdict(carrier),
        "article": P0_ARTICLE.model,
        "ideal_gross_static_lift_kg": round(
            gross_static_lift_kg(carrier.envelope_volume_m3), 4
        ),
        "baseline_payload_mass_kg": round(payload_mass_kg(items), 4),
        "rated_payload_margin_kg": round(payload_margin_kg(carrier, items), 4),
        "reserve_policy": asdict(policy),
        "required_reserve_kg": round(policy.required_reserve_kg(carrier.rated_payload_kg), 4),
        "reserve_closes": policy.closes(carrier.rated_payload_kg, payload_mass_kg(items)),
        "smallest_article_vendor_high_figure": chosen.model if chosen else None,
        "smallest_article_vendor_low_figure": fallback.model if fallback else None,
        "dock": asdict(dock),
        "items": [
            {
                **asdict(item),
                "total_mass_kg": round(item.total_mass_kg, 4),
            }
            for item in items
        ],
    }


if __name__ == "__main__":
    print(json.dumps(_summary(), indent=2))
