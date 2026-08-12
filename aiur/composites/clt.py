"""Classical laminate theory for the CARRIER-P0 composite structures.

This is the analysis half of the composites discipline: given a stacking
sequence, what is the laminate's stiffness, what does it do when the tool
cools from cure, how much load does each ply actually see, and which ply
fails first.  It is written out in full rather than pulled from a package
because the rest of ``aiur`` is dependency-free and runs in CI on every
push, and because a laminate calculation whose internals cannot be read is a
laminate calculation nobody can argue with.

What the module computes, in the order the questions get asked:

1. ``Q``  — the reduced stiffness of one lamina in its own fibre axes.
2. ``Qbar`` — the same lamina rotated into the laminate axes.
3. ``A``, ``B``, ``D`` — the laminate's extensional, coupling and bending
   stiffness, by integration through the thickness.
4. Engineering constants — the ``Ex``, ``Ey``, ``Gxy``, ``nuxy`` a stress
   analyst or an FE model wants.
5. Thermal and cure-shrinkage resultants — the loads a laminate applies to
   itself on cooldown, which produce laminate CTE, warpage of an unsymmetric
   stack, and the residual stress that cracks a thin transverse ply before
   any external load is applied.
6. Ply-by-ply strain, stress, and failure index under a combined mechanical
   and thermal load case.

Sign and unit conventions, held everywhere:

* Angles in degrees, measured from the laminate x axis, right-handed about z.
* Plies are listed **bottom surface first** (most negative z first).  A
  layup written top-down on a traveler is reversed on entry, and
  :func:`Laminate.from_top_down` exists so nobody has to remember which.
* Force resultants ``N`` in N/mm, moment resultants ``M`` in N (N.mm/mm).
* Strains are engineering strains; the shear terms are ``gamma``, not
  tensor ``epsilon_xy``, and the CTE shear term is correspondingly ``2 c s
  (a1 - a2)``.
* Temperature change ``dT`` is signed and is negative for a cooldown from
  cure to room temperature, which is the load case that matters.

The one modelling limit worth stating up front: CLT is a thin-plate theory.
It has no interlaminar stress, no free-edge effect, and no through-thickness
strength.  The parts it sizes here are 0.16-1.2 mm skins where that is the
right idealisation.  Where a joint or a ply drop introduces an interlaminar
stress, the answer is a coupon, not a thicker CLT model, and the DoE plan
says which coupon.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from .materials import PlyMaterial, material as lookup_material

Matrix = list[list[float]]
Vector = list[float]

#: Below this the laminate is treated as having no coupling at all.  Scaled
#: against the B-matrix norm normalised by A and D, so it is dimensionless.
COUPLING_TOLERANCE = 1e-9


# --------------------------------------------------------------------------
# Small dense linear algebra.  Six-by-six at most; clarity beats speed.
# --------------------------------------------------------------------------


def solve(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> Vector:
    """Solve ``matrix @ x = rhs`` by Gauss-Jordan with partial pivoting."""

    n = len(matrix)
    if any(len(row) != n for row in matrix):
        raise ValueError("matrix must be square")
    if len(rhs) != n:
        raise ValueError("right-hand side length must match the matrix")

    augmented = [list(map(float, row)) + [float(rhs[i])] for i, row in enumerate(matrix)]
    for column in range(n):
        pivot_row = max(range(column, n), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot_row][column]) < 1e-12:
            raise ValueError("matrix is singular to working precision")
        augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        augmented[column] = [value / pivot for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return [row[n] for row in augmented]


def invert(matrix: Sequence[Sequence[float]]) -> Matrix:
    """Return the inverse of a small square matrix."""

    n = len(matrix)
    columns = [solve(matrix, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[columns[j][i] for j in range(n)] for i in range(n)]


def _zeros(rows: int, cols: int) -> Matrix:
    return [[0.0] * cols for _ in range(rows)]


# --------------------------------------------------------------------------
# Lamina stiffness
# --------------------------------------------------------------------------


def reduced_stiffness(mat: PlyMaterial) -> Matrix:
    """Return the 3x3 reduced stiffness ``Q`` in the lamina's fibre axes, MPa."""

    denominator = 1.0 - mat.nu12 * mat.nu21
    q11 = mat.e1_mpa / denominator
    q22 = mat.e2_mpa / denominator
    q12 = mat.nu12 * mat.e2_mpa / denominator
    return [
        [q11, q12, 0.0],
        [q12, q22, 0.0],
        [0.0, 0.0, mat.g12_mpa],
    ]


