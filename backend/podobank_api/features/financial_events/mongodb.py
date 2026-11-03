import logging
import os
from threading import Lock
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

logger = logging.getLogger(__name__)
MONGODB_TIMEOUT_MS = 2_000
_CLIENTS: dict[str, MongoClient[Any]] = {}
_CLIENTS_LOCK = Lock()


def _client_for(uri: str) -> MongoClient[Any]:
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(uri)
        if client is None:
            client = MongoClient(
                uri,
                connectTimeoutMS=1_000,
                serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS,
                timeoutMS=MONGODB_TIMEOUT_MS,
                retryWrites=False,
            )
            _CLIENTS[uri] = client
        return client


def close_mongodb_clients() -> None:
    """Close lazily created MongoDB clients when the API application shuts down."""
    with _CLIENTS_LOCK:
        clients = tuple(_CLIENTS.values())
        _CLIENTS.clear()

    for client in clients:
        client.close()


def write_event_best_effort(event: dict[str, object]) -> bool:
    """Attempt one acknowledged MongoDB insert without affecting a committed transaction."""
    mongo_url = os.environ.get("MONGO_URL", "").strip()
    database_name = os.environ.get("MONGO_DB_NAME", "").strip()
    if not mongo_url or not database_name:
        logger.warning(
            "financial_event_mongodb_write_skipped operation=%s reason=configuration_missing",
            event.get("operation", "unknown"),
        )
        return False

    try:
        collection = _client_for(mongo_url)[database_name].get_collection(
            "financial_events",
            write_concern=WriteConcern(w=1, j=True),
        )
        document = {"_id": event["event_id"], **event}
        collection.insert_one(document)
    except PyMongoError:
        logger.warning(
            "financial_event_mongodb_write_failed operation=%s reason=mongo_unavailable",
            event.get("operation", "unknown"),
        )
        return False
    return True
