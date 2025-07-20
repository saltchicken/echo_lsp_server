local M = {}

-- Globals for ghost text state
local ghost_ns = vim.api.nvim_create_namespace("echo_lsp_ghost")
local ghost_extmarks = {}
local ghost_text = ""
local ghost_line = nil
local ghost_bufnr = nil

-- Utility functions to clear ghost text
local function clear_ghost_text()
	if ghost_bufnr then
		vim.api.nvim_buf_clear_namespace(ghost_bufnr, ghost_ns, 0, -1)
	end
	ghost_extmarks = {}
	ghost_text = ""
	ghost_line = nil
	ghost_bufnr = nil
end

-- Insert first line of ghost text at cursor in ghost_line
local function insert_ghost_text()
	if not ghost_bufnr or not ghost_line or ghost_text == "" then
		return
	end
	local lines = vim.split(ghost_text, "\n", true)
	if #lines == 0 then
		return
	end
	local insert_text = lines[1]

	local row = ghost_line
	local col = vim.api.nvim_win_get_cursor(0)[2]

	local orig_line = vim.api.nvim_buf_get_lines(ghost_bufnr, row, row + 1, true)[1] or ""
	local prefix = orig_line:sub(1, col)
	local suffix = orig_line:sub(col + 1)

	local new_line = prefix .. insert_text .. suffix

	vim.api.nvim_buf_set_lines(ghost_bufnr, row, row + 1, true, { new_line })
	clear_ghost_text()

	-- Move cursor forward by length of inserted text
	local new_col = col + #insert_text
	vim.api.nvim_win_set_cursor(0, { row + 1, new_col })
end

-- LSP handler for ghostText/virtualText notification
local function on_ghost_text_virtual_text(_, result, ctx)
	if not result or not result.uri then
		return
	end
	local bufnr = vim.uri_to_bufnr(result.uri)
	if not vim.api.nvim_buf_is_loaded(bufnr) then
		vim.fn.bufload(bufnr)
	end

	local line = result.line or 0
	local text = result.text or ""

	vim.api.nvim_buf_clear_namespace(bufnr, ghost_ns, 0, -1)
	ghost_extmarks = {}

	local lines = vim.split(text, "\n", true)
	if #lines > 0 then
		local first_line_text = lines[1]
		local cursor_pos = vim.api.nvim_win_get_cursor(0)
		local col = cursor_pos[2]

		local extmark_id = vim.api.nvim_buf_set_extmark(bufnr, ghost_ns, line, col, {
			virt_text = { { first_line_text, "Comment" } },
			virt_text_pos = "overlay",
			hl_mode = "combine",
		})
		table.insert(ghost_extmarks, extmark_id)
	end

	ghost_text = text
	ghost_line = line
	ghost_bufnr = bufnr
end

-- Autocmd callback to clear ghost text and notify echo_lsp to cancel ghost text
local function clear_ghost_text_and_notify()
	if ghost_bufnr then
		vim.api.nvim_buf_clear_namespace(ghost_bufnr, ghost_ns, 0, -1)
		ghost_extmarks = {}
		ghost_text = ""
		ghost_line = nil
		ghost_bufnr = nil
	end

	local bufnr = vim.api.nvim_get_current_buf()
	local clients = vim.lsp.get_active_clients({ bufnr = bufnr })
	for _, client in ipairs(clients) do
		if client.name == "echo_lsp" then
			client.notify("$/cancelGhostText", nil)
		end
	end
end

-- Setup function to register LSP, handlers, autocmds, and keymaps
function M.setup()
	local lspconfig = require("lspconfig")

	-- 1. Register echo_lsp if not already registered
	if not lspconfig.echo_lsp then
		local path_to_launch = vim.fn.expand("~/.local/share/echo_lsp_server/launch.sh")
		lspconfig.echo_lsp = {
			default_config = {
				cmd = { path_to_launch },
				filetypes = { "text", "markdown", "lua", "python", "javascript", "typescript" },
				root_dir = function()
					return vim.loop.cwd()
				end,
				single_file_support = true,
			},
		}
	end

	-- 2. Setup echo_lsp with diagnostic options and custom handlers
	lspconfig.echo_lsp.setup({
		on_attach = function(client, bufnr)
			-- Keymaps
			if client.name == "echo_lsp" then
				local opts = { noremap = true, silent = true, buffer = bufnr }
				vim.keymap.set("i", "<C-n>", function()
					M.trigger_ghost_text()
				end, opts)
				vim.keymap.set("i", "<Tab>", function()
					if #ghost_extmarks > 0 then
						insert_ghost_text()
					else
						-- Send normal Tab key input
						vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", false)
					end
				end, opts)
			end
		end,

		handlers = {
			["ghostText/virtualText"] = vim.schedule_wrap(on_ghost_text_virtual_text),
		},

		flags = {
			debounce_text_changes = 150,
		},

		diagnostics = {
			virtual_lines = true,
			underline = true,
			update_in_insert = false,
			virtual_text = false,
		},
	})

	-- 3. Setup autocmds for InsertCharPre, CursorMovedI, TextChangedI, InsertLeave
	vim.api.nvim_create_autocmd({ "InsertCharPre", "CursorMovedI", "TextChangedI", "InsertLeave" }, {
		callback = clear_ghost_text_and_notify,
	})
end

-- Expose ghost text state and utility functions globally
_G.ghost_state = {
	extmark = function()
		if #ghost_extmarks > 0 then
			return ghost_extmarks
		else
			return nil
		end
	end,
	text = function()
		return ghost_text
	end,
	line = function()
		return ghost_line
	end,
	bufnr = function()
		return ghost_bufnr
	end,
	clear = clear_ghost_text,
	insert = insert_ghost_text,
}

-- Function to trigger ghost text request
function M.trigger_ghost_text()
	local bufnr = vim.api.nvim_get_current_buf()
	local clients = vim.lsp.get_active_clients({ bufnr = bufnr })
	local echo_client = nil
	for _, client in ipairs(clients) do
		if client.name == "echo_lsp" then
			echo_client = client
			break
		end
	end
	if not echo_client then
		vim.notify("Echo LSP not active", vim.log.levels.WARN)
		return
	end

	local pos = vim.api.nvim_win_get_cursor(0)
	local line = pos[1] - 1
	local char = pos[2]
	local uri = vim.uri_from_bufnr(bufnr)

	local params = {
		textDocument = { uri = uri },
		position = { line = line, character = char },
	}

	echo_client.request("custom/triggerGhostText", params, function(err, result)
		if err then
			vim.notify("Error triggering ghost text: " .. tostring(err), vim.log.levels.ERROR)
		end
	end, bufnr)
end

return M
