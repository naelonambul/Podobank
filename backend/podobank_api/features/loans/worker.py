from datetime import UTC, datetime
from threading import Event

from sqlalchemy.engine import Engine

from podobank_api.database import create_database_engine, initialize_database
from podobank_api.features.loans.service import process_due_repayments
from podobank_api.settings import Settings


def run_repayment_worker(
    engine: Engine,
    *,
    interval_seconds: int = 3600,
    stop_event: Event | None = None,
) -> None:
    stop = stop_event or Event()
    while not stop.is_set():
        process_due_repayments(engine, as_of=datetime.now(UTC).date())
        stop.wait(interval_seconds)


def main() -> None:
    settings = Settings.from_environment()
    engine = create_database_engine(settings.database_url)
    try:
        initialize_database(
            engine,
            staff_initial_phone=settings.staff_initial_phone,
            staff_initial_password=settings.staff_initial_password,
        )
        run_repayment_worker(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
