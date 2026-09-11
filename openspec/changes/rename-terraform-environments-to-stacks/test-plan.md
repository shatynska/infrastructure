# Test plan — `rename-terraform-environments-to-stacks`

Derived from this change's six delta specifications at commit `541dec8`, the commit holding the approved plan, by an author other than whoever implements it. No implementation existed when these tests were written, and none was read: the superseded behaviour was established by comparing each delta against the requirement as it currently stands in `openspec/specs/`, never by reading workflow or Terraform code as an oracle.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files, and it is not reachable by `openspec show`. It has to be read on purpose, before implementing.

**This file was written in two passes, and the second is at the bottom.** Everything down to *Obsolete-test candidates* covers the twenty-one MODIFIED requirements the change carried when its plan was committed. A twenty-second was added to the delta afterwards; *Second pass* at the end of this file accounts for its eleven scenarios and carries the running totals for both. Do not stop at the first totals table.

## Where the tests are

One new module, added whole:

- `.github/tests/test_terraform_stacks_are_the_iterated_unit.py` — 40 tests across 10 classes.

The dispatched test-path glob was `.github/tests/*.py` and nothing was written outside it except this file. **This pass adds tests and never subtracts.** No existing test file was edited, deleted or disabled, and no module or test method was renamed — `tasks.md` 4.4 records the latter as deliberately out of scope.

## Baseline

**Full**, taken before any test was written, at `541dec8`:

    python3 -m unittest discover --start-directory .github/tests
    Ran 601 tests in 10.287s — OK

That matched `design.md` decision 6's recorded baseline of 601 green on trunk `032f923`, so the plan commit itself changed no test outcome.

**Re-baselined after rebasing onto trunk `74ea5b9`.** The figures above predate three of main's own continuous-integration changes — `narrow-the-molecule-trigger-to-what-it-reads`, `select-the-molecule-matrix-per-role` and `cache-the-apt-index-within-a-converge` — which between them added 111 tests and one module, `test_the_suite_is_triggered_by_what_it_reads.py`. Measured in a throwaway checkout of `74ea5b9`:

    Ran 712 tests in 20.294s — OK

And from this branch, with the derived module present:

    Ran 752 tests in 20.511s — FAILED (failures=72)

752 − 712 = 40, which is exactly this module's test count, unchanged by the rebase. **Every failure is in the new module**; filtering the `FAIL:`/`ERROR:` lines for anything outside `test_terraform_stacks_are_the_iterated_unit` yields zero. The 712 pre-existing tests are still green. The 72 count exceeds 40 because eight of the new tests report per-workflow or per-tool `subTest` failures.

One measurement trap is worth recording, because it reads as three real regressions. Taking the 712 figure by moving the derived module aside **in this working tree** instead makes `test_ci_configuration`'s three repository-wide credential scans fail: `tracked_files()` raises `TrackedFilesUnavailable` when a tracked path is absent from the working tree, rather than scanning around it. That is the suite behaving as designed, and it is why the trunk figure was taken in a checkout of trunk.

`terraform validate` was **not** run and no Molecule scenario was touched: this change touches no Terraform module and no Ansible role, which is `design.md` decision 6's own reading and the reason only the third of `AGENTS.md`'s three test rows was dispatched.

## What the failures establish, and what they do not

Thirty-eight of the forty fail, and almost all of them fail in the **second** of the four failure states the `testing` standard enumerates: **the target is absent**. `terraform/stacks/` does not exist and the four workflows still carry the old vocabulary, so those assertions never executed and nothing yet establishes whether they are any good. Do not report a red run here as evidence about the assertions themselves.

**Two tests pass before the implementation exists, deliberately, and each says so in its own docstring:**

- `TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_the_converge_play_still_names_the_environment_group_it_targets` — it guards against **overreach**, so its subject is a property the tree already has and must keep. It can only go red on a sweep that went too far, which is a state the tree cannot be in until the sweep runs.
- `TestTheMatrixAndItsOutputsNameTheStack.test_every_needs_output_read_names_an_output_that_job_publishes` — the four workflows agree with themselves today; what it holds is that they still agree once every output and every reader of it has been renamed.

Neither is the fourth failure state (an alarm). They are named here so a reader does not have to work that out from a green line.

The nine tests in `TestTheseReadsDiscriminate` also pass: they build fixture trees and establish that the reads above report what they claim to, rather than asserting anything about this change. A check that passes because it read nothing is what they exist against — at two stacks, three of the census reads are otherwise vacuous over the real repository.

## Running them

Whole module:

    python3 -m unittest discover --start-directory .github/tests -p 'test_terraform_stacks*'

One test, individually selectable — both forms verified to work from the repository root:

    PYTHONPATH=.github/tests python3 -m unittest \
      test_terraform_stacks_are_the_iterated_unit.TestTheTerraformRootIsNamedForTheStack\
.test_the_stack_root_holds_the_stack_directories

    python3 -m unittest discover --start-directory .github/tests \
      -k test_the_stack_root_holds_the_stack_directories

## The tests, and the assertion provenance of each

Every test is named below by its runner-selectable identifier, abbreviated to `Class.method` — prefix `test_terraform_stacks_are_the_iterated_unit.` to select it. **SPECIFIED** means the assertion traces to SHALL text or to a scenario in a delta spec; **DERIVED** means it traces to this change's `design.md` or `tasks.md` rather than to a scenario.

### `TestTheTerraformRootIsNamedForTheStack` — iac-repo-foundations

| Test | Provenance |
|---|---|
| `.test_the_stack_root_holds_the_stack_directories` | SPECIFIED — *Environment and Module Folder Structure*: "stack directories under `terraform/stacks/`"; scenario *Prod environment consumes a shared module*. Asserts a non-empty root plus the presence of `prod`, never a fixed membership: enumerating today's two would be the defect scenario *Adding a future environment does not require restructuring* forbids. |
| `.test_no_terraform_directory_is_still_divided_by_the_environment_axis` | DERIVED — `proposal.md`'s *What Changes* and `tasks.md` 2.1 and 2.4. No scenario states it; the absence of the old directory is a property of the move, not of what the pipeline does. |
| `.test_every_stack_consumes_the_shared_modules_by_relative_path` | SPECIFIED — scenario *Prod environment consumes a shared module*, and "Stacks consume modules by relative path". |
| `.test_no_stack_pins_a_module_version_of_its_own` | SPECIFIED — "there is no per-stack module version pinning, and none SHALL be introduced"; scenario *Adding a future environment does not require restructuring*. |
| `.test_every_stack_carries_its_committed_non_secret_configuration` | SPECIFIED — *Version Control Excludes State and Secrets*, whose tracked row is now `terraform/stacks/<name>/terraform.tfvars`; scenario *CI has the environment configuration it needs*. |

### `TestEveryStackDeclaresItsPipelineConfiguration` — iac-cicd-pipeline

| Test | Provenance |
|---|---|
| `.test_every_stack_directory_carries_a_declaration_with_both_required_fields` | SPECIFIED — *Each Environment Declares Its Own Pipeline Configuration*: "Every directory under `terraform/stacks/` SHALL carry a committed, machine-readable file"; scenario *An environment missing its declaration fails the pipeline*. |
| `.test_no_two_stacks_declare_the_same_secret_or_the_same_github_environment` | SPECIFIED — scenarios *Two environments declaring the same read-only secret are refused* and *Two environments declaring the same GitHub Environment are refused*. |
| `.test_no_stack_declares_the_write_tokens_own_name_as_its_read_only_secret` | SPECIFIED — scenario *A declaration naming the write token's own name is refused*. |

### `TestEachStackNamesAWorkspaceDerivedFromItsOwnName` — iac-state-management

| Test | Provenance |
|---|---|
| `.test_every_stack_names_a_workspace_derived_from_its_stack_name` | SPECIFIED — *Remote State Backend*: "named `infrastructure-<stack>`"; scenario *State is not stored locally*. Asserts the **derivation**, never that any HCP workspace was renamed — this change renames none, and entry 63 owns that. |
| `.test_no_two_stacks_name_the_same_workspace` | SPECIFIED — scenario *Two environments do not share a workspace*. |

### `TestDiscoveryIteratesTheStackRoot` — iac-cicd-pipeline

| Test | Provenance |
|---|---|
| `.test_each_terraform_workflow_carries_one_discovery_body_over_the_stack_root` | SPECIFIED — scenario *Discovery finding no environment fails rather than reporting success*, whose WHEN is now "discovery over `terraform/stacks/`"; and *Scheduled Drift Detection*'s "against every stack". |
| `.test_the_three_discovery_bodies_stay_identical` | DERIVED — `tasks.md` 3.1: "The three bodies stay byte-identical — `.github/tests` asserts it, and that assertion is what makes running one copy evidence about all three." |
| `.test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical` | SPECIFIED for the path rule — *Pull Request Plan Visibility* and *Gated Production Apply Applies the Reviewed Plan*. DERIVED for the identity — `tasks.md` 3.1a. |
| `.test_the_host_converge_discovery_reads_each_stacks_own_declaration` | SPECIFIED — scenario *A new environment needs no workflow edit*, which names the host-converge workflow. DERIVED for the locator shape and for the two kept handles (`inventory_root`, `group_vars_root`) — `design.md` decision 2a and `tasks.md` 3.2. |
| `.test_no_discovery_body_still_names_an_environments_root` | DERIVED — `tasks.md` 3.1 and 3.2, and `proposal.md`'s "a directory called `stacks/` iterated by a shell variable called `environments_root` … contradicts itself inside one file". |

