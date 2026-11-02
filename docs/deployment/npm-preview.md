# PodoBank preview through Nginx Proxy Manager

This optional deployment serves the demo at `https://podobank.oci-dev.duckdns.org`. Nginx Proxy Manager (NPM) terminates HTTPS, protects the host with an Access List, sends `/api/` to FastAPI, and sends all other paths to the Vue frontend. The default local Compose setup is unchanged.

This is a synthetic-data development demo, not a production deployment. Keep NPM Access List authentication enabled. The application also requires its normal customer or bank employee login.

## Prerequisites

- `podobank.oci-dev.duckdns.org` must resolve to this server before requesting a certificate.
- The existing NPM container must be attached to the Docker network named `nginx-proxy-manager` (or set `NPM_DOCKER_NETWORK` to its actual network name).
- NPM must accept inbound ports 80 and 443 for certificate validation and HTTPS traffic.
- The operator must have an authenticated NPM admin session. Do not put NPM admin or Access List passwords in Git, repository env files, or chat.

Check the Docker network and DNS before starting:

```sh
docker network inspect nginx-proxy-manager
getent ahosts podobank.oci-dev.duckdns.org
```

If DNS does not resolve to this server, configure the DuckDNS record before requesting a certificate. Do not publish the host without a valid certificate and Access List.

## Prepare local environment files

The repository ignores `.env.npm-preview` and `.env.npm-preview.db`. Keep the existing `.env` unchanged. Create the preview files only when they do not already exist:

```sh
if [ ! -e .env.npm-preview ]; then
  install -m 600 .env.npm-preview.example .env.npm-preview
fi
if [ ! -e .env.npm-preview.db ]; then
  install -m 600 .env.npm-preview.db.example .env.npm-preview.db
fi
agent-git check-ignore -v .env.npm-preview .env.npm-preview.db
```

Replace every `replace-with-...` value before starting the preview:

- Use the same `MARIADB_DATABASE`, `MARIADB_USER`, and `MARIADB_PASSWORD` as the existing development database in both preview files. Put the existing root password only in `.env.npm-preview.db`. Do not change database credentials or initialize/reset the existing database as part of this setup.
- Set `COMPOSE_DATABASE_URL` to the matching database URL. Percent-encode reserved characters in the URL password component if the existing DB password contains any.
- Generate a unique `JWT_SECRET` with `openssl rand -hex 32` and set unique, strong bank employee and demo customer passwords. Do not reuse the documented local demo defaults.
- Keep `APP_ENV=development`, `AUTH_COOKIE_SECURE=true`, and the exact HTTPS values for `API_ORIGIN`, `FRONTEND_ORIGINS`, and `KAKAO_REDIRECT_URI`.
- The preview can use the seeded local demo login without Kakao. Kakao OAuth remains unavailable while its provider credentials are placeholders; enabling it also requires registering the HTTPS callback with Kakao.
- Keep `NPM_DOCKER_NETWORK` equal to the existing NPM Docker network name.

The DB-only file is mounted into MariaDB as its `env_file`; application signing and login secrets stay out of that container. The preview frontend API base is set by the overlay to `/api`.

## Start the preview containers

Validate the merged Compose model, then build and start the API and frontend under the existing Compose project name. The API may start its declared `db` dependency if it is stopped; existing named volumes are retained.

```sh
COMPOSE_ENV_FILE=.env.npm-preview.db \
docker compose --project-name podobank \
  --env-file .env.npm-preview \
  -f compose.yaml -f compose.npm-preview.yaml \
  config --quiet

COMPOSE_ENV_FILE=.env.npm-preview.db \
docker compose --project-name podobank \
  --env-file .env.npm-preview \
  -f compose.yaml -f compose.npm-preview.yaml \
  up -d --build api frontend
```

Only the API and frontend join the external NPM network. MariaDB remains on the PodoBank default network. Their stable NPM network aliases are `podobank-api` and `podobank-frontend`.

## Configure NPM

In the NPM admin UI:

1. Under **Access Lists**, add a list with a unique username and strong password. Do not enable unauthenticated access. Keep the credentials in the team's approved password manager.
2. Under **Hosts → Proxy Hosts**, add `podobank.oci-dev.duckdns.org` with:
   - Scheme: `http`
   - Forward Hostname / IP: `podobank-frontend`
   - Forward Port: `80`
   - Access List: the list created above
   - Block Common Exploits: enabled
3. Edit that host and add a **Custom Location**:
   - Location: `/api/`
   - Scheme: `http`
   - Forward Hostname / IP: `podobank-api`
   - Forward Port: `8000`
   - Forward Path: `/` (this removes `/api/` before FastAPI receives the request)
4. In the **SSL** tab, request a certificate for `podobank.oci-dev.duckdns.org`, enable **Force SSL**, and save only after the certificate is valid. Keep the Access List attached to the host so both UI and API paths require authentication.

No NPM custom Advanced config is needed. Do not expose the API or database with new host ports.

## Verify access

An unauthenticated request should receive HTTP `401`:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://podobank.oci-dev.duckdns.org/
```

Use the Access List username below; curl prompts for its password:

```sh
curl --fail --show-error --user '<access-list-username>' \
  https://podobank.oci-dev.duckdns.org/api/health
```

The authenticated API response should be HTTP `200` with the FastAPI health payload. Then open `https://podobank.oci-dev.duckdns.org/accounts` in a browser, complete the NPM Access List prompt, and sign in with a seeded demo customer or bank employee account. The frontend requests `/api/...` on the same HTTPS origin, so its Secure HttpOnly session cookie should be sent automatically.

## Roll back

First disable or remove the NPM Proxy Host and its `/api/` Custom Location. From the primary checkout with its existing `.env`, restore the base local configuration:

```sh
env -u COMPOSE_ENV_FILE docker compose --project-name podobank \
  --env-file .env -f compose.yaml up -d --build api frontend
```

This returns the frontend to its direct local API origin. Do not run `docker compose down -v`, delete named volumes, or reset sample data as part of rollback.
