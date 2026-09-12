# Test plan — `rename-the-external-services`

Written by an author other than whoever implements section 4, from the approved delta specs and before any implementation existed. This file is not an artifact the OpenSpec schema knows about: it does not appear among `openspec instructions apply`'s context files and must be read on purpose.

**This pass is additive only.** It added one module. It edited, deleted and disabled nothing, and it wrote no implementation. Every test named below as *obsolete* is a candidate for the implementing author to re-point — none was touched here.

## The test command and the row it comes from

`AGENTS.md`'s "Testing" section gives this repository three test commands. This change's entire testable surface is a static read of committed files, so it owes tests under one row only:

    python3 -m unittest discover --start-directory .github/tests   # from the repository root

Test-path glob: `.github/tests/*.py`. Nothing here is owed under `terraform test` (this change adds and edits no Terraform module) or under Molecule (it adds no role, edits no role and touches no scenario — tasks.md 1.5 states that already and this agrees with it).

## Baseline

**Full**, taken before writing anything, on the change's branch at the commit holding the approved plan:

| | Tests | Result |
|---|---|---|
| Before | 846 | OK |
| After | 864 | 1 failure, named below |

846 matches tasks.md 1.4's recorded baseline exactly. PyYAML resolved at 6.0.1, the version `.github/requirements-ci.txt` pins, so no module failed to import and the count is comparable.

The one failure after is `test_the_external_service_names_are_retired.TestNoCommittedFileNamesARetiredExternalService.test_no_swept_file_names_a_retired_external_name`, red by design: it reports 38 occurrences of a retired name across 9 committed files, every one of them a file tasks.md sections 4 and 5 names. That list is reproduced under *What the implementation must make pass*.

## What was added

One module: `.github/tests/test_the_external_service_names_are_retired.py`, 18 tests.

Individually selectable, in the form the runner takes:

    python3 -m unittest discover --start-directory .github/tests \
        --pattern 'test_the_external_service_names_are_retired.py'

    # or one test:
    python3 -m unittest test_the_external_service_names_are_retired\
.TestNoCommittedFileNamesARetiredExternalService\
.test_no_swept_file_names_a_retired_external_name

| Test | Classification |
|---|---|
| `TestNoCommittedFileNamesARetiredExternalService.test_no_swept_file_names_a_retired_external_name` | DERIVED — tasks.md 3.2. No requirement names a workspace, a repository secret or a Hetzner project as a value. |
| `TestNoCommittedFileNamesARetiredExternalService.test_the_sweep_reaches_the_files_the_rename_moves` | DERIVED — a guard, so a listing that read nothing cannot report the tree clean. |
| `TestNoCommittedFileNamesARetiredExternalService.test_every_exemption_names_something_the_repository_has` | DERIVED — a guard against an exemption that outlives its reason. |
| `TestTheDeployGateNamesTheEnvironmentAStackDeclares.test_the_deploy_gate_and_a_stacks_declaration_name_one_environment` | **SPECIFIED** — *Gated Deploy Reuses the Terraform Production Environment*: "the **same** `main-production` GitHub Environment protection rule already used by the Terraform apply workflow", and its scenario "Same approvers gate both kinds of production change". |
| The 14 tests in `TestTheseReadsDiscriminate` | DERIVED — fixture-driven discriminators, see below. |

Nothing in this module is deliberately untested that is not recorded in *Uncovered* below.

### The one genuinely new specified assertion, and why it is an equality

`TestTheDeployGateNamesTheEnvironmentAStackDeclares` compares `platform-deploy.yml`'s gated job's `environment:` with the `github_environment` a stack's own `pipeline.yml` declares, and requires exactly one stack to own it. Nothing in the suite read those two files as naming the same Environment until now: `GATED_DEPLOY_ENVIRONMENT` (`test_ci_configuration.py`) and `PROD_GITHUB_ENVIRONMENT` (`test_environment_agnostic_pipeline.py`) are separate literals in separate modules, both spelling `production` today by coincidence rather than by an assertion.

Written as an equality rather than against the literal `main-production` on purpose. Whether that Environment requires a reviewer is a repository setting no static read reaches, so a literal would assert only that a name was typed twice. The equality reports the failure this change actually risks — tasks.md 4.3 and 4.6 landing in different commits, or one of them not landing — and the proposal's Impact section says why that failure is the dangerous one: GitHub **creates** an Environment a workflow names, with no protection rules, so a deploy gated on a name no stack declares runs *unreviewed* rather than failing.

