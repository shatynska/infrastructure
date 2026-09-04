## Why

`add-platform-monitoring`'s deploy reported full success — every container "Healthy" per `docker compose up -d --wait` — while Grafana was actually crash-looping every ~60 seconds (`GF_PATHS_DATA='/var/lib/grafana' is not writable`, `mkdir: can't create directory '/var/lib/grafana/plugins': Permission denied`), because the host's `main-data` volume had never been mounted by Ansible. Compose's `--wait` only waits for "Running" state on a service with no Docker `HEALTHCHECK` defined — none of that change's six new services define one — so a broken deploy reported green. The mechanism this project already relies on to catch a partial deploy (`docker compose up -d --wait` failing the deploy step when a service doesn't come up healthy — recorded as the chosen failure-detection method in `deploy-platform-compose-stack`'s design record) only works when every service actually has a real healthcheck. This incident is exactly the case where it didn't.

## What Changes

- Add an explicit Docker Compose `healthcheck:` to each of `add-platform-monitoring`'s six new services (Prometheus, Alertmanager, Grafana, node-exporter, cAdvisor, postgres-exporter) in `platform/docker-compose.yml`, each checking that service's own real readiness endpoint — not merely that its process is running.
- With real healthchecks in place, the existing `docker compose up -d --wait` mechanism (already relied upon, no new mechanism introduced) will correctly detect any reason one of these services fails to become healthy — not just the volume-permission cause behind this incident, but any future misconfiguration too — and fail the GitHub Actions deploy step loudly and immediately instead of reporting false success.
- Codify this as an actual spec requirement — in `iac-platform-services`, that these six monitoring services (and any service added to the shared stack after this requirement's adoption) define a real healthcheck, explicitly not retroactive to the pre-existing Traefik/Postgres services; and in `iac-platform-deploy-pipeline`, that the deploy job fails when a healthchecked service does not reach a healthy state, and a non-healthchecked service (such as the pre-existing Traefik/Postgres) does not reach a running state — rather than leaving it as design-record prose a future change can silently regress, the way this one did.

Explicitly out of scope:
- Adding healthchecks to Traefik or Postgres — pre-existing services outside this incident's cause; a candidate for a separate future change, not folded in here.
- Any change to Ansible remaining manually operator-run, or to the `deploy` account's forced-command SSH restriction. No pre-flight SSH check is added; the fix works entirely through the deploy mechanism that already exists.
- Re-litigating any `add-platform-monitoring` decision (network placement, secrets, retention, etc.).

## Capabilities

### New Capabilities

(none — this extends existing capabilities)

### Modified Capabilities

- `iac-platform-services`: adds a requirement that the six monitoring services this change covers (Prometheus, Alertmanager, Grafana, node-exporter, cAdvisor, postgres-exporter) — and any service added to the shared platform stack after this requirement's adoption — each define a Docker healthcheck reflecting their actual readiness. Explicitly not retroactive to the pre-existing Traefik or Postgres services.
- `iac-platform-deploy-pipeline`: adds a requirement making explicit, as a testable requirement, that the deploy job fails when a service that defines a healthcheck does not reach a healthy state within `docker compose up`'s wait (and, for a service with no healthcheck defined — such as the pre-existing Traefik and Postgres — that it must still reach a running state), rather than reporting success regardless.

## Impact

- `platform/docker-compose.yml`: six `healthcheck:` blocks added, one per new service; no other service behavior changes.
- `platform/README.md`: brief note that every service added to the shared stack going forward is expected to define a real healthcheck (not retroactive to the pre-existing Traefik/Postgres), for whoever adds the next one.
- No Terraform, Ansible, or GitHub Actions workflow changes — the fix is entirely within the Compose file, using a deploy mechanism (`docker compose up -d --wait` inside `app-deploy`) that already exists and needs no modification.
