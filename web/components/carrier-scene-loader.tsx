"use client";

import dynamic from "next/dynamic";

const CarrierScene = dynamic(
  () => import("./carrier-scene").then((module) => module.CarrierScene),
  {
    ssr: false,
    loading: () => (
      <div className="scene" aria-hidden="true" data-renderer="booting">
        <div className="scene-hud">
          <span>RENDER / LOAD</span>
          <span>METRIC WORLD</span>
        </div>
      </div>
    ),
  },
);

export function CarrierSceneLoader() {
  return <CarrierScene />;
}
