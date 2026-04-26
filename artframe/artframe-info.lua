-- artframe-info.lua — museum-style label per image (osd-overlay variant).
-- Renders ASS directly via the osd-overlay command, which (unlike
-- osd-msg1 / show-text) does NOT do property expansion and accepts
-- raw libass markup.

local utils = require 'mp.utils'
local msg   = require 'mp.msg'

local meta_by_name = {}
local hide_timer
local SHOW_S    = tonumber(os.getenv('ARTFRAME_LABEL_SECS') or '12')
local OVERLAY_ID = 47

-- ── data load ────────────────────────────────────────────────────────
local function load_meta()
    local f = io.open('/var/lib/artframe/metadata.json', 'r')
    if not f then msg.warn('metadata.json not found'); return end
    local data = f:read('*all'); f:close()
    local list = utils.parse_json(data)
    if not list then msg.warn('metadata.json failed to parse'); return end
    for _, item in ipairs(list) do
        if item.filename then meta_by_name[item.filename] = item end
    end
    msg.info('loaded ' .. tostring(#list) .. ' metadata entries')
end

-- ── string helpers ───────────────────────────────────────────────────
local function trim(s)
    if not s then return nil end
    s = s:gsub('^%s+', ''):gsub('%s+$', '')
    return s
end

local function strip_trailing_parens(s)
    if not s then return nil end
    local prev
    repeat
        prev = s
        s = s:gsub('%s*%b()%s*$', '')
    until s == prev
    return s
end

local function first_line(s)
    if not s then return nil end
    return s:match('^[^\r\n]+') or s
end

local function clean_artist(s)
    s = first_line(s)
    s = strip_trailing_parens(s)
    s = trim(s)
    if not s or s == '' or s == 'Unknown' then return nil end
    return s
end

local function clean_text(s)
    s = trim(first_line(s))
    if not s or s == '' or s == 'Unknown' then return nil end
    return s
end

local museum_short = {
    ['Metropolitan Museum of Art'] = 'The Met',
}
local function clean_museum(s)
    s = clean_text(s)
    if not s then return nil end
    return museum_short[s] or s
end

-- Escape ASS-special chars so user text renders literally.
local function ass_esc(s)
    if not s then return '' end
    s = s:gsub('\\', '\\\\')
    s = s:gsub('{',  '\\{')
    s = s:gsub('}',  '\\}')
    return s
end

-- ── overlay ──────────────────────────────────────────────────────────
local function clear()
    mp.command_native({
        name   = 'osd-overlay',
        id     = OVERLAY_ID,
        format = 'none',
        data   = '',
    })
end

local function show(item)
    if hide_timer then hide_timer:kill(); hide_timer = nil end

    local title  = clean_text(item.title) or 'Untitled'
    local artist = clean_artist(item.artist)
    local date   = clean_text(item.date)
    local museum = clean_museum(item.museum)

    -- Logical reference resolution: 1920x1080. mpv scales to actual
    -- display (works on 1080p and 4K equally).
    -- Anchor 2 = bottom-centre, 70 px above bottom edge.
    local rows = {}
    table.insert(rows,
        '{\\fs40\\b1\\i1\\bord2\\shad1\\3c&H000000&\\1c&HFAFAFA&}'
        .. ass_esc(title))
    if artist then
        table.insert(rows,
            '{\\fs28\\b0\\i0\\bord2\\shad1\\3c&H000000&\\1c&HEEEEEE&}'
            .. ass_esc(artist))
    end
    local meta_parts = {}
    if date   then table.insert(meta_parts, date) end
    if museum then table.insert(meta_parts, museum) end
    if #meta_parts > 0 then
        table.insert(rows,
            '{\\fs22\\b0\\i0\\bord2\\shad1\\3c&H000000&\\1c&HCCCCCC&}'
            .. ass_esc(table.concat(meta_parts, ' · ')))
    end

    local body = table.concat(rows, '\\N')
    local ass  = '{\\an2\\pos(960,1010)}' .. body

    msg.info('overlay: ' .. (title or '?') .. ' / ' .. (artist or '?'))

    mp.command_native({
        name   = 'osd-overlay',
        id     = OVERLAY_ID,
        format = 'ass-events',
        data   = ass,
        res_x  = 1920,
        res_y  = 1080,
        z      = 1000,
    })

    hide_timer = mp.add_timeout(SHOW_S, clear)
end

local function on_file_loaded()
    local path = mp.get_property('path')
    if not path then return clear() end
    local fname = path:match('([^/\\]+)$')
    local item  = meta_by_name[fname]
    if item then show(item) else clear() end
end

load_meta()
mp.register_event('file-loaded', on_file_loaded)
