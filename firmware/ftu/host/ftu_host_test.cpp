// Host test for the FTU logic.  No Arduino, no framework: one file, exit
// status 0 only if everything agrees.
//
//   (a) PARITY    - replays the vectors written by tools/ftu_vectors.py (the
//                   Python reference is the oracle) through must_terminate().
//   (b) SCENARIOS - the firmware-only behaviour: arming, heartbeat timer,
//                   altitude cross-check, confirmation, latch, sequencer,
//                   persistence, and the packet format.
//
// Usage: ftu_host_test <vectors.csv>
#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../src/geofence.hpp"
#include "../src/protocol.hpp"

using namespace ftu;

namespace {

int g_checks = 0;
int g_failed = 0;
const char* g_scenario = "";

void check_impl(bool ok, const char* expr, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failed;
        std::printf("    FAIL [%s] line %d: %s\n", g_scenario, line, expr);
    }
}
#define CHECK(x) check_impl((x), #x, __LINE__)

bool same_double(double a, double b) {
    if (std::isnan(a) || std::isnan(b)) return std::isnan(a) && std::isnan(b);
    return a == b && std::signbit(a) == std::signbit(b);
}

// ---------------------------------------------------------------------------
// (a) Parity
// ---------------------------------------------------------------------------

/// Split a line in place on commas; returns the field count.
int split(char* line, char* fields[], int max_fields) {
    int n = 0;
    char* p = line;
    while (n < max_fields) {
        fields[n++] = p;
        char* c = std::strchr(p, ',');
        if (!c) break;
        *c = '\0';
        p = c + 1;
    }
    return n;
}

struct ParityResult {
    long vectors = 0;
    long mismatches = 0;
    long defaults = 0;
    long default_mismatches = 0;
    long baro = 0;
    long baro_mismatches = 0;
    double baro_worst_m = 0.0;
    long by_reason[7] = {0, 0, 0, 0, 0, 0, 0};
    bool ok = false;
};

ParityResult run_parity(const char* path) {
    ParityResult res;
    std::FILE* f = std::fopen(path, "r");
    if (!f) {
        std::printf("cannot open %s\n", path);
        return res;
    }
    const GeofenceLimits def;
    char line[1024];
    while (std::fgets(line, sizeof line, f)) {
        size_t len = std::strlen(line);
        while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = '\0';
        if (len == 0 || line[0] == '#') continue;
        char* fld[16];
        const int n = split(line, fld, 16);

        if (fld[0][0] == 'D' && n == 3) {
            // A default read from the Python source by introspection.
            const double v = std::strtod(fld[2], nullptr);
            double mine = std::nan("");
            if (!std::strcmp(fld[1], "max_range_m")) mine = def.max_range_m;
            else if (!std::strcmp(fld[1], "max_altitude_m")) mine = def.max_altitude_m;
            else if (!std::strcmp(fld[1], "max_flight_s")) mine = def.max_flight_s;
            else if (!std::strcmp(fld[1], "min_descent_altitude_m")) mine = def.min_descent_altitude_m;
            else if (!std::strcmp(fld[1], "link_timeout_s")) mine = kDefaultLinkTimeoutS;
            else if (!std::strcmp(fld[1], "link_lost_s")) mine = 0.0;   // exercised by argc < 5 rows
            else if (!std::strcmp(fld[1], "commanded")) mine = 0.0;     // exercised by argc < 4 rows
            ++res.defaults;
            if (!same_double(v, mine)) {
                ++res.default_mismatches;
                std::printf("    DEFAULT MISMATCH %s: python %a, c++ %a\n", fld[1], v, mine);
            }
        } else if (fld[0][0] == 'V' && n == 14) {
            const int argc = std::atoi(fld[1]);
            GeofenceLimits lim;
            lim.max_range_m = std::strtod(fld[2], nullptr);
            lim.max_altitude_m = std::strtod(fld[3], nullptr);
            lim.max_flight_s = std::strtod(fld[4], nullptr);
            lim.min_descent_altitude_m = std::strtod(fld[5], nullptr);
            const double range = std::strtod(fld[6], nullptr);
            const double alt = std::strtod(fld[7], nullptr);
            const double flight = std::strtod(fld[8], nullptr);
            const bool commanded = fld[9][0] == '1';
            const double lost = std::strtod(fld[10], nullptr);
            const double timeout = std::strtod(fld[11], nullptr);
            const bool want_term = fld[12][0] == '1';
            const char* want_reason = fld[13];

            // Same arity as the Python call, so the default arguments are
            // the ones under test for argc < 6.
            Decision d{false, Reason::None};
            switch (argc) {
                case 3: d = must_terminate(lim, range, alt, flight); break;
                case 4: d = must_terminate(lim, range, alt, flight, commanded); break;
                case 5: d = must_terminate(lim, range, alt, flight, commanded, lost); break;
                case 6: d = must_terminate(lim, range, alt, flight, commanded, lost, timeout); break;
                default: ++res.mismatches; continue;
            }
            ++res.vectors;
            const bool agree = d.terminate == want_term &&
                               std::strcmp(reason_str(d.reason), want_reason) == 0 &&
                               d.terminate == (d.reason != Reason::None);
            if (agree) {
                ++res.by_reason[static_cast<int>(d.reason)];
            } else {
                if (++res.mismatches <= 10) {
                    std::printf("    MISMATCH argc=%d range=%a alt=%a flight=%a cmd=%d lost=%a "
                                "timeout=%a: python (%d,'%s') c++ (%d,'%s')\n",
                                argc, range, alt, flight, commanded, lost, timeout, want_term,
                                want_reason, d.terminate, reason_str(d.reason));
                }
            }
        } else if (fld[0][0] == 'P' && n == 3) {
            const double p = std::strtod(fld[1], nullptr);
            const double want = std::strtod(fld[2], nullptr);
            const double err = std::fabs(pressure_altitude_m(p) - want);
            ++res.baro;
            if (err > res.baro_worst_m) res.baro_worst_m = err;
            // 5 m: far inside the sensor's own error, far outside rounding.
            if (!(err <= 5.0)) ++res.baro_mismatches;
        } else {
            std::printf("    unparsed line: %s\n", line);
            ++res.mismatches;
        }
    }
    std::fclose(f);
    res.ok = res.vectors >= 20000 && res.mismatches == 0 && res.defaults == 7 &&
             res.default_mismatches == 0 && res.baro > 0 && res.baro_mismatches == 0;
    return res;
}

// ---------------------------------------------------------------------------
// (b) Scenario harness
// ---------------------------------------------------------------------------

constexpr double kHomeLat = 50.45, kHomeLon = 30.52, kGround = 150.0;

/// Drives an Ftu at 10 Hz the way main.cpp does, models the two gate pins,
/// and checks the invariants that must hold on every single step.
struct Rig {
    Ftu* f;
    Sample s;
    uint64_t t = 1000;
    bool hb_on = true;           // autopilot heartbeat running (2 Hz edges)
    bool pin_a = false, pin_b = false;
    bool ever_terminated = false;
    Reason first_reason = Reason::None;
    uint64_t terminated_at = 0;
    long gate_a_steps = 0, gate_b_steps = 0;
    long persist_requests = 0;
    Outputs last{Gate::None, State::Disarmed, Reason::None, false};

    explicit Rig(Ftu& ftu) : f(&ftu) {
        s.gnss_valid = true;
        s.lat_deg = kHomeLat;
        s.lon_deg = kHomeLon;
        s.gnss_alt_m = kGround;
        s.baro_valid = true;
        s.baro_alt_m = kGround;
        s.batt_valid = true;
        s.batt_mv = 5000;
    }

