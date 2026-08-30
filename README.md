# Sri Lanka News Ingestion Service

Publisher-agnostic Python foundation for discovering, extracting, and
normalizing Sri Lankan news articles before they are submitted to the platform
backend.

Phase 6 implements Daily Mirror as the first real publisher and submits
normalized article data to the Spring Boot internal ingestion API. Python
still owns no persistence.

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

The default run processes at most three feed entries sequentially. It logs a
concise created/duplicate/failed summary and has no scheduler.

## Architecture

- `src/ingestion/config` validates `INGESTION_*` environment settings.
- `src/ingestion/sources` defines the contract for future publisher adapters.
  `DailyMirrorAdapter` contains all Daily Mirror feed, JSON-LD, and CSS rules.
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

Daily Mirror discovery uses its official Breaking News RSS feed. Article pages
prefer `NewsArticle` JSON-LD for headline, body, author, publication time, and
image, with Daily Mirror-specific HTML fallbacks. Cleaned extracted article
content is submitted for internal backend persistence but is never part of the
public Article API. Image metadata remains local to Python.

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

## Phase 6 boundaries

Included:

- Daily Mirror RSS discovery and article extraction
- Validated normalization and conservative canonicalization
- Shared-secret backend submission client
- One-time bounded CLI run
- Offline unit tests

Not included:

- Additional publishers
- Browser automation or Playwright
- MongoDB or other persistence
- Scheduling, retries, queues, Redis, authentication, AI, summaries,
  translations, embeddings, topic/entity extraction, or story clustering

Phase 7 — Second and Third Sources has not been started.
