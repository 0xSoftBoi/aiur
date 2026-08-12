import type { Metadata } from "next";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { COMPOSITES } from "@/lib/composites-data";
import { REPO_URL } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Structures",
  description:
    "The composite structures discipline: laminate design, cure development, tooling, bonding, and defect disposition — every number read out of the executable models.",
};

const DOCS = `${REPO_URL}/blob/main/docs/composites`;
const SOURCE = `${REPO_URL}/blob/main/aiur/composites`;

export default function StructuresPage() {
  const { gate, evidence, parts, findings, delamination, massRollup, modules, experimentRuns } =
    COMPOSITES;

  return (
    <>
      <PageHead
        eyebrow="Structures"
        title={
          <>
            Thin, deployable,
            <br />
            <strong>and not yet qualified</strong>
          </>
        }
        lede="The dock's flight article is a thin prepreg laminate and its capture ring stows rolled against the keel. Every figure on this page is read out of the models that sized them, and a test fails if this page drifts from what those models now produce."
      />

      {/* The honest state first. A structures page that led with results
          would be implying an evidence grade this programme does not hold. */}
      <section className="struct-state-section" aria-labelledby="state-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / EVIDENCE STATE</span>
            <span>DESIGN STUDY / NOT A DESIGN</span>
          </div>
          <div className="section-head">
            <h2 id="state-title">What this is worth today</h2>
          </div>
          <div className="struct-state" data-reveal>
            <div className="struct-state-figure">
              <strong>{evidence.measuredAllowables}</strong>
              <span>MEASURED ALLOWABLES</span>
            </div>
            <div className="struct-state-copy">
              <p>
                Every laminate here is sized against handbook-representative
                lamina values, so every schedule is a <em>design study</em>,
                not a design. The package reports that in its own output
                rather than leaving a reader to infer it from the precision
                of the numbers.
              </p>
              <p>
                {evidence.plannedCoupons} specimens across ten coupons, and{" "}
                {experimentRuns} designed-experiment runs, are what convert
                it. Each experiment names the assumption in the code it
                replaces.
              </p>
              <a href={`${DOCS}/allowables.md`} target="_blank" rel="noreferrer">
                THE COUPON PLAN <span aria-hidden="true">↗</span>
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="struct-findings" aria-labelledby="findings-title">
        <div className="shell">
          <div className="section-meta">
            <span>02 / FINDINGS</span>
            <span>EACH ONE CHANGED THE DESIGN</span>
          </div>
          <div className="section-head">
            <h2 id="findings-title">What the analysis changed</h2>
            <p className="section-lede dark-lede">
              Seven results came out of building the models. None of them
              confirmed a decision that had already been made.
            </p>
          </div>

          <div className="struct-finding-grid" data-reveal>
            {findings.map((finding) => (
              <article className="struct-finding" key={finding.id}>
                <div className="struct-finding-head">
                  <span>{finding.id}</span>
                  <strong>{finding.figure}</strong>
                </div>
                <h3>{finding.title}</h3>
                <p>{finding.copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="struct-parts" aria-labelledby="parts-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>03 / THE PARTS</span>
            <span>FOUR LAMINATES</span>
          </div>
          <div className="section-head">
            <h2 id="parts-title">What is actually composite</h2>
            <p className="section-lede">
              Mass limits are not chosen. Each is the mass allocated to that
              part from a named line of the vehicle budget, divided by its
              area — so a laminate that grows cannot quietly exceed the dock&rsquo;s
              allocation.
            </p>
          </div>

          <div className="struct-table-wrap" data-reveal>
            <table className="struct-table">
              <caption className="visually-hidden">
                Composite parts, their stacking sequences, and what sizes each
              </caption>
              <thead>
                <tr>
                  <th scope="col">Part</th>
                  <th scope="col">Stack</th>
                  <th scope="col">Thickness</th>
                  <th scope="col">Areal mass</th>
                  <th scope="col">Mass</th>
                  <th scope="col">Sized by</th>
                </tr>
              </thead>
              <tbody>
                {parts.map((part) => (
                  <tr key={part.id}>
                    <th scope="row">
                      <strong>{part.id}</strong>
                      <span>{part.name}</span>
                    </th>
                    <td className="mono">{part.stack}</td>
                    <td className="mono">{part.thicknessMm.toFixed(3)} mm</td>
                    <td className="mono">{part.arealMassGsm} g/m²</td>
                    <td className="mono">
                      {part.partMassG} g
                      {part.quantity > 1 ? ` (×${part.quantity})` : ""}
                    </td>
                    <td>{part.sizedBy}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="struct-rollup" data-reveal>
            {massRollup.map((line) => (
              <div key={line.line}>
                <span>{line.line.toUpperCase()}</span>
                <strong>
                  {line.actualG} g <i aria-hidden="true">/</i> {line.budgetG} g
                </strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="struct-depth" aria-labelledby="depth-title">
        <div className="shell">
          <div className="section-meta">
            <span>04 / DISPOSITION</span>
            <span>DEPTH, NOT ONLY SIZE</span>
          </div>
          <div className="section-head">
            <h2 id="depth-title">Where a defect sits decides what it costs</h2>
            <p className="section-lede dark-lede">
              The plies above a delamination buckle as a small plate. One thin
              ply has almost no bending stiffness, so the shallow case — the
              one hardest to detect and easiest to write off as cosmetic — is
              the critical one. An inspection record without a depth cannot be
              dispositioned at all.
            </p>
          </div>

          <div className="struct-depth-grid" data-reveal>
            {delamination.map((row) => (
              <div className="struct-depth-card" key={row.id}>
                <span>{row.id}</span>
                <div>
                  <strong>{row.shallowMm} mm</strong>
                  <i>ONE PLY DOWN</i>
                </div>
                <div>
                  <strong>{row.midMm} mm</strong>
                  <i>MID-THICKNESS</i>
                </div>
              </div>
            ))}
          </div>
          <p className="struct-note">
            Critical delamination radius at each part&rsquo;s governing compressive
            strain. On the retention path no delamination is accepted at any
            size — not because of the arithmetic, but because a defect there is
            evidence of a process escape on a part whose failure drops a
            captured aircraft.
          </p>
        </div>
      </section>

      <section className="struct-package" aria-labelledby="package-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>05 / THE PACKAGE</span>
            <span>
              {gate.valid ? "GATE GREEN" : "GATE FAILING"} / {gate.errorCount} ERRORS
            </span>
          </div>
          <div className="section-head">
            <h2 id="package-title">{modules.length} modules, one gate</h2>
            <p className="section-lede">
              Dependency-free, run on every push. The gate returns non-zero
              when the record and the arithmetic disagree — a design rule
              broken without a waiver, a waiver that outlived its rule break,
              a qualified cure cycle failing its own criteria — or when a
              critical structural check fails.
            </p>
          </div>

          <div className="struct-modules" data-reveal>
            {modules.map((module) => (
              <a
                className="struct-module"
                key={module.name}
                href={`${SOURCE}/${module.name}.py`}
                target="_blank"
                rel="noreferrer"
              >
                <strong>aiur.composites.{module.name}</strong>
                <p>{module.copy}</p>
              </a>
            ))}
          </div>

          <div className="release-cta">
            <span>DESIGN RULE / 001</span>
            <strong>CONCEPT ART IS NOT EVIDENCE.</strong>
            <a href={`${DOCS}/README.md`} target="_blank" rel="noreferrer">
              READ THE DISCIPLINE <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
      </section>

      <Pager current="/structures" />
    </>
  );
}
