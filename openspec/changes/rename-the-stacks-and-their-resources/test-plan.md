# Test plan — rename-the-stacks-and-their-resources

Written by an author other than whoever implements this change, from the approved delta specifications at commit `b08a71e` and from `proposal.md`, `design.md` and `tasks.md` at that commit. No implementation source for the behaviour under test was read: the `MODIFIED` operations were established by comparing each delta against the requirement as it currently stands in `openspec/specs/`, not by reading the code that satisfies it today.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among the context files `openspec instructions apply` lists, and it has to be read on purpose. Whoever implements this change should read it before starting: it names every test that must go green, the tests that must be re-pointed rather than deleted, and the assumptions these tests took about names the implementation is free to choose.

**This pass adds tests and never subtracts.** No existing test was edited, deleted or disabled. Two existing `.tftest.hcl` variable blocks gained a value for a newly required module input — that is supplying an input, not weakening an assertion, and it is stated in full under *What was changed in existing test files* below. No implementation was written: the `hostname` role does not exist, and creating it to make its scenarios execute would have been writing the code under test.

---

## Baseline

Taken on this working tree at commit `b08a71e`, before any test was written, under all three of this project's test commands.

| Command | Where from | Result |
|---|---|---|
| `python3 -m unittest discover --start-directory .github/tests` | repository root | **784 tests, OK** |
| `terraform init -backend=false && terraform test` | `terraform/modules/server/` | **18 passed, 0 failed** |
| `terraform init -backend=false && terraform test` | `terraform/modules/volume/` | **8 passed, 0 failed** |
| `ansible/scripts/run-molecule test --all` | `ansible/roles/hostname/` | **not run, and why:** the role does not exist. Its scenarios were written against the delta specification and cannot execute until it does, which is the expected outcome of deriving tests before an implementation exists — see *The Host's Own Name Is Set by the Converge* in the coverage tables, and unresolved question 4. |

`terraform test` needed `terraform init -backend=false` in each module directory first — a fresh working tree carries no provider cache, and without it the command fails with *"there is no package for registry.terraform.io/hetznercloud/hcloud 1.68.0 cached in .terraform/providers"*, which reads as a broken test rather than an unprovisioned tree. The `.terraform/` directories that run created are the test command's own side effect and are gitignored.

After this pass, with nothing implemented:

| Command | Result | Reading |
|---|---|---|
| `.github/tests` | **838 tests, 35 failures** | 784 baseline green, +54 added, 35 of them red. Every failure is in one of the two new modules; no existing test changed state. |
| `terraform test` (server) | **19 passed, 3 failed, 2 skipped** | The 18 baseline runs still pass. Terraform skips the remaining runs in a file once one fails, which is why the two new files are separate. |
| `terraform test` (volume) | **8 passed, 1 failed, 3 skipped** | The 8 baseline runs still pass. |

---

## Scenario coverage

Every `#### Scenario:` block in the seven delta specifications is accounted for exactly once. **84 scenarios, 84 accounted for.**

The four `REMOVED` requirement blocks — *Environment and Module Folder Structure*, *Each Environment Has a Dedicated Hetzner Cloud Project*, *Each Environment Declares Its Own Pipeline Configuration*, *Dynamic Inventory via hcloud Plugin* — carry no scenarios of their own: each states only a **Reason** and a **Migration** naming the requirement that replaces it. They contribute nothing to the count, and the scenarios they held reappear under the `ADDED` requirements below, some renamed. That renaming is the whole purpose of the `REMOVED`+`ADDED` pairing (design.md decision 3).

Three shorthands are used in the tables:

- **NEW** — a test this pass wrote. Red until the implementation lands, unless noted.
- **EXISTING** — a test already on the trunk that covers the scenario and that this change does not disturb. Named so that the count is a count rather than a judgment.
- **UNCOVERED** — accounted for, with the reason.

### `iac-repo-foundations` — 8 scenarios

| Scenario | Covered by |
|---|---|
| A stack directory consumes a shared module | EXISTING `test_a_second_environment.TestEveryEnvironmentConsumesTheSharedModules` (reads module calls from whatever directories exist, so it follows the rename). NEW `test_a_stack_and_its_environment_are_named_separately.TestTheTreeCarriesTheRenamedValues.test_the_stack_directories_are_named_for_their_tenant_and_environment` for the renamed path itself. |
| Adding a stack does not require restructuring | **UNCOVERED.** "without moving or renaming existing files" is a property of a diff, not of a tree; no static read of the committed files can see it. Recorded as uncovered by the earlier change that introduced the scenario, for the same reason. The other half — that adding a stack needs no workflow edit — is covered under `iac-cicd-pipeline` below. |
| A stack's name is not read as its environment | NEW `…TestEveryStackDeclaresTheGroupItConverges.test_no_stacks_name_and_declared_group_are_assumed_equal`. |
| A shared module change reaches every stack without an imposed order | EXISTING `test_a_second_environment.TestNoEnvironmentsApplyWaitsOnAnother`. Unchanged by this delta. |
| Promotion ordering is exercised at the approval, not by the workflow | **UNCOVERED.** It is a discipline available to a human approver, stated by the requirement itself "as what holds rather than as what is guaranteed". No committed file records it and no test command can observe it. |
| Local state is never staged | EXISTING `.gitignore` coverage in `test_a_second_environment`. Unchanged. |
| CI has the environment configuration it needs | NEW, indirectly: `…TestTheTreeCarriesTheRenamedValues.test_each_stacks_server_is_named_for_its_stack` and `…test_each_stacks_volume_is_named_on_the_rank_axis` read `terraform/stacks/main-production/terraform.tfvars` out of the checkout; a tfvars absent from the renamed directory fails them. The scenario is reached by this delta for its body naming the renamed path, not for a new obligation. |
| Secret-bearing variable file is not committable | EXISTING `.gitignore` coverage. Unchanged. |

### `iac-state-management` — 7 scenarios

