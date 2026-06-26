"""Selective semantic layer glue for e2egraph.

The dispatch of Claude Code subagents is done by the orchestrator (SKILL.md Step 4),
NEVER by this module — there is no provider API key anywhere in e2egraph. This module
only (1) identifies GraphQL participants worth analyzing and (2) deterministically
merges the subagents' JSON results back into the graph. Both are pure and testable.
"""


def gql_participants(graph):
    """Return (consumers, providers) sorted repo-name lists for GraphQL.

    consumers: repos with an env_var whose label contains 'GRAPHQL', or a calls_api
               whose target mentions 'graphql'.
    providers: repos with a 'defines_gql_op' edge (GraphQL resolvers).
    """
    consumers, providers = set(), set()
    for n in graph.get("nodes", []):
        if n.get("type") == "env_var" and "GRAPHQL" in (n.get("label") or "").upper():
            consumers.add(n.get("repo"))
    for e in graph.get("edges", []):
        if e.get("type") == "calls_api" and "graphql" in str(e.get("target", "")).lower():
            consumers.add(e["source"].split(":")[0])
        if e.get("type") == "defines_gql_op":
            providers.add(e["source"].split(":")[0])
    consumers.discard(None)
    providers.discard(None)
    return sorted(consumers), sorted(providers)


def merge_semantic(graph, results):
    """Merge a semantic-results dict into graph (mutates and returns it).

    results = {
      "flow_descriptions": {flow_name: text},          # optional
      "gql_links": [{consumer, provider, operation, kind, description, evidence}],  # optional
      "community_names": {id: name},                   # optional, applied to community labels if present
    }
    Adds calls_gql_op edges (confidence AMBIGUOUS) between repo nodes + a GraphQL flow
    per link; applies flow descriptions. Never invents a hard edge — gql links are AMBIGUOUS.
    """
    results = results or {}
    descs = results.get("flow_descriptions", {}) or {}
    for f in graph.get("flows", []):
        if f.get("name") in descs:
            f["description"] = descs[f["name"]]
    repo_ids = {n["id"] for n in graph.get("nodes", []) if n.get("type") == "repo"}
    seen = set()
    for link in results.get("gql_links", []) or []:
        c, p, op = link.get("consumer"), link.get("provider"), link.get("operation")
        if not (c and p and op) or c == p:
            continue
        key = (c, p, op)
        if key in seen:
            continue
        seen.add(key)
        if c in repo_ids and p in repo_ids:
            graph["edges"].append({"source": c, "target": p, "type": "calls_gql_op",
                                   "confidence": "AMBIGUOUS",
                                   "evidence": link.get("evidence", f"gql {op}")})
        kind = link.get("kind", "operation")
        graph["flows"].append({
            "name": f"GraphQL: {c} → {p}.{op}",
            "path": [c, p],
            "description": link.get("description", f"{c} calls {p} {kind} {op}.")})
    return graph
