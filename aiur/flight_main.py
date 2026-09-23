"""The flight program: what the payload computer runs from arming to pickup.

``aiur.flight_supervisor`` decides; this module is the loop around it that
reads sensors, drives the three outputs the package has (cutdown, imager,
radio), and writes the flight log in the exact shape ``aiur.s0_evidence``
reduces.  It is written against small interfaces — ``Sensors``,
``Actuators``, ``Clock`` — so the same program runs on the bench with
recorded inputs, in the twin with simulated physics, and on the Pi with the
real devices, and so the S0-A cold soak exercises the code that flies.

Rules the loop keeps regardless of backend:

* one tick per second, wall-clock or simulated, never faster than the
  supervisor was tested at;
* every log row is flushed before the next tick, so a brownout loses at
  most one second of record;
* the cutdown line is driven from the supervisor's latched output every
  tick, never from an edge that a missed tick could lose;
* the hardware timer is *read*, not driven — the program has no way to
  start, stop, or reset it, and logs only whether it fired.

The Pi backend is deliberately not implemented here: it is the S0-A build
item, and stubbing it with a fake would let a fake fly.  ``--backend pi``
says exactly what has to exist.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .flight_supervisor import (
    FlightInputs,
    FlightLimits,
    FlightOutput,
    FlightState,
    FlightSupervisor,
)
from .strato import SoundingBalloon, parachute_descent_rate_m_s, standard_atmosphere
from .strato_sim import FLIGHT_LOG_FIELDS

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class SensorFrame:
    """One second of inputs as the devices report them."""

    arm_pin_pulled: bool
    gnss_valid: bool
    latitude_deg: float | None
    longitude_deg: float | None
    altitude_m: float | None
    battery_v: float
    internal_temp_c: float
    #: A termination command decoded from the uplink this tick.
    ground_terminate: bool = False
    #: The hardware timer's fired line, read back.
    timer_fired: bool = False


class Sensors(Protocol):
    def read(self, now_s: float) -> SensorFrame: ...


class Actuators(Protocol):
    def cutdown(self, asserted: bool) -> None: ...

    def capture(self, now_s: float, geotag: bool) -> bool:
        """Take a frame; return True when it was stored."""
        ...

    def transmit(self, packet: dict[str, object]) -> bool:
        """Send telemetry; return True when the radio accepted it."""
        ...


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep_until(self, t_s: float) -> None: ...


def east_north_km(
    lat_deg: float, lon_deg: float, ref_lat_deg: float, ref_lon_deg: float
) -> tuple[float, float]:
    """Equirectangular offset from the launch fix; fine inside a geofence."""

    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    ref_lat = math.radians(ref_lat_deg)
    ref_lon = math.radians(ref_lon_deg)
    east = (lon - ref_lon) * math.cos(0.5 * (lat + ref_lat)) * EARTH_RADIUS_KM
    north = (lat - ref_lat) * EARTH_RADIUS_KM
    return east, north


# ----------------------------------------------------------------------
# Backends
# ----------------------------------------------------------------------


class FakeClock:
    """Simulated time: sleeping advances the clock instead of waiting."""

    def __init__(self, start_s: float = 0.0) -> None:
        self._now = start_s

    def now(self) -> float:
        return self._now

    def sleep_until(self, t_s: float) -> None:
        if t_s > self._now:
            self._now = t_s


class WallClock:
    def __init__(self) -> None:
        import time

        self._time = time
        self._start = time.monotonic()

    def now(self) -> float:
        return self._time.monotonic() - self._start

    def sleep_until(self, t_s: float) -> None:
        delay = t_s - self.now()
        if delay > 0:
            self._time.sleep(delay)


@dataclass
class SimulatedSensors:
    """Minimal physics for exercising the program: climb, burst, descend.

    Uses the ascent model and the parachute model directly; a uniform wind
    drifts the fix east.  Fault knobs mirror ``aiur.strato_sim`` so the same
    behaviours can be checked at the program level.
    """

    balloon: SoundingBalloon = SoundingBalloon()
    canopy_area_m2: float = 0.73
    launch_lat_deg: float = 45.0
    launch_lon_deg: float = 10.0
    wind_east_m_s: float = 8.0
    ground_hold_s: float = 60.0
    gnss_dropout: tuple[float, float] | None = None
    terminate_at_s: float | None = None
    battery_initial_v: float = 6.2
    battery_sag_v_per_h: float = 0.25
    insulation_leak: float = 0.35
    _altitude: float = 0.0
    _east_km: float = 0.0
    _under_balloon: bool = True
    _last_s: float | None = None
    _cutdown: bool = False

    def apply_cutdown(self, asserted: bool) -> None:
        if asserted:
            self._cutdown = True

    def read(self, now_s: float) -> SensorFrame:
        dt = 0.0 if self._last_s is None else now_s - self._last_s
        self._last_s = now_s
        released = now_s >= self.ground_hold_s
        if released and dt > 0:
            if self._under_balloon and (
                self._cutdown or self._altitude >= self.balloon.burst_altitude_m()
            ):
                self._under_balloon = False
            if self._under_balloon:
                vz = self.balloon.ascent_rate_at_m_s(min(self._altitude, 46_900.0))
            elif self._altitude > 0.0:
                vz = -parachute_descent_rate_m_s(
                    self.balloon.payload_mass_kg,
                    self.canopy_area_m2,
                    altitude_m=min(self._altitude, 47_000.0),
                )
            else:
                vz = 0.0
            self._altitude = max(0.0, self._altitude + vz * dt)
            if self._altitude > 0.0:
                self._east_km += self.wind_east_m_s * dt / 1000.0
        gnss_valid = not (
            self.gnss_dropout is not None
            and self.gnss_dropout[0] <= now_s < self.gnss_dropout[0] + self.gnss_dropout[1]
        )
        ambient = standard_atmosphere(min(self._altitude, 47_000.0)).temperature_c
        lon = self.launch_lon_deg + math.degrees(
            self._east_km / (EARTH_RADIUS_KM * math.cos(math.radians(self.launch_lat_deg)))
        )
        return SensorFrame(
            arm_pin_pulled=True,
            gnss_valid=gnss_valid,
            latitude_deg=self.launch_lat_deg if gnss_valid else None,
            longitude_deg=lon if gnss_valid else None,
            altitude_m=self._altitude if gnss_valid else None,
            battery_v=self.battery_initial_v - self.battery_sag_v_per_h * now_s / 3600.0,
            internal_temp_c=20.0 + (ambient - 20.0) * self.insulation_leak,
            ground_terminate=self.terminate_at_s is not None and now_s >= self.terminate_at_s,
            timer_fired=False,
        )


class RecordedSensors:
    """Replay the sensor columns of a flight log: the bench's regression input."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("no rows to replay")
        self._rows = rows
        self._index = 0

    def read(self, now_s: float) -> SensorFrame:
        row = self._rows[min(self._index, len(self._rows) - 1)]
        self._index += 1
        gnss = row["gnss_valid"].strip() in {"1", "true", "True"}
        altitude = float(row["altitude_m"]) if gnss and row["altitude_m"].strip() else None
        x = float(row["x_km"]) if gnss and row.get("x_km", "").strip() else 0.0
        y = float(row["y_km"]) if gnss and row.get("y_km", "").strip() else 0.0
        lat = 45.0 + y / EARTH_RADIUS_KM * 180.0 / math.pi if gnss else None
        lon = (
            10.0 + x / (EARTH_RADIUS_KM * math.cos(math.radians(45.0))) * 180.0 / math.pi
            if gnss
            else None
        )
        return SensorFrame(
            arm_pin_pulled=True,
            gnss_valid=gnss,
            latitude_deg=lat,
            longitude_deg=lon,
            altitude_m=altitude,
            battery_v=float(row["battery_v"]),
            internal_temp_c=float(row["internal_temp_c"]),
            ground_terminate=row.get("reason", "").startswith("ground command"),
            timer_fired=row.get("timer_fired", "0").strip() == "1",
        )

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._rows)


