# 아키텍처 다이어그램

이 디렉터리의 HTML 파일이 ERD와 시스템 아키텍처의 편집 가능한 원본입니다. 저장소 README에는 각 HTML 페이지를 캡처한 PNG가 표시됩니다.

둘 중 하나의 HTML 다이어그램을 수정하면 다음 명령으로 미리보기 이미지를 다시 만들고, HTML 변경과 함께 PNG 두 파일을 같은 변경에 포함하세요.

```sh
cd frontend
npm ci
npx playwright install --with-deps chromium
node scripts/render-diagram-previews.mjs
```

렌더링 도구 버전은 `frontend/package-lock.json`에 고정된 Playwright를 사용합니다.
