"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import {
  CARRIER_SPEC,
  EQUIVALENT_ENVELOPE_DIAMETER_M,
} from "@/lib/carrier-spec";

type RendererState = "booting" | "ready" | "unavailable";

const WHITE = 0xe9ece8;
const GRAPHITE = 0x151819;
const BLACK = 0x070808;
const AMBER = 0xff6b24;
const COOL = 0x73a3ad;

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function smoothstep(min: number, max: number, value: number) {
  const x = clamp01((value - min) / (max - min));
  return x * x * (3 - 2 * x);
}

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

function makeMicroDrone(materials: {
  carbon: THREE.Material;
  metal: THREE.Material;
  rotor: THREE.Material;
  light: THREE.Material;
}) {
  const group = new THREE.Group();
  const halfAxis = CARRIER_SPEC.droneMotorDiagonalM / (2 * Math.sqrt(2));
  const armLength = halfAxis * 2.35;
  const armGeometry = new THREE.BoxGeometry(armLength, 0.006, 0.008);
  const bodyGeometry = new THREE.BoxGeometry(0.032, 0.014, 0.025);
  const motorGeometry = new THREE.CylinderGeometry(0.006, 0.006, 0.012, 12);
  const rotorGeometry = new THREE.TorusGeometry(
    CARRIER_SPEC.dronePropDiameterM / 2,
    0.00065,
    4,
    28,
  );

  const armA = new THREE.Mesh(armGeometry, materials.carbon);
  armA.rotation.y = Math.PI / 4;
  const armB = armA.clone();
  armB.rotation.y = -Math.PI / 4;
  group.add(armA, armB, new THREE.Mesh(bodyGeometry, materials.carbon));

  const motorLocations: Array<[number, number]> = [
    [halfAxis, halfAxis],
    [halfAxis, -halfAxis],
    [-halfAxis, halfAxis],
    [-halfAxis, -halfAxis],
  ];
  motorLocations.forEach(([x, z]) => {
    const motor = new THREE.Mesh(motorGeometry, materials.metal);
    motor.position.set(x, 0.007, z);
    const rotor = new THREE.Mesh(rotorGeometry, materials.rotor);
    rotor.rotation.x = Math.PI / 2;
    rotor.position.set(x, 0.015, z);
    group.add(motor, rotor);
  });

  const navLight = new THREE.Mesh(new THREE.SphereGeometry(0.003, 8, 8), materials.light);
  navLight.position.set(0.014, 0.008, 0);
  group.add(navLight);

  // P0 probe: 110 mm from tip to prop plane, drawn at the same metric scale.
  const probe = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0015, 0.0015, 0.1, 8),
    materials.metal,
  );
  probe.position.y = 0.058;
  const probeHead = new THREE.Mesh(
    new THREE.SphereGeometry(0.006, 12, 8),
    materials.metal,
  );
  probeHead.scale.y = 0.7;
  probeHead.position.y = CARRIER_SPEC.droneProbeStandoffM;
  group.add(probe, probeHead);

  return group;
}

