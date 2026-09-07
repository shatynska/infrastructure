## 1. Implementation

- [ ] 1.1 Wrap the script body in `{% raw %}…{% endraw %}`. It lives in a
  `copy:` task's `content:`, which Ansible renders as Jinja, and
  `docker images --format '{{.Repository}}:{{.Tag}}'` is Go template syntax that
  Jinja will try to evaluate. No `--format` and no `{% raw %}` appears anywhere
  under `ansible/` today, so there is no precedent to copy. Fails loudly at
  converge, not silently — but budget for it.
- [ ] 1.2 Extend the `app-deploy` script content in
  `ansible/roles/deploy_user/tasks/main.yml` with a reclamation step that runs
  after `docker compose up -d --wait`: take the reference set from
  `docker compose config --images`, enumerate local images matching
  `ghcr.io/<any owner>/<app>:`, and remove those not in the reference set.
- [ ] 1.3 Compute the reference set **first** and abandon the run where it is
  empty or could not be computed. An empty pattern file makes `grep -vxF -f`
  match every line, so the degraded path must be an explicit early return, not
  a consequence of the filter. Match whole lines (`-x`): `-F` alone matches
  substrings, so a reference entry that is a prefix of another local tag would
  protect the wrong image. Normalise both sides to a tagged form first — the
  local listing always emits a tag, a Compose reference without one may not.
- [ ] 1.4 Remove with plain `docker image rm`. Do not pass `-f`, and do not
  substitute `docker image prune -a`: a refused removal is the expected outcome
  for the live tag on every run, and that refusal is the design's only backstop
  against a wrong reference set.
- [ ] 1.5 Exclude untagged members of the namespace (`<none>` tags), which are
  digest-referenced images that cannot appear in a tag-shaped reference set.
- [ ] 1.6 Isolate the step's failure as a single unit — a function invoked as
  `reclaim || true`, or one `{ …; } || true` group. A trailing `|| true` on the
  last of several lines protects only that line, leaving a script under
  `set -euo pipefail` able to fail a deploy that already succeeded.
- [ ] 1.7 Do not invoke the removal with an empty candidate list: pass `-r`
  where `xargs` is used, or guard the loop. Without it `docker image rm` runs
  with no arguments on every deploy that has nothing to reclaim, producing a
  usage error that `|| true` then hides — the recurring noise design.md warns
  invites someone to "make it stop".
- [ ] 1.8 Bound the whole reclamation step with `timeout`, enumeration included
  — `docker images` and `docker compose config` are calls to the same daemon the
  removals are, so a bound around only the removals leaves the wedged-daemon case
  reachable. Pick a value generous against a legitimate steady-state run (order
  of a minute, not of a second) and record it in the script comment. Expiry is a
  reclamation failure like any other: swallowed, deploy still successful.
- [ ] 1.9 Report on every exit path, split by path because the paths cannot
  know the same things. The bounded region prints `considered N, removed M` when
  it completes, and prints its reason when it aborts on an empty or
  undeterminable reference set. The **wrapper** prints the timeout line from
  `timeout`'s exit status (124), outside the bounded region — only that line
  must live outside, since a report printed inside the region cannot survive it
  being killed, and that path reports a reason rather than counts because no
  count survives the kill either.

  Emit the completed-run line *unconditionally*. A `grep` over the namespace
  that matches nothing exits 1, which under `set -euo pipefail` can abandon the
  group before the report runs — and that is the **ordinary** path for
  `platform`, whose namespace is empty by design, so the delta's "whether it
  removed images or found nothing to remove" clause would go unmet on the one
  application that always takes it. Compute the counts into variables with the
  enumeration tolerated failing, then report.

  This is the step's only per-run signal: `|| true` swallows every other one,
  and `deploy-receive` carries this session's output back to the calling
  workflow. A report reachable only on the ordinary path reports only when
  nothing is wrong, which inverts what it is for.

- [ ] 1.10 Update `ansible/roles/deploy_user/README.md`, whose "The unified
  shape" section states that `app-deploy` "runs `docker compose pull && docker
  compose up -d --wait` in that directory" — true until this change and
  incomplete after it. Extend the onboarding paragraph in that same section too:
  the delta makes name equality between an application's deploy name and the
  second segment of its image repository a normative onboarding obligation, and
  a comment inside `tasks/main.yml` is not where anyone onboarding an
  application looks. Getting it wrong reclaims nothing, silently.

  Update the scenario's own comments in the same pass, for the same reason.
  `molecule.yml`'s header asserts that "an empty `services: {}` Compose file
  keeps `docker compose pull && up -d --wait` a real, fast, no-registry-needed
  success", and `verify.yml`'s `fail_msg` at 84-90 repeats it. Both are already
  loose — the fixture declares a `noop` service on `alpine:3.19` — and this
  change falsifies them further by making the fixtures locally-built
  `ghcr.io/…` images. Sweeping the pre-existing inaccuracy is optional;
  leaving behind the part this change makes untrue is not. This repository already carries a queued entry
  (`docs/change-queue.md` 9) about documentation that stopped being true; not
  adding to it is cheaper than sweeping it later.
