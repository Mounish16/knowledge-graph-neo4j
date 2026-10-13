"""
llm_qa.py
---------
Ask natural-language questions about the graph loaded into Neo4j (via
load_data.py) and get answers grounded in real Cypher query results --
this is Text2Cypher: the LLM writes the query, Neo4j runs it, the LLM
phrases the answer from the real rows that came back.

This version uses a LOCAL model through Ollama (https://ollama.com) instead
of a paid API -- no API key, no cost, nothing leaves your machine. Ollama
runs its own local HTTP server, so the only new thing this file needs is
Python's built-in `urllib` to talk to it -- no extra pip package either.

Two model calls per question:
  1. question + live graph schema  -> the model generates a Cypher query
  2. that query's real results     -> the model phrases the final answer

Safety: any generated query containing a write clause (CREATE, MERGE,
DELETE, SET, REMOVE, DROP, ...) is rejected before it ever touches Neo4j --
this process can only ever read the graph, never change it.

Setup:
    brew install ollama          # or see https://ollama.com/download
    ollama serve                 # starts the local model server (often auto-started already)
    ollama pull qwen2.5-coder:7b # downloads the model once (a few GB)
    python load_data.py          # make sure the graph is loaded first
    python llm_qa.py

Then just type questions, e.g.:
    > Which requirements derive from HLR-001?
    > What does LLR-007 ultimately trace back to?
    > Which high-level requirements have no verification?
    > exit
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password123")

# a code-tuned model tends to write noticeably more correct Cypher than a
# generic chat model at the same size -- swap via OLLAMA_MODEL if you'd
# rather use something else you already have pulled (e.g. "llama3.1:8b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

# Cypher clauses that could modify the database -- a generated query
# matching any of these (case-insensitive, whole word) is rejected before
# it ever runs. This is the guardrail: read-only, always.
WRITE_CLAUSES = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH|LOAD\s+CSV)\b"
    r"|CALL\s+apoc\.",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# talking to the local Ollama server (plain HTTP, stdlib only)
# ----------------------------------------------------------------------
def ollama_chat(prompt: str, max_tokens: int = 500) -> str:
    """
    Send one prompt to the local Ollama model and return its reply text.
    Uses Ollama's /api/chat endpoint with streaming turned off, so the
    whole response comes back in one JSON object.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL} ({exc}). "
            f"Is it running? Try: ollama serve"
        ) from exc
    return data["message"]["content"].strip()


def check_ollama_ready() -> None:
    """Fail fast with a helpful message if Ollama isn't up or the model isn't pulled yet."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"Could not reach Ollama at {OLLAMA_URL} ({exc}).")
        print("Is it running? Try: ollama serve")
        sys.exit(1)

    available = {m["name"] for m in data.get("models", [])}
    # Ollama model names sometimes show with an implicit ":latest" tag
    if OLLAMA_MODEL not in available and f"{OLLAMA_MODEL}:latest" not in available:
        print(f"Model '{OLLAMA_MODEL}' isn't pulled yet. Run:")
        print(f"    ollama pull {OLLAMA_MODEL}")
        sys.exit(1)


# ----------------------------------------------------------------------
# schema introspection
# ----------------------------------------------------------------------
def get_schema_text(session) -> str:
    """
    Pull the graph's actual current shape straight from Neo4j (labels,
    relationship types, property keys, plus a handful of real example
    relationships) so the prompt we hand the model never goes stale, even
    if you load more data later.
    """
    labels = [r["label"] for r in session.run("CALL db.labels() YIELD label RETURN label")]
    rel_types = [
        r["relationshipType"]
        for r in session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
    ]
    prop_keys = [
        r["propertyKey"] for r in session.run("CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey")
    ]

    examples = session.run(
        "MATCH (a)-[r]->(b) RETURN labels(a) AS a_labels, a.name AS a_name, "
        "type(r) AS rel, labels(b) AS b_labels, b.name AS b_name LIMIT 10"
    )
    example_lines = [
        f"({rec['a_name']}:{'/'.join(rec['a_labels'])})-[:{rec['rel']}]->"
        f"({rec['b_name']}:{'/'.join(rec['b_labels'])})"
        for rec in examples
    ]

    return (
        f"Node labels: {', '.join(labels)}\n"
        f"Relationship types: {', '.join(rel_types)}\n"
        f"Property keys: {', '.join(prop_keys)}\n"
        f"Example relationships:\n  " + "\n  ".join(example_lines)
    )


# ----------------------------------------------------------------------
# the two model calls
# ----------------------------------------------------------------------
def generate_cypher(schema_text: str, question: str) -> str:
    """Ask the local model to translate one natural-language question into one Cypher query."""
    prompt = f"""You translate natural-language questions into Cypher queries for a Neo4j database.

