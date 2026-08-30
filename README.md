# Sri Lanka News Ingestion Service

Publisher-agnostic Python foundation for discovering, extracting, and
normalizing Sri Lankan news articles before they are submitted to the platform
backend.

Phase 7 live sources are Daily Mirror, NewsFirst English, and Hiru News Sinhala.
Every publisher submits normalized article data through the same Spring Boot
internal ingestion API; Python still owns no persistence.

## Requirements

- Python 3.12 or newer

## Setup

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the package and development tools:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env`, set `INGESTION_API_KEY` to the same strong
random value configured in the backend, and review the backend URL and run
limit. Do not commit `.env`.

Start the backend against Atlas before running one controlled ingestion:

```powershell
ingest-daily-mirror
```

Run each supported source independently with `ingest-daily-mirror`,
`ingest-newsfirst`, or `ingest-hiru-news-sinhala`. The default run
processes at most three entries sequentially. It logs a
concise created/duplicate/failed summary and has no scheduler.

## Architecture

- `src/ingestion/config` validates `INGESTION_*` environment settings.
- `src/ingestion/sources` defines the shared adapter contract. Each supported
  publisher keeps its own discovery URL, selectors, date rules, and quirks.
- `src/ingestion/models` contains immutable discovery, extraction, and
  normalized article models.
- `src/ingestion/http` owns bounded HTTP requests and domain errors.
- `src/ingestion/extraction` provides publisher-neutral RSS and HTML helpers.
- `src/ingestion/normalization` contains conservative canonical URL handling.
- `src/ingestion/logging.py` configures structured JSON application logging.
- `src/ingestion/backend` submits normalized metadata and cleaned extracted
  content to the protected Spring Boot
  internal API and handles created, duplicate, validation, authentication, and
  service-failure responses.
- `src/ingestion/runner.py` performs one bounded sequential ingestion run.
- `tests/fixtures` contains local RSS and HTML samples; tests use no internet.

Daily Mirror uses official RSS discovery. NewsFirst and Hiru News use their
public latest-news HTML listings. Ada Derana Sinhala support remains in the
codebase but is not an active Phase 7 source because both its RSS and homepage
return publisher/CDN HTTP 403 responses from the development environment; its
backend source registration is disabled.
Article adapters prefer structured metadata where available and retain
publisher-specific HTML fallbacks. Publisher-local timestamps are normalized
to UTC. Cleaned extracted content remains internal-only in the backend.

## Checks

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
```

To apply formatting locally:

```powershell
python -m ruff format .
```

## Phase 7 boundaries

Included:

- Daily Mirror, NewsFirst English, and Hiru News Sinhala live adapters
- Retained but disabled Ada Derana Sinhala adapter
- RSS and conservative latest-listing discovery
- Validated normalization and conservative canonicalization
- Shared-secret backend submission client
- One-time bounded CLI run
- Offline unit tests

Not included:

- Additional active publishers beyond the three verified sources
- Browser automation or Playwright
- MongoDB or other persistence
- Scheduling, retries, queues, Redis, authentication, AI, summaries,
  translations, embeddings, topic/entity extraction, or story clustering

Scheduling remains a future phase.
