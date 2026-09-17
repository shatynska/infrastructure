## Why

`reclaim-superseded-app-images` closed the accumulation this host was dying of — one image per merge per application, 190 images and 42.88 GB by the time it shipped — and it closed it at the deploy. What it could not reach, by its own construction, is everything that is not one application's own superseded tag. Measured on `main-server` on 2026-09-07, after that change's rollout:

```
TYPE      TOTAL   SIZE      RECLAIMABLE
Images    29      6.774GB   3.221GB (47%)
```

Three classes make up that 47%, and no mechanism on this host reaches any of them:

- **Ten fully dangling images**, ~3.2 GB and the bulk of the figure. Verified on the host: `RepoTags=[]`, `RepoDigests=[]`, and no stopped container to hold them. They carry no repository name, so they fall outside every application's namespace by construction.
- **Superseded platform base images** — `traefik:v3.2` against a live `v3.7.10`, `gcr.io/cadvisor/cadvisor:v0.49.1` against a live `ghcr.io/google/cadvisor:v0.60.5`, `postgres:16` against a live `postgres:16.15`. A base image is shared, so *one* application's reference set is not authority over it, which is exactly why per-deploy reclamation refuses to consider it.
- **Test and one-off residue** — `alpine:3.20`, `alpine:3.21`, `alpine:latest`, `curlimages/curl`, `docker:27-cli`, `polinux/stress`, `traefik/whoami`. Nothing on this host has ever removed one.

This is not the emergency the previous change was. The remaining ~1.4 GB of tagged residue is static and the root filesystem reads 15% full. What is not static is the first class: dangling images arise from moving tags and from pull churn, nothing reclaims them, and the only current backstop is `HostDiskPressure`, which fires at 90% full.

## What Changes

**A new `image_prune` role installs a systemd timer that removes every local image no enumerated application and no container still wants.**

The keep set is the **union** across every application in `deploy_apps` of the images that application's Compose file references — rendered across every profile the file declares, not only the active ones — unioned with the image of every container on the host. A host-level timer can compute that union; a single deploy cannot, and that difference is what lets this change reach a shared base image that `app-deploy` must leave alone.

References are resolved to **image IDs** before comparison, so a digest pin, a moving tag and a multiply-tagged image are each compared as the image they are rather than as the string that names them. An image outside the keep set is removed by each of its tags where it has tags, and by ID where it has none, with each tag re-checked at removal time to confirm it still names the image it was selected as.

Three of `app-deploy`'s reclamation constraints are **carried over unchanged**: removal is never forced, an unresolvable reference set abandons the run, and an empty one removes nothing. Two of its *scope* rules are **deliberately reversed**, on evidence the design records — the namespace restriction, because the union across applications is the authority a single reference set was not, and the untagged-image exclusion, because an ID-shaped keep set resolves a digest pin on its merits. In both cases the reasoning behind the original rule is honoured rather than discarded: the absence of a tag is still not treated as evidence that nothing references an image.

One constraint is carried over with its outcome inverted. `app-deploy` abandons a reclamation without failing, because a maintenance step must never fail a deploy that already succeeded; this unit has no caller to damage and abandons by failing, so the host records the fault.

## Impact

- **Spec**: `iac-host-configuration` gains one ADDED requirement. The existing "Superseded Application Images Are Reclaimed at Deploy Time" is unchanged and is not superseded: it stays the primary mechanism at the rate that matters, and this becomes the safety net queue entry 10 anticipated.
- **Code**: a new `ansible/roles/image_prune/` (tasks, defaults, meta, README, `molecule/default` and `molecule/abandon-paths` scenarios), and one role entry in `ansible/playbooks/host-baseline.yml`. No change to `deploy_user`, `app-deploy`, or `platform/`.
- **Inputs**: the role consumes `deploy_apps` — already set in `ansible/inventory/group_vars/prod.yml` and already the version-controlled enumeration of deployable applications — and asserts its presence by name per "A Role's Absent Required Input Is Reported by Name". No new variable, no new secret, nothing to render in `deploy.yml`. Ansible writes the list to a data file the script reads, so the on-host copy is refreshed by a converge — the same way the `sudoers` rules generated from that list already are.
- **Tests**: the behaviour is asserted by two new Molecule scenarios — `default` for the keep-set and removal cases, and `abandon-paths` for the three branches that need a host `default`'s own fixtures put out of reach. Both `molecule.yml` files must satisfy `iac-cicd-pipeline`'s existing discovery-based checks, agreeing on a digest with each other as well as with their siblings. The digest-pin fixture needs a `registry:2` container; it is digest-pinned and pre-seeded into the instance, so the suite keeps the offline property that spec describes it as having.
- **Host**: on the measured state, the first run removes 10 dangling images, `traefik:v3.2`, `gcr.io/cadvisor/cadvisor:v0.49.1`, `postgres:16`, three `alpine` tags, `curlimages/curl`, `docker:27-cli`, `polinux/stress` and `traefik/whoami`, and keeps every image any container holds and every image `platform`'s and `commerce-ops`'s Compose files reference.
- **Rollback**: every image this removes is pullable again — the platform pins come from public upstream registries, and `ghcr.io/*/commerce-ops` is a public package (established by the previous change, 2026-09-07). An over-removal costs a pull, not a capability.

## Non-goals

- **A retention window.** `docker image prune --filter until=<age>` filters on an image's **Created** timestamp, which for a pulled image is its upstream build date and not when this host pulled or last used it. Verified on the host: the *running* `prom/alertmanager:v0.28.1` was created 2025-03-07, and the running `postgres:16-alpine` on 2026-08-13. A 168h window excludes essentially nothing, so it is not a safety property and this change does not pretend it is one. See design.md.
- **`docker image prune -af`**, which queue entry 10 and the previous change's Alternatives section both name. Rejected on the same finding: with the window decorative, `-af` reduces to "remove every image no container currently holds", which loses the image of any service that is defined and never started. Decided against by the operator on 2026-09-07 in favour of the union reference set.
- **An alertable signal that the prune is still working.** The run reports on every exit path and a failed run leaves a failed systemd unit, but neither is scraped. Closing that needs node-exporter's textfile collector, which is a `platform/` change; recorded in `docs/change-queue.md` rather than folded in.
- **Reclaiming the disk of a retired *application*'s data or volumes.** Only images are in scope. Removing an application from `deploy_apps` does make its images reclaimable here, which is entry 10's third target.
