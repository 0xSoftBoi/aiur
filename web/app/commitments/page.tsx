import type { Metadata } from "next";
import Image from "next/image";
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
  ["004", "Power loss holds, it does not drop", "If the actuator loses power with an aircraft captured, it stays mechanically retained. The keeper is not the load path, and software is never permitted to release something it cannot observe."],
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
              A Ø180 mm recovery mouth, a positive mechanical keeper that owns
              retention outright, two independent physical contacts that must both
              agree before capture is claimed, and an emergency release commanded
              from every software state.
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

        <div className="shell">
          <figure className="render-frame" data-reveal>
            <Image
              src="/renders/dock-section.png"
              alt="Simulated capture approach with software-in-the-loop episode telemetry overlaid: seed, elapsed time, and contact closing speed"
              width={1920}
              height={1080}
              sizes="(max-width: 900px) 100vw, 900px"
            />
            <figcaption className="render-caption">
              <span>SIMULATION OUTPUT, NOT CONCEPT ART — SEE RULE 001</span>
              <strong>SIL / DIGITAL TWIN</strong>
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="plate-section" aria-labelledby="plate-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>02 / CONTROLLED GEOMETRY</span>
            <span>REV-B / SCREENING ARTICLE</span>
          </div>
          <div className="section-head">
            <h2 id="plate-title">The drawing is generated, not drawn</h2>
            <p className="section-lede">
              Every callout below is emitted by the same script that writes the
              STLs the printer receives. A dimension on this sheet cannot
              disagree with the part that gets made.
            </p>
          </div>

          <figure className="plate" data-reveal>
            <div className="plate-sheet">
              <img
                src="/p0a_cross_section_rev_b_dark.svg"
                alt="Dimensioned cross-section of the P0-A Rev-B recovery interface: Ø180 mm funnel mouth, Ø16 mm throat, 65 mm depth, Ø12 mm probe belt, Ø9 mm seat, 5.2 mm keeper slot, 110 mm probe tip standoff above the rotor plane."
              />
            </div>
            <figcaption className="plate-block">
              <div><span>DRAWING</span><strong>P0A-XS-REV-B</strong></div>
              <div><span>REVISION</span><strong>B</strong></div>
              <div><span>UNITS</span><strong>MILLIMETRES</strong></div>
              <div><span>SOURCE</span><strong>generate_rev_a.py</strong></div>
              <div><span>COMMIT</span><strong>ab364ba</strong></div>
              <div><span>STATUS</span><strong>SCREENING ARTICLE</strong></div>
            </figcaption>
          </figure>

          <div className="note-band">
            <span>WHAT THIS SHEET IS NOT</span>
            <p>
              First-article fit geometry, not production interface control
              dimensions and not a flight-qualified part. The physical fit owns
              the final geometry; this sheet owns what gets printed to test it.
            </p>
          </div>
        </div>
      </section>

      <section className="rules paper-section" id="rules" aria-labelledby="rules-title">
        <div className="shell">
          <div className="section-meta">
            <span>03 / DESIGN RULES</span>
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
