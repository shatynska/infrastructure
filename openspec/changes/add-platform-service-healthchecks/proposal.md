## Why

`add-platform-monitoring`'s deploy reported full success — every container "Healthy" per `docker compose up -d --wait` — while Grafana was actually crash-looping every ~60 seconds (`GF_PATHS_DATA='/var/lib/grafana' is not writable`, `mkdir: can't create directory '/var/lib/grafana/plugins': Permission denied`), because the host's `main-data` volume had never been mounted by Ansible. Compose's `--wait` only waits for "Running" state on a service with no Docker `HEALTHCHECK` defined — none of that change's six new services define one — so a broken deploy reported green. The mechanism this project already relies on to catch a partial deploy (`docker compose up -d --wait` failing the deploy step when a service doesn't come up healthy — recorded as the chosen failure-detection method in `deploy-platform-compose-stack`'s design record) only works when every service actually has a real healthcheck. This incident is exactly the case where it didn't.

**Scope expanded during implementation** (originally Traefik/Postgres were declared out of scope — see the superseded "Explicitly out of scope" note this revision removes): live testing of the six healthchecks proposed here surfaced that Compose's "no healthcheck defined → wait for running state" fallback, which the original proposal relied on to justify leaving Traefik/Postgres uncovered, does not reliably catch a crash-looping service. A service with `restart: unless-stopped` (both Traefik and Postgres have this) can satisfy `--wait`'s "reached running" check during the brief moment it's up between automatic restarts, even while genuinely crash-looping — reproduced twice locally by deliberately breaking Traefik's entrypoint: `docker compose up -d --wait` reported success while Traefik had already restarted 6-8 times. This means the original scope decision's own safety justification for excluding Traefik/Postgres doesn't hold up, so this revision folds them in too.

## What Changes

- Add an explicit Docker Compose `healthcheck:` to all eight services in `platform/docker-compose.yml` — the six `add-platform-monitoring` introduced (Prometheus, Alertmanager, Grafana, node-exporter, cAdvisor, postgres-exporter) plus the two pre-existing ones this revision adds (Traefik, Postgres) — each checking that service's own real readiness signal, not merely that its process is running.
- With real healthchecks on every service, the existing `docker compose up -d --wait` mechanism (already relied upon, no new mechanism introduced) will correctly detect any reason a service fails to become healthy — not just the volume-permission cause behind the originating incident, but any future misconfiguration too, and not just for the six original services but for the whole stack — and fail the GitHub Actions deploy step loudly and immediately instead of reporting false success.
- Codify this as an actual spec requirement — in `iac-platform-services`, that every service in the shared platform stack (all eight existing, and any added after this requirement's adoption) defines a real healthcheck; and in `iac-platform-deploy-pipeline`, that the deploy job fails when any healthchecked service does not reach a healthy state — rather than leaving it as design-record prose a future change can silently regress, the way this one did. The deploy-pipeline delta also corrects the previously-assumed "a service with no healthcheck still fails the deploy if it never reaches running" fallback to state its actual, narrower guarantee (see Decisions in design.md) — now purely hypothetical for this stack, since no service is left without a real healthcheck, but honest about what it would and wouldn't catch if a future service were added without one.

Explicitly out of scope:
- Any change to Ansible remaining manually operator-run, or to the `deploy` account's forced-command SSH restriction. No pre-flight SSH check is added; the fix works entirely through the deploy mechanism that already exists.
- Re-litigating any `add-platform-monitoring` decision (network placement, secrets, retention, etc.).

## Capabilities

### New Capabilities

(none — this extends existing capabilities)

### Modified Capabilities

- `iac-platform-services`: adds a requirement that every service in the shared platform stack — all eight existing (Traefik, Postgres, Prometheus, Alertmanager, Grafana, node-exporter, cAdvisor, postgres-exporter), and any added after this requirement's adoption — defines a Docker healthcheck reflecting its actual readiness. No longer carves out an exemption for Traefik/Postgres.
- `iac-platform-deploy-pipeline`: adds a requirement making explicit, as a testable requirement, that the deploy job fails when any service that defines a healthcheck does not reach a healthy state within `docker compose up`'s wait. Also corrects the previously-assumed fallback for a hypothetical future service with no healthcheck: Compose's wait only guarantees the container reached a running state *at least transiently*, which does **not** reliably catch a crash-looping service under an automatic restart policy — demonstrated live this session, not assumed.

## Impact

- `platform/docker-compose.yml`: eight `healthcheck:` blocks added (one per service); Traefik's `command:` gains `--ping=true` to expose the endpoint its healthcheck needs; no other service behavior changes.
- `platform/README.md`: brief note that every service in the shared stack, including Traefik and Postgres now, is expected to define a real healthcheck, for whoever adds the next one.
- No Terraform, Ansible, or GitHub Actions workflow changes — the fix is entirely within the Compose file, using a deploy mechanism (`docker compose up -d --wait` inside `app-deploy`) that already exists and needs no modification.
