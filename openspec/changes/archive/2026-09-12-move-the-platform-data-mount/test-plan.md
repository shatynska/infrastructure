# Test plan — move-the-platform-data-mount

Tests derived from this change's delta specifications by an author other than whoever implements it, before any implementation existed. The deltas were read at commit `f3c94cd`, the commit holding the approved plan.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among the context files `openspec instructions apply` lists, so it has to be read on purpose. Read it before implementing: it records what each new test asserts, what it does not, which existing tests the implementation must re-point, and the assumptions the tests took where the plan left a question open.

Nothing in this pass edited, deleted or disabled an existing test, and nothing in it wrote implementation. **This pass adds tests and never subtracts.**

## What was written

| Surface | Path | Runner |
|---|---|---|
| Molecule | `ansible/roles/platform_data_volume/molecule/superseded-path-retired/` | `ansible/scripts/run-molecule test -s superseded-path-retired`, from `ansible/roles/platform_data_volume` |
| Molecule | `ansible/roles/platform_data_volume/molecule/superseded-path-in-force-refused/` | `ansible/scripts/run-molecule test -s superseded-path-in-force-refused`, from the same directory |
| `.github/tests` | `.github/tests/test_the_platform_data_mount_moved.py` | `python3 -m unittest discover --start-directory .github/tests`, from the repository root |

Both Molecule scenarios are reached by `ansible/scripts/run-molecule test --all` from the role directory, which is what tasks.md 5.2 runs. `test --all` stops at the first failing scenario and lists no scenario sorting after it, so read the SCENARIO RECAP and confirm it names all six the role now has: `default`, `multiple-devices-discoverable`, `multiple-devices-reverse-order`, `no-device-discoverable`, `superseded-path-in-force-refused`, `superseded-path-retired`.

### Two Molecule scenarios, where tasks.md 3.2 asks for one

tasks.md 3.2 frames the retirement as four limbs of a single scenario. Three of them are in `superseded-path-retired`; the fourth — a declaration naming the path in force — is a scenario of its own, and the reason is the delta's own wording. It requires the run to fail "before any task that changes the host has run", and that is observable only against a host nothing has yet changed. In a scenario that has already converged the role, the mount, the mount-point directory and the filesystem all exist before the refusal is ever attempted, so the ordering could not be told apart from a refusal arriving after the mount — which is precisely what the requirement forbids and what design.md Decision 3a names as the catastrophic case. Splitting it buys three independent host-state reads (`blkid` finds no filesystem, the mount-point directory does not exist, `/etc/fstab` names neither spelling) that the combined form could not make at all.

## Baseline

Taken before any test was written. **Scoped**, and this is its scope:

| What | Command | Result |
|---|---|---|
| The whole static suite | `python3 -m unittest discover --start-directory .github/tests`, from the repository root | **864 tests, green**, 23s |
| Every Molecule scenario of `platform_data_volume` | `ansible/scripts/run-molecule test --all`, from `ansible/roles/platform_data_volume` | **exit 0**; SCENARIO RECAP named all four scenarios the role then had, `failed=0` on each |

The namespace was brought to this project's initial state first — `ansible/scripts/run-molecule destroy --all` from the role directory, and `.molecule-home/tmp/` removed — as AGENTS.md's shared-service rule requires.

**Not baselined, with the reason:** `ansible/roles/swap`. No test this pass wrote bears on that role; its `molecule/default/verify.yml` appears below only as an obsolete-test candidate, because it carries the superseded path as a literal. Whoever implements task 2.5 should run it before and after that edit.

## Scenario accounting

Thirteen `#### Scenario:` blocks across the two delta specs; thirteen accounted for.

### `iac-host-configuration` — *Platform Data Volume Is Mounted at a Fixed Host Path* (MODIFIED)

The delta is purely additive against the requirement as it stands under `openspec/specs/`: four paragraphs of normative prose and four scenarios are added, and **not one word of the five existing scenarios changes**. That is why the first five below owe no new test.