- [ ] 1.11 Comment the script body with why the namespace is scoped to the
  application's own repository, why the owner segment is a wildcard, why
  removal is never forced, and that the application's deploy name must equal
  the second segment of its image repository for any of it to match — the
  decisions a later reader is most likely to "simplify" into a bug.

## 2. Tests

- [ ] 2.1 Extend `ansible/roles/deploy_user/molecule/default/` to deploy an
  application twice at two different tags of one namespaced repository, and
  assert the superseded tag is gone and the live one remains. Assert the
  reported counts of that second run too — otherwise nothing anywhere checks the
  report on the path it is most often read on, and 2.9 only establishes that the
  early-exit reports differ from it. The two tags MUST be distinct images, not
  two tags of one image ID: Docker untags rather than removes in that case, so
  both assertions would pass without any disk having been reclaimed — the same
  hazard 2.4 names for its own fixture.
- [ ] 2.2 Cover the shared-base case: a second tag of a base image repository
  present on the host survives a deploy of an application referencing that
  repository.
- [ ] 2.3 Cover the previous-owner case: an image under a different owner
  segment but the same application name is reclaimed.
- [ ] 2.4 Cover unforced removal: an in-namespace image that no Compose service
  references, held by a **stopped** container, survives the deploy. This is the
  assertion that catches a later `-f`; without it the backstop is unenforced.
  The fixture image MUST carry exactly one tag — Docker refuses removal only
  where it would drop the last reference, so a second tag makes the command
  succeed by untagging and the assertion fails against a correct
  implementation, or passes for the wrong reason.
- [ ] 2.5 Cover the degraded reference set: with `docker compose config
  --images` unable to produce a set, no image in the namespace is removed.
- [ ] 2.6 Cover failure isolation with a real induction, not a stubbed one: the
  stopped-container image from 2.4 makes `docker image rm` genuinely fail, and
  `app-deploy` must still exit zero with the containers running. A test that
  asserts the exit status without making any removal fail would pass against a
  reclamation step that matched nothing at all.
- [ ] 2.7 The untagged exclusion is **not covered by a test**, and this is a
  deliberate, recorded gap in the same shape as 2.9's. The fixture it would need
  is an in-namespace image carrying no tag, and that arises only from a repo
  digest — i.e. a real pull from a registry, which 2.8 forbids on determinism
  grounds. "Tag then untag" does not substitute: it yields `<none>:<none>`, a
  fully dangling image, which is the proposal's *first* non-goal and outside
  every namespace by construction — so a test built that way would prove the
  wrong property while reading as though it proved this one.

  The property is held instead by the `:<none>` filter being visible in the
  script (1.5) and by review. Accepted on the operator's decision, 2026-09-07,
  against the alternative of adding a digest-pinned local `registry:2` to the
  scenario: no application in this repository pins its own image by digest
  today, so the failure mode — reclaiming an image an application is pinned to —
  is currently unreachable. **Revisit this if any application ever adopts a
  digest pin**, at which point the registry fixture becomes worth its scope.

