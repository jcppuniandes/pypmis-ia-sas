"""Deterministic, non-CPM execution policy and graph checks."""

from collections import deque

PACKAGE_TYPES = ["EWP", "PWP", "CWP", "IWP", "TWP", "SUPPORT", "LOGISTICS", "TEMPORARY_WORKS"]
CONSTRAINT_TYPES = [
    "ENGINEERING",
    "PROCUREMENT",
    "MATERIAL",
    "LOGISTICS",
    "ACCESS",
    "WORKFRONT",
    "PREDECESSOR",
    "PERMIT",
    "QUALITY",
    "HSE",
    "RESOURCE",
    "EQUIPMENT",
    "TEMPORARY_WORKS",
    "INTERFACE",
    "CLIENT_DECISION",
    "CONTRACTUAL",
    "OTHER",
]
DIMENSIONS = ["ENGINEERING", "MATERIAL", "LOGISTICS", "ACCESS", "PERMIT", "QUALITY", "HSE", "RESOURCE", "PREDECESSOR"]
DIMENSION_TYPES = {
    "ENGINEERING": ["ENGINEERING"],
    "MATERIAL": ["PROCUREMENT", "MATERIAL"],
    "LOGISTICS": ["LOGISTICS", "TEMPORARY_WORKS"],
    "ACCESS": ["ACCESS", "WORKFRONT"],
    "PERMIT": ["PERMIT"],
    "QUALITY": ["QUALITY"],
    "HSE": ["HSE"],
    "RESOURCE": ["RESOURCE", "EQUIPMENT"],
    "PREDECESSOR": ["PREDECESSOR", "INTERFACE", "CLIENT_DECISION", "CONTRACTUAL", "OTHER"],
}
LIFECYCLE = {
    "DRAFT": ["PLANNED", "SUPERSEDED"],
    "PLANNED": ["DRAFT", "UNDER_REVIEW", "SUPERSEDED"],
    "UNDER_REVIEW": ["PLANNED", "READY", "SUPERSEDED"],
    "READY": ["PLANNED", "RELEASED", "SUPERSEDED"],
    "RELEASED": ["IN_PROGRESS", "SUPERSEDED"],
    "IN_PROGRESS": ["COMPLETED", "SUPERSEDED"],
    "COMPLETED": ["CLOSED"],
    "CLOSED": [],
    "SUPERSEDED": [],
}
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "cwa_rules": {"allow_nested": True, "reject_cycles": True},
    "package_types": PACKAGE_TYPES,
    "dependency_types": ["DELIVERABLE", "MATERIAL", "WORKFRONT", "INTERFACE", "SUPPORT"],
    "reject_dependency_cycles": True,
    "package_lifecycle": LIFECYCLE,
    "constraint_types": {kind: {"enabled": True, "blocking": "USER_SELECTABLE"} for kind in CONSTRAINT_TYPES},
    "readiness_requirements": {
        kind: {"required_dimensions": requirements, "require_scope_or_plan": True, "require_activity": False}
        for kind, requirements in {
            "EWP": ["ENGINEERING"],
            "PWP": ["MATERIAL"],
            "CWP": ["ENGINEERING", "MATERIAL", "ACCESS"],
            "IWP": ["ENGINEERING", "MATERIAL", "ACCESS", "HSE"],
            "TWP": ["QUALITY"],
            "SUPPORT": ["RESOURCE"],
            "LOGISTICS": ["LOGISTICS"],
            "TEMPORARY_WORKS": ["LOGISTICS", "ACCESS"],
        }.items()
    },
    "release_workflow": "EXPLICIT_INDEPENDENT_AFTER_READY",
    "separation_of_duties": {
        "author_cannot_publish": True,
        "owner_cannot_clear": True,
        "preparer_cannot_release": True,
        "assessor_cannot_release": True,
    },
}


def has_cycle(edges):
    graph, degree = {}, {}
    for before, after in edges:
        graph.setdefault(before, set()).add(after)
        degree.setdefault(before, 0)
        degree.setdefault(after, 0)
    for children in graph.values():
        for child in children:
            degree[child] += 1
    queue = deque(node for node, count in degree.items() if not count)
    visited = 0
    while queue:
        visited += 1
        for child in graph.get(queue.popleft(), set()):
            degree[child] -= 1
            if not degree[child]:
                queue.append(child)
    return visited != len(degree)


def assess_policy(package_type, policy, constraints, dependencies, evidence, has_scope, has_activity):
    """Inputs are canonical facts, no dates or CPM calculations participate."""
    requirements = policy["readiness_requirements"][package_type]
    open_constraints = [row for row in constraints if row["status"] in {"OPEN", "IN_PROGRESS"}]
    blockers = [row["id"] for row in open_constraints if row["blocking"]]
    nonblocking = [row["id"] for row in open_constraints if not row["blocking"]]
    dependency_blockers = [
        row["id"]
        for row in dependencies
        if row["blocking"] and row["status"] == "ACTIVE" and row["predecessor_status"] not in {"COMPLETED", "CLOSED"}
    ]
    dimensions = {}
    missing = []
    for dimension in DIMENSIONS:
        required = dimension in requirements["required_dimensions"]
        affected = [
            row["id"]
            for row in open_constraints
            if row["constraint_type"] in DIMENSION_TYPES[dimension] and row["blocking"]
        ]
        if dimension == "PREDECESSOR":
            affected += dependency_blockers
        reference = evidence.get(dimension, "").strip()
        state = "BLOCKED" if affected else "READY" if reference else "MISSING_EVIDENCE" if required else "NOT_REQUIRED"
        dimensions[dimension] = {
            "state": state,
            "required": required,
            "evidence_reference": reference,
            "blocking_ids": affected,
        }
        if required and state != "READY":
            missing.append(dimension)
    mapping_missing = []
    if requirements["require_scope_or_plan"] and not has_scope:
        mapping_missing.append("SCOPE_OR_PLAN")
    if requirements["require_activity"] and not has_activity:
        mapping_missing.append("ACTIVITY")
    state = (
        "NOT_READY" if blockers or dependency_blockers or mapping_missing else "PARTIALLY_READY" if missing else "READY"
    )
    return {
        "readiness_state": state,
        "blocking_constraints": blockers,
        "open_nonblocking_constraints": nonblocking,
        "dependency_state": {"blocking_ids": dependency_blockers, "items": dependencies},
        "evidence_state": {"missing_dimensions": missing, "missing_mappings": mapping_missing, "references": evidence},
        "dimensions": dimensions,
    }
