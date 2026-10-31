# 구현 계획

## 요약

승인된 포도뱅크 intent 문서와 spec 문서를 저장소의 최초 제품 기준선으로 설정한다. 이 변경은 제품 문서만 다루며 애플리케이션 코드 작성이나 컨테이너 실행은 포함하지 않는다. 후속 작업은 백엔드, 관측, UI 순서로 각각 별도 변경에서 진행한다.

## 변경 파일 및 구성요소

<!-- 모든 변경 파일은 change.json의 write_scope에 포함되어야 한다. -->

- `changes/podobank-product-init/intent.md`: 승인된 제품 목표, 범위, 제약사항.
- `changes/podobank-product-init/spec.md`: 승인된 기능 요구사항, SQLite에서 MariaDB로 전환하는 방식, SQLAlchemy Core와 직접 작성한 SQL, Docker Compose 서비스, Nginx/Vue에서 FastAPI로 직접 통신하는 CORS 구조.
- `intent.md`, `spec.md`: 변경 준비가 완료되면 승인된 패킷 사본으로 기준선 미설정 표시가 있는 루트 파일을 교체한다.
- `changes/podobank-product-init/plan.md`, `changes/podobank-product-init/closure.json`: 이 계획과 최종 종료 기록.

백엔드, 프론트엔드, 컨테이너, 관측 설정 파일은 이 패킷의 범위에 포함하지 않는다.

## 작업 순서

1. 소유자가 이미 승인한 intent와 spec에 이어 이 계획을 검토하고 승인한다. `python3 scripts/repo.py status --change podobank-product-init`을 실행해 변경 상태가 `readiness=ready`인지 확인한다. 준비가 완료되기 전에 루트 파일을 수정하지 않는다.
2. 루트 `intent.md`와 `spec.md`를 승인된 패킷 사본으로 각각 교체한다. 사본을 그대로 사용해 기준선 미설정 표시를 제거한다. `python3 scripts/repo.py status --change podobank-product-init`으로 두 문서가 패킷과 일치하고 변경 범위 안에 있는지 확인한다.
3. `python3 scripts/repo.py verify --change podobank-product-init --full`을 실행해 등록된 검사를 모두 수행하고, 종료 기록에 사용할 증거 경로를 보관한다.
4. `python3 scripts/repo.py close podobank-product-init --evidence <전체-검증-증거-경로>`를 실행해 `changes/podobank-product-init/closure.json`을 생성한다.
5. 전체 변경 내용과 상태를 검토한 뒤 `agent-git`으로 커밋하고, `agent-gh`로 푸시한 다음 본문에 `Change-ID: podobank-product-init`을 포함한 PR을 연다. 소유자가 PR을 검토하고 squash 방식으로 병합한다.

## 검증 및 증거

- `python3 scripts/repo.py status --change podobank-product-init`: 승인 순서, 문서 최신성, 변경 범위, 준비 상태를 확인한다.
- `python3 scripts/repo.py verify --change podobank-product-init --full`: 등록된 모든 검사를 실행한다. 현재 이 변경에 연결된 검사는 `control-plane`이며 `python3 -m unittest discover -s scripts/tests -t .`을 실행한다.
- `python3 scripts/repo.py close ... --evidence <전체-검증-증거-경로>`: 전체 검증 증거가 완전하고 현재 트리와 일치하는지 확인한 뒤 종료 기록을 작성한다.
- closure가 포함된 PR의 필수 `summary` CI 검사가 통과해야 소유자가 merge할 수 있다.

## 위험과 완화

- 승인된 문서를 수정하면 해당 승인 해시가 오래된 상태가 된다. 수정된 문서와 그 뒤에 승인된 문서를 순서대로 다시 승인하고 전체 검증 및 종료 기록을 갱신한다.
- 이 product-init 변경은 저장소 문서만 검증하며 실제 금융 기능, CORS, Compose, 이벤트 수집 동작을 검증하지 않는다. 해당 동작은 후속 구현 변경에서 검증한다.
- 루트 기준선 사본은 승인된 패킷 사본과 바이트 단위로 같아야 한다. 파일을 통째로 교체하고 `repo.py status`로 확인한다.

## 되돌리기 및 복구

- 병합 전에는 패킷 문서를 수정하고 영향받는 승인을 갱신한다. 루트 사본을 패킷과 다시 맞춘 뒤 전체 검증을 실행하고 종료 기록을 새로 만든다. 공유 Git 기록은 다시 쓰지 않는다.
- 병합 후에는 제품 기준선이 동결된다. 종료 커밋을 되돌리는 대신 새 변경 패킷으로 기준선을 수정한다.

## 미결 사항

이 product-init 변경에서 추가로 정할 사항은 없다. 백엔드 구현 세부사항은 후속 백엔드 변경에서 다룬다.
