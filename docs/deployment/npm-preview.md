# PodoBank preview through Cloudflare Workers

The preview is available at `https://podobank.i234.workers.dev` (UI) and `https://podobank-api.i234.workers.dev` (API). The `podobank` and `podobank-api` Workers and their VPC Service bindings are already deployed. The existing Tunnel connects them to OCI over HTTP:

| Public URL | Existing VPC Service upstream | Service |
| --- | --- | --- |
| `https://podobank.i234.workers.dev` | `http://127.0.0.1:8081` | Vue UI served by Nginx |
| `https://podobank-api.i234.workers.dev` | `http://127.0.0.1:8000` | FastAPI |

Keep the API's current root paths such as `/health`, `/auth/login`, and `/accounts/me`. Do not add an `/api` prefix or URI rewriting in Worker code or Nginx. The frontend image receives the API Worker URL as its build-time `VITE_API_ORIGIN`.

This is a synthetic-data development preview, not a production deployment. The API hostname is publicly reachable, including unauthenticated routes such as `/health` and `/auth/login`; CORS only constrains browser JavaScript and does not authenticate non-browser clients. User financial routes still require the application's JWT session and DB role. Do not use real customer data or production credentials.

## Existing services and network boundaries

- Do not edit or restart Cloudflare Workers, the Cloudflare Tunnel, VPC Services, Nginx Proxy Manager (NPM), MariaDB, MongoDB, monitoring services, or any shared volume for this preview update.
- The Compose overlay keeps its existing NPM network attachments and aliases for compatibility. Worker routing uses the existing host loopback ports and does not require NPM changes.
- The API and database host ports remain bound to `127.0.0.1`; do not publish either port on a public interface.
- Keep `APP_ENV=development`, `AUTH_COOKIE_SECURE=true`, the current database credentials, and all existing secret values. The Kakao REST API key and client secret remain placeholders until Kakao OAuth is configured.
- In `.env.npm-preview`, use these exact routing values:

```dotenv
API_ORIGIN=https://podobank-api.i234.workers.dev
FRONTEND_ORIGINS=https://podobank.i234.workers.dev
KAKAO_REDIRECT_URI=https://podobank.i234.workers.dev/auth/kakao/callback
```

The frontend build uses `https://podobank-api.i234.workers.dev`. Vue sends credentialed requests to the API Worker. FastAPI allows only the UI Worker origin with credential support. The API session cookie remains Secure, HttpOnly, and SameSite=Lax.

## Environment files

Use the existing `.env.npm-preview` and `.env.npm-preview.db` files from the active Compose project. Do not recreate or replace either file if it already exists. Keep both files ignored and mode `0600`. The database-only file supplies MariaDB startup variables; it is not modified by this routing change.

The checked-in `.env.npm-preview.example` contains replaceable values for local preparation. It keeps `APP_ENV=development` and Kakao placeholders. Never print or commit `.env.npm-preview`, `.env.npm-preview.db`, or their secret values.

When the source checkout and active runtime env files are in different directories, set these shell variables to their existing locations. Do not copy secrets into the source checkout:

```sh
PODOBANK_SOURCE_DIR=/path/to/Podobank
PREVIEW_ENV_DIR=/path/to/active/preview
```

## Validate and rebuild only the application containers

First validate the merged Compose model. `config --quiet` does not print resolved secret values:

```sh
COMPOSE_ENV_FILE="$PREVIEW_ENV_DIR/.env.npm-preview.db" \
docker compose --project-name podobank \
  --env-file "$PREVIEW_ENV_DIR/.env.npm-preview" \
  -f "$PODOBANK_SOURCE_DIR/compose.yaml" \
  -f "$PODOBANK_SOURCE_DIR/compose.npm-preview.yaml" \
  config --quiet
```

Rebuild only API and frontend. `--no-deps` prevents Compose from starting, stopping, or recreating MariaDB or another dependency:

```sh
COMPOSE_ENV_FILE="$PREVIEW_ENV_DIR/.env.npm-preview.db" \
docker compose --project-name podobank \
  --env-file "$PREVIEW_ENV_DIR/.env.npm-preview" \
  -f "$PODOBANK_SOURCE_DIR/compose.yaml" \
  -f "$PODOBANK_SOURCE_DIR/compose.npm-preview.yaml" \
  up -d --build --no-deps api frontend
```

Do not run `down`, `down -v`, database initialization/reset, credential rotation, or sample-data commands as part of updating preview routing. Capture the IDs and running states of `db`, `mongo`, monitoring, NPM, and other shared containers before and after; they must remain unchanged.

## Verify public access

The UI root and API health route should respond successfully:

```sh
curl -fsS https://podobank.i234.workers.dev/
curl -fsS https://podobank-api.i234.workers.dev/health
```

Check credentialed CORS from the exact UI origin:

```sh
curl --include --request OPTIONS \
  --header 'Origin: https://podobank.i234.workers.dev' \
  --header 'Access-Control-Request-Method: POST' \
  --header 'Access-Control-Request-Headers: content-type' \
  https://podobank-api.i234.workers.dev/auth/login
```

The response must allow `https://podobank.i234.workers.dev`, include credential support, and not allow unrelated origins. Open `https://podobank.i234.workers.dev/accounts` and sign in with an existing demo customer or bank employee account. Browser API calls must use existing paths such as `/auth/login` and `/accounts/me`, with credentials included.

The application login flow is the authentication boundary for customer and employee screens. Kakao login remains unavailable while provider credentials are placeholders; local demo login continues to work.

## Roll back

If the Worker preview needs to be rolled back, restore the previous DuckDNS values in `compose.npm-preview.yaml`, `.env.npm-preview.example`, and only the three corresponding URL keys in the existing `.env.npm-preview`. Rebuild only API and frontend with the same `--no-deps` command. Do not change NPM configuration, stop shared services, alter database credentials, or remove volumes.
