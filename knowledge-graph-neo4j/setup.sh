#!/usr/bin/env bash
# Creates a virtual environment for this project. Since there are no
# third-party dependencies, this just isolates the Python interpreter --
# nothing gets pip-installed.
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
echo "Virtual environment created at .venv"
echo "Activate it with:"
echo "    source .venv/bin/activate"
echo "Then run the demo with:"
echo "    python main.py"
