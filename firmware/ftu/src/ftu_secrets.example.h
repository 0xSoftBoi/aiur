// Copy to ftu_secrets.h (git-ignored) and fill in.  One key per vehicle.
//
// The key authenticates uplink commands (protocol.hpp).  Anyone who has it can
// terminate or disarm the vehicle, and it sits in flash on a payload that may
// be found by a stranger: generate a new one for every flight article, e.g.
//   python3 -c "import secrets; print(', '.join(f'0x{b:02x}' for b in secrets.token_bytes(16)))"
#pragma once

#define FTU_VEHICLE_ID 1
#define FTU_PSK {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
