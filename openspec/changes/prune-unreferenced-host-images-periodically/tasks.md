## 1. Implementation

- [ ] 1.1 Create `ansible/roles/image_prune/` with the conventional shape —
  `tasks/main.yml`, `defaults/main.yml`, `meta/main.yml`, `README.md`. Put the
  schedule, the randomised delay and the duration bound in `defaults/main.yml`
  as `image_prune_on_calendar`, `image_prune_randomized_delay_sec` and
  `image_prune_timeout_start_sec`, so the unit files (tasks 1.10, 1.11) read
  them rather than hardcoding literals; `deploy_apps` stays the one input with
  no default. Give
  `meta/main.yml` the `galaxy_info` `namespace`/`role_name` pair every role here
  carries: Molecule's bundled ansible-compat refuses a scenario whose role has a
  `meta/main.yml` without a resolvable fully-qualified name (see the `docker`
  role's own comment for the full diagnosis). This role has no dependencies.
- [ ] 1.2 Assert `deploy_apps` before any task acts on the host, per
  "A Role's Absent Required Input Is Reported by Name" — defined, a sequence,
  and neither a string nor a mapping — with a `fail_msg` naming the variable and
  `ansible/inventory/group_vars/prod.yml` as where to set it. Copy the shape
  from `deploy_user/tasks/main.yml`'s existing assert rather than inventing a
  second one. An **empty** `deploy_apps` is a supplied value and this assert
  SHALL accept it; what it means is decided at run time by task 1.6, not here.
- [ ] 1.3 Template the enumerated application names to a data file — one name
  per line, `root:root`, mode `0644`, at `/etc/prune-host-images/apps` — from
  `deploy_apps | map(attribute='name')`, creating `/etc/prune-host-images/`
  (`root:root`, `0755`) first. The extraction is named because the elements are
  `{name, public_key}` mappings and rendering them raw is silent: the file would
  name *something*, so the no-application guard would not fire, every name would
  miss its `/opt/<name>/docker-compose.yml` as the benign skip, and the keep set
  would reduce to container images — `docker image prune -a`, reporting a
  healthy run. Task 2.9's assertion on this file's contents is what stands
  between that and production.

  This file, not the script, is how the list reaches the host: the script body
  is `{% raw %}`-wrapped (task 1.4) and interpolates nothing, and
  wrapping only parts of it would leave a `content:` block that is half Jinja
  and half Go template, which is the collision the wrapper exists to prevent.
  Notify nothing — the next scheduled run picks the file up.
- [ ] 1.4 Install the prune script at `/usr/local/bin/prune-host-images`,
  `root:root`, mode `0755`, via `copy:`. **Wrap the whole `content:` in
  `{% raw %}…{% endraw %}`.** Ansible renders `content:` as Jinja, and this
  script uses Go template syntax (`docker images --format '{{.ID}}'`,
  `docker inspect -f '{{.Image}}'`) that Jinja will otherwise try to evaluate.
  This fails loudly at converge rather than silently, but it will fail.
- [ ] 1.5 **Enumerate the local images first, then build the keep set.** The
  order is a guard, not a style choice: with the keep set built first, an image
  a concurrent deploy pulls in between is on the host, outside a keep set read
  from the pre-deploy Compose file, and — before `up -d --wait` — held by no
  container, so neither the runtime's refusal nor the per-tag re-check (task
  1.8) protects it. Enumerating candidates first means the interval can only
  narrow what the run removes.

  Enumerate local images with `docker images -a --no-trunc --format` —
  `--no-trunc` is load-bearing, since `{{.ID}}` is otherwise a 12-character
  prefix that will not compare equal to the full IDs steps 6 and 7 produce.
  Then build the keep set as a set of image IDs, in this order:
  1. read the application names from `/etc/prune-host-images/apps`. If the file
     is absent, unreadable, or names none, abandon the run (task 1.6) —
     reported and non-zero. Do not let it die under `set -e` on the one input
     the whole keep set derives from. Report the **file being absent** and the
     **file naming no application** distinguishably: the first means the host
     has not converged, the second means the inventory names nothing, and they
     send an operator to different places. An **unreadable** file reports as
     absent: from the run's side the host has not supplied an enumeration, and
     the remedy is the same converge;
  2. for each name, if `/opt/<name>/docker-compose.yml` is absent, contribute
     nothing and continue;
  3. otherwise enumerate that file's declared profiles with
     `docker compose config --profiles` and render with **all of them passed**.
     Invoke both with an explicit `--project-directory /opt/<name>`, since
     `.env` resolution depends on it and — under the well-formedness rule in
     step 5 — a wrong project directory turns every run into an abandoned one:
     `docker compose --project-directory /opt/<name> --profile a --profile b … config --images`.
     No `-f` is needed: `--project-directory` alone drives Compose file
     discovery, checked by running it against a directory from outside it;
     A bare `config --images` omits every service behind an inactive profile —
     executed against Compose v5.4.0 locally; the host runs v5.5.0, where
     `--profiles` was confirmed present but this behaviour was not itself
     re-executed — which is exactly the defined-but-never-started class this
     design exists to protect. Passing a profile the file does not declare is
     tolerated (exit 0, checked);
  4. if either compose invocation fails, **abandon the entire run** (task 1.7);
  5. reject any emitted reference that is not a well-formed image reference —
     an empty repository or tag segment, a trailing `:`, a residual `${` — by
     abandoning the run (task 1.7). `docker compose config` returns 0 on an
     unset interpolation variable, emitting `ghcr.io/example/:v1` and a warning
     (checked locally), so this is the only thing standing between a missing
     `.env` key and that application's images losing their protection.
     **A digest reference (`repo@sha256:…`) is well-formed** and must pass this
     check: it is the form the change exists to honour, and a naive pattern
     that rejects it would abandon every run of a host whose applications pin;
  6. resolve each surviving reference with `docker image inspect -f '{{.Id}}'`,
     adding the ID; a well-formed reference that resolves to no local image
     contributes nothing and is not an error;
  7. add the image of every container: `docker ps -aq`, and if that yields any
     ID, `docker inspect -f '{{.Image}}'` over them, which returns IDs directly
     and needs no resolution step. **Guard the empty case** — `docker inspect`
     with no arguments exits 1 (checked), which under `set -euo pipefail` would
     abandon the run on a host with no containers, and that is precisely the
     state the empty keep set in scenario `abandon-paths` (task 2.4) arranges.
