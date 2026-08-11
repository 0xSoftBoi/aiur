import Link from "next/link";

import { FOOTER_NAV } from "@/lib/site-content";

export function SiteFooter() {
  return (
    <footer className="footer">
      <div className="shell footer-top">
        <div className="footer-brand">
          <Link className="brand" href="/">
            <span className="brand-mark" aria-hidden="true">
              <i />
              <i />
            </span>
            AIUR
          </Link>
          <p>Persistent airborne infrastructure for autonomous aircraft.</p>
        </div>

        {FOOTER_NAV.map((column) => (
          <nav key={column.heading} aria-label={column.heading}>
            <h3>{column.heading}</h3>
            {column.links.map(([label, href]) =>
              href.startsWith("http") ? (
                <a key={label} href={href} target="_blank" rel="noreferrer">
                  {label}
                </a>
              ) : (
                <Link key={label} href={href}>
                  {label}
                </Link>
              ),
            )}
          </nav>
        ))}
      </div>

      <div className="shell footer-bottom">
        <span>© 2026 AIUR / CARRIER-P0</span>
        <span>Targets shown are exit criteria, not claimed results.</span>
      </div>
    </footer>
  );
}
