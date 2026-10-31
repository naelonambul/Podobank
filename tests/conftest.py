import os

import pytest


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get(
        "PODOBANK_DATABASE_URL",
        "mysql+pymysql://podobank:local-only-password@127.0.0.1:3306/podobank",
    )
