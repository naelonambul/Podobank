# Stack Versions

Version audit date: 2026-11-01.

Use the latest upstream LTS line when the project publishes one. Otherwise use
the current supported stable release/channel. Pin exact versions in container
images and lockfiles. Re-check upstream support and patch levels before adding
the UI and observability services; those services are not configured yet.

| Component | Selected version | Upstream support policy |
|---|---:|---|
| Python | 3.13.18 | Security-only support through 2029-10; official binary installers ended with 3.13.17. Local development accepts Python 3.13.x; use the newest patch available. |
| uv | 0.13.6 | Current stable project package manager; no separate LTS line. |
| MariaDB | 12.3.3 | Latest Community LTS line. |
| FastAPI | 0.162.0 | No separate LTS line; locked stable release. |
| HTTPX | 0.28.1 | No separate LTS line; locked stable release. |
| PyJWT | 2.15.1 | No separate LTS line; locked stable release. |
| PyMySQL | 1.2.3 | No separate LTS line; locked stable release. |
| SQLAlchemy | 2.1.6 | No separate LTS line; locked stable release. |
| Uvicorn | 0.54.0 | No separate LTS line; locked stable release. |
| argon2-cffi | 25.1.0 | No separate LTS line; locked stable release. |
| anyio | 4.16.0 | No separate LTS line; locked stable release. |
| Ruff | 0.17.3 | No separate LTS line; locked stable release. |
| Node.js | 26.13.0 | LTS (`Lithium`); used for the later Vue build. |
| Vue | 3.5.44 | Current stable release; 3.6 is still a prerelease. |
| Nginx | 1.30.6 | Stable channel; Nginx does not publish a formal LTS line. |
| Grafana Alloy | 1.21.3 | Current stable release; no formal LTS line. |
| Loki | 3.7.9 | Current stable release; no formal LTS line. |
| Prometheus | 3.13.3 | Supported LTS line. |
| Grafana | 13.3.0 | Current supported patch line; Grafana does not label an OSS LTS line. |

The API Docker image installs production dependencies with `uv sync --locked
--no-dev --no-editable`, so its package versions come from `uv.lock`.

## MariaDB volume upgrades

The existing development volume may contain data written by MariaDB 11.8.9.
Before starting MariaDB 12.3.3 against that volume, take a backup or have the
owner approve resetting disposable development data. MariaDB does not support
in-place major-version downgrades. If recovery to 11.8 is needed after 12.3 has
modified the data directory, restore a pre-upgrade backup into a fresh volume;
do not start 11.8 against the modified 12.3 data directory.

## Sources

- [Python release versions](https://www.python.org/doc/versions/) and [Python branch support lifecycle](https://devguide.python.org/versions/)
- [uv 0.13.6 release](https://github.com/astral-sh/uv/releases) and [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [MariaDB 12.3 LTS announcement](https://mariadb.org/mariadb-server-12-3-lts-released/) and [Q3 2026 maintenance releases](https://mariadb.org/mariadb-server-12-3-11-8-11-4-and-10-11-q3-2026-maintenance-releases-and-goodbye-10-6/)
- [MariaDB major-version downgrade guidance](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/downgrading-between-major-versions-of-mariadb)
- [Node.js 26.13.0 LTS](https://nodejs.org/en/blog/release/v26.13.0)
- [Vue releases](https://github.com/vuejs/core/releases)
- [Nginx stable and mainline releases](https://nginx.org/en/download.html)
- [Grafana Alloy releases](https://github.com/grafana/alloy/releases)
- [Loki releases](https://github.com/grafana/loki/releases)
- [Prometheus LTS policy](https://prometheus.io/docs/introduction/release-cycle/) and [release versions](https://github.com/prometheus/prometheus/releases)
- [Grafana version support policy](https://grafana.com/docs/grafana/latest/upgrade-guide/when-to-upgrade/)
