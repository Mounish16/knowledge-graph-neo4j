"""
test_knowledge_graph.py
------------------------
Plain unittest tests (standard library only -- no pytest required).

Two kinds of test here:

  * the engine tests (graph ops, path finding, inference, persistence),
    which check KnowledgeGraph itself still behaves;
  * TestSampleDataIntegrity, which checks the traceability DATA is sound --
    no link pointing at an artefact that doesn't exist, no accidental
    orphan, every artefact tracing back to a customer request. A typo in a
    requirement ID is otherwise invisible until someone notices a missing
    line in a demo, so it's worth failing the build over.

Run with:
    python -m unittest discover -v
"""

import os
import tempfile
import unittest

from knowledge_graph import KnowledgeGraph
from rules import (conflict_is_symmetric_rule, impact_rule, implements_rule,
                   transitive_dependency_rule, transitive_trace_rule)
from sample_data import (ARTEFACTS, CONFLICTS_WITH, DEPENDS_ON, DERIVES_FROM,
                         VERIFIES, build_sample_graph)


class TestBasicGraphOps(unittest.TestCase):
    def setUp(self):
        self.kg = KnowledgeGraph()
        self.kg.add_fact("LLR-001", "derives_from", "HLR-001")
        self.kg.add_fact("HLR-001", "derives_from", "SYS-004")

    def test_add_and_query(self):
        self.assertEqual(len(self.kg), 2)
        self.assertIn("LLR-001", self.kg.entities())
        self.assertIn("HLR-001", self.kg.entities())
        self.assertIn("SYS-004", self.kg.entities())

        results = self.kg.query(subject="LLR-001")
        self.assertEqual(results, [("LLR-001", "derives_from", "HLR-001")])

    def test_duplicate_fact_is_idempotent(self):
        self.kg.add_fact("LLR-001", "derives_from", "HLR-001")
        self.assertEqual(len(self.kg), 2)

    def test_remove_fact(self):
        self.kg.remove_fact("LLR-001", "derives_from", "HLR-001")
        self.assertEqual(self.kg.query(subject="LLR-001"), [])
        self.assertEqual(len(self.kg), 1)

    def test_neighbors(self):
        neighbors = self.kg.neighbors("HLR-001")
        self.assertIn(("derives_from", "SYS-004"), neighbors["outgoing"])
        self.assertIn(("derives_from", "LLR-001"), neighbors["incoming"])

    def test_wildcard_query_matches_everything(self):
        self.assertEqual(len(self.kg.query()), 2)


class TestPathFinding(unittest.TestCase):
    def test_find_path_multi_hop(self):
        kg = build_sample_graph()
        # a module design and the customer request it ultimately serves,
        # several layers apart. NOTE: find_path defaults to max_depth=6,
        # which is one hop too shallow for a full chain here -- see
        # test_full_chain_needs_more_than_the_default_depth below.
        path = kg.find_path("MOD-001", "CR-001", max_depth=10)
        self.assertIsNotNone(path)
        self.assertEqual(path[0].from_node, "MOD-001")
        self.assertEqual(path[-1].to_node, "CR-001")
        # each step's "to_node" must feed into the next step's "from_node"
        for a, b in zip(path, path[1:]):
            self.assertEqual(a.to_node, b.from_node)

    def test_full_chain_needs_more_than_the_default_depth(self):
        """A full traceability chain is module -> LLD -> HLD -> LLR -> HLR
        -> SYS -> SN -> CR, which is 7 hops. find_path's default
        max_depth=6 silently returns None for it, so any caller walking a
        whole chain has to raise the limit explicitly. Documented as a
        test so it can't quietly regress."""
        kg = build_sample_graph()
        self.assertIsNone(kg.find_path("MOD-001", "CR-001"))
        self.assertIsNotNone(kg.find_path("MOD-001", "CR-001", max_depth=7))

    def test_find_path_same_node(self):
        kg = build_sample_graph()
        self.assertEqual(kg.find_path("HLR-001", "HLR-001"), [])

    def test_find_path_unreachable(self):
        kg = KnowledgeGraph()
        kg.add_fact("LLR-001", "derives_from", "HLR-001")
        kg.add_entity("LLR-500")  # isolated artefact, no links
        self.assertIsNone(kg.find_path("LLR-001", "LLR-500"))