    void set_alt(double m) { s.gnss_alt_m = m; s.baro_alt_m = m; }
    /// Move the vehicle `m` metres north of home.
    void set_range(double m) { s.lat_deg = kHomeLat + m / 111194.93; }

    void step_once() {
        t += 100;
        s.now_ms = t;
        s.hb_edges = (hb_on && (t % 500 == 0)) ? 1u : 0u;
        last = f->step(s);
        if (last.persist_dirty) ++persist_requests;
        // What main.cpp does with the output.
        pin_a = last.gate == Gate::A;
        pin_b = last.gate == Gate::B;
        if (pin_a) ++gate_a_steps;
        if (pin_b) ++gate_b_steps;

        // Invariants, every step, every scenario.
        CHECK(!(pin_a && pin_b));                                   // never both gates
        if (last.state != State::Terminated) CHECK(last.gate == Gate::None);  // no gate before latch
        if (last.state != State::Terminated) CHECK(last.reason == Reason::None);
        if (ever_terminated) {
            CHECK(last.state == State::Terminated);                 // the latch
            CHECK(last.reason == first_reason);                     // and its reason
        } else if (last.state == State::Terminated) {
            ever_terminated = true;
            first_reason = last.reason;
            terminated_at = t;
            CHECK(first_reason != Reason::None);
        }
    }
    void run(double seconds) {
        const long n = std::lround(seconds * 10.0);
        for (long i = 0; i < n; ++i) step_once();
    }
    /// Sit on the ground long enough for the references, then climb at 5 m/s
    /// to `alt_m`.  Keeps the ground link alive with a PING every 10 min.
    void climb_to(double alt_m) {
        run(5.0);
        while (s.gnss_alt_m < alt_m) {
            set_alt(s.gnss_alt_m + 0.5);
            step_once();
        }
    }
    void ping() { f->on_command(Command::Ping, 0, t); }
    /// Run for `seconds`, pinging every 10 minutes.
    void run_linked(double seconds) {
        const long n = std::lround(seconds * 10.0);
        for (long i = 0; i < n; ++i) {
            if (i % 6000 == 0) ping();
            step_once();
        }
    }
};

Config test_config() {
    Config c;  // flight defaults; scenarios override single fields
    return c;
}

void scenario_bench_never_arms() {
    g_scenario = "bench: 24 h powered on the ground, no autopilot, no ground station";
    Ftu f(test_config());
    Rig r(f);
    r.hb_on = false;
    // Weather and sensor noise well inside the arming height.
    for (int i = 0; i < 24 * 3600 * 10; ++i) {
        r.s.baro_alt_m = kGround + 120.0 * std::sin(i * 1e-4);
        r.s.gnss_alt_m = kGround + 40.0 * std::sin(i * 0.37);
        r.step_once();
    }
    CHECK(f.state() == State::Disarmed);
    CHECK(!r.ever_terminated);
    CHECK(r.gate_a_steps == 0 && r.gate_b_steps == 0);
    CHECK(f.home_set());
}

void scenario_spike_does_not_arm() {
    g_scenario = "arming: excursion above arm height shorter than the dwell";
    Ftu f(test_config());
    Rig r(f);
    r.run(5.0);
    r.set_alt(kGround + 5000.0);
    r.run(29.0);  // dwell is 30 s
    CHECK(f.state() == State::Disarmed);
    r.set_alt(kGround);
    r.run(60.0);
    CHECK(f.state() == State::Disarmed);
    // Exactly at the arming height is not above it.
    r.set_alt(kGround + 300.0);
    r.run(120.0);
    CHECK(f.state() == State::Disarmed);
}

void scenario_arms_in_climb() {
    g_scenario = "arming: 5 m/s ascent arms once, 30 s after passing +300 m";
    Ftu f(test_config());
    Rig r(f);
    r.run(5.0);
    uint64_t t_cross = 0, t_armed = 0;
    while (r.s.gnss_alt_m < 2000.0) {
        r.set_alt(r.s.gnss_alt_m + 0.5);
        r.step_once();
        if (!t_cross && r.s.gnss_alt_m > kGround + 300.0) t_cross = r.t;
        if (!t_armed && f.state() == State::Armed) t_armed = r.t;
    }
    CHECK(t_cross != 0 && t_armed != 0);
    CHECK(t_armed - t_cross == 30000);
    CHECK(f.state() == State::Armed);
    CHECK(!r.ever_terminated);
}

void scenario_arms_on_one_source() {
    g_scenario = "arming: either altitude source alone is enough";
    {
        Ftu f(test_config());
        Rig r(f);
        r.run(5.0);
        r.s.gnss_valid = false;  // fix lost at launch
        r.s.baro_alt_m = kGround + 1000.0;
        r.run(31.0);
        CHECK(f.state() == State::Armed);
    }
    {
        Ftu f(test_config());
        Rig r(f);
        r.s.baro_valid = false;  // barometer never answered
        r.run(5.0);
        r.s.gnss_alt_m = kGround + 1000.0;
        r.run(31.0);
        CHECK(f.state() == State::Armed);
    }
    {
        // Barometer port blocked on the ground value; GNSS climbs.
        Ftu f(test_config());
        Rig r(f);
        r.run(5.0);
        r.s.gnss_alt_m = kGround + 1000.0;
        r.run(31.0);
        CHECK(f.state() == State::Armed);
    }
    {
        // No source at all: stays disarmed (and the ground can ARM by command).
        Ftu f(test_config());
        Rig r(f);
        r.s.gnss_valid = false;
        r.s.baro_valid = false;
        r.run(600.0);
        CHECK(f.state() == State::Disarmed);
        CHECK(f.on_command(Command::Arm, 0, r.t) == CommandResult::Ok);
        CHECK(f.state() == State::Armed);
    }
}

void scenario_command_needs_arm() {
    g_scenario = "command: TERMINATE refused while DISARMED; ARM then TERMINATE fires";
    Ftu f(test_config());
    Rig r(f);
    r.hb_on = false;
    r.run(10.0);
    CHECK(f.on_command(Command::Terminate, 0, r.t) == CommandResult::RefusedDisarmed);
    r.run(60.0);
    CHECK(f.state() == State::Disarmed && !r.ever_terminated);
    CHECK(f.on_command(Command::Arm, 0, r.t) == CommandResult::Ok);
    r.run(1.0);
    CHECK(f.state() == State::Armed);
    CHECK(f.on_command(Command::Terminate, 0, r.t) == CommandResult::Ok);
    r.step_once();
    CHECK(f.state() == State::Terminated);
    CHECK(r.first_reason == Reason::Commanded);
    CHECK(r.last.gate == Gate::A);  // first pulse starts in the same step
}

