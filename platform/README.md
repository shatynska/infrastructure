# platform

The shared Compose stack for services common to the whole server — a
reverse proxy, a single shared PostgreSQL instance, and metrics
collection/alerting/dashboards. See `iac-platform-services`.

## Boundary

- **One shared PostgreSQL instance, per-application databases.** A new
  application gets a new database inside this instance, not its own
  PostgreSQL container.
- **Every application on the host reuses this stack's reverse proxy and
  database** rather than defining its own instance of either. Per-application
  Compose files live in separate application repositories, not here.
- **Deployed by a GitHub Actions workflow, not Ansible.** A PR touching
  `platform/**` is validated via `docker compose config` (no deploy
  credential); merging to `main` runs a credential-less job that posts the
  diff to the run's job summary, then a `production`-Environment-gated job
  that joins the same private Tailscale tailnet the host is a member of
  (`connect-platform-deploy-via-tailscale`) and authenticates as the
  `deploy` account (provisioned by `bootstrap-ansible-host-baseline`) to
  trigger its one fixed deploy script over SSH — reachable only over that
  tailnet, not the public internet, so this pipeline never needed SSH
  opened beyond the operator's own CIDR. See `iac-platform-deploy-pipeline`
  and `.github/workflows/platform-deploy.yml`. Ansible's configuration-
  management scope stops at the container runtime; it never templates this
  stack's service definitions or invokes its lifecycle commands.
- **No dedicated monitoring server.** Prometheus, Alertmanager, and Grafana
  run in this same stack, on this same host, rather than on a second server
  dedicated to observability. Single-host observability risk is mitigated
  with an external dead-man's-switch (see Monitoring and alerting below),
  not a second server.

## Joining the platform network

An application repository's own `docker-compose.yml` reaches Traefik and
Postgres by declaring the `platform_edge` network as external and
attaching its service(s) to it:

```yaml
services:
  app:
    # ...
    networks:
      - platform_edge
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.app.rule=Host(`app.example.com`)"

networks:
  platform_edge:
    external: true
```

Reach the shared Postgres instance at `postgres:5432` on that same
network — see `iac-platform-services`'s "Single Shared PostgreSQL
Instance, Per-Application Databases" requirement. How a new application
actually gets its own database/role inside that instance is not yet
defined (tracked as follow-up work, see
`openspec/changes/deploy-platform-compose-stack/proposal.md`).

## Monitoring and alerting

Prometheus collects metrics from node-exporter (host), cAdvisor (every
container on the host), postgres-exporter (the shared Postgres instance),
and Traefik's own metrics endpoint (per-application HTTP status/error-rate
counts). Alertmanager routes alerts to Slack, plus a permanent Watchdog
alert routed to an external dead-man's-switch heartbeat service. Grafana
provides dashboards. See `openspec/changes/add-platform-monitoring/design.md`
for the full rationale — network placement, why configuration is inline in
`docker-compose.yml`, and the trade-offs accepted along the way.

**Grafana is reachable only over the private Tailscale tailnet** — not
routed through Traefik, not on the public interface. From a device already
on the tailnet, open `http://<tailnet-IP-or-MagicDNS-name>:3000` and sign in
as `admin` with the credential in the `PLATFORM_GRAFANA_ADMIN_PASSWORD`
GitHub Actions secret.

### One-time manual step: postgres-exporter's monitoring role

postgres-exporter connects to the shared Postgres instance as a dedicated,
restricted-privilege role — never the instance's superuser credential. This
role is **not** created by any automation in this repository (deliberately
— see design.md's "That role is created by a one-time manual operator step,
not by this change's automation"): run this once, by hand, against the
running `postgres` container, using a password matching whatever is stored
in the `PLATFORM_POSTGRES_EXPORTER_PASSWORD` GitHub Actions secret:

```sql
CREATE ROLE pgexporter WITH LOGIN PASSWORD '<value of PLATFORM_POSTGRES_EXPORTER_PASSWORD>';
GRANT pg_monitor TO pgexporter;
```

`pg_monitor` is Postgres's own built-in predefined role: read-only access to
the statistics views postgres-exporter's standard collectors query, no
table data access, no superuser. If this role is ever missing or its
password out of sync (e.g. after rebuilding the shared instance), the
`MetricsTargetDown` alert fires for the `postgres-exporter` job rather than
that metrics gap going unnoticed.

### One-time manual step: dead-man's-switch registration

Register this host with a third-party heartbeat/dead-man's-switch service
(e.g. Healthchecks.io) and put the ping URL it gives you in the
`PLATFORM_DEADMANSWITCH_URL` GitHub Actions secret. Configure that service's
expected check-in interval to comfortably exceed Alertmanager's Watchdog
`repeat_interval` (2 minutes, per `platform/docker-compose.yml`'s
`alertmanager_config` -- lowered from an original 5 minutes after
`fix-deadmansswitch-repeat-interval` found that value, equal to the
inherited `group_interval`, caused real delivery to silently halve to
every ~10 minutes instead), so a single delayed gossip round doesn't
produce a false page. This is the actual implementation of the mitigation named in
"No dedicated monitoring server" above — if the host, Alertmanager, or the
whole platform stack goes down, this is what notices.

## Status

`docker-compose.yml` defines Traefik (ACME-issued TLS, Docker-label
routing), a single shared PostgreSQL instance, and the monitoring/alerting
stack described above, deployed by `.github/workflows/platform-deploy.yml`.
See `openspec/changes/deploy-platform-compose-stack/` for the change that
built the original stack, `openspec/changes/integrate-ansible-host-config/`
for the change that established the boundary above, and
`openspec/changes/add-platform-monitoring/` for the monitoring/alerting
stack.
