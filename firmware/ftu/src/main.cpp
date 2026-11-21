// FTU glue for a LilyGO T-Beam Supreme class board (ESP32-S3, SX1262, u-blox
// M10) with an external MS5611, two cutter gates and an opto heartbeat input.
//
// Everything that decides anything is in geofence.cpp and protocol.cpp, which
// are tested on the host.  This file only moves bytes: sensors -> Sample,
// radio -> Command, Outputs -> two GPIOs, Persist -> NVS.  Keep it that way;
// logic added here is logic that no test sees.
//
// STATUS: this file has been compiled (see docs/strato/ftu.md for the exact
// build) but has NEVER run on hardware.  Pin numbers, PMU rail assignments,
// the TCXO voltage and the GNSS baud rate are from memory of the board family
// and must be checked against the schematic of the board revision in hand.
#include <Arduino.h>
#include <Preferences.h>
#include <SPI.h>
#include <Wire.h>

#include <RadioLib.h>
#include <SparkFun_u-blox_GNSS_v3.h>
#include <esp_idf_version.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>

#include "geofence.hpp"
#include "protocol.hpp"

#ifndef FTU_HAS_AXP2101
#define FTU_HAS_AXP2101 1
#endif
#if FTU_HAS_AXP2101
#define XPOWERS_CHIP_AXP2101
#include <XPowersLib.h>
#endif

#if __has_include("ftu_secrets.h")
#include "ftu_secrets.h"  // defines FTU_VEHICLE_ID and FTU_PSK; not in the repository
#elif defined(FTU_REQUIRE_KEY) && FTU_REQUIRE_KEY
// The flight environment refuses to build without a private key: with the
// development key below, anyone who has read this repository can DISARM or
// TERMINATE the vehicle.
#error "ftu_secrets.h not found (copy src/ftu_secrets.example.h). The flight build needs a private key."
#else
#warning "ftu_secrets.h not found: building with the PUBLIC development key. Bench only."
#define FTU_VEHICLE_ID 1
#define FTU_PSK {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f}
#define FTU_DEVELOPMENT_KEY 1
#endif

// ---------------------------------------------------------------------------
// Pins.  *** VERIFY EVERY ONE AGAINST THE BOARD REVISION BEFORE POWERING A
// CUTTER. ***  "board" = fixed by the T-Beam Supreme PCB (taken from the
// vendor pin map as remembered, unverified here).  "harness" = our choice of
// a free header pin; whether these GPIOs are actually broken out on the
// Supreme's headers is NOT verified.
// ---------------------------------------------------------------------------
namespace pin {
// board: SX1262
constexpr int kLoraSck = 12, kLoraMiso = 13, kLoraMosi = 11, kLoraCs = 10;
constexpr int kLoraRst = 5, kLoraDio1 = 1, kLoraBusy = 4;
// board: GNSS UART (names from the ESP32 side)
constexpr int kGnssRx = 9, kGnssTx = 8;
// board: sensor I2C bus (also carries the on-board OLED/magnetometer/BME280)
constexpr int kI2cSda = 17, kI2cScl = 18;
// board: PMU I2C bus (AXP2101)
constexpr int kPmuSda = 42, kPmuScl = 41;
// board: BOOT button, active low
constexpr int kButton = 0;
// harness: CUT_A_GATE / CUT_B_GATE.  Not strapping pins (0, 3, 45, 46): a
// strapping pin has a defined level at reset that is not ours to choose.
// Each MOSFET needs its own gate pull-down (10 k) on the FTU side: during
// reset and boot these pins are high-impedance.
constexpr int kCutA = 15, kCutB = 16;
// harness: HEARTBEAT, opto-transistor to ground, internal pull-up
constexpr int kHeartbeat = 21;
// harness: FTU_RAW through a divider to an ADC1 pin.  NOT IN THE NETLIST
// (connections.csv has no such net): see docs/strato/ftu.md.
constexpr int kVbatSense = 2;
}  // namespace pin

