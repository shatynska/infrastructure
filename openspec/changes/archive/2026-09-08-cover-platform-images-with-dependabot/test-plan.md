# Test plan — cover-platform-images-with-dependabot

Derived from this change's delta spec (`specs/iac-safety-hardening/spec.md`, MODIFIED requirement *Automated Dependency Updates*) before any implementation of the change existed. The author of these tests has not read an implementation of the change, because none exists: `.github/dependabot.yml` still carries two ecosystems.

This file is **not** an artifact the OpenSpec schema knows about. It does not appear among `openspec instructions apply`'s context files and has to be opened on purpose.

## Where the tests are, and how to run them

All of them are in `.github/tests/test_ci_configuration.py`, appended as one new section at the end of the file. Nothing above that section was edited.

```
# the whole suite, from the repository root
python3 -m unittest discover --start-directory .github/tests --verbose

# one test, individually selectable, from .github/tests/
python3 -m unittest test_ci_configuration.TestEveryComposeFileDeclaringAServiceImageIsCovered \
    .test_every_compose_file_declaring_a_service_image_is_covered
```

`AGENTS.md`'s "Testing" table has three rows, and the dispatch carried all three. Every property this change states is a static read of a committed file — `.github/dependabot.yml` compared against the Compose files the tree holds — so every test landed in the third row's glob, `.github/tests/*.py`. Nothing needed the Terraform row or the Molecule row, and nothing was left unplaceable.

## Baseline

Taken before any test was written, from this change's working tree:

```
$ python3 -m unittest discover --start-directory .github/tests
Ran 170 tests in 1.229s
OK
```

Full-suite, not scoped. Nothing was failing beforehand, so every failure listed below is attributable to the tests added here.

After the additions: **193 tests, 8 failures, 0 errors.** The 170 pre-existing tests all still pass. The suite's own self-assertions — standard-library-only imports, no network-capable module, no spawned Terraform binary or container runtime — are among them and still pass: this section adds no import at all, because its wildcard matcher is written with `re`, which the suite already uses.

## What is red now, and what is green now

Eight tests fail, and each fails because the target does not exist: the `docker-compose` stanza is not in `.github/dependabot.yml` and the README sentence is not in `README.md`. They are the implementation's acceptance criteria.

| Failing test | What must exist for it to pass |
|---|---|
| `TestDependabotWatchesEveryRequiredEcosystem.test_dependabot_configures_every_required_ecosystem` | a `docker-compose` entry in `.github/dependabot.yml` (task 1.1) |
| `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_every_compose_file_declaring_a_service_image_is_covered` | that entry naming `/platform` (task 1.1) |
| `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_file_the_pinning_floor_check_reads_is_one_this_ecosystem_covers` | the same |
| `TestTheImageGroupSplitsByBlastRadius.test_the_ecosystem_declares_a_group_at_all` | a `groups:` entry with patterns (task 1.2) |
| `TestTheImageGroupSplitsByBlastRadius.test_no_group_pattern_matches_the_database_or_the_reverse_proxy` | those patterns matching neither `postgres` nor `traefik` (task 1.2) |
| `TestTheImageGroupSplitsByBlastRadius.test_the_patterns_select_every_other_image_the_stack_declares` | those patterns matching the other six, written as dependency names (task 1.2) |
| `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_readme_says_the_stack_images_are_refreshed_by_this_ecosystem` | the README sentence (task 4.2) |
| `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_readme_passage_names_the_question_no_check_can_answer` | that sentence naming the persistent-store question (task 4.2) |

The configuration design.md Decisions 1 and 4 describe was run through the same helpers, as a throwaway dictionary, without writing it to `.github/dependabot.yml`: it produces no missing ecosystem, no coverage offence, six matched dependencies out of eight, and neither `postgres` nor `traefik` among them. The eight failures are therefore satisfiable by the configuration the change intends and not by that configuration alone being guessed at.

