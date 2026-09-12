# Test plan — `namespace-the-molecule-loop-devices`

Written by the change's test author, from the approved delta specification, before any implementation existed. Nothing in this pass reads the implementation of the behaviour under test, and nothing in it edits, deletes or disables an existing test: **this pass adds tests and never subtracts.**

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files, so whoever implements this change has to open it on purpose. Its location is `test-plan.md` in this change's own directory.

## What was written

One new module, and no change to any existing one:

- `.github/tests/test_the_molecule_fixtures_namespace_their_loop_devices.py`

Test command, run from the repository root — the `.github/tests` row of `AGENTS.md`'s test table, which is the row all six new scenarios belong to:

    python3 -m unittest discover --start-directory .github/tests

    # the new module alone
    python3 -m unittest discover --start-directory .github/tests \
        --pattern "test_the_molecule_fixtures*"

Every test below is named in a form the runner selects individually, as `<module>.<class>.<method>`.

## Baseline

Taken before anything was written: **a full-suite run**, `python3 -m unittest discover --start-directory .github/tests` from the repository root. **884 tests, 0 failures, 0 errors, 24.5s.** Nothing was failing beforehand, so every failure reported below is this pass's own contribution.

After this pass: **927 tests, 5 failures.** 927 − 884 = 43, which is the whole of the new module; the 5 failures are all in it and are listed under *Expected state on arrival*. No pre-existing test changed its result.

## Scenario accounting

The delta reproduces the whole of the modified requirement, so it carries **35** `#### Scenario:` blocks. **29** of them are reproduced verbatim from the live requirement (`openspec/specs/iac-cicd-pipeline/spec.md`, the requirement *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge*) and state no behaviour this change introduces; **6** are new. Every one of the 35 is accounted for exactly once below.

### The six new scenarios — covered

| Scenario | Covering tests (module `test_the_molecule_fixtures_namespace_their_loop_devices`) |
|---|---|
| A fixture naming a kernel-held handle as a literal fails the checks | `.TestNoFixtureNamesAKernelHeldHandleAsALiteral.test_no_authored_fixture_play_names_a_loop_minor_as_a_literal`; `.TestNoFixtureNamesAKernelHeldHandleAsALiteral.test_no_authored_fixture_play_claims_a_handle_by_an_unrecognised_construction`; discriminated by `.TestTheFixturePlayEnumerationDiscriminates.test_a_tree_whose_plays_all_name_literals_fails_twice_over`, `.test_a_tree_whose_plays_derive_their_handles_satisfies_both`, `.test_a_literal_minor_in_a_mknod_is_caught_behind_a_derived_path`, `.test_a_claim_by_an_unrecognised_construction_is_refused` |
| The entry point and the fixtures are checked against each other | `.TestTheFixturesAndTheEntryPointAgreeOnTheName.test_every_name_the_deriving_fixtures_read_is_one_the_entry_point_supplies`; `.TestTheFixturesAndTheEntryPointAgreeOnTheName.test_every_deriving_fixture_reads_a_value_the_entry_point_could_supply`; discriminated by `.TestTheNameAgreementCheckDiscriminates.test_a_rename_in_the_fixtures_alone_is_a_mismatch`, `.test_a_rename_in_the_entry_point_alone_is_a_mismatch`, `.test_two_sides_naming_the_same_value_agree`, `.test_a_name_molecule_supplies_is_not_read_as_the_entry_points`, `.test_a_name_the_scenario_definition_supplies_is_not_read_as_the_entry_points`, `.test_a_play_deriving_a_device_from_nothing_supplied_is_reported` |
| The supplied value is derived from the working tree rather than fixed | `.TestTheEntryPointDerivesTheValueItSupplies.test_the_entry_point_supplies_a_value_for_the_kernel_held_handle`; `.TestTheEntryPointDerivesTheValueItSupplies.test_the_supplied_value_derives_from_the_working_trees_own_path`; `.TestTheEntryPointDerivesTheValueItSupplies.test_the_analysis_recognises_the_namespace_the_entry_point_already_derives`; discriminated by `.TestTheDerivationAnalysisDiscriminates.test_an_entry_point_deriving_the_value_passes`, `.test_an_entry_point_assigning_a_constant_fails`, `.test_an_entry_point_whose_derivation_ignores_its_argument_fails`, `.test_an_entry_point_supplying_nothing_fails`, `.test_the_supplied_set_is_what_the_script_assigns` |
| A fixture claiming a kernel-held handle establishes it is free first | `.TestAFixtureEstablishesTheHandleIsFreeBeforeClaimingIt.test_every_associating_fixture_releases_reads_and_refuses_first`; discriminated by `.TestTheAssociationGuardCheckDiscriminates.test_a_play_that_releases_reads_and_refuses_passes`, `.test_a_play_associating_without_a_release_fails`, `.test_a_play_releasing_without_reading_what_holds_it_fails`, `.test_a_play_that_reads_registers_and_releases_regardless_fails`, `.test_a_failed_when_false_on_the_read_is_not_a_refusal`, `.test_a_refusal_naming_nothing_the_read_registered_does_not_count`, `.test_a_play_claiming_no_handle_is_not_held_to_this`, `.test_a_folded_command_is_read_as_one_invocation` |
| Checks over the fixture plays fail rather than passing over an empty set | **`.TestTheFixturePlayEnumerationRefusesToBeEmpty.test_some_fixture_play_derives_a_kernel_held_handle`** — a test of its own, not a clause of another; plus `.TestTheFixturePlayEnumerationRefusesToBeEmpty.test_the_fixture_play_enumeration_is_not_empty`; discriminated by `.TestTheFixturePlayEnumerationDiscriminates.test_a_tree_whose_plays_all_name_literals_fails_twice_over` and `.test_a_tree_whose_plays_derive_their_handles_satisfies_both` |
| The workflow reaches the suite through the entry point | `.TestTheWorkflowReachesTheSuiteThroughTheEntryPoint.test_no_step_invokes_the_tool_directly`; `.TestTheWorkflowReachesTheSuiteThroughTheEntryPoint.test_the_workflow_invokes_the_molecule_suite`; discriminated by `.TestTheWorkflowCheckDiscriminates.test_an_invocation_through_the_entry_point_passes`, `.test_an_invocation_of_the_tool_directly_fails`, `.test_a_workflow_invoking_nothing_is_recognised_as_invoking_nothing`, `.test_the_word_molecule_in_an_argument_is_not_an_invocation`, `.test_an_invocation_behind_a_wrapper_is_still_read` |

