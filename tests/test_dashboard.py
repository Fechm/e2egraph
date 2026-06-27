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

if __name__ == "__main__":
    unittest.main()
