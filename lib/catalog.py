# -*- coding: utf-8 -*-
"""Deterministic feature catalog: scans repos and lists user-facing operations.

No LLM / no token cost — pure regex over source files. Stdlib only.

Public API
----------
extract_catalog(detect_result) -> list[feature_dict]
catalog_by_repo(features)      -> {repo: [feature_dict, ...]}
mark_traced(features, traced_slugs) -> list[feature_dict]  (annotated copy)

Feature dict schema
-------------------
{
  "name":       str,          # operation / resolver / endpoint name
  "kind":       str,          # query | mutation | subscription | resolver | endpoint
  "root_field": str | None,   # first selected field for GQL ops; None for others
  "repo":       str,
  "file":       str,          # relative path inside the repo
  "line":       int,          # 1-based line where the feature was found
  "role":       str,          # consumed | defined
}
"""

import os
import re

from lib.io_utils import read_text_safe

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

# Matches ANY template literal `...` (non-greedy, DOTALL). We deliberately do
# NOT anchor to a `gql`/`gpl`/alias tag, because real code uses tag typos
# (`gpl\``), codegen helpers, and untagged literals. Each literal is then
# checked for a GraphQL operation header before being treated as an operation.
_TEMPLATE_LITERAL_RE = re.compile(r"`(.*?)`", re.DOTALL)

# Operation header: query/mutation/subscription with OPTIONAL <Name> and OPTIONAL
# variable definitions, up to the opening brace of the selection set.
# Real-world GraphQL ops are frequently anonymous (no name after the keyword),
# e.g.  `mutation ($input: Foo!) { changeOrderEntity(...) { ... } }`.
_OP_HEADER_RE = re.compile(
    r"\b(query|mutation|subscription)\s*([A-Za-z_]\w*)?\s*(?:\([^)]*\))?\s*\{",
    re.IGNORECASE,
)

# Standalone .graphql/.gql operation header (same pattern, used directly on file text)
_GQL_FILE_OP_RE = _OP_HEADER_RE

# Root field: first real identifier token inside the selection set `{ ... }`.
# We scan token by token, skipping whitespace, and ignore the meta-field
# `__typename` (which is not the feature being traced).
_FIELD_TOKEN_RE = re.compile(r"[A-Za-z_]\w*")

# NestJS resolver decorators
# @Query(() => X)  |  @Mutation(() => X)  |  @ResolveField(() => X)
# Optional name option:  { name: 'fieldName' }
_RESOLVER_DECO_RE = re.compile(
    r"@(Query|Mutation|ResolveField)\s*\([^)]*\)",
    re.DOTALL,
)
_RESOLVER_NAME_OPT_RE = re.compile(r"""['"]?name['"]?\s*:\s*['"]([^'"]+)['"]""")

# Method name on the same or next non-empty line after the decorator
_METHOD_NAME_RE = re.compile(r"^\s*(?:async\s+)?([A-Za-z_]\w*)\s*\(", re.MULTILINE)

# NestJS HTTP decorators — reuse patterns from relations.py without importing it
# to keep catalog self-contained and avoid circular risk.
_CONTROLLER_RE = re.compile(r"@Controller\(\s*(?:['\"]([^'\"]*)['\"])?")
_HTTP_DECO_RE = re.compile(r"@(Get|Post|Put|Delete|Patch)\(\s*(?:['\"]([^'\"]*)['\"])?")

