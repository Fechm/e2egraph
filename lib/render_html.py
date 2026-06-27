"""Render a self-contained Cytoscape.js HTML from a graph dict. Stdlib only."""
import json, os

_TYPE_COLOR = {
    "repo": "#2563eb", "module": "#7c3aed", "file": "#0891b2", "symbol": "#64748b",
    "env_var": "#16a34a", "service": "#db2777", "db_table": "#ea580c",
    "endpoint": "#ca8a04", "queue": "#9333ea", "bucket": "#0d9488",
}

# Node types kept in collapsed view; low-level types (file, symbol, env_var, endpoint) are dropped.
_KEEP_TYPES = {"repo", "module", "service", "db_table", "queue", "bucket"}


def _vendor_js():
    path = os.path.join(os.path.dirname(__file__), "vendor", "cytoscape.min.js")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _collapse_graph(graph):
    """Return a new graph dict collapsed to repo/module/shared-resource nodes.

    Does NOT mutate the input graph.
    - Keeps only nodes whose type is in _KEEP_TYPES.
    - For each edge, replaces dropped endpoints with that node's owning repo id.
      Edges where the repo fallback is unknown, or where source == target after
      remapping, or that are duplicates of (source, target, type) are dropped.
    """
    nodes = graph["nodes"]
    edges = graph["edges"]

    # Build id->node map
    id_to_node = {n["id"]: n for n in nodes}

    # Kept node ids
    kept_ids = {n["id"] for n in nodes if n.get("type") in _KEEP_TYPES}

    # Kept nodes list (preserve order, no mutation)
    kept_nodes = [n for n in nodes if n["id"] in kept_ids]

    def resolve(node_id):
        """Return the kept node id to use for node_id, or None if unresolvable."""
        if node_id in kept_ids:
            return node_id
        node = id_to_node.get(node_id)
        if node is None:
            return None
        repo_id = node.get("repo")
        if repo_id and repo_id in kept_ids:
            return repo_id
        return None

    # Remap edges
    seen = set()
    kept_edges = []
    for e in edges:
        src = resolve(e.get("source", ""))
        tgt = resolve(e.get("target", ""))
        if src is None or tgt is None:
            continue
        if src == tgt:
            continue  # drop self-loops created by collapsing
        key = (src, tgt, e.get("type", "unknown"))
        if key in seen:
            continue
        seen.add(key)
        kept_edges.append({"source": src, "target": tgt, "type": e.get("type", "unknown")})

    return {"nodes": kept_nodes, "edges": kept_edges, "flows": list(graph.get("flows", []))}


def render_html(graph, out_path, max_nodes=5000):
    n_total = len(graph["nodes"])
    collapsed = n_total > max_nodes
    active_graph = _collapse_graph(graph) if collapsed else graph

    elements = []
    node_ids = {n["id"] for n in active_graph["nodes"]}
    for n in active_graph["nodes"]:
        elements.append({"data": {"id": n["id"], "label": n.get("label", n["id"]),
                                  "ntype": n.get("type", "file")}})
    for i, e in enumerate(active_graph["edges"]):
        if e["source"] in node_ids and e.get("target") in node_ids:
            edata = {"id": f"e{i}", "source": e["source"],
                     "target": e["target"], "etype": e.get("type", "unknown")}
            if "evidence" in e:
                edata["evidence"] = e["evidence"]
            elements.append({"data": edata})
    data_json = json.dumps(elements)
    colors_json = json.dumps(_TYPE_COLOR)
    flows_json = json.dumps(active_graph.get("flows", []))

    # Banner HTML — empty string when not collapsed so the layout is unaffected.
    if collapsed:
        banner_html = (
            f'<div id="banner" style="position:absolute;top:0;left:0;right:280px;z-index:10;'
            f'background:#fbbf24;color:#1e1b4b;padding:8px 14px;font-size:13px;'
            f'font-weight:600;font-family:system-ui,sans-serif;">'
            f'Vista colapsada: {n_total} nodos (umbral {max_nodes}) — mostrando repos, '
            f'módulos y recursos compartidos. '
            f'Genera el grafo completo por repo para ver archivos y símbolos.'
            f'</div>'
        )
        # Push #cy down to leave room for the banner (~38px)
        cy_top = "38px"
    else:
        banner_html = ""
        cy_top = "0"

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>e2egraph</title>
<style>
  body{{margin:0;font-family:system-ui,sans-serif}}
  #cy{{position:absolute;top:{cy_top};bottom:0;left:0;right:280px}}
  #panel{{position:absolute;top:0;bottom:0;right:0;width:280px;overflow:auto;
          border-left:1px solid #e2e8f0;padding:12px;box-sizing:border-box}}
  .flow{{padding:6px;border-bottom:1px solid #eee;font-size:13px}}
  #detail{{margin-top:14px;padding:10px;background:#f8fafc;border:1px solid #e2e8f0;
           border-radius:6px;font-size:12px;display:none}}
  #detail h4{{margin:0 0 6px;font-size:13px;color:#1e293b}}
  #detail p{{margin:4px 0;color:#475569}}
  #detail .dl{{margin-top:8px}}
  #detail .dl strong{{color:#1e293b}}
