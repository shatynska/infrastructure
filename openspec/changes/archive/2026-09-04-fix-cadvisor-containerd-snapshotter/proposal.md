## Why

`add-platform-monitoring` (merged, PR #45; not yet archived) deployed
cAdvisor v0.49.1 to provide per-container metrics (restart/OOM detection
via `container_start_time_seconds`/`container_oom_events_total`, feeding
the `ContainerRestartingOrOOMKilled` alert rule and the "Container health"
Grafana dashboard). On `main-server`, this has never actually worked:
Docker Engine 29.7.2 here uses containerd's snapshotter/image-store
backend (`docker info` shows `driver-type: io.containerd.snapshotter.v1`),
not the classic overlayfs graphdriver cAdvisor v0.49.1's Docker container
factory assumes. It tries to parse
`/var/lib/docker/image/overlayfs/layerdb/mounts/<id>/mount-id` directly off
disk to identify each container's read-write layer — a path that doesn't
exist in this storage mode — and fails for every real container
(`Failed to create existing container: ... failed to identify the
read-write layer ID ... mount-id: no such file or directory`, in its own
logs). It falls back to tracking only systemd cgroup units instead of
containers.

This is worse than just "no data": verified live during
`add-platform-monitoring`'s own verification (see that change's `tasks.md`
and project memory), `ContainerRestartingOrOOMKilled` false-fired 8 times
on unrelated systemd session-scope cgroups (SSH login session churn) and
reached Slack with a blank container name in the alert text.

This is exactly cAdvisor's own upstream bug
[google/cadvisor#3643](https://github.com/google/cadvisor/issues/3643),
fixed by
[google/cadvisor#3709](https://github.com/google/cadvisor/pull/3709)
(merged 2025-12-02), first released in v0.54.0. The fix makes cAdvisor's
Docker factory resolve each container's read-write layer via a containerd
client instead of parsing on-disk layerdb files, which requires mounting
containerd's own socket in addition to `docker.sock`.

## What Changes

- Bump the `cadvisor` service's image in `platform/docker-compose.yml`
  from `gcr.io/cadvisor/cadvisor:v0.49.1` to `ghcr.io/google/cadvisor:v0.60.5`
  — both the tag (to a current `v0.54.0`-or-later release) and the
  registry itself change: `gcr.io/cadvisor/cadvisor` is shut down (Google
  Container Registry was deprecated in March 2024, shut down March 2025);
  versions from v0.53.0 onward publish to `ghcr.io/google/cadvisor`.
- Add a read-only bind mount for containerd's socket
  (`/run/containerd/containerd.sock`) to the `cadvisor` service, alongside
  its existing `docker.sock` mount — needed for the fixed code path to
  work.
- No change to the Prometheus scrape config, alert rules, or Grafana
  dashboards — same exporter, same metric names, same job name.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — `skip_specs: true` is set in this change's `.openspec.yaml`.
`add-platform-monitoring` (the change that introduced cAdvisor and the
container-health alert rule) is merged but not yet archived, and no
requirement text in `openspec/specs/` mentions cAdvisor or container-level
metrics at all — that intent exists only in `add-platform-monitoring`'s own
not-yet-archived delta specs and design.md. This change restores the
already-stated behavior of a not-yet-archived change; it does not change
what any archived requirement says.

## Impact

- `platform/docker-compose.yml`: `cadvisor` service — image tag bump, one
  new volume mount.
- No Ansible, Terraform, or GitHub Actions workflow changes.
- Deployed the same way as any other `platform/` change (not Ansible's
  responsibility — `iac-platform-services`'s "Platform Stack Deployment Is
  Not Ansible's Responsibility" requirement).
- Regression test: this session's false-positive reproduction (documented
  in project memory) — after the fix, cAdvisor must not false-fire
  `ContainerRestartingOrOOMKilled` on unrelated systemd cgroups, and must
  report real per-container `id` labels (e.g. `/docker/<container-id>`).