void scenario_heartbeat() {
    g_scenario = "heartbeat: loss starts a timer, does not cut down";
    {
        Ftu f(test_config());
        Rig r(f);
        r.climb_to(5000.0);
        CHECK(f.state() == State::Armed);
        r.run_linked(600.0);
        CHECK(f.heartbeat_present() && !f.heartbeat_timer_running());
        r.hb_on = false;
        const uint64_t t_lost = r.t;
        r.run_linked(10.0);
        CHECK(!f.heartbeat_present() && f.heartbeat_timer_running());
        CHECK(f.state() == State::Armed);
        r.run_linked(585.0);  // 595 s after the last edge: still inside 5 s + 600 s
        CHECK(f.state() == State::Armed);
        r.run_linked(15.0);
        CHECK(f.state() == State::Terminated);
        CHECK(r.first_reason == Reason::HeartbeatLoss);
        // Silence detection (5 s) plus grace (600 s), to within one 0.5 s edge period.
        const double waited_s = static_cast<double>(r.terminated_at - t_lost) / 1000.0;
        CHECK(waited_s >= 604.5 && waited_s <= 605.5);
    }
    g_scenario = "heartbeat: back for longer than the recovery time cancels the timer";
    {
        Ftu f(test_config());
        Rig r(f);
        r.climb_to(5000.0);
        r.hb_on = false;
        r.run_linked(300.0);
        r.hb_on = true;
        r.run_linked(40.0);  // recovery is 30 s
        CHECK(!f.heartbeat_timer_running());
        r.run_linked(1200.0);
        CHECK(f.state() == State::Armed);
    }
    g_scenario = "heartbeat: an autopilot in a reboot loop does not hold the timer off";
    {
        Ftu f(test_config());
        Rig r(f);
        r.climb_to(5000.0);
        r.hb_on = false;
        const uint64_t t_lost = r.t;
        // 3 s of heartbeat every 20 s: never back for the 30 s recovery time.
        while (!r.ever_terminated && r.t - t_lost < 900000) {
            r.hb_on = ((r.t - t_lost) % 20000) < 3000;
            if ((r.t / 100) % 6000 == 0) r.ping();
            r.step_once();
        }
        CHECK(r.ever_terminated);
        CHECK(r.first_reason == Reason::HeartbeatLoss);
        CHECK(r.terminated_at - t_lost <= 612000);
    }
    g_scenario = "heartbeat: never present after arming counts as lost from arming";
    {
        Ftu f(test_config());
        Rig r(f);
        r.hb_on = false;
        r.climb_to(1000.0);
        CHECK(f.state() == State::Armed);
        r.run_linked(500.0);  // armed ~80 s before the climb ended: 580 s of the 600 s grace
        CHECK(f.state() == State::Armed);
        r.run_linked(200.0);
        CHECK(r.first_reason == Reason::HeartbeatLoss);
    }
    g_scenario = "heartbeat: ignored when not required (FTU flown alone)";
    {
        Config c = test_config();
        c.heartbeat_required = false;
        Ftu f(c);
        Rig r(f);
        r.hb_on = false;
        r.climb_to(5000.0);
        r.run_linked(7200.0);
        CHECK(f.state() == State::Armed);
    }
    g_scenario = "heartbeat: absence on the ground does nothing";
    {
        Ftu f(test_config());
        Rig r(f);
        r.hb_on = false;
        r.run(3600.0);
        CHECK(f.state() == State::Disarmed && !f.heartbeat_timer_running());
    }
}

void scenario_range_and_confirmation() {
    g_scenario = "range: one bad fix does not terminate; a sustained excursion does";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(20000.0);
    r.set_range(100000.0);
    r.run_linked(60.0);
    CHECK(std::fabs(f.range_m() - 100000.0) < 5.0);
    CHECK(f.state() == State::Armed);
    r.set_range(400000.0);  // a jump: 4.9 s of it, confirm is 5 s
    r.run(4.9);
    r.set_range(100000.0);
    r.run_linked(60.0);
    CHECK(f.state() == State::Armed);
    r.set_range(150000.0 - 50.0);  // just inside the fence
    r.run_linked(60.0);
    CHECK(f.state() == State::Armed);
    r.set_range(150000.0 + 50.0);
    const uint64_t t0 = r.t;
    r.run(10.0);
    CHECK(f.state() == State::Terminated);
    CHECK(r.first_reason == Reason::Range);
    CHECK(r.terminated_at - t0 >= 5000 && r.terminated_at - t0 <= 5200);
}

void scenario_gnss_loss_holds_range() {
    g_scenario = "range: GNSS loss holds the last range and does not terminate by itself";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(20000.0);
    r.set_range(120000.0);
    r.run_linked(30.0);
    r.s.gnss_valid = false;
    r.set_range(900000.0);  // ignored: flagged invalid
    r.run_linked(1800.0);
    CHECK(f.state() == State::Armed);
    CHECK(std::fabs(f.range_m() - 120000.0) < 5.0);
}

/// Altitude cross-check: returns the state after 60 s at the given readings.
State altitude_case(bool gnss_valid, double gnss_alt, bool baro_valid, double baro_alt,
                    bool* disagree, Reason* reason) {
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(15000.0);
    r.s.gnss_valid = gnss_valid;
    r.s.gnss_alt_m = gnss_alt;
    r.s.baro_valid = baro_valid;
    r.s.baro_alt_m = baro_alt;
    r.run_linked(60.0);
    if (disagree) *disagree = f.altitude_disagree();
    if (reason) *reason = f.reason();
    return f.state();
}

void scenario_altitude_crosscheck() {
    g_scenario = "altitude: source selection and the disagreement rule";
    bool dis = false;
    Reason why = Reason::None;
    // Both agree, below the ceiling.
    CHECK(altitude_case(true, 26900.0, true, 26800.0, &dis, &why) == State::Armed);
    CHECK(!dis);
    // Both agree, above the ceiling.
    CHECK(altitude_case(true, 27100.0, true, 27150.0, &dis, &why) == State::Terminated);
    CHECK(why == Reason::Altitude);
    // Within the threshold GNSS wins: barometer says "above", GNSS says "below".
    CHECK(altitude_case(true, 26500.0, true, 27900.0, &dis, &why) == State::Armed);
    CHECK(!dis);
    // ...and the converse: GNSS above, barometer (inside the threshold) below.
    CHECK(altitude_case(true, 27050.0, true, 25500.0, &dis, &why) == State::Terminated);
    // Disagreement, GNSS stuck low, barometer above the ceiling: terminate.
    CHECK(altitude_case(true, 12000.0, true, 27500.0, &dis, &why) == State::Terminated);
    CHECK(dis && why == Reason::Altitude);
    // Disagreement, barometer stuck low (iced port), GNSS above: terminate.
    CHECK(altitude_case(true, 27500.0, true, 3000.0, &dis, &why) == State::Terminated);
    CHECK(dis && why == Reason::Altitude);
    // Disagreement, both below the ceiling: flagged, no termination.
    CHECK(altitude_case(true, 25000.0, true, 3000.0, &dis, &why) == State::Armed);
    CHECK(dis);
    // One source only.
    CHECK(altitude_case(false, 0.0, true, 27500.0, &dis, &why) == State::Terminated);
    CHECK(altitude_case(false, 0.0, true, 26500.0, &dis, &why) == State::Armed);
    CHECK(altitude_case(true, 27500.0, false, 0.0, &dis, &why) == State::Terminated);
    CHECK(altitude_case(true, 26500.0, false, 0.0, &dis, &why) == State::Armed);
    // No source: the last value (15 km) is held; no termination.
    CHECK(altitude_case(false, 99999.0, false, 99999.0, &dis, &why) == State::Armed);

    g_scenario = "altitude: a single wild barometer sample does not terminate";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(20000.0);
    r.s.baro_alt_m = 45000.0;
    r.run(4.9);
    r.s.baro_alt_m = 20000.0;
    r.run_linked(600.0);
    CHECK(f.state() == State::Armed);
}

