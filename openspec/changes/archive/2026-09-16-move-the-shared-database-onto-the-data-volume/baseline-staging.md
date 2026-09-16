# Baseline — `main-staging`, before the copy

Captured 2026-09-16 from the running instance, before `platform-postgres-1` was stopped. Task 6.3 compares against this, and without it "every database that was there before" is decidable only from memory.

    docker exec platform-postgres-1 sh -lc 'psql -U $POSTGRES_USER -d postgres -tAc "..."'

## Databases and sizes

| Database | Size | Owner |
|---|---|---|
| `commerce-ops` | 9726 kB | `commerce-ops` |
| `platform_admin` | 7678 kB | `platform_admin` |
| `postgres` | 7678 kB | `platform_admin` |

## Login roles

`commerce-ops`, `pgexporter`, `platform_admin`

`pgexporter` is the one whose absence is silent: it serves `/metrics` with HTTP 200 and `pg_up 0` when it cannot connect, so its container stays healthy and its Prometheus target stays up. Task 6.4 reads `pg_up 1` for that reason.
