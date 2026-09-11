# Test plan — close-ci-verification-gaps

Derived from this change's delta specs before any of its implementation existed. Not an artifact the OpenSpec schema knows about: it does **not** appear among `openspec instructions apply`'s context files and must be read on purpose.

Authored by `openspec-change-test-writer`, which did not read `.github/workflows/*`, `.github/dependabot.yml` or any other implementation of the behavior under test. Superseded behavior was established by comparing each `MODIFIED` delta against the requirement as it currently stands under `openspec/specs/`.

**This pass is additive only. It added tests and subtracted nothing.** No existing test file was edited, deleted or disabled, and no implementation was written.

---

## 1. The suite

```
.github/tests/test_ci_configuration.py
```

46 tests. Authorised test-path glob for this change: `.github/tests/*.py`.

`terraform test` remains this project's test command for `terraform/modules/*/tests/*.tftest.hcl`. This suite is additional to it, not a replacement: every scenario this change carries is about GitHub Actions configuration, `.github/dependabot.yml` and `.pre-commit-config.yaml`, none of which the module-level Terraform mechanism can reach.

## 2. Runner and the invocation CI must use

Python standard-library `unittest` plus PyYAML, and — for one test only — the external tools listed under *External tools* below. No network, credential, container runtime or Terraform binary. Full run: ~0.2 s.

**The exact command the `pr-validation.yml` step should use, with the repository root as its working directory — this is the invocation the suite was verified under:**

```yaml
- name: CI configuration tests
  run: python3 -m unittest discover --start-directory .github/tests --verbose
```

- **Working directory: the repository root** (the workflow default). Do not set `working-directory:`; it is unnecessary and would obscure the paths in failure messages. The suite locates the repository root itself by walking up for `openspec/config.yaml`, so it also runs correctly from `.github/tests/`, and honours `REPO_ROOT` when set — that override exists for the fixture-based self-tests in §4.6, not for CI.
- **Exit status 1 on any failure** — verified. Nothing further is needed to make the check fail.
- **No `if:` and no `continue-on-error:`** on the step; the requirement is that it runs unconditionally and that its result is not swallowed. Three tests assert exactly this and will stay red until the step exists (§4.6 F1, F2).
- `--start-directory .github/tests` puts that directory on `sys.path`, so no `PYTHONPATH` is needed.

Individually selectable, which is how the implementation step should use it while working through tasks:

```sh
python3 -m unittest discover --start-directory .github/tests \
    -k test_every_terraform_lockfile_directory_appears_in_dependabot_config
```

### Dependency

**PyYAML, pinned exactly in `.github/requirements-ci.txt`** alongside `pre-commit` (`tasks.md` 4.2). **Verified against PyYAML 6.0.1** — pin that version, so the pin and this verification agree. Everything else the suite imports is its runtime's standard library, and two tests assert that it stays that way (§4.6 F3).

### External tools

Beyond Python and PyYAML the suite needs **`bash`, `find`, `xargs`, `basename`, `grep`, `sort` and `jq`** — but for **one test only**, `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing` (A4). That test is behavioral: it executes `ansible-verify.yml`'s own discovery snippet against a scratch tree, and the snippet calls those tools before it can reach the failure branch under test. Every other test in the suite needs Python and PyYAML alone.

Where any of those tools is absent, the test **skips and names the missing tool** rather than asserting on an exit status that says nothing about discovery: `jq: command not found` is also a non-zero exit, so `assertNotEqual(0, returncode)` would pass on an accident and the message assertion would then fail for a cause the workflow is not responsible for. `unittest` reports the skip and its reason in the run output — it is not counted as a pass.

**Under CI (`CI` set in the environment) it fails instead of skipping.** A skipped check on a runner is exactly the "green having verified nothing" failure this change exists to close, so on a runner whose image stopped shipping `jq` the suite must go red, not quietly drop the test. GitHub-hosted `ubuntu-latest` images ship all seven today; the guard exists so that ceasing to is visible.

