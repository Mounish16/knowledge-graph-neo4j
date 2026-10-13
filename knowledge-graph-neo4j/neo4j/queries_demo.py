"""
queries_demo.py
----------------
Runs the same demo queries as ../main.py, but expressed as Cypher against a
real Neo4j database instead of Python code against the in-memory graph.

Each section maps onto a view a traceability console needs: lineage,
impact, coverage, and the quality counters (orphans, unverified). The
point of the pairing is that every one of them is a single Cypher pattern
over the same two relationship types -- no per-view schema, no
precomputed matrix to keep in sync.

Run load_data.py first, then:

    python queries_demo.py
"""

from __future__ import annotations

import os

from neo4j import GraphDatabase

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "password123")


def section(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> None:
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with driver.session() as session:
        section("1. Everything directly around HLR-001  (kg.neighbors equivalent)")
        result = session.run(
            "MATCH (h:Entity {name: 'HLR-001'})-[r]-(other) "
            "RETURN type(r) AS rel, other.name AS other, "
            "       [l IN labels(other) WHERE l <> 'Entity'][0] AS layer, "
            "       startNode(r).name = 'HLR-001' AS outgoing "
            "ORDER BY rel, other"
        )
        for record in result:
            arrow = "-->" if record["outgoing"] else "<--"
            print(f"   HLR-001 {arrow}[{record['rel']}]{arrow} "
                  f"{record['other']} ({record['layer']})")

        section("2. UPSTREAM -- full lineage of LLR-007, back to the customer")
        # variable-length path: *1.. means "one or more hops", which is
        # what turns a single-hop stored link into a full chain
        result = session.run(
            "MATCH (start:Entity {name: 'LLR-007'})-[:DERIVES_FROM*1..]->(a:Entity) "
            "RETURN a.name AS id, [l IN labels(a) WHERE l <> 'Entity'][0] AS layer, a.text AS text "
            "ORDER BY layer"
        )
        for record in result:
            print(f"   {record['id']:9} {record['layer']:20} {(record['text'] or '')[:44]}")

        section("3. DOWNSTREAM -- change impact of CR-001")
        result = session.run(
            "MATCH (d:Entity)-[:DERIVES_FROM*1..]->(:Entity {name: 'CR-001'}) "
            "RETURN [l IN labels(d) WHERE l <> 'Entity'][0] AS layer, count(d) AS affected "
            "ORDER BY affected DESC"
        )
        total = 0
        for record in result:
            total += record["affected"]
            print(f"   {record['layer']:22} {record['affected']:3} affected")
        print(f"   {'TOTAL':22} {total:3}")

        section("4. NEIGHBOURHOOD at depth 2  (the console's depth selector)")
        # both directions, up to 2 hops -- this is the whole "show me
        # everything near this node" view in one pattern
        result = session.run(
            "MATCH (pivot:Entity {name: 'HLR-001'})-[:DERIVES_FROM|VERIFIES*1..2]-(n:Entity) "
            "RETURN DISTINCT n.name AS id, [l IN labels(n) WHERE l <> 'Entity'][0] AS layer "
            "ORDER BY layer, id"
        )
        for record in result:
            print(f"   {record['id']:9} {record['layer']}")

        section("5. ORPHANS -- artefacts that trace to nothing")
        result = session.run(
            "MATCH (a:Entity) "
            "WHERE NOT (a)-[:DERIVES_FROM]->() "
            "  AND NOT a:CustomerRequest AND NOT a:Verification "
            "RETURN a.name AS id, [l IN labels(a) WHERE l <> 'Entity'][0] AS layer, a.text AS text"
        )
        rows = list(result)
        for record in rows:
            print(f"   {record['id']:9} {record['layer']:8} {(record['text'] or '')[:44]}")
        if not rows:
            print("   (none)")

        section("6. UNVERIFIED -- requirements with no verification evidence")
        result = session.run(
            "MATCH (h:HLR) WHERE NOT (h)<-[:VERIFIES]-() "
            "RETURN h.name AS id, h.status AS status, h.text AS text "
            "ORDER BY id"
        )
        for record in result:
            print(f"   {record['id']:9} {record['status']:9} {(record['text'] or '')[:40]}")

        section("7. COVERAGE -- has each customer request reached module design?")
        result = session.run(
            "MATCH (cr:CustomerRequest) "
            "OPTIONAL MATCH (mod:ModuleDesign)-[:DERIVES_FROM*1..]->(cr) "
            "RETURN cr.name AS id, cr.text AS text, "
            "       count(DISTINCT mod) AS modules "
            "ORDER BY modules ASC, id"
        )
        for record in result:
            flag = "  <-- no implementation" if record["modules"] == 0 else ""
            print(f"   {record['id']:8} {record['modules']:2} module(s)  "
                  f"{(record['text'] or '')[:36]}{flag}")

        section("8. Inference-as-a-query: which module implements which requirement")
        # this is the Cypher equivalent of rules.implements_rule -- instead
        # of a Python rule adding derived facts to the graph, the pattern
        # match IS the inference, recomputed fresh on every run so it can
        # never go stale against the authored links
        result = session.run(
            "MATCH (m:ModuleDesign)-[:DERIVES_FROM*1..]->(h:HLR) "
            "RETURN m.name AS module, collect(DISTINCT h.name) AS implements "
            "ORDER BY module"
        )
        for record in result:
            print(f"   {record['module']} implements {', '.join(sorted(record['implements']))}")

        section("9. Many-to-many: artefacts derived from more than one parent")
        result = session.run(
            "MATCH (a:Entity)-[:DERIVES_FROM]->(p:Entity) "
            "WITH a, collect(p.name) AS parents "
            "WHERE size(parents) > 1 "
            "RETURN a.name AS id, [l IN labels(a) WHERE l <> 'Entity'][0] AS layer, parents "
            "ORDER BY id"
        )
        for record in result:
            print(f"   {record['id']:9} {record['layer']:14} <- {', '.join(sorted(record['parents']))}")

        section("10. HLR LAYER ONLY -- how high-level requirements relate")
        # without the horizontal links this view would be disconnected
        # dots: an HLR links up to a system requirement and down to an
        # LLR, but never sideways to another HLR
        result = session.run(
            "MATCH (a:HLR)-[r:DEPENDS_ON|CONFLICTS_WITH]->(b:HLR) "
            "RETURN a.name AS a, type(r) AS rel, b.name AS b "
            "ORDER BY a, b"
        )
        for record in result:
            arrow = "conflicts with" if record["rel"] == "CONFLICTS_WITH" else "depends on"
            print(f"   {record['a']} {arrow} {record['b']}")

        section("11. LLR LAYER ONLY")
        result = session.run(
            "MATCH (a:LLR)-[r:DEPENDS_ON|CONFLICTS_WITH]->(b:LLR) "
            "RETURN a.name AS a, type(r) AS rel, b.name AS b "
            "ORDER BY a, b"
        )
        for record in result:
            arrow = "conflicts with" if record["rel"] == "CONFLICTS_WITH" else "depends on"
            print(f"   {record['a']} {arrow} {record['b']}")

        section("12. CONFLICTS -- requirements in tension, any layer")
        result = session.run(
            "MATCH (a)-[:CONFLICTS_WITH]->(b) "
            "RETURN a.name AS a, a.text AS text_a, b.name AS b, b.text AS text_b "
            "ORDER BY a"
        )
        for record in result:
            print(f"   {record['a']} <-> {record['b']}")
            print(f"      {record['a']}: {(record['text_a'] or '')[:52]}")
            print(f"      {record['b']}: {(record['text_b'] or '')[:52]}")

        section("13. WHAT BLOCKS THE MOST -- prerequisites by how much rests on them")
        result = session.run(
            "MATCH (dependent)-[:DEPENDS_ON*1..]->(prereq) "
            "RETURN prereq.name AS id, [l IN labels(prereq) WHERE l <> 'Entity'][0] AS layer, "
            "       count(DISTINCT dependent) AS waiting "
            "ORDER BY waiting DESC, id LIMIT 6"
        )
        for record in result:
            print(f"   {record['id']:9} {record['layer']:5} "
                  f"{record['waiting']} requirement(s) wait on it")

        section("14. Summary counters  (the console's header row)")
        artefacts = session.run("MATCH (a:Entity) RETURN count(a) AS n").single()["n"]
        links = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        orphans = session.run(
            "MATCH (a:Entity) WHERE NOT (a)-[:DERIVES_FROM]->() "
            "AND NOT a:CustomerRequest AND NOT a:Verification "
            "RETURN count(a) AS n"
        ).single()["n"]
        unverified = session.run(
            "MATCH (h:HLR) WHERE NOT (h)<-[:VERIFIES]-() RETURN count(h) AS n"
        ).single()["n"]
        print(f"   artefacts   {artefacts}")
        print(f"   links       {links}")
        print(f"   orphans     {orphans}")
        print(f"   unverified  {unverified}")

    driver.close()
    print("\nOpen http://localhost:7474 to see the same graph visually.")
    print("Start with:  MATCH (n)-[r]->(m) RETURN n, r, m")


if __name__ == "__main__":
    main()
