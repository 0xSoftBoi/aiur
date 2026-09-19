import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { SYSTEM_LOOP } from "@/lib/site-content";
import { STRATO_SPEC } from "@/lib/strato-spec";

export const metadata: Metadata = {
  title: "Solutions",
  description:
    "The flight loop: climb, observe, report, return — and why returning with the picture is the hard part.",
};

export default function SolutionsPage() {
  return (
    <>
      <PageHead
        eyebrow="Solutions"
        index="01 / 05"
        title={
          <>
            Getting up is easy.
            <br />
            <strong>Coming back with the picture isn&apos;t.</strong>
          </>
        }
        lede="Cold, power, tracking, termination, and the landing all get harder above the tropopause. Aiur treats each one as a gate with a number, not as a risk to carry into the first free flight."
      />

      <section className="thesis paper-section" id="loop" aria-labelledby="loop-title">
        <div className="shell">
          <div className="section-meta">
            <span>01 / THE SYSTEM</span>
            <span>ALTITUDE × EVIDENCE</span>
          </div>
          <p className="thesis-kicker">A satellite is a schedule. A balloon is a decision.</p>
          <h2 id="loop-title">
            THE FLIGHT
            <br />
            <em>LOOP.</em>
          </h2>
          <p className="section-lede dark-lede">
            Four steps, each one earned before the next. The loop is the product;
            the balloon is a consumable in it.
          </p>

          <div className="system-loop" data-reveal aria-label="Aiur observation flight loop">
            {SYSTEM_LOOP.map((step) => (
              <article key={step.title}>
                <span>{step.index}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.copy}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="carrier-vision" id="float" aria-labelledby="float-title">
        <div className="shell carrier-copy">
          <div className="section-meta light-meta">
            <span>02 / NORTH STAR</span>
            <span>PERSISTENT FLOAT</span>
          </div>
          <p className="eyebrow">THE SOUNDING FLIGHT IS ONLY THE FIRST ARTICLE</p>
          <h2 id="float-title">
            THE FLOAT IS
            <br />
            <em>THE INFRASTRUCTURE.</em>
          </h2>
          <p className="section-lede">
            A fixed-volume envelope stops where its buoyancy runs out and stays
            there for days. Observation becomes persistent, and the package
            that proved itself on a sounding flight becomes the thing that
            watches a region continuously.
          </p>

          <div className="carrier-capabilities" data-reveal aria-label="Long-term float capabilities">
            <div><span>01</span><strong>PERSISTENT LIFT</strong></div>
            <div><span>02</span><strong>REGIONAL VIEW</strong></div>
            <div><span>03</span><strong>DAY / NIGHT POWER</strong></div>
            <div><span>04</span><strong>CONTINUOUS DOWNLINK</strong></div>
          </div>

          <div className="scale-disclosure">
            <span>MODEL DISCLOSURE</span>
            <p>
              The float figures are executable, not aspirational: a 3 kg gross
              article at {STRATO_SPEC.thresholdAltitudeM / 1000} km needs a{" "}
              {STRATO_SPEC.floatEnvelopeVolumeM3.toFixed(0)} m³ envelope in the
              1976 standard atmosphere, and its day/night power balance closes
              or fails in the same script. Float is gated on the sounding
              article and gets no envelope until S0-C is boring.
            </p>
          </div>

          <div className="section-foot">
            <Link className="button" href="/commitments">
              See what we commit to <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>
      <Pager current="/solutions" />
    </>
  );
}
