"""Render a capture-architecture trade study as a readable table."""
import json, sys

def render(report: dict) -> str:
    out = []
    archs = report["architectures"]
    out.append(f"CAPTURE-ARCHITECTURE TRADE STUDY  ({report['episodes_per_condition']} episodes/condition, seed {report['seed']})")
    out.append(f"ranked by: {report['ranked_by']}")
    out.append("")
    hdr = f"{'architecture':<34} {'safe':>5} {'noise':>7} {'wind':>6} {'nom%':>6} {'act':>4} {'sens':>5} {'parts':>6} {'dock g':>7}"
    out.append(hdr); out.append("-" * len(hdr))
    for a in archs:
        out.append(
            f"{a['name'][:34]:<34} {('yes' if a['safe'] else 'NO'):>5} "
            f"{a['noise_tolerance']:>6.0f}x {a['wind_tolerance_m_s']:>5.1f} "
            f"{a['nominal_capture_rate_pct']:>6.1f} {a['actuator_count']:>4} "
            f"{a['sensed_channels']:>5} {a['part_count']:>6} {a['est_dock_mass_g']:>7.0f}"
        )
    out.append("")
    out.append("noise = highest positioning-noise multiple still capturing above the collapse threshold")
    out.append("        (this is the sensor the design lets you get away with)")
    out.append("")
    for a in archs:
        out.append(f"--- {a['name']}")
        out.append(f"    {a['summary']}")
        for c in a["conditions"]:
            out.append(f"      {c['axis']:6} {c['level']:5.1f} -> {c['capture_rate_pct']:6.2f}% "
                       f"[{c['ci_low_pct']:.0f},{c['ci_high_pct']:.0f}]  unsafe={c['unsafe_episodes']}")
        for w in a["known_weaknesses"]:
            out.append(f"      weakness: {w}")
        out.append("")
    return "\n".join(out)

if __name__ == "__main__":
    print(render(json.load(open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin)))
