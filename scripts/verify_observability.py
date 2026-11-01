#!/usr/bin/env python3
"""Validate and smoke-test the isolated local observability stack."""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "compose.yaml"
CONFIG_TIMEOUT_SECONDS = 60
START_TIMEOUT_SECONDS = 600
POLL_TIMEOUT_SECONDS = 120

EMIT_API_EVENT = """
import os
from sqlalchemy import text
from podobank_api.database import create_database_engine
from podobank_api.features.observability.events import configure_financial_event_logging
from podobank_api.features.transactions.service import TransactionService
from podobank_api.seed import DEMO_CUSTOMER_PHONE
from podobank_api.settings import Settings

configure_financial_event_logging(os.environ.get("FINANCIAL_EVENTS_PATH"))
settings = Settings.from_environment()
engine = create_database_engine(settings.database_url)
try:
    with engine.connect() as connection:
        user_id = connection.execute(
            text("SELECT id FROM users WHERE phone_number = :phone_number"),
            {"phone_number": DEMO_CUSTOMER_PHONE},
        ).scalar_one()
    TransactionService(engine).deposit(user_id=int(user_id), amount=1)
finally:
    engine.dispose()
"""

VERIFY_PIPELINE = """
import json
import time
import urllib.parse
import urllib.request
from urllib.error import URLError

def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())

def loki_has(operation):
    query = '{service="podobank-api",operation="' + operation + '",outcome="success"}'
    now_ns = int(time.time() * 1_000_000_000)
    parameters = urllib.parse.urlencode({
        "query": query,
        "start": str(now_ns - 600_000_000_000),
        "end": str(now_ns),
        "limit": "20",
        "direction": "backward",
    })
    result = get_json("http://loki:3100/loki/api/v1/query_range?" + parameters)
    return any(stream.get("values") for stream in result.get("data", {}).get("result", []))

def prometheus_has(operation):
    expression = (
        'podobank_financial_operations_total{operation="' + operation
        + '",outcome="success",reason="completed"}'
    )
    parameters = urllib.parse.urlencode({"query": expression})
    result = get_json("http://prometheus:9090/api/v1/query?" + parameters)
    samples = result.get("data", {}).get("result", [])
    return any(float(item.get("value", [0, "0"])[1]) >= 1 for item in samples)

expected = ("deposit", "repayment_batch")
deadline = time.monotonic() + 120
last_state = {}
while time.monotonic() < deadline:
    try:
        last_state = {
            operation: {
                "loki": loki_has(operation),
                "prometheus": prometheus_has(operation),
            }
            for operation in expected
        }
        if all(all(state.values()) for state in last_state.values()):
            print(json.dumps(last_state, sort_keys=True))
            raise SystemExit(0)
    except (OSError, ValueError, KeyError, URLError) as error:
        last_state = {"last_error": type(error).__name__}
    time.sleep(2)

print(json.dumps(last_state, sort_keys=True), file=__import__("sys").stderr)
raise SystemExit("timed out waiting for Loki events and Prometheus counters")
"""


class VerificationError(RuntimeError):
    """Raised when a required observability check fails."""


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


def compose_environment(env_file: Path, test_values: dict[str, str]) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        *test_values,
        "COMPOSE_ENV_FILE",
        "COMPOSE_FILE",
        "COMPOSE_PROJECT_NAME",
        "COMPOSE_PROFILES",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "COMPOSE_ENV_FILE": str(env_file),
            "API_PORT": "0",
            "DB_PORT": "0",
            "GRAFANA_PORT": "0",
        }
    )
    return environment


