# Test plan — `apply-host-configuration-through-a-gated-workflow`

Derived from this change's delta specifications at commit `d38fb6e`, the commit holding the approved plan, by an author who has not seen and will not write the implementation. **This file is not an artifact the OpenSpec schema knows about**, so it does not appear among the context files `openspec instructions apply` lists: it has to be read on purpose, before implementing.

Everything here is additive. No existing test was edited, deleted or disabled, and no implementation was written — in particular `.github/workflows/host-converge.yml` and `ansible/requirements.txt` were deliberately **not** created, because their absence is what several of these tests report.

## Test command, glob, and what was written

| | |
|---|---|
| Test command | `python3 -m unittest discover --start-directory .github/tests`, from the repository root |
| Test-path glob | `.github/tests/*.py` |
| Written | `.github/tests/test_host_converge_workflow.py` (36 tests) |

The other two rows of this project's testing table place nothing here. This change touches no Ansible role and no Terraform module, so neither the Molecule row nor the `terraform test` row has a subject; every property below that is testable at all is a static read of a committed file, or the execution of a committed shell body against a scratch tree, which is what that suite is for.

## Baseline

Taken before anything was written, over the **full** suite:

    python3 -m unittest discover --start-directory .github/tests
    Ran 557 tests in 8.490s
    OK

After adding the new module, over the same full suite:

    Ran 593 tests in 9.037s
    FAILED (failures=32)

593 − 557 = 36 new tests. 561 pass (557 pre-existing + 4 new, see below) and 32 fail. **No pre-existing test regressed**: every failure is in the new module.

### Which new tests are red, and on what

| Failure state | Count | What it establishes |
|---|---|---|
| The target does not exist yet | 26 | 25 report `.github/workflows/host-converge.yml does not exist`; one reports that `ansible/requirements.txt` states no `ansible-core` pin because the file is not there. The assertions never executed; they establish the target's absence and nothing about their own quality. |
| The code ran and produced a wrong value | 2 | `prod` declares `read_only_secret: HCLOUD_TOKEN` (the name every GitHub Environment shadows), and `ansible/inventory/prod.hcloud.yml` reads `HCLOUD_TOKEN_PROD` while its declaration states `HCLOUD_TOKEN`. Both are the defects tasks 2.1 repairs. |
| A committed option is absent | 3 | Neither inventory source declares `connect_with`, so no per-run connection-address selection exists and none defaults to `public_ipv4`. Repaired by tasks 1.1/1.2. |
| Blocked on the above | 1 | `test_the_converge_job_sets_the_variable_the_sources_read` fails at its own precondition — there is no selection variable in the committed sources to look for in the workflow yet. |

### Which new tests are green before the implementation, and why

Four. Each is named here so a green run of them is not read as coverage of an unimplemented behaviour.

- `TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares.test_the_comparison_is_literal_rather_than_case_insensitive` and `TestTheConvergeRunsTheAnsibleTheRolesWereVerifiedUnder.test_the_pin_read_discriminates` — discriminators over fixture data. They exercise this module's own readers, not the change; they are green by construction and exist so the two assertions that depend on those readers cannot pass vacuously.
- `TestNoDeclarationNamesTheWriteTokensOwnName.test_every_declaration_states_a_read_only_secret_to_read` — a fail-closed guard. Green because both committed declarations do state a secret name; it exists so the sweep beside it cannot be green over a tree it could not read.
- `TestAnEnvironmentThatCanBeProvisionedCanBeConverged.test_every_provisioned_environment_has_a_source_and_variables_of_its_own` — green because the committed tree already satisfies the clause at two environments. The clause is **new** in this delta and its enforcement is not green: the refusal that makes it hold for a third environment is `TestHostConvergeDiscoveryFailsClosed.test_discovery_fails_on_an_environment_with_no_variables_of_its_own`, which is red.

### One defect this pass found in its own tests, and fixed

The pre-approval job's locator first used the sibling suite's `invocation_lines` helper to find the step writing to `$GITHUB_STEP_SUMMARY`. That helper skips a match sitting inside an unclosed quote — correct for detecting a *command*, wrong here, because the summary is written by redirecting into it (`} >>"$GITHUB_STEP_SUMMARY"`, the shape `platform-deploy.yml` already uses). The locator found no publishing job in a workflow that had one. It now matches as text over the comment-stripped body. Recorded because it was a broken test rather than a red one, and the three tests behind it would otherwise have been unsatisfiable by any correct implementation.

