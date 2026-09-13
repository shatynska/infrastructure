# Test plan — `rename-the-github-environments`

Written by an author other than whoever implements this change, from the delta specifications alone, before any implementation of it existed. No implementation source was read: `terraform/stacks/*/pipeline.yml` and `.github/workflows/platform-deploy.yml` were read as the *declarations the deltas describe*, which the delta specs name explicitly ("the Environment that stack's own committed pipeline declaration names"), and the existing `.github/tests` modules were read because this pass may only add and had to establish what it must not duplicate.

This file is **not an artifact the OpenSpec schema knows about**. It will not appear among `openspec instructions apply`'s context files and has to be opened on purpose.

## Baseline

**Full suite, taken before anything was written.** `python3 -m unittest discover --start-directory .github/tests`, run from the repository root: **967 tests, OK**, 25.2s. Nothing was already failing, so every failure reported below is attributable to this pass.

After this pass: **1006 tests, 7 failures**, 25.2s. All 967 pre-existing tests still pass. The 7 failures are the new assertions that are red by design until the implementation lands; they are named in *Red at authoring*, below.

## Which pull request each test rides in

`tasks.md` 2.2 requires this stated with its mechanic, and the mechanic is: both pull requests come off one branch in sequence and both must be green before either merges, so a test asserting production's new Environment name, committed before the staging pull request merges, turns the **staging** pull request's required check red — and the remedy a red canary invites is deleting or weakening the test, which this project's rules forbid outright.

The split is therefore a split of **files**, not of commits within one file, so that it is mechanical rather than a manual bisection of a module:

| File | Pull request | Why it cannot ride in the other one |
|---|---|---|
| `.github/tests/test_the_staging_github_environment_moves_first.py` | **First — staging's flip, section 4.** Commit it alongside task 4.1. | Asserts only `main-staging`'s declaration. Green once 4.1 lands; says nothing about production. |
| `.github/tests/test_the_github_environments_are_named_for_their_stacks.py` | **Second — production's half, section 7.** Commit it only after the staging pull request has merged. | Every assertion in it is about production's name, about the deploy gate that names it, or about a property true only once **both** stacks have flipped. |

The second file imports three readers from the first (`declared_axes`, `off_the_stack_axis`, `axes_that_coincide`), which is the suite's established sibling-import idiom and which makes the ordering a hard dependency rather than a convention: the second file cannot be committed before the first exists.

**One test in the second file is green from the moment it is committed and must not be read as slack.** `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares` passes both before and after this change; what it reports is the *interval*, and both ends of that interval (task 7.1's declaration flip and task 7.6's runbook correction) land in the same pull request. Its effect is to refuse to let that pull request merge with the declaration moved and the document not.

## The split was violated once, and repaired before it cost anything

**Recorded because the mechanism this file describes is exactly what caught it.** Both modules were committed together in `2887795`, although the table above says the production module rides the *second* pull request and must be committed only after the first has merged. The consequence was latent for several commits: the branch carried five assertions about production's Environment name that cannot pass until section 7 lands, so the canary pull request would have opened with a red required check.

It surfaced at the moment of opening that pull request, on a routine re-read of what the branch actually contained — not from a review round and not from a failing check, because no check had yet run on a pull request. The module was removed from the branch with the suite going 1006 → 980 and all 980 passing, and `tasks.md` 7.0 restores it from `2887795` as the first act of section 7, before any of that section's edits, so the five run red and then go green rather than appearing to have passed all along.

**The wider point is the one this file already makes.** A red canary invites exactly one remedy — weakening or deleting the test that is red — and the split exists so that nobody is ever offered that choice. Committing both files at once quietly reintroduced the choice while every artifact still said it had been designed away.

## What was written

39 tests across two new modules. Nothing existing was edited, deleted or disabled.

### `test_the_staging_github_environment_moves_first.py` — 13 tests

| Test | Classification |
|---|---|
| `TestTheStagingStackDeclaresTheEnvironmentNamedForIt.test_the_staging_stack_declares_the_environment_named_for_it` | DERIVED |
| `TestTheStagingStackDeclaresTheEnvironmentNamedForIt.test_the_staging_stacks_two_axes_no_longer_spell_one_word` | DERIVED |
| `TestTheseReadsDiscriminate` — 11 tests | fixture-driven discriminators (see below) |

