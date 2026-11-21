"""Station-keeping at float with the full control chain on the 6-DoF plant.

    ros2 launch aiur_bringup sim_float.launch.py wind_east_m_s:=-5.0

station_keeper (outer loop) -> attitude_controller (inner loop) ->
flight_plant (rigid body + added mass + gust gradients).  Exits after
`duration_s` of simulated time with a STATION_REPORT line.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    design = LaunchConfiguration("design").perform(context)
    ns, sim = "aiur", {"use_sim_time": True}
    report = Node(package="aiur_flight", executable="station_report", namespace=ns, output="screen",
                  parameters=[sim, {"duration_s": LaunchConfiguration("duration_s"),
                                    "output": LaunchConfiguration("output")}])
    nodes = [
        Node(package="aiur_strato_sim", executable="flight_plant", namespace=ns, output="screen",
             parameters=[{"design": design,
                          "wind_east_m_s": LaunchConfiguration("wind_east_m_s"),
                          "wind_north_m_s": LaunchConfiguration("wind_north_m_s"),
                          "gust_sigma_m_s": LaunchConfiguration("gust_sigma_m_s")}]),
        Node(package="aiur_flight", executable="attitude_controller", namespace=ns, output="screen",
             parameters=[sim, {"design": design}]),
        Node(package="aiur_flight", executable="station_keeper", namespace=ns, output="screen",
             parameters=[sim, {"always_active": True, "airspeed_lag_s": 5.0,
                               "max_airspeed_m_s": LaunchConfiguration("max_airspeed_m_s")}]),
        report,
        RegisterEventHandler(OnProcessExit(target_action=report,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ]
    urdf = os.path.join(get_package_share_directory("aiur_description"), "urdf",
                        design.replace("/", "_") + ".urdf")
    if os.path.exists(urdf):
        with open(urdf) as fh:
            nodes.append(Node(package="robot_state_publisher", executable="robot_state_publisher",
                              namespace=ns, parameters=[sim, {"robot_description": fh.read()}]))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("design", default_value="S2-dayloiter/hull"),
        DeclareLaunchArgument("wind_east_m_s", default_value="-4.0"),
        DeclareLaunchArgument("wind_north_m_s", default_value="0.0"),
        DeclareLaunchArgument("gust_sigma_m_s", default_value="0.5"),
        DeclareLaunchArgument("max_airspeed_m_s", default_value="6.0"),
        DeclareLaunchArgument("duration_s", default_value="1800.0"),
        DeclareLaunchArgument("output", default_value="/tmp/aiur_station.json"),
        OpaqueFunction(function=setup),
    ])
