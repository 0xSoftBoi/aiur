"""Scenario builders for the CARRIER-P0 digital twin.

Each builder is a deterministic function of a seed: it jitters initial
conditions, optionally samples a fault plan, and returns a complete
``EpisodeConfig``.  Campaign presets map to these builders:

* ``sil-p0b`` — moving suspended dock (bench rig), one aircraft recovery.
  Mirrors the P0-B article.
* ``sil-p0c`` — tethered carrier, full launch/sortie/recovery cycle.
  Mirrors the P0-C article.
* ``sil-p0d`` — tethered carrier, two aircraft, sequential dock use.
  Mirrors the P0-D article under the interpretation documented in
  :func:`sil_p0d`.
* ``outdoor-gust-sweep`` / ``degraded-sensor-sweep`` — engineering studies
  for the vertical concept work (docs/verticals/), not gates.
"""

from __future__ import annotations

from dataclasses import replace
import random

from .disturbances import AirModelParams, INDOOR_CALM, outdoor_breeze
from .engine import (
    DroneSetup,
    EpisodeConfig,
    Platform,
    ScriptAction,
    ScriptStep,
)
from .faults import sample_fault_plan
from .guidance import GuidanceParams, MissionMode
from .sensors import LIGHTHOUSE_GRADE, PoseSensorParams, scaled_sensor
from .vec import Vec3

#: Seed decorrelation constant so scenario jitter and engine process noise
#: never share a stream even though both derive from the episode seed.
_SCENARIO_SALT = 0x9E3779B9


def _scenario_rng(seed: int) -> random.Random:
    return random.Random(seed ^ _SCENARIO_SALT)


def _jitter(rng: random.Random, base: Vec3, radius_m: float) -> Vec3:
    return base + Vec3(
        rng.uniform(-radius_m, radius_m),
        rng.uniform(-radius_m, radius_m),
        rng.uniform(-radius_m, radius_m) * 0.5,
    )


def sil_p0b(
    seed: int,
    *,
    with_fault: bool = False,
    air: AirModelParams = INDOOR_CALM,
    drone_sensor: PoseSensorParams = LIGHTHOUSE_GRADE,
    guidance: GuidanceParams = GuidanceParams(),
    record_telemetry: bool = False,
) -> EpisodeConfig:
    """Moving suspended dock: autonomous terminal approach and capture."""

    rng = _scenario_rng(seed)
    dock_center = Vec3(0.0, 0.0, 2.0)
    start = _jitter(rng, Vec3(0.45, -0.35, 0.90), 0.15)
    return EpisodeConfig(
        platform=Platform.RIG,
        platform_position=dock_center,
        drones=(
            DroneSetup(
                start_position=start,
                mission=MissionMode.RECOVER_ONLY,
                station=start,
            ),
        ),
        script=(ScriptStep(0, ScriptAction.RECOVER),),
        air=air,
        drone_sensor=drone_sensor,
        guidance=guidance,
        max_duration_s=150.0,
        fault_plan=sample_fault_plan(rng) if with_fault else (),
        record_telemetry=record_telemetry,
    )


def sil_p0c(
    seed: int,
    *,
    with_fault: bool = False,
    air: AirModelParams = INDOOR_CALM,
    record_telemetry: bool = False,
) -> EpisodeConfig:
    """Tethered carrier: complete autonomous launch/sortie/recovery cycle."""

    rng = _scenario_rng(seed)
    carrier_position = Vec3(0.0, 0.0, 3.0)
    waypoint = _jitter(rng, Vec3(1.2, 0.8, 1.2), 0.2)
    return EpisodeConfig(
        platform=Platform.CARRIER,
        platform_position=carrier_position,
        drones=(
            DroneSetup(
                start_position=carrier_position,  # replaced by pre-roll capture
                mission=MissionMode.LAUNCH_SORTIE_RECOVER,
                station=waypoint,
                sortie_waypoints=(waypoint,),
                start_captured=True,
            ),
        ),
        script=(
            ScriptStep(0, ScriptAction.LAUNCH_SORTIE),
            ScriptStep(0, ScriptAction.RECOVER),
        ),
        air=air,
        max_duration_s=240.0,
        tethered=True,
        fault_plan=sample_fault_plan(rng) if with_fault else (),
        record_telemetry=record_telemetry,
    )


