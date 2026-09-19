import Link from "next/link";

import { STRATO_SPEC } from "@/lib/strato-spec";
import { AppCard } from "@/components/app-card";
import { APPLICATIONS, NEWS, REPO_URL } from "@/lib/site-content";

export default function Home() {
  return (
    <>
      <section className="hero shell" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow"><span>AIUR / 002</span> STRATOSPHERIC OBSERVATION</p>
          <h1 id="hero-title">
            Go up.
            <br />
            <strong>Look down.</strong>
          </h1>
          <p className="lede">
            Aiur builds small observation packages that climb into the
            stratosphere, look down over a five-hundred-kilometre horizon,
            report what they see, and come back.
          </p>
          <p className="hero-proof">
            No aircraft, no dock, no deployable payload. One article to build,
            three gates to get through, and the whole design record in public.
            Every number below is a model result or an exit criterion, not a
            flight we are claiming.
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
          <strong>STRATO-P0</strong>
          <p>Observation first. Latex sounding article. Sub-kilogram package. Helium only. No claimed flight.</p>
        </aside>

        <div className="spec-rail" data-reveal aria-label="STRATO-P0 reference figures">
          <div>
            <span>STRATOSPHERIC THRESHOLD</span>
            <strong>{(STRATO_SPEC.thresholdAltitudeM / 1000).toFixed(0)} KM</strong>
          </div>
          <div>
            <span>HORIZON FROM THERE</span>
            <strong>{Math.round(STRATO_SPEC.horizonDistanceKm)} KM</strong>
          </div>
          <div>
            <span>PACKAGE CEILING</span>
            <strong>≤{STRATO_SPEC.payloadCeilingKg.toFixed(1)} KG</strong>
          </div>
          <div>
            <span>NADIR GSD / REF. OPTIC</span>
            <strong>{STRATO_SPEC.nadirGsdM.toFixed(1)} M</strong>
          </div>
        </div>
      </section>

      <section className="mission paper-section" aria-labelledby="mission-title">
        <div className="shell">
          <p className="kicker">Our mission</p>
          <h2 className="statement" data-reveal id="mission-title">
            A satellite is a schedule. A balloon is a decision. We are building
            the cheapest package that can make <strong>that decision pay</strong>,
            in a cold chamber, before anyone claims it works in flight.
          </h2>
        </div>
      </section>

      <section className="applications" aria-labelledby="applications-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / APPLICATIONS</span>
            <span>WHERE THE VIEW PAYS</span>
          </div>
          <div className="section-head">
            <h2 id="applications-title">Where this is useful</h2>
            <p className="section-lede">
              The package is useful wherever a regional picture is worth more
              today than a sharper one next week.
            </p>
          </div>

          <div className="app-grid" data-reveal>
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
            <span>ALTITUDE × EVIDENCE</span>
          </div>
          <p className="thesis-kicker">Altitude is cheap. Coming back with the picture is the job.</p>
          <h2 id="thesis-title">
            GETTING UP IS EASY.
            <br />
            <em>RETURNING CLOSES THE LOOP.</em>
          </h2>
          <p className="section-lede dark-lede">
            Cold, power, tracking, termination, and the landing all get harder
            above the tropopause. Aiur treats each one as a gate with a number,
            not as a risk to carry into the first free flight.
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
        style={{ backgroundImage: "url(/strato-altitude-ladder.svg)" }}
      >
        <div className="shell careers-inner">
          <p className="kicker">Careers</p>
          <h2 id="careers-title">Join the adventure</h2>
          <p className="section-lede">
            Aiur is small, physical, and unglamorous by design. If you would rather
            close a loop in a cold chamber than draw one on a slide, this is the place.
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
              models, and evidence tooling live in the engineering repository.
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
