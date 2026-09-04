## 1. Add healthchecks

- [ ] 1.1 Add a `healthcheck:` to the `prometheus` service: `wget --spider -q http://localhost:9090/-/ready` (or equivalent), with a reasonable interval/timeout/retries/start_period
- [ ] 1.2 Add a `healthcheck:` to the `alertmanager` service: `wget --spider -q http://localhost:9093/-/ready`, with a reasonable interval/timeout/retries/start_period
- [ ] 1.3 Add a `healthcheck:` to the `grafana` service: `wget --spider -q http://localhost:3000/api/health`, with a reasonable interval/timeout/retries/start_period
- [ ] 1.4 Add a `healthcheck:` to the `node-exporter` service: `wget --spider -q http://localhost:9100/metrics`, with a reasonable interval/timeout/retries/start_period
- [ ] 1.5 Add a `healthcheck:` to the `cadvisor` service: `wget --spider -q http://localhost:8080/healthz`, with a reasonable interval/timeout/retries/start_period
- [ ] 1.6 Add a `healthcheck:` to the `postgres-exporter` service: `wget --spider -q http://localhost:9187/metrics`, with a reasonable interval/timeout/retries/start_period. This only detects the exporter's own HTTP server failing to come up — it does NOT detect a bad Postgres credential (see design.md's Decisions/Risks); do not extend its scope to imply otherwise
- [ ] 1.7 Confirm `wget` is actually present in each of the six images (check each image's base/documentation) — swap to `curl` or a raw TCP check (e.g. `nc -z`) for any image where it isn't, rather than assuming

## 2. Verify the fix actually catches a broken deploy

- [ ] 2.1 Locally (or in a scratch environment), deliberately reproduce the incident's exact failure mode: mount an unwritable/wrong-permission directory as Grafana's `/var/lib/grafana` and run `docker compose up -d --wait`
- [ ] 2.2 Confirm `docker compose up -d --wait` now fails non-zero (rather than reporting all services healthy) when Grafana is stuck crash-looping this way
- [ ] 2.3 Confirm a normal, correctly-configured `docker compose up -d --wait` still succeeds and reports all six services healthy, so this change doesn't introduce false failures
- [ ] 2.4 Beyond Grafana, negative-test each of the other five services generically: temporarily override that service's `command`/`entrypoint` to something that never opens its healthcheck's port (e.g. `sleep infinity`), confirm `docker compose up -d --wait` fails non-zero specifically because that service never becomes healthy, then revert. This establishes the "fails loudly, for any cause that stops the service's own HTTP layer from coming up" claim per-service, not just for Grafana
- [ ] 2.5 Specifically for postgres-exporter, confirm (don't just assume) that pointing it at a bad `DATA_SOURCE_NAME` still leaves its healthcheck reporting `healthy` (i.e. the documented gap in design.md's Risks is real, not a stale assumption) — if it turns out `/metrics` actually does fail in this case, correct design.md's claim instead of leaving the false negative undocumented
- [ ] 2.6 Once genuinely healthy and correctly configured, confirm each of the six services' healthcheck reports `healthy` — e.g. `docker inspect --format '{{.State.Health.Status}}' <container>` for each
- [ ] 2.7 Confirm the `iac-platform-deploy-pipeline` delta's "no-healthcheck service that never starts running still fails the deploy" scenario, not just the healthchecked-service scenarios: temporarily break a non-healthchecked service (Traefik or Postgres — e.g. override its `command` to something that exits immediately or never comes up), confirm `docker compose up -d --wait` still fails non-zero because that service never reaches running, then revert

## 3. Documentation

- [ ] 3.1 Add a brief note to `platform/README.md` that every service added to the shared stack going forward is expected to define a real healthcheck (not retroactive to the pre-existing Traefik/Postgres), so whoever adds the next service does the same
- [ ] 3.2 Run `docker compose config` to confirm the Compose file still parses cleanly with the new `healthcheck:` blocks
- [ ] 3.3 Confirm `openspec validate --strict` passes for this change
