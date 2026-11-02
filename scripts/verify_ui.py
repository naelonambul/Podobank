#!/usr/bin/env python3
"""Validate and drive the isolated mobile Podobank web application."""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
COMPOSE_FILE = ROOT / "compose.yaml"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.64.1-noble"
CONFIG_TIMEOUT_SECONDS = 60
START_TIMEOUT_SECONDS = 600
POLL_TIMEOUT_SECONDS = 120

FIXTURE_SETUP = r'''
import json
import sys
from datetime import date, datetime
from sqlalchemy import text
from podobank_api.database import create_database_engine
from podobank_api.features.auth.passwords import hash_password
from podobank_api.features.loans.service import LoanService
from podobank_api.features.transactions.service import TransactionService
from podobank_api.settings import Settings

payload = json.loads(sys.stdin.readline())
engine = create_database_engine(Settings.from_environment().database_url)

def create_customer(connection, fixture):
    password = fixture.get("password")
    result = connection.execute(
        text("""
            INSERT INTO users (
                name, phone_number, password_hash, age, gender, marital_status,
                is_employed, role
            ) VALUES (
                :name, :phone, :password_hash, 30, 'female', 'single', 1, 'customer'
            )
        """),
        {
            "name": fixture["name"],
            "phone": fixture["phone"],
            "password_hash": hash_password(password) if password else None,
        },
    )
    user_id = int(result.lastrowid)
    connection.execute(
        text("""
            INSERT INTO accounts (owner_user_id, account_number, balance)
            VALUES (:user_id, :account_number, 0)
        """),
        {"user_id": user_id, "account_number": fixture["account_number"]},
    )
    return user_id

try:
    with engine.begin() as connection:
        default_customer_id = int(connection.execute(
            text("SELECT id FROM users WHERE phone_number = :phone"),
            {"phone": payload["customer"]["phone"]},
        ).scalar_one())
        connection.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
            {
                "password_hash": hash_password(payload["customer"]["password"]),
                "user_id": default_customer_id,
            },
        )
        employee_id = int(connection.execute(
            text("SELECT id FROM users WHERE phone_number = :phone AND role = 'bank_employee'"),
            {"phone": payload["employee"]["phone"]},
        ).scalar_one())
        recipient_id = create_customer(connection, payload["recipient"])
        approval_id = create_customer(connection, payload["approval"])
        rejection_id = create_customer(connection, payload["rejection"])
        overdue_id = create_customer(connection, payload["overdue"])
        car_product_id = int(connection.execute(
            text("SELECT id FROM loan_products WHERE code = 'car_purchase'")
        ).scalar_one())

    loans = LoanService(engine)
    transactions = TransactionService(engine)
    overdue_application = loans.apply(user_id=overdue_id, product_id=car_product_id)
    loans.approve(
        application_id=int(overdue_application["id"]),
        employee_id=employee_id,
    )
    overdue_record = loans.customer_applications(user_id=overdue_id)[0]
    first_due_date = overdue_record["repayments"][0]["due_date"]
    if isinstance(first_due_date, str):
        first_due_date = date.fromisoformat(first_due_date)
    elif isinstance(first_due_date, datetime):
        first_due_date = first_due_date.date()
    transactions.withdraw(user_id=overdue_id, amount=int(overdue_record["principal_amount"]))
    overdue_result = loans.process_due_repayments(as_of_date=first_due_date)
    if overdue_result.overdue < 1 or overdue_result.paid:
        raise RuntimeError("could not prepare an overdue installment fixture")

    print(json.dumps({
        "fixture_user_ids": {
            "customer": default_customer_id,
            "recipient": recipient_id,
            "approval": approval_id,
            "rejection": rejection_id,
            "overdue": overdue_id,
        },
        "overdue_due_date": first_due_date.isoformat(),
    }, sort_keys=True))
finally:
    engine.dispose()
'''