void scenario_clock_criteria() {
    g_scenario = "flight time: 16 h after arming, with link and heartbeat healthy";
    {
        Ftu f(test_config());
        Rig r(f);
        r.climb_to(20000.0);
        r.run_linked(16.0 * 3600.0 - 4200.0);  // the climb took ~66 min
        CHECK(f.state() == State::Armed);
        r.run_linked(900.0);
        CHECK(f.state() == State::Terminated);
        CHECK(r.first_reason == Reason::FlightTime);
        // The flight clock keeps running for telemetry; take it back to the
        // instant of the latch.  One 0.1 s step past the limit (strict '>').
        const double at_latch = f.flight_s() - static_cast<double>(r.t - r.terminated_at) / 1000.0;
        CHECK(at_latch > 16.0 * 3600.0 && at_latch < 16.0 * 3600.0 + 0.2);
    }
    g_scenario = "link loss: 3 h without an authenticated uplink";
    {
        Ftu f(test_config());
        Rig r(f);
        r.climb_to(20000.0);
        r.ping();
        const uint64_t t_ping = r.t;
        r.run(3.0 * 3600.0 - 1.0);
        CHECK(f.state() == State::Armed);
        r.run(2.0);
        CHECK(f.state() == State::Terminated);
        CHECK(r.first_reason == Reason::LinkLoss);
        CHECK(r.terminated_at - t_ping >= 10800000 && r.terminated_at - t_ping <= 10800200);
    }
    g_scenario = "link loss: time on the pad before arming is not counted";
    {
        Ftu f(test_config());
        Rig r(f);
        r.run(4.0 * 3600.0);  // four hours on the launch field, no uplink at all
        CHECK(f.state() == State::Disarmed);
        r.climb_to(5000.0);
        r.run(600.0);
        CHECK(f.state() == State::Armed);
    }
    g_scenario = "precedence: an unconfirmed range trip does not mask flight time";
    {
        Config c = test_config();
        c.limits.max_flight_s = 3600.0;
        c.confirm_ms = 60000;
        Ftu f(c);
        Rig r(f);
        r.climb_to(5000.0);
        while (f.flight_s() < 3590.0) { r.ping(); r.run(1.0); }
        r.set_range(200000.0);  // tripped but 60 s from confirmed
        r.run(15.0);
        CHECK(r.first_reason == Reason::FlightTime);
    }
}

void scenario_latch() {
    g_scenario = "latch: nothing un-terminates";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(20000.0);
    r.set_range(160000.0);
    r.run(10.0);
    CHECK(f.state() == State::Terminated && r.first_reason == Reason::Range);
    // Everything goes back to nominal, and the ground asks nicely.
    r.set_range(0.0);
    r.set_alt(kGround);
    CHECK(f.on_command(Command::Disarm, 600, r.t) == CommandResult::RefusedLatched);
    CHECK(f.on_command(Command::Arm, 0, r.t) == CommandResult::Ok);
    r.run_linked(3600.0);  // Rig::step_once checks state and reason on every step
    CHECK(f.state() == State::Terminated && f.reason() == Reason::Range);
    // A second, different criterion does not rewrite the reason.
    r.set_alt(40000.0);
    r.run(60.0);
    CHECK(f.reason() == Reason::Range);
}

/// Records the gate timeline of a sequencer run at 10 ms resolution.
struct Timeline {
    int pulses = 0;
    char order[64] = {0};
    uint64_t on_ms[64] = {0}, off_ms[64] = {0};
    bool overlap = false;
};

Timeline run_sequencer(CutterSequencer& seq, uint64_t t0, uint64_t duration_ms,
                       uint16_t rest_mv, uint16_t load_mv, bool batt_valid) {
    Timeline tl;
    Gate prev = Gate::None;
    for (uint64_t t = t0; t < t0 + duration_ms; t += 10) {
        // The cell voltage the sequencer sees depends on what it did last.
        const uint16_t mv = (seq.gate() == Gate::None) ? rest_mv : load_mv;
        const Gate g = seq.step(t, batt_valid, mv);
        const bool a = g == Gate::A, b = g == Gate::B;
        if (a && b) tl.overlap = true;
        if (g != prev) {
            if (prev != Gate::None && tl.pulses > 0) tl.off_ms[tl.pulses - 1] = t;
            if (g != Gate::None && tl.pulses < 63) {
                // A direct A->B or B->A hand-over would be an overlap in
                // practice (MOSFET turn-off time); the sequencer must pass
                // through None.
                if (prev != Gate::None) tl.overlap = true;
                tl.order[tl.pulses] = a ? 'A' : 'B';
                tl.on_ms[tl.pulses] = t;
                ++tl.pulses;
            }
            prev = g;
        }
    }
    return tl;
}

void scenario_sequencer() {
    const Config c = test_config();
    g_scenario = "sequencer: A,B x3, one gate at a time, with gaps";
    {
        CutterSequencer seq(c);
        CHECK(seq.step(0, true, 5000) == Gate::None);  // not started: nothing
        seq.start(1000);
        Timeline tl = run_sequencer(seq, 1000, 120000, 5000, 4200, true);
        CHECK(!tl.overlap);
        CHECK(tl.pulses == 6);
        CHECK(std::strcmp(tl.order, "ABABAB") == 0);
        for (int i = 0; i < tl.pulses; ++i) {
            CHECK(tl.off_ms[i] - tl.on_ms[i] == c.pulse_ms);
            if (i > 0) CHECK(tl.on_ms[i] - tl.off_ms[i - 1] >= c.gap_ms);
        }
        CHECK(tl.on_ms[0] == 1000);  // no delay before the first pulse
        CHECK(seq.stop() == SequencerStop::Complete);
        CHECK(seq.pulses_started() == 6);
        // And it stays off.
        Timeline after = run_sequencer(seq, 200000, 600000, 5000, 4200, true);
        CHECK(after.pulses == 0);
    }
    g_scenario = "sequencer: under-voltage under load cuts each pulse short";
    {
        CutterSequencer seq(c);
        seq.start(0);
        Timeline tl = run_sequencer(seq, 0, 120000, 4500, 2900, true);  // sags below 3000 mV
        CHECK(!tl.overlap);
        CHECK(tl.pulses == 6);
        for (int i = 0; i < tl.pulses; ++i) CHECK(tl.off_ms[i] - tl.on_ms[i] <= 10);
        CHECK(seq.uv_aborts() == 6);
    }
    g_scenario = "sequencer: resting under-voltage stops the sequence";
    {
        CutterSequencer seq(c);
        seq.start(0);
        Timeline tl = run_sequencer(seq, 0, 12000, 5000, 4200, true);  // A, gap, B, in the gap
        CHECK(tl.pulses == 2 && seq.gate() == Gate::None);
        Timeline tl2 = run_sequencer(seq, 12000, 120000, 3500, 3000, true);  // cells flat
        CHECK(tl2.pulses == 0);
        CHECK(seq.stop() == SequencerStop::UnderVoltage);
        CHECK(seq.gate() == Gate::None);
    }
    g_scenario = "sequencer: with no voltage measurement it fires regardless";
    {
        CutterSequencer seq(c);
        seq.start(0);
        Timeline tl = run_sequencer(seq, 0, 120000, 0, 0, false);
        CHECK(tl.pulses == 6 && !tl.overlap);
    }
    g_scenario = "sequencer: one extra cycle on request, only after it has stopped";
    {
        CutterSequencer seq(c);
        seq.start(0);
        seq.extend_one_cycle(10);  // still running: ignored
        Timeline tl = run_sequencer(seq, 0, 120000, 5000, 4200, true);
        CHECK(tl.pulses == 6);
        seq.extend_one_cycle(120000);
        Timeline tl2 = run_sequencer(seq, 120000, 120000, 5000, 4200, true);
        CHECK(tl2.pulses == 2 && std::strcmp(tl2.order, "AB") == 0 && !tl2.overlap);
        CHECK(seq.stop() == SequencerStop::Complete);
    }
    g_scenario = "sequencer: through the whole unit, gates off before and after";
    {
        Ftu f(c);
        Rig r(f);
        r.climb_to(5000.0);
        CHECK(r.gate_a_steps == 0 && r.gate_b_steps == 0);
        f.on_command(Command::Terminate, 0, r.t);
        r.run(300.0);
        CHECK(f.sequencer().stop() == SequencerStop::Complete);
        CHECK(r.gate_a_steps == 3 * 40 && r.gate_b_steps == 3 * 40);  // 3 x 4 s at 10 Hz
        CHECK(r.last.gate == Gate::None);
        // A repeated TERMINATE gives exactly one more cycle.
        f.on_command(Command::Terminate, 0, r.t);
        r.run(300.0);
        CHECK(r.gate_a_steps == 4 * 40 && r.gate_b_steps == 4 * 40);
    }
}

