local M = {}

local ns = vim.api.nvim_create_namespace("echo_lsp_ghost_text")
local state = {
	extmark = nil,
	text = "",
	line = nil,
	bufnr = nil,
}

function M.clear()
	if state.extmark and state.bufnr then
		vim.api.nvim_buf_clear_namespace(state.bufnr, ns, 0, -1)
	end
	state.extmark, state.text, state.line, state.bufnr = nil, "", nil, nil
end

function M.insert()
	local bufnr = state.bufnr
	local line = state.line
	local ghost = state.text
	local extmark = state.extmark

	if not (bufnr and line and ghost and extmark) then
		return
	end

	local cursor = vim.api.nvim_win_get_cursor(0)
	local cursor_line = cursor[1] - 1
	local cursor_col = cursor[2]

	-- Only insert if on correct line
	if cursor_line ~= line then
		return
	end

	local lines = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)
	if not lines or not lines[1] then
		return
	end
	local current_line = lines[1]

	local new_line = current_line:sub(1, cursor_col) .. ghost .. current_line:sub(cursor_col + 1)
	vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { new_line })

	local target_col = cursor_col + #ghost
	M.clear()

	vim.schedule(function()
		vim.api.nvim_win_set_cursor(0, { line + 1, target_col })
	end)
end

vim.lsp.handlers["ghostText/virtualText"] = function(_, result)
	if not result or not result.uri then
		return
	end

	local bufnr = vim.uri_to_bufnr(result.uri)
	if not vim.api.nvim_buf_is_loaded(bufnr) then
		vim.fn.bufload(bufnr)
	end

	local line = result.line or 0
	local text = result.text or ""
	local cursor_pos = vim.api.nvim_win_get_cursor(0)
	local cursor_line = cursor_pos[1] - 1
	local cursor_col = cursor_pos[2]

	vim.api.nvim_buf_clear_namespace(bufnr, ns, 0, -1)

	if line == cursor_line then
		state.extmark = vim.api.nvim_buf_set_extmark(bufnr, ns, line, cursor_col, {
			virt_text = { { text, "Comment" } },
			virt_text_pos = "inline",
		})
		state.text = text
		state.line = line
		state.bufnr = bufnr
	end
end

vim.api.nvim_create_autocmd({ "InsertCharPre", "CursorMovedI", "TextChangedI", "InsertLeave" }, {
	callback = function(args)
		M.clear()

		local bufnr = args.buf
		local clients = vim.lsp.get_active_clients({ bufnr = bufnr })
		for _, client in ipairs(clients) do
			if client.name == "echo_lsp" then
				client.notify("$/cancelGhostText")
			end
		end
	end,
})

vim.api.nvim_create_autocmd("LspAttach", {
	callback = function(args)
		local client = vim.lsp.get_client_by_id(args.data.client_id)
		if not client or client.name ~= "echo_lsp" then
			return
		end

		local bufnr = args.buf

		vim.keymap.set("i", "<C-n>", function()
			local pos = vim.api.nvim_win_get_cursor(0)
			local uri = vim.uri_from_bufnr(bufnr)

			client.request("custom/triggerGhostText", {
				textDocument = { uri = uri },
				position = { line = pos[1] - 1, character = pos[2] },
			}, function(err)
				if err then
					vim.notify("Error triggering ghost text: " .. tostring(err), vim.log.levels.ERROR)
				end
			end, bufnr)
		end, { buffer = bufnr, desc = "Trigger Ghost Text" })

		vim.keymap.set("i", "<Tab>", function()
			print("working")
			if state.extmark then
				M.insert()
			else
				vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", true)
			end
		end, { buffer = bufnr, desc = "Accept Ghost Text" })
	end,
})

vim.g._echo_lsp_ghost_state = {
	extmark = function()
		return state.extmark
	end,
	text = function()
		return state.text
	end,
	line = function()
		return state.line
	end,
	bufnr = function()
		return state.bufnr
	end,
	clear = M.clear,
	insert = M.insert,
}
