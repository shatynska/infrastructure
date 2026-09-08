## Why

`.github/dependabot.yml` watches `terraform` and `github-actions`. Nothing watches the eight container images `platform/docker-compose.yml` pins — Traefik, PostgreSQL, Prometheus, Alertmanager, Grafana, node-exporter, postgres-exporter and cAdvisor — so they are refreshed only when a person happens to notice. These are the services the host actually runs: Traefik terminates TLS for every public hostname, and a stale one is a security exposure rather than a cosmetic lag.

The staleness is a **consequence of a trade this repository made deliberately**, and nothing currently pays it back. *Shared-Stack Service Images Are Pinned to an Exact Release* (`openspec/specs/iac-platform-services/spec.md`) forbids a floating tag precisely so that a version change appears as a committed diff the deploy approver sees. That buys review at the cost of currency: a pinned tag never moves on its own, so the same requirement that makes upgrades visible also makes them depend entirely on someone remembering. Dependabot is the half that was missing — it turns "someone remembers" into a pull request that goes through the review the pin exists to enable.

`docs/deferred-work.md` already carries the same shape and *rejects* it: the Molecule platform image digest is left to age on purpose, because a test base image the suite runs against reproducibly is worth more than a current one. That argument does not transfer. Reproducibility is not what a production reverse proxy is for, and the entry itself says so by scoping its trade to "a test-only base image".

The mechanism exists. Dependabot's `docker-compose` ecosystem — separate from `docker`, which reads Dockerfiles this repository does not have — reached general availability on 2025-02-25.

This is entry 31 in `docs/change-queue.md`, and finding 13 in `docs/review-2026-09-08-host-readiness.md`. That entry calls it "a one-stanza change in `.github/dependabot.yml`". It is not, for a reason the entry could not have known: the requirement it lands in enumerates its ecosystems by name, and a test reads that enumeration back.

## What Changes

- **A third Dependabot ecosystem, `docker-compose`, scoped to `/platform`.** The directory is not a preference. Dependabot's Docker Compose file fetcher lists the contents of the configured directory and selects `type == "file"` — it does **not** recurse — and raises `Repo must contain a docker-compose.yaml file.` when that directory holds none. `directory: "/"` would therefore not scan the tree; it would fail, because no Compose file sits at the repository root. `/platform` holds exactly one file matching the fetcher's pattern.

- ***Automated Dependency Updates* stops enumerating two ecosystems and enumerates three.** The requirement's opening sentence names `terraform` and `github-actions` as the set, and `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems` iterates that same pair. Adding a stanza without amending both would leave the specification describing a configuration the repository no longer has.

- **The coverage obligation the `terraform` ecosystem already carries is extended to `docker-compose`, on a stronger footing.** For `terraform` the argument is that the ecosystem offers no discovery mechanism. For `docker-compose` it is the fetcher's non-recursion, read from its source rather than inferred: a second stack added at, say, `platform/monitoring/docker-compose.yml` is not partially covered by the `/platform` entry — it is uncovered, silently, with the existing entry still green.

- **A `.github/tests` assertion enforcing that coverage on both conditions the fetcher applies.** A file's **content** decides that it owes coverage — its top-level `services:` is a mapping whose entries declare an `image:`. Its **name and directory** decide whether it has any: the fetcher selects by filename as well as by directory, so a stack file at `platform/stack.yml` would sit in the configured directory and never be read. Asserting the directory alone would reproduce, inside the check, the silent uncoverage the check exists to prevent. Deciding the population by shape is also what keeps this from becoming a third, differently-drawn exclusion rule over `ansible/roles/` — `docs/deferred-work.md` records an open complaint that there are already two — since `ansible/roles/geerlingguy.docker/tasks/docker-compose.yml` is an Ansible **task list** that Dependabot's own filename pattern matches and a shape test does not.

- **No `ignore` stanzas, including for PostgreSQL major versions.** Reasoning in `design.md`, Decision 3; it turns on *No Store on This Host Holds Data Requiring Backup*, archived on 2026-09-08.

- **A `groups` entry bundling the six monitoring images, with Traefik and PostgreSQL left ungrouped**, its patterns written as Dependabot dependency names (`prom/*`, `grafana/*`, and the two full registry paths) rather than as Compose service names, which Dependabot does not match on and which would leave the group inert. Reasoning in `design.md`, Decision 4; asserted rather than left to inspection, because an inert group fails silently and an over-broad one (`postgres*`) pulls in the database the split exists to keep out.

- **`docs/change-queue.md` entry 31 is deleted**, and `docs/review-2026-09-08-host-readiness.md` finding 13 and reading-order step 4 are updated to say it landed. The queue entry's arithmetic is corrected in passing rather than carried forward: it reads "nine image pins … three exporters, cAdvisor", which counts cAdvisor twice. There are eight. (`README.md`'s "three exporters" is a different count and is not wrong — it treats cAdvisor as one of the three.)

Nothing about the running host changes. This change adds no service, alters no image pin, and converges nothing. What it changes is whether a stale pin produces a pull request.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-safety-hardening`: *Automated Dependency Updates* requires a third package ecosystem, `docker-compose`; states the coverage obligation over Compose files and the fetcher behaviour that gives that obligation its force; and records that the images so covered remain subject to the pinning and human-review obligations `iac-platform-services` already imposes rather than being exempted by automation.

## Impact

- **Configuration**: `.github/dependabot.yml` — one added stanza with a `groups` entry, and an explanatory comment in the form the `terraform` stanza already uses.
- **Specifications**: `openspec/specs/iac-safety-hardening/spec.md`.
- **Tests**: `.github/tests/test_ci_configuration.py`. The change declares a specification delta, so it owes derived tests, and the test author is dispatched with all three rows of `AGENTS.md`'s table rather than with a verdict about which apply. The properties here are static reads of committed files — `.github/dependabot.yml` against the Compose files the tree holds — which is the `.github/tests` row's stated subject. Nothing here needs a network call, a credential, a container runtime or a Terraform binary.
- **Documentation**: `docs/change-queue.md` (entry 31 deleted), `docs/review-2026-09-08-host-readiness.md` (finding 13, reading-order step 4), `README.md` (the CI/CD section explains how `pre-commit` revisions stay fresh but says nothing about how image pins do; one sentence closes that).
- **Pipeline behaviour, deliberately unchanged**: a Dependabot pull request touching only `platform/**` runs the required `validate` job, whose `docker compose config (platform/)` step is gated on that path and whose CI-configuration tests — including the image-pin floor check — are unconditional. Its `terraform plan` step is gated on `terraform/**` and so does not run, which is why such a pull request needs none of the repository secrets Dependabot's restricted token cannot reach. Merging runs `platform-deploy.yml`, whose `deploy` job is gated on the `production` Environment's approver.
- **Not covered, and named rather than implied**: *No Store on This Host Holds Data Requiring Backup* has a scenario reaching a store "a bumped image newly declares". Enabling Dependabot here makes that scenario fire routinely, and no assertion in `.github/tests` can discharge it — detecting a `VOLUME` an upstream image declares requires a registry call, which that suite forbids itself and asserts it forbids. That obligation stays with the human review of each bump, which is where the pinning requirement already puts the half a static check cannot decide.
