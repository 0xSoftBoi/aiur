import Link from "next/link";

import { PAGE_ORDER } from "@/lib/site-content";

/** Prev / next rail so an interior page has somewhere to go but the footer. */
export function Pager({ current }: { current: string }) {
  const index = PAGE_ORDER.findIndex(([href]) => href === current);
  if (index === -1) return null;

  const previous = PAGE_ORDER[index - 1];
  const next = PAGE_ORDER[index + 1];

  return (
    <nav className="pager" aria-label="Section">
      <div className="shell pager-inner">
        {previous ? (
          <Link href={previous[0]} className="pager-link prev">
            <span>Previous</span>
            <strong>
              <i aria-hidden="true">←</i> {previous[1]}
            </strong>
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link href={next[0]} className="pager-link next">
            <span>Next</span>
            <strong>
              {next[1]} <i aria-hidden="true">→</i>
            </strong>
          </Link>
        ) : (
          <span />
        )}
      </div>
    </nav>
  );
}
