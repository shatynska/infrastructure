# Test plan — make-the-pipeline-environment-agnostic

Written by an author other than whoever implements this change, from the delta
specs at commit `fbef40d` (the commit holding the approved plan) and from no
implementation. Nothing in this pass edited, deleted or disabled an existing
test: **this pass adds tests and never subtracts.**

This file is not an artifact the OpenSpec schema knows about, so it does not
appear among `openspec instructions apply`'s context files. It has to be read on
purpose, before implementing.

## Where the tests are

- `.github/tests/test_environment_agnostic_pipeline.py` — new, 64 test methods.
  Every test here is individually selectable with
  `python3 -m unittest test_environment_agnostic_pipeline.<Class>.<method>`
  run from `.github/tests`, or with
  `python3 -m unittest discover --start-directory .github/tests` from the
  repository root.

The Terraform-module and Molecule rows of this project's three test commands are
not used, and no test was placed under either: every property these deltas add
is a static read of a committed file, or an execution of a shell snippet taken
out of one. No test in this pass makes a network call, spawns a container or
runs a Terraform binary, so
`test_ci_configuration.TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`
— which reads every module in the directory — holds over the new module.

## Baseline

Full suite, taken before any test was written, from the repository root at
commit `fbef40d`:

    python3 -m unittest discover --start-directory .github/tests
    Ran 390 tests in 5.558s — OK

Nothing was failing beforehand. After this pass, the same command reports:

    Ran 454 tests in 5.6s — FAILED (failures=47)

All 47 failures are in the new module; the 390 pre-existing tests still pass.
Counted by method rather than by subtest, the new module contributes 64 methods,
of which **44 fail and 20 pass**. Failing is the correct outcome — nothing is
implemented — and each failing test's state is recorded below.

### What the 20 passing tests are, and why none of them is a false green

A test that passes on its first run before any implementation exists is an alarm
under this project's testing floor, so each one was investigated rather than
recorded as coverage.

- **Five are guards**, written to fail if the thing every other assertion in
  their class reads has disappeared: `test_the_repository_has_at_least_one_environment`,
  `test_there_is_a_name_to_look_for`, `test_the_workflow_still_plans`,
  `test_the_workflow_still_applies`, `test_the_gate_still_exists`. Passing is
  their intended state; they exist so that a class cannot pass over an empty set.
- **Fifteen assert properties the repository already has**, which the delta
  either carries through unchanged or states more widely than the existing suite
  did. Each is a regression guard over a restructure that could drop it
  silently:
  `test_no_job_running_terraform_plan_declares_an_environment` (stated over three
  workflows where the existing suite states it over one),
  `test_every_apply_job_declares_an_environment`,
  `test_each_apply_job_depends_on_a_job_that_plans`,
  `test_each_apply_job_applies_a_saved_plan_and_recomputes_none`,
  `test_the_drift_plan_does_not_take_the_state_lock`,
  `test_the_workflow_is_scheduled_and_manually_triggerable`,
  `test_the_scheduled_drift_workflow_carries_no_destroy_gate`,
  `test_the_path_filter_names_no_single_environment`,
  `test_every_job_running_terraform_plan_scans_for_secrets_first`,
  `test_the_registered_context_is_not_the_matrix_job`,
  `test_the_registered_context_concludes_on_the_plan_matrixs_behalf`,
  `test_the_reporting_job_depends_on_every_other_job`,
  `test_the_conventions_file_states_that_apply_is_not_run_locally`,
  `test_the_boundary_is_stated_outside_the_generated_workflow_block`,
  `test_the_readme_states_the_boundary_for_human_operators`.

Two of those fifteen are worth naming to the implementing author, because they
are **weak today and become load-bearing only after the restructure**:
`test_the_registered_context_concludes_on_the_plan_matrixs_behalf` passes now
because `validate` is itself the job that plans, and
`test_every_job_running_terraform_plan_scans_for_secrets_first` passes now
because there is one plan and it already sits after gitleaks in that job. Both
are what will catch the restructure going wrong.

