// layer_views.cypher
// ------------------
// Copy-paste these one at a time into the Neo4j Browser at
// http://localhost:7474 (neo4j / password123).
//
// These are the single-layer and mixed-layer views: the picture someone
// wants when they care about the requirements themselves rather than the
// process that produced them.
//
// The links come in two kinds:
//   VERTICAL   DERIVES_FROM, VERIFIES        -- between layers
//   HORIZONTAL DEPENDS_ON, CONFLICTS_WITH    -- between peers at one layer
//
// The horizontal ones are what make a single-layer view readable. Filter
// to just the HLRs using only the vertical chain and you get disconnected
// dots, because an HLR links up to a system requirement and down to an
// LLR, but never sideways to another HLR.


// ====================================================================
// 1. HLR LAYER ONLY  -- how the high-level requirements relate
// The view to show someone who only wants to see the requirements.
// ====================================================================
MATCH (a:HLR)-[r:DEPENDS_ON|CONFLICTS_WITH]-(b:HLR)
RETURN a, r, b;


// Same, but including any HLR that has no peer links at all, so nothing
// is silently missing from the picture:
MATCH (n:HLR)
OPTIONAL MATCH (n)-[r:DEPENDS_ON|CONFLICTS_WITH]-(m:HLR)
RETURN n, r, m;


// ====================================================================
// 2. LLR LAYER ONLY
// ====================================================================
MATCH (a:LLR)-[r:DEPENDS_ON|CONFLICTS_WITH]-(b:LLR)
RETURN a, r, b;


// ====================================================================
// 3. UNION OF HLR + LLR  -- mix and match
// Both layers at once: the vertical links showing which LLR realises
// which HLR, plus the horizontal links within each layer.
// ====================================================================
MATCH (a)-[r]-(b)
WHERE (a:HLR OR a:LLR) AND (b:HLR OR b:LLR)
RETURN a, r, b;


// ====================================================================
// 4. ONE HLR AND EVERYTHING IT TOUCHES
// Its peers, and the LLRs that realise it. Change the id to pivot.
// ====================================================================
MATCH (h:HLR {name: 'HLR-007'})
OPTIONAL MATCH (h)-[peer:DEPENDS_ON|CONFLICTS_WITH]-(other:HLR)
OPTIONAL MATCH (llr:LLR)-[real:DERIVES_FROM]->(h)
RETURN h, peer, other, real, llr;


// ====================================================================
// 5. CONFLICTS  -- requirements in tension, at any layer
// Stored one way and derived both ways, so starting from either
// requirement finds it.
// ====================================================================
MATCH (a)-[r:CONFLICTS_WITH]-(b)
WHERE a.name < b.name
RETURN a, r, b;


// As a table, with the wording, for a review meeting:
MATCH (a)-[:CONFLICTS_WITH]-(b)
WHERE a.name < b.name
RETURN a.name AS requirement_a, a.text AS text_a,
       b.name AS requirement_b, b.text AS text_b;


// ====================================================================
// 6. DEPENDENCY CHAIN  -- what a requirement ultimately rests on
// Variable-length path, so it walks the whole chain rather than one hop.
// ====================================================================
MATCH path = (start:LLR {name: 'LLR-018'})-[:DEPENDS_ON*1..]->(prereq)
RETURN path;


// Flat list version:
MATCH (start:LLR {name: 'LLR-018'})-[:DEPENDS_ON*1..]->(prereq)
RETURN DISTINCT prereq.name AS must_be_met_first, prereq.text AS text;


// ====================================================================
// 7. WHAT BLOCKS THE MOST  -- prerequisites ranked by how much rests
// on them. These are the requirements to schedule first, and the ones
// that hurt most if they slip.
// ====================================================================
MATCH (dependent)-[:DEPENDS_ON*1..]->(prereq)
RETURN prereq.name AS requirement,
       [l IN labels(prereq) WHERE l <> 'Entity'][0] AS layer,
       count(DISTINCT dependent) AS things_waiting_on_it,
       prereq.text AS text
ORDER BY things_waiting_on_it DESC
LIMIT 10;


// ====================================================================
// 8. ISOLATED REQUIREMENTS  -- no peer links at their own layer
// Not necessarily wrong, but worth a look: a requirement that relates to
// nothing else at its level is often either genuinely standalone or
// missing a link someone forgot to author.
// ====================================================================
MATCH (n)
WHERE (n:HLR OR n:LLR)
  AND NOT (n)-[:DEPENDS_ON|CONFLICTS_WITH]-()
RETURN [l IN labels(n) WHERE l <> 'Entity'][0] AS layer, n.name AS id, n.text AS text;


// ====================================================================
// 9. THE FULL PICTURE  -- everything, for reference
// ====================================================================
MATCH (n)-[r]->(m) RETURN n, r, m;