**How that was found, and what else it establishes.** The nine extract-and-run discovery tests were probed against a throwaway prototype workflow written **outside the repository**, in this session's scratchpad, and deleted from nothing because it was never in the tree. All nine went green against it, as did every converge-job shape assertion. That establishes the harness is satisfiable — a nine-test suite no implementation could pass would be a defect handed downstream, and it is not distinguishable from a red suite by running it.

## Every scenario, accounted for

28 scenarios across the two delta specs (17 in `iac-cicd-pipeline`, 11 in `iac-host-configuration`); 28 accounted for below. Test names are given in the form `python3 -m unittest <module>.<Class>.<test>` selects, run from the repository root.

### `iac-cicd-pipeline` — ADDED: Host Configuration Is Applied by a Gated Workflow

| Scenario | Covered by |
|---|---|
| A merge to the host configuration converges without a workstation | `test_host_converge_workflow.TestAMergeConvergesWithoutAWorkstation.test_the_workflow_is_triggered_by_a_merge_touching_the_host_configuration`, `.test_the_converge_job_runs_the_host_baseline_play` |
| A host's first converge is the operator's | **Uncovered** — see below |
| The pre-approval job holds no converge credential | `TestThePreApprovalJobHoldsNoConvergeCredential.test_the_publishing_job_declares_no_github_environment`, `.test_the_publishing_job_consumes_no_secret`, `.test_the_publishing_job_publishes_the_host_configuration_diff` |
| The converge job is gated on the environment's own GitHub Environment | `TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment.test_the_converge_job_takes_its_environment_from_discovery` |
| An environment that cannot be converged fails the workflow | `TestHostConvergeDiscoveryFailsClosed.test_discovery_fails_on_a_source_whose_environment_declares_no_pipeline`, `.test_discovery_fails_on_an_environment_with_no_inventory_source` |
| Discovery finding no environment fails rather than reporting success | `TestHostConvergeDiscoveryFailsClosed.test_discovery_fails_when_it_finds_no_environment` |
| A run is requested for an environment that does not exist | `TestHostConvergeDiscoveryFailsClosed.test_a_dispatched_environment_discovery_did_not_find_is_refused`; converses `.test_a_dispatched_environment_discovery_found_is_the_only_one_selected`, `.test_an_empty_dispatch_input_selects_every_environment` |
| A wrong secret stops the run before the host is touched | `TestAWrongSecretStopsTheRunBeforeTheHostIsTouched.test_the_credentials_are_exercised_before_the_play_runs` |
| The converge job supplies what the run needs | `TestTheConvergeJobIsProvisionedBeforeItRuns.test_the_toolchain_and_galaxy_content_are_installed_first`, `.test_every_ansible_command_runs_from_the_directory_that_configures_it` |
| The converge runs the Ansible the roles were verified under | `TestTheConvergeRunsTheAnsibleTheRolesWereVerifiedUnder.test_the_converge_job_installs_from_the_repositorys_own_manifest` **and** `.test_the_two_manifests_pin_one_version` (both halves; tasks 3.4-0) |
| One environment's failure does not silence another's | `TestOneEnvironmentsConvergeDoesNotSilenceAnother.test_a_failing_converge_does_not_abandon_its_siblings` |

Two further assertions trace to SHALL text in this requirement rather than to a scenario, and are recorded so they are not read as invented: `TestOneEnvironmentsConvergeDoesNotSilenceAnother.test_an_in_flight_converge_is_not_cancelled_by_a_later_one` ("A converge SHALL NOT be cancelled in favour of a later one"), and `TestAWrongSecretStopsTheRunBeforeTheHostIsTouched.test_the_play_is_given_the_environment_the_matrix_row_names`.

### `iac-cicd-pipeline` — MODIFIED: Each Environment Declares Its Own Pipeline Configuration

