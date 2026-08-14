import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { COMPANY, PROGRAM } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Company",
  description:
    "Aiur is both the manufacturer of the carrier and the operator of the loop it makes possible.",
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
        lede="Aiur designs the carrier and runs the loop it makes possible. Nothing is handed over a wall, so no claim outlives the evidence behind it."
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
            Aiur advances only when the previous interface produces evidence.
            Bench retention comes before motion. Motion comes before carrier integration.
            One aircraft comes before two.
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

          <figure className="render-frame" data-reveal>
            <Image
              src="/renders/dock-capture-detail.png"
              alt="The keeper closing on the seated probe head, the moment P0-A's gate measures"
              width={1920}
              height={1080}
              sizes="(max-width: 900px) 100vw, 900px"
            />
            <figcaption className="render-caption">
              <span>P0-A / WHAT THE GATE MEASURES</span>
              <strong>RENDERED, NOT PHOTOGRAPHED</strong>
            </figcaption>
          </figure>

          <div className="section-foot">
            <Link className="button" href="/careers">
              Join the adventure <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>
      <Pager current="/company" />
    </>
  );
}