| # | Scenario | Covered by | Note |
|---|---|---|---|
| 1 | Volume is mounted at a known path | existing `molecule/default` (`Assert the data volume is mounted at the fixed path, on the expected device and filesystem`); additionally, at the new path, by `superseded-path-retired`'s `Assert the device is live-mounted at the fixed path in force` | text unchanged |
| 2 | Mount survives a reboot | existing `molecule/default` (the `/etc/fstab` entry and the `umount` + `mount -a` proxy); additionally by `superseded-path-retired`'s `Assert the fixed path in force is what the host mounts at boot` | text unchanged |
| 3 | Dependent subdirectories exist before a service needs them | existing `molecule/default`; **and newly**, for the half nothing read before — that the stack binds a path the role actually mounts — `test_the_platform_data_mount_moved.TestEveryHostVolumeBindLiesUnderTheMountTheRoleEstablishes` | text unchanged; the static half is what `docs/change-queue.md` entry 62 suspended |
| 4 | No device is supplied and none can be discovered | existing `molecule/no-device-discoverable` | text unchanged; no new test |
| 5 | More than one candidate device is attached | existing `molecule/multiple-devices-discoverable` and `multiple-devices-reverse-order` | text unchanged; no new test |
| 6 | A superseded mount path is declared | **new** — `superseded-path-retired`: `Assert no active /etc/fstab entry still names the superseded path`, `Assert the fixed path in force is what the host mounts at boot`, `Assert the device is live-mounted at the fixed path in force` | |
| 7 | No superseded mount path is declared | **new** — `superseded-path-retired`: `Assert an empty superseded declaration changed nothing about /etc/fstab` (the first form: no path declared at all), and Molecule's own `idempotence` action (the second form: a host whose superseded paths have already been retired, which under design.md Decision 3 is every converge after the first) | |
| 8 | A path is declared superseded and is also the path in force | **new** — `superseded-path-in-force-refused`, all six assertions, over both spellings | |
| 9 | A running service still holds the superseded path | **new** — `superseded-path-retired`: `Assert the live mount at the superseded path was not disturbed`, `Assert the process holding the superseded path still holds it`, and `Assert the superseded path was genuinely held, so the converge faced a busy target` | |

### `iac-safety-hardening` — *No Store on This Host Holds Data Requiring Backup* (MODIFIED)

The delta changes exactly two characters' worth of content: the path literal in two rows of the dated store table. No scenario's text changes, and no obligation changes. **This requirement owes no new test**, and that is a judgment rather than an omission — each of its four scenarios is recorded below with the reason.

| # | Scenario | Accounted for as | Reason |
|---|---|---|---|
| 10 | A persistent store is added to the host | covered by existing tests; **uncovered by this pass** | Already asserted by `test_ci_configuration.TestEveryPersistentStoreTheStackDeclaresIsClassified`-family checks over `CLASSIFIED_STACK_STORES`. Those carry the superseded path as a key, so the implementation must re-point them (see the obsolete list); if it re-points `platform/docker-compose.yml` and forgets, the existing census goes red on an unclassified store, which is the signal working as designed. |
| 11 | A store's stated reason ceases to hold | covered by existing tests; **uncovered by this pass** | The properties the reasons rest on — Prometheus's retention flags, Grafana's provisioning — are untouched by this change. |
| 12 | An application asks for durable storage on this host | **uncovered** | It states what an application SHALL be directed to do. There is no committed file whose static read decides it and no role behaviour that exhibits it, so it is outside both test surfaces this change owes. Unchanged by this delta. |
| 13 | The stated divergence is not a precedent | **uncovered** | Same: it constrains how a future proposal is read, not what any file or host does. Unchanged by this delta. |

## What each new test asserts, and its provenance

Per-assertion classification is written beside each assertion in the files themselves; this is the summary.

### `superseded-path-retired`

| Assertion | Provenance |
|---|---|
| `/etc/fstab` was read and reduced to at least one active entry | **DERIVED** — a premise check, added after the defect recorded below |
| No active `/etc/fstab` entry names the superseded path | **SPECIFIED** — scenario 6's `THEN` |
| The fixed path in force is in `/etc/fstab`, on the expected device and filesystem | **SPECIFIED** — scenario 6's first half |
| The device is live-mounted at the fixed path in force | **SPECIFIED** — scenario 1, at the path this change moves to |
| The live mount at the superseded path was not disturbed | **SPECIFIED** — scenario 9 |
| The holding process survived with its working directory intact | **SPECIFIED** — scenario 9's "nor otherwise interrupt that service's access" |
| The marker written through the superseded path reads back through the fixed one | **DERIVED** — no scenario states it. It establishes that the fixture is the one design.md Decision 2 requires: one device at two mount points, rather than two directories that merely look alike |
| An empty superseded declaration changed nothing about `/etc/fstab` | **SPECIFIED** — scenario 7 |
| The superseded path was busy throughout | **DERIVED** — it establishes that the fixture presented the case scenario 9 is about. Without it, a role that unmounted the path would be reported compliant by a scenario whose premise never held |

