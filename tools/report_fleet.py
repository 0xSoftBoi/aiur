"""Render a fleet-throughput study as a readable table."""
import json, sys


def render(report: dict) -> str:
    out = []
    svc = report["service_model"]
    base = report["base_params"]
    out.append("FLEET-THROUGHPUT STUDY")
    out.append(
        f"service model: p_capture={svc['p_capture']:.3f} "
        f"[{svc['ci_low']*100:.0f},{svc['ci_high']*100:.0f}]%, "
        f"{svc['episodes']} twin episodes, {len(svc['occupancy_samples_s'])} occupancy samples"
    )
    out.append(f"  source: {svc['source']}")
    out.append(
        f"fleet cycle: sortie {base['sortie_s']:.0f}s of {base['endurance_s']:.0f}s endurance"
        f" ({base['endurance_s'] - base['sortie_s']:.0f}s reserve), recharge {base['recharge_s']:.0f}s"
    )
    out.append(
        f"policy: {base['queue_policy']}, retry limit {base['retry_limit']}, "
        f"stow {base['stow_s']:.0f}s, go-around {base['go_around_s']:.0f}s"
    )
    mode = base.get("energy_mode", "charge_in_place")
    if mode == "swap":
        chargers = base.get("charger_channels")
        chargers = "one/airframe" if chargers is None else chargers
        out.append(
            f"energy: battery swap, {base['swap_s']:.0f}s exchange, "
            f"{base['spare_packs']} spare packs, {chargers} chargers, "
            f"pack recharge {base.get('pack_charge_s') or base['recharge_s']:.0f}s"
        )
    else:
        out.append("energy: charge in place (recovered aircraft holds its slot)")
    corridors = base.get("approach_corridors")
    holds = base.get("traffic_holds_s", 0.0)
    miss = base.get("traffic_miss_penalty", 0.0)
    if corridors is not None or holds or miss:
        out.append(
            f"traffic: {corridors if corridors is not None else 'one/head'} corridors, "
            f"{holds:.0f}s hold/neighbour, {miss:.2f} miss-penalty/neighbour"
        )
    else:
        out.append("traffic: independent corridors (interaction off — head counts are LOWER bounds)")
    span = base.get("magazine_span_m")
    if span is not None:
        out.append(
            f"magazine: {span:.0f}m slot line, '{base.get('stow_policy', 'balanced')}' "
            f"stow policy, {base.get('pitch_authority_g_m', 0):.0f} g·m pitch authority"
        )
    else:
        out.append("magazine: scalar trim only (geometry off — no pitch moment modelled)")
    radios = base.get("radio_channels")
    if radios is not None:
        lpc = base.get("links_per_channel", 0)
        out.append(
            f"radio: {radios} x {lpc} = {radios * lpc} concurrent links, "
            f"approach link cost {base.get('approach_link_cost', 1)}"
        )
    else:
        out.append("radio: unlimited (link budget off — no airborne ceiling modelled)")
    out.append(f"seeds {report['seeds']}, loss threshold {report['loss_threshold_pct']}%")
    out.append("")

    hdr = f"{'fleet':>6} {'heads':>6} {'serves':>7} {'loss%':>7} {'thr/h':>8} {'dem/h':>8} {'p95 wait':>9} {'util':>6} {'lnch':>6} {'air':>7} {'qmax':>5} {'fin':>4} {'trim g':>7} {'trim%':>6}  binding"
    out.append(hdr)
    out.append("-" * len(hdr))
    for sweep in report["sweeps"]:
        for row in sweep["rows"]:
            out.append(
                f"{sweep['fleet_size']:>6} {row['capture_heads']:>6} "
                f"{('yes' if row['serves_fleet'] else 'NO'):>7} "
                f"{row['worst_loss_pct']:>7.2f} {row['throughput_per_hour']:>8.1f} "
                f"{row['demand_per_hour']:>8.1f} {row['p95_queue_wait_s']:>9.1f} "
                f"{row['head_utilisation']:>6.2f} {row['launch_utilisation']:>6.2f} "
                f"{row['mean_airborne']:>7.1f} {row['max_queue_depth']:>5} "
                f"{row.get('peak_on_final', 0):>4} "
                f"{row['peak_trim_error_g']:>7.0f} "
                f"{100 * row['trim_exceedance_fraction']:>6.1f}  "
                f"{row['binding_constraint'][:48]}"
            )
        out.append("")

    out.append("fin = peak aircraft simultaneously on final approach")
    out.append("trim g = peak uncorrected buoyant trim error; trim% = time outside trim authority")
    if base.get("magazine_span_m") is not None:
        out.append("")
        out.append("MAGAZINE PITCH (from the stow distribution)")
        h3 = f"{'fleet':>6} {'heads':>6} {'peak g·m':>10} {'pitch%':>7}"
        out.append(h3)
        out.append("-" * len(h3))
        for sweep in report["sweeps"]:
            for row in sweep["rows"]:
                out.append(
                    f"{sweep['fleet_size']:>6} {row['capture_heads']:>6} "
                    f"{row.get('peak_pitch_moment_g_m', 0):>10.0f} "
                    f"{100 * row.get('pitch_exceedance_fraction', 0):>7.1f}"
                )
            out.append("")
    out.append("")

    out.append("MECHANISM LIFE (actuations over the run; life test must cover these x margin)")
    hdr2 = f"{'fleet':>6} {'heads':>6} {'keeper cyc':>11} {'swap cyc':>9}"
    out.append(hdr2)
    out.append("-" * len(hdr2))
    for sweep in report["sweeps"]:
        for row in sweep["rows"]:
            out.append(
                f"{sweep['fleet_size']:>6} {row['capture_heads']:>6} "
                f"{row.get('keeper_cycles', 0):>11} {row.get('swap_cycles', 0):>9}"
            )
        out.append("")

    out.append("MINIMUM CAPTURE HEADS")
    for sweep in report["sweeps"]:
        minimum = sweep["minimum_heads"]
        answer = f"{minimum} head(s)" if minimum is not None else "NOT SERVED at any tested count"
        out.append(f"  {sweep['fleet_size']:>4} aircraft -> {answer}")
    out.append("")
    out.append("caveats:")
    for caveat in report["caveats"]:
        out.append(f"  - {caveat}")
    return "\n".join(out)


if __name__ == "__main__":
    print(render(json.load(open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin)))
