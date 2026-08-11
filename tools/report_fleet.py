"""Render a fleet-throughput study as a readable table."""
import json, sys


def render_design_points(report: dict) -> str:
    out = ["FLEET DESIGN POINTS — the whole carrier, every constraint on"]
    svc = report["service_model"]
    out.append(
        f"service model: p_capture={svc['p_capture']:.3f}, "
        f"mean head occupancy {sum(svc['occupancy_samples_s'])/len(svc['occupancy_samples_s']):.1f}s, "
        f"energy: {report['energy_mode']}"
    )
    out.append("")
    for p in report["design_points"]:
        b, m = p["bill"], p["metrics"]
        status = "SERVED" if p["converged"] else "NOT CONVERGED"
        out.append(
            f"=== {p['target_airborne']} aircraft airborne  [{status}]  "
            f"(achieved {p['achieved_airborne']:.1f}, {p['iterations']} iterations)"
        )
        taut = p.get("taut_constraints") or []
        out.append(
            "    taut (reducing any one breaks the target): "
            + (", ".join(taut) if taut else "—")
        )
        out.append("    bill of materials:")
        out.append(f"      airframes owned         {b['fleet_size']}")
        out.append(f"      capture heads           {b['capture_heads']}")
        out.append(f"      magazine slots          {b['magazine_slots']}")
        out.append(f"      launch lanes            {b['launch_lanes']}")
        out.append(
            f"      radios                  {b['radio_channels']} "
            f"x {b['links_per_channel']} links = {b['radio_channels']*b['links_per_channel']}"
        )
        out.append(f"      ballast rate            {b['ballast_rate_g_s']:.0f} g/s")
        out.append(
            f"      trim authority          {b['pitch_authority_g_m']}/{b['roll_authority_g_m']} g·m pitch/roll"
        )
        if b["energy_mode"] == "swap":
            out.append(
                f"      battery pool            {b['spare_packs']} spare packs, "
                f"{b['charger_channels']} chargers"
            )
        out.append(
            f"      dock mass               {b['dock_mass_g']:.0f} g "
            f"(heads + {b['magazine_slots']} passive slots)"
        )
        out.append(
            f"    mechanism life: {m['keeper_cycles']} keeper + {m['swap_cycles']} swap "
            "actuations / 4h (qualify to 2x, per NASA-STD-5017)"
        )
        out.append("")
    out.append("notes:")
    for note in report["design_points"][0]["notes"]:
        out.append(f"  - {note}")
    return "\n".join(out)


def render_mixed_fleet(report: dict) -> str:
    sh = report["shared"]
    out = ["MIXED-FLEET CARRIER — recovery aircraft and scouts on one platform"]
    out.append("")
    out.append("SHARED (summed across classes — one radio, one launch airspace, one lift):")
    out.append(
        f"  radios              {sh['radios']} x {sh['links_per_channel']} links "
        f"= {sh['radios']*sh['links_per_channel']} concurrent"
    )
    out.append(
        f"  radio link load     {sh['total_link_load']:.0f} "
        f"({100*sh['radio_utilisation']:.0f}% of budget), dominated by {report['radio_dominated_by']}"
    )
    out.append(f"  launch lanes        {sh['launch_lanes_total']} total")
    out.append(f"  airframe mass       {sh['airframe_mass_kg']:.1f} kg carried")
    out.append("")
    out.append("PER CLASS (own dock, own duty cycle):")
    hdr = f"  {'class':<13} {'airborne':>8} {'links/ea':>8} {'radio load':>11} {'fleet':>6} {'heads':>6} {'lanes':>6}"
    out.append(hdr)
    out.append("  " + "-" * (len(hdr) - 2))
    for c in report["classes"]:
        flag = "" if c["converged"] else "  [NOT CONVERGED]"
        out.append(
            f"  {c['name']:<13} {c['target_airborne']:>8} {c['radio_links_each']:>8.1f} "
            f"{c['link_load']:>11.0f} {c['fleet_size']:>6} {c['capture_heads']:>6} "
            f"{c['launch_lanes']:>6}{flag}"
        )
    out.append("")
    out.append("notes:")
    for note in report["notes"]:
        out.append(f"  - {note}")
    return "\n".join(out)


def render(report: dict) -> str:
    if report.get("study") == "mixed-fleet carrier":
        return render_mixed_fleet(report)
    if report.get("study") == "fleet design point":
        return render_design_points(report)
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
        width = base.get("magazine_width_m", 0.0)
        cols = base.get("magazine_columns", 1)
        geom = f"{span:.0f}m" + (f" x {width:.0f}m ({cols} cols)" if width else " line")
        out.append(
            f"magazine: {geom}, '{base.get('stow_policy', 'balanced')}' stow policy, "
            f"{base.get('pitch_authority_g_m', 0):.0f}/{base.get('roll_authority_g_m', 0):.0f} "
            "g·m pitch/roll authority"
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
        out.append("MAGAZINE TRIM (from the stow distribution)")
        h3 = f"{'fleet':>6} {'heads':>6} {'pitch g·m':>10} {'pitch%':>7} {'roll g·m':>10} {'roll%':>7}"
        out.append(h3)
        out.append("-" * len(h3))
        for sweep in report["sweeps"]:
            for row in sweep["rows"]:
                out.append(
                    f"{sweep['fleet_size']:>6} {row['capture_heads']:>6} "
                    f"{row.get('peak_pitch_moment_g_m', 0):>10.0f} "
                    f"{100 * row.get('pitch_exceedance_fraction', 0):>7.1f} "
                    f"{row.get('peak_roll_moment_g_m', 0):>10.0f} "
                    f"{100 * row.get('roll_exceedance_fraction', 0):>7.1f}"
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
