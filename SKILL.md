---
name: e2egraph
description: "Use to visualize and trace the end-to-end flow across local repositories — how one repo connects to another via env vars, API calls, proto/gRPC, shared libs and databases. Builds a per-repo graph then a cross-repo general graph. No provider API key: semantic steps run via Claude Code subagents."
---

# /e2egraph

Turn local repos into a navigable knowledge graph and trace end-to-end flow across them.

## Usage

```
/e2egraph                      # build/refresh the dashboard (index.html) over the root
/e2egraph --root C:\IACC       # set the parent root explicitly
/e2egraph --update             # incremental: only changed repos
/e2egraph flows                # catalog: list detected features/operations to trace
/e2egraph flow "<feature>"     # trace ONE feature end-to-end (frontend→…→data) and add it to the dashboard
/e2egraph --depth structural   # skip the semantic layer (zero Claude tokens)
/e2egraph query "<question>"   # answer from graph.json via the session (no API key)
```

## What you must do when invoked

If `--help`/`-h` with no other args: print the Usage block verbatim and stop.

### Step 0 - Resolve interpreter (once)

```bash
SKILL_DIR="$HOME/.claude/skills/e2egraph"
PYTHON=$(command -v python3 || command -v python)
"$PYTHON" -c "import sys" || { echo "Python 3 required"; exit 1; }
ROOT="${1:-$(pwd)}"   # or the --root value
mkdir -p "$ROOT/e2egraph-out"
echo "$PYTHON" > "$ROOT/e2egraph-out/.e2egraph_python"
```

### Step 1 - Detect repos and files

```bash
cd "$SKILL_DIR" && "$PYTHON" -c "
import json, sys
from lib.detect import detect
print(json.dumps(detect(sys.argv[1])))
" "$ROOT" > "$ROOT/e2egraph-out/.e2egraph_detect.json"
```
Read it silently; present a clean summary: `Repos: N` and per-repo file counts. If 0 repos, stop with `No repos found under <root>.`

### Step 2 - Build each repo's graph (structural, free)

For each repo in the detect output, run symbols (ctags or fallback) + relations + build, writing `e2egraph-out/repos/<repo>/graph.json`. Drive this with one Python block per repo that imports `lib.symbols`, `lib.relations`, `lib.build`, and `read_text_safe` from `lib.io_utils`; read each source file's text with `read_text_safe(path)` (it returns `""` and never raises on unreadable/non-UTF8/binary files, so one bad file cannot abort a repo); calls `extract_relations` and `extract_symbols_ctags`/`extract_symbols_fallback`, then `build_repo_graph`, and `json.dump`s the result. Honor `--no-ctags` by skipping `extract_symbols_ctags`. If `ctags_available()` is False, print once: `ctags not found - using regex symbol fallback.`

For `--update`, only rebuild the repo(s) named on the command line (or whose files changed); reuse existing `repos/*/graph.json` for the rest.

### Step 3 - Merge into the general graph

```bash
cd "$SKILL_DIR" && "$PYTHON" -c "
import json, glob, os, sys
from lib.crossrepo import merge_graphs
root=sys.argv[1]
graphs=[json.load(open(p,encoding='utf-8')) for p in glob.glob(os.path.join(root,'e2egraph-out','repos','*','graph.json'))]
merged=merge_graphs(graphs)
json.dump(merged, open(os.path.join(root,'e2egraph-out','graph.json'),'w',encoding='utf-8'))
print('Merged %d repos: %d nodes, %d edges, %d flows' % (len(graphs), len(merged['nodes']), len(merged['edges']), len(merged['flows'])))
" "$ROOT"
```

### Step 4 - Semantic layer (selective; skip if --depth structural)

Skip this step entirely when `--depth structural` is present.

**4a — Identify GraphQL participants**

Load `e2egraph-out/graph.json` and call `lib.semantic.gql_participants(graph)` to obtain two sorted lists: `consumers` (repos with a `GRAPHQL` env var or a `calls_api` edge whose target contains "graphql") and `providers` (repos with a `defines_gql_op` edge). If both lists are empty, skip 4b–4d and go straight to community naming below.

