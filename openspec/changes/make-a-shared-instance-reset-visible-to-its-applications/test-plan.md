# Test plan

Derived from this change's approved delta specifications, at commit `2225b9c`, by an author who has not read and will not write the implementation. Everything here was written before any part of the change existed on disk.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files and has to be read on purpose. Read it before implementing: it records which test covers which scenario, which assertions are the author's invention rather than the specification's, what is deliberately left uncovered, and which fixtures look gratuitously specific and are not.

## Where the tests are

| Row of AGENTS.md's table | Command | What was added |
|---|---|---|
| The behaviour of an Ansible role on a host | `ansible/scripts/run-molecule test --all`, from `ansible/roles/deploy_user` | One new scenario, `ansible/roles/deploy_user/molecule/probe-and-window/` (`molecule.yml`, `prepare.yml`, `converge.yml`, `verify.yml`) |
| A static read of a committed file | `python3 -m unittest discover --start-directory .github/tests`, from the repository root | One new module, `.github/tests/test_a_shared_instance_reset_is_visible.py` (29 tests) |

**Nothing existing was edited, deleted or disabled.** The pass is additive only. The three existing `deploy_user` scenarios (`default`, `ghcr-credential-absent`, `ghcr-credential-rejected`) and all 26 existing `.github/tests` modules are untouched.

**The new scenario's name sorts after every existing one, deliberately.** `molecule test --all` runs a role's scenarios in sorted order and stops at the first failure, so a new scenario sorting before `default` would leave every existing one neither executed nor listed in the SCENARIO RECAP for as long as this change is red.

### Selecting one test

Molecule's smallest selectable unit is the scenario; within it, each task carries a unique name, quoted below.

    ansible/scripts/run-molecule test -s probe-and-window     # from ansible/roles/deploy_user

A single static test is selectable by its dotted name, with the suite directory on the path:

    PYTHONPATH=.github/tests python3 -m unittest \
      test_a_shared_instance_reset_is_visible.TestTheWindowDeclarationHasOneFixedPath.test_the_role_the_role_readme_and_the_runbook_all_name_it

## Baseline

Taken before any file in this pass was written.

- **Static suite — full.** `python3 -m unittest discover --start-directory .github/tests` from the repository root: **1285 tests, OK, 34.0s**. Nothing was failing beforehand. After this pass: 1314 tests, 6 failures, all of them this change's own target-absent failures (listed under *What is red today*).
- **Molecule — scoped, with the scope stated.** `ansible/scripts/run-molecule test -s ghcr-credential-absent` from `ansible/roles/deploy_user`: **exit 0, SCENARIO RECAP `failed=0`**. That is one of the role's three scenarios, chosen because it is the cheapest (it converges no container runtime) and because a green run of it establishes what the baseline is for — that the harness is provisioned in this working tree and that the role converges here. This tree's Molecule namespace is `make-a-shared-instance-reset-visible-to-4b4163`.
- **A full `--all` Molecule baseline was NOT taken, and the reason is recorded rather than the run being claimed.** AGENTS.md records that `--all` stops at the first failure, and this machine has previously had `--all` runs of this repository killed for memory. Running the other two scenarios individually would have been possible but buys nothing this pass needs: no test here edits them, and their result is established on every pull request by `ansible-verify.yml`.
- **The new scenario's own converge was run** — `ansible/scripts/run-molecule converge -s probe-and-window`: **exit 0, `failed=0`**. The role as it stands accepts the four-entry `deploy_apps` list carrying the new `probe_public_key` field, so the scenario's redness is its assertions and not its converge.
- **The scenario's PostgreSQL fixture was exercised on its own**, against that converged instance, by running `verify.yml`'s section 1 as a playbook of its own from the session's scratch directory — nothing was written into the repository to do it. **12 tasks, `failed=0`**: `postgres:18.6` starts inside the Molecule instance on the `vfs` storage driver, the roles, databases, schema and marker tables are provisioned, a throwaway client on `platform_edge` authenticates as `commerce-ops` and reads exactly one row, and `probe-denied`'s connection really does fail with `permission denied for database` and not with an authentication failure. That is what makes the six-token coverage below reachable at all, and it is established rather than assumed. Every container this pass created was then removed with `run-molecule destroy --all` from the role directory; `docker ps` names none of this tree's instances afterwards.
- `ansible-lint` over the new scenario directory: **Passed, 0 failures, 0 warnings**, profile `production`.

## Scenario accounting

