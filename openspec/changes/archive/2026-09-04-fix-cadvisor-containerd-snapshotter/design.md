## Context

See proposal.md - Why. Confirmed on `main-server` this session:
containerd's socket exists at the standard path `/run/containerd/containerd.sock`
(root:root owned, `srw-rw----`, group-readable — verified via a throwaway
container bind-mounting `/run/containerd` read-only).

The `cadvisor` service already bind-mounts `/var/run:/var/run:ro`, and
`/var/run` on this host is a symlink to `/run` (`readlink -f /var/run` →
`/run`). That means containerd's socket is already technically visible
inside the container, just at `/var/run/containerd/containerd.sock` rather
than cAdvisor's default expected path (`/run/containerd/containerd.sock`).
The existing `docker.sock` mount follows the same pattern: it's separately,
explicitly mounted at `/var/run/docker.sock:/var/run/docker.sock:ro` even
though the blanket `/var/run:/var/run:ro` mount already covers it — kept
explicit for clarity about what cAdvisor actually depends on, not because
it's technically required. This change follows that same established
convention for the containerd socket rather than relying on the path
already being covered incidentally.

Also confirmed this session: `gcr.io/cadvisor/cadvisor` (the registry
currently pinned in `platform/docker-compose.yml`) is dead — Google
Container Registry was deprecated in March 2024 and shut down in March
2025. Versions from v0.53.0 onward publish to `ghcr.io/google/cadvisor`
instead. The registry, not just the tag, must change.

## Goals / Non-Goals

**Goals:**
- Get cAdvisor actually reporting real per-container metrics on this host.
- Keep the diff to exactly what's needed: image reference and one new
  mount. No changes to Prometheus, Alertmanager, or Grafana configuration.

**Non-Goals:**
- Re-architecting container-metrics collection (e.g. switching to a
  different exporter). The upstream fix directly addresses the reported
  bug; no need to introduce a new component.
- Migrating the Docker daemon off the containerd-snapshotter storage
  backend. That fights the direction Docker itself is moving, and a daemon
  restart would be more disruptive than this fix.

## Decisions

**Bump to `ghcr.io/google/cadvisor:v0.60.5`** (latest stable as of this
change, confirmed via upstream release history), not just the minimum
fixed version (`v0.54.0`). Rationale: this project pins exact versions for
external images already (`prom/prometheus:v3.7.3`, `traefik:v3.7.10`,
etc.) rather than floating tags, and there's no reason to pin an
intermediate version when the latest stable is already known and
available. One version-specific risk was found and dismissed: v0.54.1 had
a since-superseded regression (`google/cadvisor#3772`, containerd factory
registration failing when the socket isn't reachable) — not relevant to
v0.60.5, and irrelevant to this host anyway since the new mount makes the
socket reachable.

**Add an explicit `/run/containerd/containerd.sock:/run/containerd/containerd.sock:ro`
mount**, matching cAdvisor's default expected containerd endpoint path,
rather than passing an explicit `--containerd=/var/run/containerd/containerd.sock`
flag pointing at the path already incidentally covered by the existing
`/var/run:/var/run:ro` mount. Alternatives considered: relying on the
existing blanket mount plus a flag override — rejected because it's less
obvious to a future reader why the flag points where it does, versus a
mount whose destination matches cAdvisor's own documented default (no flag
needed at all).

## Risks / Trade-offs

- [Risk] Docker API version mismatch: a newer cAdvisor release could
  require a Docker Engine API version this host doesn't have (seen in an
  unrelated Docker Desktop/WSL2 report, `google/cadvisor#3793`). → Mitigation:
  this host runs a native Docker Engine 29.7.2 (not Docker Desktop), which
  supports a current API version; task 2 verifies cAdvisor's Docker factory
  registers successfully after the bump, which would surface this
  immediately if it occurred.
- [Risk] The version jump is large (v0.49.1 → v0.60.5, 11 minor versions),
  so other unrelated behavior could differ. → Mitigation: the Prometheus
  scrape job (`cadvisor:8080`), metric names, and alert rule expressions
  are unaffected by this change — cAdvisor's core metrics format is stable
  across this range; task 2 verifies the scrape target stays `up` and
  metrics keep flowing after the bump.
- [Risk] cAdvisor's raw cgroup factory — a separate mechanism from the
  Docker-factory/layerdb bug this change fixes — could keep tracking
  arbitrary systemd session-scope cgroups as pseudo-containers even after
  the Docker factory starts working correctly, reproducing the original
  false-positive by a different path. → Mitigation: task 3.5 explicitly
  reproduces the original false-positive conditions as a regression test,
  which would catch this regardless of which factory causes it. If it
  still false-fires, the fallback is a `--docker_only=true` flag (or an
  equivalent cgroup filter) on the `cadvisor` service — not applied
  preemptively, since it isn't known to be needed yet.

## Migration Plan

Standard `platform/` deploy (not Ansible's responsibility — deployed via
this repo's existing platform-deploy pipeline, same as any other
`platform/docker-compose.yml` change). No data migration: cAdvisor holds no
persistent state of its own. Rollback is reverting the image tag and
removing the new mount, same mechanism as any other Compose change.
