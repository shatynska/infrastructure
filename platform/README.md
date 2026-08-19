# platform

The shared Compose stack for services common to the whole server — a
reverse proxy and a single shared PostgreSQL instance today; monitoring
(Prometheus/Grafana), when added, runs here too. See `iac-platform-services`.

## Boundary

- **One shared PostgreSQL instance, per-application databases.** A new
  application gets a new database inside this instance, not its own
  PostgreSQL container.
- **Every application on the host reuses this stack's reverse proxy and
  database** rather than defining its own instance of either. Per-application
  Compose files live in separate application repositories, not here.
- **Deployed by a mechanism other than Ansible.** What starts, stops, or
  updates this stack is not decided yet (candidates: a CI workflow applying
  it over SSH, a systemd unit paired with a `git pull`, Watchtower, or a
  manual step) — see `openspec/changes/integrate-ansible-host-config/design.md`'s
  Open Questions. Ansible's configuration-management scope stops at the
  container runtime; it never templates this stack's service definitions or
  invokes its lifecycle commands.
- **No dedicated monitoring server.** When Prometheus/Grafana are added,
  they run in this same stack, on this same host, rather than on a second
  server dedicated to observability. Single-host observability risk is
  mitigated with an external dead-man's-switch, not a second server.

## Status

Directory only — no `docker-compose.yml` service content yet. See
`openspec/changes/integrate-ansible-host-config/` for the change that
established this boundary.