void scenario_persistence() {
    g_scenario = "reset in flight: armed state, references and flight clock survive";
    {
        Config c = test_config();
        Persist saved;
        double flight_before = 0.0;
        {
            Ftu f(c);
            Rig r(f);
            r.climb_to(20000.0);
            r.set_range(80000.0);
            r.run_linked(7200.0);
            saved = f.persist();
            flight_before = f.flight_s();
            CHECK(r.persist_requests > 100);  // once a minute, plus events
        }
        CHECK(saved.state == static_cast<uint8_t>(State::Armed));
        CHECK(flight_before - saved.flight_s < 61.0);
        Ftu f2(c);
        f2.restore(saved);
        Rig r2(f2);
        r2.set_alt(20000.0);     // it wakes up at float, not on the ground
        r2.set_range(80000.0);
        r2.run_linked(60.0);
        CHECK(f2.state() == State::Armed);            // not DISARMED with a 20 km "ground"
        CHECK(std::fabs(f2.range_m() - 80000.0) < 5.0);  // home is the original home
        CHECK(f2.flight_s() >= saved.flight_s + 59.0);
        r2.set_range(151000.0);
        r2.run(10.0);
        CHECK(f2.state() == State::Terminated && f2.reason() == Reason::Range);
    }
    g_scenario = "reset after termination: latch, reason and pulse count survive";
    {
        Config c = test_config();
        Persist saved;
        {
            Ftu f(c);
            Rig r(f);
            r.climb_to(5000.0);
            f.on_command(Command::Terminate, 0, r.t);
            r.run(12.0);  // A done, gap, B on: 2 pulses started
            saved = f.persist();
        }
        CHECK(saved.state == static_cast<uint8_t>(State::Terminated));
        CHECK(saved.reason == static_cast<uint8_t>(Reason::Commanded));
        CHECK(saved.pulses_started == 2);
        Ftu f2(c);
        f2.restore(saved);
        CHECK(f2.persist().pulses_started == 2);  // before the first step, too
        Rig r2(f2);
        r2.set_alt(4000.0);
        r2.run(300.0);
        CHECK(f2.state() == State::Terminated && f2.reason() == Reason::Commanded);
        CHECK(r2.gate_a_steps == 2 * 40 && r2.gate_b_steps == 2 * 40);  // 4 remaining pulses
        CHECK(f2.sequencer().pulses_started() == 6);
    }
    g_scenario = "brown-out on every pulse: bounded across resets, both cutters tried";
    {
        Config c = test_config();
        Persist saved;
        saved.state = static_cast<uint8_t>(State::Terminated);
        saved.reason = static_cast<uint8_t>(Reason::LinkLoss);
        int boots = 0, a = 0, b = 0;
        for (; boots < 50; ++boots) {
            Ftu f(c);
            f.restore(saved);
            Sample s;
            bool reset = false;
            for (uint64_t t = 100; t < 60000 && !reset; t += 100) {
                s.now_ms = t;
                Outputs o = f.step(s);
                // main.cpp stores before it drives the gate.
                if (o.persist_dirty) saved = f.persist();
                if (o.gate != Gate::None) {
                    (o.gate == Gate::A ? a : b)++;
                    reset = true;  // the rail collapses the moment the gate opens
                }
            }
            if (!reset) break;
        }
        CHECK(boots == 6);
        CHECK(a == 3 && b == 3);
        CHECK(saved.pulses_started == 6);
    }
    g_scenario = "a stored DISARMED state is not restored: fresh references";
    {
        Persist saved;
        saved.state = static_cast<uint8_t>(State::Disarmed);
        saved.gnss_ref_set = true;
        saved.ref_gnss_alt_m = -5000.0;  // would arm at once if it were believed
        saved.baro_ref_set = true;
        saved.ref_baro_alt_m = -5000.0;
        Ftu f(test_config());
        f.restore(saved);
        Rig r(f);
        r.run(120.0);
        CHECK(f.state() == State::Disarmed);
    }
}

void scenario_disarm_hold() {
    g_scenario = "DISARM: bounded hold, then the normal arming rule applies again";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(10000.0);
    r.run_linked(100.0);
    const double flight_before = f.flight_s();
    CHECK(f.on_command(Command::Disarm, 600, r.t) == CommandResult::Ok);
    r.run(599.0);
    CHECK(f.state() == State::Disarmed && f.disarm_hold_active());
    r.run(1.0 + 29.0);
    CHECK(f.state() == State::Disarmed);
    r.run(2.0);
    CHECK(f.state() == State::Armed);  // still at 10 km: re-armed after the dwell
    CHECK(f.flight_s() >= flight_before);  // the flight clock was not reset
    // The hold is capped at max_disarm_hold_s (1 h) whatever is asked for.
    CHECK(f.on_command(Command::Disarm, 65535, r.t) == CommandResult::Ok);
    r.run(3600.0 + 35.0);
    CHECK(f.state() == State::Armed);
    // While held, the autonomous criteria are off - which is the point of
    // it, and the reason it is bounded.
    f.on_command(Command::Disarm, 300, r.t);
    r.set_range(500000.0);
    r.run(200.0);
    CHECK(f.state() == State::Disarmed && !r.ever_terminated);
    r.run(200.0);
    CHECK(f.state() == State::Terminated && r.first_reason == Reason::Range);
}

void scenario_time_backwards() {
    g_scenario = "clock: a backwards or repeated timestamp cannot shorten a timer";
    Ftu f(test_config());
    Sample s;
    s.gnss_valid = true;
    s.gnss_alt_m = 100.0;
    s.baro_valid = true;
    s.baro_alt_m = 100.0;
    for (uint64_t t = 0; t < 2000; t += 100) { s.now_ms = 100000 + t; f.step(s); }
    s.gnss_alt_m = s.baro_alt_m = 5000.0;
    s.now_ms = 110000; f.step(s);
    s.now_ms = 1000;   f.step(s);  // clock jumps back
    s.now_ms = 111000; f.step(s);
    CHECK(f.state() == State::Disarmed);  // 1 s of dwell so far, not "elapsed = huge"
    s.now_ms = 139999; f.step(s);
    CHECK(f.state() == State::Disarmed);
    s.now_ms = 140000; f.step(s);
    CHECK(f.state() == State::Armed);
}

