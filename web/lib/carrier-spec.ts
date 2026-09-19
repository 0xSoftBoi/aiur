/**
 * Metric values used by the live Three.js model.
 *
 * Length, helium volume and rated payload mirror the vendor article selected
 * in aiur/envelope.py (RC-Zeppelin 3.5 m indoor; docs/carrier-sizing.md).
 * The vendor publishes length and helium volume but not envelope diameter.
 * The renderer therefore uses a volume-matched prolate spheroid; its derived
 * diameter is a visualization parameter, not a frozen airframe dimension.
 */
export const CARRIER_SPEC = {
  envelopeLengthM: 3.5,
  heliumVolumeM3: 4.0,
  ratedPayloadKg: 0.5,
  dockMouthDiameterM: 0.18,
  dockThroatDiameterM: 0.016,
  dockDepthM: 0.065,
  droneMotorDiagonalM: 0.1,
  dronePropDiameterM: 0.055,
  droneProbeStandoffM: 0.11,
  p0AircraftCount: 2,
  terminalClosingSpeedMps: 0.2,
} as const;

const envelopeSemiMajorM = CARRIER_SPEC.envelopeLengthM / 2;

export const EQUIVALENT_ENVELOPE_DIAMETER_M =
  2 *
  Math.sqrt(
    CARRIER_SPEC.heliumVolumeM3 /
      ((4 / 3) * Math.PI * envelopeSemiMajorM),
  );
