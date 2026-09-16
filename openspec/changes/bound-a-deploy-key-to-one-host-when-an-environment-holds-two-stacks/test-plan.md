# Test plan

Derived from this change's delta specifications at commit `f306e94`, the commit holding the approved plan, by an author other than whoever implements it and before any implementation existed. This file is not an artifact the OpenSpec schema knows about: it does not appear among `openspec instructions apply`'s context files and has to be read on purpose.

## Which of this project's three test commands this change owes tests under

The `.github/tests` row, and no other. `AGENTS.md`'s table gives the row's subject as "any property that is a static read of a committed file", and what this change alters is exactly that — which file a variable is written in, and how a required status check resolves it. The Molecule row covers what a role *does* on a host and this change alters no role behaviour; `tasks.md`'s closing note records the sweep of `ansible/roles/*/molecule/` that established it, including that no scenario asserts the `deploy_apps` refusal's message text. The `terraform test` row touches no module here.

- **Test command:** `python3 -m unittest discover --start-directory .github/tests`, run from the repository root.
- **Test-path glob:** `.github/tests/*.py`.
- **File written by this pass:** `.github/tests/test_a_deploy_key_is_bound_to_one_host.py` (new). Nothing else under the glob was edited, deleted or disabled.

## Baseline

Taken before any test was written, over the whole suite rather than a scope of it:

    python3 -m unittest discover --start-directory .github/tests
    Ran 1285 tests in 29.547s
    OK

Nothing failed beforehand, so every failure reported below is attributable to this pass.

After this pass, over the same command:

    Ran 1335 tests in 30.889s
    FAILED (failures=13)

+50 tests, and the 13 failures are all in the new module and all expected — see *Which assertions are red at authoring* below. No pre-existing test changed state.

## Naming a test so the runner can select it

Every test below is named `<module>.<Class>.<test>` and is selectable individually:

    python3 -m unittest discover --start-directory .github/tests -k <test name>

## Scenario accounting

25 `#### Scenario:` blocks across the two delta specs — 12 in `iac-cicd-pipeline`, 13 in `iac-host-configuration`. Every one is accounted for exactly once below.

All tests named are in `test_a_deploy_key_is_bound_to_one_host` unless stated otherwise.

### `iac-host-configuration` — ADDED *A Host-Scoped Variable Lives in the Host's Own Vars File* (4 scenarios)

| Scenario | Covered by |
|---|---|
| Two stacks share an environment | `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation.test_the_two_stacks_share_one_group_and_provision_two_hosts`; `.test_two_hosts_that_each_authorise_the_key_yield_no_offence`; `.test_an_entry_in_the_shared_environments_file_answers_neither_stack`; `.test_each_host_authorises_a_keypair_of_its_own`; and over the committed tree `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile.test_no_environments_file_supplies_the_deploy_key_authorisations`, `.test_a_hosts_own_file_supplies_its_authorisations`, `.test_no_public_half_is_authorised_on_two_hosts` |
| A value that is a property of the environment | `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile.test_the_environments_files_still_supply_an_environment_wide_baseline`; `.test_no_variable_is_supplied_from_both_an_environments_file_and_a_hosts` |
| A stack whose declared server has no vars file is reported | `TestEachStacksHostHasAVarsFileOfItsOwn.test_every_stack_carrying_a_declaration_declares_a_server_name`; `.test_every_stack_has_a_host_vars_file_named_for_its_server` |
| A host vars file is keyed on the name Terraform declares | `TestEachStacksHostHasAVarsFileOfItsOwn.test_no_host_vars_file_is_named_for_a_server_no_stack_declares`; discriminated by `TestTheseReadsDiscriminate.test_a_renamed_server_leaves_a_file_nothing_resolves_to`, which exercises both halves of a rename |

The requirement's own disclosure paragraph — the three placements it names as unmet, and the backlog entry it cites — carries no scenario and is covered by `TestTheUnmetPlacementsAreTheOnesTheRequirementNames.test_the_three_named_placements_are_where_the_requirement_says_they_are` and `.test_the_backlog_entry_the_requirement_cites_exists`.

### `iac-cicd-pipeline` — MODIFIED *Each Stack Declares Its Own Pipeline Configuration* (12 scenarios)

