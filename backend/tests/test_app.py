import unittest

from fastapi.testclient import TestClient

from podobank_api.app import app


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_reports_ok(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
