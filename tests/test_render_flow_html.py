import os, tempfile, unittest
from lib.render_flow_html import render_flow_html

CHAIN = {
    "feature": "saveRequestTne",
    "summary": "El estudiante guarda su solicitud TNE.",
    "steps": [
        {"id": "s1", "layer": "frontend", "repo": "webapp", "title": "TNEPage.saveRequest",
         "file": "src/components/pages/TNEPage/TNEPage.tsx", "line": 229,
         "mechanism": "GraphQL mutation saveRequestTne",
         "detail": "Se envía la mutation al backend.",
         "used_in": "Botón Guardar en /tne del front.",
         "participants": ["mutation saveRequestTne — src/graphql/mutations/saveRequestTne.ts:3"],
         "next": "s2"},
        {"id": "s2", "layer": "gateway_resolver", "repo": "gateway-api",
         "title": "TneResolver.saveRequestTne",
         "file": "src/modules/tne/resolver.ts", "line": 24,
         "mechanism": "gRPC client-streaming", "detail": "Delega en TneService.", "next": "s3"},
        {"id": "s3", "layer": "data", "repo": "tne-api", "title": "table public.request_tne",
         "file": "database/objects/models/requestTne.ts", "line": 194,
         "detail": "Persiste la solicitud."},
    ],
}

class TestRenderFlowHtml(unittest.TestCase):
    def test_renders_interactive_self_contained_chain(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "flow.html")
            render_flow_html(CHAIN, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("<html", html.lower())
        self.assertIn("saveRequestTne", html)                 # feature
        self.assertIn("TNEPage.saveRequest", html)            # step title
        self.assertIn("src/modules/tne/resolver.ts", html)    # a file path is present
        self.assertIn("Bot", html)                            # used_in text present (Botón…)
        self.assertIn("public.request_tne", html)             # data step
        self.assertIn("onclick", html.lower())                # clickable
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)                    # self-contained, no external refs

    def test_tolerates_missing_optional_fields(self):
        chain = {"feature": "x", "steps": [{"id": "a", "layer": "frontend", "repo": "r", "title": "t"}]}
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "f.html")
            render_flow_html(chain, out)  # must not raise
            self.assertTrue(os.path.exists(out))

    def test_security_badge_and_panel(self):
        chain = {"feature": "f", "steps": [
            {"id": "s1", "layer": "gateway_resolver", "repo": "gateway-api", "title": "Resolver",
             "file": "src/r.ts", "line": 10,
             "security": {"level": "risk",
                          "controls": ["JWT guard — r.ts:8"],
                          "flags": ["token en cookie sin httpOnly — auth.ts:45"],
                          "note": "Revisión heurística; no sustituye auditoría."}},
            {"id": "s2", "layer": "data", "repo": "x", "title": "tabla y"},  # no security
        ]}
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "f.html")
            from lib.render_flow_html import render_flow_html
            render_flow_html(chain, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("Seguridad", html)
        self.assertIn("riesgo", html.lower())                      # honest label for 'risk'
        self.assertIn("httpOnly", html)                            # the flag text + file:line
        self.assertIn("JWT guard", html)                           # the control
        self.assertNotIn("es seguro", html.lower())                # never claims "secure"
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_default_disclaimer_when_note_missing(self):
        chain = {"feature": "f", "steps": [
            {"id": "s1", "layer": "data", "repo": "x", "title": "t",
             "security": {"level": "ok", "controls": ["query parametrizada"]}}]}
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "f.html")
            from lib.render_flow_html import render_flow_html
            render_flow_html(chain, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("no sustituye", html.lower())  # default disclaimer present


if __name__ == "__main__":
    unittest.main()