**Fifteen of the twenty-three new tests pass on their first run, and that is not the alarm state it would be for a test written against absent code.** Their target is not the absent `docker-compose` stanza — it is the discovery and matching helpers added alongside them in the same file, which do exist. They are the suite's own established "is this a real read of the file" pattern: fixture trees, a fixture configuration, and the fetcher's filename pattern exercised against names the committed tree does not contain. Two of them — `test_the_tree_holds_a_stack_definition_at_all` and `test_the_shared_platform_stack_is_among_the_files_discovered` — read the committed tree and pass because `platform/docker-compose.yml` is already there; they exist to stop the coverage comparison from passing over an empty discovery.

Discovery was additionally run with `REPO_ROOT` pointed at the **main** working tree, with this change's worktree present under `.claude/worktrees/`, and returned `platform/docker-compose.yml` and nothing else — the phantom copy is pruned, which is what design.md Decision 2's "Which walker" paragraph requires and what `docs/change-queue.md` entry 34 records the `terraform` assertion getting wrong.

## Scenario accounting

The MODIFIED requirement carries **13** `#### Scenario:` blocks. All 13 are accounted for below: four are new with this change, nine are unchanged and already covered by tests written for earlier changes.

### New with this change

**Scenario: Platform image update is proposed automatically**

| Limb | Test |
|---|---|
| the ecosystem that would propose it is configured (enabling condition) | `TestDependabotWatchesEveryRequiredEcosystem.test_dependabot_configures_every_required_ecosystem` |
| it would reach the stack that pins the images | `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_the_shared_platform_stack_is_among_the_files_discovered`, `.test_every_compose_file_declaring_a_service_image_is_covered` |
| "the same gated deploy approval as any other change to the stack definition" | `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment` |
| **"Dependabot SHALL open a pull request"** | **deliberately untested** — see *Deliberately untested* below |

**Scenario: Every Compose file declaring a service image is covered**

| Limb | Test |
|---|---|
| the comparison over the committed tree | `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_every_compose_file_declaring_a_service_image_is_covered` |
| non-vacuity of that comparison | `.test_the_tree_holds_a_stack_definition_at_all`, `.test_the_shared_platform_stack_is_among_the_files_discovered` |
| the population is decided by content, not by name | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_task_list_under_a_matching_name_is_not_a_stack_definition`, `.test_a_stack_definition_is_discovered_whatever_it_is_named`, `.test_a_services_mapping_declaring_no_image_is_not_a_stack_definition` |
| the directory condition reports a file the configuration omits | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_in_a_directory_the_configuration_omits_is_reported` |
| the filename condition (the "AND") | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_the_filename_pattern_does_not_match_is_reported` |
| a file meeting both is not reported | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_meeting_both_conditions_is_accepted`, `.test_a_directory_pattern_is_read_as_a_glob` |

**Scenario: A stack file the fetcher's name pattern does not match is reported**