The fixture's own choices — `/dev/loop90`, the 512M sparse backing file, the `sleep` process with its working directory on the mount, the `prometheus/holder-marker.txt` marker — are this scenario's, not the specification's.

### `superseded-path-in-force-refused`

| Assertion | Provenance |
|---|---|
| Both spellings were refused rather than converged | **SPECIFIED** — scenario 8's "SHALL fail", and its prohibition on resolving the case by exclusion |
| Both refusals came from an `assert`, not from a task that acts on the host | **SPECIFIED** — scenario 8's ordering clause |
| Each diagnostic names the colliding path | **SPECIFIED** |
| Each diagnostic names `platform_data_volume_mount_path` and `platform_data_volume_superseded_mount_paths` | **SPECIFIED** that it names "both inputs it was read from"; **DERIVED** that the two tokens are those variable names — see the project questions below |
| No filesystem was created on the device | **SPECIFIED** — the ordering clause, keyed to the role's first host-changing task |
| The mount-point directory was never created | **SPECIFIED** — same clause, keyed to the second |
| Nothing was mounted and neither spelling reached `/etc/fstab` | **SPECIFIED** — same clause, keyed to the third |

### `.github/tests/test_the_platform_data_mount_moved.py`

Every assertion in this module is **DERIVED** except the containment check's subject, which traces to scenario 3. The module's own docstrings carry each one's classification. The two propositions are design.md Decision 5's, and tasks.md 3.3 and 3.4 state them.

## Discriminators, and what a green run of the static module establishes

The static module is a check that does not execute the behaviour it asserts: a pass reports that the committed files could be read and agree, never that any host is mounted anywhere. Two consequences were discharged inside this pass rather than left to whoever reads a green suite later.

**The containment check is green over the tree as it stands today** — the role default and the compose sources both name the superseded path, so they agree — and it will be green again after the change lands, because both move together. A check in that position passes identically when it asserts nothing. Six fixture-driven discriminators supply their own material and establish that it does not:

- `TestTheContainmentCheckDiscriminates.test_a_stack_binding_the_superseded_path_is_reported` — the one the check stands or falls on. `/mnt/main` is a proper string prefix of `/mnt/main-data`, so a `startswith` implementation passes this fixture and is vacuous.
- `...test_moving_the_role_default_alone_is_reported` — the other direction, so the two literals are held to each other rather than to a constant.
- `...test_a_stack_binding_under_the_path_in_force_is_not_reported` — the converse, so the check is not satisfied by reporting everything.
- `...test_the_runtime_observation_mounts_are_out_of_reach_by_construction` — the ten host observation mounts, none of which is enumerated anywhere in the module.
- `...test_a_role_default_that_cannot_be_read_is_a_failure_not_a_pass`.
- `TestEveryHostVolumeBindLiesUnderTheMountTheRoleEstablishes.test_the_committed_stack_declares_at_least_one_host_volume_bind` — the premise, over the committed tree.

All six were run and all six pass.

**The sweep is red at authoring**, on the property it exists to assert, which is the other way a check of this kind establishes that it discriminates. It reports 18 occurrences across 9 files (below). Eight further discriminators exercise its exemptions over scratch trees — the line-scoped declaration exemption, an indented declaration, indented prose, prose beside a declaration in one file, a block-sequence declaration (not exempt, by design), the `.github/tests/` prefix, the whole-path exemption and its expiry, and a tree it can read nothing in. The `openspec/` prefix exemption cannot be exercised on a scratch tree — the walker that reads one prunes `openspec` itself — so it is established over the repository instead, by `test_the_openspec_tree_names_the_path_and_is_not_reported`, which asserts both halves: that the tracked `openspec/` tree does name the path, and that the sweep reports none of it.

## Baseline-relative results of the derived tests

Run after writing, against the role as it stands with no implementation.

