import os, tempfile, unittest
from lib.catalog import extract_catalog, catalog_by_repo, mark_traced
from lib.detect import detect

class TestCatalog(unittest.TestCase):
    def _repo(self, root, rel, content):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(content)

    def test_extracts_gql_ops_and_resolvers(self):
        with tempfile.TemporaryDirectory() as root:
            self._repo(root, "webapp/package.json", "{}")
            self._repo(root, "webapp/src/q.ts",
                       "export const Q = gql`\n  query GetUsers {\n    users { id name }\n  }\n`;\n"
                       "export const M = gql`mutation SaveX { saveX(input: $i) { ok } }`;")
            self._repo(root, "api/package.json", "{}")
            self._repo(root, "api/src/r.ts",
                       "@Query(() => [User])\n  users() {}\n  @Mutation(() => Result)\n  saveX() {}")
            det = detect(root)
            feats = extract_catalog(det)
            names = {(f["name"], f["role"]) for f in feats}
            self.assertIn(("GetUsers", "consumed"), names)
            self.assertIn(("SaveX", "consumed"), names)
            getusers = next(f for f in feats if f["name"] == "GetUsers")
            self.assertEqual(getusers["kind"], "query")
            self.assertEqual(getusers["root_field"], "users")
            self.assertTrue(any(f["role"] == "defined" and f["name"] in ("users", "saveX") for f in feats))
            # file paths are relative + carry a line number
            self.assertTrue(all(not f["file"].startswith(root.replace("\\", "/")) for f in feats))
            self.assertTrue(all(isinstance(f["line"], int) and f["line"] >= 1 for f in feats))

    def test_group_and_mark_traced(self):
        feats = [{"name": "GetUsers", "kind": "query", "root_field": "users", "repo": "webapp",
                  "file": "src/q.ts", "line": 2, "role": "consumed"}]
        by = catalog_by_repo(feats)
        self.assertIn("webapp", by)
        marked = mark_traced(feats, {"getusers"})
        self.assertTrue(marked[0]["traced"])

    def test_gql_file_extension(self):
        """Standalone .graphql/.gql files are also scanned."""
        with tempfile.TemporaryDirectory() as root:
            self._repo(root, "webapp/package.json", "{}")
            self._repo(root, "webapp/src/GetProfile.graphql",
                       "query GetProfile {\n  profile { name email }\n}\n")
            det = detect(root)
            feats = extract_catalog(det)
            names = {f["name"] for f in feats}
            self.assertIn("GetProfile", names)
            gp = next(f for f in feats if f["name"] == "GetProfile")
            self.assertEqual(gp["root_field"], "profile")
            self.assertEqual(gp["role"], "consumed")

    def test_resolver_field_from_decorator_name_arg(self):
        """@Query(() => X, { name: 'customField' }) uses the name arg."""
        with tempfile.TemporaryDirectory() as root:
            self._repo(root, "api/package.json", "{}")
            self._repo(root, "api/src/r.ts",
                       "@Query(() => Foo, { name: 'customField' })\n  someMethod() {}")
            det = detect(root)
            feats = extract_catalog(det)
            defined = [f for f in feats if f["role"] == "defined"]
            names = {f["name"] for f in defined}
            self.assertIn("customField", names)

    def test_endpoint_defined(self):
        """@Controller + @Get/@Post emit kind=endpoint, role=defined."""
        with tempfile.TemporaryDirectory() as root:
            self._repo(root, "api/package.json", "{}")
            self._repo(root, "api/src/c.ts",
                       "@Controller('v1/items')\nclass ItemsController {\n"
                       "  @Get(':id')\n  findOne() {}\n"
                       "  @Post()\n  create() {}\n}")
            det = detect(root)
            feats = extract_catalog(det)
            eps = [f for f in feats if f["kind"] == "endpoint"]
            paths = {f["name"] for f in eps}
            self.assertIn("/v1/items/*", paths)
            self.assertIn("/v1/items", paths)
            for ep in eps:
                self.assertEqual(ep["role"], "defined")

    def test_mark_traced_by_root_field(self):
        """mark_traced also matches on root_field, not only name."""
        feats = [{"name": "GetUsers", "kind": "query", "root_field": "users", "repo": "webapp",
                  "file": "src/q.ts", "line": 2, "role": "consumed"}]
        marked = mark_traced(feats, {"users"})
        self.assertTrue(marked[0]["traced"])

    def test_unreadable_file_skipped(self):
        """A file that doesn't exist should not crash extract_catalog."""
        det = {
            "root": "/fake/root",
            "repos": [{"name": "svc", "path": "/fake/root/svc",
                       "files": [{"path": "/fake/root/svc/src/ghost.ts", "lang": "ts"}]}]
        }
        feats = extract_catalog(det)
        self.assertIsInstance(feats, list)

    def test_catalog_by_repo_groups_correctly(self):
        feats = [
            {"name": "GetA", "kind": "query", "root_field": "a", "repo": "svc1",
             "file": "f.ts", "line": 1, "role": "consumed"},
            {"name": "GetB", "kind": "query", "root_field": "b", "repo": "svc2",
             "file": "g.ts", "line": 1, "role": "consumed"},
            {"name": "GetC", "kind": "mutation", "root_field": "c", "repo": "svc1",
             "file": "h.ts", "line": 2, "role": "consumed"},
        ]
        by = catalog_by_repo(feats)
        self.assertEqual(len(by["svc1"]), 2)
        self.assertEqual(len(by["svc2"]), 1)

    def test_mark_traced_false_when_no_match(self):
        feats = [{"name": "GetUsers", "kind": "query", "root_field": "users", "repo": "webapp",
                  "file": "src/q.ts", "line": 2, "role": "consumed"}]
        marked = mark_traced(feats, {"completely_different"})
        self.assertFalse(marked[0]["traced"])

    def test_anonymous_gql_operation_identified_by_root_field(self):
        with tempfile.TemporaryDirectory() as root:
            self._repo(root, "web/package.json", "{}")
            self._repo(root, "web/src/graphql/mutations/changeOrder.ts",
                       "import gql from 'graphql-tag';\n"
                       "export default gql`\n"
                       "  mutation ($i: ChangeOrderEntityInput!) {\n"
                       "    changeOrderEntity(input: $i) {\n"
                       "      response { statusCode }\n"
                       "    }\n"
                       "  }\n`;\n")
            det = detect(root)
            feats = extract_catalog(det)
            f = next((x for x in feats if x.get("root_field") == "changeOrderEntity"), None)
            self.assertIsNotNone(f)
            self.assertEqual(f["kind"], "mutation")
            self.assertEqual(f["role"], "consumed")
            self.assertEqual(f["name"], "changeOrderEntity")  # anónima -> cae al root field

if __name__ == "__main__":
    unittest.main()
