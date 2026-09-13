# Test plan — deploy-the-platform-stack-per-environment

Derived from this change's delta specifications at commit `3d96cb0`, which is the commit holding the approved plan, by an author other than whoever implements it. Nothing in this pass reads the implementation of the behaviour under test: `.github/workflows/platform-deploy.yml` was not read, and every property below traces to a delta scenario, to this change's `design.md` or `tasks.md`, or to a committed file that is not that workflow.

**This file is not an artifact the OpenSpec schema knows about.** It does not appear among the context files `openspec instructions apply` lists, so it has to be read on purpose before implementing.

**This pass adds tests and never subtracts.** No existing test file was edited, deleted or disabled; no implementation was written. The obsolete list below is the input to somebody else's destructive action and every entry is a candidate for human confirmation, never a conclusion.

## What was written

One new module: `.github/tests/test_the_platform_stack_deploys_per_stack.py` (101 tests).

Run it with the project's third test command, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

    # this module alone
    python3 -m unittest discover --start-directory .github/tests \
        -p "test_the_platform_stack_deploys_per_stack.py"

    # one class or one test, individually selectable
    python3 -m unittest discover --start-directory .github/tests \
        -k TestPlatformDeployDiscoveryFailsClosed
    python3 -m unittest discover --start-directory .github/tests \
        -k test_no_job_declares_a_literal_github_environment

Run through `discover` in every form: it is discovery that puts `.github/tests` on `sys.path`, which is what makes the module's sibling imports resolve.

## Baseline

Full suite, taken before any test was written, at commit `3d96cb0` with a clean working tree:

    python3 -m unittest discover --start-directory .github/tests
    Ran 1022 tests in 26.3s — OK

Nothing failed beforehand, so every failure reported afterwards is attributable to this pass. After it:

    Ran 1123 tests in 27.2s — FAILED (failures=28)

All 28 failures are in the new module. No test outside it changed state.

## Which of the new assertions are red, and what each red establishes

The module's docstring carries this too, as `test_a_second_environment.py` does for its own.

**RED until the implementation lands (28 failures).** Split by what the failure establishes:

- **Target absent** — the 14 tests in `TestPlatformDeployDiscoveryFailsClosed`. The workflow has no discovery step, so the locator fails and the assertions inside were never exercised. This is the second failure state: it establishes the step's absence and nothing about whether the refusals are asserted correctly. Read them again once the step exists.
- **Target present, property absent** — the remaining 14. The committed declarations carry no opt-in field (4 tests), and the committed workflow declares a literal Environment, builds no discovered matrix, carries a workflow-level concurrency group and has no step reading the whole secret set (10 tests). These executed and reported the property's absence.

**GREEN from the moment they were written, and that is not an alarm.** `TestOneStacksKeyDoesNotReachAnotherStacksHost`, `TestTheRenderedEnvIsNeverCommitted`, `TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount` and one of `TestTheDiffIsPublishedOnceBeforeAnyGate`'s two tests. Their subject is a property of the committed tree this change deliberately does not alter — two hosts authorising different public halves, no committed `.env`, the tailnet join before the first SSH, the deploy credential confined to a job declaring an `environment:`, one credential-free job publishing the diff. Each is written over the discovered set, so it acquires a second subject the day a second stack opts in. A check whose target already carries the asserted property cannot fail, which is why every predicate in the module is also run over fixture material — see below.

**PART GREEN, PART RED.** `TestTheDiffIsPublishedOnceBeforeAnyGate.test_one_credential_free_job_publishes_the_diff_before_every_gate` passes today, but its "every deploy row waits for the diff" half reads an empty set of rows and says nothing until the matrix exists.

**VACUOUS until the implementation lands.** `TestAStackOptingInAuthorisesTheDeployOnItsHost` compares two committed files over the stacks that opt in, and none does. Its guard test is red rather than silent, which is what stops the comparison passing over an empty set.

## Fixture-driven discriminators

