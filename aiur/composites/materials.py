"""Lamina property registry for the CARRIER-P0 composite structures.

Every number in a composites program eventually decides a thickness, and a
thickness decides whether the article flies.  The failure mode this module
exists to prevent is the one every composites shop has lived through: a
handbook lamina value gets typed into a stiffness calculation, the laminate
gets cut to that thickness, and nobody can say afterwards whether the value
came from a vendor datasheet, a textbook table, or somebody's memory of a
different resin system.

So each property set carries a :class:`Basis` — where the number came from —
and the registry refuses to answer a question its basis cannot support.
:func:`allowable_grade` is the gate: a laminate sized against
``HANDBOOK_REPRESENTATIVE`` data is a *design study*, and only a laminate
sized against ``MEASURED`` lot data backed by coupons is a *design*.  The
program is presently at design-study grade for every material here, and says
so rather than implying otherwise by quoting four significant figures.

Units are held in the structural set used throughout ``aiur.composites``:

    stress, modulus     MPa (N/mm^2)
    length, thickness   mm
    temperature         degC unless a symbol says K
    density             g/cm^3
    areal weight        g/m^2

Two idealisations are baked in and are worth stating where they can be read
rather than in a document nobody opens:

* A woven ply is **smeared** — treated as a homogeneous orthotropic layer with
  ``E1 == E2``.  Classical laminate theory has no representation of crimp, and
  a weave's real knockdown relative to two crossed unidirectional plies is a
  coupon result, not a calculation.  The smeared idealisation is standard,
  slightly optimistic in strength, and adequate for sizing.
* Cured ply thickness (CPT) is a *process* output, not a material constant.
  The CPT here is the value the cure spec is written to hold; a laminate that
  measures thicker has a lower fibre volume fraction and is a nonconformance,
  which is exactly what ``aiur.composites.process`` computes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping


class Basis(str, Enum):
    """Where a property value came from.  Ordered weakest to strongest."""

    #: Textbook or industry-representative value for a material *class*.
    #: Adequate for trade studies and sizing; never adequate for an allowable.
    HANDBOOK_REPRESENTATIVE = "handbook_representative"
    #: Published by the material supplier for this product, typical (not
    #: statistically reduced) values at room-temperature dry.
    VENDOR_TYPICAL = "vendor_typical"
    #: This program's own coupon data, reduced but not yet to a statistical
    #: basis (too few panels, or a single lot).
    MEASURED_TYPICAL = "measured_typical"
    #: Statistically reduced from this program's coupons across lots — the
    #: only basis that may be used as a structural allowable.
    MEASURED_BASIS_VALUE = "measured_basis_value"


#: Bases that may be used to size flight structure with a knockdown, versus
#: bases that may only be used to explore a design space.
DESIGN_GRADE_BASES: frozenset[Basis] = frozenset(
    {Basis.MEASURED_TYPICAL, Basis.MEASURED_BASIS_VALUE}
)


class Form(str, Enum):
    UNIDIRECTIONAL = "unidirectional"
    PLAIN_WEAVE = "plain_weave"
    TWILL_2X2 = "twill_2x2"


@dataclass(frozen=True)
class CureChemistry:
    """Kinetics and viscosity parameters for one resin system.

    The kinetic form is the diffusion-limited autocatalytic model used for
    epoxy prepregs (Kamal-Sourour with a Fournier/Hubert diffusion factor):

        da/dt = A exp(-Ea/RT) a^m (1-a)^n / (1 + exp(C (a - (aC0 + aCT T))))

    with ``T`` in kelvin.  The diffusion denominator is what makes the model
    predict **vitrification** — the reaction stalling when the glass
    transition of the partially cured resin climbs past the cure temperature —
    and vitrification, not gelation, is what leaves an undercured part that
    passes a visual inspection and fails a hot/wet coupon.

    Glass transition follows DiBenedetto:

        (Tg - Tg0) / (Tginf - Tg0) = lam a / (1 - (1 - lam) a)

    Viscosity follows Castro-Macosko, which is what sizes the pressure
    application window: apply full pressure before minimum viscosity and the
    resin bleeds out; apply it after gelation and the voids stay.
    """

    name: str
    basis: Basis
    #: Pre-exponential factor, 1/s.
    kinetic_a_per_s: float
    #: Activation energy, J/mol.
    kinetic_ea_j_mol: float
    #: Autocatalytic and nth-order exponents.
    kinetic_m: float
    kinetic_n: float
    #: Diffusion factor constants (dimensionless, dimensionless, 1/K).
    diffusion_c: float
    diffusion_alpha_c0: float
    diffusion_alpha_ct_per_k: float
    #: Seed conversion.  The autocatalytic term is zero at a == 0, so the
    #: model needs a non-zero start; prepreg has advanced this far in
    #: manufacture and storage anyway.
    initial_conversion: float
    #: Degree of cure at gelation — resin stops flowing, voids stop moving.
    gel_conversion: float
    #: DiBenedetto constants, degC and dimensionless.
    tg_uncured_c: float
    tg_full_c: float
    tg_lambda: float
    #: Castro-Macosko viscosity constants: Pa.s, J/mol, dimensionless.
    viscosity_mu1_pa_s: float
    viscosity_u_j_mol: float
    viscosity_a: float
    viscosity_b: float
    #: Total exotherm, J/g — sizes the thermal spike in a thick laminate.
    enthalpy_j_g: float

    def __post_init__(self) -> None:
        if not 0.0 < self.initial_conversion < 1.0:
            raise ValueError("initial conversion must be in (0, 1)")
        if not 0.0 < self.gel_conversion < 1.0:
            raise ValueError("gel conversion must be in (0, 1)")
        if self.tg_full_c <= self.tg_uncured_c:
            raise ValueError("fully cured Tg must exceed uncured Tg")
        if not 0.0 < self.tg_lambda <= 1.0:
            raise ValueError("DiBenedetto lambda must be in (0, 1]")


@dataclass(frozen=True)
class PlyMaterial:
    """One cured lamina, smeared to a homogeneous orthotropic layer.

    Strengths are stored as positive magnitudes, compression included.
    """

    name: str
    form: Form
    basis: Basis
    #: In-plane elastic constants, MPa except the dimensionless Poisson ratio.
    e1_mpa: float
    e2_mpa: float
    g12_mpa: float
    nu12: float
    #: Coefficients of thermal expansion, 1/K.  Fibre-direction CTE of a
    #: carbon lamina is negative: the fibre shrinks on heating.
    alpha1_per_k: float
    alpha2_per_k: float
    #: Through-thickness CTE, 1/K.  Resin-dominated in every laminate here,
    #: and an order of magnitude larger than the in-plane values — which is
    #: precisely why a cured corner does not come off the tool at the angle
    #: it was moulded at.  Unused by classical laminate theory; the spring-in
    #: model is built on the mismatch between this and the in-plane CTE.
    alpha3_per_k: float
    #: Cure shrinkage, dimensionless strain (positive = contraction).  The
    #: transverse figure carries essentially all of the resin's chemical
    #: shrinkage; the fibre direction is restrained by the fibre.
    shrink1: float
    shrink2: float
    #: Through-thickness cure shrinkage, dimensionless. The second half of
    #: the spring-in driver, and the half that does not disappear when a
    #: part is cured at low temperature.
    shrink3: float
    #: Lamina strengths, MPa, positive magnitudes.
    xt_mpa: float
    xc_mpa: float
    yt_mpa: float
    yc_mpa: float
    s12_mpa: float
    #: Cured ply thickness the cure spec holds, mm.
    cured_ply_thickness_mm: float
    #: Fibre areal weight (g/m^2), cured lamina density (g/cm^3), and the
    #: nominal fibre volume fraction the CPT implies.
    fibre_areal_weight_gsm: float
    cured_density_g_cm3: float
    nominal_fibre_volume_fraction: float
    #: Constituent densities, g/cm^3 — needed for void content by ASTM D2734.
    fibre_density_g_cm3: float
    resin_density_g_cm3: float
    #: Resin system driving the cure cycle.
    chemistry: str
    #: Room-temperature-dry ultimate strain in the fibre direction, used by
    #: the stowage check for deployables.
    ultimate_strain_1: float
    note: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "e1_mpa",
            "e2_mpa",
            "g12_mpa",
            "xt_mpa",
            "xc_mpa",
            "yt_mpa",
            "yc_mpa",
            "s12_mpa",
            "cured_ply_thickness_mm",
            "fibre_areal_weight_gsm",
            "cured_density_g_cm3",
            "fibre_density_g_cm3",
            "resin_density_g_cm3",
            "ultimate_strain_1",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{self.name}: {field_name} must be positive")
        if not 0.0 < self.nu12 < 0.5:
            raise ValueError(f"{self.name}: nu12 outside physical range")
        if not 0.0 < self.nominal_fibre_volume_fraction < 1.0:
            raise ValueError(f"{self.name}: fibre volume fraction outside (0, 1)")
        # Maxwell-Betti reciprocity: nu21 = nu12 * E2 / E1 must stay below the
        # bound that keeps the reduced stiffness matrix positive definite.
        if self.nu12 * self.nu12 * self.e2_mpa / self.e1_mpa >= 1.0:
            raise ValueError(f"{self.name}: nu12*nu21 >= 1, stiffness not positive definite")
        if self.form is not Form.UNIDIRECTIONAL and self.e1_mpa != self.e2_mpa:
            raise ValueError(
                f"{self.name}: a smeared woven ply is modelled with E1 == E2; "
                "an unbalanced weave must be entered as two unidirectional plies"
            )

    @property
    def nu21(self) -> float:
        return self.nu12 * self.e2_mpa / self.e1_mpa

    @property
    def areal_mass_g_m2(self) -> float:
        """Cured areal mass of one ply, g/m^2 — fibre plus retained resin."""

        return self.cured_ply_thickness_mm * 1e-3 * self.cured_density_g_cm3 * 1e6

    @property
    def resin_mass_fraction(self) -> float:
        """Cured resin mass fraction implied by CPT and areal weight."""

        return 1.0 - self.fibre_areal_weight_gsm / self.areal_mass_g_m2

    def theoretical_density_g_cm3(self) -> float:
        """Void-free density from the constituent rule of mixtures.

        The difference between this and a measured density is the void
        content (ASTM D2734); see :mod:`aiur.composites.process`.
        """

        vf = self.nominal_fibre_volume_fraction
        return vf * self.fibre_density_g_cm3 + (1.0 - vf) * self.resin_density_g_cm3


#: 180 degC-cure toughened epoxy, representative of the aerospace prepreg
#: class (Hexcel 8552 and equivalents).  Kinetic, DiBenedetto and
#: Castro-Macosko constants are the widely published values for that class.
#: They are entered here as HANDBOOK_REPRESENTATIVE on purpose: this program
#: has not run a DSC on its own lot, and the cure spec says so.
EPOXY_180C = CureChemistry(
    name="epoxy-180C-toughened",
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    kinetic_a_per_s=1.53e5,
    kinetic_ea_j_mol=6.65e4,
    kinetic_m=0.813,
    kinetic_n=2.74,
    diffusion_c=43.1,
    diffusion_alpha_c0=-1.684,
    diffusion_alpha_ct_per_k=5.475e-3,
    initial_conversion=0.002,
    gel_conversion=0.47,
    tg_uncured_c=-1.5,
    tg_full_c=243.0,
    tg_lambda=0.435,
    viscosity_mu1_pa_s=3.45e-10,
    viscosity_u_j_mol=7.6534e4,
    viscosity_a=3.8,
    viscosity_b=2.5,
    enthalpy_j_g=540.0,
)

#: 120 degC-cure epoxy, the system a shop without an autoclave actually uses:
#: oven plus vacuum bag, lower exotherm, lower service temperature.  Constants
#: are the same functional forms with a faster, lower-energy reaction.
EPOXY_120C = CureChemistry(
    name="epoxy-120C-oven",
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    kinetic_a_per_s=4.2e4,
    kinetic_ea_j_mol=5.85e4,
    kinetic_m=0.75,
    kinetic_n=2.10,
    diffusion_c=40.0,
    diffusion_alpha_c0=-1.520,
    diffusion_alpha_ct_per_k=5.60e-3,
    initial_conversion=0.004,
    gel_conversion=0.50,
    tg_uncured_c=-8.0,
    tg_full_c=135.0,
    tg_lambda=0.46,
    viscosity_mu1_pa_s=6.1e-10,
    viscosity_u_j_mol=6.90e4,
    viscosity_a=3.6,
    viscosity_b=2.4,
    enthalpy_j_g=480.0,
)

CHEMISTRIES: Mapping[str, CureChemistry] = {
    chemistry.name: chemistry for chemistry in (EPOXY_180C, EPOXY_120C)
}


#: Thin plain-weave carbon, the workhorse skin ply for thin high-precision
#: parts: two fibre directions per ply keeps a three-ply laminate symmetric
#: and balanced, and 0.20 mm CPT keeps the funnel skin under its areal mass.
PW_CARBON_193 = PlyMaterial(
    name="PW-C-193",
    form=Form.PLAIN_WEAVE,
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    e1_mpa=62_000.0,
    e2_mpa=62_000.0,
    g12_mpa=4_200.0,
    nu12=0.045,
    alpha1_per_k=2.1e-6,
    alpha2_per_k=2.1e-6,
    alpha3_per_k=42.0e-6,
    shrink1=0.0005,
    shrink2=0.0030,
    shrink3=0.0055,
    xt_mpa=760.0,
    xc_mpa=620.0,
    yt_mpa=760.0,
    yc_mpa=620.0,
    s12_mpa=95.0,
    cured_ply_thickness_mm=0.199,
    fibre_areal_weight_gsm=193.0,
    cured_density_g_cm3=1.544,
    nominal_fibre_volume_fraction=0.55,
    fibre_density_g_cm3=1.76,
    resin_density_g_cm3=1.28,
    chemistry="epoxy-180C-toughened",
    ultimate_strain_1=0.0122,
    note="3k plain weave, smeared orthotropic idealisation",
)

#: 80 gsm spread-tow plain weave.  Halving the ply thickness is the single
#: highest-leverage move available to a thin-laminate programme: it doubles
#: the number of orientations available inside a fixed thickness, suppresses
#: transverse microcracking, and lets a two-ply deployable reach a stowage
#: radius a 0.20 mm ply cannot.
PW_CARBON_80 = PlyMaterial(
    name="PW-C-80",
    form=Form.PLAIN_WEAVE,
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    e1_mpa=64_000.0,
    e2_mpa=64_000.0,
    g12_mpa=4_300.0,
    nu12=0.043,
    alpha1_per_k=2.0e-6,
    alpha2_per_k=2.0e-6,
    alpha3_per_k=41.0e-6,
    shrink1=0.0005,
    shrink2=0.0030,
    shrink3=0.0055,
    xt_mpa=820.0,
    xc_mpa=640.0,
    yt_mpa=820.0,
    yc_mpa=640.0,
    s12_mpa=98.0,
    cured_ply_thickness_mm=0.080,
    fibre_areal_weight_gsm=80.0,
    cured_density_g_cm3=1.553,
    nominal_fibre_volume_fraction=0.568,
    fibre_density_g_cm3=1.76,
    resin_density_g_cm3=1.28,
    chemistry="epoxy-180C-toughened",
    ultimate_strain_1=0.0128,
    note="spread-tow thin ply; enables tight stowage radii",
)

#: Standard-modulus unidirectional tape, the reference for anything that has
#: to carry an axial load: the keel rail caps and the boom's longitudinal
#: plies.
UD_CARBON_IM = PlyMaterial(
    name="UD-C-IM",
    form=Form.UNIDIRECTIONAL,
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    e1_mpa=161_000.0,
    e2_mpa=11_400.0,
    g12_mpa=5_170.0,
    nu12=0.32,
    alpha1_per_k=-0.3e-6,
    alpha2_per_k=28.1e-6,
    alpha3_per_k=28.1e-6,
    shrink1=0.0004,
    shrink2=0.0055,
    shrink3=0.0055,
    xt_mpa=2_560.0,
    xc_mpa=1_590.0,
    yt_mpa=73.0,
    yc_mpa=185.0,
    s12_mpa=90.0,
    cured_ply_thickness_mm=0.140,
    fibre_areal_weight_gsm=145.0,
    cured_density_g_cm3=1.578,
    nominal_fibre_volume_fraction=0.58,
    fibre_density_g_cm3=1.78,
    resin_density_g_cm3=1.30,
    chemistry="epoxy-180C-toughened",
    ultimate_strain_1=0.0159,
    note="intermediate-modulus UD tape",
)

#: High-modulus unidirectional tape.  Buys stiffness per unit mass and a CTE
#: near zero, and pays for it in strain to failure — which is why it is
#: allowed in the keel and forbidden in anything that gets rolled up.
UD_CARBON_HM = PlyMaterial(
    name="UD-C-HM",
    form=Form.UNIDIRECTIONAL,
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    e1_mpa=300_000.0,
    e2_mpa=6_500.0,
    g12_mpa=4_500.0,
    nu12=0.30,
    alpha1_per_k=-1.1e-6,
    alpha2_per_k=32.0e-6,
    alpha3_per_k=32.0e-6,
    shrink1=0.0003,
    shrink2=0.0060,
    shrink3=0.0060,
    xt_mpa=1_600.0,
    xc_mpa=800.0,
    yt_mpa=30.0,
    yc_mpa=130.0,
    s12_mpa=60.0,
    cured_ply_thickness_mm=0.090,
    fibre_areal_weight_gsm=100.0,
    cured_density_g_cm3=1.645,
    nominal_fibre_volume_fraction=0.58,
    fibre_density_g_cm3=1.91,
    resin_density_g_cm3=1.28,
    chemistry="epoxy-180C-toughened",
    ultimate_strain_1=0.0053,
    note="high-modulus UD tape; low strain allowable, do not stow rolled",
)

#: Style-1080 glass plain weave.  Radio-transparent, high strain to failure,
#: and cheap: the dock's antenna window and the outer surface ply that keeps
#: a carbon skin from grounding an antenna or scuffing an aircraft.
PW_GLASS_1080 = PlyMaterial(
    name="PW-G-1080",
    form=Form.PLAIN_WEAVE,
    basis=Basis.HANDBOOK_REPRESENTATIVE,
    e1_mpa=24_500.0,
    e2_mpa=24_500.0,
    g12_mpa=3_900.0,
    nu12=0.13,
    alpha1_per_k=6.5e-6,
    alpha2_per_k=6.5e-6,
    alpha3_per_k=38.0e-6,
    shrink1=0.0008,
    shrink2=0.0030,
    shrink3=0.0050,
    xt_mpa=420.0,
    xc_mpa=380.0,
    yt_mpa=420.0,
    yc_mpa=380.0,
    s12_mpa=70.0,
    cured_ply_thickness_mm=0.047,
    fibre_areal_weight_gsm=48.0,
    cured_density_g_cm3=1.784,
    nominal_fibre_volume_fraction=0.40,
    fibre_density_g_cm3=2.54,
    resin_density_g_cm3=1.28,
    chemistry="epoxy-180C-toughened",
    ultimate_strain_1=0.0175,
    note="E-glass 1080 weave; RF window and abrasion ply",
)

MATERIALS: Mapping[str, PlyMaterial] = {
    material.name: material
    for material in (
        PW_CARBON_193,
        PW_CARBON_80,
        UD_CARBON_IM,
        UD_CARBON_HM,
        PW_GLASS_1080,
    )
}


def material(name: str) -> PlyMaterial:
    try:
        return MATERIALS[name]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown ply material {name!r}; known: {sorted(MATERIALS)}") from None


def chemistry(name: str) -> CureChemistry:
    try:
        return CHEMISTRIES[name]
    except KeyError:  # pragma: no cover - defensive
        raise KeyError(f"unknown resin system {name!r}; known: {sorted(CHEMISTRIES)}") from None


def allowable_grade(basis: Basis) -> str:
    """Say what a value on this basis is allowed to be used for."""

    if basis is Basis.MEASURED_BASIS_VALUE:
        return "structural allowable"
    if basis is Basis.MEASURED_TYPICAL:
        return "sizing with knockdown; not an allowable until a basis value exists"
    return "trade study and sizing only; not a structural allowable"


def validate_materials() -> list[str]:
    """Registry-level checks.  Returns error strings; empty means consistent."""

    errors: list[str] = []
    for name, mat in MATERIALS.items():
        if mat.name != name:
            errors.append(f"{name}: registry key does not match material name")
        if mat.chemistry not in CHEMISTRIES:
            errors.append(f"{name}: unknown resin system {mat.chemistry!r}")
        # A cured ply cannot be lighter than its own fibre.
        if mat.areal_mass_g_m2 <= mat.fibre_areal_weight_gsm:
            errors.append(f"{name}: cured areal mass is below the fibre areal weight")
        # Resin content outside 25-45% by mass means the CPT, the areal weight
        # and the density triplet disagree with each other.
        if not 0.25 <= mat.resin_mass_fraction <= 0.45:
            errors.append(
                f"{name}: implied resin mass fraction {mat.resin_mass_fraction:.3f} "
                "is outside the 0.25-0.45 band; CPT, areal weight and density disagree"
            )
        # The same triplet, checked by volume: fibre volume fraction implied by
        # the areal weight must land near the declared nominal.
        implied_vf = (
            mat.fibre_areal_weight_gsm
            / (mat.fibre_density_g_cm3 * 1e6)
            / (mat.cured_ply_thickness_mm * 1e-3)
        )
        if abs(implied_vf - mat.nominal_fibre_volume_fraction) > 0.04:
            errors.append(
                f"{name}: fibre volume fraction from areal weight {implied_vf:.3f} "
                f"disagrees with declared {mat.nominal_fibre_volume_fraction:.3f}"
            )
        # The nominal lamina is void-free by definition: its declared density
        # must be the rule-of-mixtures density of its constituents.  Any gap
        # between nominal and measured density is void content, and that
        # belongs to a panel record, not to the material registry.
        if abs(mat.cured_density_g_cm3 - mat.theoretical_density_g_cm3()) > 0.01:
            errors.append(
                f"{name}: declared density {mat.cured_density_g_cm3:.3f} differs from the "
                f"rule-of-mixtures density {mat.theoretical_density_g_cm3():.3f}; the "
                "nominal lamina must be void-free"
            )
        # Strain to failure must be consistent with modulus and strength to
        # within the nonlinearity a lamina actually shows.
        implied_strain = mat.xt_mpa / mat.e1_mpa
        if not 0.75 <= implied_strain / mat.ultimate_strain_1 <= 1.25:
            errors.append(
                f"{name}: ultimate strain {mat.ultimate_strain_1:.4f} is inconsistent "
                f"with Xt/E1 = {implied_strain:.4f}"
            )
        if mat.basis in DESIGN_GRADE_BASES and not mat.note:
            errors.append(f"{name}: measured data must name its panel set in `note`")
    return errors


def snapshot() -> dict[str, object]:
    return {
        "units": {
            "stress": "MPa",
            "length": "mm",
            "temperature": "degC",
            "density": "g/cm^3",
            "areal_weight": "g/m^2",
        },
        "errors": validate_materials(),
        "materials": [
            {
                **asdict(mat),
                "nu21": round(mat.nu21, 5),
                "areal_mass_g_m2": round(mat.areal_mass_g_m2, 1),
                "resin_mass_fraction": round(mat.resin_mass_fraction, 4),
                "theoretical_density_g_cm3": round(mat.theoretical_density_g_cm3(), 4),
                "allowable_grade": allowable_grade(mat.basis),
            }
            for mat in MATERIALS.values()
        ],
        "chemistries": [asdict(chem) for chem in CHEMISTRIES.values()],
    }
