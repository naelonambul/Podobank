# 구현 계획

## 요약

이번 변경은 백엔드 개발 기반과 도구 설정을 완성한다. FastAPI health API, SQLite 스키마·샘플 데이터·개발 초기화 도구, Docker Compose 실행, 품질 검사, PyCharm/uv 잠금 파일, 스택별 ignore 규칙, Codex 프로젝트 범위 Serena MCP 설정을 제공한다. 고객 선택적 비밀번호 로그인과 직원 로컬 로그인 요구는 함께 승인된 spec에 기록한다. 로그인·금융 API, 대출 처리, MariaDB 연동은 이 변경의 범위가 아니며, 이번 변경이 병합된 뒤 별도 구현 변경으로 진행한다.

초기 기능 개발과 검증에는 SQLite를 사용하고 SQLAlchemy Core의 연결·트랜잭션 기능으로 직접 SQL을 실행한다. ORM은 사용하지 않는다. 관측 파이프라인과 Vue/Nginx UI는 후속 변경에서 구현한다.

## 역할 구분

- **사람 소유자(사용자):** 제품 결정을 내리고 intent·spec·plan을 승인하며 PR을 검토하고 병합한다.
- **코딩 에이전트(Codex):** 승인된 plan과 `write_scope` 안에서 구현·검증하고, 커밋·푸시·PR 작성을 맡는다. 사람 소유자의 승인이나 병합 결정을 대신하지 않는다.
- **개발용 SQLite:** 실제 금융정보가 없는 초기화 가능한 로컬 DB다. 사람 소유자와 코딩 에이전트 모두 이 DB를 비우고 스키마·관계·샘플 데이터를 다시 만들 수 있다. MariaDB나 개발 환경 외의 DB에는 같은 초기화 권한을 적용하지 않는다.

## 변경 파일 및 구성요소

<!-- 모든 변경 파일은 change.json의 write_scope에 포함되어야 한다. -->

- `spec.md`: 고객의 선택적 비밀번호 로그인과 직원 로컬 로그인 요구를 제품 기준에 반영한다.
- `backend/**`: FastAPI health API, 설정, SQLite 직접 SQL 접근, 초기화·시드 도구와 기반 테스트.
- `pyproject.toml`, `uv.lock`: Python 프로젝트 의존성과 Ruff 설정, uv로 생성한 잠금 파일.
- `.codex/config.toml`: 전역 `serena` MCP 항목은 비활성화하고 PodoBank 프로젝트 전용 `serena_podobank` 연결을 로컬 MCP endpoint로 지정한다. Git에 포함하며, 애플리케이션 이미지 빌드 컨텍스트에서는 제외한다.
- `compose.yaml`, `Dockerfile`, `.dockerignore`: FastAPI 컨테이너와 영속 SQLite 파일 실행 설정.
- `.gitignore`: PyCharm 프로젝트 파일, Python 가상환경·캐시, Vue/Node 의존성·빌드 산출물, MariaDB·관측 스택의 로컬 데이터 디렉터리를 제외한다. `uv.lock`과 패키지 잠금 파일은 제외하지 않는다.
- `.dockerignore`: IDE 파일, 언어별 캐시·테스트, 비밀·로컬 데이터와 프론트엔드 빌드 산출물을 이미지 컨텍스트에서 제외하고 소스·설정·잠금 파일은 유지한다.
- `.env.example`, `README.md`: 개발 환경 변수와 백엔드 실행 방법.
- `scripts/verify_backend.py`, `checks.json`: 격리된 Python 환경에서 Ruff와 SQLite 검사를 실행하고 기존 `core` 그룹에 등록한다. CI core 검사는 Python과 Git만 필요로 하며 `.github/workflows/**`는 수정하지 않는다.

## 작업 순서

