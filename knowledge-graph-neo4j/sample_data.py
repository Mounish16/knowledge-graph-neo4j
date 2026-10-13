"""
sample_data.py
--------------
Builds the sample knowledge base: a requirements traceability chain for a
defence programme, from customer request down to module design and
verification evidence.

Shape of the chain:

    CR   Customer Request
     |
     v
    SN   Stakeholder Need
     |
     +--> SYS  System Requirement
     +--> SAF  Safety Requirement
           |
           v
          HLR  High-Level Requirement   <--[verifies]--  VER  Verification
           |
           v
          LLR  Low-Level Requirement
           |
           v
          HLD --> LLD --> MOD  Module Design

Links come in two kinds.

VERTICAL -- between layers, the traceability chain itself:
    derives_from     child points at the parent it was derived from
    verifies         verification evidence points at what it verifies

Keeping the vertical chain to a single predicate is deliberate.
"Upstream" and "downstream" then become the two directions of one
relationship, which is what makes lineage, impact and depth-N
neighbourhood queries one-liners rather than special cases.

HORIZONTAL -- between peers at the SAME layer:
    depends_on       this requirement needs another one to be met first
    conflicts_with   two requirements are in tension and need resolving

The horizontal links are what make a single-layer view useful. Filter the
graph to just the HLRs using only vertical links and you get a screen of
disconnected dots, because HLRs connect upwards to system requirements
and downwards to LLRs, but never to each other. `depends_on` and
`conflicts_with` are what turn that into a readable picture of how the
requirements at one level actually relate -- which is the view someone
wants when they care about the requirements themselves rather than the
process that produced them.

Entity naming follows the requirement ID (e.g. "HLR-001"), with the
requirement wording carried as a `text` attribute, so IDs stay short and
readable in the graph view while the full text is still queryable.
"""

from knowledge_graph import KnowledgeGraph

PROGRAMME = "AGM-X Talon Blk II"

