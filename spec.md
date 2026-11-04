# Specification

## Summary

포도뱅크(PodoBank)는 개발 부트캠프 팀 포트폴리오용 가상 은행 앱이다. 이번 초기 구현은 카카오 로그인, 조건부 로컬 로그인, 기본 계좌 발급, 입출금, 계좌 이체, 대출을 제공한다. 체크카드는 이번 범위에서 제외하고 결제는 계좌 이체로 처리한다. 금융 서비스의 실패·성공 관측 이벤트는 JSONL에서 Grafana Alloy를 거쳐 Loki와 Prometheus로 전달한다. API는 커밋된 금융 상태 변경에 대한 개인정보 최소화 이벤트를 MongoDB에 직접 최선 노력 방식으로 기록한다. MariaDB는 금융 업무 데이터의 원본이며 MongoDB 기록 실패가 금융 거래를 되돌리거나 재시도 대상으로 만들지 않는다. Docker Compose로 필요한 서비스를 실행한다. 로컬 개발은 브라우저가 FastAPI에 직접 요청하고, 원격 미리보기는 별도 Cloudflare Workers URL을 통해 기존 Cloudflare Tunnel의 VPC Service로 OCI의 Vue 및 FastAPI loopback 포트에 연결한다.

## Requirements

### Functional

