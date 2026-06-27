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

def attach_catalog(index, catalog_features, traced_slugs):
    """Attach catalog features to an index, marking traced ones with href.

    Parameters
    ----------
    index : dict
        The dict returned by ``index_flows()``.
    catalog_features : list[dict]
        Feature dicts from ``lib.catalog.extract_catalog()``.
    traced_slugs : set[str]
        Lower-cased slugs / entry-symbols of traced flows (used for matching).

    Returns
    -------
    dict
        A *new* index dict (same flows/groups/cross_links) with an additional
        key ``"catalog"`` -> ``{repo: [annotated_feature, ...]}``.
        Input feature dicts are NOT mutated.
    """
    lower_slugs = {s.lower() for s in traced_slugs}

    # Build a reverse lookup: lower-case slug/symbol -> flow href
    # so we can produce the correct href for each traced feature.
    slug_to_href = {}
    for flow in index.get("flows", []):
        slug_to_href[flow["slug"].lower()] = flow["href"]
        entry_sym = _norm(flow.get("entry_repo", ""))  # not the symbol
    # Also index by entry symbol (the slug already IS the entry symbol in most cases,
    # but we also walk the flows to capture entry["symbol"] values if present).
    # We rebuild from the original flows list which stores slug and href.
    for flow in index.get("flows", []):
        slug_to_href[flow["slug"].lower()] = flow["href"]

    catalog_by_repo = {}
    for feat in catalog_features:
        name_lower = feat.get("name", "").lower()
        rf_lower = (feat.get("root_field") or "").lower()

        # Determine if traced
        traced = name_lower in lower_slugs or (rf_lower and rf_lower in lower_slugs)

        # Determine href
        href = None
        if traced:
            # Find which flow slug matches
            match_key = None
            if name_lower in lower_slugs:
                match_key = name_lower
            elif rf_lower in lower_slugs:
                match_key = rf_lower
            # slug_to_href uses the flow's slug.lower() as key; match_key is the
            # traced_slug itself. We need the flow whose slug == match_key.
            href = slug_to_href.get(match_key)
            if href is None:
                # Fallback: construct href from the matched slug
                href = f"flows/{match_key}.html"

        annotated = dict(feat)  # copy — do not mutate original
        annotated["traced"] = traced
        annotated["href"] = href

        repo = feat.get("repo", "")
        catalog_by_repo.setdefault(repo, []).append(annotated)

    # Build result: copy index and add "catalog" key
    result = dict(index)
    result["catalog"] = catalog_by_repo
    return result


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
    """Write a self-contained index.html dashboard.

    If ``index`` contains a ``"catalog"`` key (added by ``attach_catalog``),
    the dashboard also renders a catalog view alongside the flows view:
    - Sidebar lists repos with ``traced/total`` counts.
    - A search input filters both flows and catalog items.
    - Traced catalog features show a security badge and a link to the flow.
    - Pending (un-traced) features are shown compact with a "pendiente de trazar" marker.

    When ``index`` has NO ``"catalog"`` key the output is identical to the
    original behaviour (existing tests pass unchanged).
    """
    flows = index["flows"]
    groups = index["groups"]
    cross_links = index["cross_links"]
    catalog = index.get("catalog")  # None when not present

    # Inline JSON for JS filtering
    index_json = json.dumps(index, ensure_ascii=False)

    # -----------------------------------------------------------------------
    # Sidebar: repos list
    # -----------------------------------------------------------------------
    # When catalog is present, collect all repos from BOTH sources.
    if catalog is not None:
        # Merge repos from flows (groups keys) and catalog keys, preserving order
        all_repos_set = set(groups.keys()) | set(catalog.keys())
        all_repos = [r for r in list(groups.keys()) if r in all_repos_set]
        for r in catalog.keys():
            if r not in all_repos:
                all_repos.append(r)

        # Count traced/total for each repo
        def _repo_counts(repo):
            cat_feats = catalog.get(repo, [])
            total = len(cat_feats)
            traced_count = sum(1 for f in cat_feats if f.get("traced"))
            return traced_count, total

        total_features = sum(len(v) for v in catalog.values())
        total_traced = sum(
            sum(1 for f in feats if f.get("traced"))
            for feats in catalog.values()
        )

        sidebar_items = []
        sidebar_items.append(
            '<li><a href="#" class="sidebar-link active" data-repo="__all__">'
            f'Todos <span class="repo-count">({len(flows)} flujos)</span></a></li>'
        )
        for repo in all_repos:
            tc, tot = _repo_counts(repo)
            flow_count = len(groups.get(repo, []))
            sidebar_items.append(
                f'<li><a href="#" class="sidebar-link" data-repo="{_esc(repo)}">'
                f'{_esc(repo)} <span class="repo-count">{tc}/{tot}</span></a></li>'
            )
    else:
        all_entry_repos = list(groups.keys())
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

    # -----------------------------------------------------------------------
    # Build flows cards HTML (always present)
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # Build catalog section HTML (only when catalog is present)
    # -----------------------------------------------------------------------
    catalog_section_html = ""
    if catalog is not None:
        # Build a slug -> worst_security lookup from the indexed flows
        slug_security = {f["slug"]: f["worst_security"] for f in flows}

        catalog_rows = []
        for repo, feats in catalog.items():
            for feat in feats:
                name = feat.get("name", "")
                root_field = feat.get("root_field") or name
                kind = feat.get("kind", "")
                ffile = feat.get("file", "")
                line = feat.get("line", "")
                traced = feat.get("traced", False)
                href = feat.get("href")

                # Search text for this row
                search_parts = [name, root_field, ffile, repo, kind]
                row_search = " ".join(search_parts).lower()

                if traced and href:
                    # Find worst_security from the matching flow
                    # href is like "flows/<slug>.html" → extract slug
                    flow_slug = href.replace("flows/", "").replace(".html", "")
                    sec = slug_security.get(flow_slug)
                    badge_html = _security_badge(sec)
                    row_html = (
                        f'<div class="cat-row cat-traced" data-repo="{_esc(repo)}" data-search="{_esc(row_search)}">'
                        f'<span class="cat-name"><a href="{_esc(href)}">{_esc(root_field)}</a></span>'
                        f'<span class="cat-kind">{_esc(kind)}</span>'
                        f'{badge_html}'
                        f'<span class="cat-file">{_esc(ffile)}:{_esc(str(line))}</span>'
                        f'</div>'
                    )
                else:
                    # Pending feature: embed root_field in a data attribute for JS to build the command
                    # Use html.escape to safely embed the feature name; JS reads data-feature and builds the command
                    row_html = (
                        f'<div class="cat-row cat-pending" data-repo="{_esc(repo)}" data-search="{_esc(row_search)}">'
                        f'<input type="checkbox" class="cat-select-cb" data-feature="{_esc(root_field)}" aria-label="Seleccionar {_esc(root_field)}">'
                        f'<span class="cat-name cat-name-muted">{_esc(root_field)}</span>'
                        f'<span class="cat-kind">{_esc(kind)}</span>'
                        f'<span class="cat-pending-label">pendiente de trazar</span>'
                        f'<span class="cat-file">{_esc(ffile)}:{_esc(str(line))}</span>'
                        f'<button class="cat-trace-btn" data-feature="{_esc(root_field)}" title="/e2egraph flow &quot;{_esc(root_field)}&quot;">Trazar</button>'
                        f'</div>'
                    )
                catalog_rows.append(row_html)

        catalog_rows_html = "\n".join(catalog_rows)
        catalog_section_html = f"""
<textarea id="clip-fallback" aria-hidden="true" tabindex="-1"></textarea>
<section id="catalog-section">
  <h2 class="section-title">Catálogo de funcionalidades
    <span class="catalog-totals">{total_features} funcionalidades &middot; {total_traced} trazadas</span>
  </h2>
  <div id="catalog-list">
    {catalog_rows_html}
  </div>
  <div id="catalog-empty" style="display:none;text-align:center;padding:40px 0;color:#95a5a6;font-size:14px">
    No se encontraron funcionalidades.
  </div>
  <div id="batch-copy-bar">
    <button id="batch-copy-btn" disabled>Copiar selección (0)</button>
  </div>
</section>"""

    # -----------------------------------------------------------------------
    # Extra CSS for catalog (injected only when needed)
    # -----------------------------------------------------------------------
    catalog_css = ""
    if catalog is not None:
        catalog_css = """
/* Catalog section */
.section-title{font-size:17px;font-weight:600;color:#2c3e50;margin:28px 0 12px;display:flex;align-items:baseline;gap:12px}
.catalog-totals{font-size:12px;color:#7f8c8d;font-weight:400}
#catalog-list{display:flex;flex-direction:column;gap:4px}
.cat-row{display:flex;align-items:center;gap:10px;padding:7px 12px;border-radius:6px;font-size:13px;flex-wrap:wrap}
.cat-row.hidden{display:none}
.cat-traced{background:#fff;border:1px solid #d5e8f8}
.cat-pending{background:#fafafa;border:1px solid #eaecee;opacity:.85}
.cat-name{font-weight:500;color:#2c3e50;min-width:180px}
.cat-name a{color:#2980b9;text-decoration:none}
.cat-name a:hover{text-decoration:underline}
.cat-name-muted{color:#7f8c8d}
.cat-kind{font-size:11px;background:#f0f3f4;color:#566573;border-radius:3px;padding:1px 6px;white-space:nowrap}
.cat-pending-label{font-size:11px;color:#aab7b8;font-style:italic}
.cat-file{font-size:11px;color:#aab7b8;margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:300px}
/* Trace button */
.cat-trace-btn{font-size:11px;padding:2px 10px;border:1px solid #2980b9;border-radius:4px;background:#eaf4fb;color:#2980b9;cursor:pointer;white-space:nowrap;transition:background .12s,color .12s}
.cat-trace-btn:hover{background:#2980b9;color:#fff}
.cat-trace-btn.copied{background:#27ae60;border-color:#27ae60;color:#fff}
/* Batch copy bar */
#batch-copy-bar{position:sticky;bottom:16px;z-index:10;display:none;justify-content:flex-end;padding:6px 0 2px}
#batch-copy-btn{background:#2980b9;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:13px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.18);transition:background .12s}
#batch-copy-btn:hover{background:#1a6395}
#batch-copy-btn:disabled{background:#95a5a6;cursor:default}
/* Hidden textarea for clipboard fallback */
#clip-fallback{position:absolute;left:-9999px;top:-9999px;opacity:0;pointer-events:none}
/* Checkbox */
.cat-select-cb{width:14px;height:14px;flex-shrink:0;cursor:pointer}
"""

    # -----------------------------------------------------------------------
    # Extra JS for catalog filtering (injected only when needed)
    # -----------------------------------------------------------------------
    catalog_js = ""
    if catalog is not None:
        catalog_js = """
  // ----------------------------------------------------------------
  // Clipboard helper: try navigator.clipboard, fall back to execCommand
  // ----------------------------------------------------------------
  function copyToClipboard(text, btn) {
    function doFallback(txt) {
      var ta = document.getElementById("clip-fallback");
      if (!ta) { ta = document.createElement("textarea"); ta.id = "clip-fallback"; document.body.appendChild(ta); }
      ta.value = txt;
      ta.select();
      try { document.execCommand("copy"); } catch(e) {}
    }
    function onSuccess(b) {
      if (!b) return;
      var orig = b.textContent;
      b.textContent = "¡Copiado!";
      b.classList.add("copied");
      setTimeout(function() { b.textContent = orig; b.classList.remove("copied"); }, 1500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() { onSuccess(btn); }).catch(function() {
        doFallback(text); onSuccess(btn);
      });
    } else {
      doFallback(text); onSuccess(btn);
    }
  }

  // ----------------------------------------------------------------
  // Trace buttons: copy /e2egraph flow "<feature>" to clipboard
  // ----------------------------------------------------------------
  document.querySelectorAll(".cat-trace-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var feature = btn.dataset.feature || "";
      var cmd = '/e2egraph flow "' + feature.replace(/\\\\/g, "\\\\\\\\").replace(/"/g, '\\\\"') + '"';
      copyToClipboard(cmd, btn);
    });
  });

  // ----------------------------------------------------------------
  // Batch select: checkboxes + "Copiar seleccion (N)" button
  // ----------------------------------------------------------------
  var batchBar = document.getElementById("batch-copy-bar");
  var batchBtn = document.getElementById("batch-copy-btn");
  var allCbs = Array.from(document.querySelectorAll(".cat-select-cb"));

  function updateBatchBar() {
    var checked = allCbs.filter(function(cb) { return cb.checked; });
    var n = checked.length;
    if (batchBar) batchBar.style.display = n > 0 ? "flex" : "none";
    if (batchBtn) batchBtn.textContent = "Copiar selección (" + n + ")";
    if (batchBtn) batchBtn.disabled = n === 0;
  }

  allCbs.forEach(function(cb) {
    cb.addEventListener("change", updateBatchBar);
  });

  if (batchBtn) {
    batchBtn.addEventListener("click", function() {
      var checked = allCbs.filter(function(cb) { return cb.checked; });
      var lines = checked.map(function(cb) {
        var feature = cb.dataset.feature || "";
        return '/e2egraph flow "' + feature.replace(/\\\\/g, "\\\\\\\\").replace(/"/g, '\\\\"') + '"';
      });
      copyToClipboard(lines.join("\\n"), batchBtn);
    });
  }

  // Catalog filtering
  var catRows = Array.from(document.querySelectorAll(".cat-row"));
  var catalogEmpty = document.getElementById("catalog-empty");

  function applyCatalogFilters() {
    var q = searchText.trim().toLowerCase();
    var visible = 0;
    catRows.forEach(function(row) {
      var repoMatch = activeRepo === "__all__" || row.dataset.repo === activeRepo;
      var searchMatch = !q || row.dataset.search.indexOf(q) !== -1;
      if (repoMatch && searchMatch) {
        row.classList.remove("hidden");
        visible++;
      } else {
        row.classList.add("hidden");
      }
    });
    if (catalogEmpty) {
      catalogEmpty.style.display = visible === 0 ? "block" : "none";
    }
  }
"""
        # Patch the applyFilters call to also call applyCatalogFilters
        # (done via the combined applyAllFilters function below)

    # Determine the combined filter call
    if catalog is not None:
        apply_all_js = """
  function applyAllFilters() {
    applyFilters();
    applyCatalogFilters();
  }
"""
        filter_call = "applyAllFilters"
    else:
        apply_all_js = ""
        filter_call = "applyFilters"

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
{catalog_css}
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
  {catalog_section_html}
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

  {catalog_js}
  {apply_all_js}

  // Sidebar
  document.querySelectorAll(".sidebar-link").forEach(function(link) {{
    link.addEventListener("click", function(e) {{
      e.preventDefault();
      document.querySelectorAll(".sidebar-link").forEach(function(l) {{ l.classList.remove("active"); }});
      link.classList.add("active");
      activeRepo = link.dataset.repo;
      {filter_call}();
    }});
  }});

  // Search
  document.getElementById("search-box").addEventListener("input", function(e) {{
    searchText = e.target.value;
    {filter_call}();
  }});
}})();
</script>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_content)
