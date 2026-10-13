"""
rules.py
--------
Inference rules for KnowledgeGraph.infer(), for the requirements
traceability graph.

Each rule is a plain function: it takes the graph and yields NEW triples
that logically follow from the facts already there. Forward chaining, no
external logic engine.

Why this matters for traceability: the graph only stores single-hop
`derives_from` links, because that is all anyone actually authors. Every
question a traceability console asks -- full lineage, impact of a change,
which module implements which requirement -- is derived from those single
hops rather than stored separately. That means the derived answers can
never drift out of sync with the authored links.
"""

from __future__ import annotations

from typing import Iterator

from knowledge_graph import KnowledgeGraph, Triple


def _entity_type(kg: KnowledgeGraph, name: str) -> str:
    return kg.entity_attrs.get(name, {}).get("type", "")


def _ancestors(kg: KnowledgeGraph, start: str) -> set[str]:
    """Every artefact reachable by following derives_from upwards.

    Walks the whole chain rather than a single hop, so one application of
    the rule produces the complete closure. `seen` also guards against a
    circular derives_from chain, which would otherwise loop forever --
    requirements shouldn't contain cycles, but a graph built from real
    data eventually will, and this is where it would bite.
    """
    found: set[str] = set()
    stack = [start]
    seen = {start}
    while stack:
        node = stack.pop()
        for _, _, parent in kg.query(subject=node, predicate="derives_from"):
            if parent not in seen:
                seen.add(parent)
                found.add(parent)
                stack.append(parent)
    return found


def transitive_trace_rule(kg: KnowledgeGraph) -> Iterator[Triple]:
    """
    If X derives_from Y, and Y derives_from Z (to any depth), infer
    X traces_to Z.

    e.g. LLR-007 derives_from HLR-003, HLR-003 derives_from SYS-002,
         SYS-002 derives_from SN-002, SN-002 derives_from CR-002
         => LLR-007 traces_to CR-002

    This is the "why does this requirement exist?" question, answered for
    every artefact at once. Note it yields the full closure in a single
    pass, not one hop per application.
    """
    subjects = {s for s, _, _ in kg.query(predicate="derives_from")}
    for subject in sorted(subjects):
        for ancestor in sorted(_ancestors(kg, subject)):
            yield (subject, "traces_to", ancestor)


def impact_rule(kg: KnowledgeGraph) -> Iterator[Triple]:
    """
    If X derives_from Y, then Y impacts X.

    The inverse edge, made explicit. `derives_from` answers "what does
    this come from"; `impacts` answers "what breaks if I change this" --
    the same link read the other way, which is the downstream direction a
    change-impact view needs.
    """
    for child, _, parent in kg.query(predicate="derives_from"):
        yield (parent, "impacts", child)


def implements_rule(kg: KnowledgeGraph) -> Iterator[Triple]:
    """
    If a module design traces (at any depth) back to a high-level
    requirement, infer that the module implements it.

    e.g. MOD-001 -> LLD-001 -> HLD-001 -> LLR-001 -> HLR-001
         => MOD-001 implements HLR-001

    This is the allocation question -- "which piece of hardware or
    software actually delivers this requirement" -- which is normally
    maintained as a separate hand-written matrix that goes stale. Here it
    falls out of the links that already exist.
    """
    for name in kg.entities():
        if _entity_type(kg, name) != "module_design":
            continue
        for ancestor in sorted(_ancestors(kg, name)):
            if _entity_type(kg, ancestor) == "hlr":
                yield (name, "implements", ancestor)


def conflict_is_symmetric_rule(kg: KnowledgeGraph) -> Iterator[Triple]:
    """
    If A conflicts_with B, then B conflicts_with A.

    A conflict between two requirements isn't directional -- neither one
    "owns" it -- but authoring it twice would be duplication that can fall
    out of step. So it's stored one way and the reverse is derived, which
    means a query starting from either requirement finds it.
    """
    for a, _, b in kg.query(predicate="conflicts_with"):
        yield (b, "conflicts_with", a)


def transitive_dependency_rule(kg: KnowledgeGraph) -> Iterator[Triple]:
    """
    If A depends_on B, and B depends_on C, then A needs C too.

    e.g. LLR-018 depends_on LLR-017, LLR-017 depends_on LLR-013
         => LLR-018 requires LLR-013

    Authored dependencies are single hops, because that is how an engineer
    thinks about them. This is the question that actually matters when
    scheduling or deleting something: everything this requirement
    ultimately rests on, however far down the chain.
    """
    subjects = {s for s, _, _ in kg.query(predicate="depends_on")}
    for subject in sorted(subjects):
        found: set[str] = set()
        stack = [subject]
        seen = {subject}
        while stack:
            node = stack.pop()
            for _, _, prereq in kg.query(subject=node, predicate="depends_on"):
                if prereq not in seen:
                    seen.add(prereq)
                    found.add(prereq)
                    stack.append(prereq)
        for prereq in sorted(found):
            yield (subject, "requires", prereq)


ALL_RULES = [
    transitive_trace_rule,
    impact_rule,
    implements_rule,
    conflict_is_symmetric_rule,
    transitive_dependency_rule,
]
