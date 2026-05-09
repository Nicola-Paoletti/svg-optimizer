#!/bin/bash
# Double-click this file to launch SVG Optimizer.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"

# Check Python3 is available
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  ERROR: Python3 is not installed on this machine."
    echo "  Please install it from https://www.python.org/downloads/"
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

# First run: create virtual environment and install dependencies
if [ ! -d "$VENV" ]; then
    echo ""
    echo "  First launch — setting up (this takes about 30 seconds)..."
    echo ""
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r requirements.txt
    echo "  Setup complete!"
    echo ""
fi

"$VENV/bin/python3" optimize.py