| Scenario | Covered by |
|---|---|
| One stack's credentials do not reach another's project | **UNCOVERED.** A Hetzner API token's scope is not a committed file and is reachable only by an API call this suite is forbidden to make. The checkable proxy — that no two stacks declare the same read-only secret — is EXISTING `test_environment_agnostic_pipeline` coverage, re-asserted by NEW `…TestEveryStackDeclaresTheGroupItConverges.test_the_other_two_required_fields_are_still_declared_and_distinct` because this change edits every declaration. |
| An ungated stack cannot reach a reviewed stack's resources | **UNCOVERED.** Repository settings plus a token's project scope. Same reason. |
| Two stacks may name a resource identically | NEW `…TestTheTreeCarriesTheRenamedValues.test_each_stacks_volume_is_named_on_the_rank_axis` — both stacks name their volume `main`, which is the scenario's own example. |
| State is not stored locally | EXISTING `test_a_second_environment.TestEachEnvironmentHasAWorkspaceOfItsOwn` and `test_terraform_stacks_are_the_iterated_unit`. Unchanged. |
| Two environments do not share a workspace | EXISTING `test_terraform_stacks_are_the_iterated_unit.TestEachStackNamesAWorkspaceDerivedFromItsOwnName.test_no_two_stacks_name_the_same_workspace`. **Survives this change**; its sibling in the same class does not — see the obsolete list. |
| Plan and apply run outside HCP Terraform's own execution | EXISTING coverage of the `cloud` block. Unchanged. |
| Concurrent apply attempts are serialized | **UNCOVERED.** HCP Terraform's own locking behaviour; no static read reaches it. This delta touches the scenario only for the renamed path in its body. |

### `iac-cicd-pipeline` — 30 scenarios

*Each Stack Declares Its Own Pipeline Configuration* (ADDED), 8:

| Scenario | Covered by |
|---|---|
| A new stack needs no workflow edit | EXISTING `test_terraform_stacks_are_the_iterated_unit.TestDiscoveryIteratesTheStackRoot` and `test_ci_configuration`'s no-literal assertions. NEW, in the strongest available form: `…TestHostConvergeDiscoveryReadsTheDeclaredGroup` runs the real discovery body over stacks called `alpha-live` and `bravo-live`, names no workflow has ever seen. |
| A converge reads its Ansible group from the declaration, not from the stack's name | NEW `…TestHostConvergeDiscoveryReadsTheDeclaredGroup.test_a_stack_whose_group_differs_from_its_name_is_accepted_and_emitted`, `…TestTheConvergeSeparatesTheTwoHandles.test_the_inventory_path_and_the_group_are_taken_from_different_handles` and `…test_the_play_variable_is_fed_from_the_declared_group`. |
| Two stacks declaring the same read-only secret are refused | EXISTING `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed` and `test_host_converge_workflow.TestHostConvergeDiscoveryFailsClosed`. Carried across unchanged by the delta. |
| Two stacks declaring the same GitHub Environment are refused | EXISTING, same classes. |
| Two stacks declaring the same Ansible group are accepted | NEW `…TestHostConvergeDiscoveryReadsTheDeclaredGroup.test_two_stacks_declaring_one_group_are_accepted`, and NEW `…TestEveryStackDeclaresTheGroupItConverges.test_the_declared_group_carries_no_distinctness_obligation` for the static half. |
| A declaration naming the write token's own name is refused | EXISTING `test_host_converge_workflow.TestNoDeclarationNamesTheWriteTokensOwnName`. |
| A stack missing its declaration fails the pipeline | EXISTING for the absent-declaration half; NEW `…TestHostConvergeDiscoveryReadsTheDeclaredGroup.test_a_stack_declaring_no_group_is_refused_by_name` for the half this delta adds — "or one lacking a field the running workflow requires". |
| Discovery finding no stack fails rather than reporting success | EXISTING `test_environment_agnostic_pipeline.TestDiscoveryFailsClosed`. |

*Credential Scoping by Privilege* (MODIFIED), 5 — **all EXISTING**, in `test_environment_agnostic_pipeline` and `test_ci_configuration`. This requirement is reached by the delta only because it cross-references a renamed requirement by title; no obligation and no scenario changes. Listed individually so the count is a count: *Plan jobs receive only a read-only Hetzner token*; *A plan job holds no credential for another environment*; *An Environment omitting the write token does not apply with another's*; *Apply job receives the read-write Hetzner token only after approval*; *Pull request validation requires no manual approval*.

*Destroy Policy Gate* (MODIFIED), 6 — **all EXISTING**, in `test_ci_configuration.TestDestroyPolicyGateFailsClosed` and `test_planned_environment_apply_stage`: *Unintended resource replacement blocks the pipeline*; *Deliberate teardown is possible with explicit acknowledgement*; *A disposable environment is destroyed without an override label*; *An environment declaring nothing is gated*; *An uninspectable plan blocks the pipeline*; *Drift-detection plan is not affected by this gate*.

The paragraph this delta adds to that requirement — that a rename is not a ground for the override label — is recorded as **deliberately untested**, on the requirement's own grounds: "This paragraph states the discipline rather than adding a mechanism." The gate cannot tell a rename from a rehearsed teardown, and the judgment it describes is the approver's. The change's own tasks.md 9.2 is where it is exercised.

*Gated Production Apply Applies the Reviewed Plan* (MODIFIED), 11 — **all EXISTING**, in `test_planned_environment_apply_stage` and `test_terraform_stacks_are_the_iterated_unit.TestThePathRuleAndItsConsumersFollowTheStackRoot`, which derive their paths from the stack directories that exist rather than from literals and so follow the rename: *Merge does not apply immediately*; *A merge affecting one environment raises no other environment's approval*; *A shared module change reaches every environment*; *A plan its own gate refused is not applied*; *One environment's failed plan does not block another's apply*; *An unresolvable set of planned environments fails the run*; *Reviewer sees the exact diff before approving*; *Applied changes match the approved plan*; *Apply credentials are inaccessible before approval*; *An unresolvable set of affected environments fails the run*; *A merge that cannot change infrastructure raises no approval request*. The delta reaches this requirement for two scenario bodies naming the renamed stack directories; NEW `…test_the_stack_directories_are_named_for_their_tenant_and_environment` is what fails if the tree and those bodies disagree.