# ---------------------------------------------------------------------
# (id, layer, text, status)
#
# Deliberately small enough to render legibly, but with the same shape as
# the real thing -- including three planted defects, so the graph can
# demonstrate a traceability console's counters rather than looking
# artificially clean:
#   * LLR-099 is an orphan (traces to nothing)
#   * five HLRs have no verification evidence
#   * five artefacts have more than one parent
# ---------------------------------------------------------------------
ARTEFACTS = [
    # --- Customer Requests -------------------------------------------
    ("CR-001", "customer_request", "Standoff engagement of relocatable targets", "approved"),
    ("CR-002", "customer_request", "No increase in aircrew workload", "approved"),
    ("CR-003", "customer_request", "Exportable configuration", "draft"),
    ("CR-004", "customer_request", "Twenty-year magazine life", "approved"),
    ("CR-005", "customer_request", "Airworthiness release within 30 months", "approved"),
    ("CR-006", "customer_request", "GPS-denied terminal accuracy", "approved"),

    # --- Stakeholder Needs -------------------------------------------
    ("SN-001", "stakeholder_need", "Pilot: launch and leave", "approved"),
    ("SN-002", "stakeholder_need", "Pilot: single-action target designation", "approved"),
    ("SN-003", "stakeholder_need", "Mission planner: offline route generation", "approved"),
    ("SN-004", "stakeholder_need", "Weapons officer: in-flight retarget", "approved"),
    ("SN-007", "stakeholder_need", "Safety board: no single-point arming failure", "approved"),
    ("SN-009", "stakeholder_need", "FMS customer: no source-code escrow", "draft"),

    # --- System Requirements -----------------------------------------
    ("SYS-001", "system_requirement", "Standoff launch range shall exceed the quoted figure", "approved"),
    ("SYS-002", "system_requirement", "Terminal miss distance within stated CEP", "approved"),
    ("SYS-004", "system_requirement", "Autonomous terminal guidance without operator input", "approved"),
    ("SYS-006", "system_requirement", "Store interface compliant with carriage standard", "approved"),
    ("SYS-007", "system_requirement", "In-flight retargeting via datalink", "draft"),

    # --- Safety Requirements -----------------------------------------
    ("SAF-001", "safety_requirement", "Inadvertent arming shall be prevented", "approved"),
    ("SAF-002", "safety_requirement", "Two independent arming interlocks required", "approved"),
    ("SAF-003", "safety_requirement", "Release consent shall be positively commanded", "approved"),
    ("SAF-004", "safety_requirement", "Safe separation from the launch aircraft", "approved"),

    # --- High-Level Requirements -------------------------------------
    ("HLR-001", "hlr", "The system shall provide an imaging seeker for terminal guidance", "approved"),
    ("HLR-002", "hlr", "The system shall stabilise the seeker gimbal during terminal phase", "approved"),
    ("HLR-003", "hlr", "The system shall perform scene matching against reference imagery", "approved"),
    ("HLR-005", "hlr", "The system shall compute a navigation solution without GNSS", "approved"),
    ("HLR-007", "hlr", "The system shall apply the guidance law during terminal phase", "approved"),
    ("HLR-009", "hlr", "The system shall authenticate datalink messages", "approved"),
    ("HLR-010", "hlr", "The system shall enforce a datalink cutoff prior to impact", "draft"),
    ("HLR-013", "hlr", "The system shall implement a two-position safe and arm device", "approved"),
    ("HLR-014", "hlr", "The system shall report safe and arm state to the aircraft", "approved"),
    ("HLR-018", "hlr", "The system shall withstand the specified airframe loads", "approved"),
    ("HLR-022", "hlr", "The system shall follow a fail-safe trajectory on fault", "approved"),

    # --- Low-Level Requirements --------------------------------------
    ("LLR-001", "llr", "Detector interface shall sample at the specified frame rate", "approved"),
    ("LLR-002", "llr", "Non-uniformity correction shall be applied per frame", "approved"),
    ("LLR-003", "llr", "Bad pixel substitution shall use neighbouring elements", "approved"),
    ("LLR-004", "llr", "Gimbal rate loop shall track commanded line-of-sight rate", "approved"),
    ("LLR-005", "llr", "Gimbal soft-stop shall engage before mechanical limits", "approved"),
    ("LLR-007", "llr", "Correlation window shall be sized from the reference chip", "approved"),
    ("LLR-008", "llr", "Correlation confidence below threshold shall be rejected", "approved"),
    ("LLR-011", "llr", "IMU samples shall be time-tagged to the master clock", "approved"),
    ("LLR-013", "llr", "Kalman filter shall propagate at the navigation rate", "approved"),
    ("LLR-017", "llr", "Guidance commands shall be limited to airframe capability", "approved"),
    ("LLR-018", "llr", "Proportional navigation gain shall be scheduled on range", "approved"),
    ("LLR-021", "llr", "Message authentication code shall be verified before action", "approved"),
    ("LLR-023", "llr", "Rejection of an unauthenticated message shall be logged", "approved"),
    ("LLR-024", "llr", "Both interlocks shall be independently monitored", "approved"),
    ("LLR-025", "llr", "Safe and arm state shall be sampled at the reporting rate", "approved"),
    ("LLR-031", "llr", "Airframe load factor shall be monitored in flight", "draft"),
    # planted defect: orphan, traces to nothing
    ("LLR-099", "llr", "Legacy telemetry format shall remain selectable", "draft"),

    # --- Design ------------------------------------------------------
    ("HLD-001", "hld", "Seeker Subsystem", "approved"),
    ("HLD-002", "hld", "Navigation Subsystem", "approved"),
    ("HLD-003", "hld", "Guidance Subsystem", "approved"),
    ("HLD-004", "hld", "Datalink Subsystem", "approved"),
    ("HLD-005", "hld", "Safe and Arm Subsystem", "approved"),

    ("LLD-001", "lld", "Focal Plane Interface Module", "approved"),
    ("LLD-002", "lld", "Gimbal Servo Controller", "approved"),
    ("LLD-003", "lld", "Scene Correlator", "approved"),
    ("LLD-004", "lld", "Inertial Navigation Filter", "approved"),
    ("LLD-005", "lld", "Guidance Law Processor", "approved"),
    ("LLD-006", "lld", "Message Authentication Unit", "approved"),
    ("LLD-007", "lld", "Interlock Monitor", "approved"),

    ("MOD-001", "module_design", "Seeker Electronics Assembly", "approved"),
    ("MOD-002", "module_design", "Navigation Computer Assembly", "approved"),
    ("MOD-003", "module_design", "Safety Logic Assembly", "approved"),

    # --- Verification ------------------------------------------------
    ("VER-001", "verification", "Seeker bench test", "passed"),
    ("VER-002", "verification", "Captive carry flight trial", "passed"),
    ("VER-003", "verification", "Arming interlock fault injection", "passed"),
    ("VER-004", "verification", "GPS-denied navigation trial", "planned"),
]

