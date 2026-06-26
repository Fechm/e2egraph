"""Discover repos and source files under a root directory. Stdlib only."""
import os

IGNORE_DIRS = {"node_modules", "dist", "build", ".git", "vendor", "target",
               "__pycache__", ".next", "coverage", "e2egraph-out"}

REPO_MARKERS = {"package.json", "go.mod", "pom.xml", "Cargo.toml",
                "pyproject.toml", "requirements.txt", "build.gradle", ".git"}

LANG_BY_EXT = {
    ".ts": "ts", ".tsx": "ts", ".js": "js", ".jsx": "js",
    ".py": "py", ".go": "go", ".java": "java", ".rs": "rust",
    ".rb": "ruby", ".php": "php", ".cs": "csharp", ".proto": "proto",
    ".sql": "sql",
}

def _is_repo_root(path):
    try:
        entries = set(os.listdir(path))
    except OSError:
        return False
    return bool(entries & REPO_MARKERS)

def _list_files(repo_path):
    files = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            lang = LANG_BY_EXT.get(ext)
            if lang:
                full = os.path.join(dirpath, name)
                files.append({"path": full.replace("\\", "/"), "lang": lang})
    return files

def detect(root):
    """Return {'root', 'repos': [{'name','path','files':[{path,lang}]}]}."""
    root = os.path.abspath(root)
    repos = []
    if _is_repo_root(root):
        candidates = [root]
    else:
        candidates = [os.path.join(root, d) for d in sorted(os.listdir(root))
                      if os.path.isdir(os.path.join(root, d)) and d not in IGNORE_DIRS]
        candidates = [c for c in candidates if _is_repo_root(c)]
    for c in candidates:
        repos.append({
            "name": os.path.basename(c.rstrip("/\\")),
            "path": c.replace("\\", "/"),
            "files": _list_files(c),
        })
    return {"root": root.replace("\\", "/"), "repos": repos}
