# ArduPilot in the loop: ArduRover SITL flying the airship physics

Status: **run**. The real ArduRover 4.7.3 firmware (SITL build) arms and flies
`aiur.strato.flight6dof` through ArduPilot's JSON physics interface.

- Stock Rover turns the S2 hull about as well as the in-repo controller, but
  it cuts the throttle to slow down, and on this hull zero throttle is zero
  rudder (§5–§8).
- A Lua inner loop on the autopilot (`scripts/aiur_inner.lua`, §9) puts the
  in-repo control law with its thrust floor and an airspeed limit under
  Rover's EKF, arming and mode machinery. With it the hull holds a crosswind
  station and weathercocks correctly in wind at the airspeed limit, where
  stock Rover is blown 12 km downwind.
- The ROS 2 station-keeping chain now flies ArduRover SITL end to end
  (`ros2 launch aiur_bringup sitl_ardupilot.launch.py`, §10), with the wind
  estimated on board instead of handed in.

Everything below is marked as *run* (with numbers) or *reasoned* (not run).
Sections 1–8 are the first pass (stock Rover); 9–11 were added after it and
supersede the recommendation where they say so.

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
| (airspeed) | `ARSPD_TYPE 100`, only with `aiur_inner.parm` | JSON `airspeed` = true airspeed along body x | SITL turns it into a pitot pressure; see §9 for why its noise is zeroed |
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
# (the turn test now sends SET_ATTITUDE_TARGET and sets WP_SPEED itself; it reproduces 5.1 exactly)
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
7. **Not tested at all** (in this first pass; crosswind and wind at the
   limit were flown later, §9.1): crosswind transits (Rover assumes velocity
   along the heading), wind ≥ airspeed limit, the SP1 trainer
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

## 9. The thrust floor: a Lua inner loop on the autopilot (*run*)

`sitl/ardupilot/scripts/aiur_inner.lua`, enabled with `INNER=1` (which also
layers `sitl/ardupilot/aiur_inner.parm`). It is
`flight6dof.FlightController.command` for yaw and speed, at 50 Hz:

```
N      = Izz (wn² e_psi − 2 ζ wn r)                       wn 0.35, ζ 0.9, Izz 420.7 kg m²
T_spd  = 2.0 e_v + ∫ 0.15 e_v dt                          e_v = min(ground-speed error, AIN_ASPD_MAX − airspeed)
T      = max(T_spd, min(Tmax, max(0.30 Tmax min(1, |e_psi|/0.2), |N| / (arm sin 25°))))
gimbal = asin(clamp(−N / (arm T_now)))                    T_now: 0.6 s lag model of the commanded thrust
```

How it sits in ArduPilot (4.7.3 scripting API, checked against
`bindings.desc` in the source):

- **Demand.** The companion sends exactly what it sends stock Rover:
  `SET_ATTITUDE_TARGET`, heading in the quaternion, thrust = signed ground
  speed / `WP_SPEED`. Rover processes it as usual; the script reads the same
  message with `mavlink:register_rx_msgid(82)` / `mavlink:receive_chan()`.
  There is no binding that exposes GUIDED's desired heading and speed.
- **Output.** `SRV_Channels:set_output_pwm_chan_timeout()` on the steering and
  throttle channels, 200 ms timeout. Rover's own controllers keep running
  underneath; if the script stops, is disabled (`AIN_ENABLE 0`) or the
  demand is older than 3 s, the override lapses and they have the outputs
  back. `vehicle:set_steering_and_throttle()` exists but was not used: it
  switches GUIDED into a different sub-mode and every incoming
  `SET_ATTITUDE_TARGET` would switch it back.
- **Fallback, run:** `INNER=1 run_sitl.sh turn --set AIN_ENABLE=0` gives the
  stock result to the digit (19.1 s, 3.3°). *Not run:* killing the script
  mid-flight; a Lua error.
- **Airspeed.** Rover does have the airspeed library. With `ARSPD_TYPE 100`
  the plant's JSON `airspeed` (true airspeed) reaches
  `ahrs:airspeed_estimate()`; times `ahrs:get_EAS2TAS()` it reads 6.00 m/s
  at a true 6.00. Two honest caveats: (1) SITL's sensor is a pitot with
  ±2 Pa of noise, and at 20 km the whole signal is 1.6 Pa at 6 m/s, so
  `SIM_ARSPD_RND` is set to 0 to stand in for an anemometer — no
  differential-pressure sensor can do this job on the vehicle; (2) the
  airspeed limit is therefore only as real as that sensor.
