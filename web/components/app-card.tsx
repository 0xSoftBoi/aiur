import type { CSSProperties } from "react";

type Application = {
  id: string;
  slug: string;
  accent: string;
  title: string;
  copy: string;
};

/**
 * Aiur has renders of one airframe and one dock, not photographs of six
 * application domains. Cropping the same grey object six ways read as a lamp
 * and a tent, so each card is built from an accent field, a plotted index, and
 * a technical grid instead of pretending to be photography.
 */
export function AppCard({ app, index }: { app: Application; index: number }) {
  return (
    <article
      className="app-card"
      id={app.slug}
      data-reveal
      style={
        {
          "--accent": app.accent,
          "--delay": `${(index % 3) * 70}ms`,
        } as CSSProperties
      }
    >
      <div className="app-media" aria-hidden="true">
        <span className="app-field" />
        <span className="app-grid-lines" />
        <span className="app-numeral">{app.id}</span>
        <span className="app-tag">{app.title}</span>
      </div>
      <div className="app-body">
        <h3>{app.title}</h3>
        <p>{app.copy}</p>
        <span className="app-rule" aria-hidden="true" />
      </div>
    </article>
  );
}
