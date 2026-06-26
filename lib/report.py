"""Generate GRAPH_REPORT.md from a merged graph dict. Stdlib only."""

def generate_report(graph):
    repos = [n for n in graph["nodes"] if n.get("type") == "repo"]
    counts = {}
    for n in graph["nodes"]:
        counts[n.get("type", "?")] = counts.get(n.get("type", "?"), 0) + 1
    lines = ["# e2egraph — Graph Report", "",
             f"Repos: {len(repos)} · Nodes: {len(graph['nodes'])} · Edges: {len(graph['edges'])}",
             "", "## Repositories", ""]
    for r in sorted(repos, key=lambda x: x["label"]):
        lines.append(f"- **{r['label']}**")
    lines += ["", "## Node types", ""]
    for t, c in sorted(counts.items()):
        lines.append(f"- {t}: {c}")
    lines += ["", "## E2E Flows", ""]
    if graph.get("flows"):
        for f in graph["flows"]:
            lines.append(f"- **{f['name']}** — {f['description']}")
    else:
        lines.append("_No cross-repo flows detected._")
    return "\n".join(lines) + "\n"
