import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from access_common import AccessError
from api_policy import approved_get_path


class APIPolicyTests(unittest.TestCase):
    def setUp(self):
        self.specification = {
            "openapi": "3.0.3",
            "paths": {
                "/health": {"get": {}},
                "/services/{service}/status": {"get": {"parameters": [{"in": "query", "name": "limit"}]}},
                "/admin/reload": {"get": {}},
                "/services": {"post": {}},
            },
        }
        self.approved = ["/health", "/services/{service}/status", "/services"]

    def test_explicit_and_parameterized_get_routes(self):
        for target in ["/health", "/services/demo/status", "/services/demo/status?limit=10"]:
            self.assertEqual(approved_get_path(target, self.specification, self.approved), target)

    def test_method_path_and_query_bypasses_are_rejected(self):
        targets = [
            "/services", "/admin/reload", "/unknown", "https://other.invalid/health", "//other.invalid/health",
            "/health#fragment", "/health\r\nAuthorization: other", "/services/../health", "/services/./health",
            "/services//status", "/services/demo%2fother/status", "/health%3fignored", "/health\\other",
            "/services/{service}/status", "/health?token=other", "/services/demo/status?limit=1&limit=2",
            "/services/demo/status?limit=1;method=POST", "/services/demo/status?limit=%0aother",
        ]
        for target in targets:
            with self.subTest(target=target), self.assertRaises(AccessError):
                approved_get_path(target, self.specification, self.approved)

    def test_exact_unapproved_route_cannot_match_an_approved_template(self):
        self.specification["paths"]["/services/admin/status"] = {"post": {}}
        with self.assertRaises(AccessError):
            approved_get_path("/services/admin/status", self.specification, self.approved)

    def test_remote_references_and_missing_required_parameters_fail_closed(self):
        operation = self.specification["paths"]["/health"]["get"]
        operation["$ref"] = "https://other.invalid/openapi.yaml"
        with self.assertRaises(AccessError):
            approved_get_path("/health", self.specification, self.approved)
        del operation["$ref"]
        operation["parameters"] = [{"in": "query", "name": "version", "required": True}]
        with self.assertRaises(AccessError):
            approved_get_path("/health", self.specification, self.approved)
        self.assertEqual(approved_get_path("/health?version=1", self.specification, self.approved), "/health?version=1")

    def test_malformed_parameters_and_query_floods_fail_closed(self):
        for parameters in [None, "invalid", [{"$ref": "#/components/parameters/limit"}]]:
            self.specification["paths"]["/health"]["parameters"] = parameters
            with self.assertRaises(AccessError):
                approved_get_path("/health", self.specification, self.approved)
        del self.specification["paths"]["/health"]["parameters"]
        with self.assertRaises(AccessError):
            approved_get_path("/health?" + "&".join(f"key{number}=1" for number in range(51)), self.specification, self.approved)


if __name__ == "__main__":
    unittest.main()
