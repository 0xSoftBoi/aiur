--[[
aiur_inner.lua - heading / speed inner loop with a thrust floor, for a hull
whose only yaw authority is a gimballed stern thruster.

Why.  Stock ArduRover limits steering to throttle x tan(MOT_VEC_ANGLEMAX) and
cuts the throttle whenever it wants to slow, stop or reverse.  On this hull
zero throttle is zero rudder and the hull is yaw-unstable, so every throttle
cut is a heading loss (docs/strato/ardupilot-sitl.md, section 7.2).  This
script is the in-repo law, aiur.strato.flight6dof.FlightController.command,
run on the autopilot:

    N      = Izz (wn^2 e_psi - 2 zeta wn r)                 yaw moment demand
    T_spd  = Kp e_v + integral(Ki e_v)                      speed loop
    T      = max(T_spd, min(Tmax, max(floor Tmax min(1, |e_psi|/0.2),
                                      |N| / (arm sin(limit)))))   thrust floor
    gimbal = asin(clamp(-N / (arm T_now)))                  through CURRENT thrust

What it replaces, and what it does not.  Rover keeps the EKF, arming,
modes, failsafes, logging and telemetry.  In GUIDED the companion sends the
same message as for stock Rover - SET_ATTITUDE_TARGET, yaw in the quaternion,
thrust = signed ground speed / WP_SPEED - and Rover processes it as usual.
The script reads the same message off the MAVLink stream and overrides the
steering and throttle *outputs* with a 200 ms timeout
(SRV_Channels:set_output_pwm_chan_timeout).  If the script stops, errors, is
disabled (AIN_ENABLE 0) or the demand is older than 3 s, the override lapses
and Rover's own controllers, which never stopped running, have the outputs
back within 200 ms.

Speed.  The demand is ground speed along the commanded heading, as for stock
Rover.  If an airspeed estimate exists (ARSPD_TYPE set; in SITL the plant
sends "airspeed" over JSON) the speed error is min(ground-speed error,
AIN_ASPD_MAX - airspeed): the airspeed limit lives here, not in the
companion's choice of ground speed.  The thrust floor may still exceed it
briefly, as it does in the in-repo controller.

Failsafe.  Rover's HOLD (the default failsafe action) is "throttle zero" and
LOITER inside its radius is the same.  With AIN_FS_HOLD = 1 the script stays
active in HOLD and LOITER: it holds the heading it had on entry and zero
ground speed along it, thrust floor included, so the hull keeps its bow
where it was and falls back slowly instead of swinging beam-on.  Disarming
always stops the motor.

Airframe numbers are for ladder()["S2-dayloiter/hull"]; see the constants.
--]]

-- airframe (aiur.strato.flight6dof.Airframe.from_design(S2))
local YAW_INERTIA = 420.7                  -- kg m2, rigid + added
local ARM         = 10.03                  -- m, thruster aft of centre of volume
local T_MAX       = 7.547                  -- N
local GIMBAL_LIM  = math.rad(25.0)
local THRUST_LAG  = 0.6                    -- s, used to estimate current thrust
-- FlightController defaults
local WN, ZETA    = 0.35, 0.9
local SPD_P       = 2.0                    -- N per m/s
local SPD_I       = 0.15                   -- N per m
local FLOOR       = 0.30

local PERIOD_MS   = 20
local DEMAND_TIMEOUT_MS = 3000
local OVERRIDE_MS = 200
local MODE_HOLD, MODE_LOITER, MODE_GUIDED = 4, 5, 15
local SET_ATTITUDE_TARGET = 82
local K_STEERING, K_THROTTLE = 26, 70

local PARAM_KEY = 73
assert(param:add_table(PARAM_KEY, "AIN_", 3), "aiur_inner: could not add AIN_ params")
assert(param:add_param(PARAM_KEY, 1, "ENABLE", 1))
assert(param:add_param(PARAM_KEY, 2, "ASPD_MAX", 6.0))
assert(param:add_param(PARAM_KEY, 3, "FS_HOLD", 1))
local P_ENABLE   = Parameter("AIN_ENABLE")
local P_ASPD_MAX = Parameter("AIN_ASPD_MAX")
local P_FS_HOLD  = Parameter("AIN_FS_HOLD")
local P_WP_SPEED = Parameter("WP_SPEED")

mavlink:init(10, 1)
mavlink:register_rx_msgid(SET_ATTITUDE_TARGET)

local ch_steer = SRV_Channels:find_channel(K_STEERING)
local ch_thr   = SRV_Channels:find_channel(K_THROTTLE)

local hdg_cmd, gs_cmd, demand_ms = 0.0, 0.0, nil
local hold_mode, hold_hdg = nil, 0.0
local active = false
local integ, t_now, t_cmd = 0.0, 0.0, 0.0
local aspd_lp = nil
local last_report = 0

local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function wrap_pi(a)
  return math.atan(math.sin(a), math.cos(a))
end

local function read_demands(now)
  while true do
    local msg = mavlink:receive_chan()
    if msg == nil then return end
    -- mavlink_message_t: 12 header bytes, then the payload in wire order:
    -- uint32 time_boot_ms, float q[4], float body rates[3], float thrust, ...
    local _, q1, q2, q3, q4, _, _, _, thrust = string.unpack("<I4fffffffff", msg, 13)
    hdg_cmd = math.atan(2.0 * (q1 * q4 + q2 * q3), 1.0 - 2.0 * (q3 * q3 + q4 * q4))
    gs_cmd = clamp(thrust, -1.0, 1.0) * (P_WP_SPEED:get() or 0.0)
    demand_ms = now
  end