### `iac-safety-hardening` — 7 scenarios

| Scenario | Covered by |
|---|---|
| Prod server is protected against console deletion | EXISTING `terraform/modules/server/tests/protection.tftest.hcl`, kept executable by this pass. The console refusal itself is server-side provider behaviour and is **UNCOVERED**, as that file's own header already records; what is covered is the precondition — the attribute is parameterised and passed through. |
| Prod volume is protected against console deletion | EXISTING `terraform/modules/volume/tests/delete_protection.tftest.hcl`, same reading. |
| Shared module remains reusable by a future non-prod environment | EXISTING, both modules' `delete_protection = false` runs. |
| Server is created with backups enabled | EXISTING `terraform/modules/server/tests/creation.tftest.hcl` (`plan_backups_default_to_true`, `plan_backups_can_be_disabled`). That the production stack passes `backups = true` is **UNCOVERED** — a stack-level composition outside the module test glob, as recorded below. |
| Prod resources are labeled | NEW `terraform/modules/server/tests/tenant_label.tftest.hcl` for the module's obligation; NEW `…TestTheTreeCarriesTheRenamedValues.test_each_stack_declares_the_environment_axis_spelled_in_full` and `…test_each_stack_passes_the_tenant_axis_to_its_modules` for the stack's. |
| Prod volume is labeled | NEW `terraform/modules/volume/tests/tenant.tftest.hcl`, plus the same two stack-level tests. |
| An SSH key a stack owns directly is labeled | NEW `…TestTheTreeCarriesTheRenamedValues.test_each_stacks_ssh_key_is_named_and_labelled_like_every_other_resource`. |

### `iac-server-lifecycle` — 4 scenarios

All four — *Toggle enabled creates the server*, *Toggle disabled creates nothing*, *Toggle disabled also removes resources coupled to the server*, *Re-enabling requires no lost configuration* — are **UNCOVERED at the stack level and covered at the module level**, unchanged by this delta, which alters only the stack's name in their bodies. `terraform/modules/server/tests/creation.tftest.hcl` covers what the module creates; the `count = var.server_enabled ? 1 : 0` composition lives in the stack directory, which is a Terraform root module and outside the `terraform/modules/<name>/tests/` glob this project's test command reaches. The earlier change that wrote these scenarios recorded the same gap.

### `iac-data-volumes` — 6 scenarios

| Scenario | Covered by |
|---|---|
| Toggle enabled creates the volume | EXISTING `terraform/modules/volume/tests/creation.tftest.hcl` at module level; the stack-level double toggle is **UNCOVERED** for the reason above. |
| Volume toggle disabled creates nothing | **UNCOVERED**, same reason. |
| Disabling the server also removes the volume | **UNCOVERED**, same reason. |
| Re-enabling requires no lost configuration | **UNCOVERED**, same reason — it is a property of a plan against existing state. |
| Volume is created already attached | EXISTING `creation.tftest.hcl` (`plan_attaches_to_server_at_creation`). |
| Volume shares the server's location | **UNCOVERED.** `location` is provider-computed and unknown at plan time, as that file's header records. |

The new obligation this delta adds to *Conditional Prod Volume Creation* — that the volume's name not carry the role of its consumer, and that the mount not be disturbed by the rename — is covered by NEW `…TestTheTreeCarriesTheRenamedValues.test_each_stacks_volume_is_named_on_the_rank_axis` and NEW `…TestTheMountIsNotKeyedOnTheVolumesName`.

### `iac-host-configuration` — 22 scenarios

*Dynamic Inventory via the hcloud Plugin, One Source per Stack* (ADDED), 9:

| Scenario | Covered by |
|---|---|
| Inventory resolved live from Hetzner | EXISTING `test_host_configuration_names_its_environment.TestInventoryIsResolvedLiveRatherThanFromACommittedFile`. |
| Hosts are grouped by every axis their labels carry | NEW `…TestASourcesNameIsNotReadAsItsGroupsName.test_every_source_groups_hosts_by_both_axes`. |
| Disabled server yields no stale inventory entry | **UNCOVERED.** The `hcloud` plugin resolving nothing for an absent server is live API behaviour. |
| A stack's source reaches only its own project | EXISTING `test_host_configuration_names_its_environment.TestEachEnvironmentHasAnInventorySourceOfItsOwn` (per-source credential distinctness). The project boundary itself is **UNCOVERED**, per `iac-state-management` above. |
| A source's name is not read as its group's name | NEW `…TestASourcesNameIsNotReadAsItsGroupsName.test_the_group_vars_file_each_stack_declares_exists`, `…test_no_group_vars_file_is_named_for_a_stack_that_is_not_a_group`, and `…TestTheConvergeSeparatesTheTwoHandles.test_the_inventory_path_and_the_group_are_taken_from_different_handles`. |
| A further stack is brought into inventory | EXISTING `test_host_configuration_names_its_environment.TestAFurtherEnvironmentIsAddedRatherThanEditedIn`; NEW `…test_two_stacks_declaring_one_group_are_accepted` adds a second stack to a synthetic tree without editing the first's source. |
| An inventory source cannot authenticate | EXISTING `ansible.cfg`'s `any_unparsed_is_failed` assertion. The run's actual failure is live behaviour and **UNCOVERED**. |
| A stack that can be provisioned but not converged is reported | NEW `…TestASourcesNameIsNotReadAsItsGroupsName.test_every_stack_has_an_inventory_source_named_for_the_stack` and NEW `…TestHostConvergeDiscoveryReadsTheDeclaredGroup.test_the_group_vars_cross_check_follows_the_declared_group`. |
| A source's credential variable is the name the stack declares | EXISTING `test_host_converge_workflow.TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares`. |

