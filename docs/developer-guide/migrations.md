# Migrations hygiene

ReportAgent applies SQL files from `app/db/migrations/` in **lexicographic filename order** on startup (`app/db/init_db.py`).

## Duplicate numeric prefixes

Historical duplicates exist (two `007_*`, `008_*`, `009_*`). On **existing** databases only unapplied filenames run — renames are safe only for fresh installs.

| File | Notes |
|------|-------|
| `007_add_admin_audit_log.sql` | Admin audit |
| `007_add_yookassa_tables.sql` | YooKassa — runs after admin audit on fresh DB |
| `008_add_stripe_integration.sql` | Stripe |
| `008_add_preview_log.sql` | Legacy preview schema |
| `009_add_preview_log.sql` | No-op if `008_add_preview_log` applied |

**New migrations** use monotonic numbers (`031_`, `032_`, …). Do not reuse `007`–`009`.

## Fresh install checklist

1. `docker compose up` → migrations auto-apply
2. Verify: `sqlite3 app/data/users.db "SELECT filename FROM schema_migrations ORDER BY filename"`
3. Backup before manual SQL: `./scripts/backup.sh`
