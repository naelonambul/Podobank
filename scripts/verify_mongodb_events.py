#!/usr/bin/env python3
"""Validate direct, best-effort MongoDB event writes from the API."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "compose.yaml"
COMMAND_TIMEOUT_SECONDS = 60
START_TIMEOUT_SECONDS = 600

SET_DEMO_CREDENTIALS = """
from podobank_api.database import create_database_engine
from podobank_api.demo_credentials import rotate_demo_credentials
from podobank_api.settings import Settings

settings = Settings.from_environment()
engine = create_database_engine(settings.database_url)
try:
    with engine.begin() as connection:
        rotate_demo_credentials(
            connection,
            employee_phone=settings.bank_employee_phone,
            employee_password=settings.bank_employee_password,
            demo_customer_password=settings.demo_customer_password,
        )
finally:
    engine.dispose()
"""

API_DEPOSIT = """
import json
import os
from http.cookies import SimpleCookie
from urllib.request import Request, urlopen

from podobank_api.features.auth.tokens import SESSION_COOKIE_NAME
from podobank_api.seed import DEMO_CUSTOMER_PHONE

base_url = "http://127.0.0.1:8000"
login_request = Request(
    base_url + "/auth/login",
    data=json.dumps({
        "phone_number": DEMO_CUSTOMER_PHONE,
        "password": os.environ["DEMO_CUSTOMER_PASSWORD"],
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(login_request, timeout=5) as response:
    login = json.loads(response.read())
    cookie_headers = response.headers.get_all("Set-Cookie", [])
if login != {"status": "authenticated"}:
    raise RuntimeError("demo customer login did not succeed")

session_cookie = None
for header in cookie_headers:
    cookies = SimpleCookie()
    cookies.load(header)
    cookie = cookies.get(SESSION_COOKIE_NAME)
    if cookie is not None and cookie.value:
        session_cookie = f"{cookie.key}={cookie.value}"
        break
if session_cookie is None:
    raise RuntimeError("API login did not return a session cookie")

deposit_request = Request(
    base_url + "/transactions/deposit",
    data=json.dumps({"amount": 1}).encode(),
    headers={"Content-Type": "application/json", "Cookie": session_cookie},
    method="POST",
)
with urlopen(deposit_request, timeout=10) as response:
    result = json.loads(response.read())
if result.get("amount") != 1 or not isinstance(result.get("balance"), int):
    raise RuntimeError("API did not return a successful deposit result")
print(json.dumps({"amount": result["amount"], "balance": result["balance"]}))
"""

CHECK_API_HEALTH = """
import urllib.request

urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2).close()
"""


class VerificationError(RuntimeError):
    """Raised when the direct MongoDB event check fails."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config-only", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    return result


def compose_base(project: str, env_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--project-name",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE_FILE),
    ]


def test_values(destination: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", maxsplit=1)
            values[name] = value

    values.update(
        {
            "APP_ENV": "test",
            "API_PORT": "0",
            "DB_PORT": "0",
            "FRONTEND_PORT": "0",
            "GRAFANA_PORT": "0",
            "GRAFANA_ADMIN_PASSWORD": f"verify-{uuid.uuid4().hex}-only",
            "MARIADB_ROOT_PASSWORD": f"root-{uuid.uuid4().hex}-only",
            "MARIADB_PASSWORD": f"db-{uuid.uuid4().hex}-only",
            "BANK_EMPLOYEE_PASSWORD": f"verify-employee-{uuid.uuid4().hex}",
            "DEMO_CUSTOMER_PASSWORD": f"verify-customer-{uuid.uuid4().hex}",
            "MONGO_URL": "mongodb://mongo:27017",
            "MONGO_DB_NAME": "podobank_events",
        }
    )
    values["COMPOSE_DATABASE_URL"] = (
        f"mysql+pymysql://{values['MARIADB_USER']}:{values['MARIADB_PASSWORD']}"
        f"@db:3306/{values['MARIADB_DATABASE']}"
    )
    destination.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    return values


def compose_environment(env_file: Path, values: dict[str, str]) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        *values,
        "COMPOSE_ENV_FILE",
        "COMPOSE_FILE",
        "COMPOSE_PROJECT_NAME",
        "COMPOSE_PROFILES",
    ):
        environment.pop(name, None)
    environment["COMPOSE_ENV_FILE"] = str(env_file)
    return environment


def run(
    command: list[str],
    *,
    label: str,
    environment: dict[str, str],
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> str:
    print(label, flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise VerificationError(f"{label} failed: {type(error).__name__}") from error
    if result.returncode:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        raise VerificationError(f"{label} failed (exit {result.returncode}).\n{details}")
    return result.stdout.strip()


def compose_config(compose: list[str], environment: dict[str, str]) -> dict[str, object]:
    run(
        [*compose, "config", "--quiet"],
        label="Checking the Compose configuration with isolated example values.",
        environment=environment,
    )
    output = run(
        [*compose, "config", "--format", "json"],
        label="Checking API and MongoDB service boundaries.",
        environment=environment,
    )
    try:
        config = json.loads(output)
        services = config["services"]
        api = services["api"]
        mongo = services["mongo"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise VerificationError("Compose must define the API and MongoDB services.") from error

    if "event-projector" in services:
        raise VerificationError(
            "The best-effort design must not include an event-projector service."
        )
    if mongo.get("ports"):
        raise VerificationError("MongoDB must not publish a host port.")
    if mongo.get("image") != "mongo:7.0.45":
        raise VerificationError("MongoDB must use the pinned mongo:7.0.45 image.")
    api_environment = api.get("environment", {})
    if api_environment.get("MONGO_URL") != "mongodb://mongo:27017":
        raise VerificationError("FastAPI must receive MONGO_URL using the Compose service name.")
    if api_environment.get("MONGO_DB_NAME") != "podobank_events":
        raise VerificationError("FastAPI must receive MONGO_DB_NAME=podobank_events.")
    if "mongo" in api.get("depends_on", {}):
        raise VerificationError("FastAPI must not depend on MongoDB availability.")
    return config


def mongo_documents(
    compose: list[str],
    environment: dict[str, str],
    database_name: str,
) -> list[dict[str, object]]:
    eval_script = (
        "const events = db.getSiblingDB("
        + json.dumps(database_name)
        + ").financial_events; print(JSON.stringify(events.find({operation:'deposit'}).toArray()));"
    )
    output = run(
        [
            *compose,
            "exec",
            "-T",
            "mongo",
            "mongosh",
            "mongodb://mongo:27017/" + database_name,
            "--quiet",
            "--eval",
            eval_script,
        ],
        label="Reading API-written financial events from MongoDB.",
        environment=environment,
    )
    try:
        documents = json.loads(output)
    except json.JSONDecodeError as error:
        raise VerificationError("MongoDB did not return valid event JSON.") from error
    if not isinstance(documents, list):
        raise VerificationError("MongoDB event query did not return a document list.")
    return documents


def verify_event_document(document: dict[str, object]) -> None:
    expected_fields = {
        "_id",
        "event_id",
        "schema_version",
        "timestamp",
        "event",
        "operation",
        "outcome",
        "reason",
    }
    if set(document) != expected_fields:
        raise VerificationError("MongoDB event document contains missing or unapproved fields.")
    if document["_id"] != document["event_id"]:
        raise VerificationError("MongoDB _id must be the technical event UUID.")
    if (
        document["event"] != "financial_operation"
        or document["operation"] != "deposit"
        or document["outcome"] != "success"
        or document["reason"] != "completed"
        or document["schema_version"] != 1
    ):
        raise VerificationError("MongoDB event document has unexpected operation fields.")


def emit_http_deposit(
    compose: list[str],
    environment: dict[str, str],
    *,
    label: str,
) -> None:
    output = run(
        [*compose, "exec", "-T", "api", "python", "-c", API_DEPOSIT],
        label=label,
        environment=environment,
        timeout=30,
    )
    try:
        result = json.loads(output.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise VerificationError(
            "TransactionService did not return its committed result."
        ) from error
    if result.get("amount") != 1 or result.get("balance", 0) < 1:
        raise VerificationError("The API did not return a successful financial deposit.")


def verify_smoke(compose: list[str], environment: dict[str, str], values: dict[str, str]) -> None:
    run(
        [*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "300", "db", "mongo", "api"],
        label="Starting an isolated MariaDB, MongoDB, and API stack.",
        environment=environment,
        timeout=START_TIMEOUT_SECONDS,
    )
    run(
        [*compose, "exec", "-T", "api", "podobank-api", "init-db"],
        label="Preparing the isolated demo database.",
        environment=environment,
        timeout=120,
    )
    run(
        [*compose, "exec", "-T", "api", "python", "-c", SET_DEMO_CREDENTIALS],
        label="Setting temporary demo login credentials in the isolated database.",
        environment=environment,
    )

    emit_http_deposit(
        compose,
        environment,
        label="Creating one authenticated HTTP deposit while MongoDB is available.",
    )
    documents = mongo_documents(compose, environment, values["MONGO_DB_NAME"])
    if len(documents) != 1:
        raise VerificationError(f"Expected one MongoDB deposit event, found {len(documents)}.")
    verify_event_document(documents[0])

    run(
        [*compose, "stop", "api", "mongo"],
        label="Stopping the API and MongoDB before the outage restart check.",
        environment=environment,
    )
    run(
        [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "api"],
        label="Starting a fresh API container while MongoDB remains stopped.",
        environment=environment,
        timeout=180,
    )
    run(
        [*compose, "exec", "-T", "api", "python", "-c", CHECK_API_HEALTH],
        label="Verifying the API health endpoint while MongoDB is stopped.",
        environment=environment,
    )
    emit_http_deposit(
        compose,
        environment,
        label="Creating an authenticated HTTP deposit while MongoDB is stopped.",
    )
    run(
        [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "mongo"],
        label="Restarting MongoDB after the best-effort write was missed.",
        environment=environment,
        timeout=180,
    )
    documents = mongo_documents(compose, environment, values["MONGO_DB_NAME"])
    if len(documents) != 1:
        raise VerificationError(
            "MongoDB outage must not fail the financial transaction, and the missed event "
            "must not be retried or restored."
        )


def main() -> int:
    arguments = parser().parse_args()
    if shutil.which("docker") is None:
        raise VerificationError("Docker CLI is required for MongoDB event verification.")
    version = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if version.returncode:
        raise VerificationError("Docker Compose v2 is required for MongoDB event verification.")

    project = f"podobank-mongodb-events-{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="podobank-mongodb-events-") as temporary_directory:
        env_file = Path(temporary_directory) / "compose.env"
        values = test_values(env_file)
        environment = compose_environment(env_file, values)
        compose = compose_base(project, env_file)
        try:
            compose_config(compose, environment)
            if arguments.smoke:
                run(
                    ["docker", "info", "--format", "{{.ServerVersion}}"],
                    label="Checking the local Docker engine.",
                    environment=environment,
                )
                verify_smoke(compose, environment, values)
        finally:
            if arguments.smoke:
                cleanup = subprocess.run(
                    [
                        *compose,
                        "down",
                        "--volumes",
                        "--remove-orphans",
                        "--timeout",
                        "15",
                    ],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=60,
                )
                if cleanup.returncode:
                    message = "isolated MongoDB event resources may need cleanup"
                    if sys.exc_info()[0] is None:
                        raise VerificationError(message)
                    print(f"warning: {message}", file=sys.stderr)

    print("MongoDB event verification passed.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