`main-staging`'s Environment name is **DERIVED, not SPECIFIED**, and the distinction is load-bearing: **no scenario in any of the three delta specs names `main-staging` as a GitHub Environment.** The `iac-cicd-pipeline` scenarios that mention the staging stack name its *directory* (`terraform/stacks/main-staging/`), which this change does not move; every scenario that names an Environment names `main-production`. The value comes from `proposal.md`, `tasks.md` 4.1 and `docs/naming-conventions.md`'s stack table.

### `test_the_github_environments_are_named_for_their_stacks.py` — 26 tests

| Test | Classification |
|---|---|
| `TestTheProductionStackDeclaresTheEnvironmentNamedForIt.test_the_production_stack_declares_the_environment_named_for_it` | SPECIFIED |
| `TestTheProductionStackDeclaresTheEnvironmentNamedForIt.test_the_production_stacks_two_axes_no_longer_spell_one_word` | DERIVED |
| `TestEveryStacksGithubEnvironmentIsOnTheStackAxis.test_every_stack_declares_the_github_environment_named_for_it` | SPECIFIED for the relation, DERIVED for its extension to every stack |
| `TestEveryStacksGithubEnvironmentIsOnTheStackAxis.test_no_stacks_two_axes_spell_one_word` | DERIVED |
| `TestTheDeployGateNamesTheProductionStacksEnvironment.test_the_deploy_gate_names_the_production_stacks_declared_environment` | SPECIFIED |
| `TestTheDeployGateNamesTheProductionStacksEnvironment.test_the_environment_both_are_named_for_is_the_one_the_requirement_names` | SPECIFIED |
| `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares.test_the_sweep_reaches_the_runbook` | DERIVED |
| `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares.test_the_sweep_finds_the_commands_it_exists_to_read` | DERIVED |
| `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares.test_no_documented_secret_write_names_an_undeclared_environment` | DERIVED |
| `TestTheseReadsDiscriminate` — 17 tests | fixture-driven discriminators (see below) |

### Why these are not a restatement of the three literals this change moves

`PROD_GITHUB_ENVIRONMENT`, `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT` and `GATED_DEPLOY_ENVIRONMENT` each compare a committed declaration against a constant in the same module — and both sides are moved by the implementing author, in the same commit. A green result there establishes that one value was typed twice. What the new tests add:

- the literal the **requirement** states, asserted by an author who has not seen the implementation;
- the **relation** the naming scheme states — a stack's GitHub Environment is the stack's own directory name — which no constant can satisfy by being edited alongside its own subject, because the directory name is not something this change moves;
- **which stack** the platform deploy shares its Environment with. `TestTheDeployGateNamesTheEnvironmentAStackDeclares` in `test_the_external_service_names_are_retired.py` asserts the gate and *some* stack's declaration name one Environment, deliberately without naming either side. It is satisfied by a deploy gated on the **staging** stack's Environment — an ungated production deploy, since staging's Environment requires no reviewer by design.

### Red at authoring, and on which property

Every static-read check that is red at authoring goes green as the change lands, and that transition is what establishes it discriminates on real content. Recorded here so the later green can be read against it:

| Test | Red on |
|---|---|
| `…moves_first.…test_the_staging_stack_declares_the_environment_named_for_it` | `main-staging` declares `staging` |
| `…moves_first.…test_the_staging_stacks_two_axes_no_longer_spell_one_word` | `main-staging`'s two axes both spell `staging` |
| `…named_for_their_stacks.…test_the_production_stack_declares_the_environment_named_for_it` | `main-production` declares `production` |
| `…named_for_their_stacks.…test_the_production_stacks_two_axes_no_longer_spell_one_word` | `main-production`'s two axes both spell `production` |
| `…named_for_their_stacks.…test_every_stack_declares_the_github_environment_named_for_it` | both stacks |
| `…named_for_their_stacks.…test_no_stacks_two_axes_spell_one_word` | both stacks |
| `…named_for_their_stacks.…test_the_environment_both_are_named_for_is_the_one_the_requirement_names` | `platform-deploy.yml` gates on `production` |

Two committed-tree assertions are **green at authoring** and are answered by their fixtures rather than by investigation, per the static-read rule: `…test_the_deploy_gate_names_the_production_stacks_declared_environment` (both sides currently say `production`) and the whole of `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares`.

### The fixture obligation