| Scenario | Covered by |
|---|---|
| A new environment needs no workflow edit *(revised: now names the host-converge workflow)* | New: `TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment.test_the_workflow_names_no_environment`, `.test_no_step_maps_an_environment_to_its_secret`, `TestHostConvergeDiscoveryFailsClosed.test_discovery_emits_every_convergeable_environment`. The three Terraform workflows stay covered by the existing `test_environment_agnostic_pipeline.TestNoWorkflowNamesAnEnvironment`, unedited. |
| Two environments declaring the same read-only secret are refused | **Unchanged by this delta**; already covered by `test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_no_two_environments_declare_the_same_read_only_secret`, `.TestTheDeclarationCensusIsARealReadOfTheTree.test_two_environments_declaring_one_read_only_secret_are_reported`, `.TestDiscoveryFailsClosed.test_discovery_fails_on_two_environments_sharing_a_read_only_secret`. No new test. |
| Two environments declaring the same GitHub Environment are refused | Unchanged; existing `.test_no_two_environments_declare_the_same_github_environment`, `.test_two_environments_declaring_one_github_environment_are_reported`, `.test_discovery_fails_on_two_environments_sharing_a_github_environment`. No new test. |
| A declaration naming the write token's own name is refused | **New**: `TestNoDeclarationNamesTheWriteTokensOwnName.test_no_environment_declares_the_write_tokens_own_name`, guarded by `.test_every_declaration_states_a_read_only_secret_to_read`. Red today on `prod`. |
| An environment missing its declaration fails the pipeline | Existing `.test_every_environment_directory_carries_a_declaration` / `.test_discovery_fails_on_a_declaration_missing_a_field` cover the Terraform side; the host-converge side is new: `TestHostConvergeDiscoveryFailsClosed.test_discovery_fails_on_a_declaration_missing_a_field`. |
| Discovery finding no environment fails rather than reporting success *(Terraform discovery)* | Unchanged; existing `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed.test_discovery_fails_when_it_finds_no_environment`. No new test. |

### `iac-host-configuration` — ADDED: The Address a Converge Connects To Is Selected Per Run

**All four scenarios are uncovered by this suite**, and that is the change's own position rather than a gap this pass introduced: tasks 1.3 records them as manual verification against the live Hetzner API, because what they assert is what a run **connects to**, which no static read of a committed file can establish and which `.github/tests` may not attempt (it makes no network call and holds no credential).

| Scenario | Why uncovered / what stands beside it |
|---|---|
| A run supplying no selection reaches the public address | Uncovered: needs a run. The committed default is asserted by `TestTheConnectionAddressIsSelectableAndDefaultsToThePublicOne.test_the_selection_defaults_to_the_public_address`, which establishes the literal in the file and **not** what a run dials. tasks 1.3 establishes the latter. |
| A run selecting the tailnet address reaches the host over the tailnet | Uncovered: needs a tailnet-joined machine and a live host. Beside it: `.test_every_source_takes_its_connection_address_per_run` and `TestTheConvergeSelectsTheAddressTheInventoryReads.test_the_converge_job_sets_the_variable_the_sources_read` establish that a selection exists and that the converge job sets the variable the sources read. tasks 3.7 and 7.5 observe the rest. |
| An unrecognised selection fails the run | Uncovered entirely. This is the plugin's own option validation, exercised by tasks 1.3's third command; there is no committed file whose content decides it. It is also the one of the four a comment cannot establish, which is why tasks 1.3 names it specifically. |
| The selection adds no reachable host and removes no guard | Uncovered as a run property. The committed-shape half continues to be held by the existing `test_host_configuration_names_its_environment` classes — `TestInventoryIsResolvedLiveRatherThanFromACommittedFile`, `TestARunWhoseTargetGroupResolvesToNoHostRefuses`, `TestAFurtherEnvironmentIsAddedRatherThanEditedIn` — which run unchanged over the modified sources and go red if the selection disturbed any of them. |

### `iac-host-configuration` — MODIFIED: Dynamic Inventory via hcloud Plugin

