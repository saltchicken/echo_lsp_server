local M = {}

local ns = vim.api.nvim_create_namespace("ghost_text")
local state = {
	extmark = nil,
	text = nil,
	line = nil,
	bufnr = nil,
}

function M.clear()
	if state.bufnr then
		vim.api.nvim_buf_clear_namespace(state.bufnr, ns, 0, -1)
	end
	state.extmark = nil
	state.text = nil
	state.line = nil
	state.bufnr = nil
end

function M.insert()
	local bufnr = state.bufnr
	local line = state.line
	local ghost = state.text
	local extmark = state.extmark

	if not (bufnr and line and ghost and extmark) then
		print("Insert failed: ghost text state incomplete")
		return
	end

	local cursor = vim.api.nvim_win_get_cursor(0)
	if cursor[1] - 1 ~= line then
		print("Insert failed: not on ghost text line")
		return
	end

	local col = cursor[2]
	local lines = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)
	if not lines or not lines[1] then
		return
	end

	local new_line = lines[1]:sub(1, col) .. ghost .. lines[1]:sub(col + 1)
	vim.api.nvim_buf_set_lines(bufnr, line, line + 1, false, { new_line })

	vim.schedule(function()
		vim.api.nvim_win_set_cursor(0, { line + 1, col + #ghost })
	end)

	M.clear()
end

-- Handler for custom LSP notification: ghostText/virtualText
vim.lsp.handlers["ghostText/virtualText"] = function(_, result)
	if not result or not result.uri then
		print("ghostText handler: missing result or URI")
		return
	end

	local bufnr = vim.uri_to_bufnr(result.uri)
	if not vim.api.nvim_buf_is_loaded(bufnr) then
		vim.fn.bufload(bufnr)
	end

	local line = result.line or 0
	local text = result.text or ""

	if not text or text == "" then
		M.clear()
		return
	end

	local cursor = vim.api.nvim_win_get_cursor(0)
	local cursor_line = cursor[1] - 1
	local cursor_col = cursor[2]

	vim.api.nvim_buf_clear_namespace(bufnr, ns, 0, -1)

	if line == cursor_line then
		local extmark = vim.api.nvim_buf_set_extmark(bufnr, ns, line, cursor_col, {
			virt_text = { { text, "Comment" } },
			virt_text_pos = "inline",
		})

		state.extmark = extmark
		state.text = text
		state.line = line
		state.bufnr = bufnr

		print("ghostText set at line", line, "with text:", text)
	else
		M.clear()
	end
end

-- Keymap setup
vim.keymap.set("i", "<Tab>", function()
	require("echo_lsp.ghost").insert()
end, { desc = "Accept ghost text", noremap = true, silent = true })

return M