### Four failures were repaired during this pass, and none was repaired by
### changing an expected value

Recorded because the testing floor requires a broken test to be distinguished
from a wrong implementation, and because each repair was to a **locator**, never
to an assertion:

1. A `terraform plan` matcher read `echo "::error::terraform plan failed …"` in
   `drift.yml` as a plan step. Repaired by making invocation detection
   quote-aware (`invocation_lines`).
2. The affected-environment resolution locator matched `pr-validation.yml`'s
   existing formatting-and-validation loop, which walks both directories and
   resolves nothing. Repaired by requiring the step to declare an `env:` input
   and write to `$GITHUB_OUTPUT`.
3. The discovery locator matched steps that merely *mention*
   `terraform/environments/prod` in a heading string. Repaired by the same
   `$GITHUB_OUTPUT` clause.
4. The digest-emitter locator matched `apply.yml`'s plan step, which takes
   `secrets.HCLOUD_TOKEN` through `env:` for the ordinary reason. Repaired by
   requiring the step's `id` to be exposed in the job's `outputs:`.

A fifth was a genuinely over-specified assertion: the README probe transcribed
AGENTS.md's wording and would have been "fixed" by editing README prose. It was
replaced with an anchor-and-neighbourhood read, which is this suite's existing
idiom for a prose obligation.

## Scenario accounting

Both delta specs together declare **52 scenarios** (48 in `iac-cicd-pipeline`,
4 in `iac-safety-hardening`). All 52 are accounted for below: 41 covered by at
least one named test, 11 recorded as uncovered or partially covered with the
reason.

### ADDED — Each Environment Declares Its Own Pipeline Configuration (5)

| Scenario | Test(s) |
|---|---|
| A new environment needs no workflow edit | `TestNoWorkflowNamesAnEnvironment.test_no_terraform_workflow_names_an_environment_directory`, `.test_no_terraform_workflow_maps_an_environment_to_a_secret`, `TestDiscoveryFailsClosed.test_discovery_emits_every_well_formed_environment` |
| Two environments declaring the same read-only secret are refused | `TestTheDeclarationCensusIsARealReadOfTheTree.test_two_environments_declaring_one_read_only_secret_are_reported`, `TestDiscoveryFailsClosed.test_discovery_fails_on_two_environments_sharing_a_read_only_secret`, `TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret` |
| Two environments declaring the same GitHub Environment are refused | `TestTheDeclarationCensusIsARealReadOfTheTree.test_two_environments_declaring_one_github_environment_are_reported`, `TestDiscoveryFailsClosed.test_discovery_fails_on_two_environments_sharing_a_github_environment`, `TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_github_environment` |
| An environment missing its declaration fails the pipeline | `TestDiscoveryFailsClosed.test_discovery_fails_on_an_environment_with_no_declaration`, `.test_discovery_fails_on_a_declaration_missing_a_field`, `TestTheDeclarationCensusIsARealReadOfTheTree.test_an_environment_with_no_declaration_is_reported`, `.test_an_environment_missing_a_field_the_workflows_read_is_reported`, `TestEveryEnvironmentCarriesAPipelineDeclaration.test_every_environment_directory_carries_a_declaration`, `.test_every_declaration_names_all_three_fields` |
| Discovery finding no environment fails rather than reporting success | `TestDiscoveryFailsClosed.test_discovery_fails_when_it_finds_no_environment` |

### MODIFIED — Pull Request Plan Visibility (5)

