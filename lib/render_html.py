"""Render a self-contained Cytoscape.js HTML from a graph dict. Stdlib only."""
import json, os

_TYPE_COLOR = {
    "repo": "#2563eb", "module": "#7c3aed", "file": "#0891b2", "symbol": "#64748b",
    "env_var": "#16a34a", "service": "#db2777", "db_table": "#ea580c",
    "endpoint": "#ca8a04", "queue": "#9333ea", "bucket": "#0d9488",
}

def _vendor_js():
    path = os.path.join(os.path.dirname(__file__), "vendor", "cytoscape.min.js")
    with open(path, encoding="utf-8") as f:
        return f.read()

def render_html(graph, out_path):
    elements = []
    node_ids = {n["id"] for n in graph["nodes"]}
    for n in graph["nodes"]:
        elements.append({"data": {"id": n["id"], "label": n.get("label", n["id"]),
                                  "ntype": n.get("type", "file")}})
    for i, e in enumerate(graph["edges"]):
        if e["source"] in node_ids and e.get("target") in node_ids:
            elements.append({"data": {"id": f"e{i}", "source": e["source"],
                                      "target": e["target"], "etype": e["type"]}})
    data_json = json.dumps(elements)
    colors_json = json.dumps(_TYPE_COLOR)
    flows_json = json.dumps(graph.get("flows", []))
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>e2egraph</title>
<style>
  body{{margin:0;font-family:system-ui,sans-serif}}
  #cy{{position:absolute;top:0;bottom:0;left:0;right:280px}}
  #panel{{position:absolute;top:0;bottom:0;right:0;width:280px;overflow:auto;
          border-left:1px solid #e2e8f0;padding:12px;box-sizing:border-box}}
  .flow{{padding:6px;border-bottom:1px solid #eee;font-size:13px}}
</style></head><body>
<div id="cy"></div>
<div id="panel"><h3>E2E Flows</h3><div id="flows"></div></div>
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
</script></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
