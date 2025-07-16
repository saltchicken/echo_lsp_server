-- echo_lsp_server.lua

local lsp_config = require('lspconfig')
local util = require('lspconfig.util')

local server_name = 'echo_lsp_server'

local function get_server_path()
    local path = util.path
    local script_path = debug.getinfo(1, "S").source
    if script_path:sub(1,1) == "@" then
        script_path = script_path:sub(2)
    end
    local plugin_dir = path.dirname(path.dirname(script_path))
    local launch_script = path.join(plugin_dir, "scripts", "launch.sh")

    -- Ensure launch script is executable
    if vim.fn.has("unix") == 1 then
        vim.fn.system("chmod +x " .. vim.fn.fnameescape(launch_script))
    end

    return launch_script
end

lsp_config[server_name] = {
    default_config = {
        name = server_name,
        cmd = { get_server_path() },
        filetypes = { 'text', 'plaintext' },
        root_dir = function(fname)
            return util.find_git_ancestor(fname) or util.path.dirname(fname)
        end,
    },
    docs = {
        description = [[
            Simple LSP server that echoes the current line as hover information.
        ]],
        default_config = {
            root_dir = 'util.find_git_ancestor(fname) or util.path.dirname(fname)',
        },
    },
}
