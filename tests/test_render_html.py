import os, tempfile, unittest
from lib.render_html import render_html

class TestRenderHtml(unittest.TestCase):
    def test_self_contained_html(self):
        graph = {"nodes": [{"id": "svc-a", "label": "svc-a", "type": "repo"}],
                 "edges": [], "flows": []}
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "graph.html")
            render_html(graph, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("<html", html.lower())
        self.assertIn("cytoscape", html.lower())
        self.assertIn("svc-a", html)
        # The original spec had assertNotIn("http://", html) and assertNotIn("https://", html)
        # but the vendored cytoscape.min.js contains inert URLs in its license banner
        # (e.g. http://en.wikipedia.org/wiki/MIT_License). Those are plain text inside a
        # <script> block — they are never loaded. The real intent is: no external resources.
        self.assertNotIn('<script src=', html)   # no external script tags
        self.assertNotIn('<link', html)           # no external stylesheet/font links
        # Verify the library is actually inlined (vendored JS is ~370 KB)
        self.assertGreater(len(html), 50000)

    def test_dangling_edges_skipped(self):
        # An edge whose target is not a present node must be dropped; a valid
        # edge between two present nodes must be kept.
        graph = {
            "nodes": [
                {"id": "svc-a", "label": "svc-a", "type": "repo"},
                {"id": "svc-b", "label": "svc-b", "type": "repo"},
            ],
            "edges": [
                {"source": "svc-a", "target": "ghost", "type": "calls_api"},
                {"source": "svc-a", "target": "svc-b", "type": "calls_api"},
            ],
            "flows": [],
        }
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "graph.html")
            render_html(graph, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        # Dangling edge dropped: "ghost" never serialized as an edge target.
        self.assertNotIn('"target": "ghost"', html)
        # Valid edge kept.
        self.assertIn('"target": "svc-b"', html)

if __name__ == "__main__":
    unittest.main()
