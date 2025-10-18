# Repository Guidelines

## Project Structure & Module Organization
Core bot logic lives in `src/bot.py`, built around python-telegram-bot and Beancount helpers. Environment samples sit in `src/.env.example` (duplicate to `.env` or `.env.docker` before running). Tests live in `src/test_bot.py`; add new suites alongside the module under test. Deployment scaffolding is in the root: `Dockerfile`, `docker-compose.yaml`, and the top-level `Makefile`. Keep personal Beancount files under `beancount_root/` with its Makefile targets exposed to the bot.

## Build, Test, and Development Commands
Use `uv run src/bot.py` for a fast local launch with the pinned Python toolchain; `make run` wraps the same entry point with standard Python. Install dependencies via `uv sync` or `pip install -r requirements.txt` if you prefer pip. Run unit tests with `make test` (calls `pytest -q src/test_bot.py`). `make docker` delegates to `docker-compose up -d` for container runs; adjust `docker-compose.yaml` volume paths beforehand.

## Coding Style & Naming Conventions
Target Python 3.12, four-space indents, and descriptive `snake_case` for functions and variables. Favor module-level constants for environment keys, mirroring `bot.py`. Static typing is encouraged where possible. Run `ruff check src` locally; commits such as `92e4305` show the expectation that lint passes.

## Testing Guidelines
Prefer pytest-style tests in `src/test_*`. Name tests after the behavior asserted (e.g., `test_parse_multi_leg`). Mock Telegram or subprocess interactions to keep tests deterministic. When adding features, extend coverage for both successful and failure paths; current automation depends on contributors running `make test`.

## Commit & Pull Request Guidelines
Recent history uses concise, imperative subject lines (`fix docker-compose run method`). Group related changes into single commits and describe the motivation in the body when additional context helps reviewers. For PRs, include: summary of changes, manual test notes (`make test`, `uv run`), configuration updates, and screenshots or log excerpts for user-facing changes. Link GitHub issues where applicable.

## Configuration & Deployment Notes
Keep secrets out of Git. Copy `src/.env.example` to the appropriate `.env` and fill `MAKEFILE`, `BEANCOUNT_ROOT`, and bot credentials. Ensure the Beancount Makefile exposes `bal` and `pay` targets; the bot shells out to them for `/bal` and `/pay`. When deploying via systemd (`beancountbot.service`) or Docker, verify environment files and volume paths reference the same ledger root.
