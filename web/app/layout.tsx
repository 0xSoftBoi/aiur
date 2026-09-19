import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site-footer";
import { SceneGate } from "@/components/scene-gate";
import { ScrollReveal } from "@/components/scroll-reveal";
import { SiteHeader } from "@/components/site-header";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AIUR — Stratospheric Observation",
    template: "%s — AIUR",
  },
  description:
    "Small lighter-than-air packages that climb into the stratosphere, observe, report, and come back.",
  metadataBase: new URL("https://aiur.vercel.app"),
  openGraph: {
    title: "AIUR — Stratospheric Observation",
    description:
      "Go up, look down, come back. STRATO-P0 is the first observation article.",
    type: "website",
  },
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#070808",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SceneGate />
        <ScrollReveal />
        <a className="skip-link" href="#top">
          Skip to content
        </a>
        <SiteHeader />
        <main id="top">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
