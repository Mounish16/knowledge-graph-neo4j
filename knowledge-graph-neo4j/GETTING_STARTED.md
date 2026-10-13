# Getting started — from a completely empty machine

This guide assumes you have **nothing** installed yet: no Docker, no
Ollama, no Python virtual environment, nothing. Follow it top to bottom and
you'll end up with a working knowledge graph in Neo4j that you can ask
questions of in plain English, using a free local AI model.

Total one-time setup time: roughly 20-40 minutes, mostly spent waiting on
downloads (Docker Desktop, the Neo4j image, and the Ollama model are each a
few hundred MB to a few GB).

Everything below is written for **macOS** (Terminal / VS Code's integrated
terminal). If you're on Windows or Linux, see the note at the very bottom.

---

## Part 1 — Install the prerequisites (one time only)

### 1a. Install Docker Desktop

Docker Desktop is what runs the Neo4j database. Download and install it
from:

https://www.docker.com/products/docker-desktop/

After installing, **open the Docker Desktop app** and wait for it to
finish starting (the whale icon in your menu bar stops animating and shows
"Docker Desktop is running"). Leave it running in the background — you'll
need it every time you use this project.

Verify it worked:

```bash
docker --version
docker compose version
```

Both should print a version number, not an error.

### 1b. Install Ollama

Ollama is what runs the free local AI model. If you have Homebrew:

```bash
brew install ollama
```

If you don't have Homebrew, download the installer instead from:

https://ollama.com/download

Verify it worked:

```bash
ollama --version
```

---

## Part 2 — Get the project files

Clone the repository (or unzip a downloaded copy) anywhere you like, then
open a terminal in that folder.

```bash
git clone https://github.com/Mounish16/knowledge-graph-neo4j.git
cd knowledge-graph-neo4j
```

---

## Part 3 — One-time setup inside the project

Run these once. After today, you won't need to repeat this part.

```bash
# 1. start the Neo4j database in Docker (downloads the Neo4j image the first time — a few hundred MB)
cd neo4j
docker compose up -d
docker compose logs -f
# wait until you see a line containing "Started." then press Ctrl+C (Neo4j keeps running)

# 2. set up Python and install the one real dependency (the neo4j driver)
bash setup.sh
source .venv/bin/activate

# 3. load the sample knowledge graph (people/companies/cities) into Neo4j
python load_data.py

# 4. download the local AI model (a few GB, only needs to happen once)
ollama pull qwen2.5-coder:7b
```

If your machine is low on disk space or memory, you can substitute a
smaller model in step 4:

```bash
ollama pull llama3.2
```
(then always set `export OLLAMA_MODEL=llama3.2` before running `llm_qa.py`
in Part 4 below, since the smaller model isn't the default)

---

## Part 4 — Every time you want to use it

Once Part 1-3 are done, this is the routine to come back to it later
(after a reboot, closing the terminal, etc.):

```bash
# 1. make sure Docker Desktop is open and running (check the whale icon)

# 2. start Neo4j
cd path/to/knowledge-graph-neo4j/neo4j
docker compose up -d

# 3. start Ollama's local server — needs its OWN terminal tab, since it stays running in the foreground
ollama serve
```

(Optional: run `brew services start ollama` once instead of step 3, and
Ollama will always run quietly in the background from then on — you can
skip step 3 for good.)

Back in your main terminal tab:

```bash
# 4. activate the Python environment (already created in Part 3)
source .venv/bin/activate

# 5. ask the graph questions in plain English
python llm_qa.py
```

Then just type questions at the `>` prompt, for example:

```
> Which requirements derive from HLR-001?
> What does LLR-007 ultimately trace back to?
> Which high-level requirements have no verification?
> exit
```

Two other things you can run instead of/alongside `llm_qa.py`:

```bash
python queries_demo.py   # a fixed set of demo Cypher queries, no AI model involved
open http://localhost:7474   # Neo4j's own visual graph browser (login: neo4j / password123)
```

---

## Part 5 — Shutting down

```bash
deactivate               # leave the Python environment
docker compose down      # stop Neo4j (your data is kept)
```
Then just close (or Ctrl+C) the terminal tab running `ollama serve`, if you
started it manually rather than via `brew services`.

To wipe the loaded graph data entirely and start fresh later:
```bash
docker compose down -v   # stop Neo4j AND delete all stored data
python load_data.py      # reloads the original sample data next time
```

---

## Troubleshooting

**`docker compose up -d` fails with a connection error.** Docker Desktop
isn't running yet — open the app, wait for the whale icon to settle, then
retry.

**`python load_data.py` can't connect.** Neo4j usually needs 15-30 seconds
after `docker compose up -d` before it's ready. Rerun
`docker compose logs -f`, wait for "Started.", then retry.

**`ollama pull` or `python llm_qa.py` says it can't reach Ollama.** Make
sure `ollama serve` is actually running in some terminal tab (or that
`brew services start ollama` was run once).

**A question comes back with "Query failed" or a strange answer.** The
local AI model is much smaller than a hosted one and occasionally writes
an imperfect query. Try rephrasing the question more specifically (name
the exact relationship you're asking about), or try a larger model if your
machine can handle it: `ollama pull qwen2.5-coder:14b` then
`export OLLAMA_MODEL=qwen2.5-coder:14b`.

---

## Windows / Linux notes

- **Docker Desktop** is available for Windows and Linux at the same link
  above; on Linux you can alternatively install Docker Engine + the
  `docker-compose-plugin` via your package manager.
- **Ollama** has a native Windows installer and a Linux install script,
  both linked from https://ollama.com/download.
- All the `bash`/`python`/`docker` commands above work as-is in a Linux
  terminal or in WSL (Windows Subsystem for Linux) on Windows. If you're
  using plain Windows PowerShell instead of WSL, replace
  `source .venv/bin/activate` with `.venv\Scripts\activate` and
  `bash setup.sh` with manually running `python -m venv .venv` followed by
  `pip install -r requirements.txt`.
