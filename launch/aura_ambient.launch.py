import os
import json
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # Locate configuration profiles inside root workspaces directory paths
    # (Adjust logic or hardcode paths based on your workspace setup)
    config_file_path = os.path.join(os.getcwd(), 'config', 'system_config.json')
    
    # Pre-parse parameter arrays to cleanly propagate settings down to isolated ROS 2 nodes
    with open(config_file_path, 'r') as file:
        cfg = json.load(file)
        
    dock_cfg = cfg["ros2_navigation_docking"]

    # 1. Define the Central Ambient Vision/Radar AI Engine Node
    ambient_hub_node = Node(
        package='aura_health_ambient', # Replace with your local package identifier if using a workspace setup
        executable='main_hub.py',
        name='aura_main_hub',
        output='screen',
        parameters=[{
            'config_path': config_file_path
        }]
    )

    # 2. Define the Closed-Loop Autonomous Docking Kinematics Node
    autodock_node = Node(
        package='aura_health_ambient',
        executable='ros2_autodock.py',
        name='aura_autodock_manager',
        output='screen',
        parameters=[{
            'battery_low_threshold': float(dock_cfg["battery_low_threshold_percent"]),
            'linear_forward_speed': float(dock_cfg["docking_speeds"]["linear_forward_meas_mps"]),
            'linear_creep_speed': float(dock_cfg["docking_speeds"]["linear_creep_mps"]),
            'angular_adjust_speed': float(dock_cfg["docking_speeds"]["angular_adjust_radps"]),
            'cmd_vel_topic': str(dock_cfg["cmd_vel_topic"]),
            'ir_signals_topic': str(dock_cfg["ir_signals_topic"])
        }]
    )

    # Combine nodes inside the LaunchDescription array to force parallel deployment threads
    return LaunchDescription([
        ambient_hub_node,
        autodock_node
    ])