This dependency is a property of the *implemented* discovery snippet, recorded after the fact: the snippet's final form pipes `find` through `xargs basename`, `grep -v '\.'` and `sort` into `jq -R -s -c`. Nothing in the delta specs requires that shape — see Q4 — so a reimplementation that drops `jq` would narrow this list rather than violate anything.

## 3. Baseline

**Full baseline, taken before any test was written**, and **re-confirmed after the suite was placed** at `.github/tests/`:

| Module | Command | Before | After placement |
| --- | --- | --- | --- |
| `terraform/modules/volume` | `terraform test` | 8 passed, 0 failed | 8 passed, 0 failed |
| `terraform/modules/server` | `terraform test` | 18 passed, 0 failed | 18 passed, 0 failed |

All 26 pre-existing `terraform test` assertions still pass. The new suite adds no test to either module, touches no file under `terraform/`, and cannot change these results. No existing test was edited, deleted or disabled.

The static-assertion suite itself had no prior baseline — it did not exist.

## 4. Scenario accounting

29 scenarios across six requirements; 29 accounted for below.

Legend: **C** covered by at least one test · **P** partially covered (the repository-state half is asserted; the named half is not reachable) · **U** uncovered, with reason.

### 4.1 `iac-cicd-pipeline` — ADDED: Ansible Configuration Is Verified in Continuous Integration

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| A1 | Ansible-only pull request is linted and syntax-checked | P | `TestAnsibleBlockingTier.test_an_ansible_path_filter_selects_changes_under_ansible`, `.test_the_blocking_tier_runs_ansible_lint`, `.test_the_blocking_tier_runs_an_ansible_syntax_check`. Asserts that an `ansible/**` filter selects the checks and that both checks are invoked. **Not covered:** that `ansible-lint` actually reports an error on bad content — that is `ansible-lint`'s behavior, not this repository's to assert. |
| A2 | A newly added role scenario runs without a workflow change | P | `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_names_no_role_literally`. Proves the negative the requirement states ("discover ... rather than enumerate"): no role currently carrying a `molecule/` directory is named in the workflow. The role list is read from the tree at test time, so the test stays correct as roles are added. **Not covered:** that a hypothetical new scenario is in fact executed — that needs a real runner. |
| A3 | Every scenario a role declares is executed | C | `TestMoleculeDiscoveryAndScenarioCoverage.test_molecule_is_invoked_across_all_scenarios`. The requirement names the mechanism (`--all` rather than the `default` scenario), so the static assertion is the scenario. |
| A4 | Discovering no roles fails rather than passes | C | `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing`. **Behavioral**: extracts the discovery step's shell, executes it under `bash -e` against a scratch tree containing an empty `ansible/roles/`, and asserts a non-zero exit carrying a message that names discovery. Because it runs the real snippet it needs that snippet's external tools — `bash`, `find`, `xargs`, `basename`, `grep`, `sort`, `jq` — and skips (fails, under CI) when one is absent rather than reading an accidental non-zero exit as evidence; see §2 *External tools*. See also §7 Q4. |
| A5 | A failing Molecule scenario does not block a merge | P | `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_uses_no_continue_on_error`. Asserts the visibility half — the run reports its true conclusion. **Not covered:** that the workflow is absent from branch protection's required checks. Branch protection is GitHub-side configuration, not repository state. |
| A6 | Ansible verification receives no production credential | C | `TestVerificationJobsCarryNoCredential.test_no_pull_request_validation_job_declares_an_environment`, `.test_the_molecule_workflow_declares_no_environment`, `.test_the_molecule_workflow_consumes_no_secret`. The scenario is itself a statement about configuration ("without ... a declared deployment `environment:`"), so these assertions are the scenario. |

