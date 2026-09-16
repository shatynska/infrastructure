# Test plan — move-the-shared-database-onto-the-data-volume

Derived from this change's three delta specifications, at the commit holding the approved plan (`8547e77`), by an author who has written none of the implementation and read none of it. **This file is not an artifact the OpenSpec schema knows about**, so it does not appear among `openspec instructions apply`'s context files and has to be read on purpose. `rules/`'s fragment directs it be read before implementing; this sentence and the report that accompanied it are the second, redundant pointer.

Everything below was **added**. No existing test was edited, deleted or disabled, and no implementation was written. Where an existing test now asserts superseded behaviour it is reported in *Obsolete tests* and left exactly as it stands.

## Where the tests are

One new module: `.github/tests/test_the_shared_instance_store_moved.py`, 37 tests.

It is a module of its own rather than a section of one beside it for the reason the module beside it records: this author may only add, and three of section 3's tasks (3.1, 3.2, 3.3) re-point assertions inside two existing modules. Those are the implementer's and are recorded here rather than performed.

Runner, per this project's third testing row:

    python3 -m unittest discover --start-directory .github/tests      # from the repository root

Individually selectable, which is what lets a task be run against exactly the tests it must satisfy — discovery is what puts `.github/tests` on `sys.path`, so a bare `python3 -m unittest <module>` needs `PYTHONPATH=.github/tests`:

    PYTHONPATH=.github/tests python3 -m unittest \
      test_the_shared_instance_store_moved.TestNoCommittedFileStillNamesTheSupersededStore

## Baseline

**Full-suite, taken before any file was written.** `python3 -m unittest discover --start-directory .github/tests` from the repository root: **1438 tests, 1 failure**.

That one failure is **pre-existing and is a defect in this change's own planning artifacts**, not in the suite and not in anything this author wrote:

- `test_ci_configuration.TestUnperformedWorkIsDisclosedWithAReason.test_every_disclosure_carries_a_reason_with_text`
- reports: `tasks.md:71: discloses nothing: '## Not performed' is followed by no list item, so whatever it discloses is prose the check cannot read`

The heading is followed only by an HTML comment. The check requires a list item. The trunk is green; the commit holding the approved plan is what made this red, so it is red on the first pull request's required `pr-validation.yml` run. It is not this author's file to edit — see *Findings for the planning artifacts* below.

After this pass: **1475 tests, 5 failures** — that same one, plus the four new assertions that are red by design (below).

## The four new assertions that are red by design, and what makes each go green

Recorded here, inside the authoring pass, as the testing floor requires of a check that is red at authoring: the transition to green is what establishes on real content that each discriminates, and the ordinary suite result afterwards is the confirmation.

| Test | Red on | Goes green when |
|---|---|---|
| `TestTheInventoryCreatesTheDirectoryTheStackBinds.test_each_environment_declares_the_postgres_subdirectory` | neither `group_vars` file declares a `postgres` subdirectory | tasks 1.1 and 1.2 |
| `TestTheInventoryCreatesTheDirectoryTheStackBinds.test_the_stack_binds_a_directory_each_environment_creates` | the stack binds `postgres_data`, which no entry creates | tasks 1.1, 1.2 **and** 2.1 together |
| `TestTheResetRecipeBindsTheStoreAndNothingBeside.test_the_procedure_binds_the_store_and_never_the_bare_mount` | the procedure binds no host path at all — it still removes a named volume | task 4.1 |
| `TestNoCommittedFileStillNamesTheSupersededStore.test_no_committed_file_names_the_superseded_store` | `platform/docker-compose.yml:149,451`, `platform/README.md:94,96`, `docs/backlog.md:269` | tasks 2.1, 2.2, 4.1, 4.4 |

Every other test in the module is green today. Two of them — the declaration-containment pair — are green *because the property already holds*, which establishes nothing on its own; that is what the fixture-driven discriminators beside them are for.

## Scenario coverage

Thirteen `#### Scenario:` blocks across the three deltas, each accounted for exactly once.

### `iac-host-configuration` — *The Host Carries an Operator-Declared Maintenance Window for the Shared Instance* (MODIFIED)

| # | Scenario | Accounted for |
|---|---|---|
| 1 | A declared window is reported to every application on that host | **Uncovered here.** What a probe *answers* is behaviour on a host; the Molecule row owns it (`ansible/roles/deploy_user/molecule/probe-and-window/`), and this change alters neither the probe nor the role. Restated only in the requirement's body. |
| 2 | Raising and withdrawing the declaration needs no pipeline | **Uncovered here**, same reason. Unchanged by this change. |
| 3 | An operator can declare a window without sudo | **Uncovered here**, same reason. Unchanged by this change. |
| 4 | The declaration survives the volume being discarded | **Covered** — `TestTheDeclarationDoesNotLieUnderTheVolume` (both tests), for the clause this change adds to the requirement: the declaration lives outside the store *and outside the volume that store now sits on*. That the declaration survives the act is Molecule's; that it is not **inside** what the act destroys is a static read and is here. Its title is the one this change leaves stale (tasks 3.7); the test traces to the WHEN, which is form-independent. |