| Scenario | Test(s) |
|---|---|
| A secret scan precedes every plan | `TestEveryPlanIsScannedInItsOwnJob.test_every_job_running_terraform_plan_scans_for_secrets_first` (plus the existing ordering test — see the strengthening entry below) |
| Reviewer sees the plan without leaving GitHub | `TestThePlanMatrixReportsEveryEnvironment.test_each_environments_plan_comment_is_keyed_to_that_environment` |
| A shared module change is planned against every environment | `TestThePlanMatrixReportsEveryEnvironment.test_the_plan_runs_as_a_matrix_over_discovered_environments`, `TestTheAffectedEnvironmentSetIsResolvedFailClosed.test_the_pull_request_workflow_resolves_which_environments_are_affected` — **structural only**, see the uncovered list |
| One environment's plan failure does not hide the others | `TestThePlanMatrixReportsEveryEnvironment.test_one_environments_plan_failure_does_not_abandon_the_others`, `TestTheAggregatingValidateJobCoversThePlanMatrix.test_the_registered_context_concludes_on_the_plan_matrixs_behalf` |
| An environment-scoped change is planned against that environment only | `TestTheAffectedEnvironmentSetIsResolvedFailClosed.test_the_pull_request_workflow_resolves_which_environments_are_affected` — **structural only**, see the uncovered list |

### MODIFIED — Credential Scoping by Privilege (5)

| Scenario | Test(s) |
|---|---|
| Plan jobs receive only a read-only Hetzner token | `TestPlanJobsHoldOnlyTheirOwnReadOnlyToken.test_no_job_running_terraform_plan_declares_an_environment`, `.test_every_plan_job_selects_its_token_by_the_declared_secret_name` |
| A plan job holds no credential for another environment | `TestPlanJobsHoldOnlyTheirOwnReadOnlyToken.test_every_plan_job_selects_its_token_by_the_declared_secret_name`, `TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret` |
| An Environment omitting the write token does not apply with another's | `TestTheApplyJobEstablishesItResolvedItsOwnWriteToken.test_the_guard_fails_when_the_apply_job_resolved_the_repository_token`, `.test_the_guard_reads_the_repository_scoped_hcloud_token_by_that_name` |
| Apply job receives the read-write Hetzner token only after approval | `TestTheApplyJobEstablishesItResolvedItsOwnWriteToken.test_the_guard_passes_when_the_environment_supplied_its_own_token`, `TestEveryApplyIsGatedAndPerEnvironment.test_every_apply_job_declares_an_environment` — **partial**, see the uncovered list |
| Pull request validation requires no manual approval | `TestPlanJobsHoldOnlyTheirOwnReadOnlyToken.test_no_job_running_terraform_plan_declares_an_environment` |

### MODIFIED — Gated Production Apply Applies the Reviewed Plan (8)

| Scenario | Test(s) |
|---|---|
| Merge does not apply immediately | `TestEveryApplyIsGatedAndPerEnvironment.test_every_apply_job_declares_an_environment` — **partial**, the reviewer requirement is repository settings |
| A merge affecting one environment raises no other environment's approval | `TestTheAffectedEnvironmentSetIsResolvedFailClosed.test_the_apply_workflow_resolves_which_environments_a_merge_affects` — **structural only** |
| A shared module change reaches every environment | `TestTheAffectedEnvironmentSetIsResolvedFailClosed.test_the_apply_workflow_resolves_which_environments_a_merge_affects`, `TestEveryApplyIsGatedAndPerEnvironment.test_no_apply_job_names_its_environment_as_a_literal` |
| Reviewer sees the exact diff before approving | `TestEveryApplyIsGatedAndPerEnvironment.test_the_reviewer_reads_the_plan_from_the_run_summary`, `.test_each_apply_job_depends_on_a_job_that_plans` |
| Applied changes match the approved plan | `TestEveryApplyIsGatedAndPerEnvironment.test_each_apply_job_applies_a_saved_plan_and_recomputes_none`, `.test_the_saved_plan_artifact_is_named_per_environment` |
| Apply credentials are inaccessible before approval | `TestPlanJobsHoldOnlyTheirOwnReadOnlyToken.test_no_job_running_terraform_plan_declares_an_environment`, `TestEveryApplyIsGatedAndPerEnvironment.test_every_apply_job_declares_an_environment` — **partial** |
| An unresolvable set of affected environments fails the run | `TestTheAffectedEnvironmentSetIsResolvedFailClosed.test_the_resolution_refuses_an_unresolvable_input_rather_than_emptying_it` |
| A merge that cannot change infrastructure raises no approval request | `TestTheApplyWorkflowStillRaisesNoApprovalForNonInfrastructure.test_the_path_filter_names_no_single_environment`, plus the existing `test_ci_configuration.TestApplyWorkflowTriggerIsPathFiltered` (unaffected by this change) |