- [ ] 2.8 Build **four** distinct `ghcr.io/…`-shaped fixture images inside the
  instance, one `docker build` each from a two-line `FROM alpine:3.19` plus a
  per-fixture distinguishing layer: two tags of one namespaced repository for
  2.1, a previous-owner reference for 2.3, and the stopped-container image for
  2.4. Build, not `docker tag`: tagging yields one image ID wearing several
  tags, which 2.1 forbids outright ("distinct images, not two tags of one image
  ID") and 2.4 forbids by requiring exactly one tag — `alpine:3.19` keeps its
  own, so anything tagged off it already has two. `docker tag` stays correct for
  2.2's second base-image tag, which is out of namespace by construction.

  Order construction **after** the deploy at `verify.yml:58` — that is where
  `alpine:3.19` actually enters the instance; lines 35 and 46 only write its
  name into a Compose file.

  Then order each fixture individually: build an in-namespace fixture
  **immediately before the deploy that must observe it**, and never let one
  exist before a deploy that would reclaim it. Reclamation runs on 2.1's *first*
  deploy too, and three of the four fixtures live in the namespace it clears —
  so a single up-front construction block hands deploy #1 the tag-B image, the
  previous-owner image and the stopped-container image as candidates. The
  tag-B case would fail loudly at deploy #2, but **2.3 would pass for the wrong
  reason**, its image having been reclaimed by the earlier deploy rather than by
  the one the scenario is about — the same wrong-reason pass 2.4 and 2.6 each
  guard against for themselves. Create 2.4's stopped container in the same step
  as its image, so the image is never unheld while a deploy runs. If a build fails, try `DOCKER_BUILDKIT=0` first:
  `prepare.yml` puts the nested daemon on the `vfs` storage driver with
  `containerd-snapshotter` disabled.

  Local by construction means `pull_policy: never` on the fixture services is a
  convenience keeping `docker compose pull` a real success, not a load-bearing
  assumption — which matters because Compose is not pinned here:
  `molecule.yml`'s digest pins the platform image, while `docker-compose-plugin`
  arrives from upstream apt via `geerlingguy.docker` at converge.
  **Do not point a fixture at a real GHCR package.** Not because the suite is
  offline — it already pulls `alpine:3.19` from Docker Hub, so
  `iac-cicd-pipeline`'s "offline" means credential-free, which a public package
  would also be — but because an external, mutable package outside this
  repository's control is the class of dependency that capability's
  digest-pinning obligation exists to exclude. Where the local-build route
  fails, **raise it**.
- [ ] 2.9 Cover the early-exit reports: assert the empty/undeterminable
  reference-set path reports its reason, distinguishably from a run that found
  nothing to reclaim. Assert the found-nothing branch too, on the `platform`
  deploy the scenario already performs at `verify.yml:121` — `platform`
  publishes no image of its own, so its namespace is permanently empty and that
  deploy is a free instance of the completed-but-removed-nothing path. The duration-bound scenario is **not** covered here —
  wedging a container daemon inside a Molecule container is not reproducible
  without breaking the same daemon the preceding `docker compose pull` needs, so
  that clause is held by the `timeout` being visible in the script and by
  review, not by a test. This is a deliberate gap, recorded rather than left to
  be noticed.

## 3. Verification

- [ ] 3.1 `pre-commit run --all-files` (`ansible-lint`,
  `ansible-playbook --syntax-check`, `gitleaks`, `terraform fmt`).
- [ ] 3.2 `molecule test -s default` for the `deploy_user` role.
- [ ] 3.3 `python3 -m unittest discover --start-directory .github/tests` from
  the repository root. Not merely a formality: `AGENTS.md` puts
  `ansible/roles/*/molecule/*/molecule.yml` in that suite's scope, and this
  change may touch that file.

## 4. Rollout

Ordered deliberately: the backlog is cleared **before** the new script reaches
the host. `commerce-ops` merges trigger deploys from another repository on their
own schedule, so "clear it before the next deploy" is an intention, not a
control — installing the script first leaves a window in which an unrelated merge
performs exactly the ~42.88 GB in-deploy unlinking design.md rules out. The
clearance does not depend on the new script, so reordering closes that window at
no cost.

- [ ] 4.1 Record `docker system df` and `docker images --format '{{.Repository}}'
  | sort | uniq -c` as the baseline (2026-09-07: 219 images, 46.43 GB, 42.88 GB
  reclaimable, 190 of them `ghcr.io/shatynska/commerce-ops`).
- [ ] 4.2 Clear the accumulated backlog by hand on the host, using the command
  in design.md's "The one-time backlog is cleared by hand" verbatim — namespace
  -scoped, untagged excluded, empty reference set aborts, plain `docker image rm`,
  never `-f`, never `prune -a`. Run it **privileged**, over the same access path
  `ansible-playbook` uses, in the same session as 4.3: the enumerated operator
  accounts hold `docker` group membership but no `sudo`, and `/opt/commerce-ops`
  is `drwxr-x--- deploy:deploy`, so the command's first two steps fail there
  (checked on the host, 2026-09-07). Re-read `docker system df` afterwards.
- [ ] 4.3 Only then run the host-configuration playbook — from `main`, after
  the pull request has merged — so the new `app-deploy` reaches `main-server`.
  Running it from this change's own branch would put a script on production
  ahead of the required checks.
- [ ] 4.4 After the next `commerce-ops` deploy, confirm the single tag that
  deploy superseded is gone and the tag it deployed remains — the change's
  `ship:confirm` observation. This is the steady-state behaviour every future
  deploy runs, which is what the gate should be proving; 4.2 is disk hygiene,
  not evidence about the mechanism. Should the observation fail, the script
  change is what is reverted: the hand clearance stands, having removed only
  images nothing referenced.
- [ ] 4.5 Record the reclamation step's reported counts and the deploy's
  elapsed time from that first steady-state run, so the expectation for every
  later deploy rests on an observation rather than an estimate.

## 5. Follow-up recorded, not done here

- [x] 5.1 Entry 10 in `docs/change-queue.md` records the periodic host-level
  prune covering fully dangling images, untagged namespace members and
  applications that no longer deploy — the three cases this change's proposal
  names as non-goals.
