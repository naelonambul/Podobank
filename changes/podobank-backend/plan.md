# 구현 계획

## 요약

승인된 spec의 금융 기능과 카카오·로컬 인증을 FastAPI 백엔드로 구현한다. 초기 기능 개발과 검증에는 SQLite를 사용하고, 입출금·이체·대출 동작이 안정된 마지막 단계에서 테이블 구조를 확정해 MariaDB를 연동한다. SQLite 개발 DB는 자유롭게 초기화하고 테이블·관계를 바꿀 수 있게 하며, 샘플 데이터를 넣거나 빈 DB로 시작할 수 있는 개발 도구를 제공한다. SQLAlchemy Core의 연결·트랜잭션 기능으로 직접 작성한 SQL을 실행하고 ORM은 사용하지 않는다.

이번 변경은 백엔드에 한정한다. 관측 파이프라인과 Nginx/Vue 화면은 후속 변경에서 구현한다.

## 역할 구분

- **사람 소유자(사용자):** 제품 결정을 내리고 intent·spec·plan을 승인하며 PR을 검토하고 병합한다.
- **코딩 에이전트(Codex):** 승인된 plan과 `write_scope` 안에서 구현·검증하고, 커밋·푸시·PR 작성을 맡는다. 사람 소유자의 승인이나 병합 결정을 대신하지 않는다.
- **개발용 SQLite:** 실제 금융정보가 없는 초기화 가능한 로컬 DB다. 사람 소유자와 코딩 에이전트 모두 이 DB를 비우고 스키마·관계·샘플 데이터를 다시 만들 수 있다. MariaDB나 개발 환경 외의 DB에는 같은 초기화 권한을 적용하지 않는다.

## 변경 파일 및 구성요소

<!-- 모든 변경 파일은 change.json의 write_scope에 포함되어야 한다. -->

- `spec.md`: 승인된 제품 기준에 고객 선택적 비밀번호 로그인과 직원 로컬 로그인을 반영한다.
- `backend/**`: FastAPI 앱, 설정, 인증, 계좌·거래·대출 API, SQL 접근, 시드·초기화 도구, 상환 처리와 백엔드 테스트.
- `uv.lock`: PyCharm의 uv 프로젝트 인터프리터가 사용하는 의존성 잠금 파일로 저장소에 포함하고, `pyproject.toml` 변경과 함께 갱신한다. Python 가상환경 디렉터리 `.venv/`는 로컬에 둔다.
- `compose.yaml`, `Dockerfile`: FastAPI 컨테이너와 영속 SQLite 파일을 실행하고, MariaDB 연동 단계에 MariaDB 서비스를 추가한다.
- `.gitignore`: PyCharm 프로젝트 파일, Python 가상환경·캐시, Vue/Node 의존성·빌드 산출물, MariaDB와 관측 스택의 로컬 데이터 디렉터리를 제외한다. `uv.lock`과 패키지 잠금 파일은 제외하지 않는다.
- `.dockerignore`: PyCharm/IDE 파일, `.venv`, Python·Node 캐시와 테스트, 로컬 비밀·DB·관측 데이터, 프론트엔드 빌드 산출물을 이미지 컨텍스트에서 제외하고 소스·설정·잠금 파일은 유지한다.
- `pyproject.toml`: 애플리케이션 및 개발 의존성과 Ruff 설정.
- `scripts/verify_backend.py`, `checks.json`: 격리된 Python 환경에서 Ruff와 SQLite 테스트를 실행하고 기존 `core` 검사 그룹에 등록한다. core 검사는 Python과 Git만 필요로 하며 `.github/workflows/**`는 수정하지 않는다. MariaDB Compose 통합 검사는 개발 환경에서 별도로 실행한다.
- `.env.example`, `.gitignore`, `README.md`: 로컬 Kakao/JWT 설정 예시, 비밀·로컬 DB 파일 제외, 실행 방법.

## 작업 순서

