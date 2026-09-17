# Test plan — add-a-staging-environment

Derived from this change's delta specifications at commit `3f992e6`, the commit holding the approved plan, by an author other than whoever implements it. No implementation of this change was read, and none exists: the deltas and the current specifications under `openspec/specs/` are what the tests below trace to.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among the context files `openspec instructions apply` lists, so it has to be read on purpose. Read it before implementing: it is the scenario-to-test mapping the task list's verification step (4.1) is checked against.

Everything written here is additive. This pass added one test module and edited, deleted or disabled nothing. **This pass adds tests and never subtracts.**

## Where the tests are

`.github/tests/test_a_second_environment.py` — 35 tests, all individually selectable:

    python3 -m unittest discover --start-directory .github/tests
    python3 -m unittest discover --start-directory .github/tests -k <test name>
    python3 -m unittest discover --start-directory .github/tests -k <class name>

Run from the repository root, and through `discover` in both forms — it is
discovery that puts `.github/tests` on `sys.path`. `python3 -m unittest
<module>.<class>.<test>` from the repository root does **not** work and fails
to import the module.

**Why `.github/tests` and not another row of AGENTS.md's testing table.** `terraform test` places tests only under `terraform/modules/<name>/tests/`, and this change touches no module — it adds an environment directory, which this repository gives no test destination. Molecule tests a role's behaviour on a host, and this change touches no role. `.github/tests` is the remaining row and the only one whose subject — any property that is a static read of a committed file, repository-wide — covers what this change commits.

## Baseline

Full suite, taken before any test was written, from the repository root of the `add-a-staging-environment` working tree at commit `3f992e6`:

    python3 -m unittest discover --start-directory .github/tests
    Ran 494 tests in 8.434s
    OK

Not scoped. Nothing failed beforehand, so every failure listed below is attributable to this pass.

After this pass: **529 tests, 5 failures**, all five in the new module and all five expected — see *What the implementation must make pass*.

## What the implementation must make pass