Twenty-two `#### Scenario:` blocks across the three ADDED requirements. Each is accounted for exactly once below. The count is the check: 22 scenarios, 22 rows.

### `iac-host-configuration` — *An Application Can Probe Its Own Database Through a Read-Only Forced Command* (14 scenarios)

| # | Scenario | Covered by |
|---|---|---|
| 1 | A probe key can only probe its own application | Molecule: "Assert a role or database disagreeing with the forced command's argument refuses, and is not reported as any token"; "Assert each probe key's line carries restrict and a forced command naming only its own application"; "Assert each probe sudoers rule is the exact, fully-qualified, wildcard-free line for its own application"; "Assert sudo refuses app-probe for an application with no rule of its own". Static: `TestThePrivilegedHalfIsBoundToOneApplication` (3 tests) |
| 2 | A stopped instance is not reported as a destroyed database | Molecule: "Assert a stopped instance answers unreachable and never absent" (section 8, run last and deliberately so) |
| 3 | An unclassified failure is not resolved to the nearest token | Molecule: "Assert an unrecognised message from the instance, and a malformed or incomplete object, each refuse without a token" |
| 4 | A probe key cannot deliver or deploy | Molecule: "Assert an archive piped at a probe key delivers nothing and deploys nothing"; "Assert the database is still untouched after the delivery attempt" |
| 5 | A leaked probe key cannot be used to pivot into the host's network | Molecule: "Assert each probe key's line carries restrict and a forced command naming only its own application" — **proxy coverage; the live half is uncovered, see U1** |
| 6 | An absent role is told apart from a refused credential | Molecule: "Assert an absent role answers absent, and a wrong password against a present one answers credential-refused"; and again after a real reset in "Assert a destroyed database is reported as absent, and never as a refused credential" |
| 7 | A stale password is told apart from a reset instance | Molecule: "Assert an absent role answers absent, and a wrong password against a present one answers credential-refused" |
| 8 | An unreachable instance is not reported as a credential problem | Molecule: "Assert an instance that cannot be reached is not reported as a credential problem" (section 5) |
| 9 | A marker table that does not exist is an ordinary answer | Molecule: "Assert an unknown table is an ordinary empty, and a qualified name is resolved rather than refused" |
| 10 | A table name cannot execute anything | Molecule: "Assert no table name executed anything, at any layer"; the admissible-outcome limb in "Assert every phase-A case reached an outcome the requirement admits for it" |
| 11 | A schema-qualified table name is not refused for being qualified | Molecule: "Assert an unknown table is an ordinary empty, and a qualified name is resolved rather than refused" (two cases: `public.` and a non-public schema) |
| 12 | An oversized or unrecognised input object | Molecule: "Assert an oversized input object is refused without the probe having read it all" (both limbs, including *without having read it all*); the unknown-fields limb by case `unknown-fields-ignored` in "Assert every phase-A case reached an outcome the requirement admits for it" |
| 13 | An application that declares no probe key gets none | Molecule: "Assert an application declaring no probe key received no probe entry and no probe sudoers rule"; the *SHALL NOT fail* limb by the converge having completed at all, stated in that task's own message |
| 14 | The password never reaches a command line | Molecule: "Assert the password appeared in no process listing taken while the probe ran"; "Assert no shell history or other file under the deploy account's home carries the password"; "Assert an operand beyond the fixed argument is refused, with no token". **The `docker inspect` half is partial — see U4** |

### `iac-host-configuration` — *The Host Carries an Operator-Declared Maintenance Window for the Shared Instance* (4 scenarios)

| # | Scenario | Covered by |
|---|---|---|
| 15 | A declared window is reported to every application on that host | Molecule: "Assert every probe on the host answers window-open whatever stands beneath it" — four applications, over a **healthy** instance, whose answers with no window would be `populated`, `credential-refused`, `absent` and a refusal respectively; and again over an instance that has been removed entirely (section 6) |
| 16 | Raising and withdrawing the declaration needs no pipeline | Molecule: "Assert withdrawing the declaration is enough to stop the window being reported", read against the raise in "Raise the declaration as the operator account, with no sudo and no pipeline". Molecule runs exactly one converge per scenario and it has already happened, so *no converge in between* holds by construction |
| 17 | An operator can declare a window without sudo | Molecule: "Assert raising the declaration succeeded using only the capability the operator already holds"; "Assert no sudoers rule was added for raising or withdrawing the declaration"; guarded by "Assert the operator account has no sudo at all". **The account is a fixture — see U6** |
| 18 | The declaration survives the volume being discarded | Molecule: "Assert the declaration outlived the act it announces, and is still in force" (section 6) |

