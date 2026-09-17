# Test plan — promote-molecule-to-a-required-check

Derived from this change's delta specifications before any implementation of it existed, by an author who has not read an implementation of it. Written to satisfy task 1.1–1.7.

This file is **not** an artifact the OpenSpec schema knows about. It will not appear among the context files `openspec instructions apply` lists, and has to be opened on purpose by whoever implements next.

- **Test command:** `python3 -m unittest discover --start-directory .github/tests`, run from the repository root.
- **Test-path glob:** `.github/tests/*.py`. Every new test was written into the existing `.github/tests/test_ci_configuration.py`, appended as one new section before that file's `if __name__ == "__main__":` block. No existing line was edited, deleted or disabled.
- **Rows not in play:** no scenario in this delta belongs to the `terraform test` row or to the `molecule test --all` row of `AGENTS.md`'s Testing table. Every reachable scenario is a static read of a committed workflow file, or an execution of a shell snippet taken out of one.

## Baseline

Taken **before** the new tests were written, over the whole suite (the suite is one file, so a scoped baseline and a full one coincide):

```
$ python3 -m unittest discover --start-directory .github/tests
Ran 111 tests in 0.565s
OK
```

No test was failing beforehand, and none was skipping: the machine carries `bash`, `find`, `xargs`, `basename`, `grep`, `sort` and `jq`, so the existing extract-and-run test executed rather than skipping.

After the new tests were added, with the implementation not yet written:

```
$ python3 -m unittest discover --start-directory .github/tests
Ran 128 tests in 0.625s
FAILED (failures=12)
```

Seventeen tests were added. Twelve fail, none errors, and each fails for the reason the specification names rather than by an import failure or a defect in the test:

| Failing test | Failure message, abridged |
|---|---|
| `TestEveryRequiredCheckIsShapedToBeRegistrable.test_no_required_check_workflow_declares_a_workflow_level_path_filter` | `'paths' unexpectedly found in {'paths': ['ansible/**']}` — ansible-verify.yml's `pull_request` trigger declares `paths:` |
| `TestEveryRequiredCheckIsShapedToBeRegistrable.test_every_required_context_names_a_job_whose_name_is_a_literal` | ansible-verify.yml declares no job whose context is `ansible-verify`; it declares `['discover', 'molecule (${{ matrix.role }})']` |
| `TestTheAggregatingJobConcludesOnTheSuitesBehalf.test_the_aggregating_job_depends_on_discovery_and_on_the_matrix` | 0 jobs whose context is `ansible-verify` |
| `TestTheAggregatingJobConcludesOnTheSuitesBehalf.test_the_aggregating_job_runs_whatever_its_dependencies_concluded` | 0 jobs whose context is `ansible-verify` |
| `TestOnlyTheMoleculeMatrixIsGated.test_the_matrix_job_is_conditioned_on_the_change_detection_output` | the matrix job `molecule` carries no `if:` |
| `TestDiscoveryDeclaresTheLeastPrivilegeItNeeds.test_the_discovery_job_declares_the_read_scopes_its_change_detection_uses` | the discovery job `discover` declares no job-level `permissions:` block |
| `TestTheAggregatingGateDiscriminates.test_the_gate_script_can_be_executed_standalone` | 0 jobs whose context is `ansible-verify` |
| `TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row` | 0 jobs whose context is `ansible-verify` |
| `TestTheAggregatingGateDiscriminates.test_the_gate_names_the_skip_when_it_refuses_the_vacuous_green` | 0 jobs whose context is `ansible-verify` |
| `TestChangeDetectionResolvesTheGatesInput.test_a_run_that_is_not_a_pull_request_resolves_to_the_whole_suite` | found 0 `run:` steps in `discover` taking `github.event_name` through `env:` |
| `TestChangeDetectionResolvesTheGatesInput.test_a_pull_request_resolves_to_what_the_change_filter_found` | found 0 such steps |
| `TestChangeDetectionResolvesTheGatesInput.test_the_change_filter_itself_runs_only_where_there_is_a_diff` | the discovery job `discover` carries no change-filter step |

Five of the seventeen **pass on their first run**, which the testing floor treats as an alarm rather than as coverage. Each was investigated, and each is a regression guard over a property the current workflow already has and this change could remove — not a test that asserts nothing:

