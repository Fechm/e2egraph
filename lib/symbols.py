"""Symbol extraction: universal-ctags (JSON) with a regex fallback. Stdlib only."""
import json, re, shutil, subprocess

FALLBACK_RES = {
    "py": [re.compile(r"^\s*def\s+(\w+)", re.M), re.compile(r"^\s*class\s+(\w+)", re.M)],
    "ts": [re.compile(r"\bfunction\s+(\w+)"), re.compile(r"\bclass\s+(\w+)")],
    "js": [re.compile(r"\bfunction\s+(\w+)"), re.compile(r"\bclass\s+(\w+)")],
}

def ctags_available():
    return shutil.which("ctags") is not None

def extract_symbols_fallback(file_path, lang, text):
    out = []
    for rx in FALLBACK_RES.get(lang, []):
        for m in rx.finditer(text):
            out.append({"name": m.group(1), "file": file_path, "kind": "symbol"})
    return out

def extract_symbols_ctags(repo_path):
    """Run ctags over a repo, return list of {name,file,kind}. [] on any failure."""
    try:
        proc = subprocess.run(
            ["ctags", "--output-format=json", "-R", "--fields=+n", repo_path],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    syms = []
    for line in proc.stdout.splitlines():
        try:
            tag = json.loads(line)
        except ValueError:
            continue
        if tag.get("_type") == "tag" and tag.get("name"):
            syms.append({"name": tag["name"],
                         "file": (tag.get("path") or "").replace("\\", "/"),
                         "kind": tag.get("kind", "symbol")})
    return syms
