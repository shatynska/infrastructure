# Test plan — open-autoupdate-pr-with-app-token

Tests derived from this change's delta specs, before any implementation of the change existed. The author of these tests did not read the implementation and did not write it.

This file is **not** an artifact the OpenSpec schema knows about. It does not appear among the context files `openspec instructions apply` lists, so whoever implements this change has to open it on purpose.

All tests live in `.github/tests/test_ci_configuration.py` (the third row of AGENTS.md's testing table: every assertion here is a static read of a committed file). They are appended as one new section at the end of that file, after its existing 131 tests, with a provenance header naming this change. Nothing in the file was edited, deleted or disabled.

Runner, from the repository root:

```
python3 -m unittest discover --start-directory .github/tests
```

A single test, selectable individually (this is the form task 1.1 and task 2.5 should use):

```
python3 -m unittest test_ci_configuration.TestNoWorkflowOpensAPullRequestWithTheDefaultToken\
.test_no_pull_request_opening_step_is_given_the_default_workflow_token
```

## Baseline

Taken on the unmodified tree, before any test was written — **full suite, not scoped**:

| Command | Result |
|---|---|
| `python3 -m unittest discover --start-directory .github/tests` | 131 tests, OK |
| `pre-commit run --all-files` | 6 hooks, all passed |

After this pass, on the same unmodified workflow and README: **146 tests, 8 failures**, all 8 among the 15 added here. The 131 pre-existing tests are unchanged and still pass. `pre-commit run --all-files` still passes all 6 hooks.

## Scenario accounting

The delta spec carries **9** `#### Scenario:` blocks under one MODIFIED requirement (`Automated Dependency Updates`). Each is accounted for exactly once below. (The dispatch that commissioned this pass said ten; the file has nine — four pre-existing and five new.)

| # | Scenario | Covered by |
|---|---|---|
| 1 | Provider version update is proposed automatically | Uncovered — pre-existing, untouched by this delta. Its enabling condition is covered by `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems`; the outcome is Dependabot's behaviour, not a static read. |
| 2 | Every lockfile-bearing directory is covered | Pre-existing, untouched: `TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config` |
| 3 | Action version update is proposed automatically | Uncovered — pre-existing, untouched. Same reason as 1. |
| 4 | Pre-commit hook revisions are refreshed on a schedule | Pre-existing, untouched: `TestScheduledHookRefresh.test_a_scheduled_workflow_runs_pre_commit_autoupdate`. Newly reinforced by `TestNoWorkflowOpensAPullRequestWithTheDefaultToken.test_a_committed_workflow_step_opens_a_pull_request_at_all`, which asserts the "opens a pull request with the result" half. |
| 5 | A workflow-opened pull request receives the required status checks | **Uncovered, deliberately.** It is an observation of a live pull request — that `validate` and `ansible-verify` reported a conclusion and the pull request is mergeable. It needs a network call and a merged change, both of which this suite's own tests forbid it. It belongs to the change's confirm gate; tasks 6.1–6.3 are where it is discharged. |
| 6 | No workflow opens a pull request with the default workflow token | `TestNoWorkflowOpensAPullRequestWithTheDefaultToken`: `test_a_committed_workflow_step_opens_a_pull_request_at_all`, `test_every_pull_request_opening_step_is_given_an_explicit_token`, `test_no_pull_request_opening_step_is_given_the_default_workflow_token`, `test_a_step_producing_that_token_appears_earlier_in_the_same_job`; plus `TestPermissionsReading.test_the_default_token_is_recognised_in_both_its_spellings` |
| 7 | The default workflow token is not left holding unused write authority | `TestThePullRequestJobLeavesTheDefaultTokenNoWrite.test_the_job_opening_a_pull_request_receives_no_write_scope`; plus `TestPermissionsReading.test_write_grants_are_recognised_in_both_the_mapping_and_blanket_forms` and `.test_a_job_block_replaces_the_workflow_block_rather_than_adding_to_it` |
| 8 | A permissions declaration is present rather than merely absent | `TestThePullRequestJobLeavesTheDefaultTokenNoWrite.test_the_job_opening_a_pull_request_declares_permissions_explicitly`; plus `TestPermissionsReading.test_a_declaration_absent_at_both_levels_is_read_as_absent` and `.test_an_empty_mapping_is_a_declaration_granting_no_write`. Absence is also an offender inside scenario 7's test, so deleting the declarations cannot buy a green run. |
| 9 | A long-lived automation credential is documented where it can be found | `TestTheAutomationCredentialIsDocumentedInTheReadme`: `test_the_pull_request_job_draws_its_identity_from_a_repository_secret`, `test_every_secret_holding_that_credential_is_named_in_the_readme`, `test_the_readme_passage_says_how_that_credential_is_rotated`, `test_the_readme_passage_states_the_authority_that_credential_holds` |

### Deliberately untested, within a covered scenario

- **Scenario 9, "name that credential".** The runbook must name the credential itself, alongside the secrets, the authority and the rotation procedure. A free-text name has no static form that could be asserted without dictating the README's wording. What is asserted instead is that a single README section names every secret the pull-request job reads, and that this same passage states an authority and a rotation procedure — a passage a reader can find, rather than four facts scattered across the file.
- **`branch-token` left at its default.** Design Decision 3 requires it; the scenarios do not state it. It is covered indirectly and by a DERIVED extension: every input on the pull-request step named `token` or ending `-token` is read, so pinning `branch-token` to `GITHUB_TOKEN` fails. That an explicitly-set-and-correct `branch-token` is preferable to a defaulted one is not asserted either way.
- **The secrets exist, the App is installed, its permissions are as scoped.** Not repository content. Tasks 5.1–5.4 are the operator's, and no test here can or should stand in for them.

## Assertion provenance

Every test method carries its own SPECIFIED / DERIVED annotation in its docstring. Summarised:

**SPECIFIED** (traces to SHALL text or to a scenario in the delta spec):

- `test_a_committed_workflow_step_opens_a_pull_request_at_all` — "opens a pull request with the result"; also the vacuity guard for the whole section.
- `test_every_pull_request_opening_step_is_given_an_explicit_token` — "SHALL be given an explicit token input".
- `test_no_pull_request_opening_step_is_given_the_default_workflow_token` — "neither `secrets.GITHUB_TOKEN` nor `github.token`".
- `test_a_step_producing_that_token_appears_earlier_in_the_same_job` — "a step producing that token SHALL appear before it in the same job".
- `test_the_job_opening_a_pull_request_declares_permissions_explicitly` — "SHALL come from an explicit declaration at workflow or job level".
- `test_the_job_opening_a_pull_request_receives_no_write_scope` — "an explicit `permissions:` declaration SHALL be in force for that job, and the permissions it grants SHALL NOT include a write".
- `test_a_declaration_absent_at_both_levels_is_read_as_absent`, `test_an_empty_mapping_is_a_declaration_granting_no_write`, `test_write_grants_are_recognised_in_both_the_mapping_and_blanket_forms`, `test_the_default_token_is_recognised_in_both_its_spellings` — unit-level cover for the helpers the four tests above rest on.
- `test_every_secret_holding_that_credential_is_named_in_the_readme` — "the secrets holding it".
- `test_the_readme_passage_says_how_that_credential_is_rotated` — "how it is rotated" (the obligation; the matched word is DERIVED, see below).
- `test_the_readme_passage_states_the_authority_that_credential_holds` — "the authority it is scoped to" (same split).

**DERIVED** (inferred; no scenario states it):

- `test_the_pull_request_job_draws_its_identity_from_a_repository_secret` — from the requirement's "such an identity is supplied by repository secrets rather than by repository content", not from a scenario. Without it, the three README tests would each pass over an empty set of secrets and the README obligation would be satisfied by a README saying nothing.
- The extension of the token check from `token:` to every `*-token` input — from design Decision 3.
- `test_a_job_block_replaces_the_workflow_block_rather_than_adding_to_it` — the precedence is GitHub Actions' own semantics, not spec text.
- The vocabulary matched in the README passage: `rotat` for rotation, and any of `permission` / `scope` / `authorit` / `read and write` / `write access` for authority. The obligations are specified; the words are this check's choice, because a runbook sentence has no other static form. **This is the assertion most likely to need adjusting** — if the README states both facts in words outside that vocabulary, widen the vocabulary rather than weakening the test, and record the widening.
- Discovery of a pull-request-opening step: `uses:` matching `create-pull-request`, or a `run:` containing `gh pr create` / `hub pull-request`, or a POSTed `/pulls` API call. `apply.yml`'s `gh api repos/.../pulls/<n>` is deliberately not matched — reading a pull request is not opening one.

## Obsolete tests

**None. No test in the suite is superseded by this delta**, and this is a determination, not an empty search result:

- Search bound: `.github/tests/*.py` — the dispatched test-path glob, which is the whole of the suite this change touches (one file).
- The delta is a MODIFIED of `Automated Dependency Updates`, and the modification is **purely additive**. Comparing the requirement in `openspec/specs/iac-safety-hardening/spec.md` against the delta block by block: 0 blocks removed or altered, 11 added (6 paragraphs and 5 scenarios). Every pre-existing paragraph and all four pre-existing scenarios are present verbatim.
- The three tests bearing on that requirement today — `TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config`, `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems`, `TestScheduledHookRefresh.test_a_scheduled_workflow_runs_pre_commit_autoupdate` — each assert text the delta leaves untouched. None is a candidate for deletion or rewriting.
- `TestDiscoveryDeclaresTheLeastPrivilegeItNeeds` also asserts workflow permissions, but only over `ansible-verify.yml`, which this change does not touch. Not superseded.

No earlier `test-plan.md` was supplied for this change, and none was searched for.

## Unresolved project questions

None that changed an assertion. Both questions that arose were answered by the repository:

- Runner and test placement — AGENTS.md's testing table names the row (`python3 -m unittest discover --start-directory .github/tests`, `.github/tests/*.py`), and the suite is `unittest`, not `pytest`.
- Constraints on what may be asserted — the suite's own `TestTheSuiteNeedsNoPrivilegedResource` asserts them, and it reads this file's AST. The new section adds no import, spawns no process and makes no network call, so those three tests still pass.

## Expected state, and what implementation must make pass

Against the **unmodified** workflow and README, 8 of the 15 new tests fail. All 8 are failing because the committed files produce a wrong value — the code ran and the assertion discriminated. None is failing because a target is absent: `.github/workflows/pre-commit-autoupdate.yml`, `README.md` and the suite itself all exist.

**Red today — implementation must turn these green:**

| Test | What is wrong today |
|---|---|
| `TestNoWorkflowOpensAPullRequestWithTheDefaultToken.test_every_pull_request_opening_step_is_given_an_explicit_token` | the `create-pull-request` step supplies no `token:` at all |
| `….test_no_pull_request_opening_step_is_given_the_default_workflow_token` | same, via the guard it calls |
| `….test_a_step_producing_that_token_appears_earlier_in_the_same_job` | same, via the guard it calls; no minting step exists |
| `TestThePullRequestJobLeavesTheDefaultTokenNoWrite.test_the_job_opening_a_pull_request_receives_no_write_scope` | the job declares `contents: write` and `pull-requests: write` |
| `TestTheAutomationCredentialIsDocumentedInTheReadme.test_the_pull_request_job_draws_its_identity_from_a_repository_secret` | the job names no repository secret |
| `….test_every_secret_holding_that_credential_is_named_in_the_readme` | same |
| `….test_the_readme_passage_says_how_that_credential_is_rotated` | same |
| `….test_the_readme_passage_states_the_authority_that_credential_holds` | same |

Tasks 2.1–2.3 close the first four; tasks 2.1 and 3.1 together close the last four.

**Green today, and expected to stay green.** These are not coverage of new behaviour; each is a guard on the cheapest way of faking the fix. Their passing on the first run is not the fourth failure state — the target exists and the property already holds — and each was shown to discriminate against a mutated fixture (below):

- `test_a_committed_workflow_step_opens_a_pull_request_at_all` — fails if the discovery stops matching anything, which would otherwise turn the whole section green over an empty list.
- `test_the_job_opening_a_pull_request_declares_permissions_explicitly` — fails if both `permissions:` blocks are deleted. "Grants no write" is trivially true of a workflow declaring nothing, so deleting the workflow-level block along with the job-level one is the cheapest way to make the write test green, and it is the opposite of what the requirement asks. **Task 2.3 must delete the job-level block only.**
- The five `TestPermissionsReading` unit tests — helper-level, and green because the helpers are correct.

### Discrimination evidence

Because two of the new tests pass against the unmodified tree, the section was run against a scratch fixture (`REPO_ROOT` override, the mechanism `TestTheSuiteDiscriminates` already uses) shaped like the intended implementation, and then against five one-property mutations of it:

| Fixture | Failures |
|---|---|
| implementation-shaped | 0 of 15 |
| no `permissions:` at either level | `…declares_permissions_explicitly`, `…receives_no_write_scope` |
| `branch-token:` pinned to `secrets.GITHUB_TOKEN` | `…is_given_the_default_workflow_token` |
| minting step moved after the pull-request step | `…producing_that_token_appears_earlier_in_the_same_job` |
| `token:` input deleted | `…given_an_explicit_token`, `…default_workflow_token`, `…appears_earlier_in_the_same_job` |
| job-level `contents: write` reintroduced | `…receives_no_write_scope` |

The fixture is scratch-only and is not committed.