| Test | Result | Which failure state |
|---|---|---|
| `test_the_platform_data_mount_moved` — 18 of 19 tests | **pass** | the discriminators and the containment check |
| `...TestNoCommittedFileStillNamesTheSupersededMountPath.test_no_committed_file_names_the_superseded_mount_path` | **fail** | the code ran and produced a wrong value: 18 occurrences in 9 committed files. Goes green when tasks 2.1–2.6, 3.1, 3.5 and 4.1 land |
| Whole static suite | **883 tests, 1 failure** — the sweep, above | the other 882 are the baseline's 864 plus this module's 18 passing |
| `superseded-path-retired` | **fail at `Assert no active /etc/fstab entry still names the superseded path`** | the code ran and produced a wrong value. `create`, `prepare`, `converge` and `idempotence` all succeeded; the host ended the converge with **both** paths in `/etc/fstab` — `['/dev/loop90 /mnt/main-data ext4 defaults 0 0', '/dev/loop90 /mnt/main ext4 defaults 0 0']`, which is the two-paths-at-boot defect this change exists to prevent, exhibited live |
| `superseded-path-in-force-refused` | **fail at `Assert both self-defeating declarations were refused rather than converged`** | the code ran and produced a wrong value: the role converged a declaration naming the path in force |

**Two things a reader of those two red runs should not over-read.** An Ansible verify playbook stops at its first failing assertion, so in `superseded-path-retired` only the premise check and the first assertion have executed; everything after it — the live mount, the holder, the marker, the empty declaration, the busy check — is written but not yet exercised, and will first run when the implementation gets past the first. And the converge and `idempotence` actions passing establishes something useful on its own: **ext4 accepted a second mountpoint for a device already mounted**, which design.md Decision 2 names as the one mechanically uncertain step in the forward run, and `converge.yml` is idempotent as written.

## State this pass left behind

The Molecule namespace for this working tree was destroyed after every run; `docker ps -a` shows no container carrying it. `.molecule-home/` remains inside the tree and goes with it. The two loop-device associations noted above are the exception, for the reason given there.

## Obsolete-test candidates

**Candidates for human confirmation, every one of them.** None was edited, deleted or disabled by this pass, and none should be deleted: each carries the superseded path as a literal and needs **re-pointing**, not removal. The superseding delta is the same for all — `iac-host-configuration`'s MODIFIED *Platform Data Volume Is Mounted at a Fixed Host Path*, whose fixed path this change moves, and for the last two `iac-safety-hardening`'s MODIFIED *No Store on This Host Holds Data Requiring Backup*, whose table identifies two stores by path.

The search was bounded to the dispatched test-path globs — `ansible/roles/<name>/molecule/<scenario>/` and `.github/tests/*.py` — and was performed as a literal search for the superseded path within them. No earlier `test-plan.md` was supplied to this pass as a scenario-to-test index.

| Test | Evidence | Task that re-points it |
|---|---|---|
| `ansible/roles/platform_data_volume/molecule/default/converge.yml:27,54` | `platform_data_volume_mount_path: /mnt/main-data` in `vars:`, and the interface comment above it | 3.1 |
| `ansible/roles/platform_data_volume/molecule/default/verify.yml:16` | the same variable, redeclared for the verify play | 3.1 |
| `ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/verify.yml:43` | the same variable | 3.1 |
| `ansible/roles/swap/molecule/default/verify.yml:48,49` | `swap_forbidden_prefix: /mnt/main-data`, and the comment above it deriving that value from `platform_data_volume`'s defaults | 2.5 |
| `.github/tests/test_ci_configuration.py` — `CLASSIFIED_STACK_STORES` keys `/mnt/main-data/prometheus` and `/mnt/main-data/grafana`, and the fixture at the `uploads` service naming `/mnt/main-data/uploads` | the keys are compared against the stores `platform/docker-compose.yml` declares, so re-pointing the compose file alone turns them red | 3.5 |
| `.github/tests/test_a_second_environment.py` | names the superseded path and carries the entry-64 commitment in prose | 3.5 |
| `.github/tests/test_a_stack_and_its_environment_are_named_separately.py` | explains why the volume's name and the mount path differ | 3.5 |

