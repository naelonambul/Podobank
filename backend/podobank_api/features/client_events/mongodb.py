import os
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal

from bson.errors import BSONError
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.write_concern import WriteConcern

from podobank_api.features.client_events.schemas import ClientEvent

_CLIENTS: dict[str, MongoClient[Any]] = {}
_LOCK = Lock()


class EventsUnavailable(Exception):
    pass


def close_client_event_clients() -> None:
    with _LOCK:
        clients = tuple(_CLIENTS.values())
        _CLIENTS.clear()
    for client in clients:
        client.close()


def store_event(event: ClientEvent) -> Literal["stored", "duplicate"]:
    uri = os.environ.get("MONGO_URL", "").strip()
    database = os.environ.get("MONGO_DB_NAME", "").strip()
    if not uri or not database:
        raise EventsUnavailable
    try:
        with _LOCK:
            if uri not in _CLIENTS:
                _CLIENTS[uri] = MongoClient(
                    uri,
                    connectTimeoutMS=1000,
                    serverSelectionTimeoutMS=2000,
                    timeoutMS=2000,
                    retryWrites=False,
                )
            client = _CLIENTS[uri]
        collection = client[database].get_collection(
            "client_events",
            write_concern=WriteConcern(w=1, j=True),
        )
        collection.insert_one(
            {
                "_id": event.event_id,
                **event.model_dump(),
                "received_at": datetime.now(UTC),
            }
        )
    except DuplicateKeyError:
        return "duplicate"
    except (BSONError, PyMongoError, ValueError, OverflowError) as error:
        raise EventsUnavailable from error
    return "stored"
