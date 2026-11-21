#!/usr/bin/env python3
"""Run one free-flight case in Gazebo, headless, from a given initial state.

    gz_fins_run.py WORLD.sdf --vel-frd U V W --thrust N --duration S
                   --mass M --added-mass XX YY ZZ --com X Y Z [--csv OUT] [--rtf R]

Stock ``gz sim`` cannot start a model with a velocity, and ApplyLinkWrench's
persistent force is fixed in the world frame.  This runner uses the gz-sim
Python bindings to (1) give the link its velocity with a one-step impulse from
rest (the model must start level, at zero yaw) and (2) apply
thrust along the body x axis at the link origin (the hull axis: the thruster
of flight6dof at zero gimbal) on every step.  Nothing else is touched; the
aerodynamics are the stock systems named in the world file.

``--vel-frd`` is the body velocity in flight6dof's axes (x forward, y right,
z down); the link is x forward, y left, z up.
"""
import argparse
import math
import time

from gz.math7 import Vector3d
from gz.sim8 import Link, Model, TestFixture, World, world_entity


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("--vel-frd", type=float, nargs=3, default=[0.0, 0.0, 0.0])
    ap.add_argument("--thrust", type=float, default=0.0)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--mass", type=float, required=True, help="rigid mass, kg")
    ap.add_argument("--added-mass", type=float, nargs=3, required=True, help="xx yy zz, kg")
    ap.add_argument("--com", type=float, nargs=3, required=True, help="CoM in the link frame, m")
    ap.add_argument("--csv", default=None, help="log truth from the ECM (no ROS needed)")
    ap.add_argument("--rtf", type=float, default=0.0, help="pace to this real-time factor")
    ap.add_argument("--wait", type=float, default=0.0, help="seconds to wait before stepping")
    args = ap.parse_args()

    fixture = TestFixture(args.world)
    state = {"link": None, "n": 0, "rows": []}
    u, v, w = args.vel_frd

    def pre(info, ecm):
        if state["link"] is None:
            world = World(world_entity(ecm))
            for m in world.models(ecm):
                ent = Model(m).link_by_name(ecm, "base_link")
                if ent:
                    state["link"] = Link(ent)
                    state["link"].enable_velocity_checks(ecm, True)
        link = state["link"]
        if state["n"] == 0:
            # One-step impulse from rest: generalised momentum of a pure
            # translation, (m + A) v as force and m r_g x v as torque about
            # the link origin.  (Link.set_linear_velocity cannot be used: the
            # Physics system keeps the command component and zeroes the
            # velocity on every later step.)
            v0 = (u, -v, -w)
            f = [(args.mass + a) * c / 0.01 for a, c in zip(args.added_mass, v0)]
            rg = args.com
            tq = [args.mass * (rg[1] * v0[2] - rg[2] * v0[1]) / 0.01,
                  args.mass * (rg[2] * v0[0] - rg[0] * v0[2]) / 0.01,
                  args.mass * (rg[0] * v0[1] - rg[1] * v0[0]) / 0.01]
            link.add_world_wrench(ecm, Vector3d(*f), Vector3d(*tq))
        elif args.thrust:
            pose = link.world_pose(ecm)
            link.add_world_wrench(ecm, pose.rot().rotate_vector(Vector3d(args.thrust, 0, 0)),
                                  Vector3d(0, 0, 0))
        state["n"] += 1

    def post(info, ecm):
        if args.csv is None or state["link"] is None:
            return
        link = state["link"]
        pose, lin, ang = link.world_pose(ecm), link.world_linear_velocity(ecm), \
            link.world_angular_velocity(ecm)
        if pose is None or lin is None or ang is None:
            return
        rot = pose.rot()
        nose = rot.rotate_vector(Vector3d(1, 0, 0))
        vb, wb = rot.rotate_vector_reverse(lin), rot.rotate_vector_reverse(ang)
        t = info.sim_time.total_seconds()
        state["rows"].append((t, pose.pos().x(), pose.pos().y(), pose.pos().z(),
                              math.degrees(-math.atan2(nose.y(), nose.x())),
                              math.degrees(math.asin(max(-1.0, min(1.0, nose.z())))),
                              math.degrees(rot.euler().x()),
                              vb.x(), -vb.y(), -vb.z(), wb.x(), -wb.y(), -wb.z()))

    fixture.on_pre_update(pre)
    fixture.on_post_update(post)
    fixture.finalize()
    server = fixture.server()
    if args.wait:
        time.sleep(args.wait)
    total = int(round(args.duration / 0.01)) + 1
    if args.rtf > 0:
        chunk, done, t0 = 20, 0, time.time()
        while done < total:
            n = min(chunk, total - done)
            server.run(True, n, False)
            done += n
            lag = done * 0.01 / args.rtf - (time.time() - t0)
            if lag > 0:
                time.sleep(lag)
    else:
        server.run(True, total, False)
    if args.csv:
        with open(args.csv, "w") as fh:
            fh.write("t,x,y,z,yaw_deg,pitch_deg,roll_deg,u,v,w,p,q,r\n")
            for row in state["rows"]:
                fh.write(",".join(f"{c:.6f}" for c in row) + "\n")


if __name__ == "__main__":
    main()
