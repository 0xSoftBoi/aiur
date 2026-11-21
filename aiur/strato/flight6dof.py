"""Six-degree-of-freedom flight of the hull architecture.

Rigid body plus added mass, in body axes (x forward, y right, z down) with
the origin at the centre of volume.  The formulation is the standard one for
vehicles moving in a heavy fluid [cited: Fossen, *Handbook of Marine Craft
Hydrodynamics*, ch. 6 and 8; Li & Nahon 2007 for the airship terms]:

    M nu_r_dot + C_RB(nu_r) nu_r + C_A(nu_r) nu_r = tau_static + tau_aero + tau_thrust

with ``nu_r`` the velocity *relative to the air*.  Three things follow that
matter for a stratospheric airship and are easy to get wrong:

* The Munk moment is not an add-on.  It falls out of ``C_A`` as
  ``(k2 - k1) m_displaced u v`` and is the dominant yaw/pitch moment.
* A neutrally buoyant body is carried by a gust almost exactly: its rigid
  mass equals the displaced mass, so the pressure-gradient force of an
  accelerating air mass accelerates the vehicle with it.  Working in
  relative velocity captures that with no extra term.
* At 20 km the dynamic pressure at cruise is a few pascals.  Fins are weak,
  and the only moment that does not depend on airspeed is thrust vectoring.

Run ``python -m aiur.strato.flight6dof`` for the handling scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import sys

from .atmosphere import G0, Gust, isa
from .hull import Hull

Vec = tuple


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _add(*vs):
    return tuple(sum(c) for c in zip(*vs))


def _scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def quat_to_matrix(q):
    """Rotation matrix body -> NED from a unit quaternion (w, x, y, z)."""

    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


def _mat_vec(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def _mat_t_vec(m, v):
    return tuple(m[0][i] * v[0] + m[1][i] * v[1] + m[2][i] * v[2] for i in range(3))


def euler_from_quat(q):
    """(roll, pitch, yaw) in radians."""

    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def quat_from_euler(roll, pitch, yaw):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy)


def _invert(a):
    n = len(a)
    m = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        d = m[c][c]
        m[c] = [x / d for x in m[c]]
        for r in range(n):
            if r != c and m[r][c] != 0.0:
                f = m[r][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [row[n:] for row in m]


@dataclass
class Airframe:
    """Everything the equations of motion need about one vehicle."""

    hull: Hull
    mass_kg: float                 # total, including lift gas
    altitude_m: float
    cg_below_cv_m: float
    cg_aft_of_cv_m: float = 0.0
    fin_area_total_m2: float = 0.0
    fin_station_frac: float = 0.86  # fin centre of pressure, fraction of length
    fin_lift_slope: float = 2.2     # per rad on a fin pair incl. carry-over
    ruddervator_fraction: float = 0.0   # movable part of each fin pair's lift
    crossflow_cd: float = 1.0
    drag_multiplier: float = 1.8
    thruster_station_frac: float = 1.0  # stern
    thruster_z_m: float = 0.0
    max_thrust_n: float = 5.0
    gimbal_limit_rad: float = math.radians(25.0)
    thrust_lag_s: float = 0.6
    gimbal_rate_rad_s: float = math.radians(60.0)

    def __post_init__(self) -> None:
        self.air = isa(self.altitude_m)
        h = self.hull
        rho = self.air.density_kg_m3
        k1, k2, kp = h.lamb_factors()
        self.m_disp = rho * h.volume_m3
        kd2 = h.displaced_inertia_coeff()
        self.a11 = (k1 * self.m_disp, k2 * self.m_disp, k2 * self.m_disp)
        self.a22 = (0.0, kp * self.m_disp * kd2, kp * self.m_disp * kd2)
        self.rg = (-self.cg_aft_of_cv_m, 0.0, self.cg_below_cv_m)
        # Rigid inertia about the centre of volume: equipment is strung along
        # the spine, so pitch/yaw radius of gyration tracks the hull's.
        r = h.radius_m
        ixx = self.mass_kg * (0.55 * r) ** 2 + self.mass_kg * self.cg_below_cv_m**2
        iyy = self.mass_kg * kd2 * 1.05 + self.mass_kg * self.cg_below_cv_m**2
        izz = self.mass_kg * kd2 * 1.05
        self.inertia = (ixx, iyy, izz)
        m, (xg, yg, zg) = self.mass_kg, self.rg
        big = [[0.0] * 6 for _ in range(6)]
        for i in range(3):
            big[i][i] = m + self.a11[i]
            big[3 + i][3 + i] = self.inertia[i] + self.a22[i]
        # -m S(rg) upper right, m S(rg) lower left
        s = ((0, -zg, yg), (zg, 0, -xg), (-yg, xg, 0))
        for i in range(3):
            for j in range(3):
                big[i][3 + j] = -m * s[i][j]
                big[3 + i][j] = m * s[i][j]
        self.m_inv = _invert(big)
        self.x_cv = h.centre_of_volume_m
        self.x_fin = self.x_cv - self.fin_station_frac * h.length_m       # body x (negative = aft)
        self.x_thr = self.x_cv - self.thruster_station_frac * h.length_m
        self.strips = [(self.x_cv - x, rad, dx) for x, rad, dx in h.stations(20)]
        #: Rotational gust (q_g, r_g): the velocity gradient of a frozen gust
        #: field sweeping along the hull.  A uniform gust carries a neutrally
        #: buoyant hull with it and disturbs nothing; the *gradient* is what
        #: puts different crossflow on the nose and the tail.
        self.gust_rot = (0.0, 0.0)
        self.buoyancy_n = self.m_disp * G0
        self.weight_n = self.mass_kg * G0

    @classmethod
    def from_design(cls, dp, **over) -> "Airframe":
        g = dp.geometry
        hull = Hull(g["volume_m3"], g["fineness"])
        gross = dp.mass_kg["gross"]
        film = dp.mass_kg["envelope_film"] + dp.mass_kg["seams_patches"] + dp.mass_kg["fins"]
        suspended = gross - film
        cg_z = suspended * (hull.radius_m + 0.25) / (gross + dp.lift["gas_mass_kg"])
        kw = dict(hull=hull, mass_kg=gross + dp.lift["gas_mass_kg"] + dp.lift["margin_kg"],
                  altitude_m=dp.mission["float_altitude_m"], cg_below_cv_m=cg_z,
                  fin_area_total_m2=g["fin_area_total_m2"],
                  max_thrust_n=dp.propulsion["dash"]["thrust_n"] * dp.propulsion["n_props"])
        kw.update(over)
        return cls(**kw)


@dataclass
class State:
    pos: Vec = (0.0, 0.0, 0.0)             # NED metres (z down)
    quat: Vec = (1.0, 0.0, 0.0, 0.0)
    vel: Vec = (0.0, 0.0, 0.0)             # body, relative to air
    rate: Vec = (0.0, 0.0, 0.0)
    thrust_n: float = 0.0
    gimbal_yaw: float = 0.0
    gimbal_pitch: float = 0.0


@dataclass
class Controls:
    thrust_n: float = 0.0
    gimbal_yaw: float = 0.0      # positive pushes the stern to starboard
    gimbal_pitch: float = 0.0    # positive pushes the stern down
    rudder: float = 0.0          # -1..1, only if ruddervator_fraction > 0
    elevator: float = 0.0


def forces(af: Airframe, st: State, ctl: Controls):
    """Generalised force (X, Y, Z, K, M, N) excluding Coriolis terms."""

    rho = af.air.density_kg_m3
    u, v, w = st.vel
    p, q, r = st.rate
    # Aerodynamic terms see body rate relative to the rotating air.
    q, r = q - af.gust_rot[0], r - af.gust_rot[1]
    rot = quat_to_matrix(st.quat)
    # static
    down_b = _mat_t_vec(rot, (0.0, 0.0, 1.0))
    f = _scale(down_b, af.weight_n - af.buoyancy_n)
    mo = _cross(af.rg, _scale(down_b, af.weight_n))
    # axial drag
    h = af.hull
    speed = math.sqrt(u * u + v * v + w * w)
    re = rho * max(abs(u), 0.05) * h.length_m / af.air.viscosity_pa_s
    cd = h.drag_coefficient(re) * af.drag_multiplier
    fx = -0.5 * rho * abs(u) * u * h.reference_area_m2 * cd
    fy = fz = 0.0
    mx = my = mz = 0.0
    # viscous crossflow on hull strips
    for xb, rad, dx in af.strips:
        vc = v + r * xb
        wc = w - q * xb
        mag = math.hypot(vc, wc)
        k = -0.5 * rho * af.crossflow_cd * 2.0 * rad * dx * mag
        dfy, dfz = k * vc, k * wc
        fy += dfy
        fz += dfz
        my += -xb * dfz
        mz += xb * dfy
    # fins (one pair acts in each plane)
    if af.fin_area_total_m2 > 0.0:
        s_pair = 0.5 * af.fin_area_total_m2
        xf = af.x_fin
        for axis in (0, 1):
            cross = (v + r * xf) if axis == 0 else (w - q * xf)
            defl = (ctl.rudder if axis == 0 else ctl.elevator) * af.ruddervator_fraction
            vf = math.hypot(u, cross)
            limit = vf * math.tan(math.radians(15.0))
            # Control deflection shifts the effective incidence by up to 15 deg.
            eff = cross + defl * limit
            lin = max(-limit, min(limit, eff))
            sep = eff - lin
            force = -0.5 * rho * s_pair * (af.fin_lift_slope * vf * lin + 1.2 * abs(sep) * sep)
            if axis == 0:
                fy += force
                mz += xf * force
            else:
                fz += force
                my += -xf * force
        # roll damping from all four fins
        span_arm = h.radius_m * 1.3
        mx += -0.5 * rho * af.fin_area_total_m2 * 1.2 * abs(p * span_arm) * (p * span_arm) * span_arm
    # thrust, gimballed at the stern
    t = st.thrust_n
    cy, sy = math.cos(st.gimbal_yaw), math.sin(st.gimbal_yaw)
    cp, sp = math.cos(st.gimbal_pitch), math.sin(st.gimbal_pitch)
    ft = (t * cp * cy, t * cp * sy, t * sp)
    mt = _cross((af.x_thr, 0.0, af.thruster_z_m), ft)
    force = (f[0] + fx + ft[0], f[1] + fy + ft[1], f[2] + fz + ft[2])
    moment = (mo[0] + mx + mt[0], mo[1] + my + mt[1], mo[2] + mz + mt[2])
    return force, moment


def derivative(af: Airframe, st: State, ctl: Controls, wind_ned: Vec):
    force, moment = forces(af, st, ctl)
    v, om = st.vel, st.rate
    m = af.mass_kg
    # Rigid-body Coriolis/centripetal
    f_rb = _scale(_add(_cross(om, v), _cross(om, _cross(om, af.rg))), m)
    iw = (af.inertia[0] * om[0], af.inertia[1] * om[1], af.inertia[2] * om[2])
    m_rb = _add(_cross(om, iw), _scale(_cross(af.rg, _cross(om, v)), m))
    # Added-mass Coriolis: the second moment term is the Munk moment.
    a11v = (af.a11[0] * v[0], af.a11[1] * v[1], af.a11[2] * v[2])
    a22w = (af.a22[0] * om[0], af.a22[1] * om[1], af.a22[2] * om[2])
    f_a = _cross(om, a11v)
    m_a = _add(_cross(v, a11v), _cross(om, a22w))
    rhs = [force[i] - f_rb[i] - f_a[i] for i in range(3)] + \
          [moment[i] - m_rb[i] - m_a[i] for i in range(3)]
    acc = [sum(af.m_inv[i][j] * rhs[j] for j in range(6)) for i in range(6)]
    rot = quat_to_matrix(st.quat)
    pos_dot = _add(_mat_vec(rot, v), wind_ned)
    qw, qx, qy, qz = st.quat
    p, q, r = om
    quat_dot = (0.5 * (-qx * p - qy * q - qz * r), 0.5 * (qw * p + qy * r - qz * q),
                0.5 * (qw * q - qx * r + qz * p), 0.5 * (qw * r + qx * q - qy * p))
    return pos_dot, quat_dot, tuple(acc[:3]), tuple(acc[3:])


def step(af: Airframe, st: State, ctl: Controls, wind_ned: Vec, dt: float) -> State:
    """Advance one RK4 step; actuators are first-order/rate-limited."""

    def shift(s: State, d, h: float) -> State:
        pd, qd, vd, wd = d
        q = tuple(s.quat[i] + qd[i] * h for i in range(4))
        n = math.sqrt(sum(c * c for c in q))
        return State(_add(s.pos, _scale(pd, h)), tuple(c / n for c in q),
                     _add(s.vel, _scale(vd, h)), _add(s.rate, _scale(wd, h)),
                     s.thrust_n, s.gimbal_yaw, s.gimbal_pitch)

    k1 = derivative(af, st, ctl, wind_ned)
    k2 = derivative(af, shift(st, k1, dt / 2), ctl, wind_ned)
    k3 = derivative(af, shift(st, k2, dt / 2), ctl, wind_ned)
    k4 = derivative(af, shift(st, k3, dt), ctl, wind_ned)
    comb = tuple(tuple((a + 2 * b + 2 * c + d) / 6.0 for a, b, c, d in zip(*parts))
                 for parts in zip(k1, k2, k3, k4))
    new = shift(st, comb, dt)
    lim = af.gimbal_limit_rad
    tgt_t = max(0.0, min(af.max_thrust_n, ctl.thrust_n))
    new.thrust_n = st.thrust_n + (tgt_t - st.thrust_n) * min(1.0, dt / af.thrust_lag_s)
    for name, cmd in (("gimbal_yaw", ctl.gimbal_yaw), ("gimbal_pitch", ctl.gimbal_pitch)):
        cur = getattr(st, name)
        tgt = max(-lim, min(lim, cmd))
        delta = max(-af.gimbal_rate_rad_s * dt, min(af.gimbal_rate_rad_s * dt, tgt - cur))
        setattr(new, name, cur + delta)
    return new


# --- attitude / speed controller ---------------------------------------------

@dataclass
class FlightController:
    """Heading, pitch and airspeed hold through one gimballed stern thruster.

    Moment demand is computed as a PD law on attitude error and converted to
    a gimbal angle through the *current* thrust, because the control moment
    is thrust times lever arm: no thrust, no authority.  The thrust command
    therefore carries a floor whenever attitude error is large - a vehicle
    that idles its propeller to save energy must not also give up its rudder.
    """

    yaw_inertia: float
    pitch_inertia: float
    lever_arm_m: float
    max_thrust_n: float
    gimbal_limit_rad: float
    natural_freq_rad_s: float = 0.35
    damping: float = 0.9
    speed_gain_n_per_m_s: float = 2.0
    speed_integral_n_per_m: float = 0.15
    authority_floor: float = 0.30
    use_fins: bool = False
    #: Integral gain as a fraction of wn^3.  At cruise the Munk moment, the
    #: fins and the pendulum nearly cancel in pitch, so the airframe has
    #: almost no stiffness of its own and a PD loop holds whatever attitude
    #: it happens to be in (mission6 found it flying 9 degrees nose-down
    #: against a 1 kg lift surplus).  The integrator removes that offset.
    integral_fraction: float = 0.10
    _int: float = 0.0
    _yaw_int: float = 0.0
    _pitch_int: float = 0.0
    saturated_s: float = 0.0

    @classmethod
    def for_airframe(cls, af: Airframe, **kw) -> "FlightController":
        return cls(yaw_inertia=af.inertia[2] + af.a22[2],
                   pitch_inertia=af.inertia[1] + af.a22[1],
                   lever_arm_m=abs(af.x_thr), max_thrust_n=af.max_thrust_n,
                   gimbal_limit_rad=af.gimbal_limit_rad,
                   use_fins=af.ruddervator_fraction > 0.0, **kw)

    def command(self, heading_cmd: float, airspeed_cmd: float, pitch_cmd: float,
                roll_pitch_yaw: Vec, rate: Vec, airspeed: float, thrust_now: float,
                dt: float) -> Controls:
        _, pitch, yaw = roll_pitch_yaw
        _, q, r = rate
        wn, z = self.natural_freq_rad_s, self.damping
        err = math.atan2(math.sin(heading_cmd - yaw), math.cos(heading_cmd - yaw))
        m_max = self.lever_arm_m * self.max_thrust_n * math.sin(self.gimbal_limit_rad)
        ki = self.integral_fraction * wn**3
        e_pitch = pitch_cmd - pitch
        # Anti-windup: integrate only what the gimbal could actually deliver.
        # Pitch only, and only half the authority.  Yaw is left PD: its error
        # is driven by guidance rather than by a standing moment, and an
        # integrator there winds up on every heading change (38 degrees of
        # overshoot on a 90 degree turn when tried).
        lim = 0.5 * m_max
        if abs(e_pitch) < 0.35:
            self._pitch_int = max(-lim, min(lim, self._pitch_int
                                            + self.pitch_inertia * ki * e_pitch * dt))
        n_cmd = self.yaw_inertia * (wn * wn * err - 2 * z * wn * r) + self._yaw_int
        m_cmd = self.pitch_inertia * (wn * wn * e_pitch - 2 * z * wn * q) + self._pitch_int
        # speed loop
        e_v = airspeed_cmd - airspeed
        self._int = max(-self.max_thrust_n, min(self.max_thrust_n,
                                               self._int + self.speed_integral_n_per_m * e_v * dt))
        thrust = self.speed_gain_n_per_m_s * e_v + self._int
        # authority floor proportional to how much moment is being asked for
        want = max(abs(n_cmd), abs(m_cmd)) / (self.lever_arm_m * math.sin(self.gimbal_limit_rad))
        thrust = max(thrust, min(self.max_thrust_n, max(self.authority_floor * self.max_thrust_n
                                                        * min(1.0, abs(err) / 0.2), want)))
        thrust = max(0.0, min(self.max_thrust_n, thrust))
        t_eff = max(thrust_now, 0.05 * self.max_thrust_n)
        # Stern thruster at x = -arm.  r x F = (x,0,0) x (0,Fy,Fz) = (0, -x Fz, x Fy):
        # yaw moment is -arm*Fy, pitch moment is +arm*Fz.  The two signs differ,
        # and getting the pitch one wrong is positive feedback that pendulum
        # stability hides at zero pitch command (found by mission6).
        sy = -n_cmd / (self.lever_arm_m * t_eff)
        sp = m_cmd / (self.lever_arm_m * t_eff)
        sat = abs(sy) > math.sin(self.gimbal_limit_rad) or abs(sp) > math.sin(self.gimbal_limit_rad)
        self.saturated_s += dt if sat else 0.0
        lim = math.sin(self.gimbal_limit_rad)
        gy = math.asin(max(-lim, min(lim, sy)))
        gp = math.asin(max(-lim, min(lim, sp)))
        rud = ele = 0.0
        if self.use_fins:
            rud = max(-1.0, min(1.0, 4.0 * err - 6.0 * r))
            ele = max(-1.0, min(1.0, -4.0 * (pitch_cmd - pitch) + 6.0 * q))
        return Controls(thrust, gy, gp, rud, ele)


# --- scenarios ---------------------------------------------------------------

def run(af: Airframe, duration_s: float, heading_cmd_fn, airspeed_cmd: float,
        wind_ned: Vec = (0.0, 0.0, 0.0), gust: Gust | None = None, dt: float = 0.05,
        controlled: bool = True, initial: State | None = None, record_s: float = 1.0,
        ctl_kw: dict | None = None) -> dict:
    st = initial or State(vel=(airspeed_cmd, 0.0, 0.0))
    fc = FlightController.for_airframe(af, **(ctl_kw or {}))
    t = 0.0
    rows = []
    next_rec = 0.0
    energy_j = 0.0
    beta_sq = 0.0
    n = 0
    max_beta = 0.0
    hdg_err_sq = 0.0
    while t < duration_s:
        g = gust.step(dt) if gust else (0.0, 0.0, 0.0)
        w = (wind_ned[0] + g[0], wind_ned[1] + g[1], wind_ned[2] + g[2])
        rpy = euler_from_quat(st.quat)
        airspeed = math.sqrt(sum(c * c for c in st.vel))
        if gust:
            # Taylor's frozen-turbulence hypothesis: d/dx = (d/dt) / U.
            gb = _mat_t_vec(quat_to_matrix(st.quat), tuple(gust.rate))
            u_eff = max(airspeed, 2.0)
            af.gust_rot = (gb[2] / u_eff, -gb[1] / u_eff)
        hc = heading_cmd_fn(t, st)
        if controlled:
            c = fc.command(hc, airspeed_cmd, 0.0, rpy, st.rate, st.vel[0], st.thrust_n, dt)
        else:
            c = Controls(thrust_n=st.thrust_n)
        st = step(af, st, c, w, dt)
        beta = math.atan2(st.vel[1], max(abs(st.vel[0]), 0.05))
        beta_sq += beta * beta
        max_beta = max(max_beta, abs(beta))
        e = math.atan2(math.sin(hc - rpy[2]), math.cos(hc - rpy[2]))
        hdg_err_sq += e * e
        n += 1
        energy_j += st.thrust_n * max(st.vel[0], 0.0) * dt
        if t >= next_rec:
            rows.append({"t": round(t, 2), "n": st.pos[0], "e": st.pos[1], "d": st.pos[2],
                         "u": st.vel[0], "v": st.vel[1], "w": st.vel[2],
                         "roll_deg": math.degrees(rpy[0]), "pitch_deg": math.degrees(rpy[1]),
                         "yaw_deg": math.degrees(rpy[2]), "r_deg_s": math.degrees(st.rate[2]),
                         "thrust_n": st.thrust_n, "gimbal_yaw_deg": math.degrees(st.gimbal_yaw),
                         "gimbal_pitch_deg": math.degrees(st.gimbal_pitch),
                         "beta_deg": math.degrees(beta), "heading_cmd_deg": math.degrees(hc)})
            next_rec += record_s
        t += dt
        if abs(rpy[1]) > 1.4 or airspeed > 80.0:
            break
    return {"rows": rows, "final": st, "duration_s": t,
            "rms_sideslip_deg": math.degrees(math.sqrt(beta_sq / max(n, 1))),
            "max_sideslip_deg": math.degrees(max_beta),
            "rms_heading_error_deg": math.degrees(math.sqrt(hdg_err_sq / max(n, 1))),
            "gimbal_saturated_fraction": fc.saturated_s / max(t, dt),
            "mean_thrust_power_w": energy_j / max(t, dt), "completed": t >= duration_s - dt}


def handling_report(af: Airframe, cruise: float, ctl_kw: dict | None = None) -> dict:
    """The five standard handling checks for one airframe."""

    out = {}
    # 1. open loop from a 2 degree sideslip: how fast does it diverge?
    st0 = State(vel=(cruise * math.cos(math.radians(2)), cruise * math.sin(math.radians(2)), 0.0),
                thrust_n=0.0)
    ol = run(af, 60.0, lambda t, s: 0.0, cruise, controlled=False, initial=st0)
    t_double = None
    for row in ol["rows"]:
        if abs(row["yaw_deg"]) > 10.0:
            t_double = row["t"]
            break
    out["open_loop_time_to_10deg_yaw_s"] = t_double
    out["open_loop_max_sideslip_deg"] = round(ol["max_sideslip_deg"], 1)
    # 2. calm cruise trim
    tr = run(af, 240.0, lambda t, s: 0.0, cruise, ctl_kw=ctl_kw)
    last = tr["rows"][-1]
    out["trim_airspeed_m_s"] = round(last["u"], 2)
    out["trim_thrust_n"] = round(last["thrust_n"], 2)
    out["trim_pitch_deg"] = round(last["pitch_deg"], 2)
    # 3. 90 degree heading step
    hs = run(af, 300.0, lambda t, s: math.radians(90.0) if t > 10 else 0.0, cruise, ctl_kw=ctl_kw)
    t90 = next((r["t"] - 10 for r in hs["rows"] if r["yaw_deg"] > 81.0), None)
    out["step90_rise_time_s"] = t90
    out["step90_overshoot_deg"] = round(max(r["yaw_deg"] for r in hs["rows"]) - 90.0, 1)
    out["step90_max_sideslip_deg"] = round(hs["max_sideslip_deg"], 1)
    out["step90_gimbal_saturated_fraction"] = round(hs["gimbal_saturated_fraction"], 3)
    out["step90_completed"] = hs["completed"]
    # 4. heading hold in gusts
    for sigma in (0.5, 1.5):
        gh = run(af, 600.0, lambda t, s: 0.0, cruise, gust=Gust(sigma, 20.0, seed=7),
                 ctl_kw=ctl_kw)
        key = f"gust{sigma:g}"
        out[f"{key}_rms_heading_error_deg"] = round(gh["rms_heading_error_deg"], 2)
        out[f"{key}_rms_sideslip_deg"] = round(gh["rms_sideslip_deg"], 2)
        out[f"{key}_gimbal_saturated_fraction"] = round(gh["gimbal_saturated_fraction"], 3)
        out[f"{key}_mean_thrust_power_w"] = round(gh["mean_thrust_power_w"], 1)
        out[f"{key}_completed"] = gh["completed"]
    return out


def station_keep(af: Airframe, max_airspeed: float, wind_ned: Vec, start_offset_m: Vec,
                 duration_s: float = 1800.0, gust_sigma: float = 0.5, seed: int = 3,
                 dt: float = 0.05) -> dict:
    """Close the outer loop: fly back to a station and hold it in wind.

    ``guidance.StationKeeper`` produces an air-velocity demand from position
    error and a wind estimate; the inner loop turns that into heading and
    airspeed.  The wind estimate is the truth wind low-passed over 60 s,
    which is what a GNSS-minus-airspeed estimator delivers.
    """

    from .guidance import StationKeeper
    keeper = StationKeeper(max_airspeed)
    fc = FlightController.for_airframe(af)
    hdg0 = math.atan2(-wind_ned[1], -wind_ned[0]) if any(wind_ned[:2]) else 0.0
    st = State(pos=(start_offset_m[0], start_offset_m[1], 0.0),
               quat=quat_from_euler(0.0, 0.0, hdg0), vel=(max(1.0, 0.5 * max_airspeed), 0.0, 0.0))
    gust = Gust(gust_sigma, 20.0, seed=seed)
    west = [wind_ned[0], wind_ned[1]]
    t = 0.0
    rows = []
    energy = 0.0
    err_sq = 0.0
    n = 0
    next_rec = 0.0
    cmd = keeper.command(-st.pos[0], -st.pos[1], west[0], west[1])
    while t < duration_s:
        g = gust.step(dt)
        w = (wind_ned[0] + g[0], wind_ned[1] + g[1], g[2])
        a = dt / 60.0
        west[0] += a * (w[0] - west[0])
        west[1] += a * (w[1] - west[1])
        gb = _mat_t_vec(quat_to_matrix(st.quat), tuple(gust.rate))
        speed = math.sqrt(sum(c * c for c in st.vel))
        af.gust_rot = (gb[2] / max(speed, 2.0), -gb[1] / max(speed, 2.0))
        if n % 20 == 0:
            cmd = keeper.command(-st.pos[0], -st.pos[1], west[0], west[1])
        rpy = euler_from_quat(st.quat)
        c = fc.command(cmd.heading_rad, cmd.airspeed_m_s, 0.0, rpy, st.rate, st.vel[0],
                       st.thrust_n, dt)
        st = step(af, st, c, w, dt)
        energy += st.thrust_n * max(st.vel[0], 0.0) * dt
        dist = math.hypot(st.pos[0], st.pos[1])
        if t > duration_s * 0.5:
            err_sq += dist * dist
        n += 1
        if t >= next_rec:
            rows.append({"t": round(t, 1), "n": st.pos[0], "e": st.pos[1], "dist_m": dist,
                         "airspeed": st.vel[0], "yaw_deg": math.degrees(rpy[2]),
                         "thrust_n": st.thrust_n, "alt_err_m": -st.pos[2]})
            next_rec += 5.0
        t += dt
    half = max(1, n // 2)
    return {"rows": rows, "final_distance_m": math.hypot(st.pos[0], st.pos[1]),
            "rms_distance_second_half_m": math.sqrt(err_sq / half),
            "mean_thrust_power_w": energy / duration_s,
            "altitude_excursion_m": max(abs(r["alt_err_m"]) for r in rows),
            "gimbal_saturated_fraction": fc.saturated_s / duration_s}


def main(argv: list[str]) -> int:
    from .sizing import ladder
    pts = ladder()
    dp = pts["S2-dayloiter/hull"]
    cruise = dp.mission["cruise_airspeed_m_s"]
    report = {}
    ref = dp.geometry["volume_m3"] ** (2 / 3)
    for label, over in (
        ("fins 0.30 gimbal", {"fin_area_total_m2": 0.30 * ref}),
        ("fins 0.45 gimbal", {"fin_area_total_m2": 0.45 * ref}),
        ("fins 0.60 gimbal", {"fin_area_total_m2": 0.60 * ref}),
        ("fins 0.45 +ruddervator", {"fin_area_total_m2": 0.45 * ref,
                                    "ruddervator_fraction": 0.5}),
    ):
        af = Airframe.from_design(dp, **over)
        report[label] = handling_report(af, cruise)
    af = Airframe.from_design(dp)
    sk = {}
    for wind in (3.0, 5.0, 6.0, 8.0):
        r = station_keep(af, cruise, (0.0, -wind, 0.0), (0.0, -1500.0, 0.0))
        sk[f"wind {wind:g} m/s"] = {k: round(v, 2) for k, v in r.items() if k != "rows"}
    report["_station_keeping"] = sk
    if "--json" in argv:
        print(json.dumps(report, indent=2))
        return 0
    sk = report.pop("_station_keeping")
    print(f"station-keeping, sized hull, {cruise:g} m/s airspeed limit, start 1.5 km downwind, 30 min")
    for k, v in sk.items():
        print(f"  {k:14s} {v}")
    print()
    keys = list(next(iter(report.values())).keys())
    print(f"{'check':42s}" + "".join(f"{k[:24]:>24s}" for k in report))
    for k in keys:
        print(f"{k:42s}" + "".join(f"{str(report[c][k]):>24s}" for c in report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