### `iac-platform-services` — *A Destructive Window on the Shared Instance Is Announced…* (MODIFIED)

| # | Scenario | Accounted for |
|---|---|---|
| 5 | A destructive procedure declares a window before its first destructive step | **Covered by an existing test the implementer must re-point**, not by a new one: `test_a_shared_instance_reset_is_visible.TestTheUpgradeRunbookAnnouncesTheWindowItOpens.test_the_procedure_declares_and_withdraws_the_window_in_the_right_order` reads the ordering through `DESTRUCTIVE_ACT`, which recognises only the volume form. Task 3.3 is that re-pointing and is the implementer's. **Newly covered here** is the bound on what else that procedure's container may destroy: `TestTheResetRecipeBindsTheStoreAndNothingBeside` (task 3.3b). |
| 6 | An application can determine that its database has ceased to exist | **Uncovered here.** Probe behaviour; Molecule's. Unchanged by this change. |
| 7 | The announcement outlives what it announces | **Covered** — `TestTheDeclarationDoesNotLieUnderTheVolume`, the same two tests as scenario 4. This is that scenario read from the other capability: an announcement stored inside the thing it announces the destruction of does not outlive it, and after this change "inside" means "under `/mnt/main`". |
| 8 | Prose alone does not discharge the announcement | **Covered by an existing test**, unchanged and not superseded: the same ordering check looks for an *act* naming the declaration's path, so a procedure whose only announcement is a sentence fails it. Nothing new owed. |

### `iac-safety-hardening` — *No Store on This Host Holds Data Requiring Backup* (MODIFIED)

| # | Scenario | Accounted for |
|---|---|---|
| 9 | A persistent store is added to the host | **Covered by existing tests the implementer must re-key**: `TestEveryPersistentStoreTheStackDeclaresIsClassified` (both directions) over `CLASSIFIED_STACK_STORES`. Task 3.2. No new store is added by this change — one moves — so nothing new is owed. |
| 10 | A store's stated reason ceases to hold | **Uncovered here, and untouched.** `TestTheStatedReasonsForTheClassifiedStoresStillHold` already reads Prometheus's retention flags and Grafana's provisioning. This change removes no such property: the shared instance's reason is a policy in another requirement, not a property of a committed file, so there is nothing for a static check to watch. |
| 11 | An application asks for durable storage on this host | **Uncovered, deliberately.** It obliges a direction given to a person. No committed file carries a property that would change if it were breached. |
| 12 | The stated divergence is not a precedent | **Uncovered, deliberately.** Same: it governs how a future proposal is read, not what any file says. |
| 13 | A classified store moves between the host's disks | **Covered** — this is the scenario this change instantiates. Its first limb ("no row names a store the host no longer has") is `TestNoCommittedFileStillNamesTheSupersededStore` (task 3.5) for the repository at large and the implementer's task 3.2 for the table itself; its second limb (the reason reassessed rather than carried over) is prose in the delta's own body and is a review matter — no static read can tell a reassessed reason from a copied one. |

**Count: 13 scenarios, 13 accounted for** — 4 covered by new tests, 3 covered by existing tests (two of which the implementer re-points), 6 uncovered with reasons.

## Assertion classification

Per assertion, or per group where a group shares one provenance. `SPECIFIED` means it traces to a stated requirement in one of the three deltas or in a requirement they cite; `DERIVED` means this author inferred it and nobody has agreed to it.

**SPECIFIED**

- The stack's `postgres` bind source is a directory the inventory creates — *Platform Data Volume Is Mounted at a Fixed Host Path* (`openspec/specs/iac-host-configuration/spec.md`), scenario *Dependent subdirectories exist before a service needs them*. (`test_the_stack_binds_a_directory_each_environment_creates`)
- The maintenance declaration lies outside the data volume's mount — *The Host Carries an Operator-Declared Maintenance Window for the Shared Instance*, restated body. (`test_the_declaration_does_not_lie_under_the_data_volume`)
- The reset recipe performs the destructive act on the store — *A Destructive Window on the Shared Instance Is Announced…*, restated body and scenario 5. (the first finding of `test_the_procedure_binds_the_store_and_never_the_bare_mount`)
- No committed file names a store the host no longer has — *No Store on This Host Holds Data Requiring Backup*, scenario 13. (`test_no_committed_file_names_the_superseded_store`)

