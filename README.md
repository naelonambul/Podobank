# 포도뱅크 (PodoBank)

개발 부트캠프 팀 포트폴리오용 가상 은행 프로젝트입니다. 백엔드는 FastAPI와 MariaDB를 사용하고 SQLAlchemy Core로 SQL을 직접 실행합니다. 관측 스택은 Docker Compose로 함께 실행하며 UI는 후속 단계에서 추가합니다.

## 백엔드 개발 환경

### Docker Compose

```sh
cp -n .env.example .env
docker compose up --build
```

`.env`가 이미 있으면 덮어쓰지 말고 `.env.example`의 새 설정 항목을 직접 추가합니다. MariaDB는 Oracle SQL 모드와 엄격한 데이터 검사를 켠 채 실행되며, 데이터는 `mariadb_data` 영속 볼륨에 보관됩니다. FastAPI는 `http://localhost:8000`에서 실행되고 `/health`가 상태를 반환합니다. API 시작은 기존 DB 스키마나 데이터를 변경하지 않습니다.

#### 금융 이벤트 관측

Compose는 금융 서비스 결과를 JSONL 이벤트 파일에 기록하고 Alloy가 Loki 로그와 Prometheus 카운터로 전달합니다. Grafana는 `http://localhost:${GRAFANA_PORT:-3000}`에서 열립니다. 로그인 계정과 암호는 `.env`의 `GRAFANA_ADMIN_USER`와 `GRAFANA_ADMIN_PASSWORD`이며, 예시 암호는 로컬 데모용이므로 `.env`에서 바꿀 수 있습니다. `PodoBank Financial Operations` 대시보드에는 성공·실패 추이와 최근 이벤트가 표시됩니다.

Loki는 로그를 30일, Prometheus는 지표를 15일 보관합니다. 원본 JSONL 입력은 별도의 `financial_events` named volume에 보관되고 자동 삭제되지 않습니다. 표준 `docker compose down`은 볼륨을 보존합니다. 원본 이벤트를 정리할 때는 Compose 프로젝트의 `financial_events` 볼륨만 명시적으로 제거합니다. 관측 컨테이너 포트는 호스트에 공개되지 않고 Grafana만 loopback에 바인딩됩니다.

관측 설정과 수집 흐름을 별도 Compose 프로젝트에서 확인하려면 다음을 실행합니다. 이 검증은 임시 환경 파일과 볼륨을 사용하고 완료 후 해당 프로젝트만 정리합니다.

```sh
python3 scripts/verify_observability.py --smoke
```

최초 실행은 다음 명령으로 스키마와 기본 시드 데이터를 준비합니다. 이 명령은 기존 테이블 구조와 데이터를 보존하며, 테이블 구조를 변경하지 않습니다. 개발 단계에서 스키마 정의가 달라지면 마이그레이션을 유지하지 않고 아래 `reset-db` 명령으로 `podobank_dev`를 비운 뒤 새 스키마를 생성합니다.

대출 기능은 원장 테이블의 거래 유형 제약을 확장합니다. `CREATE TABLE IF NOT EXISTS`는 이미 생성된 원장 제약을 바꾸지 않으므로, 기존 개발 DB에는 승인된 초기화 명령을 명시적으로 실행해 새 스키마를 적용해야 합니다. 이 명령은 `podobank_dev` 데이터를 삭제하므로 필요한 데이터를 먼저 보존하세요. API 시작이나 `init-db`는 기존 DB를 자동 초기화하지 않습니다.

```sh
docker compose exec api podobank-api init-db
```

개발 환경 초기화는 데모 고객과 계좌, 은행 직원 계정을 준비합니다. 직원 로그인은 `.env`의 `BANK_EMPLOYEE_PHONE`과 `BANK_EMPLOYEE_PASSWORD`를 사용합니다. Kakao 로그인을 쓰려면 Kakao Developers의 REST API 키, 클라이언트 시크릿, 등록된 리다이렉트 URI를 `.env`에 넣습니다.

### 입출금과 이체 API

로그인한 고객은 `POST /transactions/deposit`, `POST /transactions/withdrawal`, `POST /transactions/transfer`를 사용할 수 있습니다. 금액은 양의 정수 원(KRW)입니다. 입금은 데모용 잔액 충전이며 외부 결제망과 연결되지 않습니다. 이체 요청은 `{"destination_account_id": 123, "amount": 10000}` 형식으로 보내며, 대상 ID는 `GET /accounts/recipients` 응답에서 선택합니다. 출금·이체의 잔액 부족은 `409`, 잘못된 금액과 자기 계좌 이체는 `422`를 반환합니다.