It is green today and must stay green. That is stated rather than hidden: a static check that is green at authoring establishes nothing on its own, which is what the discriminators below are for.

### Discriminators

Every assertion in the new module is a static read, so a green run reports only that the files could be read. Each read is therefore pointed at material the test supplies:

- The retired-name finder: an in-scope file naming each of the four names (reported), a clean corpus (not reported), the *replacement* names (not reported — the substring trap this match could have fallen into), an exempt path under each exemption (not reported), a path merely resembling an exempt one (reported), several occurrences in one file (all reported, not just the first), undecodable bytes (read rather than dropped), and a root that is no repository (raises rather than reporting clean).
- The gate comparison: a half-renamed pair (reported), an agreeing pair (not reported), a workflow gating on nothing (reported), two stacks owning the gated Environment (reported), and a read of the committed workflow returning exactly one Environment.

No discriminator came back negative, and none could be written but not executed.

The retired-name sweep additionally carries the stronger evidence: it is **red at authoring on real content**, on the property it exists to assert, and goes green as the change lands. No second record is owed at that point — the ordinary suite result is the confirmation, read against this one.

## Scenario accounting

Thirty-four `#### Scenario:` blocks across nine `MODIFIED` requirements in three capabilities. Every one is accounted for below exactly once.

**The shape of this delta is why so few are covered, and it is not a gap in this pass.** Eight of the nine requirements move exactly one literal — the GitHub Environment `production` becomes `main-production` — in requirement prose and, in seven scenarios, in a scenario body. The ninth corrects a rationale sentence and moves no literal at all. No scenario's *obligation* changes. What each renamed scenario asserts about the world is a property of a GitHub Environment's protection rules, which is a repository setting; the diff against `openspec/specs/` confirms it, one substitution at a time.

### `iac-cicd-pipeline` — Gated Production Apply Applies the Reviewed Plan (11)

| Scenario | Delta moves a literal in it | Account |
|---|---|---|
| Merge does not apply immediately | yes | **Partially covered** by `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_prod_declares_the_secret_and_environment_it_already_uses`, once tasks.md 4.10 moves `PROD_GITHUB_ENVIRONMENT` — that the stack declares the Environment by the new name. That the apply job *pauses for a required reviewer* is uncovered: a protection rule, reachable only by a network call this suite forbids itself. |
| A merge affecting one environment raises no other environment's approval | yes | Same account. The per-stack gating of the apply job is already asserted by `test_environment_agnostic_pipeline.TestEveryApplyIsGatedAndPerEnvironment` and moves with the declaration; the approval behaviour itself is uncovered, as above. |
| A shared module change reaches every environment | no | Uncovered by this pass; the delta changes nothing in it and existing coverage is unaffected. |
| A plan its own gate refused is not applied | no | As above. |
| One environment's failed plan does not block another's apply | no | As above. |
| An unresolvable set of planned environments fails the run | no | As above. |
| Reviewer sees the exact diff before approving | no | As above. |
| Applied changes match the approved plan | no | As above. |
| Apply credentials are inaccessible before approval | no | As above. |
| An unresolvable set of affected environments fails the run | no | As above. |
| A merge that cannot change infrastructure raises no approval request | no | As above. |

### `iac-cicd-pipeline` — Scheduled Workflows Report Their Own Liveness (8)

The delta's only edit is in the paragraph explaining why the ping key is repository-scoped: `production` becomes `main-production`. No scenario body changes.

| Scenario | Account |
|---|---|
| A scheduled run that fails is reported as a failure | Uncovered by this pass — unchanged by the delta. |
| A workflow that stops running at all is detected | Uncovered by this pass — unchanged, and in any case a property of a third-party observer. |
| A run in which a conditional job is skipped reports success | Uncovered by this pass — unchanged. |
| A failure in an early job is still reported | Uncovered by this pass — unchanged. |
| A cancelled run raises no alarm of its own | Uncovered by this pass — unchanged. |
| A scheduled workflow added without a report fails the pull request | Uncovered by this pass — unchanged; already asserted in `test_ci_configuration.py`. |
| The report needs no human approval | Uncovered by this pass — unchanged. The clause the rename touches ("SHALL declare no deployment `environment:`") is a negative about a name, and asserting the *absence* of an Environment declaration is already read there. |
| The routine alarm does not consume the last-resort one | Uncovered by this pass — unchanged. |