// FTU_RAW divider: 100 k over 47 k puts 5.4 V at 1.73 V on the pin.
constexpr float kVbatDivider = (100.0f + 47.0f) / 47.0f;

#ifndef FTU_FREQ_MHZ
#define FTU_FREQ_MHZ 869.525  // EU 869.40-869.65 MHz: 500 mW ERP, 10 % duty.  Site-specific.
#endif
#ifndef FTU_TCXO_V
#define FTU_TCXO_V 1.8  // unverified for this module
#endif
#ifndef FTU_GNSS_BAUD
#define FTU_GNSS_BAUD 9600  // u-blox factory default; the board vendor may ship another
#endif
#ifndef FTU_DEBUG_SERIAL
#define FTU_DEBUG_SERIAL 0
#endif

// Native-USB serial can stall for ~100 ms per write with no host attached,
// which in flight is always.  Logging is therefore compiled out of the flight
// build rather than left to time out inside the 10 Hz loop.
#if FTU_DEBUG_SERIAL
#define LOG(...) Serial.printf(__VA_ARGS__)
#else
#define LOG(...) do { } while (0)
#endif

using ftu::Gate;
using ftu::State;
namespace proto = ftu::proto;

namespace {

const uint8_t kKey[proto::kKeyLen] = FTU_PSK;

constexpr uint32_t kStepMs = 100;            // decision rate, 10 Hz
constexpr uint32_t kWatchdogS = 8;
constexpr uint32_t kTelemetryMs = 30000;     // 370.7 ms on air -> 1.24 % duty
constexpr uint32_t kTelemetryTermMs = 10000; // after termination -> 3.71 % duty
constexpr uint32_t kSensorStaleMs = 3000;
constexpr uint32_t kStoredMagic = 0x46545531;  // "FTU1": bump on any Persist layout change

ftu::Config g_cfg;  // flight defaults; edit in geofence.hpp, where the tests see them
ftu::Ftu g_ftu(g_cfg);
Preferences g_nvs;
proto::CommandReceiver* g_rx = nullptr;  // points at a static in setup(); no heap
uint8_t g_boot_count = 0;

SX1262 g_radio = new Module(pin::kLoraCs, pin::kLoraDio1, pin::kLoraRst, pin::kLoraBusy);
bool g_radio_ok = false;
bool g_tx_active = false;
uint64_t g_tx_start_ms = 0;
uint64_t g_radio_retry_ms = 0;
volatile bool g_dio1 = false;

SFE_UBLOX_GNSS_SERIAL g_gnss;
bool g_gnss_ok = false;
bool g_gnss_airborne = false;
uint64_t g_gnss_retry_ms = 0;
uint64_t g_fix_ms = 0;
bool g_fix_valid = false;
double g_lat = 0.0, g_lon = 0.0, g_gnss_alt = 0.0;

uint16_t g_prom[8] = {0};
bool g_baro_present = false;
enum class BaroPhase : uint8_t { Idle, WaitD1, WaitD2 };
BaroPhase g_baro_phase = BaroPhase::Idle;
uint64_t g_baro_phase_ms = 0;
uint32_t g_baro_d1 = 0;
uint64_t g_baro_ms = 0;
bool g_baro_valid = false;
double g_baro_alt = 0.0;

volatile uint32_t g_hb_edges = 0;

uint64_t g_next_step_ms = 0;
uint64_t g_next_tele_ms = 0;
bool g_tele_now = false;

#if FTU_HAS_AXP2101
XPowersPMU g_pmu;
#endif

uint64_t now_ms() { return static_cast<uint64_t>(esp_timer_get_time() / 1000); }

void IRAM_ATTR on_dio1() { g_dio1 = true; }
void IRAM_ATTR on_heartbeat() { g_hb_edges = g_hb_edges + 1; }

// ---------------------------------------------------------------------------
// Gates
// ---------------------------------------------------------------------------

/// Break before make.  ftu::Gate cannot express "both"; this keeps the pins
/// from overlapping for the microseconds between two writes as well.
void apply_gate(Gate g) {
    if (g != Gate::A) digitalWrite(pin::kCutA, LOW);
    if (g != Gate::B) digitalWrite(pin::kCutB, LOW);
    if (g == Gate::A) digitalWrite(pin::kCutA, HIGH);
    if (g == Gate::B) digitalWrite(pin::kCutB, HIGH);
}

// ---------------------------------------------------------------------------
// Persistent state
// ---------------------------------------------------------------------------

struct Stored {
    uint32_t magic;
    ftu::Persist p;
};

void save_state() {
    Stored s{kStoredMagic, g_ftu.persist()};
    g_nvs.putBytes("st", &s, sizeof s);
}

void load_state() {
    Stored s;
    if (g_nvs.getBytesLength("st") == sizeof s && g_nvs.getBytes("st", &s, sizeof s) == sizeof s &&
        s.magic == kStoredMagic) {
        g_ftu.restore(s.p);
    }
}

// ---------------------------------------------------------------------------
// MS5611 (I2C 0x77).  Non-blocking: one conversion is ~9 ms at OSR 4096 and
// the loop must not wait for it.
// ---------------------------------------------------------------------------

constexpr uint8_t kMsAddr = 0x77;

bool ms_cmd(uint8_t cmd) {
    Wire.beginTransmission(kMsAddr);
    Wire.write(cmd);
    return Wire.endTransmission() == 0;
}

bool ms_read(uint8_t cmd, uint8_t* buf, uint8_t n) {
    if (!ms_cmd(cmd)) return false;
    if (Wire.requestFrom(kMsAddr, n) != n) return false;
    for (uint8_t i = 0; i < n; ++i) buf[i] = static_cast<uint8_t>(Wire.read());
    return true;
}

bool ms_begin() {
    if (!ms_cmd(0x1E)) return false;  // reset; reloads the PROM into the ASIC
    delay(4);
    for (uint8_t i = 0; i < 8; ++i) {
        uint8_t b[2];
        if (!ms_read(static_cast<uint8_t>(0xA0 + 2 * i), b, 2)) return false;
        g_prom[i] = static_cast<uint16_t>((b[0] << 8) | b[1]);
    }
    return true;
}

void baro_service(uint64_t now) {
    if (!g_baro_present) {
        // Retry once a second: the sensor is on a soldered pigtail and this
        // unit runs for 16 h in the cold.
        if (now - g_baro_phase_ms >= 1000) {
            g_baro_phase_ms = now;
            g_baro_present = ms_begin();
        }
        return;
    }
    uint8_t b[3];
    switch (g_baro_phase) {
        case BaroPhase::Idle:
            if (now - g_baro_phase_ms >= 400) {
                g_baro_phase = ms_cmd(0x48) ? BaroPhase::WaitD1 : BaroPhase::Idle;  // D1, OSR 4096
                g_baro_phase_ms = now;
                if (g_baro_phase == BaroPhase::Idle) g_baro_present = false;
            }
            break;
        case BaroPhase::WaitD1:
            if (now - g_baro_phase_ms >= 12) {
                if (ms_read(0x00, b, 3) && ms_cmd(0x58)) {  // read ADC, start D2
                    g_baro_d1 = (static_cast<uint32_t>(b[0]) << 16) | (static_cast<uint32_t>(b[1]) << 8) | b[2];
                    g_baro_phase = BaroPhase::WaitD2;
                } else {
                    g_baro_phase = BaroPhase::Idle;
                    g_baro_present = false;
                }
                g_baro_phase_ms = now;
            }
            break;
        case BaroPhase::WaitD2:
            if (now - g_baro_phase_ms >= 12) {
                if (ms_read(0x00, b, 3)) {
                    const uint32_t d2 = (static_cast<uint32_t>(b[0]) << 16) | (static_cast<uint32_t>(b[1]) << 8) | b[2];
                    const ftu::Ms5611Reading m = ftu::ms5611_compensate(g_prom, g_baro_d1, d2);
                    const double alt = m.ok ? ftu::pressure_altitude_m(m.pressure_pa) : NAN;
                    if (m.ok && !isnan(alt)) {
                        g_baro_alt = alt;
                        g_baro_ms = now;
                        g_baro_valid = true;
                    }
                } else {
                    g_baro_present = false;
                }
                g_baro_phase = BaroPhase::Idle;
                g_baro_phase_ms = now;
            }
            break;
    }
}

// ---------------------------------------------------------------------------
// GNSS
// ---------------------------------------------------------------------------

/// The one GNSS setting this unit cannot fly without.  In the default
/// "portable" model a u-blox receiver stops reporting above 12 km; the
/// airborne <1 g model is good to 80 km.  The setting is read back, not
/// assumed, and the result is a telemetry flag that the pre-launch check
/// must see set.
void gnss_configure() {
    if (!g_gnss_ok) {
        g_gnss_ok = g_gnss.begin(Serial1);
        if (!g_gnss_ok) return;
        g_gnss.setUART1Output(COM_TYPE_UBX);
        g_gnss.setNavigationFrequency(1);
        g_gnss.setAutoPVT(true);
    }
    if (!g_gnss_airborne) {
        g_gnss.setDynamicModel(DYN_MODEL_AIRBORNE1g);
        g_gnss_airborne = g_gnss.getDynamicModel() == DYN_MODEL_AIRBORNE1g;
    }
}

void gnss_service(uint64_t now) {
    if (!g_gnss_ok || !g_gnss_airborne) {
        // The configuration calls block for up to about a second each.  That
        // is acceptable before and during flight, not during a cutter pulse.
        if (g_ftu.gate() == Gate::None && now - g_gnss_retry_ms >= 30000) {
            g_gnss_retry_ms = now;
            gnss_configure();
        }
        if (!g_gnss_ok) return;
    }
    g_gnss.checkUblox();
    if (g_gnss.getPVT()) {  // true once per fresh NAV-PVT; does not block with auto-PVT
        const bool ok = g_gnss.getFixType() == 3 && g_gnss.getGnssFixOk() &&
                        !g_gnss.getInvalidLlh() && g_gnss.getSIV() >= 5;
        if (ok) {
            g_lat = g_gnss.getLatitude() * 1e-7;
            g_lon = g_gnss.getLongitude() * 1e-7;
            g_gnss_alt = g_gnss.getAltitudeMSL() * 1e-3;
            g_fix_ms = now;
        }
        g_fix_valid = ok;
    }
}

// ---------------------------------------------------------------------------
// Radio
// ---------------------------------------------------------------------------

void radio_begin() {
    // SF10 / 125 kHz / CR 4/5, private sync word, 22 dBm, 8-symbol preamble.
    const int st = g_radio.begin(FTU_FREQ_MHZ, 125.0, 10, 5, RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 22,
                                 8, FTU_TCXO_V, false);
    g_radio_ok = st == RADIOLIB_ERR_NONE;
    if (!g_radio_ok) {
        LOG("radio begin failed: %d\n", st);
        return;
    }
    g_radio.setDio2AsRfSwitch(true);
    g_radio.setCurrentLimit(140.0);
    g_radio.setCRC(2);
    g_radio.setDio1Action(on_dio1);
    g_radio.startReceive();
}

void handle_uplink(const uint8_t* buf, size_t len, uint64_t now) {
    proto::Command c;
    const proto::Status st = g_rx->accept(buf, len, c);
    if (st != proto::Status::Ok) {
        LOG("uplink rejected: %u\n", static_cast<unsigned>(st));
        return;
    }
    // Store the counter before acting: if the action resets the unit, the
    // same packet must not be accepted again after the reboot.
    g_nvs.putUInt("ctr", g_rx->last_counter());
    ftu::Command cmd = ftu::Command::Ping;
    switch (c.cmd) {
        case proto::Cmd::Ping: cmd = ftu::Command::Ping; break;
        case proto::Cmd::Arm: cmd = ftu::Command::Arm; break;
        case proto::Cmd::Disarm: cmd = ftu::Command::Disarm; break;
        case proto::Cmd::Terminate: cmd = ftu::Command::Terminate; break;
    }
    const ftu::CommandResult r = g_ftu.on_command(cmd, c.arg, now);
    LOG("uplink cmd %u arg %u -> %u\n", static_cast<unsigned>(c.cmd), c.arg, static_cast<unsigned>(r));
    (void)r;
    g_tele_now = true;  // the next telemetry packet is the acknowledgement
}

void radio_service(uint64_t now) {
    if (!g_radio_ok) {
        // A unit without a radio still fences autonomously, and link loss
        // will bring it down after 3 h.  Keep trying in the meantime.
        if (g_ftu.gate() == Gate::None && now - g_radio_retry_ms >= 30000) {
            g_radio_retry_ms = now;
            radio_begin();
        }
        return;
    }
    if (g_dio1) {
        g_dio1 = false;
        if (g_tx_active) {
            g_radio.finishTransmit();
            g_tx_active = false;
        } else {
            uint8_t buf[64];
            const size_t n = g_radio.getPacketLength();
            if (n > 0 && n <= sizeof buf && g_radio.readData(buf, n) == RADIOLIB_ERR_NONE) {
                handle_uplink(buf, n, now);
            }
        }
        g_radio.startReceive();
    }
    if (g_tx_active && now - g_tx_start_ms > 2000) {
        // TX-done never arrived.  Do not sit deaf to TERMINATE because of it.
        g_tx_active = false;
        g_radio.standby();
        g_radio.startReceive();
    }
}

void send_telemetry(uint64_t now, bool batt_valid, uint16_t batt_mv) {
    proto::Telemetry t;
    t.vehicle_id = FTU_VEHICLE_ID;
    t.lat_deg = g_lat;
    t.lon_deg = g_lon;
    t.gnss_alt_m = g_gnss_alt;
    t.baro_alt_m = g_baro_alt;
    t.gate = static_cast<uint8_t>(g_ftu.gate());
    t.state = static_cast<uint8_t>(g_ftu.state());
    t.reason = static_cast<uint8_t>(g_ftu.reason());
    uint8_t flags = 0;
    if (g_fix_valid && now - g_fix_ms < kSensorStaleMs) flags |= proto::kFlagGnssValid;
    if (g_baro_valid && now - g_baro_ms < kSensorStaleMs) flags |= proto::kFlagBaroValid;
    if (g_ftu.home_set()) flags |= proto::kFlagHomeSet;
    if (g_ftu.heartbeat_present()) flags |= proto::kFlagHeartbeat;
    if (g_ftu.altitude_disagree()) flags |= proto::kFlagAltDisagree;
    if (g_gnss_airborne) flags |= proto::kFlagGnssAirborne;
    if (g_ftu.disarm_hold_active()) flags |= proto::kFlagDisarmHold;
    if (g_ftu.sequencer().stop() == ftu::SequencerStop::UnderVoltage) flags |= proto::kFlagUnderVoltage;
    t.flags = flags;
    t.batt_mv = batt_valid ? batt_mv : 0;
    t.flight_s = g_ftu.flight_s();
    t.ack = static_cast<uint16_t>(g_rx->last_counter());
    t.boot_count = g_boot_count;
    t.pulses = g_ftu.sequencer().pulses_started();
    t.rx_rejects = g_rx->rejects();

    uint8_t buf[proto::kTelemetryLen];
    if (proto::encode_telemetry(t, buf, sizeof buf) != proto::kTelemetryLen) return;
    if (g_radio.startTransmit(buf, sizeof buf) == RADIOLIB_ERR_NONE) {
        g_tx_active = true;
        g_tx_start_ms = now;
    } else {
        g_radio.startReceive();
    }
}

// ---------------------------------------------------------------------------
// Cell voltage
// ---------------------------------------------------------------------------

/// Returns false if the reading cannot be a 3S lithium primary pack that is
/// running this processor.  An unfitted or broken divider reads near zero,
/// and a "0 V" battery would otherwise tell the sequencer to stop before the
/// first pulse.  An implausible reading is treated as no reading, and the
/// sequencer then fires without the under-voltage checks.
bool read_battery(uint16_t* mv) {
#if FTU_HAS_VBAT_SENSE
    uint32_t sum = 0;
    for (int i = 0; i < 8; ++i) sum += analogReadMilliVolts(pin::kVbatSense);
    const float v = static_cast<float>(sum) / 8.0f * kVbatDivider;
    if (v < 2500.0f || v > 6500.0f) return false;
    *mv = static_cast<uint16_t>(v);
    return true;
#else
    (void)mv;
    return false;
#endif
}

// ---------------------------------------------------------------------------
// PMU
// ---------------------------------------------------------------------------

void pmu_begin() {
#if FTU_HAS_AXP2101
    // On the Supreme the radio and the GNSS are fed from AXP2101 LDOs that
    // are off until asked for.  Rail assignment is from memory of the vendor
    // examples (ALDO1 sensors/OLED, ALDO3 LoRa, ALDO4 GNSS) - VERIFY.  If the
    // PMU does not answer, carry on: a board fed through its 3V3 pin with the
    // PMU bypassed needs none of this.
    if (!g_pmu.begin(Wire1, AXP2101_SLAVE_ADDRESS, pin::kPmuSda, pin::kPmuScl)) {
        LOG("no AXP2101\n");
        return;
    }
    g_pmu.setALDO1Voltage(3300); g_pmu.enableALDO1();
    g_pmu.setALDO3Voltage(3300); g_pmu.enableALDO3();
    g_pmu.setALDO4Voltage(3300); g_pmu.enableALDO4();
    // The PMU's own protections must not switch the FTU off in flight.  The
    // power key is not reachable in the box, and a battery "low voltage
    // shutdown" is meaningless here (there is no Li-ion on the PMU input).
    g_pmu.disableIRQ(XPOWERS_AXP2101_ALL_IRQ);
    g_pmu.clearIrqStatus();
    g_pmu.setPowerKeyPressOffTime(XPOWERS_POWEROFF_10S);  // the longest the chip offers
#endif
}

}  // namespace