function addCarrier(scene: THREE.Scene) {
  const carrier = new THREE.Group();
  carrier.name = "CARRIER-P0";

  const hullMaterial = new THREE.MeshPhysicalMaterial({
    color: GRAPHITE,
    roughness: 0.34,
    metalness: 0.04,
    clearcoat: 0.22,
    clearcoatRoughness: 0.5,
    sheen: 0.24,
    sheenColor: new THREE.Color(0x5f6666),
  });
  const structuralMaterial = new THREE.MeshStandardMaterial({
    color: 0x232829,
    roughness: 0.42,
    metalness: 0.62,
  });
  const darkMaterial = new THREE.MeshStandardMaterial({
    color: BLACK,
    roughness: 0.52,
    metalness: 0.32,
  });
  const seamMaterial = new THREE.MeshBasicMaterial({ color: 0x343a3b });
  const orangeMaterial = new THREE.MeshBasicMaterial({ color: AMBER });

  const hull = new THREE.Mesh(new THREE.SphereGeometry(1, 72, 36), hullMaterial);
  hull.scale.set(
    CARRIER_SPEC.envelopeLengthM / 2,
    EQUIVALENT_ENVELOPE_DIAMETER_M / 2,
    EQUIVALENT_ENVELOPE_DIAMETER_M / 2,
  );
  carrier.add(hull);

  // Circumferential construction seams make the volume readable without a
  // fake sci-fi wireframe. Their radii follow the same prolate spheroid.
  [-1.55, -0.78, 0, 0.78, 1.55].forEach((x) => {
    const a = CARRIER_SPEC.envelopeLengthM / 2;
    const b = EQUIVALENT_ENVELOPE_DIAMETER_M / 2;
    const radius = b * Math.sqrt(1 - (x * x) / (a * a));
    const seam = new THREE.Mesh(
      new THREE.TorusGeometry(radius, 0.004, 5, 64),
      seamMaterial,
    );
    seam.rotation.y = Math.PI / 2;
    seam.position.x = x;
    carrier.add(seam);
  });

  // Tail surfaces. These are intentionally simple visual geometry; the vendor
  // envelope length/volume and P0 dock/UAV dimensions remain the scale anchors.
  const finHorizontal = new THREE.Mesh(
    new THREE.BoxGeometry(0.62, 0.025, 1.1),
    darkMaterial,
  );
  finHorizontal.position.x = -1.83;
  finHorizontal.rotation.z = -0.09;
  const finVertical = new THREE.Mesh(
    new THREE.BoxGeometry(0.62, 0.9, 0.025),
    darkMaterial,
  );
  finVertical.position.set(-1.82, 0.16, 0);
  finVertical.rotation.z = -0.13;
  carrier.add(finHorizontal, finVertical);

  const rail = new THREE.Mesh(
    new THREE.BoxGeometry(1.62, 0.035, 0.09),
    structuralMaterial,
  );
  rail.position.y = -0.79;
  const gondola = new THREE.Mesh(
    new THREE.BoxGeometry(0.82, 0.17, 0.32),
    darkMaterial,
  );
  gondola.position.set(0.1, -0.87, 0);
  carrier.add(rail, gondola);

  // Vendor baseline is a dual vector-motor platform. Keep both propulsion pods
  // symmetric and visually subordinate to the lifting envelope.
  [-0.42, 0.42].forEach((z) => {
    const motor = new THREE.Mesh(
      new THREE.CylinderGeometry(0.085, 0.085, 0.19, 24, 1, true),
      structuralMaterial,
    );
    motor.rotation.z = Math.PI / 2;
    motor.position.set(-0.08, -0.81, z);
    const rotor = new THREE.Mesh(
      new THREE.TorusGeometry(0.074, 0.006, 8, 32),
      darkMaterial,
    );
    rotor.rotation.y = Math.PI / 2;
    rotor.position.copy(motor.position);
    rotor.position.x += 0.1;
    carrier.add(motor, rotor);
  });

  // Rev-A funnel: Ø180 mm mouth, Ø16 mm throat, 65 mm deep.
  const funnel = new THREE.Mesh(
    new THREE.CylinderGeometry(
      CARRIER_SPEC.dockThroatDiameterM / 2,
      CARRIER_SPEC.dockMouthDiameterM / 2,
      CARRIER_SPEC.dockDepthM,
      48,
      1,
      true,
    ),
    new THREE.MeshStandardMaterial({
      color: 0x3a3f40,
      roughness: 0.36,
      metalness: 0.38,
      side: THREE.DoubleSide,
    }),
  );
  funnel.position.set(0.22, -1.005, 0);
  carrier.add(funnel);

  const throat = new THREE.Mesh(
    new THREE.CylinderGeometry(0.008, 0.008, 0.055, 18),
    structuralMaterial,
  );
  throat.position.set(0.22, -0.947, 0);
  carrier.add(throat);

  const status = new THREE.Mesh(new THREE.SphereGeometry(0.013, 12, 12), orangeMaterial);
  status.position.set(0.47, -0.88, 0.168);
  carrier.add(status);

  scene.add(carrier);
  return carrier;
}

