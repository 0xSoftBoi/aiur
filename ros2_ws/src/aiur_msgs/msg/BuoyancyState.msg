# Lift-cell state.  On the vehicle this is assembled from the gas RTD, the
# hull differential-pressure sensor and the ballast/valve actuator states.
std_msgs/Header header
float32 gas_mass_kg            # estimate; truth in simulation
float32 gas_temperature_k
float32 ambient_temperature_k
float32 supertemperature_k     # gas minus ambient
float32 fill_fraction          # 0..1 of full cell volume
float32 superpressure_pa
float32 ballast_remaining_kg
bool vent_open
bool burst
