# Local development

## Public frontend

Use Node.js 24 and pnpm 10.32.1. From `frontend/web` run
`pnpm install --frozen-lockfile`, then `pnpm dev --host 127.0.0.1`.
Public routes work without paid API credentials. The app/auth routes require a
configured backend; they are not a mocked interactive demo.

The API client defaults to `http://127.0.0.1:8080/api/v1` on localhost. You may
copy `frontend/web/.env.example` to `.env.local` to override this. Keep frontend
and API hostnames consistent (`localhost` or `127.0.0.1`) for cookies and CORS.

Run `pnpm build` to produce and verify prerendered HTML. Example canonical hosts
and nginx server names use `vizuai.example`; configure your own hosts before any
deployment. Run `python site/legal/generate_site.py` from the repo root if editing
the anonymized legal examples.

## Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest --disable-socket --allow-unix-socket
```

Run tests without real credentials or a production `.env`. The tests use fakes
and temporary databases where implemented. See validation.md for known failures.

## API

1. Copy `.env.example` to `.env`
2. Start a local PostgreSQL instance (optional convenience: `docker compose up -d postgres`)
3. Supply your own GCP project/bucket settings and credentials outside the repo
4. Apply the Alembic migrations to an empty development database with `alembic upgrade head`
5. Configure Resend and a verified sender to exercise email login
6. Run `python main_web.py` and check `http://127.0.0.1:8080/healthz`

The API also requires storage configuration for uploads and Cloud Tasks for
asynchronous jobs. Its health endpoint is a process check, not a full dependency
readiness check. Google IAM permissions, bucket CORS and URL-signing permissions
must be configured in your own cloud project.

## Worker and optional integrations

Set `APP_MODE=worker` and supply `OPENAI_API_KEY`, `SEARCHAPI_KEY`, storage,
database, and GCP project settings. Configure a Cloud Tasks queue and worker
target, then start `python main_worker.py`. Gemini/Vertex and Decor8 provide
fallbacks when configured. Real model/search requests may incur charges.

T-Bank checkout requires your own merchant account and webhook setup; no merchant
credentials are included. Telegram is optional and needs a separate bot token.
Redis is optional; without it, runtime state and concurrency limiting are local
to each worker process. Rate limiting is disabled in the local example only.

## Container templates

`Dockerfile.web_api` builds the API and `frontend/web/Dockerfile` builds the
frontend. The root Dockerfile retains the legacy worker runtime. Cloud Build
templates use the invoking project's `PROJECT_ID` and configurable substitutions.
No workflow automatically deploys or has access to the original infrastructure.

This guide describes dependencies and entrypoints. It does not claim a fresh
production deployment has been provisioned or validated as part of publication.
