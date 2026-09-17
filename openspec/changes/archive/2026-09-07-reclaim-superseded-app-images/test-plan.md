# Test plan — reclaim-superseded-app-images

Derived from `specs/iac-host-configuration/spec.md` (one `ADDED` requirement, 11 scenarios) ahead of the implementation, following `tasks.md` section 2.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files and has to be read on purpose. Read it before implementing `tasks.md` section 1.

Everything below was written without reading `ansible/roles/deploy_user/tasks/main.yml`. The delta is a pure `ADDED` requirement, so there is no superseded behaviour to establish and nothing in the existing script bears on what the tests assert.

## Where the tests are, and how to run them

One suite, one scenario. All tests are Molecule tasks appended to `ansible/roles/deploy_user/molecule/default/verify.yml` (from line 581; the first 580 lines are untouched).

```
cd ansible/roles/deploy_user && molecule test -s default
```

While iterating, `molecule converge -s default` then `molecule verify -s default` re-runs verify only, against a live instance.

**Provision first, or the command does not run at all.** A fresh working tree carries no Galaxy content, and this scenario converges the sibling `docker` role, whose `meta/main.yml` depends on `geerlingguy.docker`. Without it the run fails at the `syntax` action, before `converge`, with "The role 'geerlingguy.docker' was not found" — see the baseline below. `ansible-verify.yml` states the install, and `-p ansible/roles` is load-bearing (each scenario sets `ANSIBLE_ROLES_PATH` to `ansible/roles`, so a role in the default `~/.ansible/roles` is never found):

```
pip install -r ansible/requirements-test.txt
ansible-galaxy collection install -r ansible/requirements.yml
ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles
```

**Granularity.** Molecule's selectable unit is the scenario, not the assertion: there is no way to run one of these tests alone. Each is therefore identified below by its exact Ansible task `name`, which is what the run prints and what `--start-at-task` accepts. Every task added by this pass has a name beginning `Reclaim ` or `Assert `, and the block is contiguous at the end of the file.

The `.github/tests` suite (`python3 -m unittest discover --start-directory .github/tests`) is untouched and owes nothing here: its scope over this role is `ansible/roles/*/molecule/*/molecule.yml`, and this pass modified only `verify.yml`. Nothing in that suite reads `verify.yml` (checked).

## Baseline

Taken before writing anything, on the dispatched worktree at `e765879`, working tree clean.

| Run | Result |
|---|---|
| `molecule test -s default`, unprovisioned | **FAILED** at the `syntax` action — `geerlingguy.docker` not installed. Not a defect; a working tree carries tracked files only. |
| `molecule test -s default`, after `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles` | **GREEN.** 12 actions, 0 failed; `verify` play recap `ok=42 changed=0 failed=0`. |

This is a **scoped** baseline: the `deploy_user` role's `default` scenario, the only scenario this change touches. `molecule test --all` across every role was not run.

## Result of running the derived tests against the unimplemented change

`molecule converge -s default && molecule verify -s default`, on the worktree with these tests in place:

- Everything through the second deploy **executed and passed**: all four fixture images built (`docker build` with `DOCKER_BUILDKIT=0` works on the nested vfs daemon), the fixture self-check passed (four distinct image IDs, the stopped-container image carrying exactly one tag), both fixture deploys exited 0, `docker compose pull` skipped both fixture images on `pull_policy: never`, and Compose recreated the `app` container from tag A to tag B — freeing tag A.
- The run then **failed at `Assert the superseded tag is gone after the second deploy and the deployed tag remains`**, on `'ABSENT ghcr.io/reclaim-fixture/commerce-ops:fixture-tag-a'`. The deploy's own output carried no reclamation report of any kind.

That is failure state **"the target does not exist yet"**: it establishes that nothing in `app-deploy` reclaims anything today, and nothing more. Every assertion after this one was **not executed** — Ansible's `assert` fails the play at the first failure — so their evaluation is unverified and they will surface one at a time as the implementation lands. What *was* separately verified, by driving the remaining steps by hand inside the live instance (recorded here because the fail-fast hid them):

