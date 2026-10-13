"""
knowledge_graph.py
------------------
A tiny, dependency-free "knowledge graph" (a.k.a. triple store / knowledge base).

Core idea: knowledge is stored as FACTS shaped like

    (subject, predicate, object)

e.g.  ("Alice", "works_at", "Acme Corp")
      ("Acme Corp", "located_in", "London")

This one file is pure standard-library Python -- no pip installs required.
It supports:

  * adding/removing entities and facts
  * wildcard queries over (subject, predicate, object)
  * neighbor lookups (outgoing + incoming edges)
  * shortest-path search between two entities (BFS over the graph)
  * a very small forward-chaining rule engine (simple transitive inference)
  * saving/loading the whole graph to/from JSON
  * a plain-text pretty printer
  * exporting a self-contained HTML visualization (no CDN, no JS deps)

Everything here is intentionally simple and readable rather than optimized --
this is meant as a clear, working reference implementation you can extend.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, NamedTuple


Triple = tuple[str, str, str]


class PathStep(NamedTuple):
    """One hop in a find_path() result, already oriented start -> end."""
    from_node: str
    predicate: str
    to_node: str
    direction: str  # "forward" or "reverse"

    def __repr__(self) -> str:
        arrow = f"--{self.predicate}-->" if self.direction == "forward" else f"<--{self.predicate}--"
        return f"{self.from_node} {arrow} {self.to_node}"


@dataclass
class KnowledgeGraph:
    """An in-memory knowledge graph built from (subject, predicate, object) facts."""

    # the raw set of facts -- the single source of truth
    triples: set[Triple] = field(default_factory=set)

    # optional free-form attributes per entity, e.g. {"Alice": {"age": 30}}
    entity_attrs: dict[str, dict] = field(default_factory=dict)

    # ---- derived indexes, kept in sync automatically -------------------
    # subject -> list of (predicate, object)
    _forward: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))
    # object -> list of (predicate, subject)
    _backward: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))

    # ------------------------------------------------------------------
    # basic mutation
    # ------------------------------------------------------------------
    def add_entity(self, name: str, **attrs) -> None:
        """Register an entity (optional) and/or set attributes on it."""
        self.entity_attrs.setdefault(name, {})
        if attrs:
            self.entity_attrs[name].update(attrs)

    def add_fact(self, subject: str, predicate: str, obj: str) -> None:
        """Add a single (subject, predicate, object) fact to the graph."""
        triple = (subject, predicate, obj)
        if triple in self.triples:
            return  # already known, nothing to do
        self.triples.add(triple)
        self._forward[subject].append((predicate, obj))
        self._backward[obj].append((predicate, subject))
        self.add_entity(subject)
        self.add_entity(obj)

    def add_facts(self, facts: Iterable[Triple]) -> None:
        for s, p, o in facts:
            self.add_fact(s, p, o)

    def remove_fact(self, subject: str, predicate: str, obj: str) -> None:
        triple = (subject, predicate, obj)
        if triple not in self.triples:
            return
        self.triples.discard(triple)
        self._forward[subject].remove((predicate, obj))
        self._backward[obj].remove((predicate, subject))

    # ------------------------------------------------------------------
    # querying
    # ------------------------------------------------------------------
    def query(self, subject: str | None = None, predicate: str | None = None,
              obj: str | None = None) -> list[Triple]:
        """
        Wildcard search over facts. Pass None for "anything".

        Examples:
            kg.query(subject="Alice")                     # everything about Alice
            kg.query(predicate="works_at")                 # every works_at fact
            kg.query(subject="Alice", predicate="friend_of")
        """
        results = []
        for s, p, o in self.triples:
            if subject is not None and s != subject:
                continue
            if predicate is not None and p != predicate:
                continue
            if obj is not None and o != obj:
                continue
            results.append((s, p, o))
        return sorted(results)

    def entities(self) -> list[str]:
        return sorted(self.entity_attrs.keys())

    def neighbors(self, entity: str) -> dict[str, list[tuple[str, str]]]:
        """Return outgoing and incoming edges for an entity."""
        return {
            "outgoing": sorted(self._forward.get(entity, [])),
            "incoming": sorted(self._backward.get(entity, [])),
        }

    def find_path(self, start: str, end: str, max_depth: int = 6) -> list["PathStep"] | None:
        """
        Breadth-first search for the shortest chain of facts connecting
        `start` to `end`, following edges in either direction.

        Returns a list of PathStep(from_node, predicate, to_node, direction)
        in TRAVERSAL ORDER (i.e. step[0].from_node == start and
        step[-1].to_node == end), or None if unreachable.

        `direction` is "forward" when the step follows a fact as stored
        (from_node, predicate, to_node), and "reverse" when it follows a
        fact backwards (the stored fact is actually to_node, predicate,
        from_node).
        """
        if start == end:
            return []

        # each queue entry: (current_node, path_so_far)
        visited = {start}
        queue: deque[tuple[str, list[PathStep]]] = deque([(start, [])])

        while queue:
            node, path = queue.popleft()
            if len(path) >= max_depth:
                continue

            # try outgoing edges: node --predicate--> other
            for predicate, other in self._forward.get(node, []):
                if other in visited:
                    continue
                new_path = path + [PathStep(node, predicate, other, "forward")]
                if other == end:
                    return new_path
                visited.add(other)
                queue.append((other, new_path))

            # try incoming edges: other --predicate--> node (walked backwards,
            # so from the traversal's point of view we go node -> other)
            for predicate, other in self._backward.get(node, []):
                if other in visited:
                    continue
                new_path = path + [PathStep(node, predicate, other, "reverse")]
                if other == end:
                    return new_path
                visited.add(other)
                queue.append((other, new_path))

        return None

    # ------------------------------------------------------------------
    # tiny forward-chaining inference engine
    # ------------------------------------------------------------------
    def infer(self, rule: Callable[["KnowledgeGraph"], Iterator[Triple]]) -> list[Triple]:
        """
        Apply a single inference rule once and add any newly derived facts.
        A rule is a function that looks at the current graph and yields new
        (subject, predicate, object) triples. Returns the list of facts that
        were actually new (and got added).

        See rules.py for ready-made example rules (e.g. transitive location).
        """
        new_facts = []
        for s, p, o in rule(self):
            if (s, p, o) not in self.triples:
                self.add_fact(s, p, o)
                new_facts.append((s, p, o))
        return new_facts

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "triples": sorted(list(self.triples)),
            "entity_attrs": self.entity_attrs,
        }

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def load_json(cls, path: str) -> "KnowledgeGraph":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        kg = cls()
        for name, attrs in data.get("entity_attrs", {}).items():
            kg.add_entity(name, **attrs)
        for s, p, o in data.get("triples", []):
            kg.add_fact(s, p, o)
        return kg

    # ------------------------------------------------------------------
    # human-friendly output
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.triples)

    def __repr__(self) -> str:
        return f"KnowledgeGraph(entities={len(self.entities())}, facts={len(self.triples)})"

    def pretty_print(self) -> str:
        """Return a readable, grouped text view of the whole graph."""
        lines = [f"Knowledge graph: {len(self.entities())} entities, {len(self.triples)} facts", "=" * 60]
        for entity in self.entities():
            out = sorted(self._forward.get(entity, []))
            if not out:
                continue
            lines.append(f"\n{entity}")
            for predicate, obj in out:
                lines.append(f"    --{predicate}--> {obj}")
        return "\n".join(lines)
