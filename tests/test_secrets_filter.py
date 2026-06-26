import unittest
from lib.secrets_filter import classify_env, mask_name

class TestSecretsFilter(unittest.TestCase):
    def test_service_vars_kept(self):
        self.assertEqual(classify_env("GATEWAY_URL"), "service")
        self.assertEqual(classify_env("USERS_API_HOST"), "service")
        self.assertEqual(classify_env("PAYMENTS_BASE_URL"), "service")

    def test_secret_vars_flagged(self):
        self.assertEqual(classify_env("ACME_SECRET_KEY"), "secret")
        self.assertEqual(classify_env("DB_PASSWORD"), "secret")
        self.assertEqual(classify_env("JWT_TOKEN"), "secret")

    def test_other_vars(self):
        self.assertEqual(classify_env("NODE_ENV"), "other")

    def test_mask_keeps_shape_hides_middle(self):
        masked = mask_name("ACME_SECRET_KEY")
        self.assertTrue(masked.startswith("ACME"))
        self.assertTrue(masked.endswith("KEY"))
        self.assertIn("•", masked)
        self.assertNotIn("SECRET", masked)

if __name__ == "__main__":
    unittest.main()
