import json, os, tempfile, unittest
from lib.detect import detect
from lib.relations import extract_relations
from lib.symbols import extract_symbols_fallback
from lib.build import build_repo_graph
from lib.crossrepo import merge_graphs
from lib.render_html import render_html

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
# Built at runtime so this test file contains no famous secret literal.
SECRET_EXAMPLE = "ACME" + "_SECRET_KEY"

class TestIntegration(unittest.TestCase):
    def test_end_to_end_known_connection(self):
        det = detect(FIX)
        graphs = []
        for repo in det["repos"]:
            rels, syms = [], []
            for f in repo["files"]:
                with open(f["path"], encoding="utf-8") as fh:
                    text = fh.read()
                rels += extract_relations(f["path"], f["lang"], text)
                syms += extract_symbols_fallback(f["path"], f["lang"], text)
            graphs.append(build_repo_graph(repo, rels, syms))
        merged = merge_graphs(graphs)
        # Known cross-repo connection via shared table
        self.assertTrue(any(n["type"] == "db_table" and n["label"] == "public.users"
                            for n in merged["nodes"]))
        self.assertTrue(any("Shared table" in f["name"] for f in merged["flows"]))
        # Secret var name never appears verbatim anywhere in the serialized graph
        blob = json.dumps(merged)
        self.assertNotIn(SECRET_EXAMPLE, blob)
        self.assertIn("USERS_API_URL", blob)
        # HTML renders and is self-contained
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "graph.html")
            render_html(merged, out)
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertNotIn(SECRET_EXAMPLE, html)

if __name__ == "__main__":
    unittest.main()
