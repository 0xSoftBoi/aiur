#!/usr/bin/env python3
"""Generate deterministic CARRIER-P0 P0-A Rev-A fabrication geometry.

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
class RevA:
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
    probe_mast_diameter_mm: float = 3.0
    probe_head_bore_diameter_mm: float = 3.2
    probe_tip_height_above_prop_plane_mm: float = 110.0
    keeper_length_mm: float = 28.0
    keeper_width_mm: float = 18.0
    keeper_thickness_mm: float = 2.5
    keeper_slot_width_mm: float = 4.2
    keeper_nominal_open_travel_mm: float = 11.0
    lathe_segments: int = 64


REV_A = RevA()
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


def funnel_mesh(design: RevA = REV_A) -> Mesh:
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


def probe_head_mesh(design: RevA = REV_A) -> Mesh:
    """Rounded bench probe head with a 3.2 mm through-bore for a 3 mm mast."""

    profile = [
        (3.0, 0.0),
        (3.0, 2.0),
        (4.8, 3.0),
        (5.7, 4.5),
        (6.0, 6.0),
        (5.8, 7.5),
        (5.0, 9.0),
        (3.7, 10.2),
        (1.6, 10.2),
        (1.6, 0.0),
    ]
    return lathe("p0a_probe_head", profile, design.lathe_segments)


def keeper_mesh(design: RevA = REV_A) -> Mesh:
    """Sliding fork keeper; load is reacted through guides, not the actuator."""

    left = -20.0
    right = 8.0
    half_width = design.keeper_width_mm / 2.0
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


def meshes(design: RevA = REV_A) -> tuple[Mesh, ...]:
    return funnel_mesh(design), probe_head_mesh(design), keeper_mesh(design)


def validate_mesh(mesh: Mesh) -> None:
    if not mesh.triangles:
        raise ValueError(f"{mesh.name}: empty mesh")
    if mesh.degenerate_faces():
        raise ValueError(f"{mesh.name}: degenerate triangles")
    if mesh.nonmanifold_edges():
        raise ValueError(f"{mesh.name}: non-manifold edges")
    if mesh.volume_mm3() <= 0:
        raise ValueError(f"{mesh.name}: non-positive volume")


def write_binary_stl(mesh: Mesh, path: Path) -> None:
    validate_mesh(mesh)
    header = f"AIUR CARRIER-P0 P0-A REV-A {mesh.name}".encode("ascii")[:80].ljust(80, b" ")
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


def drill_template_svg(design: RevA = REV_A) -> str:
    half_pattern = design.flange_hole_square_mm / 2.0
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
  <circle cx="50" cy="50" r="8" class="cut"/>
{holes}
  <text x="4" y="7" class="text">P0-A REV-A — M3 DRILL TEMPLATE — PRINT 100%</text>
  <text x="4" y="12" class="text">4 x Ø3.2 on 40 mm square; center throat Ø16</text>
  <line x1="25" y1="92" x2="75" y2="92" class="cut"/>
  <line x1="25" y1="90.5" x2="25" y2="93.5" class="cut"/>
  <line x1="75" y1="90.5" x2="75" y2="93.5" class="cut"/>
  <text x="44" y="89" class="text">50 mm CHECK</text>
</svg>
'''


def generate_outputs(output_dir: Path, design: RevA = REV_A) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    part_meshes = meshes(design)
    for mesh in part_meshes:
        write_binary_stl(mesh, output_dir / f"{mesh.name}.stl")
    (output_dir / "p0a_drill_template.svg").write_text(
        drill_template_svg(design), encoding="utf-8"
    )

    part_data = {mesh.name: _mesh_manifest(mesh) for mesh in part_meshes}
    manifest = {
        "article": "CARRIER-P0 P0-A Rev-A",
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
    (output_dir / "p0a_rev_a_manifest.json").write_text(
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
