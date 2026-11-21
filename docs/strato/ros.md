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
  aiur_strato_sim   plant node: ascent.AscentSim behind standard topics; owns /clock
  aiur_flight       float_manager, station_keeper, termination, mission_logger
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
  heading/airspeed loop from `flight6dof.FlightController` on the companion.
  That inner loop is in the 6-DoF model but **not yet a ROS node** — it is
  the next piece of work, and the vehicle is not flyable from ROS until it
  exists.

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
someone else. It does not check the fins: the stock plugin models a bare
hull, which is why the comparison runs on a rail — off it, the hull tumbles.
A fin model in Gazebo is open work.

## Known gaps

- No inner-loop (heading/airspeed) ROS node yet; the plant accepts an air
  velocity and applies a first-order lag.
- The plant has no attitude dynamics; the 6-DoF model does, but is not yet
  behind a ROS node.
- Sensor noise, GNSS dropouts and link loss are not injected. The P0 twin's
  fault-injection pattern is the template.
- `robot_localization` is installed but not in the loop; on the vehicle the
  autopilot's EKF is the estimator.