### `TestTheMatrixAndItsOutputsNameTheStack` — iac-cicd-pipeline

DERIVED throughout, and stated as such in the class docstring: **no scenario names a matrix key or a job output.** What the scenarios state is that the pipeline iterates over stacks; `design.md` decision 2 is what resolves that obligation onto these identifiers.

| Test | Provenance |
|---|---|
| `.test_no_workflow_still_carries_a_retired_identifier` | DERIVED — `tasks.md` 3.3 and 8.4. Reads comments and `::error::` messages too, deliberately. |
| `.test_every_workflow_carries_the_replacements_expected_of_it` | DERIVED — `tasks.md` 3.3. Paired with the absence assertion, which alone would pass against an emptied file. |
| `.test_no_job_publishes_an_output_named_for_the_environment` | DERIVED — `tasks.md` 3.3. |
| `.test_every_needs_output_read_names_an_output_that_job_publishes` | DERIVED — `design.md` decision 6, which records this agreement as asserted for `apply.yml` alone and names the gap for `drift.yml` and `pr-validation.yml`. Widened to all four. |
| `.test_the_host_converge_dispatch_input_names_the_stack` | DERIVED — `tasks.md` 3.4: "the one operator-facing rename in the change". |

### `TestTheEnvironmentAxisIsNotRenamedWithTheUnit` — the four keepers

This class is the half of the check that catches **overreach**, which the retired-identifier sweep cannot see.

| Test | Provenance |
|---|---|
| `.test_the_converge_play_still_names_the_environment_group_it_targets` | SPECIFIED by a requirement this change does **not** modify — *Host Configuration Names the Environment It Targets* (`openspec/specs/iac-host-configuration/spec.md`). DERIVED for the mapping onto `TARGET_ENVIRONMENT`, `target_environment=` and `--vault-id` — `design.md` decision 2a. |
| `.test_the_target_environment_handle_is_derived_from_the_stack_name` | DERIVED — `design.md` decision 2 and `tasks.md` 3.5: the assignment becomes `TARGET_ENVIRONMENT: ${{ matrix.stack.name }}`. Asserts the assignment rather than the values, so it stays true when entry 62 makes the two diverge. |
| `.test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares` | SPECIFIED — *Gated Production Apply Applies the Reviewed Plan* ("Every stack's apply job SHALL declare an `environment:`") and *Credential Scoping by Privilege* ("No job that runs `terraform plan` SHALL declare an `environment:`"). |
| `.test_the_resource_labels_still_name_the_environment_axis` | SPECIFIED for the labels — *Consistent Resource Labeling* and its two scenarios. DERIVED for the equality with the directory name — `proposal.md`'s "No environment's *value* is renamed either". |

### `TestThePathRuleAndItsConsumersFollowTheStackRoot`

| Test | Provenance |
|---|---|
| `.test_the_changed_files_filter_names_the_stack_root` | SPECIFIED — *Pull Request Plan Visibility*'s path rule and scenario *Reviewer sees the plan without leaving GitHub*. A filter left at the old path matches nothing, and every plan is conditioned on its output. |
| `.test_validate_and_tflint_discover_directories_under_the_stack_root` | SPECIFIED — *Pull Request Validation Checks*: "against every directory under `terraform/modules/` and `terraform/stacks/`, discovered rather than enumerated"; scenario *A newly added module is validated and linted without a workflow change*. |
| `.test_dependabot_names_every_stack_directory_under_the_stack_root` | SPECIFIED — *Automated Dependency Updates*: "adding a Terraform module or stack SHALL include adding it here"; scenario *Every lockfile-bearing directory is covered*. |
| `.test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root` | SPECIFIED — *Pull Request Plan Visibility*: "identifying which stack each plan belongs to"; scenario *A shared module change is planned against every environment*. |
| `.test_the_drift_issue_title_names_the_stack_root` | SPECIFIED — *Scheduled Drift Detection*: "a **single, deduplicated** GitHub issue for that stack … identified per stack". |

### `TestTheWriteCredentialRecordNamesTheStackRoot` — iac-safety-hardening

| Test | Provenance |
|---|---|
| `.test_the_agents_record_states_the_prohibition_over_the_stack_root` | SPECIFIED — *Write Credentials Confined to the Gated Pipeline*, scenario *An agent opening the repository is told the boundary*, and the two scenarios naming "any stack directory under `terraform/stacks/`". Asserts only the half this change moves: that the directory the record points at is the one that now exists. |

### `TestNoCommittedFileStillNamesTheOldTerraformRoot`

| Test | Provenance |
|---|---|
| `.test_no_committed_file_names_the_old_terraform_root` | DERIVED — `tasks.md` 8.4, which states the grep as what "proves the sweep was complete rather than mostly complete". No scenario states it. |

**This is the assertion most likely to be argued with, so its scope is written into the class docstring rather than left to be read off the code:** it reads the whole tree (AGENTS.md's "Testing" puts a static read of a committed file in this suite's scope wherever the file lives); `openspec/` is pruned by the walker it borrows, which is a **superset** of the exclusions `tasks.md` 8.4 names and errs permissively; this module is excluded by path, because its own prose names the old root, and its needle is assembled from two string fragments so that a reader grepping the tree does not land on the check that forbids the thing; **nothing else is excluded and no allowance list is offered.** If the implementer finds a committed file that legitimately needs to quote the old path — a historical note in `docs/change-queue.md` or `docs/deferred-work.md` is the plausible case — that is a reviewable decision about what this change decided to keep, and it should be raised rather than resolved by adding an exemption to this test.

### `TestTheseReadsDiscriminate`

Nine tests, all DERIVED, none asserting anything about this change. They establish that the census reads the directories it is given, that a stack missing or carrying an unparseable declaration is **reported** rather than raising, that the old-root sweep reports a planted occurrence and reports nothing on a swept tree and refuses a tree it could not read, that the retired-identifier patterns match what they name and **do not match any of the four keepers**, and that the two interpolation forms normalise to one another. The idiom is the suite's own (`TestTheseReadsDiscriminate` in `test_a_second_environment.py`, the `…IsARealReadOfTheFile` classes in `test_ci_configuration.py`).

The keeper-matching pair is the load-bearing one: three of the four keepers contain the word `environment`, and a pattern that matched one of them would make the retired-identifier sweep unsatisfiable — the only route to green would be the overreach this change forbids.

## Scenario accounting

**98 `#### Scenario:` blocks across 21 MODIFIED requirements in 6 capabilities. All 98 are accounted for below exactly once.**

Three accounting outcomes are used, and the distinction matters because this change is a rename:

- **NEW** — covered by at least one test this pass added, named.
- **VOCAB** — *the delta changes only this scenario's vocabulary.* The behaviour it states is unchanged by this change and is already covered by the existing suite under an assertion the implementer **relocates** (see the obsolete list) rather than replaces. No new test is owed and none was written. This is an accounting outcome, not an implicit judgment that the scenario needs no test at all.
- **GAP** — uncovered, with the reason. Every GAP here is the same class of reason and it is the correct outcome rather than a failure: the scenario's subject is not a static read of a committed file, so `AGENTS.md`'s "Testing" section puts it outside this suite and the other two rows cannot reach it either (no Terraform module, no Ansible role). These are reported as gaps, not placed.

### iac-cicd-pipeline — *Pull Request Validation Checks* (7)

| # | Scenario | Outcome |
|---|---|---|
| 1 | PR with a misconfiguration fails validation | GAP — requires running Trivy over a pull request. |
| 2 | PR with a leaked credential fails validation | GAP — requires running `gitleaks` over a diff. |
| 3 | A credential outside Terraform is still caught | VOCAB — the requirement's unconditional-scan paragraph is unchanged; covered by `test_ci_configuration.TestSecretScanningIsUnconditional`. |
| 4 | Local and CI secret scans agree | VOCAB — covered by `test_ci_configuration.TestSecretScanVersionParity`; names no path. |
| 5 | Secret scanning requires no third-party license | VOCAB — covered by `test_ci_configuration.TestSecretScanningNeedsNoLicense`. |
| 6 | A newly added module is validated and linted without a workflow change | **NEW** — `TestThePathRuleAndItsConsumersFollowTheStackRoot.test_validate_and_tflint_discover_directories_under_the_stack_root`. |
| 7 | A module's tests run in CI | VOCAB — the `terraform test` loop iterates `terraform/modules/` only and is untouched by the rename. |

### *Pull Request Plan Visibility* (5)