Every assertion in both modules is a **static read of a committed file**, so a green run establishes nothing on its own. Each reader is split into a thin tree-reader and a pure finder that takes what it examines as an argument, and 28 of the 39 tests are fixture-driven discriminators that hand a finder material the test itself supplies — a mapping, a string corpus, or a scratch tree written into a temporary directory. **Every discriminator was written and executed in this pass**; none is deferred and none was unrunnable here. Both directions are exercised for every finder: material built to falsify it, and clean material that would expose a finder reporting everything.

## Scenario accounting

31 `#### Scenario:` blocks across 8 MODIFIED requirements in 3 delta specs. All 31 accounted for; **2 covered, 29 uncovered with reason.**

The shape of this change is why that ratio is what it is, and it is not a shortfall. **The behaviour of every one of these 31 scenarios is unchanged by this change.** What each delta moves is the Environment's *name* in the requirement's prose. So for each scenario the question is only: does its delta-new content — the name `main-production` — appear somewhere a static read can reach, and is it already read?

### `iac-cicd-pipeline` / Gated Production Apply Applies the Reviewed Plan (11 scenarios)

| Scenario | Accounted for |
|---|---|
| Merge does not apply immediately | **Covered**, for the half that is a static read, by `…named_for_their_stacks.TestTheProductionStackDeclaresTheEnvironmentNamedForIt.test_the_production_stack_declares_the_environment_named_for_it`. What the test reads is the committed declaration that decides which Environment the apply job attaches to. **That the job pauses, and that a required reviewer approves, is not covered**: a protection rule is a repository setting, the requirement says so itself, and `tasks.md` 8.1 makes it an operator observation. |
| A merge affecting one environment raises no other environment's approval | Uncovered. Names the stack *directories*, which this change does not move; the path-filter behaviour is unchanged and already read elsewhere in the suite. Nothing this change alters. |
| A shared module change reaches every environment | Uncovered. Names no Environment. Unchanged by this change. |
| A plan its own gate refused is not applied | Uncovered. Names no Environment. Unchanged by this change. |
| One environment's failed plan does not block another's apply | Uncovered. Names no Environment. Unchanged by this change. |
| An unresolvable set of planned environments fails the run | Uncovered. Names no Environment. Unchanged by this change. |
| Reviewer sees the exact diff before approving | Uncovered. Names no Environment. Unchanged by this change. |
| Applied changes match the approved plan | Uncovered. Names no Environment. Unchanged by this change. |
| Apply credentials are inaccessible before approval | Uncovered. Which secrets an Environment holds, and when a pending job can read them, is a repository setting. `tasks.md` 6.3 and 8.1 make it an operator observation. |
| An unresolvable set of affected environments fails the run | Uncovered. Names no Environment. Unchanged by this change. |
| A merge that cannot change infrastructure raises no approval request | Uncovered. Names no Environment. Unchanged by this change. |

### `iac-cicd-pipeline` / Scheduled Workflows Report Their Own Liveness (8 scenarios)

All eight uncovered, one reason: **no scenario in this requirement names an Environment at all.** The delta's edit is confined to the supporting paragraph "Secrets on the `main-production` Environment are readable only by a job that declares that Environment", which explains *why* the liveness credential is repository-scoped. That the reporting job declares no `environment:` and reads a repository-scoped secret is already asserted in this suite and is unchanged by this change; restating it here would add a second assertion of a proposition this change does not touch.

Scenarios: *A scheduled run that fails is reported as a failure*; *A workflow that stops running at all is detected*; *A run in which a conditional job is skipped reports success*; *A failure in an early job is still reported*; *A cancelled run raises no alarm of its own*; *A scheduled workflow added without a report fails the pull request*; *The report needs no human approval*; *The routine alarm does not consume the last-resort one*.

### `iac-platform-deploy-pipeline` (10 scenarios)

