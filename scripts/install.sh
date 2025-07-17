#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/../server"
VENV_DIR="$SERVER_DIR/.venv"

# Create a virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  uv venv "$VENV_DIR"
fi

# Install dependencies
source "$VENV_DIR/bin/activate"
uv pip install -r "$SERVER_DIR/requirements.txt"