function MetricCarrierFallback() {
  const envelopeLengthMm = CARRIER_SPEC.envelopeLengthM * 1000;
  const envelopeDiameterMm = EQUIVALENT_ENVELOPE_DIAMETER_M * 1000;
  const dockMouthMm = CARRIER_SPEC.dockMouthDiameterM * 1000;
  const dockThroatMm = CARRIER_SPEC.dockThroatDiameterM * 1000;
  const dockDepthMm = CARRIER_SPEC.dockDepthM * 1000;
  const motorHalfAxisMm =
    (CARRIER_SPEC.droneMotorDiagonalM * 1000) / (2 * Math.sqrt(2));
  const rotorRadiusMm = (CARRIER_SPEC.dronePropDiameterM * 1000) / 2;
  const hullBottom = envelopeDiameterMm / 2;
  const railY = hullBottom + 30;
  const funnelTopY = railY + 155;
  const funnelBottomY = funnelTopY + dockDepthMm;
  const droneY = funnelTopY + CARRIER_SPEC.droneProbeStandoffM * 1000;

  return (
    <svg
      className="metric-fallback"
      viewBox="-2500 -1100 5000 2350"
      role="presentation"
      focusable="false"
    >
      <g className="metric-measure">
        <path d="M-2250 -920V-850M2250 -920V-850M-2250 -885H2250" />
        <text x="0" y="-910" textAnchor="middle">
          {envelopeLengthMm.toFixed(0)} MM / VOLUME-MATCHED P0 ENVELOPE
        </text>
      </g>

      <ellipse
        className="metric-hull"
        cx="0"
        cy="0"
        rx={envelopeLengthMm / 2}
        ry={envelopeDiameterMm / 2}
      />
      {[-1550, -780, 0, 780, 1550].map((x) => {
        const radius =
          (envelopeDiameterMm / 2) *
          Math.sqrt(1 - (x * x) / ((envelopeLengthMm / 2) ** 2));
        return (
          <ellipse
            className="metric-seam"
            key={x}
            cx={x}
            cy="0"
            rx={Math.max(8, radius * 0.075)}
            ry={radius}
          />
        );
      })}

      <path className="metric-fin" d="M-1840 -250-2290 -690-2080 -110-1840 0Z" />
      <path className="metric-fin" d="M-1840 40-2290 510-2060 170-1830 0Z" />
      <rect className="metric-rail" x="-810" y={railY} width="1620" height="34" />
      <rect className="metric-gondola" x="-310" y={railY + 34} width="820" height="150" />

      <g className="metric-dock" transform="translate(220 0)">
        <path
          d={`M${-dockThroatMm / 2} ${funnelTopY} L${-dockMouthMm / 2} ${funnelBottomY} M${dockThroatMm / 2} ${funnelTopY} L${dockMouthMm / 2} ${funnelBottomY}`}
        />
        <path d={`M${-dockMouthMm / 2} ${funnelBottomY} H${dockMouthMm / 2}`} />
      </g>

      <g className="metric-drone" transform={`translate(220 ${droneY})`}>
        <path
          d={`M${-motorHalfAxisMm} ${-motorHalfAxisMm} L${motorHalfAxisMm} ${motorHalfAxisMm} M${-motorHalfAxisMm} ${motorHalfAxisMm} L${motorHalfAxisMm} ${-motorHalfAxisMm}`}
        />
        {[
          [-motorHalfAxisMm, -motorHalfAxisMm],
          [-motorHalfAxisMm, motorHalfAxisMm],
          [motorHalfAxisMm, -motorHalfAxisMm],
          [motorHalfAxisMm, motorHalfAxisMm],
        ].map(([x, y]) => (
          <circle key={`${x}:${y}`} cx={x} cy={y} r={rotorRadiusMm} />
        ))}
        <path d={`M0 0V${-CARRIER_SPEC.droneProbeStandoffM * 1000}`} />
        <circle cx="0" cy={-CARRIER_SPEC.droneProbeStandoffM * 1000} r="6" />
      </g>

      <g className="metric-callout" transform="translate(620 985)">
        <path d="M-360 0H0" />
        <text x="18" y="4">
          Ø{dockMouthMm.toFixed(0)} MM DOCK / {Math.round(CARRIER_SPEC.droneMotorDiagonalM * 1000)} MM UAV
        </text>
      </g>
    </svg>
  );
}

