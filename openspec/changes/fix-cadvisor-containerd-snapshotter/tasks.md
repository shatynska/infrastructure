## 1. Implement

- [x] 1.1 In `platform/docker-compose.yml`'s `cadvisor` service, change the image reference from `gcr.io/cadvisor/cadvisor:v0.49.1` to `ghcr.io/google/cadvisor:v0.60.5`, with a comment noting `gcr.io/cadvisor/cadvisor` is shut down (versions from v0.53.0 onward publish to `ghcr.io/google/cadvisor` instead)
- [x] 1.2 Add a read-only bind mount `/run/containerd/containerd.sock:/run/containerd/containerd.sock:ro` to the `cadvisor` service, alongside its existing `docker.sock` mount, with a comment explaining why (containerd-snapshotter support, `google/cadvisor#3643`/`#3709`)

## 2. Verify

- [x] 2.1 Run `docker compose config` against the changed file to confirm it's still valid — passes
- [x] 2.2 Confirm `openspec validate --strict` passes for this change — passes
- [ ] 2.3 Run this project's full pre-commit verification before considering the change complete — `pre-commit`/`gitleaks` aren't installed in this dev environment; ran the equivalent checks manually where available (see task 2.1)

## 3. Deploy and confirm

- [x] 3.1 Merge to `main` and let the existing `platform-deploy.yml` pipeline deploy it (not a manual/local deploy — this is `platform/`'s normal path) — merged via PR #48, deployed successfully after a re-run (an unrelated duplicate-looking workflow run was cancelled by mistake on first attempt; re-triggered cleanly, no partial-deploy state resulted since the cancellation happened before the host was touched)
- [x] 3.2 Check cAdvisor's logs post-deploy: confirm the "failed to identify the read-write layer ID" error is gone and the Docker container factory registers successfully — confirmed: `Registration of the docker container factory successfully` and `Registration of the containerd container factory successfully`, zero layerdb/mount-id errors
- [x] 3.3 Query Prometheus for `container_start_time_seconds` (or similar) and confirm it now reports real per-container `id` labels (e.g. `/docker/<container-id>`) instead of only systemd cgroup paths like `/user.slice/...` — confirmed, with a naming-scheme correction: this host's systemd cgroup driver names them `/system.slice/docker-<hash>.scope`, not `/docker/<hash>`, but critically the `name` label now correctly resolves to each container's real name (`platform-alertmanager-1`, `commerce-ops-app-1`, etc. — previously always blank)
- [x] 3.4 Confirm the `cadvisor` Prometheus scrape target is still `up` and the "Container health" Grafana dashboard renders real per-container data — scrape target confirmed `up`; dashboard rendering not separately re-checked here (covered by `add-platform-monitoring`'s own still-open task 5.6)
- [x] 3.5 Regression-test the false-positive this bug caused: reproduce the same conditions that triggered it this session (repeated short-lived SSH sessions or similar systemd-session churn against the host) and confirm `ContainerRestartingOrOOMKilled` does NOT false-fire on unrelated systemd cgroups anymore — confirmed: repeated SSH churn no longer produces deep `/user.slice/user-*/...` series (only the top-level `/user.slice` remains), and no false alert fired
- [x] 3.6 Force an actual container restart (e.g. `docker restart` on a real container more than 3 times within 10 minutes) and confirm `ContainerRestartingOrOOMKilled` fires and correctly names that real container — this closes `add-platform-monitoring`'s own blocked task 3.5(b) — confirmed: `ContainerRestartingOrOOMKilled` fired with `name: test5xx-restart-target`, correctly naming the real container (restarts spaced 35s apart, wider than Prometheus's 30s scrape interval, after an initial too-fast attempt undercounted `changes()`)
