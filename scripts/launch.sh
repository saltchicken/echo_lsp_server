#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/../server"
VENV_DIR="$SERVER_DIR/.venv"

export LLM_API_URL="${1:-http://main:8000/generate}"

# Activate the virtual environment and run the server
exec "$VENV_DIR/bin/python" "$SERVER_DIR/llmcoder.py"