Five tests are red now and go green as the change lands. Every other new test is a guard whose subject already exists (prod's configuration, `apply.yml`) or is vacuous until the second environment directory appears; a guard passing on its first run is the expected result rather than the "passed before any implementation existed" alarm, because its target is not absent. The module's own docstring says which is which.

| Test | Goes green on |
|---|---|
| `test_a_second_environment_directory_exists` | tasks 2.1–2.4 |
| `test_the_second_environment_names_its_own_workspace` | task 2.1 |
| `test_the_second_environment_declares_its_own_secret_and_environment` | task 2.4 |
| `test_the_conventions_file_states_the_prohibition_over_every_environment` | task 3.2 |
| `test_the_readme_runbook_states_the_prohibition_over_every_environment` | task 3.3 |

Two further tests are **vacuous today and become red the moment the staging directory is added**, which is deliberate — they read the records against the set of environments that exist:

| Test | Goes red on | Goes green on |
|---|---|---|
| `test_no_readme_sentence_calls_an_existing_environment_anticipated` | task 2.1 | task 3.3 |
| `test_every_environment_that_declares_a_volume_names_it_identically` | a staging `terraform.tfvars` naming its volume anything but prod's name | task 2.3 |

One existing test, not written by this pass, also goes red when the staging lockfile is committed and green when task 2.7 is done: `test_ci_configuration.TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config`. Design.md Decision 9 already predicts it. It is not obsolete; it is the check working.

### These tests were confirmed satisfiable

The five red tests were run against a throwaway copy of the tree, outside the repository, carrying a staging environment directory and generalised records (`REPO_ROOT` is the suite's own override for the tree it reads). All 35 passed. The same probe was then given two defects — staging naming prod's workspace, and staging naming its volume `staging-data` — and the four assertions those defects violate went red. So the red tests are in the state "the target is absent", not the state "the test is broken", and the guards discriminate over a real two-environment tree rather than only over fixtures. Nothing was written into the repository to establish this.

## Scenario coverage

Nineteen `#### Scenario:` blocks across the three delta specs and the one requirement they remove. Each is accounted for exactly once.

### iac-state-management — MODIFIED: Remote State Backend

| Scenario | Covered by |
|---|---|
| State is not stored locally | `test_every_environment_configures_an_hcp_workspace_as_its_backend`, `test_no_environment_configures_a_local_backend`, `test_no_environment_directory_holds_a_state_file`, `test_the_state_exclusion_is_recorded_in_gitignore` |
| Two environments do not share a workspace | `test_no_two_environments_name_the_same_workspace`, `test_every_workspace_name_follows_the_per_environment_form`, `test_the_second_environment_names_its_own_workspace` |
| Plan and apply run outside HCP Terraform's own execution | **Uncovered.** Whether a run executes on the GitHub Actions runner or on HCP Terraform's own is decided by the workspace's Execution Mode, an HCP setting reachable only through its UI or API. The committed half — that the workflows invoke the Terraform CLI in a runner job — is already asserted by `test_environment_agnostic_pipeline.py`'s plan and apply assertions; nothing this pass could add distinguishes a Local workspace from a remote one by reading a file. |

The requirement's own prose says workspace-name uniqueness "is a property of the HCP Terraform organization" that no file here can detect. That is true of the organization; the tests above cover the half that is a static read — that no two environments **committed here** name one workspace.

### iac-state-management — MODIFIED: Workspace Execution Mode Set to Local

| Scenario | Covered by |
|---|---|
| Saved plan files are usable by the pipeline | **Uncovered by this pass.** That the pipeline saves a plan and applies that same artifact is already asserted by `test_planned_environment_apply_stage.TestASavedPlanIsPublishedOnlyAfterItsOwnChecksPassed` and `test_ci_configuration.TestSavedPlanIsWhatGetsApplied`; whether the plan file is *applicable*, which is what Execution Mode decides, is an HCP setting and an outcome of a real run. |
| A newly created workspace is set to Local before its environment is used | **Uncovered.** An HCP workspace setting. tasks.md 1.4 is the mechanism and the operator's report is the evidence. |
| Remote execution mode is treated as misconfiguration | **Uncovered.** Same setting, read from the same place. |

All three are named in design.md Decision 9 as beyond a static read. **A static residue was considered and rejected:** asserting that every environment's `versions.tf` carries a comment stating the Local requirement, as prod's does. No scenario obliges such a comment and no task writes one for staging, so the assertion would have been this author designing a convention. Recorded here so the absence of the test is distinguishable from the absence of the thought.

### iac-state-management — ADDED: Each Environment Has a Dedicated Hetzner Cloud Project

| Scenario | Covered by |
|---|---|
| One environment's credentials do not reach another's project | **Uncovered.** What a Hetzner API token can reach is an API fact needing a credential and a network call, both of which this suite forbids. The committed residue — that no two environments name one read-only secret — is already asserted by `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret`, and that assertion stops being vacuous the day staging lands. |
| An ungated environment cannot reach a reviewed environment's resources | **Uncovered.** A GitHub Environment's protection rules are a repository setting and the token's reach is an API fact. Residue already asserted: `..._declaration.test_no_two_environments_declare_the_same_github_environment` and `test_environment_agnostic_pipeline.TestEveryApplyIsGatedAndPerEnvironment.test_every_apply_job_declares_an_environment`. |
| Two environments may name a resource identically | Covered in part: `test_the_platform_stack_hardcodes_exactly_one_volume_mount_name`, `test_every_environment_that_declares_a_volume_names_it_identically`. The "both SHALL be creatable" half is a Hetzner API fact and is uncovered. |

### iac-state-management — REMOVED: Dedicated Hetzner Cloud Project for Prod

| Scenario | Covered by |
|---|---|
| Prod credentials are isolated | **Uncovered, by operation.** The requirement is removed, and removed behaviour is not tested. Its obligation is not lost: the ADDED requirement above states it over every environment, and its scenarios are accounted for there. |

### iac-repo-foundations — MODIFIED: Environment and Module Folder Structure

| Scenario | Covered by |
|---|---|
| Prod environment consumes a shared module | `test_every_environment_calls_at_least_one_shared_module`, `test_every_module_call_resolves_to_a_relative_path_under_terraform_modules` — written over the discovered set, so the assertion reaches prod and every environment added after it |
| Adding a future environment does not require restructuring | Covered in part: the same two tests, plus `test_no_environment_pins_a_module_version_of_its_own` and `test_a_second_environment_directory_exists`. **The "without moving or renaming existing files" half is uncovered:** it is a property of a diff, not of a tree, and no single static read of the committed files can see it. Review is the mechanism; tasks.md 4.4's diff read is where it is looked at. |
| A shared module change reaches every environment without an imposed order | `test_no_apply_job_depends_on_another_environments_apply`, `test_the_apply_matrix_is_neither_serialised_nor_abandoned_on_a_sibling`, `test_every_apply_job_attaches_to_an_environment_resolved_per_row` |
| Promotion ordering is exercised at the approval, not by the workflow | Covered in part by the same three tests, which assert the half that is a committed file: the workflow implements no ordering, and none can be reintroduced without failing them. **The other half is uncovered** — that an approver withholds approval until a lower environment has been seen to succeed is a human discipline, which the delta itself states "as what holds rather than as what is guaranteed". |

### iac-safety-hardening — MODIFIED: Write Credentials Confined to the Gated Pipeline

| Scenario | Covered by |
|---|---|
| Local apply is refused by the API | **Uncovered.** The refusal happens at the Hetzner Cloud API, under a credential, over the network. |
| Local plan remains available | **Uncovered.** Same boundary. |
| A non-production environment's write token is confined identically | **Uncovered.** Which secrets a GitHub Environment holds, and what sits on a workstation, are neither committed files nor readable without a network call. Residue asserted: `test_the_second_environment_declares_its_own_secret_and_environment` (the repository names a read-only secret of its own for the second environment) and the two census assertions cited above. |
| An agent opening the repository is told the boundary | Already covered by `test_environment_agnostic_pipeline.TestTheWriteCredentialBoundaryIsStatedToAgents.test_the_conventions_file_states_that_apply_is_not_run_locally`, whose fragment match survives this change's generalisation — verified against a generalised `AGENTS.md` in the probe above. Strengthened, not replaced, by `test_the_conventions_file_states_the_prohibition_over_every_environment`. |
| The record covers an environment added after it was written | `test_the_conventions_file_states_the_prohibition_over_every_environment`, `test_the_readme_runbook_states_the_prohibition_over_every_environment`, supported by `test_no_readme_sentence_calls_an_existing_environment_anticipated` |

**A static check for the token-on-disk half was considered and rejected.** The requirement forbids a write token in "a dotfile, `direnv` file, or any `.tfvars` file", which reads like a static sweep — but `.envrc` is gitignored and holds the **read-only** token by this repository's own README instructions, and no static read can tell a read-only token from a write one. Such a test would fail on a correctly provisioned workstation, and the repair for a false offence is to loosen the assertion, which is the repair this suite must never need. `gitleaks` covers a committed secret; the confinement itself is confirmed by the operator.

## Assertion classification

Per the testing floor, every assertion is one of three things. The module annotates each test in its own docstring; this is the summary.

**SPECIFIED** — traces to SHALL text or to a scenario in a delta spec. Every test in `TestEachEnvironmentHasAWorkspaceOfItsOwn`, `TestEveryEnvironmentConsumesTheSharedModules`, `TestNoEnvironmentsApplyWaitsOnAnother`, and `TestTheWriteCredentialRecordCoversEveryEnvironment`; and `test_the_second_environment_names_its_own_workspace` as to its *form* (`infrastructure-<environment>` is stated by the requirement).

**DERIVED** — inferred from this change's `design.md`, `tasks.md` or `proposal.md`, with no scenario stating it. Each is listed so it is reviewable rather than indistinguishable from a stated requirement:

| Derived assertion | Where it comes from | What it obliges |
|---|---|---|
| The four `SECOND_ENVIRONMENT*` literals — the name `staging`, `HCLOUD_TOKEN_STAGING`, the GitHub Environment `staging`, `destroy_policy_gate: false` | tasks.md 2.4, 1.5, 1.6 | That the second environment is named and declared exactly as the task list says. No delta scenario names an environment called `staging`; the deltas are written over "every environment" throughout, which is the point of them. |
| `test_every_environment_that_declares_a_volume_names_it_identically` | design.md Decision 4, tasks.md 2.3; the requirement's own prose gives the reason | Stronger than the scenario: the scenario *permits* a shared volume name, this *requires* one. Asserted because the failure it catches is silent — a differently named volume plans, applies and mounts, and only the containers expecting `/mnt/main-data` notice. |
| `test_the_platform_stack_hardcodes_exactly_one_volume_mount_name` | the same | Locates the value the assertion above compares against, and stops it comparing against nothing. |
| `test_no_readme_sentence_calls_an_existing_environment_anticipated` | tasks.md 3.3 | That no committed record describes an environment that exists as not existing. A reader told an environment is anticipated has no reason to look for its write token at all, which is the *Write Credentials* defect in its most readable form. |
| Every test in `TestTheseReadsDiscriminate` | none — it is machinery | That the predicates the SPECIFIED assertions rest on actually read something. Nothing in it reads a committed file. |

**DELIBERATELY UNTESTED** — recorded above with its reason at each point: the three Execution Mode scenarios, both Hetzner-token-reach scenarios, both local `terraform` scenarios, the non-production write-token confinement, the "creatable" half of identical resource names, the "without moving or renaming" half of adding an environment, the approver's promotion discipline, the removed prod-project scenario, and the two rejected static checks (the `versions.tf` Execution Mode comment, and the token-on-disk sweep).

## Obsolete tests

The change carries MODIFIED and REMOVED deltas, so a search was made. It was bounded to `.github/tests/*.py` — the dispatched test-path glob — and to the scenario-to-test mapping in the archived `make-the-pipeline-environment-agnostic` change's own `test-plan.md`, which is the only prior mapping this repository holds. No unbounded search was made: this author has not read the implementation and holds no requirement-to-test index, and a wider sweep would be guesswork presented as a finding.

**One candidate, for human confirmation. It is not a deletion candidate.**

| Test | Superseded by | Evidence | What to do |
|---|---|---|---|
| `test_environment_agnostic_pipeline.TestTheWriteCredentialBoundaryIsStatedToAgents.test_the_conventions_file_states_that_apply_is_not_run_locally` | `iac-safety-hardening` MODIFIED *Write Credentials Confined to the Gated Pipeline*, scenario "An agent opening the repository is told the boundary" | Its docstring quotes the scenario as requiring `AGENTS.md` to state "that **production** changes reach Hetzner only through the gated pipeline". The delta rewrites that scenario to say "**infrastructure** changes". The quoted text is superseded; the assertion is not — it matches the fragments `"is never run locally"` and `"only through the gated"`, both of which survive, and the test was confirmed still passing against a generalised `AGENTS.md` in the probe above. | Correct the docstring's quotation when task 3.2 lands, so the citation names the requirement as it then stands. **Do not delete or weaken the assertion.** |

**No other bearing test was found.** Distinguishing the two readings that phrase can carry: for the workspace, backend and module-structure requirements, **no such test exists** — a grep of the whole suite for `versions.tf`, `cloud`, `workspace` and `infrastructure-prod` returns nothing, so those requirements were never covered rather than covered by something this search missed. For the remaining requirements, **none was found by this search**, which is the weaker statement and is meant as such.

## Unresolved project questions

Recorded here rather than asked, because a dispatched subagent has no channel to ask on. Each names the assumption taken and the tests that depend on it.

1. **Does `<environment>` in `infrastructure-<environment>` mean the directory name?** The delta states the form and never says what fills it. *Assumption:* the environment directory's own name — the only identifier this repository gives an environment that a static read can reach, and the one prod's committed `infrastructure-prod` is consistent with. *Depends on it:* `test_every_workspace_name_follows_the_per_environment_form`, `test_the_second_environment_names_its_own_workspace`.

2. **Is a shared volume name required or merely permitted?** The scenario says environments MAY name a resource identically; design.md Decision 4 and tasks.md 2.3 say staging DOES. *Assumption:* required, on the strength of `platform/docker-compose.yml`'s hardcoded `/mnt/main-data/...` paths, which the requirement's own prose names as the reason the shared name matters. *Depends on it:* `test_every_environment_that_declares_a_volume_names_it_identically`. If a future environment legitimately wants a different volume name, that test is where the decision surfaces — and the compose paths are what have to move with it.

3. **Should a record naming one environment be an offence whenever it names one, or only when it names one *and* generalises over none?** The requirement says the record "SHALL state the prohibition over every environment rather than naming one", while tasks.md 3.2 says to keep "prod's reviewer gate stated as prod's". *Assumption:* the second reading — a prohibition sentence naming an environment is an offence only if no phrase in it reaches the others. *Depends on it:* both tests in `TestTheWriteCredentialRecordCoversEveryEnvironment`. The consequence to be aware of when writing task 3.2: a sentence saying the prohibition holds for every environment *and* that prod is additionally reviewed passes; a sentence whose only subject is prod does not.

4. **How narrow should "describes an environment as anticipated" be?** No convention exists. *Assumption:* six literal phrases (`ANTICIPATION_MARKERS` in the module), each pairing an environment with non-existence, chosen narrow so a sentence anticipating something else about an environment that exists is not reported. *Depends on it:* `test_no_readme_sentence_calls_an_existing_environment_anticipated`.

Both convention files were read — `CLAUDE.md`, which imports `AGENTS.md`, and `AGENTS.md` itself. The suite's own idiom (SPECIFIED/DERIVED docstrings, predicates exercised against fixtures, sibling-helper imports rather than restated helpers, no spawned command) was taken from the five existing modules and is followed.

## What a green run of these tests does not establish

Nothing in the new module reads a repository setting, an HCP Terraform workspace setting, or the Hetzner Cloud API. Whether `infrastructure-staging` exists at all, whether its Execution Mode is Local, whether the `staging` GitHub Environment exists or requires a reviewer, which secrets it holds, and what staging's tokens can reach are all outside every test command this project has. They are confirmed by the operator's report against tasks 1.1–1.8 and by reading the actual pipeline runs against design.md Decision 9's list — not by this suite.
