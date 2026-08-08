import { CarrierSceneLoader } from "@/components/carrier-scene-loader";
import { CARRIER_SPEC } from "@/lib/carrier-spec";

const SYSTEM_LOOP = [
  {
    index: "01",
    title: "DEPLOY",
    copy: "Release mission aircraft from persistent infrastructure already in the air.",
  },
  {
    index: "02",
    title: "COORDINATE",
    copy: "Keep mission state, communications, and eventually edge compute with the carrier.",
  },
  {
    index: "03",
    title: "RECOVER",
    copy: "Bring the aircraft back through a physical interface that can seat, retain, verify, and release.",
  },
  {
    index: "04",
    title: "REPEAT",
    copy: "Turn a one-way sortie into a reusable loop, then add energy and fleet scale.",
  },
] as const;

const BENCH_GATE = [
  ["50", "CAPTURE / RELEASE CYCLES"],
  ["≥5 N", "AXIAL RETENTION / 10 S"],
  ["≥1 N", "LATERAL ±X / ±Y / 10 S"],
  ["10", "POWER-OFF MANUAL RELEASES"],
] as const;

const PROGRAM = [
  ["P0-A", "BENCH CAPTURE", "ACTIVE", "Positive retention + independent physical truth"],
  ["P0-B", "MOVING DOCK", "LOCKED", "Earn dynamic approach only after the bench gate"],
  ["P0-C", "TETHERED CARRIER", "LOCKED", "Integrate the recovery article with buoyant lift"],
  ["P0-D", "TWO AIRCRAFT", "LOCKED", "Prove separation, sequencing, and repeated recovery"],
] as const;

const RELEASES = [
  {
    id: "001",
    title: "CARRIER-P0 PROGRAM",
    copy: "Closed-loop architecture, payload budget, and evidence gates.",
    href: "https://github.com/0xSoftBoi/aiur/pull/1",
  },
  {
    id: "002",
    title: "P0-A BENCH ARTICLE",
    copy: "A dimensioned recovery interface with explicit pass / fail criteria.",
    href: "https://github.com/0xSoftBoi/aiur/pull/2",
  },
  {
    id: "003",
    title: "REV-A FABRICATION PACK",
    copy: "Reproducible CAD, fabrication geometry, and strict evidence reduction.",
    href: "https://github.com/0xSoftBoi/aiur/pull/3",
  },
] as const;