| Passing on first run | The property it guards, and the task that could break it |
|---|---|
| `TestEveryRequiredCheckIsShapedToBeRegistrable.test_the_generated_matrix_context_is_not_the_one_registered` | the matrix job's name is generated and is not `ansible-verify`; task 3.1 names a new job |
| `TestTheMoleculeWorkflowRunsOnPullRequestsAndOnDispatch.test_the_workflow_triggers_on_pull_requests_and_on_a_manual_dispatch` | both triggers survive task 2.1's rewrite of the `on:` block |
| `TestOnlyTheMoleculeMatrixIsGated.test_no_step_inside_the_matrix_job_carries_its_own_condition` | task 2.7 puts the gate on the job, not on a step |
| `TestOnlyTheMoleculeMatrixIsGated.test_role_discovery_runs_whatever_a_pull_request_touched` | tasks 2.3/2.6 add `if:` to the filter step only, not to discovery or its job |
| `TestDiscoveryDeclaresTheLeastPrivilegeItNeeds.test_no_job_in_the_molecule_workflow_receives_a_write_scope` | task 2.4 adds a `permissions:` block and must add no write scope |

### The two extract-and-run tests were checked for discrimination

A target-absent failure establishes only that the target is absent: the assertions never executed, so nothing yet said whether they are any good. Both extract-and-run tests were therefore exercised against a **throwaway fixture repository built outside this repository** (in a scratch directory, deleted afterwards; no file was written into the repository and no part of the implementation was authored). Against a conforming fixture all seventeen new tests pass. Against six deliberately defective variants, each is caught, and by the intended test alone:

| Defect injected into the fixture | Caught by |
|---|---|
| resolution polarity inverted — a dispatch defaults to `false` | `test_a_run_that_is_not_a_pull_request_resolves_to_the_whole_suite` |
| the gate reads a skipped matrix as a success | `test_the_gate_concludes_as_the_table_says_on_every_row`, `test_the_gate_names_the_skip_when_it_refuses_the_vacuous_green` |
| the gate does not check the discovery result first | `test_the_gate_concludes_as_the_table_says_on_every_row` |
| the gate treats `cancelled` as harmless | `test_the_gate_concludes_as_the_table_says_on_every_row` |
| the matrix job left ungated | `test_the_matrix_job_is_conditioned_on_the_change_detection_output` |
| a workflow-level `paths:` filter reinstated | `test_no_required_check_workflow_declares_a_workflow_level_path_filter` |

## The two extracted scripts, named distinctly

Task 1.5 requires these not be conflated as "the extracted script". They are different steps, in different jobs, with different tests:

- **The aggregating gate** — the single `run:` step of the job named `ansible-verify`. Its three inputs (the discovery job's result, the matrix job's result, the discovery job's change-detection output) arrive through the step's `env:` block. Tested by `TestTheAggregatingGateDiscriminates`, over design Decision 4's table.
- **The change-detection resolution** — a `run:` step in the discovery job that decides the "Ansible changed" input from `github.event_name`: on `pull_request` it is the change filter's output, on any other event it is `true`. Tested by `TestChangeDetectionResolvesTheGatesInput`, over the event name. The gate's table takes "Ansible changed" as *given*, so the polarity is invisible to the gate's test and is asserted only here.

Both tests locate their step and its inputs by the **expressions** the `env:` block assigns rather than by the variable names the implementation chooses, so the implementer is free to name the variables.

`TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row` iterates a case list of **seven rows** — the whole of Decision 4's table, four refusals and three passes — not the subset the scenarios happen to name. Two of those rows name two matrix results (`failure` and `cancelled`), exactly as the table's own cells do, so the run is seven rows and nine executions; the delta states cancellation and failure as separate scenarios and a gate can discriminate one while conflating the other.

## Scenario accounting

The delta declares **28** scenarios across four requirement blocks. All 28 are accounted for below, plus the one scenario reached through the REMOVED requirement. Nothing is omitted.

### MODIFIED — Required Status Checks Report on Every Pull Request (6)

| Scenario | Disposition |
|---|---|
| Documentation-only pull request remains mergeable | **Split.** Workflow-file half covered by `TestEveryRequiredCheckIsShapedToBeRegistrable.test_no_required_check_workflow_declares_a_workflow_level_path_filter` and by rows 5–6 of `TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row`. The **merge-outcome clause** ("the pull request SHALL be mergeable") is unreachable by any test command here — see *Unreachable* below |
| A required check reports without doing work it was not asked to do | `TestOnlyTheMoleculeMatrixIsGated.test_the_matrix_job_is_conditioned_on_the_change_detection_output`; `TestChangeDetectionResolvesTheGatesInput.test_a_pull_request_resolves_to_what_the_change_filter_found`; gate rows 5–6 |
| A required check whose work was skipped does not report success | gate row 3 (`test_the_gate_concludes_as_the_table_says_on_every_row`), plus `test_the_gate_names_the_skip_when_it_refuses_the_vacuous_green` |
| A required check whose change detection did not conclude does not report success | gate row 1 |
| A cancelled dependency does not report success | gate rows 4 and 7, `cancelled` result |
| A failed dependency reports failure whatever the change detection said | gate row 7, `failure` result |

Structural coverage the same requirement's prose obliges, with no scenario of its own: `TestTheAggregatingJobConcludesOnTheSuitesBehalf.test_the_aggregating_job_depends_on_discovery_and_on_the_matrix` and `.test_the_aggregating_job_runs_whatever_its_dependencies_concluded`; `TestEveryRequiredCheckIsShapedToBeRegistrable.test_the_generated_matrix_context_is_not_the_one_registered`.

### MODIFIED — Branch Protection on the Default Branch (3)

| Scenario | Disposition |
|---|---|
| Direct push to main is rejected | **Unreachable** — see below |
| Pull request with failing checks cannot merge | **Unreachable** — see below |
| Every registered context names a literal job | **Split.** Workflow-file half covered by `TestEveryRequiredCheckIsShapedToBeRegistrable.test_every_required_context_names_a_job_whose_name_is_a_literal`, driven by the module-level `REQUIRED_STATUS_CHECK_WORKFLOWS`. The **registration half** is unreachable — see below |

### MODIFIED — Gated Production Apply Applies the Reviewed Plan (5)

The only edit to this requirement is a cross-reference whose singular becomes a plural; all five scenarios are carried through verbatim and no behaviour they assert changes. Each is already covered, and no new test was written for it:

| Scenario | Covered by (existing) |
|---|---|
| Merge does not apply immediately | `TestSavedPlanIsWhatGetsApplied.test_exactly_one_job_declares_the_production_environment`, `.test_the_apply_job_depends_on_the_planning_job` |
| Reviewer sees the exact diff before approving | `TestSavedPlanIsWhatGetsApplied.test_the_planning_job_declares_no_environment` |
| Applied changes match the approved plan | `TestSavedPlanIsWhatGetsApplied.test_the_apply_job_applies_a_saved_plan_file` |
| Apply credentials are inaccessible before approval | `TestSavedPlanIsWhatGetsApplied.test_exactly_one_job_declares_the_production_environment` |
| A merge that cannot change infrastructure raises no approval request | `TestApplyWorkflowTriggerIsPathFiltered.test_the_path_filter_excludes_changes_that_cannot_affect_infrastructure`, `.test_the_push_trigger_declares_a_path_filter` |

The requirement's changed sentence — "There is more than one such workflow, and the constraint holds of each" — **is** newly covered, by `TestEveryRequiredCheckIsShapedToBeRegistrable.test_no_required_check_workflow_declares_a_workflow_level_path_filter`, which iterates every workflow behind a registered context rather than one.

### ADDED — Ansible Configuration Is Verified in Continuous Integration and Gates the Merge (14)

| Scenario | Disposition |
|---|---|
| Ansible-only pull request is linted and syntax-checked | Carried verbatim; covered by existing `TestAnsibleBlockingTier.test_an_ansible_path_filter_selects_changes_under_ansible`, `.test_the_blocking_tier_runs_ansible_lint`, `.test_the_blocking_tier_runs_an_ansible_syntax_check`. No new test: the lint tier's subject is `pr-validation.yml`, which this change does not touch. (Task 4.3 may rename those methods; the scenario's coverage moves with them.) |
| A newly added role scenario runs without a workflow change | Carried verbatim; existing `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_names_no_role_literally` |
| Every scenario a role declares is executed | Carried verbatim; existing `TestMoleculeDiscoveryAndScenarioCoverage.test_molecule_is_invoked_across_all_scenarios` |
| Discovering no roles fails rather than passes | Carried verbatim; existing `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing` |
| A failing Molecule scenario blocks the merge | **Split.** Aggregating-job half ("the aggregating job SHALL conclude failure") covered by gate rows 4 and 7; visibility half by existing `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_uses_no_continue_on_error`. The **merge-outcome clause** is unreachable — see below |
| A pull request touching no Ansible file starts no container | `TestOnlyTheMoleculeMatrixIsGated.test_the_matrix_job_is_conditioned_on_the_change_detection_output` and `.test_no_step_inside_the_matrix_job_carries_its_own_condition`; `TestChangeDetectionResolvesTheGatesInput.test_a_pull_request_resolves_to_what_the_change_filter_found` (`false` case); gate row 5 |
| Role discovery runs even where the suite does not | `TestOnlyTheMoleculeMatrixIsGated.test_role_discovery_runs_whatever_a_pull_request_touched`, plus gate row 1 for the "its failure SHALL fail the required status check" clause |
| A manual run verifies the whole suite | `TestChangeDetectionResolvesTheGatesInput.test_a_run_that_is_not_a_pull_request_resolves_to_the_whole_suite` (the second script, **not** the gate's table), supported by `.test_the_change_filter_itself_runs_only_where_there_is_a_diff` and by `TestTheMoleculeWorkflowRunsOnPullRequestsAndOnDispatch.test_the_workflow_triggers_on_pull_requests_and_on_a_manual_dispatch` |
| Ansible verification receives no production credential | Carried verbatim; existing `TestVerificationJobsCarryNoCredential.test_the_molecule_workflow_declares_no_environment` and `.test_the_molecule_workflow_consumes_no_secret`. Newly extended by `TestDiscoveryDeclaresTheLeastPrivilegeItNeeds.test_no_job_in_the_molecule_workflow_receives_a_write_scope` and `.test_the_discovery_job_declares_the_read_scopes_its_change_detection_uses`, which cover the requirement's new least-privilege sentence |
| Every scenario's platform image is pinned by digest | Carried verbatim; existing `TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest` (+ `.test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name`, `.test_every_platform_a_scenario_declares_is_checked_not_only_the_first`) |
| A scenario declaring no platform image fails rather than being skipped | Carried verbatim; existing `TestMoleculeScenarioImagesArePinnedByDigest.test_no_scenario_declares_a_platform_without_an_image`, `.test_a_scenario_declaring_no_platform_image_is_reported_by_name` |
| Scenarios sharing an image repository agree on its digest | Carried verbatim; existing `TestMoleculeScenarioImagesArePinnedByDigest.test_scenarios_sharing_an_image_repository_name_the_same_digest`, `.test_a_partial_digest_refresh_is_reported` |
| Installed Galaxy content is not held to this repository's pinning obligation | Carried verbatim; existing `TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest.*` (nine methods) |
| An upstream re-push cannot change what the suite ran against | Carried verbatim; existing `TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest` and `TestImageReferenceParsing.*` |

### REMOVED — Ansible Configuration Is Verified in Continuous Integration

The removed requirement carries eleven scenarios in `openspec/specs/iac-cicd-pipeline/spec.md`. Ten are re-added verbatim under the new requirement and are accounted for in the table above; the ADDED block's other four scenarios are new to it. One is dropped:

| Scenario | Disposition |
|---|---|
| A failing Molecule scenario does not block a merge | **Uncovered, by the operation.** Removed behaviour is not to be tested. Its inverse — *A failing Molecule scenario blocks the merge* — is what the ADDED block carries. The existing test whose docstring cites it is recorded as an obsolete-test candidate below |

## Scenarios no test command in this project can reach

Recorded as a disposition, not as a gap. Each is a property of repository settings or of a merge outcome; `.github/tests` may make no network call, and the requirement itself says so ("Registering a context is repository settings rather than repository content, so nothing in this repository can verify that it happened"). Each is covered by the ship-stage observation in tasks 8.5 and 8.6, not by a test.

| Scenario (or clause) | Why unreachable | Observed by |
|---|---|---|
| *Direct push to main is rejected* | branch-protection setting | task 8.5, first bullet — a direct read of `repos/<owner>/<repo>/branches/main/protection` |
| *Pull request with failing checks cannot merge* | merge outcome | task 8.5, second bullet — the throwaway pull request |
| *Every registered context names a literal job*, **registration half** | which contexts are registered is a repository setting | task 8.5, first bullet |
| *Documentation-only pull request remains mergeable*, **merge-outcome clause** | merge outcome | task 8.2 (the change's own doc-only pull request) and task 8.5 |
| *A failing Molecule scenario blocks the merge*, **merge-outcome clause** | merge outcome | task 8.5, second bullet |

Their workflow-file halves — no workflow-level path filter, a literal job name, a gate that discriminates — **are** reachable and are asserted, as the tables above record.

Every new test whose subject touches branch protection says in its own docstring what it did not establish, and the new section's header comment says it once more for the section as a whole. No green run of this suite is evidence that a context is registered.

One further path is unreachable by any test and is not a scenario: what `dorny/paths-filter` does on an event carrying no diff. Nothing in this repository has observed it — `pr-validation.yml` runs on `pull_request` only. `test_the_change_filter_itself_runs_only_where_there_is_a_diff` asserts the step is conditioned so it never runs there; the condition's effect is observed by task 8.6's manual dispatch.

## Assertion classification

Every new assertion is annotated in its own docstring as SPECIFIED (it traces to SHALL text or to a scenario in the delta) or DERIVED (it traces to `design.md` or `tasks.md` rather than to the specification). The derived ones, gathered:

| Derived assertion | What it traces to | Note |
|---|---|---|
| `TestTheMoleculeWorkflowRunsOnPullRequestsAndOnDispatch.test_the_workflow_triggers_on_pull_requests_and_on_a_manual_dispatch`, `workflow_dispatch` limb | scenario *A manual run verifies the whole suite* presupposes such a trigger without requiring this spelling | the `pull_request` limb of the same test is SPECIFIED |
| `TestTheAggregatingGateDiscriminates.test_the_gate_script_can_be_executed_standalone` | design Decision 5; tasks 3.2 | the scenarios state what the gate concludes, not how it is made testable |
| `TestTheAggregatingGateDiscriminates.test_the_gate_names_the_skip_when_it_refuses_the_vacuous_green` | tasks 3.2 ("a distinct message … naming it as a green that verified nothing") | the conclusion is specified; the message is not |
| `TestChangeDetectionResolvesTheGatesInput.test_the_change_filter_itself_runs_only_where_there_is_a_diff` | design Decision 1; tasks 2.3 | the specification requires the suite to run in full on a diffless event, not that the filter step be skipped |

Each carries "Reconsider this assertion, do not weaken it, if …" in its docstring, naming the alternative implementation that would justify revisiting it.

**Deliberately untested**, and recorded rather than dropped:

- The `branches: [main]` limb of the `pull_request` trigger (task 2.1). No scenario states it, `pr-validation.yml` carries it for reasons of its own, and a test would constrain the implementer without a requirement behind it.
- The exact `dorny/paths-filter` version pin (task 2.2). Task 2.2's own verification is a grep of both workflows; asserting pin parity here would be a new invented constraint whose scope is wider than this change.
- The workflow's `name:` and its top comment (tasks 3.4, 3.5). Prose, verified by review; `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_names_no_role_literally` already guards the one failure mode a comment can introduce.
- Whether `molecule test --all`'s recap names every scenario (design Decision 8, deferred to a queue entry). Not this change's subject, and unreachable from this row of the Testing table in any case.

## Obsolete tests — candidates for human confirmation, never conclusions

Search bound: `.github/tests/*.py`, the dispatched test-path glob, and nothing else. No earlier `test-plan.md` path was supplied for this change, so no scenario-to-test mapping was available beyond the docstrings in that file. Every entry below is a **candidate for confirmation by the implementer**, not a conclusion, and nothing in this pass edited, deleted or disabled any of them.

| Test | Superseded by | Evidence |
|---|---|---|
| `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_uses_no_continue_on_error` | REMOVED *Ansible Configuration Is Verified in Continuous Integration*; the ADDED requirement's scenario *A failing Molecule scenario blocks the merge* | its docstring cites the dropped scenario *A failing Molecule scenario does not block a merge* by name, and its failure message says `continue-on-error` "destroys the signal the advisory tier exists to collect". **The assertion itself is not obsolete and must stay** — under promotion `continue-on-error` reports a green *required* check for a failed suite. Only the docstring and the message are superseded (task 4.2/4.3) |
| `TestVerificationJobsCarryNoCredential.test_the_molecule_workflow_declares_no_environment` | REMOVED requirement | its docstring reads "SPECIFIED -- same scenario, advisory tier"; there is no advisory tier after this change. The assertion is carried through the ADDED requirement verbatim and must stay (task 4.3) |
| `TestRequiredCheckIsNotPathFiltered` (whole class; one method, `test_the_required_check_declares_no_workflow_level_path_filter`) | MODIFIED *Required Status Checks Report on Every Pull Request*; MODIFIED *Gated Production Apply Applies the Reviewed Plan* | its class docstring says "This asserts the second half" of a constraint stated in the singular, and its method reads `PR_VALIDATION` alone. The delta makes the constraint plural. Task 4.1 widens it; the new `TestEveryRequiredCheckIsShapedToBeRegistrable.test_no_required_check_workflow_declares_a_workflow_level_path_filter` **already asserts the plural form** over the module-level `REQUIRED_STATUS_CHECK_WORKFLOWS`, so 4.1 may reduce to reusing that constant, or to deciding the older method is now redundant. That decision is the implementer's — this pass neither made it nor edited the class |

Two further sites carry the stale word rather than a stale subject, found by the same search and offered as candidates for the same reason: `TestAnsibleBlockingTier` and its `test_the_blocking_tier_runs_*` methods name a tier label the delta renames (*Blocking tier* → *Lint tier*), and the class docstrings across the Ansible section abbreviate the requirement to "Ansible Configuration Is Verified in CI", a name that no longer exists after archive. The assertions are unaffected; task 4.3 decides whether to rename.

This list is **not empty and not exhaustive by construction**: it is what a search of the one file in the dispatched glob turned up, matching on docstring citations of the dropped scenario, on the word "advisory", and on the singular "the required check". A test bearing on the superseded behaviour whose docstring names neither would not have been found by it.

## Unresolved project questions

The project's conventions were read (`AGENTS.md`, and `CLAUDE.md`, which imports it). Two questions arose that they do not answer; each was resolved by assumption rather than by asking, because a dispatched author has no channel to ask on, and both are recorded here with the tests that depend on them:

1. **Whether a new test section belongs in the existing `.github/tests/test_ci_configuration.py` or in a second file under the same glob.** `AGENTS.md` names the glob, not the file count. Assumed: the existing file, because `TestTheSuiteNeedsNoPrivilegedResource` asserts the no-network, no-container, no-Terraform, standard-library-only constraints by reading `SUITE_PATH` — its own file alone — so a second file would sit outside those self-assertions. **All seventeen new tests depend on this assumption**, and moving them to a new file would silently drop them out of that guard.
2. **What the project calls the levels of its tests.** `AGENTS.md` names three test commands by subject rather than by level, and records no vocabulary for unit/integration/acceptance. Assumed: none is needed, and each test is placed by subject per the Testing table. Nothing depends on this beyond the vocabulary used in this file.

## What the implementation must make pass

Run exactly these, from the repository root, to check a given task:

```
python3 -m unittest test_ci_configuration.TestEveryRequiredCheckIsShapedToBeRegistrable   # tasks 2.1, 3.1
python3 -m unittest test_ci_configuration.TestTheMoleculeWorkflowRunsOnPullRequestsAndOnDispatch  # task 2.1
python3 -m unittest test_ci_configuration.TestTheAggregatingJobConcludesOnTheSuitesBehalf # task 3.1
python3 -m unittest test_ci_configuration.TestOnlyTheMoleculeMatrixIsGated                # tasks 2.6, 2.7
python3 -m unittest test_ci_configuration.TestDiscoveryDeclaresTheLeastPrivilegeItNeeds    # task 2.4
python3 -m unittest test_ci_configuration.TestTheAggregatingGateDiscriminates              # task 3.2
python3 -m unittest test_ci_configuration.TestChangeDetectionResolvesTheGatesInput         # tasks 2.2, 2.3, 2.5
```

(`python3 -m unittest` resolves `test_ci_configuration` when run with `.github/tests` on `PYTHONPATH`, or from inside that directory; the whole-suite command in the header needs neither.)

An individual method is selectable in the same form, e.g.

```
python3 -m unittest test_ci_configuration.TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row
```

Both extract-and-run classes need `bash`. Where it is absent they skip and name it, except under `CI`, where they fail instead — the same skip-vs-fail precondition the existing role-discovery test uses, for the same reason.