1. `pyproject.toml`, `uv.lock`, `.codex/config.toml`, `backend/**`, `Dockerfile`, `compose.yaml`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `checks.json`, `scripts/verify_backend.py`에 FastAPI 프로젝트 기반, SQLite 연결·스키마·샘플 고객 및 계좌 시드, 개발 DB 초기화 도구, Docker Compose 환경, Serena 프로젝트 연결 및 검사 명령을 구성한다. `.codex/config.toml`은 전역 `serena` MCP 서버를 비활성화하고 PodoBank 전용 `serena_podobank` 연결을 `http://127.0.0.1:9121/mcp`에 둔다. 이 설정은 Git으로 공유하되 `.gitignore`에서는 제외하지 않고 `.dockerignore`에서 제외한다. PyCharm의 uv 프로젝트 인터프리터에서 생성·갱신한 `uv.lock`은 저장소에 포함하고, `.venv/`는 로컬에 둔다. `.gitignore`와 `.dockerignore`는 PyCharm 및 Python·Vue/Node·FastAPI·MariaDB·Alloy·Loki·Prometheus·Grafana 스택의 로컬 캐시, 빌드 산출물, 비밀, 런타임 데이터를 반영하되 소스와 잠금 파일은 유지한다. `reset-db`는 기본 샘플 시드 또는 `--no-seed` 빈 DB를 제공하고, `APP_ENV=development`의 SQLite URL에서만 허용한다. MariaDB와 개발 환경 외의 설정에서는 거부한다.
2. `docker compose config --quiet`, `python3 scripts/verify_backend.py --suite sqlite`, TOML 값과 ignore 동작 확인을 실행한다. TOML을 표준 라이브러리로 읽어 전역 `serena.enabled=false` 및 프로젝트 endpoint를 확인한다. `git check-ignore`와 Docker ignore 검토에서 `.codex/config.toml`이 Git 추적 대상이고 Docker 빌드 컨텍스트에는 포함되지 않음을 확인한다. Compose API 컨테이너가 health endpoint에 응답하고 재시작 뒤에도 SQLite 영속 볼륨의 데이터가 유지되는지 확인한다.
3. 승인된 `changes/podobank-backend/spec.md`를 루트 `spec.md`에 반영한 뒤 `python3 scripts/repo.py verify --change podobank-backend --full`을 실행한다. 모든 등록 검사가 통과하면 해당 증거로 `python3 scripts/repo.py close podobank-backend --evidence <전체-검증-증거-경로>`를 실행한다.
4. closure가 포함된 변경을 커밋하고 `agent-gh`로 푸시한 뒤 본문에 `Change-ID: podobank-backend`를 넣은 PR을 연다. 소유자가 검토·병합한 뒤 main의 push 검증과 closure anchor를 확인한다. 다음 백엔드 기능은 병합된 기준에서 별도 change packet으로 시작한다.

## 검증 및 증거

- `python3 scripts/verify_backend.py --suite sqlite`는 health API, SQLite 스키마·시드, 기본/빈 DB 초기화 및 안전 제한을 검증한다.
- `docker compose config --quiet`을 실행하고 Compose 컨테이너의 health 및 SQLite 영속성을 확인한다.
- `git check-ignore`로 PyCharm, Python, Node/Vue 및 로컬 서비스 데이터 산출물이 제외되는지 확인한다. `uv.lock`과 서비스 설정 파일은 제외되지 않아야 한다.
- Python `tomllib`으로 `.codex/config.toml`을 읽어 전역 Serena가 비활성화되고 PodoBank 프로젝트 연결이 `127.0.0.1:9121/mcp`를 가리키는지 확인한다. Git은 이 설정을 추적하고 Docker 빌드 컨텍스트는 `.codex/`를 제외해야 한다.
- `python3 scripts/repo.py verify --change podobank-backend --full`은 closure 직전의 전체 필수 검사를 실행한다. 증거 경로는 closure에 기록한다.

## 위험과 완화

- 개발 초기화 명령이 잘못된 DB를 지울 수 있다. 실행 전 개발 환경과 SQLite dialect를 모두 확인하고 조건이 다르면 삭제 전에 중단한다.
- `.gitignore`와 `.dockerignore`가 소스·설정 파일까지 가릴 수 있다. ignore 검사로 `uv.lock`, Compose 설정, 서비스 구성 파일이 제외되지 않는지 확인한다.
- SQLite 파일은 컨테이너 재생성에도 보존되어야 한다. Compose named volume을 사용하고 초기화 명령만 명시적 DB 재설정을 수행한다.

## 되돌리기 및 복구

- 기반 설정에 문제가 있으면 Compose 서비스를 중지하고 소스 설정을 수정한다. 로컬 SQLite 파일과 named volume은 자동 삭제하지 않는다.
- 공유 Git 기록을 다시 쓰거나 개발 DB 볼륨을 자동 삭제하지 않는다.
- 이번 범위 밖의 인증·금융 기능이 필요하면 별도 change packet으로 계획하고 승인받는다.

## 미결 사항

인증·거래·대출 동작은 후속 백엔드 구현 변경에서 다룬다. 이벤트 상세 필드와 Prometheus 지표, Grafana 대시보드 구성은 관측 단계에서 정한다.
