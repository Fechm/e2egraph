# -*- coding: utf-8 -*-
import unittest
from lib.relations import extract_relations

class TestRelations(unittest.TestCase):
    def test_ts_imports_and_env_and_api(self):
        src = (
            "import { Foo } from './foo';\n"
            "const url = process.env.USERS_API_URL;\n"
            "const secret = process.env.ACME_SECRET_KEY;\n"
            "await axios.get(`${url}/v1/users`);\n"
        )
        edges = extract_relations("svc-a/src/index.ts", "ts", src)
        types = {e["type"] for e in edges}
        self.assertIn("imports", types)
        self.assertIn("uses_env", types)
        self.assertIn("calls_api", types)
        env_edges = [e for e in edges if e["type"] == "uses_env"]
        names = {e["target_name"] for e in env_edges}
        self.assertIn("USERS_API_URL", names)              # service var kept verbatim
        self.assertNotIn("ACME_SECRET_KEY", names)          # secret var not verbatim
        self.assertTrue(any("•" in n for n in names))  # secret var masked
        for e in edges:
            self.assertIn(e["confidence"], {"EXTRACTED", "INFERRED", "AMBIGUOUS"})

    def test_sql_table(self):
        edges = extract_relations("svc-b/q.sql", "sql",
                                  "SELECT * FROM public.users WHERE id = 1;")
        self.assertTrue(any(e["type"] == "reads_table" and e["target_name"] == "public.users"
                            for e in edges))

    def test_proto_service(self):
        edges = extract_relations("a.proto", "proto", "service UserService {\n}")
        self.assertTrue(any(e["type"] == "shares_proto" and e["target_name"] == "UserService"
                            for e in edges))

    def test_sql_write_tables(self):
        edges = extract_relations(
            "w.sql", "sql",
            "INSERT INTO public.orders (id) VALUES (1); UPDATE public.users SET x=1;")
        write_names = {e["target_name"] for e in edges if e["type"] == "writes_table"}
        self.assertIn("public.orders", write_names)
        self.assertIn("public.users", write_names)

    def test_python_imports(self):
        edges = extract_relations("m.py", "py", "from app.core import db\nimport os\n")
        import_names = {e["target_name"] for e in edges if e["type"] == "imports"}
        self.assertIn("app.core", import_names)
        self.assertIn("os", import_names)

    def test_js_require_import(self):
        edges = extract_relations("a.js", "js", "const x = require('./foo');")
        self.assertTrue(any(e["type"] == "imports" and e["target_name"] == "./foo"
                            for e in edges))

    def test_unknown_lang_returns_list_no_raise(self):
        edges = extract_relations("a.txt", "unknownlang", "whatever")
        self.assertIsInstance(edges, list)

    def test_nestjs_config_service_env(self):
        src = "const u = this.configService.get('USERS_API_URL');\n" \
              "const k = configService.get('ACME_SECRET_KEY');\n"
        edges = extract_relations("a.ts", "ts", src)
        env = [e for e in edges if e["type"] == "uses_env"]
        names = {e["target_name"] for e in env}
        self.assertIn("USERS_API_URL", names)          # service var, verbatim
        self.assertNotIn("ACME_SECRET_KEY", names)      # secret var masked
        self.assertTrue(any("•" in n for n in names))

    def test_drizzle_pgtable_and_pgschema(self):
        src = "export const users = pgTable('app_users', { id: serial() });\n" \
              "export const sch = pgSchema('billing');\n"
        edges = extract_relations("schema.ts", "ts", src)
        tbls = {e["target_name"] for e in edges if e["type"] == "declares_table"}
        self.assertIn("app_users", tbls)
        self.assertIn("billing", tbls)

    def test_existing_process_env_still_works(self):
        edges = extract_relations("b.ts", "ts", "const x = process.env.GATEWAY_URL;")
        self.assertTrue(any(e["type"] == "uses_env" and e["target_name"] == "GATEWAY_URL"
                            for e in edges))

    def test_defines_endpoint_combines_controller_and_method(self):
        src = ("@Controller('v1/users')\n"
               "class UsersController {\n"
               "  @Get(':id')\n  findOne() {}\n"
               "  @Post()\n  create() {}\n}")
        edges = extract_relations("c.ts", "ts", src)
        eps = {e["target_name"] for e in edges if e["type"] == "defines_endpoint"}
        self.assertIn("/v1/users/*", eps)   # :id -> *
        self.assertIn("/v1/users", eps)     # @Post() with no path -> prefix only

    def test_normalize_endpoint_path(self):
        from lib.relations import normalize_endpoint_path
        self.assertEqual(normalize_endpoint_path("/v1/users/42"), "/v1/users/*")
        self.assertEqual(normalize_endpoint_path("v1/Users/:id"), "/v1/users/*")

    def test_config_object_all_caps_access(self):
        src = "const c = new UserGrpcClient(config.USERS_API_ADDRESS);\n" \
              "const r = `${config.RBAC_API_HOST}:${config.RBAC_API_PORT}`;\n"
        edges = extract_relations("g.ts", "ts", src)
        names = {e["target_name"] for e in edges if e["type"] == "uses_env"}
        self.assertIn("USERS_API_ADDRESS", names)
        self.assertIn("RBAC_API_HOST", names)

    def test_config_pattern_does_not_capture_config_service_get(self):
        # configService.get('X') must still be captured exactly once, not doubled or broken
        edges = extract_relations("g.ts", "ts", "const x = configService.get('USERS_API_URL');")
        names = [e["target_name"] for e in edges if e["type"] == "uses_env"]
        self.assertEqual(names.count("USERS_API_URL"), 1)

if __name__ == "__main__":
    unittest.main()