**Where no bearing test was found, said explicitly.** Nothing in either test-path glob bears on the four *new* scenarios — no such test exists, rather than none having been found: the role has no superseded-path input today, so nothing could have asserted anything about retiring one. And the three `.github/tests` modules above sit inside this sweep's own exempt prefix, so **the sweep will not catch a miss in any of them**; they are read by eye. The same holds of `terraform/stacks/main-staging/terraform.tfvars`, which names entry 64 without naming any path — outside the test-path globs entirely, and named here only because tasks.md 2.6 already says so.

## Unresolved project questions

Each is an assumption this pass took where the convention files and the plan did not settle it. None was resolved silently.

1. **The tokens a refusal's diagnostic must contain.** The delta says the message names "both inputs it was read from"; it does not say by what name. The assumption taken is the two variable names, `platform_data_volume_mount_path` and `platform_data_volume_superseded_mount_paths`, which is what tasks.md 1.2 and design.md Decision 3 use. *Depends on it:* `superseded-path-in-force-refused`'s `Assert each diagnostic names the path and both inputs it was read from`. If the implementation words the message differently, that assertion is what to reconcile — by agreeing on the wording, not by dropping the assertion.

2. **The variable name and shape of the new input.** `platform_data_volume_superseded_mount_paths`, a list, defaulting to `[]`. It is design.md Decision 3's, not the specification's — the delta deliberately states the obligation without naming an input. Both new scenarios declare it, and the sweep's line-scoped exemption is keyed on that exact key text. *Depends on it:* both scenarios, and `SUPERSEDED_DECLARATION_KEY` in the static module. A different name means editing all four places.

3. **The fixed path in force is hardcoded `/mnt/main` in the new scenarios** rather than read from the role's defaults. Deliberate: the retirement obligation is about the relationship between two paths, and a scenario written against whatever the default happens to be would test the default rather than the relationship. *Consequence:* if the implementation chooses a different new path, these two scenarios need their literal changed — which the static containment check, reading the default, does not.

4. **Loop device minors 90 and 91.** `losetup` associations are kernel-global, and 87, 88 and 89 are taken by this role's existing scenarios. A CI host whose kernel already holds 90 or 91 is a fixture flake, not a defect in the role. This is the same unresolved question the `add-platform-monitoring` change recorded for `/dev/loop87`; nothing in this pass had the authority to fix the class, which needs a repository-wide decision about fact caching between `prepare` and `converge`. Note that a `losetup` association outlives the container that made it — after these runs the machine shows `/dev/loop90` and `/dev/loop91` associated with backing files that no longer exist, exactly as it already showed 87, 88 and 89 from this role's existing scenarios. That is the established behaviour rather than something these scenarios introduce, and `destroy` does not reclaim it.

5. **Where a sweep of this shape lives, and what a new module in `.github/tests` is called.** design.md Decision 5 says "a module of this change's own", following the sweep in `test_terraform_stacks_are_the_iterated_unit.py`; the repository records no naming convention for such a module. `test_the_platform_data_mount_moved.py` was chosen to read like its siblings. Nothing depends on the name except the runner lines quoted above.

6. **Importing `_under` across modules in the suite.** design.md Decision 5 names that helper explicitly and the suite's own rules permit a module importing a sibling; no convention says whether an underscore-prefixed helper may cross a module boundary. It is imported rather than restated, because two copies of a containment rule is exactly how one of them drifts.

## A defect found in this pass's own tests, and fixed inside it

Recorded because it explains a premise check that would otherwise look like padding, and because it is the failure mode this manifest's readers are most likely to reproduce.

The first draft of both verify playbooks reduced `/etc/fstab` with `(... | b64decode).split('\n')` inside a **folded** (`>-`) YAML scalar. YAML performs no escape processing in a folded scalar, so the two characters backslash-n reach the template as themselves, nothing ever matches, and the whole file comes back as a single element. The reduction was empty, and `Assert no active /etc/fstab entry still names the superseded path` **passed** — against a host carrying the superseded entry, which is the exact state it was written to catch. It was caught because the assertion after it failed with `entries: []`.

Both files now use `splitlines()`, which is correct in either scalar style, and both carry a premise check that the reduction is non-empty, so an empty reduction fails loudly instead of satisfying every absence assertion vacuously. The sibling scenarios that use `split('\n')` are unaffected: they do it inside a double-quoted scalar, where YAML unescapes it first.
