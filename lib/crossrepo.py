"""Merge per-repo graphs and resolve cross-repo edges into shared resources + E2E flows."""

import re
from lib.secrets_filter import classify_env
from lib.relations import normalize_endpoint_path

_INTERP_RE = re.compile(r"\$\{[^}]*\}")

def _static_path_from_url(url):
    u = _INTERP_RE.sub("", url)
    m = re.search(r"/[A-Za-z0-9_\-/:{}]+", u)
    if not m:
        return None
    path = normalize_endpoint_path(m.group(0))
    # require at least 2 path segments to avoid noise like "/" or "/health"
    return path if path.count("/") >= 2 else None

def _shared_resource(merged_nodes, node_id, label, ntype):
    if not any(n["id"] == node_id for n in merged_nodes):
        merged_nodes.append({"id": node_id, "label": label, "type": ntype,
                             "repo": None, "layer": "shared", "path": None,
                             "lang": None, "source_location": None})

_SERVICE_SUFFIX_TOKENS = {"url", "host", "endpoint", "uri", "base"}
_GENERIC_TOKENS = {"api", "service", "svc"} | _SERVICE_SUFFIX_TOKENS

def _norm_tokens(s):
    return [t for t in s.lower().replace("_", "-").split("-") if t]

def _service_candidate_tokens(varname):
    toks = _norm_tokens(varname)
    while toks and toks[-1] in _SERVICE_SUFFIX_TOKENS:
        toks.pop()
    return toks

def _match_repo(varname, repo_token_map):
    cand = _service_candidate_tokens(varname)
    meaningful = [t for t in cand if t not in _GENERIC_TOKENS and len(t) >= 4]
    if not meaningful:
        return None
    best = None
    for repo_name, rtoks in repo_token_map.items():
        if cand and cand == list(_norm_tokens(repo_name)):
            return repo_name
        if any(t in rtoks for t in meaningful):
            best = repo_name
    return best

def merge_graphs(graphs):
    nodes = []
    edges = []
    for g in graphs:
        nodes.extend(g["nodes"])
        edges.extend(g["edges"])
    flows = []
    # Resolve shared tables: reads_table/writes_table/declares_table target becomes a db_table node
    table_targets = {}
    for e in edges:
        if e["type"] in ("reads_table", "writes_table", "declares_table") and e.get("unresolved"):
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
    # Resolve service env vars to repo calls_service edges
    repo_names = [n["label"] for n in nodes if n.get("type") == "repo" and n.get("label")]
    repo_token_map = {rn: set(_norm_tokens(rn)) for rn in repo_names}
    seen_calls = set()
    for n in nodes:
        if n.get("type") != "env_var":
            continue
        if classify_env(n.get("label", "")) != "service":
            continue
        owner = n.get("repo")
        target_repo = _match_repo(n.get("label", ""), repo_token_map)
        if target_repo and target_repo != owner and owner in repo_token_map:
            key = (owner, target_repo)
            if key in seen_calls:
                continue
            seen_calls.add(key)
            edges.append({"source": owner, "target": target_repo, "type": "calls_service",
                          "confidence": "INFERRED", "evidence": f"env var {n['label']}"})
            flows.append({"name": f"Service call: {owner} → {target_repo}",
                          "path": [owner, target_repo],
                          "description": f"{owner} calls {target_repo} via {n['label']}."})
    # Index endpoints defined per repo (defines_endpoint edges)
    endpoint_def = {}  # normalized_path -> set(repo)
    for e in edges:
        if e["type"] == "defines_endpoint":
            endpoint_def.setdefault(e["target"], set()).add(e["source"].split(":")[0])
    seen_ep = set()
    for e in edges:
        if e["type"] != "calls_api":
            continue
        consumer = e["source"].split(":")[0]
        path = _static_path_from_url(e.get("target", "") or "")
        if not path:
            continue
        for provider in endpoint_def.get(path, ()):  # exact normalized-path match
            if provider == consumer:
                continue
            key = (consumer, provider, path)
            if key in seen_ep:
                continue
            seen_ep.add(key)
            edges.append({"source": consumer, "target": provider, "type": "calls_endpoint",
                          "confidence": "INFERRED", "evidence": f"calls {path}"})
            flows.append({"name": f"Endpoint: {consumer} → {provider} {path}",
                          "path": [consumer, provider],
                          "description": f"{consumer} calls {provider} endpoint {path}."})
    return {"nodes": nodes, "edges": edges, "flows": flows}
