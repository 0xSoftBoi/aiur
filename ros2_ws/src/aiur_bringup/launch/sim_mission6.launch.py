"""Whole mission on the unified plant, through MAVLink.

    ros2 launch aiur_bringup sim_mission6.launch.py design:=S2-dayloiter/hull

unified_plant (buoyancy + 6-DoF + autopilot inner loop) <-MAVLink/UDP-> mavlink_bridge
<-ROS topics-> float_manager, station_keeper, termination, mission_logger.
Fault arguments (seconds of flight, negative = off): gimbal_jam_at_s, motor_fail_at_s.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

DESIGNS = {"S1-touch/hull": (3.0, 5.0), "S2-dayloiter/hull": (6.0, 10.0),
           "SP1-trainer/hull": (3.0, 6.0)}


def setup(context):
    design = LaunchConfiguration("design").perform(context)
    cruise, dash = DESIGNS[design]
    ns, sim = "aiur", {"use_sim_time": True}
    L = LaunchConfiguration
    logger = Node(package="aiur_flight", executable="mission_logger", namespace=ns, output="screen",
                  parameters=[sim, {"output_dir": L("output_dir")}])
    return [
        Node(package="aiur_flight", executable="mavlink_bridge", namespace=ns, output="screen",
             parameters=[sim, {"dash_airspeed_m_s": dash}]),
        Node(package="aiur_strato_sim", executable="unified_plant", namespace=ns, output="screen",
             parameters=[{"design": design, "wind_profile": L("wind_profile"),
                          "wind_scale": L("wind_scale"), "steps_per_tick": L("steps_per_tick"),
                          "gimbal_jam_at_s": L("gimbal_jam_at_s"),
                          "motor_fail_at_s": L("motor_fail_at_s")}]),
        Node(package="aiur_flight", executable="float_manager", namespace=ns, output="screen",
             parameters=[sim, {"vent_enabled": False, "cruise_airspeed_m_s": cruise,
                               "float_duration_s": L("float_duration_s")}]),
        Node(package="aiur_flight", executable="station_keeper", namespace=ns, output="screen",
             parameters=[sim, {"max_airspeed_m_s": cruise, "entry_guidance": True}]),
        Node(package="aiur_flight", executable="termination", namespace=ns, output="screen",
             parameters=[sim, {"max_range_m": L("max_range_m")}]),
        logger,
        RegisterEventHandler(OnProcessExit(target_action=logger,
                                           on_exit=[EmitEvent(event=Shutdown())])),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("design", default_value="S2-dayloiter/hull"),
        DeclareLaunchArgument("wind_profile", default_value="midlat-summer-p50"),
        DeclareLaunchArgument("wind_scale", default_value="1.0"),
        DeclareLaunchArgument("steps_per_tick", default_value="1"),
        DeclareLaunchArgument("float_duration_s", default_value="3600.0"),
        DeclareLaunchArgument("max_range_m", default_value="150000.0"),
        DeclareLaunchArgument("gimbal_jam_at_s", default_value="-1.0"),
        DeclareLaunchArgument("motor_fail_at_s", default_value="-1.0"),
        DeclareLaunchArgument("output_dir", default_value="/tmp/aiur_mission6"),
        OpaqueFunction(function=setup),
    ])
