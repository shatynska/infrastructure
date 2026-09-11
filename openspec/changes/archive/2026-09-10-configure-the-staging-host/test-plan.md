# Test plan — `configure-the-staging-host`

Written before any implementation of this change existed, by an author other than whoever implements it, from this change's delta specs and not from code.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files, and has to be read on purpose. Read it before implementing: it is what says which tests a given task must make pass, and which two existing tests this change supersedes.

**This pass is additive only.** It added one file under a dispatched test-path glob and this manifest. It edited, deleted and disabled nothing, and it wrote no implementation. Every existing test in the repository is exactly as it was.

## What was written

One new module, under the `.github/tests` row of AGENTS.md's *Testing* table:

- `.github/tests/test_host_configuration_names_its_environment.py` — 28 tests.

Nothing was written under the Terraform row (this change touches no Terraform module) or the Molecule row (see *Why no Molecule scenario was added*, below).

Runner, from the repository root:

```
python3 -m unittest discover --start-directory .github/tests
```

Any single test is selectable by name:

```
python3 -m unittest discover --start-directory .github/tests \
    -k test_every_environment_directory_has_an_inventory_source_of_its_own
```

Run through `discover` in both forms. It is discovery that puts `.github/tests` on `sys.path`, which is what makes the module's sibling imports resolve; `python3 -m unittest <module>.<class>.<test>` from the repository root does not.

## Baseline

**Scoped, and the scope is stated.** Taken from the repository root immediately before the new module was written, on the tree at `ffd216f`:

```
python3 -m unittest discover --start-directory .github/tests
→ Ran 529 tests in 10.186s — OK
```

Nothing was failing beforehand, so every failure below is attributable to the new module.

**Two of the project's three test commands were not baselined**, and neither was run at all:

- `ansible/scripts/run-molecule test --all` — no test was placed under it by this pass, and running it needs a container runtime and the per-working-tree provisioning AGENTS.md's *Namespacing Molecule per working tree* section requires. Task 5.1 already obliges the implementer to establish the two scenarios named under *Obsolete tests* pass on the current tree before changing anything; that is the baseline for the Molecule row and it is that task's, not this pass's.
- `terraform test` — this change touches no Terraform module, so the row has no subject here.

**After the new module, from the repository root:**

```
python3 -m unittest discover --start-directory .github/tests
→ Ran 557 tests in 10.328s — FAILED (failures=16)
```

All 16 failures are in the new module. No pre-existing test changed state.

## Which new tests are red now, and on what

The dispatch named three facts about the current tree. Each red test is mapped to the one it fails on, so a failure that turns out to have another cause is distinguishable from an expected one.

