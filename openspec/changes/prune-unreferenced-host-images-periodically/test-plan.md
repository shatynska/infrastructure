# Test plan — prune-unreferenced-host-images-periodically

Derived from `specs/iac-host-configuration/spec.md` (one `ADDED` requirement,
**24 scenarios**) ahead of the implementation, following `tasks.md` section 2.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among `openspec instructions apply`'s context files and has to be read on
purpose. Read it before implementing `tasks.md` section 1 — and read
"What this pass could NOT do" before claiming section 2 complete.

Everything below was written without reading any implementation of the prune
script or the role: none exists. The delta is a pure `ADDED` requirement, so
there is no superseded behaviour to establish.

## Where the tests are, and how to run them

Two Molecule scenarios, both new, both entirely additive:

```
ansible/roles/image_prune/molecule/default/       molecule.yml converge.yml prepare.yml verify.yml
ansible/roles/image_prune/molecule/abandon-paths/ molecule.yml converge.yml prepare.yml verify.yml
```

```
cd ansible/roles/image_prune && molecule test --all
```

**Read the SCENARIO RECAP, not the exit code.** Scenarios run in sorted order
and the run stops at the first failure, so `default` is silently never executed
while `abandon-paths` is red. Confirm the recap names both. While the role is
red, iterate with `molecule test -s <name>`, or `molecule converge -s <name>`
followed by `molecule verify -s <name>` against a live instance.

**Granularity.** Molecule's selectable unit is the scenario, not the assertion;
there is no way to run one of these tests alone. Each is therefore identified
below by its exact Ansible task `name`, which is what the run prints and what
`--start-at-task` accepts. Ansible's `assert` fails the play at the first
failure, so assertions surface one at a time as the implementation lands.

### Before every run, without exception

```
rm -rf ~/.ansible/tmp/molecule.* ~/.cache/molecule/image_prune
```

and confirm no peer session is mid-run (`docker ps` for `*-instance`
containers, `pgrep -af molecule`). The instance name and these paths are stable
per role and shared across worktrees. A collision kills a container under a live
module and surfaces as "Module result deserialization failed" at `create`,
`prepare` or `verify` — which reads as a module bug and is not one, and which
can pass as easily as fail (`tasks.md` 2.1).

### Provisioning (`tasks.md` 2.2) — a run before this proves nothing

```
pip install -r ansible/requirements-test.txt
ansible-galaxy collection install -r ansible/requirements.yml
ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles
```

`-p ansible/roles` is load-bearing: each scenario sets `ANSIBLE_ROLES_PATH` to
`ansible/roles`, so a role installed to the default `~/.ansible/roles` is never
found, and the run dies at `syntax` before `converge`.

