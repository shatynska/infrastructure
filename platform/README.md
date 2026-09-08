# platform

The shared Compose stack for services common to the whole server — a
reverse proxy, a single shared PostgreSQL instance, and metrics
collection/alerting/dashboards. See `iac-platform-services`.

## Boundary

- **One shared PostgreSQL instance, for non-durable data only.** An
  application that keeps technical or temporary relational records on this
  host gets a database inside this instance rather than its own PostgreSQL
  container. Durable data — data whose loss would not be tolerable — never
  goes in this instance under any circumstances. It belongs off this host
  altogether, save for one narrow exception, elsewhere on the host, that
  nothing has yet met; see "The shared database" below.
- **A new persistent store has to say why it needs no backup.** Any volume —
  named or anonymous, and including one an *image* declares rather than this
  stack definition — or any writable host bind mount, whether added here or by
  an application on this host, means naming which of the reasons in *No Store
  on This Host Holds Data Requiring Backup*
  (`openspec/specs/iac-safety-hardening/spec.md`) it satisfies, in the change
  that adds it — or, for a store added by an application in its own
  repository, in the change here that records it, since nothing else would
  leave a record on this side. The image half is not hypothetical: Alertmanager's store exists
  only because `prom/alertmanager` declares one, and nothing in this file
  mentions it. A store satisfying no reason owes a logical backup written
  outside this host and a rehearsed, checked restore before it first holds
  data.
- **Every application on the host reuses this stack's reverse proxy** rather
  than defining its own, and reuses this stack's database for any non-durable
  relational data it keeps here. Per-application Compose files live in
  separate application repositories, not here.
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
Instance, Per-Application Databases" requirement.

### The shared database

**What it is for.** Technical or temporary records **in a relational
database**, whose loss is tolerable to the application that wrote them: a job
table, bookkeeping an application would rather not put in its system of
record. An application that keeps data of that kind on this host gets a database
and a role inside this instance rather than running a PostgreSQL container
of its own.

A non-relational store — a Redis cache, a queue file, an uploads directory —
is outside this instance and outside that requirement. It is governed
instead by *No Store on This Host Holds Data Requiring Backup*
(`openspec/specs/iac-safety-hardening/spec.md`), like any other store on
this host.

**Nothing in it is backed up, and that is a decision rather than an
omission.** It is what the scoping above buys: because the instance holds
only data whose loss its writer can tolerate, the host needs no backup
mechanism for it, and *No Store on This Host Holds Data Requiring Backup*
(`openspec/specs/iac-safety-hardening/spec.md`) records that classification
along with what becomes owed if it ever stops being true. Do not read the
absence of a dump as a gap someone forgot to close — read it as the reason
durable data is not welcome here.

**Durable data goes to an external managed service that owns its own
backups.** Never into this instance: that prohibition is absolute, and no
backup lifts it, because holding only non-durable data is exactly what makes
this instance classifiable as needing no backup. Not into a PostgreSQL
container of the application's own on this host either — unless the logical
backup written off the host and the rehearsed, checked restore that
*No Store on This Host Holds Data Requiring Backup*
(`openspec/specs/iac-safety-hardening/spec.md`) demands are both in place
before the data lands. That is a bar, not a footnote, and no application has
cleared it.

**Getting a database inside the instance** is a manual step today —
`docs/bootstrap-a-new-host.md` carries the `CREATE ROLE` / `CREATE DATABASE`
recipe. Automating it, and delivering the credential the way an
application's deploy key is delivered, is deliberately deferred until an
application actually needs one; see `docs/deferred-work.md`.

## Monitoring and alerting

Prometheus collects metrics from node-exporter (host), cAdvisor (every
container on the host), postgres-exporter (the shared Postgres instance),
and Traefik's own metrics endpoint (per-application HTTP status/error-rate
counts). Alertmanager routes alerts to Slack, plus a permanent Watchdog
alert routed to an external dead-man's-switch heartbeat service. Grafana
provides dashboards. See `add-platform-monitoring`'s design.md
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
See `deploy-platform-compose-stack` for the change that built the original
stack, `integrate-ansible-host-config` for the change that established the
boundary above, and `add-platform-monitoring` for the monitoring/alerting
stack.

Every service in this stack defines a real Docker `healthcheck:` reflecting
its own readiness, not just that its process is running -- this is what
lets `docker compose up -d --wait` (in `app-deploy` on the host) actually
fail the deploy job when a service comes up broken, instead of reporting
false success. When adding a new service here, give it a real healthcheck
too (see `add-platform-service-healthchecks` for why this
matters and what it does and doesn't catch).