def run(
    command: list[str],
    *,
    label: str,
    environment: dict[str, str],
    timeout: int = CONFIG_TIMEOUT_SECONDS,
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


def write_test_environment(destination: Path) -> dict[str, str]:
    example = ROOT / ".env.example"
    values: dict[str, str] = {}
    for line in example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", maxsplit=1)
            values[name] = value

    values.update(
        {
            "API_PORT": "0",
            "DB_PORT": "0",
            "GRAFANA_PORT": "0",
            "GRAFANA_ADMIN_PASSWORD": f"verify-{uuid.uuid4().hex}-only",
            "MARIADB_ROOT_PASSWORD": f"root-{uuid.uuid4().hex}-only",
            "MARIADB_PASSWORD": f"db-{uuid.uuid4().hex}-only",
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


def verify_monitoring_port_bindings(compose: list[str], environment: dict[str, str]) -> None:
    run(
        [*compose, "config", "--quiet"],
        label="Checking the Compose configuration with isolated example values.",
        environment=environment,
    )
    rendered = run(
        [*compose, "config", "--format", "json"],
        label="Checking monitoring services do not publish host ports.",
        environment=environment,
    )
    try:
        services = json.loads(rendered)["services"]
        published = {
            name: services[name].get("ports", [])
            for name in ("alloy", "loki", "prometheus")
        }
        grafana_ports = services["grafana"].get("ports", [])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise VerificationError("Could not read the rendered monitoring service ports.") from error

    if any(published.values()):
        raise VerificationError("Alloy, Loki, and Prometheus must remain internal to Compose.")
    if (
        len(grafana_ports) != 1
        or grafana_ports[0].get("host_ip") != "127.0.0.1"
        or grafana_ports[0].get("target") != 3000
    ):
        raise VerificationError("Grafana must publish only its UI on 127.0.0.1:3000.")


def http_json(url: str, *, authorization: str | None = None) -> dict | list:
    headers = {"Accept": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    request = Request(url, headers=headers)
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def wait_for_grafana(base_url: str, *, username: str, password: str) -> None:
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    authorization = f"Basic {credentials}"
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_error = "not ready"
    while time.monotonic() < deadline:
        try:
            datasources = http_json(f"{base_url}/api/datasources", authorization=authorization)
            names = {item.get("name") for item in datasources if isinstance(item, dict)}
            dashboard = http_json(
                f"{base_url}/api/dashboards/uid/podobank-financial-operations",
                authorization=authorization,
            )
            if names >= {"Prometheus", "Loki"} and dashboard.get("dashboard", {}).get(
                "title"
            ) == "PodoBank Financial Operations":
                print("Grafana data sources and dashboard are provisioned.", flush=True)
                return
            last_error = "provisioned resources are incomplete"
        except (HTTPError, URLError, OSError, ValueError, AttributeError) as error:
            last_error = type(error).__name__
        time.sleep(2)
    raise VerificationError(f"Grafana provisioning check timed out: {last_error}")


def host_url(compose: list[str], service: str, container_port: int, environment: dict[str, str]) -> str:
    output = run(
        [*compose, "port", service, str(container_port)],
        label=f"Resolving the isolated {service} port.",
        environment=environment,
    )
    match = re.search(r":(\d+)$", output.splitlines()[-1].strip())
    if match is None:
        raise VerificationError(f"Could not parse the published port for {service}.")
    return f"http://127.0.0.1:{match.group(1)}"


def verify_smoke(compose: list[str], environment: dict[str, str], values: dict[str, str]) -> None:
    run(
        [*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "240"],
        label="Starting the isolated API and observability stack.",
        environment=environment,
        timeout=START_TIMEOUT_SECONDS,
    )
    run(
        [*compose, "exec", "-T", "api", "podobank-api", "init-db"],
        label="Preparing the isolated demo database.",
        environment=environment,
    )
    run(
        [*compose, "exec", "-T", "api", "python", "-c", EMIT_API_EVENT],
        label="Creating one demo deposit event through TransactionService.",
        environment=environment,
    )
    run(
        [
            *compose,
            "exec",
            "-T",
            "api",
            "podobank-api",
            "process-repayments",
            "--as-of-date",
            time.strftime("%Y-%m-%d", time.gmtime()),
        ],
        label="Creating one repayment-batch event through the scheduled CLI.",
        environment=environment,
    )
    run(
        [*compose, "exec", "-T", "api", "python", "-c", VERIFY_PIPELINE],
        label="Verifying both events in Loki and their counters in Prometheus.",
        environment=environment,
        timeout=POLL_TIMEOUT_SECONDS + 30,
    )
    grafana_url = host_url(compose, "grafana", 3000, environment)
    wait_for_grafana(
        grafana_url,
        username=values["GRAFANA_ADMIN_USER"],
        password=values["GRAFANA_ADMIN_PASSWORD"],
    )


def main() -> int:
    arguments = parser().parse_args()
    if shutil.which("docker") is None:
        raise VerificationError("Docker CLI is required for observability verification.")
    version = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=CONFIG_TIMEOUT_SECONDS,
    )
    if version.returncode:
        raise VerificationError("Docker Compose v2 is required for observability verification.")

    project = f"podobank-observability-{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="podobank-observability-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        env_file = temporary_root / "compose.env"
        values = write_test_environment(env_file)
        environment = compose_environment(env_file, values)
        compose = compose_base(project, env_file)
        try:
            verify_monitoring_port_bindings(compose, environment)
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
                    message = "isolated observability resources may need cleanup"
                    if sys.exc_info()[0] is None:
                        raise VerificationError(message)
                    print(f"warning: {message}", file=sys.stderr)

    print("Observability verification passed.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
