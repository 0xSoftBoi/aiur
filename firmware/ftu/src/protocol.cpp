#include "protocol.hpp"

#include <cmath>

namespace ftu {
namespace proto {

namespace {

void put16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v);
    p[1] = static_cast<uint8_t>(v >> 8);
}
uint16_t get16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0] | (static_cast<uint16_t>(p[1]) << 8));
}
void put24(uint8_t* p, int32_t v) {
    const uint32_t u = static_cast<uint32_t>(v);
    p[0] = static_cast<uint8_t>(u);
    p[1] = static_cast<uint8_t>(u >> 8);
    p[2] = static_cast<uint8_t>(u >> 16);
}
int32_t get24(const uint8_t* p) {
    uint32_t u = p[0] | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16);
    if (u & 0x800000u) u |= 0xFF000000u;  // sign-extend
    return static_cast<int32_t>(u);
}
void put32(uint8_t* p, uint32_t v) {
    for (int i = 0; i < 4; ++i) p[i] = static_cast<uint8_t>(v >> (8 * i));
}
uint32_t get32(const uint8_t* p) {
    uint32_t v = 0;
    for (int i = 0; i < 4; ++i) v |= static_cast<uint32_t>(p[i]) << (8 * i);
    return v;
}

const int32_t kScale24 = 8388607;  // 2^23 - 1

/// Clamp, scale and round an angle; NaN encodes as 0.
int32_t angle_to_i24(double deg, double full_scale_deg) {
    if (!(deg == deg)) return 0;
    if (deg > full_scale_deg) deg = full_scale_deg;
    if (deg < -full_scale_deg) deg = -full_scale_deg;
    return static_cast<int32_t>(std::lround(deg * kScale24 / full_scale_deg));
}

uint16_t alt_to_u16(double m) {
    if (!(m == m)) return 0;  // NaN
    const double v = m + 1000.0;
    if (v <= 0.0) return 0;
    if (v >= 65535.0) return 65535;
    return static_cast<uint16_t>(std::lround(v));
}

bool valid_cmd(uint8_t c) {
    return c >= static_cast<uint8_t>(Cmd::Ping) && c <= static_cast<uint8_t>(Cmd::Terminate);
}

void bump(uint8_t& counter) {
    if (counter < 255) ++counter;
}

inline uint64_t rotl(uint64_t x, int b) { return (x << b) | (x >> (64 - b)); }

}  // namespace

uint16_t crc16_ccitt(const uint8_t* data, size_t len) {
    // CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final
    // xor.  Check value for "123456789" is 0x29B1 (tested on the host).
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc = static_cast<uint16_t>(crc ^ (static_cast<uint16_t>(data[i]) << 8));
        for (int b = 0; b < 8; ++b) {
            crc = (crc & 0x8000u) ? static_cast<uint16_t>((crc << 1) ^ 0x1021u)
                                  : static_cast<uint16_t>(crc << 1);
        }
    }
    return crc;
}

uint64_t siphash24(const uint8_t key[kKeyLen], const uint8_t* data, size_t len) {
    // SipHash-2-4, Aumasson & Bernstein 2012.  Checked on the host against
    // the reference vectors from the paper's test file.
    uint64_t k0 = 0, k1 = 0;
    for (int i = 0; i < 8; ++i) {
        k0 |= static_cast<uint64_t>(key[i]) << (8 * i);
        k1 |= static_cast<uint64_t>(key[8 + i]) << (8 * i);
    }
    uint64_t v0 = 0x736f6d6570736575ULL ^ k0;
    uint64_t v1 = 0x646f72616e646f6dULL ^ k1;
    uint64_t v2 = 0x6c7967656e657261ULL ^ k0;
    uint64_t v3 = 0x7465646279746573ULL ^ k1;

    auto round = [&]() {
        v0 += v1; v1 = rotl(v1, 13); v1 ^= v0; v0 = rotl(v0, 32);
        v2 += v3; v3 = rotl(v3, 16); v3 ^= v2;
        v0 += v3; v3 = rotl(v3, 21); v3 ^= v0;
        v2 += v1; v1 = rotl(v1, 17); v1 ^= v2; v2 = rotl(v2, 32);
    };

    const size_t blocks = len / 8;
    for (size_t b = 0; b < blocks; ++b) {
        uint64_t m = 0;
        for (int i = 0; i < 8; ++i) m |= static_cast<uint64_t>(data[8 * b + i]) << (8 * i);
        v3 ^= m;
        round(); round();
        v0 ^= m;
    }
    uint64_t last = static_cast<uint64_t>(len & 0xFF) << 56;
    for (size_t i = 0; i < (len & 7u); ++i) {
        last |= static_cast<uint64_t>(data[8 * blocks + i]) << (8 * i);
    }
    v3 ^= last;
    round(); round();
    v0 ^= last;
    v2 ^= 0xFF;
    round(); round(); round(); round();
    return v0 ^ v1 ^ v2 ^ v3;
}