- [ ] 1.6 Make each of "the host carries no enumeration", "the enumeration
  names no application" and "the keep set is empty" an explicit abandon
  condition that removes nothing, not a property of the comparison. The first
  two abandon alike and report differently (task 1.5.1). These are three
  conditions, not one: with no application
  enumerated the union is still non-empty on any host that has containers, so
  the empty-keep-set guard cannot fire, and the run silently degrades to
  "remove every image no container holds" — `docker image prune -a`, the
  mechanism design.md rejects. Note also that every filter shape available here
  degrades the wrong way on a genuinely empty keep set: the previous change's
  `grep -vxF -f` matched every line, and a membership test against an empty set
  is false for everything, which likewise makes the whole host a candidate.
- [ ] 1.7 Make "an application's Compose file exists but cannot be rendered" and
  "a rendered reference is malformed" abandon the whole run, not that
  application's contribution. Note that `docker compose config` is **not** a
  daemon call — it parses locally and returns 0 against a dead `DOCKER_HOST` —
  so its failure means the file, not the runtime. A missing file is the
  separate, benign case in 1.5.2.
- [ ] 1.8 Remove an image whose ID is not in the keep set **by each of its
  tags**, one `docker image rm <repo>:<tag>` per tag, and by its ID only where
  it carries none. Never pass `-f`. `docker image rm <id>` on a multiply-tagged
  image fails with "must be forced", so removing by ID unconditionally would
  either strand every multi-tagged image or push someone to add `-f` — the one
  flag this design may not have.

  **Re-resolve each tag immediately before removing it** and skip it unless
  `docker image inspect -f '{{.Id}}'` still returns the ID it was selected as.
  Selection is by ID and removal is by name, and a pull can re-point a tag in
  between — a concurrent deploy, or any moving tag such as this host's own
  `postgres:16`. In the window between `docker compose pull` and
  `docker compose up -d --wait` the newly named image has no container holding
  it, so the runtime's refusal does not engage. This check is what lets
  design.md decline a lock.

  Individual removal failures are **tolerated and counted**, never fatal: a
  refusal is a normal outcome per the delta, and dependent-child images surfaced
  by `docker images -a` will produce them. Do not use `xargs` for the removal
  loop without accounting for its exit 123 on any single failure. The
  enumeration steps in 1.5 are the ones whose failure is fatal.
  Do **not** use `docker image prune` in either form: its dangling filter
  selects on absence of a tag, which would sweep a digest-pinned image on a
  property design.md establishes is not evidence.
