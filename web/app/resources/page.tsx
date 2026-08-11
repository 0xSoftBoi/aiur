import type { Metadata } from "next";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { NEWS, REPO_URL } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Resources",
  description:
    "News, the public engineering log, and the design rules that govern what Aiur publishes.",
};

export default function ResourcesPage() {
  return (
    <>
      <PageHead
        eyebrow="Resources"
        title={
          <>
            Everything we
            <br />
            <strong>have published</strong>
          </>
        }
        lede="Design decisions, gates, geometry, and evidence tooling live in the engineering repository. Nothing here is summarised out of it."
      />

      <section className="news" id="news" aria-labelledby="news-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / NEWS</span>
            <span>PUBLIC / VERSIONED</span>
          </div>
          <div className="section-head">
            <h2 id="news-title">Latest news</h2>
            <p className="section-lede">
              Each entry links to the change that produced it, not to a press
              release about it.
            </p>
          </div>

          <div className="news-grid" data-reveal>
            {NEWS.map((item) => (
              <a className="news-card" key={item.title} href={item.href} target="_blank" rel="noreferrer">
                <div className="news-meta">
                  <span>{item.tag}</span>
                  <time>{item.date}</time>
                </div>
                <strong>{item.title}</strong>
                <p>{item.copy}</p>
                <i aria-hidden="true">Read more ↗</i>
              </a>
            ))}
          </div>

          <div className="release-cta" id="rules">
            <span>DESIGN RULE / 001</span>
            <strong>CONCEPT ART IS NOT EVIDENCE.</strong>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              OPEN THE ENGINEERING REPO <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
      </section>
      <Pager current="/resources" />
    </>
  );
}
