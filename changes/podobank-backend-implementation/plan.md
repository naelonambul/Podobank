# 구현 계획

## 요약

병합된 제품 기준을 따라 SQLite를 사용하는 FastAPI 기능을 완성한다. 고객 Kakao 가입·로그인과 선택적 비밀번호, 직원 로컬 로그인, JWT HttpOnly 세션, 기본 계좌 발급, 입금·출금·계좌 이체, 대출 신청·직원 승인·거절, 월 상환과 연체 수납을 구현한다. SQLAlchemy Core의 Engine·Connection·트랜잭션으로 직접 SQL을 실행하고 ORM은 사용하지 않는다. 개발 SQLite는 기존 `reset-db`로 자유롭게 재구성할 수 있다.

이 변경은 백엔드 기능에 한정한다. MariaDB 전환은 SQLite 백엔드 동작이 검증된 후 별도 단계로 진행한다. Alloy·Loki·Prometheus·Grafana의 구성과 이벤트 상세 필드·지표는 관측 단계에서 정하고, Vue 3·Nginx 화면은 UI 단계에서 구현한다.

## 역할 구분

- **사람 소유자(사용자):** 기준선과 이 plan을 승인하고 각 커밋을 검토하며 PR을 병합한다.
- **코딩 에이전트(Codex):** 승인된 plan과 `write_scope`에 따라 API·SQL·테스트를 구현하고 검증한다. 사람 소유자의 승인이나 병합을 대신하지 않는다.
- **개발용 SQLite:** 가상 사용자·계좌만 보관한다. 초기화 및 스키마 재구성은 `APP_ENV=development`인 SQLite에서만 허용한다.

## 변경 파일 및 구성요소

<!-- 모든 변경 파일은 change.json의 write_scope에 포함되어야 한다. -->

- `backend/podobank_api/app.py`: FastAPI 앱을 조립하고 기능별 router를 등록한다. 금융 규칙과 SQL을 넣지 않는다.
- `backend/podobank_api/features/auth/{api.py,dependencies.py,kakao.py,service.py,sql.py}`: 카카오·로컬 인증, 세션, 권한 확인과 인증 SQL.
- `backend/podobank_api/features/accounts/{api.py,service.py,sql.py}`: 고객 계좌 조회, 기본 계좌 발급, 잔액 확인·변경을 소유한다.
- `backend/podobank_api/features/transactions/{api.py,service.py,sql.py}`: 입금·출금·이체, 수취인 검색, 거래 내역과 거래 원장을 소유한다. 결제는 별도 기능이 아니라 이체 흐름을 재사용한다.
- `backend/podobank_api/features/loans/{api.py,service.py,sql.py,worker.py}`: 상품 조회, 신청, 직원 승인·거절, 상환 회차·연체와 자동 상환 작업자를 소유한다.
- `backend/podobank_api/{database.py,schema.py,seed.py,settings.py,cli.py}`: SQLite 연결·트랜잭션 설정, 개발 스키마 생성·초기화, 샘플 데이터, 환경 설정과 운영 명령을 제공한다. SQLite 스키마는 초기 개발용이며 승인된 `reset-db`로 자유롭게 재생성할 수 있다.
- `backend/tests/{auth,accounts,transactions,loans}/**`: 기능 경계에 맞춘 임시 SQLite 기반 API·서비스 검사. Kakao 외부 호출은 대체 가능한 provider로 주입한다.
- `pyproject.toml`, `uv.lock`: `pwdlib[argon2]` 비밀번호 해시, `PyJWT` 세션 토큰, `httpx` Kakao 사용자 검증 의존성과 검사 도구 잠금 정보를 반영한다. 구현 전에 Context7로 현재 공식 문서를 확인한다.
- `.env.example`: Kakao OAuth, JWT 비밀값, 직원 초기 전화번호·비밀번호, CORS origin의 로컬 설정 예시. 실제 비밀은 커밋하지 않는다.
- `compose.yaml`: FastAPI API와 단일 `repayment-worker` 서비스, health 의존성, SQLite named volume을 정의한다. MariaDB는 추가하지 않는다.
- `README.md`: API 흐름, 환경 변수, 가상 직원 계정 설정, SQLite·Compose 실행과 검사 방법을 설명한다.
- `scripts/verify_backend.py`: 하나의 재현 가능한 백엔드 검증 진입점으로 Ruff lint·format과 전체 기능 검사를 실행한다. 기존 `checks.json`의 백엔드 경로 매핑을 통해 `repo.py verify`와 CI가 같은 명령을 사용한다.

### 기능 폴더와 의존 방향

```text
backend/podobank_api/
  app.py
  cli.py
  database.py
  schema.py
  seed.py
  settings.py
  features/
    auth/{api.py,dependencies.py,kakao.py,service.py,sql.py}
    accounts/{api.py,service.py,sql.py}
    transactions/{api.py,service.py,sql.py}
    loans/{api.py,service.py,sql.py,worker.py}
backend/tests/
  auth/
  accounts/
  transactions/
  loans/
```

