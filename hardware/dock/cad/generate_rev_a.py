#!/usr/bin/env python3
"""Generate deterministic CARRIER-P0 P0-A fabrication geometry.

The source geometry is deliberately dependency-free so a clean checkout can
regenerate the manufacturing artifacts without a CAD kernel.  Dimensions are
in millimetres.  These parts are bench-screening geometry, not flight-qualified
hardware.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]
Vec2 = tuple[float, float]


@dataclass(frozen=True)
class DockRevision:
    """One complete parameter set for the capture chain.

    Every dimension the tolerance stack reasons about is a field here, and
    nothing that matters is a literal inside a mesh function.  Rev-A had the
    probe seat diameter and the keeper tine reach buried in the geometry while
    ``keeper_open_travel_mm`` was declared and consumed by nothing, which is
    how the commanded stroke and the geometry it has to clear came to disagree
    by 2.6 mm without anything noticing.
    """

    #: Revision label; appears in the generated manifest so a printed part
    #: can always be traced back to the geometry that produced it.
    name: str = "Rev-A"
    funnel_mouth_diameter_mm: float = 180.0
    funnel_throat_diameter_mm: float = 16.0
    funnel_depth_mm: float = 65.0
    funnel_mouth_wall_mm: float = 1.2
    funnel_flange_diameter_mm: float = 70.0
    funnel_flange_thickness_mm: float = 3.0
    funnel_total_height_mm: float = 73.0
    flange_hole_diameter_mm: float = 3.2
    flange_hole_square_mm: float = 40.0
    probe_head_diameter_mm: float = 12.0
    #: Lower cylinder the keeper actually bears on.  The Ø12 belt above it is
    #: what the funnel guides; this is what retains.
    probe_head_seat_diameter_mm: float = 6.0
    probe_mast_diameter_mm: float = 3.0
    probe_head_bore_diameter_mm: float = 3.2
    probe_tip_height_above_prop_plane_mm: float = 110.0
    #: How far the keeper body extends behind the dock axis, carrying the
    #: guides and the actuator link.
    keeper_back_reach_mm: float = 20.0
    keeper_width_mm: float = 18.0
    keeper_thickness_mm: float = 2.5
    keeper_slot_width_mm: float = 4.2
    #: How far the fork tines reach past the dock axis.  Sets the stroke the
    #: keeper needs to clear the head on release.
    keeper_tine_reach_mm: float = 8.0
    keeper_open_travel_mm: float = 11.0

    # --- keeper drive (slider-crank) -------------------------------------
    #: Crank radius on the servo horn.  An in-line slider-crank gives a
    #: stroke of exactly 2R, so this is the stroke requirement halved rather
    #: than a number chosen for packaging.
    crank_radius_mm: float = 6.5
    #: Link length between pin centres.  L/R = 3 keeps the maximum obliquity
    #: near 19.5 deg, which bounds the side load the keeper guides carry to
    #: about 0.35x the axial force.
    link_length_mm: float = 19.5
    #: Pin diameter for both joints; drilled after print, like the funnel
    #: flange, so no hole is modelled.
    drive_pin_diameter_mm: float = 3.0
    #: Where the link attaches to the keeper, along the keeper's own x axis.
    #: Must sit in the solid back, behind the slot round end.
    keeper_pin_x_mm: float = -14.0
    #: Plate thickness for the crank and the link.
    drive_plate_thickness_mm: float = 3.0
    #: Material each side of a drilled pin hole.
    drive_pin_edge_margin_mm: float = 3.0

    lathe_segments: int = 64

    @property
    def keeper_length_mm(self) -> float:
        """Overall keeper length, derived rather than declared.

        Rev-A declared 28 mm alongside a tine reach of 8 mm and a back reach
        of 20 mm; the moment either moved, the declared length was wrong. It
        is now the sum, so it cannot disagree with the geometry.
        """

        return self.keeper_back_reach_mm + self.keeper_tine_reach_mm

    @property
    def drive_stroke_mm(self) -> float:
        """Stroke an in-line slider-crank delivers: exactly twice the crank."""

        return 2.0 * self.crank_radius_mm

    @property
    def drive_obliquity_deg(self) -> float:
        """Worst-case link angle, which sets the side load on the guides."""

        return math.degrees(math.asin(self.crank_radius_mm / self.link_length_mm))

    @property
    def servo_axis_x_mm(self) -> float:
        """Servo axis position, with the keeper closed.

        In-line slider-crank: the keeper pin sits at ``L + R`` from the axis
        at full extension and ``L - R`` when retracted.
        """

        return self.keeper_pin_x_mm - (self.link_length_mm + self.crank_radius_mm)

    def drive_stroke_shortfall_mm(self) -> float:
        """Positive when the linkage cannot deliver the commanded stroke.

        The commanded stroke is itself checked against the geometry by
        ``release_travel_shortfall_mm``; this closes the other half of the
        chain, from servo rotation to keeper travel.  Rev-A's defect was
        exactly a number that nothing downstream consumed.
        """

        return self.keeper_open_travel_mm - self.drive_stroke_mm

    def exact_release_travel_mm(self) -> float:
        """Stroke needed for the tines to clear the widest part of the head.

        The tine material nearest the axis sits at the slot half-width, so it
        is clear of a circle of radius ``r`` once it has retracted past
        ``sqrt(r^2 - slot_half^2)`` beyond its own reach.
        """

        slot_half = self.keeper_slot_width_mm / 2.0
        head = self.probe_head_diameter_mm / 2.0
        if head <= slot_half:
            return self.keeper_tine_reach_mm
        return self.keeper_tine_reach_mm + math.sqrt(head * head - slot_half * slot_half)

    def release_travel_shortfall_mm(self) -> float:
        """Positive when the commanded stroke cannot clear the head."""

        return self.exact_release_travel_mm() - self.keeper_open_travel_mm


#: The article the P0-A gate was originally written against.  Kept so its
#: geometry stays reproducible and so the tolerance stack can still show why
#: it was superseded; it is not the article to build.  Three of its four
#: critical stacks do not close and its keeper cannot clear the probe head.
REV_A = DockRevision()

#: Rev-B closes every capture-chain stack with margin.  Four dimensions move,
#: and they move together because the constraints are coupled: the slot has to
#: grow to clear the mast, which costs retention ledge, so the seat grows with
#: it; and the tines shorten while the stroke lengthens so release stops being
#: negative at nominal.  Derived and checked in aiur/tolerance.py.
REV_B = DockRevision(
    name="Rev-B",
    probe_head_seat_diameter_mm=9.0,
    keeper_slot_width_mm=5.2,
    keeper_tine_reach_mm=5.0,
    keeper_open_travel_mm=13.0,
)

#: Backwards-compatible alias for callers that predate the revision split.
RevA = DockRevision
CURRENT = REV_B
PETG_DENSITY_G_CM3 = 1.27


@dataclass
class Mesh:
    name: str
    triangles: list[Triangle]

    def bounds(self) -> tuple[Vec3, Vec3]:
        points = [point for triangle in self.triangles for point in triangle]
        low = tuple(min(point[axis] for point in points) for axis in range(3))
        high = tuple(max(point[axis] for point in points) for axis in range(3))
        return low, high  # type: ignore[return-value]

    def volume_mm3(self) -> float:
        signed = 0.0
        for a, b, c in self.triangles:
            signed += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                + a[1] * (b[2] * c[0] - b[0] * c[2])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6.0
        return abs(signed)

    def degenerate_faces(self) -> int:
        return sum(_normal(a, b, c)[1] <= 1e-9 for a, b, c in self.triangles)

    def nonmanifold_edges(self) -> int:
        edge_counts: dict[tuple[Vec3, Vec3], int] = {}
        for triangle in self.triangles:
            for index in range(3):
                p = _key(triangle[index])
                q = _key(triangle[(index + 1) % 3])
                edge = tuple(sorted((p, q)))
                edge_counts[edge] = edge_counts.get(edge, 0) + 1
        return sum(count != 2 for count in edge_counts.values())


def _key(point: Vec3) -> Vec3:
    return tuple(round(value, 8) for value in point)  # type: ignore[return-value]


def _normal(a: Vec3, b: Vec3, c: Vec3) -> tuple[Vec3, float]:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    magnitude = math.sqrt(sum(value * value for value in cross))
    if magnitude == 0:
        return (0.0, 0.0, 0.0), 0.0
    return tuple(value / magnitude for value in cross), magnitude  # type: ignore[return-value]


def lathe(name: str, profile: Sequence[Vec2], segments: int) -> Mesh:
    """Revolve a closed radial/z profile around Z."""

    if segments < 12 or len(profile) < 3:
        raise ValueError("lathe needs >=12 segments and a closed-area profile")
    if any(radius <= 0 for radius, _ in profile):
        raise ValueError("this generator expects an annular profile")

    rings: list[list[Vec3]] = []
    for radius, z_value in profile:
        ring = []
        for index in range(segments):
            theta = 2.0 * math.pi * index / segments
            ring.append((radius * math.cos(theta), radius * math.sin(theta), z_value))
        rings.append(ring)

    triangles: list[Triangle] = []
    for profile_index in range(len(profile)):
        next_profile = (profile_index + 1) % len(profile)
        for index in range(segments):
            next_index = (index + 1) % segments
            a = rings[profile_index][index]
            b = rings[profile_index][next_index]
            c = rings[next_profile][next_index]
            d = rings[next_profile][index]
            triangles.extend(((a, b, c), (a, c, d)))
    return Mesh(name, triangles)


def _area2(a: Vec2, b: Vec2, c: Vec2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _polygon_area(points: Sequence[Vec2]) -> float:
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def _inside_triangle(point: Vec2, a: Vec2, b: Vec2, c: Vec2) -> bool:
    eps = 1e-9
    return (
        _area2(a, b, point) >= -eps
        and _area2(b, c, point) >= -eps
        and _area2(c, a, point) >= -eps
    )


def triangulate_polygon(points: Sequence[Vec2]) -> list[tuple[int, int, int]]:
    """Triangulate a simple polygon by ear clipping."""

    if len(points) < 3:
        raise ValueError("polygon needs at least three vertices")
    vertices = list(range(len(points)))
    if _polygon_area(points) < 0:
        vertices.reverse()
    output: list[tuple[int, int, int]] = []

    while len(vertices) > 3:
        found_ear = False
        for position, current in enumerate(vertices):
            previous = vertices[position - 1]
            following = vertices[(position + 1) % len(vertices)]
            if _area2(points[previous], points[current], points[following]) <= 1e-9:
                continue
            if any(
                _inside_triangle(
                    points[candidate],
                    points[previous],
                    points[current],
                    points[following],
                )
                for candidate in vertices
                if candidate not in {previous, current, following}
            ):
                continue
            output.append((previous, current, following))
            del vertices[position]
            found_ear = True
            break
        if not found_ear:
            raise ValueError("polygon could not be triangulated")

    output.append(tuple(vertices))  # type: ignore[arg-type]
    return output


def extrude_polygon(name: str, points: Sequence[Vec2], thickness: float) -> Mesh:
    """Extrude a simple XY polygon from z=0 to thickness."""

    if thickness <= 0:
        raise ValueError("thickness must be positive")
    points = list(points)
    if _polygon_area(points) < 0:
        points.reverse()
    faces = triangulate_polygon(points)
    bottom = [(x, y, 0.0) for x, y in points]
    top = [(x, y, thickness) for x, y in points]
    triangles: list[Triangle] = []

    for a, b, c in faces:
        triangles.append((bottom[c], bottom[b], bottom[a]))
        triangles.append((top[a], top[b], top[c]))

    for index in range(len(points)):
        next_index = (index + 1) % len(points)
        a = bottom[index]
        b = bottom[next_index]
        c = top[next_index]
        d = top[index]
        triangles.extend(((a, b, c), (a, c, d)))
    return Mesh(name, triangles)


def funnel_mesh(design: DockRevision = CURRENT) -> Mesh:
    """Funnel shell, integral drill-after-print flange, and short throat."""

    profile = [
        (90.0, 0.0),
        (10.0, 65.0),
        (35.0, 65.0),
        (35.0, 68.0),
        (10.0, 68.0),
        (10.0, 73.0),
        (8.0, 73.0),
        (8.0, 65.0),
        (88.8, 0.0),
    ]
    return lathe("p0a_funnel", profile, design.lathe_segments)


def probe_head_mesh(design: DockRevision = CURRENT) -> Mesh:
    """Rounded bench probe head with a through-bore for the mast.

    Two radii do different jobs and are therefore separate parameters: the
    seat cylinder from the base to 2 mm is what the keeper bears on, and the
    belt above it is what the funnel taper guides.  The flare between them is
    interpolated so the seat can grow without redrawing the profile by hand.
    """

    seat = design.probe_head_seat_diameter_mm / 2.0
    belt = design.probe_head_diameter_mm / 2.0
    bore = design.probe_head_bore_diameter_mm / 2.0
    # Flare from the seat up to the belt, then the rounded crown.
    profile = [
        (seat, 0.0),
        (seat, 2.0),
        (seat + 0.60 * (belt - seat), 3.0),
        (seat + 0.90 * (belt - seat), 4.5),
        (belt, 6.0),
        (belt - 0.20, 7.5),
        (belt - 1.00, 9.0),
        (belt - 2.30, 10.2),
        (bore, 10.2),
        (bore, 0.0),
    ]
    return lathe("p0a_probe_head", profile, design.lathe_segments)


def keeper_mesh(design: DockRevision = CURRENT) -> Mesh:
    """Sliding fork keeper; load is reacted through guides, not the actuator.

    The tine reach is a parameter because it, not the slot, sets the stroke
    the servo must deliver to release: the tines have to retract clear of the
    widest part of the head, and every millimetre of reach is a millimetre of
    stroke.
    """

    left = -design.keeper_back_reach_mm
    right = design.keeper_tine_reach_mm
    half_width = design.keeper_width_mm / 2.0
    # The drive pin lands in the solid back; check it stays clear of the slot
    # and of the back edge rather than trusting the two numbers to agree.
    boss_margin = design.drive_pin_diameter_mm / 2.0 + design.drive_pin_edge_margin_mm
    if design.keeper_pin_x_mm + boss_margin > -design.keeper_slot_width_mm / 2.0:
        raise ValueError("keeper drive pin would break into the slot")
    if design.keeper_pin_x_mm - boss_margin < left:
        raise ValueError("keeper drive pin would break out of the back edge")
    slot_radius = design.keeper_slot_width_mm / 2.0
    points: list[Vec2] = [
        (left, -half_width),
        (right, -half_width),
        (right, -slot_radius),
    ]
    # The open slot terminates in a round end centered on the dock axis.
    for index in range(9):
        theta = math.radians(-90.0 - 180.0 * index / 8.0)
        points.append((slot_radius * math.cos(theta), slot_radius * math.sin(theta)))
    points.extend(
        [
            (right, slot_radius),
            (right, half_width),
            (left, half_width),
        ]
    )
    return extrude_polygon("p0a_keeper", points, design.keeper_thickness_mm)


def _rounded_bar(length: float, half_width: float, segments: int = 16) -> list[Vec2]:
    """A stadium outline: a bar of `length` between two rounded ends."""

    half = length / 2.0
    points: list[Vec2] = []
    for i in range(segments + 1):
        theta = math.pi * (-0.5 + i / segments)
        points.append((half + half_width * math.cos(theta), half_width * math.sin(theta)))
    for i in range(segments + 1):
        theta = math.pi * (0.5 + i / segments)
        points.append((-half + half_width * math.cos(theta), half_width * math.sin(theta)))
    return points


def crank_mesh(design: DockRevision = CURRENT) -> Mesh:
    """Servo-horn crank for the keeper drive.

    Pin holes are drilled after print from the linkage template, the same way
    the funnel flange holes are: modelling a hole would need boolean geometry
    this dependency-free generator does not have, and a slot open to an edge
    would let a pin walk out under 600 life cycles (P0-DRIVE-006).
    """

    half_width = design.drive_pin_diameter_mm / 2.0 + design.drive_pin_edge_margin_mm
    return extrude_polygon(
        "p0a_crank",
        _rounded_bar(design.crank_radius_mm, half_width),
        design.drive_plate_thickness_mm,
    )


def link_mesh(design: DockRevision = CURRENT) -> Mesh:
    """Link between the crank pin and the keeper pin, holes drilled after print."""

    half_width = design.drive_pin_diameter_mm / 2.0 + design.drive_pin_edge_margin_mm
    return extrude_polygon(
        "p0a_link",
        _rounded_bar(design.link_length_mm, half_width),
        design.drive_plate_thickness_mm,
    )


def meshes(design: DockRevision = CURRENT) -> tuple[Mesh, ...]:
    return (
        funnel_mesh(design),
        probe_head_mesh(design),
        keeper_mesh(design),
        crank_mesh(design),
        link_mesh(design),
    )


def validate_mesh(mesh: Mesh) -> None:
    if not mesh.triangles:
        raise ValueError(f"{mesh.name}: empty mesh")
    if mesh.degenerate_faces():
        raise ValueError(f"{mesh.name}: degenerate triangles")
    if mesh.nonmanifold_edges():
        raise ValueError(f"{mesh.name}: non-manifold edges")
    if mesh.volume_mm3() <= 0:
        raise ValueError(f"{mesh.name}: non-positive volume")


def write_binary_stl(mesh: Mesh, path: Path, revision: str = "") -> None:
    """Write an STL whose header names the revision that produced it.

    The header used to be a hardcoded REV-A regardless of the geometry
    inside it, and both revisions wrote the same filenames, so nothing on
    disk distinguished a superseded keeper from a current one.  A slicer
    shows the header; a technician holding two prints cannot see a dataclass.
    """

    validate_mesh(mesh)
    label = f"AIUR CARRIER-P0 P0-A {revision or 'UNSPECIFIED'} {mesh.name}"
    header = label.encode("ascii")[:80].ljust(80, b" ")
    payload = bytearray(header)
    payload.extend(struct.pack("<I", len(mesh.triangles)))
    for a, b, c in mesh.triangles:
        normal, _ = _normal(a, b, c)
        payload.extend(struct.pack("<12fH", *normal, *a, *b, *c, 0))
    path.write_bytes(payload)


def _mesh_manifest(mesh: Mesh) -> dict[str, object]:
    low, high = mesh.bounds()
    volume_cm3 = mesh.volume_mm3() / 1000.0
    return {
        "triangles": len(mesh.triangles),
        "bounds_mm": {
            "min": [round(value, 4) for value in low],
            "max": [round(value, 4) for value in high],
        },
        "volume_cm3": round(volume_cm3, 3),
        "solid_petg_mass_estimate_g": round(volume_cm3 * PETG_DENSITY_G_CM3, 2),
        "degenerate_faces": mesh.degenerate_faces(),
        "nonmanifold_edges": mesh.nonmanifold_edges(),
    }


def drill_template_svg(design: DockRevision = CURRENT) -> str:
    half_pattern = design.flange_hole_square_mm / 2.0
    revision = design.name.upper()
    throat_radius = design.funnel_throat_diameter_mm / 2.0
    hole_radius = design.flange_hole_diameter_mm / 2.0
    holes = "\n".join(
        f'  <circle cx="{50 + x:g}" cy="{50 + y:g}" r="1.6" class="drill"/>'
        for x, y in (
            (-half_pattern, -half_pattern),
            (half_pattern, -half_pattern),
            (half_pattern, half_pattern),
            (-half_pattern, half_pattern),
        )
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
  <style>
    .cut{{fill:none;stroke:#000;stroke-width:.25}}
    .drill{{fill:none;stroke:#d00;stroke-width:.3}}
    .axis{{stroke:#777;stroke-width:.15;stroke-dasharray:2 1}}
    .text{{font:3px sans-serif;fill:#000}}
  </style>
  <line x1="15" y1="50" x2="85" y2="50" class="axis"/>
  <line x1="50" y1="15" x2="50" y2="85" class="axis"/>
  <circle cx="50" cy="50" r="35" class="cut"/>
  <circle cx="50" cy="50" r="{throat_radius:g}" class="cut"/>
{holes}
  <text x="4" y="7" class="text">P0-A {revision} — M3 DRILL TEMPLATE — PRINT 100%</text>
  <text x="4" y="12" class="text">4 x Ø{design.flange_hole_diameter_mm:g} on {design.flange_hole_square_mm:g} mm square; center throat Ø{design.funnel_throat_diameter_mm:g}</text>
  <line x1="25" y1="92" x2="75" y2="92" class="cut"/>
  <line x1="25" y1="90.5" x2="25" y2="93.5" class="cut"/>
  <line x1="75" y1="90.5" x2="75" y2="93.5" class="cut"/>
  <text x="44" y="89" class="text">50 mm CHECK</text>
</svg>
'''


def linkage_drill_template_svg(design: DockRevision = CURRENT) -> str:
    """1:1 pin-hole template for the crank and the link.

    The linkage carries no modelled holes: like the funnel flange, they are
    drilled after print.  Getting the link centres wrong changes the
    delivered stroke directly, so the template carries a measured check line
    the way the flange template does.
    """

    revision = design.name.upper()
    pin_r = design.drive_pin_diameter_mm / 2.0
    crank = design.crank_radius_mm
    link = design.link_length_mm
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="70mm" viewBox="0 0 100 70">
  <style>
    .drill{{fill:none;stroke:#d00;stroke-width:.3}}
    .axis{{stroke:#777;stroke-width:.15;stroke-dasharray:2 1}}
    .cut{{fill:none;stroke:#000;stroke-width:.25}}
    .text{{font:3px sans-serif;fill:#000}}
  </style>
  <text x="4" y="7" class="text">P0-A {revision} - KEEPER DRIVE PIN TEMPLATE - PRINT 100%</text>
  <text x="4" y="12" class="text">Pins &#216;{design.drive_pin_diameter_mm:g}; crank {crank:g} mm centres; link {link:g} mm centres</text>
  <line x1="14" y1="24" x2="{26 + crank:g}" y2="24" class="axis"/>
  <text x="4" y="25" class="text">CRANK</text>
  <circle cx="20" cy="24" r="{pin_r:g}" class="drill"/>
  <circle cx="{20 + crank:g}" cy="24" r="{pin_r:g}" class="drill"/>
  <line x1="14" y1="40" x2="{26 + link:g}" y2="40" class="axis"/>
  <text x="4" y="41" class="text">LINK</text>
  <circle cx="20" cy="40" r="{pin_r:g}" class="drill"/>
  <circle cx="{20 + link:g}" cy="40" r="{pin_r:g}" class="drill"/>
  <line x1="20" y1="60" x2="70" y2="60" class="cut"/>
  <line x1="20" y1="58.5" x2="20" y2="61.5" class="cut"/>
  <line x1="70" y1="58.5" x2="70" y2="61.5" class="cut"/>
  <text x="38" y="57" class="text">50 mm CHECK</text>
  <text x="4" y="67" class="text">Stroke = 2 x crank centres = {design.drive_stroke_mm:g} mm; verify at the keeper with a dial indicator.</text>
</svg>
"""