### MODIFIED — Destroy Policy Gate (6)

| Scenario | Test(s) |
|---|---|
| Unintended resource replacement blocks the pipeline | Existing `test_ci_configuration.TestDestroyPolicyGateFailsClosed` (carried through unchanged) — **uncovered behaviourally**, see the uncovered list |
| Deliberate teardown is possible with explicit acknowledgement | **Uncovered**, see the uncovered list |
| A disposable environment is destroyed without an override label | `TestTheDestroyGateReadsApplicabilityFromTheDeclaration.test_the_gate_takes_its_applicability_from_the_matrix`, `.test_the_gate_names_no_environment` — **structural only** |
| An environment declaring nothing is gated | `TestTheDeclarationCensusIsARealReadOfTheTree.test_an_environment_declaring_nothing_about_the_gate_is_gated`, `TestEveryEnvironmentCarriesAPipelineDeclaration.test_prod_declares_the_destroy_policy_gate_applicable` |
| An uninspectable plan blocks the pipeline | Existing `test_ci_configuration.TestDestroyPolicyGateFailsClosed.test_the_gate_does_not_swallow_an_inspection_failure`, `.test_the_gate_asserts_the_document_is_a_terraform_plan`, `.test_the_gate_distinguishes_an_uninspectable_plan_from_a_clean_one` (unchanged by this delta) |
| Drift-detection plan is not affected by this gate | `TestTheDestroyGateReadsApplicabilityFromTheDeclaration.test_the_scheduled_drift_workflow_carries_no_destroy_gate` |

### MODIFIED — Serialized Terraform Runs (2)

| Scenario | Test(s) |
|---|---|
| Two merges in quick succession apply in order | `TestConcurrencyIsDeclaredPerEnvironment.test_every_job_that_plans_or_applies_declares_its_own_concurrency_group` |
| Two environments do not queue behind each other | `TestConcurrencyIsDeclaredPerEnvironment.test_the_workflow_declares_no_workflow_level_concurrency_group`, `.test_every_job_that_plans_or_applies_declares_its_own_concurrency_group` |

### MODIFIED — Scheduled Drift Detection (6)

| Scenario | Test(s) |
|---|---|
| Manual out-of-band change is detected | `TestDriftDetectionIsPerEnvironment.test_the_drift_plan_runs_over_every_discovered_environment`, `.test_the_drift_issue_is_identified_per_environment` — **partial**, the detection half needs real infrastructure |
| Repeated drift does not open duplicate issues | `TestDriftDetectionIsPerEnvironment.test_the_drift_issue_is_identified_per_environment` — **structural only** |
| Drift in one environment does not resolve another's report | `TestDriftDetectionIsPerEnvironment.test_the_drift_issue_is_identified_per_environment` |
| Resolved drift closes the report | **Uncovered**, see the uncovered list |
| One environment's failure does not silence the rest | `TestDriftDetectionIsPerEnvironment.test_one_environments_failure_does_not_silence_the_rest`, `.test_the_reporting_job_depends_on_every_other_job` |
| Drift plan does not contend with an apply | `TestDriftDetectionIsPerEnvironment.test_the_drift_plan_does_not_take_the_state_lock` |

### MODIFIED — The Continuous-Integration Configuration Is Itself Verified (3)

This requirement's only change is the `always()` allowance; all three scenarios
are carried through and are already covered by the existing suite.