- [ ] 1.9 Report on every exit path except the duration bound, which is
  systemd's to record (task 1.10). A completed run prints
  `considered N, removed M` and exits 0. **Both counts are deduplicated by image
  ID**, so a two-tag image counts once however many `docker image rm`
  invocations it took. `N` is the number of distinct identities the run
  enumerated. `M` is the number of **those** for which one of this run's own
  `docker image rm` invocations reported the image deleted — anchored to the
  invocation, not to the host's state afterwards, so a refused removal, a tag
  skipped by the re-check, and a tag dropped from an image that survives under
  another each leave it unchanged. Track `M` from the
  removal loop rather than diffing the host at the end: `app-deploy` removes images too, a weekly window will
  occasionally overlap a deploy, and a diff would credit that deploy's work to
  this run in the one report this change emits.

  An abandoned run prints which condition ended it — unresolvable Compose
  file (naming the application), malformed reference (naming it), no enumeration
  on the host, enumeration naming no application, empty keep set, could not
  enumerate local images — and exits
  non-zero. Compute the counts into variables with the enumeration's status
  checked in its own right, rather than as the head of a pipeline whose failure
  the report would swallow and print as `considered 0, removed 0` —
  byte-identical to a healthy run over a host with nothing to reclaim.
- [ ] 1.10 Install `prune-host-images.service` as `Type=oneshot` running that
  script, with `TimeoutStartSec=` set to a value generous against a legitimate
  run (order of minutes, not seconds) and recorded in a comment. The bound is
  the unit's, not a `timeout` inside the script: systemd records the expiry in
  the journal and marks the unit failed from outside the process, which is
  where `app-deploy` had to work to put its own timeout line. Do **not** also
  wrap the script body in `timeout`.
- [ ] 1.11 Install `prune-host-images.timer` with a weekly `OnCalendar=`, an
  explicit `UTC` suffix, `Persistent=true` and a `RandomizedDelaySec=`. Enable
  and start the **timer**, never the service — starting the service runs a prune
  during the converge, which is an Ansible run removing images from a host as a
  side effect of configuring it, and the delta forbids it.
- [ ] 1.12 Add `image_prune` to `ansible/playbooks/host-baseline.yml`, after
  `docker` (the runtime must exist) and with a comment saying why the position
  matters, matching how `ops_user`'s and `platform_data_volume`'s entries
  already explain theirs.

  **Add `image_prune` to `.ansible-lint`'s `mock_roles` in the same commit.**
  `ansible-lint` does not resolve role references through `ansible.cfg`'s
  `roles_path`, so without the entry it reports a false `role not found`
  against `host-baseline.yml` *and* against both new `converge.yml` files, and
  `pre-commit run --all-files` (task 3.3) fails. That file's own comment states
  the rule; every existing role is listed there.
- [ ] 1.13 Write `ansible/roles/image_prune/README.md` covering: what the keep
  set is and that it is a union rendered across every declared profile; that
  `deploy_apps` is read from the same inventory variable `deploy_user` reads and
  not copied; and — stated plainly, because it is the operational consequence
  operators will meet — that **removing an application from `deploy_apps` makes
  that application's images reclaimable by the next scheduled run after the next
  converge**, since the on-host list is written at converge time. The delta
  requires this be recorded in the role's own documentation.
- [ ] 1.14 Fix `docs/change-queue.md` entry 10's own text: it says the previous
  proposal "names both of these as non-goals" and then lists three. A word, not
  a change; the entry is deleted when this change is archived, so fix it in the
  same commit that adds the artifacts rather than leaving it for a sweep.

## 2. Tests

Dispatched to an author other than whoever implements section 1, from the
approved delta rather than from the script. Two of this project's three test
commands are in scope; the Terraform row is not.

- [x] 2.1 **Before running Molecule at all**, clear the shared state its runs
  collide on and confirm no peer session is mid-run:
  `rm -rf ~/.ansible/tmp/molecule.* ~/.cache/molecule/image_prune`. The instance
  name and these paths are stable per role and shared across worktrees. A
  collision kills a container under a live module and surfaces as "Module result
  deserialization failed" at `create`, `prepare` or `verify` — which reads as a
  module bug and is not one. It can also pass as easily as fail. This is recorded
  nowhere in the repository — the queue entry that held it was deleted when its
  change archived — which is why it is written out in full here; task 3.6 queues
  giving it a permanent home.