### `iac-platform-services` — *A Destructive Window on the Shared Instance Is Announced to the Applications That Hold Databases in It* (4 scenarios)

| # | Scenario | Covered by |
|---|---|---|
| 19 | A destructive procedure declares a window before its first destructive step | Static: `TestTheUpgradeRunbookAnnouncesTheWindowItOpens.test_the_procedure_declares_and_withdraws_the_window_in_the_right_order` — both limbs, read by position within the section rather than by step number |
| 20 | An application can determine that its database has ceased to exist | Molecule: "Assert a destroyed database is reported as absent, and never as a refused credential" (section 7, after a real discard-and-re-initialise). The third limb — *absence only from a reading that succeeded* — by "Assert a stopped instance answers unreachable and never absent" (section 8) |
| 21 | The announcement outlives what it announces | Molecule: "Assert the declaration outlived the act it announces, and is still in force" |
| 22 | Prose alone does not discharge the announcement | Static: `TestTheChecksDiscriminate.test_a_runbook_announcing_the_window_only_in_prose_is_caught` — the ordering check run over a fixture runbook whose only announcement is a sentence addressed to a human, which is the shape the procedure was in on 2026-09-15 |

## Normative prose accounted for

Several obligations in these requirements are stated in prose rather than in a scenario. A derivation reading only `#### Scenario:` headings would leave them to nobody, so they are enumerated and mapped here as scenarios are.

| Clause | Covered by |
|---|---|
| The input is a single JSON object on standard input carrying `password` and `table`, both required | Molecule: cases `missing-table`, `missing-password`, `not-an-object`, `malformed-json`, `empty-input` in "Assert an unrecognised message from the instance, and a malformed or incomplete object, each refuse without a token" |
| It MAY carry `role` and `database`, which SHALL equal the derived names | Molecule: case `agreeing-role-and-database` in "Assert a role or database disagreeing with the forced command's argument refuses, and is not reported as any token" |
| Unknown fields are accepted and ignored | Molecule: case `unknown-fields-ignored`, whose answer must equal the answer the same object without them gets |
| The input is size-bounded, and an oversized object refuses *without having been read in full* | Molecule: "Assert an oversized input object is refused without the probe having read it all" — fed over a FIFO that is never closed, so a probe that reads to end-of-input is killed by `timeout` and reports status 124, which is distinguishable from any refusal |
| No operand beyond the fixed argument | Molecule: "Assert an operand beyond the fixed argument is refused, with no token" |
| The probe writes to no database and creates, alters or drops nothing | Molecule: "Assert no probe wrote to, created, altered or dropped anything in the database" (a before/after read of the table set and the marker row count across every phase-A probe); "Assert the database is still untouched after the delivery attempt" |
| Exit zero when and only when a token is emitted; otherwise non-zero, no token, a diagnostic on stderr | Molecule: "Assert every probe exits zero when and only when it emitted a token" — asserted over **every** case at once, because the obligation is a biconditional over all of them |
| Exactly one token on standard output and nothing else | Same task (`stdout_lines | length == 1` on every token-emitting case) |
| `absent` is resolved without the application's credential | Molecule: cases `absent-unknown-password` and `absent-another-applications-password`, for an application for which no correct password exists anywhere; and section 7, where the credential that was correct before the reset still yields `absent` |
| `unreachable` precedes `absent`, and the precedence is not an evaluation order | Molecule: section 8, where the role and database really are gone AND the instance is unreadable — a probe evaluating `absent` first answers `absent` with a clear conscience |
| The table name is required to be an optionally schema-qualified identifier, and one outside that shape refuses rather than answering `empty` | Molecule: "Assert a table name outside the identifier shape refuses rather than answering empty" |
| The table name is never interpolated into a command string at any layer | Molecule: "Assert no table name executed anything, at any layer" — canaries checked on the host **and** inside the instance's own container |
| A probe public key is enumerated beside its deploy key, and the two are distinct | Static: `TestEveryProbeKeyIsDeclaredBesideItsDeployKeyAndIsADifferentKey` |
| The probe entry carries `restrict` and is bound to one invocation | Molecule: "Assert each probe key's line carries restrict and a forced command naming only its own application" |
| The declaration's location is a fixed, documented path | Static: `TestTheWindowDeclarationHasOneFixedPath` (two tests — that the three places name it, and that no committed file names a different one) |
| Ansible provisions what the declaration is held in, reachable by an account with no `sudo` | Static: `TestTheWindowDirectoryIsProvisionedForAnOperatorWithNoSudo` (root-owned, group `docker`, mode `0775`). Molecule: "Assert the declaration's directory was provisioned root-owned, group docker, mode 0775" |
| The declaration is evaluated by the **privileged** half | Molecule: "Assert the privileged half is where the window is evaluated" — `sudo app-probe` invoked directly while a window stands. An implementation answering `window-open` in `deploy-probe` passes every other window assertion and fails this one |
| A declaration left raised fails safe | Not separately asserted; it is the behaviour every `window-open` assertion already exercises, and its converse (a withdrawal being required to clear it) is "Assert withdrawing the declaration is enough to stop the window being reported". Recorded here so the absence of a test of its own is distinguishable from the absence of the thought |
| The means can be taken up by an application entitled to it (the contract is written down) | Static: `TestTheConsumerContractIsWrittenDown` |
| The converge itself declares no window | Molecule: "Assert the converge itself declares no window" — DERIVED, recorded below |