# Extra extensions scanned for GQL operations (not in detect.py's LANG_BY_EXT)
_GQL_EXTENSIONS = {".graphql", ".gql"}
_IGNORE_DIRS = {"node_modules", "dist", "build", ".git", "vendor", "target",
                "__pycache__", ".next", "coverage", "e2egraph-out"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_endpoint_path(p):
    """Lowercase, map :param and {param} and pure-digit segments to '*'."""
    segs = [s for s in p.strip("/").split("/") if s]
    out = []
    for s in segs:
        if (s.isdigit()
                or re.fullmatch(r":[A-Za-z0-9_]+", s)
                or re.fullmatch(r"\{[A-Za-z0-9_]+\}", s)):
            out.append("*")
        else:
            out.append(s.lower())
    return "/" + "/".join(out) if out else "/"


def _relative(full_path, repo_path):
    """Return the path of *full_path* relative to *repo_path*, with forward slashes."""
    # Normalise both to forward-slash strings
    full = full_path.replace("\\", "/")
    base = repo_path.rstrip("/") + "/"
    if full.startswith(base):
        return full[len(base):]
    return full  # fallback: return as-is


def _line_of_offset(text, offset):
    """Return the 1-based line number for a character *offset* in *text*."""
    return text[:offset].count("\n") + 1


def _extract_root_field(body_after_brace):
    """Extract the first real field in *body_after_brace* (text after the opening '{').

    Skips the meta-field ``__typename`` so the captured root field reflects the
    actual feature being traced.
    """
    for m in _FIELD_TOKEN_RE.finditer(body_after_brace):
        token = m.group(0)
        if token == "__typename":
            continue
        return token
    return None


def _looks_like_gql(literal):
    """Heuristic: True if a template literal looks like a GraphQL operation.

    Requires a query/mutation/subscription header followed (eventually) by an
    opening brace, found near the START of the literal. This keeps CSS,
    interpolated message strings, SQL, etc. out while remaining tag-agnostic.
    """
    head = literal.lstrip()[:200]
    return _OP_HEADER_RE.search(head) is not None


def _extract_gql_operations(text, rel_path, repo_name):
    """Yield feature dicts for GQL operations found in *text*.

    Tag-agnostic: in .ts/.tsx/.js/.jsx files it scans every template literal
    (regardless of tag — ``gql``, the ``gpl`` typo, codegen aliases, or no tag)
    and keeps those containing a GraphQL operation header. In .graphql/.gql
    files it scans the whole text.
    """
    ext = os.path.splitext(rel_path)[1].lower()
    is_gql_file = ext in _GQL_EXTENSIONS
    is_ts_js = ext in {".ts", ".tsx", ".js", ".jsx"}

    if not (is_gql_file or is_ts_js):
        return

    # Collect (chunk_text, base_offset_in_file) pairs to search. We are
    # tag-agnostic: instead of anchoring to a `gql`/`gpl`/alias tag, we scan
    # every template literal and keep only those that actually contain a
    # GraphQL operation header near the start (avoids CSS/string false
    # positives while tolerating tag typos and untagged literals).
    chunks = []
    if is_gql_file:
        chunks.append((text, 0))
    else:  # ts/js — scan every backtick template literal
        for m in _TEMPLATE_LITERAL_RE.finditer(text):
            literal = m.group(1)
            if not _looks_like_gql(literal):
                continue
            # m.start(1) is the offset just after the opening backtick
            chunks.append((literal, m.start(1)))

    for chunk, base_offset in chunks:
        for op_m in _OP_HEADER_RE.finditer(chunk):
            kind = op_m.group(1).lower()
            op_name = op_m.group(2)  # None when the operation is anonymous

            # Absolute offset of the operation keyword in the original file
            abs_offset = base_offset + op_m.start()
            line = _line_of_offset(text, abs_offset)

            # Root field: text after the `{` that opens the selection set
            after_brace = chunk[op_m.end():]
            root_field = _extract_root_field(after_brace)

            # The display name is the operation name when present; anonymous
            # operations fall back to their root field (the actual feature).
            name = op_name or root_field
            if not name:
                # Neither a name nor a discernible root field: not useful.
                continue

            yield {
                "name": name,
                "kind": kind,
                "root_field": root_field,
                "repo": repo_name,
                "file": rel_path,
                "line": line,
                "role": "consumed",
            }


def _extract_resolvers(text, rel_path, repo_name):
    """Yield feature dicts for NestJS @Query/@Mutation/@ResolveField decorators."""
    lines = text.splitlines()
    # We iterate line by line to track the decorator line number precisely.
    i = 0
    while i < len(lines):
        line_text = lines[i]
        deco_m = _RESOLVER_DECO_RE.search(line_text)
        if deco_m:
            deco_type = deco_m.group(1)  # Query | Mutation | ResolveField
            kind = "resolver" if deco_type == "ResolveField" else deco_type.lower()

            # Try to find name: 'x' inside the decorator argument
            # (may span multiple lines — look ahead a few lines)
            deco_body = line_text
            lookahead = 1
            while "@" not in deco_body[deco_m.start() + 1:] and lookahead <= 4:
                if i + lookahead < len(lines):
                    deco_body += "\n" + lines[i + lookahead]
                lookahead += 1

            name_opt = _RESOLVER_NAME_OPT_RE.search(deco_body)
            if name_opt:
                field_name = name_opt.group(1)
                line_no = i + 1  # decorator line (1-based)
            else:
                # Fall back to the method name on the same or next code line
                rest = "\n".join(lines[i:i + 5])
                # Skip the decorator itself to find the method signature
                method_search = rest[deco_m.end():]
                mm = _METHOD_NAME_RE.search(method_search)
                if mm:
                    field_name = mm.group(1)
                    # Method line number
                    method_offset = deco_m.end() + mm.start()
                    line_no = i + 1 + rest[:method_offset + deco_m.end()].count("\n")
                else:
                    i += 1
                    continue

            yield {
                "name": field_name,
                "kind": kind,
                "root_field": None,
                "repo": repo_name,
                "file": rel_path,
                "line": line_no,
                "role": "defined",
            }
        i += 1


def _extract_endpoints(text, rel_path, repo_name):
    """Yield feature dicts for NestJS REST endpoints (@Controller + @Get/Post/...)."""
    prefix = ""
    lines = text.splitlines()
    for i, line_text in enumerate(lines):
        mc = _CONTROLLER_RE.search(line_text)
        if mc:
            prefix = (mc.group(1) or "").strip("/")
            continue
        mm = _HTTP_DECO_RE.search(line_text)
        if mm:
            sub = (mm.group(2) or "").strip("/")
            full = "/".join(s for s in [prefix, sub] if s)
            path = _normalize_endpoint_path(full)
            yield {
                "name": path,
                "kind": "endpoint",
                "root_field": None,
                "repo": repo_name,
                "file": rel_path,
                "line": i + 1,
                "role": "defined",
            }


def _scan_extra_gql_files(repo_path, repo_name):
    """Walk the repo directory and yield extra .graphql/.gql files not captured by detect."""
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in _GQL_EXTENSIONS:
                full = os.path.join(dirpath, fname).replace("\\", "/")
                rel = _relative(full, repo_path)
                text = read_text_safe(full)
                if text:
                    yield from _extract_gql_operations(text, rel, repo_name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_catalog(detect_result):
    """Scan repos from a detect() result and return a list of feature dicts.

    Parameters
    ----------
    detect_result : dict
        The dict returned by ``lib.detect.detect(root)``.

    Returns
    -------
    list[dict]
        Each dict has keys: name, kind, root_field, repo, file, line, role.
    """
    features = []
    for repo in detect_result.get("repos", []):
        repo_name = repo["name"]
        repo_path = repo["path"]

        # Track which .graphql/.gql files were already covered via detect files list
        seen_gql_files = set()

        for file_info in repo.get("files", []):
            full_path = file_info["path"]
            lang = file_info["lang"]
            ext = os.path.splitext(full_path)[1].lower()

            text = read_text_safe(full_path)
            if not text:
                continue

            rel = _relative(full_path, repo_path)

            # GQL operations consumed (ts/js/gql/graphql)
            if lang in ("ts", "js") or ext in _GQL_EXTENSIONS:
                features.extend(_extract_gql_operations(text, rel, repo_name))
                if ext in _GQL_EXTENSIONS:
                    seen_gql_files.add(full_path.replace("\\", "/"))

            # NestJS resolvers defined (ts only)
            if lang == "ts":
                features.extend(_extract_resolvers(text, rel, repo_name))
                features.extend(_extract_endpoints(text, rel, repo_name))

        # Also scan .graphql/.gql files that detect() doesn't index
        for feat in _scan_extra_gql_files(repo_path, repo_name):
            # Reconstruct the absolute path to check for duplicates
            abs_candidate = (repo_path.rstrip("/") + "/" + feat["file"])
            if abs_candidate not in seen_gql_files:
                features.append(feat)

    return features


def catalog_by_repo(features):
    """Group a list of features by repo name.

    Parameters
    ----------
    features : list[dict]

    Returns
    -------
    dict[str, list[dict]]
    """
    result = {}
    for feat in features:
        result.setdefault(feat["repo"], []).append(feat)
    return result


def mark_traced(features, traced_slugs):
    """Return a copy of *features* annotated with a ``traced`` boolean.

    A feature is considered traced if its ``name`` OR ``root_field`` matches
    any slug in *traced_slugs* (case-insensitive comparison).

    Parameters
    ----------
    features : list[dict]
    traced_slugs : set[str]
        Lower-case slugs to match against.

    Returns
    -------
    list[dict]
        New list; original dicts are not mutated.
    """
    lower_slugs = {s.lower() for s in traced_slugs}
    result = []
    for feat in features:
        name_lower = feat.get("name", "").lower()
        rf_lower = (feat.get("root_field") or "").lower()
        traced = name_lower in lower_slugs or (rf_lower and rf_lower in lower_slugs)
        result.append({**feat, "traced": traced})
    return result