def transformed_stiffness(mat: PlyMaterial, angle_deg: float) -> Matrix:
    """Return ``Qbar``: the lamina stiffness rotated into laminate axes."""

    q = reduced_stiffness(mat)
    q11, q12, q22, q66 = q[0][0], q[0][1], q[1][1], q[2][2]
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    c2, s2 = c * c, s * s
    c4, s4 = c2 * c2, s2 * s2
    cs = c * s

    qbar11 = q11 * c4 + 2.0 * (q12 + 2.0 * q66) * s2 * c2 + q22 * s4
    qbar12 = (q11 + q22 - 4.0 * q66) * s2 * c2 + q12 * (c4 + s4)
    qbar22 = q11 * s4 + 2.0 * (q12 + 2.0 * q66) * s2 * c2 + q22 * c4
    qbar16 = (q11 - q12 - 2.0 * q66) * cs * c2 + (q12 - q22 + 2.0 * q66) * cs * s2
    qbar26 = (q11 - q12 - 2.0 * q66) * cs * s2 + (q12 - q22 + 2.0 * q66) * cs * c2
    qbar66 = (q11 + q22 - 2.0 * q12 - 2.0 * q66) * s2 * c2 + q66 * (c4 + s4)

    return [
        [qbar11, qbar12, qbar16],
        [qbar12, qbar22, qbar26],
        [qbar16, qbar26, qbar66],
    ]


def transformed_expansion(mat: PlyMaterial, angle_deg: float) -> Vector:
    """Return ``[ax, ay, axy]`` — lamina CTE rotated into laminate axes, 1/K.

    The third term is an *engineering* shear expansion, so it carries the
    factor of two that converts the tensor component.
    """

    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    a1, a2 = mat.alpha1_per_k, mat.alpha2_per_k
    return [
        a1 * c * c + a2 * s * s,
        a1 * s * s + a2 * c * c,
        2.0 * c * s * (a1 - a2),
    ]


def transformed_shrinkage(mat: PlyMaterial, angle_deg: float) -> Vector:
    """Return ``[sx, sy, sxy]`` — cure shrinkage strain in laminate axes.

    Sign convention matches strain: a shrinking ply has *negative* strain, so
    the stored positive shrinkage magnitudes are negated here once, at the
    only place that knows what the sign means.
    """

    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    e1, e2 = -mat.shrink1, -mat.shrink2
    return [
        e1 * c * c + e2 * s * s,
        e1 * s * s + e2 * c * c,
        2.0 * c * s * (e1 - e2),
    ]


# --------------------------------------------------------------------------
# Laminate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ply:
    """One ply in a stacking sequence."""

    material: str
    angle_deg: float
    #: Overrides the material CPT when a ply is knowingly built thicker or
    #: thinner than nominal — an as-built record, or a doubler.
    thickness_mm: float | None = None

    @property
    def mat(self) -> PlyMaterial:
        return lookup_material(self.material)

    @property
    def thickness(self) -> float:
        return self.material_thickness if self.thickness_mm is None else self.thickness_mm

    @property
    def material_thickness(self) -> float:
        return self.mat.cured_ply_thickness_mm


@dataclass(frozen=True)
class PlyState:
    """Strain, stress, and failure of one ply at one surface."""

    index: int
    material: str
    angle_deg: float
    z_mm: float
    #: Total strain in laminate axes (what a strain gauge on that plane sees).
    strain_xy: tuple[float, float, float]
    #: Total strain rotated into the ply's own fibre axes.
    strain_12: tuple[float, float, float]
    #: Mechanical strain in fibre axes — total minus free thermal/chemical
    #: strain.  This is the part that makes stress.
    mechanical_strain_12: tuple[float, float, float]
    stress_12_mpa: tuple[float, float, float]
    max_strain_index: float
    tsai_wu_index: float
    #: Load multiplier at which Tsai-Wu reaches unity for this ply, holding
    #: the thermal part of the load case fixed.
    strength_ratio: float


