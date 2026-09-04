## 1. Implement

- [x] 1.1 In `platform/docker-compose.yml`'s `cadvisor` service, change the image reference from `gcr.io/cadvisor/cadvisor:v0.49.1` to `ghcr.io/google/cadvisor:v0.60.5`, with a comment noting `gcr.io/cadvisor/cadvisor` is shut down (versions from v0.53.0 onward publish to `ghcr.io/google/cadvisor` instead)
- [x] 1.2 Add a read-only bind mount `/run/containerd/containerd.sock:/run/containerd/containerd.sock:ro` to the `cadvisor` service, alongside its existing `docker.sock` mount, with a comment explaining why (containerd-snapshotter support, `google/cadvisor#3643`/`#3709`)

## 2. Verify

- [x] 2.1 Run `docker compose config` against the changed file to confirm it's still valid — passes
- [x] 2.2 Confirm `openspec validate --strict` passes for this change — passes
- [ ] 2.3 Run this project's full pre-commit verification before considering the change complete — `pre-commit`/`gitleaks` aren't installed in this dev environment; ran the equivalent checks manually where available (see task 2.1)

## 3. Deploy and confirm

- [ ] 3.1 Merge to `main` and let the existing `platform-deploy.yml` pipeline deploy it (not a manual/local deploy — this is `platform/`'s normal path)
- [ ] 3.2 Check cAdvisor's logs post-deploy: confirm the "failed to identify the read-write layer ID" error is gone and the Docker container factory registers successfully
- [ ] 3.3 Query Prometheus for `container_start_time_seconds` (or similar) and confirm it now reports real per-container `id` labels (e.g. `/docker/<container-id>`) instead of only systemd cgroup paths like `/user.slice/...`
- [ ] 3.4 Confirm the `cadvisor` Prometheus scrape target is still `up` and the "Container health" Grafana dashboard renders real per-container data
- [ ] 3.5 Regression-test the false-positive this bug caused: reproduce the same conditions that triggered it this session (repeated short-lived SSH sessions or similar systemd-session churn against the host) and confirm `ContainerRestartingOrOOMKilled` does NOT false-fire on unrelated systemd cgroups anymore
- [ ] 3.6 Force an actual container restart (e.g. `docker restart` on a real container more than 3 times within 10 minutes) and confirm `ContainerRestartingOrOOMKilled` fires and correctly names that real container — this closes `add-platform-monitoring`'s own blocked task 3.5(b)
