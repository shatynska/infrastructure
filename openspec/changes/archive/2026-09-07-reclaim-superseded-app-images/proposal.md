## Why

Nothing on the host ever removes an application image, and the disk is filling with images no container will run again.

`/usr/local/bin/app-deploy` is four lines: `cd /opt/<app>`, `docker compose pull`, `docker compose up -d --wait`. Every merge to an application's trunk pushes a fresh SHA-tagged image, `app-deploy` pulls it, and the image it replaced stays on disk forever. Measured on `main-server` on 2026-09-07:

```
TYPE      TOTAL   SIZE      RECLAIMABLE
Images    219     46.43GB   42.88GB (92%)
```

219 images, of which **190 are `ghcr.io/shatynska/commerce-ops`** — one application's superseded tags. Against that, everything the host is actually *for* comes to 118 MB of volumes and 63 MB of containers. The root filesystem reads 66% full (47 GB of 75 GB) and essentially all of it is garbage.

This is a shared-fate problem, not one application's problem. `platform`'s Postgres, Prometheus, Grafana and Traefik sit on the same root filesystem as `/var/lib/docker`, so the disk filling does not degrade one application — it stops every container on the host at once, including the monitoring stack that would otherwise be how anyone found out.

Nothing about this is self-limiting. The accumulation rate is one image per merge per application, and the only reason the host is still running is that 80 GB happened to be more than five months of it.

## What Changes

**`app-deploy` reclaims the images its own previous deploys left behind**, as a step that runs after the new containers are healthy.

The reclamation is scoped to the application's own image namespace — `ghcr.io/<any owner>/<app>` — and removes every tag there that the application's current Compose file does not reference. It never considers an image outside that namespace, so a base image several applications share (`postgres:16`, `traefik:v3.7.10`) is not a candidate for removal by any of them.

Placing it in `app-deploy` rather than in each application's deploy workflow means every application on the host inherits it, present and future, and no application repository has to know how the host manages disk.

## Impact

- **Spec**: `iac-host-configuration` gains one ADDED requirement. The existing "Restricted Deploy Account Supports Per-Application Forced-Command Deploys" requirement is unchanged: this adds a step to what `app-deploy` does, and changes nothing about who may invoke it, with what argument, or over which key.
- **Code**: `ansible/roles/deploy_user/tasks/main.yml` — the `app-deploy` script content — and that role's `README.md`, which describes the script's body and would otherwise stop being true. No new file, no new role, no new variable.
- **Tests**: `ansible/roles/deploy_user/molecule/default/` — the scenario already installs a real Docker Engine and drives a real deploy through `deploy-receive`, so reclamation is exercisable there directly rather than asserted statically.
- **Host**: steady state becomes one image per application rather than one per merge. The *accumulated* backlog — ~190 images and the bulk of the 42.88 GB for `commerce-ops` — is cleared once by hand as a rollout step, deliberately not through the deploy path: reclamation is bounded in outcome but that much unlinking inside a production deploy window, on a single-disk host also carrying Postgres and the monitoring stack, is a cost the mechanism does not need to incur to prove itself. See design.md, "The one-time backlog is cleared by hand".
- **Rollback**: rolling back an application re-pulls its image from GHCR rather than finding it already on disk, which costs a pull, not a capability. Checked for the namespace the hand clearance empties: `ghcr.io/shatynska/commerce-ops` is a public package and three tags taken from the host's own image list each resolve anonymously at GHCR, so pre-transfer builds stay recoverable even where no GHCR credential is configured.

## Non-goals

- **Fully dangling images and layers.** They carry no repository name and so fall outside every application's namespace by construction.
- **Untagged images that *are* in an application's namespace.** An image referenced by digest keeps its repository name but shows no tag, so it can never appear in a tag-shaped reference set. It is deliberately left alone rather than treated as unreferenced — see design.md.
- **Images of applications that no longer deploy.** Reclamation is driven by a deploy; an application that never deploys again is never revisited.

All three are the job of a periodic host-level prune, which is a different mechanism on a different trigger (a timer, not a deploy) and is recorded as entry 10 in `docs/change-queue.md` rather than folded in here.