**4b — Dispatch Claude Code subagents (no API key)**

Send a **single message** with one `Agent` tool call per consumer–provider pair, all in parallel. Use agent type `general-purpose`. There is NO provider API key anywhere in e2egraph; these run in the current Claude Code session only.

Prompt template for each subagent (fill in `<CONSUMER_PATH>` and `<PROVIDER_PATH>` from the detect output):

> You are analysing GraphQL usage between two local repositories.
> Consumer repo: `<CONSUMER_PATH>` — read its GraphQL operations: look for gql template literals (`.gql`, `.graphql` files, `gql\`...\`` tagged literals, `DocumentNode` variables).
> Provider repo: `<PROVIDER_PATH>` — read its resolvers: look for `@Query()`, `@Mutation()`, `@ResolveField()` decorators (NestJS), or SDL type definitions (`.graphql` schema files).
> Only assert a link when a consumed operation name **plausibly matches** a resolver name. When uncertain, note it in the description field — these become AMBIGUOUS edges.
> Return STRICT JSON only, no markdown fences, no extra keys:
> ```json
> {
>   "gql_links": [
>     {"consumer": "<consumer-repo-name>", "provider": "<provider-repo-name>",
>      "operation": "<operationName>", "kind": "query|mutation|subscription",
>      "description": "<one sentence; flag uncertainty>",
>      "evidence": "<file:line or literal snippet>"}
>   ],
>   "flow_descriptions": {
>     "<existing flow name from graph.json>": "<plain-language rewrite>"
>   }
> }
> ```
> If nothing found, return `{"gql_links": [], "flow_descriptions": {}}`.

**4c — Merge results**

For each agent result, parse the JSON and call:
```python
from lib.semantic import merge_semantic
merge_semantic(graph, result)
```
After processing all agents, re-save `graph.json`. Print a summary: how many `gql_links` were added and the token counts from each Agent result.

**4d — Community naming (all runs)**

Also dispatch one additional subagent that reads the merged `graph.json` node list and returns `{"community_names": {"<node-id>": "<plain-language name>"}}` for any cluster/community nodes present. Merge those names into matching node labels via `merge_semantic(graph, result)` and re-save.

**Guarantee:** No API key is used at any point. All subagents run inside the current Claude Code session via the Agent tool.

### Step 5 - Render overview and dashboard

```bash
cd "$SKILL_DIR" && "$PYTHON" -c "
import json, os, glob, sys
from lib.overview import to_overview
from lib.render_html import render_html
from lib.report import generate_report
from lib.catalog import extract_catalog
from lib.dashboard import index_flows, attach_catalog, render_dashboard_html
root=sys.argv[1]
out=os.path.join(root,'e2egraph-out')
g=json.load(open(os.path.join(out,'graph.json'),encoding='utf-8'))
ov=to_overview(g)
render_html(ov, os.path.join(out,'graph.html'))      # clean architecture view (repos+flows)
open(os.path.join(out,'GRAPH_REPORT.md'),'w',encoding='utf-8').write(generate_report(g))
# load detect result for the catalog (fallback: re-run detect if file absent)
detect_path=os.path.join(out,'.e2egraph_detect.json')
if os.path.exists(detect_path):
    detect_result=json.load(open(detect_path,encoding='utf-8'))
else:
    from lib.detect import detect
    detect_result=detect(root)
    json.dump(detect_result,open(detect_path,'w',encoding='utf-8'))
# extract consumed entry points (free, deterministic)
feats=[f for f in extract_catalog(detect_result) if f['role']=='consumed']
# load any traced flows and build traced-slug set
chains,traced=[],set()
for p in glob.glob(os.path.join(out,'flows','*.json')):
    c=json.load(open(p,encoding='utf-8')); chains.append(c)
    traced.add((c.get('slug') or '').lower())
    sym=(c.get('entry') or {}).get('symbol')
    if sym: traced.add(sym.lower())
# build index, attach catalog, render dashboard
idx=index_flows(chains)
idx=attach_catalog(idx, feats, traced)
render_dashboard_html(idx, os.path.join(out,'index.html'))
catalog_count=sum(len(v) for v in idx['catalog'].values())
print('Dashboard:', os.path.join(out,'index.html'), '| flujos:', len(chains), '| catalogo:', catalog_count)
" "$ROOT"
```

