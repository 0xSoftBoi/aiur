import { CarrierSceneLoader } from "@/components/carrier-scene-loader";
import { CARRIER_SPEC } from "@/lib/carrier-spec";

const loop = [
  ["01", "DEPLOY", "Release one aircraft into a bounded sortie."],
  ["02", "COORDINATE", "Keep navigation, comms, and mission state with the carrier."],
  ["03", "RECOVER", "Guide a 100 mm-class vehicle into a positive belly dock."],
  ["04", "REPEAT", "Turn recovery into infrastructure, then scale the fleet."],
] as const;

export default function Home() {
  return (
    <main>
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
          <span>CARRIER-P0</span>
          <span className="status-dot" />
          <span>BENCH PROGRAM</span>
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

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">
            <span>001</span> PERSISTENT AIRBORNE INFRASTRUCTURE
          </p>
          <h1>
            THE CARRIER
            <br />
            IS THE <em>BASE.</em>
          </h1>
          <p className="lede">
            A buoyant autonomous mothership that deploys, coordinates, recovers,
            and eventually recharges its own air fleet.
          </p>
        </div>

        <div className="hero-side mono-card">
          <span className="mono-label">CURRENT ARTICLE</span>
          <strong>P0 / HELIUM</strong>
          <p>One active belly dock. One to two micro-UAVs. Indoor, tethered, measured.</p>
        </div>

        <div className="spec-rail" aria-label="Carrier P0 key dimensions">
          <div>
            <span>ENVELOPE</span>
            <strong>{CARRIER_SPEC.envelopeLengthM.toFixed(1)} M</strong>
          </div>
          <div>
            <span>HELIUM</span>
            <strong>{CARRIER_SPEC.heliumVolumeM3.toFixed(1)} M³</strong>
          </div>
          <div>
            <span>DOCK MOUTH</span>
            <strong>{Math.round(CARRIER_SPEC.dockMouthDiameterM * 1000)} MM</strong>
          </div>
          <div>
            <span>UAV FRAME</span>
            <strong>{Math.round(CARRIER_SPEC.droneMotorDiagonalM * 1000)} MM</strong>
          </div>
        </div>

        <div className="scroll-cue" aria-hidden="true">
          <span>SCROLL / FOLLOW THE SORTIE</span>
          <i />
        </div>
      </section>

      <section className="story story-left shell" id="mission">
        <div className="story-index">01 / THESIS</div>
        <div className="story-copy">
          <p className="eyebrow">THE BOTTLENECK ISN&apos;T ANOTHER DRONE</p>
          <h2>
            DRONES NEED
            <br />
            SOMEWHERE TO <em>COME HOME.</em>
          </h2>
          <p>
            Range, battery, backhaul, and recovery all compound at the edge. Aiur
            moves the base station into the air: persistent lift above, fast aircraft
            below.
          </p>
        </div>
        <aside className="datum datum-right">
          <span>RENDER SCALE</span>
          <strong>1 UNIT = 1 M</strong>
          <small>
            Drone, dock, and envelope length are rendered from the P0 engineering
            model. Envelope diameter is volume-matched to 5.5 m³.
          </small>
        </aside>
      </section>

      <section className="story story-right shell" id="loop">
        <div className="story-index">02 / LOOP</div>
        <div className="loop-panel">
          <p className="eyebrow">THE PRODUCT IS THE CYCLE</p>
          <h2>DEPLOY. RECOVER. REPEAT.</h2>
          <div className="loop-grid">
            {loop.map(([index, title, copy]) => (
              <article key={title}>
                <span>{index}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="story story-left shell" id="dock">
        <div className="story-index">03 / RECOVERY</div>
        <div className="story-copy compact">
          <p className="eyebrow">THE HARD PART FIRST</p>
          <h2>
            MAKE RECOVERY
            <br />
            <em>BORING.</em>
          </h2>
          <p>
            P0 does not chase a 40 m airframe or airborne data center. It proves the
            belly interface first: seat, positively retain, confirm with independent
            physical sensing, release, repeat.
          </p>
        </div>
        <div className="dock-metrics">
          <div>
            <span>FUNNEL</span>
            <strong>Ø180</strong>
            <small>MM</small>
          </div>
          <div>
            <span>PROBE TIP</span>
            <strong>110</strong>
            <small>MM ABOVE PROP PLANE</small>
          </div>
          <div>
            <span>CLOSING LIMIT</span>
            <strong>≤0.20</strong>
            <small>M/S TARGET</small>
          </div>
        </div>
      </section>

      <section className="proof" id="program">
        <div className="shell proof-inner">
          <div className="story-index">04 / PROGRAM</div>
          <p className="eyebrow">NORTH STAR / EVIDENCE FIRST</p>
          <h2>
            FROM ONE DOCK
            <br />
            TO AN <em>AIRBORNE FLEET.</em>
          </h2>
          <p className="proof-lede">
            The long-range idea is carrier-scale compute, energy, communications,
            and a fleet that can return to its own infrastructure. The current job
            is smaller and harder to fake: close P0-A, then earn moving recovery.
          </p>

          <div className="program-grid">
            <article className="active">
              <span>P0-A</span>
              <strong>BENCH CAPTURE</strong>
              <p>50 cycles · load screens · independent capture truth</p>
              <i>ACTIVE</i>
            </article>
            <article>
              <span>P0-B</span>
              <strong>MOVING DOCK</strong>
              <p>Suspended interface · ≥9/10 captures · zero rotor contact</p>
              <i>LOCKED</i>
            </article>
            <article>
              <span>P0-C</span>
              <strong>TETHERED CARRIER</strong>
              <p>Helium article · full payload · autonomous recovery</p>
              <i>LOCKED</i>
            </article>
            <article>
              <span>P0-D</span>
              <strong>TWO AIRCRAFT</strong>
              <p>Sequential release · recovery · positive separation</p>
              <i>LOCKED</i>
            </article>
          </div>

          <div className="proof-footer">
            <div>
              <span>DESIGN RULE</span>
              <strong>CONCEPT ART IS NOT EVIDENCE.</strong>
            </div>
            <a
              href="https://github.com/0xSoftBoi/aiur"
              target="_blank"
              rel="noreferrer"
            >
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
        <p>BUILD THE CARRIER.</p>
        <span>© 2026 / CARRIER-P0</span>
      </footer>
    </main>
  );
}