- [x] 2.2 Provision before believing any result: a fresh working tree carries
  tracked files only, and this scenario converges the `docker` role, whose
  `meta/main.yml` depends on `geerlingguy.docker`. Without it the run fails at
  `syntax`, before `converge`. `-p ansible/roles` is load-bearing — each
  scenario sets `ANSIBLE_ROLES_PATH` to `ansible/roles`, so a role installed to
  the default `~/.ansible/roles` is never found:
  ```
  pip install -r ansible/requirements-test.txt
  ansible-galaxy collection install -r ansible/requirements.yml
  ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles
  ```
  Pulling the digest-pinned `registry:2` on the controller ahead of time saves
  the first run some seconds, but is not a precondition — task 2.5's `prepare`
  obtains it itself.

  Record the baseline — the run before anything was written — in `test-plan.md`,
  and report verification as **not run, and why** until provisioning completes.
- [x] 2.3 Create `ansible/roles/image_prune/molecule/default/`. Fixture images
  are built locally with `docker build`; **no fixture may point at a real GHCR
  or Docker Hub package of this project's, and none may be pulled from one**, so
  the scenario stays deterministic. Build distinct images for: a shared base
  referenced by one fixture application and not another; a superseded tag of
  that same repository; an image referenced by a defined service with no
  container; an image referenced only by a service behind an **inactive
  profile**; an image held by a **stopped container** and referenced by nothing;
  a tagged image referenced by nothing and held by nothing; an **untagged**
  image referenced by nothing and held by nothing (build a tag, then rebuild
  different content at the same tag, stranding the first as untagged) — this is
  the class the proposal identifies as the change's largest target, ten images
  and ~3.2 GB on the host; an image carrying **two tags**, neither referenced;
  and an image carrying **two tags** that a **stopped container** holds and no
  Compose file references.
- [x] 2.4 Create a second scenario, `molecule/abandon-paths/`, for the three
  abandon branches `default` cannot host — its fixtures include two stopped
  containers, and design.md's own "any host with containers has a non-empty
  union" puts the empty-union branch out of reach there. Each arrangement must
  reach a **different** branch; they are easy to collapse into one that
  abandons early and reads as covering all three:

  1. **Empty enumeration.** Converge with `deploy_apps: []`. The run abandons at
     the enumeration read and reports "names no application".
  2. **Absent enumeration.** Remove `/etc/prune-host-images/apps`, then run the
     script. It abandons and reports the host-not-converged condition,
     **distinguishably** from arrangement 1 — that distinction is the delta
     scenario "An enumeration the host does not carry is distinguishable from
     one naming nothing", and asserting only "both abandon" would not test it.
  3. **Empty keep set.** This one needs a *non-empty* `deploy_apps`, or the run
     abandons at step 1 and never computes a keep set at all — the branch would
     read as covered and never be entered. Arrange: `deploy_apps` naming one
     **never-deployed** application (no `/opt/<name>/docker-compose.yml`), no
     containers on the host, and **at least one unreferenced local image
     present**. The union is then genuinely empty, and the fixture image is what
     makes 2.8's mutation of this guard able to go red — without it, deleting
     the guard changes nothing observable.

  Arrangements 1 and 3 need different `deploy_apps` values in one scenario: use
  `include_role` with overridden vars, as 2.7 does for the retired-application
  case, and not a hand-edit of the on-host file — editing it directly bypasses
  the version-controlled-enumeration clause that is the whole reason the list is
  not a glob of `/opt`. This scenario carries the same `iac-cicd-pipeline`
  obligations as `default` (task 2.10).