## Deliberately uncovered

Recorded with reasons, so that the absence of a test is distinguishable from the absence of the thought.

- **U1 — the live half of "A leaked probe key cannot be used to pivot into the host's network".** Refusing a port-forwarding, agent-forwarding, X11 or pty channel is OpenSSH's own enforcement of `restrict`, not this role's logic, and observing it needs a real SSH client, a real session and a real private key — none of which this scenario has, since it pipes at the scripts directly exactly as `default` does for the deploy key. The static proxy (that `restrict` is present on each probe entry) is what this role actually controls. `default`'s verify.yml takes the same position for the deploy key, and that change assigned the live half to a rollout step.
- **U2 — no test pins the literal stderr patterns the implementation matches on.** design.md decision 3 names `password authentication failed for user` and the connection-level messages. What is asserted instead is the behaviour against a **real** PostgreSQL instance emitting real messages, which is strictly stronger for the version under test and does not freeze an implementation detail. What it does not catch is a future `psql` changing its wording — but neither would a test pinning the pattern, which would go green against a probe that had stopped matching anything real.
- **U3 — `lc_messages` set to a non-English locale.** design.md decision 3 names it as a case that must refuse rather than guess. Inducing it means reconfiguring the fixture instance's locale and depending on a translation catalogue being present in the image, which makes the test's subject the image rather than the probe. The unclassified-error case (`permission denied for database`) exercises the same code path — a message matching neither pattern — from a condition the fixture controls exactly.
- **U4 — the `docker inspect` half of "The password never reaches a command line" is partial.** The throwaway client container is short-lived, so a sampling run that never captures it asserts nothing about `-e PGPASSWORD=...`. The assertion is written to read both sample files, but only the process-listing half carries a vacuity guard ("Assert the sampler really looked while the probe was running"), and only that half is load-bearing. A reviewer should read decision 7's third paragraph rather than relying on this.
- **U5 — delivering `commerce-ops`'s private key halves to that repository's Environments (tasks.md 4.3).** Outside this repository entirely; no test here can reach it, and none should.
- **U6 — that a real operator account holds the `docker` group.** The window scenario builds a fixture account holding exactly what `ops_user` grants and asserts the declaration is raisable with that and nothing more. Whether `ops_user` still grants the `docker` group and still writes no `sudoers.d` file belongs to that role's own scenarios, and asserting it here would duplicate them while coupling this scenario to a role it does not converge.
- **U7 — whether the consumer documentation's prose is any good.** The static check reads that each of the six tokens, the two required fields, the forced command and the probe keypair are named. Whether each token's meaning is stated correctly, whether the document says which of them should stop a delivery, and whether a reader meeting `absent` finds the `platform` exception are questions for review, and tasks.md 5.3 and 5.4 assign them there.
- **U8 — a second application actually calling the probe.** Outside this repository, by the requirement's own words: "Whether an application actually consults the announcement is that application's own decision."
- **U9 — the `deploy` account not being in the `docker` group.** design.md decision 2 requires it; `default`'s verify.yml already asserts that `deploy` cannot run `sudo docker` or an arbitrary privileged command, and this pass does not restate an existing test's content.

## Assertion provenance

