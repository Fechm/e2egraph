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
        table_flows = [f for f in merged["flows"]
                       if f["name"] == "Shared table: public.users"]
        self.assertEqual(len(table_flows), 1)
        self.assertEqual(table_flows[0]["path"], ["svc-a", "svc-b"])

    def test_shared_proto_links_two_repos(self):
        g_x = {"repo": "svc-x", "nodes": [{"id": "svc-x", "type": "repo", "repo": "svc-x"}],
               "edges": [{"source": "svc-x:file:a.proto", "target": "user.proto",
                          "type": "shares_proto", "confidence": "EXTRACTED",
                          "evidence": "proto", "unresolved": True}]}
        g_y = {"repo": "svc-y", "nodes": [{"id": "svc-y", "type": "repo", "repo": "svc-y"}],
               "edges": [{"source": "svc-y:file:b.proto", "target": "user.proto",
                          "type": "shares_proto", "confidence": "EXTRACTED",
                          "evidence": "proto", "unresolved": True}]}
        merged = merge_graphs([g_x, g_y])
        service_nodes = [n for n in merged["nodes"]
                         if n["type"] == "service" and n["id"] == "proto:user.proto"]
        self.assertEqual(len(service_nodes), 1)
        proto_edges = [e for e in merged["edges"] if e["type"] == "shares_proto"]
        self.assertEqual(len(proto_edges), 2)
        for e in proto_edges:
            self.assertEqual(e["unresolved"], False)
            self.assertEqual(e["target"], "proto:user.proto")
        proto_flows = [f for f in merged["flows"]
                       if f["name"] == "Shared proto: user.proto"]
        self.assertEqual(len(proto_flows), 1)
        self.assertEqual(proto_flows[0]["path"], ["svc-x", "svc-y"])

    def test_single_repo_no_flow(self):
        g = {"repo": "svc-solo", "nodes": [{"id": "svc-solo", "type": "repo", "repo": "svc-solo"}],
             "edges": [{"source": "svc-solo:file:q.sql", "target": "orders",
                        "type": "reads_table", "confidence": "EXTRACTED",
                        "evidence": "sql", "unresolved": True}]}
        merged = merge_graphs([g])
        table_nodes = [n for n in merged["nodes"]
                       if n["type"] == "db_table" and n["id"] == "table:orders"]
        self.assertEqual(len(table_nodes), 1)
        self.assertEqual(merged["flows"], [])

if __name__ == "__main__":
    unittest.main()
