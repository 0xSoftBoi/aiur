# Stern propulsor demand, as sent over DroneCAN to the pod node.
std_msgs/Header header
float32 thrust_n
float32 gimbal_yaw_rad      # positive pushes the stern to starboard
float32 gimbal_pitch_rad    # positive pushes the stern down
