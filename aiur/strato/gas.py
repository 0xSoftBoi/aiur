"""Lift gases.

Hydrogen and helium are treated as ideal gases; at stratospheric pressures the
error is far below every other uncertainty in the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .atmosphere import Air, M_AIR, R_UNIVERSAL


@dataclass(frozen=True)
class LiftGas:
    name: str
    molar_mass_kg_mol: float
    cp_j_kgk: float
    #: Thermal conductivity near 220 K, W/(m K) [cited: NIST webbook].
    conductivity_w_mk: float
    #: Delivered price per normal cubic metre, USD [estimate, see references].
    usd_per_nm3: float
    #: Volume purity as filled.  The impurity is treated as air.
    purity: float = 0.995
    flammable: bool = False

    @property
    def effective_molar_mass(self) -> float:
        return self.purity * self.molar_mass_kg_mol + (1.0 - self.purity) * M_AIR

    @property
    def gas_constant(self) -> float:
        return R_UNIVERSAL / self.effective_molar_mass

    def density(self, pressure_pa: float, temperature_k: float) -> float:
        return pressure_pa / (self.gas_constant * temperature_k)

    def lift_per_m3(self, air: Air, superpressure_pa: float = 0.0,
                    supertemperature_k: float = 0.0) -> float:
        """Net lift (kg of supported mass) per cubic metre of gas.

        ``supertemperature_k`` is gas minus ambient; a sun-warmed gas is less
        dense and lifts more, a night-cooled one lifts less.
        """

        rho_gas = self.density(air.pressure_pa + superpressure_pa,
                               air.temperature_k + supertemperature_k)
        return air.density_kg_m3 - rho_gas

    def lift_per_kg_gas(self, air: Air, supertemperature_k: float = 0.0) -> float:
        """Supported mass per kilogram of gas when the cell is *not* full.

        Independent of altitude for a slack cell: this is why a zero-pressure
        balloon rises at constant lift until the envelope fills.
        """

        ratio = (M_AIR / self.effective_molar_mass) * (
            (air.temperature_k + supertemperature_k) / air.temperature_k)
        return ratio - 1.0


#: Prices are per normal cubic metre delivered in cylinders or bundles, 2025-26.
#: Helium is volatile and supply-interrupted; hydrogen is an industrial
#: commodity that can also be made on site.  See references, "lift gas".
HYDROGEN = LiftGas("hydrogen", 0.00201588, 14_300.0, 0.135, 1.6, purity=0.995, flammable=True)
HELIUM = LiftGas("helium", 0.004002602, 5_193.0, 0.118, 28.0, purity=0.99)

GASES = {"hydrogen": HYDROGEN, "helium": HELIUM}
