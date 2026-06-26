import unittest
from lib.report import generate_report

class TestReport(unittest.TestCase):
    def test_report_lists_repos_and_flows(self):
        graph = {"nodes": [{"id": "svc-a", "type": "repo", "label": "svc-a"},
                            {"id": "svc-b", "type": "repo", "label": "svc-b"}],
                 "edges": [], "flows": [{"name": "Shared table: public.users",
                                          "path": ["svc-a", "svc-b"],
                                          "description": "svc-a, svc-b share table public.users."}]}
        md = generate_report(graph)
        self.assertIn("# e2egraph", md)
        self.assertIn("svc-a", md)
        self.assertIn("Shared table: public.users", md)
        self.assertIn("## E2E Flows", md)

if __name__ == "__main__":
    unittest.main()
