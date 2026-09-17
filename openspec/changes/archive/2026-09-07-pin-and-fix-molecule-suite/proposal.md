## Why

The Molecule suite is this repository's largest test asset, and since `close-ci-verification-gaps` it runs in CI. Its result is not yet trustworthy, for two independent reasons — and those two are exactly the blockers `docs/change-queue.md` entry 4 names against promoting it to a required status check.

**It runs against a moving target.** All eight scenarios under `ansible/roles/*/molecule/*/molecule.yml` declare `image: geerlingguy/docker-ubuntu2204-ansible:latest`. `AGENTS.md` requires that "any external role or collection used for any purpose is pinned to an exact version", and `iac-cicd-pipeline` already requires the Molecule run to install from exact pinned manifests and to "NOT resolve any dependency version freshly at run time" — but the container every scenario executes inside is resolved freshly on each run and escapes both. Upstream re-pushed that tag on 2026-09-06. "It passed locally" and "it passed in CI" have never been claims about the same image.

**One scenario fails deterministically on a defect in its own assertion.** `ansible/roles/platform_data_volume/molecule/default/verify.yml:194` aborts with `object of type 'dict' has no attribute 'pw_name'` — on PR #57 and again on the post-merge dispatch on `main`, same failure both times. Until it is fixed, `iac-host-configuration`'s subdirectory ownership requirement is unverified, and the suite cannot be green often enough for "consecutive green runs" to mean anything.

## What Changes

**Every scenario's platform image is pinned by digest.** The repository publishes exactly one tag — `latest`, and nothing else (Docker Hub tag count is 1) — so there is no version tag to pin to and a digest is the only exact form available. All eight scenarios move to `geerlingguy/docker-ubuntu2204-ansible@sha256:0172e3b5…`, the manifest-list digest, written without the tag — see `design.md` decision 1, which was made the other way and reversed on evidence: keeping `:latest` alongside the digest makes `community.docker` build a lookup that cannot match the local image, so every `create` pulls and every machine with a `credsStore` fails. That makes the *reference* identical and immutable on every machine; each architecture still resolves to its own image beneath the list, which is what lets an amd64 runner and an arm64 developer machine both run the suite at all. What the pin removes is the mutability, not the architecture split.

**Every scenario also gains `pre_build_image: true`, and this is the larger change.** Discovered during implementation, not planned: the Docker driver reuses `image:` as the tag of an image it builds locally, so a digest there makes `create` fail outright. `pre_build_image: true` skips that build and runs the pinned image directly, which is what makes the digest usable at all.

Skipping the build removes the driver's default `Dockerfile.j2` layer — which no scenario had overridden, and which ran `apt-get update && apt-get install -y python3 sudo bash ca-certificates iproute2 python3-apt aptitude rsync` inside every container on every `molecule create`. So the suite was never reproducible, and the image pin alone would not have made it so: each run installed whatever those eight packages resolved to that day. It now reaches no package archive during `create`, and what is pinned is the whole container rather than only its base. Of that package list only `aptitude` and `rsync` are absent from the pinned image, and nothing in this repository uses either — see `design.md` decision 2a for how that was established.

**The `platform_data_volume` verify assertion is made safe, without being weakened.** The line reads:

```yaml
- item.stat.pw_name == item.item.owner or item.stat.uid | string == item.item.owner
```

This change's own investigation corrects the cause recorded in `docs/change-queue.md` entry 8. That entry attributes the failure to uid `65534` not resolving inside the container; it does resolve, to `nobody`. The failing entry is the *other* fixture — `grafana`, `472/472` — for which the image has no `passwd` or `group` record at all, so `stat` returns no `pw_name` key and Jinja raises on the left operand before the `or` can reach the uid comparison the author intended as the fallback. Verified directly against the pinned image: `getent passwd 65534` → `nobody`, `getent passwd 472` → nothing.

