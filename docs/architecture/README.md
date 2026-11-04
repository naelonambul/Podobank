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

## OCI 서비스 카드 로고

시스템 아키텍처 HTML은 아래 공식 사이트 또는 프로젝트 저장소의 로고를 로컬 파일로 사용합니다. 각 원본은 2026-11-04에 가져왔으며, 다이어그램 카드에서 제품을 식별하는 용도입니다.

| 파일 | 프로그램 | 공식 출처 및 사용 안내 |
| --- | --- | --- |
| `assets/nginx.svg` | NGINX | [NGINX 공식 사이트 로고](https://nginx.org/img/nginx_logo.svg). 표시 이름은 NGINX로 유지하고 로고는 원본 비율과 색상을 보존합니다. |
| `assets/fastapi.png` | FastAPI | [FastAPI 공식 문서 로고](https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png). 원본을 수정하지 않고 표시합니다. |
| `assets/mariadb.png` | MariaDB | [MariaDB 공식 로고 페이지](https://mariadb.com/about-us/logos/). 제공된 검정 세로형 로고를 사용하며 색상을 바꾸지 않고 비율과 여백을 유지합니다. |
| `assets/mongodb-mark.svg` | MongoDB | [MongoDB 공식 브랜드 리소스](https://www.mongodb.com/company/newsroom/brand-resources)에서 연결되는 [공식 로고 마크 원본 SVG](https://images.contentstack.io/v3/assets/blt7151619cb9560896/blta30d0168850404a8/65fda6758f44440029c3a12a/la1a1agcxt7ppntea-logo-marks.svg). 원본의 진한 청록색 잎 모양만 독립 표시하며, 형태와 색상은 바꾸지 않고 카드의 `MongoDB` 텍스트와 함께 사용합니다. |
| `assets/grafana-alloy.svg` | Grafana Alloy | [Grafana 공식 Alloy 로고](https://grafana.com/media/oss/alloy/alloy-logo.svg). 원본 비율을 유지합니다. |
| `assets/loki.svg` | Loki | [Grafana 공식 Loki 로고](https://grafana.com/static/img/logos/logo-loki.svg). 원본 비율을 유지합니다. |
| `assets/prometheus.svg` | Prometheus | [Prometheus 공식 저장소 로고](https://github.com/prometheus/prometheus/blob/main/documentation/images/prometheus-logo.svg). 프로젝트 이름과 함께 표시합니다. |
| `assets/grafana.svg` | Grafana | [Grafana 공식 저장소 아이콘](https://github.com/grafana/grafana/blob/main/public/img/grafana_icon.svg). 프로젝트 이름과 함께 표시합니다. |

로고는 해당 제품을 식별하는 목적으로만 사용하며 제품의 보증이나 제휴를 의미하지 않습니다. 모든 이미지는 저장소에 포함되므로 렌더링 중 외부 URL을 요청하지 않습니다.
