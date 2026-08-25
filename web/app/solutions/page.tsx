import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { SYSTEM_LOOP } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Solutions",
  description:
    "The carrier loop: deploy, coordinate, recover, repeat — and why recovery is the hard part.",
};

export default function SolutionsPage() {
  return (
    <>
      <PageHead
        eyebrow="Solutions"
        index="01 / 05"
        title={
          <>
            Launching is easy.
            <br />
            <strong>Recovery isn&apos;t.</strong>
          </>
        }
        lede="Endurance, energy, backhaul, and fleet coordination all get harder at the edge. Aiur moves infrastructure with the mission instead of making every aircraft carry the entire problem alone."
      />

      <section className="thesis paper-section" id="loop" aria-labelledby="loop-title">
        <div className="shell">
          <div className="section-meta">
            <span>01 / THE SYSTEM</span>
            <span>AUTONOMY × INFRASTRUCTURE</span>
          </div>
          <p className="thesis-kicker">A drone is an aircraft. Persistence is a system.</p>
          <h2 id="loop-title">
            THE CARRIER
            <br />
            <em>LOOP.</em>
          </h2>
          <p className="section-lede dark-lede">
            Four steps, each one earned before the next. The loop is the product;
            the aircraft is a passenger in it.
          </p>

          <div className="system-loop" data-reveal aria-label="Aiur autonomous carrier loop">
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

      <section className="carrier-vision" id="carrier" aria-labelledby="carrier-title">
        <div className="shell carrier-copy">
          <div className="section-meta light-meta">
            <span>02 / NORTH STAR</span>
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

          <figure className="render-frame" data-reveal>
            <Image
              src="/renders/carrier-v1-hero.png"
              alt="CARRIER-P0 rendered from the animated scene: hull, gondola, propulsion, and belly dock"
              width={1920}
              height={1080}
              sizes="(max-width: 900px) 100vw, 900px"
            />
            <figcaption className="render-caption">
              <span>CARRIER-P0 / GENERAL ARRANGEMENT</span>
              <strong>RENDERED, NOT PHOTOGRAPHED</strong>
            </figcaption>
          </figure>

          <figure className="render-frame" data-reveal>
            <video
              src="/renders/carrier-p0-breakdown.mp4"
              poster="/renders/carrier-p0-breakdown-poster.jpg"
              controls
              muted
              loop
              playsInline
              preload="none"
              width={1920}
              height={1080}
              aria-label="CARRIER-P0 assembly breakdown and belly-dock capture, rendered from the engineering geometry"
            />
            <figcaption className="render-caption">
              <span>CARRIER-P0 / ASSEMBLY AND CAPTURE</span>
              <strong>APPROACH FLOWN BY THE SIMULATOR</strong>
            </figcaption>
          </figure>

          <div className="carrier-capabilities" data-reveal aria-label="Long-term carrier capabilities">
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
