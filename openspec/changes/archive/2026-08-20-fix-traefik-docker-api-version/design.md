## Context

See proposal.md - Why. The host runs Docker Engine 29.7.2, whose daemon enforces a minimum API version of 1.40. `platform/docker-compose.yml` pins `traefik:v3.2`, whose Docker provider requests a hardcoded, non-negotiated API version of 1.24 — below that floor — so every poll of the Docker socket is rejected and Traefik never builds a routing table.

Upstream (traefik/traefik issues #12253, #12420; official v3.6 migration notes) confirms Traefik's Docker provider gained automatic API version negotiation starting `v3.6.16`, carried forward through the `v3.7` line. `v3.2` predates that fix entirely — no flag or environment variable on `v3.2` avoids the problem, since the hardcoded request happens before any negotiation logic exists.

## Goals / Non-Goals

**Goals:**
- Restore Traefik's Docker provider to a working state so it discovers and routes labeled containers, matching what `iac-platform-services`'s existing requirements already describe.
- Keep the fix to a single, exact version-pin bump, consistent with this repo's "any external image/role is pinned to an exact version" convention.

**Non-Goals:**
- Re-evaluating or changing any other part of the Traefik configuration (entrypoints, ACME resolver, Docker provider flags) — none of it is implicated in this defect.
- Introducing `DOCKER_API_VERSION` as a static environment-variable override. That would work today but is a workaround, not a fix: it re-hardcodes a version number that will need bumping again the next time Docker raises its API floor, whereas upgrading to a Traefik release with real auto-negotiation removes the failure mode itself.

## Decisions

**Bump to `traefik:v3.7.10`, not `v3.7.11` or a `v3.6.x` tag.**
- `v3.7.10` (released 2026-07-31) already carries the Docker API auto-negotiation fix (present since `v3.6.16`), so it resolves the defect.
- `v3.7.11` (released 2026-08-19, the day before this investigation) is the newest patch but has had essentially no field time before going into this production stack; `v3.7.10` gives the same fix with three weeks of real-world soak. Decided with the user rather than guessed, given this is a production version pin.
- Checked the v3.6/v3.7 migration notes against this stack's actual usage: the only deprecations found (`traefik.docker.network`/`traefik.docker.lbswarm` labels in v3.2.2; ACME `dnsChallenge` delay/propagation option renames in v3.3) touch features this stack doesn't use (no Swarm labels, no DNS-01 challenge — this stack uses `tlschallenge`). No other breaking change applies to the Docker provider's `exposedbydefault`/`network` flags or the `websecure`/`web` entrypoints this stack relies on.

## Risks / Trade-offs

- [A five-minor-version jump (v3.2 → v3.7) could carry unreviewed behavior changes beyond the Docker provider] → Mitigated by the migration-notes check above finding no applicable breaking change, and by the PR-time `docker compose config` validation plus the diff-then-approval gate in `platform-deploy.yml`, which puts the exact rendered diff in front of a human before it reaches production.
- [Docker could raise its minimum API floor again in a future Engine release] → Out of scope for this change; auto-negotiation (the property this bump restores) is the correct standing defense against that, as opposed to re-pinning a static API version by hand each time.
- [Rollback (reverting to v3.2 after v3.7 has run and written to the ACME volume) assumes `acme.json`'s on-disk format is unchanged across the jump; this was not separately checked — the migration-notes review above only covered label/flag deprecations, not ACME storage format] → If rollback is ever invoked, verify `acme.json` loads cleanly under `v3.2` before relying on it, or fall back to deleting the file and letting Traefik re-request certificates (accepting a brief TLS gap and consuming a Let's Encrypt rate-limit slot).

## Migration Plan

1. Change `image: traefik:v3.2` to `image: traefik:v3.7.10` in `platform/docker-compose.yml`.
2. Open a PR — `pr-validation.yml` runs `docker compose config` against it (no deploy credential).
3. On merge to `main`, `platform-deploy.yml`'s `diff` job posts the exact diff to the run's job summary; the gated `deploy` job (production Environment approval) applies it via the existing fixed `platform-compose-deploy` wrapper (`docker compose pull && docker compose up -d --wait`).
4. Verify post-deploy: `docker logs platform-traefik-1` shows no further `Provider error` entries, and a labeled test container (e.g. the throwaway `whoami` from the original smoke test, redeployed) resolves through `https://test.shatynska.com` with a real Let's Encrypt certificate instead of Traefik's default self-signed one.
5. Rollback, if needed: revert the image tag to `v3.2` in a follow-up PR through the same gated pipeline — Traefik itself is stateless aside from the ACME account/certs volume, which is untouched by this change.
