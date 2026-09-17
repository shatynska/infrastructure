## Why

Traefik's Docker provider has been failing continuously since the platform stack was deployed — confirmed from `platform-traefik-1`'s very first second of uptime — with `Error response from daemon: client version 1.24 is too old. Minimum supported API version is 1.40`. This means Traefik currently discovers zero containers via Docker labels: it cannot route to any application, for any domain, at all. The `iac-platform-services` requirement that a labeled application container gets routed (`Shared Docker Network for Application Reuse`) has never actually been satisfiable in production. This was surfaced by manually smoke-testing domain routing with a throwaway `whoami` container, but is a pre-existing defect independent of that test.

## What Changes

- Bump the pinned Traefik image tag in `platform/docker-compose.yml` from `v3.2` to `v3.7.10`, which includes Traefik's Docker API auto-negotiation fix (landed upstream starting `v3.6.16`) needed to work with Docker Engine 29's raised API floor (minimum `1.40`). See design.md's Decisions for why `v3.7.10` specifically, not the newer `v3.7.11`.
- No other flags, labels, or structure in `platform/docker-compose.yml` change — this is a version-pin bump only.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
(none — `iac-platform-services`'s existing requirements already describe the correct behavior; this restores compliance with them rather than changing what they require. See `.openspec.yaml`'s `skip_specs: true`.)

## Impact

- `platform/docker-compose.yml`: the `traefik` service's `image` tag.
- Deployment: ships only through the existing gated `platform-deploy.yml` pipeline (PR diff review → production-Environment approval → deploy over Tailscale) — no manual host changes, consistent with this repo's production-change rule.
- No impact to Postgres, ACME configuration, entrypoints, or the `platform_edge` network definition.
