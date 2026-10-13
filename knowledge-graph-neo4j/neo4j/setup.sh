#!/usr/bin/env bash
# Creates a virtual environment for the Neo4j scripts in this folder and
# installs the one real dependency (the official neo4j Python driver).
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "Virtual environment ready at neo4j/.venv"
echo ""
echo "Next steps:"
echo "  1. docker compose up -d          # start Neo4j"
echo "  2. source .venv/bin/activate     # activate this venv (if not already)"
echo "  3. python load_data.py           # load the sample graph into Neo4j"
echo "  4. python queries_demo.py        # run the demo queries"
echo "  5. open http://localhost:7474    # explore visually (login: neo4j / password123)"