void scenario_sensor_math() {
    g_scenario = "sensor math: MS5611 datasheet example";
    {
        // MS5611-01BA03 datasheet, "typical" column of the calculation table.
        const uint16_t prom[8] = {0, 40127, 36924, 23317, 23282, 33464, 28312, 0};
        const Ms5611Reading m = ms5611_compensate(prom, 9085466u, 8569150u);
        CHECK(m.ok);
        CHECK(std::fabs(m.temperature_c - 20.07) < 0.011);
        CHECK(std::fabs(m.pressure_pa - 100009.0) < 2.0);
        const uint16_t blank[8] = {0, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0};
        CHECK(!ms5611_compensate(blank, 9085466u, 8569150u).ok);
        const uint16_t zero[8] = {0, 0, 0, 0, 0, 0, 0, 0};
        CHECK(!ms5611_compensate(zero, 9085466u, 8569150u).ok);
        CHECK(!ms5611_compensate(prom, 0u, 8569150u).ok);
        CHECK(!ms5611_compensate(prom, 0xFFFFFFu, 8569150u).ok);
        // Cold branch (below -15 C) runs and stays monotonic in D1.
        // D2 = 7000000 is about -44 C with these coefficients; D1 = 4200000
        // is then about 47 hPa, i.e. roughly 20 km.
        const Ms5611Reading c1 = ms5611_compensate(prom, 4200000u, 7000000u);
        const Ms5611Reading c2 = ms5611_compensate(prom, 4300000u, 7000000u);
        CHECK(c1.ok && c2.ok && c1.temperature_c < -15.0 && c2.pressure_pa > c1.pressure_pa);
        CHECK(c1.pressure_pa > 3000.0 && c1.pressure_pa < 7000.0);
        // A conversion that would give a negative pressure is a fault, not a reading.
        CHECK(!ms5611_compensate(prom, 3000000u, 7000000u).ok);
    }
    g_scenario = "sensor math: standard atmosphere table (geometric altitude)";
    {
        // US Standard Atmosphere 1976 table values.
        CHECK(std::fabs(pressure_altitude_m(101325.0) - 0.0) < 1.0);
        CHECK(std::fabs(pressure_altitude_m(54048.0) - 5000.0) < 5.0);
        CHECK(std::fabs(pressure_altitude_m(26499.0) - 10000.0) < 5.0);
        CHECK(std::fabs(pressure_altitude_m(5529.3) - 20000.0) < 10.0);
        CHECK(std::fabs(pressure_altitude_m(2549.2) - 25000.0) < 10.0);
        CHECK(std::fabs(pressure_altitude_m(1197.0) - 30000.0) < 15.0);
        CHECK(std::isnan(pressure_altitude_m(0.0)));
        CHECK(std::isnan(pressure_altitude_m(-5.0)));
        CHECK(std::isnan(pressure_altitude_m(std::nan(""))));
        // Monotonic and continuous across the layer boundaries.
        double prev = pressure_altitude_m(110000.0);
        bool mono = true;
        for (double p = 109990.0; p > 300.0; p -= 10.0) {
            const double h = pressure_altitude_m(p);
            if (!(h > prev) || h - prev > 250.0) mono = false;
            prev = h;
        }
        CHECK(mono);
    }
    g_scenario = "sensor math: great-circle distance";
    {
        CHECK(std::fabs(great_circle_m(0, 0, 1, 0) - 111194.93) < 1.0);
        CHECK(std::fabs(great_circle_m(0, 0, 0, 1) - 111194.93) < 1.0);
        CHECK(great_circle_m(50.45, 30.52, 50.45, 30.52) == 0.0);
        CHECK(std::fabs(great_circle_m(60, 0, 60, 1) - 111194.93 * 0.5) < 10.0);
        CHECK(std::fabs(great_circle_m(0, 179.5, 0, -179.5) - 111194.93) < 1.0);  // date line
        CHECK(std::fabs(great_circle_m(0, 0, 0, 180) - 3.14159265358979 * 6371008.8) < 1.0);
    }
    g_scenario = "reason strings";
    {
        CHECK(std::strcmp(reason_str(Reason::None), "") == 0);
        CHECK(std::strcmp(reason_str(Reason::HeartbeatLoss), "heartbeat loss") == 0);
        CHECK(static_cast<int>(Reason::Commanded) == 1 && static_cast<int>(Reason::LinkLoss) == 5);
    }
}

// ---------------------------------------------------------------------------
// Protocol
// ---------------------------------------------------------------------------

const uint8_t kKey[proto::kKeyLen] = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                                      0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f};

void scenario_protocol_primitives() {
    g_scenario = "protocol: CRC-16 and SipHash-2-4 reference values";
    CHECK(proto::crc16_ccitt(reinterpret_cast<const uint8_t*>("123456789"), 9) == 0x29B1);
    CHECK(proto::crc16_ccitt(nullptr, 0) == 0xFFFF);
    // SipHash reference vectors: key 00..0f, message 00..(n-1).
    uint8_t msg[64];
    for (int i = 0; i < 64; ++i) msg[i] = static_cast<uint8_t>(i);
    CHECK(proto::siphash24(kKey, msg, 0) == 0x726fdb47dd0e0e31ULL);
    CHECK(proto::siphash24(kKey, msg, 1) == 0x74f839c593dc67fdULL);
    CHECK(proto::siphash24(kKey, msg, 7) == 0xab0200f58b01d137ULL);
    CHECK(proto::siphash24(kKey, msg, 8) == 0x93f5f5799a932462ULL);
    CHECK(proto::siphash24(kKey, msg, 15) == 0xa129ca6149be45e5ULL);
    CHECK(proto::siphash24(kKey, msg, 63) == 0x958a324ceb064572ULL);

    g_scenario = "protocol: time on air at SF10 / 125 kHz / CR 4/5";
    const double toa_t = proto::lora_time_on_air_ms(proto::kTelemetryLen);
    const double toa_c = proto::lora_time_on_air_ms(proto::kCommandLen);
    // Hand calculation: Tsym 8.192 ms; 24 B -> 8+25 payload symbols, 19 B -> 8+20;
    // plus 12.25 preamble symbols.
    CHECK(std::fabs(toa_t - 45.25 * 8.192) < 1e-6);
    CHECK(std::fabs(toa_c - 40.25 * 8.192) < 1e-6);
    CHECK(toa_t < 400.0);
    // Published reference point: SF7/125k/CR4-5, 8 preamble, 10-byte payload, CRC on = 41.216 ms.
    CHECK(std::fabs(proto::lora_time_on_air_ms(10, 7) - 41.216) < 1e-6);
    // SF12 engages low-data-rate optimisation: 10 bytes = 991.232 ms.
    CHECK(std::fabs(proto::lora_time_on_air_ms(10, 12) - 991.232) < 1e-6);
}