| Test | Currently | Fails on |
|---|---|---|
| `test_every_environment_directory_has_an_inventory_source_of_its_own` | RED | `ansible/inventory/hcloud.yml` is one source naming no environment; `staging` and `prod` both lack one |
| `test_no_two_inventory_sources_take_the_same_credential_variable` | RED | one source only — the collision check fails closed rather than passing over a set of one |
| `test_no_inventory_source_relies_on_the_plugins_bare_credential_fallback` | RED | `hcloud.yml` declares no token option at all, so the plugin falls back to bare `HCLOUD_TOKEN` |
| `test_the_inventory_sources_differ_only_in_the_credential_they_name` | RED | one source only — the cross-source comparison fails closed |
| `test_ansible_cfg_declares_no_default_inventory` | RED | `ansible/ansible.cfg` carries `inventory = inventory/hcloud.yml` |
| `test_ansible_cfg_fails_a_run_whose_inventory_source_cannot_be_parsed` | RED | `ansible/ansible.cfg` sets no `any_unparsed_is_failed` |
| `test_ansible_cfg_does_not_set_the_neighbouring_unparsed_is_failed` | GREEN | guard — today's `ansible.cfg` sets neither of the two one-word-apart settings, and must still set only the right one afterwards |
| `test_every_inventory_source_resolves_hosts_from_the_plugin_and_groups_by_label` | GREEN | guard — today's single source already names the plugin and groups by label; the split must not lose either |
| `test_no_committed_inventory_file_enumerates_a_host` | GREEN | guard — no committed hosts file exists today and none may appear |
| `test_the_baseline_play_takes_its_target_from_a_supplied_input` | RED | `ansible/playbooks/host-baseline.yml` carries the literal `hosts: prod` |
| `test_the_baseline_play_gives_its_target_no_default` | RED | same literal — `hosts:` is not a template at all |
| `test_the_lint_sentinel_names_no_environment_this_repository_has` | RED | `.ansible-lint` declares no `extra_vars:` |
| `test_the_syntax_check_hook_supplies_the_same_sentinel` | RED | same, and the pre-commit hook supplies no `-e target_environment=` |
| `test_the_playbook_opens_with_a_play_that_runs_when_no_host_resolved` | RED | the first play is the converge play, and it declares `become: true` |
| `test_the_guard_refuses_a_run_that_supplied_no_environment` | RED | no guard play, so no `assert` task exists to read |
| `test_the_guard_refuses_a_target_group_that_holds_no_host` | RED | same |
| `test_the_two_refusals_are_separate_tasks` | RED | same |
| `test_each_guard_refusal_names_the_environment_in_its_diagnostic` | RED | same |
| `test_the_guard_adds_no_further_required_input_to_a_run_that_resolves_hosts` | RED | same |
| the nine `TestTheseReadsDiscriminate` tests | GREEN | fixture-driven; they establish that the predicates above find the defects they name |

**One of these was written wrong on the first attempt and is recorded rather than quietly fixed**, because it is the failure mode the testing standard calls an alarm: `test_the_guard_adds_no_further_required_input_to_a_run_that_resolves_hosts` initially PASSED against the current tree. With no guard play, it read the converge play instead — which declares no `vars_prompt`, no `vars_files` and no Jinja at all — and reported no further input for a check that does not exist. It now asserts first that the first play targets localhost, and is red like the rest of its class.

## Scenario accounting

Nine `#### Scenario:` blocks in the delta spec, all in `iac-host-configuration`. Nine accounted for. None is uncovered; each carries a stated residue that a static read cannot reach.

### MODIFIED — *Dynamic Inventory via hcloud Plugin*

Both outcomes the MODIFIED operation produces are here: new tests for the requirement as revised (below), and the obsolete-test candidates the revision supersedes (further down). The two are independent — the new tests touch nothing existing.

| Scenario | Covered by | Residue not covered, and why |
|---|---|---|
| Inventory resolved live from Hetzner | `test_every_inventory_source_resolves_hosts_from_the_plugin_and_groups_by_label`, `test_every_environment_directory_has_an_inventory_source_of_its_own` | That the API is actually reached is a live call. **Deliberately untested** — the suite makes no network call, by its own requirement. Tasks 1.2 and 9.1 exercise it by hand. |
| Disabled server yields no stale inventory entry | `test_no_committed_inventory_file_enumerates_a_host` | That a *destroyed* server yields no entry needs a destroyed server and a live call. **Deliberately untested.** What is covered is the mechanism that makes staleness impossible: a host no committed file names cannot go stale in one. |
| An environment's source reaches only its own project | `test_every_environment_directory_has_an_inventory_source_of_its_own`, `test_no_two_inventory_sources_take_the_same_credential_variable`, `test_no_inventory_source_relies_on_the_plugins_bare_credential_fallback`, `test_ansible_cfg_declares_no_default_inventory` | Which Hetzner project a credential actually belongs to is an API fact. **Deliberately untested** — task 9.1's `--graph` on both sources is what establishes it. |
| A further environment is brought into inventory | `test_the_inventory_sources_differ_only_in_the_credential_they_name`, plus the census above | "Without editing any existing source" is an edit that did not happen, which no static read can observe. What is asserted is the property that makes the edit unnecessary — see that test's own docstring. |
| An inventory source cannot authenticate | `test_ansible_cfg_fails_a_run_whose_inventory_source_cannot_be_parsed`, `test_ansible_cfg_does_not_set_the_neighbouring_unparsed_is_failed` | That the setting has the effect described is a run-time fact. **Deliberately untested** — design.md Decision 2a reproduced all three states by hand and task 1.3a repeats it. |