- **Pitch** stays in the separate `aiur_pitch.lua`; both scripts run together.
- New parameters: `AIN_ENABLE` (1), `AIN_ASPD_MAX` (6 m/s), `AIN_FS_HOLD` (1).

Two things went wrong on the way and their runs were discarded: the plant
first sent *equivalent* airspeed where SITL expects *true* airspeed (the
script read 1.6 m/s at a true 6 and the cap never engaged), and with SITL's
default pitot noise the reading was meaningless. The table below is from
the third pass, with both fixed.

### 9.1 Before / after

Same plant, same seeds, same companion (`fly_test.py` with the true mean
wind); "stock" is §5's configuration. Truth log unless marked. The two
harder cases are new for both.

| Case | Metric | Stock Rover loops | `aiur_inner.lua` | in-repo controller |
|---|---|---|---|---|
| 90° step, 6 m/s, calm | rise time | 19.1 s | **13.0 s** | 13.0 s |
| | overshoot | 3.3° | 7.1° | 8.3° |
| | max sideslip | 9.8° | 12.6° | 13.5° |
| | gimbal saturated | 0.013 | 0.023 | 0.013 |
| | peak thrust | 4.47 N | 7.54 N | — |
| Heading hold, 0.5 m/s gusts, 500 s | RMS heading error (EKF / truth) | 2.21° / 2.55° | 2.71° / 3.05° | 2.09° |
| | gimbal saturated | 0.062 | **0.028** | 0.016 |
| | mean thrust power | 16.3 W | 14.1 W | 14.7 W |
| | peak airspeed | 7.39 m/s | **6.11 m/s** | — |
| Station 1.5 km upwind, 4 m/s wind | final / RMS distance | 81.4 / 123.8 m | 80.8 / 122.6 m | 80.2 / 124.0 m |
| same, 0.5 m/s gusts | final / RMS distance | 103.6 / 148.2 m | 95.6 / 148.8 m | 58.3 / 124.6 m |
| | gimbal saturated | 0.264 | **0.147** | 0.18 |
| | heading RMS off upwind while holding | 8.2° | **3.3°** | — |
| | time above 6.3 m/s airspeed | 11.3 % | **0 %** | — |
| | time at zero thrust | 2 % | 0 % | — |
| **Crosswind transit**: station 1.5 km at 90° to a 4 m/s wind | final / RMS distance | 76.2 / 104.4 m | 76.7 / 104.6 m | 72.8 / 106.1 m |
| same, 0.5 m/s gusts | final / RMS distance | 44.5 / 57.6 m | **10.8 / 43.8 m** | 80.5 / 104.3 m |
| | gimbal saturated | 0.381 | 0.232 | 0.29 |
| **Wind at the airspeed limit**: 6 m/s, station 1.5 km upwind | final / RMS distance | **11 980 / 9 414 m** | **1 499.7 / 1 491.8 m** | 1 516 / 1 516 m |
| | time at zero thrust | 99 % | 0 % | — |
| same, 0.5 m/s gusts | final / RMS distance | 12 592 / 9 819 m | 1 955.5 / 1 857.4 m | 1 781 / 1 755 m |
| | mean airspeed | −0.07 m/s | 5.89 m/s | — |
| Rover HOLD for 300 s in 4 m/s wind | mean throttle | 0 % | 13.1 % | — |
| | heading RMS off upwind | 118° | 0.2° | — |
| | drift | 1 283 m (4.3 m/s) | 3.7 m | — |

Reading it:

- **Calm and steady wind:** no difference in station-keeping; the turn is now
  the in-repo turn (13.0 s), because the law is the same and the rate cap is
  gone.
- **Gusts:** the gimbal saturates about half as often, the bow stays within
  3° RMS of the wind instead of 8°, thrust never reaches zero, and the
  airspeed limit holds. RMS distance does not improve at 4 m/s upwind
  (148 m both); it does in the crosswind case. One seed per case.
- **Crosswind:** stock Rover's inner loop copes — the companion's guidance
  does the crabbing — but with gusts it is saturated 38 % of the time.