수취인 목록은 `GET /accounts/recipients`에 `limit`, `offset`을 지정해 페이지 단위로 조회합니다. 정확한 계좌번호 또는 전화번호 검색은 `POST /accounts/recipients/search` 본문에 `{"query": "010-1234-5678"}`처럼 전달합니다. 전화번호는 숫자만 입력해도 됩니다. 검색어는 URL에 넣지 않아 접근 로그에 남지 않습니다. 응답의 계좌번호는 뒤 네 자리만 보이고 전화번호는 뒤 네 자리만 반환됩니다.

현재 고객 계좌의 원장 내역은 `GET /accounts/me/ledger`로 조회합니다. `start_at`, `end_at`은 UTC 오프셋을 포함한 ISO 8601 날짜 시각(예: `2026-11-01T00:00:00Z`)이며, 페이지 크기는 1~100, 오프셋은 0~10000입니다. 출금 원장 금액은 음수, 입금·수취 이체 금액은 양수입니다. 이체의 두 원장 행은 같은 `transaction_id`로 묶입니다.

잔액 변경과 원장 쓰기는 MariaDB InnoDB 트랜잭션에서 함께 커밋됩니다. 월별 파티션은 현재 UTC 월부터 12개월을 미리 만들고 그 이후 시각은 catch-all 파티션에 저장합니다. 보존 기간이 승인되기 전에는 원장 파티션을 자동 삭제하지 않습니다. API 요청 재시도에 대한 멱등성 키는 아직 제공하지 않으므로, 응답을 받지 못한 요청을 다시 보내면 별도 거래로 처리될 수 있습니다.

### 대출 API와 상환 실행

고객은 `GET /loans/products`로 대출 상품을 확인하고 `POST /loans/applications`에 `{"product_id": 1}`을 보내 신청합니다. 상품의 원금과 기간은 서버의 상품 조건을 사용합니다. `GET /loans/me`는 본인의 신청과 회차별 상환 상태를 반환합니다. 은행 직원은 `GET /loans/pending`에서 심사 대상을 확인한 뒤 `POST /loans/{application_id}/approve` 또는 `/reject`로 처리합니다. 승인 시 원금 입금, 상환 일정 생성, 대출 상태 변경이 하나의 InnoDB 트랜잭션으로 처리됩니다.

월 상환일은 승인일에서 한 달이 지난 뒤 처음 도래하는 UTC 월의 1일입니다. 이후 회차는 매월 1일입니다. 일일 상환 작업은 다음의 일회성 CLI를 호스트 스케줄러에서 UTC 기준으로 호출합니다. Compose API 컨테이너가 실행 중일 때의 cron 예시는 다음과 같습니다.

```cron
CRON_TZ=UTC
15 0 * * * cd /path/to/Podobank && docker compose exec -T api podobank-api process-repayments
```

`podobank-api process-repayments --as-of-date YYYY-MM-DD`로 처리 기준일을 지정할 수 있습니다. 기본값은 현재 UTC 날짜입니다. 작업이 중단된 동안 예정된 회차는 오래된 날짜부터 처리하며, 잔액이 부족한 회차는 일부 인출 없이 연체로 기록합니다. 연체 회차는 고객이 `POST /loans/me/{application_id}/repayments`에 월 납입액의 정수 배를 보내 직접 상환합니다. 스케줄러에서 명령의 종료 코드를 확인하고, 실패 시 같은 기준일로 다시 호출할 수 있습니다.

로컬 MariaDB의 전용 `podobank_test` 데이터베이스에서 API, 원자성, 동시성, 파티션 검증을 실행하려면 품질 검사 절차의 `DATABASE_URL`과 `APP_ENV=test`를 설정한 뒤 다음 명령을 실행합니다.

```sh
python3 scripts/verify_backend.py --suite mariadb
```

카카오 로그인은 credentials 포함 요청으로 `POST /auth/kakao/state`를 호출해 응답의 `authorization_url`로 이동합니다. 카카오 콜백에서 받은 `code`와 `state`도 credentials 포함 요청으로 `POST /auth/kakao/login`에 보내면 API가 브라우저의 단기 HttpOnly state 쿠키를 확인한 뒤 코드를 교환합니다.

