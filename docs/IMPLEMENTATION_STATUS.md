# Implementation status

Updated: 2026-10-21 (Asia/Colombo)

## Delivered and verified

- One-service FastAPI + compiled React architecture with protected API routing, health check, SPA deep-link fallback, Dockerfile, and schema-valid `render.yaml`.
- SQLite persistence configuration, WAL/foreign keys/busy timeout, Alembic startup migration, indexes, integer minor-unit money, uploads/backups directories, and consistent SQLite backup API.
- First-run Super Admin bootstrap, Argon2 passwords, database sessions, HttpOnly/Secure production cookie settings, session expiry, CSRF checks, login throttling, role permissions, server-side cost filtering, security headers, and audit events.
- Responsive Supabase-inspired application shell, dark design system, collapsible navigation, mobile drawer, global Ctrl+K search, loading/error/empty states, toasts, side-panel forms, pagination, and split production bundles.
- Live dashboard aggregations and protected financial contribution reporting.
- Supplier/customer/vehicle/part creation and editing API, customer history detail API, catalog search, and responsive resource tables/forms.
- RFQs with multiple lines/suppliers, supplier offers, offer comparison data, supplier selection, and approval attribution.
- Transactional receiving, adjustment, reservation, release, issue, return, movement history, negative-stock prevention, and order reservation/dispatch rules.
- Customer quotations, approval, idempotent conversion to sales order, order dispatch, idempotent invoice creation, partial/full payments, balance enforcement, invoice PDF, item warranty generation, claims, and authenticated attachments.
- Local Windows setup/run scripts, Docker/Render/deployment instructions, backup/restore procedure, user guidance, assumptions, API tests, Playwright checks, and responsive screenshots.

## Follow-up scope before claiming every item in the original master specification

The current repository is a tested operational core, not yet every edge module listed in the master brief. The next implementation cycle should add:

- Dedicated purchase orders and goods receipts after selected supplier offers.
- Credit-note and customer-return ledgers with controlled reversal accounting.
- Customer quotation revision snapshots and detailed order status-event timelines.
- Database-backed custom permission editor instead of the current fixed least-privilege role matrix.
- Full user lifecycle UI for password changes, activation/deactivation, and session revocation.
- Supplier documents/performance dashboards and warranty claim event/evidence screens.
- CSV import/export, saved filters, bulk actions, column preferences, notifications, and print/PDF exports for reports and quotations.
- Secure supervised restore tooling; restore is currently an intentionally offline documented operation.
- Scheduled encrypted offsite backups and storage threshold alerting.
- Docker/container-recreation persistence test and staging Render acceptance (Docker was unavailable on this workstation).

These are deliberately recorded rather than represented as completed or hidden behind nonfunctional controls.