| Scenario | Covered by |
|---|---|
| Inventory resolved live from Hetzner | Unchanged; existing `test_host_configuration_names_its_environment.TestInventoryIsResolvedLiveRatherThanFromACommittedFile.test_every_inventory_source_resolves_hosts_from_the_plugin_and_groups_by_label`. No new test. |
| Disabled server yields no stale inventory entry | Unchanged; run-time behaviour, held statically by `.test_no_committed_inventory_file_enumerates_a_host`. No new test. |
| An environment's source reaches only its own project | Unchanged; existing `TestEachEnvironmentHasAnInventorySourceOfItsOwn` (three tests). No new test. |
| A further environment is brought into inventory | Unchanged; existing `TestAFurtherEnvironmentIsAddedRatherThanEditedIn.test_the_inventory_sources_differ_only_in_the_credential_they_name`. No new test. **Note for the implementer:** that test compares the two sources' parsed documents with the credential scrubbed, so tasks 1.1 and 1.2 must add an *identical* `connect_with` line to both or it goes red — correctly. |
| An inventory source cannot authenticate | Unchanged; existing `TestANamedInventorySourceIsWhatMakesARunReachAnEnvironment` (three tests over `ansible.cfg`). No new test. |
| An environment that can be provisioned but not converged is reported | **New**: `TestAnEnvironmentThatCanBeProvisionedCanBeConverged.test_every_provisioned_environment_has_a_source_and_variables_of_its_own` (green today, see above) and `TestHostConvergeDiscoveryFailsClosed.test_discovery_fails_on_an_environment_with_no_variables_of_its_own`, `.test_discovery_fails_on_an_environment_with_no_inventory_source` (red). |
| A source's credential variable is the name the environment declares | **New**: `TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares.test_each_source_reads_the_name_its_declaration_states` (red on `prod`), with `.test_the_comparison_is_literal_rather_than_case_insensitive` establishing the comparison is literal rather than case-folding. |

## Assertion classification

Every assertion in the new module carries a SPECIFIED or DERIVED annotation in its own docstring, in the idiom the four modules beside it already use. In summary:

- **SPECIFIED** — traces to SHALL text or to a scenario in a delta spec. All of the scenario coverage above.
- **DERIVED** — traces to `design.md` or `tasks.md` rather than to a scenario, and is labelled as such in the test itself. These are: the workflow's filename and the dispatch input's name; that the connection-address variable is set at **job** level rather than at workflow or step level (tasks 3.4a); that both inventory sources read one selection variable (tasks 1.2); that an empty dispatch input selects every environment (tasks 3.2); that a dispatched environment discovery *did* find is the only one selected; and the two reader discriminators.
- **Deliberately untested** — the four address scenarios above; the whole of §7's operator work (repository settings, keypairs, Environment secrets), which is not committed content and which nothing in this suite may read; and whether `ansible/requirements.txt` pins `ansible-core` *alone* (tasks 3.4-0 asks for it; the delta obliges only that the two files agree on that one version, so no assertion was invented about the manifest's other contents).

## Obsolete tests — candidates for human confirmation

Search bound: `.github/tests/*.py`, the dispatched glob, and nowhere else. No earlier `test-plan.md` was supplied for this change, so no scenario-to-test mapping was available to search from; what follows was found by reading the two files the change's own artifacts name.

Both entries are **candidates for human confirmation**. Neither was edited, deleted or disabled by this pass, and tasks 2.2 assigns the edits to the implementer.

**1. `test_environment_agnostic_pipeline.py`, the pinned expectation of production's read-only secret name.**

- Identifier: `python3 -m unittest test_environment_agnostic_pipeline.TestEveryEnvironmentCarriesAPipelineDeclaration.test_prod_declares_the_secret_and_environment_it_already_uses`
- Superseded by: `iac-cicd-pipeline` MODIFIED — "No environment's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every environment", and the scenario *A declaration naming the write token's own name is refused*.
- Evidence: the module sets `PROD_READ_ONLY_SECRET = "HCLOUD_TOKEN"` (line 164), justified by a comment resting on that change's "nothing in repository settings changes for N=1"; the test asserts `assertEqual(PROD_READ_ONLY_SECRET, declaration.read_only_secret)` with a message reading "so the repository secret that exists today would have to be renamed in the same instant as the merge" — which is exactly what this change does deliberately.
- Presentation after tasks 2.1: **goes red**. Re-pointing the constant is not weakening a test; the proposition changed in the specification.

**2. `test_environment_agnostic_pipeline.py`, the digest-emitter exemption in the literal-named-credential sweep.**

- Identifier: `python3 -m unittest test_environment_agnostic_pipeline.TestNoWorkflowNamesAnEnvironment.test_no_terraform_workflow_maps_an_environment_to_a_secret`
- Superseded by: the same clause. The exemption exists only because prod's own read-only secret and the omitted-write-token guard's mandatory `secrets.HCLOUD_TOKEN` read are the same string.
- Evidence: the test's docstring states "Prod declares `HCLOUD_TOKEN` as its own read-only secret ... so the guard's mandatory read and this sweep's subject are the same string", and names as one of three closed escapes "giving prod a different read-only secret name" — the rename tasks 2.1 performs. After it, `declared_secrets` no longer contains `HCLOUD_TOKEN`, the exemption matches nothing, and `assertLessEqual(len(exempted), 1)` passes over an empty list.
- Presentation after tasks 2.1: **stays green while becoming untrue**. This is the entry that needs a human, because no run will surface it. Either correct the docstring to say the escape was taken deliberately and the exemption is now inert, or remove the exemption; both change no result.