export default function Home() {
  return (
    <main id="top">
      <CarrierSceneLoader />

      <header className="nav shell">
        <a className="brand" href="#top" aria-label="Aiur home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
          </span>
          AIUR
        </a>
        <div className="nav-center" aria-label="Program status">
          <span>AIRBORNE AUTONOMY</span>
          <span className="status-dot" />
          <span>P0-A / ACTIVE</span>
        </div>
        <a
          className="nav-link"
          href="https://github.com/0xSoftBoi/aiur"
          target="_blank"
          rel="noreferrer"
        >
          ENGINEERING <span aria-hidden="true">↗</span>
        </a>
      </header>

      <section className="hero shell" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow"><span>AIUR / 001</span> PERSISTENT AIRBORNE INFRASTRUCTURE</p>
          <h1 id="hero-title">
            KEEP AUTONOMY
            <br />
            <em>IN THE AIR.</em>
          </h1>
          <p className="lede">
            Aiur is building carrier systems that deploy, coordinate, and recover
            autonomous aircraft from persistent infrastructure in the sky.
          </p>
        </div>

        <aside className="hero-article" aria-label="Current engineering article">
          <div className="article-state">
            <span className="status-dot" />
            BUILDING NOW
          </div>
          <strong>CARRIER-P0</strong>
          <p>Recovery first. Indoor helium article. Micro-UAV class. No claimed flight demo.</p>
        </aside>

        <div className="spec-rail" aria-label="Carrier P0 reference dimensions">
          <div>
            <span>REFERENCE AIRFRAME</span>
            <strong>{CARRIER_SPEC.envelopeLengthM.toFixed(1)} M</strong>
          </div>
          <div>
            <span>HELIUM VOLUME</span>
            <strong>{CARRIER_SPEC.heliumVolumeM3.toFixed(1)} M³</strong>
          </div>
          <div>
            <span>VENDOR-RATED PAYLOAD</span>
            <strong>≤{CARRIER_SPEC.ratedPayloadKg.toFixed(1)} KG</strong>
          </div>
          <div>
            <span>REV-A DOCK MOUTH</span>
            <strong>Ø{Math.round(CARRIER_SPEC.dockMouthDiameterM * 1000)} MM</strong>
          </div>
        </div>

        <div className="scroll-cue" aria-hidden="true">
          <span>SCROLL / CLOSE THE LOOP</span>
          <i />
        </div>
      </section>

      <section className="thesis paper-section" id="system" aria-labelledby="thesis-title">
        <div className="shell">
          <div className="section-meta">
            <span>01 / THE SYSTEM</span>
            <span>AUTONOMY × INFRASTRUCTURE</span>
          </div>
          <p className="thesis-kicker">A drone is an aircraft. Persistence is a system.</p>
          <h2 id="thesis-title">
            LAUNCHING IS EASY.
            <br />
            <em>RECOVERY CLOSES THE LOOP.</em>
          </h2>
          <p className="section-lede dark-lede">
            Endurance, energy, backhaul, and fleet coordination all get harder at
            the edge. Aiur moves infrastructure with the mission instead of making
            every aircraft carry the entire problem alone.
          </p>

          <div className="system-loop" aria-label="Aiur autonomous carrier loop">
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

      <section className="evidence" id="evidence" aria-labelledby="evidence-title">
        <div className="shell evidence-layout">
          <div className="evidence-copy">
            <div className="section-meta light-meta">
              <span>02 / PHYSICAL TRUTH</span>
              <span>REV-A / BENCH</span>
            </div>
            <p className="eyebrow">THE HARD PART FIRST</p>
            <h2 id="evidence-title">
              SOFTWARE ENDS
              <br />
              <em>AT THE DOCK.</em>
            </h2>
            <p className="section-lede">
              The first article is deliberately unglamorous: a Ø180 mm recovery
              mouth, positive mechanical keeper, two independent physical contacts,
              and a manual release that still works with controller and actuator power removed.
            </p>
            <p className="evidence-note">
              P0-A is a bench gate, not a marketing milestone. Propellers stay off.
              Missing evidence is a failed gate.
            </p>
          </div>

          <div className="gate-panel" aria-label="P0-A exit criteria">
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

      <section className="carrier-vision" id="carrier" aria-labelledby="carrier-title">
        <div className="shell carrier-copy">
          <div className="section-meta light-meta">
            <span>03 / NORTH STAR</span>
            <span>CARRIER SYSTEMS</span>
          </div>
          <p className="eyebrow">THE AIRCRAFT IS ONLY ONE LAYER</p>
          <h2 id="carrier-title">
            THE CARRIER IS
            <br />
            <em>THE INFRASTRUCTURE.</em>
          </h2>
          <p className="section-lede">
            At scale, the carrier becomes the fleet&apos;s compute, communications,
            energy, deployment, and recovery layer. Small mission aircraft can stay
            small because the expensive capabilities live somewhere persistent.
          </p>

          <div className="carrier-capabilities" aria-label="Long-term carrier capabilities">
            <div><span>01</span><strong>PERSISTENT LIFT</strong></div>
            <div><span>02</span><strong>EDGE COMPUTE</strong></div>
            <div><span>03</span><strong>FLEET COMMS</strong></div>
            <div><span>04</span><strong>RECOVERY + ENERGY</strong></div>
          </div>

          <div className="scale-disclosure">
            <span>VISUALIZATION DISCLOSURE</span>
            <p>
              The live model uses 1 world unit = 1 meter. Published P0 length,
              helium volume, dock, and UAV dimensions anchor scale. Envelope diameter
              is volume-matched because the vendor does not publish that dimension.
            </p>
          </div>
        </div>
      </section>

      <section className="program paper-section" id="program" aria-labelledby="program-title">
        <div className="shell">
          <div className="section-meta">
            <span>04 / PROGRAM</span>
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

          <div className="program-list">
            {PROGRAM.map(([id, title, status, copy]) => (
              <article className={status === "ACTIVE" ? "active" : undefined} key={id}>
                <span className="program-id">{id}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
                <span className="program-status">{status}</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="releases" id="releases" aria-labelledby="releases-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>05 / ENGINEERING LOG</span>
            <span>PUBLIC / VERSIONED</span>
          </div>
          <div className="release-heading">
            <h2 id="releases-title">WHAT&apos;S REAL.</h2>
            <p>
              The public record is the product record. Design decisions, gates,
              geometry, and evidence tooling live in the engineering repository.
            </p>
          </div>

          <div className="release-list">
            {RELEASES.map((release) => (
              <a key={release.id} href={release.href} target="_blank" rel="noreferrer">
                <span>{release.id}</span>
                <div>
                  <strong>{release.title}</strong>
                  <p>{release.copy}</p>
                </div>
                <i aria-hidden="true">↗</i>
              </a>
            ))}
          </div>

          <div className="release-cta">
            <span>DESIGN RULE / 001</span>
            <strong>CONCEPT ART IS NOT EVIDENCE.</strong>
            <a href="https://github.com/0xSoftBoi/aiur" target="_blank" rel="noreferrer">
              OPEN THE ENGINEERING REPO <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
      </section>

      <footer className="footer shell">
        <a className="brand" href="#top">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
          </span>
          AIUR
        </a>
        <p>PERSISTENT AIRBORNE INFRASTRUCTURE.</p>
        <span>© 2026 / CARRIER-P0</span>
      </footer>
    </main>
  );
}
