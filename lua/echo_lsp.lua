-- echo_lsp.lua

local lsp_config = require('lspconfig')
local util = require('lspconfig.util')

local server_name = 'echo_lsp_server'

local function get_server_path()
    -- This assumes the plugin is installed in a standard path
    local plugin_path = util.root_pattern('server/echo_lsp_server.py')()
    if not plugin_path then
        return nil
    end
    return plugin_path .. '/scripts/launch.sh'
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
