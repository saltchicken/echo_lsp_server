# LLMCoder

LLMCoder is a Neovim plugin that provides code completion suggestions using a large language model (LLM). It integrates with Neovim's LSP client to provide inline ghost text suggestions that can be triggered manually or automatically.

## Features

-   **Code completion:** Get code suggestions from an LLM.
-   **Ghost text:** Display suggestions as inline ghost text.
-   **LSP integration:** Integrates with Neovim's built-in LSP client.
-   **Customizable:** Configure keymaps, ghost text appearance, and server settings.
-   **Automatic trigger:** Automatically trigger suggestions as you type.

## Prerequisites

-   Neovim >= 0.8
-   `uv` (for Python environment and package management)

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/llmcoder.git ~/.config/nvim/pack/plugins/start/llmcoder
    ```

2.  **Install the Python dependencies:**

    Run the installation script to create a virtual environment and install the required Python packages.

    ```bash
    ~/.config/nvim/pack/plugins/start/llmcoder/scripts/install.sh
    ```

## Configuration

To configure LLMCoder, add the following to your `init.lua`:

```lua
require('llmcoder').setup({
    keymaps = {
        trigger = '<C-n>',
        accept = '<Tab>',
    },
    ghost_text = {
        hl_group = 'Comment',
        enabled = true,
    },
    server = {
        launch_script = vim.fn.expand('~/.local/share/llmcoder/launch.sh'),
        filetypes = { 'text', 'markdown', 'lua', 'python', 'javascript', 'typescript' },
    },
    auto_trigger = {
        enabled = false,
        delay_ms = 500,
    },
})
```

### Options

-   `keymaps`:
    -   `trigger`: The keymap to trigger a code completion suggestion. Default: `<C-n>`.
    -   `accept`: The keymap to accept a suggestion. Default: `<Tab>`.
-   `ghost_text`:
    -   `hl_group`: The highlight group for the ghost text. Default: `Comment`.
    -   `enabled`: Whether to show ghost text. Default: `true`.
-   `server`:
    -   `launch_script`: The path to the server launch script.
    -   `filetypes`: The filetypes for which the LSP server should be active.
-   `auto_trigger`:
    -   `enabled`: Whether to automatically trigger suggestions as you type. Default: `false`.
    -   `delay_ms`: The delay in milliseconds before triggering a suggestion. Default: `500`.

## Usage

Once installed and configured, LLMCoder will automatically start when you open a file with a supported filetype.

-   **Trigger a suggestion:** Press the `trigger` keymap (default: `<C-n>`) in insert mode.
-   **Accept a suggestion:** Press the `accept` keymap (default: `<Tab>`) in insert mode.
-   **Cancel a suggestion:** Move the cursor or leave insert mode.

## How it Works

LLMCoder consists of two main components:

1.  **Lua frontend:** The Neovim plugin that interacts with the user and the Neovim API. It handles keymaps, displays ghost text, and communicates with the LSP server.
2.  **Python backend:** A Python-based LSP server that receives requests from the Neovim plugin, queries an LLM for code suggestions, and sends the suggestions back to the plugin.

The backend server communicates with an external LLM API to get code completion suggestions. The default endpoint is `http://localhost:8000/generate`. You can change this in the `server/llmcoder.py` file.