class RecordingActuators:
    """Bench/twin actuators: remember every command so tests can check them."""

    def __init__(self, sensors: SimulatedSensors | None = None, *, radio_ok: bool = True) -> None:
        self.cutdown_history: list[bool] = []
        self.frames: list[tuple[float, bool]] = []
        self.packets: list[dict[str, object]] = []
        self._sensors = sensors
        self._radio_ok = radio_ok

    def cutdown(self, asserted: bool) -> None:
        self.cutdown_history.append(asserted)
        if self._sensors is not None:
            self._sensors.apply_cutdown(asserted)

    def capture(self, now_s: float, geotag: bool) -> bool:
        self.frames.append((now_s, geotag))
        return True

    def transmit(self, packet: dict[str, object]) -> bool:
        self.packets.append(packet)
        return self._radio_ok


PI_BACKEND_CONTRACT = (
    "The Pi backend is the S0-A build item and is not implemented here. It must provide: "
    "Sensors.read() returning SensorFrame from the arming-pin GPIO, the u-blox receiver in "
    "the airborne dynamic model (fix validity, lat, lon, altitude), the bus ADC, the internal "
    "thermistor, the LoRa uplink inbox, and the timer's fired line; Actuators.cutdown() "
    "driving the burn-wire MOSFET gate, capture() storing a frame with its tag, and "
    "transmit() handing a packet to the LoRa module; and WallClock. Then run "
    "`python -m aiur.flight_main --backend pi --log /var/flight/<run_id>-flight-log.csv`."
)