Every assertion in both files carries its classification in a comment or docstring beside it. The ones that are **DERIVED** — invented by this pass or traced to `design.md`/`tasks.md` rather than to SHALL text — are collected here, because they are what a reviewer has to agree to:

- **The declaration's file name, `shared-postgres-window`.** The delta fixes that the path is fixed and documented and names the directory; the file name is design.md decision 5's. A test that raises a window cannot avoid naming it.
- **Mode `0775` rather than `0770`.** design.md decision 5's reasoning (world-readable so that reading the declaration does not depend on group membership).
- **The role-variable name `probe_public_key`**, the script paths `/usr/local/bin/app-probe` and `/usr/local/bin/deploy-probe`, the `sudoers` file name `/etc/sudoers.d/app-probe-<app>` and the exact grant line. `deploy-probe`'s path is the delta's own; the rest are tasks.md 3.7/3.8 and the existing deploy path's shape.
- **A three-part table name (`a.b.c`) refuses.** design.md decision 7's "one identifier, or two separated by a dot". The delta says "optionally schema-qualified" and stops.
- **`visudo` validation of the probe `sudoers` file.** tasks.md 3.8.
- **Every enumerated application declaring a probe key.** The requirement makes it OPTIONAL; tasks.md 4.1 names both entries in both files. If a later decision leaves one without a key deliberately, reconsider that assertion rather than repairing it.
- **The fixture image agreeing with the stack's pin.** tasks.md 1.5 and design.md decision 7; the delta fixes no image.
- **The six tokens appearing in the onboarding document in backticked form.** The spelling is this pass's, chosen because it is how this repository's documentation names such values; the requirement obliges the contract to be takeable up, not its typography.
- **"Assert the converge itself declares no window."** Nobody asked for it. A converge that raised a declaration would stop every application on the host delivering, silently and indefinitely, and nothing else would report it.
- **An empty input object refusing** (case `empty-input`). No scenario names it; `password` and `table` are both required, so it is the incomplete case in its most literal form.
- **The fixture self-checks** — that the application's credential really works from `platform_edge`, that `probe-denied` really produces an unrecognised message, that the fixture operator really has no `sudo`, that the sampler really looked. None is an obligation of the delta; each exists so that a failure below it is readable as a broken fixture rather than as a defect in the probe.

## Fixture-driven discriminators

The static module's checks do not execute the behaviour they assert, so a green run of them establishes only that the files could be read. `TestTheChecksDiscriminate` (17 tests) points every check at scratch trees this module supplies: a positive control, and one falsifying case per check on the property that check exists to assert — a runbook naming another path, a `0755` directory, a wildcard in the `sudoers` rule, a probe key equal to its deploy key, a `group_vars` file with no applications, a runbook announcing the window only in prose, a window raised after the volume is discarded, a window withdrawn after re-provisioning, a contract missing one token, a fixture on another major, a stack pinned to a floating tag. **All 17 pass today**, against the real tree's checks being red.

The Molecule scenario needs none: it executes the behaviour it asserts, and is red at authoring on the property each assertion is about. That redness is recorded below; the ordinary suite result is what confirms it as the implementation lands.

## What is red today, and on which property

Six static tests, and the whole Molecule scenario. Each is red because the target is absent, which establishes the target's absence and nothing about whether the assertion discriminates — for the static ones, the discriminators above are what establish that.

| Test | Red on |
|---|---|
| `TestTheWindowDeclarationHasOneFixedPath.test_the_role_the_role_readme_and_the_runbook_all_name_it` | Nothing names `/var/lib/platform-maintenance` |
| `TestTheWindowDirectoryIsProvisionedForAnOperatorWithNoSudo.test_the_role_provisions_the_declared_directory` | No task provisions the directory |
| `TestThePrivilegedHalfIsBoundToOneApplication.test_the_role_grants_sudo_on_the_privileged_probe_script` | No `sudoers` grant on `app-probe` exists |
| `TestEveryProbeKeyIsDeclaredBesideItsDeployKeyAndIsADifferentKey.test_every_enumerated_application_declares_a_distinct_probe_key` | No `group_vars` entry declares `probe_public_key` |
| `TestTheUpgradeRunbookAnnouncesTheWindowItOpens.test_the_procedure_declares_and_withdraws_the_window_in_the_right_order` | The runbook carries neither act |
| `TestTheConsumerContractIsWrittenDown.test_the_onboarding_document_carries_every_term_of_the_contract` | The contract is not written down |
| `probe-and-window` (whole scenario) | Fails at its first assertion — the declaration's directory does not exist. `deploy-probe` and `app-probe` do not exist either |

