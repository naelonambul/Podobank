import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from podobank_api.app import create_app
from podobank_api.settings import Settings


def event():
    return {
        "event_id": str(uuid4()),
        "type": "page_view",
        "occurred_at": "2026-11-04T05:46:27.929Z",
        "session_id": str(uuid4()),
        "anonymous_id": str(uuid4()),
        "page": {
            "path": "/home?token=secret#fragment",
            "referrer": "https://example.test/?code=secret",
        },
        "props": {"route_name": "home"},
        "schema_version": 4,
    }


class ClientEventTests(unittest.TestCase):
    def setUp(self):
        settings = Settings.from_environment(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://unused:unused@localhost/podobank_test",
            }
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self):
        self.client.close()

    def test_anonymous_event_is_validated_and_sanitized(self):
        with patch(
            "podobank_api.features.client_events.api.store_event", return_value="stored"
        ) as store:
            response = self.client.post("/events", json=event())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "stored"})
        received = store.call_args.args[0]
        self.assertEqual(received.page.path, "/home")
        self.assertEqual(received.page.referrer, "https://example.test/")

    def test_duplicate_returns_200(self):
        with patch("podobank_api.features.client_events.api.store_event", return_value="duplicate"):
            response = self.client.post("/events", json=event())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "duplicate"})

    def test_invalid_envelopes_are_rejected_without_writing(self):
        cases = [
            ("event_id", "bad"),
            ("type", "Bad"),
            ("schema_version", 3),
            ("schema_version", "4"),
            ("occurred_at", "2026-11-04T05:46:27"),
            ("props", []),
            ("extra", "secret"),
        ]
        with patch("podobank_api.features.client_events.api.store_event") as store:
            for key, value in cases:
                payload = event()
                payload[key] = value
                with self.subTest(key=key, value=value):
                    response = self.client.post("/events", json=payload)
                    self.assertEqual(response.status_code, 422)
                    self.assertNotIn("secret", response.text)
            store.assert_not_called()

    def test_malformed_and_oversized_bodies(self):
        self.assertEqual(self.client.post("/events", content="{").status_code, 422)
        self.assertEqual(self.client.post("/events", content=b"x" * 32769).status_code, 413)
        response = self.client.post("/events", content=iter([b"x" * 17000, b"x" * 17000]))
        self.assertEqual(response.status_code, 413)

    def test_props_limits(self):
        cases = [
            {"value": "x" * 8193},
            {str(i): i for i in range(65)},
            {"a": {"b": {"c": {"d": {"e": 1}}}}},
        ]
        for props in cases:
            payload = event()
            payload["props"] = props
            response = self.client.post("/events", json=payload)
            self.assertIn(response.status_code, (413, 422))

    def test_storage_failure_is_safe_and_health_survives(self):
        from podobank_api.features.client_events.mongodb import EventsUnavailable

        with patch(
            "podobank_api.features.client_events.api.store_event", side_effect=EventsUnavailable
        ):
            response = self.client.post("/events", json=event())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": {"code": "events_unavailable"}})
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_missing_configuration_and_shutdown_cleanup(self):
        from podobank_api.features.client_events.mongodb import EventsUnavailable, store_event
        from podobank_api.features.client_events.schemas import ClientEvent

        with patch.dict("os.environ", {"MONGO_URL": "", "MONGO_DB_NAME": ""}):
            with self.assertRaises(EventsUnavailable):
                store_event(ClientEvent.model_validate(event()))
        with patch("podobank_api.app.close_client_event_clients") as close:
            with TestClient(
                create_app(
                    Settings.from_environment(
                        {
                            "APP_ENV": "test",
                            "DATABASE_URL": "mysql+pymysql://unused:unused@localhost/podobank_test",
                        }
                    )
                )
            ):
                pass
            close.assert_called_once()

    def test_writer_acknowledges_duplicate_and_does_not_hide_other_errors(self):
        from unittest.mock import MagicMock

        from bson.errors import InvalidDocument
        from pymongo.errors import DuplicateKeyError, OperationFailure

        from podobank_api.features.client_events import mongodb
        from podobank_api.features.client_events.schemas import ClientEvent

        client = MagicMock()
        collection = client.__getitem__.return_value.get_collection.return_value
        payload = event()
        with (
            patch.dict(
                "os.environ", {"MONGO_URL": "mongodb://mongo:27017", "MONGO_DB_NAME": "test"}
            ),
            patch.dict(mongodb._CLIENTS, {}, clear=True),
            patch.object(mongodb, "MongoClient", return_value=client) as constructor,
        ):
            parsed = ClientEvent.model_validate(payload)
            self.assertEqual(mongodb.store_event(parsed), "stored")
            stored = collection.insert_one.call_args.args[0]
            self.assertEqual(stored["_id"], payload["event_id"])
            self.assertEqual(stored["page"]["path"], "/home")
            self.assertIn("received_at", stored)
            collection.insert_one.side_effect = DuplicateKeyError("duplicate")
            self.assertEqual(mongodb.store_event(parsed), "duplicate")
            collection.insert_one.side_effect = OperationFailure("private connection details")
            with self.assertRaises(mongodb.EventsUnavailable):
                mongodb.store_event(parsed)
            for error in (InvalidDocument("private payload"), OverflowError("private integer")):
                collection.insert_one.side_effect = error
                with self.subTest(error=type(error).__name__):
                    with self.assertRaises(mongodb.EventsUnavailable):
                        mongodb.store_event(parsed)
            constructor.assert_called_once()
            self.assertEqual(constructor.call_args.kwargs["timeoutMS"], 2000)
            mongodb.close_client_event_clients()
            client.close.assert_called_once()
            self.assertEqual(mongodb._CLIENTS, {})

    def test_compact_json_props_below_byte_limit_are_accepted(self):
        payload = event()
        payload["props"] = {"items": [0] * 2800}
        with patch("podobank_api.features.client_events.api.store_event", return_value="stored"):
            self.assertEqual(self.client.post("/events", json=payload).status_code, 201)
