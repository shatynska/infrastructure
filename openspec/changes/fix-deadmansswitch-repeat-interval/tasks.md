## 1. Implement

- [x] 1.1 In `platform/docker-compose.yml`'s `alertmanager_config`, change the Watchdog route's `repeat_interval` from `5m` to `2m`, with a comment explaining why (observed ~2x delivery-cadence doubling when repeat_interval equals the inherited group_interval)

## 2. Verify

- [x] 2.1 Run `docker compose config` against the changed file to confirm it's still valid — passes
- [x] 2.2 Confirm `openspec validate --strict` passes for this change — passes

## 3. Deploy and confirm

- [ ] 3.1 Merge to `main` and let the gated `platform-deploy.yml` pipeline deploy it
- [ ] 3.2 Confirm the live config reflects `repeat_interval: 2m` for the Watchdog route (`/api/v2/status`)
- [ ] 3.3 Observe real delivery cadence over at least 20-30 minutes (via `alertmanager_notifications_total{integration="webhook"}` or the dead-man's-switch's own ping log) and confirm it's now close to 5 minutes, not ~10
- [ ] 3.4 Confirm no further false "down" notifications reach Slack over the same observation window