*The Host's Own Name Is Set by the Converge* (ADDED), 6 — the only requirement in this change whose scenarios are covered by Molecule:

| Scenario | Covered by |
|---|---|
| A host renamed in the provisioning layer answers to the new name after a converge | NEW Molecule `ansible/roles/hostname/molecule/default/` — `verify.yml`'s *Assert the host answers to the name this repository states* and *Assert the name is no longer the one the instance was created with*. The instance is created as `created-elsewhere`, which is what gives the run something to rename. NEW `…TestTheReportedNameIsPinnedBeforeTheHostIsRenamed.test_the_baseline_play_runs_the_role_that_sets_the_hosts_own_name` for the play that runs it. |
| The host's name carries the company and the reported name does not | NEW Molecule `default/verify.yml`'s *Assert the name carries the company and the inventory identity, in that order* for the first half; NEW `test_the_hosts_own_name_is_set_by_the_converge.TestTheReportedNameIsPinnedRatherThanInherited.test_the_pinned_name_is_the_hosts_inventory_identity_and_carries_no_company` for the second, which Molecule cannot reach — `tailscale` has no scenario. |
| The reported name is pinned before the host's own name changes | NEW `…TestTheReportedNameIsPinnedBeforeTheHostIsRenamed.test_the_hostname_role_runs_after_the_role_that_pins_the_reported_name`. This is tasks.md 5.7's assertion, and the only thing besides a comment holding the invariant the plan's own review found. |
| The host resolves the name it was just given | NEW Molecule `default/verify.yml` — the `/etc/hosts` loopback assertion, the `getent` assertion and the *no unresolved-host warning* assertion. NEW `…TestTheHostnameRoleRefusesAndResolves.test_the_role_sets_the_loopback_entry_as_well_as_the_name` for the shape. |
| A host already on the private network has its reported name corrected | NEW `…TestTheReportedNameIsPinnedRatherThanInherited.test_a_host_already_on_the_private_network_has_its_reported_name_corrected` and `…test_the_correcting_task_reports_its_own_changed_state`. **Not covered behaviourally**: it would need a container running `tailscaled` and joining a real tailnet, which tasks.md 5.5 declines. The converge's own play recap, read by a human, is what establishes the effect. |
| An absent company variable refuses | NEW Molecule `ansible/roles/hostname/molecule/absent-company/`, in the shape `hardening/molecule/absent-ssh-cidrs` established. NEW `…TestTheHostnameRoleRefusesAndResolves.test_the_check_is_the_roles_first_task` and `…test_the_check_names_the_variable_and_where_it_is_set` for what a Molecule run cannot see over the committed file. |

*Host Configuration Names the Environment It Targets* (MODIFIED), 2:

| Scenario | Covered by |
|---|---|
| A run names the environment it configures | EXISTING `test_host_configuration_names_its_environment.TestTheBaselinePlayNamesTheEnvironmentItTargets`. The clause this delta adds — that an unattended run takes the value from the stack's declaration — is NEW `…TestTheConvergeSeparatesTheTwoHandles.test_the_play_variable_is_fed_from_the_declared_group`. |
| A run supplying no environment refuses | EXISTING `test_host_configuration_names_its_environment.TestARunWhoseTargetGroupResolvesToNoHostRefuses`, which asserts the guard play's shape. That it actually refuses is **UNCOVERED** by every test command this project has — the earlier change that wrote the guard recorded that gap and it is unchanged here. |

*Platform Data Volume Is Mounted at a Fixed Host Path* (MODIFIED), 5:

| Scenario | Covered by |
|---|---|
| Volume is mounted at a known path | EXISTING Molecule `ansible/roles/platform_data_volume/molecule/default/`. |
| Mount survives a reboot | EXISTING, the `fstab` assertion in that scenario. |
| Dependent subdirectories exist before a service needs them | EXISTING, same scenario. |
| No device is supplied and none can be discovered | EXISTING Molecule `…/molecule/no-device-discoverable/`. |
| More than one candidate device is attached | EXISTING Molecule `…/molecule/multiple-devices-discoverable/` and `…/multiple-devices-reverse-order/`. |

The clause this delta adds — **Discovery SHALL NOT be keyed on the volume's name** — is covered by NEW `…TestTheMountIsNotKeyedOnTheVolumesName.test_discovery_is_keyed_on_the_volumes_id_and_on_no_name`.

---

## Assertion classification

Every assertion in the files this pass wrote carries its classification in its own docstring or comment — SPECIFIED where it traces to SHALL text or to a scenario, DERIVED where it traces to `design.md` or `tasks.md` rather than to a scenario. The classification is repeated at the point of the assertion so that it survives a reader who never opens this file. What follows is the summary.

**Predominantly DERIVED, and the reason matters.** Not one delta scenario states a stack's directory name, an inventory filename, a Hetzner resource name, a role name or a variable name. The scenarios are written over *"a stack"*, *"the `main` volume"* and *"the company variable"*. Every concrete name this pass asserts — `main-production`, `main-staging`, `production`, `main`, `operator`, `target_environment`, `hostname`, `company`, `ansible/inventory/group_vars/all.yml` — comes from `proposal.md`, `design.md` decisions 1, 2, 4, 5 and 7, and `tasks.md` sections 3, 4 and 5. They are asserted rather than left to review because each is read by something that resolves a wrong value silently: a path, a group name, a label selector, a container's name.

**Deliberately untested**, each recorded above with its reason:

- The Destroy Policy Gate's rename paragraph — a discipline, not a mechanism, by the requirement's own words.
- Every Hetzner-side effect: that a resource was renamed, that a plan renames it **in place** rather than replacing it, that a token reaches one project. The change's own tasks.md 9.2 makes the plan the reviewer's, and 11.1 makes the effect the operator's.
- The tailnet **machine** rename — an operator step in the Tailscale interface, confirmed by observation from a second peer (tasks.md 10.1, 10.2). The pin these tests assert is a different field, and reading it as the rename is the mistake design.md decision 6 exists to prevent.
- Stack-level Terraform composition (the `count` couplings, `backups = true` at the stack) — a Terraform root module is outside `terraform/modules/<name>/tests/`, the only glob `terraform test` reaches in this project.

**Tests that pass on their first run, before any implementation exists.** Recorded here rather than left to read as an alarm, following the convention `test_terraform_stacks_are_the_iterated_unit` established. Each guards against **overreach** — a property the tree already has and must keep — or is a discriminator supplying its own material:

| Test | Why it is green now |
|---|---|
| `…TestASourcesNameIsNotReadAsItsGroupsName.test_every_stack_has_an_inventory_source_named_for_the_stack` | The source already follows the stack; the rename must keep that true. Red if the sources and the directories are renamed out of step. |
| `…TestEveryStackDeclaresTheGroupItConverges.test_the_other_two_required_fields_are_still_declared_and_distinct` | The two existing fields are already declared and distinct. Red if adding a third loses one. |
| `…TestEveryStackDeclaresTheGroupItConverges.test_the_declared_group_carries_no_distinctness_obligation` | A negative read: nothing tests the new field for distinctness because the field does not exist. Red if the implementation adds a distinctness check. |
| `…TestTheTerraformDiscoveryDoesNotRequireTheConvergeField.test_no_terraform_workflow_reads_the_converge_only_field` | Same shape; it is paired with `test_the_converge_workflow_does_read_it`, which is red, so the pair cannot both be satisfied by a repository where the field exists nowhere. |
| `…TestTheConvergeSeparatesTheTwoHandles.test_the_concurrency_group_stays_on_the_stack` | The concurrency group already reads the stack's name and must keep doing so. |
| `…TestTheMountIsNotKeyedOnTheVolumesName` (both) | The discovery is already keyed on the volume's id, and the role's diagnostic currently names a volume the stacks still declare. The second goes red the moment the stacks are renamed and the diagnostic is not. |
| `…TestTheCompanyIsHeldInOnePlace.test_no_role_gives_the_company_a_default` | No role defines `company` yet. Red if the new role ships a default. |
| `…TestTheNewRoleIsCoveredByTheSuiteThatRunsRoles` (both) | Green because **this pass created the scenario directories**. They guard against the role landing without them. |
| `terraform/modules/server/tests/firewall_name.tftest.hcl`'s `plan_the_firewall_name_is_not_derived_from_the_tenant_either` | The present name is the old derivation, which is not the tenant. It guards against one derivation being swapped for another — design.md decision 4 rejects `name = var.tenant` by name. |
| Both `TestTheseReadsDiscriminate` classes | Fixture-driven discriminators: they supply their own material, so they pass on a tree that has not been renamed and would fail if a reader stopped reading. |

**Fixture-driven discriminators.** Every static read this pass wrote is pointed at material the test supplies, in one of two forms: the two `TestTheseReadsDiscriminate` classes, which run each reader over a scratch tree built to falsify it; and `TestHostConvergeDiscoveryReadsTheDeclaredGroup`, which runs the workflow's own discovery body over four scratch trees whose accept-rows and refuse-rows falsify one another. All of them execute here and are green. No discriminator was left unwritten, and none could be written but not run.

---

## What was changed in existing test files

**Eight `.tftest.hcl` files gained two variable values between them, and nothing else.** `tasks.md` 2.5 assigns this work to the derived-test author. `tenant` and `firewall_name` become required module inputs with no default, so from the moment the modules change, every `run` block in these files fails with *"No value for required variable"* before reaching an assertion:

- `terraform/modules/server/tests/{creation,firewall,labels,protection,validations}.tftest.hcl` — each file-level `variables` block gained `tenant = "main"` and `firewall_name = "main"`.
- `terraform/modules/volume/tests/{creation,delete_protection,labels}.tftest.hcl` — each gained `tenant = "main"`.

Each addition carries a comment saying why it is there. **No assertion, no `run` block name, no expected value and no `expect_failures` list was touched.** Supplying an input a module newly requires is not a weakening of what a test asserted; it is what keeps the existing assertions running at all. The baseline confirms it: the 18 server runs and 8 volume runs that passed before still pass.

---

## One assertion added after the code review, tracing to no scenario

`test_the_hosts_own_name_is_set_by_the_converge.TestTheUnsafeWriteFallbackStaysOffOutsideTheScenariosThatNeedIt`, four tests, added after the change's code review asked for it and **after** the implementation existed. It is recorded separately from everything above because its provenance is different in kind: **it traces to no scenario in any delta.** It is a guard on an implementation decision, and its own docstring says so first, so that a reader does not take it for a requirement-derived assertion.

The decision it guards is `hostname_unsafe_writes`, which the role acquired because `/etc/hostname` and `/etc/hosts` are bind mounts inside a container and the rename an atomic write ends with fails over one with `EBUSY` — so without a fallback the role could not be exercised by a scenario at all. The setting is load-bearing in **both** directions, which is what makes a single check insufficient and four of them warranted:

- **Off, on a real host.** The atomic write succeeds and the fallback is never consulted, *except* where something is already wrong — a read-only `/etc`, a full filesystem. There, falling back means an interrupted in-place write can truncate `/etc/hosts` and leave a host that cannot resolve its own name: the exact condition the task writing that file exists to prevent, reached through the mechanism meant to prevent it.
- **On, in this role's own scenarios.** It is what makes the role runnable, and therefore verified by anything at all.