# (child, parent) -- child derives_from parent
DERIVES_FROM = [
    # CR -> SN
    ("SN-001", "CR-001"), ("SN-002", "CR-002"), ("SN-003", "CR-001"),
    ("SN-004", "CR-001"), ("SN-007", "CR-005"), ("SN-009", "CR-003"),

    # SN -> SYS / SAF
    ("SYS-001", "SN-001"), ("SYS-002", "SN-002"), ("SYS-004", "SN-001"),
    ("SYS-006", "SN-003"), ("SYS-007", "SN-004"),
    ("SAF-001", "SN-007"), ("SAF-002", "SN-007"),
    ("SAF-003", "SN-007"), ("SAF-004", "SN-007"),

    # SYS / SAF -> HLR
    ("HLR-001", "SYS-004"), ("HLR-002", "SYS-004"), ("HLR-003", "SYS-002"),
    ("HLR-005", "SYS-002"), ("HLR-007", "SYS-002"), ("HLR-009", "SYS-007"),
    ("HLR-010", "SYS-007"), ("HLR-013", "SAF-002"), ("HLR-014", "SAF-003"),
    ("HLR-018", "SYS-006"), ("HLR-022", "SAF-004"),
    # second parent: the GPS-denied customer request drives the navigation
    # requirement directly as well. This many-to-many case is precisely
    # what a tree cannot represent and a graph can.
    ("HLR-005", "CR-006"),

    # HLR -> LLR
    ("LLR-001", "HLR-001"), ("LLR-002", "HLR-001"), ("LLR-003", "HLR-001"),
    ("LLR-004", "HLR-002"), ("LLR-005", "HLR-002"),
    ("LLR-007", "HLR-003"), ("LLR-008", "HLR-003"),
    ("LLR-011", "HLR-005"), ("LLR-013", "HLR-005"),
    ("LLR-017", "HLR-007"), ("LLR-018", "HLR-007"),
    ("LLR-021", "HLR-009"), ("LLR-023", "HLR-009"),
    ("LLR-024", "HLR-013"), ("LLR-025", "HLR-014"),
    ("LLR-031", "HLR-018"),
    # LLR-099 deliberately has no parent

    # LLR -> HLD
    ("HLD-001", "LLR-001"), ("HLD-001", "LLR-004"),
    ("HLD-002", "LLR-011"), ("HLD-002", "LLR-013"),
    ("HLD-003", "LLR-017"), ("HLD-004", "LLR-021"),
    ("HLD-005", "LLR-024"),

    # HLD -> LLD
    ("LLD-001", "HLD-001"), ("LLD-002", "HLD-001"), ("LLD-003", "HLD-001"),
    ("LLD-004", "HLD-002"), ("LLD-005", "HLD-003"),
    ("LLD-006", "HLD-004"), ("LLD-007", "HLD-005"),

    # LLD -> Module Design
    ("MOD-001", "LLD-001"), ("MOD-001", "LLD-002"), ("MOD-001", "LLD-003"),
    ("MOD-002", "LLD-004"), ("MOD-002", "LLD-005"),
    ("MOD-003", "LLD-007"),
]

# (verification, artefact it verifies)
VERIFIES = [
    ("VER-001", "HLR-001"), ("VER-001", "HLR-002"),
    ("VER-002", "HLR-018"),
    ("VER-003", "HLR-013"), ("VER-003", "HLR-014"),
    ("VER-004", "HLR-005"),
    # HLR-003, 007, 009, 010 and 022 have no verification -- these are
    # what an "unverified" counter should surface
]