| Scenario | Accounted for |
|---|---|
| PR with invalid Compose syntax fails validation | Uncovered. Names no Environment; the requirement's edit is to the prose forbidding the validation job to declare one, and that the job declares none is already asserted and unchanged. |
| Validation requires no deploy secret | Uncovered. Same reason. |
| Pull request touching no platform file remains mergeable | Uncovered. Names no Environment. Unchanged by this change. |
| Merge does not deploy immediately | **Covered**, for the half that is a static read, by `…named_for_their_stacks.TestTheDeployGateNamesTheProductionStacksEnvironment.test_the_environment_both_are_named_for_is_the_one_the_requirement_names`. That the deploy job *pauses* for a reviewer is a protection rule; `tasks.md` 8.3 makes it an operator observation. |
| Same approvers gate both kinds of production change | **Covered**, for the half that is a static read, by `…TestTheDeployGateNamesTheProductionStacksEnvironment.test_the_deploy_gate_names_the_production_stacks_declared_environment` — the deploy's `environment:` literal and the production stack's own declaration name one Environment. **That the approvers are the same people is not covered**: a required-reviewer list is a repository setting. |
| Approver sees the diff without leaving the workflow run | Uncovered. The diff job's running under no `environment:` is already asserted and unchanged; what the run's summary displays at approval time is a run, not a file. |
| Diff visibility does not depend on pull request review having occurred | Uncovered. A property of a run. |
| Deploy job joins the tailnet before SSH | Uncovered. Names no Environment; a property of a run. |
| Tailnet join credential is confined to the gated job | Uncovered. Which Environment holds `TAILSCALE_OAUTH_SECRET`, and when a pending job can read it, is a repository setting. `tasks.md` 3.2, 6.3 and 8.3 make it an operator observation. |
| Deploy key is inaccessible before approval | Uncovered. Same reason; `tasks.md` 8.3 is the observation, and it is the only thing that exercises `PLATFORM_DEPLOY_SSH_KEY` at all. |

### `iac-state-management` (2 scenarios)

| Scenario | Accounted for |
|---|---|
| HCP token cannot reach real infrastructure on its own | Uncovered. Names no Environment, and asserts what a compromised job *cannot do* — not reachable by any test this suite may run. |
| The split mechanism remains wired for a future upgrade | Uncovered. Names no Environment. The delta's edit is to the requirement's own sentence, which now says the Environment-scoped copy of `TF_API_TOKEN` lives on `main-production`. **That a secret exists under a given Environment is unreachable by any static read**, and this is the one secret whose omission fails silently — an Environment missing it falls back to the repository-scoped copy of the same name. `tasks.md` 6.3 and 6.4 are what stand in its place, and `design.md` names this as the wrinkle that survives the good news. |

## What could not be placed, and why

Stated plainly rather than substituted for. **No test in this repository can establish anything about a GitHub deployment Environment**: not that `main-production` or `main-staging` exists, not that either holds a secret, not that `main-production` carries a required reviewer, not that `main-staging` carries none, and not that `production` and `staging` were deleted. Reaching any of them is a network call, and `.github/tests` may not make one — a prohibition that suite asserts of itself, in `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`.

That is not a limitation of this pass's effort. It is the change's own shape: three of the four things it touches are repository settings, and `design.md` says so in its first sentence. **The verification that matters is the operator-observation sequence in `tasks.md` sections 4, 8 and 9**, and a green suite is evidence that the committed declarations were moved — never that the Environments they now name are there to attach to.

Nothing weaker was written in place of any of them. In particular, no test asserts "an Environment name was typed somewhere" as a stand-in for "the Environment is gated": the change's own `design.md` records a predecessor's mistake of exactly that shape, and a probe reaching the wrong code path is worse than no probe because it is reported as a measurement.

## Deliberately untested

**A tree-wide sweep for the retired Environment names `production` and `staging`.** Considered, and declined for the reason a predecessor author already recorded in `test_the_external_service_names_are_retired.py`: those two words are also the **Ansible group names**, which this change must not move, and a sweep for either reports every correct use of the environment axis. `tasks.md` 5.1 lists nine needles and triages every hit by hand, and 5.3 names three sites that legitimately keep the old spelling — two describing a *different* repository's own `production` Environment, one a dated record. A sweep carrying three whole-path exemptions plus two prefix exemptions would read as coverage while holding open exactly the holes the manual triage exists to inspect.

What **was** taken from that surface is the one needle with no false positives: `gh secret set --env <name>`, which takes a deployment Environment and never an Ansible group, a `group_vars` file or a `--vault-id` label. That is `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares`, and it is narrow on purpose.

**The three identifier sets that collapse at staging's flip** (`tasks.md` 4.2). Not asserted, and the reason is that only one of the three is reachable: `environment_identifiers()` in `test_a_second_environment.py` is a module-level function another module already imports, while the other two are set literals built inside a test method's body and readable only by parsing Python source. A check that asserted one of three while reading as though it covered the collapse would be the weaker-stand-in this pass is forbidden to write. It stays `tasks.md` 4.2's sweep, and *Findings* below records what that sweep should add.