The Galaxy exclusion the delta's "same Galaxy exclusion" clause points at is carried by `.TestTheFixturePlayEnumerationDiscriminates.test_installed_galaxy_content_contributes_no_fixture_play`, and is derived from `ansible/requirements.yml` by reusing `test_ci_configuration.py`'s own `authored_scenario_files` and `galaxy_role_directories` rather than by naming a role.

**The counted set is the deriving subset.** `test_some_fixture_play_derives_a_kernel_held_handle` counts fixture plays whose loop device is *interpolated*, never the wider set of plays claiming a handle by any means. The wider set is non-empty today — five plays name minors 87–91 as literals — which is the very state these obligations forbid, so counting it would report the enumeration healthy in exactly the condition that empties every other check over it.

### The 29 reproduced scenarios — uncovered by this pass, with the reason

**Reason, identical for all 29:** reproduced verbatim from the live requirement, stating no behaviour this change introduces. Each is already covered by the pre-existing suite — `test_ci_configuration.py`, `test_the_suite_is_triggered_by_what_it_reads.py`, `test_the_matrix_runs_the_roles_a_pull_request_owes.py` and `test_the_derivation_follows_or_refuses_every_route.py` between them — which the baseline above records green. No test was derived for them by this pass, and none of their existing tests was read, edited or re-derived.

1. Ansible-only pull request is linted and syntax-checked
2. Narrowing the lint tier's trigger fails the pipeline's own checks
3. A pull request changing only Ansible content no scenario reads starts no container
4. An unconsidered new path under the configuration directory runs the suite
5. A correct skip says what was actually unchanged
6. A committed credential is caught wherever in the repository it lands
7. A credential assigned across a folded scalar's continuation is still caught
8. A second read of an already-permitted path is still refused
9. Editing a scenario above a permitted read does not invalidate the permitted set
10. A scenario reaching an excluded path fails the pipeline's own checks
11. A controller read that does not delegate is still a controller read
12. A read of the managed node is not held to the enumerated paths
13. A newly added role scenario runs without a workflow change
14. Every scenario a role declares is executed
15. Discovering no roles fails rather than passes
16. Discovery failing is not reported as a correct skip
17. A failing Molecule scenario blocks the merge
18. A pull request touching no Ansible file starts no container
19. Role discovery runs even where the suite does not
20. A manual run verifies the whole suite
21. A change to a pinned manifest runs the suite
22. Ansible verification receives no production credential
23. Every scenario's platform image is pinned by digest
24. A scenario declaring no platform image fails rather than being skipped
25. Scenarios sharing an image repository agree on its digest
26. Installed Galaxy content is not held to this repository's pinning obligation
27. An upstream re-push cannot change what the suite ran against
28. Every authored scenario bounds its instance's host name
29. Every authored scenario's instance name carries the namespace

