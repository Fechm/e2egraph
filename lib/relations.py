# -*- coding: utf-8 -*-
"""Extract structural edges from one file's source text. Stdlib only."""
import re
from lib.secrets_filter import classify_env, mask_name

IMPORT_RES = {
    "ts": [re.compile(r"""import\s+[^;]*?from\s+['"]([^'"]+)['"]"""),
           re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")],
    "js": [re.compile(r"""import\s+[^;]*?from\s+['"]([^'"]+)['"]"""),
           re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")],
    "py": [re.compile(r"""^\s*from\s+([.\w]+)\s+import""", re.M),
           re.compile(r"""^\s*import\s+([.\w]+)""", re.M)],
}
ENV_RES = [
    re.compile(r"process\.env\.([A-Z0-9_]+)"),
    re.compile(r"""process\.env\[['"]([A-Z0-9_]+)['"]\]"""),
    re.compile(r"""os\.environ(?:\.get)?\[?\(?['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"import\.meta\.env\.([A-Z0-9_]+)"),
]
CONFIG_RES = [
    re.compile(r"""(?:configService|config)\.get\(\s*['"]([A-Z][A-Z0-9_]+)['"]"""),
    re.compile(r"""this\.config(?:Service)?\.get\(\s*['"]([A-Z][A-Z0-9_]+)['"]"""),
]
DRIZZLE_RES = [
    re.compile(r"""pgTable\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""pgSchema\(\s*['"]([^'"]+)['"]"""),
]
API_RES = [
    re.compile(r"""axios\.(?:get|post|put|delete|patch)\(\s*[`'"]([^`'"]+)"""),
    re.compile(r"""fetch\(\s*[`'"]([^`'"]+)"""),
]
SQL_READ_RE = re.compile(r"\bFROM\s+([a-zA-Z_][\w.]*)", re.I)
SQL_WRITE_RE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE)\s+([a-zA-Z_][\w.]*)", re.I)

def _edge(src, etype, target_name, confidence, evidence):
    return {"source": src, "type": etype, "target_name": target_name,
            "confidence": confidence, "evidence": evidence}

def extract_relations(file_path, lang, text):
    edges = []
    for rx in IMPORT_RES.get(lang, []):
        for m in rx.finditer(text):
            edges.append(_edge(file_path, "imports", m.group(1), "EXTRACTED",
                               f"import '{m.group(1)}'"))
    seen_env = set()
    for rx in ENV_RES:
        for m in rx.finditer(text):
            raw = m.group(1)
            kind = classify_env(raw)
            name = mask_name(raw) if kind == "secret" else raw
            if name not in seen_env:
                seen_env.add(name)
                edges.append(_edge(file_path, "uses_env", name, "EXTRACTED",
                                   "env reference"))
    for rx in CONFIG_RES:
        for m in rx.finditer(text):
            raw = m.group(1)
            kind = classify_env(raw)
            name = mask_name(raw) if kind == "secret" else raw
            if name not in seen_env:
                seen_env.add(name)
                edges.append(_edge(file_path, "uses_env", name, "EXTRACTED",
                                   "config reference"))
    for rx in API_RES:
        for m in rx.finditer(text):
            edges.append(_edge(file_path, "calls_api", m.group(1), "INFERRED",
                               f"http call {m.group(1)}"))
    if lang == "sql":
        for m in SQL_READ_RE.finditer(text):
            edges.append(_edge(file_path, "reads_table", m.group(1), "EXTRACTED", "SQL FROM"))
        for m in SQL_WRITE_RE.finditer(text):
            edges.append(_edge(file_path, "writes_table", m.group(1), "EXTRACTED", "SQL write"))
    if lang in ("ts", "js"):
        for rx in DRIZZLE_RES:
            for m in rx.finditer(text):
                edges.append(_edge(file_path, "declares_table", m.group(1), "EXTRACTED",
                                   "drizzle table"))
    if lang == "proto":
        for m in re.finditer(r"service\s+(\w+)", text):
            edges.append(_edge(file_path, "shares_proto", m.group(1), "EXTRACTED", "proto service"))
    return edges