- 새 업무 기능은 `features/<기능>/`에 둔다. `api.py`는 HTTP 입력·응답과 router, `service.py`는 업무 규칙과 트랜잭션 조율, `sql.py`는 해당 기능 소유 테이블의 직접 SQL만 맡는다. 기능이 작을 때는 파일을 더 나누지 않는다.
- 기능 간 데이터 변경은 같은 SQLAlchemy Core `Connection`을 전달해 하나의 트랜잭션으로 묶는다. `accounts`는 계좌·잔액 변경 API를 소유하고, 거래·대출은 해당 업무 서비스 경로를 통해서만 잔액을 반영한다. 한 기능의 `sql.py`를 다른 기능에서 직접 가져오지 않는다.
- `app.py`는 조립 지점이고 `database.py`는 연결·트랜잭션 지점이다. 각 기능 API는 자신의 서비스에 의존한다. 업무 로직을 `app.py`나 한 파일에 계속 쌓지 않는다.
- 구조 자체로 강제할 수 없는 경계는 문서 규칙만 늘리지 않는다. 반복되는 위반이 확인되면 그때 Ruff 규칙이나 작은 정적 검사로 바꾼다. 이번 변경에는 별도 아키텍처 프레임워크나 import-linter를 추가하지 않는다.

## 작업 순서

1. `backend/podobank_api/features/{auth,accounts}/**`, `backend/podobank_api/{app.py,database.py,schema.py,seed.py,settings.py,cli.py}`, `backend/tests/auth/**`, `backend/tests/accounts/**`, `pyproject.toml`, `uv.lock`, `.env.example`에 인증과 초기 계좌를 구현한다. 계약은 `POST /auth/kakao`, `POST /auth/local`, `POST /auth/password`, `POST /auth/logout`, `GET /auth/me`, `GET /accounts/me`로 제공한다. Kakao access token은 FastAPI가 Kakao 사용자 정보 API로 확인하고 저장·로그에 남기지 않는다. 신규 고객은 전화번호, 나이, 성별, 혼인 상태, 직장 유무와 선택 비밀번호를 등록하며 전화번호 중복만 검사한다. 기존 Kakao 고객은 저장된 Kakao subject로 확인한다. 직원은 전화번호·비밀번호 로컬 로그인만 쓰며 초기 직원 한 명의 비밀번호는 환경 변수에서 받아 안전하게 해시해 저장한다. 비밀번호 해시는 Argon2id, 앱 세션은 서명된 JWT HttpOnly 쿠키로 처리하고 계정 권한은 매 요청 DB에서 확인한다. 고객이 처음 로그인할 때 계좌 한 개만 발급한다. 기본 시드에는 가상 프로필과 고유 전화번호·계좌번호를 가진 여러 고객과 직원 한 명을 제공하고, 같은 표시 이름을 가진 고객도 넣어 검색 결과의 구분을 확인한다. CORS는 명시된 `CORS_ALLOWED_ORIGINS`만 허용하고 필요한 method·header를 고정하며 credentials를 켜고 wildcard를 금지한다. Kakao HTTP provider를 교체 가능한 경계로 둬 테스트에는 실자격증명을 요구하지 않는다. 이 단계 검사 명령은 `python3 scripts/verify_backend.py --suite sqlite`이다.
2. `backend/podobank_api/features/{accounts,transactions}/**`, `backend/tests/{accounts,transactions}/**`에 입금·출금·계좌 이체·거래 내역과 수취인 검색을 구현한다. 계약은 `POST /accounts/me/deposits`, `/accounts/me/withdrawals`, `/accounts/me/transfers`, `GET /accounts/me/transactions`, `GET /recipients?query=...`로 제공한다. 결제는 이체 경로를 재사용한다. 검색은 계좌번호·전화번호·사용자 목록을 지원하고 이름이 겹칠 경우 계좌번호와 전화번호 일부를 함께 반환해 구분한다. 잔액은 정수 원으로 저장하고 금액 변경과 거래 원장은 같은 DB 트랜잭션에서 처리한다. 잔액 부족 시 잔액과 성공 원장을 변경하지 않는다. 이 단계 검사 명령은 `python3 scripts/verify_backend.py --suite sqlite`이다.
3. `backend/podobank_api/features/{accounts,loans}/**`, `backend/podobank_api/{schema.py,seed.py,cli.py}`, `backend/tests/loans/**`, `compose.yaml`에 대출과 상환을 구현한다. 계약은 `GET /loan-products`, `POST /loans/applications`, `GET /loans`, 직원 전용 `GET /staff/loans/applications`, `POST /staff/loans/applications/{id}/decision`, 고객 `POST /loans/{id}/repayments`로 제공한다. 자동차 구매 3천만 원/60개월, 전세자금 9천6백만 원/24개월, 주택 매매 3억6천만 원/360개월 무이자 상품을 시드한다. 고객은 대기·상환 중 대출이 없을 때 신청할 수 있고, 직원은 신청 조건을 바꾸지 않고 승인 또는 거절한다. 승인은 대출 상태, 즉시 입금, 상환 회차 생성을 한 트랜잭션으로 처리한다. 첫 회차는 승인일로부터 한 달이 지난 뒤의 첫 1일에 청구한다. Compose의 상환 작업자는 `features/loans/worker.py`에서 시작 시 밀린 회차를 처리한 뒤 매시간 due 회차를 확인한다. 잔액 부족은 부분 차감 없이 연체로 기록하고, 고객의 수동 상환은 월 상환액의 정수배만 허용해 오래된 회차부터 처리한다. 회차별 고유 제약과 조건부 상태 갱신으로 작업자 재시작·중복 실행을 멱등하게 만든다. 이 단계 검사 명령은 `python3 scripts/verify_backend.py --suite sqlite` 및 `docker compose config --quiet`이다.
4. `README.md`, `scripts/verify_backend.py`, `backend/tests/**`, `compose.yaml`을 정리하고 API와 worker를 별도 Compose 프로젝트·볼륨으로 빌드해 health, 상환 실행, SQLite 유지 동작을 확인한다. 기존 개발 named volume은 검사에서 삭제하지 않는다. 세 단계의 backend suite와 Ruff는 `python3 scripts/verify_backend.py --suite sqlite`로 재실행한다.
5. 전체 변경을 검토한 뒤 `python3 scripts/repo.py verify --change podobank-backend-implementation --full`을 실행한다. 통과한 증거로 `python3 scripts/repo.py close podobank-backend-implementation --evidence <전체-검증-증거-경로>`를 실행하고 closure 후보 상태를 확인한다. 구현 단계별 커밋을 검토 가능한 단위로 유지하고, 완성된 변경을 bot 계정으로 푸시해 `Change-ID: podobank-backend-implementation`이 포함된 PR을 연다.

