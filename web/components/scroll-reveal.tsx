"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/**
 * Reveals any [data-reveal] element once it enters the viewport by flipping it
 * to data-revealed. Elements start hidden only when this script is live, so a
 * no-JS or reduced-motion visitor sees the finished page immediately.
 */
export function ScrollReveal() {
  const pathname = usePathname();

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));

    if (reduced || typeof IntersectionObserver === "undefined") {
      nodes.forEach((node) => node.setAttribute("data-revealed", ""));
      return;
    }

    document.documentElement.setAttribute("data-reveal-ready", "");

    let delivered = false;

    const observer = new IntersectionObserver(
      (entries) => {
        delivered = true;
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.setAttribute("data-revealed", "");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 },
    );

    nodes.forEach((node) => observer.observe(node));

    // Fail open. Hiding content is done in CSS, so an observer that never
    // delivers a callback would leave the page permanently blank rather than
    // merely un-animated. If nothing has been delivered by the time the first
    // scroll would plausibly have happened, drop the effect and show
    // everything. A working observer always delivers an initial batch, so this
    // does not fire on a healthy page.
    const failOpen = window.setTimeout(() => {
      if (delivered) return;
      observer.disconnect();
      nodes.forEach((node) => node.setAttribute("data-revealed", ""));
    }, 1200);

    return () => {
      window.clearTimeout(failOpen);
      observer.disconnect();
    };
  }, [pathname]);

  return null;
}