size_t encode_telemetry(const Telemetry& t, uint8_t* out, size_t cap) {
    if (cap < kTelemetryLen) return 0;
    out[0] = static_cast<uint8_t>((kVersion << 4) | kTypeTelemetry);
    out[1] = t.vehicle_id;
    put24(out + 2, angle_to_i24(t.lat_deg, 90.0));
    put24(out + 5, angle_to_i24(t.lon_deg, 180.0));
    put16(out + 8, alt_to_u16(t.gnss_alt_m));
    put16(out + 10, alt_to_u16(t.baro_alt_m));
    out[12] = static_cast<uint8_t>(((t.gate & 0x03) << 6) | ((t.state & 0x03) << 4) | (t.reason & 0x0F));
    out[13] = t.flags;
    put16(out + 14, t.batt_mv);
    double f2 = t.flight_s / 2.0;
    if (!(f2 > 0.0)) f2 = 0.0;
    if (f2 > 65535.0) f2 = 65535.0;
    put16(out + 16, static_cast<uint16_t>(f2));
    put16(out + 18, t.ack);
    const uint8_t pulses = t.pulses > 15 ? 15 : t.pulses;
    out[20] = static_cast<uint8_t>(((t.boot_count & 0x0F) << 4) | pulses);
    out[21] = t.rx_rejects;
    put16(out + 22, crc16_ccitt(out, kTelemetryLen - 2));
    return kTelemetryLen;
}

Status decode_telemetry(const uint8_t* buf, size_t len, Telemetry& out) {
    if (len != kTelemetryLen) return Status::BadLength;
    if (crc16_ccitt(buf, kTelemetryLen - 2) != get16(buf + 22)) return Status::BadCrc;
    if (buf[0] != static_cast<uint8_t>((kVersion << 4) | kTypeTelemetry)) return Status::BadVersion;
    out.vehicle_id = buf[1];
    out.lat_deg = static_cast<double>(get24(buf + 2)) * 90.0 / kScale24;
    out.lon_deg = static_cast<double>(get24(buf + 5)) * 180.0 / kScale24;
    out.gnss_alt_m = static_cast<double>(get16(buf + 8)) - 1000.0;
    out.baro_alt_m = static_cast<double>(get16(buf + 10)) - 1000.0;
    out.gate = static_cast<uint8_t>(buf[12] >> 6);
    out.state = static_cast<uint8_t>((buf[12] >> 4) & 0x03);
    out.reason = static_cast<uint8_t>(buf[12] & 0x0F);
    out.flags = buf[13];
    out.batt_mv = get16(buf + 14);
    out.flight_s = static_cast<double>(get16(buf + 16)) * 2.0;
    out.ack = get16(buf + 18);
    out.boot_count = static_cast<uint8_t>(buf[20] >> 4);
    out.pulses = static_cast<uint8_t>(buf[20] & 0x0F);
    out.rx_rejects = buf[21];
    return Status::Ok;
}

