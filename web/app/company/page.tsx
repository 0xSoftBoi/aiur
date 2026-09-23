import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { COMPANY, PROGRAM } from "@/lib/site-content";
import readiness from "@/lib/readiness.json";

const CLOSER_LABEL: Record<string, string> = {
  software: "CLOSED BY A COMMIT",
  decision: "FOUNDER DECISION",
  bench: "BENCH EVIDENCE",
  tethered: "TETHERED EVIDENCE",
  flight: "FLIGHT EVIDENCE",
};

export const metadata: Metadata = {
  title: "Company",
  description:
    "Aiur is both the manufacturer of the observation package and the operator of the flights it makes possible.",
};

export default function CompanyPage() {
  return (
    <>
      <PageHead
        eyebrow="Company"
        index="04 / 05"
        title={
          <>
            Manufacturer
            <br />
            <strong>and operator</strong>
          </>
        }
        lede="Aiur designs the package and flies the loop it makes possible. Nothing is handed over a wall, so no claim outlives the evidence behind it."
      />

      <section className="company paper-section" id="structure" aria-label="Company structure">
        <div className="shell">
          <div className="section-meta">
            <span>01 / STRUCTURE</span>
            <span>ONE TEAM, TWO ROLES</span>
          </div>

          <div className="company-grid" data-reveal>
            {COMPANY.map((entry) => (
              <article key={entry.role}>
                <span className="company-role">{entry.role}</span>
                <h3>{entry.title}</h3>
                <p>{entry.copy}</p>
                <dl>
                  {entry.facts.map(([value, label]) => (
                    <div key={label}>
                      <dt>{value}</dt>
                      <dd>{label}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="program paper-section" id="program" aria-labelledby="program-title">
        <div className="shell">
          <div className="section-meta">
            <span>02 / PROGRAMME</span>
            <span>GATES, NOT DECKS</span>
          </div>
          <h2 id="program-title">
            EARN THE NEXT
            <br />
            <em>DEGREE OF FREEDOM.</em>
          </h2>
          <p className="section-lede dark-lede">
            Aiur advances only when the previous gate produces evidence.
            The cold chamber comes before the tether. The tether comes before free flight.
            Two sounding flights come before any float.
          </p>

          <div className="program-list" data-reveal>
            {PROGRAM.map(([id, title, status, copy]) => (
              <article className={status === "ACTIVE" ? "active" : undefined} key={id}>
                <span className="program-id">{id}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
                <span className="program-status">{status}</span>
              </article>
            ))}
          </div>

          <div className="section-foot">
            <Link className="button" href="/careers">
              Join the adventure <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>

      <section className="program paper-section" id="readiness" aria-labelledby="readiness-title">
        <div className="shell">
          <div className="section-meta">
            <span>03 / READINESS</span>
            <span>GENERATED FROM aiur/s0_readiness.py</span>
          </div>
          <h2 id="readiness-title">
            WHAT IS CLOSED,
            <br />
            <em>AND WHAT CANNOT BE YET.</em>
          </h2>
          <p className="section-lede dark-lede">
            Every item names what closes it. A commit can close software; it
            cannot close a decision, a bench, a tether, or a flight, and the
            validator refuses to let it. Software items:{" "}
            {readiness.by_closer.software.closed} closed, {readiness.by_closer.software.open} open.
          </p>

          <div className="program-list" data-reveal>
            {readiness.items.map((item) => (
              <article className={item.status === "closed" ? "active" : undefined} key={item.id}>
                <span className="program-id">{item.id}</span>
                <h3>{CLOSER_LABEL[item.closed_by] ?? item.closed_by.toUpperCase()}</h3>
                <p>{item.title}</p>
                <span className="program-status">{item.status.toUpperCase()}</span>
              </article>
            ))}
          </div>
        </div>
      </section>
      <Pager current="/company" />
    </>
  );
}
