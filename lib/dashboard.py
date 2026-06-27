"""Dashboard index for traced E2E flows. Stdlib only — zero LLM/token cost."""
import html
import json
import re


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(s):
    """Lowercase, non-alnum chars -> '-', collapse runs, strip edges."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


def _norm(s):
    """Lowercase, strip, collapse internal spaces (for match keys)."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _entry_of(chain):
    """Return entry dict {repo, kind, symbol}; derive from steps[0] when absent."""
    if chain.get("entry"):
        return chain["entry"]
    steps = chain.get("steps", [])
    if steps:
        s0 = steps[0]
        return {
            "repo": s0.get("repo", ""),
            "kind": s0.get("layer", ""),
            "symbol": s0.get("title", ""),
        }
    return {"repo": "", "kind": "", "symbol": ""}


def _derive_slug(chain):
    """Return chain['slug'] or derive one from feature."""
    if chain.get("slug"):
        return chain["slug"]
    return _slugify(chain.get("feature", "flow"))


_SECURITY_RANK = {"risk": 3, "review": 2, "ok": 1}


def _worst_security(chain):
    """Return the worst security level across all steps, or None."""
    worst = None
    worst_rank = 0
    for step in chain.get("steps", []):
        lvl = (step.get("security") or {}).get("level")
        rank = _SECURITY_RANK.get(lvl, 0)
        if rank > worst_rank:
            worst_rank = rank
            worst = lvl
    return worst


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_flows(chains):
    """Return a dashboard index dict from a list of chain dicts.

    Structure:
    {
      "flows": [ {slug, feature, summary, entry_repo, repos, worst_security,
                  n_steps, href, search_text} ],
      "groups": { entry_repo: [slug, ...] },
      "cross_links": { slug: { step_id: target_slug } }
    }
    """
    # Build entry lookup: (norm_repo, norm_symbol) -> target_slug
    entry_lookup = {}
    for chain in chains:
        slug = _derive_slug(chain)
        entry = _entry_of(chain)
        key = (_norm(entry.get("repo", "")), _norm(entry.get("symbol", "")))
        entry_lookup[key] = slug

    flows = []
    groups = {}
    cross_links = {}

    for chain in chains:
        slug = _derive_slug(chain)
        entry = _entry_of(chain)
        entry_repo = entry.get("repo", "")
        feature = chain.get("feature", "")
        summary = chain.get("summary", "")
        steps = chain.get("steps", [])

        # Unique repos in order of appearance
        seen_repos = []
        for step in steps:
            r = step.get("repo", "")
            if r and r not in seen_repos:
                seen_repos.append(r)

        # Build search_text
        step_titles = " ".join(step.get("title", "") for step in steps)
        search_text = " ".join([feature, summary, step_titles] + seen_repos).lower()

        flow_record = {
            "slug": slug,
            "feature": feature,
            "summary": summary,
            "entry_repo": entry_repo,
            "repos": seen_repos,
            "worst_security": _worst_security(chain),
            "n_steps": len(steps),
            "href": f"flows/{slug}.html",
            "search_text": search_text,
        }
        flows.append(flow_record)

        # Group by entry repo
        groups.setdefault(entry_repo, []).append(slug)

        # Detect cross-links: steps (excluding own entry) that match another flow's entry
        own_entry_key = (_norm(entry.get("repo", "")), _norm(entry.get("symbol", "")))
        links_for_flow = {}
        for step in steps:
            step_key = (_norm(step.get("repo", "")), _norm(step.get("title", "")))
            if step_key == own_entry_key:
                continue  # never self-link on the entry step
            target = entry_lookup.get(step_key)
            if target and target != slug:
                links_for_flow[step["id"]] = target
        if links_for_flow:
            cross_links[slug] = links_for_flow

    return {"flows": flows, "groups": groups, "cross_links": cross_links}


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _esc(s):
    """HTML-escape a string."""
    return html.escape(str(s) if s is not None else "")


