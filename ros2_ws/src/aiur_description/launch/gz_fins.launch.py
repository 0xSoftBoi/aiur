"""Cross-check the fin model: Gazebo LiftDrag + LighterThanAirDynamics against
the in-repo 6-DoF, open loop, for fin area ratios 0.30, 0.50 and 0.60.

    ros2 launch aiur_description gz_fins.launch.py
    ros2 launch aiur_description gz_fins.launch.py select:=yaw2
    ros2 launch aiur_description gz_fins.launch.py select:=fins050_li-nahon rtf:=5

Prints one GZ_FINS line per case (see docs/strato/gazebo-fins.md).  ``select``
filters by case group (convention, yaw2, pitch2, cruise) or id substring;
``csv_dir`` keeps the Gazebo truth logs for gz_fins_diagnose.py.
"""

import os

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction,
                            RegisterEventHandler, SetEnvironmentVariable)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def script(name: str) -> str:
    """The package's CMakeLists installs only gz_drag_check.py, so fall back
    to the source tree of a standard colcon workspace (install/<pkg> next to
    src/<pkg>), or to $AIUR_DESCRIPTION_SCRIPTS."""

    prefix = get_package_prefix("aiur_description")
    for d in (os.path.join(prefix, "lib", "aiur_description"),
              os.environ.get("AIUR_DESCRIPTION_SCRIPTS", ""),
              os.path.join(prefix, "..", "..", "src", "aiur_description", "scripts")):
        if d and os.path.exists(os.path.join(d, name)):
            return os.path.abspath(os.path.join(d, name))
    raise FileNotFoundError(f"{name}: set AIUR_DESCRIPTION_SCRIPTS to the scripts directory")


def setup(context):
    share = get_package_share_directory("aiur_description")
    worlds = os.path.join(share, "worlds")
    check = ExecuteProcess(
        cmd=["python3", script("gz_fins_check.py"), os.path.join(worlds, "fins", "cases.json"),
             worlds, script("gz_fins_run.py"), LaunchConfiguration("select").perform(context),
             LaunchConfiguration("rtf").perform(context),
             LaunchConfiguration("csv_dir").perform(context)],
        output="screen")
    return [
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", os.path.join(share, "models")),
        Node(package="ros_gz_bridge", executable="parameter_bridge",
             arguments=["/model/aiur/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry"]),
        check,
        RegisterEventHandler(OnProcessExit(target_action=check,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("select", default_value=""),
        DeclareLaunchArgument("rtf", default_value="20"),
        DeclareLaunchArgument("csv_dir", default_value=""),
        OpaqueFunction(function=setup),
    ])
