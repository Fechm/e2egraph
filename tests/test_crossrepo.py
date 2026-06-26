import unittest
from lib.crossrepo import merge_graphs

class TestCrossRepo(unittest.TestCase):
    def test_shared_table_links_two_repos(self):
        g_a = {"repo": "svc-a", "nodes": [{"id": "svc-a", "type": "repo", "repo": "svc-a"}],
               "edges": [{"source": "svc-a:file:w.sql", "target": "public.users",
                          "type": "writes_table", "confidence": "EXTRACTED",
                          "evidence": "sql", "unresolved": True}]}
        g_b = {"repo": "svc-b", "nodes": [{"id": "svc-b", "type": "repo", "repo": "svc-b"}],
               "edges": [{"source": "svc-b:file:r.sql", "target": "public.users",
                          "type": "reads_table", "confidence": "EXTRACTED",
                          "evidence": "sql", "unresolved": True}]}
        merged = merge_graphs([g_a, g_b])
        table_nodes = [n for n in merged["nodes"] if n["type"] == "db_table"]
        self.assertTrue(any(n["label"] == "public.users" for n in table_nodes))
        repos_touching = {e["source"].split(":")[0] for e in merged["edges"]
                          if e["type"] in ("reads_table", "writes_table")}
        self.assertEqual(repos_touching, {"svc-a", "svc-b"})
        self.assertTrue(any(f["name"] for f in merged["flows"]))

if __name__ == "__main__":
    unittest.main()
