import Link from "next/link";

import { CARRIER_SPEC } from "@/lib/carrier-spec";
import { AppCard } from "@/components/app-card";
import { APPLICATIONS, NEWS, REPO_URL } from "@/lib/site-content";

export default function Home() {
  return (
    <>
      <section className="hero shell" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow"><span>AIUR / 001</span> PERSISTENT AIRBORNE INFRASTRUCTURE</p>
          <h1 id="hero-title">
            Stay up.
            <br />
            <strong>Come back.</strong>
          </h1>
          <p className="lede">
            Aiur builds carrier systems that launch and recover autonomous
            aircraft without a runway, a net, or a crew on the ground.
          </p>
          <p className="hero-proof">
            One article on the bench today, four gates to get through, and the
            whole design record in public. Every number below is an exit
            criterion, not a result we are claiming.
          </p>
          <div className="hero-actions">
            <a className="button" href={REPO_URL} target="_blank" rel="noreferrer">
              Read the engineering log <span aria-hidden="true">↗</span>
            </a>
            <Link className="text-link" href="/solutions">
              How the loop works <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>

        <aside className="hero-article" aria-label="Current engineering article">
          <div className="article-state">
            <span className="status-dot" />
            BUILDING NOW
          </div>
          <strong>CARRIER-P0</strong>
          <p>Recovery first. Indoor helium article. Micro-UAV class. No claimed flight demo.</p>
        </aside>

        <div className="spec-rail" data-reveal aria-label="Carrier P0 reference dimensions">
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
      </section>

      <section className="mission paper-section" aria-labelledby="mission-title">
        <div className="shell">
          <p className="kicker">Our mission</p>
          <h2 className="statement" data-reveal id="mission-title">
            A small aircraft can only go as far as the thing that gets it back.
            So we are building <strong>that thing first</strong>, on a bench,
            before anyone claims it works in flight.
          </h2>
        </div>
      </section>

      <section className="applications" aria-labelledby="applications-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / APPLICATIONS</span>
            <span>WHERE THE LOOP PAYS</span>
          </div>
          <div className="section-head">
            <h2 id="applications-title">Where this is useful</h2>
            <p className="section-lede">
              The carrier is useful wherever the limiting factor is not the aircraft
              but everything the aircraft has to leave behind.
            </p>
          </div>

          <div className="app-grid">
            {APPLICATIONS.slice(0, 3).map((app, index) => (
              <AppCard app={app} index={index} key={app.slug} />
            ))}
          </div>

          <div className="section-foot">
            <Link className="text-link" href="/applications">
              All six areas <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>

      <section className="thesis paper-section" aria-labelledby="thesis-title">
        <div className="shell">
          <div className="section-meta">
            <span>02 / THE SYSTEM</span>
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
          <div className="section-foot">
            <Link className="text-link dark-link" href="/solutions">
              How the loop closes <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>

      <section
        className="careers"
        aria-labelledby="careers-title"
        style={{ backgroundImage: "url(/renders/dock-hero.png)" }}
      >
        <div className="shell careers-inner">
          <p className="kicker">Careers</p>
          <h2 id="careers-title">Join the adventure</h2>
          <p className="section-lede">
            Aiur is small, physical, and unglamorous by design. If you would rather
            close a loop on a bench than draw one on a slide, this is the place.
          </p>
          <Link className="button" href="/careers">
            Work with us <span aria-hidden="true">→</span>
          </Link>
        </div>
      </section>

      <section className="news" aria-labelledby="news-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>03 / NEWS</span>
            <span>PUBLIC / VERSIONED</span>
          </div>
          <div className="section-head">
            <h2 id="news-title">What changed recently</h2>
            <p className="section-lede">
              The public record is the product record. Design decisions, gates,
              geometry, and evidence tooling live in the engineering repository.
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

          <div className="section-foot">
            <Link className="text-link" href="/resources">
              Everything we have published <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </section>

    </>
  );
}
