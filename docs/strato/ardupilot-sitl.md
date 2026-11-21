# ArduPilot in the loop: ArduRover SITL flying the airship physics

Status: **run**. The real ArduRover 4.7.3 firmware (SITL build) arms and flies
`aiur.strato.flight6dof` through ArduPilot's JSON physics interface. It turns
the S2 hull about as well as the in-repo controller and, with the companion's
station-keeping law on top, holds station the same as the in-repo loop in
steady wind and somewhat worse in gusts. Rover's own navigation (waypoint +
boat loiter) is not usable in gusts, and Rover has no pitch or altitude loop.
Everything below is marked as *run* (with numbers) or *reasoned* (not run).

## 1. What was obtained

| Item | How | Result |
|---|---|---|
| ArduRover SITL binary | `curl https://firmware.ardupilot.org/Rover/stable/SITL_x86_64_linux_gnu/ardurover` | HTTP 200, 6,865,160 bytes, sha256 `612ad9af57ba0f1fe4240a9ba293a12a80b0b2963a1f792eb520126b6e2a5e4a`, static x86-64 ELF, reports `ArduRover V4.7.3 (d9c5097c)` |
| its `git-version.txt` | same directory | commit `d9c5097c3d8333435712ffed86bca8ce00c4bb46` (2026-11-14) |
| ArduPilot source (reference only, not built) | `git clone --depth 1 --branch Rover-4.7.3 https://github.com/ArduPilot/ardupilot` (no submodules) | reachable; HEAD `d9c5097c…`, identical to the binary's commit |
| other prebuilt SITL binaries | `.../Plane/stable/SITL_x86_64_linux_gnu/arduplane` | HTTP 200 (not downloaded, not run) |
| | `.../Blimp/stable/SITL_x86_64_linux_gnu/blimp` | HTTP 404 |

Nothing was built from source: the prebuilt binary was sufficient. The source
tree was used to read the JSON interface (`libraries/SITL/SIM_JSON.cpp`,
`examples/JSON/readme.md`) and the Rover control code quoted below. No
ArduPilot code or binary is in this repository; `run_sitl.sh` downloads the
binary into a scratch directory on first use. The "stable" URL moves with
ArduPilot releases; the hash above is what these results were produced with.

Python 3.12, pymavlink 2.4.50.

## 2. Architecture

```
 sitl/ardupilot/json_plant.py                 ardurover (SITL, V4.7.3)                 sitl/ardupilot/fly_test.py
 ┌──────────────────────────────┐  UDP 9002   ┌──────────────────────────┐  TCP 5760   ┌─────────────────────────────┐
 │ aiur.strato.flight6dof       │◄────────────│ servo PWM[16], binary,   │  MAVLink 2  │ wait EKF+GPS, GUIDED, arm   │
 │  Airframe.from_design(S2)    │  40 bytes   │ one packet per frame     │────────────►│ turn test / station test    │
 │  step(af, st, ctl, wind, dt) │             │                          │  telemetry  │ (optionally the companion:  │
 │  dt = 5 ms per frame         │────────────►│ EKF3, Rover GUIDED,      │◄────────────│  guidance.StationKeeper ->  │
 │  wind ramp, optional gust    │  JSON line  │ AR_AttitudeControl,      │  setpoints  │  heading + ground speed)    │
 │  truth.csv (5 Hz)            │  state      │ AP_MotorsUGV, Lua        │             │ result.json, ekf_series.csv │
 └──────────────────────────────┘             └──────────────────────────┘             └─────────────────────────────┘
        lock-step: one physics step and one reply per servo packet; ArduPilot's clock is the plant's timestamp
```

- The plant is the unmodified in-repo model: same `Airframe`, same `step`,
  constant density at 20 km (0.0889 kg/m3), 15.76 kg, 7.55 N max thrust,
  ±25° gimbal, 0.6 s thrust lag, 60°/s gimbal rate.
- Lock-step means simulated time is exact at any wall speed. Measured: about
  13–16× real time alone, about 6× with three runs in parallel on four cores
  (the Python plant is the bottleneck, 0.15 ms per RK4 step).
- Home is set to 50.0 N 30.0 E, **20 000 m**, so SITL's baro, GPS and the
  EKF origin are at float altitude. Ascent from the ground is not simulated.
