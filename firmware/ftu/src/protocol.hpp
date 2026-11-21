// FTU LoRa packets: one downlink (telemetry), one uplink (command).
//
// Portable C++17, no heap, no exceptions, no dependency on geofence.hpp: the
// ground station can compile this file alone.
//
// Design constraints
//   - The link is SF10 / 125 kHz / CR 4/5 (hardware.md, "Radio links").  One
//     symbol is 8.192 ms, so every byte matters: the payload symbol count
//     moves in steps of 5 bytes.  Telemetry is held at 24 bytes (371 ms) and
//     the command at 19 bytes (330 ms); see lora_time_on_air_ms().
//   - Fixed length per type, little-endian, no optional fields.  A decoder
//     that has nothing to parse has nothing to get wrong.
//   - Telemetry is not secret and not authenticated: forging it harms nobody
//     in the air.  Commands are authenticated and replay-protected, because a
//     forged or replayed TERMINATE or DISARM is the whole threat.
//
// Telemetry, 24 bytes
//   0      ver_type      high nibble version (1), low nibble type (1)
//   1      vehicle_id
//   2..4   lat           int24, degrees * (2^23 - 1) / 90     (1.2 m)
//   5..7   lon           int24, degrees * (2^23 - 1) / 180    (2.4 m at equator)
//   8..9   gnss_alt      uint16, metres + 1000, saturating    (-1000..64535 m)
//   10..11 baro_alt      uint16, same coding
//   12     status        bits 7..6 Gate now driven (0 none, 1 A, 2 B),
//                        bits 5..4 State, bits 3..0 Reason (geofence.hpp)
//   13     flags         see TelemetryFlag
//   14..15 batt_mv       uint16
//   16..17 flight_2s     uint16, flight clock / 2 s, saturating (36.4 h)
//   18..19 ack           uint16, low half of the last accepted command counter
//   20     boot_pulses   high nibble boot count mod 16, low nibble cutter
//                        pulses started (saturating at 15)
//   21     rx_rejects    uint8, uplinks rejected since boot, saturating
//   22..23 crc16         CRC-16/CCITT-FALSE over bytes 0..21
//
// Command, 19 bytes
//   0      ver_type      high nibble version (1), low nibble type (2)
//   1      vehicle_id
//   2..5   counter       uint32, strictly increasing per vehicle
//   6      cmd           Cmd
//   7..8   arg           uint16 (meaning per Cmd)
//   9..16  mac           SipHash-2-4(key, bytes 0..8), little-endian
//   17..18 crc16         CRC-16/CCITT-FALSE over bytes 0..16
//
// Why a CRC as well as a MAC (and the SX1262's own CRC): it is two bytes, it
// rejects line noise before any keyed work is done, and it lets the reject
// counters tell "corrupted" from "wrong key or forged", which is the first
// thing one wants to know on a range day.
//
// Why SipHash-2-4: it is a keyed PRF designed as a MAC for short messages,
// it is ~40 lines with no tables, and it needs no library on either end.  It
// is not a certified algorithm and a 64-bit tag is short by cryptographic
// standards.  At one guess per 0.33 s of airtime, 2^63 guesses is not the
// weak point of a system whose key sits in flash on a recovered payload.
//
// Replay protection: the receiver stores the highest counter it has accepted
// (in flash, so it survives a reset) and accepts only larger ones.  The
// ground station should derive its counter from UTC seconds: monotonic
// without having to remember anything, and still valid after its laptop is
// replaced on the field.
#pragma once

#include <cstddef>
#include <cstdint>

