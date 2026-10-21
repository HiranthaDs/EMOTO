# Repository guidance

- Preserve the one-service FastAPI + compiled React + SQLite architecture.
- Never add an external database or public static upload route.
- Store monetary values as integer cents and mutate inventory only through auditable server transactions.
- Add Alembic migrations for schema changes; never recreate production data.
- Run `npm run build` and `pytest -q` before delivery.
