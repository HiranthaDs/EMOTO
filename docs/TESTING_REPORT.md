# EMOTO testing report

Date: 2026-10-21 (Asia/Colombo)

## Executed successfully

- `npm run build`: TypeScript validation and Vite production build completed.
- `python -m alembic upgrade head`: initial migration applied to SQLite.
- `pytest -q`: 5 tests passed.
- `npm run lint`: ESLint passed with no warnings or errors.
- `npm run test:e2e`: 10 Playwright checks passed using installed Chrome at 1440, 1024, 768, 390, and 360 pixel widths.
- The Render Blueprint validated successfully against `https://render.com/schema/render.yaml.json`.
- Covered: setup/login/logout, invalid login, CSRF rejection, supplier and customer creation, vehicle linking, part creation, receiving, RFQ and supplier offer, supplier selection, quotation approval, order conversion and reservation, dispatch, invoice generation, partial/full payments, warranty generation, PDF response, negative-stock rejection, and SQLite backup creation.
- Browser coverage: first-run/login entry, desktop and mobile navigation, responsive drawer behavior, parts navigation, and no document-level horizontal overflow at every required viewport.

## Visual review

Baselines are stored in `docs/screenshots/` for 1440 desktop, 1024 tablet, 768 tablet, 390 mobile, and 360 mobile. Review corrected the mobile drawer stacking behavior and changed the 768 layout to the compact navigation shell.

## Environment limitation

Docker was not installed on the authoring machine, so an actual `docker build` and container persistence recreation test were not executed. The image uses a conventional two-stage Node/Python build, runs Alembic before Uvicorn, binds `0.0.0.0:$PORT`, uses one worker, and stores runtime data beneath `/var/data`.

## Remaining pre-production acceptance

- Build and run the Docker image on a Docker-enabled host.
- Exercise a staging Render deployment using real persistent-disk lifecycle behavior.
- Complete browser-based acceptance with representative business users and real printer/PDF settings.
- Configure and test a recurring encrypted offsite backup process.

