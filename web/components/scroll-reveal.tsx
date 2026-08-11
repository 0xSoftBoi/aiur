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

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.setAttribute("data-revealed", "");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 },
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [pathname]);

  return null;
}