- **Wind at the limit — the case that separates them.** The correct demand is
  "bow into wind, zero ground speed". Stock Rover arrives at the start with
  forward ground speed, cuts the throttle to shed it, loses the bow, ends up
  pointing downwind doing 6 m/s over the ground against a demand of zero,
  and holds zero thrust for the rest of the run: 12 km lost in 30 min. With
  the script the hull holds the bow into wind at 6.0 m/s airspeed and loses
  0 m (steady) or 456 m (gusts; the in-repo controller loses 281 m — the
  script's airspeed cap is strict, the in-repo floor is allowed to exceed it).
- The in-repo column beats both in the 4 m/s gust row and loses to both in
  the crosswind gust row; with one seed each that is noise, not ranking.

### 9.2 Failsafe: is thrust still cut?

**Stock: yes.** Rover's failsafe actions end in HOLD (`FS_ACTION` 2, the
default; EKF failsafe too), and HOLD is throttle zero. Run: 300 s in HOLD in
a 4 m/s wind — motor off, hull swings (118° RMS off the wind, through 180°)
and drifts 1 283 m.

**With the script: no, by design, and it is a parameter.** `AIN_FS_HOLD 1`
(default) keeps the script active in HOLD and LOITER: it holds the heading
it had on entry and zero ground speed along it, thrust floor and airspeed
cap included. Same test: 13 % throttle, bow within 0.4° of the wind, 3.7 m
of drift. `aiur_inner.parm` also sets `FS_ACTION 6` (Loiter, else Hold).

What that costs and what was not tested:

- HOLD no longer stops the motor. Disarming does. An operator who wants the
  stock meaning sets `AIN_FS_HOLD 0`.
- The script needs EKF velocity and yaw. On an **EKF failsafe** it has nothing
  to steer by, goes inactive, and thrust is cut as in stock. Not addressed.
- Tested by commanding HOLD (the state `FS_ACTION 2` produces) with the
  companion silent. *Not run:* a real GCS/companion-loss trigger (GCS
  failsafe is disabled in SITL, §4), the `FS_ACTION 6` LOITER path, gusts,
  a wind above the limit, a heading on entry that is not into wind (the
  script would hold it and drift sideways; a better rule is "point against
  the measured drift", not written).

## 10. The ROS 2 chain flying ArduRover (*run*)

```
ros2 launch aiur_bringup sitl_ardupilot.launch.py [gust:=0.5] [inner:=1] [use_airspeed:=true]

 run_sitl.sh idle ─┬─ json_plant.py ◄─UDP JSON─► ardurover SITL ◄─MAVLink TCP 5760─► mavlink_bridge (autopilot:=ardurover)
                   │                                                                    │ odom, gps/fix, baro, battery, airspeed, cmd/propulsion*
                   └─ (downloads the binary on first use)                               ▼
                                                              station_keeper (always_active) ── cmd/air_velocity, wind/estimate ──► bridge
                                                              station_report (relative_time, report_wind) ── one STATION_REPORT line, launch shuts down
 * in this mode cmd/propulsion is the autopilot's actual SERVO_OUTPUT_RAW, converted to newtons and radians
```

What `mavlink_bridge` does in `autopilot:=ardurover` (default `sim` is
untouched: every new branch is behind `self.rover`):

1. connects (retrying while SITL opens its port), sends a 1 Hz companion
   heartbeat;
2. requests streams with `MAV_CMD_SET_MESSAGE_INTERVAL`: GLOBAL_POSITION_INT
   and SERVO_OUTPUT_RAW at 5 Hz, ATTITUDE at 10 Hz, VFR_HUD, SCALED_PRESSURE,
   SYS_STATUS, GPS_RAW_INT, EKF_STATUS_REPORT at 1 Hz;
3. waits for a 3D fix and EKF attitude + velocity + position, sets GUIDED,
   sets `WP_SPEED` to `dash_airspeed_m_s` (the scale of the thrust field),
   arms (`auto_arm`);
4. from `activate_after_s` of autopilot time publishes odometry — which is
   what starts `station_keeper` — with the map origin placed so the vehicle
   is at `start_offset_*` (the station is the origin, as `station_report`
   assumes);
5. on every GLOBAL_POSITION_INT sends `SET_ATTITUDE_TARGET`: heading from
   `cmd/air_velocity`, thrust = (commanded airspeed + wind estimate along
   that heading) / `WP_SPEED`, signed;
6. does not send the float actuator command and does not publish `buoyancy`
   or gas/ambient temperature: stock Rover has neither end of that.

**Time.** No `/clock`, `use_sim_time` off. Every stamp is ArduPilot's
`time_boot_ms`; `station_keeper` takes dt from odometry stamps, the bridge
sends one setpoint per position message, `station_report` counts stamped
seconds. So the chain is correct at any SITL speed and SITL runs
lock-stepped at ~15× real time; the only wall-clock quantity is the
companion's reaction latency (milliseconds against a 200 ms telemetry
period). The bridge's start-up retries are wall-paced (0.25 s). The first
version used 2 s, which at 15× was 30 s of flight per step and left the hull
drifting unarmed until activation; that run is not the one reported.

