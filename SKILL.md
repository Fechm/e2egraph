---
name: e2egraph
description: "Use to visualize and trace the end-to-end flow across local repositories — how one repo connects to another via env vars, API calls, proto/gRPC, shared libs and databases. Builds a per-repo graph then a cross-repo general graph. No provider API key: semantic steps run via Claude Code subagents."
---

# /e2egraph

Turn local repos into a navigable knowledge graph and trace end-to-end flow across them.

## Usage

```
/e2egraph                      # current dir as root: build each repo + the general graph
/e2egraph <repo-path>          # build/update one repo, recompute the general graph
/e2egraph --root C:\IACC       # set the parent root explicitly
/e2egraph --update             # incremental: only changed repos
/e2egraph --depth structural   # skip the semantic layer (zero Claude tokens)
/e2egraph --no-ctags           # force regex fallback for symbols
/e2egraph query "<question>"   # answer from graph.json via the session (no API key)
/e2egraph path "repoA/x" "repoB/y"   # flow/path between two points
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

### Step 5 - Render outputs

```bash
cd "$SKILL_DIR" && "$PYTHON" -c "
import json, os, sys
from lib.render_html import render_html
from lib.report import generate_report
root=sys.argv[1]; g=json.load(open(os.path.join(root,'e2egraph-out','graph.json'),encoding='utf-8'))
render_html(g, os.path.join(root,'e2egraph-out','graph.html'))
open(os.path.join(root,'e2egraph-out','GRAPH_REPORT.md'),'w',encoding='utf-8').write(generate_report(g))
print('Wrote graph.html and GRAPH_REPORT.md')
" "$ROOT"
```

### Step 6 - Report

Tell the user where the outputs are (`<root>/e2egraph-out/`), paste the **E2E Flows** section of `GRAPH_REPORT.md`, and offer to trace the most interesting flow with `/e2egraph query`.

## For /e2egraph query and path

When `e2egraph-out/graph.json` exists and the user asks a question, load it and answer using only its nodes/edges/flows; cite `source_location`. For `path`, do a BFS over edges between the two node ids and report the chain. No API key - reason over the JSON in-session.

## Honesty & security rules

- Never invent an edge; unsure -> `AMBIGUOUS` with evidence.
- Never write env-var values or full secret names to any artifact (handled by `lib/secrets_filter`).
- Always show semantic-layer token counts.
- Warn before rendering HTML for a graph above ~5000 nodes; collapse to repo/module view.