**Count:** 6 covered + 29 uncovered-with-reason = 35 = the number of `#### Scenario:` blocks in the delta.

## Expected state on arrival

Five checks are **RED** today, each on a property the tree does not yet carry. Recorded here, inside the authoring pass, because a check red at authoring that goes green as the change lands is what establishes that it discriminates *on real content*:

| Red test | The property it is red on |
|---|---|
| `.TestNoFixtureNamesAKernelHeldHandleAsALiteral.test_no_authored_fixture_play_names_a_loop_minor_as_a_literal` | Ten fixture plays name `/dev/loop87`–`/dev/loop91`, or the minor in a `mknod ... b 7 90` |
| `.TestTheEntryPointDerivesTheValueItSupplies.test_the_entry_point_supplies_a_value_for_the_kernel_held_handle` | `ansible/scripts/run-molecule` supplies `INFRA_WORKTREE_NS`, `ANSIBLE_HOME`, `ANSIBLE_COLLECTIONS_PATH` — no loop base |
| `.TestTheEntryPointDerivesTheValueItSupplies.test_the_supplied_value_derives_from_the_working_trees_own_path` | The same absence, read for its derivation |
| `.TestAFixtureEstablishesTheHandleIsFreeBeforeClaimingIt.test_every_associating_fixture_releases_reads_and_refuses_first` | `default/prepare.yml` associates with no release earlier in the file; the other three release without reading what holds the minor first |
| `.TestTheFixturePlayEnumerationRefusesToBeEmpty.test_some_fixture_play_derives_a_kernel_held_handle` | No fixture play derives its device — the enumeration is empty, which is the state the other checks start in |

Four checks are **GREEN on arrival**, recorded rather than contorted into failing. Two were predicted by `tasks.md` 1.2; two were not, and are reported as found:

| Green test | Why |
|---|---|
| `.TestTheWorkflowReachesTheSuiteThroughTheEntryPoint.test_no_step_invokes_the_tool_directly` (and `.test_the_workflow_invokes_the_molecule_suite`) | **Predicted.** `.github/workflows/ansible-verify.yml` already runs `../../scripts/run-molecule test --all`; the test locks that in, and nothing read it before |
| `.TestTheFixturesAndTheEntryPointAgreeOnTheName.test_every_name_the_deriving_fixtures_read_is_one_the_entry_point_supplies` (and `.test_every_deriving_fixture_reads_a_value_the_entry_point_could_supply`) | **Predicted.** Green over an empty set — no fixture derives a device yet. This is the empty-enumeration case arriving early, and is exactly why the scenario above is a test of its own |
| `.TestNoFixtureNamesAKernelHeldHandleAsALiteral.test_no_authored_fixture_play_claims_a_handle_by_an_unrecognised_construction` | **Not predicted; reported as found.** Every play claiming a handle today names it as a literal, so each one is *recognised* and is reported by the literal check instead. This check is the refusal that catches a third construction appearing later; it is correctly green now |
| `.TestTheEntryPointDerivesTheValueItSupplies.test_the_analysis_recognises_the_namespace_the_entry_point_already_derives` | **Not predicted; deliberate.** A positive control on real content: `INFRA_WORKTREE_NS` *is* derived from the working tree today, so an analysis reporting it underived would be broken in the direction that makes the assertion beside it unfalsifiable-by-passing |

**An absent target fails rather than skipping.** Nothing in the module skips under any condition. The workflow assertion reaches `.github/workflows/ansible-verify.yml` through `load_yaml`, which raises `AssertionError` on a file that is not there; the entry point is read through `read_text`, which does the same.

## Assertion classification

Every assertion carries a SPECIFIED / DERIVED annotation in its own docstring. In summary:

**SPECIFIED** — traces to SHALL text in the delta: the literal check; the unrecognised-construction refusal; both halves of the name agreement; the derivation of the supplied value (the *obligation*); the release/read/refusal ordering and each of its four negative cases; the empty-enumeration refusal and its "fails twice over" case; the direct-invocation failure; the Galaxy exclusion; the vacuity guards on the workflow and fixture-play enumerations.

