-- UFC_Keypad CV trim and direct cockpit command bridge for DCS Export.lua
--
-- Installation:
--   1. Copy this file to Saved Games\DCS[.openbeta]\Scripts\UFC_Keypad_CVTrim.lua
--   2. Add this line near the end of Saved Games\DCS[.openbeta]\Scripts\Export.lua:
--        dofile(lfs.writedir() .. [[Scripts\UFC_Keypad_CVTrim.lua]])
--
-- Ports:
--   5518: DCS -> UFC_Keypad telemetry JSON
--   5519: UFC_Keypad -> DCS command JSON

local socket = require('socket')

local UFC_CVTRIM = UFC_CVTRIM or {}
UFC_CVTRIM.host = '127.0.0.1'
UFC_CVTRIM.telemetry_port = 5518
UFC_CVTRIM.command_port = 5519
UFC_CVTRIM.last_send = 0
UFC_CVTRIM.send_interval = 0.25
UFC_CVTRIM.pending_release = nil
UFC_CVTRIM.log_path = nil
UFC_CVTRIM.last_command = 'none'

local function now_time()
    return LoGetModelTime and LoGetModelTime() or socket.gettime()
end

local function init_log_path()
    if UFC_CVTRIM.log_path then return UFC_CVTRIM.log_path end
    if lfs and lfs.writedir then
        UFC_CVTRIM.log_path = lfs.writedir() .. [[Logs\UFC_Keypad_CVTrim.log]]
    else
        UFC_CVTRIM.log_path = [[UFC_Keypad_CVTrim.log]]
    end
    return UFC_CVTRIM.log_path
end

local function log(msg)
    local path = init_log_path()
    local f = io.open(path, 'a')
    if f then
        f:write(string.format('[%.3f] %s\n', now_time(), tostring(msg)))
        f:close()
    end
end

local tx = socket.udp()
tx:setpeername(UFC_CVTRIM.host, UFC_CVTRIM.telemetry_port)

local rx = socket.udp()
rx:setsockname(UFC_CVTRIM.host, UFC_CVTRIM.command_port)
rx:settimeout(0)

log('UFC_Keypad_CVTrim bridge loaded')

local function json_number(name, value)
    if type(value) == 'number' then
        return string.format('"%s":%.3f', name, value)
    end
    return string.format('"%s":null', name)
end

local function json_string_value(name, value)
    value = tostring(value or ''):gsub('\\', '\\\\'):gsub('"', '\\"')
    return string.format('"%s":"%s"', name, value)
end

local function draw_arg(arg)
    if LoGetAircraftDrawArgumentValue then
        local ok, value = pcall(LoGetAircraftDrawArgumentValue, arg)
        if ok and type(value) == 'number' then return value end
    end
    return nil
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
    local w = pick_number(self_data, {'Weight', 'weight', 'GrossWeight', 'gross_weight', 'Mass', 'mass'})
    if w then
        if w < 25000 then return w * 2.20462262 end
        return w
    end
    return nil
end

local function get_trim_deg()
    local mech = LoGetMechInfo and LoGetMechInfo() or nil
    local raw = pick_number(mech, {
        'stab_trim_deg', 'stabilator_trim_deg', 'elevator_trim_deg', 'pitch_trim_deg',
        'StabTrim', 'stabilator', 'elevator', 'Elevator', 'pitchTrim', 'PitchTrim'
    })
    if raw then
        if raw >= -1.2 and raw <= 1.2 then return raw * 20.0 end
        return raw
    end
    if LoGetAircraftDrawArgumentValue then
        for _, arg in ipairs({15, 16, 17, 18, 345, 346, 500, 501, 502, 503}) do
            local v = draw_arg(arg)
            if type(v) == 'number' and math.abs(v) > 0.001 then
                return v * 20.0
            end
        end
    end
    return nil
end

local function append_probe_args(parts)
    -- DCS-BIOS source-confirmed key arguments:
    -- 511 = EJECTION_SEAT_ARMED, 248 = ECM_MODE_SW, 276/267 = RWR lights.
    table.insert(parts, json_number('seat_armed_arg_511', draw_arg(511)))
    table.insert(parts, json_number('ecm_mode_arg_248', draw_arg(248)))
    table.insert(parts, json_number('rwr_power_light_arg_276', draw_arg(276)))
    table.insert(parts, json_number('rwr_enable_light_arg_267', draw_arg(267)))
    table.insert(parts, json_number('fcs_reset_arg_349', draw_arg(349)))
    table.insert(parts, json_number('canopy_sw_arg_453', draw_arg(453)))
    -- Candidate stabilator / trim draw args. probe_hornet_bridge.py will show which one moves.
    for _, arg in ipairs({15, 16, 17, 18, 345, 346, 500, 501, 502, 503}) do
        table.insert(parts, json_number('trim_arg_' .. tostring(arg), draw_arg(arg)))
    end
end

local function send_telemetry()
    local weight = get_weight_lbs()
    local trim = get_trim_deg()
    local parts = {
        '"type":"cv_trim"',
        json_string_value('bridge', 'loaded'),
        json_string_value('last_command', UFC_CVTRIM.last_command),
        json_number('time', now_time()),
        json_number('gross_weight_lbs', weight),
        json_number('stab_trim_deg', trim)
    }
    append_probe_args(parts)
    tx:send('{' .. table.concat(parts, ',') .. '}')
end