### Step 6 - Report

Tell the user that the entry point is `<root>/e2egraph-out/index.html` (the central dashboard — sidebar by entry repo, live text search, cross-links to each traced flow). Note that `graph.html` has the clean architecture view (repos + shared resources + flow edges). Paste the **E2E Flows** section of `GRAPH_REPORT.md`. Offer to trace the most interesting flow with `/e2egraph flow "<feature>"` (traces a feature end-to-end from frontend to data layer and adds it to the dashboard).

## For /e2egraph query

When `e2egraph-out/graph.json` exists and the user asks a question, load it and answer using only its nodes/edges/flows; cite `source_location`. No API key — reason over the JSON in-session.

## For /e2egraph flow "<feature>"

The controlling agent (Claude Code session) executes this protocol. No provider API key is used at any point — subagents run inside the current Claude Code session via the Agent tool.

**1. Resolve the feature.**
From `graph.json`, find where the named feature/operation is used: a frontend action, a GraphQL operation, or a named endpoint. If ambiguous, show the candidates and ask the user to clarify.

**2. Dispatch a Claude Code subagent (Agent tool, general-purpose).**
The subagent READS the real code and traces the chain hop by hop:

  frontend → gateway resolver → gRPC/REST client → proto/contract → microservice handler → DB table/service

The subagent must return STRICT JSON only (no markdown fences), with this exact structure:

```json
{
  "feature": "<human-readable name>",
  "slug": "<kebab-case-identifier>",
  "entry": { "repo": "<name>", "kind": "frontend|gateway|service", "symbol": "<symbol>" },
  "summary": "<one paragraph end-to-end description>",
  "steps": [
    {
      "id": "<slug-step-N>",
      "layer": "frontend|gateway_resolver|grpc_client|proto|microservice|data",
      "repo": "<repo name>",
      "title": "<step title>",
      "file": "<relative/path/to/file>",
      "line": <line number or null>,
      "mechanism": "<e.g. GraphQL mutation, gRPC call, SQL query>",
      "detail": "<what happens here>",
      "used_in": ["<other feature slugs that share this step>"],
      "participants": ["<repo names involved>"],
      "security": {
        "level": "ok|review|risk",
        "controls": ["<control description with file:line>"],
        "flags": ["<flag description with file:line>"],
        "note": "<optional free text>"
      },
      "data_shape": {
        "label": "<e.g. CreateUserInput>",
        "kind": "graphql_input|proto_message|joi_schema|db_model|unknown",
        "source": "<file:line>",
        "fields": [
          { "name": "<field>", "type": "<type>", "required": true, "note": "<optional>" }
        ]
      }
    }
  ]
}
```

The `security` and `data_shape` blocks are optional per step but should be included whenever the real code provides enough evidence.

**Honesty rules for the subagent:**
- Never fabricate a hop, field, or security control that is not present in the actual code.
- When uncertain about a hop, set `"level": "review"` and explain what could not be confirmed.
- For security: NEVER stamp a step as "secure" — always report the controls that are present plus any flags (e.g. missing auth check, no input validation) with exact `file:line`.
- Extract `data_shape` from the real GraphQL input type, proto message, Joi schema, or DB model — do not guess field names.

**3. Render and save.**
After the subagent returns:

```python
from lib.render_flow_html import render_flow_html
from lib.catalog import extract_catalog
from lib.dashboard import index_flows, attach_catalog, render_dashboard_html
import json, glob, os

# Save the chain
slug = chain["slug"]
out_dir = os.path.join(root, "e2egraph-out", "flows")
os.makedirs(out_dir, exist_ok=True)
json.dump(chain, open(os.path.join(out_dir, f"{slug}.json"), "w", encoding="utf-8"), indent=2)

# Render the individual flow page
render_flow_html(chain, os.path.join(out_dir, f"{slug}.html"))

# Rebuild the dashboard with full catalog so the new flow appears
chains = [json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(root, "e2egraph-out", "flows", "*.json"))]
traced = set()
for c in chains:
    traced.add((c.get("slug") or "").lower())
    sym = (c.get("entry") or {}).get("symbol")
    if sym: traced.add(sym.lower())
detect_path = os.path.join(root, "e2egraph-out", ".e2egraph_detect.json")
if os.path.exists(detect_path):
    detect_result = json.load(open(detect_path, encoding="utf-8"))
else:
    from lib.detect import detect
    detect_result = detect(root)
    json.dump(detect_result, open(detect_path, "w", encoding="utf-8"))
feats = [f for f in extract_catalog(detect_result) if f["role"] == "consumed"]
idx = index_flows(chains)
idx = attach_catalog(idx, feats, traced)
render_dashboard_html(idx, os.path.join(root, "e2egraph-out", "index.html"))
```

Report to the user: the flow HTML path, the dashboard path, and a one-paragraph summary of the chain.

**Token cost note:** Tracing a flow uses session tokens (the subagent reads real code). The result is cached as `flows/<slug>.json`. Re-running the dashboard step (to refresh `index.html` after tracing more flows) is deterministic and costs zero tokens.

## For /e2egraph flows

This command is deterministic and costs zero tokens.

**Two-level model:**

- **Catalog (free, deterministic):** The dashboard (`e2egraph-out/index.html`) already renders the full feature catalog grouped by repo. It includes a live text search and marks each entry as `traced` (a `flows/<slug>.json` exists) or `pending` (not yet traced). The catalog is built by `extract_catalog` from the detect result — no tokens consumed.
- **Deep trace (paid, cached):** `/e2egraph flow "<feature>"` traces one entry point end-to-end (frontend → gateway → microservice → data), spending session tokens. The result is cached as `flows/<slug>.json` and the dashboard card is updated automatically.

**When the user runs `/e2egraph flows`:**

Point the user to `e2egraph-out/index.html` — open it in a browser to browse and search the full catalog with traced/pending markers. If the user wants the catalog in chat (no browser), extract it in-session:

```python
import json, os
from lib.catalog import extract_catalog
root = "$ROOT"   # fill in at runtime
detect_path = os.path.join(root, "e2egraph-out", ".e2egraph_detect.json")
detect_result = json.load(open(detect_path, encoding="utf-8"))
feats = [f for f in extract_catalog(detect_result) if f["role"] == "consumed"]
# group by repo and print
from collections import defaultdict
by_repo = defaultdict(list)
for f in feats:
    by_repo[f["repo"]].append(f)
for repo, items in sorted(by_repo.items()):
    print(f"\n### {repo}")
    for f in items:
        print(f"  {f['kind']:20s}  {f['name']}  ({f['file']}:{f['line']})")
```

Present the output as a grouped list and offer to trace any entry with `/e2egraph flow "<feature>"`.

## Honesty & security rules

- Never invent an edge; unsure -> `AMBIGUOUS` with evidence.
- Never write env-var values or full secret names to any artifact (handled by `lib/secrets_filter`).
- Always show semantic-layer token counts.
- Warn before rendering HTML for a graph above ~5000 nodes; collapse to repo/module view.
- Security observations in flow traces are heuristic and per-step: report controls that are present with evidence (file:line) and flags where controls are missing or weak. Never issue a binary "secure" verdict for a step or the overall flow.
- The dashboard (`index.html`), search, and overview (`graph.html`) are fully deterministic and cost zero tokens. Only tracing a flow with `/e2egraph flow` uses session tokens (the subagent reads real code).
