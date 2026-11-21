"""Cross-check the in-repo flight model against Gazebo's stock LTA physics.

    ros2 launch aiur_description gz_check.launch.py design:=S2-dayloiter/hull

Runs Gazebo headless with the generated model on a rail, bridges its odometry
into ROS, and prints one GZ_CHECK line comparing terminal airspeed and
initial acceleration with what the sizing model expects.
"""

import json
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction,
                            RegisterEventHandler, SetEnvironmentVariable)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    share = get_package_share_directory("aiur_description")
    design = LaunchConfiguration("design").perform(context)
    name = design.replace("/", "_")
    with open(os.path.join(share, "worlds", "expectations.json")) as fh:
        expect = json.load(fh)[design]
    check = Node(package="aiur_description", executable="gz_drag_check.py", output="screen",
                 arguments=[json.dumps(expect), "890"])
    return [
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", os.path.join(share, "models")),
        Node(package="ros_gz_bridge", executable="parameter_bridge",
             arguments=["/model/aiur/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry"]),
        ExecuteProcess(cmd=["gz", "sim", "-s", "-r", "--iterations", "90000",
                            os.path.join(share, "worlds", name + "_rail.sdf")], output="log"),
        check,
        RegisterEventHandler(OnProcessExit(target_action=check,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("design", default_value="S2-dayloiter/hull"),
        OpaqueFunction(function=setup),
    ])
