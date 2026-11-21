--[[
aiur_pitch.lua - altitude hold through the pitch axis of the stern gimbal.

ArduRover has no pitch or altitude loop, and no output function for a second
(vertical) thrust-vector axis.  This script is the smallest thing that fills
the gap on a stock firmware: it runs inside ArduPilot at 10 Hz, reads the
EKF's height and climb rate, and writes the gimbal-pitch servo directly.

    u   = (alt_target - alt) / ALT_BAND  -  climb / CLIMB_BAND  -  K_Q * q
    pwm = 1500 + 500 * clamp(u, -1, 1)          (SERVOn_FUNCTION = 94, Script1)

Positive u is "stern down / nose up".  The hull is a pendulum (CG 1.2 m below
the centre of volume, ~190 N m/rad) and the gimbal delivers at most ~10 N m
at cruise thrust, so full deflection is only ~3 degrees of pitch: altitude is
changed slowly, by flying the hull slightly nose-up or nose-down, and only
while there is thrust and airspeed.  This is a trim loop, not a climb
controller.  The altitude target is the height at arming.

The servo is released (set to trim) when disarmed.
--]]

local ALT_BAND   = 20.0   -- m of altitude error for full deflection
local CLIMB_BAND = 0.30   -- m/s of climb rate for full deflection (damping)
local K_Q        = 2.0    -- deflection per rad/s of pitch rate
local PERIOD_MS  = 100
local FUNC       = 94     -- SRV_Channel k_scripting1

local chan = SRV_Channels:find_channel(FUNC)
local target = nil

local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function update()
  if chan == nil then
    chan = SRV_Channels:find_channel(FUNC)
    return update, 1000
  end
  local pos = ahrs:get_relative_position_NED_origin()
  local vel = ahrs:get_velocity_NED()
  if not arming:is_armed() or pos == nil or vel == nil then
    target = nil
    SRV_Channels:set_output_pwm_chan_timeout(chan, 1500, 1000)
    return update, PERIOD_MS
  end
  local alt = -pos:z()
  if target == nil then
    target = alt
    gcs:send_text(6, string.format("aiur_pitch: holding %.0f m (rel. origin)", target))
  end
  local q = ahrs:get_gyro():y()
  local u = (target - alt) / ALT_BAND + vel:z() / CLIMB_BAND - K_Q * q
  u = clamp(u, -1.0, 1.0)
  SRV_Channels:set_output_pwm_chan_timeout(chan, math.floor(1500 + 500 * u + 0.5), 1000)
  return update, PERIOD_MS
end

gcs:send_text(6, "aiur_pitch.lua loaded")
return update, 2000
