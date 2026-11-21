// Flight-termination unit (FTU) decision logic.
//
// Platform-independent C++17: no Arduino headers, no heap, no exceptions, no
// clock and no I/O.  Inputs are measurements and a monotonic millisecond
// count; outputs are a state, a reason and at most one cutter gate.  The same
// translation units build for the ESP32-S3 (src/main.cpp) and for the host
// test binary (host/), so what is tested on the host is what flies.
//
// Two layers:
//
//   1. must_terminate() - a line-for-line port of
//      aiur.strato.guidance.Geofence.must_terminate.  It is pure, uses IEEE-754
//      binary64 exactly like the Python floats it mirrors, and is replayed
//      against vectors generated from the Python (tools/ftu_vectors.py).
//      Do not "improve" it here; change the Python first, regenerate, re-run.
//
//   2. Ftu - everything the Python does not have and a real unit needs:
//      arming, heartbeat supervision, altitude source selection, confirmation
//      of sensor-derived criteria, the termination latch and the cutter
//      sequencer.  These are covered by scenario tests in host/.
//
// double, not float: the ESP32-S3 FPU is single precision, so double is done
// in software.  At <= 10 evaluations a second that costs microseconds, and it
// buys bit-identical comparisons with the reference at the thresholds.
#pragma once

#include <cstdint>
#include <limits>

namespace ftu {

// ---------------------------------------------------------------------------
// Layer 1: the reference criteria
// ---------------------------------------------------------------------------

/// Why the unit terminated.  Values 1..5 are the reasons the Python reference
/// can return, in its precedence order; they are part of the packet format
/// (protocol.hpp sends the number), so never renumber.
enum class Reason : uint8_t {
    None = 0,        // ""
    Commanded = 1,   // "commanded"
    Range = 2,       // "range"
    Altitude = 3,    // "altitude"
    FlightTime = 4,  // "flight time"
    LinkLoss = 5,    // "link loss"
    // Firmware-only: never returned by must_terminate().
    HeartbeatLoss = 6,  // "heartbeat loss"
};

/// The exact string the Python reference returns for a reason ("" for None).
const char* reason_str(Reason r);

/// Mirrors the dataclass fields of guidance.Geofence, same defaults.
struct GeofenceLimits {
    double max_range_m = 150000.0;
    double max_altitude_m = 27000.0;
    double max_flight_s = 16.0 * 3600.0;
    /// Present in the reference but read by nothing there; carried for parity
    /// of the structure only.
    double min_descent_altitude_m = 0.0;
};

/// Default of the reference's link_timeout_s argument.
constexpr double kDefaultLinkTimeoutS = 3.0 * 3600.0;

struct Decision {
    bool terminate;
    Reason reason;
};

/// Port of Geofence.must_terminate.  Strict '>' on every limit, precedence
/// commanded > range > altitude > flight time > link loss, and - as in
/// Python - a NaN input compares false and therefore never trips its own
/// criterion.  The Ftu class relies on that last property to mark a
/// measurement as unknown.
Decision must_terminate(const GeofenceLimits& limits, double range_m, double altitude_m,
                        double flight_s, bool commanded = false, double link_lost_s = 0.0,
                        double link_timeout_s = kDefaultLinkTimeoutS);

// ---------------------------------------------------------------------------
// Sensor mathematics (portable so the host can check it)
// ---------------------------------------------------------------------------

/// Great-circle distance on a sphere of mean Earth radius, metres.  Error
/// against the ellipsoid is < 0.6 %, i.e. < 1 km at the 150 km fence.
double great_circle_m(double lat1_deg, double lon1_deg, double lat2_deg, double lon2_deg);

/// Geometric altitude (m) of a static pressure (Pa) in the 1976 standard
/// atmosphere, valid 0..47 km.  Returns NaN for p <= 0 or NaN.
/// This is *pressure* altitude: the real atmosphere differs from the standard
/// one by hundreds of metres, which is one reason the barometer is the
/// lower-confidence source for the absolute ceiling.
double pressure_altitude_m(double pressure_pa);

struct Ms5611Reading {
    bool ok;             // false if the PROM is blank or the result is absurd
    double pressure_pa;
    double temperature_c;
};

/// MS5611-01BA03 first- and second-order compensation, as in the datasheet.
/// prom[1..6] are C1..C6; d1/d2 are the raw 24-bit pressure and temperature
/// conversions.  The second-order terms matter here: they apply below 20 C
/// and again below -15 C, which is where this sensor spends the flight.
Ms5611Reading ms5611_compensate(const uint16_t prom[8], uint32_t d1, uint32_t d2);

// ---------------------------------------------------------------------------
// Layer 2: the unit
// ---------------------------------------------------------------------------

enum class State : uint8_t {
    Disarmed = 0,    // on the ground: nothing can fire
    Armed = 1,       // in flight: criteria are evaluated
    Terminated = 2,  // latched; the cutter sequencer runs
};

/// At most one gate.  The sequencer's output is this enum, not two booleans,
/// so "both on" is unrepresentable rather than merely avoided.
enum class Gate : uint8_t { None = 0, A = 1, B = 2 };

enum class Command : uint8_t { Ping, Arm, Disarm, Terminate };

enum class CommandResult : uint8_t {
    Ok,
    RefusedDisarmed,  // TERMINATE while DISARMED: send ARM first
    RefusedLatched,   // DISARM after termination
};

enum class SequencerStop : uint8_t { Running = 0, Complete = 1, UnderVoltage = 2, NotStarted = 3 };

struct Config {
    GeofenceLimits limits;
    double link_timeout_s = kDefaultLinkTimeoutS;

