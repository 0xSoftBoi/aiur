import type { Metadata } from "next";

import { PageHead } from "@/components/page-head";
import { Pager } from "@/components/pager";
import { REPO_URL } from "@/lib/site-content";

export const metadata: Metadata = {
  title: "Careers",
  description:
    "Aiur is small, physical, and unglamorous by design. The engineering repository is the front door.",
};

const WHAT_WE_LOOK_FOR = [
  {
    id: "01",
    title: "Payload and thermal",
    copy:
      "People who can take a mass allocation and a −55 °C soak to a package that keeps imaging, tracking, and terminating, and who treat a dropout as data rather than embarrassment.",
  },
  {
    id: "02",
    title: "Avionics and links",
    copy:
      "Trackers on separate power, a termination path that needs no computer, and a downlink whose margin is budgeted before it is trusted. Chamber first, tether later.",
  },
  {
    id: "03",
    title: "Test engineering",
    copy:
      "Instrumentation and evidence reduction — the part of the programme that decides whether a gate actually passed.",
  },
  {
    id: "04",
    title: "Modelling",
    copy:
      "An atmosphere, ascent, and geometry model that stays honest about what it does not model, and that loses arguments to the flight log.",
  },
] as const;

export default function CareersPage() {
  return (
    <>
      <PageHead
        eyebrow="Careers"
        index="05 / 05"
        title={
          <>
            Come build
            <br />
            <strong>the hard part</strong>
          </>
        }
        lede="Aiur is small, physical, and unglamorous by design. If you would rather close a loop on a bench than draw one on a slide, this is the place."
      />

      <section className="applications" id="roles" aria-labelledby="roles-title">
        <div className="shell">
          <div className="section-meta light-meta">
            <span>01 / WHO WE NEED</span>
            <span>NO OPEN REQS YET</span>
          </div>
          <div className="section-head">
            <h2 id="roles-title">What we look for</h2>
            <p className="section-lede">
              There is no formal job board. These are the shapes of work the
              programme currently generates.
            </p>
          </div>

          <div className="rule-list light-rules" data-reveal>
            {WHAT_WE_LOOK_FOR.map((role) => (
              <article key={role.id}>
                <span className="program-id">{role.id}</span>
                <h3>{role.title}</h3>
                <p>{role.copy}</p>
              </article>
            ))}
          </div>

          <div className="note-band" id="apply" data-reveal>
            <span>HOW TO APPLY</span>
            <p>
              Aiur has no recruiting inbox published yet. The engineering repository
              is the front door: read the open programme, and open an issue or a
              pull request on something you would do differently.
            </p>
          </div>

          <div className="section-foot">
            <a className="button" href={REPO_URL} target="_blank" rel="noreferrer">
              See how we work <span aria-hidden="true">↗</span>
            </a>
          </div>
        </div>
      </section>
      <Pager current="/careers" />
    </>
  );
}
