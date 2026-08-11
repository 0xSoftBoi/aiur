"use client";

import { usePathname } from "next/navigation";

import { CarrierSceneLoader } from "@/components/carrier-scene-loader";

/**
 * The live carrier scene is the home page's argument for itself. Behind an
 * interior page it is just a large grey airframe competing with the type, so
 * it renders on "/" only.
 */
export function SceneGate() {
  const pathname = usePathname();
  if (pathname !== "/") return null;
  return <CarrierSceneLoader />;
}