@dataclass(frozen=True)
class LaminateResponse:
    """Mid-plane response to one combined mechanical and thermal load case."""

    mid_strain: tuple[float, float, float]
    curvature: tuple[float, float, float]
    plies: tuple[PlyState, ...]

    @property
    def critical_ply(self) -> PlyState:
        return max(self.plies, key=lambda ply: ply.tsai_wu_index)

    @property
    def max_tsai_wu(self) -> float:
        return self.critical_ply.tsai_wu_index

    @property
    def max_strain_index(self) -> float:
        return max(ply.max_strain_index for ply in self.plies)

    @property
    def first_ply_failure_ratio(self) -> float:
        """Smallest load multiplier that fails any ply."""

        return min(ply.strength_ratio for ply in self.plies)


class Laminate:
    """A stacking sequence and everything derivable from it.

    Plies are stored bottom-surface first.  Construction is cheap; the ABD
    matrices are computed once and cached, because every downstream question
    asks for them.
    """

    def __init__(self, plies: Iterable[Ply], *, name: str = "") -> None:
        self.plies: tuple[Ply, ...] = tuple(plies)
        if not self.plies:
            raise ValueError("a laminate needs at least one ply")
        self.name = name
        self._abd: Matrix | None = None

    # -- construction ------------------------------------------------------

    @classmethod
    def from_top_down(cls, plies: Iterable[Ply], *, name: str = "") -> "Laminate":
        """Build from a top-surface-first list, as a traveler writes it."""

        return cls(tuple(plies)[::-1], name=name)

    @classmethod
    def from_angles(
        cls,
        material_name: str,
        angles_deg: Sequence[float],
        *,
        name: str = "",
    ) -> "Laminate":
        """Build a single-material laminate from a bottom-up angle list."""

        return cls((Ply(material_name, angle) for angle in angles_deg), name=name)

    # -- geometry ----------------------------------------------------------

    @property
    def thickness_mm(self) -> float:
        return sum(ply.thickness for ply in self.plies)

    @property
    def ply_count(self) -> int:
        return len(self.plies)

    def z_boundaries(self) -> tuple[float, ...]:
        """Ply interface heights measured from the mid-plane, bottom first."""

        half = self.thickness_mm / 2.0
        boundaries = [-half]
        for ply in self.plies:
            boundaries.append(boundaries[-1] + ply.thickness)
        # Guard the accumulation: a long stack must still close on +h/2.
        boundaries[-1] = half
        return tuple(boundaries)

    @property
    def areal_mass_g_m2(self) -> float:
        """Cured areal mass of the laminate, g/m^2 — the mass budget input."""

        return sum(
            ply.thickness * 1e-3 * ply.mat.cured_density_g_cm3 * 1e6 for ply in self.plies
        )

    # -- stiffness ---------------------------------------------------------

    def abd(self) -> Matrix:
        """Return the 6x6 ``[[A, B], [B, D]]`` laminate stiffness matrix.

        Units: ``A`` in N/mm, ``B`` in N, ``D`` in N.mm.
        """

        if self._abd is not None:
            return [row[:] for row in self._abd]

        a = _zeros(3, 3)
        b = _zeros(3, 3)
        d = _zeros(3, 3)
        z = self.z_boundaries()
        for k, ply in enumerate(self.plies):
            qbar = transformed_stiffness(ply.mat, ply.angle_deg)
            z0, z1 = z[k], z[k + 1]
            dz = z1 - z0
            dz2 = (z1 * z1 - z0 * z0) / 2.0
            dz3 = (z1 ** 3 - z0 ** 3) / 3.0
            for i in range(3):
                for j in range(3):
                    a[i][j] += qbar[i][j] * dz
                    b[i][j] += qbar[i][j] * dz2
                    d[i][j] += qbar[i][j] * dz3

        abd = _zeros(6, 6)
        for i in range(3):
            for j in range(3):
                abd[i][j] = a[i][j]
                abd[i][j + 3] = b[i][j]
                abd[i + 3][j] = b[i][j]
                abd[i + 3][j + 3] = d[i][j]
        self._abd = abd
        return [row[:] for row in abd]

    def a_matrix(self) -> Matrix:
        abd = self.abd()
        return [row[:3] for row in abd[:3]]

    def b_matrix(self) -> Matrix:
        abd = self.abd()
        return [row[3:] for row in abd[:3]]

    def d_matrix(self) -> Matrix:
        abd = self.abd()
        return [row[3:] for row in abd[3:]]

    # -- classification ----------------------------------------------------

    def is_symmetric(self, *, tolerance: float = 1e-9) -> bool:
        """True when the stack mirrors about the mid-plane.

        Checked on the geometry rather than on ``B``, because a stack can be
        geometrically unsymmetric and still show a small ``B`` by accident,
        and the shop cares about the stack.
        """

        n = self.ply_count
        for k in range(n // 2):
            top = self.plies[n - 1 - k]
            bottom = self.plies[k]
            if bottom.material != top.material:
                return False
            if abs(bottom.angle_deg - top.angle_deg) > tolerance:
                return False
            if abs(bottom.thickness - top.thickness) > tolerance:
                return False
        return True

    def is_balanced(self, *, tolerance: float = 1e-9) -> bool:
        """True when every off-axis ply has an equal and opposite partner.

        An unbalanced laminate has non-zero ``A16``/``A26``: pull on it and it
        shears.  For a bonded assembly that means the part twists off the tool
        on cooldown even when it is symmetric.
        """

        remaining: list[Ply] = list(self.plies)
        for ply in self.plies:
            if _self_balanced(ply, tolerance=tolerance):
                continue
            partner_angle = (-ply.angle_deg) % 180.0
            for candidate in remaining:
                if candidate.material != ply.material:
                    continue
                if abs(candidate.thickness - ply.thickness) > tolerance:
                    continue
                if abs((candidate.angle_deg % 180.0) - partner_angle) <= 1e-6:
                    remaining.remove(candidate)
                    break
            else:
                return False
        return True

    def coupling_ratio(self) -> float:
        """Dimensionless size of ``B`` against ``A`` and ``D``.

        ``B`` has units between ``A`` and ``D``, so the honest scalar measure
        is ``max|B| / sqrt(max|A| max|D|)``.  Zero for any symmetric stack.
        """

        a = max(abs(value) for row in self.a_matrix() for value in row)
        d = max(abs(value) for row in self.d_matrix() for value in row)
        b = max(abs(value) for row in self.b_matrix() for value in row)
        return b / math.sqrt(a * d)

    def is_coupled(self) -> bool:
        return self.coupling_ratio() > COUPLING_TOLERANCE

    def orientation_fractions(self) -> dict[str, float]:
        """Thickness fraction in the 0 / 90 / +-45 / other families.

        The 10 %-rule check reads this: every family present in a design
        laminate carries at least 10 % of the thickness, so no direction is
        left to the resin alone.
        """

        total = self.thickness_mm
        buckets = {"0": 0.0, "90": 0.0, "45": 0.0, "other": 0.0}
        for ply in self.plies:
            angle = ply.angle_deg % 180.0
            if math.isclose(angle, 0.0, abs_tol=1e-6):
                key = "0"
            elif math.isclose(angle, 90.0, abs_tol=1e-6):
                key = "90"
            elif math.isclose(angle, 45.0, abs_tol=1e-6) or math.isclose(
                angle, 135.0, abs_tol=1e-6
            ):
                key = "45"
            else:
                key = "other"
            # A woven ply puts half its thickness in each of two directions.
            if ply.mat.form.value != "unidirectional":
                cross = "90" if key == "0" else "0" if key == "90" else key
                buckets[key] += ply.thickness / 2.0
                buckets[cross] += ply.thickness / 2.0
            else:
                buckets[key] += ply.thickness
        return {key: value / total for key, value in buckets.items()}

    def max_contiguous_same_angle(self) -> int:
        """Longest run of same-orientation *unidirectional* plies.

        A thick block of like-oriented plies is where transverse cracks link
        up and turn into a delamination, so layup rules cap the run length.

        A woven ply breaks a run even when its nominal angle matches, because
        half its fibre is at 90 degrees to that angle: it is exactly the
        crack-arresting interruption the rule is asking for.  That is not a
        loophole — it is why the keel rail carries fabric between its tape
        plies instead of a single thicker tape block.
        """

        best = current = 1
        for previous, ply in zip(self.plies, self.plies[1:]):
            both_ud = (
                previous.mat.form.value == "unidirectional"
                and ply.mat.form.value == "unidirectional"
            )
            same = math.isclose(
                previous.angle_deg % 180.0, ply.angle_deg % 180.0, abs_tol=1e-6
            )
            if both_ud and same:
                current += 1
                best = max(best, current)
            else:
                current = 1
        return best

    # -- engineering constants --------------------------------------------

    def engineering_constants(self) -> dict[str, float]:
        """In-plane smeared constants, MPa and dimensionless.

        For a symmetric laminate these are exact.  For an unsymmetric one
        they describe a membrane restrained flat, which is a different
        structure from the free part — so the caller is told, via
        ``valid_for_free_plate``, rather than being handed a number that
        quietly means something else.
        """

        a_inverse = invert(self.a_matrix())
        h = self.thickness_mm
        ex = 1.0 / (h * a_inverse[0][0])
        ey = 1.0 / (h * a_inverse[1][1])
        gxy = 1.0 / (h * a_inverse[2][2])
        nuxy = -a_inverse[0][1] / a_inverse[0][0]
        nuyx = -a_inverse[0][1] / a_inverse[1][1]
        # Bending constants come from D, and a thin skin's buckling and
        # spring-back are bending problems, so both are reported.
        d = self.d_matrix()
        d_inverse = invert(d)
        exb = 12.0 / (h ** 3 * d_inverse[0][0])
        eyb = 12.0 / (h ** 3 * d_inverse[1][1])
        return {
            "ex_mpa": ex,
            "ey_mpa": ey,
            "gxy_mpa": gxy,
            "nuxy": nuxy,
            "nuyx": nuyx,
            "ex_bending_mpa": exb,
            "ey_bending_mpa": eyb,
            "valid_for_free_plate": not self.is_coupled(),
        }

    # -- thermal and cure-shrinkage response --------------------------------

    def _resultants(self, per_ply_strain) -> tuple[Vector, Vector]:
        """Integrate a per-ply free strain into ``(N, M)`` resultants."""

        n_res = [0.0, 0.0, 0.0]
        m_res = [0.0, 0.0, 0.0]
        z = self.z_boundaries()
        for k, ply in enumerate(self.plies):
            qbar = transformed_stiffness(ply.mat, ply.angle_deg)
            free = per_ply_strain(ply)
            z0, z1 = z[k], z[k + 1]
            dz = z1 - z0
            dz2 = (z1 * z1 - z0 * z0) / 2.0
            for i in range(3):
                stress = sum(qbar[i][j] * free[j] for j in range(3))
                n_res[i] += stress * dz
                m_res[i] += stress * dz2
        return n_res, m_res

    def thermal_resultants(self, delta_t_k: float) -> tuple[Vector, Vector]:
        """``(N_T, M_T)`` for a temperature change, N/mm and N."""

        return self._resultants(
            lambda ply: [
                component * delta_t_k
                for component in transformed_expansion(ply.mat, ply.angle_deg)
            ]
        )

    def shrinkage_resultants(self, fraction: float = 1.0) -> tuple[Vector, Vector]:
        """``(N_S, M_S)`` from cure shrinkage locked in after gelation.

        ``fraction`` is the share of total chemical shrinkage that occurs
        *after* the resin gels; shrinkage before gelation is taken up by
        resin flow and does not build stress.  It is an engineering target
        until the DoE's shrinkage panel measures it.
        """

        if not 0.0 <= fraction <= 1.0:
            raise ValueError("shrinkage fraction must be in [0, 1]")
        return self._resultants(
            lambda ply: [
                component * fraction
                for component in transformed_shrinkage(ply.mat, ply.angle_deg)
            ]
        )

    def mixed_solve(
        self,
        resultants: Sequence[float],
        restrained: Sequence[int] = (),
    ) -> Vector:
        """Solve the ABD system with a mixed set of boundary conditions.

        ``resultants`` holds ``[Nx, Ny, Nxy, Mx, My, Mxy]``.  Indices listed
        in ``restrained`` have their *generalised strain* held at zero
        instead, and the corresponding resultant is whatever the restraint
        has to supply.  Rows for restrained degrees of freedom are replaced
        by an identity row, which is the standard way to impose a kinematic
        constraint on a stiffness system without partitioning it by hand.
        """

        if len(resultants) != 6:
            raise ValueError("six resultants required")
        restrained_set = set(restrained)
        if not restrained_set <= set(range(6)):
            raise ValueError("restrained indices must be in 0..5")
        matrix = self.abd()
        rhs = list(map(float, resultants))
        for index in restrained_set:
            matrix[index] = [1.0 if column == index else 0.0 for column in range(6)]
            rhs[index] = 0.0
        return solve(matrix, rhs)

    def cte_per_k(self) -> tuple[float, float, float]:
        """Laminate in-plane CTE ``(ax, ay, axy)``, 1/K.

        Computed by applying the unit thermal resultant to the full 6x6
        system, so an unsymmetric laminate's thermal curvature is accounted
        for rather than silently dropped.
        """

        n_res, m_res = self.thermal_resultants(1.0)
        solution = solve(self.abd(), list(n_res) + list(m_res))
        return (solution[0], solution[1], solution[2])

    def thermal_curvature_per_k(self) -> tuple[float, float, float]:
        """Curvature per kelvin, 1/(mm.K).  Zero for a symmetric laminate."""

        n_res, m_res = self.thermal_resultants(1.0)
        solution = solve(self.abd(), list(n_res) + list(m_res))
        return (solution[3], solution[4], solution[5])

    # -- load response -----------------------------------------------------

    def response(
        self,
        *,
        n_per_mm: Sequence[float] = (0.0, 0.0, 0.0),
        m_per_mm: Sequence[float] = (0.0, 0.0, 0.0),
        delta_t_k: float = 0.0,
        shrinkage_fraction: float = 0.0,
        edge: str = "free",
    ) -> LaminateResponse:
        """Solve one combined mechanical + thermal + shrinkage load case.

        The thermal and chemical parts enter twice, and getting that wrong is
        the classic residual-stress error: they add to the applied resultants
        to find the laminate's deformation, and they subtract from each ply's
        total strain to find the mechanical strain that makes stress.

        ``edge`` selects the transverse boundary condition, which is not a
        detail — it moved the predicted surface strain of a skin panel here
        by a factor of two:

        ``free``
            All six resultants prescribed.  Correct for a narrow strip with
            free edges: the plate curls anticlastically, ``ky`` releases, and
            the effective bending stiffness drops to ``1/d11``.  This is the
            right model for a coupon and the conservative one for a panel.
        ``cylindrical``
            ``ey`` and ``ky`` restrained to zero, their resultants reacted by
            the surrounding structure.  Correct for a skin panel that is long
            between line supports — a funnel gore between two ribs, a strip
            of a closed section — where the material either side of the
            loaded strip prevents the anticlastic curvature from developing.
        """

        n_thermal, m_thermal = self.thermal_resultants(delta_t_k)
        n_shrink, m_shrink = self.shrinkage_resultants(shrinkage_fraction)
        resultants = [
            n_per_mm[0] + n_thermal[0] + n_shrink[0],
            n_per_mm[1] + n_thermal[1] + n_shrink[1],
            n_per_mm[2] + n_thermal[2] + n_shrink[2],
            m_per_mm[0] + m_thermal[0] + m_shrink[0],
            m_per_mm[1] + m_thermal[1] + m_shrink[1],
            m_per_mm[2] + m_thermal[2] + m_shrink[2],
        ]
        if edge == "free":
            restrained: tuple[int, ...] = ()
        elif edge == "cylindrical":
            restrained = (1, 4)  # ey and ky held at zero
        else:
            raise ValueError(f"unknown edge condition {edge!r}")
        solution = self.mixed_solve(resultants, restrained)
        mid = (solution[0], solution[1], solution[2])
        curvature = (solution[3], solution[4], solution[5])

        states: list[PlyState] = []
        z = self.z_boundaries()
        for k, ply in enumerate(self.plies):
            # Evaluate both faces of the ply and keep the worse: under
            # bending the outer fibre governs, and a ply-midpoint-only
            # evaluation understates a thin skin in bending.
            for z_eval in (z[k], z[k + 1]):
                strain_xy = tuple(
                    mid[i] + z_eval * curvature[i] for i in range(3)
                )
                strain_12 = _rotate_strain(strain_xy, -ply.angle_deg)
                free_12 = (
                    ply.mat.alpha1_per_k * delta_t_k - ply.mat.shrink1 * shrinkage_fraction,
                    ply.mat.alpha2_per_k * delta_t_k - ply.mat.shrink2 * shrinkage_fraction,
                    0.0,
                )
                mechanical = tuple(strain_12[i] - free_12[i] for i in range(3))
                q = reduced_stiffness(ply.mat)
                stress = tuple(
                    sum(q[i][j] * mechanical[j] for j in range(3)) for i in range(3)
                )
                states.append(
                    PlyState(
                        index=k,
                        material=ply.material,
                        angle_deg=ply.angle_deg,
                        z_mm=z_eval,
                        strain_xy=strain_xy,  # type: ignore[arg-type]
                        strain_12=strain_12,
                        mechanical_strain_12=mechanical,  # type: ignore[arg-type]
                        stress_12_mpa=stress,  # type: ignore[arg-type]
                        max_strain_index=max_strain_index(ply.mat, mechanical),
                        tsai_wu_index=tsai_wu_index(ply.mat, stress),
                        strength_ratio=tsai_wu_strength_ratio(ply.mat, stress),
                    )
                )
        return LaminateResponse(mid, curvature, tuple(states))

    def describe(self) -> str:
        """Stacking-sequence shorthand, as a traveler would print it."""

        angles = [
            f"{ply.angle_deg:g}" for ply in self.plies
        ]
        materials = {ply.material for ply in self.plies}
        stack = "/".join(angles)
        suffix = f" ({sorted(materials)[0]})" if len(materials) == 1 else ""
        symmetry = "s" if self.is_symmetric() else ""
        if symmetry:
            half = angles[: len(angles) // 2]
            if len(angles) % 2 == 0:
                stack = "/".join(half)
                return f"[{stack}]s{suffix}"
        return f"[{stack}]{suffix}"


def _self_balanced(ply: Ply, *, tolerance: float = 1e-9) -> bool:
    """True when a ply needs no mirror-angle partner to keep ``A16`` at zero.

    On-axis plies are trivially balanced.  A woven ply at 45 degrees is
    balanced *by itself*, because the weave already carries tows at +45 and
    -45 — a fact worth encoding, since demanding a partner ply for it would
    force every quasi-isotropic fabric skin to carry an unnecessary ply and a
    tenth of a millimetre of unnecessary thickness.
    """

    angle = ply.angle_deg % 180.0
    if abs(angle) <= tolerance or abs(angle - 90.0) <= tolerance:
        return True
    if ply.mat.form.value != "unidirectional" and abs(angle % 90.0 - 45.0) <= tolerance:
        return True
    return False


def _rotate_strain(strain_xy: Sequence[float], angle_deg: float) -> tuple[float, float, float]:
    """Rotate an engineering strain vector by ``angle_deg`` about z.

    Passing ``-theta`` takes laminate axes into the fibre axes of a ply laid
    at ``+theta``.  The halving and doubling of the shear term is the tensor
    conversion; writing it out here keeps it in one place.
    """

    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    ex, ey, gxy = strain_xy
    exy = gxy / 2.0
    e1 = ex * c * c + ey * s * s + 2.0 * exy * c * s
    e2 = ex * s * s + ey * c * c - 2.0 * exy * c * s
    e12 = (ey - ex) * c * s + exy * (c * c - s * s)
    return (e1, e2, 2.0 * e12)


# --------------------------------------------------------------------------
# Failure criteria
# --------------------------------------------------------------------------


def max_strain_index(mat: PlyMaterial, mechanical_strain_12: Sequence[float]) -> float:
    """Maximum-strain failure index; >= 1 is failure.

    Strain allowables are derived from the strength and modulus rather than
    stored separately, so a strength edit cannot leave a stale strain limit
    behind.
    """

    e1, e2, g12 = mechanical_strain_12
    limits = (
        mat.xt_mpa / mat.e1_mpa if e1 >= 0 else mat.xc_mpa / mat.e1_mpa,
        mat.yt_mpa / mat.e2_mpa if e2 >= 0 else mat.yc_mpa / mat.e2_mpa,
        mat.s12_mpa / mat.g12_mpa,
    )
    return max(abs(value) / limit for value, limit in zip((e1, e2, g12), limits))


def _tsai_wu_coefficients(mat: PlyMaterial) -> tuple[float, float, float, float, float, float]:
    f1 = 1.0 / mat.xt_mpa - 1.0 / mat.xc_mpa
    f2 = 1.0 / mat.yt_mpa - 1.0 / mat.yc_mpa
    f11 = 1.0 / (mat.xt_mpa * mat.xc_mpa)
    f22 = 1.0 / (mat.yt_mpa * mat.yc_mpa)
    f66 = 1.0 / (mat.s12_mpa ** 2)
    # The interaction term is not measurable without a biaxial test, so it
    # takes the standard stability-preserving value F12 = -0.5 sqrt(F11 F22).
    f12 = -0.5 * math.sqrt(f11 * f22)
    return f1, f2, f11, f22, f66, f12


def tsai_wu_index(mat: PlyMaterial, stress_12_mpa: Sequence[float]) -> float:
    """Tsai-Wu failure index; >= 1 is failure of that ply."""

    s1, s2, t12 = stress_12_mpa
    f1, f2, f11, f22, f66, f12 = _tsai_wu_coefficients(mat)
    return (
        f1 * s1
        + f2 * s2
        + f11 * s1 * s1
        + f22 * s2 * s2
        + f66 * t12 * t12
        + 2.0 * f12 * s1 * s2
    )


def tsai_wu_strength_ratio(mat: PlyMaterial, stress_12_mpa: Sequence[float]) -> float:
    """Multiplier ``R`` on this stress state that reaches failure.

    Solves ``a R^2 + b R = 1``.  Reported instead of the index alone because
    the index is quadratic: an index of 0.25 is a factor of two on load, not
    a factor of four, and sizing off the index has cost programmes parts.
    """

    s1, s2, t12 = stress_12_mpa
    f1, f2, f11, f22, f66, f12 = _tsai_wu_coefficients(mat)
    a = f11 * s1 * s1 + f22 * s2 * s2 + f66 * t12 * t12 + 2.0 * f12 * s1 * s2
    b = f1 * s1 + f2 * s2
    if a <= 1e-30:
        if abs(b) <= 1e-30:
            return math.inf
        return 1.0 / b if b > 0 else math.inf
    return (-b + math.sqrt(b * b + 4.0 * a)) / (2.0 * a)


def bending_strain_at_radius(thickness_mm: float, radius_mm: float) -> float:
    """Peak surface strain when a laminate of this thickness is rolled.

    The whole stowage question for a deployable reduces to this one line:
    ``eps = t / (2 R)`` at the neutral axis of a symmetric laminate.  It is
    why a deployable boom is built from the thinnest ply available and why
    high-modulus fibre, which has the lowest strain allowable, is the wrong
    material for anything that gets rolled.
    """

    if thickness_mm <= 0:
        raise ValueError("thickness must be positive")
    if radius_mm <= 0:
        raise ValueError("radius must be positive")
    return thickness_mm / (2.0 * radius_mm)


def minimum_stow_radius_mm(
    laminate: Laminate,
    *,
    knockdown: float = 0.5,
) -> float:
    """Smallest rolling radius the laminate may be stowed at, mm.

    The knockdown is applied to the fibre-direction ultimate strain and is
    doing real work: a stowed structure sits at strain for the whole time
    between packing and deployment, so the governing property is creep
    rupture and stress relaxation, not the room-temperature ultimate a
    coupon reports.  A factor of two on strain is the customary starting
    point for long-duration stowage and stays an engineering target here
    until the stowage-hold test in the DoE plan measures it.
    """

    if not 0.0 < knockdown <= 1.0:
        raise ValueError("knockdown must be in (0, 1]")
    allowable = min(ply.mat.ultimate_strain_1 for ply in laminate.plies) * knockdown
    return laminate.thickness_mm / (2.0 * allowable)