- [x] 2.5 Add the digest-pin fixture, which needs a registry and is therefore
  called out separately from 2.3: run a `registry:2` container **inside the
  Molecule instance**, pinned by digest rather than by its mutable tag and
  **pre-seeded into the instance** — `prepare` obtains the digest-pinned image
  on the controller (`delegate_to: localhost`, idempotent, so a CI runner with a
  cold cache is not a precondition), then `docker save`/`docker load` into the
  instance — so the instance itself pulls nothing and
  `iac-cicd-pipeline`'s "runs offline against local containers" stays true of
  it. Obtaining the image on the controller is a provisioning step like the
  Galaxy roles in 2.2; add it there. Push a
  fixture image to it, then **remove the local tag and re-pull by digest**, and
  have a fixture application's Compose file reference it by `@sha256:` digest.
  Without the untag-and-re-pull the pushed image keeps its build tag, so the
  fixture fails 2.6's own pre-assertion that it carries none — and an author who
  relaxes that pre-assertion instead loses the property the fixture exists to
  prove. This is a local registry serving a locally
  built image — it points at no real package and 2.3's constraint does not
  forbid it. This fixture is not optional padding: the digest-pin scenario is
  the single property justifying not carrying forward the previous change's
  untagged-image exclusion, and its failure mode is deleting an image an
  application is pinned to. If the toolchain makes a local registry unworkable,
  do not quietly drop the scenario — record it in 2.11 with the reason and say
  so in the report.
- [x] 2.6 Assert the fixtures are what they claim **before** asserting
  behaviour: distinct image IDs, each two-tag fixture carrying exactly two tags,
  the singly-held stopped-container image carrying exactly one, and the
  untagged and digest-pinned fixtures each carrying none — and that the untagged
  and digest-pinned fixtures are distinct images, since both present as tagless
  and an assertion that conflated them would prove nothing. The previous change records a fixture built without noticing
  the multi-tag case, which passed for the wrong reason.
- [x] 2.7 Cover the delta's scenarios that are reachable in a container.
  **Order matters within this scenario:** make every keep-set and removal
  assertion first, and introduce the unresolvable-Compose-file and
  malformed-reference arrangements only afterwards. An abandoning run removes
  nothing, so once either is in place every "SHALL still be present" assertion
  here passes whether or not the keep set is computed correctly — eleven
  positive assertions going green for the reason 2.8 exists to catch. The
  cases: the
  superseded pin removed; the union keeping one application's image against
  another's; the defined-but-not-running image kept; the **profile-gated** image
  kept; the container-held image kept and not forced; the unreferenced image
  removed; the untagged unreferenced image removed by ID; the **unreferenced
  two-tag image removed through each of its tags** (a by-ID implementation
  fails here with "must be forced", which is the whole reason task 1.8 removes
  by tag); the **two-tag image a stopped container holds keeping both tags** —
  the runtime's refusal guards the image and not its individual tags, so this is
  what the container contribution to the keep set buys and the only place it is
  observable; the **digest-pinned
  image kept**; the retired-application case, arranged by
  **re-converging with a reduced `deploy_apps`** — `include_role` with
  overridden vars, after 2.9's initial-converge assertion — rather than by
  hand-editing the on-host file, which would leave the
  version-controlled-enumeration clause, the whole reason the list is not a glob
  of `/opt`, never exercised; the never-deployed case (enumerated, no Compose file, run
  proceeds); the unresolvable Compose file abandoning the whole run; the
  **malformed reference** abandoning the whole run (a Compose file interpolating
  an unset variable); the three abandon branches task 2.4 arranges in
  `abandon-paths` — the **empty enumeration**, the **absent enumeration**
  reporting distinguishably from it, and the **empty keep set**; the
  completed-run report with its two counts; and the abandoned-run report plus
  non-zero exit on each branch that takes it.
