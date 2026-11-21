# STRATO on ROS 2

Status: runs headless on ROS 2 Jazzy + Gazebo Harmonic (Ubuntu 24.04).

The rule from the P0 twin carries over: the control code under test is the
control code that will fly. The three flight nodes each wrap one class from
[`aiur/strato/guidance.py`](../../aiur/strato/guidance.py) — the same
objects the batch models call.

## Workspace

```
ros2_ws/src/
  aiur_msgs         BuoyancyState, FlightStatus, FloatCommand - the only custom interfaces
  aiur_core         installs the repo's `aiur` Python package (symlink; one copy of the code)
  aiur_description  GENERATED: URDF, hull STL, Gazebo models and worlds
  aiur_strato_sim   plant (whole mission, ascent.AscentSim) and flight_plant (6-DoF at float); own /clock
  aiur_flight       float_manager, station_keeper, attitude_controller, termination, loggers
  aiur_bringup      launch files and the MAVROS topic map
```

Build and fly a mission:

```
python tools/strato_export.py                 # regenerate aiur_description from the sizing
cd ros2_ws && colcon build && source install/setup.bash
ros2 launch aiur_bringup sim_mission.launch.py design:=S1-touch/hull record:=true
```

The launch returns when the vehicle has landed, leaving `summary.json`,
`track.csv` and (with `record:=true`) an MCAP bag in `output_dir`. A
three-hour flight takes about a minute. Arguments: `design`
(`S1-touch/hull`, `S1-touch/tandem`, `S2-dayloiter/hull`), `wind_profile`,
`wind_scale`, `float_duration_s`, `max_range_m`, `steps_per_tick`.

A recorded run is in [`evidence/`](evidence/): float entry at 5,168 s,
float held at 19,876 ± 38 m for an hour, landing 64.5 km out — the batch
model gives 5,172 s and 64.6 km.

## The whole mission over MAVLink

```
ros2 launch aiur_bringup sim_mission6.launch.py design:=S2-dayloiter/hull
```

`unified_plant` is `mission6.UnifiedSim` - buoyancy model plus 6-DoF, with
the attitude inner loop inside it, as it is inside an autopilot - behind a
MAVLink 2 UDP port. `mavlink_bridge` is the only thing that talks to it.
The flight nodes see standard topics and cannot tell the difference.

| Direction | MAVLink | ROS |
| --- | --- | --- |
| in | `GLOBAL_POSITION_INT` + `ATTITUDE` | `odom` (ENU/FLU), `gps/fix` |
| in | `VFR_HUD`, `SCALED_PRESSURE`, `SYS_STATUS` | `airspeed`, `baro/pressure`, `battery` |
| in | `NAMED_VALUE_FLOAT` (gas_temp, fill, dp, ballast) | `buoyancy`, `temperature/*` |
| out | `SET_ATTITUDE_TARGET` (heading + pitch quaternion, thrust = airspeed / dash) | `cmd/air_velocity`, `cmd/float.pitch_cmd_rad` |
| out | `COMMAND_LONG MAV_CMD_DO_SET_ACTUATOR` (vent, ballast rate, trim) | `cmd/float` |

One recorded run: 164,220 frames received, 23,460 sent; float held at
19,870 m (sd 178 m); landing 59.3 km from launch. Fault arguments
`gimbal_jam_at_s`, `motor_fail_at_s` and `gps_dropout_at_s` inject failures
mid-flight; during a GNSS outage the bridge dead-reckons on barometric
altitude (one run: 1,197 s dead-reckoned, mission completed).

What this does and does not show: the mapping and the bridge work on the
real wire format. The thing on the other end is this repo's simulation, not
ArduPilot. ArduPilot SITL has not been run, and ArduPilot has no stock frame
that accepts these two messages for a propeller airship - that custom frame
is unwritten.

## Station-keeping with the full control chain

```
ros2 launch aiur_bringup sim_float.launch.py wind_east_m_s:=-5.0
```

`station_keeper` (outer loop) → `attitude_controller` (inner loop, wrapping
`flight6dof.FlightController`) → `flight_plant` (rigid body, added mass,
gust gradients). The command crossing the last arrow is
`aiur_msgs/PropulsionCommand` — thrust and two gimbal angles, exactly what
the stern pod's CAN node receives. S2 hull, 6 m/s airspeed limit, starting
1.5 km downwind, 30 minutes, 0.5 m/s turbulence:

| Wind | Final distance from station | RMS distance, second half | Gimbal saturated |
| ---: | ---: | ---: | ---: |
| 3 m/s | 23 m | 83 m | 46 % |
| 5 m/s | 228 m | 554 m | 10 % |
| 8 m/s | 5.4 km and growing | — | 8 % |

It holds what its airspeed allows and loses ground head-to-wind above that.
The gimbal working hard in light wind is the low-airspeed regime where fins
do nothing and thrust is being throttled back; it is the handling case to
watch on the SP1 trainer.

## Topics (namespace `/aiur`)

