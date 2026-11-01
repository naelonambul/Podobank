import json
import logging
import tempfile
import unittest
from datetime import UTC, datetime
from logging.handlers import QueueHandler
from pathlib import Path
from unittest.mock import patch

import podobank_api.features.observability.events as event_module
from podobank_api.features.observability.events import (
    configure_financial_event_logging,
    record_financial_operation,
    shutdown_financial_event_logging,
)

EVENT_LOGGER = logging.getLogger("podobank_api.financial_events")


class FinancialEventTests(unittest.TestCase):
    def test_records_privacy_safe_jsonl_with_utc_timestamp(self) -> None:
        with tempfile.TemporaryDirectory(prefix="podobank-events-test-") as temporary_directory:
            event_path = Path(temporary_directory) / "financial-events.jsonl"
            handler = configure_financial_event_logging(event_path)
            self.assertIsNotNone(handler)
            self.assertIsInstance(handler, QueueHandler)
            try:
                record_financial_operation("deposit", "success", "completed")
                shutdown_financial_event_logging()

                line = event_path.read_text(encoding="utf-8").strip()
                event = json.loads(line)
            finally:
                shutdown_financial_event_logging()

        self.assertEqual(
            set(event),
            {"timestamp", "event", "operation", "outcome", "reason"},
        )
        self.assertEqual(event["event"], "financial_operation")
        self.assertEqual(event["operation"], "deposit")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["reason"], "completed")
        timestamp = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
        self.assertEqual(timestamp.tzinfo, UTC)
        for sensitive_value in ("01012345678", "987654321012", "876543210", "jwt-secret"):
            self.assertNotIn(sensitive_value, line)

    def test_repayment_batch_contains_only_bounded_count_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="podobank-events-test-") as temporary_directory:
            event_path = Path(temporary_directory) / "financial-events.jsonl"
            handler = configure_financial_event_logging(event_path)
            self.assertIsNotNone(handler)
            self.assertIsInstance(handler, QueueHandler)
            try:
                record_financial_operation(
                    "repayment_batch",
                    "success",
                    "completed",
                    repayment_counts=(3, 2, 1, 0),
                )
                shutdown_financial_event_logging()
                event = json.loads(event_path.read_text(encoding="utf-8").strip())
            finally:
                shutdown_financial_event_logging()

        self.assertEqual(
            set(event),
            {
                "timestamp",
                "event",
                "operation",
                "outcome",
                "reason",
                "processed",
                "paid",
                "overdue",
                "skipped",
            },
        )
        self.assertEqual(
            (event["processed"], event["paid"], event["overdue"], event["skipped"]),
            (3, 2, 1, 0),
        )

    def test_rejects_unbounded_labels_without_raising(self) -> None:
        with tempfile.TemporaryDirectory(prefix="podobank-events-test-") as temporary_directory:
            event_path = Path(temporary_directory) / "financial-events.jsonl"
            handler = configure_financial_event_logging(event_path)
            self.assertIsNotNone(handler)
            self.assertIsInstance(handler, QueueHandler)
            try:
                record_financial_operation("deposit-01012345678", "success", "completed")
                record_financial_operation("deposit", "success", "raw-phone-01012345678")
                shutdown_financial_event_logging()
                self.assertFalse(event_path.exists())
            finally:
                shutdown_financial_event_logging()

    def test_logging_failure_does_not_escape_into_financial_service(self) -> None:
        with patch.object(EVENT_LOGGER, "info", side_effect=OSError("sink unavailable")):
            record_financial_operation("withdrawal", "failure", "insufficient_funds")

    def test_cli_process_exit_does_not_wait_for_event_sink(self) -> None:
        with (
            patch.object(event_module, "_WAIT_ON_EXIT", False),
            patch.object(event_module, "shutdown_financial_event_logging") as shutdown,
        ):
            event_module._shutdown_at_exit()

        shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
