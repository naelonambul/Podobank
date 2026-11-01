# Implementation Plan

## Summary

Compose의 API 컨테이너가 사용할 MariaDB URL을 Compose 파일 안에서 조립하지 않고, 로컬 `.env`의 `COMPOSE_DATABASE_URL`에서 받도록 한다. `.env.example`에서는 기존 MariaDB 변수들을 조합해 컨테이너 내부 호스트명 `db`를 사용하는 URL을 만든다. 사용자명과 비밀번호를 Compose YAML의 URL 안에 직접 보간하지 않는다.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `compose.yaml`: API의 `DATABASE_URL`을 필수 `COMPOSE_DATABASE_URL` 값으로 설정한다.
- `.env.example`: 기존 `MARIADB_DATABASE`, `MARIADB_USER`, `MARIADB_PASSWORD` 값을 참조하는 `COMPOSE_DATABASE_URL` 예시를 추가한다.

## Order of work

1. `.env.example`에 `COMPOSE_DATABASE_URL=mysql+pymysql://${MARIADB_USER}:${MARIADB_PASSWORD}@db:3306/${MARIADB_DATABASE}`를 추가한다. 참조 대상 변수보다 뒤에 두어 Compose의 `.env` 변수 보간으로 완성 URL을 만든다.
2. `compose.yaml`의 API 환경에서 `DATABASE_URL`을 `${COMPOSE_DATABASE_URL:?Set COMPOSE_DATABASE_URL in the local .env file}`로 설정한다. YAML에 사용자명·비밀번호를 조립하는 URL 식을 두지 않는다.
3. `.env.example`을 지정해 Compose 구성이 정상 해석되는지 확인하고, 해석된 API URL의 호스트가 `db`, 데이터베이스가 `podobank_dev`인지 비밀 값을 출력하지 않고 검증한다.
4. 로컬 `.env`를 사용하는 Compose 스택을 올려 API health endpoint가 정상 응답하는지 확인한다. 이어 저장소 전체 검증을 실행하고 변경 diff와 `repo.py status`를 확인한다.

## Tests and proof

- `docker compose --env-file .env.example config --quiet`가 성공해야 한다.
- Compose 설정에서 API의 `DATABASE_URL`이 서비스 DNS 이름 `db`와 `podobank_dev`를 가리키는지 검사한다. 검증 과정에서 URL 전체나 자격 증명은 출력하지 않는다.
- `docker compose config --quiet`, Compose API 서비스 실행, `/health` 확인이 성공해야 한다.
- `python3 scripts/repo.py verify --change compose-database-url-env --full`이 모든 등록 검사를 완료하고 실패 또는 차단된 검사가 없어야 한다.
- 최종 diff에서 `.env.example`과 `compose.yaml` 외의 제품 파일이 바뀌지 않았는지, `.env`나 자격 증명이 추적 파일에 포함되지 않았는지 확인한다.

## Risks and mitigations

- `.env.example`의 변수 순서나 보간 문법이 잘못되면 Compose URL이 해석되지 않을 수 있다. 예시 파일을 직접 `--env-file`로 지정해 검증한다.
- 로컬 `.env`에 `COMPOSE_DATABASE_URL`이 없으면 API 설정 해석이 명시적으로 실패한다. 필수 변수 오류 메시지로 설정 이름과 `.env` 위치를 안내한다.
- GitGuardian의 기존 알림은 과거 커밋 `91f7b2f`에 대한 기록일 수 있어 이 수정만으로 자동 종료되지 않을 수 있다. 이 변경은 Git 기록을 다시 쓰거나 알림 상태를 대신 변경하지 않는다.

## Rollback or recovery

- 검증에 실패하면 새 변경의 `compose.yaml`과 `.env.example` 수정만 되돌리고, 병합된 MariaDB 도입 변경이나 로컬 데이터 볼륨은 건드리지 않는다.
- 기존 로컬 `.env`는 무시 파일이며 이 변경 범위 밖이다. 필요하면 소유자가 예시 파일을 기준으로 로컬 값을 갱신한다.

## Open questions

없음.
