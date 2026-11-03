# Specification

## Summary

포도뱅크(PodoBank)는 개발 부트캠프 팀 포트폴리오용 가상 은행 앱이다. 이번 초기 구현은 카카오 로그인, 조건부 로컬 로그인, 기본 계좌 발급, 입출금, 계좌 이체, 대출을 제공한다. 체크카드는 이번 범위에서 제외하고 결제는 계좌 이체로 처리한다. 금융 서비스의 실패·성공 관측 이벤트는 JSONL에서 Grafana Alloy를 거쳐 Loki와 Prometheus로 전달한다. 커밋된 금융 상태 변경의 성공 이벤트는 MariaDB 트랜잭셔널 아웃박스에서 별도 적재기가 MongoDB로 전달한다. Docker Compose로 필요한 서비스를 실행한다. 로컬 개발은 브라우저가 FastAPI에 직접 요청하고, 원격 미리보기는 Nginx Proxy Manager(NPM)가 Vue 앱과 HTTPS API 경로를 제공한다.

## Requirements

### Functional

- **FR-1 초기 기능 범위:** 이번 구현은 입출금, 계좌 이체, 대출을 제공한다. 체크카드 기능은 포함하지 않는다.
- **FR-2 가입과 계좌 발급:** 고객은 카카오 로그인으로 가입하고 가입 과정에서 휴대전화번호, 나이, 성별(남성/여성), 혼인 상태(미혼/기혼), 직장 유무를 입력한다. 휴대전화번호는 중복 여부만 확인하며 SMS 인증은 하지 않는다. 신규 사용자의 첫 로그인 때 기본 계좌를 하나 자동 발급하고, 다음 로그인부터 기존 계좌를 사용한다. 사전 등록한 데모 사용자는 가상 번호와 프로필 값을 쓴다.
- **FR-3 로그인 세션:** 카카오 또는 로컬 로그인 성공 후 서버는 JWT를 HttpOnly 쿠키로 설정한다. API는 해당 세션과 사용자의 DB 역할을 확인한다.
- **FR-4 화면 서빙, 은행 API와 CORS:** Nginx가 Vue 3 정적 앱을 서빙하고 FastAPI는 금융 API를 전담한다. 로컬 개발에서 브라우저는 설정된 FastAPI origin에 직접 요청한다. 원격 미리보기에서 `podobank.oci-dev.duckdns.org`는 Vue 앱을, `podobank-api.oci-dev.duckdns.org`는 FastAPI를 각각 제공한다. 미리보기 빌드는 API 호스트를 API base로 사용한다. FastAPI는 환경별로 명시된 프론트엔드 origin만 CORS 허용 목록에 두고 credential 포함 요청을 허용한다. JWT 쿠키를 전달하기 위해 Vue 요청은 credentials를 포함하며, 허용 origin·HTTP method·header를 명시하고 credentials 사용 시 와일드카드(`*`)를 쓰지 않는다.
- **FR-5 입출금과 이체:** 입금은 잔액을 늘리고, 출금과 계좌 이체는 보내는 계좌 잔액을 줄인다. 이체는 받는 계좌 잔액도 늘린다. 결제 동작도 계좌 이체로 처리한다. 받는 사용자는 계좌번호, 휴대전화번호, 사용자 목록에서 찾을 수 있어야 한다.
- **FR-6 잔액 부족:** 출금·이체·결제 시 잔액이 부족하면 거래를 실패 처리하고 계좌 잔액을 변경하지 않는다.
- **FR-7 대출:** 대출 상품은 데이터베이스에 미리 등록한다. 사용자는 신청 중이거나 상환 중인 대출이 없을 때 상품 하나를 신청할 수 있다. 은행 직원은 상품 조건을 바꾸지 않고 승인하거나 거절한다. 승인 즉시 상품 금액은 신청자의 계좌에 입금된다. 대출은 이자 없이 매월 1일 자동 상환하며, 첫 상환은 승인일로부터 한 달이 지난 뒤의 1일부터 시작한다. 월 상환액은 원금을 상환 개월 수로 나누며, 원금은 개월 수로 나누어 떨어져야 한다. 거절되거나 전액 상환된 뒤에는 새 대출을 신청할 수 있다.
- **FR-8 상환과 연체:** 자동 상환은 매월 상환액 한 회차분을 차감한다. 잔액이 부족하면 부분 차감 없이 해당 회차를 연체 처리한다. 연체금은 월 상환액의 정수배로 납부할 수 있어 여러 회차를 한 번에 또는 나누어 갚을 수 있다.
- **FR-9 데이터 저장과 SQL 접근:** 초기 백엔드부터 사용자, 계정 등급, 계좌, 잔액, 이체 원장, 대출 상품, 대출 신청·승인·상환 데이터를 MariaDB에 저장한다. 데이터 접근은 SQLAlchemy Core의 Engine·Connection·트랜잭션 기능을 사용하고 SQL은 직접 작성한다. SQLAlchemy ORM은 사용하지 않는다. 초기 데이터에는 은행 직원 계정 한 명과 대출 상품을 등록한다.
- **FR-10 이벤트 기록과 수집:** 거래·대출 서비스 호출마다 서비스 수준 성공·실패 결과를 줄 단위 JSON 이벤트로 기록하고 Alloy가 자동 수집한다. 이벤트의 `event` 값은 `financial_operation`이며 `operation`은 `deposit`, `withdrawal`, `transfer`, `loan_application`, `loan_approval`, `loan_rejection`, `repayment_batch`, `manual_loan_repayment` 중 하나다. `outcome`은 `success` 또는 `failure`, `reason`은 코드에 정의된 유한한 정적 값이다. UTC RFC 3339 시각을 포함하며, 상환 배치 이벤트에는 처리·완료·연체·건너뜀 회차 수만 추가할 수 있다. HTTP 인증·권한·요청 스키마 단계의 거절은 금융 서비스 호출이 아니므로 포함하지 않는다. 수동 내보내기나 대시보드 입력은 없다.
- **FR-11 관측 저장:** Loki에서 구조화 금융 이벤트를 조회하고 Prometheus에서 `podobank_financial_operations_total{operation,outcome,reason}` 카운터를 조회한다. Alloy는 이벤트를 파싱해 카운터를 만들고 Prometheus는 Alloy의 내부 메트릭 엔드포인트를 스크랩한다. 카운터는 서비스 호출 한 번을 세며 `repayment_batch`도 배치 실행 한 번으로 센다. Grafana는 두 데이터 소스를 자동 설정하고 성공·실패 추이와 최근 이벤트를 표시하는 대시보드를 파일에서 프로비저닝한다. Loki 보존 기간은 30일, Prometheus 보존 기간은 15일이다.
- **FR-12 개발 서비스 실행:** 개발·데모 환경의 컨테이너 서비스를 Docker Compose로 정의한다. MariaDB는 금융 업무 데이터의 유일한 원본이며 데이터는 영속 볼륨에 저장한다. FastAPI는 MariaDB health check가 통과한 뒤 연결한다. 관측 스택은 Grafana Alloy, Loki, Prometheus, Grafana 및 각 저장 볼륨을 사용한다. MongoDB 7.0.45는 호스트 포트와 NPM 네트워크에 공개하지 않는 전용 영속 서비스다. `.env.example`과 로컬 `.env`는 적재기가 사용할 `MONGO_URL=mongodb://mongo:27017`과 `MONGO_DB_NAME=podobank_events`를 제공한다. 별도 이벤트 적재기가 MariaDB 아웃박스를 MongoDB에 투영하며 FastAPI 요청 경로는 MongoDB에 연결하지 않는다. 최종 제품 구성에는 UI 단계에서 추가한 Nginx도 포함한다.
- **FR-13 로컬 로그인:** 은행 직원은 카카오 계정 없이 휴대전화번호와 비밀번호로 로그인한다. 고객은 가입할 때 비밀번호를 선택적으로 설정할 수 있고, 비밀번호를 비워 두면 카카오 로그인만 가능하다. 고객은 카카오 로그인 상태에서 비밀번호를 설정한 뒤 로컬 로그인을 사용할 수 있다. 로컬 로그인은 비밀번호가 설정된 계정에만 허용한다. 로컬 로그인도 FR-3과 동일한 JWT HttpOnly 쿠키 세션을 발급하며, 권한은 DB의 계정 등급으로 판별한다.
- **FR-14 HTTPS 원격 미리보기:** 팀원은 `https://podobank.oci-dev.duckdns.org`에서 데모 화면을 보고 `https://podobank-api.oci-dev.duckdns.org`에서 API를 사용할 수 있다. NPM은 두 호스트의 TLS를 각각 종료해 프론트엔드와 API 컨테이너에 전달하며 두 호스트 모두 Access List 없이 공개한다. 사용자는 UI를 NPM 인증 없이 열고 앱의 고객 또는 직원 로그인으로 인증한다. API는 UI origin만 CORS 허용하고 사용자 금융 기능은 JWT 세션과 DB 역할로 보호한다. CORS는 비브라우저 클라이언트의 접근을 막지 않으므로 두 호스트 모두 인터넷에서 직접 접근 가능하다. `/health`, `/auth/login` 등 앱 세션이 필요하지 않은 API 경로도 인터넷에서 도달할 수 있으므로 이 미리보기는 합성 개발 데이터만 사용한다. 프록시 네트워크에는 프론트엔드와 API만 연결하고 데이터베이스는 연결하지 않는다. 미리보기 Compose 설정은 별도 overlay로 제공하여 기본 로컬 개발 구성을 바꾸지 않는다.
- **FR-15 커밋 이벤트 아웃박스:** 금융 상태를 성공적으로 바꾸는 각 MariaDB 트랜잭션은 그 변경을 설명하는 개인정보 최소화 이벤트를 같은 트랜잭션의 아웃박스 행으로 기록한다. 아웃박스 삽입이 실패하면 금융 변경도 롤백한다. 실패한 서비스 시도는 보장 대상에 포함하지 않고 기존 JSONL 최선 노력 기록으로 유지한다. 자동 상환 배치는 각 회차 처리 트랜잭션의 커밋된 상태 변경마다 아웃박스 이벤트를 기록하며, 기존 JSONL의 배치 집계 이벤트는 실행당 한 건으로 유지한다.
- **FR-16 MongoDB 이벤트 투영:** 독립 적재기는 MariaDB 아웃박스를 재시도하며 MongoDB에 비동기 반영한다. 전달은 최소 한 번(at-least-once)이며 이벤트 UUID를 MongoDB `_id`로 사용해 재실행·재시도 시 중복 문서를 만들지 않는다. MongoDB 장애는 API 금융 동작을 막지 않고 대기 행을 잃지 않는다. 성공적으로 투영된 아웃박스 행도 자동 삭제하지 않으며, MongoDB 복구 시 전체 재투영이 가능해야 한다.

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
- **NFR-5 금융 동작 격리:** JSONL 파일·Loki·Prometheus의 기록 장애는 이미 커밋된 금융 동작의 결과를 바꾸지 않는다. 반면 성공 이벤트 아웃박스는 금융 변경과 같은 MariaDB 트랜잭션의 일부이므로 아웃박스 기록 실패는 해당 변경을 롤백한다. MongoDB 또는 적재기 장애는 금융 API의 기동·요청 처리에 영향을 주지 않고 아웃박스 재시도 지연만 만든다. 관측·투영 구성은 개발·데모용이며 운영 배포의 가용성 보장은 범위에 포함하지 않는다.
- **NFR-7 MongoDB 격리:** MongoDB는 개발·데모 Compose 서비스로만 실행하고 호스트나 NPM 네트워크에 포트를 공개하지 않는다. 별도 적재기만 MongoDB에 연결하며 FastAPI는 MongoDB 클라이언트를 만들지 않는다. MongoDB 7.0은 2027-08-31 지원 종료 전에 호스트 커널 호환성을 해결한 뒤 지원 중인 주요 버전으로 올린다.
- **NFR-8 이벤트 전달과 보존:** 커밋된 성공 이벤트는 MariaDB 아웃박스에 남고, 적재기는 성공 확인 전까지 재시도한다. MongoDB 기록 후 MariaDB 확인 전에 프로세스가 죽어도 같은 UUID로 다시 upsert할 수 있다. 재시도는 지수형 대기 시간을 사용하고 레코드를 자동 폐기하지 않는다. 투영 완료 여부와 관계없이 아웃박스 행을 보존하며 자동 정리하지 않는다.
- **NFR-6 원격 미리보기 보안:** 원격 미리보기 UI와 API 모두 HTTPS를 사용하고 NPM Access List 없이 공개한다. UI의 고객·직원 화면은 앱 로그인이 필요하다. API는 `AUTH_COOKIE_SECURE=true`, UI origin만 허용하는 credentialed CORS, JWT 세션 및 DB 역할 검증을 사용한다. CORS는 비브라우저 요청의 접근 제어가 아니다. `/health`, `/auth/login` 등 앱 세션이 필요하지 않은 경로도 인터넷에서 도달 가능하다. API는 합성 개발 데이터만 제공하고 기본 개발 JWT 키, 직원 비밀번호, 데모 고객 비밀번호를 사용하지 않는다. 미리보기 구성에서 MariaDB 포트는 NPM 네트워크에 노출하지 않는다. 이 환경은 운영 배포가 아니다.

