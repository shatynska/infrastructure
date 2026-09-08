## Why

Two requirements in this repository describe a host that does not exist. *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) requires every application to be given a database inside the platform's one instance. Read on `main-server` on 2026-09-08, that instance holds `postgres`, `platform_admin` and the two templates and nothing else, while the one application on the host runs its own `postgres:16-alpine` container on its own `app_db` network. The requirement is unmet, and `platform/README.md` says why in its own words: "How a new application actually gets its own database/role inside that instance is not yet defined."

The change queue recorded that as entry 20, and recorded entry 19 next to it: the only backup of this host is Hetzner's daily server snapshot, so a logical dump written outside the Hetzner project was the obvious missing piece. Reading the host answered entry 19 differently than the entry assumed. A dump of the shared instance would today copy nothing, because the shared instance holds nothing.

The operator's answer settles both. **Durable product data belongs in Supabase** — a Pro-plan project with vendor-managed daily backups — and not on this host. **The shared instance stays**, with its role narrowed to what it is actually good for: non-critical technical or temporary records an application would rather not put in Supabase. Data of that class does not warrant a backup mechanism, and the operator has said so explicitly.

That makes the platform stack's own stores classifiable, and every one of them lands outside the backup obligation. They were enumerated from the host — `docker volume ls` and each running container's mounts — rather than read off the stack definition, which is how the fifth was found. One further store, an application's own, does not satisfy the obligation and is named as a divergence rather than omitted:

| Store | Why it needs no backup |
|---|---|
| `postgres_data`, on the host `platform_postgres_data` | Non-durable technical data by policy, as of this change |
| `/mnt/main-data/prometheus` | `--storage.tsdb.retention.time=28d`, `--storage.tsdb.retention.size=4GB` — a rolling window that deletes itself |
| `/mnt/main-data/grafana` | Datasource and all three dashboards are provisioned from `platform/docker-compose.yml`, so a redeploy recreates them; the rest of the directory — Grafana's own database, and any dashboard saved through the UI, which the stack permits — is non-durable by policy |
| `traefik_letsencrypt`, on the host `platform_traefik_letsencrypt` | 28 kB of certificates ACME re-issues on demand |
| Alertmanager's anonymous volume at `/alertmanager` | Silences and the notification log, non-durable by policy — a lost silence lapses into a notification, which is the safe direction. Declared by the image, not by `platform/docker-compose.yml`, which is why the census was taken from the host |

So the work is not a backup pipeline. It is writing down which data this host is permitted to hold, and what becomes owed the moment that stops being true — because the property above is a decision, and an undocumented decision is indistinguishable from an oversight to whoever next puts a database here.

## What Changes

- **The shared instance is scoped to non-durable data.** *Single Shared PostgreSQL Instance, Per-Application Databases* stops mandating a database for every application and instead binds when an application actually stores technical or temporary data on this host: that data goes in the shared instance rather than in a new container. Durable application data belongs in an external managed service that owns its own backups.
- **The reuse scenario is narrowed to match.** *Shared Services Live in a Dedicated Platform Stack* currently has a new application reusing "the existing platform-managed reverse proxy and database rather than defining its own instance of either". Under the scoping above, an application whose data is durable legitimately uses neither this instance nor its own container, so the database half of that scenario is qualified. The reverse-proxy half is unchanged and unconditional.
- **A new requirement records the classification and, more importantly, its triggers.** *No Store on This Host Holds Data Requiring Backup* (`iac-safety-hardening`) states the property a store must satisfy, carries the five above as a dated table, and fires in two directions: durable data landing here owes a logical backup and a rehearsed restore **before** it lands, and a classified store whose stated reason stops being true — a retention flag removed, the stanza provisioning Grafana's dashboards deleted — is in breach the moment it does, with no new data required. The classification will age; the triggers are what stay true.
- **The divergence this host is already in is named in the requirement itself**, dated, with its resolution and the note that it is not a precedent — the form *Monitoring Services Are Not Reachable From Application Containers* already uses for a stated exception. A requirement whose only correction lives in `docs/change-queue.md` would lose it: that file's entries are deleted when their change archives.
- **`Data Durability for Stateful Resources` is amended** so the two requirements stop giving different accounts of the same setting. `backups = true` stays; its rationale now says what the snapshot is — daily, crash-consistent, root disk only, not the attached volume — and that it does not discharge the new obligation.
- **`platform/README.md` closes its open question**: what the shared instance is for, that its contents are not backed up, and where an application with durable state goes instead.
- **The commerce-ops divergence is recorded with a named resolution** rather than tolerated silently: that application's 12 MB moves to Supabase, which is work in its own repository and not in this one.
- **`docs/change-queue.md` entries 19 and 20 are deleted**, both resolved here.

Nothing about the running system changes. No service is added, removed or reconfigured; no host is converged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-services`: *Single Shared PostgreSQL Instance, Per-Application Databases* is narrowed to non-durable data and made conditional on an application actually storing such data here; *Shared Services Live in a Dedicated Platform Stack*'s reuse scenario is qualified for the database half.
- `iac-safety-hardening`: adds *No Store on This Host Holds Data Requiring Backup*, and amends *Data Durability for Stateful Resources* so its rationale states what the server snapshot covers rather than implying it is a database backup.

## Impact

- **Specifications**: `openspec/specs/iac-platform-services/spec.md`, `openspec/specs/iac-safety-hardening/spec.md`.
- **Documentation**: `platform/README.md`, including its Boundary section, which states the superseded model more prominently than the paragraph that raised the question; `docs/bootstrap-a-new-host.md`, whose per-application database step offers a choice this change removes; `docs/review-2026-09-08-host-readiness.md` and `platform/.env.example`, which carry pointers this change invalidates; `docs/change-queue.md` (entries 19 and 20 deleted; two entries added — the commerce-ops migration this repository cannot perform, and an unrelated finding about the static suite recorded under `AGENTS.md`'s "A second change surfacing"); `docs/deferred-work.md` (per-application provisioning: the manual step is written down, and automating it is deferred until an application needs one).
- **Code, configuration and host**: none. `platform-postgres` and `postgres-exporter` stay exactly as they are.
- **Tests**: the change declares specification deltas, so it owes derived tests under `AGENTS.md`, and the test author is dispatched with all three rows of that file's table rather than with a verdict about which apply. Two of the classification's reasons are static reads of `platform/docker-compose.yml` — Prometheus's retention flags and Grafana's provisioned datasource and dashboards — which is the `.github/tests` row's stated subject; the rest is policy that may not be placeable anywhere, and that outcome is the author's to report.
- **Depends on a fact outside this repository**: that the Supabase project stays on a plan with backups. The requirement states the dependency rather than assuming it.
