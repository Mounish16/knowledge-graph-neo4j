"""
main.py
-------
Runnable demo that ties everything together:

  1. build the requirements traceability graph
  2. run some example queries
  3. trace a module design back to the customer request it serves
  4. run inference rules to derive lineage, impact and allocation
  5. save the graph to JSON and reload it (round-trip check)
  6. export interactive HTML visualizations

Run it with:
    python main.py
"""

from knowledge_graph import KnowledgeGraph
from sample_data import build_sample_graph
from rules import ALL_RULES
from viz import export_html


def section(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def describe(kg: KnowledgeGraph, artefact_id: str) -> str:
    text = kg.entity_attrs.get(artefact_id, {}).get("text", "")
    return f"{artefact_id}: {text}"


def main() -> None:
    kg = build_sample_graph()

    section("1. The whole graph")
    print(kg.pretty_print())

    # export the AUTHORED graph before inference runs, so the visual shows
    # the links a person actually wrote rather than every derived one --
    # the inferred version is exported separately at the end
    export_html(kg, "graph.html", title="Requirements Traceability (authored links)")

    section("2. Query examples")
    print("Everything HLR-001 derives from:")
    for _, _, parent in kg.query(subject="HLR-001", predicate="derives_from"):
        print("   ", describe(kg, parent))

    print("\nWhat derives from HLR-001?")
    for child, _, _ in kg.query(predicate="derives_from", obj="HLR-001"):
        print("   ", describe(kg, child))

    print("\nHLR-001's immediate neighbours:")
    neighbours = kg.neighbors("HLR-001")
    for predicate, obj in neighbours["outgoing"]:
        print(f"    --{predicate}--> {obj}")
    for predicate, subject in neighbours["incoming"]:
        print(f"    <--{predicate}-- {subject}")

    section("3. Path finding -- module design back to the customer request")
    # NOTE: a full chain is 7 hops (MOD -> LLD -> HLD -> LLR -> HLR -> SYS
    # -> SN -> CR), which is deeper than find_path's default max_depth=6,
    # so the limit has to be raised explicitly here
    path = kg.find_path("MOD-001", "CR-001", max_depth=10)
    print("Shortest connection from MOD-001 to CR-001:")
    if path is None:
        print("   no path found")
    else:
        for step in path:
            print("   ", step)

    section("4. Inference (forward chaining)")
    print("Facts before inference:", len(kg))
    for rule in ALL_RULES:
        new_facts = kg.infer(rule)
        print(f"Rule '{rule.__name__}' derived {len(new_facts)} new fact(s)")
    print("Facts after inference:", len(kg))

    print("\nFull upstream lineage of LLR-007:")
    for _, _, ancestor in sorted(kg.query(subject="LLR-007", predicate="traces_to")):
        print("   ", describe(kg, ancestor))

    print("\nWhat MOD-001 implements:")
    for _, _, hlr in sorted(kg.query(subject="MOD-001", predicate="implements")):
        print("   ", describe(kg, hlr))

    section("4b. Horizontal links -- relationships within a single layer")
    print("HLR layer, on its own:")
    for a, predicate, b in sorted(kg.query(predicate="depends_on")):
        if a.startswith("HLR-"):
            print(f"    {a} depends on {b}")
    print("\nRequirements in tension (conflicts are stored one way, derived both):")
    seen = set()
    for a, _, b in sorted(kg.query(predicate="conflicts_with")):
        if (b, a) in seen:
            continue
        seen.add((a, b))
        print(f"    {a} <-> {b}")
        print(f"       {describe(kg, a)}")
        print(f"       {describe(kg, b)}")

    print("\nWhat LLR-018 ultimately rests on (walking the whole chain):")
    for _, _, prereq in sorted(kg.query(subject="LLR-018", predicate="requires")):
        print("   ", describe(kg, prereq))

    section("5. Save / load round-trip")
    kg.save_json("graph_export.json")
    reloaded = KnowledgeGraph.load_json("graph_export.json")
    assert reloaded.triples == kg.triples, "round-trip mismatch!"
    print(f"Saved to graph_export.json and reloaded successfully "
          f"({len(reloaded)} facts, {len(reloaded.entities())} entities).")

    section("6. HTML visualizations")
    export_html(kg, "graph_inferred.html",
                title="Requirements Traceability (including inferred links)")
    print("Wrote graph.html          -- the authored links only")
    print("Wrote graph_inferred.html -- the same graph plus everything derived")
    print("Open either in any browser (no server needed).")


if __name__ == "__main__":
    main()
