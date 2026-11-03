import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from podobank_api.app import app
from podobank_api.features.financial_events import mongodb


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_reports_ok(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_application_shutdown_closes_lazy_mongodb_client(self) -> None:
        mongo_url = "mongodb://mongo:27017"
        mongodb.close_mongodb_clients()
        self.addCleanup(mongodb.close_mongodb_clients)

        with patch("podobank_api.features.financial_events.mongodb.MongoClient") as client_factory:
            mongo_client = client_factory.return_value
            mongodb._client_for(mongo_url)

            with TestClient(app):
                pass

        mongo_client.close.assert_called_once_with()
