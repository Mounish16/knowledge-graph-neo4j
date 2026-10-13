"""
streamlit_app.py
-----------------
A chat-style web UI for asking the Neo4j knowledge graph questions in
plain English, instead of typing them into a terminal loop.

This reuses the exact same Text2Cypher logic as llm_qa.py (imported
directly below, not duplicated): a local model via Ollama writes the
Cypher, Neo4j runs it, the model phrases the answer. Same safety
guardrail too -- any generated query with a write clause is refused
before it ever reaches Neo4j.

Setup:
    pip install -r requirements.txt   # adds streamlit
    streamlit run streamlit_app.py

Needs Neo4j (Docker) and Ollama already running -- see README.md in this
folder, or ../GETTING_STARTED.md for the full from-scratch walkthrough.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import streamlit as st
from neo4j import GraphDatabase

import llm_qa

st.set_page_config(page_title="Knowledge Graph Q&A", page_icon="🕸️", layout="centered")


# ----------------------------------------------------------------------
# connections
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_driver(uri: str, user: str, password: str):
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def check_ollama(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as response:
            json.loads(response.read().decode("utf-8"))
        return True, ""
    except urllib.error.URLError as exc:
        return False, str(exc)


def guess_browser_url(bolt_uri: str) -> str:
    """
    Neo4j Browser (the visual UI) runs on a different port (7474, plain
    HTTP) than the Bolt driver connection (7687). Guess the Browser URL
    from the Bolt URI's host, since they're almost always the same machine
    -- the sidebar field below lets you override this if not.
    """
    match = re.search(r"://([^:/]+)", bolt_uri)
    host = match.group(1) if match else "localhost"
    return f"http://{host}:7474"


# ----------------------------------------------------------------------
# sidebar: connection settings (defaults come from llm_qa.py's env vars)
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("Connection settings")
    neo4j_uri = st.text_input("Neo4j URI", value=llm_qa.NEO4J_URI)
    neo4j_user = st.text_input("Neo4j user", value=llm_qa.NEO4J_USER)
    neo4j_password = st.text_input("Neo4j password", value=llm_qa.NEO4J_PASSWORD, type="password")
    ollama_url = st.text_input("Ollama URL", value=llm_qa.OLLAMA_URL)
    ollama_model = st.text_input("Ollama model", value=llm_qa.OLLAMA_MODEL)

    # llm_qa.ollama_chat() reads these as module globals -- overriding them
    # here means the sidebar fields actually take effect
    llm_qa.OLLAMA_URL = ollama_url
    llm_qa.OLLAMA_MODEL = ollama_model

    st.divider()
    neo4j_browser_url = st.text_input("Neo4j Browser URL", value=guess_browser_url(neo4j_uri))
    st.link_button("Open Neo4j Browser 🡵", neo4j_browser_url, use_container_width=True)

    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

st.title("🕸️ Knowledge Graph Q&A")
st.caption(f"Neo4j + local model (`{ollama_model}` via Ollama) — Text2Cypher, read-only.")


# ----------------------------------------------------------------------
# connectivity checks
# ----------------------------------------------------------------------
neo4j_ok = True
driver = None
try:
    driver = get_driver(neo4j_uri, neo4j_user, neo4j_password)
except Exception as exc:
    neo4j_ok = False
    st.error(f"Can't connect to Neo4j at {neo4j_uri}: {exc}\n\nIs the container running? `docker compose up -d`")

ollama_ok, ollama_err = check_ollama(ollama_url)
if not ollama_ok:
    st.error(f"Can't reach Ollama at {ollama_url}: {ollama_err}\n\nIs it running? `ollama serve`")

if not (neo4j_ok and ollama_ok):
    st.stop()


# ----------------------------------------------------------------------
# schema (fetched once, shown collapsed)
# ----------------------------------------------------------------------
if "schema_text" not in st.session_state:
    with driver.session() as session:
        st.session_state.schema_text = llm_qa.get_schema_text(session)

with st.expander("Graph schema (sent to the model with every question)"):
    st.code(st.session_state.schema_text, language="text")


# ----------------------------------------------------------------------
# chat history
# ----------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # each: {role, content, cypher?, rows?}

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("cypher"):
            with st.expander("Cypher query used"):
                st.code(msg["cypher"], language="cypher")
                rows = msg.get("rows")
                if rows is not None:
                    st.caption(f"{len(rows)} row(s) returned")
                    if rows:
                        st.dataframe(rows)


# ----------------------------------------------------------------------
# ask a new question
# ----------------------------------------------------------------------
question = st.chat_input("Ask a question about the graph...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Generating Cypher..."):
            try:
                query = llm_qa.generate_cypher(st.session_state.schema_text, question)
            except RuntimeError as exc:
                st.error(str(exc))
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {exc}"})
                st.stop()

        with st.expander("Cypher query used", expanded=True):
            st.code(query, language="cypher")

        if not llm_qa.is_safe(query):
            refusal = "Refused: the generated query contained a write clause, so I didn't run it."
            st.warning(refusal)
            st.session_state.messages.append({"role": "assistant", "content": refusal, "cypher": query})
            st.stop()

        with st.spinner("Querying Neo4j..."):
            try:
                with driver.session() as session:
                    rows = llm_qa.run_query(session, query)
            except Exception as exc:
                failure = f"Query failed: {exc}"
                st.error(failure)
                st.session_state.messages.append({"role": "assistant", "content": failure, "cypher": query})
                st.stop()

        st.caption(f"{len(rows)} row(s) returned")
        if rows:
            st.dataframe(rows)

        with st.spinner("Phrasing answer..."):
            try:
                answer = llm_qa.synthesize_answer(question, query, rows)
            except RuntimeError as exc:
                answer = str(exc)

        st.write(answer)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "cypher": query, "rows": rows}
        )