Every assertion in this module is a static read of a committed file, so a green run establishes nothing on its own. `TestTheseReadsDiscriminate` (62 tests) runs each predicate over material the module supplies, carrying the defect that predicate names, plus the conforming case so the predicate cannot be one that reports everything. All 62 pass, so every predicate was established to discriminate at authoring time rather than after the fact.

Covered predicates: `platform_opt_in`, `group_variables` (including the unknown-tag refusal), `deploy_authorisation_offences` (both directions), `stack_name_occurrences`, `gate_offences`, `ordering_offences`, `serialisation_offences`, `confinement_offences`, `diff_offences`, `secret_set_offences`, `disclosure_offences`, `rendered_secret_resolution`, `tailnet_ordering_offences`, `deploy_account_offences`, `shared_key_offences`, `committed_env_files`.

One discriminator caught a defect in this pass's own work before it was reported: the SSH matcher read `ssh-keyscan` as an SSH connection, so the deploy-account assertion failed the committed known-hosts step for a reason no requirement states. That was a broken test, not a finding about the workflow; it was repaired and the case kept as `test_a_known_hosts_step_is_not_read_as_a_connection`.

## Scenario coverage

35 scenarios across the two delta specs (24 in `iac-platform-deploy-pipeline`, 11 in `iac-cicd-pipeline`). Every one is accounted for below, exactly once.

Test identifiers are abbreviated: `NEW` is `test_the_platform_stack_deploys_per_stack`, and every name is selectable with `-k`.

### iac-platform-deploy-pipeline — ADDED: Each Stack's Deploy Attaches to the Environment Its Own Declaration Names

| Scenario | Covered by | Notes |
|---|---|---|
| A merge does not deploy to a reviewed stack immediately | `NEW.TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares.test_every_deploy_row_attaches_to_an_environment`, `.test_the_same_declared_field_gates_both_kinds_of_change_to_a_stack` | **Partial, and the limit is stated.** Whether an Environment pauses for a reviewer is a repository setting no static read reaches. What is asserted is the half the repository carries: the row attaches to the Environment the discovered declaration names. |
| Same approvers gate both kinds of change to one stack | `NEW.…test_the_same_declared_field_gates_both_kinds_of_change_to_a_stack` | Partial for the same reason: one declared field is what both mechanisms resolve from; the reviewer list is a setting. |
| An unreviewed stack deploys without an approval prompt | `NEW.…test_no_condition_distinguishes_one_stacks_deploy_from_anothers`, `NEW.TestThePlatformDeployNamesNoStack.test_the_platform_deploy_names_no_stack_environment_or_group` | Partial: what is asserted is that nothing in workflow text decides it, which is precisely the requirement's own "the workflow SHALL NOT distinguish them". |
| One stack's failed deploy does not withhold another's | `NEW.TestNoStacksDeployIsOrderedBehindAnother.test_one_stacks_failed_deploy_does_not_withhold_anothers` | Covers all three mechanisms design.md Decision 6 names: `fail-fast`, `max-parallel`, a `needs:` between rows. |

### iac-platform-deploy-pipeline — ADDED: The Platform Deploy Names No Stack