| Limb | Test |
|---|---|
| a stack file in a named directory under a non-matching name is reported | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_the_filename_pattern_does_not_match_is_reported` |
| the discovery does not filter by name first, so such a file can be reported at all | `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_definition_is_discovered_whatever_it_is_named` |
| the boundary between a matching and a non-matching name | `TestTheFetcherFilenamePatternIsTranscribedFaithfully.test_the_names_the_fetcher_selects_are_matched`, `.test_the_names_the_fetcher_passes_over_are_not_matched` |

**Scenario: A proposed image update is not exempt from the stack's own obligations**

| Limb | Test |
|---|---|
| "SHALL pass the pinning requirement's automated floor check" — the file that check reads is one this ecosystem reaches | `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_file_the_pinning_floor_check_reads_is_one_this_ecosystem_covers` |
| "SHALL receive the human review" — the reviewer is told, where a reviewer looks | `.test_the_readme_says_the_stack_images_are_refreshed_by_this_ecosystem`, `.test_the_readme_passage_names_the_question_no_check_can_answer` |
| **whether the bumped image declares a persistent store the current one does not** | **deliberately untested** — see below |

### Unchanged by this change, and already covered

These nine were not re-derived. The delta reproduces them verbatim; their tests were written for earlier changes and are listed so the count is complete.

| Scenario | Where it is covered |
|---|---|
| Provider version update is proposed automatically | `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems` (enabling condition only; the pull request itself is Dependabot's behaviour) |
| Every lockfile-bearing directory is covered | `TestDependabotCoverage.test_every_terraform_lockfile_directory_appears_in_dependabot_config` |
| Action version update is proposed automatically | `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems` (enabling condition only) |
| Pre-commit hook revisions are refreshed on a schedule | `TestScheduledHookRefresh.test_a_scheduled_workflow_runs_pre_commit_autoupdate` |
| A workflow-opened pull request receives the required status checks | `TestNoWorkflowOpensAPullRequestWithTheDefaultToken` |
| No workflow opens a pull request with the default workflow token | `TestNoWorkflowOpensAPullRequestWithTheDefaultToken` |
| The default workflow token is not left holding unused write authority | `TestThePullRequestJobLeavesTheDefaultTokenNoWrite` |
| A permissions declaration is present rather than merely absent | `TestPermissionsReading`, `TestThePullRequestJobLeavesTheDefaultTokenNoWrite` |
| A long-lived automation credential is documented where it can be found | `TestTheAutomationCredentialIsDocumentedInTheReadme` |

## Assertion classification

Every new test carries its classification in its own docstring. Summarised:

**SPECIFIED** — traces to SHALL text in the delta spec:

- `TestDependabotWatchesEveryRequiredEcosystem.test_dependabot_configures_every_required_ecosystem`
- `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_the_tree_holds_a_stack_definition_at_all`
- `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_the_shared_platform_stack_is_among_the_files_discovered`
- `TestEveryComposeFileDeclaringAServiceImageIsCovered.test_every_compose_file_declaring_a_service_image_is_covered`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_task_list_under_a_matching_name_is_not_a_stack_definition`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_definition_is_discovered_whatever_it_is_named`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_the_filename_pattern_does_not_match_is_reported`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_in_a_directory_the_configuration_omits_is_reported`
- `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_file_the_pinning_floor_check_reads_is_one_this_ecosystem_covers`
- `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_stack_deploy_stays_gated_on_the_production_environment`

**DERIVED** — inferred from `design.md`/`tasks.md`, or invented as a discrimination guard; no scenario states them:

- `TestDependabotWatchesEveryRequiredEcosystem.test_the_ecosystem_check_reads_the_configuration`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_services_mapping_declaring_no_image_is_not_a_stack_definition`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_stack_file_meeting_both_conditions_is_accepted`
- `TestTheComposeCoverageCheckIsARealReadOfTheTree.test_a_directory_pattern_is_read_as_a_glob`
- `TestTheFetcherFilenamePatternIsTranscribedFaithfully.test_the_names_the_fetcher_selects_are_matched`
- `TestTheFetcherFilenamePatternIsTranscribedFaithfully.test_the_names_the_fetcher_passes_over_are_not_matched`
- every test in `TestTheImageGroupSplitsByBlastRadius` (five) — the grouping is design.md Decision 4 and no scenario states it
- `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_readme_says_the_stack_images_are_refreshed_by_this_ecosystem`

**Mixed** — `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations.test_the_readme_passage_names_the_question_no_check_can_answer` is SPECIFIED for the obligation ("SHALL be established by that review") and DERIVED for the vocabulary it matches on, exactly as the existing credential-runbook assertions are.

Three DERIVED assertions constrain the implementation more than the delta spec does, and are called out so they can be argued with rather than discovered:

1. **The group patterns must select every stack image other than `postgres` and `traefik`.** Membership is computed from the stack rather than enumerated, so adding a service to `platform/docker-compose.yml` without grouping it turns this red. That is deliberate under design.md Decision 4's split, but it is a maintenance obligation the spec does not state.
2. **The README must carry the passage.** The requirement's SHALL text does not mention the README for image bumps; design.md's first risk and task 4.2 do, and the test matches on vocabulary rather than on a sentence.
3. **`platform-deploy.yml` must have exactly one job on `environment: production`.** A pre-existing property, asserted here because scenario "Platform image update is proposed automatically" now depends on it and nothing else in the suite reads it.

## Deliberately untested

- **That Dependabot in fact opens a pull request** (scenario "Platform image update is proposed automatically"). Behaviour of a service outside this repository. No static read of a committed file reaches it, and this suite may make no network call. This is the same boundary the `terraform` and `github-actions` scenarios already accept.
- **Whether a bumped image declares a persistent store the current one does not** (scenario "A proposed image update is not exempt from the stack's own obligations", third limb). The store is declared by the image, not by the stack definition, so establishing it needs a registry call — which this suite forbids itself and asserts that it forbids. The delta spec says so in its own text. What *is* asserted is that a reviewer is told they owe the question.
- **That a `weekly` schedule and an unset `open-pull-requests-limit` are right** (design.md Decision 5). Neither is stated by a scenario, and an assertion over them would restate the configuration rather than check anything about the tree.
- **That no `ignore` stanza is present** (design.md Decision 3). Same reason: the decision is an argument about what *not* to write, and a test asserting the absence of a key would fail the day someone has a good reason for one, with the reasoning living only in an archived design.

## Added after this plan was written

One assertion, added during the build in response to the code-review gate, and recorded here so this manifest does not understate what the suite now holds.

`TestEveryComposeFileDeclaringAServiceImageIsCovered .test_every_configured_directory_holds_a_file_the_fetcher_selects` — DERIVED, stated by no scenario. Every assertion this plan derived walks tree → configuration: each stack definition must be reachable. Nothing walked configuration → tree, and the fetcher fails hard in that direction — it raises when the configured directory holds no file its filename pattern selects. A directory named in the configuration that holds none errors on every Dependabot run, opens no pull request, and leaves the suite green. That mechanism is what design.md Decision 1 rests on when it argues `directory: "/"` would fail rather than scan, so it is now asserted rather than only reasoned about. Observed red against a `directories:` list carrying a phantom `/apps`, then restored.

## Obsolete tests

One entry. It is a **candidate for human confirmation**, not a conclusion: this pass added tests and edited or deleted none.

**`test_ci_configuration.TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems`** (`.github/tests/test_ci_configuration.py`, line 236 as of this writing)

- **Superseded by**: the MODIFIED requirement's opening sentence, which this change widens from "both the `terraform` and `github-actions` package ecosystems" to "the `terraform`, `github-actions` and `docker-compose` package ecosystems".
- **Evidence**: the test's body iterates the literal pair `("terraform", "github-actions")` and asserts each is configured — the enumeration the delta widens. Its name asserts "both", which is false of three. Its own docstring cites "the requirement's opening sentence" as what it traces to.
- **Replaced by**: `TestDependabotWatchesEveryRequiredEcosystem.test_dependabot_configures_every_required_ecosystem`, which asserts all three and is red until the stanza lands.
- **Not done here**: `tasks.md` 3.5 asks for the old test to be renamed and extended in place. This pass may not edit an existing test under any operation, so it wrote the widened assertion as a new test instead and reports the old one here. Whoever implements should decide between deleting the old test (its assertion is a strict subset of the new one) and performing the rename 3.5 describes; task 3.5's own note about which references may be edited — and which archived test-plans may not — still applies either way.

**Search bound**: `.github/tests/*.py`, the dispatched glob, and nowhere else. Within it, the Dependabot configuration is read by exactly three places: the two methods of `TestDependabotCoverage`, and `TestTheSuiteDiscriminates.DEPENDABOT_TEST`, which selects the *terraform lockfile* test by name and is unaffected by this delta and by the rename above. No earlier `test-plan.md` was supplied to this pass, so no scenario-to-test mapping outside the suite itself was consulted. This is a bounded search of one file, not an exhaustive search of the repository: read the single entry above as "nothing else in the dispatched glob was found to bear on the superseded enumeration", not as "no such test exists anywhere".

## Unresolved project questions

The obligation to ask was discharged by recording, not asking: this pass ran as a dispatched subagent with no channel to ask on.

1. **May a test author rename an existing test?** `AGENTS.md` says the tests are derived by an author other than the implementer, and `tasks.md` 3.5 asks for a rename. Nothing records whether that author may perform it. *Assumption taken*: no — the pass is additive only, so the widened assertion was written as a new test and the old one reported above. *Tests depending on it*: `TestDependabotWatchesEveryRequiredEcosystem.test_dependabot_configures_every_required_ecosystem` (new) and, indirectly, whether `TestDependabotCoverage.test_dependabot_configures_both_required_ecosystems` survives.
2. **How much of a stated-but-unspecified design decision should a test bind?** Decision 4's grouping and task 4.2's README sentence are decisions of the change, not SHALL text of the requirement. `AGENTS.md` records no convention on whether such decisions get assertions. *Assumption taken*: assert them, marked DERIVED, on the reasoning tasks 3.4 gives — both of the grouping's failure modes are silent. *Tests depending on it*: all five in `TestTheImageGroupSplitsByBlastRadius`, and both README tests in `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations`. 2a. **What is a Dependabot dependency name?** — **recorded after the fact, on 2026-09-08, because this list did not carry it and that omission is what let the defect through.** This section exists to expose unverified beliefs about Dependabot, and the belief that actually failed was never written down: it sat in design.md Decision 4's table as though it were a fact, and both the helper and the configuration were derived from it. *Assumption originally taken*: the image reference with its tag stripped, registry host included. **Wrong.** `dependabot-core` builds the dependency as `Dependency.new(name: details.fetch("image"), ..., source: source_from(details))` — the registry lives in the source, never in the name — so `quay.io/prometheuscommunity/postgres-exporter` is the dependency `prometheuscommunity/postgres-exporter`. Two group patterns therefore matched nothing, and `TestTheImageGroupSplitsByBlastRadius` stayed green because it computed its expected names from the same wrong helper. *Now*: anchored to pull requests Dependabot actually opened, in `TestDependencyNamingMatchesWhatDependabotActuallyDid`. Of the images this stack declares, only `quay.io/...` has been **observed**; `ghcr.io`, `host:port` and bare `localhost` are still inferred, and the helper's docstring says so. *The general lesson, which outlives this entry*: an assumption about an external system that decides what gets committed needs at least one assertion tracing to that system's observed behaviour. Deriving the check and the artefact from one belief tests the belief against itself.
3. **Which wildcard semantics does Dependabot apply to a group's patterns?** Read from documentation rather than from source, unlike the file fetcher's regex, which design.md quotes from `dependabot-core`. *Assumption taken*: `*` matches any run of characters including `/`, `?` matches one, matching is case-insensitive — implemented with `re` rather than by adding an `fnmatch` import, and deliberately distinct from the suite's existing `gh_glob_matches`, whose `*` stops at a `/`. *Tests depending on it*: `TestTheImageGroupSplitsByBlastRadius.test_no_group_pattern_matches_the_database_or_the_reverse_proxy`, `.test_the_patterns_select_every_other_image_the_stack_declares`, `.test_the_group_check_reads_the_patterns`.
4. **Python tooling.** The project pins the suite's dependencies in `.github/requirements-ci.txt` and runs no `ruff` or `mypy` — `.pre-commit-config.yaml` carries no Python linter. *Assumption taken*: neither was run; the new section follows the file's existing style and adds no import.
