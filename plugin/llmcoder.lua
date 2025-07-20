print("hello")
local function find_git_root()
	local uv = vim.loop -- use luv bindings
	local cwd = uv.cwd()
	local home = os.getenv("HOME") or "~"

	local function is_git_dir(path)
		local stat = uv.fs_stat(path .. "/.git")
		return stat and (stat.type == "directory" or stat.type == "file")
	end

	local function is_home_or_root(path)
		return path == home or path == "/"
	end

	local function dirname(path)
		local pattern = package.config:sub(1, 1) == "\\" and "\\[^\\]+$" or "/[^/]+$"
		return path:match("^(.+)" .. pattern) or path
	end

	local dir = cwd
	while not is_home_or_root(dir) do
		if is_git_dir(dir) then
			return dir
		end
		local parent = dirname(dir)
		if parent == dir then
			break
		end
		dir = parent
	end

	-- fallback if no .git directory was found
	return cwd
end
