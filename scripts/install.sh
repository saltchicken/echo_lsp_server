#!/bin/bash
set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/../server"
VENV_DIR="$SERVER_DIR/.venv"

# Create a virtual environment using uv
if [ ! -d "$VENV_DIR" ]; then
  uv venv "$VENV_DIR"
  echo "Virtual environment created at $VENV_DIR"
fi

# Make the server executable
chmod +x "$SERVER_DIR/echo_lsp_server.py"

echo "Installation complete."