**DERIVED** — traces to this change's `design.md`/`tasks.md` or to this pass's judgement, each labelled in place:

- **The spelling `INFRA_WORKTREE_LOOP_BASE`**, read by `TestTheEntryPointDerivesTheValueItSupplies`. The delta says the entry point's obligations "SHALL be checked over the entry point itself", and the entry point carries no name-bearing declaration to read a spelling out of, so the name is the only available anchor; it comes from `design.md` Decision 2. The cost is stated in the module: a *coordinated* rename of both sides fails this one check and costs a visible edit. A *one-sided* rename — the failure the delta's own scenario names — is caught by the name-free agreement check, which reads no spelling. This is the one place where the instance-name checks' "which variable carries it is deliberately not asserted" precedent could not be followed.
- **The positive control** on `INFRA_WORKTREE_NS` (above).
- **The two exclusions** applied to the environment names a play reads — a `MOLECULE_`-prefixed name, and a name the scenario's own `molecule.yml` declares in its provisioner environment. Both are supplied by something other than the entry point, so neither is evidence of a mismatch. Without them `multiple-devices-discoverable/prepare.yml` would be a permanent mismatch on `MOLECULE_MULTI_DEVICE_REVERSE_ORDER` and the repair reached for would be to weaken the comparison.
- **The two recognised derivation constructions** (`/dev/loop{{ … }}` and `'/dev/loop' ~ …`). Anything else claiming a handle is refused rather than passed over.
- **The folded-scalar reader** and the command-position reading of a workflow `run:` line, each written against a shape this repository actually uses.

**Deliberately untested, with the reason:**

- **That two different working trees resolve two different loop bases.** It needs the entry point to be *run*, twice, which means spawning a shell; the `.github/tests` suite may not, and the one existing test that shells out does so for a workflow snippet, not for a property like this. `tasks.md` 2.1 and 7.2 carry it. The static half — that the value flows from the working tree's own path rather than from a constant — *is* asserted here.
- **The run-time refusal of a foreign minor.** Not reachable in this repository: the guard is the first task of the first play and Molecule runs nothing between `create` and `prepare` in which a foreign association could be planted. `design.md` Decision 4 states this, and the delta specifies the static shape for that reason.
- **The attribution guard's predicate.** What is checked is that a refusal stands between the read and the release and mentions what the read registered — not that `/root/platform-data-volume-` is the right prefix. A static check of the condition would be a substring search any rearrangement satisfies.
- **That each fixture asserts its device starts with no filesystem.** `design.md` Decision 8 assigns this to Molecule deliberately: it is a claim about what a run establishes, not about what a file says.
- **A repository-wide sweep for any *other* workflow invoking `molecule` directly.** The delta's scenario is about "the workflow that runs the Molecule suite", and there is one. A sweep would be an invented requirement; recorded here rather than written.

## Fixture-driven discriminators

Every check in this module is a static read — a pass establishes only that the target could be read — so each one is pointed at material the test itself supplies. Four classes carry them, all of them green, none of them negative:

- `TestTheFixturePlayEnumerationDiscriminates` — scratch `ansible/` trees built on `test_ci_configuration.py`'s own `ScenarioTreeFixtureMixin`, extended to write plays beside the definitions.
- `TestTheNameAgreementCheckDiscriminates` — a rename on each side in turn, plus the agreeing case.
- `TestTheDerivationAnalysisDiscriminates` — an entry point assigning a constant, and the subtler one whose *function* ignores the root it was handed while the call site still mentions it.
- `TestTheAssociationGuardCheckDiscriminates` — association with no release; release with no read; read-register-release with the refusal removed; a refusal naming nothing the read registered; `failed_when: false` not counted as a refusal.
- `TestTheWorkflowCheckDiscriminates` — a direct invocation, an invocation behind a wrapper, and `-name molecule` as an argument to `find`, which a reader of the bare word would misreport.

**No discriminator came back negative**, and none was written-but-not-run: every one executes in the ordinary suite run.

**Satisfiability was checked outside the repository.** The whole module was additionally run against a throwaway copy of `ansible/` and `.github/workflows/` carrying the implementation `tasks.md` describes — `loop_base_for()` exporting `INFRA_WORKTREE_LOOP_BASE`, and the ten plays rewritten to derive, read, refuse and detach. All 43 tests passed there. That establishes the checks are satisfiable by the planned implementation rather than over-constrained, and it was done in a session scratch directory: **no file in this repository was modified to do it**, and the copy has been deleted.

## Obsolete tests