- [x] 2.8 **Map every guard to the assertion that must turn red when it is
  removed**, and record the mapping in `test-plan.md`. This task stops at the
  mapping: running the mutations needs an implementation to mutate, and writing
  one here would be writing the code under test, so the round itself is task
  3.2 and section 2 is not complete until 3.2 has filled the mapping's result
  column in. Check, while mapping, that each assertion *can* evaluate false —
  an assertion that cannot fail is the defect this whole exercise is about.

  The guards: the no-application-
  enumerated abandon, the **absent-enumeration abandon** — on a live host,
  mutating it to fall through reaches a container-only keep set, which is
  `docker image prune -a`; in `abandon-paths`, which carries no containers, the
  mutated run instead falls to the empty-keep-set guard and reports the wrong
  condition, so what goes red is arrangement 2's distinguishable-report
  assertion (do not add containers to that scenario to make a removal
  observable — arrangement 3 requires there be none) — the empty-keep-set
  abandon, the abandon-on-unrenderable-
  Compose-file branch, the malformed-reference rejection, the all-profiles
  render, the container-image contribution to the keep set (mutate it away and the two-tag
  stopped-container assertion in 2.7 must go red — it is redundant with the
  runtime's refusal for the *image*, not for its tags), removal by tag rather
  than by ID, the `--no-trunc` on the local enumeration, and the absence of
  `-f`. The previous
  change shipped three assertions that were green for reasons unrelated to what
  they claimed: a `regex_search('timeout ')` matching the script's own comment
  about the timeout, a `.split('\n')` over a folded YAML scalar where `\n` was
  two literal characters, and a `removed[^0-9]*[0-9]+` matching Compose's own
  `Removed` output. Each read as coverage. Every guard here is over a
  destructive operation, so an assertion that cannot fail is worse than an
  absent one.
- [x] 2.9 Assert the *timer* is enabled and the *service* has never run after
  converge, and that the fixture images present before the converge are all
  still present after it — the delta's "Configuring the host does not prune it"
  scenario. A scenario that only checks the unit files exist would pass against
  a role that runs a prune during every converge. Assert `Persistent=true` on
  the timer as a static read of the installed unit, for the catch-up scenario.
  Assert too, **against the initial converge and before the reduced-`deploy_apps`
  re-converge in 2.7 rewrites it**, that `/etc/prune-host-images/apps` contains
  exactly that converge's `deploy_apps` names — so a defective template cannot
  ship green behind a retired-application case arranged some other way.
- [x] 2.10 Both new `molecule.yml` files must satisfy `iac-cicd-pipeline`'s existing
  discovery-based checks in `.github/tests`, which read every scenario this
  repository authors under `ansible/roles/*/molecule/`: each platform image
  pinned by digest, and — where a scenario names an image repository another
  already names — the **same** digest. That now includes these two agreeing
  with **each other**, not only with their siblings in other roles. These are constraints on
  the file, not new assertions to write; that suite asserts what a committed
  file *says*, statically, may not spawn a container, and must not be given the
  behavioural assertions, which are Molecule's. Run it as
  `python3 -m unittest discover --start-directory .github/tests` from the
  repository root to confirm.
- [x] 2.11 Record in `test-plan.md` everything the delta states that no
  scenario reaches, with the reason for each. Five entries are expected.

  The **duration bound** and a **wedged runtime**: wedging the daemon inside a
  Molecule container breaks the same daemon the scenario's own fixtures need,
  and the bound is systemd's, so both are held by a static read of the installed
  unit and by review.

  The **no-age-criterion** scenario: every fixture is built during the run, so
  none carries an old `Created`, and no implementation of tasks 1.5-1.8 consults
  a timestamp at all — an assertion would pass against a conforming and a
  non-conforming script alike. Held by a static read that the script calls
  neither `docker image prune` nor anything reading `Created`.

  The **pre-removal tag re-resolution** (task 1.8) and the
  **enumerate-local-images-first ordering** (task 1.5), for one shared reason:
  both are observable only when the host's images change *midway through a run*,
  and a black-box scenario has no seam between the run's enumeration and its
  removal loop at which to change them. A fixture that re-points a tag before
  the run, or an assertion over the script's line order, passes whether or not
  the guard exists — the false-green shape tasks 2.8 and 3.2 exist to prevent — so
  neither is on 2.8's mutation map and neither may be given a placeholder
  assertion in 2.7. Both are held by review and by a static read of the
  installed script, and `design.md`'s Risks section states that limit rather
  than leaving it here. These two are what close the concurrent-deploy window,
  so the least-verified part of this design is the part dealing with the only
  actor that competes with it. If a deterministic arrangement is found for
  either — sized rather than slept — add it to 2.7 and 2.8 together and strike
  it from this list.

  For every entry: do not add an assertion that matches the script's or the unit
  file's own comment text, which is one of the three false-green shapes named in
  task 2.8.

### Traps that have already cost time in this area

- `copy:`'s `content:` is rendered as Jinja; `{{.Repository}}` needs
  `{% raw %}…{% endraw %}` (task 1.4).
- In a folded (`>-`) YAML scalar, `\n` is a literal backslash and `n`. Use
  `.splitlines()` rather than `.split('\n')`.
- `regex_search`'s group spec is `'\1'`, not `'\\1'`, in a folded scalar.
  `'\\1'` raises `'NoneType' object has no attribute 'group'`, which reads like
  a failed match.
- `grep -c '…[^/]\+…'` without `-E` silently matches nothing: in a basic regular
  expression, `+` is a literal.
- `services: {}` does **not** make `docker compose up -d --wait` succeed — it
  exits 1 with "no service selected". There is no fixture through that path that
  yields a successful deploy and an empty reference set.
- `timeout 0` disables the bound entirely rather than expiring immediately.
- `docker compose config` returns 0 against a dead `DOCKER_HOST`, and returns 0
  on an unset interpolation variable; `docker images` returns non-zero against a
  dead daemon. Only the latter proves the runtime answered.
- `docker inspect` with no arguments exits 1, so a `docker ps -aq | xargs`
  pipeline abandons the run on a host with no containers.
- An **apostrophe inside a shell comment** breaks an `ansible.builtin.shell`
  task at load time. Its free-form body goes through `split_args`, which counts
  quotes and knows nothing about shell comments, so `# the runtime's own
  refusal` leaves the count odd and the task never runs — failing with "failed
  at splitting arguments, either an unbalanced jinja2 block or quotes" pointed
  at the `name:` line, which reads like a YAML defect and is not. It cost the
  test-derivation pass a full scenario run to diagnose. Keep prose in YAML
  comments, not in shell bodies.

## 3. Verification and rollout

- [ ] 3.1 Run `molecule test --all` from `ansible/roles/image_prune/`, per this
  project's Molecule row, and read the **SCENARIO RECAP** rather than the exit
  code: scenarios run in sorted order and the run stops at the first failure, so
  a scenario sorting after a failing one is silently never executed. Confirm the
  recap names every scenario the role has. While the role is red, iterate with
  `-s <name>`.
- [ ] 3.2 **Run the mutation round** that task 2.8 mapped, now that there is an
  implementation to mutate: for each guard, remove or invert it, confirm the
  named assertion goes **red**, restore it, and fill in that row of
  `test-plan.md`'s mapping. A guard whose assertion stays green is not a
  passing test — it is an assertion that cannot fail, over a destructive
  operation. Section 2 is not complete until this is done.
- [ ] 3.3 Run `pre-commit run --all-files` (`ansible-lint`,
  `ansible-playbook --syntax-check`, `gitleaks`) and the `.github/tests` suite.
- [ ] 3.4 Dispatch `ai-toolkit:change-code-reviewer` over the diff, against a
  diff that already passes 3.1, 3.2 and 3.3. Ask it to read the installed
  script's enumerate-before-keep-set ordering and its per-tag re-resolution
  line by line: `test-plan.md` records both as unverified by any assertion, and
  this review is the only thing that checks them.
- [ ] 3.5 Ship by merging. The host-configuration half reaches prod by an
  operator running `ansible-playbook` — this repository has no Ansible pipeline,
  and that is already how every host-configuration change reaches production
  here, including the one that installs `app-deploy`. It needs the Ansible Vault
  password, which only the operator holds.
- [ ] 3.6 **Confirm the effect** — this change can answer the gate, so it is not
  waivable. On the host after the converge: `systemctl list-timers` names
  `prune-host-images.timer` with a next elapse; `systemd-analyze verify` accepts
  both units; `docker system df` is unchanged by the converge itself; then
  `systemctl start prune-host-images.service` once, by hand, and read
  `journalctl -u prune-host-images.service`. The expected report on the measured
  2026-09-07 state is a completed run that removes the ten dangling images,
  `traefik:v3.2`, `gcr.io/cadvisor/cadvisor:v0.49.1`, `postgres:16`,
  `alpine:3.20`, `alpine:3.21`, `alpine:latest`, `curlimages/curl:latest`,
  `docker:27-cli`, `polinux/stress:latest` and `traefik/whoami:latest`, and
  keeps every image the eleven running containers hold together with
  `postgres:16-alpine` and `postgres:16.15`. Confirm with `docker system df` and
  by checking each of those eleven containers is still up.
- [ ] 3.7 Record two follow-ups in `docs/change-queue.md`, neither of which
  belongs in this change. First, the one this change names as a non-goal:
  node-exporter's textfile collector plus a staleness alert, so a prune that has
  silently stopped working is alertable rather than only journalled — a
  `platform/` change. Second, giving the Molecule shared-state hazard in task
  2.1 a permanent home in `AGENTS.md`: it is recorded nowhere in this repository
  today, the queue entry that held it was deleted when its change archived, and
  it has now cost two sessions time it did not need to.
