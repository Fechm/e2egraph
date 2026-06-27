import unittest
from lib.overview import to_overview

class TestOverview(unittest.TestCase):
    def test_drops_folders_keeps_flows(self):
        g = {"nodes": [
            {"id": "a", "type": "repo", "repo": "a", "label": "a"},
            {"id": "a:mod:src", "type": "module", "repo": "a", "label": "src"},
            {"id": "a:file:x.ts", "type": "file", "repo": "a", "label": "x.ts"},
            {"id": "b", "type": "repo", "repo": "b", "label": "b"},
            {"id": "table:public.users", "type": "db_table", "repo": None, "label": "public.users"}],
            "edges": [
            {"source": "a", "target": "a:mod:src", "type": "contains"},
            {"source": "a:mod:src", "target": "a:file:x.ts", "type": "contains"},
            {"source": "a", "target": "b", "type": "calls_service", "evidence": "env var B_API_URL"},
            {"source": "a:file:x.ts", "target": "table:public.users", "type": "reads_table",
             "evidence": "SQL FROM"}],
            "flows": []}
        ov = to_overview(g)
        types = {n["type"] for n in ov["nodes"]}
        self.assertNotIn("module", types)
        self.assertNotIn("file", types)
        self.assertIn("repo", types)
        self.assertIn("db_table", types)
        etypes = {e["type"] for e in ov["edges"]}
        self.assertNotIn("contains", etypes)
        self.assertIn("calls_service", etypes)
        # reads_table edge re-mapped from file 'a:file:x.ts' to repo 'a'
        self.assertTrue(any(e["type"] == "reads_table" and e["source"] == "a"
                            and e["target"] == "table:public.users" for e in ov["edges"]))

    def test_drops_self_loops_and_dupes(self):
        g = {"nodes": [{"id": "a", "type": "repo", "repo": "a", "label": "a"}],
             "edges": [
                {"source": "a:file:x", "target": "a:file:y", "type": "imports"},  # dropped (not flow)
                {"source": "a:file:x", "target": "a", "type": "calls_service"}],   # self-loop after remap
             "flows": []}
        ov = to_overview(g)
        self.assertEqual(ov["edges"], [])  # import dropped; self-loop dropped

    def test_keeps_all_resource_types(self):
        g = {"nodes": [
            {"id": "r", "type": "repo", "repo": "r", "label": "r"},
            {"id": "svc1", "type": "service", "repo": None, "label": "svc1"},
            {"id": "tbl1", "type": "db_table", "repo": None, "label": "tbl1"},
            {"id": "q1", "type": "queue", "repo": None, "label": "q1"},
            {"id": "b1", "type": "bucket", "repo": None, "label": "b1"},
            {"id": "ev1", "type": "env_var", "repo": "r", "label": "MY_VAR"},
            {"id": "sym1", "type": "symbol", "repo": "r", "label": "fn"},
        ], "edges": [], "flows": []}
        ov = to_overview(g)
        types = {n["type"] for n in ov["nodes"]}
        self.assertIn("repo", types)
        self.assertIn("service", types)
        self.assertIn("db_table", types)
        self.assertIn("queue", types)
        self.assertIn("bucket", types)
        self.assertNotIn("env_var", types)
        self.assertNotIn("symbol", types)

    def test_flows_pass_through(self):
        flows = [{"name": "User login", "steps": ["a", "b"]}]
        g = {"nodes": [{"id": "a", "type": "repo", "repo": "a", "label": "a"}],
             "edges": [], "flows": flows}
        ov = to_overview(g)
        self.assertEqual(ov["flows"], flows)

    def test_deduplicates_edges(self):
        g = {"nodes": [
            {"id": "a", "type": "repo", "repo": "a", "label": "a"},
            {"id": "b", "type": "repo", "repo": "b", "label": "b"},
            {"id": "a:file:1", "type": "file", "repo": "a", "label": "f1.ts"},
            {"id": "a:file:2", "type": "file", "repo": "a", "label": "f2.ts"},
        ], "edges": [
            {"source": "a:file:1", "target": "b", "type": "calls_service"},
            {"source": "a:file:2", "target": "b", "type": "calls_service"},
        ], "flows": []}
        ov = to_overview(g)
        # Both remap to a->b calls_service, should dedup to 1
        matching = [e for e in ov["edges"]
                    if e["source"] == "a" and e["target"] == "b" and e["type"] == "calls_service"]
        self.assertEqual(len(matching), 1)

    def test_keeps_flow_edge_types(self):
        g = {"nodes": [
            {"id": "a", "type": "repo", "repo": "a", "label": "a"},
            {"id": "b", "type": "repo", "repo": "b", "label": "b"},
            {"id": "tbl", "type": "db_table", "repo": None, "label": "tbl"},
        ], "edges": [
            {"source": "a", "target": "b", "type": "calls_endpoint"},
            {"source": "a", "target": "b", "type": "calls_gql_op"},
            {"source": "a", "target": "tbl", "type": "reads_table"},
            {"source": "a", "target": "tbl", "type": "writes_table"},
            {"source": "a", "target": "b", "type": "shares_proto"},
            {"source": "a", "target": "b", "type": "depends_pkg"},
            {"source": "a", "target": "b", "type": "uses_env"},   # dropped
            {"source": "a", "target": "b", "type": "imports"},    # dropped
        ], "flows": []}
        ov = to_overview(g)
        etypes = {e["type"] for e in ov["edges"]}
        self.assertIn("calls_endpoint", etypes)
        self.assertIn("calls_gql_op", etypes)
        self.assertIn("reads_table", etypes)
        self.assertIn("writes_table", etypes)
        self.assertIn("shares_proto", etypes)
        self.assertIn("depends_pkg", etypes)
        self.assertNotIn("uses_env", etypes)
        self.assertNotIn("imports", etypes)

if __name__ == "__main__":
    unittest.main()
