import type { Metadata } from "next";
import Link from "next/link";

import { AppCard } from "@/components/app-card";
import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { APPLICATIONS } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Applications",
  description:
    "Where a persistent airborne carrier pays: energy, emergency response, industry, maritime, environment, defence.",
};

export default function ApplicationsPage() {
  return (
    <>
      <PageHead
        eyebrow="Applications"
        index="02 / 05"
        title={
          <>
            Where this
            <br />
            <strong>is useful</strong>
          </>
        }
        lede="The carrier is useful wherever the limiting factor is not the aircraft but everything the aircraft has to leave behind."
      />

      <section className="applications" aria-label="Application areas">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / SIX AREAS</span>
            <span>NON-EXHAUSTIVE</span>
          </div>

          <div className="app-grid">
            {APPLICATIONS.map((app, index) => (
              <AppCard app={app} index={index} key={app.slug} />
            ))}
          </div>

          <div className="note-band" data-reveal>
            <span>SCOPE NOTE</span>
            <p>
              These are the domains the architecture is aimed at, not deployments
              Aiur has flown. The current article is a bench recovery gate; nothing
              on this page is a delivered capability.
            </p>
          </div>

          <div className="section-foot">
            <Link className="button" href="/solutions">
              How the system works <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>
      <Pager current="/applications" />
    </>
  );
}
