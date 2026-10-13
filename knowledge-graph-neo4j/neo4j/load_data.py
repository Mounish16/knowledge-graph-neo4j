"""
load_data.py
------------
Loads the SAME sample knowledge graph used by the vanilla version
(../sample_data.py) into a real Neo4j database running in Docker.

Every entity becomes a Neo4j node (labeled by its "type" attribute, e.g.
:HLR, :LLR, :ModuleDesign), and every (subject, predicate, object) fact
becomes a directed relationship, e.g.:

    (LLR-001:LLR)-[:DERIVES_FROM]->(HLR-001:HLR)
    (VER-001:Verification)-[:VERIFIES]->(HLR-001:HLR)

Run docker-compose up first (see docker-compose.yml in this folder), then:

    python load_data.py

Connection settings can be overridden with environment variables:
    NEO4J_URI       (default: bolt://localhost:7687)
    NEO4J_USER      (default: neo4j)
    NEO4J_PASSWORD  (default: password123 -- must match docker-compose.yml)
"""

from __future__ import annotations

import os
import sys

# reuse the exact same sample data as the vanilla version, one folder up
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sample_data import build_sample_graph  # noqa: E402

from neo4j import GraphDatabase

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "password123")

# map our generic entity "type" attribute onto a Neo4j label.
# Anything missing here silently falls back to the generic "Entity" label,
# which would collapse every layer into one and break label-specific
# queries -- so every type used in sample_data.py must appear below.
TYPE_TO_LABEL = {
    "customer_request": "CustomerRequest",
    "stakeholder_need": "StakeholderNeed",
    "system_requirement": "SystemRequirement",
    "safety_requirement": "SafetyRequirement",
    "hlr": "HLR",
    "llr": "LLR",
    "hld": "HLD",
    "lld": "LLD",
    "module_design": "ModuleDesign",
    "verification": "Verification",
}


def clear_database(tx):
    """Wipe everything so re-running this script is always safe/repeatable."""
    tx.run("MATCH (n) DETACH DELETE n")


def merge_entity(tx, name: str, entity_type: str, attrs: dict) -> None:
    """
    Create (or update) one node. Every node gets a generic :Entity label
    (handy for label-agnostic queries) PLUS a specific label like :Person.
    MERGE means "create if missing, otherwise reuse the existing node" --
    that's what makes this safe to run more than once.
    """
    label = TYPE_TO_LABEL.get(entity_type, "Entity")
    # label names come from our own fixed mapping above, never from user
    # input, so it's safe to interpolate them directly into the query text
    # (Neo4j doesn't allow parameterizing labels/relationship types).
    tx.run(
        f"MERGE (n:Entity:{label} {{name: $name}}) SET n += $attrs",
        name=name,
        attrs=attrs,
    )


def merge_relationship(tx, subject: str, predicate: str, obj: str) -> None:
    """Create (or reuse) one relationship between two already-loaded nodes."""
    rel_type = predicate.upper()  # Neo4j convention: RELATIONSHIP_TYPES_LIKE_THIS
    tx.run(
        f"""
        MATCH (a:Entity {{name: $subject}}), (b:Entity {{name: $obj}})
        MERGE (a)-[:{rel_type}]->(b)
        """,
        subject=subject,
        obj=obj,
    )


def main() -> None:
    kg = build_sample_graph()

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"Could not connect to Neo4j at {URI}: {exc}")
        print("Is the container running? Try: docker compose up -d")
        sys.exit(1)

    with driver.session() as session:
        print("Clearing existing data...")
        session.execute_write(clear_database)

        print(f"Loading {len(kg.entities())} entities...")
        for name in kg.entities():
            attrs = kg.entity_attrs.get(name, {})
            entity_type = attrs.get("type", "")
            clean_attrs = {k: v for k, v in attrs.items() if k != "type"}
            session.execute_write(merge_entity, name, entity_type, clean_attrs)

        print(f"Loading {len(kg.triples)} relationships...")
        for subject, predicate, obj in sorted(kg.triples):
            session.execute_write(merge_relationship, subject, predicate, obj)

    driver.close()
    print("\nDone.")
    print("Open http://localhost:7474 in your browser (login: neo4j / password123)")
    print("and try this query to see the whole graph:")
    print("    MATCH (n)-[r]->(m) RETURN n, r, m")


if __name__ == "__main__":
    main()
