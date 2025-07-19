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
	if not (state.extmark and state.bufnr and state.line) then
		return
	end
	local line_content = vim.api.nvim_buf_get_lines(state.bufnr, state.line, state.line + 1, false)[1]
	local cursor_col = vim.api.nvim_win_get_cursor(0)[2]
	local new_line = line_content:sub(1, cursor_col) .. state.text .. line_content:sub(cursor_col + 1)
	vim.api.nvim_buf_set_lines(state.bufnr, state.line, state.line + 1, false, { new_line })
	local target_line, target_col = state.line, cursor_col + #state.text
	M.clear()
	vim.schedule(function()
		vim.api.nvim_win_set_cursor(0, { target_line + 1, target_col })
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
	local cursor_line = vim.api.nvim_win_get_cursor(0)[1] - 1
	local cursor_col = vim.api.nvim_win_get_cursor(0)[2]

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
		local clients = vim.lsp.get_active_clients({ bufnr = args.buf })
		local uri = vim.uri_from_bufnr(args.buf)
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
		if client.name ~= "echo_lsp" then
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
					vim.notify("GhostText error: " .. tostring(err), vim.log.levels.ERROR)
				end
			end, bufnr)
		end, { buffer = bufnr, desc = "Trigger Ghost Text" })

		vim.keymap.set("i", "<Tab>", function()
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
	insert = M.insert,
	clear = M.clear,
}