프로덕션은 `API_ORIGIN`, `FRONTEND_ORIGINS`, Kakao 리다이렉트 URI를 HTTPS와 같은 hostname으로 설정해야 합니다. 세션·OAuth state 쿠키는 `SameSite=Lax`를 사용하므로 서로 다른 hostname 간 쿠키 전송을 지원하지 않습니다.

개발 DB의 데이터를 지우고 샘플 데이터와 함께 재생성하려면 `docker compose run --rm api podobank-api reset-db`를 실행합니다. 샘플 행 없이 빈 스키마만 만들려면 `docker compose run --rm api podobank-api reset-db --no-seed`를 실행합니다. 이 명령은 개발 환경의 `podobank_dev` 데이터베이스에만 허용됩니다.

### 로컬 Python API 실행

```sh
cp -n .env.example .env
docker compose up -d db
uv sync --extra dev
set -a && . ./.env && set +a
uv run podobank-api init-db
uv run uvicorn podobank_api.app:app --reload
```

로컬 API는 Compose의 MariaDB를 사용합니다. 로컬 API 실행 시 `.env`의 `DATABASE_URL`과 인증 설정을 셸 환경에 불러옵니다.

### 품질 검사

```sh
docker compose up -d db
docker compose exec -T db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"' <<'SQL'
CREATE DATABASE IF NOT EXISTS podobank_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON podobank_test.* TO 'podobank'@'%';
FLUSH PRIVILEGES;
SQL
set -a && . ./.env && set +a
DATABASE_URL="mysql+pymysql://${MARIADB_USER}:${MARIADB_PASSWORD}@127.0.0.1:${DB_PORT:-3306}/podobank_test" APP_ENV=test python3 scripts/verify_backend.py --suite mariadb
python3 scripts/repo.py verify --change podobank-auth-account-foundation --full
```

검증은 전용 `podobank_test` 데이터베이스에 연결합니다. 백엔드 검증 스크립트는 선언된 도구를 임시 Python 가상환경에 설치한 뒤 Ruff lint, Ruff format 검사와 MariaDB 통합 테스트를 실행합니다.

---

## Repository workflow

A small, agent-neutral starter repository for an AI-native software development lifecycle.

This template turns the repository itself into the shared control plane for planning, implementation, verification, and review. It is inspired by the AI-Native SDLC playbook and generalizes the artifact-driven workflow so it can be used with different coding agents.

## Core workflow

```text
idea
  -> changes/<id>/  (intent -> spec -> plan, each approved by the owner in order)
  -> implementation + verification, inside the change's write scope
  -> merge accepted intent/spec into the root baseline
  -> closure.json -> pull request -> merge (squash by default)
```

The root `intent.md` and `spec.md` are the durable product baseline. A new product's first change is `product-init`, which establishes them. `python3 scripts/repo.py status` computes every change's stage, freshness, approval and readiness. See `changes/README.md`.

## Quick start

1. Create a new repository from this GitHub template and clone it.
2. Remove the template's own closed change packets. Do this before protecting `main`, because it commits directly to it, and include the push: until then `status` fails with `frozen packet removed from the candidate`, which is expected.

   ```sh
   find changes -mindepth 1 -maxdepth 1 -type d ! -name _template -exec git rm -rq {} +
   git commit -m "Remove the template's closed change packets"
   git push origin main
   ```

3. Configure the repository once, as `docs/host-setup.md` describes: add it to the GitHub App's installation, so the App account can open pull requests, your account reviews and merges them, and `main` is protected.
4. Create the `product-init` packet: `python3 scripts/repo.py new <id> --kind product-init --title "<summary>"`. It copies the root `intent.md` and `spec.md` into the packet and adds them to `write_scope`. Pass `--scope` for every other path the change will touch, including `checks.json`, before the plan is approved, because the approval binds the scope.
5. Ask an agent to interrogate the idea until the intent is concrete, then approve `intent.md` yourself: `python3 scripts/repo.py approve <id> intent.md --by <you>` records a digest-bound claim for exactly the bytes you reviewed. The agent commits and pushes it.
6. Draft and approve `spec.md`, then the change's `plan.md`, in that order.
7. Implement only when `python3 scripts/repo.py status --change <id>` reports `readiness=ready`.
8. Verify, close and open a pull request as the Lifecycle section of `changes/README.md` describes, and review against `REVIEW.md`.