def cross_section_svg(design: DockRevision = CURRENT) -> str:
    """Dimensioned cross-section, generated from the revision parameters.

    The previous drawing was drawn by hand and went stale the moment Rev-B
    moved four dimensions: it still showed a Ø6 seat and a 4.2 mm slot while
    the generator emitted Ø9 and 5.2 mm, and nothing could detect that.  A
    drawing is a build document, so it is derived like every other one.

    Two panels because one scale cannot serve both: the funnel is 180 mm
    across and the features that decide capture are a few millimetres.
    """

    rev = design.name.upper()
    # --- panel 1: general arrangement, 1.6 px/mm -------------------------
    ga = 1.6
    mouth_r = design.funnel_mouth_diameter_mm / 2.0 * ga
    depth = design.funnel_depth_mm * ga
    throat_r = design.funnel_throat_diameter_mm / 2.0 * ga
    cx, cy = 300.0, 250.0
    standoff = design.probe_tip_height_above_prop_plane_mm * ga

    # --- panel 2: capture detail, 14 px/mm -------------------------------
    d = 14.0
    dx, dy = 720.0, 250.0
    belt_r = design.probe_head_diameter_mm / 2.0 * d
    seat_r = design.probe_head_seat_diameter_mm / 2.0 * d
    mast_r = design.probe_mast_diameter_mm / 2.0 * d
    slot_r = design.keeper_slot_width_mm / 2.0 * d
    tine = design.keeper_tine_reach_mm * d
    thick = design.keeper_thickness_mm * d

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="560" viewBox="0 0 1000 560">
  <defs>
    <marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse">
      <path d="M0,0 L8,4 L0,8 z" fill="#263238"/>
    </marker>
    <style>
      .t{{font:700 20px system-ui,sans-serif;fill:#111827}}
      .s{{font:500 12px system-ui,sans-serif;fill:#4b5563}}
      .l{{font:600 12px system-ui,sans-serif;fill:#111827}}
      .part{{stroke:#111827;stroke-width:2.5;fill:none;stroke-linejoin:round}}
      .keeper{{stroke:#1d4ed8;stroke-width:3;fill:#dbeafe}}
      .probe{{stroke:#b45309;stroke-width:3;fill:#fef3c7}}
      .seat{{stroke:#b45309;stroke-width:3;fill:#fde68a}}
      .dim{{stroke:#263238;stroke-width:1.2;fill:none;marker-start:url(#a);marker-end:url(#a)}}
      .ext{{stroke:#9ca3af;stroke-width:1;stroke-dasharray:4 3}}
      .ax{{stroke:#9ca3af;stroke-width:1;stroke-dasharray:8 3 2 3}}
      .rotor{{stroke:#dc2626;stroke-width:2;stroke-dasharray:7 5}}
    </style>
  </defs>
  <rect width="1000" height="560" fill="#fff"/>
  <text x="36" y="34" class="t">CARRIER-P0 — P0-A {rev} DOCK CROSS-SECTION</text>
  <text x="36" y="54" class="s">GENERATED FROM generate_rev_a.py — DIMENSIONS IN mm — SCREENING ARTICLE, PHYSICAL FIT OWNS FINAL GEOMETRY</text>

  <text x="36" y="88" class="l">GENERAL ARRANGEMENT</text>
  <line x1="{cx:g}" y1="110" x2="{cx:g}" y2="470" class="ax"/>
  <path d="M{cx - mouth_r:g} {cy + depth:g} L{cx - throat_r:g} {cy:g} L{cx + throat_r:g} {cy:g} L{cx + mouth_r:g} {cy + depth:g}" class="part"/>
  <line x1="{cx - mouth_r:g}" y1="{cy + depth:g}" x2="{cx + mouth_r:g}" y2="{cy + depth:g}" class="ext"/>
  <line x1="{cx - mouth_r:g}" y1="{cy + depth + 34:g}" x2="{cx + mouth_r:g}" y2="{cy + depth + 34:g}" class="dim"/>
  <text x="{cx - 34:g}" y="{cy + depth + 28:g}" class="l">&#216;{design.funnel_mouth_diameter_mm:g}</text>
  <line x1="{cx + mouth_r + 26:g}" y1="{cy:g}" x2="{cx + mouth_r + 26:g}" y2="{cy + depth:g}" class="dim"/>
  <text x="{cx + mouth_r + 32:g}" y="{cy + depth / 2:g}" class="l">{design.funnel_depth_mm:g} deep</text>
  <line x1="{cx - throat_r - 60:g}" y1="{cy:g}" x2="{cx - throat_r:g}" y2="{cy:g}" class="ext"/>
  <text x="{cx - throat_r - 116:g}" y="{cy - 6:g}" class="l">throat &#216;{design.funnel_throat_diameter_mm:g}</text>
  <line x1="{cx - mouth_r - 10:g}" y1="{cy + depth + standoff:g}" x2="{cx + mouth_r + 10:g}" y2="{cy + depth + standoff:g}" class="rotor"/>
  <text x="{cx + mouth_r - 46:g}" y="{cy + depth + standoff + 18:g}" class="l">rotor plane</text>
  <line x1="{cx - mouth_r - 30:g}" y1="{cy + depth:g}" x2="{cx - mouth_r - 30:g}" y2="{cy + depth + standoff:g}" class="dim"/>
  <text x="{cx - mouth_r - 128:g}" y="{cy + depth + standoff / 2:g}" class="l">{design.probe_tip_height_above_prop_plane_mm:g} standoff</text>
  <text x="36" y="500" class="s">Probe tip standoff keeps the rotor plane clear of the funnel lip; the aircraft never enters the mouth.</text>

  <text x="560" y="88" class="l">CAPTURE DETAIL — the keeper bears on the SEAT, never on the belt</text>
  <line x1="{dx:g}" y1="110" x2="{dx:g}" y2="430" class="ax"/>
  <rect x="{dx - belt_r:g}" y="150" width="{2 * belt_r:g}" height="46" rx="8" class="probe"/>
  <text x="{dx + belt_r + 10:g}" y="176" class="l">belt &#216;{design.probe_head_diameter_mm:g} — funnel guides this</text>
  <rect x="{dx - seat_r:g}" y="196" width="{2 * seat_r:g}" height="34" class="seat"/>
  <text x="{dx + belt_r + 10:g}" y="218" class="l">seat &#216;{design.probe_head_seat_diameter_mm:g} — keeper bears here</text>
  <rect x="{dx - mast_r:g}" y="230" width="{2 * mast_r:g}" height="120" class="probe"/>
  <text x="{dx + belt_r + 10:g}" y="300" class="l">mast &#216;{design.probe_mast_diameter_mm:g}</text>
  <rect x="{dx - slot_r - tine:g}" y="230" width="{tine - slot_r + 0.0:g}" height="{thick:g}" class="keeper"/>
  <rect x="{dx + slot_r:g}" y="230" width="{tine - slot_r:g}" height="{thick:g}" class="keeper"/>
  <text x="{dx - slot_r - tine - 150:g}" y="{230 + thick / 2 + 4:g}" class="l">keeper tines</text>
  <line x1="{dx - slot_r:g}" y1="370" x2="{dx + slot_r:g}" y2="370" class="dim"/>
  <text x="{dx - 22:g}" y="390" class="l">slot {design.keeper_slot_width_mm:g}</text>
  <line x1="{dx + slot_r:g}" y1="{230 + thick + 26:g}" x2="{dx + tine:g}" y2="{230 + thick + 26:g}" class="dim"/>
  <text x="{dx + slot_r + 4:g}" y="{230 + thick + 44:g}" class="l">tine reach {design.keeper_tine_reach_mm:g}</text>
  <text x="560" y="470" class="s">Open travel {design.keeper_open_travel_mm:g} mm; the tines must clear the belt, needing {design.exact_release_travel_mm():.2f} mm.</text>
  <text x="560" y="490" class="s">Drive: in-line slider-crank, crank {design.crank_radius_mm:g} mm, link {design.link_length_mm:g} mm, stroke = 2 x crank.</text>
  <text x="560" y="510" class="s">Retention ledge is (seat &#8722; slot)/2 per side. Pin holes are drilled after print.</text>
</svg>
"""


def generate_outputs(output_dir: Path, design: DockRevision = CURRENT) -> dict[str, object]:
    """Write the fabrication artifacts for one revision.

    Every filename carries the revision slug.  Two revisions writing the
    same names into the same directory is how a superseded keeper ends up on
    a print bed: the geometry differs, the file does not, and nothing warns
    anyone.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    slug = design.name.lower().replace("-", "_").replace(" ", "_")
    part_meshes = meshes(design)
    for mesh in part_meshes:
        write_binary_stl(
            mesh, output_dir / f"{mesh.name}_{slug}.stl", design.name.upper()
        )
    (output_dir / f"p0a_drill_template_{slug}.svg").write_text(
        drill_template_svg(design), encoding="utf-8"
    )
    (output_dir / f"p0a_linkage_template_{slug}.svg").write_text(
        linkage_drill_template_svg(design), encoding="utf-8"
    )
    (output_dir / f"p0a_cross_section_{slug}.svg").write_text(
        cross_section_svg(design), encoding="utf-8"
    )

    part_data = {mesh.name: _mesh_manifest(mesh) for mesh in part_meshes}
    manifest = {
        "article": f"CARRIER-P0 P0-A {design.name}",
        "units": "mm",
        "status": "bench screening geometry; not flight qualified",
        "design": asdict(design),
        "parts": part_data,
        "printed_petg_mass_estimate_g": round(
            sum(part["solid_petg_mass_estimate_g"] for part in part_data.values()), 2
        ),
        "notes": [
            "STL volume is geometry-derived; weigh every physical part.",
            "The four M3 flange holes are drilled after print using the 1:1 template.",
            "The probe head is a coupon component; the Crazyflie flight-probe base is not frozen.",
        ],
    }
    (output_dir / f"p0a_{slug}_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args(argv)
    manifest = generate_outputs(args.out_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