On a machine whose Docker credential helper is broken (Docker Desktop's
`credsStore` under WSL — see README's "If `molecule create` fails on your
machine"), export `DOCKER_CONFIG` at a directory holding an empty `{}` for the
whole run. `default`'s `prepare.yml` obtains the digest-pinned registry image on
the **controller** and passes the controller's environment through, so the same
export covers it:

```
mkdir -p /tmp/molecule-docker && echo '{}' > /tmp/molecule-docker/config.json
DOCKER_CONFIG=/tmp/molecule-docker molecule test --all
```

### `.github/tests` owes nothing new

`tasks.md` 2.10's obligations on the two new `molecule.yml` files are
**constraints on those files, not new assertions to write**: that suite
discovers `ansible/roles/*/molecule/*/molecule.yml` and applies its existing
pinning and digest-agreement checks automatically. Both new scenarios pin
`geerlingguy/docker-ubuntu2204-ansible` at the same digest every sibling
carries. Confirmed:
`python3 -m unittest discover --start-directory .github/tests` → **89 tests, OK**
with the new scenarios in place (identical to the baseline below).

No file under `.github/tests/` was added or modified by this pass.

## Baseline

Taken before writing anything, on the dispatched worktree at `08954be`, working
tree clean.

| Run | Result |
|---|---|
| `python3 -m unittest discover --start-directory .github/tests` | **GREEN** — 89 tests, OK |
| `molecule test --all` from `ansible/roles/image_prune/` | **NOT RUNNABLE** — the directory did not exist. There was nothing to baseline for this role. |
| `molecule test -s default` from `ansible/roles/docker/` (harness sanity check) | **GREEN** — SCENARIO RECAP `actions=12 successful=8 failed=0`, after the provisioning above |

This is a **scoped** baseline. Its scope: the `.github/tests` suite in full, plus
one sibling Molecule scenario run to establish that the harness itself works on
this machine — so that a failure in the new scenarios is attributable to them
and not to the toolchain. `molecule test --all` across every role was **not**
run; the four other roles' scenarios are untouched by this pass.

## Result of running the derived tests against the unimplemented change

`molecule test -s abandon-paths` and `molecule test -s default`, on the worktree
with these scenarios in place and nothing of `tasks.md` section 1 implemented.

Both scenarios reach `verify` — `dependency`, `destroy`, `syntax`, `create`,
`prepare`, `converge` and `idempotence` all **succeed**. Note that `converge`
succeeding is not evidence the role works: `ansible/roles/image_prune/` exists
(it holds `molecule/`), so Ansible resolves the role name and runs its empty
task list without complaint. Nothing is installed.

Both then fail at the first assertion that reads an installed artifact:

- `abandon-paths` → **`Assert the converge wrote an enumeration that names no
  application`**, on `'APPS-FILE present'`.
- `default` → **`Assert the unit, timer and script were installed where the role
  says`**, reporting `FILE-ABSENT []`, `FILE-ABSENT []`,
  `FILE-ABSENT [/usr/local/bin/prune-host-images]`.

That is failure state **"the target does not exist yet"**. It establishes that
nothing on the host prunes anything today and **nothing more**: every assertion
after the first is unexecuted, so their evaluation is unverified and they will
surface one at a time as the implementation lands.

### What was separately verified by hand, because fail-fast hid it

Driven inside a live instance (`molecule converge -s default`, then `docker exec`
into `image_prune-role-instance`), because the fixtures are the half of these
scenarios that does **not** depend on the implementation:

- **All eleven `default` fixtures built, and are eleven distinct image
  identities.** Confirmed from `docker images -a`.
- **Tag counts are exactly what each scenario needs**: `held-by-stopped` 1,
  `twotag` 2, `held-twotag` 2, the stranded fixture 0, the digest-pinned fixture
  0 — and the last two are *different images*, which matters because both
  present as tagless and one must be removed while the other is kept.
- **The digest-pin fixture works end to end.** The controller-obtained
  `registry@sha256:a3d8aaa6…` tarball loads into the instance, the registry
  container serves on `127.0.0.1:5000`, the fixture pushes, the build tag is
  removed, the re-pull by digest lands a tagless image, and
  `docker image inspect -f '{{.Id}}'` on the digest reference resolves it. The
  instance pulls no registry image of its own.
- **`docker images -a` reports 16 rows against 14 identities**, so the
  deduplicated-`considered` assertion can discriminate a per-identity count from
  a per-tag one.
- **The profile fixture is real.** In the instance, at Compose **v5.5.1**:
  `docker compose --project-directory /opt/beta config --profiles` emits
  `debug`; `config --images` alone emits only
  `imgprune-fixture/defined-not-running:v1`; with `--profile debug` it emits
  the profiled image too. Passing an **undeclared** profile exits 0. This
  re-confirms, at the version nearest the host's v5.5.0, the behaviour design.md
  checked at v5.4.0.
- **The unresolvable-Compose fixture really fails**: `config --images` exits 1.
- **The malformed-reference fixture really succeeds and really is malformed**:
  `config --images` exits **0** and emits exactly `imgprune-fixture/:v1`.
- **`docker inspect` with no arguments exits 1** in this instance — the trap
  `tasks.md` 1.5.7 names, confirmed on the platform the tests run on.
- `/opt/undeployed` does not exist, so the never-deployed case is genuinely in
  place from the first converge.

### Expression checks

Every non-trivial Jinja expression in these files was exercised standalone
against `ansible-core 2.21.3` **in both directions** — a passing fixture and a
failing one — before being committed, so that none of them is an assertion that
cannot go red: the apps-file equality (against a correctly rendered file and
against one rendering the `{name, public_key}` mappings raw), the
eleven-distinct-identities count (against a collision), the rows-exceed-identities
precondition (against a flat host), and the deduplicated-`considered` equality
(against a per-tag count). All nine checks passed.

### A trap this pass hit, recorded so the next author does not

**An apostrophe inside a shell COMMENT breaks Ansible's own argument splitter.**
`ansible.builtin.shell`'s free-form body is passed through `split_args`, which
counts quote characters without knowing about shell comments, so
`# the runtime's own refusal` leaves the quote count odd and the task never
runs. It fails at task-load time with "failed at splitting arguments, either an
unbalanced jinja2 block or quotes", pointing at the task `name` line — which
reads like a YAML defect and is not one. Prose in these files therefore lives in
YAML comments; shell comments stay apostrophe-free. `verify.yml` carries a note
saying so at the first shell block.

## Scenario accounting

**24 scenarios in the delta, 24 accounted for**: 20 covered by behavioural
assertions, 3 covered only by a static read of the installed artifact (each with
its reason), 1 uncovered outright with its reason. One further scenario
(`An abandoned run says why and fails`) is covered across five of its six
branches; the sixth's reason is recorded below.

| # | Delta scenario | Covered by (exact task name) | Scenario | tasks.md |
|---|---|---|---|---|
| 1 | An image superseded by a newer pin is removed | `Assert the superseded tag of the base repository is gone and the referenced one remains` | default | 2.7 |
| 2 | An image one application references is kept when another does not | `Assert an image only one enumerated application references was kept by the union` | default | 2.7 |
| 3 | A defined service that is not running keeps its image | `Assert an image a defined service references with no container anywhere was kept` | default | 2.7 |
| 4 | A service behind an inactive profile keeps its image | `Assert an image referenced only behind an inactive profile was kept` | default | 2.7 |
| 5 | An image a container holds is never removed | `Assert an image a stopped container holds was kept and its container still holds it`; the "not forced" half additionally by `Assert the script consults no age criterion and never forces a removal` | default | 2.7 |
| 6 | An image nothing references is removed | `Assert a tagged image nothing references and nothing holds was removed` | default | 2.7 |
| 7 | An untagged image nothing references is removed | `Assert an untagged image nothing references was removed by its identity` | default | 2.7 |
| 8 | A digest-referenced image an application pins is kept | `Assert a digest-pinned image an enumerated application references was kept` | default | 2.5, 2.7 |
| 9 | An unreferenced image carrying more than one tag is removed through each of them | `Assert an unreferenced two-tag image was removed through each of its tags` | default | 2.7 |
| 10 | A tag of an image a container holds is not dropped | `Assert both tags of an image a stopped container holds are still present` | default | 2.7 |
| 11 | A tag re-pointed after enumeration is not removed | **UNCOVERED**, deliberately — see below | — | 2.11 |
| 12 | A retired application's images become reclaimable | `Assert the retiring converge refreshed the on-host enumeration and left the stale file` **and** `Assert a retired application's image was reclaimed and every kept application's survived` | default | 2.7 |
| 13 | An unresolvable Compose file abandons the whole run | `Assert the unresolvable Compose fixture really is unrenderable` (precondition) **and** `Assert an unrenderable Compose file abandoned the whole run, removing nothing, and failed` | default | 2.7 |
| 14 | A malformed reference abandons the whole run | `Assert the malformed-reference fixture renders successfully and yields a malformed reference` (precondition) **and** `Assert a malformed rendered reference abandoned the whole run, removing nothing, and failed` | default | 2.7 |
| 15 | An application that has never deployed does not abandon the run | `Assert the never-deployed application is enumerated, absent from the filesystem, and harmless` | default | 2.7 |
| 16 | An enumeration the host does not carry is distinguishable from one naming nothing | `Assert a host carrying no enumeration removed nothing and failed` **and** `Assert the three abandon branches report three distinguishable conditions` | abandon-paths | 2.4.2 |
| 17 | An empty enumeration removes nothing | `Assert the converge wrote an enumeration that names no application` (precondition) **and** `Assert an enumeration naming no application removed nothing and failed` | abandon-paths | 2.4.1 |
| 18 | An empty keep set removes nothing | `Assert the empty-keep-set arrangement really is one, and removed nothing` | abandon-paths | 2.4.3 |
| 19 | An old image in active use is not removed for its age | **STATIC READ ONLY** — `Assert the script consults no age criterion and never forces a removal` | default | 2.11 |
| 20 | A completed run reports what it did | `Assert the completed run reported both counts, deduplicated by identity, and exited zero` (removed-something) **and** `Assert the installed unit runs the prune and a completed run leaves it successful` (found-nothing, through the unit) | default | 2.7 |
| 21 | An abandoned run says why and fails | `Assert the two abandoned runs are distinguishable from each other and from a completed run` (default) **and** `Assert the three abandon branches report three distinguishable conditions` **and** `Assert an abandoned run leaves a failed unit on the host` (abandon-paths). Five of six branches; the sixth below | both | 2.7 |
| 22 | A non-responding runtime does not leave the unit running indefinitely | **STATIC READ ONLY** — `Assert the schedule is the init system's and the service is a bounded oneshot` | default | 2.11 |
| 23 | Configuring the host does not prune it | `Assert the converge armed the timer and executed no prune` | default | 2.9 |
| 24 | A host that was down at its scheduled time still runs | **STATIC READ ONLY** — `Assert the timer carries the catch-up, UTC and randomised-delay settings` | default | 2.9 |

Supporting tasks that assert nothing about the requirement, but whose failure
means the fixtures or the arrangement are wrong rather than the implementation:

- `default`: `Assert the unit, timer and script were installed where the role
  says`; `Assert the host carries exactly this converge's application names, and
  nothing else` (also the guard on `tasks.md` 1.3's silent failure — a raw
  render of the `{name, public_key}` mappings); `Assert every fixture is a
  distinct image, so no assertion below reads another's outcome`; `Assert each
  fixture carries exactly the number of tags its scenario needs`; `Assert the
  host carries more image rows than identities, so the count can discriminate`.
- `abandon-paths`: `Assert this host carries no container and one unreferenced
  image`.

## Deliberate non-coverage, with reasons

`tasks.md` 2.11 expects five entries. All five are here, plus two further ones
this pass found.

**1 & 2 — the DURATION BOUND and a WEDGED RUNTIME (delta scenario 22).** Wedging
the container daemon inside a Molecule container breaks the same daemon this
scenario's own fixtures need — there is no arrangement that stops the runtime
answering the prune while leaving it answering the eleven fixture builds. The
bound is systemd's, not the run's, so there is also nothing the run itself would
print. Held by the static read that the service unit is `Type=oneshot` with a
`TimeoutStartSec=<digits>` value, and by review.

**3 — the NO-AGE-CRITERION scenario (delta scenario 19).** Every fixture is
built during the run, so none carries an old `Created` timestamp, and no
conforming implementation consults a timestamp at all. A behavioural assertion
would pass against a conforming and a non-conforming script alike. Held by the
static read that the script's non-comment lines call neither
`docker image|system prune` nor anything matching `.Created` or `until=`.

**4 & 5 — the PRE-REMOVAL TAG RE-RESOLUTION (delta scenario 11) and the
ENUMERATE-LOCAL-IMAGES-FIRST ordering (requirement prose; no scenario of its
own).** One shared reason: both are observable only when the host's images
change *midway through a run*, and a black-box Molecule scenario has no seam
between the run's enumeration and its removal loop at which to change them. A
fixture that re-points a tag *before* the run, or an assertion over the script's
line order, would pass whether or not the guard exists — exactly the false-green
shape `tasks.md` 2.8 exists to prevent. Neither is on the mutation list and
neither is given a placeholder assertion. Both are held by review and by a
static read of the installed script; `design.md`'s Risks section states this
limit in its own right, and names it as the least-verified part of the design
being the part that deals with the only actor that competes with it. **If a
deterministic arrangement is found for either — sized rather than slept — add it
to `tasks.md` 2.7 and 2.8 together and strike it from here.**

**6 — the "local images could not be enumerated" branch of delta scenario 21.**
The remaining five of that scenario's six branches are covered. This one needs
`docker images` to fail, which means a non-answering daemon, which is entry 2
above. Held by the same static read and by review.

**7 — the exact deduplicated `removed` count.** The delta fixes both counts as
deduplicated by identity. `considered` is asserted **exactly**, against the
distinct-identity count taken immediately before the run, which is what makes
per-tag double counting fail. `removed` is asserted only as `>= 1`: its exact
value depends on how the runtime treats the build base `alpine:3.19` (which has
dependent children, so a removal untags it without deleting it) and on any
intermediate build images, neither of which this pass can pin without asserting
against the classic builder's internals. The dedup half of `removed` is
therefore held by `considered`'s exactness and by review.

## Assertion classification

**Specified** — traces to a stated sentence of the delta requirement:

- the superseded tag absent, the referenced one present (1);
- both applications' distinctly-referenced images present (2);
- the defined-but-never-started image present (3);
- the profile-gated image present (4);
- the container-held image present, its container still holding it (5);
- the unreferenced tagged image absent (6);
- the untagged unreferenced image absent by identity (7);
- the digest-pinned image present (8);
- the two-tag unreferenced image absent by both tags **and** by identity (9);
- both tags of the container-held two-tag image present (10);
- the retired application's image absent and every kept one present (12);
- no image removed, the run failed, on an unrenderable Compose file (13) and on
  a malformed reference (14);
- both completed runs exiting zero with a never-deployed application enumerated
  (15);
- nothing removed and a report given, on each of the three abandon branches
  (16, 17, 18);
- **the three abandon reports being pairwise distinct** (16 — the delta says
  "distinguishably" in so many words);
- a completed run reporting both counts and exiting zero, with `considered`
  equal to the distinct-identity count (20 — the delta fixes the considered
  count as "the number of distinct identities the run enumerated");
- an abandoned run exiting non-zero and leaving a failed unit (21);
- the timer armed, the service never executed, and no image gone across the
  converge (23);
- `Persistent=true` on the installed timer (24);
- the script calling no tag-absence-selecting prune facility and never forcing a
  removal (19, 5).

**Derived** — no stated requirement fixes these. Recorded so the implementer can
see what was invented rather than agreed:

1. **The completed run's report wording.** Asserted as the shape
   `considered <N>, removed <M>`, case-insensitively, which is `tasks.md` 1.9's
   own line. The delta fixes no spelling. Depends on it: `Assert the completed
   run reported both counts, deduplicated by identity, and exited zero`.
2. **`considered` as the distinguishing marker.** Every abandoned-run assertion
   requires the word `considered` to be *absent* from that run's output — that
   is what makes it distinguishable from a completed run that found nothing,
   under `tasks.md` 1.9's shape. A different report design could satisfy the
   delta and fail this. Depends on it: all five abandon assertions.
3. **The abandoned run names the offending application.** `tasks.md` 1.9 says
   the unresolvable-Compose and malformed-reference reports name the
   application; the delta says only "report that condition". Asserted as the
   literal string `alpha` / `beta` appearing in the report. Depends on it:
   `Assert an unrenderable Compose file abandoned the whole run…` and `Assert a
   malformed rendered reference abandoned the whole run…`.
4. **Nothing else about abandon-report wording is asserted.** The three
   `abandon-paths` reports are held only to being non-empty, pairwise distinct
   and free of `considered` — deliberately, so that a correct implementation
   choosing different phrasing is not failed for it, while an implementation
   that collapses two branches into one report still goes red.
5. **The report may go to stdout or stderr.** Every report assertion reads the
   concatenation of both.
6. **The unit and timer are named `prune-host-images.service` / `.timer`**, and
   the script is at `/usr/local/bin/prune-host-images`. Both from `tasks.md`
   1.4/1.10/1.11; the delta names neither. The unit *files* are located through
   `systemctl show --property=FragmentPath`, so the installation directory is
   **not** assumed.
7. **`TimeoutStartSec=` is asserted as `<digits>` optionally suffixed `s`, `m`
   or `min`.** `TimeoutStartSec=infinity` deliberately does not satisfy it — it
   is not a bound. `tasks.md` 1.10 says "order of minutes, not seconds"; no
   specific value is asserted.
8. **`OnCalendar=` carries a literal `UTC`, and `RandomizedDelaySec=` is
   present.** From `tasks.md` 1.11; the delta requires neither.
9. **A converge with `deploy_apps: []` still writes the enumeration file,
   empty.** Required for `abandon-paths` arrangement 1 to be distinguishable
   from arrangement 2 at all. Consistent with `tasks.md` 1.2 and 1.3, which
   accept an empty list and template unconditionally.
10. **The enumeration file's exact contents and location.**
    `/etc/prune-host-images/apps`, one bare name per line, from `tasks.md` 1.3.
    Also asserted to contain no `ssh-`, `public_key` or `name` substring — the
    raw-mapping render `tasks.md` 1.3 names as the silent failure.
11. **Fixture naming.** `imgprune-fixture/*` is a Docker Hub namespace that
    exists nowhere and is never pushed to or pulled from;
    `localhost:5000/imgprune-fixture/pinned` is the scenario's own in-instance
    registry serving a locally built image. No fixture points at a real GHCR or
    Docker Hub package of this project's (`tasks.md` 2.3), and the registry
    image is carried in from the controller rather than pulled by the instance
    (`tasks.md` 2.5).
12. **Four fixture applications** — `alpha`, `beta`, `retiree`, `undeployed`.
    `tasks.md` enumerates the *cases*, not the application names.
13. **The `default` scenario runs the script directly for its report and
    exit-status assertions, and exercises the installed unit separately.**
    Reading `journalctl` inside a Molecule container was not relied on; the unit
    is instead proven by `systemctl start` plus `systemctl show -p Result
    -p ExecMainStatus`, once on the happy path (`default`) and once on an
    abandoning host (`abandon-paths`).

**Deliberately untested** — the seven entries under "Deliberate non-coverage",
each with its reason recorded there and in a comment block at the head of the
scenario that would otherwise have held it.

## Mutation testing — PERFORMED, 2026-09-08

Mapped by the test-derivation pass (`tasks.md` 2.8, which could not run the
round: there was no implementation to mutate at `08954be`, and writing one
would have been writing the code under test). **Run by the implementation step
(`tasks.md` 3.2), and all ten guards are confirmed.**

Each guard was deleted or inverted in
`ansible/roles/image_prune/tasks/main.yml`, a full `molecule test -s <scenario>`
run — `verify` is destructive, so a re-verify against an already-pruned host
would prove nothing — the failing task recorded, and the file restored and
checked byte-identical (md5 `75a8e801c6344abc076a21c2330efae3`) after every
run. Driver and per-mutation logs are outside the repository, in the session
scratchpad.

**Two results are worth more than their row.**

*Mutation 1 was caught by a different assertion than predicted.* The prediction
was `Assert an enumeration naming no application removed nothing and failed`;
that assertion stayed **green**. With the guard deleted, an empty enumeration
falls through to the empty-keep-set guard, which still abandons, still exits
non-zero and still removes nothing — so every claim that assertion makes
remains true. What caught it was the *pairwise* distinguishability check, since
arrangement 1 then reports arrangement 3's condition. Had the scenario asserted
only "each branch abandoned", as the plan did until review round 5, this guard
could have been deleted with the suite green.

*Mutation 4 came back green the first time, and that was a defective mutation,
not a coverage hole.* The script has **two** `could not be rendered` call sites
— one after `config --profiles`, one after `config --images` — and the first
anchor matched only the second. The fixture's broken Compose file fails at
`--profiles` first, so the untouched guard fired and the run abandoned
correctly. Re-run as 4b against both call sites: **red**. A non-red mutation
means either "the guard is uncovered" or "the mutation did not remove the
guard", and those demand opposite responses; reading this one either way
without checking would have been wrong.

| # | Guard (`tasks.md` 2.8) | Mutation | Assertion that must go RED | Scenario | Result |
|---|---|---|---|---|---|
| 1 | The no-application-enumerated abandon | delete the guard, fall through | `Assert an enumeration naming no application removed nothing and failed` — the canary is removed and `RC 0` appears | abandon-paths | **RED** — but by `Assert the three abandon branches report three distinguishable conditions`, not the predicted assertion; see above |
| 2 | The absent-enumeration abandon | delete the guard, fall through | `Assert the three abandon branches report three distinguishable conditions` — with no containers here the mutated run falls to the empty-keep-set guard and reports **arrangement 3's** condition for arrangement 2's premise. It still abandons, still exits non-zero, still removes nothing, so only the pairwise comparison notices. **Do not add a container to this scenario to make a removal observable** — arrangement 3 requires there be none | abandon-paths | **RED** — `Assert the three abandon branches report three distinguishable conditions`, exactly as predicted |
| 3 | The empty-keep-set abandon | delete the guard | `Assert the empty-keep-set arrangement really is one, and removed nothing` — the canary goes | abandon-paths | **RED** — `Assert the empty-keep-set arrangement really is one, and removed nothing` |
| 4 | Abandon on an unrenderable Compose file | omit that application's contribution instead of abandoning | `Assert an unrenderable Compose file abandoned the whole run, removing nothing, and failed` — the canary goes and `alpha`'s own images become candidates | default | **RED** as 4b, once both call sites were mutated — `Assert an unrenderable Compose file abandoned the whole run, removing nothing, and failed`; see above |
| 5 | The malformed-reference rejection | treat a malformed reference as one resolving to no local image | `Assert a malformed rendered reference abandoned the whole run, removing nothing, and failed` — the canary goes and the run reaches `RC 0` | default | **RED** — `Assert a malformed rendered reference abandoned the whole run, removing nothing, and failed` |
| 6 | The all-profiles render | call `config --images` without enumerating and passing `--profiles` | `Assert an image referenced only behind an inactive profile was kept` — and **only** that one | default | **RED** — `Assert an image referenced only behind an inactive profile was kept` |
| 7 | The container-image contribution to the keep set | drop `docker ps -aq` / `docker inspect` from the union | `Assert both tags of an image a stopped container holds are still present` — one tag goes while the image survives on the runtime's refusal, so the *image* assertions stay green. This is why that fixture carries two tags | default | **RED** — `Assert both tags of an image a stopped container holds are still present` |
| 8 | Removal by tag rather than by ID | remove by ID unconditionally | `Assert an unreferenced two-tag image was removed through each of its tags` — the runtime refuses with "must be forced" and all three references stay present | default | **RED** — `Assert an unreferenced two-tag image was removed through each of its tags` |
| 9 | `--no-trunc` on the local enumeration | drop it | The 12-character IDs never compare equal to the full IDs the keep set holds, so every local image becomes unreferenced: `Assert an image only one enumerated application references was kept by the union`, `…defined service…`, `…inactive profile…`, `…digest-pinned image…` and `Assert the completed run reported both counts…` all go red | default | **RED** — `Assert the superseded tag of the base repository is gone and the referenced one remains` |
| 10 | The absence of `-f` | add `-f` to the removals | `Assert an image a stopped container holds was kept and its container still holds it` (behavioural) **and** `Assert the script consults no age criterion and never forces a removal` (static) | default | **RED** — `Assert the script consults no age criterion and never forces a removal` |

## One assertion corrected during implementation, 2026-09-08

`Assert the converge armed the timer and executed no prune` read
`ExecMainStartTimestamp` and `ActiveEnterTimestamp` and expected `[]` for a
unit that has never run. On systemd 249 (the scenario's own image) those
properties read `n/a`, not empty, so the assertion failed against an
implementation that was behaving correctly: the timer was armed, the service
inactive, and `GONE-SINCE-CONVERGE` empty.

It was **not** widened to accept both spellings. Both properties are now read in
their `…Monotonic` form, which is `0` for a never-started unit on every systemd
version. That asserts the property rather than one version's spelling of it, and
still fails if the service ever runs during a converge — strictly stronger than
what it replaced.

This assertion had never executed before: the derivation pass's run stopped at
the first check for an installed artifact, and fail-fast hid everything after
it.

## Obsolete tests

**Not applicable, and the reason is the change's own shape**: the delta carries
one `ADDED` requirement and no `MODIFIED`, `REMOVED` or `RENAMED` operation, so
no existing test can have been superseded by it. No search for bearing tests was
performed, and none was needed.

Two related notes, neither of them an obsolete test:

- **Nothing existing was edited, deleted or disabled.** This pass added eight new
  files under `ansible/roles/image_prune/molecule/` and this file, and touched
  nothing else. The existing `iac-host-configuration` requirement "Superseded
  Application Images Are Reclaimed at Deploy Time" is explicitly *not*
  superseded by this change (proposal.md's Impact section), and the tests
  covering it in `ansible/roles/deploy_user/molecule/default/verify.yml` remain
  correct and were not read for content beyond their idiom.
- The predecessor change's `test-plan.md` records that its "An untagged image in
  the namespace is left alone" scenario was left uncovered pending any
  application adopting a digest pin, with **"REVISIT IF ANY APPLICATION EVER
  ADOPTS A DIGEST PIN"** written into that scenario's own `verify.yml`. This
  change does not adopt one in production, so that note is not yet triggered —
  but it is the nearest thing to a bearing test, and it is recorded here rather
  than left to be rediscovered.

## Unresolved project questions

Recorded rather than resolved: this pass ran as a dispatched subagent with no
channel to ask on, and neither `AGENTS.md` nor the change's artifacts settle
these.

| Question | Assumption taken | Tests that depend on it |
|---|---|---|
| How is the completed run's report spelled? | `tasks.md` 1.9's `considered N, removed M`, matched case-insensitively | `Assert the completed run reported both counts, deduplicated by identity, and exited zero` |
| How is an abandoned run's report spelled? | Left open. Only asserted: non-empty, pairwise distinct across branches, free of `considered`, and — for the two `default` branches — naming the application | all five abandon assertions |
| Does the report go to stdout or stderr? | Either; both are read, concatenated | all report assertions |
| Where does the role install the unit files? | **Not assumed** — resolved through `systemctl show --property=FragmentPath` | `Assert the unit, timer and script were installed where the role says` and the three static reads |
| What value does `TimeoutStartSec=` take? | Any `<digits>[s\|m\|min]`; `infinity` deliberately excluded | `Assert the schedule is the init system's and the service is a bounded oneshot` |
| Does a converge with `deploy_apps: []` still write the enumeration file? | Yes, empty | `Assert the converge wrote an enumeration that names no application`, and with it arrangement 1 |
| Does the run remove the build base `alpine:3.19` outright or merely untag it? | Left open; no assertion reads it | — |
| Is a four-application fixture set acceptable where `tasks.md` enumerates cases and not names? | Yes | every `default` assertion |
| Is running the script directly (rather than through `journalctl -u`) acceptable for the report assertions? | Yes, with the unit exercised separately through `systemctl start` on both a completed and an abandoning run | scenarios 20 and 21 |

## Findings the implementation step should know

1. **`.ansible-lint`'s `mock_roles` must gain `image_prune`.** Every role
   referenced by name needs an entry there — ansible-lint does not resolve role
   references via `ansible.cfg`'s `roles_path`, which is why `docker`,
   `deploy_user` and the rest are already listed. Without it,
   `ansible-lint ansible/` reports `syntax-check[specific]: The role
   'image_prune' was not found` against **both** new `converge.yml` files, and
   `pre-commit run --all-files` (`tasks.md` 3.2) fails. That file is outside
   this pass's write scope and was not touched. It will need the entry for
   `ansible/playbooks/host-baseline.yml` (`tasks.md` 1.12) regardless.

   With that aside, `ansible-lint ansible/` is otherwise **clean** over these
   files: the four other violations this pass introduced (a `run_once` on a
   single-host delegated task, an over-long line, and two
   `var-naming[no-role-prefix]` reports on `deploy_apps` in `include_role`)
   were fixed here. The two `noqa` markers on `deploy_apps` are deliberate and
   carry their reason inline: it is this role's one required *input*, named by
   the inventory and shared with `deploy_user`, so prefixing it would make it a
   different variable.

2. **An apostrophe in a shell comment breaks the task at load time.** See the
   trap note above. This cost this pass one full scenario run to diagnose.

3. **`converge` succeeds against a role with no tasks.** `ansible/roles/image_prune/`
   exists because it holds `molecule/`, so Ansible resolves the role name and
   runs nothing. A green `converge` is therefore not evidence the role works —
   only `verify` is.

4. **The registry image's digest is pinned in `prepare.yml`:**
   `registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373`
   (the multi-architecture manifest list for `registry:2`, read 2026-09-07).
   Refreshing it is manual and nothing warns you when it is stale — the same
   situation as the platform-image pin, and for the same reason (Dependabot
   scans Dockerfiles and Compose files, not these). It is **not** a molecule
   `platforms:` image, so `.github/tests`'s digest-agreement check does not see
   it.

5. **`docker compose` in the Molecule instance is v5.5.1**, against the host's
   v5.5.0 and design.md's locally-checked v5.4.0. The profile-omission behaviour
   the whole all-profiles render exists for was re-executed at v5.5.1 and holds
   (see "verified by hand" above), which closes the caveat design.md records.

6. **Both new scenarios take real time.** `default` builds thirteen images,
   runs a registry and pushes to it, on a nested `vfs` daemon. Budget minutes,
   not seconds, and remember that `molecule test --all` stops at the first
   failure — `abandon-paths` sorts first, so a red `abandon-paths` hides
   `default` entirely.
