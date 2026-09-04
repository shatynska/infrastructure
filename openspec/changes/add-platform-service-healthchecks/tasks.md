## 1. Add healthchecks

- [x] 1.1 Add a `healthcheck:` to the `traefik` service: `traefik healthcheck --ping`, and add `--ping=true` to its `command:` (uses Traefik's implicit internal entrypoint, default port 8080, unpublished -- no new entrypoint/port declaration needed), with a reasonable interval/timeout/retries/start_period
- [x] 1.2 Add a `healthcheck:` to the `postgres` service: `pg_isready -U $POSTGRES_USER` via `CMD-SHELL`, with a reasonable interval/timeout/retries/start_period
- [x] 1.3 Add a `healthcheck:` to the `prometheus` service: `wget --spider -q http://localhost:9090/-/ready` (or equivalent), with a reasonable interval/timeout/retries/start_period
- [x] 1.4 Add a `healthcheck:` to the `alertmanager` service: `wget --spider -q http://localhost:9093/-/ready`, with a reasonable interval/timeout/retries/start_period
- [x] 1.5 Add a `healthcheck:` to the `grafana` service: `wget --spider -q http://localhost:3000/api/health`, with a reasonable interval/timeout/retries/start_period
- [x] 1.6 Add a `healthcheck:` to the `node-exporter` service: `wget --spider -q http://localhost:9100/metrics`, with a reasonable interval/timeout/retries/start_period
- [x] 1.7 Add a `healthcheck:` to the `cadvisor` service: `wget --spider -q http://localhost:8080/healthz`, with a reasonable interval/timeout/retries/start_period
- [x] 1.8 Add a `healthcheck:` to the `postgres-exporter` service: `wget --spider -q http://localhost:9187/metrics`, with a reasonable interval/timeout/retries/start_period. This only detects the exporter's own HTTP server failing to come up -- it does NOT detect a bad Postgres credential (see design.md's Decisions/Risks); do not extend its scope to imply otherwise
- [x] 1.9 Confirm `wget`/`pg_isready`/`traefik healthcheck` are actually present/usable in each of the eight images -- verified live against the actual running production images (or an identically-tagged local container for Traefik/Postgres): all eight work as designed, no substitution needed

## 2. Verify the fix actually catches a broken deploy

All of 2.1-2.7 below were verified live in a local scratch Docker environment (this sandbox has Docker available), first against standalone containers to validate each healthcheck mechanism, then against the actual edited `platform/docker-compose.yml` end to end. Findings are recorded in design.md's Context/Risks.

- [x] 2.1 Locally, deliberately reproduced the incident's failure mode: pointed Grafana's `/var/lib/grafana` at a root-owned, non-writable directory and ran `docker compose up -d --wait`
- [x] 2.2 Confirmed `docker compose up -d --wait` failed non-zero (exit 1, `container ...-grafana-1 is unhealthy`) instead of reporting false success
- [x] 2.3 Confirmed a normal, correctly-configured `docker compose up -d --wait` succeeds (exit 0) and all eight services report `healthy`/reach running as expected -- re-run against the final edited compose file (not just the original six): all eight (`traefik`, `postgres`, `prometheus`, `alertmanager`, `grafana`, `node-exporter`, `cadvisor`, `postgres-exporter`) confirmed `healthy` via `docker inspect`
- [x] 2.4 Negative-tested each of the other healthchecked services individually: overrode each service's entrypoint to `sleep infinity` (never opens its healthcheck's port), confirmed `docker compose up -d --wait` fails non-zero specifically because that service never becomes healthy, then reverted. Confirms the "fails loudly for any cause that stops the service's own readiness layer from coming up" claim per-service, not just for Grafana
- [x] 2.5 Confirmed postgres-exporter's healthcheck reports `healthy` even when pointed at a real Postgres with no `pgexporter` role (password authentication failure, `pg_up 0` in its own metrics) -- the documented gap in design.md's Risks is real, not a stale assumption
- [x] 2.6 Confirmed all healthchecked services report `healthy` (`docker inspect --format '{{.State.Health.Status}}'`) under correct configuration
- [x] 2.7 **Discovered during this task, not merely confirmed**: the originally-assumed "no-healthcheck service that never starts running still fails the deploy" claim does NOT hold for a crash-looping service under `restart: unless-stopped`. Deliberately broke Traefik's entrypoint so it crashes immediately; reproduced twice that `docker compose up -d --wait` reported success (exit 0, Traefik listed "Healthy") while Traefik had already auto-restarted 6-8 times. This is why Traefik/Postgres were folded into this change's scope (tasks 1.1/1.2), and why the `iac-platform-deploy-pipeline` spec delta's language was corrected. **Regression-confirmed fixed**: re-ran the identical broken-entrypoint test against the final compose file with Traefik's new healthcheck in place -- `docker compose up -d --wait` now correctly fails (exit 1, `container ...-traefik-1 is unhealthy`)

## 3. Documentation

- [x] 3.1 Add a brief note to `platform/README.md` that every service in the shared stack, including Traefik and Postgres now, is expected to define a real healthcheck, so whoever adds the next service does the same
- [x] 3.2 Run `docker compose config` to confirm the Compose file still parses cleanly with the new `healthcheck:` blocks
- [x] 3.3 Confirm `openspec validate --strict` passes for this change

## 4. Deploy and confirm

- [ ] 4.1 Merge to `main` and let the gated `platform-deploy.yml` pipeline deploy it
- [ ] 4.2 Confirm all eight services report `healthy`/`running` as expected in production, matching the local verification in section 2