### 10.1 Results: 4 m/s wind, station 1.5 km upwind, 30 min

Distances are from `station_report` (EKF odometry, rounded by that node);
saturation and airspeed are from the plant's truth log.

| Chain | Gust | Final | RMS 2nd half | Wind estimate (true −4.00 E) | Yaw gimbal saturated | Time above 6.3 m/s |
|---|---|---|---|---|---|---|
| in-repo `station_keep` (truth wind, low-passed) | 0 | 80 m | 124 m | — | 0.00 | — |
| in-repo `station_keep` | 0.5 | 58 m | 125 m | — | 0.18 | — |
| pymavlink companion, wind handed in, stock Rover | 0 | 81 m | 124 m | given | 0.00 | 1.5 % |
| pymavlink companion, wind handed in, stock Rover | 0.5 | 104 m | 148 m | given | 0.26 | 11 % |
| pymavlink companion, wind handed in, `aiur_inner.lua` | 0 | 81 m | 123 m | given | 0.00 | 1.6 % |
| pymavlink companion, wind handed in, `aiur_inner.lua` | 0.5 | 96 m | 149 m | given | 0.15 | 0 % |
| **ROS chain, stock Rover** | 0 | **2 279 m** | **1 053 m** | −4.87 (wandering) | 0.16 | 17 % |
| **ROS chain, stock Rover** | 0.5 | 136 m | 142 m | **−0.97** | 0.31 | 16 % |
| **ROS chain, `inner:=1`** | 0 | 80 m | 122 m | −4.33 | 0.00 | 1.7 % |
| **ROS chain, `inner:=1`** | 0.5 | 87 m | 129 m | −4.49 | 0.15 | 0 % |
| **ROS chain, `inner:=1 use_airspeed:=true`** | 0 | 81 m | 122 m | **−4.01** | 0.00 | 1.7 % |
| **ROS chain, `inner:=1 use_airspeed:=true`** | 0.5 | 85 m | 131 m | **−4.08** | 0.15 | 0 % |

### 10.2 The self-estimated wind makes stock Rover worse, and why

`station_keeper` infers wind as *ground velocity minus the air velocity it
last commanded*. That assumes the autopilot flies the commanded **air**
velocity. ArduRover flies **ground** speed: the bridge converts the air
demand with the node's own wind estimate, Rover achieves that ground speed
whatever the real wind is, and the estimator gets back exactly the number
it supplied. The wind is unobservable — the estimate sat at −0.97 m/s in a
4 m/s wind (gust run) and the hull flew at up to 8.1 m/s airspeed to make
the ground speed asked for. When Rover then *fails* to achieve the demand
the loop is worse than blind: in the steady-wind run the estimate wandered
past the airspeed limit, the keeper went to "cannot hold, weathercock", the
bridge's ground-speed demand went negative, Rover cut the throttle (§7.2),
the hull drifted downwind, and "ground minus commanded air" read that as
still more wind. Final distance 2.3 km (3.6 km on an earlier run with the
slower start-up). Zero thrust 29 % of the run.

Two things fix it, both run:

- `inner:=1`. The script's airspeed cap makes the achieved ground speed
  depend on the real wind, so the same estimator converges (−4.33 /
  −4.49 m/s, 8–12 % high) and the result matches the handed-in-wind runs —
  slightly better in gusts (129 vs 149 m RMS, one seed).
- `use_airspeed:=true` (new `station_keeper` parameter, default off): the
  achieved air velocity is the *measured* true airspeed along the present
  heading (the script reports it as `AIN_ASPD`; the bridge publishes it on
  `airspeed`). Estimate −4.01 / −4.08 m/s. Distance is the same as without
  it; what improves is that the wind estimate is right, which matters as
  soon as the wind is near the limit. This leans on the same idealised
  airspeed sensor as §9.

### 10.3 Reproduce