class TestInference(unittest.TestCase):
    def test_transitive_trace_rule(self):
        kg = build_sample_graph()
        new_facts = kg.infer(transitive_trace_rule)
        # LLR-007 -> HLR-003 -> SYS-002 -> SN-002 -> CR-002
        self.assertIn(("LLR-007", "traces_to", "CR-002"), new_facts)
        self.assertIn(("LLR-007", "traces_to", "SYS-002"), new_facts)

    def test_transitive_trace_reaches_full_closure_in_one_pass(self):
        """The rule must walk the whole chain, not one hop -- infer() only
        applies each rule once."""
        kg = build_sample_graph()
        kg.infer(transitive_trace_rule)
        ancestors = {o for _, _, o in kg.query(subject="MOD-001", predicate="traces_to")}
        # spans every layer between module design and the customer request
        for expected in ("LLD-001", "HLD-001", "LLR-001", "HLR-001", "SYS-004",
                         "SN-001", "CR-001"):
            self.assertIn(expected, ancestors)

    def test_impact_rule_is_the_inverse_edge(self):
        kg = build_sample_graph()
        kg.infer(impact_rule)
        self.assertIn(("HLR-001", "impacts", "LLR-001"),
                      kg.query(subject="HLR-001", predicate="impacts"))

    def test_implements_rule(self):
        kg = build_sample_graph()
        new_facts = kg.infer(implements_rule)
        self.assertIn(("MOD-001", "implements", "HLR-001"), new_facts)
        # only module designs implement things
        for subject, _, _ in new_facts:
            self.assertTrue(subject.startswith("MOD-"))

    def test_inference_is_idempotent(self):
        kg = build_sample_graph()
        first = kg.infer(transitive_trace_rule)
        second = kg.infer(transitive_trace_rule)
        self.assertTrue(len(first) > 0)
        self.assertEqual(second, [])  # nothing new the second time around


class TestPersistence(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        kg = build_sample_graph()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "graph.json")
            kg.save_json(path)
            reloaded = KnowledgeGraph.load_json(path)
            self.assertEqual(kg.triples, reloaded.triples)
            self.assertEqual(kg.entity_attrs, reloaded.entity_attrs)


