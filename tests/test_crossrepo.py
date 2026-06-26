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

    def test_declares_table_links_repos(self):
        g_a = {"repo": "svc-a",
               "nodes": [{"id": "svc-a", "type": "repo", "repo": "svc-a", "label": "svc-a"}],
               "edges": [{"source": "svc-a:file:s.ts", "target": "users",
                          "type": "declares_table", "confidence": "EXTRACTED",
                          "evidence": "drizzle", "unresolved": True}]}
        g_b = {"repo": "svc-b",
               "nodes": [{"id": "svc-b", "type": "repo", "repo": "svc-b", "label": "svc-b"}],
               "edges": [{"source": "svc-b:file:q.sql", "target": "users",
                          "type": "reads_table", "confidence": "EXTRACTED",
                          "evidence": "sql", "unresolved": True}]}
        merged = merge_graphs([g_a, g_b])
        self.assertTrue(any(n["type"] == "db_table" and n["label"] == "users"
                            for n in merged["nodes"]))
        self.assertTrue(any("Shared table" in f["name"] for f in merged["flows"]))

    def test_service_env_links_to_repo(self):
        g_gw = {"repo": "gateway-api", "nodes": [
            {"id": "gateway-api", "type": "repo", "repo": "gateway-api", "label": "gateway-api"},
            {"id": "gateway-api:env:USERS_API_URL", "type": "env_var",
             "repo": "gateway-api", "label": "USERS_API_URL"}],
            "edges": []}
        g_users = {"repo": "users-api",
                   "nodes": [{"id": "users-api", "type": "repo", "repo": "users-api", "label": "users-api"}],
                   "edges": []}
        merged = merge_graphs([g_gw, g_users])
        self.assertTrue(any(e["type"] == "calls_service" and e["source"] == "gateway-api"
                            and e["target"] == "users-api" for e in merged["edges"]))
        self.assertTrue(any(f["name"] == "Service call: gateway-api → users-api"
                            for f in merged["flows"]))

    def test_generic_env_var_does_not_match(self):
        # A generic service var, and one whose meaningful token matches no repo, must NOT create a calls_service edge.
        g = {"repo": "svc-a", "nodes": [
            {"id": "svc-a", "type": "repo", "repo": "svc-a", "label": "svc-a"},
            {"id": "svc-a:env:REDIS_URL", "type": "env_var", "repo": "svc-a", "label": "REDIS_URL"},
            {"id": "svc-a:env:API_URL", "type": "env_var", "repo": "svc-a", "label": "API_URL"}],
            "edges": []}
        g2 = {"repo": "users-api",
              "nodes": [{"id": "users-api", "type": "repo", "repo": "users-api", "label": "users-api"}],
              "edges": []}
        merged = merge_graphs([g, g2])
        self.assertFalse(any(e["type"] == "calls_service" for e in merged["edges"]))

    def test_endpoint_call_links_repos(self):
        web = {"repo": "web", "nodes": [{"id": "web", "type": "repo", "repo": "web", "label": "web"}],
               "edges": [{"source": "web:file:a.ts", "target": "${base}/v1/users/42",
                          "type": "calls_api", "confidence": "INFERRED", "evidence": "fetch",
                          "unresolved": True}]}
        api = {"repo": "users-api",
               "nodes": [{"id": "users-api", "type": "repo", "repo": "users-api", "label": "users-api"}],
               "edges": [{"source": "users-api:file:c.ts", "target": "/v1/users/*",
                          "type": "defines_endpoint", "confidence": "EXTRACTED", "evidence": "GET /v1/users/*",
                          "unresolved": True}]}
        merged = merge_graphs([web, api])
        self.assertTrue(any(e["type"] == "calls_endpoint" and e["source"] == "web"
                            and e["target"] == "users-api" for e in merged["edges"]))
        self.assertTrue(any(f["name"].startswith("Endpoint:") for f in merged["flows"]))

    def test_address_env_links_to_repo(self):
        gw = {"repo": "gateway-api", "nodes": [
            {"id": "gateway-api", "type": "repo", "repo": "gateway-api", "label": "gateway-api"},
            {"id": "gateway-api:env:USERS_API_ADDRESS", "type": "env_var",
             "repo": "gateway-api", "label": "USERS_API_ADDRESS"}],
            "edges": []}
        users = {"repo": "users-api",
                 "nodes": [{"id": "users-api", "type": "repo", "repo": "users-api", "label": "users-api"}],
                 "edges": []}
        merged = merge_graphs([gw, users])
        self.assertTrue(any(e["type"] == "calls_service" and e["source"] == "gateway-api"
                            and e["target"] == "users-api" for e in merged["edges"]))

    def test_endpoint_no_match_no_edge(self):
        web = {"repo": "web", "nodes": [{"id": "web", "type": "repo", "repo": "web", "label": "web"}],
               "edges": [{"source": "web:file:a.ts", "target": "${base}/v1/orders",
                          "type": "calls_api", "confidence": "INFERRED", "evidence": "fetch",
                          "unresolved": True}]}
        api = {"repo": "users-api",
               "nodes": [{"id": "users-api", "type": "repo", "repo": "users-api", "label": "users-api"}],
               "edges": [{"source": "users-api:file:c.ts", "target": "/v1/users/*",
                          "type": "defines_endpoint", "confidence": "EXTRACTED", "evidence": "GET",
                          "unresolved": True}]}
        merged = merge_graphs([web, api])
        self.assertFalse(any(e["type"] == "calls_endpoint" for e in merged["edges"]))

    def test_exact_match_beats_superset_repo(self):
        # UMAS_API_HOST must resolve to umas-api, NOT umas-toku-due-sync-worker
        a = {"repo": "umas-api", "nodes": [
            {"id": "umas-api", "type": "repo", "repo": "umas-api", "label": "umas-api"}], "edges": []}
        w = {"repo": "umas-toku-due-sync-worker", "nodes": [
            {"id": "umas-toku-due-sync-worker", "type": "repo", "repo": "umas-toku-due-sync-worker",
             "label": "umas-toku-due-sync-worker"},
            {"id": "umas-toku-due-sync-worker:env:UMAS_API_HOST", "type": "env_var",
             "repo": "umas-toku-due-sync-worker", "label": "UMAS_API_HOST"}], "edges": []}
        merged = merge_graphs([a, w])
        cs = [e for e in merged["edges"] if e["type"] == "calls_service"]
        self.assertTrue(any(e["target"] == "umas-api" for e in cs))
        self.assertFalse(any(e["target"] == "umas-toku-due-sync-worker" for e in cs))

    def test_shared_word_backend_is_ambiguous(self):
        # NEXT_PUBLIC_GRAPHQL_BACKEND_URL must NOT resolve when two *-backend repos exist
        web = {"repo": "collaborator-portal-webapp", "nodes": [
            {"id": "collaborator-portal-webapp", "type": "repo", "repo": "collaborator-portal-webapp",
             "label": "collaborator-portal-webapp"},
            {"id": "collaborator-portal-webapp:env:NEXT_PUBLIC_GRAPHQL_BACKEND_URL", "type": "env_var",
             "repo": "collaborator-portal-webapp", "label": "NEXT_PUBLIC_GRAPHQL_BACKEND_URL"}], "edges": []}
        b1 = {"repo": "collaborator-portal-backend", "nodes": [
            {"id": "collaborator-portal-backend", "type": "repo", "repo": "collaborator-portal-backend",
             "label": "collaborator-portal-backend"}], "edges": []}
        b2 = {"repo": "online-payments-backend", "nodes": [
            {"id": "online-payments-backend", "type": "repo", "repo": "online-payments-backend",
             "label": "online-payments-backend"}], "edges": []}
        merged = merge_graphs([web, b1, b2])
        self.assertFalse(any(e["type"] == "calls_service" for e in merged["edges"]))

    def test_short_acronym_service_matches(self):
        # TNE_API_ADDRESS -> tne-api (the old len>=4 cutoff wrongly dropped this)
        gw = {"repo": "gateway-api", "nodes": [
            {"id": "gateway-api", "type": "repo", "repo": "gateway-api", "label": "gateway-api"},
            {"id": "gateway-api:env:TNE_API_ADDRESS", "type": "env_var",
             "repo": "gateway-api", "label": "TNE_API_ADDRESS"}], "edges": []}
        tne = {"repo": "tne-api", "nodes": [
            {"id": "tne-api", "type": "repo", "repo": "tne-api", "label": "tne-api"}], "edges": []}
        merged = merge_graphs([gw, tne])
        self.assertTrue(any(e["type"] == "calls_service" and e["source"] == "gateway-api"
                            and e["target"] == "tne-api" for e in merged["edges"]))

    def test_subset_unique_service_matches(self):
        # DOCUMENTS_API_ADDRESS -> services-documents-api (candidate {documents} subset, unique)
        gw = {"repo": "gateway-api", "nodes": [
            {"id": "gateway-api", "type": "repo", "repo": "gateway-api", "label": "gateway-api"},
            {"id": "gateway-api:env:DOCUMENTS_API_ADDRESS", "type": "env_var",
             "repo": "gateway-api", "label": "DOCUMENTS_API_ADDRESS"}], "edges": []}
        doc = {"repo": "services-documents-api", "nodes": [
            {"id": "services-documents-api", "type": "repo", "repo": "services-documents-api",
             "label": "services-documents-api"}], "edges": []}
        merged = merge_graphs([gw, doc])
        self.assertTrue(any(e["type"] == "calls_service" and e["target"] == "services-documents-api"
                            for e in merged["edges"]))

if __name__ == "__main__":
    unittest.main()
