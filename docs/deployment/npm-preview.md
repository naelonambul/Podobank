# PodoBank preview through Nginx Proxy Manager

This optional deployment serves the UI at `https://podobank.oci-dev.duckdns.org` and the API at `https://podobank-api.oci-dev.duckdns.org`. Nginx Proxy Manager (NPM) terminates HTTPS on two Proxy Hosts: the UI host forwards to Vue and the API host forwards to FastAPI. The default local Compose setup is unchanged.

This is a synthetic-data development demo, not a production deployment. Both NPM Proxy Hosts are public without an Access List. UI screens still require the application's customer or bank employee login. The API host is directly reachable from the internet, including unauthenticated routes such as `/health` and `/auth/login`. CORS only restricts browser JavaScript; it does not authenticate non-browser clients. User financial routes still require the application's JWT session and DB role.

## Prerequisites

- Both `podobank.oci-dev.duckdns.org` and `podobank-api.oci-dev.duckdns.org` must resolve to this server before requesting certificates.
- The existing NPM container must be attached to the Docker network named `nginx-proxy-manager` (or set `NPM_DOCKER_NETWORK` to its actual network name).
- NPM must accept inbound ports 80 and 443 for certificate validation and HTTPS traffic.
- The operator must have an authenticated NPM admin session. Do not put NPM admin credentials in Git, repository env files, or chat.

Check the Docker network and DNS before starting. If NPM uses a network other than `nginx-proxy-manager`, set `NPM_DOCKER_NETWORK` to that name in the shell and use the same value in `.env.npm-preview`:

```sh
NPM_DOCKER_NETWORK="${NPM_DOCKER_NETWORK:-nginx-proxy-manager}"
docker network inspect "$NPM_DOCKER_NETWORK"
getent ahosts podobank.oci-dev.duckdns.org podobank-api.oci-dev.duckdns.org
```

If either name does not resolve to this server, configure its DuckDNS record before requesting a certificate. Do not publish either host before its certificate is valid. Both hosts must use `Publicly Accessible` with no NPM Access List.

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
- Keep `APP_ENV=development` and `AUTH_COOKIE_SECURE=true`. Set `API_ORIGIN=https://podobank-api.oci-dev.duckdns.org`, `FRONTEND_ORIGINS=https://podobank.oci-dev.duckdns.org`, and `KAKAO_REDIRECT_URI=https://podobank.oci-dev.duckdns.org/auth/kakao/callback` exactly.
- The preview can use the seeded local demo login without Kakao. Kakao OAuth remains unavailable while its provider credentials are placeholders; enabling it also requires registering the HTTPS callback with Kakao.
- Keep `NPM_DOCKER_NETWORK` equal to the existing NPM Docker network name.

The DB-only file is mounted into MariaDB as its `env_file`; application signing and login secrets stay out of that container. The preview frontend API base is set by the overlay to `https://podobank-api.oci-dev.duckdns.org`.

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

## Set demo login credentials and load sample data

The preview overlay does not change database contents on startup. After the API is healthy, initialize any missing default schema, explicitly rotate the configured bank employee and fixed demo customer to the unique passwords in `.env.npm-preview`, then add the 10,000-customer synthetic sample dataset:

```sh
COMPOSE_ENV_FILE=.env.npm-preview.db \
docker compose --project-name podobank \
  --env-file .env.npm-preview \
  -f compose.yaml -f compose.npm-preview.yaml \
  exec -T api podobank-api init-db

COMPOSE_ENV_FILE=.env.npm-preview.db \
docker compose --project-name podobank \
  --env-file .env.npm-preview \
  -f compose.yaml -f compose.npm-preview.yaml \
  exec -T api podobank-api set-demo-credentials

COMPOSE_ENV_FILE=.env.npm-preview.db \
docker compose --project-name podobank \
  --env-file .env.npm-preview \
  -f compose.yaml -f compose.npm-preview.yaml \
  exec -T api podobank-api seed-demo-data
```

`init-db` creates missing schema and default records but does not reset existing data; it preserves existing account balances and non-null password hashes. Run it only when the approved deployment plan includes the bootstrap step. Credential rotation and sample seeding are restricted to `APP_ENV=development` and the local `podobank_dev` database. Credential rotation changes only the configured bank employee and fixed demo customer's password hashes. The sample command is explicit and additive; it reports the customer, account, ledger, loan, and repayment counts and is safe to repeat after a completed seed. Do not use the local default passwords in the preview env file.

## Configure NPM

In the NPM admin UI, leave both hosts publicly accessible without an Access List:

1. Under **Hosts → Proxy Hosts**, add the UI host `podobank.oci-dev.duckdns.org` with:
   - Scheme: `http`
   - Forward Hostname / IP: `podobank-frontend`
   - Forward Port: `80`
   - Access List: `Publicly Accessible`
   - Block Common Exploits: enabled
2. In the UI host's **SSL** tab, request a certificate for `podobank.oci-dev.duckdns.org`, enable **Force SSL**, and save only after the certificate is valid.
3. Add a second Proxy Host for the API hostname `podobank-api.oci-dev.duckdns.org` with:
   - Scheme: `http`
   - Forward Hostname / IP: `podobank-api`
   - Forward Port: `8000`
   - Access List: `Publicly Accessible`
   - Block Common Exploits: enabled
4. In the API host's **SSL** tab, request a certificate for `podobank-api.oci-dev.duckdns.org`, enable **Force SSL**, and save only after the certificate is valid. Do not add a Custom Location or path rewrite to either host.

No NPM custom Advanced config is needed. Do not expose the API or database with new host ports. The API's public exposure is intentional for this development preview; keep real customer data and production credentials out of it.

## Verify access

Both hosts should respond without an NPM authentication prompt:

```sh
curl -fsS https://podobank.oci-dev.duckdns.org/
curl -fsS https://podobank-api.oci-dev.duckdns.org/health
```

The UI should return its Vue app and API `/health` should return HTTP `200`. Check that the API accepts a preflight from the exact UI origin:

```sh
curl --include --request OPTIONS \
  --header 'Origin: https://podobank.oci-dev.duckdns.org' \
  --header 'Access-Control-Request-Method: POST' \
  --header 'Access-Control-Request-Headers: content-type' \
  https://podobank-api.oci-dev.duckdns.org/auth/login
```

The response must allow only `https://podobank.oci-dev.duckdns.org` and include credential support. Then open `https://podobank.oci-dev.duckdns.org/accounts` in a browser without an NPM prompt and sign in with a seeded demo customer or bank employee account. The frontend calls the separate API host with credentials enabled; its Secure, HttpOnly, SameSite=Lax session cookie is scoped to the API host.

## Roll back

First disable or remove both NPM Proxy Hosts. From the primary checkout with its existing `.env`, restore the base local configuration:

```sh
env -u COMPOSE_ENV_FILE docker compose --project-name podobank \
  --env-file .env -f compose.yaml up -d --build api frontend
```

This returns the frontend to its direct local API origin. Do not run `docker compose down -v`, delete named volumes, or reset sample data as part of rollback.
