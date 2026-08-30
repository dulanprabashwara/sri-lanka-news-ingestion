# Sri Lanka News Ingestion Service

Publisher-agnostic Python foundation for discovering, extracting, and
normalizing Sri Lankan news articles before they are submitted to the platform
backend.

Phase 5 defines reusable boundaries and utilities only. It does not ingest a
real publisher or persist data.

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

Runtime configuration is environment-driven. Defaults are suitable for local
development; copy `.env.example` to `.env` only when overrides are needed.
Do not commit `.env`.

## Architecture

- `src/ingestion/config` validates `INGESTION_*` environment settings.
- `src/ingestion/sources` defines the contract for future publisher adapters.
- `src/ingestion/models` contains immutable discovery, extraction, and
  normalized article models.
- `src/ingestion/http` owns bounded HTTP requests and domain errors.
- `src/ingestion/extraction` provides publisher-neutral RSS and HTML helpers.
- `src/ingestion/normalization` contains conservative canonical URL handling.
- `src/ingestion/logging.py` configures structured JSON application logging.
- `tests/fixtures` contains local RSS and HTML samples; tests use no internet.

Future adapters will own publisher-specific feed locations, selectors, and
normalization decisions. Shared extraction helpers intentionally do not claim
to be a universal article parser.

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

## Phase 5 boundaries

Included:

- Source adapter abstraction
- Validated pre-AI ingestion models
- HTTP, RSS, HTML, URL, configuration, and logging foundations
- Offline unit tests

Not included:

- Real publisher adapters or live ingestion
- Browser automation or Playwright
- MongoDB or other persistence
- Backend submission endpoints or clients
- Scheduling, retries, queues, Redis, authentication, AI, summaries,
  translations, embeddings, topic/entity extraction, or story clustering

Phase 6 will implement the first real source adapter and end-to-end submission
workflow.