### 4.2 `iac-cicd-pipeline` — MODIFIED: Pull Request Validation Checks

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| B1 | PR with a misconfiguration fails validation | U | **Uncovered.** Unchanged by this delta, and the assertion is Trivy's own detection behavior against a synthesised misconfiguration. Exercising it needs a Trivy run over a fixture tree — a second toolchain this change does not adopt. Not a gap this change opens. |
| B2 | PR with a leaked credential fails validation | P | `TestSecretScanningIsUnconditional.test_secret_scanning_precedes_any_terraform_plan_in_the_same_job`. Asserts the ordering half the scenario states ("SHALL fail before any `terraform plan` is executed"). **Not covered:** that gitleaks detects the pattern — its behavior, not this repository's. `tasks.md` 3.4 covers that manually. |
| B3 | A credential outside Terraform is still caught | C | `TestSecretScanningIsUnconditional.test_no_secret_scanning_step_is_conditioned_on_terraform_changes` and `.test_no_job_containing_a_secret_scanning_step_is_conditioned_on_terraform_changes`, guarded by `.test_the_workflow_has_a_secret_scanning_step_at_all`. The defect this change fixes *is* the path condition, so removing it is the scenario. The job-level test exists separately because relocating the condition from step to job would leave the step-level assertion green while reopening the hole. |
| B4 | Local and CI secret scans agree | C | `TestSecretScanVersionParity.test_ci_installs_the_version_the_precommit_config_pins`. The scenario is verbatim a comparison of two files. Satisfied either by a CI literal equal to the pin or by deriving the version from `.pre-commit-config.yaml` at run time (design Decision 2); a workflow doing neither fails. |
| B5 | Secret scanning requires no third-party license | C | `TestSecretScanningNeedsNoLicense.test_no_workflow_references_a_gitleaks_license_secret`, `.test_secret_scanning_uses_the_cli_not_the_marketplace_action`. |
| B6 | A newly added module is validated and linted without a workflow change | C | `TestTerraformChecksDiscoverDirectories.test_the_workflow_names_no_terraform_module_directory_literally`. Regression guard: unchanged by the delta, and `handoff.md` records directory discovery as must-not-undo. |
| B7 | A module's tests run in CI | P | `TestTerraformChecksDiscoverDirectories.test_the_workflow_runs_terraform_test`. Presence only. **Not covered:** that the check fails when a module test fails — needs a real CI run. |

### 4.3 `iac-cicd-pipeline` — MODIFIED: Gated Production Apply Applies the Reviewed Plan

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| C1 | Merge does not apply immediately | P | `TestSavedPlanIsWhatGetsApplied.test_exactly_one_job_declares_the_production_environment`, `.test_the_apply_job_depends_on_the_planning_job`. Asserts the workflow structure the pause depends on. **Not covered:** that GitHub actually pauses — that is the `production` Environment's protection rule, configured GitHub-side. |
| C2 | Reviewer sees the exact diff before approving | U | **Uncovered.** The assertion is about the content of a completed job's run summary at execution time. Nothing in the repository determines it, and no available mechanism can observe a GitHub job summary. Unchanged by this delta. |
| C3 | Applied changes match the approved plan | P | `TestSavedPlanIsWhatGetsApplied.test_the_apply_job_applies_a_saved_plan_file` — asserts the approval-gated job applies `tfplan` and recomputes no plan of its own. **Not covered:** the "SHALL error rather than apply divergent changes" half, which is Terraform's saved-plan staleness behavior against live remote state. |
| C4 | Apply credentials are inaccessible before approval | P | `TestSavedPlanIsWhatGetsApplied.test_the_planning_job_declares_no_environment` — the absent `environment:` is what keeps the read-write token out of the pre-approval job. **Not covered:** GitHub's actual secret-scoping enforcement. |
| C5 | A merge that cannot change infrastructure raises no approval request | C | `TestApplyWorkflowTriggerIsPathFiltered.test_the_push_trigger_declares_a_path_filter`, `.test_the_path_filter_still_covers_terraform_changes`, `.test_the_path_filter_excludes_changes_that_cannot_affect_infrastructure`, `.test_the_branch_constraint_is_intact`. The third evaluates the declared filter against representative documentation, Ansible, platform and OpenSpec paths using a GitHub-glob matcher, so it asserts the scenario's outcome rather than the filter's spelling. |
| — | Cross-constraint the same requirement adds: the required check SHALL NOT be path-filtered at the workflow level | C | `TestRequiredCheckIsNotPathFiltered.test_the_required_check_declares_no_workflow_level_path_filter`. Not a `#### Scenario:` block, but SHALL text the delta introduces alongside C5, and the invariant most at risk while C5 is implemented. |

