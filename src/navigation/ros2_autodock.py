import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray
from sensor_msgs.msg import BatteryState
from geometry_msgs.msg import Twist

class AuraAutoDockingNode(Node):
    def __init__(self):
        super().__init__('aura_autodocking_node')
        
        # Operational parameters loaded dynamically from configurations architecture
        self.declare_parameter('battery_low_threshold', 20.0)
        self.declare_parameter('linear_forward_speed', 0.1)
        self.declare_parameter('linear_creep_speed', 0.02)
        self.declare_parameter('angular_adjust_speed', 0.2)

        self.low_battery_threshold = self.get_parameter('battery_low_threshold').value
        self.speed_forward = self.get_parameter('linear_forward_speed').value
        self.speed_creep = self.get_parameter('linear_creep_speed').value
        self.speed_angular = self.get_parameter('angular_adjust_speed').value

        # State flags tracking docking phases
        self.is_docking_active = False
        self.is_fully_docked = False

        # ROS 2 Subscribers and Publishers
        self.battery_sub = self.create_subscription(
            BatteryState, '/battery_state', self.battery_callback, 10)
        self.ir_sub = self.create_subscription(
            Int32MultiArray, '/dock_ir_signals', self.ir_signal_callback, 10)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.get_logger().info("🚀 [ROS 2 AUTODOCK] AURA Docking Node initialized and standing by.")

    def battery_callback(self, msg: BatteryState):
        """Monitors charge thresholds. Auto-triggers recovery docking routing."""
        # Check current charge percent against safety criteria limits
        if msg.percentage * 100.0 < self.low_battery_threshold and not self.is_docking_active and not self.is_fully_docked:
            self.get_logger().warn(f"🔋 [LOW BATTERY] Charge hit {msg.percentage * 100.0}%. Commencing homing routine.")
            self.is_docking_active = True
            
        # Detect if docking interface completed successfully via positive current flow
        if msg.current > 0.1 and self.is_docking_active:
            self.get_logger().info("⚡ [CHARGING ENGAGED] Electrical contact confirmed. Shutting down locomotion engines.")
            self.is_docking_active = False
            self.is_fully_docked = True
            self.stop_chassis()

    def ir_signal_callback(self, msg: Int32MultiArray):
        """Processes beacon tracking algorithms if homing operations are engaged"""
        if not self.is_docking_active:
            return

        if len(msg.data) < 3:
            self.get_logger().error("[AUTODOCK ERROR] Incoming IR payload array size is insufficient.")
            return

        left_eye, center_eye, right_eye = msg.data
        move_cmd = Twist()

        # Closed-loop tracking state logic
        if center_eye == 1:
            # Trajectory aligned. Drive directly into dock core.
            move_cmd.linear.x = self.speed_forward
            move_cmd.angular.z = 0.0
            self.get_logger().info("🎯 [TRACKING] Homing locked: Driving forward into trạm sạc.")
        elif left_eye == 1 and right_eye == 0:
            # Beacon skewing left: correct heading by yawing left
            move_cmd.linear.x = self.speed_creep
            move_cmd.angular.z = self.speed_angular
            self.get_logger().info("↩️ [TRACKING] Skewed Right: Adjusting heading Left.")
        elif right_eye == 1 and left_eye == 0:
            # Beacon skewing right: correct heading by yawing right
            move_cmd.linear.x = self.speed_creep
            move_cmd.angular.z = -self.speed_angular
            self.get_logger().info("↪️ [TRACKING] Skewed Left: Adjusting heading Right.")
        else:
            # Signal loss backup behavior: execute broad slow searching arcs
            move_cmd.linear.x = 0.0
            move_cmd.angular.z = 0.1
            self.get_logger().warn("🚨 [TRACKING LOST] Scanning room sector patterns to recapture IR emitter...")

        self.cmd_vel_pub.publish(move_cmd)

    def stop_chassis(self):
        empty_cmd = Twist()
        self.cmd_vel_pub.publish(empty_cmd)

def main(args=None):
    rclpy.init(args=args)
    node = AuraAutoDockingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