size_t encode_command(const Command& c, const uint8_t key[kKeyLen], uint8_t* out, size_t cap) {
    if (cap < kCommandLen) return 0;
    out[0] = static_cast<uint8_t>((kVersion << 4) | kTypeCommand);
    out[1] = c.vehicle_id;
    put32(out + 2, c.counter);
    out[6] = static_cast<uint8_t>(c.cmd);
    put16(out + 7, c.arg);
    // The MAC covers everything before it: version, type, vehicle, counter,
    // command and argument.  Nothing that changes the meaning is outside it.
    const uint64_t mac = siphash24(key, out, 9);
    for (int i = 0; i < 8; ++i) out[9 + i] = static_cast<uint8_t>(mac >> (8 * i));
    put16(out + 17, crc16_ccitt(out, kCommandLen - 2));
    return kCommandLen;
}

Status decode_command(const uint8_t* buf, size_t len, const uint8_t key[kKeyLen],
                      uint8_t vehicle_id, Command& out) {
    if (len != kCommandLen) return Status::BadLength;
    if (crc16_ccitt(buf, kCommandLen - 2) != get16(buf + 17)) return Status::BadCrc;
    if (buf[0] != static_cast<uint8_t>((kVersion << 4) | kTypeCommand)) return Status::BadVersion;
    if (buf[1] != vehicle_id) return Status::WrongVehicle;
    const uint64_t mac = siphash24(key, buf, 9);
    // Constant-time comparison: accumulate differences, branch once.
    uint8_t diff = 0;
    for (int i = 0; i < 8; ++i) diff |= static_cast<uint8_t>(buf[9 + i] ^ static_cast<uint8_t>(mac >> (8 * i)));
    if (diff != 0) return Status::BadMac;
    // Only now is the content trusted enough to interpret.
    if (!valid_cmd(buf[6])) return Status::BadCommand;
    const uint16_t arg = get16(buf + 7);
    if (buf[6] == static_cast<uint8_t>(Cmd::Terminate) && arg != kTerminateConfirm) {
        return Status::BadCommand;
    }
    out.vehicle_id = buf[1];
    out.counter = get32(buf + 2);
    out.cmd = static_cast<Cmd>(buf[6]);
    out.arg = arg;
    return Status::Ok;
}

CommandReceiver::CommandReceiver(const uint8_t key[kKeyLen], uint8_t vehicle_id,
                                 uint32_t last_counter)
    : vehicle_id_(vehicle_id), last_counter_(last_counter) {
    for (size_t i = 0; i < kKeyLen; ++i) key_[i] = key[i];
}

Status CommandReceiver::accept(const uint8_t* buf, size_t len, Command& out) {
    Command c;
    Status st = decode_command(buf, len, key_, vehicle_id_, c);
    // The counter is compared only after the MAC has passed, and advanced
    // only on acceptance: an unauthenticated packet can neither be replayed
    // nor used to push the window forward and lock the real operator out.
    if (st == Status::Ok && c.counter <= last_counter_) st = Status::Replay;
    if (st != Status::Ok) {
        // A packet for another vehicle on the same channel is not an attack
        // and not an error; do not let it fill the reject counter.
        if (st != Status::WrongVehicle) bump(rejects_);
        if (st == Status::BadCrc || st == Status::BadLength) bump(rejects_crc_);
        if (st == Status::BadMac) bump(rejects_mac_);
        if (st == Status::Replay) bump(rejects_replay_);
        return st;
    }
    last_counter_ = c.counter;
    out = c;
    return Status::Ok;
}

double lora_time_on_air_ms(size_t payload_len, unsigned sf, double bw_hz, unsigned cr_denominator,
                           unsigned preamble_symbols, bool crc_on) {
    const double t_sym_ms = 1000.0 * static_cast<double>(1u << sf) / bw_hz;
    const int de = t_sym_ms > 16.0 ? 1 : 0;
    const double num = 8.0 * static_cast<double>(payload_len) - 4.0 * sf + 28.0 +
                       (crc_on ? 16.0 : 0.0);  // explicit header: no -20 term
    const double den = 4.0 * (static_cast<double>(sf) - 2.0 * de);
    double n = std::ceil(num / den) * static_cast<double>(cr_denominator);
    if (n < 0.0) n = 0.0;
    const double payload_symbols = 8.0 + n;
    return (static_cast<double>(preamble_symbols) + 4.25 + payload_symbols) * t_sym_ms;
}

}  // namespace proto
}  // namespace ftu
