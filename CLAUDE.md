# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install -e .                # CLI only
pip install -e ".[dev]"         # + pytest, ruff, mypy
pip install -e ".[web]"         # + FastAPI, PostgreSQL, Stripe, etc.
playwright install chromium     # browser automation (CLI)

# CLI
xfeed                           # full pipeline: scrape → summarize → open
xfeed login                     # manual X.com login
xfeed config show               # show config

# Web
uvicorn web.app:app --reload    # dev server on :8000
alembic upgrade head            # apply migrations
arq web.worker.WorkerSettings   # start background worker
docker-compose up               # full stack (postgres, redis, web, worker)

# Quality
ruff check .                    # lint (rules: E, F, I, N, W, UP; ignores E501)
ruff check --fix .              # auto-fix
mypy .                          # type checking (strict: disallow_untyped_defs)
pytest                          # tests (testpaths: tests/)
pytest --cov                    # with coverage
```

## Architecture

Dual-mode application: a **CLI tool** (`src/`) and a **Web SaaS** (`web/`). They share `src/` utilities but are otherwise independent.

### CLI (`src/`) — v0.4.0, stable, READ-ONLY
Local Typer app. Playwright scrapes X.com → SQLite → LM Studio/Claude summarizes → HTML/Markdown output + optional Telegram delivery. Config via `config.yaml` + `.env`.

### Web (`web/`) — multi-tenant SaaS
FastAPI with Jinja2+HTMX+Tailwind (dark theme). PostgreSQL (async SQLAlchemy) + Alembic migrations. Auth via X OAuth 2.0 PKCE → JWT in HTTP-only cookie. Stripe for payments. ARQ+Redis for background jobs (hourly cron per user's timezone). Resend for email delivery.

**Request flow:** Router → Service → DB/External API. Routers never access the database directly.

**Pipeline:** FeedProvider (Twitter API or Playwright) → PostgreSQL (batch dedup) → SummaryService (OpenAI/Anthropic/LM Studio) → Briefing → EmailDelivery

**Key services:** `pipeline_service.py` (orchestrator), `summary_service.py` (LLM abstraction, raises `SummaryGenerationError`), `auth_service.py` (JWT/cookies), `subscription_service.py` (Stripe)

## Critical Rules

- **Never modify files in `src/`** — the CLI is frozen; the web layer imports from it but must not change it
- **Logout must be POST**, not GET (CSRF safety)
- **Always sanitize** markdown→HTML with `nh3.clean()` before `|safe` in templates
- **OAuth state** is in-memory dict with 10-min TTL; needs Redis for multi-process
- **Sync API calls** (Stripe, Resend) must be wrapped in `asyncio.to_thread()`
- **Shared httpx client** via `web/http_client.py` — initialized/closed in FastAPI lifespan
- **Fernet encryption** for stored OAuth tokens (`web/db/encryption.py`); key validated at startup
- **Settings validation** uses `Literal` types for enums, `zoneinfo` for timezones
- **Prompt presets:** `default`, `anti_politics`, `tech_ai`, `custom` (in `web/prompts.py`)
- **Config** via Pydantic `BaseSettings` from `.env` (`web/config.py`); startup refuses insecure defaults in production

## Code Style

- Python 3.11+, line length 100, type hints required
- Ruff for linting, mypy strict mode
- Models: PascalCase. Services: `*_service.py`. Constants: UPPER_SNAKE_CASE in `web/constants.py`
- HTMX responses use `HX-Trigger` header for toast notifications