### `iac-state-management` — Remote State Backend (3)

The ninth requirement. It moves no name: what changes is the explanation of what pushing a `versions.tf` ahead of a workspace rename costs. No scenario body changes, and no scenario states the corrected claim.

| Scenario | Account |
|---|---|
| State is not stored locally | Uncovered by this pass — unchanged by the delta. |
| Two environments do not share a workspace | Uncovered by this pass — unchanged. Already asserted generically by `test_terraform_stacks_are_the_iterated_unit.TestEachStackNamesAWorkspaceDerivedFromItsOwnName.test_no_two_stacks_name_the_same_workspace`, which is written over every stack and moves with the tree; the workspace *names* themselves move in `test_a_second_environment.py`'s literals (see *Obsolete*). |
| Plan and apply run outside HCP Terraform's own execution | Uncovered by this pass — unchanged. |

### `iac-state-management` — HCP Terraform Access via a Static Token, Unsplit by Privilege (2)

| Scenario | Account |
|---|---|
| HCP token cannot reach real infrastructure on its own | Uncovered — unchanged by the delta, and a property of what a credential can do, which no static read reaches. |
| The split mechanism remains wired for a future upgrade | Uncovered — unchanged. |

### `iac-platform-deploy-pipeline` (10)

| Scenario | Delta moves a literal in it | Account |
|---|---|---|
| PR with invalid Compose syntax fails validation | no | Uncovered by this pass — unchanged. |
| Validation requires no deploy secret | no | Uncovered by this pass — unchanged; the requirement's renamed clause ("SHALL NOT declare a `main-production` ... Environment") is a negative already asserted in `test_ci_configuration.py`. |
| Pull request touching no platform file remains mergeable | no | Uncovered by this pass — unchanged. |
| Merge does not deploy immediately | yes | **Partially covered** by `test_ci_configuration.TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment`, once tasks.md 4.10 moves `GATED_DEPLOY_ENVIRONMENT` — that exactly one job declares the Environment by the new name. That it *pauses for a required reviewer* is uncovered: a protection rule. |
| Same approvers gate both kinds of production change | yes | **Covered, and the only scenario covered by a new assertion**: `test_the_external_service_names_are_retired.TestTheDeployGateNamesTheEnvironmentAStackDeclares.test_the_deploy_gate_and_a_stacks_declaration_name_one_environment`. It establishes the "same Environment" half. The "same required reviewers" half is uncovered: a protection rule. |
| Approver sees the diff without leaving the workflow run | no | Uncovered by this pass — unchanged. |
| Diff visibility does not depend on pull request review having occurred | yes | Uncovered — the rename is in the phrase "the `main-production` Environment's required reviewer", and what the scenario asserts is about that reviewer's view of a workflow run. No static read reaches it. |
| Deploy job joins the tailnet before SSH | no | Uncovered by this pass — unchanged. |
| Tailnet join credential is confined to the gated job | yes | Uncovered — the rename is in the WHEN ("pending `main-production` Environment approval"). What the scenario asserts is that an Environment secret is unreadable before approval: a repository setting. |
| Deploy key is inaccessible before approval | yes | Uncovered — same account. |

### Count

34 scenarios in the delta specs; 34 accounted for above. One covered, three partially covered, thirty uncovered with a reason.

## What is not testable here, and is not stood in for

Stated plainly because tasks.md 3.4 asks for it and `design.md` decision 2 says why it matters for this change in particular: its predecessor reported a probe that did not reach the code path it claimed to.