### 4.4 `iac-cicd-pipeline` — MODIFIED: Destroy Policy Gate

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| D1 | Unintended resource replacement blocks the pipeline | U | **Uncovered.** Unchanged by this delta. Executing it end-to-end requires the gate step's full shell, which continues past the inspection into merge-commit PR-number resolution and a GitHub label lookup over the API. That is not runnable outside a runner, and `design.md` Decision 5 explicitly declines to extract the gate into a script with fixtures, queuing it instead. Covering this behaviorally would require the implementation shape the change deliberately did not adopt. |
| D2 | Deliberate teardown is possible with explicit acknowledgement | U | **Uncovered**, same reason as D1 — it turns on the `destroy-override` label lookup. Unchanged by this delta. |
| D3 | An uninspectable plan blocks the pipeline | P | `TestDestroyPolicyGateFailsClosed.test_the_gate_does_not_swallow_an_inspection_failure`, `.test_the_gate_asserts_the_document_is_a_terraform_plan`, `.test_the_gate_distinguishes_an_uninspectable_plan_from_a_clean_one`, guarded by `.test_the_gate_exists`. These assert the three routes `design.md` Decision 5 names are closed, and that a distinguishing message exists. **They are structural, not behavioral** — they do not establish that a malformed `plan.json` or a `{}` document actually reaches the failure branch. `tasks.md` 1.1's four kept fixtures are the behavioral evidence, run manually; §8 recommends how to make them executable. |
| D4 | Drift-detection plan is not affected by this gate | U | **Uncovered.** Unchanged by this delta, and the scenario asserts an absence in `drift.yml`. Any static proxy (for example "no `destroy-override` appears in `drift.yml`") would constrain that workflow's reporting shape without establishing the scenario, so the thought is recorded here instead of a weak test. |

### 4.5 `iac-safety-hardening` — MODIFIED: Automated Dependency Updates

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| E1 | Provider version update is proposed automatically | P | `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems`. Asserts the enabling condition only. **Not covered:** Dependabot opening a pull request — a GitHub service behavior with no repository-side observable. |
| E2 | Every lockfile-bearing directory is covered | C | `TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config`. The scenario is verbatim a set comparison, and the test performs exactly it: `.terraform.lock.hcl` directories discovered from the tree at test time, matched against the configured `terraform` entries with GitHub-glob semantics. **This is the strongest test in the suite** — the requirement says the configuration must be kept in agreement by hand because Dependabot's `terraform` ecosystem has no discovery, and nothing else in the repository can enforce that. |
| E3 | Action version update is proposed automatically | P | Same test as E1, same limitation. |
| E4 | Pre-commit hook revisions are refreshed on a schedule | P | `TestScheduledHookRefresh.test_a_scheduled_workflow_runs_pre_commit_autoupdate`. Asserts a schedule-triggered workflow running `pre-commit autoupdate` exists. **Not covered:** that it opens a pull request when a revision changes. |

### 4.6 `iac-cicd-pipeline` — ADDED: The Continuous-Integration Configuration Is Itself Verified

Added to the delta after this pass began, when the operator chose to wire the suite into `pr-validation.yml` rather than queue it. Covered here rather than deferred, so the scenario count stays complete.

