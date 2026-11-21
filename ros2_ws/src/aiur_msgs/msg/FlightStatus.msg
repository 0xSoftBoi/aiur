# Mission-level status published by the float manager.
std_msgs/Header header
string phase                   # aiur.strato.guidance.FlightPhase value
float32 altitude_m
float32 climb_rate_m_s
float32 target_altitude_m
float32 range_from_launch_m
float32 station_error_m
float32 flight_time_s
float32 trim_command           # -1..1 vertical thrust-vector demand
bool station_keeper_saturated
bool terminate_requested
string terminate_reason