**Superseded behaviour was established by comparing the delta against the live requirement**, `openspec/specs/iac-cicd-pipeline/spec.md`, the requirement *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* — not by reading any implementation. The comparison: all 29 pre-existing scenarios are reproduced **verbatim**, and the requirement's prose gains paragraphs rather than replacing any. Nothing in the requirement's previous text is withdrawn.

**Search performed:** the dispatched test-path glob `.github/tests/*.py` and nowhere else, for the needles the superseded behaviour would carry — `dev/loop`, `losetup`, `loop_base`, `LOOP`, and `run-molecule`.

**Result: no bearing test was found, and this is a "no such test exists" rather than a "none was found by this search".** No file under the glob mentions a loop device, `losetup`, or the entry point's derivation at all. The three pre-existing mentions of `run-molecule` bear on something else and are **not** obsolete:

- `test_the_suite_is_triggered_by_what_it_reads.py`, `SELECTED_BY_THE_SUITE` carrying `ansible/scripts/run-molecule` — asserts that a pull request touching the entry point runs the suite. This change *relies* on that holding and `proposal.md` says so.
- `test_the_matrix_runs_the_roles_a_pull_request_owes.py`, two mentions — the per-role matrix selection. Untouched by this delta.

**No earlier `test-plan.md` was supplied to this pass**, so the search could not be narrowed by a prior scenario-to-test mapping; the needle search above is what it rests on.

Nothing is proposed for deletion or rewriting. Had anything been, it would have been listed here as a **candidate for human confirmation** with its superseding delta and the evidence; the list being empty here means the first thing, not the second.

## Unresolved project questions

`AGENTS.md` and `CLAUDE.md` were read. Four questions arose that neither answers; each is recorded with the assumption taken and the tests that depend on it, rather than resolved silently. There is no channel to ask on from a dispatched pass.

1. **Does a trailing inline comment naming a minor count as content?** `AGENTS.md` says nothing. `test_ci_configuration.py`'s `uncommented()` drops whole-line comments only, and the module reuses it. **Assumption:** a whole-line comment naming `/dev/loop87` is prose about what is no longer done and is not read; a *trailing* comment on a line of content is read as content, which is the refusing direction and costs a visible edit rather than a silent gap. **Depends on it:** `test_no_authored_fixture_play_names_a_loop_minor_as_a_literal`. `tasks.md` 3.5's "except where one is quoted as an example of what is no longer done" is satisfied by a whole-line comment and not by a trailing one.
2. **May a static check pin an identifier's spelling?** The existing instance-name checks deliberately pin none; this pass pins one, for the reason under *Assertion classification*. **Assumption:** permitted where the alternative is no anchor at all, with the cost stated in the module. **Depends on it:** both tests in `TestTheEntryPointDerivesTheValueItSupplies`.
3. **A new module, or a section inside `test_ci_configuration.py`?** `AGENTS.md`'s *Testing* names the row, not the granularity. **Assumption:** a new module — this pass may only add, and `test_the_platform_data_mount_moved.py` set that precedent for the same reason. **Depends on it:** the whole module. If the implementing author would rather this lived inside an existing module, that is a move they perform, not a gap in coverage.
4. **Which Python style the suite holds itself to** — line length, formatter. `.pre-commit-config.yaml` runs no Python formatter over `.github/tests`. **Assumption:** the surrounding modules' conventions (≈96-column lines, double quotes, `from __future__ import annotations`). **Depends on it:** nothing behavioural.

## What the implementation must make pass

Run the five red tests above as the definition of done for `tasks.md` sections 2 and 3, and the whole module for section 4:

    python3 -m unittest discover --start-directory .github/tests --pattern "test_the_molecule_fixtures*"

then the whole suite, per `tasks.md` 4.3 and 6.3:

    python3 -m unittest discover --start-directory .github/tests

`tasks.md` 4.1 says to "fill only what the derived tests report as a gap, and record any such gap as one rather than rewriting what was derived". The seven properties that task enumerates are each asserted above. Two notes for that step:

- The **empty-enumeration** test is the one that turns green last, when the first fixture play derives its device. Until then, three of the checks over the fixture plays are reporting green over nothing, and that test is the only thing saying so.
- A **coordinated** rename away from `INFRA_WORKTREE_LOOP_BASE` fails `TestTheEntryPointDerivesTheValueItSupplies` and is a deliberate visible edit to this module, not a defect in it. Renaming **one** side must keep failing `TestTheFixturesAndTheEntryPointAgreeOnTheName`; do not weaken that check to reach green.