Three static tests in the new module are **green today and would be green over an unimplemented tree too**, and that is stated rather than left to be discovered: `test_no_committed_file_names_a_different_maintenance_path` (nothing names any maintenance path yet), and the two `TestTheProbeFixtureRunsTheInstanceTheStackRuns` tests (which read the scenario this pass wrote, not the implementation). The first is held up by its sibling; the other two are what hold the scenario's fixture to the stack's pin.

## Obsolete tests

**Not applicable, and the reason is the operation.** Every delta in this change is `ADDED` — two new requirements in `iac-host-configuration` and one in `iac-platform-services`. There is no `MODIFIED`, `REMOVED` or `RENAMED` delta, so no existing requirement is superseded and no existing test can be bearing on superseded behaviour. This is not an empty list produced by a search that found nothing: there was nothing to search for.

For completeness, the search that *was* performed and what it established: the dispatched test-path globs were read for tests bearing on the probe and the window (`ansible/roles/deploy_user/molecule/**`, `.github/tests/*.py`). No existing test asserts anything about a probe, a maintenance window, `/var/lib/platform-maintenance`, or an application determining that its database has ceased to exist — these behaviours do not exist yet. No earlier `test-plan.md` was supplied for this change and none exists in its directory.

## Unresolved project questions

Each is a question a project convention does not answer, recorded with the assumption taken and the tests that depend on it, because a dispatched author has no channel to ask on.

1. **How a Molecule scenario in this repository should stand a real PostgreSQL fixture up.** No convention exists. Assumption: nested `docker run` from `verify.yml`, mirroring `default`'s own nested-container fixtures (which are built there for the same reason — the runtime is installed by the converge, so `prepare` is too early). Depends on it: the whole `probe-and-window` scenario.
2. **Whether the fixture image should be digest-pinned or should agree with the stack's exact-release pin.** `test_ci_configuration.py` requires a digest for Molecule *platform* images and an exact release for *shared-stack service* images, and this fixture is the second kind wearing the first's clothes. Assumption: agreement with `platform/docker-compose.yml`'s pin, asserted by `TestTheProbeFixtureRunsTheInstanceTheStackRuns`. Depends on it: that class, and the fixture tasks in `verify.yml`.
3. **Whether `.github/tests` may read `ansible/inventory/group_vars/*.yml`.** AGENTS.md says the suite's subject is any static read of a committed file "wherever the file holding it lives", and those files are excluded from the *Molecule* suite's change detection, not from this one. Assumption: yes, and it is the only mechanism in the repository that reads them. Depends on it: `TestEveryProbeKeyIsDeclaredBesideItsDeployKeyAndIsADifferentKey`.
4. **Whether a probe's standard output may carry a trailing newline.** The requirement says "exactly one token on standard output and nothing else". Assumption: one line, trailing whitespace tolerated (`stdout | trim`, `stdout_lines | length == 1`). Depends on it: "Assert every probe exits zero when and only when it emitted a token" and every token assertion.
5. **Whether `molecule test --all` can be run on this machine at all.** Memory has killed `--all` runs of this repository before. Assumption: scenarios are run individually here and `--all` is left to CI, which is what AGENTS.md prescribes while a role is red anyway. Depends on it: nothing in the tests; it bears on how tasks.md 6.1 is performed.
6. **How long a converge of this scenario takes on the `vfs` storage driver with a real PostgreSQL image.** Unknown at authoring; the image is an order of magnitude larger than the `alpine:3.19` fixtures the role already pulls. If it proves prohibitive, the answer is to split the scenario rather than to weaken it — and the split that costs least is to move sections 4 to 8 into a second scenario sorting after this one.

## Notes for whoever implements next

- **The phase order in `verify.yml` is load-bearing.** The six tokens are not six independent conditions: reaching `unreachable` means making the instance unreachable and reaching `absent` means destroying the role and database every earlier assertion reads. A case moved earlier passes for the wrong reason or fails for a fixture reason.
- **Read the fail messages before changing an assertion.** Each names the condition it is about and, where it exists, the incident or the wrong-reason pass it exists to prevent.
- **Three tasks are fixture self-checks and say so.** If one of them fails, the fixture is broken and the probe is not on trial.
- **The specified assertions are not repair candidates.** Where one does not match, the code is wrong. The derived ones are listed above and may be reconsidered — deliberately, and recorded — but not edited to match what the implementation produced.