- Accelerometer: specific force computed kinematically,
  `f_b = v̇ + ω×v + Rᵀẇ_wind + ω̇×r + ω×(ω×r) − Rᵀ(0,0,g)`, IMU at the CG
  height (1.21 m below the centre of volume). Floating level and still it
  reads (0, 0, −9.8066) m/s2 (*run*: first line of every truth log). The EKF
  aligns at t = 5.6 s and uses GPS from t = 41 s on every run; EKF position
  is within 0.5 m of truth and yaw within about 1° at the end of every run.
- `time_boot_ms` and plant time agree to within one telemetry sample
  (rise times from the EKF and from truth differ by 0.1–0.3 s).

### Servo / channel mapping

| ArduPilot output | Function | Plant | Scaling |
|---|---|---|---|
| SERVO1 | 26 GroundSteering | gimbal yaw | PWM 1500 ± 500 → ∓25°. Sign flip: Rover "right" must yaw the nose to starboard; `Controls.gimbal_yaw` positive pushes the stern to starboard. |
| SERVO3 | 70 Throttle | propeller thrust | 1000…2000 → 0…7.55 N, linear. `SERVO3_TRIM = SERVO3_MIN = 1000`: Rover's reverse demand becomes zero thrust. |
| SERVO4 | 94 Script1 | gimbal pitch | PWM 1500 ± 500 → ±25° (positive = stern down = nose up). Written by `scripts/aiur_pitch.lua`. PWM 0 = centred. |

On the vehicle these three leave the H743 over DroneCAN to the pod node
(`hardware.md`); that transport is *not* simulated here.

## 3. Which firmware, and why

| Candidate | Verdict | Reason |
|---|---|---|
| **ArduRover, boat frame, vectored thrust** | **chosen, run** | The only stock mixer for "one thruster on a steering servo": `MOT_VEC_ANGLEMAX` makes the steering demand a lateral-thrust fraction and the servo angle `atan(steer/throttle)`. GUIDED accepts heading + speed and position targets. Boats loiter instead of stopping. |
| Blimp | rejected | `Blimp/Fins.cpp` is a four-oscillating-fin indoor blimp mixer; no propeller, no thrust vectoring. No SITL binary published (404). |
| Copter | rejected | Needs several lift thrusters; attitude control assumes thrust carries the weight. |
| Sub | rejected (reasoned) | Neutrally buoyant and has depth hold, but every frame is a fixed multi-thruster matrix; no single gimballed thruster. |
| Plane | not run; plausible second candidate (reasoned) | Has what Rover lacks: airspeed-based speed control (TECS), wind-aware L1 navigation, pitch and altitude loops; rudder → gimbal yaw and elevator → gimbal pitch is a legal mapping. Against it: control scaling assumes authority grows with airspeed² (here it grows with *thrust*), TECS trades height for speed (an airship cannot), it cannot hold a point (it would orbit), and stall/landing logic has to be defeated. The binary is reachable; this was not tried. |

## 4. Parameters

`sitl/ardupilot/aiur_s2.parm` has a comment on every non-default line. The
ones that carry the design:

| Parameter | Value | Why |
|---|---|---|
| `FRAME_CLASS` | 2 (boat) | loiter at the destination instead of cutting throttle |
| `MOT_VEC_ANGLEMAX` | 25 | gimbal limit; turns on vectored-thrust mixing |
| `SERVO3_TRIM` | 1000 | unidirectional propeller |
| `CRUISE_SPEED` / `CRUISE_THROTTLE` | 6 / 32 | 2.42 N at 6 m/s in still air |
| `ATC_SPEED_P/I` | 0.08 / 0.02 | soft on purpose: thrust is also the rudder (§7.2) |
| `ATC_ACCEL_MAX` / `ATC_DECEL_MAX` | 0.1 / 0.05 | so the speed loop never asks for negative throttle |
| `ATC_STOP_SPEED` | 0 | Rover's "stopped" state zeroes throttle and resets the integrator that is holding against the wind |
| `ATC_BRAKE` | 0 | no reverse thrust |
| `ATC_STR_RAT_FF/P/I/D` | 0.2 / 4 / 0.3 / 0 | yaw accel is 0.18 rad/s2 per unit steering; hull is near-neutral in yaw, so mostly P |
| `ATC_STR_ANG_P` | 0.25 | heading error → turn rate |
| `ATC_STR_RAT_MAX`, `_ACC_MAX`, `_DEC_MAX` | 6°/s, 1.5, 1.5°/s2 | what the gimbal can deliver at cruise thrust |
| `ATC_TURN_MAX_G` | 0.1 | 0.6 g is for cars |
| `WP_SPEED` | 2 | **ground** speed: 6 m/s airspeed into a 4 m/s wind |
| `PSC_POS_P` / `PSC_VEL_P` | 0.02 / 0.1 | Rover divides lateral accel by ground speed (2) while the hull flies at 6 |
| `LOIT_TYPE` / `LOIT_RADIUS` / `LOIT_SPEED_GAIN` | 0 / 20 / 0.02 | "reverse" = zero thrust = fall back bow-first with the wind |
| `EK3_SRC1_POSZ` | 3 (GPS) | baro at 55 hPa, −56 °C, calibrated at boot 20 km lower (hardware reasoning; SITL's baro is ideal) |
| `GPS_NAVFILTER` | 8 | airborne <4 g (default; stated because other models stop above 12 km) |
| `INS_GYR_CAL` | 0 | never stationary at boot |
| `FS_THR_ENABLE`, `MODE_CH`, `ARMING_SKIPCHK` | 0, 0, 64 | no RC receiver |
| `FS_CRASH_CHECK` | 0 | "throttle on, not moving" is station-keeping, not a crash |
| `FS_GCS_ENABLE` | 0 | **SITL only** (wall-clock heartbeats at 16× speedup); must be 1 on the vehicle |
| `SERVO4_FUNCTION`, `SCR_ENABLE` | 94, 1 | pitch gimbal from Lua |

Not exercised: `MOT_THST_EXPO` (the plant's thrust is linear in command; a
real propeller needs a static-thrust test), DroneCAN output parameters,
anything about real sensors.

## 5. Results

All ArduPilot numbers are from the plant's truth log unless marked EKF.
Definitions match the in-repo ones: rise time = time to 90 % of the step,
RMS distance over the second half of the run, gimbal saturated = yaw gimbal
at its limit.

### 5.1 Heading: 90° step at 6 m/s, calm air

| | ArduRover 4.7.3 | in-repo `FlightController` (same airframe) |
|---|---|---|
| rise time | **19.1 s** | 13.0 s |
| overshoot | **3.3°** | 8.3° |
| settled within 5° | 20.1 s | — |
| max sideslip | 9.8° | 13.5° |
| gimbal saturated fraction | 0.013 | 0.013 |
| peak thrust in the turn | 4.47 N (cruise 2.44 N) | not reported |
| speed before the step | 6.00 m/s at 32.3 % throttle | 6.0 m/s at 2.42 N (32.1 %) |

Rover is slower because `ATC_STR_RAT_MAX` caps the turn at 6°/s; with 8°/s
and 2°/s2 it measured 16.7 s rise, 3.4° overshoot, 11.8° sideslip, 0.022
saturated (tuning run *d*). The in-repo controller has no rate cap.

### 5.2 Heading hold in 0.5 m/s gusts, 6 m/s, 500 s

| | ArduRover | in-repo (`gust0.5`, 600 s) |
|---|---|---|
| RMS heading error | 2.21° (EKF), 2.55° (truth) | 2.09° |
| RMS sideslip | 0.74° | 0.69° |
| gimbal saturated fraction | 0.063 | 0.016 |
| mean thrust power | 16.3 W | 14.7 W |

### 5.3 Station-keeping: 4 m/s wind, station 1.5 km upwind, 30 min, 6 m/s airspeed limit

| Controller | Gust σ | Final distance | RMS distance, 2nd half | Altitude excursion | Gimbal saturated | Mean thrust power |
|---|---|---|---|---|---|---|
| in-repo `station_keep` | 0 | 80.2 m | 124.0 m | 1.2 m | 0.00 | 7.9 W |
| in-repo `station_keep` | 0.5 | 58.3 m | 124.6 m | 52.0 m | 0.18 | 9.0 W |
| **Rover + companion `StationKeeper`** (+ Lua pitch) | 0 | **81.4 m** | **123.8 m** | 1.2 m | 0.00 | 7.8 W |
| **Rover + companion `StationKeeper`** (+ Lua pitch) | 0.5 | **103.6 m** | **148.2 m** | 36.0 m | 0.26 | 9.5 W |
| same, no Lua pitch script | 0.5 | 104.0 m | 148.2 m | 59.0 m | 0.27 | 9.2 W |
| Rover alone: position target → boat loiter (+ Lua) | 0 | **9.6 m** | **9.9 m** | 2.1 m | 0.006 | 8.4 W |
| Rover alone: position target → boat loiter (+ Lua) | 0.5 | 252.8 m | 287.9 m (max 660 m) | 30.7 m | 0.29 | 11.7 W |

Reading the table:

- The in-repo guidance law idles inside a 500 m radius by design, which is
  why "good" is ~80–125 m. Rover + the same law reproduces the in-repo
  calm-air numbers to within 1 m. That is the inner loop being equivalent.
- In gusts Rover + companion is 23 m worse on RMS distance and saturates the
  gimbal more (0.26 vs 0.18): Rover has no thrust floor, so while holding at
  13 % thrust it has about a quarter of the yaw authority the in-repo
  controller gives itself. Heading while holding: RMS 8.2° off upwind, worst
  36°.
- Rover's own loiter is the tightest hold in steady wind (10 m) and the
  worst in gusts: thrust is zero 20 % of the hold phase, heading wanders
  31° RMS (worst 86°), and it is blown out to 660 m before recovering.
- Gust runs are one seed each (plant `--gust-seed 3`); the turbulence
  sequence is not sample-identical to the in-repo run. Treat differences of
  tens of metres as noise.
- The companion's wind estimate here is the plant's mean wind, handed to
  `fly_test.py` on the command line. The in-repo scenario uses the truth wind
  low-passed over 60 s. Neither is a real estimator.
- Airspeed is not limited by anything in ArduPilot: peak airspeed was
  6.7 m/s (calm) to 7.3 m/s (gust) against a 6 m/s limit.

### 5.4 Reproduce

```bash
# in-repo controller (3/5/6/8 m/s station-keeping, then the handling table; ~50 s)
python3 -m aiur.strato.flight6dof

# in-repo numbers quoted above (default airframe handling, 4 m/s station-keeping)
python3 - <<'EOF'
from aiur.strato.sizing import ladder
from aiur.strato.flight6dof import Airframe, handling_report, station_keep
dp = ladder()["S2-dayloiter/hull"]
print(handling_report(Airframe.from_design(dp), 6.0))
for g in (0.0, 0.5):
    r = station_keep(Airframe.from_design(dp), 6.0, (0.0, -4.0, 0.0), (0.0, -1500.0, 0.0), gust_sigma=g)
    r.pop("rows"); print(g, r)
EOF

# ArduPilot (downloads the SITL binary to /tmp/aiur-ardupilot-sitl/bin on first use)
sitl/ardupilot/run_sitl.sh turn                                   # 5.1   ~50 s wall
GUST=0.5 sitl/ardupilot/run_sitl.sh turn --settle 600             # 5.2   (pre-step window; 500 s figure is from ekf_series.csv / truth.csv, t = 143..643 s)
sitl/ardupilot/run_sitl.sh companion                              # 5.3   ~2.5 min wall each
GUST=0.5 sitl/ardupilot/run_sitl.sh companion
GUST=0.5 LUA=0 sitl/ardupilot/run_sitl.sh companion
sitl/ardupilot/run_sitl.sh station
GUST=0.5 sitl/ardupilot/run_sitl.sh station
```

Each run leaves `result.json`, `fly_test.log`, `truth.csv`, `ekf_series.csv`,
`ardurover.log` and an ArduPilot dataflash log in
`$SITL_HOME/run-<scenario>[-$TAG]/`. `INSTANCE=n` shifts the ports so runs
can go in parallel. The clean-checkout path (`run_sitl.sh turn` with an empty
`SITL_HOME`) was run once end to end and reproduced 5.1 exactly.

## 6. Tuning log

Each line is one run or one parallel batch; *station* means §5.3's scenario.

| # | Change | What happened |
|---|---|---|
| 0 | First parameter guess, `hold` | EKF aligned, armed in GUIDED, accel-z −9.8066 at rest. SITL ignores SIGTERM → `kill -9` in the script. |
| t1 | `turn`, commanded 6 m/s | Flew at 2 m/s: Rover caps every GUIDED speed at `WP_SPEED`. Turn at 2 m/s: 38 s rise, 9° overshoot, 26 % saturated. |
| t2 | `WP_SPEED=6` for the turn test | 23.9 s rise, 5.1° overshoot, 7° ring-down after the turn. |
| t3 | `ATC_STR_RAT_P` 2.5→4 (a); `ANG_P` 0.25→0.15 (b); P 4 + D 1 (c) | (a) 2.4° overshoot, settled in 25 s — kept. (b) slower settle. (c) no better than (a). |
| t4 | rate/accel limits 4°/s,1→ 8,2 (d) or 6,1.5 (e) | (d) 16.7 s rise but a >5° wobble until 39 s. (e) 19.5 s, clean — kept. |
| it1 | first `station` (`LOIT_TYPE 1`, speed P 0.3, decel 0.2) | Arrived at 728 s; on switching to loiter the throttle went to zero, the hull yawed away at 1.5°/s with the gimbal hard over and no thrust, turned downwind and was blown 600 m back. Recovered and held at 10 m. |
| it2 | `LOIT_TYPE 0` | Same loss at arrival (1 km this time). With gusts: heading ended >90° off, Rover asked for reverse, i.e. zero thrust, for the remaining 600 s — a deadlock; final distance 2.7 km. |
| it3 | speed P 0.3→0.08, I 0.05→0.02, accel/decel 0.2→0.1/0.05, `ATC_STOP_SPEED 0` | Calm: clean arrival, holds at 7 m RMS. Gusts: heading swings ±30° in transit, never arrives. |
| g | `turn` with gusts, same parameters | Heading hold fine (1.6° RMS over 60 s) → the inner loop is not the problem; the navigation loop is. |
| it4 | `PSC_POS_P` 0.05→0.02, `PSC_VEL_P` 0.3→0.1 | Gusts: arrives at 730 s, holds within ~200 m, but with repeated zero-thrust heading losses. |
| c1 | companion guidance via `SET_POSITION_TARGET_LOCAL_NED` (velocity + yaw) | Zero thrust from the first command, blown 8 km downwind. Cause: Rover takes the *sign* of the speed from the north velocity component; the commanded heading was east with a slightly negative north component → "reverse". |
| c2 | companion guidance via `SET_ATTITUDE_TARGET` (yaw quaternion + thrust = speed / `WP_SPEED`) | Works: §5.3 rows 3–5. |
| lua | `aiur_pitch.lua` on/off in the gust runs | Altitude excursion 59 → 36 m; peak pitch 3° → 7.5° (15° in the Rover-loiter gust run). First-cut gains, not tuned further. |
| final | all of the above in `aiur_s2.parm`; §5 re-run from it | Numbers in §5. |

## 7. What does not work

1. **Pitch and altitude under ArduPilot.** Rover has no pitch loop, no
   altitude loop and no output function for a vertical thrust-vector axis.
   Without the script the pitch gimbal sits centred and altitude drifts
   (59 m in 30 min of 0.5 m/s gusts; 1–2 m in steady wind — `flight6dof` has
   no buoyancy stiffness, so this is a random walk, not a float model).
   `scripts/aiur_pitch.lua` (10 Hz, EKF height and climb rate → SERVO4) cut
   that to 36 m. It is a trim loop: the gimbal gives ~10 N·m at cruise thrust
   against ~190 N·m/rad of pendulum stiffness, about 3° of pitch. Vent,
   ballast and the float logic (`guidance.FloatController`) stay on the
   companion. Alternative transport, *not run*: `SERVO4_FUNCTION 0` and
   `MAV_CMD_DO_SET_SERVO` from the companion (Rover refuses DO_SET_SERVO on
   a channel that has a function assigned), or functions 184–189 with
   `MAV_CMD_DO_SET_ACTUATOR`.
2. **Zero throttle is zero rudder, and Rover cuts throttle freely.** With
   vectored thrust the steering output is limited to
   `throttle × tan(MOT_VEC_ANGLEMAX)`. Rover cuts throttle to decelerate, to
   "stop" inside the loiter radius, and whenever it wants reverse; the hull
   is yaw-unstable (10° in 8 s open loop), so each cut is a heading loss.
   `MOT_THR_MIN` does not help (zero stays zero, and it is applied after the
   mixing). There is no stock parameter that couples a steering demand to a
   thrust floor, which is exactly what the in-repo controller's
   `authority_floor` does.
3. **Rover's own loiter in gusts** (table row 7): unusable for the reason
   above. It can also deadlock: heading more than 90° off the target →
   "reverse" → zero thrust → no way to turn back (it2).
4. **Ground speed, not airspeed.** Every Rover speed target is ground speed
   along the body axis. The airspeed limit exists only as `WP_SPEED` chosen
   by whoever knows the wind. Wind at or above the airspeed limit was not
   tested; Rover would simply saturate the throttle.
5. **`SET_POSITION_TARGET_LOCAL_NED` with yaw + velocity** takes the sign
   of the speed from the north velocity component, so any heading with a
   southward component is flown in reverse (c1: the heading was east with a
   slightly negative north component). Use `SET_ATTITUDE_TARGET` for
   heading + signed speed.
6. **Low authority while holding.** At the 13 % thrust that balances a 4 m/s
   wind the gimbal is saturated a quarter of the time in 0.5 m/s gusts.
7. **Not tested at all:** crosswind transits (Rover assumes velocity along
   the heading), wind ≥ airspeed limit, the SP1 trainer
   (`json_plant.py --design SP1-trainer/hull` loads; no parameter file was
   made or flown), ascent/descent, failsafes, sensor faults, DroneCAN,
   real hardware. SITL sensors are ArduPilot's default simulated ones.
8. Unexplained and not chased: a constant ~1° difference between EKF yaw
   and truth yaw in every run.

## 8. Recommendation

**Stock ArduRover + companion, not a custom vehicle frame — with one change
to make before trusting it in gusts.**

Evidence for: the stock firmware estimates, arms, and flies heading and
speed on this hull with handling comparable to the in-repo controller
(§5.1, §5.2), and with the companion's `StationKeeper` on top it reproduces
the in-repo station-keeping in steady wind to the metre and stays within
150 m RMS in gusts (§5.3). The division of labour in `ros.md` — ArduPilot in
GUIDED as estimator, failsafe and actuator I/O; companion sends setpoints —
is what was flown.

What the evidence says to change:

- **Do not use Rover's waypoint/loiter navigation.** The companion sends
  heading + signed ground speed (`SET_ATTITUDE_TARGET`) at ≥ 1 Hz, converts
  its airspeed demand with its own wind estimate, and owns the airspeed
  limit.
- **Pitch/altitude trim goes in a Lua script on the flight controller**
  (run, §7.1), float management stays on the companion.
- **The remaining gap is the thrust floor** (§7.2, §7.6). The next step,
  *reasoned, not run*: move the inner loop itself into Lua —
  `FlightController.command` is ~40 lines — and drive
  `vehicle:set_steering_and_throttle()` in GUIDED, so steering demand can
  raise thrust. Loop bandwidths here are 0.1–0.5 rad/s; a 20–50 Hz script is
  ample. ArduPilot then remains EKF, arming, failsafe, logging and I/O.
- **A custom frame or vehicle fork is not justified yet.** What stock Rover
  lacks is a thrust floor tied to steering demand, an airspeed loop and a
  pitch axis; the first and third fit in a script and the second belongs to
  whoever holds the wind estimate. A fork becomes worth its maintenance cost
  only if the Lua inner loop proves inadequate on hardware, or if failsafe
  behaviour (which is Rover's "stop", i.e. zero thrust — the wrong action
  for this hull) has to change. ArduPlane is the other thing to try first
  (§3); it was not run.

`ros.md`'s "ArduPilot itself has never been in the loop: no SITL" is no
longer true; "no custom airship frame" still is, by choice.