1. `pyproject.toml`, `uv.lock`, `backend/**`, `Dockerfile`, `compose.yaml`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `checks.json`, `scripts/verify_backend.py`에 FastAPI 패키지, 잠금 의존성 정보, SQLite 연결, 직접 작성한 SQL 실행, 기본 시드, Docker Compose 실행 환경과 재현 가능한 검사 명령을 만든다. PyCharm의 uv 프로젝트 인터프리터에서 생성·갱신한 `uv.lock`은 커밋하고, 로컬 가상환경 `.venv/`는 커밋하지 않는다. `.gitignore`와 `.dockerignore`에는 PyCharm 및 Python·Vue/Node·FastAPI·MariaDB·Alloy·Loki·Prometheus·Grafana 스택의 로컬 캐시, 빌드 산출물, 비밀, 런타임 데이터를 반영하되 소스와 잠금 파일은 유지한다. SQLite 파일은 Compose 영속 볼륨에 둔다. 사람 소유자와 코딩 에이전트가 SQLite의 모든 테이블과 관계를 지우고 다시 만들 수 있도록 `podobank_api.cli reset-db` 명령을 제공하며, 기본 샘플 시드 또는 `--no-seed` 빈 DB를 선택할 수 있게 한다. 이 명령은 개발 환경의 SQLite URL에서만 동작하고 MariaDB 및 개발 환경이 아닌 설정에서는 거부한다. `docker compose config --quiet`으로 Compose 설정을 확인하고 `python3 scripts/verify_backend.py --suite sqlite`와 초기화 명령 테스트로 초기 검사 구성을 검증한다.
2. `backend/**`, `pyproject.toml`, `.env.example`, `README.md`에서 승인된 `spec.md`의 카카오·로컬 인증을 구현한다. 고객은 카카오 OAuth 가입 시 비밀번호를 선택적으로 설정하고, 비워 두면 카카오 전용 계정으로 남으며 인증된 카카오 세션에서 나중에 비밀번호를 설정할 수 있다. 설정한 계정만 휴대전화번호·비밀번호 로컬 로그인을 허용한다. 은행 직원은 로컬 로그인만 사용한다. 비밀번호는 안전한 단방향 해시로 저장하고, 직원 초기 비밀번호는 `BANK_EMPLOYEE_INITIAL_PASSWORD` 환경 변수에서 받아 해시로 시드한다. JWT HttpOnly 쿠키와 DB 역할 확인을 두 로그인 방식에 공통 적용한다. 휴대전화번호 중복 확인(SMS 인증 없음), 나이·성별(남성/여성)·혼인 상태·직장 유무 등록, 첫 고객 로그인 시 기본 계좌 발급을 구현한다. 직원 계정 1명과 가상 프로필을 가진 샘플 고객·계좌를 시드한다. CORS는 프론트엔드 origin, 필요한 method·header만 명시하고 credentials를 허용한다. Kakao 연동 테스트는 실제 자격 증명 없이 대체 가능한 provider를 사용한다. `python3 scripts/verify_backend.py --suite auth-account`로 고객의 두 로그인 경로, 비밀번호 미설정·설정, 직원 로컬 로그인·권한, 기본 계좌 중복 발급을 검증한다.
3. `backend/**`에 입금·출금·계좌 이체와 수취인 검색(계좌번호·휴대전화번호·사용자 목록)을 구현한다. 사용자 이름이 겹치면 휴대전화 뒷자리나 계좌번호로 구분한다. 결제는 계좌 이체로 처리하고, 잔액 변경과 거래 기록은 한 트랜잭션에서 처리한다. `python3 scripts/verify_backend.py --suite transactions`로 정상 처리, 잔액 부족 시 무변경, 원자성을 검증한다.
4. `backend/**`에 사전 등록 대출 상품, 대출 신청, 직원 전용 승인·거절, 승인 즉시 입금, 매월 1일 자동 상환, 연체 및 월 상환액 정수배 수납을 구현한다. 상품은 자동차 구매 3천만 원/60개월, 전세자금 9천6백만 원/24개월, 주택 매매 3억6천만 원/360개월이며 모두 무이자다. 대기 또는 상환 중인 대출은 사용자당 하나만 허용한다. 첫 회차는 승인일부터 한 달이 지난 뒤 첫 1일에 청구한다. 예정 회차 처리는 재시작·중복 실행에도 중복 차감되지 않게 한다. 이벤트에는 개인 프로필이나 인증 비밀을 넣지 않는다. `python3 scripts/verify_backend.py --suite loans`로 승인, 거절, 상환일, 연체, 재처리를 검증한다.
5. SQLite에서 백엔드 동작 검증이 끝나면 `backend/**`, `compose.yaml`, `pyproject.toml`의 테이블 구조를 확정하고 MariaDB DDL·드라이버·연결 설정을 추가한다. 개발 환경에서 `docker compose --profile mariadb up -d mariadb`로 MariaDB를 실행한 뒤 `python3 scripts/verify_backend.py --suite mariadb`로 같은 API 동작과 시드 상품·직원 계정을 확인한다. 개발 DB 볼륨을 삭제하지 않는다.
6. `README.md`, `backend/tests/**`, `checks.json`, `scripts/verify_backend.py`를 정리하고 `python3 scripts/repo.py verify --change podobank-backend --full`을 실행한다. 모든 등록 검사가 통과한 뒤 `python3 scripts/repo.py close podobank-backend --evidence <전체-검증-증거-경로>`로 closure를 작성한다.
7. 전체 diff와 상태를 검토해 `agent-git`으로 커밋하고 `agent-gh`로 푸시한 뒤 본문에 `Change-ID: podobank-backend`를 포함한 PR을 연다. 소유자가 PR을 검토하고 병합한 뒤 main의 push 검증과 closure anchor를 확인한다.

