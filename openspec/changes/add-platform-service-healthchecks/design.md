## Context

See `proposal.md` for the incident this change fixes. Relevant existing constraints:

- `app-deploy` (on the host, provisioned by `iac-host-configuration`'s forced-command deploy account) runs `docker compose up -d --wait`, which — per `deploy-platform-compose-stack`'s design record — is this project's already-chosen mechanism for failing the deploy job on a partial deploy. No separate post-deploy health check exists or is being added; this change makes that existing mechanism actually work for all six services `add-platform-monitoring` introduced.
- Compose's `--wait` behavior: a service with a defined `healthcheck:` is waited on until it reports `healthy` (or the wait times out, failing the command); a service with none is only waited on until it reaches `running` state, which is what let the crash-looping Grafana container in the incident report as "Healthy" in the deploy log.
- The `deploy` account's SSH key is restricted to the forced command `deploy-receive platform` (`iac-host-configuration`'s "Restricted Deploy Account Supports Per-Application Forced-Command Deploys" requirement) — nothing in this change touches that restriction or needs to.

## Goals / Non-Goals

**Goals:**
- Make a broken deploy of any of the six `add-platform-monitoring` services fail loudly, for any cause that stops that service's own HTTP server from becoming reachable and ready — which is what the incident's cause (and most realistic startup failures: bad config, permission errors, missing dependencies at the process level) actually looks like — using the mechanism this project already relies on.
- The one class of failure this goal does **not** cover: a service whose HTTP server comes up fine but which cannot do its actual job for an external reason (postgres-exporter reachable but unable to authenticate to Postgres is the concrete case here — see the Decisions table). That gap is real, pre-existing, and out of scope for this change; it stays covered by `MetricsTargetDown` instead.

**Non-Goals:**
- Healthchecks for Traefik or Postgres (pre-existing, outside this incident's cause).
- Any new pre-flight check, SSH capability, or automation of the Ansible-run step. Ansible remains manually operator-run, unchanged.
- Retrying or auto-remediating a failed deploy — failing loudly and visibly is the whole goal; recovery stays a human action, as it already is for any other deploy failure.

## Decisions

**One `healthcheck:` per new service, each hitting that service's own real readiness signal, not a generic "is the process alive" check.**

| Service | Healthcheck |
|---|---|
| Prometheus | `wget --spider -q http://localhost:9090/-/ready` — Prometheus's own documented readiness endpoint (distinct from `/-/healthy`, which reports healthy before the TSDB and rule manager are actually ready to serve/evaluate). |
| Alertmanager | `wget --spider -q http://localhost:9093/-/ready` — same rationale: Alertmanager's own readiness endpoint, not just "is the process up." |
| Grafana | `wget --spider -q http://localhost:3000/api/health` — Grafana's documented health endpoint; this is exactly the check that would have caught the incident, since Grafana fails to reach a ready state (and this endpoint reflects that) when its data directory isn't writable. |
| node-exporter | `wget --spider -q http://localhost:9100/metrics` — no dedicated readiness endpoint exists; successfully serving its metrics page is the closest real signal that it's doing its job, not just that the binary launched. |
| cAdvisor | `wget --spider -q http://localhost:8080/healthz` — cAdvisor's own documented health endpoint. |
| postgres-exporter | `wget --spider -q http://localhost:9187/metrics` — same reasoning as node-exporter: no dedicated readiness endpoint, so this only confirms the exporter's own HTTP server is up, not that it can actually reach or query Postgres. `postgres_exporter`'s `/metrics` handler returns HTTP 200 regardless of database connectivity (a bad DSN or missing role shows up as `pg_up 0` in the metrics body, not as a failed HTTP response), so this healthcheck deliberately does **not** claim to catch that class of failure — that's already caught by `add-platform-monitoring`'s separate `MetricsTargetDown` alert (`up == 0`), a different, alerting-based detection path, not this deploy-time one. Earlier draft of this row overclaimed catching "a bad DSN or missing role" via this healthcheck; corrected here after review — see `platform/README.md`'s own existing documentation of the `MetricsTargetDown` path, which already describes this exact gap correctly. |

`wget` is used throughout (present in each of these images already, since they're all built on minimal Linux bases that include it for their own use, or already ship it) rather than adding `curl` as a new dependency to any image.

**Alternative considered and rejected: a single pre-flight SSH check (e.g. `findmnt /mnt/main-data`) run from the GitHub Actions job before delivering the Compose file.** This was the first fix considered, and rejected: it would require either widening the `deploy` account's forced-command restriction (a real, deliberate security boundary this project does not lightly touch) or adding a second SSH credential with broader command execution rights, and it would only catch this one specific cause (the volume not being mounted) rather than the general class of "a service didn't actually come up" failures. The healthcheck approach catches this incident's cause and every other way a service could fail to become ready, through a mechanism that already exists and needs no new credential or workflow step.

## Risks / Trade-offs

- [Risk] A healthcheck endpoint could itself be flaky or slow to respond under load, causing `--wait` to time out and fail a deploy that was actually fine. → Mitigation: each check hits a lightweight, purpose-built readiness/health endpoint each project documents for exactly this use, not an expensive query; Compose's default healthcheck interval/timeout/retries give a service a reasonable window before being judged unhealthy.
- [Risk] `wget` availability differs slightly across these images (some are Alpine-based, some are distroless-adjacent) — an assumed-present binary that turns out missing would make the healthcheck itself fail to execute, masking the real signal behind a different error. → Mitigation: task list includes verifying each healthcheck actually runs (not just that the Compose file parses) before considering this change complete.
- [Risk] postgres-exporter's healthcheck cannot detect a bad database credential or a missing/dropped `pgexporter` role — `postgres_exporter` serves `/metrics` with HTTP 200 regardless of database connectivity, so the container-level healthcheck stays "healthy" in exactly that failure. → Mitigation: this specific gap is already covered by a different mechanism, `add-platform-monitoring`'s `MetricsTargetDown` alert — slower (alert-based, not deploy-blocking) but real. Not solved here; documented as a known, accepted residual gap rather than silently left unstated.

## Migration Plan

Purely additive to six existing service definitions; no new service, network, secret, or workflow change. Rollback is reverting the six `healthcheck:` blocks. No data or running-state impact — a redeploy after this change picks up the healthchecks the same way any other Compose service definition change is picked up.

## Open Questions

None — this is a narrow, mechanically-verifiable fix.