**No third entry was found.** Distinguishing the two possible meanings of that, as the search's own bound requires: this is *none found by this search*, not *none exists*. The search read the two modules the change's artifacts name and grepped the suite for the superseded names; it did not re-derive a requirement-to-test index for the whole suite, and this author has never seen the implementation.

## Unresolved project questions

No channel exists to ask on from a dispatched subagent, so each is recorded with the assumption taken and the tests that depend on it.

1. **The workflow's filename.** The delta says "a workflow triggered by a merge to the default branch" and names no file. Assumed `.github/workflows/host-converge.yml`, from `proposal.md` and tasks 3.1. Every test in the six workflow-shape classes and in `TestHostConvergeDiscoveryFailsClosed` depends on it; a different name makes all 29 of them red for the wrong reason and is a one-constant edit (`HOST_CONVERGE`).
2. **The environment variable the dispatch input arrives under, inside the discovery body.** Not fixed anywhere in the change. *Not assumed*: resolved at run time from the discovery step's own `env:` block — the key whose value references `inputs.environment` — so the implementer's choice is followed. Depended on by `.test_a_dispatched_environment_discovery_did_not_find_is_refused`, `.test_a_dispatched_environment_discovery_found_is_the_only_one_selected`, `.test_an_empty_dispatch_input_selects_every_environment`. If the body takes the input any other way, those tests say so in their own message rather than failing opaquely.
3. **The dispatch input's name.** Assumed `environment` (tasks 3.1). One test depends on it: `.test_a_run_can_also_be_requested_by_hand_for_one_environment`.
4. **The connection-address environment variable's name.** Not fixed by the change (tasks 1.1 says only "an environment variable"). *Not assumed*: read out of the committed inventory sources and looked for in the workflow under whatever name they use. Depended on by `TestTheConvergeSelectsTheAddressTheInventoryReads.test_the_converge_job_sets_the_variable_the_sources_read`.
5. **Job and step keys inside the workflow.** Not fixed by the change. *Not assumed*: every job and step is located by shape — the job invoking `ansible-playbook`, the job writing to the run summary, the expression-free `run:` step that enumerates the inventory and emits to `$GITHUB_OUTPUT`. A locator finding zero or two candidates fails with a message saying which property it keyed on.
6. **No library skill covers this stack's idiom** — GitHub Actions workflows asserted statically from Python `unittest`. `ai-toolkit:testing` and `python` were loaded; there is no Actions skill to load alongside them, so this pass proceeded on the testing floor plus this repository's own four existing modules as the idiom of record. Recorded rather than resolved.

## What the implementation step must make pass

Run, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

and expect 593 tests, OK. The red 32 map to tasks as follows:

- tasks **1.1 / 1.2** (the `connect_with` selection, identical in both sources) → `TestTheConnectionAddressIsSelectableAndDefaultsToThePublicOne` (3).
- tasks **2.1** (prod's `read_only_secret` becomes `HCLOUD_TOKEN_PROD`) → `TestNoDeclarationNamesTheWriteTokensOwnName.test_no_environment_declares_the_write_tokens_own_name` and `TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares.test_each_source_reads_the_name_its_declaration_states`. These are tasks 2.4's "present and red before 2.1 lands" — they are.
- tasks **2.2** → the two obsolete-test candidates above. Expect the first to go red at the same moment the two tests above go green.
- tasks **3.1–3.6** (the workflow) → the six workflow-shape classes and the nine discovery tests (25 red on the file's absence).
- tasks **3.4-0** (`ansible/requirements.txt`) → `TestTheConvergeRunsTheAnsibleTheRolesWereVerifiedUnder` (2). Both halves are required: the job's install step must **name** that manifest, resolved from its own working directory, and that manifest's `ansible-core` pin must equal `ansible/requirements-test.txt`'s (`2.21.3` today).
- tasks **3.4a** → `TestTheConvergeSelectsTheAddressTheInventoryReads` (1), which unblocks once 1.1/1.2 land.

Two shapes the discovery body must have for its nine tests to run at all, both of which tasks 3.2 already requires: it carries no `${{ }}` in its body, and it takes the dispatch input from the process environment rather than from the event.
