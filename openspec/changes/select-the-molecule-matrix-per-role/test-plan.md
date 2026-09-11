# Test plan — select-the-molecule-matrix-per-role

Written by an author other than whoever implements this change, from the delta specification alone, before any selector existed. This file is the scenario-to-test mapping, the assertion classification, the baseline, the interface the tests assume, and the findings that belong to someone else's pass.

**It is not an artifact the OpenSpec schema knows about**, so it does not appear among `openspec instructions apply`'s context files and has to be read on purpose. Read it before implementing: it is where the names the tests call, and the two wrong answers each refusal rejects, are written down.

All tests live in one new module, `.github/tests/test_the_matrix_runs_the_roles_a_pull_request_owes.py`, run by this project's third test command — `python3 -m unittest discover --start-directory .github/tests`, from the repository root. Nothing outside that module was edited, deleted or disabled. **This pass adds tests and never subtracts.**

Individually selectable, from the repository root:

    python3 -m unittest discover --start-directory .github/tests \
        -k test_a_path_the_attribution_does_not_recognise_runs_every_role

    # or, from `.github/tests`:
    python3 -m unittest test_the_matrix_runs_the_roles_a_pull_request_owes\
.TestAttributionWidensRatherThanNarrows\
.test_a_path_the_attribution_does_not_recognise_runs_every_role

## Baseline

Taken before anything was written, over the full suite: **646 tests, one failure** — `test_ci_configuration.TestEveryComposeFileDeclaringAServiceImageIsCovered.test_every_compose_file_declaring_a_service_image_is_covered`, which walks into `.molecule-home/` and flags six collection fixtures of a provisioned working tree. Pre-existing, owned by `docs/change-queue.md` entry 68, green in continuous integration, which never provisions Molecule.

After this pass: **695 tests, 70 failures, zero errors.** Every failure but the one above is in the new module. Of its 49 tests, **43 are red** — the selector does not exist, and the workflow has not been reshaped — and **6 are green**, each recorded under *Checks green at authoring* below.

A zero-error run is the thing to check when re-running this: an error rather than a failure in that module means a defect in the test, not in the absent implementation.

## The interface these tests assume

Nothing in the change's artifacts names the selector's file or its functions, so the tests had to invent them. **Implement to these names, or re-point the tests deliberately** — they are assumptions recorded as such, not requirements derived from the delta.

A Python module under `ansible/scripts/`, importable with no side effects (any command-line entry point guarded by `__name__`). The tests try `ansible/scripts/select_molecule_roles.py` first and then any other `*.py` in that directory exposing `select_roles`, so the **filename is an assumption and not a requirement**. They import it by file path through `importlib`, never with an `import` statement — an import naming it would turn `test_ci_configuration.TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` red for a reason that has nothing to do with privilege.

| Name | Signature | What the tests require of it |
|---|---|---|
| `select_roles` | `(changed_paths, root) -> sequence[str]` | The entry point the workflow calls. Attribution, closure, restriction to runnable roles and the widening all happen inside. Positional arguments. A JSON array is accepted as a return value as well as a list. Raises `EmptySelection` rather than returning nothing. |
| `derive_graph` | `(root) -> dict[str, set[str]]` | **Forward** edges: role → the roles that role's own scenarios and `meta/main.yml` reach. Raises `DerivationRefused`. |
| `reverse_closure` | `(graph, seeds) -> set[str]` | Seeds plus every role reaching them, transitively; terminates on a cycle. Takes a plain dict, so it is exercised against a fixture graph with a known answer. |
| `roles_with_scenarios` | `(root) -> set[str]` | Role directories carrying `molecule/`, dotted names excluded, agreeing with `role_names()` over the real tree. |
| `PERMITTED_NESTED_PLAYBOOKS` | mapping | Keys are 3-tuples `(file, construction, target)`, in `PERMITTED_CONTROLLER_READS`' form. Lives in the selector, per the change's tasks.md 2.2a; the test reads it rather than restating it. |
| `DerivationRefused` | `Exception` subclass | Distinct type, so a test asserting a refusal is not satisfied by a `TypeError` from a mis-specified call. |
| `EmptySelection` | `Exception` subclass | As above, for the selection refusal. |

Four further assumptions, each of which will cost an hour if it turns out wrong:

