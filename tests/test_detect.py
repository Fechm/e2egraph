import os, tempfile, unittest
from lib.detect import detect

class TestDetect(unittest.TestCase):
    def _make(self, root, path, content=""):
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

    def test_finds_repos_and_classifies_files(self):
        with tempfile.TemporaryDirectory() as root:
            self._make(root, "svc-a/package.json", "{}")
            self._make(root, "svc-a/src/index.ts", "export const x = 1")
            self._make(root, "svc-a/node_modules/dep/i.js", "junk")
            self._make(root, "svc-b/go.mod", "module b")
            self._make(root, "svc-b/main.go", "package main")
            result = detect(root)
            repos = {r["name"]: r for r in result["repos"]}
            self.assertIn("svc-a", repos)
            self.assertIn("svc-b", repos)
            files_a = [f["path"] for f in repos["svc-a"]["files"]]
            self.assertTrue(any(p.endswith("src/index.ts") for p in files_a))
            self.assertFalse(any("node_modules" in p for p in files_a))

if __name__ == "__main__":
    unittest.main()
