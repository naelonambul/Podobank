import json
import logging
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, date, datetime
from io import StringIO
from logging.handlers import QueueHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import podobank_api.features.observability.events as event_module
from podobank_api.cli import main as cli_main
from podobank_api.features.loans.service import RepaymentRunResult
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

    def test_process_repayments_cli_flushes_queued_event_on_exit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="podobank-events-test-") as temporary_directory:
            event_path = Path(temporary_directory) / "financial-events.jsonl"
            fake_engine = SimpleNamespace(dispose=lambda: None)

            def process_due_repayments(*, as_of_date: date) -> RepaymentRunResult:
                record_financial_operation(
                    "repayment_batch",
                    "success",
                    "completed",
                    repayment_counts=(0, 0, 0, 0),
                )
                return RepaymentRunResult(processed=0, paid=0, overdue=0, skipped=0)

            with (
                patch.dict(os.environ, {"FINANCIAL_EVENTS_PATH": str(event_path)}),
                patch(
                    "podobank_api.cli.Settings.from_environment",
                    return_value=SimpleNamespace(database_url="unused"),
                ),
                patch("podobank_api.cli.create_database_engine", return_value=fake_engine),
                patch("podobank_api.cli.LoanService") as loan_service_class,
            ):
                loan_service_class.return_value.process_due_repayments.side_effect = (
                    process_due_repayments
                )
                with patch.object(
                    event_module,
                    "shutdown_financial_event_logging",
                    wraps=shutdown_financial_event_logging,
                ) as shutdown:
                    try:
                        with redirect_stdout(StringIO()):
                            exit_code = cli_main(
                                ["process-repayments", "--as-of-date", "2026-11-03"]
                            )
                        self.assertEqual(exit_code, 0)

                        event_module._shutdown_at_exit()

                        shutdown.assert_called_once()
                        event = json.loads(event_path.read_text(encoding="utf-8").strip())
                    finally:
                        shutdown_financial_event_logging()
                        configure_financial_event_logging(None)

        self.assertEqual(event["operation"], "repayment_batch")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(
            (event["processed"], event["paid"], event["overdue"], event["skipped"]),
            (0, 0, 0, 0),
        )


if __name__ == "__main__":
    unittest.main()