| Test | What it holds |
|---|---|
| `test_the_role_defaults_the_fallback_off` | `ansible/roles/hostname/defaults/main.yml` declares the variable and defaults it to the literal `false`. |
| `test_only_this_roles_own_scenarios_turn_the_fallback_on` | No file anywhere under `ansible/` turns it on outside `ansible/roles/hostname/molecule/`. Stated over the whole tree, not over `group_vars` alone: a play, a second role's defaults or a task's own `vars:` reaches a real converge by the same route. |
| `test_no_inventory_variable_sets_the_fallback_at_all` | Under `ansible/inventory/` the **assignment** is the offence, whatever its value — a setting of `false` there is redundant with the role's own default and is one character from the setting that is not, in the one place whose variables reach every play a host runs. This is the case the review most wanted caught, because it would apply to a real converge and nothing else in the tree would notice. |
| `test_the_permitted_override_is_actually_present` | The positive control, and what makes the three negative reads above non-vacuous: over a repository where the setting had been removed entirely, all three would pass having found nothing. |

Because these were written **after** the implementation, they are in the second situation rather than the first: a pass reports that the tree currently carries the property, which is the expected result and not an alarm. What makes that green mean anything is four fixture-driven discriminators in `TestTheseReadsDiscriminate`, which point the reader and both guards at trees this repository does not contain — a `group_vars` file arming the fallback, a second role arming it, an inventory file setting it `false`, a commented-out assignment, and a variable whose name merely starts the same way.

One defect was found and fixed in the course of writing them, and it is the kind this suite exists to catch in itself: the file reader skipped any path with a dot-prefixed component, computed over the **absolute** path — and this repository's own working trees live under `.claude/worktrees/`, so it excluded every file in the tree and reported a repository that set the variable nowhere. It now computes that over the repository-relative path, with a comment saying why. The guard was red at that moment for a reason that had nothing to do with the tree, which is the third failure state, and it is named here for the same reason the other one is.

---

## A defect in one test this pass wrote, and its repair

Found by the implementing session on the first Molecule run and returned rather than edited there; repaired here, because a test author's defect is the test author's to fix and the repair had to be a **read** rather than an assertion.

`ansible/roles/hostname/molecule/default/verify.yml`, the task *"Assert the loopback entry answers for the name the host was just given"*, selected `/etc/hosts` lines with the pattern `'^127\\.0\\.1\\.1\\s'` — double-escaped inside a **folded** YAML scalar. A folded scalar performs no escape processing, so Jinja received the pattern exactly as written and applied its own string-literal parsing, collapsing each `\\.` to `\.`: a regex asking for a literal backslash after `127`, matching nothing on any tree. **The assertion could not have passed against any implementation.**

This is the third failure state — a defect in the test, establishing nothing about the code under test. It is recorded rather than quietly corrected because the distinction is what keeps *never weaken a test* honest: what was wrong was the read, not the expected value. The assertion's `that:`, its `fail_msg`, its `success_msg` and the `select('search', …)` line are **byte-identical** to what this pass first wrote; one line changed, and a comment now says why the escaping is what it is. The same shape was used by the earlier change `read-the-old-root-sweep-from-tracked-files` for the same class of defect.

Measured against the pinned `ansible-core` 2.21.3, over a sample carrying `127.0.1.1\tacme-hn-tree`:

- as written, double-escaped: `[]`
- as repaired, single-escaped: the line matches

The role was correct throughout: the converged container carries the loopback entry, and `hostname` returns the derived name.

---

## Obsolete tests

**Candidates for human confirmation, every one.** This pass never edits or deletes an existing test, so each entry below is the input to somebody else's destructive action and is marked as a candidate rather than a conclusion. The search was bounded to the dispatched test-path globs — `.github/tests/*.py`, `terraform/modules/<name>/tests/*.tftest.hcl`, `ansible/roles/<name>/molecule/<scenario>/` — and no earlier `test-plan.md` was supplied to this pass, so nothing outside those globs was searched and no requirement-to-test index was available. An assertion superseded by this change that lives outside those globs would not have been found.

Two of these are **not named by `tasks.md`**, and both would present to the implementer as an unexplained red.