# ----------------------------------------------------------------------
# The program
# ----------------------------------------------------------------------


class FlightProgram:
    def __init__(
        self,
        sensors: Sensors,
        actuators: Actuators,
        clock: Clock,
        log_path: Path,
        *,
        limits: FlightLimits | None = None,
        tick_s: float = 1.0,
        post_landing_s: float = 180.0,
        max_runtime_s: float = 8.0 * 3600.0,
    ) -> None:
        if tick_s <= 0:
            raise ValueError("tick must be positive")
        self.sensors = sensors
        self.actuators = actuators
        self.clock = clock
        self.log_path = log_path
        self.limits = limits or FlightLimits()
        self.supervisor = FlightSupervisor(self.limits)
        self.tick_s = tick_s
        self.post_landing_s = post_landing_s
        self.max_runtime_s = max_runtime_s
        self.launch_fix: tuple[float, float] | None = None
        self.rows_written = 0
        self.last_output: FlightOutput | None = None
        self._last_capture_s: float | None = None
        self._last_tx_s: float | None = None
        self._landed_at_s: float | None = None

    def _inputs(self, frame: SensorFrame) -> tuple[FlightInputs, float | None, float | None]:
        east = north = None
        if frame.gnss_valid and frame.latitude_deg is not None and frame.longitude_deg is not None:
            if self.launch_fix is None and frame.arm_pin_pulled:
                self.launch_fix = (frame.latitude_deg, frame.longitude_deg)
            if self.launch_fix is not None:
                east, north = east_north_km(
                    frame.latitude_deg, frame.longitude_deg, *self.launch_fix
                )
        range_km = math.hypot(east, north) if east is not None and north is not None else None
        return (
            FlightInputs(
                arm_pin_pulled=frame.arm_pin_pulled,
                gnss_valid=frame.gnss_valid,
                altitude_m=frame.altitude_m if frame.gnss_valid else None,
                range_from_launch_km=range_km,
                battery_v=frame.battery_v,
                internal_temp_c=frame.internal_temp_c,
                ground_terminate=frame.ground_terminate,
            ),
            east,
            north,
        )

    def tick(self, now_s: float, writer: csv.DictWriter, handle) -> FlightOutput:
        frame = self.sensors.read(now_s)
        inputs, east, north = self._inputs(frame)
        output = self.supervisor.step(now_s, inputs)
        self.last_output = output

        # Drive the cutdown line from the latched output every tick.
        self.actuators.cutdown(output.cutdown)

        captured = False
        if output.capture_period_s is not None and (
            self._last_capture_s is None or now_s - self._last_capture_s >= output.capture_period_s
        ):
            captured = self.actuators.capture(now_s, output.geotag)
            if captured:
                self._last_capture_s = now_s

        sent = received = False
        if self._last_tx_s is None or now_s - self._last_tx_s >= output.telemetry_period_s:
            packet = {
                "t_s": round(now_s, 1),
                "state": output.state.value,
                "alt": None if inputs.altitude_m is None else round(inputs.altitude_m, 1),
                "x_km": None if east is None else round(east, 3),
                "y_km": None if north is None else round(north, 3),
                "bat": round(frame.battery_v, 2),
                "cut": int(output.cutdown),
            }
            sent = True
            received = self.actuators.transmit(packet)
            self._last_tx_s = now_s

        writer.writerow(
            {
                "t_s": round(now_s, 1),
                "gnss_valid": int(frame.gnss_valid),
                "altitude_m": "" if inputs.altitude_m is None else round(inputs.altitude_m, 1),
                "x_km": "" if east is None else round(east, 3),
                "y_km": "" if north is None else round(north, 3),
                "state": output.state.value,
                "cutdown": int(output.cutdown),
                "timer_fired": int(frame.timer_fired),
                "beacon_only": int(output.beacon_only),
                "frame_captured": int(captured),
                "geotagged": int(captured and output.geotag),
                "telemetry_sent": int(sent),
                "telemetry_received": int(received),
                "battery_v": round(frame.battery_v, 3),
                "internal_temp_c": round(frame.internal_temp_c, 2),
                "reason": output.reason or "",
            }
        )
        handle.flush()
        self.rows_written += 1
        return output

    def run(self) -> FlightState:
        """Loop until landed (plus the hold) or the runtime limit."""

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        start = self.clock.now()
        next_tick = start
        with self.log_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FLIGHT_LOG_FIELDS)
            writer.writeheader()
            handle.flush()
            while True:
                now = self.clock.now()
                output = self.tick(now - start, writer, handle)
                if output.state is FlightState.LANDED:
                    if self._landed_at_s is None:
                        self._landed_at_s = now - start
                    elif now - start - self._landed_at_s >= self.post_landing_s:
                        break
                if now - start >= self.max_runtime_s:
                    break
                if isinstance(self.sensors, RecordedSensors) and self.sensors.exhausted:
                    break
                next_tick += self.tick_s
                self.clock.sleep_until(next_tick)
        assert self.last_output is not None
        return self.last_output.state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the STRATO-P0 flight program.")
    parser.add_argument("--backend", choices=("sim", "replay", "pi"), default="sim")
    parser.add_argument("--log", type=Path, required=True, help="flight log to write")
    parser.add_argument("--replay", type=Path, default=None, help="flight log to replay (replay backend)")
    parser.add_argument("--terminate-at", type=float, default=None, help="sim: ground command at t (s)")
    parser.add_argument("--realtime", action="store_true", help="sim: use the wall clock")
    args = parser.parse_args(argv)

    if args.backend == "pi":
        print(json.dumps({"error": PI_BACKEND_CONTRACT}, indent=2))
        return 2
    if args.backend == "replay":
        if args.replay is None:
            parser.error("--replay is required with the replay backend")
        with args.replay.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        sensors: Sensors = RecordedSensors(rows)
        actuators = RecordingActuators()
    else:
        sim = SimulatedSensors(terminate_at_s=args.terminate_at)
        sensors = sim
        actuators = RecordingActuators(sim)
    clock: Clock = WallClock() if args.realtime else FakeClock()
    program = FlightProgram(sensors, actuators, clock, args.log)
    final = program.run()
    print(
        json.dumps(
            {
                "final_state": final.value,
                "rows": program.rows_written,
                "frames": len(actuators.frames),
                "packets": len(actuators.packets),
                "cutdown_asserted": any(actuators.cutdown_history),
                "termination_reason": program.supervisor.termination_reason,
                "log": str(args.log),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
