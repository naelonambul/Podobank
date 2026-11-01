"""Privacy-safe financial operation events for the local observability pipeline."""

import atexit
import json
import logging
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from queue import Queue
from typing import Literal

FinancialOperation = Literal[
    "deposit",
    "withdrawal",
    "transfer",
    "loan_application",
    "loan_approval",
    "loan_rejection",
    "repayment_batch",
    "manual_loan_repayment",
]
FinancialOutcome = Literal["success", "failure"]

_OPERATIONS = frozenset(
    {
        "deposit",
        "withdrawal",
        "transfer",
        "loan_application",
        "loan_approval",
        "loan_rejection",
        "repayment_batch",
        "manual_loan_repayment",
    }
)
_OUTCOMES = frozenset({"success", "failure"})
_REASONS = frozenset(
    {
        "completed",
        "transaction_rejected",
        "invalid_amount",
        "account_not_found",
        "recipient_not_found",
        "self_transfer",
        "insufficient_funds",
        "database_error",
        "loan_request_rejected",
        "product_not_found",
        "active_loan_exists",
        "application_not_found",
        "application_not_pending",
        "loan_not_repaying",
        "no_overdue_installments",
        "balance_limit",
    }
)
_REPAYMENT_COUNT_KEYS = ("processed", "paid", "overdue", "skipped")
_EVENT_LOGGER = logging.getLogger("podobank_api.financial_events")
_EVENT_LOGGER.setLevel(logging.INFO)
_EVENT_LOGGER.propagate = False
_CONFIGURATION_LOCK = threading.Lock()
_EVENT_QUEUE: Queue[logging.LogRecord] = Queue(maxsize=10_000)
_EVENT_PATH: Path | None = None
_FILE_HANDLER: logging.FileHandler | None = None
_QUEUE_HANDLER: QueueHandler | None = None
_LISTENER: QueueListener | None = None
_WAIT_ON_EXIT = True


def _stop_listener_locked() -> None:
    global _EVENT_PATH, _FILE_HANDLER, _QUEUE_HANDLER, _LISTENER

    listener = _LISTENER
    _LISTENER = None
    if listener is not None:
        try:
            listener.stop()
        except Exception:
            pass
    if _QUEUE_HANDLER is not None:
        _EVENT_LOGGER.removeHandler(_QUEUE_HANDLER)
        _QUEUE_HANDLER.close()
        _QUEUE_HANDLER = None
    if _FILE_HANDLER is not None:
        try:
            _FILE_HANDLER.flush()
        except Exception:
            pass
        _FILE_HANDLER.close()
        _FILE_HANDLER = None
    _EVENT_PATH = None


def configure_financial_event_logging(
    path: str | Path | None,
    *,
    wait_on_exit: bool = True,
) -> logging.Handler | None:
    """Queue financial events for an append-only JSONL file when configured."""
    global _EVENT_PATH, _FILE_HANDLER, _QUEUE_HANDLER, _LISTENER, _WAIT_ON_EXIT

    if not path:
        with _CONFIGURATION_LOCK:
            _WAIT_ON_EXIT = wait_on_exit
        return None

    try:
        event_path = Path(path).resolve()
        event_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    with _CONFIGURATION_LOCK:
        _WAIT_ON_EXIT = wait_on_exit
        if _EVENT_PATH == event_path and _LISTENER is not None and _QUEUE_HANDLER is not None:
            return _QUEUE_HANDLER
        _stop_listener_locked()

        try:
            file_handler = logging.FileHandler(
                event_path,
                mode="a",
                encoding="utf-8",
                delay=True,
            )
        except OSError:
            return None
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        queue_handler = QueueHandler(_EVENT_QUEUE)
        listener = QueueListener(_EVENT_QUEUE, file_handler, respect_handler_level=True)
        _EVENT_LOGGER.addHandler(queue_handler)
        try:
            listener.start()
        except Exception:
            _EVENT_LOGGER.removeHandler(queue_handler)
            file_handler.close()
            queue_handler.close()
            return None
        _EVENT_PATH = event_path
        _FILE_HANDLER = file_handler
        _QUEUE_HANDLER = queue_handler
        _LISTENER = listener
        return queue_handler


def shutdown_financial_event_logging() -> None:
    """Drain queued events and stop the file listener during process shutdown."""
    with _CONFIGURATION_LOCK:
        _stop_listener_locked()


def record_financial_operation(
    operation: str,
    outcome: str,
    reason: str,
    *,
    repayment_counts: Sequence[int] | None = None,
) -> None:
    """Write one bounded, privacy-safe event without affecting the financial result."""
    if operation not in _OPERATIONS or outcome not in _OUTCOMES or reason not in _REASONS:
        return
    if repayment_counts is not None:
        if operation != "repayment_batch" or len(repayment_counts) != len(_REPAYMENT_COUNT_KEYS):
            return
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in repayment_counts
        ):
            return

    event: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "event": "financial_operation",
        "operation": operation,
        "outcome": outcome,
        "reason": reason,
    }
    if repayment_counts is not None:
        event.update(dict(zip(_REPAYMENT_COUNT_KEYS, repayment_counts, strict=True)))

    try:
        _EVENT_LOGGER.info("%s", json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        # Observability must never turn a committed transaction into an apparent failure.
        return


def _shutdown_at_exit() -> None:
    if _WAIT_ON_EXIT:
        shutdown_financial_event_logging()


atexit.register(_shutdown_at_exit)