## User experience and behavior

- 고객은 카카오 로그인 후 휴대전화번호와 프로필 정보를 등록하고 자동 발급된 기본 계좌로 입출금, 이체, 대출 기능을 이용한다. 비밀번호를 설정한 고객은 휴대전화번호와 비밀번호로도 로그인할 수 있다.
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

- MariaDB는 정형 금융 데이터와 감사 이벤트의 내구성 있는 원본이다. 각 성공 상태 변경은 해당 데이터와 아웃박스 이벤트를 동일 트랜잭션에 기록한다.
- MongoDB는 MariaDB 아웃박스에서 온 유연한 금융 이벤트 문서를 저장·조회하는 투영 저장소다. 문서에는 공통 UUID, 이벤트 유형, UTC 시각, 스키마 버전이 있고 기존 금융 이벤트의 정적 필드만 payload에 둔다.
- 이벤트 적재기는 MariaDB 아웃박스에서 행을 빌려 MongoDB에 이벤트 UUID를 `_id`로 upsert하고 성공 후 투영 상태를 MariaDB에 기록한다. 전달 의미는 최소 한 번이며 MongoDB 중복 문서는 고유 ID로 방지한다. API 요청 경로에서 MariaDB와 MongoDB를 직접 이중 기록하지 않는다.
- 성공 아웃박스 이벤트는 기존 정적 `operation`, `outcome`, `reason` 필드 및 상환 집계 필드를 사용한다. 기술적 `event_id`, 스키마 버전과 상환 배치의 `batch_id`만 봉투 메타데이터로 추가할 수 있다. 사용자·계좌 식별자, 금액, 이름, 전화번호, 원시 예외 메시지는 MongoDB에도 저장하지 않는다.
- 일반 금융 서비스 호출은 성공 업무 트랜잭션마다 이벤트 한 건을 기록한다. 자동 상환은 각 회차 트랜잭션에서 실제 상태를 바꾼 경우만 회차 이벤트를 기록한다. 이 문서의 회차 이벤트는 `processed=1`, `paid` 또는 `overdue` 중 하나만 1, 나머지는 0으로 두고, 건너뛴 회차는 아웃박스에 쓰지 않는다. 같은 실행의 회차 이벤트는 기술적 `batch_id`로 묶는다. 기존 JSONL은 계속 서비스 호출당 한 건의 배치 집계를 유지한다.
- 실패한 서비스 시도는 아웃박스에 넣지 않는다. 현재 JSONL 성공·실패 이벤트와 Alloy → Loki·Prometheus 관측 흐름은 유지하며, 실패 이벤트의 파일 기록은 최선 노력이다.
- MariaDB 아웃박스 행은 투영 완료 뒤에도 유지하며 자동 삭제하지 않는다. 적재기의 재생 모드는 보존된 행을 MongoDB에 다시 upsert해 MongoDB 저장 볼륨 재생성을 지원한다.
- Loki는 애플리케이션·런타임 및 서비스 수준 JSONL 이벤트를 수집한다. MongoDB의 커밋 이벤트 문서는 Loki 로그와 별개의 조회용 투영이다.
- 현재 Docker 호스트의 커널은 `7.0.0-1013-oracle`이다. MongoDB 공식 8.0 릴리스 노트는 Linux 커널 `6.19`부터 `7.0.13`까지 시작 호환성 문제가 있으며 `7.0.14` 이상으로 업그레이드하도록 안내한다. 이 환경에서 `mongo:8.0.34`는 시작 직후 종료됐고 `mongo:7.0.45`는 기동 및 `mongosh` ping에 성공했다. 따라서 개발용 설치는 `mongo:7.0.45`를 사용한다. MongoDB 7.0의 지원 종료일은 2027-08-31이므로, MongoDB 8.0 이상으로 올릴 때는 먼저 호스트 커널 호환성을 해결하고 지원 종료 전에 별도 변경으로 진행한다. ([MongoDB 8.0 릴리스 노트](https://www.mongodb.com/docs/v8.0/release-notes/8.0/), [MongoDB 라이프사이클](https://www.mongodb.com/legal/support-policy/lifecycles))
- 현재 Mongo 호스트 커널과 호환성 제약, MongoDB 버전 업그레이드 시점은 FR-12 및 NFR-7의 기준을 따른다.

`고객 카카오 로그인 → FastAPI 사용자 확인/기본 계좌 발급`

`고객·직원 로컬 로그인 → FastAPI 사용자 확인/JWT 세션 발급`

`브라우저 → Nginx (Vue 3 정적 앱 서빙)`

`로컬 브라우저 → FastAPI (금융 API 직접 호출)`

`미리보기 브라우저 → NPM HTTPS UI host → Vue 3`

`미리보기 브라우저 → NPM HTTPS API host → FastAPI`

`FastAPI 데이터베이스: MariaDB`

`FastAPI 금융 서비스 → MariaDB 금융 행 + outbox 행 (하나의 트랜잭션)`

`event-projector → MariaDB outbox → MongoDB 금융 이벤트 문서`

`FastAPI·상환 CLI → JSONL → Alloy → Loki·Prometheus`

FastAPI는 MariaDB에만 연결한다. 별도 event-projector가 MariaDB outbox를 읽고 `MONGO_URL`, `MONGO_DB_NAME`으로 MongoDB에 비동기 반영한다. MongoDB는 전용 named volume을 사용하며 호스트 포트나 NPM 네트워크에 연결하지 않는다. MongoDB 투영 실패는 금융 요청을 되돌리지 않고 outbox 재시도로 복구한다.

### 모듈 경계와 의존 방향

- `features/transactions`와 `features/loans`는 각 금융 상태 변경과 트랜잭션 범위를 소유한다. 성공 변경을 커밋하기 전에 같은 SQLAlchemy Core `Connection`으로 outbox writer를 호출한다.
- `features/financial_outbox`는 이벤트 봉투 검증, MariaDB outbox insert/claim/ack/retry SQL, MongoDB 투영과 재생을 소유한다. SQLAlchemy Core 직접 SQL을 사용하고 ORM을 사용하지 않는다.
- `database.py`와 `schema.py`는 Engine과 테이블 초기화를 소유한다. 금융 도메인 모듈이 outbox SQL 테이블을 직접 복제 구현하지 않는다.
- `cli.py`는 `project-events` 실행을 시작하고 종료한다. API 수명 주기와 CLI는 outbox writer를 공유하지만 MongoDB 접근 모듈은 event-projector에서만 불러온다.
- 허용 의존은 `transactions/loans → financial_outbox writer → SQLAlchemy Connection`, `cli → financial_outbox projector → MariaDB + PyMongo`다. outbox/projector는 거래·대출 서비스나 JSONL 관측 모듈에 의존하지 않는다.

로컬 개발에서는 Vue가 FastAPI origin을 직접 호출한다. 원격 미리보기는 NPM의 UI 호스트를 프론트엔드 컨테이너에, 별도 API 호스트를 FastAPI 컨테이너에 전달한다. 미리보기 빌드는 browser-visible API base로 `https://podobank-api.oci-dev.duckdns.org`를 사용한다. 두 호스트는 같은 사이트의 서로 다른 origin이므로 API의 HTTPS 전용, HttpOnly, SameSite=Lax 쿠키를 credential 포함 요청으로 전달한다. FastAPI CORS는 UI origin과 필요한 HTTP method·header만 허용하고 credentials를 허용한다. credentials를 허용할 때 origin·method·header에 와일드카드(`*`)를 사용하지 않는다. NPM은 어느 호스트에도 Access List를 요구하지 않으며 앱 로그인과 API 권한 검증은 그대로 유지한다.

## Remote preview design decision

- **Intent:** 팀원이 운영 중인 개발 서버에서 기존 화면을 HTTPS로 열어 리뷰할 수 있게 한다.
- **Goals:** UI와 API용 전용 HTTPS URL 두 개, 기존 NPM 사용, 교차 origin API 세션 쿠키 동작, DB를 프록시 네트워크에서 격리, 기본 로컬 Compose 구성을 그대로 유지.
- **Non-goals:** 운영 배포, 실제 금융 데이터, 외부 공개 가입, NPM 자체 설치·관리자 계정 변경, Kakao OAuth 자격 증명 발급.
- **Approaches considered:** (1) UI와 API를 한 호스트에 두고 `/api/` 경로로 나눈다. 한 DNS 이름과 같은 origin 쿠키를 사용하지만 사용자가 UI와 API 주소를 따로 원한다. (2) UI와 API를 별도 HTTPS 호스트로 나눈다. NPM의 두 Proxy Host와 DNS 레코드, 정확한 CORS 및 교차 origin 쿠키 설정이 필요하다. 사용자는 두 호스트 모두 NPM Access List 없이 공개하기로 했다. API는 인터넷에서 직접 접근 가능하며 브라우저 CORS는 비브라우저 클라이언트를 제한하지 않는다. (3) API 포트를 직접 공개한다. NPM TLS를 우회하므로 제외한다.
- **Selected approach:** 두 번째 방식. UI는 `podobank.oci-dev.duckdns.org`, API는 `podobank-api.oci-dev.duckdns.org`를 사용한다. 두 호스트 모두 NPM Access List 없이 HTTPS로 공개한다. UI 고객·직원 기능은 앱 로그인이 필요하고 API는 정확한 UI origin CORS와 앱 JWT·DB 역할 검증을 사용한다. API는 합성 개발 데이터만 제공한다.
- **Constraints:** 서비스 컨테이너는 기존 NPM Docker 네트워크에 연결해야 한다. 프록시 네트워크에는 API와 프론트엔드만 연결한다. 실제 DuckDNS 레코드와 인증서는 서버 운영자가 확인해야 한다. NPM 관리자 자격 증명은 저장소나 채팅에 기록하지 않는다.
- **Builder decisions:** 미리보기 전용 Compose overlay와 비밀 값 템플릿을 제공하고, NPM Access List 없이 공개하는 UI·API Proxy Host 두 개와 각각의 TLS 설정을 운영 문서에 기록한다. 비밀 값은 ignored local env 파일에만 둔다.

Docker Compose로 MariaDB, FastAPI, Vue와 관측 스택을 실행한다. 기본 Compose 설정은 로컬 개발용이다. 미리보기 전용 overlay는 API와 프론트엔드만 기존 NPM 외부 네트워크에 연결하고, MariaDB 데이터는 기존 영속 볼륨에 보존하며 FastAPI는 MariaDB health check 이후 연결한다. 스키마와 샘플 데이터의 재생성은 개발자가 명령으로 명시했을 때만 수행한다.

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
- **이벤트 투영 저장소:** MongoDB 7.0.45, PyMongo (잠금 파일에서 버전 고정)
- **SQL 접근:** SQLAlchemy Core, 직접 작성한 SQL, ORM 미사용
- **개발·데모 서비스 실행:** Docker Compose
- **브라우저 API 연결:** 로컬은 FastAPI 직접 origin, NPM 미리보기는 `https://podobank-api.oci-dev.duckdns.org` base; FastAPI CORS는 UI의 정확한 origin과 필요한 method·header를 명시하고 credential 포함 요청을 허용
- **HTTPS 미리보기:** `compose.npm-preview.yaml` 외부 네트워크 overlay, UI host `podobank.oci-dev.duckdns.org`와 API host `podobank-api.oci-dev.duckdns.org`, 두 호스트 모두 NPM Access List 없이 공개, 앱 로그인과 API JWT 인증, HTTPS 전용 쿠키
- **가입·로그인:** 고객 카카오 로그인 및 선택적 비밀번호 로컬 로그인, 직원 로컬 로그인
- **관측:** Grafana Alloy, Loki, Prometheus, Grafana. Alloy는 금융 이벤트 스트림을 처리해 Prometheus의 `podobank_financial_operations_total` 카운터를 만든다.
- **금융·프로필 데이터:** 사용자, 휴대전화번호, 나이, 성별, 혼인 상태, 직장 유무, 계정 등급, 계좌, 잔액, 이체, 대출 상품, 대출 신청·승인·상환
- **기본키와 조회 키:** `users.id`와 `accounts.id`는 짧은 숫자 기본키로 둔다. 전화번호와 카카오 사용자 식별자는 각각 고유 인덱스를 둔다. JWT의 `sub`와 원장 행의 계좌·사용자 참조 값은 내부 사용자·계좌 ID를 사용한다. 계좌 소유자와 계좌번호도 고유 인덱스로 찾는다. 원장 `entry_id`는 `BIGINT UNSIGNED AUTO_INCREMENT`로 생성한다. 날짜 파티션 키 `posted_at`은 원장 테이블의 모든 고유 키에 포함하며, 원장 기본키는 `(entry_id, posted_at)`으로 둔다.
- **원장 조회 인덱스:** `(account_id, posted_at, entry_id)` 복합 인덱스를 두어 계좌별 날짜 범위 조회와 시간순 정렬을 지원한다. 날짜 범위 조건을 포함해 파티션을 제한한다. 원장 외래 키 인덱스는 만들지 않는다.
- **이벤트·지표 데이터:** 정적 동작·결과·사유 코드와 UTC 시각으로 이루어진 JSONL 및 MariaDB outbox 이벤트, 상환 회차 집계 수, 그리고 `operation`, `outcome`, `reason` 라벨을 가진 `podobank_financial_operations_total` 카운터. outbox와 MongoDB에는 기술적 이벤트 UUID만 허용하며 사용자·계좌 식별자, 휴대전화번호, 이름, 금액, 원시 예외 문자열은 저장하지 않는다.

## Security, privacy, and policy constraints

- 계좌·거래 데이터와 사전 등록 사용자 정보는 데모용으로 만든다. 가입 사용자의 휴대전화번호는 검색을 위해 저장한다.
- 휴대전화번호를 이벤트·지표에 기록하지 않는다.
- 나이, 성별, 혼인 상태, 직장 유무도 이벤트·지표에 기록하지 않는다.
- 카카오 인증 토큰과 비밀 키를 이벤트·지표에 넣지 않으며 저장소에 커밋하지 않는다.
- 비밀번호는 평문으로 저장하거나 이벤트·지표에 기록하지 않는다.
- MariaDB outbox와 MongoDB 투영 이벤트에도 이벤트에 허용된 정적 필드와 기술적 이벤트 UUID만 저장한다. 실패 이벤트는 기존 JSONL 경로만 사용한다.
- 앱 JWT는 HttpOnly 쿠키로 전달하며 브라우저에서 읽을 수 있는 저장소에 보관하지 않는다.
- 대출 승인 API는 은행 직원만 사용할 수 있어야 한다. 초기 데이터베이스에 등록된 은행 직원 한 명만 승인 권한을 가진다.
- 관측 컨테이너 포트는 호스트에 노출하지 않고 Grafana UI만 `127.0.0.1`에 바인딩한다. Grafana 관리자 비밀번호는 개발용 `.env`에서 제공하며 `.env.example` 값은 로컬 데모 전용이다.

## Risks and concerns

- 이체 처리 중 한 계좌만 갱신되면 잔액이 맞지 않을 수 있다.
- 원장 외래 키가 없으므로 애플리케이션 오류가 고아 원장 행을 만들 수 있다. 관련 계정 존재 확인, 계좌 행 잠금, 잔액 갱신과 원장 삽입을 한 트랜잭션으로 묶고, 현재 범위에는 참조 대상 금융 레코드의 물리 삭제를 추가하지 않는다.
- 잔액 부족 거래도 실패 이벤트로 기록해야 동작 결과를 관측할 수 있다.
- 금융 이벤트 파일은 Loki 보존 기간과 별개로 named volume에 남고 자동 정리하지 않는다. 이벤트량이 누적될 수 있으므로 이 구성은 개발·데모용이며, 용량 관리가 필요한 운영 배포는 별도 설계가 필요하다.
- outbox 쓰기 장애는 성공 금융 변경과 같은 MariaDB 트랜잭션을 실패시킨다. 이 결합이 금융 변경과 성공 이벤트의 유실 방지 경계다.
- MongoDB나 적재기 장애가 길어지면 outbox가 커질 수 있다. 자동 폐기는 금지하고, 개발·데모 운영자는 영속 볼륨 용량을 관리해야 한다.
- outbox가 있는 MariaDB 데이터와 MongoDB 데이터 볼륨이 모두 유실되는 호스트 재해는 이 변경의 가용성 보장 범위가 아니다. MongoDB 볼륨만 재생성하는 경우 보존된 outbox에서 재생할 수 있다.
- 실패 시도 이벤트는 아웃박스 보장 범위 밖이다. JSONL 쓰기 장애 때 실패 관측 이벤트가 누락될 수 있다.

## Acceptance criteria

- 최초 카카오 로그인 때 기본 계좌 한 개가 발급되고 재로그인 때 중복 발급되지 않는다.
- 비밀번호를 설정하지 않은 고객은 로컬 로그인에 실패하고 카카오 로그인만 사용할 수 있다. 고객은 인증된 카카오 세션에서 비밀번호를 설정한 뒤 로컬 로그인할 수 있다.
- 사전 등록된 은행 직원은 카카오 로그인 없이 로컬 로그인할 수 있고, 로그인 뒤에도 직원 전용 API는 직원 역할만 허용한다.
- Docker Compose 기본 설정으로 로컬 개발 서비스를 실행할 수 있고, 미리보기 overlay는 API와 프론트엔드만 기존 NPM 네트워크에 추가한다.
- `https://podobank.oci-dev.duckdns.org`가 NPM 인증 없이 NPM TLS를 거쳐 Vue 앱을 표시하고, `https://podobank-api.oci-dev.duckdns.org/health`가 NPM 인증 없이 FastAPI에 도달한다. 두 호스트 모두 NPM이 HTTP upstream으로 전달한다.
- 미리보기 빌드가 API 호스트를 사용하고, UI origin의 CORS 사전 요청이 허용되며, UI에서 실행한 API 로그인과 이후 요청에 Secure, HttpOnly, SameSite=Lax JWT 쿠키가 포함된다. 로컬 빌드는 기존 localhost API origin을 계속 사용한다.
- 미리보기 API·직원·데모 고객 비밀 값은 예시 또는 개발 기본값이 아니며 저장소에 커밋되지 않는다. 두 호스트 모두 NPM 인증 없이 접근할 수 있다. API 호스트는 직접 접근 가능하고 CORS는 비브라우저 요청을 차단하지 않으며, 사용자별 금융 API는 유효한 앱 세션과 DB 역할을 요구한다.
- NPM 연결을 위한 MariaDB 네트워크 노출은 없다.
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
- Docker Compose 기본 및 NPM overlay 설정 검증은 예시 env 파일 기반으로 실행할 수 있다. 관측 컨테이너 포트는 호스트에 바인딩하지 않으며 Grafana만 loopback에 공개한다.
- MongoDB 컨테이너는 health check를 통과하고 전용 named volume을 사용한다. 재시작 또는 컨테이너 재생성 뒤에도 MongoDB 데이터가 남는다.
- MongoDB에 호스트 포트 매핑이 없고 NPM 외부 네트워크에도 연결되지 않는다.
- `.env.example`과 로컬 `.env`의 `MONGO_URL=mongodb://mongo:27017`, `MONGO_DB_NAME=podobank_events` 설정이 제공되고, Compose 내부 서비스에서 `mongo` 이름으로 MongoDB에 접속할 수 있다.
- `docker compose exec mongo mongosh --quiet --eval 'db.adminCommand({ping: 1})'` 명령이 성공해 MongoDB health를 확인할 수 있다.
- 커밋되는 각 성공 금융 업무 트랜잭션에는 동일 MariaDB 트랜잭션의 outbox 행이 정확히 하나 포함된다. outbox insert 실패 시 잔액·원장·대출 상태 변경도 함께 롤백된다.
- 자동 상환 배치의 각 회차 상태 변경은 같은 회차 DB 트랜잭션에서 이벤트를 남기며, 건너뛴 회차에는 outbox 이벤트가 없다. 기존 JSONL 배치 이벤트는 실행당 한 건과 집계값을 유지한다.
- 실패 시도에는 outbox 행을 만들지 않고 기존 JSONL 성공·실패 기록 경로를 유지한다.
- 별도 event-projector가 MongoDB 이벤트를 비동기로 투영한다. MongoDB 중지 상태에서도 API는 기동되고 금융 성공 변경은 MariaDB outbox에 남으며, MongoDB 복구 뒤 투영을 재개한다.
- MongoDB가 upsert를 완료한 직후 프로세스가 중지되어 MariaDB 확인이 빠진 경우 재시작 뒤 같은 `event_id`를 재전달해 중복 문서 없이 복구한다.
- 투영 완료된 outbox 행은 자동 삭제되지 않으며, 재생 모드에서 저장된 행을 다시 MongoDB에 upsert할 수 있다.
- MongoDB event document에는 정적 이벤트 필드와 기술적 UUID만 들어가며 사용자·계좌 식별자, 금액, 전화번호, 이름, 원시 예외 문구를 포함하지 않는다.

## Open questions

원장 파티션은 소유자가 정한 월별 간격을 사용한다. 원장 보존 기간은 미정이며 승인된 정책 전에는 자동 파티션 삭제를 허용하지 않는다. 관측 로그의 Loki 보존 기간은 30일, Prometheus 보존 기간은 15일이며 입력 JSONL 볼륨은 자동 삭제하지 않는다.