class VerificationError(RuntimeError):
    """Raised when a required web verification fails."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config-only", action="store_true")
    mode.add_argument("--quality", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--launch", action="store_true")
    mode.add_argument("--doctor", action="store_true")
    mode.add_argument("--drive", action="store_true")
    mode.add_argument("--cleanup", action="store_true")
    result.add_argument("--run-file", type=Path)
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


def redact(value: str, secrets: list[str]) -> str:
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    return value


def run(
    command: list[str],
    *,
    label: str,
    environment: dict[str, str],
    timeout: int = CONFIG_TIMEOUT_SECONDS,
    input_text: str | None = None,
    secrets: list[str] | None = None,
) -> str:
    print(label, flush=True)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise VerificationError(f"{label} failed: {type(error).__name__}") from error
    if completed.returncode:
        details = "\n".join(part for part in (completed.stdout, completed.stderr) if part.strip())
        detail = redact(details, secrets or [])
        raise VerificationError(f"{label} failed (exit {completed.returncode}).\n{detail}")
    return completed.stdout.strip()


def free_port(used: set[int]) -> int:
    for _ in range(8):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        if port not in used:
            used.add(port)
            return port
    raise VerificationError("Could not allocate distinct temporary loopback ports.")


def example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", maxsplit=1)
            values[name] = value
    return values


def make_run() -> dict[str, object]:
    run_id = uuid.uuid4().hex[:12]
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f"podobank-ui-{run_id}-", dir=tempfile.gettempdir())
    )
    evidence_dir = ROOT / ".evidence" / "ui" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=False)

    used_ports: set[int] = set()
    api_port = free_port(used_ports)
    frontend_port = free_port(used_ports)
    db_port = free_port(used_ports)
    token = uuid.uuid4().hex
    customer_password = f"Verify-{uuid.uuid4().hex[:18]}"
    employee_password = f"Verify-{uuid.uuid4().hex[:18]}"

    fixtures: dict[str, dict[str, str]] = {
        "customer": {
            "phone": "01000000001",
            "password": customer_password,
        },
        "employee": {
            "phone": "01000000002",
            "password": employee_password,
        },
        "recipient": {
            "name": "검증 수취인",
            "phone": "01099990001",
            "account_number": "200000000001",
        },
        "approval": {
            "name": "검증 승인 고객",
            "phone": "01099990003",
            "account_number": "200000000003",
            "password": f"Verify-{uuid.uuid4().hex[:18]}",
        },
        "rejection": {
            "name": "검증 거절 고객",
            "phone": "01099990004",
            "account_number": "200000000004",
            "password": f"Verify-{uuid.uuid4().hex[:18]}",
        },
        "overdue": {
            "name": "검증 연체 고객",
            "phone": "01099990005",
            "account_number": "200000000005",
            "password": f"Verify-{uuid.uuid4().hex[:18]}",
        },
    }

    values = example_values()
    database_name = f"podobank_ui_{run_id}"
    db_password = f"verify-db-{token}"
    values.update(
        {
            "APP_ENV": "development",
            "API_PORT": str(api_port),
            "DB_PORT": str(db_port),
            "FRONTEND_PORT": str(frontend_port),
            "MARIADB_DATABASE": database_name,
            "MARIADB_USER": "podobank",
            "MARIADB_PASSWORD": db_password,
            "MARIADB_ROOT_PASSWORD": f"verify-root-{token}",
            "DATABASE_URL": (
                f"mysql+pymysql://podobank:{db_password}@127.0.0.1:{db_port}/{database_name}"
            ),
            "COMPOSE_DATABASE_URL": (
                f"mysql+pymysql://podobank:{db_password}@db:3306/{database_name}"
            ),
            "API_ORIGIN": f"http://localhost:{api_port}",
            "VITE_API_ORIGIN": f"http://localhost:{api_port}",
            "KAKAO_REDIRECT_URI": (f"http://localhost:{frontend_port}/auth/kakao/callback"),
            "JWT_SECRET": f"ui-verification-{token}-secret-value-long-enough",
            "AUTH_COOKIE_SECURE": "false",
            "FRONTEND_ORIGINS": f"http://localhost:{frontend_port}",
            "BANK_EMPLOYEE_PHONE": fixtures["employee"]["phone"],
            "BANK_EMPLOYEE_PASSWORD": employee_password,
            "GRAFANA_PORT": "0",
            "GRAFANA_ADMIN_PASSWORD": f"verify-grafana-{token}",
        }
    )
    env_file = temporary_root / "compose.env"
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    run_info: dict[str, object] = {
        "schema": 1,
        "id": run_id,
        "project": f"podobank-ui-{run_id}",
        "run_dir": str(temporary_root),
        "env_file": str(env_file),
        "evidence_dir": str(evidence_dir),
        "api_origin": values["API_ORIGIN"],
        "frontend_origin": f"http://localhost:{frontend_port}",
        "fixtures": fixtures,
        "secrets": [
            values["MARIADB_PASSWORD"],
            values["MARIADB_ROOT_PASSWORD"],
            values["JWT_SECRET"],
            values["BANK_EMPLOYEE_PASSWORD"],
            values["GRAFANA_ADMIN_PASSWORD"],
            *(fixture["password"] for fixture in fixtures.values() if fixture.get("password")),
        ],
    }
    write_run_info(run_info)
    return run_info


def write_run_info(run_info: dict[str, object]) -> None:
    destination = Path(str(run_info["run_dir"])) / "run.json"
    destination.write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    destination.chmod(0o600)


def read_run_info(run_file: Path | None) -> dict[str, object]:
    if run_file is None:
        raise VerificationError("--run-file is required for --doctor, --drive, and --cleanup.")
    try:
        resolved = run_file.resolve(strict=True)
        info = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("Could not read the isolated UI run file.") from error

    run_id = info.get("id")
    if not isinstance(run_id, str) or re.fullmatch(r"[a-f0-9]{12}", run_id) is None:
        raise VerificationError("The run file has an invalid identifier.")
    run_dir = Path(str(info.get("run_dir", ""))).resolve(strict=True)
    temp_root = Path(tempfile.gettempdir()).resolve()
    if (
        run_dir.parent != temp_root
        or re.fullmatch(rf"podobank-ui-{run_id}-[a-zA-Z0-9_-]+", run_dir.name) is None
        or resolved != run_dir / "run.json"
        or info.get("project") != f"podobank-ui-{run_id}"
        or Path(str(info.get("env_file", ""))).resolve(strict=True).parent != run_dir
        or Path(str(info.get("evidence_dir", ""))).resolve()
        != (ROOT / ".evidence" / "ui" / run_id).resolve()
    ):
        raise VerificationError(
            "The run file does not point to a verifier-owned temporary project."
        )
    return info


def env_for(run_info: dict[str, object]) -> tuple[dict[str, str], list[str]]:
    values = example_values()
    values.update(
        {
            "COMPOSE_ENV_FILE": str(run_info["env_file"]),
            "API_PORT": str(run_info["api_origin"]).rsplit(":", maxsplit=1)[1],
            "FRONTEND_PORT": str(run_info["frontend_origin"]).rsplit(":", maxsplit=1)[1],
        }
    )
    # The env file is the sole source of Compose interpolation values.
    with Path(str(run_info["env_file"])).open(encoding="utf-8") as source:
        for line in source:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name, value = stripped.split("=", maxsplit=1)
                values[name] = value
    return compose_environment(Path(str(run_info["env_file"])), values), list(
        run_info.get("secrets", [])
    )


def compose_for(run_info: dict[str, object]) -> tuple[list[str], dict[str, str], list[str]]:
    env_file = Path(str(run_info["env_file"]))
    environment, secrets = env_for(run_info)
    return compose_base(str(run_info["project"]), env_file), environment, secrets


def verify_compose_config(
    compose: list[str], environment: dict[str, str], secrets: list[str]
) -> None:
    run(
        [*compose, "config", "--quiet"],
        label="Validating the isolated Compose model.",
        environment=environment,
        secrets=secrets,
    )
    rendered = run(
        [*compose, "config", "--format", "json"],
        label="Checking the frontend and API remain on separate loopback origins.",
        environment=environment,
        secrets=secrets,
    )
    try:
        services = json.loads(rendered)["services"]
        frontend = services["frontend"]
        api = services["api"]
        frontend_port = frontend["ports"][0]
        api_port = api["ports"][0]
        api_origin = frontend["build"]["args"]["VITE_API_ORIGIN"]
        allowed_origins = api["environment"]["FRONTEND_ORIGINS"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise VerificationError(
            "Could not inspect the rendered frontend Compose service."
        ) from error

    expected_api_origin = f"http://localhost:{api_port.get('published')}"
    expected_frontend_origin = f"http://localhost:{frontend_port.get('published')}"
    if isinstance(allowed_origins, str):
        origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]
    elif isinstance(allowed_origins, list):
        origins = allowed_origins
    else:
        origins = []

    if (
        frontend_port.get("host_ip") != "127.0.0.1"
        or frontend_port.get("target") != 80
        or api_port.get("host_ip") != "127.0.0.1"
        or api_port.get("target") != 8000
        or api_origin != expected_api_origin
        or expected_frontend_origin not in origins
    ):
        raise VerificationError("The frontend must be loopback-only and call the API directly.")

    nginx_config = (FRONTEND / "nginx.conf").read_text(encoding="utf-8")
    if "proxy_pass" in nginx_config or "/api/" in nginx_config:
        raise VerificationError("Nginx must serve the frontend without proxying API requests.")


def host_url(
    compose: list[str],
    service: str,
    container_port: int,
    environment: dict[str, str],
    secrets: list[str],
) -> str:
    output = run(
        [*compose, "port", service, str(container_port)],
        label=f"Resolving the isolated {service} port.",
        environment=environment,
        secrets=secrets,
    )
    match = re.search(r":(\d+)$", output.splitlines()[-1].strip())
    if match is None:
        raise VerificationError(f"Could not parse the published port for {service}.")
    return f"http://localhost:{match.group(1)}"


def launch(run_info: dict[str, object]) -> None:
    compose, environment, secrets = compose_for(run_info)
    verify_compose_config(compose, environment, secrets)
    run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        label="Checking the local Docker engine.",
        environment=environment,
        secrets=secrets,
    )
    run(
        [*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "300", "api", "frontend"],
        label="Building and starting the isolated database, API, and mobile UI.",
        environment=environment,
        timeout=START_TIMEOUT_SECONDS,
        secrets=secrets,
    )
    run(
        [*compose, "exec", "-T", "api", "podobank-api", "init-db"],
        label="Preparing the isolated database with repository demo data.",
        environment=environment,
        secrets=secrets,
    )
    fixtures = run_info["fixtures"]
    setup_payload = json.dumps(fixtures, ensure_ascii=False)
    # Feed the fixture data as stdin without putting credentials in process arguments.
    fixture_summary = run(
        [*compose, "exec", "-T", "api", "python", "-c", FIXTURE_SETUP],
        label="Creating isolated recipient, customer, and overdue-loan fixtures.",
        environment=environment,
        timeout=180,
        input_text=setup_payload + "\n",
        secrets=secrets,
    )
    try:
        sanitized_fixture_summary = json.loads(fixture_summary)
    except json.JSONDecodeError as error:
        raise VerificationError(
            "The isolated fixture setup returned invalid verification data."
        ) from error
    evidence_dir = Path(str(run_info["evidence_dir"]))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "fixture-summary.json").write_text(
        json.dumps(sanitized_fixture_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    actual_api_origin = host_url(compose, "api", 8000, environment, secrets)
    actual_frontend_origin = host_url(compose, "frontend", 80, environment, secrets)
    if (
        actual_api_origin != run_info["api_origin"]
        or actual_frontend_origin != run_info["frontend_origin"]
    ):
        raise VerificationError(
            "Compose published a port different from the isolated run settings."
        )
    write_run_info(run_info)


def http_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8", errors="replace")


def doctor(run_info: dict[str, object]) -> None:
    compose, environment, secrets = compose_for(run_info)
    services = run(
        [*compose, "ps", "--services"],
        label="Checking this run owns running database, API, and frontend services.",
        environment=environment,
        secrets=secrets,
    ).splitlines()
    if not {"db", "api", "frontend"}.issubset(set(services)):
        raise VerificationError("The isolated database, API, and frontend are not all running.")

    api_origin = host_url(compose, "api", 8000, environment, secrets)
    frontend_origin = host_url(compose, "frontend", 80, environment, secrets)
    if api_origin != run_info["api_origin"] or frontend_origin != run_info["frontend_origin"]:
        raise VerificationError("The running services do not match this run file's ports.")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_error = "services not ready"
    while time.monotonic() < deadline:
        try:
            http_text(f"{api_origin}/health")
            page = http_text(frontend_origin)
            if "포도뱅크" in page and '<div id="app"></div>' in page:
                print("The isolated API health endpoint and Vue application are ready.", flush=True)
                return
            last_error = "frontend document does not contain the expected application shell"
        except (HTTPError, URLError, OSError, ValueError) as error:
            last_error = type(error).__name__
        time.sleep(2)
    raise VerificationError(f"The isolated application did not become ready: {last_error}")


def npm_command(command: list[str], *, label: str, cwd: Path, environment: dict[str, str]) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise VerificationError(f"{label} failed: {type(error).__name__}") from error
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode:
        raise VerificationError(f"{label} failed (exit {completed.returncode}).\n{output}")
    if output.strip():
        print(output.rstrip(), flush=True)


def verify_node_runtime() -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None or npm is None:
        raise VerificationError("Node.js 26.13.0 and npm are required for frontend checks.")
    version = subprocess.run(
        [node, "--version"], capture_output=True, text=True, check=False, timeout=10
    )
    if version.returncode or version.stdout.strip() != "v26.13.0":
        actual = version.stdout.strip() if version.returncode == 0 else "unavailable"
        raise VerificationError(f"Frontend checks require Node.js v26.13.0; found {actual}.")


def quality() -> None:
    verify_node_runtime()
    environment = os.environ.copy()
    for name in ("NODE_OPTIONS", "NPM_CONFIG_PREFIX", "npm_config_prefix"):
        environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="podobank-ui-quality-") as temporary_directory:
        frontend_copy = Path(temporary_directory) / "frontend"
        shutil.copytree(
            FRONTEND,
            frontend_copy,
            ignore=shutil.ignore_patterns(
                "node_modules", "dist", "test-results", "playwright-report", ".vite"
            ),
        )
        npm_command(
            ["npm", "ci"],
            label="Installing locked frontend dependencies.",
            cwd=frontend_copy,
            environment=environment,
        )
        npm_command(
            ["npm", "run", "check"],
            label="Running frontend lint, format, and unit checks.",
            cwd=frontend_copy,
            environment=environment,
        )
        npm_command(
            ["npm", "run", "build"],
            label="Building the production frontend.",
            cwd=frontend_copy,
            environment=environment,
        )


def browser_environment(run_info: dict[str, object], evidence_dir: Path) -> dict[str, str]:
    fixtures = run_info["fixtures"]
    environment = os.environ.copy()
    for name in tuple(environment):
        if name == "NODE_OPTIONS" or name.startswith("PODOBANK_UI_"):
            environment.pop(name, None)
    environment.update(
        {
            "PODOBANK_UI_URL": str(run_info["frontend_origin"]),
            "PODOBANK_UI_API_ORIGIN": str(run_info["api_origin"]),
            "PODOBANK_UI_EVIDENCE_DIR": str(evidence_dir),
            "PODOBANK_UI_OUTPUT_DIR": str(evidence_dir / "test-results"),
        }
    )
    for name in ("customer", "employee", "approval", "rejection", "overdue"):
        environment[f"PODOBANK_UI_{name.upper()}_PHONE"] = fixtures[name]["phone"]
        environment[f"PODOBANK_UI_{name.upper()}_PASSWORD"] = fixtures[name]["password"]
    environment["PODOBANK_UI_RECIPIENT_PHONE"] = fixtures["recipient"]["phone"]
    return environment


def run_browser_tests(run_info: dict[str, object]) -> None:
    evidence_dir = Path(str(run_info["evidence_dir"]))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(str(run_info["run_dir"]))
    frontend_copy = temporary_root / "frontend"
    if frontend_copy.exists():
        shutil.rmtree(frontend_copy)
    shutil.copytree(
        FRONTEND,
        frontend_copy,
        ignore=shutil.ignore_patterns(
            "node_modules", "dist", "test-results", "playwright-report", ".vite"
        ),
    )
    environment = browser_environment(run_info, evidence_dir)
    runner = os.environ.get("PODOBANK_UI_TEST_RUNNER", "").strip().lower()
    if not runner:
        runner = "container" if sys.platform.startswith("linux") else "host"
    if runner == "host":
        verify_node_runtime()
        npm_command(
            ["npm", "ci"],
            label="Installing locked browser-test dependencies.",
            cwd=frontend_copy,
            environment=environment,
        )
        npm_command(
            ["npm", "run", "test:e2e"],
            label="Driving the app in a 384 × 832 mobile browser.",
            cwd=frontend_copy,
            environment=environment,
        )
        return
    if runner != "container":
        raise VerificationError("PODOBANK_UI_TEST_RUNNER must be 'container' or 'host'.")
    if not sys.platform.startswith("linux"):
        raise VerificationError(
            "The Playwright container runner requires Linux; set PODOBANK_UI_TEST_RUNNER=host."
        )

    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--ipc=host",
        "--network=host",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--volume",
        f"{frontend_copy}:/work",
        "--volume",
        f"{evidence_dir}:/evidence",
        "--workdir",
        "/work",
    ]
    environment["PODOBANK_UI_EVIDENCE_DIR"] = "/evidence"
    environment["PODOBANK_UI_OUTPUT_DIR"] = "/evidence/test-results"
    docker_environment = os.environ.copy()
    for name, value in environment.items():
        if name.startswith("PODOBANK_UI_"):
            docker_environment[name] = value
            command.extend(["--env", name])
    command.extend(
        [
            PLAYWRIGHT_IMAGE,
            "bash",
            "-lc",
            "npm ci && npm run test:e2e",
        ]
    )
    run(
        command,
        label="Driving all customer and employee flows in a 384 × 832 Playwright browser.",
        environment=docker_environment,
        timeout=START_TIMEOUT_SECONDS,
        secrets=list(run_info.get("secrets", [])),
    )


def cleanup_run(run_info: dict[str, object], *, suppress_errors: bool = False) -> None:
    compose, environment, secrets = compose_for(run_info)
    result = subprocess.run(
        [*compose, "down", "--volumes", "--remove-orphans", "--timeout", "15"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        message = redact(
            "\n".join(part for part in (result.stdout, result.stderr) if part.strip()), secrets
        )
        if suppress_errors:
            print("warning: isolated UI resources may need cleanup", file=sys.stderr)
            if message:
                print(message, file=sys.stderr)
            return
        raise VerificationError(f"Could not clean up the isolated UI project.\n{message}")
    shutil.rmtree(Path(str(run_info["run_dir"])), ignore_errors=False)
    print(
        f"Stopped only {run_info['project']}; evidence remains at {run_info['evidence_dir']}.",
        flush=True,
    )


def verify_docker_compose() -> None:
    if shutil.which("docker") is None:
        raise VerificationError("Docker CLI and Compose v2 are required for UI verification.")
    completed = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=CONFIG_TIMEOUT_SECONDS,
    )
    if completed.returncode:
        raise VerificationError("Docker Compose v2 is required for UI verification.")


def main() -> int:
    arguments = parser().parse_args()
    if arguments.quality:
        quality()
        print("Frontend quality checks passed.", flush=True)
        return 0

    verify_docker_compose()
    if arguments.config_only:
        run_info = make_run()
        try:
            compose, environment, secrets = compose_for(run_info)
            verify_compose_config(compose, environment, secrets)
        finally:
            shutil.rmtree(Path(str(run_info["run_dir"])), ignore_errors=True)
            shutil.rmtree(Path(str(run_info["evidence_dir"])), ignore_errors=True)
        print("Compose UI configuration passed.", flush=True)
        return 0

    if arguments.smoke:
        run_info = make_run()
        try:
            launch(run_info)
            doctor(run_info)
            run_browser_tests(run_info)
        finally:
            cleanup_run(run_info, suppress_errors=sys.exc_info()[0] is not None)
        print(f"UI smoke verification passed; evidence: {run_info['evidence_dir']}", flush=True)
        return 0

    if arguments.launch:
        run_info = make_run()
        try:
            launch(run_info)
            doctor(run_info)
        except BaseException:
            cleanup_run(run_info, suppress_errors=True)
            raise
        print(f"Run file: {Path(str(run_info['run_dir'])) / 'run.json'}", flush=True)
        print(f"Evidence: {run_info['evidence_dir']}", flush=True)
        return 0

    run_info = read_run_info(arguments.run_file)
    if arguments.doctor:
        doctor(run_info)
        print("UI Doctor passed.", flush=True)
        return 0
    if arguments.drive:
        doctor(run_info)
        run_browser_tests(run_info)
        print(f"UI browser flows passed; evidence: {run_info['evidence_dir']}", flush=True)
        return 0
    if arguments.cleanup:
        cleanup_run(run_info)
        return 0
    raise VerificationError("No UI verification mode was selected.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