void scenario_protocol_telemetry() {
    g_scenario = "protocol: telemetry round trip and quantisation";
    proto::Telemetry t;
    t.vehicle_id = 7;
    t.lat_deg = -50.4501234;
    t.lon_deg = 179.9998765;
    t.gnss_alt_m = 26999.4;
    t.baro_alt_m = -120.0;
    t.state = 2;
    t.reason = 5;
    t.gate = 2;
    t.flags = proto::kFlagGnssValid | proto::kFlagGnssAirborne | proto::kFlagUnderVoltage;
    t.batt_mv = 4876;
    t.flight_s = 57601.0;
    t.ack = 0xBEEF;
    t.boot_count = 0x23;  // only the low nibble travels
    t.pulses = 4;
    t.rx_rejects = 9;
    uint8_t buf[64];
    CHECK(proto::encode_telemetry(t, buf, 10) == 0);
    CHECK(proto::encode_telemetry(t, buf, sizeof buf) == proto::kTelemetryLen);
    CHECK(proto::kTelemetryLen == 24);
    proto::Telemetry d;
    CHECK(proto::decode_telemetry(buf, proto::kTelemetryLen, d) == proto::Status::Ok);
    CHECK(d.vehicle_id == 7 && d.gate == 2 && d.state == 2 && d.reason == 5 && d.flags == t.flags);
    CHECK(std::fabs(d.lat_deg - t.lat_deg) < 6e-6);   // 0.6 m
    CHECK(std::fabs(d.lon_deg - t.lon_deg) < 1.1e-5); // 1.2 m
    CHECK(std::fabs(d.gnss_alt_m - 26999.0) < 0.01 && std::fabs(d.baro_alt_m + 120.0) < 0.01);
    CHECK(d.batt_mv == 4876 && d.flight_s == 57600.0 && d.ack == 0xBEEF);
    CHECK(d.boot_count == 3 && d.pulses == 4 && d.rx_rejects == 9);
    // Saturation instead of wrap-around.
    t.gnss_alt_m = 1e9; t.baro_alt_m = -1e9; t.flight_s = 1e9; t.pulses = 200;
    t.lat_deg = 123.0; t.lon_deg = std::nan("");
    proto::encode_telemetry(t, buf, sizeof buf);
    CHECK(proto::decode_telemetry(buf, proto::kTelemetryLen, d) == proto::Status::Ok);
    CHECK(d.gnss_alt_m == 64535.0 && d.baro_alt_m == -1000.0 && d.flight_s == 131070.0);
    CHECK(d.pulses == 15 && d.lat_deg == 90.0 && d.lon_deg == 0.0);
    // Every single-bit error is caught by the CRC.
    proto::encode_telemetry(t, buf, sizeof buf);
    int caught = 0;
    for (size_t bit = 0; bit < proto::kTelemetryLen * 8; ++bit) {
        buf[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
        if (proto::decode_telemetry(buf, proto::kTelemetryLen, d) == proto::Status::BadCrc) ++caught;
        buf[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
    }
    CHECK(caught == static_cast<int>(proto::kTelemetryLen * 8));
    CHECK(proto::decode_telemetry(buf, proto::kTelemetryLen - 1, d) == proto::Status::BadLength);
}

void scenario_protocol_commands() {
    g_scenario = "protocol: command authentication";
    uint8_t buf[64];
    proto::Command c;
    c.vehicle_id = 7;
    c.counter = 1000;
    c.cmd = proto::Cmd::Terminate;
    c.arg = proto::kTerminateConfirm;
    CHECK(proto::encode_command(c, kKey, buf, 5) == 0);
    CHECK(proto::encode_command(c, kKey, buf, sizeof buf) == proto::kCommandLen);
    CHECK(proto::kCommandLen == 19);
    proto::Command d;
    CHECK(proto::decode_command(buf, proto::kCommandLen, kKey, 7, d) == proto::Status::Ok);
    CHECK(d.counter == 1000 && d.cmd == proto::Cmd::Terminate && d.arg == proto::kTerminateConfirm);

    // CRC rejection: every single-bit error.
    int crc_caught = 0;
    for (size_t bit = 0; bit < proto::kCommandLen * 8; ++bit) {
        buf[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
        if (proto::decode_command(buf, proto::kCommandLen, kKey, 7, d) == proto::Status::BadCrc) ++crc_caught;
        buf[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
    }
    CHECK(crc_caught == static_cast<int>(proto::kCommandLen * 8));

    // MAC rejection: an attacker who can fix up the CRC still cannot change
    // any bit of the authenticated part or of the tag.
    int accepted = 0, mac_caught = 0;
    for (size_t bit = 0; bit < (proto::kCommandLen - 2) * 8; ++bit) {
        uint8_t forged[proto::kCommandLen];
        std::memcpy(forged, buf, sizeof forged);
        forged[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
        const uint16_t crc = proto::crc16_ccitt(forged, proto::kCommandLen - 2);
        forged[17] = static_cast<uint8_t>(crc);
        forged[18] = static_cast<uint8_t>(crc >> 8);
        const proto::Status st = proto::decode_command(forged, proto::kCommandLen, kKey, 7, d);
        if (st == proto::Status::Ok) ++accepted;
        if (st == proto::Status::BadMac) ++mac_caught;
    }
    CHECK(accepted == 0);
    CHECK(mac_caught >= static_cast<int>((proto::kCommandLen - 2 - 2) * 8));  // rest: version / vehicle

    // Wrong key.
    uint8_t other[proto::kKeyLen];
    std::memcpy(other, kKey, sizeof other);
    other[15] ^= 1;
    CHECK(proto::decode_command(buf, proto::kCommandLen, other, 7, d) == proto::Status::BadMac);
    // Wrong vehicle, wrong length, a telemetry packet offered as a command.
    CHECK(proto::decode_command(buf, proto::kCommandLen, kKey, 8, d) == proto::Status::WrongVehicle);
    CHECK(proto::decode_command(buf, proto::kCommandLen - 1, kKey, 7, d) == proto::Status::BadLength);
    CHECK(proto::decode_command(buf, proto::kCommandLen + 1, kKey, 7, d) == proto::Status::BadLength);
    uint8_t tele[64];
    proto::Telemetry t;
    t.vehicle_id = 7;
    proto::encode_telemetry(t, tele, sizeof tele);
    CHECK(proto::decode_command(tele, proto::kTelemetryLen, kKey, 7, d) == proto::Status::BadLength);
    // Correctly keyed TERMINATE without its confirm word, and an unknown command code.
    c.arg = 0;
    proto::encode_command(c, kKey, buf, sizeof buf);
    CHECK(proto::decode_command(buf, proto::kCommandLen, kKey, 7, d) == proto::Status::BadCommand);
    c.cmd = static_cast<proto::Cmd>(9);
    proto::encode_command(c, kKey, buf, sizeof buf);
    CHECK(proto::decode_command(buf, proto::kCommandLen, kKey, 7, d) == proto::Status::BadCommand);

    g_scenario = "protocol: replay rejection";
    proto::CommandReceiver rx(kKey, 7, 500);  // 500 = counter loaded from flash
    uint8_t p1[32], p2[32], p3[32];
    c.cmd = proto::Cmd::Ping; c.arg = 0;
    c.counter = 501; proto::encode_command(c, kKey, p1, sizeof p1);
    c.counter = 502; proto::encode_command(c, kKey, p2, sizeof p2);
    c.counter = 500; proto::encode_command(c, kKey, p3, sizeof p3);
    CHECK(rx.accept(p3, proto::kCommandLen, d) == proto::Status::Replay);  // equal to stored
    CHECK(rx.accept(p2, proto::kCommandLen, d) == proto::Status::Ok && d.counter == 502);
    CHECK(rx.last_counter() == 502);
    CHECK(rx.accept(p2, proto::kCommandLen, d) == proto::Status::Replay);  // exact replay
    CHECK(rx.accept(p1, proto::kCommandLen, d) == proto::Status::Replay);  // older, never seen
    CHECK(rx.last_counter() == 502);
    CHECK(rx.rejects_replay() == 3 && rx.rejects() == 3);
    // A forged packet with a huge counter must not move the window.
    c.counter = 0xFFFFFFF0u;
    proto::encode_command(c, other, p3, sizeof p3);
    CHECK(rx.accept(p3, proto::kCommandLen, d) == proto::Status::BadMac);
    CHECK(rx.last_counter() == 502 && rx.rejects_mac() == 1);
    c.counter = 503; proto::encode_command(c, kKey, p1, sizeof p1);
    CHECK(rx.accept(p1, proto::kCommandLen, d) == proto::Status::Ok);
    // Corruption is counted separately; another vehicle's traffic is not counted.
    p1[4] ^= 0x10;
    CHECK(rx.accept(p1, proto::kCommandLen, d) == proto::Status::BadCrc);
    CHECK(rx.rejects_crc() == 1);
    c.vehicle_id = 8; c.counter = 600; proto::encode_command(c, kKey, p1, sizeof p1);
    const uint8_t before = rx.rejects();
    CHECK(rx.accept(p1, proto::kCommandLen, d) == proto::Status::WrongVehicle);
    CHECK(rx.rejects() == before && rx.last_counter() == 503);
    // Counter 0 is never acceptable to a fresh receiver.
    proto::CommandReceiver fresh(kKey, 7, 0);
    c.vehicle_id = 7; c.counter = 0; proto::encode_command(c, kKey, p1, sizeof p1);
    CHECK(fresh.accept(p1, proto::kCommandLen, d) == proto::Status::Replay);
}

void scenario_end_to_end() {
    g_scenario = "end to end: ground packet -> receiver -> unit; a recording of it does nothing";
    Ftu f(test_config());
    Rig r(f);
    r.climb_to(5000.0);
    proto::CommandReceiver rx(kKey, 7, 0);
    proto::Command c, d;
    c.vehicle_id = 7;
    uint8_t arm[32], term[32], disarm[32];
    c.counter = 10; c.cmd = proto::Cmd::Disarm; c.arg = 60;
    proto::encode_command(c, kKey, disarm, sizeof disarm);
    c.counter = 11; c.cmd = proto::Cmd::Arm; c.arg = 0;
    proto::encode_command(c, kKey, arm, sizeof arm);
    c.counter = 12; c.cmd = proto::Cmd::Terminate; c.arg = proto::kTerminateConfirm;
    proto::encode_command(c, kKey, term, sizeof term);

    auto deliver = [&](const uint8_t* pkt) -> proto::Status {
        const proto::Status st = rx.accept(pkt, proto::kCommandLen, d);
        if (st == proto::Status::Ok) {
            Command cmd = Command::Ping;
            if (d.cmd == proto::Cmd::Arm) cmd = Command::Arm;
            if (d.cmd == proto::Cmd::Disarm) cmd = Command::Disarm;
            if (d.cmd == proto::Cmd::Terminate) cmd = Command::Terminate;
            f.on_command(cmd, d.arg, r.t);
        }
        return st;
    };
    CHECK(deliver(disarm) == proto::Status::Ok);
    r.run(1.0);
    CHECK(f.state() == State::Disarmed);
    CHECK(deliver(arm) == proto::Status::Ok);
    r.run(1.0);
    CHECK(f.state() == State::Armed);
    // An eavesdropper replays the recorded DISARM to switch the unit off.
    CHECK(deliver(disarm) == proto::Status::Replay);
    r.run(1.0);
    CHECK(f.state() == State::Armed);
    CHECK(deliver(term) == proto::Status::Ok);
    r.run(300.0);
    CHECK(f.state() == State::Terminated && f.reason() == Reason::Commanded);
    CHECK(f.sequencer().pulses_started() == 6);
    // Replaying TERMINATE must not buy extra cutter cycles either.
    CHECK(deliver(term) == proto::Status::Replay);
    r.run(300.0);
    CHECK(f.sequencer().pulses_started() == 6);
}

struct Scenario {
    void (*fn)();
    const char* name;
};

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::printf("usage: %s <vectors.csv>\n", argv[0]);
        return 2;
    }

    std::printf("== (a) parity with aiur.strato.guidance.Geofence ==\n");
    const ParityResult p = run_parity(argv[1]);
    std::printf("  defaults checked:   %ld, mismatches %ld\n", p.defaults, p.default_mismatches);
    std::printf("  vectors replayed:   %ld, mismatches %ld\n", p.vectors, p.mismatches);
    std::printf("  agreed, by reason:  none %ld, commanded %ld, range %ld, altitude %ld, "
                "flight time %ld, link loss %ld\n",
                p.by_reason[0], p.by_reason[1], p.by_reason[2], p.by_reason[3], p.by_reason[4],
                p.by_reason[5]);
    std::printf("  barometer altitude: %ld points vs atmosphere.pressure_altitude_m, "
                "%ld outside 5 m, worst %.3f m\n", p.baro, p.baro_mismatches, p.baro_worst_m);
    std::printf("  PARITY %s\n", p.ok ? "PASS" : "FAIL");

    std::printf("== (b) firmware-only scenarios ==\n");
    const Scenario scenarios[] = {
        {scenario_bench_never_arms, "bench: never arms, never fires"},
        {scenario_spike_does_not_arm, "arming: dwell"},
        {scenario_arms_in_climb, "arming: climb"},
        {scenario_arms_on_one_source, "arming: single source / forced"},
        {scenario_command_needs_arm, "command: two-step on the ground"},
        {scenario_heartbeat, "heartbeat timer"},
        {scenario_range_and_confirmation, "range + confirmation"},
        {scenario_gnss_loss_holds_range, "range with GNSS lost"},
        {scenario_altitude_crosscheck, "altitude cross-check"},
        {scenario_clock_criteria, "flight time, link loss, precedence"},
        {scenario_latch, "latch"},
        {scenario_sequencer, "cutter sequencer"},
        {scenario_persistence, "persistence across resets"},
        {scenario_disarm_hold, "DISARM hold"},
        {scenario_time_backwards, "clock monotonicity"},
        {scenario_sensor_math, "sensor math"},
        {scenario_protocol_primitives, "protocol: CRC, MAC, time on air"},
        {scenario_protocol_telemetry, "protocol: telemetry"},
        {scenario_protocol_commands, "protocol: CRC / MAC / replay rejection"},
        {scenario_end_to_end, "end to end"},
    };
    int scenarios_failed = 0;
    for (const Scenario& sc : scenarios) {
        const int checks0 = g_checks, failed0 = g_failed;
        sc.fn();
        const bool ok = g_failed == failed0;
        if (!ok) ++scenarios_failed;
        std::printf("  %-4s %-42s %9d checks\n", ok ? "ok" : "FAIL", sc.name, g_checks - checks0);
    }
    const int n_scen = static_cast<int>(sizeof scenarios / sizeof scenarios[0]);
    std::printf("  SCENARIOS %s: %d of %d passed, %d checks, %d failed\n",
                scenarios_failed == 0 ? "PASS" : "FAIL", n_scen - scenarios_failed, n_scen,
                g_checks, g_failed);
    std::printf("  time on air SF10/125k/CR4-5: telemetry %zu B = %.1f ms, command %zu B = %.1f ms\n",
                proto::kTelemetryLen, proto::lora_time_on_air_ms(proto::kTelemetryLen),
                proto::kCommandLen, proto::lora_time_on_air_ms(proto::kCommandLen));

    const bool all = p.ok && scenarios_failed == 0;
    std::printf("== %s ==\n", all ? "ALL PASS" : "FAILED");
    return all ? 0 : 1;
}
