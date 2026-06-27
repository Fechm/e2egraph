"""Reduce a full e2egraph to a clean architecture overview.

Only repo/service/db_table/queue/bucket nodes are kept.
Only cross-cutting FLOW edge types are kept; endpoints of dropped nodes are
re-mapped to their owning repo. Self-loops and duplicate (src, tgt, type)
triples are removed.
"""

# Node types retained in the overview.
_OVERVIEW_NODE_TYPES = {"repo", "service", "db_table", "queue", "bucket"}

# Edge types retained in the overview (cross-service flow semantics).
# "contains", "uses_env", "imports" are explicitly dropped.
_FLOW_EDGE_TYPES = {
    "calls_service",
    "calls_endpoint",
    "calls_gql_op",
    "reads_table",
    "writes_table",
    "shares_proto",
    "depends_pkg",
}


def to_overview(graph):
    """Return a new graph dict collapsed to architecture overview.

    Args:
        graph: dict with "nodes", "edges", "flows".

    Returns:
        New dict {"nodes": [...], "edges": [...], "flows": [...]} where:
        - nodes: only those whose type is in _OVERVIEW_NODE_TYPES.
        - edges: only FLOW edge types; endpoints of dropped nodes are
          re-mapped to the owning repo. Self-loops and (src,tgt,type)
          duplicates are removed. Evidence is preserved when present.
        - flows: passed through unchanged.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    flows = list(graph.get("flows", []))

    # Build lookup: node_id -> node
    id_to_node = {n["id"]: n for n in nodes}

    # Set of kept node ids
    kept_ids = {n["id"] for n in nodes if n.get("type") in _OVERVIEW_NODE_TYPES}

    # Kept nodes list (preserving order, no mutation)
    kept_nodes = [n for n in nodes if n["id"] in kept_ids]

    def resolve(node_id):
        """Return kept node id for node_id, or None if unresolvable."""
        if node_id in kept_ids:
            return node_id
        node = id_to_node.get(node_id)
        if node is None:
            return None
        repo_id = node.get("repo")
        if repo_id and repo_id in kept_ids:
            return repo_id
        return None

    seen = set()
    kept_edges = []
    for e in edges:
        # Only keep FLOW edge types
        etype = e.get("type", "")
        if etype not in _FLOW_EDGE_TYPES:
            continue

        src = resolve(e.get("source", ""))
        tgt = resolve(e.get("target", ""))
        if src is None or tgt is None:
            continue
        if src == tgt:
            continue  # self-loop after remap — drop

        key = (src, tgt, etype)
        if key in seen:
            continue
        seen.add(key)

        new_edge = {"source": src, "target": tgt, "type": etype}
        if "evidence" in e:
            new_edge["evidence"] = e["evidence"]
        kept_edges.append(new_edge)

    return {"nodes": kept_nodes, "edges": kept_edges, "flows": flows}
