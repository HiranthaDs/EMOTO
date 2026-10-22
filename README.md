# EMOTO — German Spare Parts ERP

EMOTO is a same-origin React and FastAPI ERP for spare-parts sourcing, CRM, inventory, sales, invoicing, payments, warranties, reporting, audit trails, private attachments, and SQLite backups. HICH WEB Development is identified as the development company.

## Architecture

The application uses one FastAPI service. FastAPI serves `/api/v1/*`, `/health`, and the compiled React SPA from the same hostname. Runtime data is restricted to `DATA_DIR`:

- `emoto.db` — SQLite database in WAL mode
- `uploads/` — authenticated private files
- `backups/` — consistent SQLite snapshots and manifests

Money is stored as integer cents. Foreign keys are enabled on every connection. Stock mutations, reservations, payment totals, conversions, and document numbers are enforced on the server.

## Run locally on Windows

Requirements: Python 3.12+, Node.js 20+, npm, and PowerShell.

```powershell
.\setup_local.ps1
```

Edit `.env`. Generate secrets, for example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use different random values for `SESSION_SECRET` and `BOOTSTRAP_TOKEN`, then run:

```powershell
.\run_local.ps1
```

Open `http://localhost:10000`. The local runner applies database migrations, compiles the React interface, and starts the Python/FastAPI server; Docker is not required. On a new database, the app displays first-run setup. Enter the same one-time `BOOTSTRAP_TOKEN` and create a password of at least 12 characters. Setup is permanently disabled after the first user exists.

## Tests and production build

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
npm run lint
npm run test:e2e
```

The backend API documentation is available at `http://localhost:10000/api/docs` in development only.

## Deploy to Vercel

This repository is configured as one FastAPI Function that also serves the compiled React application. Docker and a persistent volume are not used. Vercel builds `frontend/dist`, installs the root Python requirements, runs Alembic automatically on a cold start, and writes SQLite data below `/tmp/emoto`.

1. Push the repository to a personal GitHub, GitLab, or Bitbucket account.
2. In Vercel, import the repository into a **Hobby** project. Keep the project root at the repository root; `vercel.json` selects FastAPI and contains the build settings.
3. In **Project > Settings > Environment Variables**, add the following to Production and Preview:
   - `SESSION_SECRET`: a random value of at least 32 characters.
   - `BOOTSTRAP_TOKEN`: a different random one-time setup value.
   - `PUBLIC_BASE_URL`: optional for previews; for production set it to the final `https://...vercel.app` or custom-domain URL so PDFs and QR links use that hostname.
4. Deploy, open `/health`, then open the root URL and create the administrator with `BOOTSTRAP_TOKEN`.

Generate secrets locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

You can also deploy from the repository root with Vercel CLI 48.1.8 or newer:

```powershell
npm install --global vercel
vercel
vercel --prod
```

### Free-tier limitations

This configuration is suitable only for a disposable personal demo or evaluation:

- Vercel Function storage is read-only except for 500 MB of temporary `/tmp` space. The database, sessions, uploads, and on-server backups can disappear after a cold start, redeployment, scale-out, or instance replacement. Separate instances do not share their SQLite data.
- Download a backup during the same live instance if you need a temporary export. It is not disaster recovery.
- Function request and response bodies are limited to 4.5 MB. The app therefore caps Vercel attachments at 4 MB (local development accepts up to 10 MB).
- Vercel's Hobby plan is for personal, non-commercial use. A live business ERP requires an eligible paid hosting plan and durable single-writer storage; this free configuration must not be treated as a production system of record.

The Function is pinned to Vercel's Singapore region (`sin1`) for lower latency from Sri Lanka. `APP_ENV=production` and `DATA_DIR=/tmp/emoto` are defined in `vercel.json`; do not add secrets to that file.

## Backup and restore

Super Admins create and download consistent backups from **Settings**. Backups use SQLite's online backup API, not a live-file copy. Download them regularly to encrypted offsite storage; disk snapshots and on-disk backups alone are not disaster recovery.

Restore is deliberately an offline operator procedure:

1. Put the service in maintenance mode and stop all writers.
2. Download the current backup and uploads first.
3. Validate the selected backup locally using `PRAGMA integrity_check`.
4. Replace the configured `DATA_DIR/emoto.db` with the validated backup while the service is stopped; never copy over an open database.
5. Start the service, confirm `/health`, sign in, and verify recent invoices and stock balances.

Keep database and uploaded-document backups together when records reference those files. Restore applies only to a deployment with durable storage; Vercel's temporary `/tmp` database is not a restore target.

## User workflow

- **Super Admin:** user administration, all business data, protected costs/margins, audit logs, and backups.
- **Sales:** customers, vehicles, quotations, orders, invoice visibility, and warranty lookup.
- **Purchasing:** suppliers, RFQs, supplier offers/comparisons, and protected acquisition costs.
- **Inventory:** catalog and transactional receiving/reserving/releasing/issuing/returns.
- **Accounts:** invoices, partial/full payments, receivables, and financial reporting.

Create suppliers and catalog parts, receive stock, then build customer and vehicle records. Purchasing can source via RFQ and approve an offer. Sales quotations do not affect stock; conversion to an order reserves available stock. Dispatch issues physical stock. Invoice generation is idempotent, payments cannot exceed the balance, and item warranties remain linked to the original invoice item.

## Security and operating notes

- Authentication uses Argon2 password hashing and opaque database-backed sessions in HttpOnly cookies.
- Mutations require a session-bound CSRF token; production cookies are Secure and SameSite=Lax.
- Login attempts are limited per email/IP in the single application process.
- Every API route performs server-side permission checks. Restricted purchase costs and financial reports are filtered server-side.
- Uploads are size/type/signature checked, randomized on disk, and only downloaded through authenticated endpoints.
- Never expose `DATA_DIR`, upload paths, the database, WAL files, backups, `.env`, or deployment secrets through static hosting.
- All displayed timestamps are formatted for Asia/Colombo. The database stores UTC timestamps.

## Verified status

See [docs/TESTING_REPORT.md](docs/TESTING_REPORT.md) for executed checks and [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for the exact delivered scope and remaining master-brief work.