def _security_badge(level):
    """Return a styled HTML badge for a security level."""
    colors = {
        "risk": ("#c0392b", "#fdf0ef", "riesgo"),
        "review": ("#d68910", "#fef9e7", "revisar"),
        "ok": ("#1e8449", "#eafaf1", "ok"),
    }
    if level in colors:
        fg, bg, label = colors[level]
        return (
            f'<span style="background:{bg};color:{fg};border:1px solid {fg};'
            f'border-radius:4px;padding:1px 7px;font-size:11px;font-weight:600;">'
            f'{label}</span>'
        )
    return '<span style="background:#ecf0f1;color:#7f8c8d;border:1px solid #bdc3c7;border-radius:4px;padding:1px 7px;font-size:11px;">—</span>'


def render_dashboard_html(index, out_path):
    """Write a self-contained index.html dashboard."""
    flows = index["flows"]
    groups = index["groups"]
    cross_links = index["cross_links"]

    all_entry_repos = list(groups.keys())

    # Inline JSON for JS filtering
    index_json = json.dumps(index, ensure_ascii=False)

    # Build sidebar items HTML
    sidebar_items = []
    sidebar_items.append(
        '<li><a href="#" class="sidebar-link active" data-repo="__all__">'
        f'Todos <span class="repo-count">({len(flows)})</span></a></li>'
    )
    for repo in all_entry_repos:
        count = len(groups[repo])
        sidebar_items.append(
            f'<li><a href="#" class="sidebar-link" data-repo="{_esc(repo)}">'
            f'{_esc(repo)} <span class="repo-count">({count})</span></a></li>'
        )
    sidebar_html = "\n".join(sidebar_items)

    # Build cards HTML
    cards = []
    for flow in flows:
        slug = flow["slug"]
        has_cross = slug in cross_links
        repos_pills = " ".join(
            f'<span class="repo-pill">{_esc(r)}</span>'
            for r in flow["repos"]
        )
        cross_indicator = (
            '<span class="cross-indicator" title="Este flujo enlaza a otros flujos">enlaza &rarr;</span>'
            if has_cross else ""
        )
        badge = _security_badge(flow["worst_security"])
        card_html = f"""<div class="flow-card" data-entry-repo="{_esc(flow['entry_repo'])}" data-search="{_esc(flow['search_text'])}">
  <div class="card-header">
    <a class="card-title" href="{_esc(flow['href'])}">{_esc(flow['feature'])}</a>
    {cross_indicator}
  </div>
  <div class="card-meta">
    <span class="entry-repo-label">Repo entrada: <strong>{_esc(flow['entry_repo'])}</strong></span>
    &nbsp;|&nbsp; {badge} &nbsp;|&nbsp;
    <span class="steps-count">{flow['n_steps']} pasos</span>
  </div>
  <div class="card-repos">{repos_pills}</div>
  <div class="card-summary">{_esc(flow['summary'])}</div>
  <div class="card-link"><a href="{_esc(flow['href'])}">Ver flujo &rarr;</a></div>
</div>"""
        cards.append(card_html)

    cards_html = "\n".join(cards)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E2E Flow Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f6fa;color:#2c3e50;display:flex;min-height:100vh}}
