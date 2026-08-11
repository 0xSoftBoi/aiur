import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site-footer";
import { SceneGate } from "@/components/scene-gate";
import { ScrollReveal } from "@/components/scroll-reveal";
import { SiteHeader } from "@/components/site-header";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AIUR — Airborne Infrastructure",
    template: "%s — AIUR",
  },
  description:
    "A lighter-than-air carrier built to deploy, coordinate, and recover autonomous aircraft.",
  metadataBase: new URL("https://aiur.vercel.app"),
  openGraph: {
    title: "AIUR — Airborne Infrastructure",
    description:
      "The carrier is the infrastructure. CARRIER-P0 is the first recovery article.",
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