class TestSampleDataIntegrity(unittest.TestCase):
    """Checks on the dataset itself, not the engine."""

    def setUp(self):
        self.ids = {a[0] for a in ARTEFACTS}
        self.kg = build_sample_graph()

    def test_no_duplicate_artefact_ids(self):
        self.assertEqual(len(self.ids), len(ARTEFACTS))

    def test_every_link_points_at_a_real_artefact(self):
        """Catches a typo'd requirement ID, which would otherwise just
        appear as a silently missing line in the graph."""
        for child, parent in DERIVES_FROM:
            self.assertIn(child, self.ids, f"unknown child {child}")
            self.assertIn(parent, self.ids, f"unknown parent {parent}")
        for ver, item in VERIFIES:
            self.assertIn(ver, self.ids, f"unknown verification {ver}")
            self.assertIn(item, self.ids, f"unknown verified item {item}")

    def test_nothing_derives_from_itself(self):
        for child, parent in DERIVES_FROM:
            self.assertNotEqual(child, parent)

    def test_exactly_one_planted_orphan(self):
        """LLR-099 is deliberately unlinked, to exercise an orphan
        counter. Any OTHER orphan is an authoring mistake."""
        has_parent = {child for child, _ in DERIVES_FROM}
        orphans = {
            a[0] for a in ARTEFACTS
            if a[0] not in has_parent
            and a[1] not in ("customer_request", "verification")
        }
        self.assertEqual(orphans, {"LLR-099"})

    def test_every_linked_artefact_traces_back_to_a_customer_request(self):
        kg = build_sample_graph()
        kg.infer(transitive_trace_rule)
        for artefact_id, layer, _, _ in ARTEFACTS:
            if layer in ("customer_request", "verification") or artefact_id == "LLR-099":
                continue
            ancestors = {o for _, _, o in kg.query(subject=artefact_id,
                                                   predicate="traces_to")}
            self.assertTrue(
                any(a.startswith("CR-") for a in ancestors),
                f"{artefact_id} does not trace back to any customer request",
            )

    def test_multi_parent_artefacts_exist(self):
        """The many-to-many case is the reason for using a graph at all --
        if the data ever lost it, the demo would lose its point."""
        from collections import defaultdict
        parents = defaultdict(list)
        for child, parent in DERIVES_FROM:
            parents[child].append(parent)
        multi = {k for k, v in parents.items() if len(v) > 1}
        self.assertIn("HLR-005", multi)
        self.assertGreaterEqual(len(multi), 2)

    def test_every_artefact_has_text_and_status(self):
        for artefact_id in self.ids:
            attrs = self.kg.entity_attrs[artefact_id]
            self.assertTrue(attrs.get("text"), f"{artefact_id} has no text")
            self.assertTrue(attrs.get("status"), f"{artefact_id} has no status")

    def test_horizontal_links_point_at_real_artefacts(self):
        for a, b in DEPENDS_ON + CONFLICTS_WITH:
            self.assertIn(a, self.ids, f"unknown artefact {a}")
            self.assertIn(b, self.ids, f"unknown artefact {b}")

    def test_horizontal_links_stay_within_one_layer(self):
        """depends_on and conflicts_with are peer relationships. A link
        crossing layers would belong in DERIVES_FROM instead, and would
        quietly corrupt the single-layer views."""
        layer = {a[0]: a[1] for a in ARTEFACTS}
        for a, b in DEPENDS_ON + CONFLICTS_WITH:
            self.assertEqual(
                layer[a], layer[b],
                f"{a} ({layer[a]}) and {b} ({layer[b]}) are on different layers",
            )

    def test_nothing_depends_on_or_conflicts_with_itself(self):
        for a, b in DEPENDS_ON + CONFLICTS_WITH:
            self.assertNotEqual(a, b)

    def test_no_circular_dependencies(self):
        """A depends_on cycle would mean a set of requirements that can
        never be scheduled, and would make transitive_dependency_rule's
        traversal meaningless."""
        kg = build_sample_graph()
        for artefact_id in sorted(self.ids):
            reachable, stack = set(), [artefact_id]
            while stack:
                node = stack.pop()
                for _, _, prereq in kg.query(subject=node, predicate="depends_on"):
                    if prereq == artefact_id:
                        self.fail(f"circular dependency involving {artefact_id}")
                    if prereq not in reachable:
                        reachable.add(prereq)
                        stack.append(prereq)

    def test_single_layer_views_are_connected(self):
        """The whole point of the horizontal links: filtering to one layer
        should give a connected picture, not loose dots. Every HLR, and
        every LLR except the planted orphan, must have at least one peer
        link at its own level."""
        kg = build_sample_graph()
        peers = {a for a, _ in DEPENDS_ON + CONFLICTS_WITH}
        peers |= {b for _, b in DEPENDS_ON + CONFLICTS_WITH}

        for artefact_id, layer, _, _ in ARTEFACTS:
            if layer not in ("hlr", "llr"):
                continue
            if artefact_id == "LLR-099":  # deliberately isolated
                continue
            self.assertIn(
                artefact_id, peers,
                f"{artefact_id} has no peer link -- it would render as a "
                f"disconnected dot in the {layer.upper()}-only view",
            )


class TestHorizontalInference(unittest.TestCase):
    def test_conflict_is_symmetric(self):
        kg = build_sample_graph()
        kg.infer(conflict_is_symmetric_rule)
        # authored one way...
        self.assertIn(("HLR-007", "conflicts_with", "HLR-018"), kg.triples)
        # ...findable from the other end too
        self.assertIn(("HLR-018", "conflicts_with", "HLR-007"), kg.triples)

    def test_transitive_dependency_walks_the_whole_chain(self):
        kg = build_sample_graph()
        kg.infer(transitive_dependency_rule)
        # LLR-018 -> LLR-017 -> LLR-013 -> LLR-011
        required = {o for _, _, o in kg.query(subject="LLR-018",
                                              predicate="requires")}
        self.assertIn("LLR-017", required)   # direct
        self.assertIn("LLR-013", required)   # two hops
        self.assertIn("LLR-011", required)   # three hops

    def test_horizontal_inference_is_idempotent(self):
        kg = build_sample_graph()
        for rule in (conflict_is_symmetric_rule, transitive_dependency_rule):
            first = kg.infer(rule)
            second = kg.infer(rule)
            self.assertTrue(len(first) > 0)
            self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