## Obsolete-test candidates

Every entry below is a **candidate for human confirmation, not a conclusion**. This pass is additive only — it added tests and subtracted none — and nothing here was edited, deleted or disabled. Each carries the delta that supersedes it and the evidence it was matched on.

The search was bounded to the dispatched test-path glob `.github/tests/*.py` and nowhere else. No earlier `test-plan.md` was supplied for this change, so the mapping was made by reading the modules the dispatch named plus a grep of the glob for every construction reading a declared `github_environment` or the stack directory listing.

| # | Test, runner-selectable | Superseded by | Evidence |
|---|---|---|---|
| 1 | `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_prod_declares_the_secret_and_environment_it_already_uses` | `iac-cicd-pipeline` / *Gated Production Apply Applies the Reviewed Plan*, scenario *Merge does not apply immediately* | Asserts `PROD_GITHUB_ENVIRONMENT` — the literal `"production"` at line 192 of that module — equals `main-production`'s declared `github_environment`. The delta states that declaration is now `main-production`. The **assertion** survives; the constant is what is superseded. `tasks.md` 7.3 owns the edit. Production pull request. |
| 2 | `test_a_second_environment.TestTheSecondEnvironmentIsDeclared.test_the_second_environment_declares_its_own_secret_and_environment` | `proposal.md` and `tasks.md` 4.1 — **not a delta scenario**; no scenario names `main-staging` as an Environment | Asserts `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT` — the literal `"staging"` at line 156 — equals `main-staging`'s declared `github_environment`. Same shape as #1. `tasks.md` 4.3 owns the edit. **Staging** pull request. |
| 3 | `test_ci_configuration.TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment` | `iac-platform-deploy-pipeline` / *Gated Deploy Reuses the Terraform Production Environment*, scenario *Merge does not deploy immediately* | Asserts exactly one job in `platform-deploy.yml` declares `GATED_DEPLOY_ENVIRONMENT` — the literal `"production"` at line 6611. The delta states the gate is `main-production`. `tasks.md` 7.3 owns the edit. Production pull request. |
| 4 | `test_the_external_service_names_are_retired.TestTheDeployGateNamesTheEnvironmentAStackDeclares` — the class **docstring**, not its assertion | `iac-platform-deploy-pipeline` / *Gated Deploy Reuses the Terraform Production Environment* | The docstring quotes the superseded requirement text verbatim (`"SHALL require manual approval via the **same** \`production\` GitHub Environment protection rule"`) and the superseded scenario text (`"both SHALL be gated by the same \`production\` Environment's required reviewers"`). The delta rewrites both. The assertion itself is an equality between two committed files, names neither side, and **survives unedited** — which its own docstring says it was written for. `tasks.md` 7.4 owns the edit. Production pull request. |
| 5 | `test_a_second_environment.environment_identifiers` — the function, and the four assertions that consume it | `tasks.md` 4.2 and `design.md`'s "Three identifier sets must gain a third spelling" — **not a delta scenario** | Built as the union of stack directory names and declared `github_environment` values. Today `{main-production, main-staging, production, staging}`; at staging's flip `staging` leaves it and at production's `production` does, collapsing it to the two stack names. Its consumers then go green by losing their subject. `tasks.md` 4.2 owns the repair — adding `target_environment` as a third source. **Staging** pull request, in the same commit as 4.1. |
| 6 | `test_host_converge_workflow.TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment.test_the_workflow_names_no_environment` | Same as #5 | Builds the same union inline (lines 1018–1020) and sweeps `host-converge.yml` for each name. `host-converge.yml` is the one workflow that actually consumes the declared Ansible group, so collapse stops it reporting a hardcoded group name. **Staging** pull request. |
| 7 | `test_environment_agnostic_pipeline.TestTheDestroyGateReadsApplicabilityFromTheDeclaration.test_the_gate_names_no_environment` | Same as #5 | Builds the same union inline (lines 2429–2433) and sweeps the destroy-gate steps. Collapse stops it reporting a gate step conditioned on a literal `production` or `staging`, which *Each Stack Declares Its Own Pipeline Configuration* forbids by name. **Staging** pull request. |