- the canary image builds;
- the degraded-reference-set deploy exits **0**, leaves `/opt/commerce-ops/docker-compose.yml` invalid, and makes `docker compose config --images` fail — so the fixture really does induce the condition its scenario is about, rather than passing vacuously;
- all three in-namespace images survive that deploy today (vacuously, since nothing reclaims — the canary is what makes it discriminating once reclamation exists).

Every Jinja expression in the report assertions (`regex_search` with a capture group, the `search` tests, the no-match sentinel) was exercised standalone against `ansible-core 2.21.3` before being committed to the file.

## Scenario accounting

11 scenarios in the delta, 11 accounted for: 8 covered, 2 uncovered with a reason, 1 covered in half with the other half's reason recorded.

| # | Delta scenario | Covered by (exact task name) | tasks.md |
|---|---|---|---|
| 1 | A deploy removes the image its predecessor left behind | `Assert the superseded tag is gone after the second deploy and the deployed tag remains` | 2.1 |
| 2 | The image the running containers use is never removed | `Assert every image the current Compose file references survived and its containers are running` | 2.1 |
| 3 | An image held by a stopped container is not removed | `Assert the unreferenced image a stopped container holds was not removed, and the container still holds it` | 2.4 |
| 4 | An image shared with another application is never a candidate | `Assert a second tag of a shared base-image repository survived the deploy` | 2.2 |
| 5 | Images published under a previous owner are reclaimed | `Assert an image under a previous owner segment but the same application name was reclaimed` | 2.3 |
| 6 | An unavailable or empty reference set reclaims nothing | `Assert a run that could not determine the reference set removed no image in the namespace` — **undeterminable half only**, see below | 2.5 |
| 7 | An untagged image in the namespace is left alone | **UNCOVERED**, deliberately — see below | 2.7 |
| 8 | A completed run reports what it did | `Assert the completed run reported how many images it considered and how many it removed` (removed-something) **and** `Assert the platform deploy, whose namespace is empty by design, still reported its counts` (found-nothing) | 2.1, 2.9 |
| 9 | A run that ends early says why | `Assert the early-exit run reported its reason, distinguishably from a completed run that found nothing` — **empty/undeterminable-reference-set half only**; the duration-bound half is uncovered, see below | 2.9 |
| 10 | A non-responding runtime does not hold the deploy open | **UNCOVERED**, deliberately — see below | 2.9 |
| 11 | A failed reclamation does not fail a successful deploy | `Assert a deploy whose reclamation could not remove an image still exits successfully with its containers up` | 2.6 |

Supporting tasks that assert nothing about the requirement but whose failure means the fixtures are wrong rather than the implementation: `Assert the first fixture deploy succeeded (precondition, not a scenario assertion)` and `Assert the four in-namespace fixtures are distinct images and the held one carries exactly one tag`.

### Uncovered, with reasons

**Scenario 7 — "An untagged image in the namespace is left alone."** Not covered, per `tasks.md` 2.7. The fixture it needs is an in-namespace image carrying no tag, which arises only from a repo digest — a real pull from a registry, which `tasks.md` 2.8 forbids on determinism grounds. "Tag then untag" does not substitute: it yields `<none>:<none>`, a fully dangling image, which is the proposal's *first* non-goal and outside every namespace by construction, so a test built that way would prove the wrong property while reading as though it proved this one. The property is held instead by the `:<none>` filter being visible in the script (`tasks.md` 1.5) and by review. Accepted on the operator's decision, 2026-09-07, against adding a digest-pinned local `registry:2` to the scenario: no application in this repository pins its own image by digest today, so the failure mode is currently unreachable. **Revisit if any application ever adopts a digest pin.**

**Scenario 10 — "A non-responding runtime does not hold the deploy open", and with it the duration-bound half of scenario 9.** Not covered, per `tasks.md` 2.9. Wedging a container daemon inside a Molecule container is not reproducible without breaking the same daemon the preceding `docker compose pull` needs. Held by the `timeout` being visible in the script (`tasks.md` 1.8) and by review.

