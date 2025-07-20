local M = {}

function M.setup()
	local lspconfig = require("lspconfig")
	local ghost_ns = vim.api.nvim_create_namespace("echo_lsp_ghost")
	local state = {
		extmarks = {},
		text = "",
		line = nil,
		bufnr = nil,
	}

	local function clear()
		if state.bufnr then
			vim.api.nvim_buf_clear_namespace(state.bufnr, ghost_ns, 0, -1)
		end
		state.extmarks = {}
		state.text = ""
		state.line = nil
		state.bufnr = nil
	end

	local function insert()
		if not state.bufnr or not state.line or state.text == "" then
			return
		end
		local lines = vim.split(state.text, "\n", true)
		if #lines == 0 then
			return
		end
		local insert_text = lines[1]

		local row = state.line
		local col = vim.api.nvim_win_get_cursor(0)[2]
		local orig_line = vim.api.nvim_buf_get_lines(state.bufnr, row, row + 1, true)[1] or ""
		local prefix = orig_line:sub(1, col)
		local suffix = orig_line:sub(col + 1)
		local new_line = prefix .. insert_text .. suffix

		vim.api.nvim_buf_set_lines(state.bufnr, row, row + 1, true, { new_line })
		clear()
		vim.api.nvim_win_set_cursor(0, { row + 1, col + #insert_text })
	end

	local function on_ghost_text(_, result)
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
		state.extmarks = {}

		local lines = vim.split(text, "\n", true)
		if #lines > 0 then
			local first_line_text = lines[1]
			local col = vim.api.nvim_win_get_cursor(0)[2]
			local extmark_id = vim.api.nvim_buf_set_extmark(bufnr, ghost_ns, line, col, {
				virt_text = { { first_line_text, "Comment" } },
				virt_text_pos = "overlay",
				hl_mode = "combine",
			})
			table.insert(state.extmarks, extmark_id)
		end

		state.text = text
		state.line = line
		state.bufnr = bufnr
	end

	local function cancel_ghost()
		local bufnr = vim.api.nvim_get_current_buf()
		for _, client in ipairs(vim.lsp.get_active_clients({ bufnr = bufnr })) do
			if client.name == "echo_lsp" then
				client.notify("$/cancelGhostText", nil)
			end
		end
		clear()
	end

	local function trigger()
		local bufnr = vim.api.nvim_get_current_buf()
		local client = vim.lsp.get_active_clients({ bufnr = bufnr })
			and vim.lsp.get_active_clients({ bufnr = bufnr })[1]
		if not client or client.name ~= "echo_lsp" then
			vim.notify("Echo LSP not active", vim.log.levels.WARN)
			return
		end

		local pos = vim.api.nvim_win_get_cursor(0)
		local uri = vim.uri_from_bufnr(bufnr)
		client.request("custom/triggerGhostText", {
			textDocument = { uri = uri },
			position = { line = pos[1] - 1, character = pos[2] },
		}, function(err)
			if err then
				vim.notify("GhostText error: " .. tostring(err), vim.log.levels.ERROR)
			end
		end, bufnr)
	end

	-- Optional: Expose if needed
	M.trigger_ghost_text = trigger

	-- Define Insert-mode autocmds
	vim.api.nvim_create_autocmd({ "InsertCharPre", "CursorMovedI", "TextChangedI", "InsertLeave" }, {
		callback = cancel_ghost,
	})

	-- Register LSP config if missing
	if not lspconfig.echo_lsp then
		local launch = vim.fn.expand("~/.local/share/echo_lsp_server/launch.sh")
		lspconfig.echo_lsp = {
			default_config = {
				cmd = { launch },
				filetypes = { "text", "markdown", "lua", "python", "javascript", "typescript" },
				root_dir = function()
					return vim.loop.cwd()
				end,
				single_file_support = true,
			},
		}
	end

	-- Setup echo_lsp
	lspconfig.echo_lsp.setup({
		handlers = {
			["ghostText/virtualText"] = vim.schedule_wrap(on_ghost_text),
		},
		on_attach = function(client, bufnr)
			local root = client.config.root_dir
			print("root: " .. root)
			if client.name ~= "echo_lsp" then
				return
			end
			local opts = { buffer = bufnr, noremap = true, silent = true }
			vim.keymap.set("i", "<C-n>", trigger, opts)
			vim.keymap.set("i", "<Tab>", function()
				if #state.extmarks > 0 then
					insert()
				else
					vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", false)
				end
			end, opts)
		end,
		diagnostics = {
			virtual_lines = true,
			underline = true,
			update_in_insert = false,
			virtual_text = false,
		},
	})
end

return M