- **FR-1 초기 기능 범위:** 이번 구현은 입출금, 계좌 이체, 대출을 제공한다. 체크카드 기능은 포함하지 않는다.
- **FR-2 가입과 계좌 발급:** 랜딩 화면에서 로그인(`/login`)과 회원가입(`/signup`)을 별도 진입점으로 제공한다. 회원가입 시작 화면은 카카오 인증을 안내하고 기존 `/auth/kakao/state` 흐름을 시작한다. 신규 카카오 사용자 응답 `registration_required`는 프로필 입력 화면(`/signup/profile`)으로 이어지며, 기존 사용자는 로그인 결과에 따라 홈으로 이동한다. 프로필 입력은 휴대전화번호, 나이, 성별(남성/여성), 혼인 상태(미혼/기혼), 직장 유무를 받고 기존 `/auth/kakao/signup` API를 사용한다. 휴대전화번호는 중복 여부만 확인하며 SMS 인증은 하지 않는다. 휴대전화번호만으로 고객 계정을 만들 수 없다. 신규 사용자의 첫 로그인 때 기본 계좌를 하나 자동 발급하고, 다음 로그인부터 기존 계좌를 사용한다. 사전 등록한 데모 사용자는 가상 번호와 프로필 값을 쓴다. 로그인 화면에는 회원가입 시작 화면으로 가는 명확한 링크를 제공한다.
- **FR-3 로그인 세션:** 카카오 또는 로컬 로그인 성공 후 서버는 JWT를 HttpOnly 쿠키로 설정한다. API는 해당 세션과 사용자의 DB 역할을 확인한다.
- **FR-4 화면 서빙, 은행 API와 CORS:** Nginx가 Vue 3 정적 앱을 서빙하고 FastAPI는 금융 API를 전담한다. 로컬 개발에서 브라우저는 설정된 FastAPI origin에 직접 요청한다. 원격 미리보기 UI는 `https://podobank.i234.workers.dev`, API는 `https://podobank-api.i234.workers.dev`에서 제공한다. 두 배포된 Worker는 기존 Tunnel VPC Service를 통해 각각 OCI의 HTTP loopback upstream `127.0.0.1:8081`과 `127.0.0.1:8000`으로 연결한다. 미리보기 빌드는 API Worker origin을 API base로 사용하고 API 경로(`/health`, `/auth/...`, `/accounts/...` 등)를 그대로 요청한다. `/api` 접두사, Worker 코드의 URI 변환, Nginx path rewrite는 사용하지 않는다. FastAPI는 UI Worker의 정확한 origin만 CORS 허용 목록에 두고 credential 포함 요청을 허용한다. JWT 쿠키를 전달하기 위해 Vue 요청은 credentials를 포함하며, 허용 origin·HTTP method·header를 명시하고 credentials 사용 시 와일드카드(`*`)를 쓰지 않는다.
- **FR-5 입출금과 이체:** 입금은 잔액을 늘리고, 출금과 계좌 이체는 보내는 계좌 잔액을 줄인다. 이체는 받는 계좌 잔액도 늘린다. 결제 동작도 계좌 이체로 처리한다. 받는 사용자는 계좌번호, 휴대전화번호, 사용자 목록에서 찾을 수 있어야 한다.
- **FR-6 잔액 부족:** 출금·이체·결제 시 잔액이 부족하면 거래를 실패 처리하고 계좌 잔액을 변경하지 않는다.
- **FR-7 대출:** 대출 상품은 데이터베이스에 미리 등록한다. 사용자는 신청 중이거나 상환 중인 대출이 없을 때 상품 하나를 신청할 수 있다. 은행 직원은 상품 조건을 바꾸지 않고 승인하거나 거절한다. 승인 즉시 상품 금액은 신청자의 계좌에 입금된다. 대출은 이자 없이 매월 1일 자동 상환하며, 첫 상환은 승인일로부터 한 달이 지난 뒤의 1일부터 시작한다. 월 상환액은 원금을 상환 개월 수로 나누며, 원금은 개월 수로 나누어 떨어져야 한다. 거절되거나 전액 상환된 뒤에는 새 대출을 신청할 수 있다.
- **FR-8 상환과 연체:** 자동 상환은 매월 상환액 한 회차분을 차감한다. 잔액이 부족하면 부분 차감 없이 해당 회차를 연체 처리한다. 연체금은 월 상환액의 정수배로 납부할 수 있어 여러 회차를 한 번에 또는 나누어 갚을 수 있다.
- **FR-9 데이터 저장과 SQL 접근:** 초기 백엔드부터 사용자, 계정 등급, 계좌, 잔액, 이체 원장, 대출 상품, 대출 신청·승인·상환 데이터를 MariaDB에 저장한다. 데이터 접근은 SQLAlchemy Core의 Engine·Connection·트랜잭션 기능을 사용하고 SQL은 직접 작성한다. SQLAlchemy ORM은 사용하지 않는다. 초기 데이터에는 은행 직원 계정 한 명과 대출 상품을 등록한다.
- **FR-10 이벤트 기록과 수집:** 거래·대출 서비스 호출마다 서비스 수준 성공·실패 결과를 줄 단위 JSON 이벤트로 기록하고 Alloy가 자동 수집한다. 이벤트의 `event` 값은 `financial_operation`이며 `operation`은 `deposit`, `withdrawal`, `transfer`, `loan_application`, `loan_approval`, `loan_rejection`, `repayment_batch`, `manual_loan_repayment` 중 하나다. `outcome`은 `success` 또는 `failure`, `reason`은 코드에 정의된 유한한 정적 값이다. UTC RFC 3339 시각을 포함하며, 상환 배치 이벤트에는 처리·완료·연체·건너뜀 회차 수만 추가할 수 있다. HTTP 인증·권한·요청 스키마 단계의 거절은 금융 서비스 호출이 아니므로 포함하지 않는다. 수동 내보내기나 대시보드 입력은 없다.
- **FR-11 관측 저장:** Loki에서 구조화 금융 이벤트를 조회하고 Prometheus에서 `podobank_financial_operations_total{operation,outcome,reason}` 카운터를 조회한다. Alloy는 이벤트를 파싱해 카운터를 만들고 Prometheus는 Alloy의 내부 메트릭 엔드포인트를 스크랩한다. 카운터는 서비스 호출 한 번을 세며 `repayment_batch`도 배치 실행 한 번으로 센다. Grafana는 두 데이터 소스를 자동 설정하고 성공·실패 추이와 최근 이벤트를 표시하는 대시보드를 파일에서 프로비저닝한다. Loki 보존 기간은 30일, Prometheus 보존 기간은 15일이다.
- **FR-12 개발 서비스 실행:** 개발·데모 환경의 컨테이너 서비스를 Docker Compose로 정의한다. MariaDB는 금융 업무 데이터의 유일한 원본이며 데이터는 영속 볼륨에 저장한다. FastAPI는 MariaDB health check가 통과한 뒤 연결한다. 관측 스택은 Grafana Alloy, Loki, Prometheus, Grafana 및 각 저장 볼륨을 사용한다. MongoDB 7.0.45는 호스트 포트와 NPM 네트워크에 공개하지 않는 전용 영속 서비스다. `.env.example`과 로컬 `.env`는 API가 사용할 `MONGO_URL=mongodb://mongo:27017`과 `MONGO_DB_NAME=podobank_events`를 제공한다. FastAPI 금융 서비스는 MariaDB 트랜잭션 커밋 뒤 허용된 이벤트 문서를 MongoDB에 직접 기록하며 MongoDB는 API 기동이나 금융 트랜잭션의 필수 의존성이 아니다. 별도 적재기, 아웃박스, 재생 기능은 두지 않는다. 최종 제품 구성에는 UI 단계에서 추가한 Nginx도 포함한다.
- **FR-13 로컬 로그인:** 은행 직원은 카카오 계정 없이 휴대전화번호와 비밀번호로 로그인한다. 고객은 가입할 때 비밀번호를 선택적으로 설정할 수 있고, 비밀번호를 비워 두면 카카오 로그인만 가능하다. 고객은 카카오 로그인 상태에서 비밀번호를 설정한 뒤 로컬 로그인을 사용할 수 있다. 로컬 로그인은 비밀번호가 설정된 계정에만 허용한다. 로컬 로그인도 FR-3과 동일한 JWT HttpOnly 쿠키 세션을 발급하며, 권한은 DB의 계정 등급으로 판별한다.
- **FR-14 HTTPS 원격 미리보기:** 팀원은 `https://podobank.i234.workers.dev`에서 데모 UI를, `https://podobank-api.i234.workers.dev`에서 API를 사용한다. Cloudflare Workers와 기존 Tunnel VPC Service가 HTTPS 공개 URL을 OCI의 HTTP loopback upstream으로 전달한다. UI Worker는 `127.0.0.1:8081`, API Worker는 `127.0.0.1:8000`에 연결한다. API 경로는 `/health`, `/auth/login`처럼 현재 FastAPI 경로를 그대로 유지한다. `/api` 접두사나 Worker/Nginx URI 변환은 추가하지 않는다. 두 Worker URL은 Access 정책 없이 공개하고 UI는 앱의 고객 또는 직원 로그인으로 보호한다. API는 UI Worker origin만 CORS 허용하고 사용자 금융 기능은 JWT 세션과 DB 역할로 보호한다. CORS는 비브라우저 클라이언트의 접근을 막지 않으므로 API의 세션 없는 경로도 인터넷에서 도달 가능하며 미리보기는 합성 개발 데이터만 사용한다. API 및 DB 포트는 loopback 바인딩을 유지하고 직접 공개하지 않는다. 이 변경은 NPM, MariaDB, MongoDB, 영속 볼륨, 관측 서비스 또는 기타 공유 서비스를 변경하거나 중지하지 않는다. 미리보기 Compose 설정은 별도 overlay로 제공하여 기본 로컬 개발 구성을 바꾸지 않는다.
- **FR-15 커밋 이벤트 직접 기록:** 금융 상태를 성공적으로 바꾸는 API 서비스는 MariaDB 트랜잭션이 커밋된 뒤 해당 성공 이벤트를 MongoDB에 직접 한 번 기록한다. 이벤트 문서는 허용된 정적 필드와 기술적 UUID만 포함한다. MongoDB 기록은 best-effort이며 큐잉, 재시도, 재생, 전달 보장 기능을 제공하지 않는다. MongoDB 연결 또는 기록 실패는 이미 커밋된 금융 거래의 성공 응답이나 DB 상태를 바꾸지 않는다. 자동 상환 배치는 각 회차 상태 변경이 커밋된 뒤 해당 이벤트를 기록하며, 기존 JSONL의 배치 집계 이벤트는 실행당 한 건으로 유지한다.
- **FR-16 이벤트 실패 처리:** MongoDB 기록 장애, API 프로세스 중단 또는 네트워크 오류로 성공 이벤트가 MongoDB에 남지 않을 수 있다. 이 손실 가능성은 의도된 동작이며 별도 유실 방지 경계를 만들지 않는다. 실패한 금융 서비스 시도는 MongoDB에 기록하지 않고 기존 JSONL 성공·실패 관측 경로를 유지한다.

### Preloaded loan products

| 상품 | 원금 | 상환 기간 | 무이자 월 상환액 |
|---|---:|---:|---:|
| 자동차 구매 | 30,000,000원 | 60개월 | 500,000원 |
| 전세자금 | 96,000,000원 | 24개월 | 4,000,000원 |
| 주택 매매 | 360,000,000원 | 360개월 | 1,000,000원 |