### ADDED — *Host Configuration Names the Environment It Targets*

| Scenario | Covered by | Residue not covered, and why |
|---|---|---|
| A run names the environment it configures | `test_the_baseline_play_takes_its_target_from_a_supplied_input` | That the run configures "no host outside it" follows from the group the inventory resolves; not statically observable. **Deliberately untested**, exercised by tasks 10.1 and 10.2. |
| A run supplying no environment refuses | `test_the_baseline_play_gives_its_target_no_default`, `test_the_guard_refuses_a_run_that_supplied_no_environment` | The refusal actually occurring. **Has no home** — see *The behaviour with no home*, below. Task 2.3 verifies it by hand. |

### ADDED — *A Run Whose Target Group Resolves to No Host Refuses*

| Scenario | Covered by | Residue not covered, and why |
|---|---|---|
| A targeted environment resolves to no host | `test_the_playbook_opens_with_a_play_that_runs_when_no_host_resolved`, `test_the_guard_refuses_a_target_group_that_holds_no_host`, `test_each_guard_refusal_names_the_environment_in_its_diagnostic`, `test_the_two_refusals_are_separate_tasks` | The refusal actually occurring, and the diagnostic actually rendering the environment's name. **Has no home.** Tasks 2.3 and 9.1a verify both by hand. |
| A run that resolves hosts is unaffected | `test_the_guard_adds_no_further_required_input_to_a_run_that_resolves_hosts` | That a run with a non-empty group proceeds past the guard. **Has no home.** Task 10.1 is its positive counterpart. |

## Assertion classification

Per assertion, in the module's own docstrings. Summarised:

**SPECIFIED** — traces to SHALL text or to a scenario in the delta:

- `test_every_environment_directory_has_an_inventory_source_of_its_own`
- `test_no_two_inventory_sources_take_the_same_credential_variable`
- `test_no_inventory_source_relies_on_the_plugins_bare_credential_fallback`
- `test_ansible_cfg_declares_no_default_inventory`
- `test_ansible_cfg_fails_a_run_whose_inventory_source_cannot_be_parsed`
- `test_every_inventory_source_resolves_hosts_from_the_plugin_and_groups_by_label`
- `test_no_committed_inventory_file_enumerates_a_host`
- `test_the_baseline_play_takes_its_target_from_a_supplied_input`
- `test_the_baseline_play_gives_its_target_no_default`
- `test_the_playbook_opens_with_a_play_that_runs_when_no_host_resolved`
- `test_the_guard_refuses_a_run_that_supplied_no_environment`
- `test_the_guard_refuses_a_target_group_that_holds_no_host`
- `test_each_guard_refusal_names_the_environment_in_its_diagnostic`
- `test_the_guard_adds_no_further_required_input_to_a_run_that_resolves_hosts`

**DERIVED** — inferred from this change's `design.md` or `tasks.md`, or from the mechanics of the tools involved, with no scenario stating it. Each obliges the implementer to satisfy something no delta scenario states, which is why they are listed rather than left indistinguishable from the above:

| Assertion | What it obliges, and where it came from |
|---|---|
| `test_the_inventory_sources_differ_only_in_the_credential_they_name` | that two sources agree on everything but the credential name — design.md Decision 1, tasks.md 1.2 |
| `test_ansible_cfg_does_not_set_the_neighbouring_unparsed_is_failed` | that the one-word-apart setting stays unset — design.md Decision 2a, which asks for exactly this assertion |
| `test_the_two_refusals_are_separate_tasks` | two `assert` tasks rather than one compound one — design.md Decision 4, tasks.md 2.1 |
| `test_the_lint_sentinel_names_no_environment_this_repository_has` | that `.ansible-lint` supplies a sentinel and it names no real environment — design.md Decision 5, which asks for exactly this assertion |
| `test_the_syntax_check_hook_supplies_the_same_sentinel` | that the two compile-time tools agree on one sentinel value — design.md Decision 5, tasks.md 3.2 |
| the name `target_environment` (module constant `TARGET_INPUT`) | the delta says "an input supplied per run" and never names it; the name comes from design.md Decision 4 and tasks.md 2.1 |
| the `default([])` filter requirement inside `test_the_guard_refuses_a_target_group_that_holds_no_host` | design.md Decision 4's "load-bearing" note about `keyed_groups` not creating an absent key |
| the nine `TestTheseReadsDiscriminate` tests | that the predicates above find the defects they name — no scenario states it; the repository's own convention (three sibling modules carry an equivalent class) |

**DELIBERATELY UNTESTED** — identified and left uncovered, with the reason:

- Every "residue" cell in the scenario tables above.
- **`ansible/.envrc.example` (tasks.md 1.4).** No delta scenario obliges its existence or its content, and task 1.4's own verification is `git check-ignore`, which spawns a version-control command the suite's own requirement forbids. A static parse of `.gitignore` could assert the pattern matches `ansible/.envrc`, but nothing in the delta obliges it and inventing the obligation here would be this author designing behaviour.
- **`ansible/inventory/group_vars/staging.yml` (tasks.md 4).** No delta scenario reaches it. Its content is staging's own inputs; the requirement that governs them, *A Role's Absent Required Input Is Reported by Name*, is not in this delta and acquires no new obligation from it.
- **The five refusal diagnostics (tasks.md 5.2).** Also not in this delta — design.md Decision 9 says so in as many words: "This is a defect against a requirement already recorded, not a new rule. … No delta is owed; the fix is owed." So no *new* test is owed for them either. What they do produce is the obsolete-test list below.
- **`image_prune` on staging, its heartbeat check name and its period (tasks.md 8, 10.6, 10.7).** No delta scenario; the behaviour is a live host's and an external observer's.

## The behaviour with no home, and whether I agree

design.md Decision 10 states that one behaviour — the guard play *actually refusing* — fits none of this project's three test commands. **I agree, on the boundaries as this repository draws them**, and would add that the case is stronger than Decision 10 states it:

- Molecule's subject is a role converged on a host. The guard is a play, and its whole point is running when there is no host; a Molecule scenario would have to converge a container in order to test the case where nothing converged.
- `.github/tests` may read committed files statically and may not spawn a command beyond `bash`/`sh` — a constraint asserted by `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` over every module in that directory, this one included. Running `ansible-playbook` there would fail an existing test, which is the clearest possible statement that it does not belong.
- `terraform test` has no subject here at all.

I did not invent a fourth layer, as instructed. What I did instead is bound what a green run means, in the module's own header: it asserts the guard is *shaped* so it can refuse, and states outright that it establishes nothing about the refusal happening. Task 8.2 queues the missing layer and tasks 2.3 and 9.1a verify the behaviour by hand in the meantime — which is the right disposition, but it means **a green pull request does not establish the guard works**, and that is worth saying at the `build:verify` gate rather than at `ship:confirm`.

## Why no Molecule scenario was added

The two Molecule scenarios this change touches already exist. This pass may only add, and the change's own tasks.md 5.3 has the implementer *edit* them — which this pass cannot do and did not do. Adding a third scenario asserting the new literal alongside the two asserting the old one would leave the repository with two scenarios contradicting each other until 5.3 ran, and would make deleting the old assertion look optional. They are recorded as obsolete instead.

## Obsolete tests

**Every entry below is a candidate for human confirmation, not a conclusion.** This pass deleted and edited nothing. Confirm each against the delta before acting on it.