- **`root` is a filesystem tree, not a checkout.** Fixture trees are temporary directories and are not repositories, so a derivation enumerating through `git ls-files` cannot be exercised against them. Every fixture tree carries a minimal `ansible/requirements.yml` (`roles: []`, `collections: []`), in case the selector reuses this suite's Galaxy-exclusion helper, which refuses an absent manifest.
- **Changed paths need not exist.** A deleted file is a changed path, and attribution is over the path string.
- **The selector imports only the standard library and what `.github/requirements-ci.txt` pins** (PyYAML). The suite's import audit reads modules in `.github/tests` only, so nothing would catch a third-party import here except the tests failing to load it.
- **The discovery step and the selection step may be one step or two.** The workflow tests locate each by what it writes — the discovery job's `outputs:` block, read back to the step `id:` that produced it — and tolerate either shape.

The workflow shape the tests read, all of it structural rather than by name: the **run-suite** output is the one the matrix job's `if:` reads, the **selection** output is the one its `strategy.matrix` reads, and the tests assert these are two different outputs. The gate step is the one whose `env:` carries all four of the discovery result, the matrix result, the run-suite output and the selection output; its body must stay free of `${{ }}`.

## Every scenario, accounted for

Seventeen `#### Scenario:` blocks in the delta. **All seventeen are covered**; none is recorded as uncovered. The delta is `ADDED`-only, so no scenario is reached through a `REMOVED` or `RENAMED` operation.

| # | Scenario | Covering tests (all in `test_the_matrix_runs_the_roles_a_pull_request_owes`) |
|---|---|---|
| 1 | A pull request confined to one role runs that role and the roles converging it | `TestTheClosureOverTheRepositorysOwnTree.test_every_roles_selection_is_the_reverse_closure_of_the_derived_graph`; `.test_a_role_whose_closure_is_smaller_than_the_tree_runs_no_other_role`; `TestTheReverseClosureOverAFixtureGraph.test_the_closure_carries_its_own_seed`; `.test_the_closure_includes_transitive_convergers` |
| 2 | A role no scenario converges runs alone | `TestTheClosureOverTheRepositorysOwnTree.test_a_role_no_scenario_converges_runs_alone` |
| 3 | A shared input runs every role | `TestAttributionWidensRatherThanNarrows.test_a_shared_input_runs_every_role`; `.test_a_shared_input_alongside_a_role_still_runs_every_role` |
| 4 | A path the attribution does not recognise runs every role | `TestAttributionWidensRatherThanNarrows.test_a_path_the_attribution_does_not_recognise_runs_every_role` |
| 5 | A change to a role that nothing converges and nothing tests runs every role | `TestARoleNothingConvergesAndNothingTestsWidensOnItsOwn.test_a_change_confined_to_it_runs_every_role` |
| 6 | A role's own tasks reaching outside that role is refused | `TestARolesOwnFilesReachingOutsideItAreRefused.test_a_role_task_file_invoking_another_role_is_refused`; `.test_a_role_task_file_reaching_another_roles_file_by_path_is_refused`; `.test_a_handler_file_reaching_outside_its_role_is_refused`; `.test_no_role_in_this_repository_reaches_outside_its_own_directory_today`; `.test_the_scan_reports_a_role_that_does_reach_outside` |
| 7 | An unverifiable role alongside a verifiable one does not widen the run | `TestARoleNothingConvergesAndNothingTestsWidensOnItsOwn.test_it_does_not_widen_a_diff_that_also_touches_a_role_that_can_be_run` |
| 8 | A role in the closure that carries no scenarios is not given a matrix row | `TestAttributionWidensRatherThanNarrows.test_a_role_in_the_closure_that_carries_no_scenarios_is_not_given_a_matrix_row`; `TestTheSelectorEnumeratesRolesLikeTheRestOfTheSuite.test_no_selection_ever_carries_a_role_that_cannot_be_run` |
| 9 | A route that cannot be closed over is permitted by instance, not by construction | `TestARouteThatCannotBeClosedOverIsPermittedByInstance.test_a_nested_playbook_named_by_expression_is_refused_where_no_entry_covers_it`; `.test_the_permitted_entries_are_keyed_by_instance`; `.test_the_repositorys_own_tree_derives_without_refusal` |
| 10 | A change to a role carrying no scenarios still runs the roles that converge it | `TestAttributionWidensRatherThanNarrows.test_a_change_to_a_role_carrying_no_scenarios_still_runs_the_roles_that_converge_it` |
| 11 | A construction the derivation cannot resolve fails the run | `TestTheDerivationRefusesWhatItCannotResolve.test_a_role_named_by_anything_but_a_literal_is_refused`; `.test_a_construction_the_derivation_has_no_rule_for_is_refused`; `.test_a_tree_carrying_none_of_these_is_not_refused` |
| 12 | An empty selection on a run that owes the suite fails | `TestTheSelectorRefusesAnEmptySelection.test_a_tree_whose_roles_carry_no_scenarios_fails_rather_than_selecting_nothing`; `TestTheMatrixIsFedTheSelection.test_the_step_that_runs_the_selector_does_not_swallow_its_exit_status` |
| 13 | Discovery still refuses a tree carrying no scenarios | `TestDiscoverysVacuityRefusalReadsTheUnfilteredTree.test_discovery_refuses_a_tree_with_no_scenarios_whatever_the_diff_said`; `.test_discovery_accepts_a_tree_that_does_carry_a_scenario` |
| 14 | The aggregating job names the subset it ran | `TestTheAggregatingGateReadsTheSelection.test_the_gate_names_the_subset_it_ran`; `.test_the_gate_concludes_as_the_table_says_on_every_row` |
| 15 | A matrix that ran where nothing was owed fails | `TestTheAggregatingGateReadsTheSelection.test_the_gate_refuses_a_matrix_that_ran_where_nothing_was_owed`; `.test_the_gate_concludes_as_the_table_says_on_every_row` |
| 16 | A run carrying no diff runs every role | `TestARunCarryingNoDiffSelectsEveryRole.test_the_selection_written_on_an_event_with_no_diff_is_every_discovered_role`; `.test_the_same_step_or_job_resolves_the_suite_as_owed_on_such_an_event` |
| 17 | A scenario added later is covered without editing the check | `TestTheClosureOverTheRepositorysOwnTree.test_a_scenario_added_later_is_covered_without_editing_this_check` |