local function command_constant(direction)
    local names
    if direction == 'up' then
        names = {'iCommandPlaneTrimPitchUp', 'iCommandPlaneTrimUp', 'iCommandTrimPitchUp'}
    elseif direction == 'down' then
        names = {'iCommandPlaneTrimPitchDown', 'iCommandPlaneTrimDown', 'iCommandTrimPitchDown'}
    else
        return nil
    end
    for _, name in ipairs(names) do
        local v = rawget(_G, name)
        if type(v) == 'number' then
            log('trim command ' .. direction .. ' using ' .. name .. '=' .. tostring(v))
            return v
        end
    end
    log('trim command constant missing for ' .. tostring(direction))
    return nil
end

local function command_stop_constant(direction)
    local names
    if direction == 'up' then
        names = {'iCommandPlaneTrimPitchUpStop', 'iCommandPlaneTrimUpStop', 'iCommandTrimPitchUpStop'}
    elseif direction == 'down' then
        names = {'iCommandPlaneTrimPitchDownStop', 'iCommandPlaneTrimDownStop', 'iCommandTrimPitchDownStop'}
    else
        return nil
    end
    for _, name in ipairs(names) do
        local v = rawget(_G, name)
        if type(v) == 'number' then return v end
    end
    return nil
end

local function json_string(msg, key)
    return string.match(msg or '', '"' .. key .. '"%s*:%s*"([^"]*)"')
end

local function json_number_value(msg, key)
    local text = string.match(msg or '', '"' .. key .. '"%s*:%s*([-+]?%d+%.?%d*)')
    if text then return tonumber(text) end
    return nil
end

local function handle_clickable(msg)
    local device_id = json_number_value(msg, 'device')
    local command = json_number_value(msg, 'command')
    local value = json_number_value(msg, 'value')
    local label = json_string(msg, 'label') or 'clickable'
    local hold_ms = json_number_value(msg, 'hold_ms') or 0
    local release_value = json_number_value(msg, 'release_value')
    if not device_id or not command or value == nil then
        log('bad clickable payload: ' .. tostring(msg))
        return
    end
    local dev = GetDevice and GetDevice(device_id) or nil
    if not dev or not dev.performClickableAction then
        log('no clickable device/action for ' .. label .. ' device=' .. tostring(device_id))
        UFC_CVTRIM.last_command = 'clickable failed no device ' .. tostring(label)
        return
    end
    dev:performClickableAction(command, value)
    UFC_CVTRIM.last_command = string.format('clickable %s dev=%s cmd=%s value=%s', label, tostring(device_id), tostring(command), tostring(value))
    log(UFC_CVTRIM.last_command)
    if release_value ~= nil and hold_ms > 0 then
        UFC_CVTRIM.pending_release = {
            time = now_time() + hold_ms / 1000.0,
            type = 'clickable',
            device = dev,
            command = command,
            value = release_value,
            label = label,
        }
    end
end

local function handle_trim(msg)
    local direction = json_string(msg, 'direction')
    if direction ~= 'up' and direction ~= 'down' then return end
    local pulse_ms = json_number_value(msg, 'pulse_ms') or 120
    local cmd = command_constant(direction)
    if type(cmd) ~= 'number' then return end
    LoSetCommand(cmd, 1)
    UFC_CVTRIM.last_command = 'trim pulse ' .. direction .. ' cmd=' .. tostring(cmd)
    log(UFC_CVTRIM.last_command)
    UFC_CVTRIM.pending_release = {
        time = now_time() + pulse_ms / 1000.0,
        type = 'trim',
        direction = direction,
        cmd = cmd,
    }
end

local function handle_ping(msg)
    UFC_CVTRIM.last_command = 'ping received'
    log('ping received')
    send_telemetry()
end

local function handle_command(msg)
    local typ = json_string(msg, 'type')
    if typ == 'clickable' then
        handle_clickable(msg)
    elseif typ == 'trim' then
        handle_trim(msg)
    elseif typ == 'ping' then
        handle_ping(msg)
    else
        log('unknown command: ' .. tostring(msg))
    end
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
    if now_time() < p.time then return end
    if p.type == 'clickable' then
        p.device:performClickableAction(p.command, p.value)
        UFC_CVTRIM.last_command = string.format('clickable release %s cmd=%s value=%s', tostring(p.label), tostring(p.command), tostring(p.value))
        log(UFC_CVTRIM.last_command)
    elseif p.type == 'trim' then
        local stop_cmd = command_stop_constant(p.direction)
        if type(stop_cmd) == 'number' then
            LoSetCommand(stop_cmd, 1)
            UFC_CVTRIM.last_command = 'trim stop ' .. p.direction .. ' stop_cmd=' .. tostring(stop_cmd)
        else
            LoSetCommand(p.cmd, 0)
            UFC_CVTRIM.last_command = 'trim release ' .. p.direction .. ' cmd=' .. tostring(p.cmd)
        end
        log(UFC_CVTRIM.last_command)
    end
    UFC_CVTRIM.pending_release = nil
end

local prev_after_next_frame = LuaExportAfterNextFrame
LuaExportAfterNextFrame = function()
    if prev_after_next_frame then prev_after_next_frame() end
    poll_commands()
    release_pending()
    local now = now_time()
    if now - UFC_CVTRIM.last_send >= UFC_CVTRIM.send_interval then
        UFC_CVTRIM.last_send = now
        send_telemetry()
    end
end
