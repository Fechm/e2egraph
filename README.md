# e2egraph

Turn local repositories into a navigable map of **end-to-end functional flows** — how a single feature travels from the frontend, through the GraphQL gateway / API layer, across gRPC or REST clients, into the destination microservice, down to the database table or external service it touches.

It is a [Claude Code](https://docs.claude.com/en/docs/claude-code) skill (`/e2egraph`). It does **not** use any provider API key: the deterministic work is plain Python, and the semantic work runs through Claude Code subagents in your current session.

> Built for microservice ecosystems (NestJS / GraphQL gateway / gRPC / Drizzle-or-SQL microservices / Next.js frontends), but the engine is generic.

---

## What you get

Running the skill over a folder of repos produces a self-contained output directory (`e2egraph-out/`) with three complementary views:

| View | File | What it answers |
|---|---|---|
| **Dashboard** | `index.html` | "What functionalities exist, and which are traced?" — a searchable catalog of every operation per repo, grouped by entry repo, each marked *traced* or *pending*. |
| **Flow** | `flows/<feature>.html` | "How does *this* feature work end to end?" — a clickable chain (frontend → resolver → gRPC/REST → microservice → table) with rich per-step detail. |
| **Overview** | `graph.html` | "Who calls whom?" — the architecture: repos as nodes, real service-to-service calls as edges. |

Plus `GRAPH_REPORT.md` (plain-language report) and `graph.json` (raw data).

Everything is a single self-contained HTML file (Cytoscape.js embedded inline) — open with a double-click, no server, no internet.

---

## The two-level model (the key idea)

Tracing every feature deeply would be expensive (each deep trace reads code via a subagent). So e2egraph splits the work in two levels:

1. **Catalog — free, deterministic, instant.** A pure-Python scan lists *every* operation in every repo (GraphQL operations consumed, resolvers/endpoints defined) with `file:line`. This fills the dashboard with full coverage at **zero token cost**.
2. **Deep trace — on demand, cached.** You pick a feature from the catalog and trace it end to end with `/e2egraph flow "<feature>"`. Only this step uses session tokens (a subagent reads the code), and the result is cached as `flows/<feature>.json` and shown on the dashboard.

> **You see everything for free; you pay only to deep-dive the features you care about.**

---

## Requirements

- **Claude Code** (the skill runs inside it).
- **Python 3** (standard library only — no `pip install` needed).
- **universal-ctags** *(optional)* — improves multi-language symbol extraction; falls back to regex if absent.
- For deep traces: a Claude Code session (the subagents run there). **No API key, ever.**

---

## Install

Place the skill folder at `~/.claude/skills/e2egraph/` and register the trigger in your `~/.claude/CLAUDE.md`:

```markdown
# e2egraph
- **e2egraph** (`~/.claude/skills/e2egraph/SKILL.md`) - local repos to E2E flow knowledge graph. Trigger: `/e2egraph`
When the user types `/e2egraph`, invoke the Skill tool with `skill: "e2egraph"` before doing anything else.
```

Or clone this repo into that path:
```bash
git clone git@github.com:Fechm/e2egraph.git ~/.claude/skills/e2egraph
```

---

## Usage

```
/e2egraph                      # build/refresh the dashboard over the current root
/e2egraph --root C:\path\repos # set the parent folder of your repos explicitly
/e2egraph --update             # incremental: only changed repos
/e2egraph flows                # the catalog (free) — what can be traced
/e2egraph flow "<feature>"     # deep-trace ONE feature end to end (uses session tokens)
/e2egraph --depth structural   # skip the semantic layer (zero tokens)
/e2egraph query "<question>"   # answer from graph.json via the session
```

**Typical workflow**

1. `/e2egraph --root <your repos folder>` → open `e2egraph-out/index.html`.
2. Search/browse the catalog; find a pending feature (e.g. `saveRequestTne`).
3. Click **"Trazar"** on its card → it copies `/e2egraph flow "saveRequestTne"` to your clipboard.
4. Paste it into Claude Code → the flow is traced in detail.
5. Refresh the dashboard → the feature now shows as traced, with its security badge and a link to its flow.

---

## Anatomy of a traced flow

Each step in a flow HTML is a **clickable node**. Clicking it shows:

- **File** (`file:line`) and what the step does.
- **Mechanism** to the next hop (GraphQL mutation, gRPC client-streaming, REST call, SQL write…).
- **Used in** — where the feature is triggered (e.g. *"Save button on the TNE request page"*).
- **Participants** — the services/calls involved inside that step.
- **Data contract** — the fields and types that travel through (GraphQL input type, proto message, validation schema, DB columns), each marked required or optional.
- **Security** — an honest, per-step observation: 🟢 controls present / 🟡 review / 🔴 risk, each with `file:line` evidence and a disclaimer. **It never stamps a step as "secure"** — it reports controls found and concrete flags, because a false green is worse than none.

---

## How it works

```
detect  →  symbols + relations  →  build (per-repo graph)  →  crossrepo (merge + resolve)  →  overview + dashboard
                                                                                                       │
                                                              catalog (deterministic, free) ───────────┤
                                                                                                       │
                                          flow "<feature>"  →  subagent traces E2E  →  flow HTML + dashboard card
```

- **Structural extraction (deterministic, free):** repo/file detection, symbols (ctags or regex fallback), imports, env-var service references (`*_URL`/`*_HOST`/`*_ADDRESS`, `config.X`, `configService.get`), API calls, `.proto` services, SQL / Drizzle tables.
- **Cross-repo resolution:** service env vars are matched to the destination repo **only when the match is unambiguous** (exact or unique token match) — it never guesses on a shared word; shared tables and proto contracts link producers and consumers.
- **Semantic layer (selective, via subagents):** deep flow tracing, plain-language descriptions, per-step security and data contracts. Runs in your Claude Code session — no API key.

---

## Guarantees

- **No provider API key** is read at any stage. The semantic layer is Claude Code subagents (your session).
- **No secret leakage.** Env-var *values* are never read. Secret-looking var *names* are masked (e.g. `STRIPE_••••_KEY`); only service endpoints (`*_URL`/`*_HOST`/…) are kept. Nothing sensitive enters the graph, the HTML, or the report.
- **Self-contained output.** Each HTML embeds its library inline — no CDN, no network, no server.
- **Honest by design.** Edges that can't be confirmed are marked `AMBIGUOUS`; security is reported as observations with evidence, never a binary verdict.

---

## Architecture

Single-responsibility Python modules under `lib/` (standard library only):

| Module | Responsibility |
|---|---|
| `detect.py` | Discover repos and source files under a root |
| `symbols.py` | Symbols via universal-ctags, regex fallback |
| `relations.py` | Edges: imports, env vars, API, proto, SQL/Drizzle, endpoints |
| `secrets_filter.py` | Classify/mask env-var names (no secret leakage) |
| `build.py` | Assemble one repo's layered graph |
| `crossrepo.py` | Merge repos + resolve cross-repo connections |
| `overview.py` | Reduce to the clean architecture view (repos + flows) |
| `catalog.py` | Deterministic feature catalog |
| `semantic.py` | Merge subagent results (gql links, descriptions) |
| `render_html.py` | Interactive Cytoscape overview |
| `render_flow_html.py` | Interactive flow chain (detail, security, data contract) |
| `dashboard.py` | Dashboard: catalog, search, sidebar, trace buttons |
| `report.py` | `GRAPH_REPORT.md` |
| `io_utils.py` | Safe file reading |

---

## Testing

```bash
cd ~/.claude/skills/e2egraph
python -m unittest discover -s tests -v
```

The suite is pure `unittest` (no dependencies) and covers every module plus an end-to-end integration test over known fixtures (including the no-secret-leakage guarantee).

---

## Known limitations

- **Cross-repo matching by name is conservative** — it resolves only unambiguous matches. When a frontend points at a backend via a generic/`localhost` URL, that link is left to the semantic layer rather than guessed.
- **The deterministic catalog/chain is good, not perfect** — code that resolves things at runtime (dynamic URLs, conditionals) may leave gaps that only a deep trace fills.
- **Deep tracing costs session tokens** (a subagent reads code). The catalog, dashboard, search, and overview are free.
- **Large graphs** collapse the overview to a repo/module view above ~5000 nodes.

---

## License

Personal/internal tooling. Use at your own discretion.
