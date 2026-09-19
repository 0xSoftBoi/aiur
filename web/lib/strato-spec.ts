/**
 * Figures shown on the site for the STRATO-P0 article.
 *
 * Every value mirrors the output of `python -m aiur.strato` in the 1976
 * standard atmosphere. They are model results and engineering allocations,
 * not measurements; regenerate this file's numbers whenever the model's
 * defaults change, and never round them in a direction that flatters.
 */
export const STRATO_SPEC = {
  /** Lowest altitude that is stratospheric at every latitude and season. */
  thresholdAltitudeM: 20_000,
  /** Reference sounding article: 1200 g latex, 850 g package, 0.9 kg free lift. */
  predictedBurstAltitudeM: 33_820,
  launchAscentRateMps: 4.5,
  timeToBurstMin: 89.5,
  ascentMinutesAboveThreshold: 27.9,
  /** Straight-line geometric horizon from the threshold altitude. */
  horizonDistanceKm: 505.2,
  visibleCapAreaKm2: 798_098,
  /** Reference optic: 1-inch-class sensor, 2.4 µm pitch, 25 mm lens. */
  nadirGsdM: 1.92,
  frameSwathKm: [10.56, 7.04],
  ambientTemperatureC: -56.5,
  /** Program allocation and the 4 lb regulatory ceiling it stays under. */
  payloadAllocationKg: 1.0,
  payloadCeilingKg: 1.814,
  baselinePackageKg: 0.85,
  landingRateLimitMps: 5.0,
  /** STRATO-P1 float reference: 3 kg gross at the threshold altitude. */
  floatEnvelopeVolumeM3: 39.15,
} as const;
