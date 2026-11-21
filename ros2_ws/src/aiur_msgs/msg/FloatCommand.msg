# Buoyancy actuation and the pitch setpoint that goes with it.
std_msgs/Header header
bool vent_open
float32 ballast_rate_kg_s
float32 trim                   # -1..1, altitude-hold demand
float32 pitch_cmd_rad          # pitch setpoint for the autopilot, nose up positive