See `.agents/skills/sdlc-artifacts/SKILL.md` for the workflow.

## Repository control plane

- `AGENTS.md`: short, always-relevant repository invariants, gates, commands, and working rules.
- `REVIEW.md`: shared review rubric.
- `intent.md`, `spec.md`: durable product baseline (why, and what must be true).
- `changes/`: one packet per change, with its own plan; `changes/README.md` defines the model.
- `scripts/repo.py`: `status` computes change state and enforces gates; `verify` runs registered checks with routing and evidence; `new`, `approve` and `close` write packet records mechanically. Standard-library Python only.
- `checks.json`: the check registry (exact argv, cwd, timeout, routed paths, required tools, group). `status` warns when product files are tracked but only the template's own check is registered.
- `scripts/hooks/guard.py`: the agent-neutral in-session guard; see `scripts/hooks/README.md`. `.claude/settings.json` is the thin Claude Code adapter, and `status` checks that it points at tracked scripts.
- `.agents/skills/`: on-demand shared agent procedures. `.claude/skills/` holds thin symlink adapters.
- `docs/`: supporting, reference, and historical documentation only.
- `.github/`: the `Change-ID` pull-request template and the `repository` CI workflow. See `docs/host-setup.md` for one-time GitHub settings.

## Authority model

The root baseline plus approved change packets are the SDLC authority. `docs/` must not override them. Concurrent initiatives are separate change packets; one pull request carries one change.

## Enforcement layers

The repository enforces its rules in three layers, from hard to soft. Soft layers only make violations rare; the hard layer makes them visible.

1. **Hard, after the fact:** `repo.py status` and `verify`, the control-plane tests, and the required `summary` check in CI. These decide. They do not depend on any agent having read anything.
2. **In session:** `scripts/hooks/guard.py`, called from the agent's pre-edit and pre-command hooks, denies or asks as `scripts/hooks/README.md` lists. What it does not intercept, layer 1 catches. It is friction and an audit trail, not authentication.
3. **Advisory:** `AGENTS.md`, the skills and `REVIEW.md`. `docs/agent-surfaces.md` records how to check that a harness still delivers them.

## Scope

The template covers Plan, Design, Build, Test and Deploy as a loop of committed artifacts and gates. The Maintain stage (a trigger that invokes an agent with no person in the path and writes what it finds back as a new intent) is out of scope: the `incident` change kind is the entry point a project would wire a monitor or ticket trigger to, and nothing here runs unattended. An `incident` change is reproduce-first: its plan opens with a reproduction that fails on the base, and the same drive passing is its acceptance (`.agents/skills/sdlc-artifacts/SKILL.md`, Incidents; per-platform defaults in `.agents/skills/verification-map/references/platforms.md`).

## Agent neutrality

SDLC semantics belong to the repository, not to a specific agent interface. Features such as interrogation commands, plan modes, subagents, or agent-specific hooks are optional convenience layers.

CLI and program installation are machine responsibilities. The repository stores the shared procedures as version-controlled skills in `.agents/skills/`.

Optional tool unavailability must not silently change the SDLC gates.

Claude Code discovers these skills through thin `.claude/skills/<name>` symlinks to `.agents/skills/<name>`, runs the guard through `.claude/settings.json`, and loads `AGENTS.md` only when no project `CLAUDE.md` shadows it. The template therefore ships no `CLAUDE.md`. Codex reads `AGENTS.md` and discovers `.agents/skills/` natively, with no adapter, and has no observed hook integration. See `docs/agent-surfaces.md` for the smoke-tested surfaces and known gaps.

## Project initialization

When a project chooses its application stack, establish the repository-native build, test, lint, format-check, and type-check commands. Register each as a check in `checks.json`, and give checks that need a new toolchain their own group and CI job. Then do the one-time GitHub setup in `docs/host-setup.md`; settings such as branch protection are never inherited from a GitHub template.

## Source material

The structure is informed by Anthropic's *The AI-Native SDLC playbook* (August 21, 2026), especially its artifact-driven handoffs, human gates, short always-loaded context, skills, deterministic guardrails, feedback loops, independent verification, PR review policy, and continuous evals.