</style></head><body>
{banner_html}<div id="cy"></div>
<div id="panel"><h3>E2E Flows</h3><div id="flows"></div><div id="detail"></div></div>
<script>{_vendor_js()}</script>
<script>
  var COLORS={colors_json};
  var FLOWS={flows_json};
  var cy=cytoscape({{
    container:document.getElementById('cy'),
    elements:{data_json},
    style:[
      {{selector:'node',style:{{'label':'data(label)','font-size':9,'width':18,'height':18,
        'background-color':function(e){{return COLORS[e.data('ntype')]||'#94a3b8';}}}}}},
      {{selector:'edge',style:{{'width':1,'line-color':'#cbd5e1','target-arrow-shape':'triangle',
        'target-arrow-color':'#cbd5e1','curve-style':'bezier'}}}}
    ],
    layout:{{name:'cose',animate:false}}
  }});
  var fc=document.getElementById('flows');
  FLOWS.forEach(function(f){{var d=document.createElement('div');d.className='flow';
    d.textContent=f.name;fc.appendChild(d);}});
  var detail=document.getElementById('detail');
  function showDetail(html){{detail.innerHTML=html;detail.style.display='block';}}
  cy.on('tap','node',function(evt){{
    var n=evt.target;
    var id=n.data('id'),lbl=n.data('label'),ntype=n.data('ntype');
    var outEdges=cy.edges('[source="'+id+'"]');
    var inEdges=cy.edges('[target="'+id+'"]');
    var outList=outEdges.map(function(e){{return cy.getElementById(e.data('target')).data('label')||e.data('target');}});
    var inList=inEdges.map(function(e){{return cy.getElementById(e.data('source')).data('label')||e.data('source');}});
    var html='<h4>'+lbl+'</h4><p><strong>Tipo:</strong> '+ntype+'</p>';
    html+='<div class="dl"><strong>Llama a:</strong><br>'+(outList.length?outList.join(', '):'—')+'</div>';
    html+='<div class="dl"><strong>Llamado por:</strong><br>'+(inList.length?inList.join(', '):'—')+'</div>';
    showDetail(html);
  }});
  cy.on('tap','edge',function(evt){{
    var e=evt.target;
    var src=cy.getElementById(e.data('source')).data('label')||e.data('source');
    var tgt=cy.getElementById(e.data('target')).data('label')||e.data('target');
    var etype=e.data('etype');
    var evidence=e.data('evidence')||'';
    var html='<h4>'+src+' → '+tgt+'</h4><p><strong>Tipo:</strong> '+etype+'</p>';
    if(evidence){{html+='<p><strong>Evidencia:</strong> '+evidence+'</p>';}}
    showDetail(html);
  }});
  cy.on('tap',function(evt){{if(evt.target===cy){{detail.style.display='none';}}}})
</script></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
