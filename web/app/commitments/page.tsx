import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { BENCH_GATE } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Commitments",
  description:
    "Evidence before claims: the P0-A bench gate, its exit criteria, and the rules that govern them.",
};

const RULES = [
  ["001", "Concept art is not evidence", "A render proves a shape, never a force, a cycle count, or a release."],
  ["002", "Targets are labelled as targets", "Numbers stay marked as exit criteria until a measurement replaces them."],
  ["003", "Missing evidence is a failed gate", "Absence of a result is treated as a negative result, not as a pending one."],
  ["004", "Power-off still releases", "Any retention mechanism must be undoable by hand with controller and actuator power removed."],
] as const;

export default function CommitmentsPage() {
  return (
    <>
      <PageHead
        eyebrow="Commitments"
        index="03 / 05"
        title={
          <>
            What we will
            <br />
            <strong>and will not claim</strong>
          </>
        }
        lede="The first article is deliberately unglamorous. Everything Aiur claims has to survive contact with a bench before it appears anywhere else."
      />

      <section className="evidence" id="interface" aria-labelledby="evidence-title">
        <div className="shell evidence-layout">
          <div className="evidence-copy">
            <div className="section-meta light-meta">
              <span>01 / PHYSICAL TRUTH</span>
              <span>REV-A / BENCH</span>
            </div>
            <p className="eyebrow">THE HARD PART FIRST</p>
            <h2 id="evidence-title">
              THE RECOVERY
              <br />
              <em>INTERFACE.</em>
            </h2>
            <p className="section-lede">
              A Ø180 mm recovery mouth, positive mechanical keeper, two independent
              physical contacts, and a manual release that still works with
              controller and actuator power removed.
            </p>
            <p className="evidence-note">
              P0-A is a bench gate, not a marketing milestone. Propellers stay off.
              Missing evidence is a failed gate.
            </p>
          </div>

          <div className="gate-panel" data-reveal aria-label="P0-A exit criteria">
            <div className="gate-head">
              <span>P0-A / EXIT CRITERIA</span>
              <strong>BENCH CAPTURE</strong>
            </div>
            <div className="gate-grid">
              {BENCH_GATE.map(([value, label]) => (
                <div key={label}>
                  <strong>{value}</strong>
                  <span>{label}</span>
                </div>
              ))}
            </div>
            <div className="gate-foot">
              <span>STATUS</span>
              <strong>TARGETS / NOT CLAIMED RESULTS</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="rules paper-section" id="rules" aria-labelledby="rules-title">
        <div className="shell">
          <div className="section-meta">
            <span>02 / DESIGN RULES</span>
            <span>NON-NEGOTIABLE</span>
          </div>
          <div className="section-head">
            <h2 id="rules-title">Design rules</h2>
            <p className="section-lede dark-lede">
              Four rules decide what may be published. They exist so that the
              public record stays worth reading.
            </p>
          </div>

          <div className="rule-list" data-reveal>
            {RULES.map(([id, title, copy]) => (
              <article key={id}>
                <span className="program-id">{id}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>

          <div className="section-foot">
            <Link className="button" href="/company#program">
              See the programme gates <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>
      <Pager current="/commitments" />
    </>
  );
}