각 상품 원금은 상환 개월 수로 나누어 떨어진다. 금액과 기간은 데모용 예시이며 공개 상품의 범위를 참고했다: [KB 신차 자동차대출](https://obank.kbstar.com/quics?cc=b051647%3Ab030008&isNew=N&page=C035671&prcode=LN20000107), [KB 전세자금대출](https://obank.kbstar.com/quics?cc=b030776%3Ab030008&page=C019479&prcode=LN20000026), [한국주택금융공사 보금자리론](https://hf.go.kr/ko/sub01/sub01_01_01.do). 실제 상품 금리·상환 방식 대신 포도뱅크 규칙인 무이자 원금 균등 상환을 적용한다.

### Non-functional

- **NFR-1 포트폴리오 데모:** 팀원이 개발 환경에서 기능과 이벤트 흐름을 실행해 리뷰어에게 보여줄 수 있어야 한다. 무중단 운영과 대규모 처리량은 목표가 아니다.
- **NFR-2 개인정보:** 샘플 데이터를 사용하고 실제 개인·금융정보, 비밀번호, 인증 토큰, 비밀 키를 이벤트나 지표에 기록하지 않는다.
- **NFR-3 개발 데이터 안전:** 스키마 초기화와 샘플 데이터 재생성은 명시적으로 실행한 개발 명령에서만 허용한다. 애플리케이션 시작 시 기존 MariaDB 데이터를 자동 삭제하거나 다시 만들지 않는다.
- **NFR-4 관측 데이터 최소화:** 금융 이벤트와 Prometheus 라벨은 개인정보·인증정보·금액·계좌 또는 사용자 식별자를 포함하지 않는다. Prometheus 라벨 값은 코드에서 정한 유한한 집합으로 제한한다.
- **NFR-5 금융 동작 격리:** JSONL 파일·Loki·Prometheus·MongoDB의 기록 장애는 이미 커밋된 금융 동작의 결과를 바꾸지 않는다. MongoDB 연결은 금융 DB 트랜잭션 커밋 뒤 제한 시간 안에 한 번 시도하며 오류는 금융 응답에 전파하지 않는다. MongoDB 장애는 API 기동과 금융 요청 처리를 막지 않는다. 관측·이벤트 구성은 개발·데모용이며 운영 배포의 가용성 보장은 범위에 포함하지 않는다.
- **NFR-7 MongoDB 격리:** MongoDB는 개발·데모 Compose 서비스로만 실행하고 호스트나 NPM 네트워크에 포트를 공개하지 않는다. FastAPI만 MongoDB 이벤트 writer로 직접 연결하며, MongoDB 연결 확인은 API 기동을 막지 않는다. MongoDB 7.0은 2027-08-31 지원 종료 전에 호스트 커널 호환성을 해결한 뒤 지원 중인 주요 버전으로 올린다.
- **NFR-8 이벤트 전달과 보존:** 성공 금융 변경 이벤트는 API가 MariaDB 커밋 뒤 MongoDB에 한 번 기록을 시도한다. MongoDB 장애·프로세스 중단·네트워크 오류 때 이벤트가 누락될 수 있으며 이를 복구하지 않는다. 아웃박스, 재시도, 재생 또는 이벤트 보존 원본은 두지 않는다.
- **NFR-6 원격 미리보기 보안:** 원격 미리보기 UI와 API는 Cloudflare Workers의 HTTPS URL로 공개한다. API와 프런트 빌드 설정은 각각 UI/API origin을 정확히 지정하고 credentialed CORS를 사용한다. `AUTH_COOKIE_SECURE=true`, HttpOnly 및 SameSite=Lax JWT 쿠키, 앱 세션 및 DB 역할 검증을 유지한다. CORS는 비브라우저 요청의 접근 제어가 아니다. `/health`, `/auth/login` 등 앱 세션이 필요하지 않은 경로도 인터넷에서 도달 가능하다. API는 합성 개발 데이터만 제공하고 기본 개발 JWT 키, 직원 비밀번호, 데모 고객 비밀번호를 사용하지 않는다. API와 MariaDB 포트는 호스트 loopback에만 바인딩하며 Cloudflare Tunnel을 통한 API 노출 외에 직접 공개하지 않는다. 이 환경은 운영 배포가 아니다.

## User experience and behavior

- 고객은 랜딩 화면의 회원가입을 선택해 카카오 인증을 시작한다. 신규 카카오 사용자는 인증 뒤 별도의 프로필 화면에서 휴대전화번호와 프로필 정보를 등록하고 자동 발급된 기본 계좌로 입출금, 이체, 대출 기능을 이용한다. 기존 고객은 로그인 화면에서 카카오 또는 설정한 휴대전화번호·비밀번호로 로그인한다. 휴대전화번호만으로 가입하는 흐름은 제공하지 않는다.
- 은행 직원은 초기 데이터에 등록된 계정으로 휴대전화번호와 비밀번호를 사용해 로컬 로그인한다. 은행 직원 로그인을 위해 카카오 로그인을 요구하지 않는다.
- 프로필 정보는 후속 상품 추천을 위한 데이터로 저장하며, 이번 초기 구현은 추천 결과를 제공하지 않는다.
- 이체 상대는 계좌번호나 휴대전화번호로 검색하거나 사용자 목록에서 선택한다. 이름이 같은 사용자는 휴대전화 뒷자리나 계좌번호 같은 보조 정보로 구분한다.
- 대출 신청은 은행 직원이 승인하기 전까지 승인 상태가 아니다.
- 계좌 잔액보다 큰 출금·이체·결제 요청은 실패하고 잔액은 그대로 유지된다.
- 대출 승인 즉시 신청자 계좌에 대출금이 입금된다.
- 대출은 이자 없이 매월 1일 자동 상환한다. 첫 상환은 승인일로부터 한 달이 지난 뒤의 1일부터 시작한다. 월 상환액은 원금 ÷ 상환 개월 수로 계산하며, 나누어 떨어지는 조건만 허용한다.
- 자동 상환 때 잔액이 부족하면 일부만 차감하지 않고 회차 전체를 연체 처리한다. 연체 상환은 월 상환액의 정수배로만 가능하다.
- Vue 3 화면은 프로토타입 「포도뱅크 웹 · 앱」을 기준으로 하며, 화면 크기는 384 × 832 px, 그리드는 16 px 배수로 한다.
- Grafana는 금융 동작의 성공·실패 카운터와 Loki의 최근 금융 이벤트를 같은 대시보드에서 보여준다.

## Architecture and design

### 이벤트 저장 역할과 전달 흐름

- MariaDB는 정형 금융 데이터의 원본이다. MongoDB는 API 금융 함수가 커밋한 업무 이벤트를 받는 비정형 이벤트 저장소다.
- FastAPI는 금융 상태 변경 트랜잭션이 커밋된 뒤 해당 함수에서 생성한 안전한 이벤트 문서를 MongoDB에 직접 한 번 기록한다. MongoDB 연결 실패는 금융 상태를 되돌리지 않는다.
- MongoDB 기록은 최선 노력이다. 큐, 아웃박스, 별도 적재기, 재시도, 재생, 또는 MariaDB 변경 감시는 없다. MongoDB 장애나 커밋 뒤 프로세스 종료로 이벤트가 빠질 수 있다.
- 이벤트 문서는 공통 UUID, 이벤트 유형, UTC 시각, 스키마 버전과 기존 금융 이벤트의 정적 필드만 담는다. 사용자·계좌 식별자, 금액, 이름, 전화번호, 원시 예외 메시지는 MongoDB에 저장하지 않는다.
- 일반 금융 서비스 호출은 성공 업무 트랜잭션이 커밋된 뒤 이벤트 기록을 한 번 시도한다. 자동 상환은 각 회차 트랜잭션에서 실제 상태를 바꾼 경우에만 회차 이벤트를 한 번 시도한다. 회차 이벤트는 `processed=1`, `paid` 또는 `overdue` 중 하나만 1, 나머지는 0으로 두고, 건너뛴 회차는 이벤트를 만들지 않는다. 같은 실행의 회차 이벤트는 기술적 `batch_id`로 묶는다. 기존 JSONL은 계속 서비스 호출당 한 건의 배치 집계를 유지한다.
- 실패한 서비스 시도는 MongoDB에 보내지 않는다. 현재 JSONL 성공·실패 이벤트와 Alloy → Loki·Prometheus 관측 흐름은 유지하며, 실패 이벤트의 파일 기록은 최선 노력이다.
- Loki는 애플리케이션·런타임 및 서비스 수준 JSONL 이벤트를 수집한다. MongoDB의 커밋 이벤트 문서는 Loki 로그와 별개의 조회용 투영이다.
- 현재 Docker 호스트의 커널은 `7.0.0-1013-oracle`이다. MongoDB 공식 8.0 릴리스 노트는 Linux 커널 `6.19`부터 `7.0.13`까지 시작 호환성 문제가 있으며 `7.0.14` 이상으로 업그레이드하도록 안내한다. 이 환경에서 `mongo:8.0.34`는 시작 직후 종료됐고 `mongo:7.0.45`는 기동 및 `mongosh` ping에 성공했다. 따라서 개발용 설치는 `mongo:7.0.45`를 사용한다. MongoDB 7.0의 지원 종료일은 2027-08-31이므로, MongoDB 8.0 이상으로 올릴 때는 먼저 호스트 커널 호환성을 해결하고 지원 종료 전에 별도 변경으로 진행한다. ([MongoDB 8.0 릴리스 노트](https://www.mongodb.com/docs/v8.0/release-notes/8.0/), [MongoDB 라이프사이클](https://www.mongodb.com/legal/support-policy/lifecycles))
- 현재 Mongo 호스트 커널과 호환성 제약, MongoDB 버전 업그레이드 시점은 FR-12 및 NFR-7의 기준을 따른다.

`고객 카카오 로그인 → FastAPI 사용자 확인/기본 계좌 발급`

`고객·직원 로컬 로그인 → FastAPI 사용자 확인/JWT 세션 발급`

`브라우저 → Nginx (Vue 3 정적 앱 서빙)`

`로컬 브라우저 → FastAPI (금융 API 직접 호출)`

`미리보기 브라우저 → https://podobank.i234.workers.dev → 기존 Tunnel VPC Service → OCI HTTP 127.0.0.1:8081 → Vue 3`

`미리보기 브라우저 → https://podobank-api.i234.workers.dev → 기존 Tunnel VPC Service → OCI HTTP 127.0.0.1:8000 → FastAPI`

`FastAPI 데이터베이스: MariaDB`

`FastAPI 금융 서비스 → MariaDB 금융 행 (업무 트랜잭션)`

`FastAPI 금융 서비스 (커밋 뒤) → MongoDB 금융 이벤트 문서 (최선 노력)`

`FastAPI·상환 CLI → JSONL → Alloy → Loki·Prometheus`

FastAPI는 기존 금융 업무를 위해 MariaDB에 연결하고, 성공한 금융 동작 이벤트를 `MONGO_URL`, `MONGO_DB_NAME`으로 MongoDB에 직접 기록한다. 이벤트 저장은 DB 트랜잭션 커밋 뒤 최선 노력으로 수행하며, 장애 시 금융 요청 결과는 유지되고 이벤트는 누락될 수 있다. MongoDB는 전용 named volume을 사용하며 호스트 포트나 NPM 네트워크에 연결하지 않는다. 별도 event-projector나 MariaDB outbox 연결, 큐, 재시도, 재생은 없다.

### 모듈 경계와 의존 방향

- `features/transactions`와 `features/loans`는 각 금융 상태 변경과 트랜잭션 범위를 소유한다. 성공 변경을 MariaDB에 커밋한 뒤 이벤트 기록 모듈을 호출한다. 상환 배치의 회차 이벤트도 각 회차 트랜잭션이 커밋된 뒤 별도로 기록한다.
- `features/financial_events`는 개인정보 최소화 이벤트 봉투 생성과 PyMongo 직접 기록을 소유한다. DB outbox, polling, retry, replay 기능은 두지 않는다.
- `database.py`와 `schema.py`는 MariaDB Engine과 금융 테이블 초기화를 소유한다. Mongo 이벤트 때문에 MariaDB 테이블을 추가하지 않는다.
- `app.py`는 Mongo 클라이언트의 수명 주기를 관리하거나 이벤트 writer에 클라이언트를 주입한다. MongoDB 연결 실패가 API 기동을 막지 않도록 연결은 지연하고 작업 실패를 금융 응답과 분리한다.
- 허용 의존은 `transactions/loans → financial_events writer → PyMongo` 및 기존 `transactions/loans → SQLAlchemy Connection`이다. 금융 DB 작업이 MongoDB에 연결되거나 JSONL 관측 경로가 MongoDB에 의존하지 않는다.

로컬 개발에서는 Vue가 FastAPI origin을 직접 호출한다. 원격 미리보기는 두 배포된 Worker를 통해 UI와 API를 별도 HTTPS 호스트로 제공하며, 기존 Tunnel의 VPC Service가 OCI의 HTTP loopback upstream에 연결한다. 미리보기 빌드는 browser-visible API base로 `https://podobank-api.i234.workers.dev`를 사용하고 UI는 기존 API path(`/auth/...`, `/accounts/...` 등)를 그대로 호출한다. 같은 Cloudflare account subdomain 아래의 두 Worker hostname은 별도 origin이므로 API는 UI origin의 CORS 요청만 허용하고 credentials를 지원한다. JWT 쿠키는 Secure, HttpOnly, SameSite=Lax를 유지한다. credentials를 허용할 때 origin·method·header에 와일드카드(`*`)를 사용하지 않는다. Worker의 공개 주소 외에 API/DB 컨테이너 포트를 인터넷에 직접 공개하지 않으며 NPM 설정은 변경하지 않는다.

## Remote preview design decision

- **Intent:** 팀원이 운영 중인 개발 서버에서 기존 화면을 HTTPS로 열어 리뷰할 수 있게 한다.
- **Goals:** UI와 API용 전용 HTTPS Worker URL 두 개, 이미 배포된 Cloudflare Workers와 기존 Tunnel VPC Services 사용, 기존 API path 및 세션 쿠키 동작 유지, API/DB의 직접 공개 방지, 기본 로컬 Compose 구성 유지, NPM과 모든 공유 서비스를 변경·중지하지 않음.
- **Non-goals:** 운영 배포, 실제 금융 데이터, 외부 공개 가입, NPM 자체 설치·관리자 계정 변경, Kakao OAuth 자격 증명 발급.
- **Approaches considered:** (1) UI와 API를 한 hostname 아래 `/api` 경로로 나누거나 proxy에서 path rewrite를 한다. 한 주소지만 사용자가 기존 API 경로를 유지하고 Nginx/Worker path rewrite를 사용하지 않기로 했다. (2) UI와 API를 별도 Worker HTTPS hostname으로 두고 기존 Tunnel VPC Service를 각각의 OCI loopback HTTP port에 연결한다. 기존 API 경로를 유지하고 이미 배포된 Worker/Tunnel 설정을 사용할 수 있어 선택한다. (3) OCI의 API나 DB 포트를 인터넷에 직접 공개한다. loopback 보호를 없애므로 제외한다.
- **Selected approach:** 두 번째 방식. UI는 `https://podobank.i234.workers.dev`, API는 `https://podobank-api.i234.workers.dev`를 사용한다. 이미 배포된 `podobank` 및 `podobank-api` Worker는 기존 Tunnel VPC Services를 통해 각각 `http://127.0.0.1:8081` 및 `http://127.0.0.1:8000`으로 전달한다. Worker와 Nginx에서 URI를 바꾸지 않고 FastAPI의 현재 root API path를 유지한다. API는 정확한 UI Worker origin만 CORS 허용하고 앱 JWT·DB 역할 검증을 사용한다. API는 합성 개발 데이터만 제공한다.
- **Constraints:** 두 Worker와 각 VPC Service는 이미 배포·연결돼 있으며 이번 저장소 변경에서 Cloudflare/Tunnel 구성을 바꾸지 않는다. 컨테이너 API·frontend host port는 기존 `127.0.0.1` bind를 유지한다. NPM, MariaDB, MongoDB, named volumes, 관측 및 기타 공유 서비스의 설정이나 실행 상태를 바꾸지 않는다. NPM 관리자 자격 증명과 환경 비밀값은 출력·저장소 기록하지 않는다.
- **Builder decisions:** 기존 미리보기 Compose overlay에서 API Worker URL을 build-time API base로 사용한다. preview env example 및 이미 사용 중인 ignored `.env.npm-preview`에서는 지정한 세 URL 값만 변경한다. Kakao placeholder와 `APP_ENV=development`는 유지한다. 배포 문서는 기존 Cloudflare Worker/VPC 연결과 검증 절차를 설명하며 API/frontend 외 Compose 서비스는 재빌드하지 않는다.

Docker Compose로 MariaDB, FastAPI, Vue와 관측 스택을 실행한다. 기본 Compose 설정은 로컬 개발용이다. 미리보기 전용 overlay는 기존 OCI Compose 프로젝트의 UI/API 설정을 유지하며, Cloudflare Tunnel VPC Services는 기존 host loopback port mapping을 사용한다. 이 변경은 NPM과 기존 외부 network, MariaDB, MongoDB, 관측 서비스 및 named volumes를 수정하거나 중지하지 않는다. API 및 frontend만 재빌드하고, DB 스키마와 샘플 데이터에는 접근하지 않는다.

`FastAPI·상환 CLI → 금융 이벤트 JSONL 파일 → Grafana Alloy → Loki·Prometheus → Grafana`

FastAPI와 `process-repayments` CLI는 전용 JSONL 이벤트 파일에 결과 이벤트를 쓴다. 파일은 API 컨테이너만 쓰고 Alloy는 읽기 전용 named volume으로 tail한다. Alloy는 이벤트 필드를 파싱해 Loki에 전달하고 같은 이벤트로부터 Prometheus 카운터를 만든다. Prometheus는 Alloy의 내부 메트릭 엔드포인트를 Compose 내부 네트워크에서 스크랩한다. 금융 서비스 작업은 이벤트 수집기나 원격 관측 서비스에 동기 요청하지 않는다. 단발성 `process-repayments` CLI는 금융 처리를 마친 뒤 종료할 때 로컬 JSONL 기록 큐를 drain해 파일에 flush한 다음 종료한다. 이 종료 처리는 DB 트랜잭션과 금융 서비스 작업을 지연시키지 않는다.

- MariaDB에 사용자, 계정 등급, 기본 계좌, 잔액, 이체, 대출 상품, 대출 상태와 회차별 상환·연체 상태를 저장한다. SQLAlchemy Core의 Engine·Connection·트랜잭션 기능으로 직접 작성한 SQL을 실행하며 ORM을 사용하지 않는다.
- 잔액과 원장을 함께 변경하는 한 DB 트랜잭션에서 쓰는 모든 테이블은 InnoDB를 사용한다. 원장 항목은 InnoDB 테이블에 저장하고, 변경할 수 없는 UTC `DATETIME(6)` 확정 시각 `posted_at`을 기준으로 `RANGE COLUMNS` 날짜 파티션을 사용한다. 파티션 간격은 월별이다. 파티션 범위 밖의 거래 기록도 거부되지 않도록 미래 범위를 처리하며, 보존 기간이 별도로 승인되기 전에는 파티션을 자동 삭제하지 않는다.
- MariaDB 파티션 제약에 맞춰 원장 테이블에는 사용자·계좌·대출·거래 테이블을 향한 외래 키를 선언하지 않는다. 다른 테이블도 원장 테이블을 참조하는 외래 키를 선언하지 않는다. 원장 행에는 내부 사용자·계좌 ID를 일반 컬럼으로 저장한다. 서비스는 원장 행을 쓰기 전에 참조 대상 레코드의 존재와 관계를 확인하고, 잔액 변경과 원장 기록을 같은 DB 트랜잭션으로 커밋한다. 변경 가능한 계좌 행은 갱신 전에 잠그며, 여러 계좌를 잠글 때는 기존에 정의한 계좌 ID 오름차순을 지킨다.
- 은행 직원 계정 한 명과 대출 상품 목록을 MariaDB 초기 데이터로 제공한다. 관측 파이프라인 개발은 백엔드 기능 구현 이후 진행한다.
- 출금과 이체는 잔액 부족 시 거절하며 잔액을 음수로 만들지 않는다.
- 입금·출금과 그 원장 항목은 한 DB 트랜잭션으로 처리한다. 이체는 보내는 계좌와 받는 계좌의 잔액 변경 및 양쪽 원장 항목을 한 트랜잭션으로 처리한다.
- 송금은 두 계좌 행을 `SELECT ... FOR UPDATE`로 잠근 뒤 잔액을 검사하고 갱신한다. 동시에 반대 방향 이체가 발생해도 계좌 ID 순서대로 잠금을 획득해 교착 가능성을 줄인다.
- 대출 승인 API는 은행 직원 계정만 사용할 수 있다.
- 금융 이벤트 JSON에는 `timestamp`, `event`, `operation`, `outcome`, `reason`을 공통 필드로 기록한다. 상환 배치는 `processed`, `paid`, `overdue`, `skipped` 정수 개수를 추가한다. 원시 예외 문구는 기록하지 않으며 `reason`은 서비스 코드의 정적 오류 코드만 사용한다.
- 이벤트의 Loki 라벨은 `operation`, `outcome`, `reason`, 고정 `service` 값으로 제한한다. 사용자 입력과 수치 값은 Loki 또는 Prometheus 라벨이 될 수 없다. Prometheus 카운터 라벨은 `operation`, `outcome`, `reason`뿐이다.
- 금융 이벤트 파일은 DB 볼륨과 분리된 named volume에 둔다. Loki 보존 기간은 30일, Prometheus 보존 기간은 15일이다. 이벤트 입력 파일 볼륨은 수집 지연 중 데이터를 보존하기 위해 자동 삭제하지 않으며, 로컬 개발자는 별도로 명시해 정리할 수 있다.
- Grafana는 Prometheus·Loki 데이터 소스와 금융 운영 대시보드를 설정 파일에서 프로비저닝한다. Grafana만 호스트 loopback 주소에 포트를 공개한다. Alloy, Loki, Prometheus 포트는 호스트에 공개하지 않는다.
- Compose 서비스 이미지는 `docs/stack-versions.md`에 기록한 감사 버전으로 고정한다. 모니터링 컨테이너는 API·DB와 별도 named volume을 사용한다.

## Interfaces, data, and dependencies

- **프론트엔드:** Vue 3
- **프론트엔드 서빙:** Nginx
- **API:** FastAPI
- **금융 데이터베이스:** MariaDB
- **금융 API 이벤트 저장소:** MongoDB 7.0.45, PyMongo (잠금 파일에서 버전 고정, API의 최선 노력 직접 기록)
- **SQL 접근:** SQLAlchemy Core, 직접 작성한 SQL, ORM 미사용
- **개발·데모 서비스 실행:** Docker Compose
- **브라우저 API 연결:** 로컬은 FastAPI 직접 origin, Worker 미리보기는 `https://podobank-api.i234.workers.dev` base; FastAPI CORS는 `https://podobank.i234.workers.dev`만 허용하고 필요한 method·header 및 credentials를 지정
- **HTTPS 미리보기:** `compose.npm-preview.yaml` overlay의 API/frontend build configuration, UI Worker `podobank.i234.workers.dev`와 API Worker `podobank-api.i234.workers.dev`, 기존 Tunnel VPC Service에서 OCI loopback HTTP ports 8081/8000으로 전달, 기존 API paths, Secure·HttpOnly·SameSite=Lax 쿠키
- **가입·로그인:** `/signup`의 카카오 가입 시작 화면, 카카오 인증 뒤 `/signup/profile`의 고객 프로필 등록, `/login`의 카카오 또는 선택적 비밀번호 로컬 로그인, 직원 로컬 로그인
- **관측:** Grafana Alloy, Loki, Prometheus, Grafana. Alloy는 금융 이벤트 스트림을 처리해 Prometheus의 `podobank_financial_operations_total` 카운터를 만든다.
- **금융·프로필 데이터:** 사용자, 휴대전화번호, 나이, 성별, 혼인 상태, 직장 유무, 계정 등급, 계좌, 잔액, 이체, 대출 상품, 대출 신청·승인·상환
- **기본키와 조회 키:** `users.id`와 `accounts.id`는 짧은 숫자 기본키로 둔다. 전화번호와 카카오 사용자 식별자는 각각 고유 인덱스를 둔다. JWT의 `sub`와 원장 행의 계좌·사용자 참조 값은 내부 사용자·계좌 ID를 사용한다. 계좌 소유자와 계좌번호도 고유 인덱스로 찾는다. 원장 `entry_id`는 `BIGINT UNSIGNED AUTO_INCREMENT`로 생성한다. 날짜 파티션 키 `posted_at`은 원장 테이블의 모든 고유 키에 포함하며, 원장 기본키는 `(entry_id, posted_at)`으로 둔다.
- **원장 조회 인덱스:** `(account_id, posted_at, entry_id)` 복합 인덱스를 두어 계좌별 날짜 범위 조회와 시간순 정렬을 지원한다. 날짜 범위 조건을 포함해 파티션을 제한한다. 원장 외래 키 인덱스는 만들지 않는다.
- **이벤트·지표 데이터:** 정적 동작·결과·사유 코드와 UTC 시각으로 이루어진 JSONL 및 API가 직접 기록하는 MongoDB 이벤트 문서, 상환 회차 집계 수, 그리고 `operation`, `outcome`, `reason` 라벨을 가진 `podobank_financial_operations_total` 카운터. MongoDB 문서에는 기술적 이벤트 UUID만 허용하며 사용자·계좌 식별자, 휴대전화번호, 이름, 금액, 원시 예외 문자열은 저장하지 않는다.

## Security, privacy, and policy constraints

- 계좌·거래 데이터와 사전 등록 사용자 정보는 데모용으로 만든다. 가입 사용자의 휴대전화번호는 검색을 위해 저장한다.
- 휴대전화번호를 이벤트·지표에 기록하지 않는다.
- 나이, 성별, 혼인 상태, 직장 유무도 이벤트·지표에 기록하지 않는다.
- 카카오 인증 토큰과 비밀 키를 이벤트·지표에 넣지 않으며 저장소에 커밋하지 않는다.
- 비밀번호는 평문으로 저장하거나 이벤트·지표에 기록하지 않는다.
- MongoDB 이벤트 문서에는 허용된 정적 필드와 기술적 이벤트 UUID만 저장한다. 실패 이벤트는 기존 JSONL 경로만 사용한다.
- 앱 JWT는 HttpOnly 쿠키로 전달하며 브라우저에서 읽을 수 있는 저장소에 보관하지 않는다.
- 대출 승인 API는 은행 직원만 사용할 수 있어야 한다. 초기 데이터베이스에 등록된 은행 직원 한 명만 승인 권한을 가진다.
- 관측 컨테이너 포트는 호스트에 노출하지 않고 Grafana UI만 `127.0.0.1`에 바인딩한다. Grafana 관리자 비밀번호는 개발용 `.env`에서 제공하며 `.env.example` 값은 로컬 데모 전용이다.

## Risks and concerns

- 이체 처리 중 한 계좌만 갱신되면 잔액이 맞지 않을 수 있다.
- 원장 외래 키가 없으므로 애플리케이션 오류가 고아 원장 행을 만들 수 있다. 관련 계정 존재 확인, 계좌 행 잠금, 잔액 갱신과 원장 삽입을 한 트랜잭션으로 묶고, 현재 범위에는 참조 대상 금융 레코드의 물리 삭제를 추가하지 않는다.
- 잔액 부족 거래도 실패 이벤트로 기록해야 동작 결과를 관측할 수 있다.
- 금융 이벤트 파일은 Loki 보존 기간과 별개로 named volume에 남고 자동 정리하지 않는다. 이벤트량이 누적될 수 있으므로 이 구성은 개발·데모용이며, 용량 관리가 필요한 운영 배포는 별도 설계가 필요하다.
- MongoDB 기록은 MariaDB 커밋 뒤 동기적으로 제한 시간 내 시도한다. MongoDB 장애나 프로세스 중단으로 이벤트가 누락될 수 있으며, 금융 거래는 이미 커밋된 결과를 유지한다.
- 이벤트를 위한 아웃박스, 별도 전달 적재기, 재시도, 재생 또는 유실 복구 기능은 제공하지 않는다. MongoDB 볼륨 유실 시 MongoDB 이벤트를 다시 구성할 수 없다.
- JSONL과 MongoDB 기록은 최선 노력이며 해당 저장소가 사용할 수 없을 때 관측 이벤트나 MongoDB 이벤트가 누락될 수 있다.

## Acceptance criteria

- 랜딩 화면에서 회원가입과 기존 계정 로그인을 서로 구분해 진입할 수 있다. 회원가입은 `/signup`에서 카카오 인증을 시작하고 로그인은 `/login`으로 간다.
- 신규 카카오 사용자에게만 프로필 입력 화면(`/signup/profile`)이 표시되며, 기존 카카오 사용자는 로그인된다. 고객은 휴대전화번호만으로 가입할 수 없다.
- 최초 카카오 로그인 때 기본 계좌 한 개가 발급되고 재로그인 때 중복 발급되지 않는다.
- 비밀번호를 설정하지 않은 고객은 로컬 로그인에 실패하고 카카오 로그인만 사용할 수 있다. 고객은 인증된 카카오 세션에서 비밀번호를 설정한 뒤 로컬 로그인할 수 있다.
- 사전 등록된 은행 직원은 카카오 로그인 없이 로컬 로그인할 수 있고, 로그인 뒤에도 직원 전용 API는 직원 역할만 허용한다.
- Docker Compose 기본 설정으로 로컬 개발 서비스를 실행할 수 있고 미리보기 overlay는 기존 OCI Compose 프로젝트의 API/frontend 설정만 보완한다.
- `https://podobank.i234.workers.dev/`가 Vue 앱을 반환하고 `https://podobank-api.i234.workers.dev/health`가 FastAPI health 응답을 반환한다. 기존 Tunnel VPC Services는 각각 HTTP loopback `127.0.0.1:8081` 및 `127.0.0.1:8000`으로 전달한다.
- 미리보기 빌드의 API base와 환경 파일의 API/UI/Kakao callback URL이 각 Worker URL과 일치한다. API 경로는 `/health`, `/auth/...` 등 기존 경로를 유지하고 `/api` 접두사나 Worker/Nginx path rewrite가 없다. 로컬 빌드는 기존 localhost API origin을 계속 사용한다.
- UI Worker origin의 CORS preflight가 정확한 UI origin과 credentials를 허용하며 다른 origin은 허용하지 않는다. UI에서 실행한 API 로그인 및 후속 요청에 Secure, HttpOnly, SameSite=Lax JWT 쿠키가 포함된다.
- `.env.npm-preview`에서는 API_ORIGIN, FRONTEND_ORIGINS, KAKAO_REDIRECT_URI의 세 URL 값만 바뀌고 모든 다른 값과 파일 mode `0600`이 보존된다. 비밀값은 터미널 출력, diff, log, 저장소에 기록되지 않는다. `.env.npm-preview.example`은 `APP_ENV=development`와 Kakao placeholder를 유지한다.
- 미리보기 API·직원·데모 고객 비밀 값은 예시 또는 개발 기본값이 아니며 저장소에 커밋되지 않는다. 두 Worker URL은 공개되고 CORS는 비브라우저 요청을 차단하지 않으며, 사용자별 금융 API는 유효한 앱 세션과 DB 역할을 요구한다.
- API와 DB port는 `127.0.0.1` loopback binding만 사용하고 인터넷에 직접 공개되지 않는다. NPM, MariaDB, MongoDB, named volumes, 관측 서비스 및 다른 공유 서비스의 설정과 실행 상태는 변경되지 않는다. Compose 실행은 API와 frontend만 대상으로 하며 dependency/shared service를 시작·중지·재생성하지 않는다.
- MariaDB 컨테이너나 FastAPI 컨테이너를 재시작해도 MariaDB 영속 볼륨의 데이터가 유지된다.
- Vue의 별도 API 호스트 요청에 JWT HttpOnly 쿠키가 포함된다. FastAPI CORS는 UI의 정확한 origin과 필요한 method·header만 허용하고 credentials를 지원하며, 해당 설정에 와일드카드를 쓰지 않는다.
- 가입 과정에서 입력한 휴대전화번호는 중복될 수 없고 SMS 인증은 하지 않는다. 사전 등록 데모 사용자에게는 가상 번호를 쓴다.
- 가입 과정에서 나이, 성별, 혼인 상태, 직장 유무를 받고 MariaDB에 저장한다.
- 입출금과 계좌 이체가 잔액에 반영되고, 잔액 부족 거래는 실패하며 잔액을 바꾸지 않는다.
- 성공한 입출금과 이체는 계좌 잔액 변경과 해당 원장 항목을 하나의 DB 트랜잭션으로 반영한다. 이체는 양쪽 원장 항목을 함께 기록하며, 참조 계정이 없으면 전체 거래를 롤백한다.
- 원장 테이블은 승인된 날짜 단위의 InnoDB `RANGE COLUMNS(posted_at)` 파티션을 사용한다. 원장 테이블에는 외래 키가 없고 다른 테이블도 원장을 외래 키로 참조하지 않는다. 모든 원장 고유 키에는 `posted_at`이 포함되며, 승인된 보존 정책이 없으면 파티션을 자동 삭제하지 않는다.
- 잔액과 원장을 함께 바꾸는 트랜잭션에서 수정되는 모든 테이블의 storage engine은 InnoDB다.
- 사용자가 대출을 신청하고 은행 직원 계정으로 승인할 수 있다.
- 사용자는 신청 중이거나 상환 중인 대출을 동시에 하나만 가질 수 있다. 거절되거나 전액 상환된 뒤 다시 신청할 수 있다.
- 사용자는 사전 등록된 대출 상품을 선택하며, 은행 직원은 신청 조건을 바꾸지 않고 승인 또는 거절할 수 있다.
- 대출 승인 즉시 신청자 계좌에 금액이 입금된다.
- 초기 DB에는 자동차 구매 3천만 원/60개월, 전세자금 9천6백만 원/24개월, 주택 매매 3억6천만 원/360개월 상품을 등록한다. 세 상품은 무이자다.
- 대출 원금은 상환 개월 수로 나누어 떨어지는 값만 신청할 수 있다.
- 대출은 이자 없이 매월 1일 자동 상환한다. 승인일부터 한 달이 지난 뒤의 첫 1일에 첫 회차를 차감한다. 잔액 부족 시 회차 전체가 연체되고, 연체금은 월 상환액의 정수배로 납부할 수 있다.
- 성공·실패 금융 이벤트가 Alloy를 통해 Loki에 자동 기록되고 기본 지표가 Prometheus에 쌓인다.
- 체크카드 기능은 이번 범위에 포함되지 않고 결제는 계좌 이체로 처리된다.
- UI 단계에서 프로토타입의 384 × 832 px 화면과 16 px 배수 그리드를 따른다.
- 초기 백엔드 기능은 MariaDB와 SQLAlchemy Core의 직접 작성 SQL로 구현하고 ORM은 사용하지 않는다. 개발 검증도 MariaDB를 대상으로 실행한다.
- 성공·실패 금융 서비스 호출마다 유효한 JSONL 이벤트 한 줄을 기록한다. `operation`, `outcome`, `reason`은 정적 허용 값만 쓰며 상환 배치의 회차 집계 외 수치 데이터를 남기지 않는다.
- 자동상환 CLI의 배치 이벤트도 API 이벤트와 같은 수집 경로를 거쳐 Loki에서 검색된다.
- Alloy는 이벤트를 Loki로 전송하고 각 이벤트마다 `podobank_financial_operations_total`을 한 번 증가시킨다. Prometheus에서 거래 유형·결과·정적 사유별 카운터를 조회할 수 있고 라벨 값 집합은 유한하다.
- Grafana 기동 후 설정된 Prometheus·Loki 데이터 소스와 금융 동작 대시보드가 자동으로 표시된다. 대시보드는 금융 동작 성공·실패 추이와 최근 구조화 이벤트를 제공한다.
- Docker Compose 기본 및 preview overlay 설정 검증은 예시 env 파일 기반으로 실행할 수 있다. 관측 컨테이너 포트는 호스트에 바인딩하지 않으며 Grafana만 loopback에 공개한다.
- MongoDB 컨테이너는 health check를 통과하고 전용 named volume을 사용한다. 재시작 또는 컨테이너 재생성 뒤에도 MongoDB 데이터가 남는다.
- MongoDB에 호스트 포트 매핑이 없고 기존 NPM 외부 네트워크에도 연결되지 않는다.
- `.env.example`과 로컬 `.env`의 `MONGO_URL=mongodb://mongo:27017`, `MONGO_DB_NAME=podobank_events` 설정이 제공되고, Compose 내부 서비스에서 `mongo` 이름으로 MongoDB에 접속할 수 있다.
- `docker compose exec mongo mongosh --quiet --eval 'db.adminCommand({ping: 1})'` 명령이 성공해 MongoDB health를 확인할 수 있다.
- 성공 금융 업무의 이벤트는 API가 MariaDB 트랜잭션을 커밋한 뒤 MongoDB에 직접 기록한다. MongoDB 기록 실패는 금융 거래 성공 결과를 바꾸지 않으며 이벤트가 누락될 수 있다.
- 자동 상환 배치의 각 커밋된 회차 상태 변경마다 MongoDB 이벤트 기록을 한 번 시도하고, 건너뛴 회차에는 이벤트를 만들지 않는다. 기존 JSONL 배치 이벤트는 실행당 한 건과 집계값을 유지한다.
- 실패 시도에는 MongoDB 이벤트를 만들지 않고 기존 JSONL 성공·실패 기록 경로를 유지한다.
- MongoDB 중지 상태에서도 API는 기동되고 금융 성공 변경은 커밋된다. MongoDB에 남지 않은 이벤트는 복구·재생·재시도하지 않는다.
- MongoDB event document에는 정적 이벤트 필드와 기술적 UUID만 들어가며 사용자·계좌 식별자, 금액, 전화번호, 이름, 원시 예외 문구를 포함하지 않는다.

## Open questions

원장 파티션은 소유자가 정한 월별 간격을 사용한다. 원장 보존 기간은 미정이며 승인된 정책 전에는 자동 파티션 삭제를 허용하지 않는다. 관측 로그의 Loki 보존 기간은 30일, Prometheus 보존 기간은 15일이며 입력 JSONL 볼륨은 자동 삭제하지 않는다.