| Scenario | Covered by |
|---|---|
| A stack opting in needs no workflow edit | `NEW.TestThePlatformDeployNamesNoStack.test_the_platform_deploy_names_no_stack_environment_or_group`, `.test_there_is_a_name_to_look_for`; `NEW.TestPlatformDeployDiscoveryFailsClosed.test_discovery_emits_every_stack_that_opts_in` |
| A stack that has not opted in is excluded and named | `NEW.TestPlatformDeployDiscoveryFailsClosed.test_a_stack_that_has_not_opted_in_is_excluded_and_named` (two sub-tests: declaring `false`, declaring nothing) |
| No stack opting in fails the workflow | `NEW.TestPlatformDeployDiscoveryFailsClosed.test_no_stack_opting_in_fails_the_workflow`; `NEW.TestEveryStackThatReceivesThePlatformStackDeclaresIt.test_at_least_one_stack_opts_in` (the committed tree's half) |
| A deploy requested for an unknown stack is refused | `NEW.TestPlatformDeployDiscoveryFailsClosed.test_a_dispatch_naming_an_unknown_stack_is_refused`, `.test_a_dispatch_naming_a_stack_that_did_not_opt_in_is_refused` |

The requirement's fail-closed SHALL text beyond those four scenarios is covered by `.test_a_stack_directory_carrying_no_declaration_is_refused`, `.test_a_stack_opting_in_without_an_environment_is_refused` and `.test_an_opt_in_value_that_is_neither_true_nor_false_is_refused`; its "reached by their own fixed names, rather than by any name derived from or mapped to the stack" by `NEW.TestThePlatformDeployNamesNoStack.test_no_matrix_row_carries_a_secret_name` and `NEW.TestPlatformDeployDiscoveryFailsClosed.test_the_emitted_matrix_carries_no_secret_name`.

### iac-platform-deploy-pipeline — ADDED: An Incomplete Per-Stack Secret Set Is Reported by Name

| Scenario | Covered by |
|---|---|
| A stack opted in before its secrets exist fails by name | `NEW.TestTheSecretSetIsEstablishedBeforeAnythingIsWritten.test_the_whole_set_is_established_before_anything_is_joined_or_written`, `.test_the_set_is_every_secret_backed_value_the_deploy_consumes` |
| A partially entered secret set fails rather than deploying | same two — the set is computed from the committed `platform/.env.example`, so a value omitted from the check is reported |
| An absent credential secret fails the deploy rather than starting the service | same two — the administrative credential is one of the computed set, and the ordering assertion places the check before the render |
| The refusal names what is missing without disclosing what is present | `NEW.…test_the_refusal_discloses_no_value` |

**Stated limit, applying to all four.** That the refusal *fires* cannot be asserted statically: whether a secret resolves to an empty string is a repository setting and the step's exit status is a runtime fact. What is asserted is the shape the repository carries — one step reads every name, it runs before anything is joined, rendered or connected to, and its message can carry no value.

### iac-platform-deploy-pipeline — MODIFIED: Reviewer Sees the Exact Diff Before Approving

| Scenario | Covered by |
|---|---|
| Approver sees the diff without leaving the workflow run | `NEW.TestTheDiffIsPublishedOnceBeforeAnyGate.test_one_credential_free_job_publishes_the_diff_before_every_gate` |
| Diff visibility does not depend on pull request review having occurred | `NEW.…test_diff_visibility_does_not_depend_on_a_review_having_occurred` |

The MODIFIED sentence "One such job SHALL serve every stack" is covered by the same first test, which reports a second publishing job and a publishing job sitting in a matrix row.

### iac-platform-deploy-pipeline — MODIFIED: Deploy Job Reaches the Host Over a Private Tailnet

| Scenario | Covered by |
|---|---|
| Deploy job joins the tailnet before SSH | `NEW.TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount.test_every_connecting_job_joins_the_tailnet_before_its_first_ssh` — GREEN today |
| Tailnet join credential is confined to the gated job | `NEW.…test_the_tailnet_and_deploy_credentials_are_confined_to_a_gated_job` — GREEN today |

### iac-platform-deploy-pipeline — MODIFIED: Deploy Credential Confined to the Gated Job

| Scenario | Covered by |
|---|---|
| Deploy key is inaccessible before approval | `NEW.…test_the_tailnet_and_deploy_credentials_are_confined_to_a_gated_job` — partial: attachment is readable, the pause is a setting |
| A job attached to no Environment can read no stack's key | same test — this is the half a static read covers fully |
| One stack's key does not reach another stack's host | `NEW.TestOneStacksKeyDoesNotReachAnotherStacksHost.test_no_two_hosts_authorise_the_same_platform_deploy_key` — the public halves are committed; the private halves are settings |

### iac-platform-deploy-pipeline — MODIFIED: Platform Secrets Rendered from CI at Deploy Time

| Scenario | Covered by |
|---|---|
| Rendered .env never enters version control | `NEW.TestTheRenderedEnvIsNeverCommitted.test_no_env_file_is_committed_under_the_stack_definition` (+ `.test_the_ignore_rules_keep_a_rendered_env_out`, DERIVED) |
| Deploy job authenticates as the provisioned deploy account | `NEW.TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount.test_every_connection_authenticates_as_the_provisioned_deploy_account` |
| Two stacks render two different sets of values | `NEW.TestThePlatformDeployNamesNoStack.test_no_job_declares_a_literal_github_environment`, `.test_no_matrix_row_carries_a_secret_name` — **partial, and the remainder is uncovered by design**: which value each GitHub Environment holds is a repository setting. What is asserted is the mechanism that makes two sets possible — a fixed secret name resolved against a per-row Environment, with nothing in workflow text mapping a stack to a secret. The requirement's own "nothing in the repository can verify it" about alert targets holds here too. |

### iac-platform-deploy-pipeline — MODIFIED: Serialized Deploys

| Scenario | Covered by |
|---|---|
| Two merges in quick succession deploy in order | `NEW.TestEachStacksDeployIsSerialisedOnItsOwn.test_two_merges_queue_per_stack_and_one_stack_does_not_hold_another` |
| One stack's queued deploy does not hold another's | same test — it reports a workflow-level group and a group naming no matrix value |

### iac-platform-deploy-pipeline — REMOVED (as a rename)

The removed requirement carries no `#### Scenario:` block of its own in the delta, so it contributes nothing to the count of 35. Recorded here all the same: **no test is owed for it.** Its obligation is carried through by *Each Stack's Deploy Attaches to the Environment Its Own Declaration Names*, whose four scenarios are covered above; removed behaviour is not to be tested. The tests that assert the removed requirement's literal are in the obsolete list.

### iac-cicd-pipeline — MODIFIED: Each Stack Declares Its Own Pipeline Configuration

Two scenarios are new in this delta and are covered here. Nine predate it, are unchanged by it, and are already covered by sibling modules — recorded as covered-by-existing rather than restated, because restating an assertion in a second module makes two places to keep current and the sibling's version is the one the requirement's other consumers read.

| Scenario | Covered by |
|---|---|
| A stack declaring nothing about the platform stack does not receive it | **New.** `NEW.TestPlatformDeployDiscoveryFailsClosed.test_a_stack_that_has_not_opted_in_is_excluded_and_named` (sub-test `declaring nothing`); `NEW.TestTheseReadsDiscriminate.test_an_absent_opt_in_reads_as_not_deployed_to` |
| A stack opting in without authorising the deploy on its host is refused | **New.** `NEW.TestAStackOptingInAuthorisesTheDeployOnItsHost.test_every_opted_in_stacks_host_authorises_the_platform_deploy_key`, `.test_there_is_an_opt_in_to_check`, and four discriminators that hand the cross-check a disagreeing pair |
| A host authorising the deploy key before the pipeline is pointed at it is accepted | **New in effect** — it states the converse the check must *not* require. `NEW.TestAStackOptingInAuthorisesTheDeployOnItsHost.test_a_host_prepared_before_its_deploy_path_is_not_reported`, `NEW.TestTheseReadsDiscriminate.test_the_implication_holds_in_one_direction_only` |
| A new stack needs no workflow edit | Covered by existing `test_environment_agnostic_pipeline.TestNoWorkflowNamesAnEnvironment` over the three Terraform workflows, **extended here to the fourth**: `NEW.TestThePlatformDeployNamesNoStack.test_the_platform_deploy_names_no_stack_environment_or_group`. Widening that module's own tuple is tasks.md 3.2 and is the implementer's; the new module reaches `platform-deploy.yml` whether or not that widening happens. |
| A converge reads its Ansible group from the declaration, not from the stack's name | Covered by existing `test_a_stack_and_its_environment_are_named_separately.TestEveryStackDeclaresTheGroupItConverges` and `TestHostConvergeDiscoveryReadsTheDeclaredGroup`. Unchanged by this delta. |
| Two stacks declaring the same read-only secret are refused | Covered by existing `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret` |
| Two stacks declaring the same GitHub Environment are refused | Covered by existing `test_environment_agnostic_pipeline` (same class) — and it is the *other half* of the guard this change's design.md names, the half that replaces the retired literal comparison |
| Two stacks declaring the same Ansible group are accepted | Covered by existing `test_a_stack_and_its_environment_are_named_separately` |
| A declaration naming the write token's own name is refused | Covered by existing `test_host_converge_workflow.TestNoDeclarationNamesTheWriteTokensOwnName` |
| A stack missing its declaration fails the pipeline | Covered by existing `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed`; the platform deploy's own discovery is covered here by `NEW.TestPlatformDeployDiscoveryFailsClosed.test_a_stack_directory_carrying_no_declaration_is_refused` |
| Discovery finding no stack fails rather than reporting success | Covered by existing `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed`; the platform deploy's own empty-set refusal is `NEW.…test_no_stack_opting_in_fails_the_workflow` |

**Count check: 24 + 11 = 35 scenarios; 35 accounted for.**

## Scenarios and obligations deliberately left uncovered

None of the 35 scenarios is left wholly uncovered. Six are covered in part, and what is left out is the same class in every case — a repository setting, which this suite may not read because it makes no network call. Recorded so the absence of an assertion is distinguishable from the absence of the thought:

- **Whether an Environment requires a reviewer**, and therefore whether a given stack's deploy pauses. Affects "A merge does not deploy to a reviewed stack immediately", "Same approvers gate both kinds of change to one stack", "An unreviewed stack deploys without an approval prompt", "Deploy key is inaccessible before approval".
- **Which secrets an Environment holds, and what value each holds.** Affects "Two stacks render two different sets of values" and every scenario of *An Incomplete Per-Stack Secret Set Is Reported by Name* — the refusal's shape is asserted, its firing is not.
- **Whether each stack's alert-delivery target is its own.** The requirement itself says "nothing in the repository can verify it". No test is owed; `tasks.md` 5.1 records the backlog entry that would make it verifiable.
- **That the deploy actually succeeds against staging.** That is `tasks.md` 6.2–6.5, the operator's observation, and the Monday prune in 6.5 is the change's real confirmation. No static test can stand in for it.

## Obsolete tests — candidates for human confirmation

Four assertions across three modules rest on a proposition this change retires: that `platform-deploy.yml` declares **exactly one literal deployment Environment**, equal to the production stack's declared `github_environment`. After tasks.md 2.5 the value read is the string `${{ matrix.stack.github_environment }}`, so each goes red.

**Nothing here was edited, deleted or disabled by this pass.** Each entry is a candidate for a human to confirm before acting, and each of the three is already described in `tasks.md` (3.1, 3.1a, 3.1b) — which is the confirmation that the change's author intended it, not a substitute for reading the test.

1. **`test_the_external_service_names_are_retired.TestTheDeployGateNamesTheEnvironmentAStackDeclares.test_the_deploy_gate_and_a_stacks_declaration_name_one_environment`**
   - Superseded by: *The Platform Deploy Names No Stack* (ADDED) and *Each Stack's Deploy Attaches to the Environment Its Own Declaration Names* (ADDED).
   - Evidence: its reader `gate_disagreements(gated, declared)` returns an offence unless `sorted(set(gated))` is exactly one name, and unless some stack declares that name — `"platform-deploy.yml declares {names} deployment environment(s); the requirement names one"`. The delta replaces "one Environment" with "the Environment each row's own declaration names".
   - Replacement proposition, already asserted additively: `test_the_platform_stack_deploys_per_stack.TestThePlatformDeployNamesNoStack.test_no_job_declares_a_literal_github_environment`.
   - Keep its discriminator class, which feeds the reader a half-renamed pair: the hazard it describes (GitHub creating an unprotected Environment for a name no stack declares) is relocated by this change, not retired.

2. **`test_the_github_environments_are_named_for_their_stacks.TestTheDeployGateNamesTheProductionStacksEnvironment`** — both of its tests:
   - `.test_the_deploy_gate_names_the_production_stacks_declared_environment`
   - `.test_the_environment_both_are_named_for_is_the_one_the_requirement_names`
   - Superseded by: the same two ADDED requirements.
   - Evidence: the first calls `deploy_gate_disagreements(platform_deploy_gated_environments(), axes, PRODUCTION_DIRECTORY)`; the second asserts `sorted(set(platform_deploy_gated_environments())) == [PRODUCTION_GITHUB_ENVIRONMENT]`. Both read the literal out of the workflow, and both quote the requirement this change removes.
   - Its class and method docstrings also cite the removed requirement **by name**, which `tasks.md` 3.3 lists as one of the three files needing a citation repair before archive.
   - Keep that module's fixture-driven discriminators for the same reason as above.

3. **`test_ci_configuration.TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment`, and the module constant `GATED_DEPLOY_ENVIRONMENT` it reads** (`test_ci_configuration.py:6611`).
   - Superseded by: *Each Stack's Deploy Attaches to the Environment Its Own Declaration Names*.
   - Evidence: it asserts exactly one job declares `environment: main-production`; after 2.5 zero do.
   - **It carries a live obligation of its own and SHALL NOT simply be deleted.** It traces to *Automated Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`) and its scenario that an automatically proposed image bump is subject to the same gated deploy approval. What keeps that true afterwards is that *every* deploy row declares an `environment:` resolved from discovery — asserted additively by `test_the_platform_stack_deploys_per_stack.TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares.test_every_deploy_row_attaches_to_an_environment`, whose docstring names that requirement so the trace is not lost.

**Bound of this search, stated so the list is not read as exhaustive.** The search ran over `.github/tests/*.py` — the dispatched test-path glob — and nowhere else, looking for reads of the literal `main-production` out of `platform-deploy.yml`, reads of `platform_deploy_gated_environments()`, and reads of `GATED_DEPLOY_ENVIRONMENT`. No earlier `test-plan.md` was supplied for this change, so no scenario-to-test mapping was available to search from. The three entries above match what `tasks.md` independently identified, which is corroboration rather than proof: **a bearing test outside `.github/tests/*.py`, or one bearing on a superseded property by a route none of those three greps reaches, would not have been found by this search.**

## Unresolved project questions

Each was recorded rather than resolved silently, with the assumption taken and the tests that depend on it. All three arise because the deltas fix an obligation and leave a spelling to the implementer; the module resolves each by shape where it can, and names a fallback where it cannot.

1. **The opt-in field's name.** The requirement says the declaration states "whether the shared platform stack is deployed to it" and fixes no field name; `tasks.md` 1.1 calls it `deploys_platform`.
   - *Assumption taken*: resolved by hint — the one declaration key whose normalised name carries `platform` — so any spelling the implementer chooses is followed. Where the committed declarations carry no such key at all (their state until this change lands), the discovery **fixtures** fall back to the literal `deploys_platform`, because a fixture cannot express an opt-in with no name to use.
   - *Tests depending on it*: every test in `TestEveryStackThatReceivesThePlatformStackDeclaresIt` and `TestPlatformDeployDiscoveryFailsClosed`. If the implementer chooses a different spelling, the fixtures follow it automatically the moment one committed declaration carries it.

2. **The environment variable the dispatch input arrives under inside the discovery body.** Nothing in the deltas fixes it.
   - *Assumption taken*: resolved from the discovery step's own `env:` block — the key whose value references `inputs.stack` — following `test_host_converge_workflow`'s established shape.
   - *Tests depending on it*: the four dispatch tests in `TestPlatformDeployDiscoveryFailsClosed`. A discovery step taking the input some other way fails those tests with a message saying so rather than with a wrong answer.

3. **The two secrets that are not `.env` values** — the one naming the host and the one holding the key. The requirement names both as members of the set and fixes neither spelling.
   - *Assumption taken*: `PLATFORM_DEPLOY_HOST` and `PLATFORM_DEPLOY_SSH_KEY`, read from the committed workflow, which already reads both, and from `tasks.md` 2.6. The module asserts the workflow references them rather than assuming it; the seven `.env`-backed names are **not** assumed — they are computed from `platform/.env.example` and matched by suffix to the secrets the workflow actually reads, so a renamed secret is reported rather than silently missed.
   - *Tests depending on it*: `TestTheSecretSetIsEstablishedBeforeAnythingIsWritten` (all three).

A fourth question was resolved rather than assumed, and is recorded because the resolution is visible in the module: **whether to import `_AnsibleTolerantLoader` from `ansible/scripts/select_molecule_roles.py` or restate it.** It is restated. `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` admits the standard library, the pinned `yaml`, and a sibling of `.github/tests/` — `ansible/scripts/` is none of the three, so an import would fail that audit, and reaching the module by a route that audit does not read would be evading a check rather than satisfying it. `design.md` Decision 4 names both routes as acceptable. The copy registers `!vault` and `!unsafe` **by name** and never a catch-all, and that refusal is asserted here rather than inherited: `TestTheseReadsDiscriminate.test_an_unknown_tag_refuses_rather_than_yielding_an_empty_document`.

## Constraints this module was written under

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` reads every module in `.github/tests/`, and it passes on this one: standard library, `yaml`, sibling helpers, and `bash` as the only spawned command. `find` and `jq` are needed only by `TestPlatformDeployDiscoveryFailsClosed`, which skips naming them where they are absent and **fails instead under `CI`**, through the suite's own `require_external_tools`.

Helpers are imported from `test_ci_configuration.py` (`PLATFORM_DEPLOY`, `ROOT`, `jobs`, `load_yaml`, `read_text`, `require_external_tools`, `secrets_referenced_by`, `step_label`, `step_text`, `steps`, `uncommented`) and `test_environment_agnostic_pipeline.py` (`ACTIONS_EXPRESSION`, `DeclarationTreeFixtureMixin`, `declared_environment`, `environment_declarations`, `environment_directories`, `invocation_lines`, `matrix_source_jobs`, `needs_of`, `run_snippet`) rather than restated.

## What the implementation step must make pass

Run the suite and expect the 28 failures above to go green. In dependency order:

1. The opt-in field on both stacks' `pipeline.yml` (tasks 1.1–1.3) closes `TestEveryStackThatReceivesThePlatformStackDeclaresIt` and un-vacuums `TestAStackOptingInAuthorisesTheDeployOnItsHost`.
2. The `discover` job's body (task 2.3) closes all 14 tests in `TestPlatformDeployDiscoveryFailsClosed` — and its refusals are what those tests actually read, so a body that discovers without refusing will still be red.
3. The matrix deploy job, its per-row `environment:`, its per-stack `concurrency` and the removal of the workflow-level group (task 2.5) close `TestThePlatformDeployNamesNoStack`, `TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares`, `TestNoStacksDeployIsOrderedBehindAnother` and `TestEachStacksDeployIsSerialisedOnItsOwn`.
4. The secret-set refusal step (task 2.6) closes `TestTheSecretSetIsEstablishedBeforeAnythingIsWritten`.

Two things the implementer should read before starting, because a conforming implementation can still fail these for a reason the tests state rather than imply:

- The discovery body must **take nothing from the event inside the step** (no `${{ }}` in the `run:`), or `TestPlatformDeployDiscoveryFailsClosed`'s locator finds no discovery step at all and the class stays red however well the discovery works. That is tasks.md 2.3's own obligation, restated here because it is the one implementation choice that makes 14 tests unrunnable rather than red.
- The secret-set step must bring its values in through the step's own `env:` block rather than interpolating `${{ secrets.* }}` into the shell body; `test_the_refusal_discloses_no_value` reports the interpolation, for the reason tasks.md 2.6 gives about a multi-line private key parsed as shell.