`.github/tests` makes no network call, and that constraint is itself asserted by tests in it — `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in `test_ci_configuration.py` reads every module in the directory, including the new one. So **nothing** below can be asserted by this suite, and no assertion here was shaped to gesture at any of it:

- That a GitHub Environment named `main-production` or `main-staging` exists, that either was renamed rather than created, that `main-production` requires a reviewer and `main-staging` does not, that either kept its fifteen and six secrets.
- That a repository secret exists under either new name, or that either old one was deleted.
- That an HCP workspace answers to a new name, carries the id it carried before, reports four resources, or has a state serial no lower than the one recorded.
- That a Hetzner project was renamed, or that its API token survived the rename.
- That any `terraform plan` reports `No changes`.

Every one of those is an operator observation in tasks.md 7.2, 8.2, 8.4 and 9.1. A green suite is **not** evidence for any of them.

Two further gaps inside what a static read *could* have reached, recorded rather than left to be discovered:

- **The Environment names `production` and `staging` are not swept.** Both are also Ansible group names, which this change does not touch and must not, so a sweep for either would report every correct use of the environment axis. tasks.md 6.4 makes those a manual read, one needle at a time, and that is where they stay.
- **`docs/change-queue.md` is exempt from the sweep** (see below), so entry 70's quotations of a moving secret name and a moving comment are caught by review alone — tasks.md 5.5 is where that lands.

## Deviation from tasks.md 3.2, with the evidence

tasks.md 3.2 states the new assertion as covering "no committed file **outside `openspec/changes/archive/`**". Implemented literally, that assertion is red on this change's own pull request, for files the repository requires to be exactly as they are. The exemption set was widened to three, each with the evidence that forced it:

1. **`openspec/changes/`** (rather than `openspec/changes/archive/`). This change's own `proposal.md`, `design.md`, `tasks.md` and `handoff.md` each name all four retired literals, as the from-side of the rename they describe — 16 occurrences. They are not archived until tasks.md 9.2, which is after the merge.
2. **`.github/tests/`**. This is where a check must name a retired name in order to assert its absence — the new module does, in its own `RETIRED_NAMES` — and where `test_a_second_environment.py`, `test_environment_agnostic_pipeline.py` and `test_host_configuration_names_its_environment.py` build synthetic trees naming `prod`, `staging`, `HCLOUD_TOKEN_STAGING` and `infrastructure-prod` to exercise a reader. tasks.md 4.10 says those fixtures do not move. **No coverage is lost by this**: the literals in that directory that *do* move are each compared against a committed declaration by their own module, so one left behind fails there.
3. **`docs/change-queue.md`**. Entry 63 — this change's own queue entry — names all four retired literals, and `AGENTS.md` has it deleted when the change is archived (tasks.md 9.3, in the archive commit). Without this exemption the assertion is red on the pull request for an entry the repository's own convention requires to still be there.

`docs/deferred-work.md` was considered as a fourth and deliberately left in scope: an entry there records work *not* done, and about a rename that means the old name genuinely persists, which is a thing to report.

`openspec/specs/` is deliberately in scope, which is narrower than the precedent in `test_terraform_stacks_are_the_iterated_unit.py` (that sweep excludes `openspec/` entire). No requirement names any of these four values today, and one that started to would be a finding rather than history.

**This is a deviation from the plan's stated scope, not a judgment that the plan was wrong about what to assert.** It is recorded here and reported rather than folded in silently.

## Obsolete tests

Every entry below is a **candidate for human confirmation**, not a conclusion. **Nothing here was edited, deleted or disabled by this pass.** Each is a test whose expected value is the behaviour a `MODIFIED` delta supersedes; the implementing author re-points them under tasks.md 4.10 and 4.11, and this list exists so the set is visible rather than inferred.

Searched within the dispatched test-path glob `.github/tests/*.py` and nowhere else. No earlier `test-plan.md` was supplied to this pass, so no scenario-to-test mapping was available to draw on; the search was by the superseded literals themselves.

| Runner-selectable test | Superseded by | Evidence |
|---|---|---|
| `test_ci_configuration.TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment` | `iac-platform-deploy-pipeline` / *Gated Deploy Reuses the Terraform Production Environment* | Reads the module constant `GATED_DEPLOY_ENVIRONMENT`, whose value is `"production"` — the Environment name the delta replaces with `main-production`. The test asserts exactly one job in `platform-deploy.yml` declares it. |
| `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_prod_declares_the_secret_and_environment_it_already_uses` | `iac-cicd-pipeline` / *Gated Production Apply Applies the Reviewed Plan*; and tasks.md 4.3 for the secret | Asserts prod's declaration equals the module constants `PROD_GITHUB_ENVIRONMENT` (`"production"`) and `PROD_READ_ONLY_SECRET` (`"HCLOUD_TOKEN_PRODUCTION"`). Both values move. |
| `test_a_second_environment.TestTheSecondEnvironmentIsDeclared.test_the_second_environment_declares_its_own_secret_and_environment` | tasks.md 4.4 (no requirement names these values) | Asserts staging's declaration equals `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT` (`"staging"`) and `SECOND_ENVIRONMENT_READ_ONLY_SECRET` (`"HCLOUD_TOKEN_STAGING"`). |
| `test_a_second_environment.TestTheSecondEnvironmentIsDeclared.test_the_second_environment_names_its_own_workspace` | tasks.md 4.1 | Asserts staging's `cloud` block names `SECOND_ENVIRONMENT_WORKSPACE` (`"infrastructure-staging"`), and its own docstring says the value moves at "`docs/change-queue.md` entry 63", which is this change. |
| `test_a_second_environment` — the module constant `WORKSPACE_FORM` | `iac-state-management` / *Remote State Backend* | Referenced by no test in the suite. Its comment quotes the requirement as "named `infrastructure-<environment>`" — a derivation *Remote State Backend* no longer states, and which the delta's "**A workspace's name SHALL NOT be computed from its stack's directory name**" forbids. A dead literal asserting a retired rule. tasks.md 4.11 deletes it. |

**Five entries found, and the search that found them was bounded.** These are not "no such test exists" anywhere else — they are what a search by superseded literal over `.github/tests/*.py` reached. A test bearing on the superseded behaviour without naming one of those literals would not have been found by it.

## Unresolved project questions

Recorded rather than resolved, since this pass has no channel to ask on. Each names the assumption taken and which tests depend on it.

1. **How wide the retired-name exemption set should be.** tasks.md 3.2 names one exemption; three were needed. *Assumption taken*: the three above, each on the stated evidence. *Depends on it*: `test_no_swept_file_names_a_retired_external_name` and `test_every_exemption_names_something_the_repository_has`. A reviewer disagreeing with any one of the three is disagreeing with an assertion, not with a detail.
2. **Whether the deploy gate's Environment should be asserted as an equality or as a literal.** tasks.md 3.1 says not to write a second assertion on `platform-deploy.yml`'s gated job, and this is not one — but it is adjacent, and the plan does not anticipate it. *Assumption taken*: the equality, for the reason stated above. *Depends on it*: `TestTheDeployGateNamesTheEnvironmentAStackDeclares` entirely. If the reviewer would rather this did not exist, deleting it costs nothing this pass claims elsewhere.
3. **Whether this module should have been a new file or a section of an existing one.** The suite's own precedent for a rename sweep lives in `test_terraform_stacks_are_the_iterated_unit.py`, which is a change-named module. *Assumption taken*: a new file, following that precedent and because a test author who may only add cannot restructure an existing module.

## What the implementation must make pass

One assertion is red. Its failure list is the sweep's own worklist, and every file on it is named by tasks.md sections 4 and 5:

| File | Occurrences | Task |
|---|---|---|
| `docs/bootstrap-a-new-host.md` | 17 | 5.2 |
| `ansible/inventory/main-production.hcloud.yml` | 3 | 4.5 |
| `terraform/stacks/main-production/versions.tf` | 3 | 4.1 |
| `terraform/stacks/main-staging/versions.tf` | 3 | 4.1, 4.2 |
| `README.md` | 4 | 5.1 |
| `ansible/inventory/main-staging.hcloud.yml` | 2 | 4.5 |
| `ansible/.envrc.example` | 2 | 4.7 |
| `.envrc.example` | 2 | 4.8 |
| `terraform/stacks/main-production/pipeline.yml` | 1 | 4.3 |
| `terraform/stacks/main-staging/pipeline.yml` | 1 | 4.4 |

Total 38. The test prints every one as `<path>:<line>: <name>` together with the replacement to write.

Two assertions are green and must **stay** green through the change — they are the ones that catch a half-done rename rather than a missed one:

- `TestTheDeployGateNamesTheEnvironmentAStackDeclares.test_the_deploy_gate_and_a_stacks_declaration_name_one_environment` — goes red if tasks.md 4.3 and 4.6 do not land together.
- `test_host_converge_workflow.TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares.test_each_source_reads_the_name_its_declaration_states` — goes red if tasks.md 4.3/4.4 and 4.5 do not land together. Confirmed as carrying this change, per tasks.md 3.3: it is written over every stack, compares each declared `read_only_secret` with its inventory source's credential variable *literally* (case included), and moves with the tree without an edit.

Also confirmed as carrying this change without an edit, per tasks.md 3.3: `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret` and `.test_no_two_environments_declare_the_same_github_environment`, both written over the whole declaration census.