/* Sidebar */
#sidebar{{width:220px;min-height:100vh;background:#2c3e50;color:#ecf0f1;flex-shrink:0;padding:0}}
#sidebar h2{{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#95a5a6;padding:20px 16px 8px}}
#sidebar ul{{list-style:none}}
#sidebar ul li a{{display:block;padding:9px 16px;color:#bdc3c7;text-decoration:none;font-size:14px;border-left:3px solid transparent;transition:background .15s}}
#sidebar ul li a:hover{{background:#34495e;color:#ecf0f1}}
#sidebar ul li a.active{{background:#1a252f;border-left-color:#3498db;color:#fff}}
.repo-count{{color:#7f8c8d;font-size:12px}}
/* Main */
#main{{flex:1;padding:24px;overflow-x:hidden}}
#main h1{{font-size:22px;margin-bottom:4px;color:#2c3e50}}
#main .subtitle{{font-size:13px;color:#7f8c8d;margin-bottom:18px}}
/* Search */
#search-box{{width:100%;max-width:480px;padding:9px 14px;font-size:14px;border:1px solid #d5d8dc;border-radius:6px;margin-bottom:20px;outline:none}}
#search-box:focus{{border-color:#3498db;box-shadow:0 0 0 2px rgba(52,152,219,.15)}}
/* Grid */
#cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
/* Card */
.flow-card{{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:16px;display:flex;flex-direction:column;gap:8px;transition:box-shadow .15s}}
.flow-card:hover{{box-shadow:0 3px 10px rgba(0,0,0,.13)}}
.flow-card.hidden{{display:none}}
.card-header{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.card-title{{font-size:15px;font-weight:600;color:#2980b9;text-decoration:none}}
.card-title:hover{{text-decoration:underline}}
.cross-indicator{{font-size:11px;background:#eaf4fb;color:#2471a3;border:1px solid #aed6f1;border-radius:10px;padding:1px 8px;white-space:nowrap}}
.card-meta{{font-size:12px;color:#7f8c8d;display:flex;align-items:center;flex-wrap:wrap;gap:4px}}
.entry-repo-label strong{{color:#2c3e50}}
.steps-count{{color:#95a5a6}}
.card-repos{{display:flex;flex-wrap:wrap;gap:5px}}
.repo-pill{{background:#eaf4fb;color:#1a5276;border-radius:4px;padding:2px 8px;font-size:11px;border:1px solid #aed6f1}}
.card-summary{{font-size:13px;color:#566573;line-height:1.45}}
.card-link a{{font-size:12px;color:#2980b9;text-decoration:none}}
.card-link a:hover{{text-decoration:underline}}
/* Empty state */
#empty-state{{display:none;text-align:center;padding:60px 0;color:#95a5a6;font-size:15px}}
</style>
</head>
<body>
<nav id="sidebar">
  <h2>Repos de entrada</h2>
  <ul>
    {sidebar_html}
  </ul>
</nav>
<main id="main">
  <h1>E2E Flow Dashboard</h1>
  <p class="subtitle">{len(flows)} flujo{"s" if len(flows) != 1 else ""} indexado{"s" if len(flows) != 1 else ""}</p>
  <input type="search" id="search-box" placeholder="Buscar flujos..." aria-label="Buscar flujos">
  <div id="cards-grid">
    {cards_html}
  </div>
  <div id="empty-state">No se encontraron flujos.</div>
</main>
<script>
(function(){{
  var INDEX = {index_json};
  var activeRepo = "__all__";
  var searchText = "";

  var grid = document.getElementById("cards-grid");
  var cards = Array.from(grid.querySelectorAll(".flow-card"));
  var emptyState = document.getElementById("empty-state");

  function applyFilters() {{
    var q = searchText.trim().toLowerCase();
    var visible = 0;
    cards.forEach(function(card) {{
      var repoMatch = activeRepo === "__all__" || card.dataset.entryRepo === activeRepo;
      var searchMatch = !q || card.dataset.search.indexOf(q) !== -1;
      if (repoMatch && searchMatch) {{
        card.classList.remove("hidden");
        visible++;
      }} else {{
        card.classList.add("hidden");
      }}
    }});
    emptyState.style.display = visible === 0 ? "block" : "none";
  }}

  // Sidebar
  document.querySelectorAll(".sidebar-link").forEach(function(link) {{
    link.addEventListener("click", function(e) {{
      e.preventDefault();
      document.querySelectorAll(".sidebar-link").forEach(function(l) {{ l.classList.remove("active"); }});
      link.classList.add("active");
      activeRepo = link.dataset.repo;
      applyFilters();
    }});
  }});

  // Search
  document.getElementById("search-box").addEventListener("input", function(e) {{
    searchText = e.target.value;
    applyFilters();
  }});
}})();
</script>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_content)