namespace ftu {
namespace proto {

constexpr uint8_t kVersion = 1;
constexpr uint8_t kTypeTelemetry = 1;
constexpr uint8_t kTypeCommand = 2;
constexpr size_t kTelemetryLen = 24;
constexpr size_t kCommandLen = 19;
constexpr size_t kKeyLen = 16;
constexpr size_t kMacLen = 8;

/// TERMINATE must carry this argument.  It guards against a ground-station
/// bug that sends the wrong command byte, not against an attacker.
constexpr uint16_t kTerminateConfirm = 0x7E4D;

enum class Cmd : uint8_t {
    Ping = 1,       // arg ignored; proves the link, resets the link-loss timer
    Arm = 2,        // arg ignored; force DISARMED -> ARMED
    Disarm = 3,     // arg = seconds to hold off automatic re-arming (capped by the unit)
    Terminate = 4,  // arg must be kTerminateConfirm
};

enum TelemetryFlag : uint8_t {
    kFlagGnssValid = 1u << 0,
    kFlagBaroValid = 1u << 1,
    kFlagHomeSet = 1u << 2,         // ground reference captured
    kFlagHeartbeat = 1u << 3,       // autopilot heartbeat present
    kFlagAltDisagree = 1u << 4,     // GNSS and barometer differ by more than the threshold
    kFlagGnssAirborne = 1u << 5,    // receiver confirmed the airborne <1 g dynamic model
    kFlagDisarmHold = 1u << 6,      // a DISARM hold is running
    kFlagUnderVoltage = 1u << 7,    // cutter sequence stopped on cell voltage
};

struct Telemetry {
    uint8_t vehicle_id = 0;
    double lat_deg = 0.0;
    double lon_deg = 0.0;
    double gnss_alt_m = 0.0;
    double baro_alt_m = 0.0;
    uint8_t gate = 0;    // ftu::Gate
    uint8_t state = 0;   // ftu::State
    uint8_t reason = 0;  // ftu::Reason
    uint8_t flags = 0;
    uint16_t batt_mv = 0;
    double flight_s = 0.0;
    uint16_t ack = 0;
    uint8_t boot_count = 0;  // only the low 4 bits travel
    uint8_t pulses = 0;      // saturates at 15 on the wire
    uint8_t rx_rejects = 0;
};

struct Command {
    uint8_t vehicle_id = 0;
    uint32_t counter = 0;
    Cmd cmd = Cmd::Ping;
    uint16_t arg = 0;
};

enum class Status : uint8_t {
    Ok = 0,
    BadLength,
    BadCrc,
    BadVersion,   // version or packet type
    WrongVehicle,
    BadMac,
    BadCommand,   // unknown command code, or TERMINATE without its confirm word
    Replay,       // counter not greater than the last accepted one
};

uint16_t crc16_ccitt(const uint8_t* data, size_t len);
uint64_t siphash24(const uint8_t key[kKeyLen], const uint8_t* data, size_t len);

/// Returns the number of bytes written, or 0 if `cap` is too small.
size_t encode_telemetry(const Telemetry& t, uint8_t* out, size_t cap);
Status decode_telemetry(const uint8_t* buf, size_t len, Telemetry& out);

size_t encode_command(const Command& c, const uint8_t key[kKeyLen], uint8_t* out, size_t cap);
/// Checks length, CRC, version, vehicle, MAC and command code - in that
/// order - but not the counter.  Use CommandReceiver on the vehicle.
Status decode_command(const uint8_t* buf, size_t len, const uint8_t key[kKeyLen],
                      uint8_t vehicle_id, Command& out);

/// The vehicle side: decode_command() plus the replay window and the reject
/// counters.  `last_counter` is to be loaded from, and saved to, flash.
class CommandReceiver {
public:
    CommandReceiver(const uint8_t key[kKeyLen], uint8_t vehicle_id, uint32_t last_counter);

    /// On Status::Ok, `out` is valid and last_counter() has advanced: store
    /// it before acting on the command.
    Status accept(const uint8_t* buf, size_t len, Command& out);

    uint32_t last_counter() const { return last_counter_; }
    uint8_t rejects() const { return rejects_; }
    uint8_t rejects_crc() const { return rejects_crc_; }
    uint8_t rejects_mac() const { return rejects_mac_; }
    uint8_t rejects_replay() const { return rejects_replay_; }

private:
    uint8_t key_[kKeyLen];
    uint8_t vehicle_id_;
    uint32_t last_counter_;
    uint8_t rejects_ = 0, rejects_crc_ = 0, rejects_mac_ = 0, rejects_replay_ = 0;
};

/// LoRa time on air in milliseconds (Semtech AN1200.13 / SX126x datasheet
/// formula), explicit header.  Low-data-rate optimisation is applied when the
/// symbol exceeds 16 ms, as the SX1262 requires.
double lora_time_on_air_ms(size_t payload_len, unsigned sf = 10, double bw_hz = 125000.0,
                           unsigned cr_denominator = 5, unsigned preamble_symbols = 8,
                           bool crc_on = true);

}  // namespace proto
}  // namespace ftu