Frames follow REP-103 and REP-105: `map` is ENU with its origin at the
launch point; `base_link` is at the hull's centre of volume, x forward,
y left, z up.

| Topic | Type | Direction |
| --- | --- | --- |
| `odom` | `nav_msgs/Odometry` | plant → nodes |
| `gps/fix` | `sensor_msgs/NavSatFix` | plant → |
| `baro/pressure` | `sensor_msgs/FluidPressure` | plant → |
| `temperature/ambient`, `temperature/gas` | `sensor_msgs/Temperature` | plant → |
| `battery` | `sensor_msgs/BatteryState` | plant → |
| `buoyancy` | `aiur_msgs/BuoyancyState` | plant → |
| `status` | `aiur_msgs/FlightStatus` | float_manager → |
| `cmd/float` | `aiur_msgs/FloatCommand` | float_manager → plant |
| `cmd/air_velocity` | `geometry_msgs/TwistStamped` | station_keeper → plant |
| `wind/estimate` | `geometry_msgs/Vector3Stamped` | station_keeper → |
| `cmd/terminate` | `std_msgs/Bool` | termination → plant |
| `termination/command` | `std_msgs/Bool` | operator → termination |
| `cmd/propulsion` | `aiur_msgs/PropulsionCommand` | attitude_controller → flight_plant |
| `airspeed`, `imu/data`, `joint_states` | `std_msgs/Float32`, `sensor_msgs/Imu`, `sensor_msgs/JointState` | flight_plant → |
| `/clock` | `rosgraph_msgs/Clock` | plant |

## From simulation to the vehicle

On the vehicle the plant node is replaced by ArduPilot + MAVROS and two
small drivers; the flight nodes are remapped, not rewritten.
[`mavros_topic_map.yaml`](../../ros2_ws/src/aiur_bringup/config/mavros_topic_map.yaml)
is the mapping. Two things do not map and are not meant to:

- `cmd/terminate` is not routed to the autopilot. Cut-down is fired by the
  flight-termination unit on its own processor; the ROS node exists so the
  same `Geofence` criteria are exercised in simulation.
- ArduPilot has no stock frame for a propeller airship (its Blimp vehicle is
  a finned indoor blimp; PX4's airship frame is unmaintained). The plan is
  ArduPilot in GUIDED mode as estimator, failsafe and actuator I/O, with the
  heading/airspeed loop (`attitude_controller`) on the companion sending
  actuator targets. The bridge from `PropulsionCommand` to MAVLink actuator
  commands is not written, and neither is the decision whether that loop
  should instead live in the autopilot as a custom frame.

## Gazebo cross-check

```
ros2 launch aiur_description gz_check.launch.py design:=S2-dayloiter/hull
```

Runs Gazebo headless with the generated model on the stock `Buoyancy` and
`LighterThanAirDynamics` systems at 20 km air density, pushes it with the
sizing model's cruise thrust, bridges odometry into ROS and prints one line:

| | Gazebo | Sizing model |
| --- | ---: | ---: |
| S2 terminal airspeed | 6.18 m/s | 6.00 m/s |
| S2 initial acceleration | 0.1507 m/s² | 0.1520 m/s² |
| S1 terminal airspeed | 3.14 m/s | 3.00 m/s |
| S1 initial acceleration | 0.0436 m/s² | 0.0437 m/s² |
| Free hull, no thrust, 590 s | 3.6 m altitude drift | neutral |

That checks drag, mass, added mass and buoyancy against physics written by
someone else.

### With fins, off the rail

```
ros2 launch aiur_description gz_fins.launch.py csv_dir:=/tmp/aiur_gz_fins
```

Twenty-three open-loop cases with four `LiftDrag` fins on the hull
([gazebo-fins.md](gazebo-fins.md)). Time for a 2 degree sideslip to grow to
10 degrees of yaw at 6 m/s:

| Fins / V^(2/3) | In-repo 6-DoF | Gazebo, same hull assumptions | Gazebo, plugin's own hull model |
| ---: | ---: | ---: | --- |
| 0.30 | 4.5 s | 4.2 s | 8.6 s, diverges |
| 0.50 | 7.8 s | 7.0 s | never: settles 5.6 degrees off |
| 0.60 | 13.2 s | 11.2 s | never: settles 1.8 degrees off |

The two agree within 7-15 % where they share assumptions, and the
difference is traced term by term. Where they differ in kind, Gazebo's hull
model (which lets flow separation remove a quarter of the Munk moment) says
the in-repo model is conservative. Both use the same assumed fin lift
slope, so that number is still untested, and "does 0.50 hold heading
unaided" flips on how much of the Munk moment is real.

## Known gaps

- ArduPilot itself has never been in the loop: no SITL, no custom airship
  frame, no parameter file.
- Sensor noise and radio loss are not injected at the message level (motor,
  gimbal and GNSS-outage faults are).
- The Gazebo fin runs are open loop; the closed-loop turn study has not been
  repeated there.
- The termination node never exercises link loss; the firmware does.
- `robot_localization` is installed but not in the loop; on the vehicle the
  autopilot's EKF is the estimator.