| Scenario | Test(s) |
|---|---|
| A regression in CI configuration fails the pull request that introduces it | Existing `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck`, `TestTheSuiteDiscriminates` |
| The suite runs regardless of what a pull request touched | Existing `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_is_unconditional` — **superseded in its job-level half**, see the obsolete list |
| The suite needs no privileged or external resource | Existing `test_ci_configuration.TestTheSuiteNeedsNoPrivilegedResource` and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`; the second covers the module added by this pass |

### MODIFIED — The Specification Record Is Verified in Continuous Integration (8)

This requirement's only change is the same `always()` allowance. All eight
scenarios are carried through and already covered by the existing suite; none
needed a new test.

| Scenario | Test(s) |
|---|---|
| A malformed specification or delta fails the pull request that introduces it | Existing `test_ci_configuration.TestTheSpecificationRecordIsValidatedByTheRequiredCheck` |
| An archived change with outstanding tasks fails the pull request that archives it | Existing, same class |
| Unperformed work disclosed without a reason fails the check | Existing `test_ci_configuration.TestUnperformedWorkIsDisclosedWithAReason`, `TestTheDisclosureCheckIsARealReadOfTheFile` |
| A disclosure section the check cannot read fails rather than passing | Existing `test_ci_configuration.TestTheDisclosureCheckIsARealReadOfTheFile` |
| The check cannot report success over a failed validation | Existing `test_ci_configuration.TestTheRecordValidationCannotReportSuccessOverAFailure`, `TestTheClosedFormIsARealReadOfTheScript` |
| The validation runs regardless of what a pull request touched | Existing `test_ci_configuration.TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_validating_step_is_unconditional` and `.test_the_job_enclosing_the_validating_step_is_unconditional` — the second is **superseded**, see the obsolete list |
| The validating tool is not resolved freshly at run time | Existing `test_ci_configuration.TestTheValidatingToolIsInstalledFromAPinnedManifest` |
| The pin is watched by the dependency-update configuration | Existing `test_ci_configuration.TestThePinIsWatchedByTheDependencyUpdateConfiguration` |

### MODIFIED — Write Credentials Confined to the Gated Pipeline (iac-safety-hardening, 4)

| Scenario | Test(s) |
|---|---|
| Local apply is refused by the API | **Uncovered**, see the uncovered list |
| Local plan remains available | **Uncovered**, see the uncovered list |
| A non-production environment's write token is confined identically | **Uncovered**, see the uncovered list |
| An agent opening the repository is told the boundary | `TestTheWriteCredentialBoundaryIsStatedToAgents.test_the_conventions_file_states_that_apply_is_not_run_locally`, `.test_the_boundary_is_stated_outside_the_generated_workflow_block`, `.test_the_readme_states_the_boundary_for_human_operators` |

## Uncovered and partially covered scenarios, with reasons

Recorded rather than omitted, so that the absence of a test is distinguishable
from the absence of the thought.

1. **A shared module change is planned against every environment** and **An
   environment-scoped change is planned against that environment only**
   (Pull Request Plan Visibility), and **A merge affecting one environment
   raises no other environment's approval** (Gated Production Apply) — covered
   **structurally**: a test asserts that a `${{ }}`-free resolution step exists
   which names both `terraform/modules` and `terraform/environments`, takes its
   input through `env:` and emits an output, and a second test executes it and
   requires it to refuse an empty input. The *mapping itself* (modules → every
   environment, `environments/<name>` → that one) is not executed, because the
   shape in which the changed paths reach that step is not fixed by this
   change's plan and inventing one here would either fail a legitimate
   implementation or force it into a shape nobody chose. Its behavioural
   verification is tasks.md 3.3's, run by the implementing author against each
   case. **This is the largest gap in this pass.**
2. **A disposable environment is destroyed without an override label** — covered
   structurally (applicability reaches the gate from the matrix, and the gate
   names no environment) but not behaviourally. The gate reads `terraform show
   -json`, and this suite may not spawn a Terraform binary; the same boundary
   the existing destroy-gate assertions already record.
3. **Unintended resource replacement blocks the pipeline** and **Deliberate
   teardown is possible with explicit acknowledgement** — carried through
   unchanged by this delta, and behaviourally unreachable for the same reason.
   The existing structural assertions stand; no new test was written, because
   nothing about them changes.
4. **Merge does not apply immediately**, **Apply credentials are inaccessible
   before approval**, **Apply job receives the read-write Hetzner token only
   after approval** — covered only in their workflow-file half. Whether the
   `production` Environment requires a reviewer, and whether a secret is
   readable before approval, are repository settings; this suite makes no
   network call and design.md is explicit that these tests must not be written
   to imply more.
5. **Manual out-of-band change is detected** and **Resolved drift closes the
   report** — the per-environment half of the first is covered; the detection
   and the close both need real infrastructure and a real GitHub issue, which
   no test command this project has can reach.
6. **Local apply is refused by the API**, **Local plan remains available**, **A
   non-production environment's write token is confined identically** — beyond
   every test command this project has. The first two are assertions about the
   Hetzner Cloud API's response to a token; the third is about which secrets a
   GitHub Environment holds and what is on an operator's workstation. None is a
   static read of a committed file.

## Assertion classification

Every test in the new module carries its classification in its own docstring, in
the convention `test_ci_configuration.py` established. In summary:

- **SPECIFIED** — 57 of the 64 methods. Each names the delta sentence or
  scenario it traces to.
- **DERIVED** — 7 methods, each naming the `design.md` decision or `tasks.md`
  item it traces to, and each carrying the sentence *"Reconsider this assertion,
  do not weaken it, if …"* where the design admits another means:
  `test_no_declaration_is_a_file_terraform_reads` (tasks 2.2);
  `test_a_clean_two_environment_tree_yields_no_offence` (the converse the four
  refusals need — a census that refused every tree would satisfy all of them);
  `test_the_registered_context_also_depends_on_discovery` (tasks 4.1a);
  `test_the_reporting_job_depends_on_every_other_job` (tasks 4.5);
  `test_the_boundary_is_stated_outside_the_generated_workflow_block` (this
  repository's own convention about the generated block);
  `test_the_reader_returns_the_values_the_declaration_states` and
  `test_a_terraform_file_is_never_read_as_a_declaration` (what stops every
  SPECIFIED assertion in the file from passing over a reader that returns
  nothing).
- **One classification is carried in a locator rather than in an assertion, and
  is stated here so it is not missed.** The three classes that execute a step
  body — `TestDiscoveryFailsClosed`,
  `TestTheAffectedEnvironmentSetIsResolvedFailClosed` and
  `TestTheApplyJobEstablishesItResolvedItsOwnWriteToken` — locate that body by a
  shape their SPECIFIED assertions then depend on: `${{ }}`-free, inputs through
  `env:`, result written to `$GITHUB_OUTPUT`. That shape is DERIVED, from
  tasks.md 3.4 and from `ansible-verify.yml`'s precedent, not from any scenario.
  Each locator's failure message states the shape it looked for and why, so a
  red test reads as a contract rather than as a mystery.
- **Deliberately untested** — the eleven scenarios listed above, each with its
  reason.

## Obsolete-test candidates

**Every entry below is a candidate for human confirmation, not a conclusion.**
Nothing in this pass edited, deleted or disabled any of them. The search was
bounded to `.github/tests/*.py`, the dispatched test-path glob, and to nowhere
else; no earlier `test-plan.md` was supplied to this pass, so no
scenario-to-test mapping from an archived change was consulted. Read this list
as *"these were found by this search"*, not as *"these are all that exist"*.

| Test (runner-selectable) | Superseded by | Evidence |
|---|---|---|
| `test_ci_configuration.TestSavedPlanIsWhatGetsApplied.test_exactly_one_job_declares_the_production_environment` | MODIFIED *Gated Production Apply Applies the Reviewed Plan*, together with ADDED *Each Environment Declares Its Own Pipeline Configuration* | Its body calls `self._job_with_environment("production")` and asserts exactly one match. The delta removes the literal `production` from workflow text ("Workflows SHALL NOT … map an environment to its … Environment name in workflow text"), so the locator finds zero jobs and the assertion fails for a reason that is the change working. Re-expressed additively by `test_environment_agnostic_pipeline.TestEveryApplyIsGatedAndPerEnvironment.test_every_apply_job_declares_an_environment` and `.test_no_apply_job_names_its_environment_as_a_literal`. |
| `test_ci_configuration.TestSavedPlanIsWhatGetsApplied.test_the_apply_job_depends_on_the_planning_job` | Same | Same locator, same first line. Re-expressed additively by `TestEveryApplyIsGatedAndPerEnvironment.test_each_apply_job_depends_on_a_job_that_plans`. |
| `test_ci_configuration.TestSavedPlanIsWhatGetsApplied.test_the_apply_job_applies_a_saved_plan_file` | Same | Same locator. Re-expressed additively by `TestEveryApplyIsGatedAndPerEnvironment.test_each_apply_job_applies_a_saved_plan_and_recomputes_none` and `.test_the_saved_plan_artifact_is_named_per_environment`. |
| `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_is_unconditional` | MODIFIED *The Continuous-Integration Configuration Is Itself Verified* | Its second half collects `job_offenders` for any job where `jobs(self.workflow)[job].get("if") is not None`. The delta now admits the single literal `always()` on a job declaring `needs:`, and design.md Decision 3a makes `validate` such a job. The **step-level** half of this test is unaffected and must stay. |
| `test_ci_configuration.TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_job_enclosing_the_validating_step_is_unconditional` | MODIFIED *The Specification Record Is Verified in Continuous Integration* | Its body collects jobs where `"if" in (jobs(self.workflow)[job] or {})`. Same allowance, same job. Its sibling `test_the_validating_step_is_unconditional` reads the **step** and is unaffected. |

No test was found bearing on the `REMOVED` or `RENAMED` operations, because
these deltas carry neither: every requirement is `ADDED` or `MODIFIED`.

### Affected but *not* obsolete — do not delete these

Two existing tests are named by tasks.md 5.3 and 5.4 and are easy to mistake for
obsolete ones. Neither is superseded:

- `test_ci_configuration.TestSecretScanningIsUnconditional.test_no_job_containing_a_secret_scanning_step_is_conditioned_on_terraform_changes`
  — tasks.md 5.3 is explicit that the plan matrix job's gate must be shaped as
  an **empty matrix** rather than an `if:`, *"not by relaxing the assertion"*.
  This test stays exactly as it is; it is a constraint on the implementation.
- `test_ci_configuration.TestSecretScanningIsUnconditional.test_secret_scanning_precedes_any_terraform_plan_in_the_same_job`
  — tasks.md 5.4 asks for it to be **strengthened**, not replaced: today
  `if not scan_indices or not plan_indices: continue` skips a job holding a plan
  and no scan. This pass did not edit it. The assertion the skip leaves unmade is
  added separately by
  `test_environment_agnostic_pipeline.TestEveryPlanIsScannedInItsOwnJob.test_every_job_running_terraform_plan_scans_for_secrets_first`,
  which reads *presence* where the existing test reads *order*. If 5.4 is
  performed, the two agree rather than duplicate; if it is not, the scenario is
  still covered.

## Unresolved project questions

Each was recorded rather than resolved silently, because this pass runs as a
dispatched subagent with no channel to ask on. Each names the assumption taken
and the tests that depend on it.

1. **The declaration file's name, format and field names are not decided.**
   design.md Decision 1 fixes what the declaration must *declare*; tasks.md 2.1
   assigns the file's name, format and fields to the implementing author, and
   neither exists at `fbef40d`.
   *Assumption taken:* none about the name or format. The file is discovered by
   shape — a committed file in the environment directory that Terraform does not
   read and that parses as a mapping — and its three fields are resolved from
   the declaration's own key names, normalised for case and punctuation: the
   destroy-gate field by a key carrying `destroy` whose value is a boolean, the
   read-only secret by a key carrying `secret` or `token`, the GitHub Environment
   by a key carrying `environment`. Every fixture builds its declarations from
   **prod's own committed declaration** — same filename, same keys, different
   values — so no fixture hard-codes a spelling.
   *Tests that depend on it:* every test in
   `TestEveryEnvironmentCarriesAPipelineDeclaration`,
   `TestTheDeclarationCensusIsARealReadOfTheTree`,
   `TestTheDeclarationReaderIsARealReadOfTheFile`, `TestDiscoveryFailsClosed`,
   and `TestNoWorkflowNamesAnEnvironment`.
   *The one thing the assumption does constrain:* the destroy-gate field must
   name the **gate** rather than its inverse — `destroy_policy_gate: true`, not
   `disposable: true` — because polarity cannot be read off a value and a
   declaration read backwards would report prod's gate applicable while the
   workflow disabled it. If the implementing author wants the inverse spelling,
   that is a decision to raise, not to absorb by editing the test.

2. **Two scenarios of the delta are in apparent tension about whether the
   destroy-gate field is required.** *An environment missing its declaration
   fails the pipeline* refuses "one lacking a field the workflows read", while
   *An environment declaring nothing is gated* requires a declaration silent on
   the gate to be accepted and gated.
   *Assumption taken:* the two string fields are required and the gate field is
   optional with a default of applicable, which is the only reading that
   satisfies both and is what design.md Decision 6 states ("a mistake in the
   declaration fails safe").
   *Tests that depend on it:*
   `TestEveryEnvironmentCarriesAPipelineDeclaration.test_every_declaration_names_all_three_fields`,
   `TestTheDeclarationCensusIsARealReadOfTheTree.test_an_environment_missing_a_field_the_workflows_read_is_reported`
   and `.test_an_environment_declaring_nothing_about_the_gate_is_gated`,
   `TestDiscoveryFailsClosed.test_discovery_fails_on_a_declaration_missing_a_field`.
   This is worth a reader's eye: it is the one place the delta could be read two
   ways.

3. **The environment-literal prohibition is written over "any file under
   `.github/workflows/`", and the assertions narrow it to three.**
   *Assumption taken:* the sweep covers `pr-validation.yml`, `apply.yml` and
   `drift.yml` — the workflows the requirement's own sentence names and this
   change restructures. A repository-wide sweep would fail `platform-deploy.yml`
   or a host workflow that legitimately addresses one host by name, for a reason
   this change did not introduce and cannot fix.
   *Tests that depend on it:* `TestNoWorkflowNamesAnEnvironment` (both
   assertions), `TestPlanJobsHoldOnlyTheirOwnReadOnlyToken` (both).
   Widening the sweep is a reviewable decision, not an authoring one.

4. **The changed-path resolution's input shape is not fixed.** tasks.md 3.3
   requires the mapping to be verifiable "by running its body standalone across
   each case", and 3.4 requires every input to arrive through `env:`; neither
   says what the changed paths look like when they get there.
   *Assumption taken:* only that the step declares an `env:` block and writes to
   `$GITHUB_OUTPUT`, which is enough to execute the fail-closed refusal without
   knowing the input's shape. The mapping itself is asserted structurally, and
   the gap is recorded above as this pass's largest.
   *Tests that depend on it:* all of
   `TestTheAffectedEnvironmentSetIsResolvedFailClosed`.

5. **No stack skill exists for GitHub Actions workflow YAML in this
   library.** The floor's instruction is to load the skill matching the stack
   under test where the library carries one; `python` was loaded for the
   runner's own idiom, and no Actions-specific skill exists. Recorded as an
   absence rather than resolved with a near-miss skill. No test depends on this;
   it is recorded because the floor requires the absence to be visible.