## 테스트 및 증거

- API 테스트는 각 테스트마다 격리된 임시 SQLite를 사용한다. Kakao 인증 provider를 fake로 대체하고 실제 Kakao 자격증명·네트워크에 의존하지 않는다.
- 인증 검사는 신규·기존 고객 Kakao 로그인, 전화번호 중복, 비밀번호 미설정/설정, 고객 비밀번호 설정, 직원 로컬 로그인, HttpOnly 쿠키, 역할별 API 접근, 첫 계좌 중복 발급과 명시적 CORS origin을 확인한다.
- 거래 검사는 입금·출금·이체·수취인 검색·거래 내역, 같은 이름 고객의 구분, 잔액 부족 무변경, 원장 원자성을 확인한다.
- 대출 검사는 상품 시드, 중복 신청 차단, 직원 승인·거절 권한, 승인 즉시 입금, 첫 상환일, 매월 1일 회차, 연체, 정수배 수동 상환, 작업자 반복 실행을 고정 날짜로 확인한다.
- `docker compose config --quiet` 및 별도 Compose 프로젝트의 health·worker 동작을 확인한다. 테스트용 프로젝트만 정리하고 기본 개발 볼륨은 보존한다.
- `python3 scripts/repo.py verify --change podobank-backend-implementation --full` 전체 증거를 closure에 기록한다.
- 이벤트 상세 payload와 Prometheus metric은 이 변경에서 확정하지 않는다. 업무 기능 결과를 관측 코드에서 연결할 경계를 유지하고 세부 필드·지표는 후속 관측 변경에서 정한다.

## 위험과 완화

- Kakao API가 외부 서비스이므로 장애·응답 변경이 로그인에 영향을 줄 수 있다. provider 경계를 두고 HTTP timeout을 설정하며, API 테스트는 fake provider로 결정적으로 실행한다.
- 거래와 상환 중 일부만 반영되면 잔액이 달라질 수 있다. 잔액 변경·원장·회차 상태를 같은 SQLite 트랜잭션에서 처리하고 조건부 갱신과 고유 제약을 둔다.
- API와 상환 작업자가 같은 SQLite 파일에 접근한다. Compose는 상환 작업자 한 개만 실행하고 쓰기 트랜잭션을 짧게 유지하며 재처리 안전성을 검사한다.
- JWT 비밀값·초기 직원 비밀번호·Kakao 토큰이 노출될 수 있다. 환경 변수만 사용하고 인증 비밀과 프로필을 로그에 남기지 않는다. 비밀번호는 평문 저장을 금지한다.
- 개발 초기화가 다른 데이터베이스를 지울 수 있다. 기존 SQLite 및 development 안전 검사 외의 초기화 경로를 추가하지 않는다.

## 되돌리기 및 복구

- 병합 전 문제는 새 커밋으로 수정하고 전체 검증 및 closure를 갱신한다. 공유 기록을 다시 쓰지 않는다.
- 개발용 SQLite 스키마 변경은 기존 승인된 `reset-db`로 재생성할 수 있다. Compose named volume은 자동 삭제하지 않는다.
- 병합 후에는 후속 change packet으로 수정한다. MariaDB와 관측 파이프라인은 이 packet의 복구 범위에 포함하지 않는다.

## 미결 사항

제품 요구사항의 미결 사항은 없다. 이벤트 상세 필드와 Prometheus 지표는 소유자가 정한 순서에 따라 backend 기능 완료 후 관측 단계에서 확정한다.