**Scenario 6 — the "determined to contain no images" half.** Covered only via the undeterminable disjunct, and that is a finding rather than a choice. See "Findings" below: a Compose file declaring no services (or none outside an inactive profile) makes `docker compose up -d --wait` exit **1** with "no service selected", so the deploy fails and reclamation never runs at all. There is no fixture through this path that yields a successful deploy and an empty reference set. `tasks.md` 2.5 asks for the undeterminable half by name ("with `docker compose config --images` unable to produce a set"), which is what is covered. The empty half remains held by `tasks.md` 1.3's explicit early return and by review.

## Assertion classification

**Specified** — traces to a stated sentence of the delta requirement:

- the superseded tag absent / the deployed tag present (scenario 1);
- every image the Compose file references still present, containers still running (scenario 2);
- the stopped-container-held image still present (scenario 3, "the removal SHALL be refused … rather than being forced");
- the other tag of the shared base repository still present (scenario 4);
- the previous-owner image gone (scenario 5);
- no image in the namespace removed on an undeterminable reference set (scenario 6);
- `app-deploy` exits 0 after a refused removal, containers up (scenario 11);
- a completed run reports a considered count and a removed count (scenario 8);
- an early-exit run reports its reason and is distinguishable from a completed run that found nothing (scenario 9);
- the degraded deploy still exits 0 (scenario 6 + the requirement's non-interference sentence).

**Derived** — no stated requirement fixes these; they are recorded so the implementer can see what was invented rather than agreed:

1. **The report's wording.** The delta says a completed run reports "how many images it considered and how many it removed" and fixes no spelling. The assertions match the words `considered` and `removed` each followed by a number, case-insensitively, which is `tasks.md` 1.9's own line (`considered N, removed M`). Depends on it: tasks 17 and 24.
2. **The early-exit reason's wording.** Asserted as the phrase `reference set` appearing, case-insensitively. Depends on it: task 23.
3. **`considered` as the distinguishing marker.** The early-exit assertion requires `considered` to be *absent* from that run's output — that is what makes it distinguishable from a completed found-nothing run under `tasks.md` 1.9's shape. A different report design could satisfy the delta and fail this. Depends on it: task 23.
4. **`removed` counts successful removals, not attempts.** The second deploy asserts `removed == 2` (the superseded tag and the previous-owner image; the stopped-container image is refused). An implementation counting attempted removals would report 3 and fail. Depends on it: task 17.
5. **`considered` deliberately left un-pinned on the second deploy.** "Considered" admits both "candidates found" (3) and "namespace members enumerated" (4) and the delta settles neither, so only its presence as a number is asserted there. On the `platform` deploy both readings give 0, so `considered == 0` and `removed == 0` are asserted. Depends on it: task 24.
6. **The report may go to stdout or stderr.** Every report assertion reads the concatenation of both.
7. **A fifth fixture image.** `tasks.md` 2.8 enumerates four; a fifth (the canary) was added. Reasoning under "Findings".
8. **Fixture naming.** `ghcr.io/reclaim-fixture/commerce-ops` and `ghcr.io/reclaim-fixture-previous-owner/commerce-ops` are owner segments that exist nowhere. No fixture points at a real GHCR package, per `tasks.md` 2.8.

**Deliberately untested** — scenarios 7 and 10, and the two halves named above, each with its reason recorded in the table and in a comment block at the head of the added section of `verify.yml`.

## Obsolete tests

**Not applicable.** The change carries one `ADDED` requirement and no `MODIFIED`, `REMOVED` or `RENAMED` delta, so no existing test can have been superseded by it. No search for bearing tests was performed and none was needed.

Two related notes, neither of them an obsolete test:

- Nothing existing was edited, deleted or disabled. The first 580 lines of `verify.yml` are byte-identical to the dispatched state (verified by diff).
- Prose inside two existing artifacts becomes further untrue with this change — `molecule.yml`'s header and the `fail_msg` at `verify.yml` 84-90, both claiming an empty `services: {}` Compose file keeps `docker compose pull && up -d --wait` a success. `tasks.md` 1.10 already assigns updating them to the implementation step. This pass did not touch them (additive only), and the claim is now known false rather than merely loose — see "Findings".

## Unresolved project questions

Recorded rather than resolved: this pass ran as a dispatched subagent with no channel to ask on, and neither `AGENTS.md` nor the change's artifacts settle these.

| Question | Assumption taken | Tests that depend on it |
|---|---|---|
| How is the reclamation report spelled? | `tasks.md` 1.9's `considered N, removed M` on the completed path; a reason naming the `reference set` on the early-exit path. | 17, 23, 24 |
| Does `considered` mean candidates found or namespace members enumerated? | Left open where it matters; pinned only where both readings agree (0, on `platform`). | 24 |
| Does `removed` count successes or attempts? | Successes. | 17 |
| Does the report go to stdout or stderr? | Either; both are read. | 17, 23, 24 |
| Is a fifth fixture image acceptable, beyond the four `tasks.md` 2.8 enumerates? | Yes — without it scenario 6 cannot discriminate. | 22 |
| Is the "wrecker" fixture — a deploy whose own container corrupts the project's Compose file before reporting healthy — acceptable as the induction for an undeterminable reference set? | Yes; it is a real induction rather than a stub, and it was the only route found. | 22, 23 |

## Findings the implementation step should know

1. **`services: {}` does not keep `docker compose up -d --wait` a success.** Checked directly on 2026-09-07 against Compose v5.4.0: a Compose file declaring no services, and equally one whose only service sits behind an inactive profile, exits **1** with `no service selected`. `config --images` and `pull` both exit 0 on such a file; only `up` refuses. This closes the "reference set determined to be empty" route to a fixture (the deploy fails before reclamation runs) and it falsifies `molecule.yml`'s header claim and `verify.yml`'s `fail_msg` at 84-90 outright rather than loosely. `tasks.md` 1.10 already owns correcting both.

2. **A fifth fixture image was added, beyond `tasks.md` 2.8's four.** By the time the degraded run happens, every remaining member of the `commerce-ops` namespace is held by a container — the deployed tag by a running one, the stopped-container fixture by a stopped one — so a reclamation that ignored the empty/undeterminable guard entirely would still remove nothing, and scenario 6 would pass for the wrong reason. The canary (`…:fixture-canary`) is an in-namespace image that nothing holds and nothing references, built immediately before that deploy under the same ordering rule as the rest. It is what makes the assertion discriminating.

3. **The shared-base decoy has teeth because it is a `docker tag`.** `alpine:reclaim-decoy` shares an image ID with `alpine:3.19`, so a namespace filter wrongly widened to `alpine:*` would *untag* it successfully — Docker refuses only where removal would drop an image's last reference. A decoy built as its own image would have been protected by the running container instead and would have proved nothing about the filter.

4. **`DOCKER_BUILDKIT=0` is set on every fixture build**, up front rather than after a failure, because `prepare.yml` puts the nested daemon on `vfs` with `containerd-snapshotter` disabled. Confirmed working in the instance; the legacy builder prints a deprecation warning and succeeds. If a future Docker release removes the classic builder, `docker commit` over `docker create` from `alpine:3.19` is the fallback that preserves what `tasks.md` 2.8 actually needs — a distinct image ID carrying exactly one tag — where `docker tag` does not.

5. **Ansible's `regex_search` group spec is spelled differently by YAML scalar style.** In a folded (`>-`) scalar it must be `'\1'`; `'\\1'` reaches the filter as a literal `\\1` and raises `'NoneType' object has no attribute 'group'`, which reads like a failed match and is not. Verified against `ansible-core 2.21.3`. Relevant if these expressions are ever reformatted.

6. **The degraded deploy is deliberately last** — it leaves `/opt/commerce-ops/docker-compose.yml` invalid. A later `molecule verify` re-run is self-healing, because `deploy-receive` overwrites that file from the archive on the scenario's first deploy.