// ---------------------------------------------------------------------------

void setup() {
    // 1. Gates low before anything else.  Until this line they are
    //    high-impedance and held off by the external pull-downs.
    pinMode(pin::kCutA, OUTPUT);
    digitalWrite(pin::kCutA, LOW);
    pinMode(pin::kCutB, OUTPUT);
    digitalWrite(pin::kCutB, LOW);

#if FTU_DEBUG_SERIAL
    Serial.begin(115200);
#endif

    // 2. Watchdog: a hung I2C bus or radio driver resets the unit within 8 s.
    //    A reset puts the gates back to high-impedance (off) and the state
    //    comes back from flash, so a reset is always safe to take.
#if ESP_IDF_VERSION_MAJOR >= 5
    esp_task_wdt_config_t wdt = {};
    wdt.timeout_ms = kWatchdogS * 1000;
    wdt.idle_core_mask = 0;
    wdt.trigger_panic = true;
    if (esp_task_wdt_reconfigure(&wdt) != ESP_OK) esp_task_wdt_init(&wdt);
#else
    esp_task_wdt_init(kWatchdogS, true);
#endif
    esp_task_wdt_add(nullptr);

    // 3. Brown-out.  The ESP32's brown-out detector is left enabled (the
    //    framework default).  If a cutter pulse drags the 3V3 rail down, a
    //    clean reset with the gates released is better than a processor
    //    running outside its supply range with a gate held on.  The pulse
    //    counter is in flash before the gate opens, so the sequence resumes
    //    with the *next* pulse rather than repeating the one that failed.
    //
    //    Sleep: this firmware never enters light or deep sleep and never
    //    starts Wi-Fi or Bluetooth.  There is no code path that calls
    //    esp_deep_sleep_start(), esp_light_sleep_start() or enables automatic
    //    light sleep; do not add one.  An FTU that is asleep is not an FTU.

    // 4. Persistent state.
    g_nvs.begin("ftu", false);
    const uint32_t boots = g_nvs.getUInt("boot", 0) + 1;
    g_nvs.putUInt("boot", boots);
    g_boot_count = static_cast<uint8_t>(boots);
    LOG("boot %u, reset reason %d\n", static_cast<unsigned>(boots), static_cast<int>(esp_reset_reason()));

    //    Ground reset: BOOT button held for 3 s at power-up forgets the last
    //    flight (state, references, flight clock).  Without this a unit
    //    recovered in ARMED or TERMINATED would come back up in that state
    //    on the bench.  The uplink counter is deliberately kept.
    pinMode(pin::kButton, INPUT_PULLUP);
    bool held = digitalRead(pin::kButton) == LOW;
    for (int i = 0; held && i < 30; ++i) {
        delay(100);
        esp_task_wdt_reset();
        held = digitalRead(pin::kButton) == LOW;
    }
    if (held) {
        g_nvs.remove("st");
        LOG("flight state cleared\n");
    }
    load_state();

    static proto::CommandReceiver rx(kKey, FTU_VEHICLE_ID, g_nvs.getUInt("ctr", 0));
    g_rx = &rx;

    // 5. Power rails, buses, sensors, radio.
    pmu_begin();
    Wire.begin(pin::kI2cSda, pin::kI2cScl, 400000);
    Wire.setTimeOut(50);  // a stuck bus costs 50 ms, not the watchdog
    g_baro_present = ms_begin();

    pinMode(pin::kHeartbeat, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(pin::kHeartbeat), on_heartbeat, CHANGE);

    Serial1.begin(FTU_GNSS_BAUD, SERIAL_8N1, pin::kGnssRx, pin::kGnssTx);
    esp_task_wdt_reset();
    gnss_configure();
    esp_task_wdt_reset();

    SPI.begin(pin::kLoraSck, pin::kLoraMiso, pin::kLoraMosi, pin::kLoraCs);
    radio_begin();

    const uint64_t now = now_ms();
    g_next_step_ms = now;
    g_next_tele_ms = now + 2000;
}

