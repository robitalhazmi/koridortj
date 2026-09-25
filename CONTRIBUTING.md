# Contributing to KoridorTJ

Thank you for your interest in contributing to KoridorTJ! We welcome contributions to help improve this transit data engineering platform.

---

## 1. Code of Conduct

All contributors are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before participating.

---

## 2. Development Workflow

1. **Fork or branch:** Create a topic branch from `main` (e.g. `feature/gtfs-parser` or `fix/dag-idempotency`).
2. **Environment Setup:**
   ```bash
   cp .env.example .env
   # Edit .env with your local credentials
   docker compose up -d postgres kafka
   ```
3. **Python & dbt Setup:**
   - Use Python 3.11+ with a virtual environment:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt  # When available in later phases
     ```
4. **Code Quality Standards:**
   - Format and lint Python code with `ruff` and `black`.
   - Lint SQL / dbt models using `sqlfluff`.
   - Ensure all unit tests pass with `pytest`.
   - Ensure dbt models build and pass tests with `dbt test`.
5. **Commit Messages:**
   - Use clear, descriptive commit messages (e.g., `feat(ingestion): add GTFS schedule validator`).
6. **Submitting a Pull Request:**
   - Open a PR against the `main` branch.
   - Ensure CI checks pass on the PR.

---

## 3. Data Integrity & Disclaimers

- Any feature, dashboard, or document displaying transaction or tap volumes must clearly label the data as **simulated / synthetic**.
- Never commit real secret keys, passwords, or production `.env` files.

---

## 4. Reporting Issues

- Use GitHub Issues to report bugs or request enhancements.
- When filing a bug, include steps to reproduce, expected vs actual behavior, and relevant logs or stack traces.
