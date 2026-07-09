-- UFC_Keypad CV catapult trim bridge for DCS Export.lua
--
-- Installation:
--   1. Copy this file to Saved Games\DCS[.openbeta]\Scripts\UFC_Keypad_CVTrim.lua
--   2. Add this line near the end of Saved Games\DCS[.openbeta]\Scripts\Export.lua:
--        dofile(lfs.writedir() .. [[Scripts\UFC_Keypad_CVTrim.lua]])
--
-- Ports:
--   5518: DCS -> UFC_Keypad telemetry JSON
--   5519: UFC_Keypad -> DCS trim pulse JSON
--
-- Notes:
--   DCS export data availability can vary by build/module.  The script sends
--   every field it can read and keeps unknown fields as nil.  UFC_Keypad only
--   auto-trims when both weight and stabilator/elevator trim angle are fresh.

local socket = require('socket')

local UFC_CVTRIM = UFC_CVTRIM or {}
UFC_CVTRIM.host = '127.0.0.1'
UFC_CVTRIM.telemetry_port = 5518
UFC_CVTRIM.command_port = 5519
UFC_CVTRIM.last_send = 0
UFC_CVTRIM.send_interval = 0.25
UFC_CVTRIM.pending_release = nil

local tx = socket.udp()
tx:setpeername(UFC_CVTRIM.host, UFC_CVTRIM.telemetry_port)

local rx = socket.udp()
rx:setsockname(UFC_CVTRIM.host, UFC_CVTRIM.command_port)
rx:settimeout(0)

local function json_number(name, value)
    if type(value) == 'number' then
        return string.format('"%s":%.3f', name, value)
    end
    return string.format('"%s":null', name)
end

local function pick_number(t, names)
    if type(t) ~= 'table' then return nil end
    for _, name in ipairs(names) do
        if type(t[name]) == 'number' then return t[name] end
    end
    return nil
end

local function get_weight_lbs()
    local self_data = LoGetSelfData and LoGetSelfData() or nil
    local w = pick_number(self_data, {'Weight', 'weight', 'GrossWeight', 'gross_weight'})
    if w then
        -- Some export builds return kg, some community exports return lbs.
        -- Hornet launch weights in kg are much smaller than 44000, so convert.
        if w < 25000 then return w * 2.20462262 end
        return w
    end

    -- Fallback: if no gross weight exists, try fuel only.  This is not enough
    -- for automatic trimming, so UFC_Keypad will treat missing gross weight as
    -- not ready unless a proper value is available.
    local eng = LoGetEngineInfo and LoGetEngineInfo() or nil
    local fuel = pick_number(eng, {'fuel_internal', 'FuelInternal', 'fuel', 'Fuel'})
    if fuel then return nil end
    return nil
end

local function get_trim_deg()
    local mech = LoGetMechInfo and LoGetMechInfo() or nil
    local raw = pick_number(mech, {
        'stab_trim_deg', 'stabilator_trim_deg', 'elevator_trim_deg', 'pitch_trim_deg',
        'StabTrim', 'stabilator', 'elevator', 'Elevator', 'pitchTrim'
    })
    if raw then
        -- If a normalized -1..1 control-surface value is returned, scale it
        -- into the Hornet catapult-trim range.  If the value is already degrees,
        -- keep it.
        if raw >= -1.2 and raw <= 1.2 then
            return raw * 20.0
        end
        return raw
    end

    -- Optional draw-argument probing.  These IDs are intentionally conservative;
    -- if none match, nil is sent and UFC_Keypad falls back to manual confirmation.
    if LoGetAircraftDrawArgumentValue then
        for _, arg in ipairs({15, 16, 17, 18, 345, 346}) do
            local v = LoGetAircraftDrawArgumentValue(arg)
            if type(v) == 'number' and math.abs(v) > 0.001 then
                return v * 20.0
            end
        end
    end
    return nil
end

local function send_telemetry()
    local weight = get_weight_lbs()
    local trim = get_trim_deg()
    local parts = {
        '"type":"cv_trim"',
        json_number('gross_weight_lbs', weight),
        json_number('stab_trim_deg', trim)
    }
    tx:send('{' .. table.concat(parts, ',') .. '}')
end

local function command_constant(direction)
    if direction == 'up' then
        return rawget(_G, 'iCommandPlaneTrimPitchUp')
    elseif direction == 'down' then
        return rawget(_G, 'iCommandPlaneTrimPitchDown')
    end
    return nil
end

local function command_stop_constant(direction)
    if direction == 'up' then
        return rawget(_G, 'iCommandPlaneTrimPitchUpStop')
    elseif direction == 'down' then
        return rawget(_G, 'iCommandPlaneTrimPitchDownStop')
    end
    return nil
end

local function handle_command(msg)
    local direction = string.match(msg or '', '"direction"%s*:%s*"([^"]+)"')
    if direction ~= 'up' and direction ~= 'down' then return end
    local cmd = command_constant(direction)
    if type(cmd) ~= 'number' then return end
    LoSetCommand(cmd, 1)
    UFC_CVTRIM.pending_release = {
        time = (LoGetModelTime and LoGetModelTime() or socket.gettime()) + 0.12,
        direction = direction,
        cmd = cmd,
    }
end

local function poll_commands()
    while true do
        local msg = rx:receive()
        if not msg then break end
        handle_command(msg)
    end
end

local function release_pending()
    local p = UFC_CVTRIM.pending_release
    if not p then return end
    local now = LoGetModelTime and LoGetModelTime() or socket.gettime()
    if now < p.time then return end
    local stop_cmd = command_stop_constant(p.direction)
    if type(stop_cmd) == 'number' then
        LoSetCommand(stop_cmd, 1)
    else
        LoSetCommand(p.cmd, 0)
    end
    UFC_CVTRIM.pending_release = nil
end

local prev_after_next_frame = LuaExportAfterNextFrame
LuaExportAfterNextFrame = function()
    if prev_after_next_frame then prev_after_next_frame() end
    poll_commands()
    release_pending()
    local now = LoGetModelTime and LoGetModelTime() or socket.gettime()
    if now - UFC_CVTRIM.last_send >= UFC_CVTRIM.send_interval then
        UFC_CVTRIM.last_send = now
        send_telemetry()
    end
end
