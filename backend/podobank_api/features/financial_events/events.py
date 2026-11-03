from datetime import UTC, datetime
from uuid import UUID, uuid4

OPERATIONS = frozenset(
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
REPAYMENT_COUNT_KEYS = ("processed", "paid", "overdue", "skipped")


def build_committed_event(
    operation: str,
    *,
    repayment_counts: tuple[int, int, int, int] | None = None,
    batch_id: str | None = None,
) -> dict[str, object]:
    if operation not in OPERATIONS:
        raise ValueError("operation is not an allowed financial event")

    if operation == "repayment_batch":
        if repayment_counts is None or batch_id is None:
            raise ValueError("repayment candidate events require counts and a batch id")
        if (
            len(repayment_counts) != len(REPAYMENT_COUNT_KEYS)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in repayment_counts
            )
            or repayment_counts[0] != 1
            or repayment_counts[1] + repayment_counts[2] != 1
            or repayment_counts[3] != 0
        ):
            raise ValueError("repayment candidate events must represent one committed state change")
        try:
            batch_id = str(UUID(batch_id))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("batch id must be a UUID") from error
    elif repayment_counts is not None or batch_id is not None:
        raise ValueError("repayment metadata is valid only for repayment candidates")

    event: dict[str, object] = {
        "event_id": str(uuid4()),
        "schema_version": 1,
        "timestamp": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "event": "financial_operation",
        "operation": operation,
        "outcome": "success",
        "reason": "completed",
    }
    if repayment_counts is not None:
        event.update(dict(zip(REPAYMENT_COUNT_KEYS, repayment_counts, strict=True)))
        event["batch_id"] = batch_id
    return event