Graph schema:
{schema_text}

Rules:
- Output ONLY the Cypher query, nothing else -- no explanation, no markdown fences.
- Only ever write read-only queries (MATCH / RETURN / WHERE / WITH / ORDER BY / LIMIT). Never write, modify, or delete data.
- Every node has a "name" property you can match on, e.g. {{name: "HLR-001"}}.
- Nodes also carry "text" (the requirement wording) and "status" properties.
- If the question asks about a relationship or connection between two named things, use an undirected pattern like (a)-[r]-(b) unless direction is clearly implied by the question.
- If unsure of the exact relationship type, match any relationship with -[r]- rather than guessing a type name.

Question: {question}

Cypher query:"""

    query = ollama_chat(prompt, max_tokens=300)
    # local models are fairly likely to wrap the answer in a
    # markdown fence anyway -- strip it if present
    query = re.sub(r"^```(?:cypher)?\s*|\s*```$", "", query, flags=re.IGNORECASE).strip()
    return query


def is_safe(query: str) -> bool:
    """True if the query contains no write clause -- the only gate before execution."""
    return not WRITE_CLAUSES.search(query)


def run_query(session, query: str) -> list[dict]:
    result = session.run(query)
    return [dict(record) for record in result]


def synthesize_answer(question: str, query: str, rows: list[dict]) -> str:
    """Ask the local model to phrase a plain-English answer, grounded only in the real query results."""
    prompt = f"""A user asked a question about a knowledge graph. Here is the Cypher query that was run against it and its real results. Answer the question in plain, natural language using ONLY this data -- do not add anything not present in the results. If the results are empty, say so plainly instead of guessing.

Question: {question}

Cypher query that was run:
{query}

Query results (as Python-style records):
{rows}

Answer:"""

    return ollama_chat(prompt, max_tokens=300)


def answer_question(session, schema_text: str, question: str) -> None:
    try:
        query = generate_cypher(schema_text, question)
    except RuntimeError as exc:
        print(f"  {exc}")
        return
    print(f"\n  Cypher: {query}")

    if not is_safe(query):
        print("  Refused: generated query contained a write clause -- not running it.")
        return

    try:
        rows = run_query(session, query)
    except Exception as exc:
        print(f"  Query failed: {exc}")
        return

    print(f"  Rows returned: {len(rows)}")
    try:
        answer = synthesize_answer(question, query, rows)
    except RuntimeError as exc:
        print(f"  {exc}")
        return
    print(f"\n  Answer: {answer}")


def main() -> None:
    check_ollama_ready()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"Could not connect to Neo4j at {NEO4J_URI}: {exc}")
        print("Is the container running, and did you run load_data.py?")
        sys.exit(1)

    with driver.session() as session:
        schema_text = get_schema_text(session)
        print(f"Connected. Using local model '{OLLAMA_MODEL}' via Ollama. Graph schema:\n")
        print(schema_text)
        print("\nAsk a question about the graph (or type 'exit'):\n")

        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question:
                continue
            if question.lower() in {"exit", "quit"}:
                break
            answer_question(session, schema_text, question)

    driver.close()
    print("\nGoodbye.")


if __name__ == "__main__":
    main()
