"""Assemble one repo's nodes/edges into a graph dict. Stdlib only."""
import os

def _rel(repo_path, file_path):
    return file_path[len(repo_path):].lstrip("/") if file_path.startswith(repo_path) else file_path

def build_repo_graph(repo, relations, symbols):
    name = repo["name"]
    nodes = {name: {"id": name, "label": name, "type": "repo", "repo": name,
                    "layer": "repo", "path": repo["path"], "lang": None,
                    "source_location": repo["path"]}}
    edges = []
    for f in repo["files"]:
        rel = _rel(repo["path"], f["path"])
        module = os.path.dirname(rel).split("/")[0] or "(root)"
        mod_id = f"{name}:mod:{module}"
        file_id = f"{name}:file:{rel}"
        if mod_id not in nodes:
            nodes[mod_id] = {"id": mod_id, "label": module, "type": "module",
                             "repo": name, "layer": "module", "path": module,
                             "lang": None, "source_location": f"{repo['path']}/{module}"}
            edges.append({"source": name, "target": mod_id, "type": "contains",
                          "confidence": "EXTRACTED", "evidence": "structure"})
        nodes[file_id] = {"id": file_id, "label": rel, "type": "file", "repo": name,
                          "layer": "file", "path": rel, "lang": f["lang"],
                          "source_location": f["path"]}
        edges.append({"source": mod_id, "target": file_id, "type": "contains",
                      "confidence": "EXTRACTED", "evidence": "structure"})
    for s in symbols:
        rel = _rel(repo["path"], s["file"])
        file_id = f"{name}:file:{rel}"
        sym_id = f"{name}:sym:{rel}:{s['name']}"
        nodes[sym_id] = {"id": sym_id, "label": s["name"], "type": "symbol",
                         "repo": name, "layer": "symbol", "path": rel, "lang": None,
                         "source_location": s["file"]}
        if file_id in nodes:
            edges.append({"source": file_id, "target": sym_id, "type": "contains",
                          "confidence": "EXTRACTED", "evidence": "ctags"})
    for r in relations:
        rel = _rel(repo["path"], r["source"])
        file_id = f"{name}:file:{rel}"
        if r["type"] == "uses_env":
            tgt = f"{name}:env:{r['target_name']}"
            nodes.setdefault(tgt, {"id": tgt, "label": r["target_name"], "type": "env_var",
                                   "repo": name, "layer": "external", "path": None,
                                   "lang": None, "source_location": None})
            edges.append({"source": file_id, "target": tgt, "type": "uses_env",
                          "confidence": r["confidence"], "evidence": r["evidence"]})
        else:
            edges.append({"source": file_id, "target": r["target_name"], "type": r["type"],
                          "confidence": r["confidence"], "evidence": r["evidence"],
                          "unresolved": True})
    return {"repo": name, "nodes": list(nodes.values()), "edges": edges}
