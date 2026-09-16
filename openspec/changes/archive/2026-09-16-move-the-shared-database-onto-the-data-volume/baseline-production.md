# Baseline — `main-production`, before the copy

Captured 2026-09-16 from the running instance, before `platform-postgres-1` was stopped. Task 6.5 compares against this.

## Databases and sizes

| Database | Size | Owner |
|---|---|---|
| `commerce-ops` | 13 MB | `commerce-ops` |
| `platform_admin` | 7678 kB | `platform_admin` |
| `postgres` | 7678 kB | `platform_admin` |

## Login roles

`commerce-ops`, `pgexporter`, `platform_admin`

`commerce-ops`'s own PostgreSQL container on this host — `commerce-ops-postgres-1`, holding that application's durable data — is **not** this instance and is untouched by this change. It keeps its own Docker volume on the root disk.