**Entries 5–7 are the only ones whose repair is not a literal move**, and they are the entries most easily missed: nothing about them goes red. Their failure mode is a green check that has quietly stopped asserting anything.

`TestNoWorkflowNamesAnEnvironment._names()` in `test_environment_agnostic_pipeline.py` is **not** an entry here, and the exclusion is deliberate rather than an oversight: it already reads `target_group` as a third source, and its companion `test_there_is_a_name_to_look_for` already asserts the set carries a name that is not a stack directory — which, after this change, is exactly the Ansible groups. It anticipated this change and needs nothing.

## Findings

**A fourth and fifth consumer of `environment_identifiers()` that `tasks.md` 4.2 does not name.** `test_host_configuration_names_its_environment.py` imports that function and consumes it twice: in `TestTheBaselinePlayNamesTheEnvironmentItTargets.setUp` (line 806), where it decides whether the converge play's `hosts:` names a real environment, and in `test_the_lint_sentinel_names_no_environment_this_repository_has` (line 911), which asserts the lint sentinel is not a real environment name. Both lose subject on the same collapse — after it, a `hosts: production` literal and a sentinel of `production` would each pass. **Both are repaired by 4.2's own edit**, since they call the shared function rather than rebuilding the set, so this is not a defect in the plan. It is stated because 4.2 asks the implementer to "verify all three still recognise the words `production` and `staging`", and there are five verifications to make rather than three.

**`handoff.md` and `tasks.md` disagree about §6.6's `--env` lines.** `handoff.md` says "`target_environment` stays on the environment axis in both files… The same holds for `--env` in §6.6's `gh secret set` lines"; `tasks.md` 7.6 and `handoff.md`'s own "What it must not undo" section both say that note changes to say the argument takes the **stack**. The `tasks.md` reading is the later one and is internally consistent with the rest of the change. **No test depends on the resolution**: those two lines carry the placeholder `--env <environment>`, and `environment_arguments` skips placeholders by construction, exercised by `test_a_placeholder_argument_is_not_read_as_an_environment`. Recorded rather than resolved.

## Unresolved project questions

Each was raised by this pass, is not answered by `AGENTS.md` or `CLAUDE.md`, and could not be asked — a dispatched subagent has no channel. The assumption taken is stated with the tests that depend on it.

| Question | Assumption taken | Tests depending on it |
|---|---|---|
| How should derived tests be split across a change that merges in two pull requests? `AGENTS.md` records the independent-test-authoring step but no convention for a multi-pull-request change, and the suite has no precedent — every existing module belongs to a single-pull-request change. | **Two modules, one per pull request**, rather than one module committed in two steps. A file boundary is mechanical (`git add` one file per pull request); splitting a module by class is a manual bisection whose failure mode is exactly the red canary `tasks.md` 2.2 is written to prevent. | All 39. |
| Does this repository want a second new module for one change, or a single one? The suite's modules are one-per-change, so two is a departure. | Two, for the reason above. If the project prefers one, the merge is textual — the second module's classes append to the first, and its imports become local references. **The pull-request ordering constraint survives the merge and would then have to be honoured by commit rather than by file.** | All 39. |
| What is the suite's authoring idiom — module docstring sections, SPECIFIED/DERIVED annotation, a `TestTheseReadsDiscriminate` class? Not recorded in `AGENTS.md`; the `python` skill covers `pytest` rather than `unittest`. | Read off the existing modules and followed exactly, including the "What no assertion here establishes" section and the citation form (name the change and artifact in prose, never a path under a change's own directory). | All 39. |
| Is `docs/bootstrap-a-new-host.md` in scope for `.github/tests`? `AGENTS.md` says the suite's subject is "wider than `.github/`… a property is in scope wherever the file holding it lives, so long as the assertion is a static read of a committed file", but no existing module reads that document. | In scope. The assertion is a static read of a committed file, needs no network, credential, container or Terraform binary, and an archived task record states that nothing in `.github/tests` reads that document and that a wrong instruction in it "survives every check this repository has". | The 3 tests of `TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares` and their 8 discriminators. |

## How to run what this change owes

    python3 -m unittest discover --start-directory .github/tests   # from the repository root

    # the staging pull request's own new tests
    python3 -m unittest test_the_staging_github_environment_moves_first

    # the production pull request's own new tests
    python3 -m unittest test_the_github_environments_are_named_for_their_stacks