def sil_p0d(
    seed: int,
    *,
    with_fault: bool = False,
    air: AirModelParams = INDOOR_CALM,
    record_telemetry: bool = False,
) -> EpisodeConfig:
    """Two-aircraft sequential dock use with positive separation.

    P0-D interpretation for one active dock: aircraft 0 launches from the
    dock and sorties to a hold station; aircraft 1, already airborne on the
    opposite station, then performs the recovery; aircraft 0 finally lands
    on its ground pad because the single dock is occupied.  This exercises
    every P0-D criterion — sequential release, one-at-a-time dock use,
    positive separation, zero simultaneous approaches — and should be
    revisited when a second dock exists.
    """

    rng = _scenario_rng(seed)
    carrier_position = Vec3(0.0, 0.0, 3.0)
    station_a = _jitter(rng, Vec3(1.3, 0.7, 1.5), 0.1)
    station_b = _jitter(rng, Vec3(-1.3, -0.7, 1.3), 0.1)
    return EpisodeConfig(
        platform=Platform.CARRIER,
        platform_position=carrier_position,
        drones=(
            DroneSetup(
                start_position=carrier_position,  # replaced by pre-roll capture
                mission=MissionMode.LAUNCH_SORTIE_RECOVER,
                station=station_a,
                sortie_waypoints=(station_a,),
                start_captured=True,
            ),
            DroneSetup(
                start_position=station_b,
                mission=MissionMode.RECOVER_ONLY,
                station=station_b,
            ),
        ),
        script=(
            ScriptStep(0, ScriptAction.LAUNCH_SORTIE),
            ScriptStep(1, ScriptAction.RECOVER),
            ScriptStep(0, ScriptAction.GROUND_LAND),
        ),
        air=air,
        max_duration_s=300.0,
        tethered=True,
        fault_plan=sample_fault_plan(rng) if with_fault else (),
        fault_target_drone=1,
        record_telemetry=record_telemetry,
    )


def outdoor_gust_case(seed: int, mean_wind_m_s: float) -> EpisodeConfig:
    """One episode of the outdoor-gust-sweep study.

    A tethered-carrier recovery under outdoor wind.  The study exists to
    locate the wind level where capture collapses for the P0-scale article;
    the expectation, to be confirmed by the sweep, is that a 4.5 m envelope
    is not an outdoor vehicle.
    """

    return sil_p0c(seed, air=outdoor_breeze(mean_wind_m_s))


def degraded_sensor_case(seed: int, noise_scale: float) -> EpisodeConfig:
    """One episode of the degraded-sensor-sweep study.

    Scales Lighthouse-grade noise up toward consumer/GNSS-grade terminal
    navigation to quantify how capture rate and funnel demands grow —
    the executable input to the toy and outdoor vertical studies.

    FDIR thresholds and the approach geometry are retuned with the sensor,
    as a real integration would tune them to the sensor spec.  The funnel
    geometry is deliberately NOT scaled: the study's question is what the
    fixed 180 mm funnel can tolerate.  Expect misses and rim contacts to
    appear as noise approaches funnel scale — that emergence is the
    finding, quantifying the funnel-size pressure on non-Lighthouse
    verticals.
    """

    sensor = scaled_sensor(LIGHTHOUSE_GRADE, noise_scale)
    sigma = sensor.position_sigma_m
    guidance = replace(
        GuidanceParams(),
        pose_jump_threshold_m=max(0.030, 8.0 * sigma),
        align_radius_m=max(0.030, 2.0 * sigma),
        corridor_base_m=max(0.060, 3.0 * sigma),
        seat_plausibility_m=max(0.060, 3.0 * sigma),
        seat_confirm_m=max(0.015, 1.5 * sigma),
    )
    return sil_p0b(seed, drone_sensor=sensor, guidance=guidance)