| # | Scenario | Outcome |
|---|---|---|
| 8 | A secret scan precedes every plan | VOCAB — ordering within a job; the delta changes only the word for the unit. |
| 9 | Reviewer sees the plan without leaving GitHub | **NEW** — `.test_the_changed_files_filter_names_the_stack_root` and `.test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root`. |
| 10 | A shared module change is planned against every environment | **NEW** — `TestDiscoveryIteratesTheStackRoot.test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical`, with `.test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root` for the per-stack identification. |
| 11 | One environment's plan failure does not hide the others | VOCAB — `fail-fast: false` on the plan matrix; unchanged by the rename. |
| 12 | An environment-scoped change is planned against that environment only | **NEW** — `.test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical`, and `.test_the_changed_files_filter_names_the_stack_root`. |

### *Gated Production Apply Applies the Reviewed Plan* (11)

| # | Scenario | Outcome |
|---|---|---|
| 13 | Merge does not apply immediately | **NEW, partial** — `TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares` covers the `environment:` declaration. GAP for the pause itself: whether an Environment requires a reviewer is a repository setting, which no committed file states. |
| 14 | A merge affecting one environment raises no other environment's approval | **NEW, partial** — `.test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical` covers the path rule that decides it. GAP for the approval request, which is a GitHub Environment behaviour. |
| 15 | A shared module change reaches every environment | **NEW, partial** — same test for the path rule; GAP for the per-Environment protection rules. |
| 16 | A plan its own gate refused is not applied | VOCAB — covered by `test_planned_environment_apply_stage.TestASavedPlanIsPublishedOnlyAfterItsOwnChecksPassed`; the delta changes only the word. |
| 17 | One environment's failed plan does not block another's apply | VOCAB — covered by `test_planned_environment_apply_stage.TestTheApplyStageRunsOverThePlanned`. |
| 18 | An unresolvable set of planned environments fails the run | VOCAB — covered by `test_planned_environment_apply_stage.TestThePlannedSetResolutionIsRunRatherThanRead`. |
| 19 | Reviewer sees the exact diff before approving | VOCAB — the plan job's summary step; unchanged apart from the heading, which #10 covers. |
| 20 | Applied changes match the approved plan | GAP — the saved-plan/state-divergence refusal is Terraform runtime behaviour. |
| 21 | Apply credentials are inaccessible before approval | GAP — a property of GitHub Environment secret resolution, not of any committed file. |
| 22 | An unresolvable set of affected environments fails the run | VOCAB — the fail-closed resolution is covered by the existing affected-set tests; this pass asserts the two copies stay identical after the rename (#12). |
| 23 | A merge that cannot change infrastructure raises no approval request | VOCAB — `apply.yml`'s workflow-level filter is `terraform/**` and `tasks.md` 5.1 obliges it be verified unchanged; covered by `test_ci_configuration.TestApplyWorkflowTriggerIsPathFiltered`. |

### *Credential Scoping by Privilege* (5)

| # | Scenario | Outcome |
|---|---|---|
| 24 | Plan jobs receive only a read-only Hetzner token | **NEW, partial** — `.test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares` holds the no-`environment:`-on-plan half in `apply.yml`. GAP for what the token can actually do at the Hetzner API. |
| 25 | A plan job holds no credential for another environment | GAP — a property of Hetzner project scoping. The committed half (each stack declaring a distinct read-only secret) is covered by `TestEveryStackDeclaresItsPipelineConfiguration.test_no_two_stacks_declare_the_same_secret_or_the_same_github_environment`. |
| 26 | An Environment omitting the write token does not apply with another's | VOCAB — covered by `test_environment_agnostic_pipeline.TestTheApplyJobEstablishesItResolvedItsOwnWriteToken`. |
| 27 | Apply job receives the read-write Hetzner token only after approval | GAP — GitHub Environment secret resolution. |
| 28 | Pull request validation requires no manual approval | **NEW, partial** — same test as #24: no plan job declares an `environment:`. |

### *Destroy Policy Gate* (6)

| # | Scenario | Outcome |
|---|---|---|
| 29 | Unintended resource replacement blocks the pipeline | GAP — requires a real plan's JSON. |
| 30 | Deliberate teardown is possible with explicit acknowledgement | GAP — same. |
| 31 | A disposable environment is destroyed without an override label | VOCAB — the per-stack applicability read is covered by `test_environment_agnostic_pipeline.TestTheDestroyGateReadsApplicabilityFromTheDeclaration`. |
| 32 | An environment declaring nothing is gated | VOCAB — same test; the default is unchanged by the rename. |
| 33 | An uninspectable plan blocks the pipeline | VOCAB — covered by `test_ci_configuration.TestDestroyPolicyGateFailsClosed`. |
| 34 | Drift-detection plan is not affected by this gate | VOCAB — `drift.yml` runs no gate; unchanged. |

### *Serialized Terraform Runs* (3)

| # | Scenario | Outcome |
|---|---|---|
| 35 | Two merges in quick succession apply in order | GAP — GitHub Actions queueing behaviour. The committed half (a `concurrency` group per stack, at job level) is covered by `test_environment_agnostic_pipeline.TestConcurrencyIsDeclaredPerEnvironment`, whose group expressions this rename moves — see the obsolete list. |
| 36 | Two environments do not queue behind each other | VOCAB — same; the group is derived from the stack's identity, and what changes is the matrix key it reads. |
| 37 | A queued plan does not cancel an apply awaiting approval | VOCAB — covered by `test_planned_environment_apply_stage.TestThePlanAndApplyGroupsAreSeparate`. |

### *Scheduled Drift Detection* (6)

| # | Scenario | Outcome |
|---|---|---|
| 38 | Manual out-of-band change is detected | **NEW, partial** — `.test_the_drift_issue_title_names_the_stack_root` covers the issue the run records it on. GAP for the detection itself, which is a real plan against Hetzner. |
| 39 | Repeated drift does not open duplicate issues | **NEW, partial** — same test: the dedup key is the whole title, so a title left at the old root matches nothing. GAP for the dedup behaviour at run time. |
| 40 | Drift in one environment does not resolve another's report | **NEW, partial** — same test; the per-stack title is what makes it true. |
| 41 | Resolved drift closes the report | **NEW, partial** — same test: the close path matches on the same title. |
| 42 | One environment's failure does not silence the rest | VOCAB — `fail-fast: false` on the drift matrix; unchanged. |
| 43 | Drift plan does not contend with an apply | VOCAB — `-lock=false`; names no path and no unit. |

### *Each Environment Declares Its Own Pipeline Configuration* (6)

| # | Scenario | Outcome |
|---|---|---|
| 44 | A new environment needs no workflow edit | **NEW** — `TestDiscoveryIteratesTheStackRoot.test_each_terraform_workflow_carries_one_discovery_body_over_the_stack_root` and `.test_the_host_converge_discovery_reads_each_stacks_own_declaration`, which between them cover all four workflows the scenario names. |
| 45 | Two environments declaring the same read-only secret are refused | **NEW** — `TestEveryStackDeclaresItsPipelineConfiguration.test_no_two_stacks_declare_the_same_secret_or_the_same_github_environment`, plus the discriminators that stop it passing vacuously at two stacks. |
| 46 | Two environments declaring the same GitHub Environment are refused | **NEW** — same test. |
| 47 | A declaration naming the write token's own name is refused | **NEW** — `.test_no_stack_declares_the_write_tokens_own_name_as_its_read_only_secret`. |
| 48 | An environment missing its declaration fails the pipeline | **NEW** — `.test_every_stack_directory_carries_a_declaration_with_both_required_fields`, with `TestTheseReadsDiscriminate.test_a_stack_missing_its_declaration_is_reported` and `.test_an_unparseable_declaration_is_reported_rather_than_raised`. |
| 49 | Discovery finding no environment fails rather than reporting success | **NEW, partial** — `.test_each_terraform_workflow_carries_one_discovery_body_over_the_stack_root` and `.test_no_discovery_body_still_names_an_environments_root` cover that the body iterates the new root. The **executed** refusal is covered by `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed`, whose locator this rename moves — see the obsolete list. |

### iac-data-volumes — *Conditional Prod Volume Creation* (4)

| # | Scenario | Outcome |
|---|---|---|
| 50 | Toggle enabled creates the volume | GAP — the obligation is on what `terraform plan` shows. The delta changes only the word ("the prod **stack**'s volume-enabled variable", "declared in the **stack**'s variables and non-secret tfvars"); the file it describes is `terraform/stacks/prod/terraform.tfvars`, whose presence `.test_every_stack_carries_its_committed_non_secret_configuration` asserts. No `terraform test` is owed: `AGENTS.md`'s Terraform row covers `terraform/modules/<name>/tests/`, and a stack is not a module. |
| 51 | Volume toggle disabled creates nothing | GAP — same. |
| 52 | Disabling the server also removes the volume | GAP — same. |
| 53 | Re-enabling requires no lost configuration | GAP — same. |

### iac-repo-foundations — *Environment and Module Folder Structure* (4)

| # | Scenario | Outcome |
|---|---|---|
| 54 | Prod environment consumes a shared module | **NEW** — `TestTheTerraformRootIsNamedForTheStack.test_the_stack_root_holds_the_stack_directories` and `.test_every_stack_consumes_the_shared_modules_by_relative_path`. |
| 55 | Adding a future environment does not require restructuring | **NEW** — `.test_every_stack_consumes_the_shared_modules_by_relative_path` and `.test_no_stack_pins_a_module_version_of_its_own`; `.test_the_stack_root_holds_the_stack_directories` is deliberately written not to enumerate today's stacks, which is this scenario's own obligation. |
| 56 | A shared module change reaches every environment without an imposed order | VOCAB — covered by `test_a_second_environment.TestNoEnvironmentsApplyWaitsOnAnother`. |
| 57 | Promotion ordering is exercised at the approval, not by the workflow | GAP — states a discipline available to a human approver, which the requirement itself calls "not a mechanism the pipeline enforces". Nothing in a committed file can carry it. |

### *Version Control Excludes State and Secrets* (3)

| # | Scenario | Outcome |
|---|---|---|
| 58 | Local state is never staged | VOCAB — a `.gitignore` property, unchanged; the delta moves only the table's path. |
| 59 | CI has the environment configuration it needs | **NEW** — `.test_every_stack_carries_its_committed_non_secret_configuration`. |
| 60 | Secret-bearing variable file is not committable | VOCAB — the `*.secret.tfvars` rules name no path. |

### iac-safety-hardening — *Provider-Level Deletion Protection* (3)

| # | Scenario | Outcome |
|---|---|---|
| 61 | Prod server is protected against console deletion | GAP — what the Hetzner API refuses. |
| 62 | Prod volume is protected against console deletion | GAP — same. |
| 63 | Shared module remains reusable by a future non-prod environment | GAP — requires `terraform destroy` against a stack that does not exist. The delta's only edit here is the path in the `prevent_destroy` sentence. |

### *Data Durability for Stateful Resources* (1)

| # | Scenario | Outcome |
|---|---|---|
| 64 | Server is created with backups enabled | GAP — what the created server carries. The delta's only edit is `terraform/environments/prod/` → `terraform/stacks/prod/` in a sentence about a server, which `design.md` decision 2 names as the case where only the path changes. |

### *Consistent Resource Labeling* (2)

| # | Scenario | Outcome |
|---|---|---|
| 65 | Prod resources are labeled | **NEW** — `TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_the_resource_labels_still_name_the_environment_axis`, as a static read of what the stack declares. GAP for the label on the created resource. |
| 66 | Prod volume is labeled | **NEW** — same test; the volume module receives the same `environment` value. GAP for the created resource. |

### *Write Credentials Confined to the Gated Pipeline* (5)

| # | Scenario | Outcome |
|---|---|---|
| 67 | Local apply is refused by the API | GAP for the refusal. The committed half — the record naming a directory that exists — is `TestTheWriteCredentialRecordNamesTheStackRoot.test_the_agents_record_states_the_prohibition_over_the_stack_root`. |
| 68 | Local plan remains available | GAP — same. |
| 69 | A non-production environment's write token is confined identically | GAP — where a secret lives is a repository setting. |
| 70 | An agent opening the repository is told the boundary | **NEW** — `.test_the_agents_record_states_the_prohibition_over_the_stack_root`. |
| 71 | The record covers an environment added after it was written | VOCAB — the generalisation is covered by `test_a_second_environment.TestTheWriteCredentialRecordCoversEveryEnvironment` and `test_environment_agnostic_pipeline.TestTheWriteCredentialBoundaryIsStatedToAgents`; this pass asserts only the path half. |

### *Automated Dependency Updates* (13)

| # | Scenario | Outcome |
|---|---|---|
| 72 | Provider version update is proposed automatically | GAP — Dependabot's own behaviour. |
| 73 | Every lockfile-bearing directory is covered | **NEW** — `.test_dependabot_names_every_stack_directory_under_the_stack_root`, which reads the entries themselves. The set comparison in `test_ci_configuration.TestDependabotCoverage` is generic and survives the rename untouched; what it cannot report is a configuration naming the **old** root, which is what the new test adds. |
| 74 | Action version update is proposed automatically | VOCAB — `github-actions` ecosystem; names no path. |
| 75 | Platform image update is proposed automatically | VOCAB — `docker-compose` ecosystem; untouched. |
| 76 | Every Compose file declaring a service image is covered | VOCAB — untouched by this change. |
| 77 | A stack file the fetcher's name pattern does not match is reported | VOCAB — "stack" here is the **Compose** stack, a different sense the delta's own stack definition distinguishes; untouched. |
| 78 | A proposed image update is not exempt from the stack's own obligations | VOCAB — same sense; untouched. |
| 79 | Pre-commit hook revisions are refreshed on a schedule | VOCAB — untouched. |
| 80 | A workflow-opened pull request receives the required status checks | VOCAB — untouched. |
| 81 | No workflow opens a pull request with the default workflow token | VOCAB — untouched. |
| 82 | The default workflow token is not left holding unused write authority | VOCAB — untouched. |
| 83 | A permissions declaration is present rather than merely absent | VOCAB — untouched. |
| 84 | A long-lived automation credential is documented where it can be found | VOCAB — untouched. |

The single sentence this delta changes in *Automated Dependency Updates* is "adding a Terraform module or **stack** SHALL include adding it here", which #73 is the scenario for. The other twelve are carried along because a MODIFIED requirement replaces its block whole.

### iac-server-lifecycle — *Conditional Prod Server Creation* (4)

| # | Scenario | Outcome |
|---|---|---|
| 85 | Toggle enabled creates the server | GAP — what `terraform plan` shows; see #50. |
| 86 | Toggle disabled creates nothing | GAP — same. |
| 87 | Toggle disabled also removes resources coupled to the server | GAP — same. |
| 88 | Re-enabling requires no lost configuration | GAP — same. The committed half ("declared in the **stack**'s variables and non-secret tfvars") is `.test_every_stack_carries_its_committed_non_secret_configuration`. |

### iac-state-management — *Remote State Backend* (3)

| # | Scenario | Outcome |
|---|---|---|
| 89 | State is not stored locally | **NEW, partial** — `TestEachStackNamesAWorkspaceDerivedFromItsOwnName.test_every_stack_names_a_workspace_derived_from_its_stack_name` covers that each stack under the new root configures its own workspace. GAP for what `terraform init` writes to disk. |
| 90 | Two environments do not share a workspace | **NEW** — `.test_no_two_stacks_name_the_same_workspace`. |
| 91 | Plan and apply run outside HCP Terraform's own execution | GAP — a property of the workspace's Execution Mode, which lives in the HCP UI. |

### *State Locking* (1)

| # | Scenario | Outcome |
|---|---|---|
| 92 | Concurrent apply attempts are serialized | GAP — HCP Terraform's locking. The delta's only edit is the path in the WHEN. |

### *Workspace Execution Mode Set to Local* (3)

| # | Scenario | Outcome |
|---|---|---|
| 93 | Saved plan files are usable by the pipeline | GAP — depends on the workspace's Execution Mode. |
| 94 | A newly created workspace is set to Local before its environment is used | GAP — "the setting lives in the HCP Terraform UI or API rather than in any file this repository commits", by the requirement's own words. |
| 95 | Remote execution mode is treated as misconfiguration | GAP — same. |

### *Each Environment Has a Dedicated Hetzner Cloud Project* (3)

| # | Scenario | Outcome |
|---|---|---|
| 96 | One environment's credentials do not reach another's project | GAP — Hetzner project scoping. |
| 97 | An ungated environment cannot reach a reviewed environment's resources | GAP — same. |
| 98 | Two environments may name a resource identically | GAP — a consequence of project separation; no committed file states it. |

### Totals

| Outcome | Count |
|---|---|
| NEW (covered by a test this pass added, whole or partial) | 28 |
| VOCAB (vocabulary-only delta; behaviour covered by an existing assertion the implementer relocates) | 36 |
| GAP (uncovered, not a static read of a committed file) | 34 |
| **Total** | **98** |

No scenario was reached through a `REMOVED` or `RENAMED` delta: all twenty-two deltas are `MODIFIED`, and `design.md` decision 3 records that neither requirement names nor scenario names are renamed here.

## Obsolete-test candidates

All twenty-two deltas are `MODIFIED`, so this list is **applicable and non-empty**. Every entry is a **candidate for human confirmation, not a conclusion.** Nothing below was edited, deleted or disabled by this pass.

**The word "obsolete" means something narrow here, and getting it wrong would be expensive.** These tests assert correct behaviour. What is superseded is the **vocabulary they assert it in**: each one keys on the literal `terraform/environments`, or on an identifier this change retires, and after the move it fails against a correct implementation. `tasks.md` 4.1 and 4.2 already assign their repair to the implementing author. **The action each one needs is a re-pointing, never a deletion**, and `tasks.md` 4.4 forbids renaming the module or the method while doing it.

The search was bounded to the dispatched test-path glob `.github/tests/*.py` and nowhere else. No earlier `test-plan.md` was supplied, so no scenario-to-test mapping was available to draw on; the evidence below is a read of each module's own source — an AST walk attributing every occurrence of a retired literal to its enclosing function or class.

### Superseded by the path move (`terraform/environments` → `terraform/stacks`)

Superseding delta: *Environment and Module Folder Structure* (iac-repo-foundations), and every requirement whose text carries the path.

| Test | Evidence |
|---|---|
| `test_environment_agnostic_pipeline` module constant `ENVIRONMENTS_DIR` (line 122) and helper `environment_directories()` (line 211) | Both build the path from `"terraform" / "environments"`. Everything in that module reading a declaration goes through them. |
| `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_every_environment_directory_carries_a_declaration` | Asserts over `environment_directories()`; its message names the old root. |
| `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_the_repository_has_at_least_one_environment` | Same helper; also names `ENVIRONMENTS_DIR`. |
| `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed._discovery_step` and `.test_discovery_fails_when_it_finds_no_environment` | **The highest-value entry in this list.** `_discovery_step` locates the body it *executes* by the `terraform/environments` literal the body contains. `design.md` decision 6 is explicit that the locator keys on the path, not the step name — so this is the locator that must move, and an implementer who renames step names alone moves nothing it reads. |
| `test_environment_agnostic_pipeline._resolution_step_of` (line ~2772) | Locates both the discovery step and the changed-path resolution by the same literal. |
| `test_environment_agnostic_pipeline.TestTheAffectedEnvironmentSetIsResolvedFailClosed._resolution_step` | Same literal. |
| `test_environment_agnostic_pipeline.TestTheAffectedEnvironmentMappingIsRunRatherThanRead.test_an_environment_scoped_change_selects_that_environment_only` and `.test_changes_in_two_environments_select_both` | Feed the resolution body scratch paths written as `terraform/environments/staging/main.tf` and `terraform/environments/prod/terraform.tfvars`. `tasks.md` 4.2 is about exactly this: a scratch path left at the old root makes the test pass for the wrong reason. |
| `test_environment_agnostic_pipeline.TestTheDuplicatedBodiesStayIdentical.test_every_workflow_discovers_environments_the_same_way` and `.test_both_workflows_resolve_the_affected_set_the_same_way` | Both locators are `lambda body: "terraform/environments" in body …`. Replaced in effect by `TestDiscoveryIteratesTheStackRoot.test_the_three_discovery_bodies_stay_identical` and `.test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical` — but **keep both**: these two are what catch a copy the rename missed. |
| `test_environment_agnostic_pipeline.TestTheTwoReadersOfADeclarationAgree._discovery_body` and `.test_both_readers_return_the_same_values_for_the_committed_declarations` | Locator on the literal; the second also reads a `github_output_pairs(...)["environments"]` key and copies a tree into `terraform/environments`. |
| `test_environment_agnostic_pipeline` fixture builders at lines 682, 1211, 2171, 2733, 3275, 3319 | Each `mkdir`s or copies into `terraform/environments`; these are the scratch trees `tasks.md` 4.2 names. |
| `test_a_second_environment` module constant at line 279, and `generalises_over_environments()` | Carry the old root and the `ENVIRONMENTS` name. |
| `test_a_second_environment.TestEachEnvironmentHasAWorkspaceOfItsOwn.test_the_repository_has_an_environment_to_read` | Names the old root in its census. Overlaps `TestEachStackNamesAWorkspaceDerivedFromItsOwnName` in this pass's module. |
| `test_a_second_environment.TestEveryEnvironmentConsumesTheSharedModules` (helper at line 682) | Builds `ROOT / "terraform" / "environments" / name`. |
| `test_a_second_environment.TestNoRecordDescribesAnExistingEnvironmentAsAnticipated.test_no_readme_sentence_calls_an_existing_environment_anticipated` | Reads README sentences quoting the old path. |
| `test_a_second_environment.TestTheSecondEnvironmentIsDeclared.test_a_second_environment_directory_exists` | Asserts a directory under the old root. |
| `test_a_second_environment.TestTheseReadsDiscriminate` — `.test_a_prohibition_naming_one_environment_is_an_offence`, `.test_a_prohibition_that_generalises_is_not_an_offence`, `.test_an_environment_name_is_matched_as_a_word_not_a_substring`, and its fixture builders at lines 1062, 1074, 1116, 1131 | Fixture trees and prohibition strings written at the old root. |
| `test_ci_configuration.TestApplyWorkflowTriggerIsPathFiltered.test_the_path_filter_still_covers_terraform_changes` | Asserts the workflow-level filter still covers a path written as `terraform/environments/...`. The filter itself is `terraform/**` and `tasks.md` 5.1 keeps it, so only the **example path** in the assertion is superseded. |
| `test_ci_configuration.TestLockfileDiscoveryPrunesWorkingTrees` — `.tree_with_worktrees`, `.test_discovery_ignores_lockfiles_inside_working_trees`, `.test_discovery_still_finds_the_repository_s_own_lockfiles` | Fixture lockfile directories written at the old root. `TestDependabotCoverage` itself is generic and is **not** in this list. |
| `test_ci_configuration.TestThePreArchiveCitationCheckIsARealReadOfTheTree.test_the_pruned_directories_are_not_read` | Uses the old root as a sample path in a pruning fixture. |
| `test_host_configuration_names_its_environment.TestEachEnvironmentHasAnInventorySourceOfItsOwn.setUp` | Reads environment names from the old root to compare against inventory sources. **Note the boundary**: `tasks.md` 5.3 keeps the inventory filenames `prod` and `staging`; only the directory this `setUp` enumerates moves. |
| `test_host_converge_workflow.TestNoDeclarationNamesTheWriteTokensOwnName.setUp` and `.test_no_environment_declares_the_write_tokens_own_name` | Read declarations from the old root. Overlaps `TestEveryStackDeclaresItsPipelineConfiguration.test_no_stack_declares_the_write_tokens_own_name_as_its_read_only_secret` in this pass's module. |
| `test_host_converge_workflow` fixture builder at line 1685, and `test_planned_environment_apply_stage` fixture builder at line 726 | Both `mkdir` `terraform/environments` in a scratch tree. |

### Superseded by the identifier renames

Superseding deltas: *Pull Request Plan Visibility*, *Gated Production Apply Applies the Reviewed Plan*, *Serialized Terraform Runs*, *Scheduled Drift Detection* and *Each Environment Declares Its Own Pipeline Configuration* — all of which now name the iterated unit a stack — via `design.md` decision 2's rule.

| Test | Evidence |
|---|---|
| `test_ci_configuration` module constant at line 4868 and `token_inputs()` | Carry `ENVIRONMENT_NAME`. |
| `test_environment_agnostic_pipeline` lines 2798, 2801, 2875 | Key a dict on the literal `"environments"` when feeding the resolution body its inputs. |
| `test_environment_agnostic_pipeline` line 3264 | `github_output_pairs(outputs).get("environments", "")` — reads the job output this change renames to `stacks`. **This is the quiet one:** `.get(..., "")` returns the empty string rather than raising, so a rename that moved the output and not this read leaves the test comparing two empty strings and reporting success. |
| Any assertion in the suite reading a `matrix.environment.*` expression out of a workflow | Not individually enumerated here because the AST walk attributes them to helpers rather than to methods; a grep for `matrix.environment` across `.github/tests/*.py` is the census, and it is small. |

### Where no bearing test was found

For four requirements, **no existing test in `.github/tests/*.py` was found by this search that bears on the behaviour the delta supersedes**, and that is a statement about this search rather than a claim that none exists:

- *Workspace Execution Mode Set to Local* and *Each Environment Has a Dedicated Hetzner Cloud Project* (iac-state-management) — both are properties of HCP Terraform and of Hetzner project scoping, which this suite may not reach. **No such test exists**, and the delta supersedes only their wording.
- *Conditional Prod Server Creation* (iac-server-lifecycle) and *Conditional Prod Volume Creation* (iac-data-volumes) — both are about what `terraform plan` shows. **No such test exists** in this suite; `AGENTS.md`'s Terraform row covers `terraform/modules/<name>/tests/` and a stack is not a module.

## Unresolved project questions

Recorded here rather than asked, because a dispatched subagent has no channel to ask on. Each names the assumption taken and the tests that depend on it.

1. **How strict the repository-wide sweep for the old path should be.** `AGENTS.md` and `CLAUDE.md` record no policy on whether a committed file may quote a path a change has just removed — a historical note in `docs/change-queue.md` or `docs/deferred-work.md` is the plausible case, and `tasks.md` 7.1 and 7.4 both write into those two files. **Assumption taken:** zero occurrences outside `openspec/`, with no allowance list, on the reading that `tasks.md` 8.4 states the grep as a completeness proof and names only four *word* keepers and no *path* keeper. **Depends on it:** `TestNoCommittedFileStillNamesTheOldTerraformRoot.test_no_committed_file_names_the_old_terraform_root`. If this is wrong, the fix is a reviewable exemption, not a quiet edit to the test.

2. **Which replacement identifier each workflow is obliged to carry.** `tasks.md` 3.3 states the rename list over "all four workflows" without saying which workflow carries which handle, and the four differ: `drift.yml` narrows by nothing, and `host-converge.yml`'s fourth body enumerates the inventory rather than the Terraform root. **Assumption taken:** the `EXPECTED_REPLACEMENTS` table at the top of the new module, derived by reading what each workflow carries today under the old names. **Depends on it:** `TestTheMatrixAndItsOutputsNameTheStack.test_every_workflow_carries_the_replacements_expected_of_it`. The table is in one place precisely so a correction is one edit.

3. **Whether `docs/naming-conventions.md`'s stack naming reaches the `pipeline.yml` field names.** The declaration's fields are `github_environment` and `read_only_secret`; `proposal.md` keeps `github_environment` explicitly and says nothing about `read_only_secret`. **Assumption taken:** both keep their names — `read_only_secret` names the secret, not the unit, so `design.md` decision 2's rule does not reach it. **Depends on it:** every test in `TestEveryStackDeclaresItsPipelineConfiguration`, and `TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares`.

4. **Whether a `.github/tests` module may cite a requirement by its capability path.** `AGENTS.md`'s citation table permits `openspec/specs/<capability>/spec.md`, and `test_ci_configuration.py` enforces the prohibition on pre-archive change paths. **Assumption taken:** the capability-path form is fine and the change's own artifacts are named in prose with no path, which is what the modules beside this one do. The full suite passes, including `TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation`, so this is confirmed rather than merely assumed.

5. **No stack-specific skill exists in the toolkit for this work.** `testing` was loaded as the floor. `python` and `terraform` were **not** loaded: the tests are a static read of committed YAML and HCL text rather than a `terraform test` or a pytest-idiom question, and the suite's own idiom (`unittest`, the helper module beside it, the discriminator classes) is the authority `testing` defers to. Recorded because the standard obliges the absence be stated rather than passed over.

## What the implementation step must make pass

In the order the failures will resolve:

1. **`git mv terraform/environments terraform/stacks`** clears `TestTheTerraformRootIsNamedForTheStack` (5 tests), `TestEveryStackDeclaresItsPipelineConfiguration` (3) and `TestEachStackNamesAWorkspaceDerivedFromItsOwnName` (2) at once — ten of the thirty-eight, with no workflow edit at all. Do this first; it is the cheapest way to confirm the census helpers read what they claim to.
2. **The four discovery bodies and the workflow vocabulary** clear `TestDiscoveryIteratesTheStackRoot` (5), `TestTheMatrixAndItsOutputsNameTheStack` (5) and `TestTheEnvironmentAxisIsNotRenamedWithTheUnit` (4). The last of those three is the one that fails on **overreach** rather than on an incomplete sweep — if it goes red, the sweep renamed a keeper.
3. **The path's consumers** — the changed-files filter, the validate/tflint loops, `dependabot.yml`, the plan-comment heading and its `body-includes` locator, and the drift issue title — clear `TestThePathRuleAndItsConsumersFollowTheStackRoot` (5).
4. **`AGENTS.md`** clears `TestTheWriteCredentialRecordNamesTheStackRoot` (1).
5. **The documentation and `direnv` sweep** (`tasks.md` 5.2–5.5 and 7.1–7.4) is what clears `TestNoCommittedFileStillNamesTheOldTerraformRoot` (1) — and it will not go green until `.github/tests`' own literals move too (`tasks.md` 4.1 and 4.2), because that sweep reads this suite's modules like any other committed file.

**Expected end state: 752 tests, green.** A count below 752 is a module that failed to import, not a suite that got smaller.

## Second pass — *Host Configuration Is Applied by a Gated Workflow*

Everything above is the first pass, over the twenty-one MODIFIED requirements the change carried at commit `541dec8`. **This section is a second pass, over one further MODIFIED requirement added to the delta afterwards**, and it is additive to what is above rather than a revision of it: the first pass's basis still holds in full. A `git diff --stat` of this change's own delta-spec directory between `e88d0b2` — the commit carrying the first pass's tests — and `HEAD` reports one file changed, 69 insertions and no deletions — the requirement below, and nothing else.

That requirement is *Host Configuration Is Applied by a Gated Workflow* (iac-cicd-pipeline), which reached the delta because the change that originally ADDED it archived while this branch sat unrebased; `design.md` decision 4 records the history. It is now live in `openspec/specs/iac-cicd-pipeline/spec.md` in the old `environment` vocabulary.

**Its delta is vocabulary-only, and that was established by diffing rather than assumed.** Diffing the requirement as it stands under `openspec/specs/` against the delta's copy yields sixteen changed lines, every one of them the same substitution: `environment` → `stack` where the word names the unit the pipeline converges. No SHALL is added, none is removed, no scenario is added or removed, and the four keepers (`github_environment`, the `environment:` job key, `target_environment`/`TARGET_ENVIRONMENT`, the Hetzner `environment` label) are untouched. The behaviour this requirement states is therefore already asserted, in full, by `test_host_converge_workflow.py` — 34 tests written when it was ADDED, whose locators are written by **shape** (the job invoking `ansible-playbook`, the step redirecting into `$GITHUB_STEP_SUMMARY`, the `run:` step enumerating the inventory root) and which survive a rename untouched.

### Baseline for this pass

**Full**, taken immediately before the first new test was written, on this branch with the first pass's module present:

    python3 -m unittest discover --start-directory .github/tests
    Ran 752 tests in 20.138s — FAILED (failures=72)

Filtering the `FAIL:`/`ERROR:` lines for anything outside `test_terraform_stacks_are_the_iterated_unit` yields zero, so the 72 are the first pass's expected reds and nothing else was broken going in. That figure is the one recorded above, re-measured rather than carried over.

**After this pass:**

    Ran 762 tests in 20.219s — FAILED (failures=76)

762 − 752 = 10, which is this pass's test count. 76 − 72 = 4, which is this pass's four assertions about the workflow; the six discriminators pass. Every failure is still inside the derived module — the same filter again yields zero.

### Where this pass's tests are

Appended to the existing module, `.github/tests/test_terraform_stacks_are_the_iterated_unit.py`, in three new classes. **Nothing already in that module was edited, and no test anywhere in the suite was edited, deleted, renamed or disabled.** A new module was considered and rejected: these tests read the same file the module's `HOST_CONVERGE` constant already names, reuse its `REPLACEMENT_IDENTIFIERS` table, and are the host-converge half of a boundary whose apply-side half is asserted three classes above.

One deliberate duplication is recorded so it is not read as an oversight. `host_converge_discovery_bodies()` is a second copy of the locator inside `TestDiscoveryIteratesTheStackRoot.test_the_host_converge_discovery_reads_each_stacks_own_declaration`, rather than that test being refactored to call it. That test is currently red; lifting its locator out of it would change what a red test asserts at the one moment when nothing could show the change was faithful.

### The tests, and the assertion provenance of each

#### `TestTheConvergeRowIsReachedThroughTheStack`

The sweep in `TestTheMatrixAndItsOutputsNameTheStack` forbids `matrix.environment` **anywhere** in `host-converge.yml` and requires `matrix.stack` **somewhere** in it. Neither says which surfaces carry it, so a rename that moved the gate, the credential or the concurrency group onto a different field of the row — `matrix.stack.name` in place of `matrix.stack.github_environment` — satisfies both sweeps while gating, crediting or serialising the wrong thing. That gap is what these three close, and it is a gap the rename creates.

| Test | Provenance |
|---|---|
| `.test_the_converge_job_is_gated_on_the_github_environment_its_stack_declares` | SPECIFIED — scenario *The converge job is gated on the environment's own GitHub Environment*, and "A converge job **per stack** SHALL declare that stack's own GitHub Environment, taken from that stack's committed pipeline declaration". DERIVED for the matrix key — `design.md` decision 2. The apply-side sibling, `TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares`, scopes itself to `apply.yml` in its own docstring; this is the other file. |
| `.test_the_converge_job_exports_the_read_only_secret_its_stack_declares` | SPECIFIED — "which repository secret holds each one's read-only credential SHALL come from discovery over committed files", and the converge job "SHALL be the only job holding the credentials a converge needs". DERIVED for the matrix key. `test_host_converge_workflow.TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment.test_no_step_maps_an_environment_to_its_secret` holds the other half and survives the rename — but it forbids a *literal* secret name, and `secrets[matrix.stack.name]` names no literal. |
| `.test_the_converge_jobs_serialisation_group_is_per_stack` | SPECIFIED — "A converge SHALL NOT be cancelled in favour of a later one. Runs against one stack SHALL be serialised". DERIVED for the matrix key. `test_host_converge_workflow.TestOneEnvironmentsConvergeDoesNotSilenceAnother.test_an_in_flight_converge_is_not_cancelled_by_a_later_one` asserts `cancel-in-progress: false` and that the group carries *some* expression; it cannot see a group expressing something other than the row. |

#### `TestTheDispatchInputStillReachesTheBodyThatValidatesIt`

| Test | Provenance |
|---|---|
| `.test_the_dispatch_input_is_mapped_into_the_body_under_a_name_that_body_reads` | SPECIFIED for the refusal the mapping feeds — scenario *A run is requested for an environment that does not exist*: "the run SHALL fail naming the stacks that were found, rather than converging none and reporting success". DERIVED for the mechanism — `tasks.md` 3.4. |

This is the other end of the wire `TestTheMatrixAndItsOutputsNameTheStack.test_the_host_converge_dispatch_input_names_the_stack` renames. That test moves the input an operator types; this one holds that the value still *arrives* inside the discovery body, which is where the refusal is written. A rename that moved the input and not the `env:` entry carrying it leaves the body reading an unset variable — which it is specified to treat as "converge every stack", because that is what every `push` supplies. A by-hand converge of one host would silently converge all of them, with nothing red anywhere.

#### `TestTheseHostConvergeReadsDiscriminate` — six tests, all DERIVED

These assert nothing about this change. The four above are a static read of one committed file, so a green result would report only that the file could be read; these run each read over material the test itself supplies. They establish that the converge locator picks out the job that runs the play and is **not** fooled by a job whose only mention of the play is a comment; that the gate read and the credential read tell the row from its fields, rejecting `matrix.environment.github_environment`, `matrix.stack.name` and a `needs.*.outputs.*` read; and that the dispatch-carrier read reports a mapping when given one, reports none when given none, and still sees the retired spelling in its `github.event.inputs` form — the last being what stops the absence assertion and the presence assertion being satisfiable by one mapping.

**Discriminator record, per the testing standard.** All six were written and executed in this pass, and all six pass. The four assertions above were **red at authoring against real content, not against an absent target**: `host-converge.yml` exists and parses, and each read reached a live value and rejected it — `environment: ${{matrix.environment.github_environment}}`, the group `host-converge-${{matrix.environment.name}}`, a `CREDENTIAL_VALUE` lookup that reads no `matrix.stack.read_only_secret`, and an `env:` entry `REQUESTED_ENVIRONMENT: ${{ inputs.environment }}`. That is the first failure state, not the second, and it is stronger evidence than the first pass's thirty-eight could produce.

### Running them

    python3 -m unittest discover --start-directory .github/tests \
      -k TestTheConvergeRowIsReachedThroughTheStack

    PYTHONPATH=.github/tests python3 -m unittest \
      test_terraform_stacks_are_the_iterated_unit.TestTheDispatchInputStillReachesTheBodyThatValidatesIt\
.test_the_dispatch_input_is_mapped_into_the_body_under_a_name_that_body_reads

### Scenario accounting — the eleven scenarios of this requirement

**11 `#### Scenario:` blocks, all 11 accounted for below exactly once.** The three outcomes are the ones defined above.

| # | Scenario | Outcome |
|---|---|---|
| 99 | A merge to the host configuration converges without a workstation | VOCAB — covered by `test_host_converge_workflow.TestAMergeConvergesWithoutAWorkstation` (3 tests, shape-located). Its `.test_a_run_can_also_be_requested_by_hand_for_one_environment` is superseded by the dispatch-input rename — see the obsolete list below — and needs re-pointing, not replacing. |
| 100 | A host's first converge is the operator's | GAP — the delta does not touch this scenario's text at all. It states a bounded exemption about what an operator may do from a workstation before a host exists on the tailnet; no committed file carries it, and neither of the other two test rows can reach it. |
| 101 | The pre-approval job holds no converge credential | VOCAB — unchanged by the delta; covered by `test_host_converge_workflow.TestThePreApprovalJobHoldsNoConvergeCredential` (3 tests). |
| 102 | The converge job is gated on the environment's own GitHub Environment | **NEW** — `TestTheConvergeRowIsReachedThroughTheStack.test_the_converge_job_is_gated_on_the_github_environment_its_stack_declares`. The behaviour half stays with `test_host_converge_workflow...test_the_converge_job_takes_its_environment_from_discovery`, which is written generically and survives. |
| 103 | An environment that cannot be converged fails the workflow | VOCAB — the two-sided refusal is covered by `test_host_converge_workflow.TestHostConvergeDiscoveryFailsClosed`, which **executes** the discovery body against a fixture tree. That tree is built at `terraform/environments` (line 1685), already in the first pass's obsolete list; re-pointing it is what keeps this scenario covered. |
| 104 | Discovery finding no environment fails rather than reporting success | VOCAB — the executed refusal is `test_host_converge_workflow...test_discovery_fails_when_it_finds_no_environment`. That the body iterates the new root is covered by `TestDiscoveryIteratesTheStackRoot.test_the_host_converge_discovery_reads_each_stacks_own_declaration` and `.test_no_discovery_body_still_names_an_environments_root`. |
| 105 | A run is requested for an environment that does not exist | **NEW, partial** — `TestTheDispatchInputStillReachesTheBodyThatValidatesIt.test_the_dispatch_input_is_mapped_into_the_body_under_a_name_that_body_reads` covers that the request still reaches the body. The **executed** refusal is `test_host_converge_workflow...test_a_dispatched_environment_discovery_did_not_find_is_refused`, whose locator this rename moves — see the obsolete list. |
| 106 | A wrong secret stops the run before the host is touched | **NEW, partial** — `.test_the_converge_job_exports_the_read_only_secret_its_stack_declares` covers the committed half: the converge runs under the secret the stack's own declaration names. GAP for the runtime half. Whether a rejected credential stops the run before the first role acts needs a real host, a real credential and a real play; `.github/tests` may not make a network call or hold a credential, and no Molecule scenario runs a workflow job. The **ordering** half is covered statically and survives: `test_host_converge_workflow.TestAWrongSecretStopsTheRunBeforeTheHostIsTouched.test_the_credentials_are_exercised_before_the_play_runs`. |
| 107 | The converge job supplies what the run needs | VOCAB — unchanged by the delta; covered by `test_host_converge_workflow.TestTheConvergeJobIsProvisionedBeforeItRuns` (2 tests). |
| 108 | The converge runs the Ansible the roles were verified under | VOCAB — the delta changes not one word of this paragraph or of this scenario; covered by `test_host_converge_workflow.TestTheConvergeRunsTheAnsibleTheRolesWereVerifiedUnder` (3 tests). |
| 109 | One environment's failure does not silence another's | **NEW, partial** — `.test_the_converge_jobs_serialisation_group_is_per_stack` covers the per-stack group the rename rewrites. The `fail-fast: false` half is VOCAB, covered by `test_host_converge_workflow...test_a_failing_converge_does_not_abandon_its_siblings`. GAP for the queueing itself, which is GitHub Actions runtime behaviour. |

### Totals, both passes

| Outcome | First pass | This pass | Total |
|---|---|---|---|
| NEW | 28 | 4 | 32 |
| VOCAB | 36 | 6 | 42 |
| GAP | 34 | 1 | 35 |
| **Scenarios** | **98** | **11** | **109** |

Across 22 MODIFIED requirements in 6 capabilities. Still no `REMOVED` and no `RENAMED` delta, and still no requirement or scenario renamed (`design.md` decision 3).

### Obsolete-test candidates found by this pass

Bounded, as before, to the dispatched test-path glob `.github/tests/*.py`. This pass's search was narrower than the first's and is stated as such: a grep of `test_host_converge_workflow.py` and `test_host_configuration_names_its_environment.py` for the old root literal and for each of the seven retired identifiers, plus a read of the former's module-constant block. **Every entry is a candidate for human confirmation, not a conclusion, and each needs a re-pointing rather than a deletion.** Nothing was edited, deleted or disabled by this pass.

The literal search returned exactly four occurrences — lines 480, 497, 539 and 1685 — all of which the first pass already lists. The two entries below are what the *constant block* turned up, and neither carries a path:

| Test | Superseding delta | Evidence |
|---|---|---|
| `test_host_converge_workflow` module constant `DISPATCH_INPUT_NAME = "environment"` (line 202), and its one consumer `TestAMergeConvergesWithoutAWorkstation.test_a_run_can_also_be_requested_by_hand_for_one_environment` | *Host Configuration Is Applied by a Gated Workflow* ("The workflow SHALL name no stack"), via `tasks.md` 3.4 | The test asserts `assertIn(DISPATCH_INPUT_NAME, inputs)` over the workflow's `workflow_dispatch` inputs. **This is a direct contradiction**, not a drift: `TestTheMatrixAndItsOutputsNameTheStack.test_the_host_converge_dispatch_input_names_the_stack` asserts `environment` is **not** among those inputs. The two cannot both be green, and the repair is one word in the constant. **Not in the first pass's list** — it is a bare string constant carrying the word without the path, which an AST walk keyed on retired path and identifier literals does not attribute. |
| `test_host_converge_workflow` module constant `DISPATCH_INPUT = re.compile(r"(?:inputs\|event\.inputs)\.environment\b")` (line 195), consumed by `TestHostConvergeDiscoveryFailsClosed._input_variable` and therefore by `.test_a_dispatched_environment_discovery_did_not_find_is_refused`, `.test_a_dispatched_environment_discovery_found_is_the_only_one_selected` and `.test_an_empty_dispatch_input_selects_every_environment` | Same | `_input_variable` resolves the variable the dispatch input arrives under by matching this pattern against the step's `env:` values. After the rename it matches nothing and returns `None`. **The third consumer is the quiet one:** the first two go red with a readable message, but `test_an_empty_dispatch_input_selects_every_environment` takes the `elif variable:` branch, supplies nothing, and passes — while asserting nothing about the input it is named for. The repair is `\.stack\b`. |

Two further tests are recorded here not as obsolete but so that re-pointing is known to be sufficient: `test_host_converge_workflow.TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment.test_the_workflow_names_no_environment` and `.test_no_step_maps_an_environment_to_its_secret` reach the old root only through `environment_directories()` and `environment_declarations()`, imported from `test_environment_agnostic_pipeline` and already listed in the first pass. Moving those helpers carries both; neither needs an edit of its own.

**Everything else in `test_host_converge_workflow.py` survives the rename untouched**, and that is a finding rather than an absence of one: its `WorkflowLocatorMixin` locates every job and step by shape, for the reason its own docstring gives, and shape is what a vocabulary change does not alter.

### Unresolved project questions from this pass

Numbered on from the five above. Recorded rather than asked, because a dispatched subagent has no channel to ask on.

6. **What handle the dispatch input arrives under inside the discovery body.** `RETIRED_IDENTIFIERS` retires `REQUESTED_ENVIRONMENT`, and `REPLACEMENT_IDENTIFIERS` names no successor; `tasks.md` 3.4 fixes the *input's* name and says nothing about the variable's. `TestHostConvergeDiscoveryFailsClosed`'s own docstring records the same question from the change that added the workflow. **Assumption taken:** the name stays the implementer's to choose, so the test asserts only that the key the workflow maps it under is a key the discovery body actually reads — an agreement, not a spelling. **Depends on it:** `test_the_dispatch_input_is_mapped_into_the_body_under_a_name_that_body_reads`.

7. **Whether the converge job reaches its GitHub Environment and its read-only secret through the matrix row at all.** Nothing in the delta obliges a matrix; a converge job could read a per-row `needs.*.outputs.*` instead. **Assumption taken:** through `matrix.stack`, which is what the committed workflow does today under the old name and what `design.md` decision 2's rule renames rather than restructures. **Depends on it:** all three tests in `TestTheConvergeRowIsReachedThroughTheStack`. If this is wrong the three are the wrong shape rather than wrong in their expectation, and that is a reviewable correction to make in one class.

8. **No skill in the toolkit covers this stack.** As recorded above for the first pass: `testing` was loaded as the floor, and the suite's own idiom — `unittest`, the shape locators, the discriminator classes — is the authority it defers to. Repeated here because the standard obliges the absence be stated in each pass rather than inherited.

### What the implementation step must make pass, from this pass

Four further failures, all in `host-converge.yml` and all cleared by the same sweep `tasks.md` 3.2–3.4 already describes:

6. **The converge job's own row** — `environment:`, the `secrets[...]` lookup and the `concurrency: group:` each read `matrix.stack.<field>` rather than `matrix.environment.<field>`, keeping the *field* names (`github_environment`, `read_only_secret`) as they are. Clears `TestTheConvergeRowIsReachedThroughTheStack` (3).
7. **The dispatch input's `env:` entry** — the `REQUESTED_ENVIRONMENT: ${{ inputs.environment }}` mapping on the discovery step becomes a mapping of `inputs.stack`, under a key the body reads. Clears `TestTheDispatchInputStillReachesTheBodyThatValidatesIt` (1). Re-point `test_host_converge_workflow`'s `DISPATCH_INPUT` and `DISPATCH_INPUT_NAME` in the same commit, or three of that module's tests go red and a fourth goes quietly vacuous.

**Expected end state: 762 tests, green.** A count below 762 is a module that failed to import, not a suite that got smaller.

## Third pass — one repair, after the implementation landed

The implementation is committed. The suite went to 761 of 762 green, with one failure: `TestThePathRuleAndItsConsumersFollowTheStackRoot.test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root`, from the first pass.

**It was a defect in the test's READ, not in what it asserts** — the third of the four failure states, and the one that has to be established by provenance rather than assumed, because "the test is broken" is otherwise available as a re-description of any failure at all. The provenance here is unambiguous: the mismatch was not in the expected value. The check harvested the heading with `stripped.partition("=")[2].strip().strip('"')` and never unescaped it. `pr-validation.yml` assigns the heading inside double quotes, so its backticks are written `\``, while the `body-includes` locator is YAML and carries bare ones. The two strings differed by two backslashes and by nothing else. The workflow is correct and finds its own comment; the check could not have gone green against any correct implementation.

**The repair is to the read, and the assertion is untouched.** A new module-level helper, `shell_double_quoted_value`, removes one matched pair of surrounding double quotes and unescapes the four characters — `$`, a backtick, `"` and `\` — that a backslash is special before inside them, and nothing else. The comparison it feeds is the same one, unchanged: the `body-includes` locator must still be found inside the heading the plan step writes.

**That it was not weakened was established, not asserted.** Two independent checks:

1. **Four fixture-driven discriminators**, added permanently as `TestTheHeadingReadDiscriminates` — all DERIVED, none asserting anything about this change. They hold that the read returns what the shell will emit, that a backslash which is *not* an escape survives (a wider substitution would rewrite a literal and make two disagreeing headings compare equal), that only a matched pair of quotes is removed, and — the load-bearing one — that the repaired read still brings an agreeing heading and locator together **and still keeps a disagreeing pair apart**.
2. **The repaired test method itself, run against deliberately mismatched material.** The repository's `pr-validation.yml` was not touched: a copy was mutated in a scratch directory and the module constant aimed at it for one run. Three mutations, three reds, with the failure arriving at the right assertion each time — a heading naming `terraform/plans/` (caught by the root assertion), a heading keeping the stack root but changing the separator, and a heading keeping the root at a deeper path (both caught by the heading-vs-locator comparison, which is the one the repair touches). The unmodified file, as a control, passes.

### Counts

    python3 -m unittest discover --start-directory .github/tests
    Ran 766 tests — OK

766 = 762 + the four discriminators this repair owes. **The expected end state recorded above as "762 tests, green" is superseded by this figure**, and by nothing else: no test was removed, none was renamed, and the one that was repaired keeps its name, its class and its assertion.

## Fourth pass — the old-root sweep was too narrow by a whole class

`TestNoCommittedFileStillNamesTheOldTerraformRoot` rests on `old_root_occurrences()`, which matched only the **prefixed** path. Code review found two committed files naming the old directory **without** its `terraform/` prefix — a `.tftest.hcl` comment reading "(not environments/prod)" and "the environments/prod-level", and a `docs/change-queue.md` entry reading "`environments/prod` couples the volume to the server" — over which the sweep reported a clean tree. Both instances were corrected in `b86750f`, before this pass; what is recorded here is the closing of the **class**, which is the part a corrected instance does not do.

The first pass's manifest called this "the assertion most likely to be argued with" and wrote its scope into the class docstring. It was argued with in the right direction and was too narrow, not too wide — worth recording, because the failure mode of a completeness proof is silence.

### The widened pattern, and its boundary

`OLD_ROOT_REFERENCE` is the union of two shapes: the prefixed path, with or without a trailing slash, exactly as before; **and** a bare `<directory>/` reference, whatever prefix it carries or none. It keys on the **path-like shape** — the word immediately followed by a slash — and never on the word.

That boundary is now stated in `old_root_occurrences()`'s own docstring rather than left to be inferred from the regular expression, per the request. What it deliberately does **not** match: the bare word with no slash after it, which stays throughout this repository wherever it names a GitHub Environment, the Hetzner `environment` label, the environment axis, the OS process environment or a pre-commit hook's environment; the word preceded by a letter, digit, underscore or hyphen, which is a longer identifier ending in it; and anything under `openspec/`, which the walker prunes as before.

The directory's bare name is derived from `OLD_ROOT_SEGMENT` by `rpartition`, not written out again: the assembly rule that constant carries applies to every literal in the module, not only to the first one.

### That it discriminates — established in both directions

Three fixture-driven discriminators added to `TestTheseReadsDiscriminate`, in that class's own idiom and using its existing scratch-tree helpers. No existing test was edited.

| Test | What it establishes |
|---|---|
| `.test_the_old_root_sweep_reports_a_bare_directory_reference` | The defect itself: a bare reference is reported, in a backticked citation, in a hyphenated compound and in a parenthetical — the three forms the two real files used. |
| `.test_the_old_root_sweep_does_not_fire_on_the_word_itself` | The direction that matters more. Eight lines of text this repository keeps — "each environment's own GitHub Environment", "a pre-commit hook environment is built against a specific interpreter", `environment = "prod"`, `TARGET_ENVIRONMENT`, "two environments do not queue behind each other", `my_environments`, `sub-environments`, "the environments and/or the stacks" — and none is an offence. A pattern keyed on the word would be satisfiable only by the overreach `TestTheEnvironmentAxisIsNotRenamedWithTheUnit` exists against. |
| `.test_the_old_root_sweep_still_reports_the_prefixed_path` | Widening a pattern can narrow it. The prefixed form is still reported — **including the form with no trailing slash**, which a bare-directory pattern alone would have missed, and which is the way this widening could quietly have lost coverage. |

**And against the two real instances**, read from `b86750f^` so the evidence is the committed text rather than a reconstruction:

| File at `b86750f^` | Old pattern | Widened pattern |
|---|---|---|
| `terraform/modules/volume/tests/creation.tftest.hcl` | 0 hits | 2 hits (lines 9, 10) |
| `docs/change-queue.md` | 0 hits | 1 hit (line 257) |

Both files at `HEAD` are clean under the widened pattern, and the widened sweep over the whole tree reports a clean tree.

### Counts

    python3 -m unittest discover --start-directory .github/tests
    Ran 769 tests — OK

769 = 766 + the three discriminators. Nothing outside `.github/tests/` was touched; the two instances were already corrected.
