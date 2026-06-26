import unittest
from lib.build import build_repo_graph

class TestBuild(unittest.TestCase):
    def test_layers_and_nodes(self):
        repo = {"name": "svc-a", "path": "/r/svc-a",
                "files": [{"path": "/r/svc-a/src/index.ts", "lang": "ts"}]}
        relations = [{"source": "/r/svc-a/src/index.ts", "type": "uses_env",
                      "target_name": "USERS_API_URL", "confidence": "EXTRACTED",
                      "evidence": "env"}]
        g = build_repo_graph(repo, relations, symbols=[])
        types = {n["type"] for n in g["nodes"]}
        self.assertIn("repo", types)
        self.assertIn("module", types)
        self.assertIn("file", types)
        self.assertIn("env_var", types)
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("svc-a", ids)
        self.assertTrue(any(e["type"] == "uses_env" for e in g["edges"]))
        for n in g["nodes"]:
            self.assertEqual(n["repo"], "svc-a")

if __name__ == "__main__":
    unittest.main()