| # | Test | Superseded by | Evidence |
|---|---|---|---|
| 1 | `test_terraform_stacks_are_the_iterated_unit.TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_the_target_environment_handle_is_derived_from_the_stack_name` | `iac-cicd-pipeline` ADDED *Each Stack Declares Its Own Pipeline Configuration*, scenario *A converge reads its Ansible group from the declaration, not from the stack's name* | The test asserts that every `TARGET_ENVIRONMENT` assignment in `host-converge.yml` reads `matrix.stack.name`, which the delta forbids in as many words. Its own docstring names this change: *"Asserting the ASSIGNMENT rather than the values is what keeps this true when entry 62 makes the group `production` while the stack is `main-production`."* Entry 62 is this change. Replaced by `…TestTheConvergeSeparatesTheTwoHandles.test_the_play_variable_is_fed_from_the_declared_group`. |
| 2 | `test_terraform_stacks_are_the_iterated_unit.TestTheEnvironmentAxisIsNotRenamedWithTheUnit.test_the_resource_labels_still_name_the_environment_axis` | `iac-safety-hardening` MODIFIED *Consistent Resource Labeling* ("Environment values SHALL be spelled in full"), and `iac-repo-foundations` ADDED *Stack and Module Folder Structure* ("that name SHALL NOT be assumed equal to the name of any axis it carries") | The test asserts each stack's declared `environment` label set equals `{directory.name}`. After the rename the directory is `main-production` and the label is `production`. Its own docstring: *"the equality holds now and is asserted now, and is the first thing entry 62 will have to restate."* Replaced by `…TestTheTreeCarriesTheRenamedValues.test_each_stack_declares_the_environment_axis_spelled_in_full`. |
| 3 | `test_terraform_stacks_are_the_iterated_unit.TestEachStackNamesAWorkspaceDerivedFromItsOwnName.test_every_stack_names_a_workspace_derived_from_its_stack_name` | `iac-state-management` MODIFIED *Remote State Backend* ("**A workspace's name SHALL NOT be computed from its stack's directory name.**") | The test asserts `workspace == f"infrastructure-{directory.name}"`. This change renames the directories and deliberately leaves the workspaces at `infrastructure-prod`/`infrastructure-staging` until a later change, so the derivation becomes false — which is why the delta retires it. **The sibling `test_no_two_stacks_name_the_same_workspace` in the same class is NOT superseded** and must survive: the delta keeps the uniqueness obligation and strengthens it. The class's own name carries the retired derivation. |
| 4 | `test_a_second_environment.TestIdenticalResourceNamesAcrossEnvironmentsAreKept.test_every_environment_that_declares_a_volume_names_it_identically` | `iac-data-volumes` MODIFIED *Conditional Prod Volume Creation* ("the on-host mount path is derived from the volume's **id** … so renaming the volume SHALL NOT disturb an existing mount") and `iac-host-configuration` MODIFIED *Platform Data Volume Is Mounted at a Fixed Host Path* ("Discovery SHALL NOT be keyed on the volume's name") | The test derives the expected volume name from the single host path `platform/docker-compose.yml` hardcodes — `main-data` — and asserts every stack's `volume_name` equals it. This change renames the volume to `main` while `proposal.md` keeps the mount path `/mnt/main-data` deliberately, so the two stop agreeing **by design**. What survives of the obligation is that the two stacks agree with *each other*, which is NEW `…test_each_stacks_volume_is_named_on_the_rank_axis`. **Not named by `tasks.md`.** |
| 5 | `test_host_converge_workflow.TestAnEnvironmentThatCanBeProvisionedCanBeConverged.test_every_provisioned_environment_has_a_source_and_variables_of_its_own` | `iac-host-configuration` ADDED *Dynamic Inventory via the hcloud Plugin, One Source per Stack* ("the `group_vars` file its declared group names SHALL exist") | The test looks for `ansible/inventory/group_vars/<stack directory name>.yml`. After this change the file is named for the **group**: stack `main-production` reads `group_vars/production.yml`. The source half of the same test is unaffected and must survive. Replaced by NEW `…TestASourcesNameIsNotReadAsItsGroupsName.test_the_group_vars_file_each_stack_declares_exists`. |
| 6 | `test_a_second_environment.TestTheSecondEnvironmentIsDeclared` — `test_a_second_environment_directory_exists`, `test_the_second_environment_names_its_own_workspace`, `test_the_second_environment_declares_its_own_secret_and_environment` | `iac-repo-foundations` ADDED *Stack and Module Folder Structure*, and `iac-state-management` MODIFIED *Remote State Backend* | The module's `SECOND_ENVIRONMENT = "staging"` is a stack **directory** name, which becomes `main-staging`. The first test asserts that directory exists; the second indexes `environment_backends()["staging"]` and expects `infrastructure-staging`, which after the rename is a lookup on a key that is gone **and** a derivation the delta retires. The third indexes `environment_declarations()["staging"]`. Re-pointing the constant fixes all three; the workspace expectation additionally has to stop being derived. |

### Two existing mechanisms that break for a reason no `tasks.md` entry predicts

Neither is an obsolete *test*; both are shared readers whose shape this change invalidates, and both will present as a wall of unexplained failures across modules the implementer did not touch. They are recorded here because that is what this pass is for.

**A. `test_environment_agnostic_pipeline._resolve_fields` resolves the GitHub Environment field by the substring `environment`.** Adding `target_environment:` to each `pipeline.yml` gives every declaration **two** keys containing that substring, and the reader then appends *"expected exactly one field naming the GitHub Environment this environment's apply job attaches to"* as an offence for every stack. Everything that reads `declaration_offences()` or `environment_declarations()` goes red — in `test_environment_agnostic_pipeline`, in `test_a_second_environment`, and in `test_host_converge_workflow`, which inherits the fixture mixin. The reader has to resolve the field by its exact name, or exclude the new one, before the field can be added at all. This is the single most likely cause of a red run that looks unrelated to the change.

**B. `test_environment_agnostic_pipeline.PROD_DIRECTORY = "prod"`.** Every fixture in that module and in `test_host_converge_workflow` builds its synthetic declarations from *prod's own committed declaration*, located by that constant. After `git mv terraform/stacks/prod terraform/stacks/main-production` the lookup returns `None` and each fixture calls `self.fail("prod carries no pipeline declaration …")`. `tasks.md` 7.2 says "every literal naming a stack directory", which covers it in principle; it is named here because the failure does not name the constant — it names a missing declaration, which reads as a broken tree.

The new modules this pass adds deliberately depend on **neither** mechanism: they parse `pipeline.yml` directly and locate a declaration template by shape, so they keep working across the rename.

---

## Unresolved project questions

No channel exists to ask on — this is a dispatched, non-interactive pass — so each question is recorded with the assumption taken and the tests that depend on it. The project's `AGENTS.md` and `CLAUDE.md` were read; none of these is answered there.

1. **No `ansible` or `molecule` skill exists in the library's testing-skill list for this stack's idiom.** `testing` names one, but it was not among the skills available to this pass. The Molecule scenarios were therefore written to the floor plus this repository's own established shapes — `hardening/molecule/absent-ssh-cidrs` and `image_prune/molecule/absent-heartbeat-key` — which `tasks.md` 5.4 names as the pattern to match. Affects both `ansible/roles/hostname/molecule/` scenarios.

2. **The `hostname` role's own interface is assumed, not specified.** These tests assume the role is named `hostname` (tasks.md 5.1), takes `company` from inventory with no default of its own, derives the name as `{{ company }}-{{ inventory_hostname }}` (proposal.md), and asserts `company` in its **first** task with a message naming `ansible/inventory/group_vars/all.yml`. A different spelling of any of these makes a test fail on a legitimate choice. Affects `ansible/roles/hostname/molecule/*` and `test_the_hosts_own_name_is_set_by_the_converge.TestTheHostnameRoleRefusesAndResolves`.

