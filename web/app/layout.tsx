import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AIUR — Airborne Infrastructure",
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
      <body>{children}</body>
    </html>
  );
}
