import type { ReactNode } from "react";

export function PageHead({
  eyebrow,
  index,
  title,
  lede,
}: {
  eyebrow: string;
  index?: string;
  title: ReactNode;
  lede: string;
}) {
  return (
    <section className="page-head">
      <div className="shell">
        <div className="page-head-meta">
          <p className="kicker">{eyebrow}</p>
          {index ? <span className="page-head-index">{index}</span> : null}
        </div>
        <h1>{title}</h1>
        <p className="lede">{lede}</p>
      </div>
      <div className="page-head-rule" aria-hidden="true" />
    </section>
  );
}