**Search bound.** Searched: the three dispatched test-path globs — `.github/tests/*.py`, `ansible/roles/<name>/molecule/<scenario>/`, and `terraform/modules/<name>/tests/*.tftest.hcl` — by grep for the literals the change replaces (`group_vars/prod.yml`, `environments/prod`, `inventory/hcloud.yml`, `HCLOUD_TOKEN`, `hosts: prod`). Nothing outside those globs was searched. **No earlier `test-plan.md` was supplied to this dispatch**, so no scenario-to-test mapping from a previous change was available to draw on; the entries below rest on the grep and on this change's own design.md Decision 9 and Impact section, both of which name the same two files.

### 1. `hardening` / `absent-ssh-cidrs`

- **Runner-selectable identifier:** `ansible/scripts/run-molecule test -s absent-ssh-cidrs`, run from `ansible/roles/hardening`.
- **The assertion:** task *"Assert the diagnostic names the input and where it is expected to be set"* in `ansible/roles/hardening/molecule/absent-ssh-cidrs/verify.yml:118`.
- **Evidence:** the condition `"'group_vars/prod.yml' in absent_cidrs_outcome.failed_msg"` matches, exactly, the literal that `ansible/roles/hardening/tasks/main.yml`'s `fail_msg` carries today and that tasks.md 5.2 replaces with `ansible/inventory/group_vars/<environment>.yml`.
- **Superseded by:** this change's *Not in the delta* fix to that `fail_msg` — design.md Decision 9, tasks.md 5.2. Note that no delta requirement supersedes it; the requirement it serves, *A Role's Absent Required Input Is Reported by Name*, is unchanged. What is superseded is the literal, not the obligation.
- **What the implementer must do:** tasks.md 5.3 — replace the literal with the new one *exactly*, not with a loosened `group_vars/` substring, which would pass against the message being replaced. tasks.md 5.1 requires confirming it passes on the current tree first, and 5.3 requires confirming it fails against the pre-5.2 message.

### 2. `image_prune` / `absent-heartbeat-key`

- **Runner-selectable identifier:** `ansible/scripts/run-molecule test -s absent-heartbeat-key`, run from `ansible/roles/image_prune`.
- **The assertion:** task *"Assert the diagnostic names the input and where it is expected to be set"* in `ansible/roles/image_prune/molecule/absent-heartbeat-key/verify.yml:113`.
- **Evidence:** the condition `"'group_vars/prod.yml' in absent_key_outcome.failed_msg"`, matching `ansible/roles/image_prune/tasks/main.yml`'s `fail_msg` at line 57. That scenario's own `fail_msg` and `success_msg` prose also names `ansible/inventory/group_vars/prod.yml`; the prose is not an assertion and does not fail, but it will read as contradicting the condition above it once 5.3 lands, and tasks.md 5.4's sweep does not list this file.
- **Superseded by:** the same fix — design.md Decision 9, tasks.md 5.2.
- **What the implementer must do:** as above.

### Where the search found nothing

Stated as "no such test exists", distinguished from "none was found":

- **`deploy_user`'s and `platform_data_volume`'s refusal messages also change (tasks.md 5.2), and no test asserts the literal being replaced.** Confirmed by reading, not only by grep: `deploy_user/molecule/default/verify.yml:440` names `group_vars/prod.yml` in a *comment* about the inline `!vault` form (tasks.md 5.4 explicitly leaves it), and `platform_data_volume/molecule/no-device-discoverable/verify.yml` asserts `platform_data_volume_device`, `volume_enabled` and `scsi-0HC_Volume_` in the message but never the `terraform/environments/prod/terraform.tfvars` path. So those two `fail_msg` edits land uncovered — before this change as much as after, and this pass adds no coverage for them, per *deliberately untested* above.
- **`.github/tests/*.py` holds no assertion this change supersedes.** The `HCLOUD_TOKEN` occurrences in `test_environment_agnostic_pipeline.py` and `test_a_second_environment.py` are about prod's *GitHub Actions* secret for Terraform, which this change does not touch (proposal.md: "Not touched … `.github/workflows/`"). They are not obsolete.
- **`terraform/modules/*/tests/*.tftest.hcl` holds nothing bearing on this change.** Its `hcloud` occurrences are the Terraform provider.