export function CarrierScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rendererState, setRendererState] = useState<RendererState>("booting");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("webgl2", {
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    if (!context) {
      setRendererState("unavailable");
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        context,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch {
      setRendererState("unavailable");
      return;
    }

    setRendererState("ready");
    renderer.setClearColor(BLACK, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(BLACK, 0.075);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.01, 80);
    camera.position.set(4.8, 1.55, 5.5);

    scene.add(new THREE.HemisphereLight(0xb5c6c9, 0x050505, 1.25));
    const key = new THREE.DirectionalLight(WHITE, 5.5);
    key.position.set(3.5, 4.5, 5);
    scene.add(key);
    const amber = new THREE.PointLight(AMBER, 20, 8, 2);
    amber.position.set(1.7, -0.7, 2.2);
    scene.add(amber);
    const cool = new THREE.PointLight(COOL, 9, 9, 2);
    cool.position.set(-3, 1.2, -2.2);
    scene.add(cool);

    const carrier = addCarrier(scene);
    carrier.rotation.set(0.035, -0.18, -0.018);

    const droneMaterials = {
      carbon: new THREE.MeshStandardMaterial({
        color: 0x111415,
        roughness: 0.44,
        metalness: 0.5,
      }),
      metal: new THREE.MeshStandardMaterial({
        color: 0x899092,
        roughness: 0.3,
        metalness: 0.82,
      }),
      rotor: new THREE.MeshBasicMaterial({
        color: 0x9ca3a4,
        transparent: true,
        opacity: 0.34,
      }),
      light: new THREE.MeshBasicMaterial({ color: AMBER }),
    };

    const droneA = makeMicroDrone(droneMaterials);
    const droneB = makeMicroDrone(droneMaterials);
    const drones = [droneA, droneB];
    drones.forEach((drone) => scene.add(drone));

    const dockedA = new THREE.Vector3(0.22, -1.145, 0);
    const dockedB = new THREE.Vector3(-0.12, -1.27, -0.2);
    const sortieA = new THREE.Vector3(1.55, -0.1, 1.15);
    const sortieB = new THREE.Vector3(0.65, 0.75, 1.75);
    droneA.position.copy(dockedA);
    droneB.position.copy(dockedB);

    const trailMaterial = new THREE.LineBasicMaterial({
      color: AMBER,
      transparent: true,
      opacity: 0.4,
    });
    const trailGeometries = [new THREE.BufferGeometry(), new THREE.BufferGeometry()];
    const trails = trailGeometries.map((geometry) => new THREE.Line(geometry, trailMaterial));
    trails.forEach((trail) => scene.add(trail));

    const grid = new THREE.GridHelper(28, 56, 0x323738, 0x171a1b);
    grid.position.y = -1.55;
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
    gridMaterials.forEach((material) => {
      material.transparent = true;
      material.opacity = 0.38;
    });
    scene.add(grid);

    // Sparse instanced fiducials give depth for camera movement with one draw call.
    const markerCount = window.innerWidth < 720 ? 80 : 180;
    const markerGeometry = new THREE.BoxGeometry(0.012, 0.012, 0.012);
    const markerMaterial = new THREE.MeshBasicMaterial({
      color: 0x52595b,
      transparent: true,
      opacity: 0.36,
    });
    const markers = new THREE.InstancedMesh(markerGeometry, markerMaterial, markerCount);
    const random = seededRandom(0xa1f0c0de);
    const dummy = new THREE.Object3D();
    for (let i = 0; i < markerCount; i += 1) {
      dummy.position.set(
        (random() - 0.5) * 18,
        (random() - 0.5) * 8,
        -1 - random() * 12,
      );
      dummy.updateMatrix();
      markers.setMatrixAt(i, dummy.matrix);
    }
    markers.instanceMatrix.needsUpdate = true;
    scene.add(markers);

    const target = new THREE.Vector3();
    const desiredCamera = new THREE.Vector3();
    const mouse = new THREE.Vector2();
    let scrollTarget = 0;
    let scroll = 0;
    let frame = 0;
    let hidden = document.hidden;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const updateViewport = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const dprCap = width < 720 ? 1.25 : 1.75;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, dprCap));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const updateScroll = () => {
      const range = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      scrollTarget = clamp01(window.scrollY / range);
    };

    const updatePointer = (event: PointerEvent) => {
      mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (event.clientY / window.innerHeight) * 2 - 1;
    };

    const updateVisibility = () => {
      hidden = document.hidden;
    };

    const updateTrail = (line: THREE.Line, from: THREE.Vector3, to: THREE.Vector3) => {
      const midpoint = from.clone().lerp(to, 0.5);
      midpoint.y += 0.28;
      const points = new THREE.QuadraticBezierCurve3(from, midpoint, to).getPoints(28);
      line.geometry.setFromPoints(points);
    };

    const animate = () => {
      frame = window.requestAnimationFrame(animate);
      if (hidden) return;

      scroll += (scrollTarget - scroll) * (reducedMotion ? 1 : 0.055);
      const deploy = smoothstep(0.11, 0.47, scroll);
      const recovery = smoothstep(0.48, 0.69, scroll);
      const dockFocus = smoothstep(0.48, 0.74, scroll);
      const finalWide = smoothstep(0.76, 0.96, scroll);

      const sortieMix = deploy * (1 - recovery);
      droneA.position.lerpVectors(dockedA, sortieA, sortieMix);
      droneB.position.lerpVectors(dockedB, sortieB, sortieMix);
      droneA.rotation.y = 0.25 + sortieMix * 0.65;
      droneB.rotation.y = -0.3 - sortieMix * 0.45;

      updateTrail(trails[0], dockedA, droneA.position);
      updateTrail(trails[1], dockedB, droneB.position);
      trailMaterial.opacity = 0.06 + sortieMix * 0.48;

      // Camera language follows the story: hero three-quarter carrier, sortie
      // standoff, then a real-scale dock close-up before returning wide.
      if (scroll < 0.5) {
        desiredCamera.set(
          4.9 - scroll * 2.4,
          1.35 - scroll * 1.0,
          5.6 - scroll * 1.2,
        );
        target.set(0, -0.08, 0);
      } else {
        desiredCamera.lerpVectors(
          new THREE.Vector3(1.3, -0.48, 1.48),
          new THREE.Vector3(5.7, 1.2, 6.6),
          finalWide,
        );
        target.lerpVectors(
          new THREE.Vector3(0.2, -0.98, 0),
          new THREE.Vector3(0, -0.1, 0),
          finalWide,
        );
        if (dockFocus < 1) desiredCamera.y += (1 - dockFocus) * 0.5;
      }

      desiredCamera.x += mouse.x * 0.14 * (1 - finalWide * 0.5);
      desiredCamera.y -= mouse.y * 0.08;
      camera.position.lerp(desiredCamera, reducedMotion ? 1 : 0.045);
      camera.lookAt(target);

      if (!reducedMotion) {
        const time = performance.now() * 0.00022;
        carrier.rotation.z = -0.018 + Math.sin(time * 1.7) * 0.008;
        carrier.rotation.y = -0.18 + mouse.x * 0.028 + Math.sin(time) * 0.012;
        markers.rotation.y += 0.00008;
      }

      grid.material instanceof THREE.Material && (grid.material.opacity = 0.38 - finalWide * 0.16);
      renderer.render(scene, camera);
    };

    updateViewport();
    updateScroll();
    window.addEventListener("resize", updateViewport, { passive: true });
    window.addEventListener("scroll", updateScroll, { passive: true });
    window.addEventListener("pointermove", updatePointer, { passive: true });
    document.addEventListener("visibilitychange", updateVisibility);
    frame = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateViewport);
      window.removeEventListener("scroll", updateScroll);
      window.removeEventListener("pointermove", updatePointer);
      document.removeEventListener("visibilitychange", updateVisibility);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => material.dispose());
        }
      });
      markerGeometry.dispose();
      markerMaterial.dispose();
      trailMaterial.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className="scene" aria-hidden="true" data-renderer={rendererState}>
      <canvas ref={canvasRef} />
      <div className="scene-hud">
        <span>{rendererState === "ready" ? "WEBGL 2 / LIVE" : "RENDER / INIT"}</span>
        <span>METRIC WORLD</span>
      </div>
      {rendererState === "unavailable" ? (
        <>
          <MetricCarrierFallback />
          <div className="scene-fallback">GPU PATH OFFLINE / METRIC SILHOUETTE</div>
        </>
      ) : null}
    </div>
  );
}
