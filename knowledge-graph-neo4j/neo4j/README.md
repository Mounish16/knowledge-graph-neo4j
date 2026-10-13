# Neo4j, Cypher and the Streamlit Q&A app

This folder is the database-backed half of the [Requirements Traceability Knowledge Graph](../README.md). It loads the same 68-artefact sample graph defined in `../sample_data.py` into a Neo4j server running in Docker, queries it with Cypher, and lets you ask questions in plain English through a local model.

The top-level README covers the data model, architecture and full setup. This page is the short reference for this folder.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Starts Neo4j 5 with Neo4j Browser on port 7474 and Bolt on 7687, with a persistent volume |
| `requirements.txt` | Python dependencies: the `neo4j` driver and `streamlit` |
| `setup.sh` | macOS / Linux helper: creates `.venv` and installs the requirements |
| `load_data.py` | Clears the database and loads every artefact as a labelled node and every link as a relationship |
| `queries_demo.py` | 14 Cypher sections run from Python: lineage, impact, depth-2 neighbourhood, orphans, unverified requirements, coverage, allocation, multi-parent artefacts, single-layer views, conflicts, bottlenecks, summary counters |
| `layer_views.cypher` | Views to paste into Neo4j Browser one at a time (HLR layer, LLR layer, conflicts, dependency chains, the full picture) |
| `llm_qa.py` | Text2Cypher on the terminal: a local model writes Cypher, Neo4j runs it, the model phrases the answer |
| `streamlit_app.py` | A chat web UI around `llm_qa.py` |

## Run order

```bash
docker compose up -d                 # 1. start Neo4j, wait for "Started." in: docker compose logs -f
python3 -m venv .venv                # 2. create an environment
source .venv/bin/activate            #    Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python load_data.py                  # 3. load the graph (68 nodes, 91 relationships)
python queries_demo.py               # 4. run the Cypher demo
streamlit run streamlit_app.py       # 5. chat UI at http://localhost:8501 (needs Ollama, below)
```

Neo4j Browser: http://localhost:7474, login `neo4j` / `password123` (a local development default in `docker-compose.yml`). To see the whole graph, run `MATCH (n)-[r]->(m) RETURN n, r, m`.

## Plain-English Q&A (Text2Cypher)

`llm_qa.py` and `streamlit_app.py` use a local model through [Ollama](https://ollama.com). Per question there are two model calls:

1. The question plus the live graph schema (labels, relationship types, properties and example relationships read from Neo4j) produce a Cypher query.
2. The real rows returned by that query produce the final answer, so answers are grounded in what is in the graph.

```bash
ollama serve                    # skip if the Ollama app or service is already running
ollama pull qwen2.5-coder:7b    # once; a few GB
python llm_qa.py                # terminal prompt
streamlit run streamlit_app.py  # or the chat UI
```

Example questions: *Which requirements derive from HLR-001? What does LLR-007 ultimately trace back to? Which high-level requirements have no verification?*

Every answer shows the generated Cypher. **Safety:** a generated query containing a write clause (`CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `DETACH`, `LOAD CSV`, `apoc` calls) is refused before it reaches Neo4j. This is a keyword check; for a real deployment also connect as a read-only Neo4j user.

A small local model is weaker at Cypher than a large hosted one. If you get "Query failed" or an odd answer, name the exact relationship in your question, or use a bigger model:

```bash
ollama pull qwen2.5-coder:14b
export OLLAMA_MODEL=qwen2.5-coder:14b      # Windows PowerShell: $env:OLLAMA_MODEL="qwen2.5-coder:14b"
```

## How the mapping works

Each entity becomes a node with two labels: the generic `:Entity` and a specific one from its `type` (`:HLR`, `:LLR`, `:ModuleDesign`, and so on, mapped in `TYPE_TO_LABEL` in `load_data.py`). Each `(subject, predicate, object)` fact becomes a directed relationship with the predicate upper-cased (`derives_from` becomes `:DERIVES_FROM`). Attributes such as `text`, `status` and `programme` become node properties.

`load_data.py` wipes the database (`MATCH (n) DETACH DELETE n`) and reloads with `MERGE`, so re-running it never creates duplicates. Only the authored links are loaded; the derived ones (`traces_to`, `impacts`, `implements`, `requires`) come from the rules in `../rules.py`, and the Cypher scripts recompute the same answers with path patterns.

## Configuration

| Variable | Default |
|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | `password123` (must match `NEO4J_AUTH` in `docker-compose.yml`) |
| `OLLAMA_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` |

## Stopping and resetting

```bash
docker compose down       # stop Neo4j, keep the data volume
docker compose down -v    # stop Neo4j and delete all stored data
```