# ---------------------------------------------------------------------
# HORIZONTAL links -- peer relationships within a single layer.
#
# (dependent, prerequisite) -- the first needs the second to be met first.
# These are what make a single-layer view readable: without them, filtering
# to just the HLRs shows disconnected dots.
# ---------------------------------------------------------------------
DEPENDS_ON = [
    # --- within HLR ---------------------------------------------------
    # scene matching is useless without an image to match, and a stable one
    ("HLR-003", "HLR-001"),   # scene matching  <- imaging seeker
    ("HLR-003", "HLR-002"),   # scene matching  <- gimbal stabilisation
    # terminal guidance needs both a navigation solution and a fix
    ("HLR-007", "HLR-005"),   # guidance law    <- navigation solution
    ("HLR-007", "HLR-003"),   # guidance law    <- scene matching
    # you can only cut off a link you can trust in the first place
    ("HLR-010", "HLR-009"),   # datalink cutoff <- message authentication
    # reporting arm state presupposes the device that has a state
    ("HLR-014", "HLR-013"),   # report S&A      <- S&A device
    # a fail-safe trajectory needs to know where it is, and to disarm
    ("HLR-022", "HLR-005"),   # fail-safe traj  <- navigation solution
    ("HLR-022", "HLR-013"),   # fail-safe traj  <- S&A device

    # --- within LLR ---------------------------------------------------
    # the seeker image-processing pipeline, in order
    ("LLR-002", "LLR-001"),   # NUC             <- detector sampling
    ("LLR-003", "LLR-002"),   # bad pixel subst <- NUC
    ("LLR-007", "LLR-003"),   # correlation     <- clean image
    ("LLR-008", "LLR-007"),   # confidence gate <- correlation
    # the gimbal control pair
    ("LLR-005", "LLR-004"),   # soft-stop       <- rate loop
    ("LLR-007", "LLR-004"),   # correlation     <- stable line-of-sight
    # the navigation chain
    ("LLR-013", "LLR-011"),   # Kalman filter   <- time-tagged IMU
    ("LLR-017", "LLR-013"),   # command limits  <- navigation solution
    ("LLR-018", "LLR-017"),   # PN gain sched   <- command limits
    # you cannot limit to airframe capability without measuring it
    ("LLR-017", "LLR-031"),   # command limits  <- load factor monitoring
    # datalink and safety chains
    ("LLR-023", "LLR-021"),   # log rejection   <- verify MAC
    ("LLR-025", "LLR-024"),   # sample state    <- monitor interlocks
]

# (a, b) -- a and b are in tension and need an explicit resolution.
# Stored one-way; conflict_is_symmetric_rule derives the reverse, so the
# authored data stays minimal.
CONFLICTS_WITH = [
    # guidance wants authority the airframe cannot always take -- LLR-017
    # ("commands limited to airframe capability") is the resolution
    ("HLR-007", "HLR-018"),
    # scheduling gain on range can demand more than the limiter allows
    ("LLR-018", "LLR-017"),
]


def build_sample_graph() -> KnowledgeGraph:
    """Build the requirements traceability graph.

    Name and signature are unchanged from the original people/companies
    version, so everything downstream that imports this -- the Neo4j
    loader, the demo queries, the HTML export -- keeps working untouched.
    """
    kg = KnowledgeGraph()

    for artefact_id, layer, text, status in ARTEFACTS:
        kg.add_entity(artefact_id, type=layer, text=text,
                      status=status, programme=PROGRAMME)

    # vertical: the traceability chain between layers
    kg.add_facts((child, "derives_from", parent) for child, parent in DERIVES_FROM)
    kg.add_facts((ver, "verifies", item) for ver, item in VERIFIES)

    # horizontal: peer relationships within a layer
    kg.add_facts((a, "depends_on", b) for a, b in DEPENDS_ON)
    kg.add_facts((a, "conflicts_with", b) for a, b in CONFLICTS_WITH)

    return kg


if __name__ == "__main__":
    graph = build_sample_graph()
    print(graph.pretty_print())
