"""ROS station-keeping chain flying the real ArduRover firmware in SITL.

    ros2 launch aiur_bringup sitl_ardupilot.launch.py                      # 4 m/s wind, station 1.5 km upwind
    ros2 launch aiur_bringup sitl_ardupilot.launch.py gust:=0.5 inner:=1 use_airspeed:=true

    json_plant.py (aiur.strato.flight6dof) <-UDP JSON-> ardurover SITL <-MAVLink/TCP-> mavlink_bridge
    (autopilot:=ardurover) <-ROS topics-> station_keeper -> cmd/air_velocity; station_report ends the run.

sitl/ardupilot/run_sitl.sh in `idle` mode starts the plant and ArduRover
(and downloads the SITL binary on first use; set ARDUROVER / SITL_HOME to
override, as for that script).  The bridge waits for GPS + EKF, sets GUIDED
and arms; at `activate_after_s` of autopilot time it starts publishing
odometry, which is what starts station_keeper.  The map origin is the
station: at activation the vehicle is at (start_east_m, start_north_m).

Time.  Nothing here uses the ROS clock for control: stamps are ArduPilot's
time_boot_ms (simulated time), station_keeper takes dt from odometry
stamps, the bridge sends one setpoint per GLOBAL_POSITION_INT, and
station_report counts simulated seconds.  So use_sim_time is left off, no
/clock is published, and SITL runs lock-stepped as fast as the plant goes
(about 15x real time); the only wall-clock quantity is the companion's
reaction latency, a few milliseconds against a 200 ms telemetry period.

Each launch needs its own ROS_DOMAIN_ID and `instance` to run in parallel.
"""

import os
import pathlib

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction,
                            RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def find_run_sitl() -> str:
    """sitl/ardupilot/run_sitl.sh lives in the repository, not in the ROS
    install tree: look upward from this file, then next to the aiur package."""

    here = pathlib.Path(__file__).resolve()
    roots = list(here.parents)
    try:
        import aiur
        roots.append(pathlib.Path(aiur.__file__).resolve().parents[1])
    except ImportError:
        pass
    if os.environ.get("AIUR_ROOT"):
        roots.insert(0, pathlib.Path(os.environ["AIUR_ROOT"]))
    for root in roots:
        cand = root / "sitl" / "ardupilot" / "run_sitl.sh"
        if cand.exists():
            return str(cand)
    raise FileNotFoundError("sitl/ardupilot/run_sitl.sh not found; set AIUR_ROOT to the repository")


def setup(context):
    L = lambda name: LaunchConfiguration(name).perform(context)  # noqa: E731
    inst = int(L("instance"))
    tag = L("tag")
    env = dict(os.environ)
    env.update({"INSTANCE": str(inst), "TAG": tag, "WIND_N": L("wind_north"), "WIND_E": L("wind_east"),
                "GUST": L("gust"), "INNER": L("inner"), "LUA": L("pitch_script"),
                "WIND_START": L("wind_start_s"), "WIND_RAMP": L("wind_ramp_s"),
                "SPEEDUP": L("speedup")})
    sitl = ExecuteProcess(cmd=[find_run_sitl(), "idle"], env=env, output="screen",
                          sigterm_timeout="3", sigkill_timeout="3")
    ns = "aiur"
    cruise, dash = float(L("max_airspeed")), float(L("dash_airspeed"))
    report = Node(package="aiur_flight", executable="station_report", namespace=ns, output="screen",
                  parameters=[{"duration_s": float(L("duration_s")), "relative_time": True, "report_wind": True,
                               "output": L("output")}])
    return [
        sitl,
        Node(package="aiur_flight", executable="mavlink_bridge", namespace=ns, output="screen",
             parameters=[{"autopilot": "ardurover",
                          "mavlink_url": f"tcp:127.0.0.1:{5760 + 10 * inst}",
                          "dash_airspeed_m_s": dash,
                          "activate_after_s": float(L("activate_after_s")),
                          "start_offset_east_m": float(L("start_east_m")),
                          "start_offset_north_m": float(L("start_north_m"))}]),
        Node(package="aiur_flight", executable="station_keeper", namespace=ns, output="screen",
             parameters=[{"max_airspeed_m_s": cruise, "always_active": True,
                          "use_airspeed": L("use_airspeed").lower() in ("1", "true", "yes")}]),
        report,
        RegisterEventHandler(OnProcessExit(target_action=report, on_exit=[EmitEvent(event=Shutdown())])),
    ]


def generate_launch_description():
    A = DeclareLaunchArgument
    return LaunchDescription([
        A("wind_east", default_value="-4.0", description="plant wind, east component (m/s, blowing TO)"),
        A("wind_north", default_value="0.0"),
        A("gust", default_value="0.0", description="plant gust sigma, m/s"),
        A("wind_start_s", default_value="60"), A("wind_ramp_s", default_value="30"),
        A("inner", default_value="0", description="1 = aiur_inner.lua thrust-floor inner loop"),
        A("pitch_script", default_value="1", description="1 = aiur_pitch.lua"),
        A("use_airspeed", default_value="false",
          description="station_keeper wind estimate from measured airspeed (needs inner:=1)"),
        A("start_east_m", default_value="-1500.0", description="vehicle position at activation; station = origin"),
        A("start_north_m", default_value="0.0"),
        A("activate_after_s", default_value="100.0"),
        A("duration_s", default_value="1800.0"),
        A("max_airspeed", default_value="6.0"), A("dash_airspeed", default_value="10.0"),
        A("speedup", default_value="20"),
        A("instance", default_value="0"), A("tag", default_value="ros"),
        A("output", default_value="/tmp/aiur_station_ardupilot.json"),
        OpaqueFunction(function=setup),
    ])
