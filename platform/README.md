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
- **No dedicated monitoring server.** When Prometheus/Grafana are added,
  they run in this same stack, on this same host, rather than on a second
  server dedicated to observability. Single-host observability risk is
  mitigated with an external dead-man's-switch, not a second server.

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

## Status

`docker-compose.yml` defines Traefik (ACME-issued TLS, Docker-label
routing) and a single shared PostgreSQL instance, deployed by
`.github/workflows/platform-deploy.yml`. See
`openspec/changes/deploy-platform-compose-stack/` for the change that
built this, and `openspec/changes/integrate-ansible-host-config/` for the
change that established the boundary above.