| # | Scenario | | Tests / reason |
| --- | --- | --- | --- |
| F1 | A regression in CI configuration fails the pull request that introduces it | C | Two halves, both covered. **Does the suite discriminate:** `TestTheSuiteDiscriminates.test_the_suite_fails_a_configuration_that_violates_a_required_property` and `.test_the_suite_passes_a_configuration_that_satisfies_it` build two synthetic repositories differing in exactly one property — whether `dependabot.yml` names every lockfile-bearing directory — run the suite as a subprocess against each, and assert the verdicts differ. **Does a failure reach the check:** `TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_does_not_swallow_its_result`, guarded by `.test_the_required_check_invokes_the_suite`. The discriminating pair is the executable form of the "absence of evidence read as evidence of absence" objection this capability raises against its own destroy gate and its own secret scanning; without it, a suite that is always green satisfies every other test here. |
| F2 | The suite runs regardless of what a pull request touched | C | `TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_is_unconditional` — no `if:` on the step and none on its job — together with `TestRequiredCheckIsNotPathFiltered.test_the_required_check_declares_no_workflow_level_path_filter`, which is what stops the workflow itself from being filtered out. |
| F3 | The suite needs no privileged or external resource | C | `TestTheSuiteNeedsNoPrivilegedResource.test_the_suite_imports_only_the_standard_library_and_pinned_dependencies` (every import is its runtime's standard library or the pinned `yaml`), `.test_the_suite_imports_no_network_capable_module` (stdlib-only does not establish this — `urllib` is stdlib), `.test_the_suite_spawns_no_terraform_binary_or_container_runtime` (reads the suite's own `subprocess` calls out of its AST; the only command it spawns is `bash`, to exercise a workflow snippet). Self-asserting by construction, which is the point: the requirement constrains the suite, so the suite is what must be inspected. |

**Count:** 6 + 7 + 5 + 4 + 4 + 3 = 29 scenarios. Covered 14 · partial 10 · uncovered 5. All 29 accounted for.

## 5. Verified run against the current tree

46 tests. `python3 -m unittest discover --start-directory .github/tests` → **23 failures, 23 passes**, exit status 1. Every failure was classified before being recorded; none is left unattributed.

### 15 failures in state 1 — the assertion ran and discriminated

These fail because the current configuration genuinely violates the delta. They are what the implementation must turn green.

| Test | What it caught |
| --- | --- |
| `TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config` | `/terraform/modules/volume` carries a lockfile no Dependabot entry names |
| `TestSecretScanningIsUnconditional.test_no_secret_scanning_step_is_conditioned_on_terraform_changes` | both gitleaks steps carry a Terraform-gated `if:` |
| `TestSecretScanVersionParity.test_ci_installs_the_version_the_precommit_config_pins` | CI names a gitleaks version the pre-commit config does not pin |
| `TestApplyWorkflowTriggerIsPathFiltered.test_the_push_trigger_declares_a_path_filter` | `apply.yml`'s push trigger has no `paths:` |
| `TestApplyWorkflowTriggerIsPathFiltered.test_the_path_filter_still_covers_terraform_changes` | (same cause) |
| `TestApplyWorkflowTriggerIsPathFiltered.test_the_path_filter_excludes_changes_that_cannot_affect_infrastructure` | (same cause) |
| `TestDestroyPolicyGateFailsClosed.test_the_gate_does_not_swallow_an_inspection_failure` | the gate tolerates a failed inspection with `\|\| true` |
| `TestDestroyPolicyGateFailsClosed.test_the_gate_asserts_the_document_is_a_terraform_plan` | the gate never asserts `format_version` |
| `TestDestroyPolicyGateFailsClosed.test_the_gate_distinguishes_an_uninspectable_plan_from_a_clean_one` | the gate carries no message naming inspection as a cause |
| `TestAnsibleBlockingTier.test_an_ansible_path_filter_selects_changes_under_ansible` | no `ansible:` entry in the paths filter |
| `TestAnsibleBlockingTier.test_the_blocking_tier_runs_ansible_lint` | `pr-validation.yml` never invokes `ansible-lint` |
| `TestAnsibleBlockingTier.test_the_blocking_tier_runs_an_ansible_syntax_check` | it never invokes an Ansible syntax check |
| `TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_required_check_invokes_the_suite` | no step runs the suite (see §2 for the exact invocation) |
| `TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_is_unconditional` | (same cause) |
| `TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_does_not_swallow_its_result` | (same cause) |

