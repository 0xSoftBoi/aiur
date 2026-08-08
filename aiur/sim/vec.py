"""Minimal 3D vector math for the CARRIER-P0 digital twin.

Pure stdlib on purpose: the twin must run in the dependency-free engineering
CI.  Vectors are immutable so simulation state can never be mutated in place
by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    def __neg__(self) -> "Vec3":
        return Vec3(-self.x, -self.y, -self.z)

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def lateral_norm(self) -> float:
        """Horizontal (x/y) magnitude; the docking problem is z-aligned."""

        return math.hypot(self.x, self.y)

    def with_z(self, z: float) -> "Vec3":
        return Vec3(self.x, self.y, z)

    def lateral(self) -> "Vec3":
        return Vec3(self.x, self.y, 0.0)

    def clamped(self, max_norm: float) -> "Vec3":
        """Return this vector scaled down so its norm never exceeds max_norm."""

        if max_norm < 0:
            raise ValueError("max_norm must be non-negative")
        norm = self.norm()
        if norm <= max_norm or norm == 0.0:
            return self
        return self * (max_norm / norm)


ZERO = Vec3()