```bash
source /opt/rosenv.sh
cd ros2_ws && colcon build && source install/setup.bash && cd ..
export PYTHONPATH=$PWD:$PYTHONPATH              # the nodes import aiur.strato
ros2 launch aiur_bringup sitl_ardupilot.launch.py                                  # stock Rover, ~2.5 min wall
ros2 launch aiur_bringup sitl_ardupilot.launch.py gust:=0.5
ros2 launch aiur_bringup sitl_ardupilot.launch.py inner:=1 [gust:=0.5]
ros2 launch aiur_bringup sitl_ardupilot.launch.py inner:=1 use_airspeed:=true [gust:=0.5]
# parallel runs: give each its own ROS_DOMAIN_ID and instance:=N tag:=name output:=file.json

# section 9 (pymavlink companion)
INNER=1 sitl/ardupilot/run_sitl.sh turn
INNER=1 GUST=0.5 sitl/ardupilot/run_sitl.sh turn --settle 600
[INNER=1] [GUST=0.5] sitl/ardupilot/run_sitl.sh companion                          # 4 m/s, upwind
[INNER=1] [GUST=0.5] sitl/ardupilot/run_sitl.sh companion --bearing -90            # crosswind transit
[INNER=1] [GUST=0.5] WIND_E=-6 sitl/ardupilot/run_sitl.sh companion                # wind at the limit
[INNER=1] sitl/ardupilot/run_sitl.sh failsafe                                      # HOLD for 300 s
INNER=1 sitl/ardupilot/run_sitl.sh turn --set AIN_ENABLE=0                         # fallback = stock
python3 -c "from aiur.strato.sizing import ladder; from aiur.strato.flight6dof import *; \
dp=ladder()['S2-dayloiter/hull']; \
[print(n,g,{k:round(v,1) for k,v in station_keep(Airframe.from_design(dp),6.0,w,s,gust_sigma=g).items() if k!='rows'}) \
 for n,w,s in (('crosswind',(0.0,-4.0,0.0),(-1500.0,0.0,0.0)),('wind6',(0.0,-6.0,0.0),(0.0,-1500.0,0.0))) for g in (0.0,0.5)]"
```

The launch file's SITL process output lands in `$SITL_HOME/run-idle-<tag>/`;
the summary is the `STATION_REPORT` line and the `output:=` JSON.
`sim_mission6.launch.py` was run once after the bridge change (whole mission,
7 224 frames in, 1 032 out, no errors); it was not diffed against a
pre-change run.

## 11. What is still not flown under ArduPilot

- **Ascent, float entry, descent, termination**: SITL starts at 20 km with a
  neutrally buoyant constant-density plant. `flight6dof` has no buoyancy
  dynamics; the unified plant that does is not behind the JSON interface.
- **The full mission launch** (`float_manager`, `termination`,
  `mission_logger` against ArduPilot): only `station_keeper` +
  `station_report` were run. `float_manager` needs `buoyancy`, which Rover
  cannot supply; vent, ballast and trim commands have no receiver.
- **DroneCAN**: the three outputs are PWM numbers in a UDP packet; the pod
  node, its failsafe and its latency are not in the loop.
- **Real sensors**: SITL's default GPS, compass, IMU and baro models; an
  idealised airspeed sensor; no GNSS dropout (the bridge's dead-reckoning
  path was not exercised against ArduPilot); no thermal effects.
- **Real failsafes**: §9.2 lists what was and was not triggered.
- **Hardware timing**: Lua at 50 Hz on an H743 alongside the EKF was not
  measured; in SITL the two scripts ran without scheduler complaints.
- Crosswind and wind-at-limit were flown with the pymavlink companion only,
  not through ROS. The SP1 trainer is still unflown.

## 12. Recommendation, revised

Stock ArduRover firmware + companion still, with **`aiur_inner.lua` as part
of the vehicle configuration, not an option**: without it Rover is unsafe in
wind at the airspeed limit (12 km lost), in HOLD (motor off, hull tumbling),
and with an on-board wind estimate (2–3.6 km lost in a steady 4 m/s wind).
With it, every case flown is within noise of the in-repo controller. §8's
"next step" is done; its "do not use Rover's waypoint/loiter navigation"
stands. A custom frame is still not justified by anything measured here.
The open items that decide whether this configuration can fly are the
airspeed sensor (§9: nothing on the bench resolves 1.6 Pa) and the EKF
failsafe (§9.2).

