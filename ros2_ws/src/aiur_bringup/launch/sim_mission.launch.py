"""Fly one simulated mission, launch to landing, and exit.

    ros2 launch aiur_bringup sim_mission.launch.py design:=S1-touch/hull

The plant owns /clock; every other node runs on simulated time.  The launch
shuts down when the mission logger exits, which it does on landing.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            OpaqueFunction, RegisterEventHandler)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Per-design parameters that are properties of the vehicle, not of the day.
DESIGNS = {
    "S1-touch/hull": {"vent_enabled": False, "max_airspeed_m_s": 3.0},
    "S1-touch/tandem": {"vent_enabled": True, "max_airspeed_m_s": 3.0},
    "S2-dayloiter/hull": {"vent_enabled": False, "max_airspeed_m_s": 6.0},
}


def setup(context):
    design = LaunchConfiguration("design").perform(context)
    d = DESIGNS[design]
    ns = "aiur"
    sim = {"use_sim_time": True}
    out = LaunchConfiguration("output_dir").perform(context)
    urdf = os.path.join(get_package_share_directory("aiur_description"), "urdf",
                        design.replace("/", "_") + ".urdf")
    nodes = [
        Node(package="aiur_strato_sim", executable="plant", namespace=ns, output="screen",
             parameters=[{"design": design,
                          "wind_profile": LaunchConfiguration("wind_profile"),
                          "wind_scale": LaunchConfiguration("wind_scale"),
                          "steps_per_tick": LaunchConfiguration("steps_per_tick")}]),
        Node(package="aiur_flight", executable="float_manager", namespace=ns, output="screen",
             parameters=[sim, {"vent_enabled": d["vent_enabled"],
                               "float_duration_s": LaunchConfiguration("float_duration_s")}]),
        Node(package="aiur_flight", executable="station_keeper", namespace=ns, output="screen",
             parameters=[sim, {"max_airspeed_m_s": d["max_airspeed_m_s"]}]),
        Node(package="aiur_flight", executable="termination", namespace=ns, output="screen",
             parameters=[sim, {"max_range_m": LaunchConfiguration("max_range_m")}]),
    ]
    logger = Node(package="aiur_flight", executable="mission_logger", namespace=ns,
                  output="screen", parameters=[sim, {"output_dir": out}])
    nodes.append(logger)
    nodes.append(RegisterEventHandler(OnProcessExit(
        target_action=logger, on_exit=[EmitEvent(event=Shutdown(reason="mission complete"))])))
    if os.path.exists(urdf):
        with open(urdf) as fh:
            nodes.append(Node(package="robot_state_publisher", executable="robot_state_publisher",
                              namespace=ns, parameters=[sim, {"robot_description": fh.read()}]))
    nodes.append(ExecuteProcess(
        cmd=["ros2", "bag", "record", "-s", "mcap", "-o", os.path.join(out, "bag"),
             "/aiur/odom", "/aiur/status", "/aiur/buoyancy", "/aiur/battery", "/aiur/gps/fix",
             "/aiur/cmd/float", "/aiur/cmd/air_velocity", "/aiur/cmd/terminate",
             "/aiur/wind/estimate", "/aiur/wind/truth"],
        condition=IfCondition(LaunchConfiguration("record")), output="log"))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("design", default_value="S1-touch/hull"),
        DeclareLaunchArgument("wind_profile", default_value="midlat-summer-p50"),
        DeclareLaunchArgument("wind_scale", default_value="1.0"),
        DeclareLaunchArgument("steps_per_tick", default_value="2"),
        DeclareLaunchArgument("float_duration_s", default_value="3600.0"),
        DeclareLaunchArgument("max_range_m", default_value="150000.0"),
        DeclareLaunchArgument("output_dir", default_value="/tmp/aiur_mission"),
        DeclareLaunchArgument("record", default_value="false"),
        OpaqueFunction(function=setup),
    ])