end

-- True airspeed: the airspeed library reports equivalent airspeed.
local function airspeed_tas()
  local eas = ahrs:airspeed_estimate()
  if eas == nil then return nil end
  return eas * ahrs:get_EAS2TAS()
end

local function update()
  local now = millis():tofloat()
  read_demands(now)
  if ch_steer == nil or ch_thr == nil then
    ch_steer = SRV_Channels:find_channel(K_STEERING)
    ch_thr = SRV_Channels:find_channel(K_THROTTLE)
    return update, 500
  end

  local dt = PERIOD_MS * 0.001
  local mode = vehicle:get_mode()
  local vel = ahrs:get_velocity_NED()
  local want_active = false
  local h, gs_target = 0.0, 0.0
  if arming:is_armed() and (P_ENABLE:get() or 0) >= 1 and vel ~= nil then
    if mode == MODE_GUIDED and demand_ms ~= nil and now - demand_ms < DEMAND_TIMEOUT_MS then
      want_active, h, gs_target = true, hdg_cmd, gs_cmd
      hold_mode = nil
    elseif (mode == MODE_HOLD or mode == MODE_LOITER) and (P_FS_HOLD:get() or 0) >= 1 then
      if hold_mode ~= mode then
        hold_mode, hold_hdg = mode, ahrs:get_yaw_rad()
        gcs:send_text(4, string.format("aiur_inner: mode %d, holding heading %.0f deg, zero ground speed",
                                       mode, math.deg(hold_hdg)))
      end
      want_active, h, gs_target = true, hold_hdg, 0.0
    else
      hold_mode = nil
    end
  else
    hold_mode = nil
  end

  -- current thrust: first-order model of what was last commanded
  t_now = t_now + (t_cmd - t_now) * math.min(1.0, dt / THRUST_LAG)

  if not want_active then
    if active then
      active = false
      gcs:send_text(4, "aiur_inner: released, stock Rover control")
    end
    -- track Rover's own throttle so a later takeover starts from it
    local pwm = SRV_Channels:get_output_pwm(K_THROTTLE)
    if pwm ~= nil and arming:is_armed() then
      t_cmd = clamp((pwm - 1000) / 1000.0, 0.0, 1.0) * T_MAX
    else
      t_cmd = 0.0
    end
    return update, PERIOD_MS
  end
  if not active then
    active = true
    integ = t_now            -- bumpless: start the integrator at the present thrust
    gcs:send_text(4, "aiur_inner: active")
  end

  local yaw = ahrs:get_yaw_rad()
  local r = ahrs:get_gyro():z()
  local err = wrap_pi(h - yaw)
  local n_cmd = YAW_INERTIA * (WN * WN * err - 2.0 * ZETA * WN * r)

  -- speed loop on ground speed along the body axis, capped by airspeed
  local gs = vel:x() * math.cos(yaw) + vel:y() * math.sin(yaw)
  local e_v = gs_target - gs
  local tas = airspeed_tas()
  if tas ~= nil then
    aspd_lp = (aspd_lp or tas) + (tas - (aspd_lp or tas)) * math.min(1.0, dt / 1.0)
    e_v = math.min(e_v, (P_ASPD_MAX:get() or 6.0) - aspd_lp)
  end
  integ = clamp(integ + SPD_I * e_v * dt, -T_MAX, T_MAX)
  local thrust = SPD_P * e_v + integ

  -- authority floor: no thrust, no rudder
  local sin_lim = math.sin(GIMBAL_LIM)
  local want = math.abs(n_cmd) / (ARM * sin_lim)
  local floor = math.min(T_MAX, math.max(FLOOR * T_MAX * math.min(1.0, math.abs(err) / 0.2), want))
  thrust = clamp(math.max(thrust, floor), 0.0, T_MAX)
  t_cmd = thrust

  -- moment -> gimbal angle through the thrust that is actually there
  local t_eff = math.max(t_now, 0.05 * T_MAX)
  local gy = math.asin(clamp(-n_cmd / (ARM * t_eff), -sin_lim, sin_lim))

  -- SERVO1: PWM > 1500 is "right" = negative gimbal yaw (see json_plant.py)
  local pwm_steer = math.floor(1500.0 - 500.0 * gy / GIMBAL_LIM + 0.5)
  local pwm_thr = math.floor(1000.0 + 1000.0 * thrust / T_MAX + 0.5)
  SRV_Channels:set_output_pwm_chan_timeout(ch_steer, pwm_steer, OVERRIDE_MS)
  SRV_Channels:set_output_pwm_chan_timeout(ch_thr, pwm_thr, OVERRIDE_MS)

  if now - last_report > 1000 then
    last_report = now
    gcs:send_named_float("AIN_T", thrust)
    if aspd_lp ~= nil then gcs:send_named_float("AIN_ASPD", aspd_lp) end
  end
  return update, PERIOD_MS
end

gcs:send_text(6, "aiur_inner.lua loaded")
return update, 1000
