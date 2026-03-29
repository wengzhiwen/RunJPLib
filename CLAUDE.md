# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 沟通语言

默认使用**简体中文**进行所有沟通和回复。

## Project Overview

RunJPLib is a Flask web application for Japanese university entrance exam information. It features AI-powered content generation, OCR/translation/analysis pipelines, vector search-based chat, and an admin management panel. Backend: Flask + MongoDB + ChromaDB. AI: OpenAI GPT models via openai-agents framework.

## Commands

```bash
# Development server
./start.sh dev                    # runs on port from FLASK_APP_PORT (default 5000)

# Production server
./start.sh prod                   # gunicorn -c gunicorn.conf.py app:app

# Install dependencies
pip install -r requirements.txt

# Code formatting (required before commits)
yapf -i <file.py>                 # format with yapf (160-char limit, PEP8-based)
isort <file.py>                   # sort imports (Google profile)

# Database indexes
python -c "from utils.core.database import ensure_indexes; ensure_indexes()"

# MongoDB dev server
./start-mongodb-dev.sh / ./stop-mongodb-dev.sh
```

No test framework is configured in this project.

## Architecture

### Application Entry Point
`app.py` uses an application factory pattern: `create_app()` registers blueprints, JWT, error handlers, and database indexes. Environment is detected via `LOG_LEVEL` (INFO=production, DEBUG=development).

### Routes (Blueprint-based)
Blueprints are defined centrally in `routes/blueprints.py`:
- `admin_bp` (`/admin`) — Admin panel, templates in `templates/admin/`
- `blog_bp` (`/blog`) — Public blog pages
- `chat_bp` (`/api/chat`) — AI chat API

Admin routes are split into submodules under `routes/admin/` (auth, dashboard, universities, blogs, pdf_processor, chat_logs, analytics). Each imports `admin_bp` from `blueprints.py` and uses `@admin_bp.route()` decorators. The `@admin_required` decorator handles JWT auth.

Public page routes remain in `routes/index.py` (homepage, university details, sitemap).

### Utils Module
Organized by domain under `utils/`:
- `core/` — config, database (MongoDB singleton + connection pool), logging, proof archiving
- `ai/` — analysis, blog generation, OCR, batch OCR, translation
- `chat/` — manager, security (rate limiting), session logging, hybrid search engine
- `document/` — PDF processor (Buffalo Workflow 5-step pipeline), wiki processor
- `university/` — repository, LLM-based tagger/classifier, vector search (LlamaIndex + ChromaDB)
- `system/` — task manager (multi-type queue with concurrent scheduling + PID monitoring), thread pools (3 isolated pools), analytics
- `tools/` — cache utilities, IP geolocation

**Import convention**: Use direct submodule imports, not top-level `utils` re-exports:
```python
from utils.core.database import get_db
from utils.ai.analysis_tool import DocumentAnalyzer
from utils.system.task_manager import task_manager
```

### Key Patterns
- **Database access**: `get_db()` returns the MongoDB database instance (singleton client with connection pool). Always check `if db is None:`.
- **Caching**: `cachetools.TTLCache` with `@cached()` decorator. Caches are defined near the functions they wrap (e.g., `routes/blog/cache.py`, `routes/index.py`).
- **Async tasks**: Thread pools via `ConcurrentTaskExecutor` — three pools (access log, blog HTML build, admin ops). Submit with `submit_*()` methods; falls back to sync when pool is full.
- **Background tasks**: `TaskManager` manages PDF processing, tag generation, analysis regeneration as queued tasks with configurable concurrency (`PDF_MAX_CONCURRENT_TASKS`).
- **Admin CSRF**: All admin POST routes require CSRF token via `X-CSRF-TOKEN` header (for API calls) or hidden form field. See `docs/developer_guides/admin_csrf_handling.md`.

### Configuration
All config is via environment variables loaded from `.env`. Key vars:
- `MONGODB_URI`, `JWT_SECRET_KEY`, `ACCESS_CODE` — required
- `OPENAI_API_KEY` — required for AI features
- `LOG_LEVEL` — INFO (prod) or DEBUG (dev)
- Model names are individually configurable: `OCR_MODEL_NAME`, `OPENAI_TRANSLATE_MODEL`, `OPENAI_ANALYSIS_MODEL`, etc.

## Code Style

- Line limit: 160 characters (yapf + pylint)
- Import sorting: isort with `profile = "google"`
- Formatter: yapf with `based_on_style = "pep8"`
- Always run `yapf -i` and `isort` on modified Python files before committing