3. **The declaration field is assumed to be spelled `target_environment`.** design.md decision 2 fixes it and `tasks.md` 3.6 writes it, so this is a strong assumption rather than a guess — but it is a literal in `TARGET_ENVIRONMENT_FIELD` and every assertion reading the declaration depends on it. The matrix key the converge job reaches it through is **not** assumed: those tests assert only that the two handles are different fields of the row.

4. **`ansible.builtin.hostname` in the pinned container image.** ~~The `default` scenario assumes the module's systemd strategy reaches `hostnamectl` inside `geerlingguy/docker-ubuntu2204-ansible` running `/lib/systemd/systemd` privileged. This could not be established here, because the role that would exercise it does not exist. If it turns out not to work, the fix is the role's own (`hostname_use:`), not the scenario's — and the scenario is what will report it.~~

   **ANSWERED AT IMPLEMENTATION, AND THE ANSWER WAS NO — the scenario reported it exactly as this entry predicted.** The module failed at `converge` with *"Could not set static hostname: Failed to set static hostname: Device or resource busy"*. The cause is not the strategy: the module writes `/etc/hostname` **atomically** under every strategy, and in a container that file is a bind mount over which a rename fails with `EBUSY`. `hostname_use:` therefore would not have helped, and this entry's guess at the fix was wrong while its prediction about who would report it was right.

   Measured directly against the pinned digest: an in-place write to `/etc/hostname` succeeds, a rename over it fails, `sethostname(2)` succeeds. The role was rewritten to do what the module's `debian` strategy does, split so each half uses the mechanism that works — `copy` with `unsafe_writes: true` for the file, `hostname <name>` for the running system. `unsafe_writes` is a fallback rather than a replacement, so a real host still takes the atomic path. `/etc/hosts` carries it for the same reason. **No assertion in either scenario was weakened to reach green**; the role changed and the scenarios did not.

5. **The 64-byte host-name limit and this working tree's namespace.** Under Molecule, `inventory_hostname` is the instance name, which carries the per-working-tree namespace, and the role prefixes the company to it. The `default` scenario's instance name is deliberately short (`hn-`) and its `converge.yml` asserts the derived name's length **before** the role runs, so a working tree with a long enough name fails naming the working tree rather than failing inside `hostnamectl`. On the tree this pass ran on, the namespace is 44 bytes and the derived name is 52.

6. **`.github/tests` module naming.** This suite names a module for the property it asserts rather than for the change. The two new names follow that convention; they are not fixed by anything, and renaming them costs only this file's references.

---

## The files this pass wrote

Tests, all inside the dispatched globs:

- `.github/tests/test_a_stack_and_its_environment_are_named_separately.py` — 34 tests, 25 red.
- `.github/tests/test_the_hosts_own_name_is_set_by_the_converge.py` — 20 tests at the end of the derivation pass, 10 red; 28 after the post-review guard above was added, all green against the implementation.
- `terraform/modules/server/tests/tenant_label.tftest.hcl`
- `terraform/modules/server/tests/firewall_name.tftest.hcl`
- `terraform/modules/volume/tests/tenant.tftest.hcl`
- `ansible/roles/hostname/molecule/default/{molecule.yml,converge.yml,verify.yml}`
- `ansible/roles/hostname/molecule/absent-company/{molecule.yml,converge.yml,verify.yml}`

Plus this manifest — `test-plan.md`, in this change's own directory, cited that way rather than by path because a change's artifacts move when it is archived — which is the one file this pass wrote outside a test-path glob.

### Running exactly what a task must satisfy

    # the whole suite, from the repository root
    python3 -m unittest discover --start-directory .github/tests

    # one module
    python3 -m unittest discover --start-directory .github/tests \
        -p 'test_the_hosts_own_name_is_set_by_the_converge.py'

    # one test, individually selectable
    PYTHONPATH=.github/tests python3 -m unittest \
        test_the_hosts_own_name_is_set_by_the_converge\
.TestTheReportedNameIsPinnedBeforeTheHostIsRenamed\
.test_the_hostname_role_runs_after_the_role_that_pins_the_reported_name

    # one module's Terraform tests, from that module's directory
    terraform init -backend=false
    terraform test                                        # every file
    terraform test -filter=tests/firewall_name.tftest.hcl  # one file

    # the new role's scenarios, from ansible/roles/hostname/
    ansible/scripts/run-molecule test --all
    ansible/scripts/run-molecule test -s absent-company

`terraform test` has no per-`run` filter, so a single `run` block is selected by selecting its file. The two new server files are separate for that reason as much as for readability: Terraform skips every remaining `run` in a file once one fails, and both files are red until the modules change.

### Order the reds go green in

Stated because several of these tests fail for want of a *different* task's work, and a reader meeting one in isolation would not know:

1. `tasks.md` 2.1–2.3 (the module inputs) turn `tenant_label.tftest.hcl`, `firewall_name.tftest.hcl` and `volume/tests/tenant.tftest.hcl` green.
2. `tasks.md` 3.1–3.5 (the stacks) turn `TestTheTreeCarriesTheRenamedValues` and `TestTheMountIsNotKeyedOnTheVolumesName.test_no_task_still_names_a_volume_no_stack_declares` green — the latter only once `tasks.md` 7.3 rewrites the role's diagnostic.
3. `tasks.md` 3.6 and 4.1–4.3 (the declaration and the inventory) turn `TestEveryStackDeclaresTheGroupItConverges` and `TestASourcesNameIsNotReadAsItsGroupsName` green.
4. `tasks.md` 6.1–6.3 (the converge workflow) turn `TestHostConvergeDiscoveryReadsTheDeclaredGroup` and `TestTheConvergeSeparatesTheTwoHandles` green.
5. `tasks.md` 4.4, 5.1–5.3 (the role, the variable and the pin) turn `test_the_hosts_own_name_is_set_by_the_converge` green and make the two Molecule scenarios executable at all.