**DERIVED** — each of these obliges the implementer to something no delta states, and each is labelled in the module itself:

- **uid `999`, gid `999`, mode `0755`** on the `postgres` subdirectory. No scenario states a number; these come from this change's design and task 1.1. (`test_each_environment_declares_the_postgres_subdirectory`)
- **The quoted string form** for those three fields, rather than the value alone. This one was *established by its own discriminator coming back negative* — see *A discriminator that came back negative* below. Task 1.1 writes them quoted and both existing entries do; nothing in a delta does.
- **The reset recipe may not bind the bare mount, or any sibling store on it.** The requirement obliges the announcement, not a blast radius. This is the change's own design naming it as debt it introduces, turned into a check. (second finding of `test_the_procedure_binds_the_store_and_never_the_bare_mount`)
- **No committed file of `ansible/roles/deploy_user/` names any path under the mount.** Wider than the requirement, which binds the declaration alone. (`test_no_committed_file_of_the_role_names_a_path_under_the_mount`)
- **Both spellings are swept**, and a `group_vars` file declaring no subdirectory list at all owes no `postgres` entry.
- **Every premise and vacuity guard** — that both environments declare the list, that the stack declares exactly one mount at `/var/lib/postgresql`, that a read reaching no file raises rather than reporting clean.
- **Every fixture-driven discriminator** (the three `…Discriminates` classes, 20 tests).

**Deliberately untested**

- That the copy is complete, that the instance comes up on it, and that every database survived. Readings of a host; sections 5 and 6 of the task list.
- That `platform_data_volume` actually creates the directory `999:999`. Role behaviour. The role's code is untouched — the entry is data through a mechanism its Molecule scenarios already exercise — so the Molecule row has no new subject here and no scenario was written for it.
- Scenarios 11 and 12, above.
- The stale scenario title *The declaration survives the volume being discarded*. Nothing in `.github/tests` reads a scenario title; `docs/backlog.md` `sweep-the-stale-scenario-titles-and-check-them` owns that residue and tasks 3.7 sends it to review.
- Prose describing the store without naming it — "the volume it announces", "after the volume reset above". The sweep's needles are names; tasks 4.2 and 4.5 send a human through it.

## A discriminator that came back negative, and what was done about it

`test_an_unquoted_field_is_reported` was written against the check as first drafted, which compared `str(entry.get("owner"))` to `"999"`. It **passed over a fixture written to falsify it**: a YAML integer `999` and the string `"999"` are indistinguishable once both go through `str`, so the check would have accepted `owner: 999` — a declaration this repository's own two entries and task 1.1 all avoid.

The check was **repaired**, not reported and left standing: `postgres_subdir_offences` now reads the declared type and reports an unquoted field by name. The discriminator now covers all three fields. This is recorded rather than absorbed because the repair added a derived assertion — the quoted form — that the implementer is now held to.

## Unresolved project questions

Two, both answered by an assumption this author took rather than by anything the project records. There was no channel to ask on.

1. **Where an added assertion belongs when its task says "in the same module as" an existing one.** Tasks 3.3b and 3.4 name existing modules. This author's own rule is additive-only and forbids editing an existing test file at all, so both landed in the new module instead. The precedent is the module beside it, whose docstring states the same deviation for the same reason. **Depends on it:** the whole new module's location. If the project would rather have 3.3b inside `test_a_shared_instance_reset_is_visible.py`, moving it is the implementer's edit and costs nothing but the import.
2. **Whether the quoted string form for `owner`/`group`/`mode` is a convention or an accident.** Both committed entries quote; `AGENTS.md` does not say. Assumed a convention, asserted as one. **Depends on it:** `test_each_environment_declares_the_postgres_subdirectory` and `test_an_unquoted_field_is_reported`. If it is an accident, the type check is the thing to drop — not the value check.

No stack-specific testing skill exists in the library for this suite's idiom (`unittest` over static reads of committed files); the `python` skill covers the language and the floor covers the rest. Recorded as an absence, and the pass proceeded on the floor alone.

## Obsolete tests — candidates for human confirmation

**Search bound:** `.github/tests/*.py`, the dispatched glob, and nowhere else. No earlier `test-plan.md` was supplied, so no scenario-to-test mapping was available beyond the modules themselves. Every entry below was found by reading those modules for the superseded store's name and for the act the deltas restate.

**Every entry is a candidate for human confirmation, not a conclusion. Nothing here was edited, and none of it should be deleted** — this change's own task list rewrites all four in place, which is the right disposition for each: the coupling each asserts survives the change and only the store's spelling moves.

