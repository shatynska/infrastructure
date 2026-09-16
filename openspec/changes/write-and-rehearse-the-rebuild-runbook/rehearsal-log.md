# Rehearsal log — `main-staging`

The running record of the rehearsal the runbook calls for. Timings and divergences are written here as each phase completes, rather than at the end, so an interrupted run still leaves an account of how far it got. What belongs in the document itself — corrections to steps, and the finished record — is moved there at task 7.1 and 7.2; this file is archived with the change.

**Stack:** `main-staging`. **Route:** the `server_enabled` toggle. **Runbook followed:** `docs/runbook-rebuild.md` as merged at `54784a6` (PR #242).

## Phase 1 — pre-state, 2026-09-16T19:28:49Z

Captured by following the merged phase 1. Everything below is what "serving what it served before" means for this host, and is what phase 16 is checked against.

**Containers — ten, all up, eight of them the platform stack:**

    commerce-ops-worker-1          Up 3 hours
    commerce-ops-app-1             Up 3 hours (healthy)
    platform-postgres-1            Up 8 hours (healthy)
    platform-alertmanager-1        Up 10 hours (healthy)
    platform-grafana-1             Up 10 hours (healthy)
    platform-postgres-exporter-1   Up 10 hours (healthy)
    platform-traefik-1             Up 10 hours (healthy)
    platform-cadvisor-1            Up 10 hours (healthy)
    platform-prometheus-1          Up 10 hours (healthy)
    platform-node-exporter-1       Up 10 hours (healthy)

`platform-postgres-1`'s shorter uptime is `move-the-shared-database-onto-the-data-volume`, archived earlier today, and is not a fault.

**Scrape targets — five, all `up`:** `cadvisor`, `node-exporter`, `postgres-exporter`, `prometheus`, `traefik`.

**Addresses:** public IPv4 `62.238.17.177`; tailnet `100.85.219.36`, which `~/.ssh/config` pins as `HostName` for the `shatynska-main-staging` alias. Server type `cx23`.

**Volume:** `scsi-0HC_Volume_106839043` → `/dev/sdb`, mounted at `/mnt/main`, 9.8G with 708M used.

**Names resolving to this server**, all by the wildcard: `commerce-ops.main-staging.fincci.bike`, `main-staging.fincci.bike`, `grafana.main-staging.fincci.bike` — each `62.238.17.177`. Grafana's name resolving is not evidence that anything serves it: Grafana binds to the tailnet address alone.

**Serving:** `https://commerce-ops.main-staging.fincci.bike/` answers **404**, `/health` and `/docs` answer **200**. See the divergence below — the 404 is the application's and is the healthy state.

**Not captured by me:** the two heartbeat checks' period and grace at the observer. That read needs the observer's own account, which this session has no credential for; it is the operator's, and the runbook's phase 1 calls for it. **Until it is done, phase 12's comparison has nothing to compare against beyond what the register claims.**

### Divergences found in phase 1

1. **The serving check is wrong, and wrong in the direction that hides a real failure.** Phase 1 and phase 16 both run `curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike`, written as though a good answer were `200`. The application answers **404** at `/` by design — it is a FastAPI service with no route there — so an operator reading the runbook literally would record a failure before touching anything, or, worse, read a 404 *after* the rebuild as the expected state.

   **It hides a real failure because Traefik's own 404 is indistinguishable by status code.** A router that never matched — because DNS is stale, or the certificate did not issue, or the application's labels did not come back — answers 404 as well. The discriminator is the `server:` header and the body's content type: the application answers `server: uvicorn` with `application/json`, Traefik answers its own. The correction is to probe `/health` (200) and to say what a bare 404 does and does not prove.

2. **`dig` is not installed on this workstation**, so a reader checking which names resolve has to reach for something else. Not a runbook defect — it names no such command — but phase 5's instruction to read the zone at the provider is the only resolution step it gives, and a local check is worth having. `python3 -c 'import socket; print(socket.gethostbyname(...))'` is what was used here.

3. **Phase 1's own credential line is short by one.** It names the operator inspection key, `gh`'s token and the read-only Hetzner token. The capture also needs the **heartbeat observer's account**, for the period-and-grace read the same phase asks for — which is the one part of phase 1 this session could not perform.