The declared owners are numeric strings in both the scenario fixture and `ansible/inventory/group_vars/prod.yml` (`"65534"`, `"472"`), so the name comparison could never have been the branch that passed. The uid comparison was always the real check; the fix guards the name access so it is actually reached. Nothing asserted is relaxed.

**The pinning obligation becomes machine-checked.** New assertions in `.github/tests/test_ci_configuration.py` read every scenario this repository authors under `ansible/roles/*/molecule/*/` and fail on a platform image carrying no digest, or on two scenarios naming the same image repository at different digests — so a scenario added later can neither reintroduce a floating tag nor be left behind by a partial refresh. This is a static read of committed YAML, consistent with that suite's existing constraints (no container runtime, no network-capable import).

**"This repository authors" is a real boundary, not a turn of phrase.** `ansible/requirements.yml`'s pinned `geerlingguy.docker` installs into `ansible/roles/geerlingguy.docker/` — beside this project's own roles, and gitignored — and it ships a scenario of its own, pinned to `geerlingguy/docker-${MOLECULE_DISTRO:-rockylinux9}-ansible:latest`. A check globbing `ansible/roles/*/molecule/*/molecule.yml` therefore sees nine files on a provisioned developer machine and eight in CI, and would demand this repository pin a file it does not own, cannot keep edited, and does not commit. The check excludes role directories named in `ansible/requirements.yml`'s `roles:` list, and only those.

**Not in scope: promoting the workflow to a required check.** That is `docs/change-queue.md` entry 4, it needs consecutive green runs as evidence, and its first step is removing `ansible-verify.yml`'s workflow-level `paths:` filter — a different concern from making the suite's result mean something. This change clears its two blockers and leaves the entry standing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-cicd-pipeline` — **one modified requirement**: *Ansible Configuration Is Verified in Continuous Integration* currently binds its "exact pinned manifests, nothing resolved freshly at run time" obligation to the Python and Galaxy toolchains only. It is extended to cover the container image each scenario runs inside, which is as much a resolved-at-run-time dependency as either — and the one that determines what the toolchain executes against. The extension states the obligation's boundary (scenarios this repository authors, not ones installed from a pinned manifest) and requires that scenarios sharing an image repository share its digest.

## Impact

- `ansible/roles/{deploy_user,docker,hardening,ops_user,platform_data_volume}/molecule/*/molecule.yml` — eight files, one `image:` line each.
- `ansible/roles/platform_data_volume/molecule/default/verify.yml` — the guarded assertion. A test file, edited because it is itself defective; no role code changes.
- `.github/tests/test_ci_configuration.py` — the derived assertions over the scenario image pins, and the manifest-derived exclusion that bounds them.
- `test-plan.md` beside this proposal — the independent test author's manifest: which scenario each assertion derives from, what was verified out-of-band, and the two assertions marked DERIVED rather than SPECIFIED. Not an OpenSpec-schema artifact, so it does not travel with the four a reviewer or implementing session is dispatched with, and has to be opened deliberately.
- `AGENTS.md` — the Testing table's "Subject" column, widened so a future test author dispatched with it can tell that a static assertion over a `molecule.yml` belongs in `.github/tests/`. Without this the table names two subjects, neither of which covers the assertion this change adds, and a test author would correctly report the gap rather than place the file.
- `README.md` — the Molecule section gains a line on how the pin is refreshed, since nothing does it automatically.
- `docs/deferred-work.md` — a digest pinned by hand has no update mechanism: Dependabot's `docker` ecosystem does not scan `molecule.yml`, and adding a custom refresh workflow is out of proportion to a test-only image. Recorded as deliberately not done, with what would make it worth revisiting.
- `docs/change-queue.md` — entries 5 and 8 are deleted when this change is archived; entry 4's blocker list is reduced to evidence and the `paths:` filter.
- No production infrastructure, no Compose stack, no Ansible role behaviour, and no credential or `environment:` declaration changes. The suite still runs offline against local containers.
