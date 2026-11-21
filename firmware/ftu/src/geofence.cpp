// See geofence.hpp for the structure.  Comments here explain decisions, not
// syntax.
#include "geofence.hpp"

#include <cmath>

namespace ftu {

namespace {
const double kNaN = std::numeric_limits<double>::quiet_NaN();
const double kPi = 3.14159265358979323846;
}  // namespace

// ---------------------------------------------------------------------------
// Layer 1
// ---------------------------------------------------------------------------

const char* reason_str(Reason r) {
    switch (r) {
        case Reason::None: return "";
        case Reason::Commanded: return "commanded";
        case Reason::Range: return "range";
        case Reason::Altitude: return "altitude";
        case Reason::FlightTime: return "flight time";
        case Reason::LinkLoss: return "link loss";
        case Reason::HeartbeatLoss: return "heartbeat loss";
    }
    return "";
}

Decision must_terminate(const GeofenceLimits& limits, double range_m, double altitude_m,
                        double flight_s, bool commanded, double link_lost_s,
                        double link_timeout_s) {
    // Same statements, same order, same operators as the Python.
    if (commanded) return {true, Reason::Commanded};
    if (range_m > limits.max_range_m) return {true, Reason::Range};
    if (altitude_m > limits.max_altitude_m) return {true, Reason::Altitude};
    if (flight_s > limits.max_flight_s) return {true, Reason::FlightTime};
    if (link_lost_s > link_timeout_s) return {true, Reason::LinkLoss};
    return {false, Reason::None};
}

// ---------------------------------------------------------------------------
// Sensor mathematics
// ---------------------------------------------------------------------------

double great_circle_m(double lat1_deg, double lon1_deg, double lat2_deg, double lon2_deg) {
    const double r = 6371008.8;  // IUGG mean radius
    const double d2r = kPi / 180.0;
    const double p1 = lat1_deg * d2r, p2 = lat2_deg * d2r;
    const double dp = (lat2_deg - lat1_deg) * d2r;
    const double dl = (lon2_deg - lon1_deg) * d2r;
    const double a = std::sin(dp / 2) * std::sin(dp / 2) +
                     std::cos(p1) * std::cos(p2) * std::sin(dl / 2) * std::sin(dl / 2);
    // Haversine: well conditioned at the short ranges that matter here.
    return 2.0 * r * std::atan2(std::sqrt(a), std::sqrt(a < 1.0 ? 1.0 - a : 0.0));
}

double pressure_altitude_m(double p) {
    if (!(p > 0.0)) return kNaN;  // also catches NaN
    // US Standard Atmosphere 1976, layer by layer, in geopotential metres.
    const double R = 287.053, g = 9.80665;
    double h;
    if (p >= 22632.06) {  // 0..11 km, lapse -6.5 K/km
        h = (288.15 / 0.0065) * (1.0 - std::pow(p / 101325.0, R * 0.0065 / g));
    } else if (p >= 5474.889) {  // 11..20 km, isothermal 216.65 K
        h = 11000.0 - (R * 216.65 / g) * std::log(p / 22632.06);
    } else if (p >= 868.0187) {  // 20..32 km, lapse +1.0 K/km
        h = 20000.0 + (216.65 / 0.001) * (std::pow(p / 5474.889, -R * 0.001 / g) - 1.0);
    } else {  // 32..47 km, lapse +2.8 K/km
        h = 32000.0 + (228.65 / 0.0028) * (std::pow(p / 868.0187, -R * 0.0028 / g) - 1.0);
    }
    // Geopotential -> geometric.  115 m at 27 km: not negligible against a
    // limit that the GNSS reports geometrically.
    const double r0 = 6356766.0;
    return r0 * h / (r0 - h);
}

Ms5611Reading ms5611_compensate(const uint16_t prom[8], uint32_t d1, uint32_t d2) {
    Ms5611Reading out{false, kNaN, kNaN};
    // A sensor that is absent or still in reset reads all-zeros or all-ones.
    bool blank = true;
    for (int i = 1; i <= 6; ++i) {
        if (prom[i] != 0x0000 && prom[i] != 0xFFFF) blank = false;
    }
    if (blank || d1 == 0 || d2 == 0 || d1 >= 0xFFFFFF || d2 >= 0xFFFFFF) return out;

    const int64_t c1 = prom[1], c2 = prom[2], c3 = prom[3], c4 = prom[4], c5 = prom[5],
                  c6 = prom[6];
    // Divisions, not shifts: the intermediate values go negative in the cold
    // and a right shift of a negative number is not what the datasheet means.
    const int64_t dt = static_cast<int64_t>(d2) - c5 * 256;
    int64_t temp = 2000 + dt * c6 / 8388608;
    int64_t off = c2 * 65536 + c4 * dt / 128;
    int64_t sens = c1 * 32768 + c3 * dt / 256;
    if (temp < 2000) {
        const int64_t t2 = dt * dt / 2147483648LL;
        const int64_t d = temp - 2000;
        int64_t off2 = 5 * d * d / 2;
        int64_t sens2 = 5 * d * d / 4;
        if (temp < -1500) {
            const int64_t e = temp + 1500;
            off2 += 7 * e * e;
            sens2 += 11 * e * e / 2;
        }
        temp -= t2;
        off -= off2;
        sens -= sens2;
    }
    const int64_t p = (static_cast<int64_t>(d1) * sens / 2097152 - off) / 32768;  // Pa
    // The part is specified 10..1200 hPa, -40..85 C.  Allow a margin (it is
    // flown below -40 C) but reject numbers that can only be a bus fault.
    if (p < 300 || p > 130000 || temp < -9000 || temp > 9000) return out;
    out.ok = true;
    out.pressure_pa = static_cast<double>(p);
    out.temperature_c = static_cast<double>(temp) / 100.0;
    return out;
}

// ---------------------------------------------------------------------------
// Cutter sequencer
// ---------------------------------------------------------------------------

void CutterSequencer::start(uint64_t now_ms, uint8_t pulses_already_started) {
    if (stop_ != SequencerStop::NotStarted) return;
    pulses_started_ = pulses_already_started;
    stop_ = SequencerStop::Running;
    gate_ = Gate::None;
    phase_start_ms_ = now_ms;
    first_gap_ = true;
}

void CutterSequencer::extend_one_cycle(uint64_t now_ms) {
    if (stop_ != SequencerStop::Complete && stop_ != SequencerStop::UnderVoltage) return;
    if (pulses_started_ > 250) return;  // counter is 8 bits on the wire and in flash
    const int need = static_cast<int>(pulses_started_) + 2 - 2 * static_cast<int>(cfg_->cycles);
    if (need > static_cast<int>(extra_pulses_)) extra_pulses_ = static_cast<uint8_t>(need);
    stop_ = SequencerStop::Running;
    gate_ = Gate::None;
    phase_start_ms_ = now_ms;
    first_gap_ = true;
}

Gate CutterSequencer::step(uint64_t now_ms, bool batt_valid, uint16_t batt_mv) {
    if (stop_ != SequencerStop::Running) {
        gate_ = Gate::None;
        return gate_;
    }
    const uint64_t elapsed = now_ms >= phase_start_ms_ ? now_ms - phase_start_ms_ : 0;

    if (gate_ != Gate::None) {
        if (elapsed >= cfg_->pulse_ms) {
            gate_ = Gate::None;
            phase_start_ms_ = now_ms;
        } else if (batt_valid && batt_mv < cfg_->uv_load_mv) {
            // The rail is collapsing under this pulse.  Let go before the
            // regulator drops out: a reset here costs the beacon and gains
            // nothing, because the wire is not heating at this voltage anyway.
            gate_ = Gate::None;
            phase_start_ms_ = now_ms;
            if (uv_aborts_ < 255) ++uv_aborts_;
        }
        return gate_;
    }

    // Both gates are off here, and have been since phase_start_ms_.
    if (!first_gap_ && elapsed < cfg_->gap_ms) return gate_;
    if (pulses_started_ >= total_pulses()) {
        stop_ = SequencerStop::Complete;
        return gate_;
    }
    if (batt_valid && batt_mv < cfg_->uv_rest_mv) {
        // Resting voltage after a recovery gap is the honest state of the
        // cells.  If it is this low the next pulse cannot cut and can only
        // reset the unit.  If no voltage measurement is fitted (batt_valid
        // false) the sequencer fires blind: failing towards cutting.
        stop_ = SequencerStop::UnderVoltage;
        return gate_;
    }
    first_gap_ = false;
    gate_ = (pulses_started_ % 2u == 0u) ? Gate::A : Gate::B;
    ++pulses_started_;
    dirty_ = true;
    phase_start_ms_ = now_ms;
    return gate_;
}

// ---------------------------------------------------------------------------
// The unit
// ---------------------------------------------------------------------------

void Ftu::restore(const Persist& p) {
    if (stepped_) return;
    if (p.state != static_cast<uint8_t>(State::Armed) &&
        p.state != static_cast<uint8_t>(State::Terminated)) {
        return;  // DISARMED (or garbage): start clean, take new references
    }
    state_ = static_cast<State>(p.state);
    reason_ = (p.reason <= static_cast<uint8_t>(Reason::HeartbeatLoss))
                  ? static_cast<Reason>(p.reason) : Reason::None;
    if (state_ != State::Terminated) reason_ = Reason::None;
    restored_pulses_ = p.pulses_started;
    flight_offset_s_ = static_cast<double>(p.flight_s);
    flight_s_ = flight_offset_s_;
    flight_s_saved_ = p.flight_s;
    gnss_ref_set_ = p.gnss_ref_set;
    home_lat_ = p.home_lat_deg;
    home_lon_ = p.home_lon_deg;
    ref_gnss_alt_ = p.ref_gnss_alt_m;
    baro_ref_set_ = p.baro_ref_set;
    ref_baro_alt_ = p.ref_baro_alt_m;
    restore_pending_ = true;
}

Persist Ftu::persist() const {
    Persist p;
    p.state = static_cast<uint8_t>(state_);
    p.reason = static_cast<uint8_t>(reason_);
    p.pulses_started = restore_pending_ ? restored_pulses_ : seq_.pulses_started();
    p.flight_s = flight_s_ > 0.0 ? static_cast<uint32_t>(flight_s_) : 0u;
    p.gnss_ref_set = gnss_ref_set_;
    p.home_lat_deg = home_lat_;
    p.home_lon_deg = home_lon_;
    p.ref_gnss_alt_m = ref_gnss_alt_;
    p.baro_ref_set = baro_ref_set_;
    p.ref_baro_alt_m = ref_baro_alt_;
    return p;
}

void Ftu::arm(uint64_t now_ms) {
    state_ = State::Armed;
    armed_at_ms_ = now_ms;
    arm_since_valid_ = false;
    hold_active_ = false;
    hb_absent_valid_ = false;
    hb_back_valid_ = false;
    range_since_valid_ = false;
    alt_since_valid_ = false;
    commanded_ = false;
    dirty_ = true;
}

void Ftu::latch(Reason r, uint64_t now_ms) {
    // The latch: there is no transition out of Terminated anywhere in this
    // file, and restore() brings it back after a reset.  A cut-down that has
    // started and then "changes its mind" leaves a vehicle with a hot wire
    // half through its suspension.
    if (state_ == State::Terminated) return;
    state_ = State::Terminated;
    reason_ = r;
    dirty_ = true;
    seq_.start(now_ms, 0);
}

void Ftu::update_references(const Sample& s) {
    // Ground references are taken once, from the first valid samples after a
    // power-on in the DISARMED state, and never moved afterwards.  A slowly
    // tracking reference would follow a slow ascent and never arm.
    if (state_ != State::Disarmed) return;
    if (!gnss_ref_set_ && s.gnss_valid) {
        sum_lat_ += s.lat_deg;
        sum_lon_ += s.lon_deg;
        sum_galt_ += s.gnss_alt_m;
        if (++gnss_ref_n_ >= cfg_.ref_samples) {
            home_lat_ = sum_lat_ / gnss_ref_n_;
            home_lon_ = sum_lon_ / gnss_ref_n_;
            ref_gnss_alt_ = sum_galt_ / gnss_ref_n_;
            gnss_ref_set_ = true;
            dirty_ = true;
        }
    }
    if (!baro_ref_set_ && s.baro_valid) {
        sum_balt_ += s.baro_alt_m;
        if (++baro_ref_n_ >= cfg_.ref_samples) {
            ref_baro_alt_ = sum_balt_ / baro_ref_n_;
            baro_ref_set_ = true;
            dirty_ = true;
        }
    }
}

void Ftu::update_altitude(const Sample& s) {
    // Which altitude does the ceiling test see?
    //
    // GNSS is the higher-confidence source for *absolute* altitude: it is
    // geometric, which is what the 27 km limit is written in, and with a 3-D
    // fix its error is tens of metres at any height (given the airborne
    // dynamic model - see main.cpp).  The barometer reports pressure altitude:
    // at 27 km the pressure is ~18 hPa, the MS5611's +-2.5 hPa is ~0.9 km
    // there, and the real atmosphere is not the standard one.  So: GNSS when
    // it is valid, barometer when it is not.
    //
    // When both are valid and differ by more than alt_disagree_m, one of them
    // is wrong and this unit cannot tell which.  The cases:
    //   - GNSS frozen or clamped low, barometer right  -> vehicle may be above
    //     the ceiling while GNSS says it is not;
    //   - barometer port iced at a low altitude, GNSS right -> GNSS is higher
    //     and is used either way;
    //   - barometer failed towards low pressure, GNSS right -> the higher
    //     value is wrong and the flight is ended early.
    // Taking the higher value turns "wrong" into "early" in the third case and
    // "never" into "on time" in the first.  An early cut-down ends a mission
    // on a parachute inside the planned area; a missed ceiling leaves a
    // vehicle above its approved envelope with no one aware of it.  So the
    // higher value is used - for this criterion only.  It is not used for
    // range (the barometer says nothing about position).  The confirm_ms
    // persistence in evaluate() keeps a single wild sample from doing this.
    //
    // No QNH or launch-site offset is applied to the barometer.  An offset
    // learned on the ground is worth < 300 m; learned from references taken
    // at different times (a late first fix) it could be kilometres wrong, and
    // that error would feed straight into the "higher value" rule above.
    if (s.gnss_valid && s.baro_valid) {
        const double diff = std::fabs(s.gnss_alt_m - s.baro_alt_m);
        alt_disagree_ = diff > cfg_.alt_disagree_m;
        altitude_m_ = (alt_disagree_ && s.baro_alt_m > s.gnss_alt_m) ? s.baro_alt_m : s.gnss_alt_m;
    } else if (s.gnss_valid) {
        alt_disagree_ = false;
        altitude_m_ = s.gnss_alt_m;
    } else if (s.baro_valid) {
        alt_disagree_ = false;
        altitude_m_ = s.baro_alt_m;
    } else {
        // Neither source: hold the last value.  It is stale, and that is
        // stated in the telemetry flags; flight time, link loss and ground
        // command do not depend on it.
        alt_disagree_ = false;
    }

    // Arming compares each source with its *own* ground reference, so sensor
    // offsets cancel, and either source may arm.  This is deliberately the
    // permissive choice.  Armed-on-the-ground is one fault away from firing
    // (a criterion must then also become true, and procedures in
    // docs/strato/ftu.md cover the bench).  Disarmed-in-flight is the failure
    // with no backstop at all: every autonomous criterion is disabled.
    const bool by_gnss = s.gnss_valid && gnss_ref_set_ &&
                         (s.gnss_alt_m - ref_gnss_alt_) > cfg_.arm_height_m;
    const bool by_baro = s.baro_valid && baro_ref_set_ &&
                         (s.baro_alt_m - ref_baro_alt_) > cfg_.arm_height_m;
    above_arm_height_ = by_gnss || by_baro;

    if (s.gnss_valid) {
        range_m_ = gnss_ref_set_
                       ? great_circle_m(home_lat_, home_lon_, s.lat_deg, s.lon_deg) : kNaN;
    }
    // else: hold the last range.  Without a position the fence cannot be
    // evaluated; see "What is not covered" in docs/strato/ftu.md.
}

void Ftu::update_heartbeat(const Sample& s, uint64_t now_ms) {
    if (s.hb_edges > 0) {
        hb_last_edge_ms_ = now_ms;
        hb_edge_seen_ = true;
    }
    hb_present_ = hb_edge_seen_ && (now_ms - hb_last_edge_ms_) < cfg_.hb_silence_ms;

    if (state_ != State::Armed || !cfg_.heartbeat_required) {
        hb_absent_valid_ = false;
        hb_back_valid_ = false;
        return;
    }
    // Why loss of heartbeat does not cut down at once.
    //
    // The heartbeat says the autopilot's processor is running.  Its absence
    // has benign causes that clear by themselves - an autopilot reboot, a
    // watchdog reset, a brown-out while the heater cycles, a connector that
    // has gone intermittent in the cold - and a cut-down cannot be taken back.
    // A vehicle with a dead autopilot is also not yet a hazard: it is a free
    // balloon that this unit is still tracking and still fencing by range,
    // altitude, time and link.  The grace period gives the autopilot time to
    // come back and gives the ground time to choose where the descent
    // happens (TERMINATE) instead of taking wherever the vehicle happens to
    // be.  After hb_grace_ms without it, the vehicle is treated as
    // uncontrolled and is brought down.
    //
    // Why the timer is not reset by a single edge.  An autopilot in a reboot
    // loop emits a few edges every cycle.  If each edge reset the timer the
    // unit would wait for ever on a vehicle nobody is flying.  The heartbeat
    // must be back continuously for hb_recover_ms before the timer is
    // cancelled; until then it keeps running.
    if (!hb_present_) {
        hb_back_valid_ = false;
        if (!hb_absent_valid_) {
            hb_absent_valid_ = true;
            hb_absent_since_ms_ = now_ms;
        }
    } else if (hb_absent_valid_) {
        if (!hb_back_valid_) {
            hb_back_valid_ = true;
            hb_back_since_ms_ = now_ms;
        } else if (now_ms - hb_back_since_ms_ >= cfg_.hb_recover_ms) {
            hb_absent_valid_ = false;
            hb_back_valid_ = false;
        }
    }
}

void Ftu::evaluate(uint64_t now_ms) {
    flight_s_ = flight_offset_s_ + static_cast<double>(now_ms - armed_at_ms_) / 1000.0;
    // Link age counts from the later of arming and the last authenticated
    // uplink, so time spent on the pad before launch is not held against it.
    const uint64_t link_ref =
        (uplink_seen_ && last_uplink_ms_ > armed_at_ms_) ? last_uplink_ms_ : armed_at_ms_;
    link_lost_s_ = static_cast<double>(now_ms - link_ref) / 1000.0;

    // Confirmation.  Range and altitude come from sensors, and one bad fix
    // (a multipath jump, a corrupted I2C read) would otherwise be enough for
    // an irreversible action.  Each must stay tripped for confirm_ms.  Each
    // has its own timer so that one flickering criterion cannot keep
    // resetting the other.  Flight time and link loss are derived from the
    // unit's own monotonic clock and a command is authenticated; none of the
    // three can glitch, so none is delayed.
    //
    // The trip tests go through must_terminate() with the other inputs set
    // to NaN (which never trips), so the comparison that is confirmed is the
    // reference's comparison and not a re-implementation of it.
    const bool range_trip =
        must_terminate(cfg_.limits, range_m_, kNaN, kNaN, false, kNaN, kNaN).terminate;
    const bool alt_trip =
        must_terminate(cfg_.limits, kNaN, altitude_m_, kNaN, false, kNaN, kNaN).terminate;
    if (!range_trip) {
        range_since_valid_ = false;
    } else if (!range_since_valid_) {
        range_since_valid_ = true;
        range_since_ms_ = now_ms;
    }
    if (!alt_trip) {
        alt_since_valid_ = false;
    } else if (!alt_since_valid_) {
        alt_since_valid_ = true;
        alt_since_ms_ = now_ms;
    }
    const bool range_ok = range_since_valid_ && (now_ms - range_since_ms_) >= cfg_.confirm_ms;
    const bool alt_ok = alt_since_valid_ && (now_ms - alt_since_ms_) >= cfg_.confirm_ms;

    // The decision itself: one call to the reference function, so the
    // precedence of reasons is the reference's.
    const Decision d = must_terminate(cfg_.limits, range_ok ? range_m_ : kNaN,
                                      alt_ok ? altitude_m_ : kNaN, flight_s_, commanded_,
                                      link_lost_s_, cfg_.link_timeout_s);
    if (d.terminate) {
        latch(d.reason, now_ms);
        return;
    }
    // Firmware-only criterion, lowest precedence.
    if (hb_absent_valid_ && (now_ms - hb_absent_since_ms_) >= cfg_.hb_grace_ms) {
        latch(Reason::HeartbeatLoss, now_ms);
    }
}

Outputs Ftu::step(const Sample& s) {
    // Time never runs backwards inside the unit, whatever the caller passes.
    uint64_t now = s.now_ms;
    if (stepped_ && now < now_ms_) now = now_ms_;
    now_ms_ = now;
    if (!stepped_) {
        stepped_ = true;
        if (restore_pending_) {
            restore_pending_ = false;
            // Clocks restart at the reset; the flight clock carries its saved
            // offset.  Link-loss and heartbeat timers restart from zero: a
            // reset loop shorter than those timers defeats them, and flight
            // time is then the backstop (documented as a limitation).
            armed_at_ms_ = now;
            if (state_ == State::Terminated) seq_.start(now, restored_pulses_);
        }
    }

    update_references(s);
    update_altitude(s);
    update_heartbeat(s, now);

    if (state_ == State::Disarmed) {
        if (hold_active_ && now >= hold_until_ms_) hold_active_ = false;
        if (hold_active_ || !above_arm_height_) {
            arm_since_valid_ = false;
        } else if (!arm_since_valid_) {
            arm_since_valid_ = true;
            arm_since_ms_ = now;
        } else if (now - arm_since_ms_ >= cfg_.arm_dwell_ms) {
            arm(now);
        }
    } else if (state_ == State::Armed) {
        evaluate(now);
    } else {
        flight_s_ = flight_offset_s_ + static_cast<double>(now - armed_at_ms_) / 1000.0;
    }

    Gate gate = Gate::None;
    if (state_ == State::Terminated) {
        gate = seq_.step(now, s.batt_valid, s.batt_mv);
        if (seq_.take_dirty()) dirty_ = true;
    }

    // Save the flight clock once a minute so a reset costs at most that much.
    if (state_ != State::Disarmed && flight_s_ >= static_cast<double>(flight_s_saved_) + 60.0) {
        flight_s_saved_ = static_cast<uint32_t>(flight_s_);
        dirty_ = true;
    }

    Outputs out{gate, state_, reason_, dirty_};
    dirty_ = false;
    return out;
}

CommandResult Ftu::on_command(Command cmd, uint16_t arg, uint64_t now_ms) {
    if (now_ms < now_ms_) now_ms = now_ms_;
    uplink_seen_ = true;
    last_uplink_ms_ = now_ms;

    switch (cmd) {
        case Command::Ping:
            return CommandResult::Ok;

        case Command::Arm:
            // Manual override of the arming rule: for the bench cutter test,
            // and for a flight in which both altitude sources failed before
            // the climb was recognised.
            if (state_ == State::Disarmed) arm(now_ms);
            return CommandResult::Ok;

        case Command::Disarm: {
            if (state_ == State::Terminated) return CommandResult::RefusedLatched;
            if (state_ == State::Armed) {
                flight_offset_s_ += static_cast<double>(now_ms - armed_at_ms_) / 1000.0;
                flight_s_ = flight_offset_s_;
                state_ = State::Disarmed;
                dirty_ = true;
            }
            commanded_ = false;
            arm_since_valid_ = false;
            hb_absent_valid_ = false;
            hb_back_valid_ = false;
            range_since_valid_ = false;
            alt_since_valid_ = false;
            // The hold is bounded and it expires by itself: a unit that is
            // still above the arming height when it expires re-arms under the
            // normal rule.  An unbounded inhibit would be a way to switch the
            // FTU off from the ground and then lose the link.
            uint32_t hold_s = arg;
            if (hold_s > cfg_.max_disarm_hold_s) hold_s = cfg_.max_disarm_hold_s;
            hold_active_ = hold_s > 0;
            hold_until_ms_ = now_ms + static_cast<uint64_t>(hold_s) * 1000u;
            return CommandResult::Ok;
        }

        case Command::Terminate:
            if (state_ == State::Disarmed) {
                // Two deliberate steps (ARM, then TERMINATE) to energise a
                // cutter on the ground.
                return CommandResult::RefusedDisarmed;
            }
            if (state_ == State::Armed) {
                commanded_ = true;  // latched by the next step(), via must_terminate()
            } else {
                // Already terminated and the sequence has stopped: the
                // operator is asking for another attempt (e.g. a cutter that
                // did not part the line at -60 C).  One more A/B cycle.
                seq_.extend_one_cycle(now_ms);
            }
            return CommandResult::Ok;
    }
    return CommandResult::Ok;
}

}  // namespace ftu
