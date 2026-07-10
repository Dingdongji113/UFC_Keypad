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
UFC_CVTRIM.scan_from = nil
UFC_CVTRIM.scan_to = nil
UFC_CVTRIM.param_probe = ''

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

local function cockpit_arg(arg)
    -- LoGetAircraftDrawArgumentValue() reads the external 3D model, not
    -- clickable cockpit controls. Device 0 owns cockpit animation arguments.
    if GetDevice then
        local ok_dev, dev = pcall(GetDevice, 0)
        if ok_dev and dev and dev.get_argument_value then
            local ok_value, value = pcall(function() return dev:get_argument_value(arg) end)
            if ok_value and type(value) == 'number' then return value end
        end
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

local function get_cockpit_params()
    if not list_cockpit_params then return nil end
    local ok, params = pcall(list_cockpit_params)
    if ok and type(params) == 'string' then return params end
    return nil
end

local function cockpit_param_number(params, name)
    if type(params) ~= 'string' then return nil end
    local prefix = name .. ':'
    for line in string.gmatch(params, '[^\r\n]+') do
        if string.sub(line, 1, #prefix) == prefix then
            return tonumber(string.sub(line, #prefix + 1))
        end
    end
    return nil
end

local function get_weight_lbs(params)
    local mass_lb = cockpit_param_number(params, 'ExternalFM:HumanInfo:mass_lb')
    if mass_lb then return mass_lb end
    local mass_kg = cockpit_param_number(params, 'ExternalFM:HumanInfo:mass')
    if mass_kg then return mass_kg * 2.20462262 end
    local self_data = LoGetSelfData and LoGetSelfData() or nil
    local w = pick_number(self_data, {'Weight', 'weight', 'GrossWeight', 'gross_weight', 'Mass', 'mass'})
    if w then
        if w < 25000 then return w * 2.20462262 end
        return w
    end
    return nil
end

local function get_trim_deg(params)
    -- Live F/A-18C probing confirms Lstab changes by about -2 degrees per
    -- second of nose-up trim and returns in the opposite direction. Convert
    -- its negative nose-up convention to the positive degrees used by Python.
    local left_stab = cockpit_param_number(params, 'ExternalFM:HumanInfo:Lstab')
    if left_stab then return -left_stab end
    local mech = LoGetMechInfo and LoGetMechInfo() or nil
    local raw = pick_number(mech, {
        'stab_trim_deg', 'stabilator_trim_deg', 'elevator_trim_deg', 'pitch_trim_deg',
        'StabTrim', 'stabilator', 'elevator', 'Elevator', 'pitchTrim', 'PitchTrim'
    })
    if raw then
        if raw >= -1.2 and raw <= 1.2 then return raw * 20.0 end
        return raw
    end
    -- Do not infer trim from arbitrary external-model arguments. A missing
    -- verified sensor must remain nil so Python holds at CAT TRIM DATA?.
    return nil
end

local function append_probe_args(parts)
    -- DCS-BIOS source-confirmed key arguments:
    -- 511 = EJECTION_SEAT_ARMED, 248 = ECM_MODE_SW, 276/267 = RWR lights.
    table.insert(parts, json_number('seat_armed_arg_511', cockpit_arg(511)))
    table.insert(parts, json_number('ecm_mode_arg_248', cockpit_arg(248)))
    table.insert(parts, json_number('rwr_power_light_arg_276', cockpit_arg(276)))
    table.insert(parts, json_number('rwr_enable_light_arg_267', cockpit_arg(267)))
    table.insert(parts, json_number('fcs_reset_arg_349', cockpit_arg(349)))
    table.insert(parts, json_number('canopy_sw_arg_453', cockpit_arg(453)))
    table.insert(parts, json_number('apu_arg_375', cockpit_arg(375)))
    table.insert(parts, json_number('rwr_power_arg_277', cockpit_arg(277)))
    table.insert(parts, json_number('obogs_arg_365', cockpit_arg(365)))
    table.insert(parts, json_number('radar_arg_440', cockpit_arg(440)))
    table.insert(parts, json_number('ins_arg_443', cockpit_arg(443)))
    table.insert(parts, json_number('hmd_brt_arg_136', cockpit_arg(136)))
    -- Candidate stabilator / trim draw args. probe_hornet_bridge.py will show which one moves.
    for _, arg in ipairs({15, 16, 17, 18, 345, 346, 500, 501, 502, 503}) do
        table.insert(parts, json_number('trim_arg_' .. tostring(arg), cockpit_arg(arg)))
    end
end

local function append_scan_args(parts)
    if UFC_CVTRIM.scan_from == nil or UFC_CVTRIM.scan_to == nil then return end
    local values = {}
    for arg = UFC_CVTRIM.scan_from, UFC_CVTRIM.scan_to do
        local value = cockpit_arg(arg)
        if type(value) == 'number' then
            table.insert(values, string.format('"%d":%.6f', arg, value))
        end
    end
    table.insert(parts, '"scan_args":{' .. table.concat(values, ',') .. '}')
end

local function send_telemetry()
    local params = get_cockpit_params()
    local weight = get_weight_lbs(params)
    local trim = get_trim_deg(params)
    local parts = {
        '"type":"cv_trim"',
        json_string_value('bridge', 'loaded'),
        json_string_value('last_command', UFC_CVTRIM.last_command),
        json_number('time', now_time()),
        json_number('gross_weight_lbs', weight),
        json_number('stab_trim_deg', trim),
        json_string_value('param_probe', UFC_CVTRIM.param_probe)
    }
    append_probe_args(parts)
    append_scan_args(parts)
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
    -- Local FA-18C command_defs.lua: HOTAS device 13, pitch trim up/down
    -- commands 3014/3015. These are cockpit device commands, not global
    -- LoSetCommand constants.
    local cmd = direction == 'up' and 3014 or 3015
    local dev = GetDevice and GetDevice(13) or nil
    if not dev or not dev.performClickableAction then
        UFC_CVTRIM.last_command = 'trim failed no HOTAS device'
        log(UFC_CVTRIM.last_command)
        return
    end
    dev:performClickableAction(cmd, 1.0)
    UFC_CVTRIM.last_command = 'trim HOTAS pulse ' .. direction .. ' cmd=' .. tostring(cmd)
    log(UFC_CVTRIM.last_command)
    UFC_CVTRIM.pending_release = {
        time = now_time() + pulse_ms / 1000.0,
        type = 'trim',
        direction = direction,
        cmd = cmd,
        device = dev,
    }
end

local function handle_ping(msg)
    UFC_CVTRIM.last_command = 'ping received'
    log('ping received')
    send_telemetry()
end

local function handle_scan_args(msg)
    local first = json_number_value(msg, 'from')
    local last = json_number_value(msg, 'to')
    if not first or not last then
        UFC_CVTRIM.last_command = 'scan_args failed missing range'
        log(UFC_CVTRIM.last_command)
        return
    end
    first = math.floor(first)
    last = math.floor(last)
    if first < 0 or last > 2000 or first > last or last - first > 1000 then
        UFC_CVTRIM.last_command = string.format('scan_args failed invalid range %s..%s', tostring(first), tostring(last))
        log(UFC_CVTRIM.last_command)
        return
    end
    UFC_CVTRIM.scan_from = first
    UFC_CVTRIM.scan_to = last
    UFC_CVTRIM.last_command = string.format('scan_args enabled %d..%d', first, last)
    log(UFC_CVTRIM.last_command)
    send_telemetry()
end

local function handle_dump_params(msg)
    if not list_cockpit_params then
        UFC_CVTRIM.param_probe = 'list_cockpit_params unavailable'
        UFC_CVTRIM.last_command = 'dump_params unavailable'
        log(UFC_CVTRIM.last_command)
        return
    end
    local ok, params = pcall(list_cockpit_params)
    if not ok or type(params) ~= 'string' then
        UFC_CVTRIM.param_probe = 'list_cockpit_params failed: ' .. tostring(params)
        UFC_CVTRIM.last_command = 'dump_params failed'
        log(UFC_CVTRIM.param_probe)
        return
    end
    local matches = {}
    for line in string.gmatch(params, '[^\r\n]+') do
        local lower = string.lower(line)
        if string.find(lower, 'trim', 1, true)
            or string.find(lower, 'stab', 1, true)
            or string.find(lower, 'weight', 1, true)
            or string.find(lower, 'mass', 1, true)
            or string.find(lower, 'gross', 1, true)
            or string.find(lower, 'fuel', 1, true) then
            table.insert(matches, line)
        end
    end
    UFC_CVTRIM.param_probe = table.concat(matches, ' | ')
    UFC_CVTRIM.last_command = 'dump_params matches=' .. tostring(#matches)
    log(UFC_CVTRIM.last_command .. ' ' .. UFC_CVTRIM.param_probe)
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
    elseif typ == 'scan_args' then
        handle_scan_args(msg)
    elseif typ == 'dump_params' then
        handle_dump_params(msg)
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
        p.device:performClickableAction(p.cmd, 0.0)
        UFC_CVTRIM.last_command = 'trim HOTAS release ' .. p.direction .. ' cmd=' .. tostring(p.cmd)
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
