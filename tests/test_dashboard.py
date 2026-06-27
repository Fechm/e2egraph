import os, tempfile, unittest
from lib.dashboard import index_flows, render_dashboard_html

FRONT = {"feature": "Guardar solicitud TNE", "slug": "saveRequestTne",
         "entry": {"repo": "webapp", "kind": "frontend_action", "symbol": "TNEPage.saveRequest"},
         "summary": "El estudiante guarda su solicitud de TNE.",
         "steps": [
            {"id": "s1", "layer": "frontend", "repo": "webapp", "title": "TNEPage.saveRequest",
             "security": {"level": "review"}},
            {"id": "s2", "layer": "microservice", "repo": "umas-api",
             "title": "GET /teachers/active-courses", "security": {"level": "risk"}}]}
ENDPOINT = {"feature": "Cursos activos del docente", "slug": "umas-active-courses",
            "entry": {"repo": "umas-api", "kind": "endpoint", "symbol": "GET /teachers/active-courses"},
            "summary": "Lista los cursos activos de un docente.",
            "steps": [{"id": "e1", "layer": "microservice", "repo": "umas-api",
                       "title": "GET /teachers/active-courses", "security": {"level": "ok"}}]}

class TestDashboard(unittest.TestCase):
    def test_index_groups_by_entry_repo(self):
        idx = index_flows([FRONT, ENDPOINT])
        self.assertIn("webapp", idx["groups"])
        self.assertIn("umas-api", idx["groups"])
        self.assertIn("saveRequestTne", idx["groups"]["webapp"])

    def test_worst_security_and_repos(self):
        idx = index_flows([FRONT, ENDPOINT])
        front = next(f for f in idx["flows"] if f["slug"] == "saveRequestTne")
        self.assertEqual(front["worst_security"], "risk")
        self.assertEqual(front["repos"], ["webapp", "umas-api"])
        self.assertEqual(front["href"], "flows/saveRequestTne.html")

    def test_cross_link_detected(self):
        # FRONT's step s2 (umas-api, GET /teachers/active-courses) is the ENTRY of ENDPOINT
        idx = index_flows([FRONT, ENDPOINT])
        self.assertEqual(idx["cross_links"].get("saveRequestTne", {}).get("s2"), "umas-active-courses")

    def test_render_dashboard_self_contained(self):
        idx = index_flows([FRONT, ENDPOINT])
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "index.html")
            render_dashboard_html(idx, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("Guardar solicitud TNE", html)     # a card
        self.assertIn("webapp", html)                    # sidebar repo
        self.assertIn("umas-api", html)                  # sidebar repo
        self.assertIn("flows/saveRequestTne.html", html) # link
        self.assertIn("input", html.lower())             # search box
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_attach_catalog_marks_traced_and_groups(self):
        from lib.dashboard import index_flows, attach_catalog
        FRONT = {"feature": "Guardar TNE", "slug": "saveRequestTne",
                 "entry": {"repo": "webapp", "kind": "frontend_action", "symbol": "saveRequestTne"},
                 "steps": [{"id": "s1", "layer": "frontend", "repo": "webapp", "title": "x",
                            "security": {"level": "risk"}}]}
        idx = index_flows([FRONT])
        catalog = [
            {"name": "saveRequestTne", "kind": "mutation", "root_field": "saveRequestTne",
             "repo": "webapp", "file": "src/graphql/mutations/saveRequestTne.ts", "line": 2, "role": "consumed"},
            {"name": "confirmPayment", "kind": "mutation", "root_field": "confirmPayment",
             "repo": "webapp", "file": "src/graphql/mutations/confirmPayment.ts", "line": 4, "role": "consumed"},
        ]
        idx = attach_catalog(idx, catalog, {"saverequesttne"})
        web = idx["catalog"]["webapp"]
        saved = next(f for f in web if f["root_field"] == "saveRequestTne")
        pending = next(f for f in web if f["root_field"] == "confirmPayment")
        self.assertTrue(saved["traced"])
        self.assertEqual(saved["href"], "flows/saveRequestTne.html")
        self.assertFalse(pending["traced"])
        self.assertIsNone(pending["href"])

    def test_render_dashboard_with_catalog(self):
        from lib.dashboard import index_flows, attach_catalog, render_dashboard_html
        import tempfile, os
        FRONT = {"feature": "Guardar TNE", "slug": "saveRequestTne",
                 "entry": {"repo": "webapp", "kind": "frontend_action", "symbol": "saveRequestTne"},
                 "steps": [{"id": "s1", "layer": "frontend", "repo": "webapp", "title": "x",
                            "security": {"level": "risk"}}]}
        idx = index_flows([FRONT])
        idx = attach_catalog(idx, [
            {"name": "confirmPayment", "kind": "mutation", "root_field": "confirmPayment",
             "repo": "webapp", "file": "src/q.ts", "line": 4, "role": "consumed"}], {"saverequesttne"})
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "index.html")
            render_dashboard_html(idx, out)
            html = open(out, encoding="utf-8").read()
        self.assertIn("confirmPayment", html)              # pending catalog item
        self.assertIn("pendiente", html.lower())           # pending marker
        self.assertIn("flows/saveRequestTne.html", html)   # traced link
        self.assertIn("input", html.lower())               # search
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


    def test_pending_feature_has_trace_command(self):
        from lib.dashboard import index_flows, attach_catalog, render_dashboard_html
        import tempfile, os
        idx = index_flows([])  # no traced flows
        idx = attach_catalog(idx, [
            {"name": "confirmPayment", "kind": "mutation", "root_field": "confirmPayment",
             "repo": "webapp", "file": "src/q.ts", "line": 4, "role": "consumed"}], set())
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "index.html")
            render_dashboard_html(idx, out)
            html = open(out, encoding="utf-8").read()
        self.assertIn("Trazar", html)                          # the button
        self.assertIn("confirmPayment", html)                  # feature in the command
        self.assertIn("e2egraph flow", html)                   # command text/template
        self.assertTrue("clipboard" in html.lower() or "execcommand" in html.lower())  # copy mechanism
        self.assertIn("selecci", html.lower())                 # batch "Copiar selección"
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