    // --- arming -----------------------------------------------------------
    /// Height above the ground reference that counts as "flying".  300 m is
    /// more than a barometer drifts with weather in a day on the bench
    /// (~35 hPa) and more than a hill walk; a 4 m/s ascent passes it in 75 s.
    double arm_height_m = 300.0;
    /// The height must be held continuously this long.
    uint32_t arm_dwell_ms = 30000;
    /// Valid samples averaged for each ground reference.
    uint8_t ref_samples = 10;
    /// Cap on the hold a DISARM command can request.
    uint32_t max_disarm_hold_s = 3600;

    // --- heartbeat --------------------------------------------------------
    /// If false the heartbeat input is ignored (FTU flown without autopilot).
    bool heartbeat_required = true;
    /// No edge for this long means the heartbeat is absent.
    uint32_t hb_silence_ms = 5000;
    /// Absent for this long while ARMED means terminate.
    uint32_t hb_grace_ms = 600000;
    /// The heartbeat must be back continuously this long to cancel the timer.
    uint32_t hb_recover_ms = 30000;

    // --- altitude cross-check ---------------------------------------------
    /// GNSS and barometer are said to disagree beyond this.  It must exceed
    /// the barometer's own honest error at the ceiling: +-2.5 hPa of sensor
    /// error is ~0.9 km at 27 km, plus the standard-atmosphere error.
    double alt_disagree_m = 2000.0;

    // --- confirmation -----------------------------------------------------
    /// A range or altitude trip must persist this long before it latches.
    uint32_t confirm_ms = 5000;

    // --- cutter sequencer -------------------------------------------------
    uint32_t pulse_ms = 4000;
    uint32_t gap_ms = 3000;
    /// A cycle is one pulse on A then one pulse on B.
    uint8_t cycles = 3;
    /// Below this *while a gate is on*, that pulse is cut short.
    uint16_t uv_load_mv = 3000;
    /// Below this *with both gates off*, no further pulse is started.
    uint16_t uv_rest_mv = 3600;
};

/// One evaluation's worth of measurements.  Validity is decided by the glue
/// (fix type, satellite count, age, I2C status); this layer trusts the flags.
struct Sample {
    uint64_t now_ms = 0;  // monotonic, never wraps in a flight (64-bit)
    bool gnss_valid = false;
    double lat_deg = 0.0;
    double lon_deg = 0.0;
    double gnss_alt_m = 0.0;  // above mean sea level
    bool baro_valid = false;
    double baro_alt_m = 0.0;  // pressure_altitude_m() of the MS5611 reading
    uint32_t hb_edges = 0;    // heartbeat edges seen since the previous step
    bool batt_valid = false;  // false if the cell-voltage divider is not fitted
    uint16_t batt_mv = 0;     // FTU_RAW, i.e. the cutter supply
};

/// What survives a reset.  A brown-out or watchdog reset in flight must not
/// return the unit to DISARMED with a "ground" reference taken at 20 km.
struct Persist {
    uint8_t state = 0;           // State
    uint8_t reason = 0;          // Reason
    uint8_t pulses_started = 0;  // cutter pulses begun, across all boots
    uint32_t flight_s = 0;       // flight clock at the last save
    bool gnss_ref_set = false;
    double home_lat_deg = 0.0;
    double home_lon_deg = 0.0;
    double ref_gnss_alt_m = 0.0;
    bool baro_ref_set = false;
    double ref_baro_alt_m = 0.0;
};

struct Outputs {
    Gate gate;           // drive exactly this gate, the other low
    State state;
    Reason reason;
    /// Call persist() and store it *before* applying `gate`: the pulse count
    /// must reach flash before the pulse that might brown the unit out.
    bool persist_dirty;
};

/// Fire A for a pulse, wait, fire B for a pulse, wait; repeat `cycles` times.
///
/// Never both: FTU_BAT is sized by the harness review for one 5 W pulse at a
/// time, and a sagging rail would take the processor - and with it the
/// tracking beacon - down in the middle of a cut-down.
///
/// A first, then B: A drops the equipment string onto its parachute; B opens
/// the hull.  In that order the payload is already clear when the hull comes
/// apart.  Reversed, a deflating hull comes down on top of the string and its
/// canopy.
class CutterSequencer {
public:
    explicit CutterSequencer(const Config& cfg) : cfg_(&cfg) {}

    /// Begin (idempotent).  `pulses_already_started` is the persisted count
    /// from before a reset, so a unit that browns out on every pulse still
    /// stops after 2 x cycles pulses instead of cycling for ever.
    void start(uint64_t now_ms, uint8_t pulses_already_started = 0);
    /// Allow one more A/B cycle after the sequence has stopped.
    void extend_one_cycle(uint64_t now_ms);
    Gate step(uint64_t now_ms, bool batt_valid, uint16_t batt_mv);