## 검증 및 증거

- API 테스트는 임시 SQLite 데이터베이스를 사용하고, 거래 실패 때 잔액과 거래 내역이 일관되게 유지되는지 확인한다.
- 개발 DB 초기화는 SQLite 개발 환경에서만 허용한다. 기본 시드로 재생성하는 경우와 `--no-seed`로 빈 DB를 만드는 경우를 테스트하고 MariaDB 연결에서는 초기화가 거부되는지 확인한다.
- 대출 테스트는 날짜를 고정해 첫 상환일, 매월 1일 차감, 연체, 정수배 수납 및 중복 실행 방지를 확인한다.
- `python3 scripts/verify_backend.py --suite <sqlite|auth-account|transactions|loans>`는 단계별 검사와 테스트를 실행한다. 이 검사는 격리된 Python 환경을 사용하며 Docker를 요구하지 않는다.
- MariaDB 연동 완료 후 `docker compose --profile mariadb up -d mariadb`와 `python3 scripts/verify_backend.py --suite mariadb`를 실행해 같은 핵심 API 계약을 별도로 검증한다. 테스트용 데이터베이스는 개발 데이터와 분리한다.
- `checks.json`에 등록한 전체 검사와 Ruff lint/format 검사는 `python3 scripts/repo.py verify --change podobank-backend --full`로 실행한다. 기존 `core` 그룹은 Python과 Git만 필요로 하며 새 CI workflow는 만들지 않는다.
- 전체 검증 증거 경로를 `repo.py close`에 전달하고, PR의 `summary` 검사가 통과해야 병합한다.

## 위험과 완화

- SQLite와 MariaDB의 SQL 차이로 동작이 달라질 수 있다. SQL은 직접 작성하되 각 DB에 맞는 DDL을 분리하고 동일한 API 계약 테스트를 양쪽에서 실행한다.
- 개발 초기화 명령이 잘못된 DB를 지울 수 있다. 실행 전 개발 환경과 SQLite dialect를 모두 확인하고 조건이 다르면 삭제 전에 중단한다.
- 이체·상환 중 일부 데이터만 기록되면 잔액이 틀어질 수 있다. 금액 변경과 원장·회차 기록을 같은 DB 트랜잭션에서 처리하고 실패 시 전체를 되돌린다.
- 자동 상환 작업이 재시작되거나 반복 실행되면 중복 차감될 수 있다. 회차별 처리 상태와 DB 제약을 사용해 처리를 멱등하게 만든다.
- CORS나 이벤트 로그에 인증 정보·개인 프로필이 노출될 수 있다. origin을 명시적으로 제한하고 로그에 민감 정보를 기록하지 않는다.
- 이 변경은 실제 카카오 키가 없어도 테스트 가능해야 한다. OAuth 키와 직원 Kakao 식별자는 `.env`로 주입하며 실제 값을 저장소에 넣지 않는다.

## 되돌리기 및 복구

- MariaDB 전환 전에 문제를 발견하면 SQLite 설정으로 되돌리고 Compose의 MariaDB 서비스는 실행하지 않는다. 로컬 SQLite 파일은 영속 볼륨에 보존한다.
- 전환 후 문제가 있으면 새 변경으로 수정한다. 공유 Git 기록을 다시 쓰거나 개발 DB 볼륨을 자동 삭제하지 않는다.
- 승인된 plan과 다른 구조 변경이 필요하면 구현을 멈추고 plan을 수정한 뒤 소유자 재승인을 받는다.

## 미결 사항

제품 동작 요구사항은 변경 패킷의 spec으로 확정한다. Kakao OAuth 키, JWT 비밀 키, 은행 직원 초기 비밀번호는 로컬 환경 설정으로 제공하며 저장소에 커밋하지 않는다. 이벤트 상세 필드와 Prometheus 지표는 관측 변경에서 정한다.
