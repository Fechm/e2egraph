"""Merge per-repo graphs and resolve cross-repo edges into shared resources + E2E flows."""

def _shared_resource(merged_nodes, node_id, label, ntype):
    if not any(n["id"] == node_id for n in merged_nodes):
        merged_nodes.append({"id": node_id, "label": label, "type": ntype,
                             "repo": None, "layer": "shared", "path": None,
                             "lang": None, "source_location": None})

def merge_graphs(graphs):
    nodes = []
    edges = []
    for g in graphs:
        nodes.extend(g["nodes"])
        edges.extend(g["edges"])
    flows = []
    # Resolve shared tables: any reads_table/writes_table target becomes a db_table node
    table_targets = {}
    for e in edges:
        if e["type"] in ("reads_table", "writes_table") and e.get("unresolved"):
            tid = f"table:{e['target']}"
            _shared_resource(nodes, tid, e["target"], "db_table")
            e["target"] = tid
            e["unresolved"] = False
            table_targets.setdefault(tid, set()).add(e["source"].split(":")[0])
    for tid, repos in table_targets.items():
        if len(repos) > 1:
            label = next(n["label"] for n in nodes if n["id"] == tid)
            flows.append({"name": f"Shared table: {label}",
                          "path": sorted(repos),
                          "description": f"{', '.join(sorted(repos))} share table {label}."})
    # Resolve shared proto services
    proto_targets = {}
    for e in edges:
        if e["type"] == "shares_proto" and e.get("unresolved"):
            pid = f"proto:{e['target']}"
            _shared_resource(nodes, pid, e["target"], "service")
            e["target"] = pid
            e["unresolved"] = False
            proto_targets.setdefault(pid, set()).add(e["source"].split(":")[0])
    for pid, repos in proto_targets.items():
        if len(repos) > 1:
            label = next(n["label"] for n in nodes if n["id"] == pid)
            flows.append({"name": f"Shared proto: {label}",
                          "path": sorted(repos),
                          "description": f"{', '.join(sorted(repos))} share proto service {label}."})
    return {"nodes": nodes, "edges": edges, "flows": flows}