void loop() {
    esp_task_wdt_reset();
    const uint64_t now = now_ms();

    radio_service(now);
    gnss_service(now);
    baro_service(now);

    if (now >= g_next_step_ms) {
        g_next_step_ms = now + kStepMs;

        ftu::Sample s;
        s.now_ms = now;
        s.gnss_valid = g_fix_valid && (now - g_fix_ms) < kSensorStaleMs;
        s.lat_deg = g_lat;
        s.lon_deg = g_lon;
        s.gnss_alt_m = g_gnss_alt;
        s.baro_valid = g_baro_valid && (now - g_baro_ms) < kSensorStaleMs;
        s.baro_alt_m = g_baro_alt;
        noInterrupts();
        s.hb_edges = g_hb_edges;
        g_hb_edges = 0;
        interrupts();
        s.batt_valid = read_battery(&s.batt_mv);

        const ftu::Outputs out = g_ftu.step(s);
        // Order matters: flash first, gate second (see Outputs::persist_dirty).
        if (out.persist_dirty) save_state();
        apply_gate(out.gate);

        // Telemetry.  Not started while a gate is on: a 22 dBm burst adds
        // ~120 mA to the 3V3 rail at the moment the cells are loaded hardest,
        // and the 3 s gaps between pulses are long enough for a packet.
        const uint32_t period = out.state == State::Terminated ? kTelemetryTermMs : kTelemetryMs;
        if (g_radio_ok && !g_tx_active && out.gate == Gate::None &&
            (g_tele_now || now >= g_next_tele_ms)) {
            g_tele_now = false;
            g_next_tele_ms = now + period;
            send_telemetry(now, s.batt_valid, s.batt_mv);
        }
    }
    delay(1);  // yield to the idle task; not sleep
}
