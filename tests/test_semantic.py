import unittest
from lib.semantic import gql_participants, merge_semantic

class TestSemantic(unittest.TestCase):
    def _graph(self):
        return {
            "nodes": [
                {"id": "web", "type": "repo", "repo": "web", "label": "web"},
                {"id": "backend", "type": "repo", "repo": "backend", "label": "backend"},
                {"id": "web:env:NEXT_PUBLIC_GRAPHQL_BACKEND_URL", "type": "env_var",
                 "repo": "web", "label": "NEXT_PUBLIC_GRAPHQL_BACKEND_URL"},
            ],
            "edges": [
                {"source": "backend:file:r.ts", "target": "getUsers",
                 "type": "defines_gql_op", "confidence": "EXTRACTED", "evidence": "@Query"},
            ],
            "flows": [{"name": "Service call: web → backend", "path": ["web", "backend"],
                       "description": "web calls backend via NEXT_PUBLIC_GRAPHQL_BACKEND_URL."}],
        }

    def test_gql_participants(self):
        consumers, providers = gql_participants(self._graph())
        self.assertIn("web", consumers)       # has *GRAPHQL* env var
        self.assertIn("backend", providers)   # has defines_gql_op edge

    def test_merge_adds_gql_edge_and_flow(self):
        g = self._graph()
        results = {"gql_links": [
            {"consumer": "web", "provider": "backend", "operation": "getUsers",
             "kind": "query", "description": "web fetches users from backend.",
             "evidence": "query GetUsers { getUsers }"}]}
        merge_semantic(g, results)
        self.assertTrue(any(e["type"] == "calls_gql_op" and e["source"] == "web"
                            and e["target"] == "backend" and e["confidence"] == "AMBIGUOUS"
                            for e in g["edges"]))
        self.assertTrue(any(f["name"] == "GraphQL: web → backend.getUsers" for f in g["flows"]))

    def test_merge_applies_flow_description(self):
        g = self._graph()
        merge_semantic(g, {"flow_descriptions":
                           {"Service call: web → backend": "Webapp talks to its GraphQL backend."}})
        f = next(f for f in g["flows"] if f["name"] == "Service call: web → backend")
        self.assertEqual(f["description"], "Webapp talks to its GraphQL backend.")

    def test_merge_handles_empty_and_self_links(self):
        g = self._graph()
        merge_semantic(g, None)  # must not raise
        merge_semantic(g, {"gql_links": [{"consumer": "web", "provider": "web",
                                          "operation": "x"}]})  # self-link skipped
        self.assertFalse(any(f["name"] == "GraphQL: web → web.x" for f in g["flows"]))

if __name__ == "__main__":
    unittest.main()