### 8 failures in state 2 — the target does not exist yet

All eight fail on `.github/workflows/ansible-verify.yml does not exist`. **Their assertions have never executed**, so whether those assertions are any good is still unverified. **They must not be counted as coverage until that workflow exists**, and a green first run is the first evidence they discriminate at all.

`TestMoleculeDiscoveryAndScenarioCoverage.{test_the_workflow_names_no_role_literally, test_molecule_is_invoked_across_all_scenarios, test_the_workflow_uses_no_continue_on_error, test_role_discovery_fails_when_it_finds_nothing}`, `TestToolchainIsInstalledFromPinnedManifests.{test_the_molecule_workflow_installs_only_from_requirement_manifests, test_the_molecule_workflow_names_both_pinned_manifests}`, `TestVerificationJobsCarryNoCredential.{test_the_molecule_workflow_declares_no_environment, test_the_molecule_workflow_consumes_no_secret}`.

**No stub was created to make these execute.** Creating `ansible-verify.yml` — even empty — would be writing the implementation.

### 23 passes

Twenty-two assert behavior that already exists and that this change must not break — regression guards for scenarios the deltas carry through unchanged (B2, B5, B6, B7, C1, C3, C4, E1, E3, E4, the required-check cross-constraint, and the destroy gate's existence), plus the five §4.6 tests whose target is the suite itself.

**These passes are not state-4 alarms.** State 4 — a pass before any implementation exists — applies where the target is absent. For all 23 the target already exists (the current workflows, or the suite itself), so a pass is the expected result and establishes that the thing currently behaves as asserted.

**One vacuous pass, flagged:** `TestToolchainIsInstalledFromPinnedManifests.test_the_validation_workflow_installs_only_from_requirement_manifests` passes because `pr-validation.yml` currently contains no `pip install` at all. It asserts nothing today and becomes meaningful only once `tasks.md` 4.3 adds the blocking tier's installs. Do not read it as evidence before then.

### Three harness repairs made during authoring — failure state 3

Recorded because a repair that is not recorded is indistinguishable from weakening an assertion to reach green, and a later reader needs to see which it was. **None changed what is asserted**; each fixed a test that never reached a meaningful assertion.

1. `test_no_workflow_references_a_gitleaks_license_secret` matched `GITLEAKS_LICENSE` inside a YAML *comment* in `pr-validation.yml`. Fixed by ignoring whole-line comments. The assertion — no license secret is required — is unchanged, and the test now passes for the right reason.
2. `test_the_path_filter_excludes_changes_that_cannot_affect_infrastructure` passed vacuously: with no `paths:` key the pattern list is empty and nothing matches, so "excludes everything" and "filters nothing" were indistinguishable. Fixed by requiring a non-empty filter first; it now fails correctly, in state 1.
3. The first form of §4.6 F3's command check grepped the suite's text for `"terraform"` and matched the Dependabot **ecosystem name**, not a command. Replaced with an AST walk over the suite's own `subprocess` calls, which can tell a spawned binary from a string that happens to name one.

## 6. Obsolete tests

**None.** The `terraform test` glob `terraform/modules/<name>/tests/*.tftest.hcl` was searched in full — all eight files across `modules/server` and `modules/volume` — for tests bearing on the four `MODIFIED` deltas, matching on assertion text, run-block names and referenced behavior against the terms those deltas turn on (`gitleaks`, `dependabot`, workflow, plan inspection, `resource_changes`, lockfile, Ansible, Molecule, `pre-commit`).

Every test in that glob asserts Hetzner resource attributes under `mock_provider` — firewall rules, labels, `delete_protection`/`rebuild_protection` coupling, variable validation. None references CI configuration, the destroy gate, or Dependabot.

**This is "no such test exists", not merely "none was found by this search."** `terraform test` cannot reach GitHub Actions YAML, so no test in that glob *could* bear on these requirements. The four `MODIFIED` requirements had no test coverage anywhere before this pass.

No earlier `test-plan.md` path was dispatched, so none was consulted; none was searched for, since its referent would sit in an archived change directory whose path this pass may not construct.

`terraform/modules/server/tests/protection.tftest.hcl` and `terraform/modules/volume/tests/delete_protection.tftest.hcl` were considered and **rejected** as obsolete candidates: the Destroy Policy Gate requirement's rationale mentions `lifecycle { prevent_destroy = true }`, but that paragraph is carried through the delta unchanged, and those tests cover module resource attributes rather than the gate. Nothing supersedes them.

## 7. Project questions

**Q1 — There was no runner for repository-configuration tests, and the project recorded no convention for one.** *Resolved by the operator:* the suite lives at `.github/tests/`, colocated with almost everything it asserts about, avoiding a top-level test root in a repository whose only other tests are module-local `*.tftest.hcl`. Mechanism: Python `unittest` + PyYAML, both already present.

**Q2 — PyYAML was unpinned, against `AGENTS.md`'s exact-pinning convention.** *Resolved:* it will be pinned in `.github/requirements-ci.txt` (`tasks.md` 4.2) alongside `pre-commit`. **Pin 6.0.1** — the version these 46 tests were verified against. Two tests (§4.6 F3) fail if the suite ever grows an import that is neither standard library nor that pinned dependency.

**Q3 — Nothing would have run the suite.** *Resolved:* the operator chose to wire it into `pr-validation.yml` as an unconditional step now rather than queue it, and the delta gained the requirement covered in §4.6. §2 gives the exact command and working directory. The implementing session should use that invocation verbatim; it is the one under which the suite's behavior here was established.

**Q4 — Whether the Molecule discovery snippet must be standalone-runnable.** *Open, assumption recorded.* The A4 test extracts the discovery step's `run:` text and executes it. `tasks.md` 5.2 already prescribes exactly that verification ("running it against a scratch tree with no matching directory and observing a non-zero exit"), so the constraint is the plan's, not this pass's invention — but the scenario itself requires only the outcome, not the shape. *Assumption taken:* `tasks.md` 5.2 is binding. *Depends on it:* `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing`, which fails with an explicit message if the snippet embeds a `${{ }}` expression. This assertion is labelled DERIVED and may be reconsidered — as a recorded change to a derived assertion, never as a repair — if the implementation satisfies the scenario another way.

## 8. Recommendations for the implementation step, not obligations

- **Do not weaken a failing test to reach green.** The 15 state-1 failures are the change's specification made executable. Every SPECIFIED assertion that does not match means the configuration is wrong, not the test.
- **Re-run the 8 state-2 tests deliberately once `ansible-verify.yml` exists**, and treat that run — not this one — as the first evidence they discriminate.
- **Land the destroy-gate fixtures executably if the queued extraction happens.** `tasks.md` 1.1 already requires four fixture files to be kept. D1–D3 stay behaviorally uncovered only because the gate's logic is inline workflow shell. If the queued script-extraction (design Decision 5's second rejected alternative) is taken up, three uncovered scenarios become directly testable with fixtures that will already exist. Note that in the queue entry `tasks.md` 7.3 creates.
- **Keep the `TestTheSuiteDiscriminates` pair green.** It is the only thing standing between this suite and the failure mode it exists to prevent elsewhere: a check that reports success without having verified anything.
