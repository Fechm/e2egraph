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

if __name__ == "__main__":
    unittest.main()