    Gate gate() const { return gate_; }
    uint8_t pulses_started() const { return pulses_started_; }
    uint8_t uv_aborts() const { return uv_aborts_; }
    SequencerStop stop() const { return stop_; }
    /// True once in the step where pulses_started() changed.
    bool take_dirty() { bool d = dirty_; dirty_ = false; return d; }

private:
    uint16_t total_pulses() const { return static_cast<uint16_t>(2u * cfg_->cycles + extra_pulses_); }

    const Config* cfg_;
    SequencerStop stop_ = SequencerStop::NotStarted;
    Gate gate_ = Gate::None;
    uint64_t phase_start_ms_ = 0;
    bool first_gap_ = false;  // the gap before the very first pulse is zero
    uint8_t pulses_started_ = 0;
    uint8_t extra_pulses_ = 0;
    uint8_t uv_aborts_ = 0;
    bool dirty_ = false;
};

class Ftu {
public:
    explicit Ftu(const Config& cfg) : cfg_(cfg), seq_(cfg_) {}
    Ftu(const Ftu&) = delete;  // seq_ points at cfg_
    Ftu& operator=(const Ftu&) = delete;

    /// Call once before the first step() with what was stored.  A stored
    /// DISARMED state is ignored (fresh ground references are taken).
    void restore(const Persist& p);

    Outputs step(const Sample& s);

    /// `cmd` must already be authenticated (protocol.hpp).  Any authenticated
    /// command, PING included, counts as the link being alive.
    CommandResult on_command(Command cmd, uint16_t arg, uint64_t now_ms);

    Persist persist() const;

    // --- status for telemetry ---------------------------------------------
    State state() const { return state_; }
    Reason reason() const { return reason_; }
    Gate gate() const { return seq_.gate(); }
    const CutterSequencer& sequencer() const { return seq_; }
    bool home_set() const { return gnss_ref_set_; }
    bool heartbeat_present() const { return hb_present_; }
    bool heartbeat_timer_running() const { return hb_absent_valid_; }
    bool altitude_disagree() const { return alt_disagree_; }
    bool disarm_hold_active() const { return hold_active_; }
    double range_m() const { return range_m_; }          // NaN if unknown
    double altitude_m() const { return altitude_m_; }    // as used by the ceiling test
    double flight_s() const { return flight_s_; }
    double link_lost_s() const { return link_lost_s_; }

private:
    void arm(uint64_t now_ms);
    void latch(Reason r, uint64_t now_ms);
    void update_references(const Sample& s);
    void update_altitude(const Sample& s);
    void update_heartbeat(const Sample& s, uint64_t now_ms);
    void evaluate(uint64_t now_ms);

    Config cfg_;
    CutterSequencer seq_;

    State state_ = State::Disarmed;
    Reason reason_ = Reason::None;
    bool dirty_ = false;
    uint64_t now_ms_ = 0;
    bool stepped_ = false;
    bool restore_pending_ = false;
    uint8_t restored_pulses_ = 0;

    // ground references
    bool gnss_ref_set_ = false;
    uint8_t gnss_ref_n_ = 0;
    double sum_lat_ = 0.0, sum_lon_ = 0.0, sum_galt_ = 0.0;
    double home_lat_ = 0.0, home_lon_ = 0.0, ref_gnss_alt_ = 0.0;
    bool baro_ref_set_ = false;
    uint8_t baro_ref_n_ = 0;
    double sum_balt_ = 0.0;
    double ref_baro_alt_ = 0.0;

    // derived measurements; NaN = unknown
    double range_m_ = std::numeric_limits<double>::quiet_NaN();
    double altitude_m_ = std::numeric_limits<double>::quiet_NaN();
    bool alt_disagree_ = false;
    bool above_arm_height_ = false;

    // arming
    bool arm_since_valid_ = false;
    uint64_t arm_since_ms_ = 0;
    bool hold_active_ = false;
    uint64_t hold_until_ms_ = 0;

    // clocks
    uint64_t armed_at_ms_ = 0;
    double flight_offset_s_ = 0.0;
    double flight_s_ = 0.0;
    uint32_t flight_s_saved_ = 0;
    bool uplink_seen_ = false;
    uint64_t last_uplink_ms_ = 0;
    double link_lost_s_ = 0.0;
    bool commanded_ = false;

    // heartbeat
    bool hb_present_ = false;
    bool hb_edge_seen_ = false;
    uint64_t hb_last_edge_ms_ = 0;
    bool hb_absent_valid_ = false;
    uint64_t hb_absent_since_ms_ = 0;
    bool hb_back_valid_ = false;
    uint64_t hb_back_since_ms_ = 0;

    // confirmation of sensor-derived trips (independent timers, see step())
    bool range_since_valid_ = false;
    uint64_t range_since_ms_ = 0;
    bool alt_since_valid_ = false;
    uint64_t alt_since_ms_ = 0;

};

}  // namespace ftu