### One stale-but-passing reference, which is *not* an obsolete-test entry

`.github/tests/test_ci_configuration.py`'s `CONFIGURATION_PATHS` tuple (around line 4662) lists `"ansible/inventory/hcloud.yml"` — a path this change deletes. It is **not** obsolete and must **not** be deleted: its own comment says the tuple is "representative of the configuration directory's breadth, not of its current contents", and the test using it only checks a GitHub Actions path filter's glob against those strings. It will still pass. Left as a note because someone sweeping for `inventory/hcloud.yml` (tasks.md 7.7 asks for exactly that grep) will find it and has to decide; the correct decision is to leave it, or to re-point it to `ansible/inventory/prod.hcloud.yml` as a cosmetic change that alters no assertion.

## Unresolved project questions

Recorded rather than resolved silently. A dispatched subagent has no channel to ask on; each carries the assumption taken and the tests that depend on it.

1. **Is `target_environment` the input's name?** The delta says "an input supplied per run" and never names it. **Assumption taken:** yes, from design.md Decision 4 and tasks.md 2.1. **Depends on it:** every test in `TestTheBaselinePlayNamesTheEnvironmentItTargets`, `TestStaticToolingIsGivenASentinelRatherThanAnEnvironment` and `TestARunWhoseTargetGroupResolvesToNoHostRefuses`. A different name means changing one module constant, `TARGET_INPUT`.

2. **Should the sentinel's literal value be asserted?** design.md Decision 5 fixes it as `syntax-check-only`. **Assumption taken:** no — the *property* Decision 5 states ("must not name a real environment") is asserted instead, together with the two tools agreeing on one value. Asserting the literal would fail a later rename that broke nothing. **Depends on it:** both tests in `TestStaticToolingIsGivenASentinelRatherThanAnEnvironment`. If the project wants the literal pinned, that is one added `assertEqual`.

3. **Which spelling of the plugin's token option?** design.md Decision 1 uses `api_token`; the committed `hcloud.yml`'s comment uses the older `token`. **Assumption taken:** accept both, so no source is reported as naming no credential merely for spelling the option the other way. **Depends on it:** `test_no_inventory_source_relies_on_the_plugins_bare_credential_fallback` and `test_no_two_inventory_sources_take_the_same_credential_variable`.

4. **How strictly should two inventory sources be required to match?** `test_the_inventory_sources_differ_only_in_the_credential_they_name` compares *parsed* documents with each source's credential name substituted out, so comments and formatting are invisible to it but any structural divergence — an extra `compose:` key on one source, a different `separator` — fails. **Assumption taken:** structural identity is what "adding a file rather than editing one" means in practice. **Depends on it:** that one test. It is the one assertion here most likely to be judged too strict; the correct response if it is, is a reviewed decision to narrow it, not a loosening during implementation.

5. **Is a seventh module the right home, rather than a section of `test_ci_configuration.py`?** AGENTS.md records no convention on when the suite grows a module. **Assumption taken:** a new module, following the precedent of `test_a_second_environment.py`, whose own header gives the reason this pass shares — an independent test author may only add.

6. **Does `AGENTS.md` need updating for the module count?** Its *Testing* section describes `.github/tests` generally and names no module count, so nothing there goes stale. Recorded because it was checked, not because it found something.

## What the implementation step must make pass

Green, from the repository root, at the end of `build:verify`:

```
python3 -m unittest discover --start-directory .github/tests
```

— all 557 tests, the 16 currently red included. Plus, per tasks.md 6.2, the Molecule suites of `hardening`, `deploy_user`, `image_prune` and `platform_data_volume`, **read from the SCENARIO RECAP rather than from the exit code**, with the two scenarios above updated to the new literal by task 5.3.

Task 6.1 asks the implementer to "land the derived `.github/tests/` assertions" and to confirm each fails against the pre-change tree. Both are already done — the module is committed by this pass and the red/green split is recorded above. What remains of 6.1 is confirming the suite is green once the change lands.