| Scenario | Covered by / uncovered with reason |
|---|---|
| A stack opting in without authorising the deploy on its host is refused | **Covered** — `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation.test_there_is_an_opt_in_to_check`; `.test_every_opted_in_stacks_own_host_authorises_the_platform_deploy_key`; discriminated by `TestTheseReadsDiscriminate.test_an_opt_in_without_an_authorisation_is_reported`, `.test_an_opt_in_whose_host_has_no_vars_file_is_reported`, `.test_an_opt_in_declaring_no_server_is_reported` |
| A host authorising the deploy key before the pipeline is pointed at it is accepted | **Covered** — `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation.test_a_host_prepared_before_its_deploy_path_is_not_reported`; discriminated by `TestTheseReadsDiscriminate.test_the_implication_holds_in_one_direction_only`, `.test_an_authorised_host_whose_stack_opts_in_is_not_reported` |
| Two stacks in one environment each owe their own authorisation | **Covered** — `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation.test_the_stack_whose_host_does_not_authorise_is_named`; `.test_the_other_hosts_authorisation_does_not_satisfy_it`; `.test_two_hosts_that_each_authorise_the_key_yield_no_offence`; discriminated by `TestTheseReadsDiscriminate.test_another_hosts_authorisation_does_not_answer_this_stacks_opt_in` |
| A new stack needs no workflow edit | **Uncovered by this pass** — wording unchanged by this delta. Covered on the trunk by `test_environment_agnostic_pipeline` and `test_terraform_stacks_are_the_iterated_unit`. |
| A converge reads its Ansible group from the declaration, not from the stack's name | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_a_stack_and_its_environment_are_named_separately`. |
| Two stacks declaring the same read-only secret are refused | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_environment_agnostic_pipeline`. |
| Two stacks declaring the same GitHub Environment are refused | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_the_github_environments_are_named_for_their_stacks`. |
| Two stacks declaring the same Ansible group are accepted | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_a_stack_and_its_environment_are_named_separately`. The new module's two-stack fixture nonetheless exercises it incidentally: `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation` builds exactly such a tree and asserts it is a legitimate one, in `.test_two_hosts_that_each_authorise_the_key_yield_no_offence`. |
| A declaration naming the write token's own name is refused | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_environment_agnostic_pipeline`. |
| A stack missing its declaration fails the pipeline | **Uncovered by this pass** — wording unchanged. |
| Discovery finding no stack fails rather than reporting success | **Uncovered by this pass** — wording unchanged. |
| A stack declaring nothing about the platform stack does not receive it | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_the_platform_stack_deploys_per_stack`. |

The nine unchanged scenarios are restated by the delta because OpenSpec restates a MODIFIED requirement whole, not because their behaviour changed. Writing new tests for them would duplicate coverage that already exists and that this change does not disturb; the existing tests named are ones this pass read, not ones it verified line by line.

### `iac-host-configuration` — MODIFIED *Dynamic Inventory via the hcloud Plugin, One Source per Stack* (9 scenarios)

| Scenario | Covered by / uncovered with reason |
|---|---|
| A stack that can be provisioned but not converged is reported | **Covered**, for the clause this delta adds ("or the server it declares has no host vars file") — `TestEachStacksHostHasAVarsFileOfItsOwn.test_every_stack_has_a_host_vars_file_named_for_its_server`; discriminated by `TestTheseReadsDiscriminate.test_a_stack_whose_declared_server_has_no_vars_file_is_reported`, `.test_a_stack_whose_server_has_a_vars_file_is_not_reported`, `.test_a_stack_naming_no_server_is_reported_rather_than_passed_over`. The scenario's two pre-existing clauses — no inventory source, no `group_vars` file — are covered on the trunk by `test_a_stack_and_its_environment_are_named_separately` and `test_host_converge_workflow`, and are unchanged. |
| A further stack is brought into inventory | **Covered**, for the clause this delta adds ("and a host vars file of its own") — `TestEachStacksHostHasAVarsFileOfItsOwn.test_every_stack_has_a_host_vars_file_named_for_its_server` asserts the obligation over every stack carrying a declaration, which is what "adding a stack adds one" amounts to statically; `TestTheseReadsDiscriminate.test_the_readers_resolve_a_server_name_out_of_a_synthetic_tree` exercises it over a tree carrying a stack the repository does not have. The "without editing any existing stack's inventory source" half is unchanged and covered on the trunk. |
| Inventory resolved live from Hetzner | **Uncovered** — wording unchanged, and not statically assertable: it is a property of a live plugin run. `tasks.md` 6.2 carries it as a run. |
| Hosts are grouped by every axis their labels carry | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_a_stack_and_its_environment_are_named_separately`. |
| Disabled server yields no stale inventory entry | **Uncovered** — wording unchanged, and a property of a live plugin run rather than of a committed file. |
| A stack's source reaches only its own project | **Uncovered by this pass** — wording unchanged. |
| A source's name is not read as its group's name | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_a_stack_and_its_environment_are_named_separately`. |
| An inventory source cannot authenticate | **Uncovered** — wording unchanged, and a property of a live run. |
| A source's credential variable is the name the stack declares | **Uncovered by this pass** — wording unchanged. Covered on the trunk by `test_a_stack_and_its_environment_are_named_separately`. |

## Assertion classification

Every assertion in the new module carries its own SPECIFIED / DERIVED annotation in its docstring. Summarised:

**SPECIFIED** — everything in `TestEachStacksHostHasAVarsFileOfItsOwn`, `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile`, `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile`, `TestTheUnmetPlacementsAreTheOnesTheRequirementNames`, `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation` and `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation`. Each traces to SHALL text or to a scenario, quoted in the docstring.

**DERIVED**, each named here so it is visible for review rather than indistinguishable from a stated requirement:

- `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile` (both tests). No scenario states a message, and the ADDED requirement says outright that nothing in it obliges a role to change. This traces to `tasks.md` 2.4: the `fail_msg` is what an operator reads *as* the converge refuses, so a stale one sends them to edit a file that no longer supplies the variable. Asserted on the directory name the message carries (`group_vars` / `host_vars`) rather than on a whole path, so the wording stays the implementing author's.
- The module-level constants `DEPLOY_APPS_FIELD`, `APPLICATION_NAME_FIELD`, `APPLICATION_KEY_FIELD`, `PLATFORM_APPLICATION` and `HOST_VARS_DIRNAME` — the requirement fixes the *placement* and not the schema or the directory. Each carries its derivation in a comment beside it.
- `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation.test_two_hosts_that_each_authorise_the_key_yield_no_offence` and the "not reported" tests in `TestTheseReadsDiscriminate` are converses no scenario states. They are the guard against a check that refuses every two-stack tree, which would satisfy the scenario while making the second tenant impossible to add.

**Deliberately untested**, recorded with reasons:

- **That Ansible loads `ansible/inventory/host_vars/` from beside a plugin inventory source.** It is a property of a program's behaviour, not of a committed file, and this suite may make no network call and hold no credential. `tasks.md` 1.1 carries it as a measurement against the live plugin, and **every assertion in the new module is conditional on it**: if `host_vars/` is not loaded from there, the file these assertions read is the wrong file and a green run says nothing. `design.md`'s *Open question for implementation* says a negative result stops the change at `plan`.
- **That a host variable shadows a group variable of the same name.** `tasks.md` 1.2's measurement. The module asserts the two sets are *disjoint*, which is what the requirement obliges, rather than asserting a precedence it does not.
- **The prose sweep of `tasks.md` 4.1 to 4.5** — `docs/naming-conventions.md`, `docs/bootstrap-a-new-host.md`, `docs/onboard-an-application.md`, both role READMEs, and `ansible/playbooks/host-baseline.yml`'s commentary. No scenario states any of it, an assertion over prose wording would be brittle against a legitimate rewrite, and `tasks.md` 4.5 already makes the sweep a task with a stated grep. The one prose surface asserted is the two `fail_msg`s, because that sentence is read at the moment a converge refuses and nothing else in the repository would catch a stale one.
- **That no key is rotated.** `tasks.md` 2.1 and 2.2 verify the public halves by `ssh-keygen -lf` fingerprint, which spawns a binary this suite's own constraints forbid. `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile.test_no_public_half_is_authorised_on_two_hosts` asserts the invariant that matters statically; that the strings did not change is a task-list verification and `tasks.md` 7.2's ship-confirm gate.
- **Repository settings** — whether a GitHub Environment exists, holds a secret, or requires a reviewer. Unreadable without a network call.

## Fixture-driven discriminators

Every assertion in the new module is a static read of a committed file, so a predicate that reported no offence whatever it was given would satisfy all of them. `TestTheseReadsDiscriminate` runs each predicate over material the module supplies, carrying the defect that predicate names and — separately — carrying none. It covers the loader (`inventory_variables`), the file-existence predicates (`missing_host_vars_offences`, `orphaned_host_vars_offences`), the placement predicates (`group_vars_authorisation_offences`, `repeated_variable_offences`), the key-sharing predicate (`duplicate_public_half_offences`), the cross-check (`opt_in_authorisation_offences`), the readers themselves over a synthetic tree, and the role-message reader (`deploy_apps_refusal_messages`).

**One discriminator came back negative during this pass and the check was repaired rather than reported.** The role-message check was first written line-wise — `group_vars` and `deploy_apps` appearing on one line — and run over the committed roles it reported nothing, because both roles write the message as a *folded* YAML scalar and the two names never share a line. That is the fourth failure state's second branch: a check asserting nothing over exactly the defect it exists to catch. It was replaced with `deploy_apps_refusal_messages`, which reads the message out of the parsed task list and selects it by the assertion's own `that:` clauses — which also keeps the two *other* refusals in those files, over the heartbeat ping key and the hardening CIDRs, from being read as this defect. `TestTheseReadsDiscriminate.test_a_refusal_naming_the_environments_file_is_read_out_of_a_folded_scalar` is the case that decides it, and is written so a future return to a line-wise read goes red.

Every discriminator was executed here, so none is owed as "written but not run".

## Which assertions are red at authoring, and on which property

Recorded per the rule that an observed red-to-green transition is what establishes a check discriminates on real content rather than on a fixture. All 13 below failed on the run reported in *Baseline*; each is expected to go green as the change lands, and none was repaired.

| Test | The property it is red on |
|---|---|
| `TestEachStacksHostHasAVarsFileOfItsOwn.test_every_stack_has_a_host_vars_file_named_for_its_server` | Neither `main-production` nor `main-staging` has a host vars file |
| `TestEachStacksHostHasAVarsFileOfItsOwn.test_no_host_vars_file_is_named_for_a_server_no_stack_declares` | `ansible/inventory/host_vars/` does not exist |
| `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile.test_no_environments_file_supplies_the_deploy_key_authorisations` | `group_vars/production.yml` and `group_vars/staging.yml` both supply `deploy_apps` |
| `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile.test_a_hosts_own_file_supplies_its_authorisations` | No host vars file exists to supply them |
| `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile.test_no_public_half_is_authorised_on_two_hosts` | Reads nothing; guarded to say so |
| `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile.test_no_variable_is_supplied_from_both_an_environments_file_and_a_hosts` | Guarded on host vars files existing |
| `TestTheUnmetPlacementsAreTheOnesTheRequirementNames.test_the_backlog_entry_the_requirement_cites_exists` | `docs/backlog.md` carries no `put-the-remaining-host-scoped-variables-on-the-host-axis` entry (`tasks.md` 5.1) |
| `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation.test_every_opted_in_stacks_own_host_authorises_the_platform_deploy_key` | Both opted-in stacks resolve to a host vars file that does not exist |
| `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation.test_a_host_prepared_before_its_deploy_path_is_not_reported` | No host authorises the platform key in its own file |
| `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile.test_neither_role_sends_an_operator_to_the_environments_file` (×2 subtests) | Both roles' `deploy_apps` `fail_msg` names `ansible/inventory/group_vars/<environment>.yml` (`tasks.md` 2.4) |
| `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile.test_each_role_names_the_hosts_own_file` (×2 subtests) | Neither message names a host vars file |

Green from the moment written, and stated so their passing is not mistaken for coverage of the change: `TestEachStacksHostHasAVarsFileOfItsOwn.test_every_stack_carrying_a_declaration_declares_a_server_name`, `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile.test_the_environments_files_still_supply_an_environment_wide_baseline`, `TestTheUnmetPlacementsAreTheOnesTheRequirementNames.test_the_three_named_placements_are_where_the_requirement_says_they_are`, `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation.test_there_is_an_opt_in_to_check`, the whole of `TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation` (it reads fixtures, not the tree) and of `TestTheseReadsDiscriminate`.

## Obsolete tests

**These are candidates for human confirmation, not conclusions.** Nothing in this pass edited, deleted or disabled any of them. `tasks.md` 3.1 is the task that re-points them, and this list is what it must carry over rather than drop.

**Search bound:** `.github/tests/*.py` only — the dispatched test-path glob — by grepping `deploy_apps`, `group_vars` and `host_vars` across every module in it and accounting for every hit. No earlier `test-plan.md` was supplied to this pass, so no scenario-to-test mapping was available to draw on beyond the modules themselves.

All entries are in `.github/tests/test_the_platform_stack_deploys_per_stack.py`.

| Test | Superseded by | Evidence |
|---|---|---|
| `TestAStackOptingInAuthorisesTheDeployOnItsHost.test_every_opted_in_stacks_host_authorises_the_platform_deploy_key` | `iac-cicd-pipeline` MODIFIED *Each Stack Declares Its Own Pipeline Configuration* — the authorisation "SHALL NOT be the `group_vars` file of the declared Ansible group" | Calls `deploy_authorisation_offences(platform_opt_ins(), {…declaration.target_group…}, authorised_applications())`; `authorised_applications()` globs `ansible/inventory/group_vars/*.yml`. Its own docstring quotes the retired wording, "in the `group_vars` file of the Ansible group it declares". Goes red the moment `deploy_apps` leaves `group_vars`. |
| `TestAStackOptingInAuthorisesTheDeployOnItsHost.test_a_host_prepared_before_its_deploy_path_is_not_reported` | Same | Asserts `prepared` is non-empty over `authorised_applications()`, whose message reads "no group_vars file authorises the platform deploy key at all". False the moment the move lands. |
| `TestOneStacksKeyDoesNotReachAnotherStacksHost.test_no_two_hosts_authorise_the_same_platform_deploy_key` | `iac-host-configuration` ADDED *A Host-Scoped Variable Lives in the Host's Own Vars File* — "one leaked private half SHALL reach one host" | Calls `shared_key_offences(authorised_keys())`; `authorised_keys()` globs `ansible/inventory/group_vars/*.yml` and keys its result on the **group** stem. `shared_key_offences` returns "reads nothing" for an empty mapping, so this goes red on the move. The new module's `.test_no_public_half_is_authorised_on_two_hosts` is the per-host successor, and is broader (every application, not the platform stack alone). |
| `TestAStackOptingInAuthorisesTheDeployOnItsHost.test_there_is_an_opt_in_to_check` | Not superseded in substance | Named here only because 3.1 will move the class around it. It reads the declaration side alone and stays correct. |
| `TestTheseReadsDiscriminate.test_a_vaulted_group_vars_file_is_read_rather_than_refused` | Same requirement | Fixture writes `staging.yml` carrying `deploy_apps` beside a `!vault` block, and asserts through `group_variables`. The loader stays needed; the fixture's *subject* is the retired placement. It is a fixture read, so it does not go red on its own — which is why it is listed: nothing would report it. |
| `TestTheseReadsDiscriminate.test_an_unknown_tag_refuses_rather_than_yielding_an_empty_document` | Same | Same fixture family; `UnreadableGroupVars` and `group_variables` are the names 3.1 re-points. |
| `TestTheseReadsDiscriminate.test_an_opt_in_without_an_authorisation_is_reported` | Same | `self.assertIn("ansible/inventory/group_vars/staging.yml", offences[0])` — asserts the offence message names the retired file by path. |
| `TestTheseReadsDiscriminate.test_an_opt_in_whose_group_has_no_group_vars_file_is_reported` | Same | Named for the retired resolution; passes `{"main-staging": "staging"}` as the group mapping. |
| `TestTheseReadsDiscriminate.test_an_opt_in_declaring_no_group_is_reported` | Same | Passes `{"main-staging": None}` as a declared **group**; under the new path the missing value is a declared **server**. |
| `TestTheseReadsDiscriminate.test_an_authorised_host_whose_stack_opts_in_is_not_reported` | Same | Third argument is `{"staging": {"platform"}}`, keyed on the group. |
| `TestTheseReadsDiscriminate.test_the_implication_holds_in_one_direction_only` | Same | Keyed on `{"staging": …, "production": …}` — groups. The one-directional rule itself is unchanged and its successor is in the new module. |
| `TestTheseReadsDiscriminate.test_two_hosts_authorising_one_key_are_reported` | `iac-host-configuration` ADDED requirement | `shared_key_offences({"production": …, "staging": …})` — the mapping's keys are groups, which is the proxy this change retires. |
| `TestTheseReadsDiscriminate.test_two_hosts_authorising_two_keys_are_not_reported` | Same | Same keying. |
| `TestTheseReadsDiscriminate.test_no_authorised_key_at_all_is_reported_rather_than_passed_over` | Same | Guards the group-keyed reader. |

Also affected but **not** obsolete, and named so 3.4's sweep can account for them without re-deriving:

- `.github/tests/test_ci_configuration.py`'s `EXCLUDED_CONFIGURATION_PATHS`, which names `ansible/inventory/group_vars/production.yml` as a path the Molecule trigger deliberately does not select. That file still exists after the change, and the exclusion is `ansible/inventory/**`, which covers `host_vars/` too. No edit is implied.
- `.github/tests/test_ci_configuration.py`'s Molecule fixture supplying `deploy_apps: []` in a scenario `verify.yml`. That is a scenario supplying a role input, unrelated to which inventory file supplies it in production.
- `.github/tests/test_a_stack_and_its_environment_are_named_separately.py`'s `group_vars` fixtures and `test_the_group_vars_file_each_stack_declares_exists`. The `group_vars` obligation is **retained** by the MODIFIED *Dynamic Inventory* requirement — the host vars file is added beside it, not in place of it.
- `.github/tests/test_host_converge_workflow.py`'s converge-discovery fixtures, which check a stack's `group_vars` file. Unchanged for the same reason; whether the converge workflow's own discovery should also check the host vars file is not something these deltas oblige — `tasks.md` 3.3 places that check in `.github/tests`.

**No obsolete-test candidate was found outside `test_the_platform_stack_deploys_per_stack.py`.** That is "none was found by this search", bounded as stated above, rather than "no such test exists".

## Unresolved project questions

Recorded because this pass had no channel to ask on. Each names the assumption taken and what depends on it.

1. **The directory a host's own vars file sits in.** The ADDED requirement fixes the file's *key* — "named for the Hetzner server name that host carries" — and not its directory. **Assumption taken:** `ansible/inventory/host_vars/<server>.yml`. Supported, but not stated: `tasks.md` 1.1 writes exactly `ansible/inventory/host_vars/main-staging.yml`, and `.github/tests/test_host_converge_workflow.py` already names `ansible/inventory/host_vars/` as one of the two places a vaulted inventory variable may live. `AGENTS.md` records no convention either way. **Depends on it:** every test reading `host_vars_documents()` — that is, all of `TestEachStacksHostHasAVarsFileOfItsOwn`, `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile`, `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation`, and `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile.test_no_variable_is_supplied_from_both_an_environments_file_and_a_hosts`.
2. **That the `deploy_apps` schema moves unchanged.** `name` and `public_key` per entry. **Assumption taken:** it does, from `tasks.md` 2.1's "moved verbatim — both entries, their comments and their public halves unchanged". **Depends on it:** every test reading an authorisation, and the `_authorisations_of` reader.
3. **What the corrected `fail_msg` says.** `tasks.md` 2.4 requires the correction and fixes no wording. **Assumption taken:** the corrected message names `host_vars` and no longer names `group_vars`. Asserted on the directory name rather than a whole path, so a message spelling the file either way satisfies it. **Depends on it:** `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile` (both tests). This is the only DERIVED class in the module and the one a reviewer should look at first if a legitimate wording fails it.
4. **Whether `ansible/inventory/host_vars/` needs a place in any CI path filter.** `AGENTS.md` records the Molecule trigger's exclusions and the static suite's scope, and this pass could not establish whether the `.github/tests` suite's own trigger enumerates paths. **Assumption taken:** none needed — the Molecule filter excludes `ansible/inventory/**` wholesale, and no assertion in the suite enumerates what the static suite reads. **Depends on it:** nothing in the new module; recorded so the implementer checks it rather than inheriting the assumption.

## What the implementation step must make pass

Run `python3 -m unittest discover --start-directory .github/tests` from the repository root. The 13 failures listed above are the ones this change must turn green, and they map onto `tasks.md` as:

- 2.1, 2.2 — the two host vars files, which turn the existence, authorisation, opt-in and disjointness tests green.
- 2.3 — removing `deploy_apps` from both `group_vars` files, which turns `test_no_environments_file_supplies_the_deploy_key_authorisations` green.
- 2.4 — the two `fail_msg`s, which turn `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile` green.
- 5.1 — the backlog entry, which turns `test_the_backlog_entry_the_requirement_cites_exists` green.
- 3.1 to 3.4 remain the implementer's own work in `test_the_platform_stack_deploys_per_stack.py`, guided by the obsolete list above. The new module does not replace that module: it adds the per-host resolution beside it, and 3.1 is what stops the retired per-group one from failing.

`tasks.md` 6.1 asks the run's **count** to be read as well as its result: 1285 before this pass, 1335 after it, and a run reporting 1285 has not picked the new module up.
