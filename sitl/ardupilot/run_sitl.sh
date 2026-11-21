#!/usr/bin/env bash
# Start json_plant.py and ArduRover SITL headless, run one fly_test.py
# scenario against them, and tear both down.
#
#   sitl/ardupilot/run_sitl.sh turn      # calm air, 90 degree heading step
#   sitl/ardupilot/run_sitl.sh station   # 4 m/s wind, hold a point 1.5 km upwind, 30 min:
#                                        #   one GUIDED position target, then Rover's boat loiter
#   sitl/ardupilot/run_sitl.sh companion # same scenario; fly_test.py plays the companion:
#                                        #   aiur.strato.guidance.StationKeeper -> heading + speed at 1 Hz
#   sitl/ardupilot/run_sitl.sh hold      # arm and sit in boat loiter
#   sitl/ardupilot/run_sitl.sh idle      # just start both and wait (connect your own GCS to tcp:5760)
#
# Environment (all optional):
#   ARDUROVER   path to the ArduRover SITL binary.  If unset, the stable
#               prebuilt binary is downloaded once into $SITL_HOME/bin.
#   SITL_HOME   scratch directory for the binary, eeprom, logs and results
#               (default /tmp/aiur-ardupilot-sitl).  Nothing is written
#               inside the repository.
#   SPEEDUP     SITL speedup (default 20; lock-step, so this is an upper bound)
#   PARM        defaults file (default aiur_s2.parm next to this script)
#   EXTRA_PARM  a second defaults file layered on top (for tuning experiments)
#   WIND_N WIND_E  plant wind, NED m/s (station default 0 / -4: blowing west)
#   GUST        plant gust sigma m/s (default 0)
#   LUA         1 = install scripts/aiur_pitch.lua (default 1), 0 = no script
#   PYTHON      interpreter with pymavlink (default /usr/bin/python3.12)
#   TAG         suffix for the result directory
#   INSTANCE    SITL instance number (default 0); shifts every port by 10*N so
#               several runs can go in parallel
# Anything after the scenario name is passed to fly_test.py.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCEN="${1:-turn}"; shift || true
SITL_HOME="${SITL_HOME:-/tmp/aiur-ardupilot-sitl}"
SPEEDUP="${SPEEDUP:-20}"
PARM="${PARM:-$HERE/aiur_s2.parm}"
PYTHON="${PYTHON:-/usr/bin/python3.12}"
GUST="${GUST:-0}"
LUA="${LUA:-1}"
INSTANCE="${INSTANCE:-0}"
JSON_PORT=$((9002 + 10 * INSTANCE))
MAV_PORT=$((5760 + 10 * INSTANCE))
URL="https://firmware.ardupilot.org/Rover/stable/SITL_x86_64_linux_gnu/ardurover"
RUN="$SITL_HOME/run-$SCEN${TAG:+-$TAG}"
TEST="$SCEN"; [ "$SCEN" = "companion" ] && TEST=station

if [ -z "${ARDUROVER:-}" ]; then
  ARDUROVER="$SITL_HOME/bin/ardurover"
  if [ ! -x "$ARDUROVER" ]; then
    mkdir -p "$SITL_HOME/bin"
    echo "downloading $URL"
    curl -fsSL -o "$ARDUROVER" "$URL"
    curl -fsSL -o "$SITL_HOME/bin/git-version.txt" "${URL%/*}/git-version.txt" || true
    chmod +x "$ARDUROVER"
  fi
fi

rm -rf "$RUN"; mkdir -p "$RUN/scripts"
[ "$LUA" = "1" ] && cp "$HERE"/scripts/*.lua "$RUN/scripts/" 2>/dev/null || true

case "$SCEN" in
  station|companion) WIND_N="${WIND_N:-0}"; WIND_E="${WIND_E:--4}"; WIND_START=60; WIND_RAMP=30 ;;
  *)       WIND_N="${WIND_N:-0}"; WIND_E="${WIND_E:-0}";  WIND_START=0;  WIND_RAMP=0 ;;
esac
# start pointing into the wind (as the in-repo station_keep scenario does), else north
YAW="$("$PYTHON" -c "import math,sys; n,e=float(sys.argv[1]),float(sys.argv[2]); print(round(math.degrees(math.atan2(-e,-n)),1) if (n or e) else 0.0)" "$WIND_N" "$WIND_E")"

PIDS=()
# ArduPilot SITL ignores SIGTERM while blocked on the JSON socket, hence -9.
cleanup() { for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT

"$PYTHON" "$HERE/json_plant.py" --wind "$WIND_N" "$WIND_E" 0 --wind-start-s "$WIND_START" \
    --wind-ramp-s "$WIND_RAMP" --gust "$GUST" --yaw-deg "$YAW" --log "$RUN/truth.csv" \
    --port "$JSON_PORT" \
    > "$RUN/plant.log" 2>&1 &
PIDS+=($!)

DEFAULTS="$PARM${EXTRA_PARM:+,$EXTRA_PARM}"
# -w wipes the eeprom so only the defaults file(s) define the vehicle.
# Home altitude 20000 m: the design float altitude (baro, GPS and the EKF origin sit there).
( cd "$RUN" && exec "$ARDUROVER" -w -S --model JSON:127.0.0.1 --speedup "$SPEEDUP" \
    --defaults "$DEFAULTS" --home 50.0,30.0,20000,"$YAW" -I"$INSTANCE" > "$RUN/ardurover.log" 2>&1 ) &
PIDS+=($!)

echo "plant + ArduRover SITL started; results in $RUN"
if [ "$SCEN" = "idle" ]; then
  echo "MAVLink on tcp:127.0.0.1:$MAV_PORT (SITL blocks until something connects). Ctrl-C to stop."
  wait
  exit 0
fi

ARGS=()
case "$SCEN" in
  station)   ARGS=(--wind "$WIND_N" "$WIND_E" 0 --start-after 100 --duration 1800) ;;
  companion) ARGS=(--wind "$WIND_N" "$WIND_E" 0 --start-after 100 --duration 1800 --guidance companion) ;;
  # Rover caps every GUIDED speed target at WP_SPEED; the turn test flies the 6 m/s cruise.
  turn)    ARGS=(--duration 300 --speed 6 --set WP_SPEED=6) ;;
  hold)    ARGS=(--duration 300) ;;
esac
"$PYTHON" "$HERE/fly_test.py" "$TEST" --connect "tcp:127.0.0.1:$MAV_PORT" --truth "$RUN/truth.csv" --out "$RUN/result.json" \
    --series "$RUN/ekf_series.csv" "${ARGS[@]}" "$@" | tee "$RUN/fly_test.log"