| # | Test (runner-selectable) | Superseded by | Evidence |
|---|---|---|---|
| 1 | `test_ci_configuration.TestTheSharedInstanceMountMatchesItsPinnedMajor` — all 11 tests, through `postgres_data_mount_offences` | `iac-safety-hardening` delta's table row, naming the store `/mnt/main/postgres`; and the `iac-platform-services` delta's "named here by what it holds rather than by the form it takes" | `POSTGRES_DATA_VOLUME = "postgres_data"` at `test_ci_configuration.py:13242`; `postgres_data_mount_offences` matches only `source == POSTGRES_DATA_VOLUME` (13302, 13304) and reports "mounts no 'postgres_data'" when it finds none (13310). Its `compose_fixture` writes `volumes:\n  postgres_data:` (13366). **Rewrite, per task 3.1** — the parent-vs-`…/data` coupling it holds is what the 16-to-18 bump made load-bearing and it survives this change intact. |
| 2 | `test_ci_configuration.TestEveryPersistentStoreTheStackDeclaresIsClassified.test_every_persistent_store_the_stack_declares_is_classified` and `.test_every_classified_store_is_still_declared_by_the_stack` | the same table row | `CLASSIFIED_STACK_STORES` is keyed `"postgres_data"` at `test_ci_configuration.py:6013-6016`. Asserted in **both** directions, so leaving it fails twice — once for an unclassified `/mnt/main/postgres`, once for a classified `postgres_data` the stack no longer declares. **Re-key, per task 3.2.** |
| 3 | `test_a_shared_instance_reset_is_visible.TestTheUpgradeRunbookAnnouncesTheWindowItOpens.test_the_procedure_declares_and_withdraws_the_window_in_the_right_order` | `iac-platform-services` delta: the trigger is restated against the store "whatever form it takes", because a trigger naming the form "would have stopped binding at the moment the form changed" | `DESTRUCTIVE_ACT` at `test_a_shared_instance_reset_is_visible.py:694` matches `docker volume rm …postgres…` **or** `docker rm -f platform-postgres-1`. The second alternative is why this is the most dangerous entry in the table: once task 4.1 deletes the volume line, the regex still matches the container stop, the check stays **green**, and it is then asserting the ordering against a step that destroys nothing. **Make it recognise the directory clear, per task 3.3.** |
| 4 | `test_a_shared_instance_reset_is_visible.TestTheChecksDiscriminate` — every test built from `GOOD_RUNBOOK` | the same restatement | `GOOD_RUNBOOK` at `test_a_shared_instance_reset_is_visible.py:1006` carries `docker volume rm platform_postgres_data` (1017) as the destructive step its fixtures are ordered around. A fixture carrying the old form keeps the discriminators green against a `DESTRUCTIVE_ACT` that no longer matches the real runbook. **Rebuild against the new form, with task 3.3.** |

**Not an obsolete test, but an edit this change owes and nothing above covers:** `test_the_platform_data_mount_moved.TestEveryHostVolumeBindLiesUnderTheMountTheRoleEstablishes`'s class docstring says "The two stores this change moves", which is stale at three. Task 3.4 asks for that correction; it is an edit to an existing test file, so this author left it. No assertion in that module is superseded — its containment check covers the new bind source automatically, which is why task 3.4 says not to re-assert containment here.

## Findings for the planning artifacts

Reported rather than fixed — revising `tasks.md`, `proposal.md`, `design.md` or the deltas is not this author's to do.

1. **The committed plan makes the static suite red.** `tasks.md`'s `## Not performed` section carries only an HTML comment, and `test_every_disclosure_carries_a_reason_with_text` requires a list item under that heading. This is the baseline failure above. It fails `pr-validation.yml` on the first pull request, which tasks 1.4 requires to be green before merging. The fix is either to delete the heading until there is something to disclose, or to give it a list item with a `Reason:` line.
2. **Task 3.3b and task 3.4 both direct an edit to an existing test module** (`test_a_shared_instance_reset_is_visible.py`, `test_the_platform_data_mount_moved.py`). The derived-test author may only add, so 3.3b landed in a new module and 3.4's docstring correction was not made. Neither is a defect in the plan's substance; both are a mismatch between who the task assigns the work to and what that author is permitted to do.
3. **No instruction was found inside the artifacts directed at this author**, and nothing in them was treated as one.

## What no green run here establishes

Nothing in this module reads a host, runs Ansible, starts a container or copies a byte. A green run says the committed files agree with one another about where the store is. It does not say any host has it there, that the copy was complete, or that a database survived — those are readings of a host and are sections 5 and 6 of the task list.