Six further tests cover the derivation the scenarios presuppose but do not state — the constructions of design.md Decision 2, in `TestTheDerivationFollowsEveryConstructionThatReachesARole`, one per construction so that a regression says which one it dropped — plus the workflow shape the selection needs: `TestTheMatrixIsFedTheSelection.test_the_matrix_rows_come_from_the_step_that_runs_the_selector`, `.test_the_selector_lives_under_the_directory_the_suites_filter_reads`, `.test_the_changed_file_list_comes_from_the_filter_that_already_runs`, and `TestTheSelectorEnumeratesRolesLikeTheRestOfTheSuite`'s three.

## Assertion classification

Every test carries its own SPECIFIED/DERIVED annotation in its docstring, which is where the reasoning lives. In summary:

**SPECIFIED** — traces to SHALL text or to a scenario. All seventeen rows above, the restriction to runnable roles, the two refusals, the widening polarity, the gate's four inputs and its unchanged refusals, and the role enumeration ("under the same enumeration of this repository's own roles").

**DERIVED** — traces to `design.md` or `tasks.md`, not to a scenario. Each is marked in the test with *reconsider this assertion, do not weaken it, if the implementation satisfies the scenario by another means*:

- Which four constructions are followed, and the spellings of each (Decision 2). The delta obliges "follow or refuse"; the enumeration is a design decision.
- That `molecule.yml`'s contents are never read (Decision 2's closing paragraph, and the change's handoff — the author's first attempt produced a graph claiming six roles depend on `docker`).
- That an external, dotted Galaxy role contributes no edge and is not a refusal.
- That `import_playbook` is *followed into* the playbook it names.
- That the closure terminates on a cycle rather than refusing one (refusing would also be conformant).
- That the closure of several seeds is the union (design.md's "A role is renamed" trade-off).
- That a diff carrying no path at all widens rather than resolving to nothing.
- That the changed-file list comes from the filter already in the job, declaring `list-files: json` (Decision 7, tasks.md 3.1).
- That the selector lives under `ansible/scripts/` (Decision 6).
- The two controls — that discovery accepts a populated tree, and that the no-diff branch still reports `false` on a pull request whose filter said so. Neither is stated anywhere; both exist because a check that can only fail is worth as little as one that can only pass.

**Deliberately untested**, each with its reason:

- **A changed path outside `ansible/`.** The selector is only ever fed the filter's matched list, which is `ansible/**` minus four exclusions. Widening on such a path would be safe; narrowing would need the filter to be wrong first, which the sibling module already asserts against.
- **What `dorny/paths-filter` actually emits for `list-files: json`.** Reproducing picomatch needs a dependency this suite is forbidden from taking and running the action needs a network call. The declaration is asserted; the behaviour is observed on the change's own pull request.
- **That the runner starts exactly the jobs the selection names.** An Actions expression evaluated on a runner. The change's tasks.md section 6 already owns this as its observation, and records that the narrowing itself is observable only on a later pull request touching exactly one role.
- **That a role still does what its scenarios say.** Molecule's subject, and this change touches no role. The change's tasks.md 4.2 runs one role to establish it.
- **The exact numerals in design.md's Context table** (`docker` owes four, `deploy_user` two, the rest one). Asserting them would assert today's tree and would need an edit the day a scenario is added — which scenario 17 forbids. The real-tree tests compute the expected closure from the derived graph with a second implementation of the closure written in the test module, and separately assert, as a **subset**, that the four cross-role edges the scenarios declare today are present. A subset assertion is stable under an edge being added and only disturbed by one being removed, which is a deliberate act on the scenarios.

## Checks green at authoring, and how each is shown to discriminate

Six of the 49 pass now. A static check whose target already carries the asserted property passes without discriminating, so each is recorded with what establishes that it can fail:

| Test | Why it is green now | What discriminates it |
|---|---|---|
| `...test_no_role_in_this_repository_reaches_outside_its_own_directory_today` | The tree carries no such route — that is design.md Decision 2's own finding | `...test_the_scan_reports_a_role_that_does_reach_outside`, a fixture tree written to falsify it: two routes, both reported, and a role-local include not reported |
| `...test_the_scan_reports_a_role_that_does_reach_outside` | It is itself the fixture-driven discriminator | Supplies its own material |
| `...test_discovery_refuses_a_tree_with_no_scenarios_whatever_the_diff_said` | The discovery step already refuses an empty tree; what is new is that it must keep doing so whatever the diff said | `...test_discovery_accepts_a_tree_that_does_carry_a_scenario` — a step refusing everything would satisfy the refusal and fail every pull request |
| `...test_discovery_accepts_a_tree_that_does_carry_a_scenario` | Fixture-driven control | Supplies its own material |
| `...test_the_same_step_or_job_resolves_the_suite_as_owed_on_such_an_event` | The existing branch already forces the suite owed on an event with no diff | Its own `pull_request` control subtest: the same body must report `false` where the filter did |
| `...test_the_selection_written_on_an_event_with_no_diff_is_every_discovered_role` | **Vacuously.** Today the matrix reads the discovery output directly, so the "selection step" this test locates *is* the discovery step, and it already writes every discovered role | `...test_the_matrix_rows_come_from_the_step_that_runs_the_selector`, which is red now and pins the located step to one invoking the selector. Once that is green, this test is exercising the selection. **Read the two together; neither alone establishes the scenario.** |

The other 43 are red at authoring, on the property each asserts. That red-to-green transition is what establishes they discriminate on real content; no fixture is owed for the ones whose material is a fixture already, and the workflow-shape tests are discriminated by the workflow changing under them.

## Obsolete tests

**Not applicable as an operation:** this change's delta carries one `ADDED` requirement and no `MODIFIED`, `REMOVED` or `RENAMED` delta, so no requirement of `iac-cicd-pipeline` is superseded and no test is obsolete by that route.

**Three findings all the same**, each a **candidate for human confirmation**, not a conclusion. None was edited, deleted or disabled here; the first in particular is a test that will go red on a correct implementation, and someone has to decide that deliberately rather than discover it mid-implementation. The search was bounded to `.github/tests/*.py`, the dispatched test-path glob, and no earlier `test-plan.md` was supplied for this change.

1. **`test_ci_configuration.TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row` asserts a row this delta reverses.** `GATE_TABLE` in that module carries the row *"nothing under ansible/ changed and the suite ran anyway"* with `concludes_success=True`. The delta requires the opposite: *"It SHALL additionally fail where the matrix ran on a run that owed the suite nothing"*, which design.md Decision 5's table states as `success / success / no → fail`. **Evidence:** that `GateRow`'s own label and its `concludes_success=True`, against scenario *A matrix that ran where nothing was owed fails*. The new module re-asserts every other row of that table, including the four refusals, so nothing is lost by re-pointing this one — but it is the implementing author's edit to make, with the reason recorded.

2. **Two gate locators resolve the fourth input ambiguously once the selection exists.** `TestTheAggregatingGateDiscriminates._gate_step` (in `test_ci_configuration.py`) and `GateBodyMixin._gate_step` (in `test_the_suite_is_triggered_by_what_it_reads.py`) both assign `inputs["changed"]` to *whichever* `env:` entry matches `needs.<discovery>.outputs.`, in an `elif` chain. With two such outputs declared, the last one wins and the gate is fed a value under the wrong name; the other arrives unset, and a body running `set -u` then fails rows the table says must pass. **Evidence:** the `elif f"needs.{discovery_key}.outputs." in expression` branch in each, and the `set(inputs) == {"discovery", "matrix", "changed"}` guard that still passes with four declared variables. The new module's own locator disambiguates structurally — run-suite is the output the matrix `if:` reads, the selection is the one `strategy.matrix` reads — and that is the shape to re-point these to.

3. **`test_ci_configuration.TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing` selects its subject positionally.** It takes the *first* step whose `run` mentions both `molecule` and `ansible/roles`. A selection step inserted ahead of discovery re-targets it silently: the assertion goes on passing, about a different script. The change's own tasks.md 3.4a already names this; it is repeated here because it is the same class of finding and a reader of this list should not have to hold both documents. **Evidence:** the `candidates[0]` selection in that method.

No search of this glob found a test bearing on the *derivation*, the *closure* or the *attribution* — those behaviours do not exist yet, and nothing in `.github/tests` asserted anything about which roles the matrix runs. That is "no such test exists", not "none was found".

## Unresolved project questions

Recorded rather than resolved silently, with the assumption taken and what depends on it. A dispatched subagent has no channel to ask on; these are the questions that would otherwise have been asked.

1. **The selector's filename and public API.** Nothing in the change's artifacts names either. Assumed as tabulated above. **Depends on it:** every test in the module except the six workflow-shape and real-tree ones. Mitigated by the loader accepting any `ansible/scripts/*.py` exposing `select_roles`, so only the function names are hard.
2. **Whether `select_roles` takes its arguments positionally, and in that order.** Assumed `(changed_paths, root)`. **Depends on it:** every selection test.
3. **Whether the graph's node set is this repository's own roles only.** Assumed yes: a dotted Galaxy role name is a literal, resolves to no role of ours, and so contributes no edge rather than refusing. **Depends on it:** `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused`, and `docker`'s real `meta/main.yml`, which names `geerlingguy.docker`.
4. **What the selector does with a *literal* nested-playbook path.** The delta refuses the expression form by instance; a literal one is neither named as followed nor named as refused. The fixture for *a construction with no rule* deliberately uses a path-based `include_tasks` into another role rather than a literal `ansible-playbook`, so this question is not prejudged. **Depends on it:** nothing asserted here — but the implementer has to decide, and the decision belongs in the selector's own comments.
5. **Whether an `EmptySelection` is reachable other than through a tree carrying no scenarios at all.** The tests assert that one route. Under design.md Decision 3's widening it is the only one. **Depends on it:** `test_a_tree_whose_roles_carry_no_scenarios_fails_rather_than_selecting_nothing`, and the choice, in `test_a_diff_carrying_no_path_at_all_does_not_resolve_to_nothing`, to assert widening rather than refusal for the degenerate diff.
6. **No stack skill covered this suite's idiom.** The library carries `testing` and `python`; this project's static suite is `unittest`, not `pytest`, and neither skill carries `unittest` specifics. The module follows the eight sibling modules' established idiom instead — `unittest.TestCase`, `subTest`, `addCleanup`, sibling imports — which is the project convention and takes precedence anyway.

## What the implementation must make pass

In dependency order, which is also the order the red tests come green in:

1. `TestTheDerivationFollowsEveryConstructionThatReachesARole` and `TestTheDerivationRefusesWhatItCannotResolve` — the derivation and its refusals, over fixture trees.
2. `TestARolesOwnFilesReachingOutsideItAreRefused` and `TestARouteThatCannotBeClosedOverIsPermittedByInstance` — the two routes closed by refusal, and the permitted entry the tree's own instance needs. Ship the entry with the refusal: a selector shipping the refusal alone turns the required check red on every pull request in the repository.
3. `TestTheReverseClosureOverAFixtureGraph` — the closure, including the cycle.
4. `TestTheClosureOverTheRepositorysOwnTree`, `TestAttributionWidensRatherThanNarrows`, `TestARoleNothingConvergesAndNothingTestsWidensOnItsOwn`, `TestTheSelectorRefusesAnEmptySelection`, `TestTheSelectorEnumeratesRolesLikeTheRestOfTheSuite` — attribution, restriction, widening and the refusal, through `select_roles` over the real tree.
5. `TestTheMatrixIsFedTheSelection`, `TestARunCarryingNoDiffSelectsEveryRole`, `TestTheAggregatingGateReadsTheSelection` — the workflow: `list-files: json`, the selection output the matrix reads, the no-diff branch forcing both outputs, and the gate's fourth input with its new row.

`TestDiscoverysVacuityRefusalReadsTheUnfilteredTree` is green now and must stay green: it is the one that goes red if the vacuity refusal is moved behind the selection.
