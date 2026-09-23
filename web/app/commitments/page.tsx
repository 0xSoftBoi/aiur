import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { BENCH_GATE } from "@/lib/site-content";
import { STRATO_SPEC } from "@/lib/strato-spec";

export const metadata: Metadata = {
  title: "Commitments",
  description:
    "Evidence before claims: the S0-A bench and cold-chamber gate, its exit criteria, and the rules that govern them.",
};

const RULES = [
  ["001", "Concept art is not evidence", "A render proves a shape, never a temperature, a link margin, or a landing. A picture from altitude with no position tag is concept art."],
  ["002", "Targets are labelled as targets", "Numbers stay marked as model results or exit criteria until a measurement replaces them."],
  ["003", "Missing evidence is a failed gate", "Absence of a result is treated as a negative result, not as a pending one."],
  ["004", "Termination does not need the computer", "If the payload computer freezes at −55 °C, the flight still ends on its own timer and its own power. Software is never the only way down."],
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
        lede="The first article is deliberately unglamorous. Everything Aiur claims has to survive a cold chamber before it appears anywhere else."
      />

      <section className="evidence" id="interface" aria-labelledby="evidence-title">
        <div className="shell evidence-layout">
          <div className="evidence-copy">
            <div className="section-meta light-meta">
              <span>01 / PHYSICAL TRUTH</span>
              <span>S0-A / BENCH + CHAMBER</span>
            </div>
            <p className="eyebrow">THE HARD PART FIRST</p>
            <h2 id="evidence-title">
              THE FLIGHT
              <br />
              <em>PACKAGE.</em>
            </h2>
            <p className="section-lede">
              A package under {STRATO_SPEC.payloadAllocationKg.toFixed(1)} kg with an imager,
              two independent trackers on separate power, a parachute drop-tested
              to {STRATO_SPEC.landingRateLimitMps.toFixed(0)} m/s, and a flight
              termination demonstrated with the payload computer switched off.
            </p>
            <p className="evidence-note">
              S0-A is a chamber gate, not a marketing milestone. Nothing flies.
              Missing evidence is a failed gate.
            </p>
          </div>

          <div className="gate-panel" data-reveal aria-label="S0-A exit criteria">
            <div className="gate-head">
              <span>S0-A / EXIT CRITERIA</span>
              <strong>BENCH + COLD CHAMBER</strong>
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

      <section className="plate-section" aria-labelledby="plate-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>02 / CONTROLLED GEOMETRY</span>
            <span>REV-A / FLIGHT PACKAGE</span>
          </div>
          <div className="section-head">
            <h2 id="plate-title">The drawing is generated, not drawn</h2>
            <p className="section-lede">
              Every dimension below is emitted by the same script that writes
              the foam cut sheet and reports the package&apos;s smallest face
              against the regulation. A number on this sheet cannot disagree
              with the box that gets cut.
            </p>
          </div>

          <figure className="plate" data-reveal>
            <div className="plate-sheet">
              <img
                src="/strato_package_rev_a_section_dark.svg"
                alt={`Dimensioned cross-section of the STRATO-P0 Rev-A flight package: ${STRATO_SPEC.packageExteriorMm.join(" by ")} mm exterior in 20 mm XPS foam, a 30 mm camera port in the end wall, a GNSS patch under a foam-only lid, and two load-line loops that run around the box rather than into it. Weight to size ratio ${STRATO_SPEC.packageWeightSizeRatioOzPerIn2} ounces per square inch at the 1 kg allocation, against a limit of 3.`}
              />
            </div>
            <figcaption className="plate-block">
              <div><span>DRAWING</span><strong>STRATO-PKG-REV-A</strong></div>
              <div><span>REVISION</span><strong>A</strong></div>
              <div><span>UNITS</span><strong>MILLIMETRES</strong></div>
              <div><span>SOURCE</span><strong>generate_package_rev_a.py</strong></div>
              <div><span>EXTERIOR</span><strong>{STRATO_SPEC.packageExteriorMm.join(" × ")}</strong></div>
              <div><span>STATUS</span><strong>FIRST-ARTICLE FIT</strong></div>
            </figcaption>
          </figure>

          <div className="note-band">
            <span>WHAT THIS SHEET IS NOT</span>
            <p>
              First-article fit geometry, not a flight-qualified enclosure. The
              physical fit owns the final dimensions; this sheet owns what gets
              cut to test it. Nominal BOM masses sum to roughly{" "}
              {STRATO_SPEC.bomNominalMassG} g against the{" "}
              {Math.round(STRATO_SPEC.baselinePackageKg * 1000)} g baseline allocation.
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
