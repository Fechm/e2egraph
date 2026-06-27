"""Render a functional flow chain as a self-contained interactive HTML file.

Stdlib only — no external dependencies or CDN references.
"""
import html
import json


# Layer colour palette
_LAYER_COLORS = {
    "frontend":         "#2563eb",
    "gateway_resolver": "#7c3aed",
    "grpc_client":      "#7c3aed",
    "proto":            "#64748b",
    "microservice":     "#0891b2",
    "data":             "#ea580c",
}
_UNKNOWN_COLOR = "#94a3b8"


def _esc(text):
    """HTML-escape a value that may be None or non-string."""
    if text is None:
        return ""
    return html.escape(str(text))


def _layer_color(layer):
    return _LAYER_COLORS.get(layer, _UNKNOWN_COLOR)


def render_flow_html(chain, out_path):
    """Write a self-contained interactive HTML file for *chain* to *out_path*.

    *chain* must have at minimum:
        {"feature": str, "steps": [{"id", "layer", "repo", "title"}, ...]}

    All other fields are optional; missing ones are silently omitted from the
    rendered output.
    """
    feature = chain.get("feature", "")
    summary = chain.get("summary", "")
    steps   = chain.get("steps", [])

    # Build a lookup map so we can resolve "next" titles in the detail panel
    step_by_id = {s["id"]: s for s in steps if "id" in s}

    # Serialise step data as JSON for inline JS — json.dumps escapes all
    # special chars, so injection is not possible.
    steps_json = json.dumps(steps, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    #  Left column: step boxes + connectors
    # ------------------------------------------------------------------ #
    def _file_label(step):
        f    = step.get("file", "")
        line = step.get("line")
        if not f:
            return ""
        return f"{f}:{line}" if line is not None else f

    step_boxes_html = []
    for idx, step in enumerate(steps):
        sid        = _esc(step.get("id", str(idx)))
        title      = _esc(step.get("title", "(untitled)"))
        repo       = _esc(step.get("repo", ""))
        layer      = step.get("layer", "")
        color      = _layer_color(layer)
        file_label = _esc(_file_label(step))
        layer_esc  = _esc(layer)

        subtitle = f"{repo} · {file_label}" if file_label else repo

        # Connector (mechanism label) between this box and the next
        connector_html = ""
        mechanism = step.get("mechanism")
        next_id   = step.get("next")
        if mechanism or next_id:
            mech_label = _esc(mechanism) if mechanism else ""
            connector_html = f"""
    <div class="connector">
      <div class="connector-line"></div>
      <div class="connector-label">{mech_label}</div>
      <div class="connector-arrow">&#9660;</div>
    </div>"""

        selected_class = ' selected' if idx == 0 else ''
        step_boxes_html.append(f"""
    <div class="step-box{selected_class}" data-step-index="{idx}" onclick="selectStep({idx})">
      <span class="layer-chip" style="background:{color};">{layer_esc}</span>
      <div class="step-title">{title}</div>
      <div class="step-subtitle">{_esc(subtitle)}</div>
    </div>{connector_html}""")

    steps_html = "\n".join(step_boxes_html)

    # ------------------------------------------------------------------ #
    #  Inline CSS
    # ------------------------------------------------------------------ #
    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f8fafc;
  color: #1e293b;
  min-height: 100vh;
}
.visually-hidden {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
header {
  background: #1e293b;
  color: #f8fafc;
  padding: 1.25rem 2rem;
  border-bottom: 3px solid #334155;
}
header h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: .02em; }
header p  { font-size: .9rem; color: #94a3b8; margin-top: .3rem; }
.layout {
  display: flex;
  gap: 0;
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.5rem;
  align-items: flex-start;
}
/* Left column */
.flow-column {
  flex: 0 0 340px;
  min-width: 220px;
}
.step-box {
  background: #fff;
  border: 2px solid #e2e8f0;
  border-radius: 10px;
  padding: .75rem 1rem;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
  position: relative;
}
.step-box:hover  { border-color: #94a3b8; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.step-box.selected { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.15); }
.layer-chip {
  display: inline-block;
  color: #fff;
  font-size: .68rem;
  font-weight: 600;
  padding: .15rem .5rem;
  border-radius: 999px;
  margin-bottom: .35rem;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.step-title   { font-size: .95rem; font-weight: 600; color: #0f172a; }
.step-subtitle { font-size: .75rem; color: #64748b; margin-top: .2rem; word-break: break-all; }
/* Connector */
.connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: .25rem 0;
}
.connector-line  { width: 2px; height: 14px; background: #cbd5e1; }
.connector-arrow { color: #94a3b8; font-size: .85rem; line-height: 1; }
.connector-label {
  font-size: .7rem;
  color: #64748b;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: .15rem .5rem;
  max-width: 240px;
  text-align: center;
  margin: .15rem 0;
  word-break: break-word;
}
/* Right panel */
.detail-panel {
  flex: 1;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 1.5rem;
  margin-left: 1.5rem;
  min-height: 300px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.detail-panel h2 { font-size: 1.1rem; font-weight: 700; color: #0f172a; margin-bottom: 1rem; }
.detail-row { margin-bottom: .75rem; }
.detail-label {
  font-size: .72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: #64748b; margin-bottom: .2rem;
}
.detail-value { font-size: .88rem; color: #1e293b; word-break: break-word; }
.detail-value.mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: .82rem; color: #0f172a; background: #f1f5f9;
  padding: .2rem .45rem; border-radius: 5px;
}
.participants-list { list-style: none; padding: 0; }
.participants-list li {
  font-size: .82rem; color: #1e293b;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 5px; padding: .2rem .5rem; margin-bottom: .3rem;
  word-break: break-all;
}
.next-hop {
  display: flex; align-items: center; gap: .5rem;
  background: #f0f9ff; border: 1px solid #bae6fd;
  border-radius: 8px; padding: .5rem .75rem; margin-top: .25rem;
}
.next-hop-arrow { font-size: 1rem; color: #0284c7; }
.next-hop-label { font-size: .82rem; color: #0369a1; font-weight: 600; }
"""

    # ------------------------------------------------------------------ #
    #  Inline JS
    # ------------------------------------------------------------------ #
    js = f"""
var STEPS = {steps_json};

function escHtml(s) {{
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}}

var LAYER_COLORS = {json.dumps(_LAYER_COLORS)};
var UNKNOWN_COLOR = {json.dumps(_UNKNOWN_COLOR)};

function layerColor(layer) {{
  return LAYER_COLORS[layer] || UNKNOWN_COLOR;
}}

function selectStep(idx) {{
  // Update selected box
  var boxes = document.querySelectorAll('.step-box');
  boxes.forEach(function(b) {{ b.classList.remove('selected'); }});
  boxes[idx].classList.add('selected');

  var step = STEPS[idx];
  var panel = document.getElementById('detail-panel');

  function row(label, value, cls) {{
    if (value == null || value === '') return '';
    var valHtml = cls ? '<span class="detail-value ' + cls + '">' + escHtml(value) + '</span>'
                      : '<div class="detail-value">' + escHtml(value) + '</div>';
    return '<div class="detail-row"><div class="detail-label">' + escHtml(label) + '</div>' + valHtml + '</div>';
  }}

  var html = '<h2>' + escHtml(step.title || '(sin título)') + '</h2>';
  html += row('Capa (Layer)', step.layer);
  html += row('Repositorio', step.repo);

  // File:line
  if (step.file) {{
    var fileLoc = step.line != null ? step.file + ':' + step.line : step.file;
    html += row('Archivo', fileLoc, 'mono');
  }}

  html += row('Mecanismo (→ siguiente)', step.mechanism);
  html += row('Descripción', step.detail);
  html += row('Usado en', step.used_in);

  // Participants
  if (step.participants && step.participants.length > 0) {{
    html += '<div class="detail-row"><div class="detail-label">Participantes</div>';
    html += '<ul class="participants-list">';
    step.participants.forEach(function(p) {{
      html += '<li>' + escHtml(p) + '</li>';
    }});
    html += '</ul></div>';
  }}

  // Next hop
  if (step.next) {{
    var nextStep = STEPS.find(function(s) {{ return s.id === step.next; }});
    if (nextStep) {{
      var chipColor = layerColor(nextStep.layer || '');
      html += '<div class="detail-row"><div class="detail-label">Siguiente paso</div>';
      html += '<div class="next-hop">';
      html += '<span class="next-hop-arrow">&#8594;</span>';
      html += '<span class="layer-chip" style="background:' + escHtml(chipColor) + ';">' + escHtml(nextStep.layer || '') + '</span>';
      html += '<span class="next-hop-label">' + escHtml(nextStep.repo) + ' / ' + escHtml(nextStep.title) + '</span>';
      html += '</div></div>';
    }}
  }}

  panel.innerHTML = html;
}}

// Auto-select first step on load
document.addEventListener('DOMContentLoaded', function() {{
  if (STEPS.length > 0) selectStep(0);
}});
"""

    # ------------------------------------------------------------------ #
    #  Assemble full HTML
    # ------------------------------------------------------------------ #
    feature_esc = _esc(feature)
    summary_esc = _esc(summary)

    document = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flow: {feature_esc}</title>
<style>{css}</style>
</head>
<body>
<span class="visually-hidden">
  Flujo funcional end-to-end: {feature_esc}. {summary_esc}
  Contiene {len(steps)} pasos interactivos. Haz clic en cada paso para ver el detalle.
</span>
<header>
  <h1>{feature_esc}</h1>
  {"<p>" + summary_esc + "</p>" if summary_esc else ""}
</header>
<div class="layout">
  <div class="flow-column">
{steps_html}
  </div>
  <div class="detail-panel" id="detail-panel">
    <p style="color:#94a3b8;">Selecciona un paso para ver el detalle.</p>
  </div>
</div>
<script>{js}</script>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(document)
