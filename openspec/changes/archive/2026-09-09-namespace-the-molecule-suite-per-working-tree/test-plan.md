# Test plan — namespace-the-molecule-suite-per-working-tree

Written by an author who has not seen and will not write this change's
implementation, from the change's delta specifications alone. Every test below
was authored before any implementation existed; the eight that fail do so
because the thing they read has not been written yet, which is the expected
result and not a defect.

This file is **not an artifact the OpenSpec schema knows about**. It will not
appear among the context files `openspec instructions apply` lists, and has to
be opened on purpose by whoever implements next.

---

## 1. Baseline

**Static suite — full baseline taken.**

    python3 -m unittest discover --start-directory .github/tests   # from the repository root
    → Ran 264 tests ... OK

Taken before a line of this pass was written. Every one of the 264 passed, so
every failure recorded below is attributable to a test this pass added.

After this pass: **294 tests, 8 failures** — the 30 new tests, of which 8 read
the real tree for something the implementation has not yet produced.

**Molecule suite — no baseline taken, and why.**

`molecule test --all` was not run. `molecule` and a reachable Docker daemon are
both present in this working tree, so this is a deliberate refusal rather than
an unavailable tool:

- A pre-change run drives containers named by the shared literals this change
  exists to replace, and writes to the shared ephemeral directory. Taking a
  baseline that way is running the hazard, on a machine `proposal.md` records as
  having carried three live working trees.
- The entry point that would make such a run safe does not exist yet, so there
  is no namespaced way to take one.
- No test this pass wrote runs under that command (see §4), so no later claim
  about a failure depends on a Molecule baseline.

Whoever implements this change still owes the Molecule run its task list asks
for — tasks 2.4, 2.6, 3.1 and 3.2 — and `AGENTS.md` requires reading the
SCENARIO RECAP rather than the exit code when they do.

**Python lint/type completion check — not run, and why.** This repository pins
no `ruff` and no `mypy`, and its `pre-commit` configuration carries no Python
hook. Running an unpinned one would be the unrepeatable-tool shape `AGENTS.md`
warns about and that this change's own task list already declines for
ShellCheck. The new code was read against the trap list in the `python` skill
instead: no mutable default arguments, no loop-variable closures, no generator
re-iteration, no broad `except`.

---

## 2. Where the tests went, and where they did not

All 30 new tests are in
`.github/tests/test_ci_configuration.py`, appended as one section with its own
provenance comment, reusing `authored_scenario_files()`,
`scenario_platform_images()`'s structure, `galaxy_role_directories()`,
`ScenarioTreeFixtureMixin`, `read_text` and `flattened`. No import was added,
no `subprocess` call was added, and the suite's own constraint tests
(`TestTheSuiteNeedsNoPrivilegedResource`) still pass.

**No test was written under `molecule test --all`, and none is owed.** That is
a judgment, not an omission. The Molecule row covers *what an Ansible role
converges to on a host, and how it fails*. Not one scenario in either delta
states a property of a role's converged result:

- The static scenarios are properties of what a `molecule.yml` **says**, which
  `AGENTS.md` places in `.github/tests` explicitly.
- The run-time scenarios are properties of **Molecule's own harness** — its
  `create` refusing, two working trees not colliding, a namespace resolving the
  same way twice. A Molecule scenario runs inside one container in one working
  tree, and its `verify` play runs only after `create` has already succeeded,
  so it cannot observe a `create` that refuses and cannot observe a second
  working tree at all.

The rename this change performs was checked for blast radius **within the
Molecule glob**: no file under `ansible/roles/*/molecule/` outside the
`molecule.yml` files themselves names any current instance name, and none
references `ansible_hostname`, `ansible_nodename`, `inventory_hostname` or
`hostvars[...]`. So no existing Molecule test bears on the rename. Task 2.1a's
sweep of each role's own `tasks/`, `templates/`, `defaults/` and `handlers/` is
**outside this pass's read bounds and was not performed here** — it remains
owed, and the explicit `hostname` does change what `ansible_hostname` and
`ansible_nodename` resolve to inside every container.

---

## 3. Scenario accounting

21 `#### Scenario:` blocks across the two delta specification files: 16 in the
`iac-cicd-pipeline` delta, 5 in the `iac-repo-foundations` delta. All 21 are
accounted for below, each exactly once.

Every test is named in the form the runner selects individually:

    cd .github/tests && python3 -m unittest test_ci_configuration.<Class>.<test>

### 3.1 `iac-cicd-pipeline` — *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* (MODIFIED)

The delta is **purely additive** against the requirement as it stands in
`openspec/specs/iac-cicd-pipeline/spec.md`: it adds two paragraphs and two
scenarios, and alters or removes no existing sentence or scenario. The 14
pre-existing scenarios are therefore accounted for by the tests that already
cover them; this pass wrote no new test for any of them and none is owed.

| Scenario | Covered by | New? |
|---|---|---|
| Ansible-only pull request is linted and syntax-checked | `TestAnsibleBlockingTier.test_the_blocking_tier_runs_ansible_lint`, `.test_the_blocking_tier_runs_an_ansible_syntax_check` | existing |
| A newly added role scenario runs without a workflow change | `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_names_no_role_literally` | existing |
| Every scenario a role declares is executed | `TestMoleculeDiscoveryAndScenarioCoverage.test_molecule_is_invoked_across_all_scenarios` | existing |
| Discovering no roles fails rather than passes | `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing` | existing |
| A failing Molecule scenario blocks the merge | `TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row`, `TestEveryRequiredCheckIsShapedToBeRegistrable.test_every_required_context_names_a_job_whose_name_is_a_literal` | existing |
| A pull request touching no Ansible file starts no container | `TestOnlyTheMoleculeMatrixIsGated.test_the_matrix_job_is_conditioned_on_the_change_detection_output` | existing |
| Role discovery runs even where the suite does not | `TestOnlyTheMoleculeMatrixIsGated.test_role_discovery_runs_whatever_a_pull_request_touched` | existing |
| A manual run verifies the whole suite | `TestChangeDetectionResolvesTheGatesInput.test_a_run_that_is_not_a_pull_request_resolves_to_the_whole_suite` | existing |
| Ansible verification receives no production credential | `TestVerificationJobsCarryNoCredential.*` | existing |
| Every scenario's platform image is pinned by digest | `TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest` | existing |
| A scenario declaring no platform image fails rather than being skipped | `TestMoleculeScenarioImagesArePinnedByDigest.test_no_scenario_declares_a_platform_without_an_image`, `.test_a_scenario_declaring_no_platform_image_is_reported_by_name` | existing |
| Scenarios sharing an image repository agree on its digest | `TestMoleculeScenarioImagesArePinnedByDigest.test_scenarios_sharing_an_image_repository_name_the_same_digest`, `.test_a_partial_digest_refresh_is_reported` | existing |
| Installed Galaxy content is not held to this repository's pinning obligation | `TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest.*` | existing |
| An upstream re-push cannot change what the suite ran against | `TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest` (the digest's content-address form is the only observable this suite can carry) | existing |
| **Every authored scenario's instance name carries the namespace** | `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenarios_instance_name_carries_the_namespace`, `.test_every_authored_scenarios_unset_default_cannot_name_a_container`; discriminated by `TestTheInstanceNameChecksAreARealReadOfTheFile.test_a_bare_literal_name_is_reported`, `.test_a_benign_default_that_would_still_create_an_instance_is_reported`, `.test_an_interpolation_declaring_no_default_at_all_is_reported`, `.test_a_default_that_cannot_name_a_container_is_accepted`, `.test_a_scenario_declaring_no_platform_is_reported_rather_than_passed_over`, `.test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name`, `.test_installed_galaxy_content_is_not_held_to_these_obligations` | **NEW** |
| **Every authored scenario bounds its instance's host name** | `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenario_declares_an_explicit_host_name`, `.test_every_declared_host_name_is_bounded_by_the_scenario_itself`; discriminated by `TestTheInstanceNameChecksAreARealReadOfTheFile.test_a_scenario_declaring_no_host_name_is_reported`, `.test_a_host_name_interpolating_the_namespace_is_reported`, `.test_a_host_name_over_the_byte_limit_is_reported` | **NEW** |

### 3.2 `iac-repo-foundations` — *Verification Writing to Shared State Is Namespaced per Working Tree* (ADDED)

| Scenario | Disposition |
|---|---|
| The binding is stated, not merely implied | **Covered** — `TestTheConventionsFileBindsTheSharedStateRuleToMolecule.test_the_conventions_file_carries_the_binding_section`, `.test_the_binding_names_an_entry_point_committed_to_this_repository`, `.test_the_conventions_file_no_longer_says_coordination_is_the_whole_safeguard`; the "SHALL fail where that statement is absent" half discriminated by `TestTheBindingCheckIsARealReadOfTheFile.*` (10 tests) |
| A run with no namespace refuses rather than sharing | **Partly covered — gap recorded, §4.1** |
| The instance name is resolvable within the limits that govern it | **Partly covered — gap recorded, §4.2** |
| Two working trees verify the same subject concurrently | **Not covered — gap recorded, §4.3** |
| A later session reclaims what an earlier one left | **Not covered — gap recorded, §4.4** |

---

## 4. Gaps — scenarios no test covers, with the reason

Each of these is a run-time property. None was covered by something weaker
wearing its name, and each says what would be needed to close it.

### 4.1 A run with no namespace refuses rather than sharing

**Statically covered:** that the resolved name *cannot be a container name* —
`test_every_authored_scenarios_unset_default_cannot_name_a_container` resolves
every interpolation to its declared default (empty where none is declared) and
fails the name if the result matches Docker's container-name grammar. That is
the property design Decision 4 turns on, and it distinguishes the sentinel from
the benign `-unset` default the design rejects.

**Not covered:** that `molecule create` then actually refuses, and that the
sentinel's instruction is legible in the error. Observing that needs a container
runtime, which the `.github/tests` suite may not use — a constraint its own
`TestTheSuiteNeedsNoPrivilegedResource` asserts. It is not a role's converged
behaviour, so it is not a Molecule scenario either. It is tasks.md 1.3, a manual
verification, and no test command in this repository can hold it.

**What would close it:** a fourth test command able to run a container without
being a Molecule scenario. None exists and this change should not invent one.

### 4.2 The instance name is resolvable within the limits that govern it

**Statically covered:** the value the 64-byte limit actually governs. Once the
scenario declares its own `hostname`, that field is a literal in a committed
file, and `test_every_declared_host_name_is_bounded_by_the_scenario_itself`
reads it: no interpolation (or its length would be decided by the working tree
again) and no more than 64 bytes.

**Not covered:** that `create` succeeds with a 70-character instance name and
the short `hostname` declared. That was verified **by hand in the session that
wrote this plan**, by running a container: a 70-character name failed with
`Bad Request ("hostname is too long (maximum 64 bytes)")`, and the same name
created once a short explicit `hostname` was declared. It is recorded in
design.md Decision 3a and in tasks.md 1.2, and it is not automatable under either
test command, for the same reason as §4.1.

The static half is not a proxy for the run-time half. It establishes that the
limit is respected by what the file declares — nothing more.

### 4.3 Two working trees verify the same subject concurrently

**Not covered by any test.** The scenario asserts a property of two
simultaneous runs in two working trees. `.github/tests` reads committed files
and starts nothing; a Molecule scenario runs in one working tree and one
container and cannot see another.

Two **necessary conditions** are asserted statically, and they are necessary
conditions, not the scenario:

- the container handle is namespaced —
  `test_every_authored_scenarios_instance_name_carries_the_namespace`;
- the two working trees would not collide on a name by accident —
  `test_no_two_authored_scenarios_resolve_to_one_name_within_a_working_tree`.

The **ephemeral-directory** half is asserted nowhere: it lives in the entry
point, whose path and interface no artifact of this change fixes (see §6, Q2).

**What would close it:** tasks.md 2.5 — running the suite from two working trees
at once and reading the container names — performed by hand, and reported with
what `docker ps` showed rather than with an exit code.

### 4.4 A later session reclaims what an earlier one left

**Not covered by any test.** The determinism this scenario turns on lives in the
entry point: the same working tree must resolve the same namespace on a later
day, so a container an earlier run left can be found and removed.

This one is *not* structurally untestable — `.github/tests` already executes
committed shell snippets standalone (`TestTheAggregatingGateDiscriminates`,
`TestChangeDetectionResolvesTheGatesInput`, and
`test_role_discovery_fails_when_it_finds_nothing`, each guarded by
`require_external_tools`), so a test could run the entry point twice from one
fixture directory and once from another and compare the strings.

**It was not written because no artifact of this change fixes what to address.**
The entry point has no stated path, and no stated way to compute the namespace
without also exec'ing Molecule. Writing the test would have meant inventing
both and obliging the implementation to a contract nobody agreed to.

**What would close it:** fix the entry point's path and give it a compute-only
invocation (`--print-namespace`, or the namespace on stdout under a flag). Then
this test is straightforwardly writable in `.github/tests`, and tasks.md 1.1
stops being a manual step. Recommended as a follow-up to this change, not folded
into it.

---

## 5. Assertion classification

Per the testing floor: every assertion is **specified** (traces to SHALL text in
a delta scenario), **derived** (inferred; no scenario states it), or
**deliberately untested**. Each test carries its own label in its docstring;
this is the roll-up.

### Specified

- `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenarios_instance_name_carries_the_namespace`
- `...test_every_authored_scenarios_unset_default_cannot_name_a_container`
- `...test_every_authored_scenario_declares_an_explicit_host_name`
- `...test_every_declared_host_name_is_bounded_by_the_scenario_itself`
- `TestTheInstanceNameChecksAreARealReadOfTheFile.test_a_bare_literal_name_is_reported`
- `...test_a_benign_default_that_would_still_create_an_instance_is_reported`
- `...test_an_interpolation_declaring_no_default_at_all_is_reported`
- `...test_a_default_that_cannot_name_a_container_is_accepted`
- `...test_a_scenario_declaring_no_platform_is_reported_rather_than_passed_over`
- `...test_a_scenario_declaring_no_host_name_is_reported`
- `...test_a_host_name_interpolating_the_namespace_is_reported`
- `...test_a_host_name_over_the_byte_limit_is_reported`
- `...test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name`
- `...test_installed_galaxy_content_is_not_held_to_these_obligations`
- `TestTheConventionsFileBindsTheSharedStateRuleToMolecule.test_the_conventions_file_carries_the_binding_section` (specified in obligation; its fragments are derived — see below)
- `...test_the_binding_names_an_entry_point_committed_to_this_repository` (specified in obligation; what counts as runnable is derived — see below)
- `TestTheBindingCheckIsARealReadOfTheFile.*` — the discriminating half of "the pipeline's own configuration checks SHALL fail where that statement is absent"

### Derived — each one an assertion nobody stated, made visible here for review

| Assertion | Where it comes from | Test |
|---|---|---|
| All authored scenarios interpolate **one** namespace variable | the requirement says "the working-tree namespace", singular; a second variable would leave scenarios on a shared name for any session that did not know about it | `...test_the_authored_scenarios_agree_on_one_namespace_variable`, `TestTheInstanceNameChecksAreARealReadOfTheFile.test_scenarios_disagreeing_on_the_namespace_variable_are_reported` |
| No two authored scenarios resolve to one name inside one working tree | tasks.md 2.2 | `...test_no_two_authored_scenarios_resolve_to_one_name_within_a_working_tree`, `TestTheInstanceNameChecksAreARealReadOfTheFile.test_two_scenarios_resolving_to_one_name_are_reported` |
| The binding section names `collections` and `ansible-galaxy` | design.md Decision 2 (a fresh namespace fails at `create` until the shared collections path is supplied; the binding section names that one-time install) and tasks.md 5.1 | `...test_the_conventions_file_carries_the_binding_section` |
| "How a session takes one" means a **committed, runnable** file — executable, or opening with a shebang | design.md Decision 6; no artifact fixes the entry point's path, so the test reads whatever backticked path the binding names | `...test_the_binding_names_an_entry_point_committed_to_this_repository`, `TestTheBindingCheckIsARealReadOfTheFile.test_a_named_entry_point_that_is_committed_and_runnable_is_found` and siblings |
| `AGENTS.md` no longer says coordination between sessions is the whole safeguard | tasks.md 5.4 | `...test_the_conventions_file_no_longer_says_coordination_is_the_whole_safeguard` |
| Either the executable bit **or** a shebang suffices | requiring both would fail a correct entry point for a reason no artifact states | `TestTheBindingCheckIsARealReadOfTheFile.test_an_entry_point_carrying_the_executable_bit_and_no_shebang_is_found` |

If the implementation reasonably chooses differently on any of these, the floor
permits a derived assertion to be **reconsidered** — recorded as a deliberate
change to a derived assertion, never performed as a silent repair, and never by
editing the assertion to match what the code produced.

### Deliberately untested — identified and left uncovered, with the reason

- **Which variable name carries the namespace.** No artifact fixes it; design
  Decision 5 only rules out a `MOLECULE_` prefix. Every check reads whatever
  variable a scenario names, so the implementation is free here. Asserting the
  absence of a `MOLECULE_` prefix was considered and dropped: design records
  that a prefixed name *works*, so the check would fail a correct-but-different
  implementation over a preference.
- **The entry point's own path.** Same reason; discovered from the binding
  section rather than named.
- **That the binding section says how a session brings its namespace to the
  project's initial state** (tasks.md 5.2). No fragment distinguishes such a
  sentence from the hazard prose `AGENTS.md` already carries — "remove",
  "destroy" and "pruned" all appear there today — and pinning a phrase would be
  inventing the wording. Left to review.
- **That `ansible-verify.yml` supplies the namespace** (tasks.md 6.1). No delta
  scenario states it, and it cannot be asserted without fixing the variable
  name. The observation that closes it is the Molecule matrix running green on
  the pull request that lands this change; a red matrix is the sentinel working.
- **That a declared `hostname` is a valid DNS label.** Docker's exact acceptance
  rules for `--hostname` were not verified in this pass, and a guessed grammar
  could fail a correct value.
- **That each scenario keeps its current name as the prefix of the new one**
  (proposal.md; tasks.md 2.2). Asserting it would freeze the current names into
  the check, which is what `authored_scenario_files()` discovery exists to
  avoid.

---

## 6. Unresolved project questions

A dispatched subagent has no channel to ask on, so each question is recorded
with the assumption taken and the tests that depend on it.

**Q1 — What is the namespace variable called?** Not fixed by proposal.md,
design.md, tasks.md or either delta. *Assumption taken:* none. Every check reads
whatever variable a scenario names. *Tests depending on it:* none constrain the
spelling; `test_the_authored_scenarios_agree_on_one_namespace_variable` requires
only that all scenarios agree on one.

**Q2 — Where does the entry point live, and how is it invoked?** Not fixed by
any artifact. *Assumption taken:* it is a committed file, named in backticks
inside `AGENTS.md`'s binding section, and either executable or opening with a
shebang. *Tests depending on it:*
`test_the_binding_names_an_entry_point_committed_to_this_repository`. This
question is also why gap §4.4 has no test.

**Q3 — Does the binding section name the collections install in those words?**
*Assumption taken:* it contains `collections` and `ansible-galaxy`, matched
case-insensitively, within 2500 characters of a mention of `ANSIBLE_HOME`,
below the generated workflow block. *Tests depending on it:*
`test_the_conventions_file_carries_the_binding_section` and its two fixture
siblings.

**Q4 — Is `TestTheConventionsFileStatesTheMoleculeSharedStateHazard` to survive
task 5.3 unchanged?** tasks.md 5.3 says its assertions should "still pass or be
updated deliberately rather than incidentally", which leaves the choice open.
*Assumption taken:* it survives. Nothing in this pass edits it, and the new
negative assertion was scoped to the one sentence (`coordination between
sessions is the whole safeguard`) that task 5.4 requires to go, so the two do
not conflict. See §7.

---

## 7. Obsolete tests — candidates for human confirmation, never conclusions

**Search bound.** `.github/tests/*.py` and `ansible/roles/*/molecule/*/`, and
nowhere else. No earlier `test-plan.md` was supplied to this pass, so no
scenario-to-test index was available beyond the two globs themselves.

One candidate. It is **not** a recommendation to delete anything, and nothing in
this pass edited, deleted or disabled it.

| Test | Superseded by | Evidence | Status |
|---|---|---|---|
| `test_ci_configuration.TestTheConventionsFileStatesTheMoleculeSharedStateHazard` (all three methods) | the `iac-repo-foundations` ADDED requirement's clause "`AGENTS.md` SHALL carry a section binding this requirement to each service it governs", as carried out by tasks.md 5.3 | The class asserts `AGENTS.md` states the hazard in five literal fragments — `shared across working trees`, `the same container`, `basename`, `rc 137`, `can equally pass` — and asserts two of them near the first. Task 5.3 revises exactly those paragraphs "so they describe the hazard as bounded by this mechanism rather than as standing". A revision that keeps the fragments leaves the class green; one that rewrites them turns it red for a reason that is a decision, not a defect. | **Candidate for human confirmation** |

**Molecule glob: no such test exists — established, not merely unfound.** Every
file under `ansible/roles/*/molecule/` was searched for the current instance
names and for `ansible_hostname`, `ansible_nodename`, `inventory_hostname` and
`hostvars[`. The only matches for "instance" outside the `molecule.yml` files
are prose in comments. No Molecule test reads an instance name or a host fact,
so the rename supersedes none of them.

---

## 8. What the implementation must make pass

Eight tests fail today, all of them reading the real tree for something not yet
written. Every fixture and discrimination test already passes, which is what
establishes the checks read something rather than returning empty lists.

**Fail because `ansible/roles/*/molecule/*/molecule.yml` has not been changed
yet** (tasks 2.2):

1. `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenarios_instance_name_carries_the_namespace`
2. `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenarios_unset_default_cannot_name_a_container`
3. `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_the_authored_scenarios_agree_on_one_namespace_variable`
4. `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_authored_scenario_declares_an_explicit_host_name`
5. `TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree.test_every_declared_host_name_is_bounded_by_the_scenario_itself`

**Fail because `AGENTS.md` has no binding section and no entry point exists**
(tasks 1.4, 5.1, 5.4):

6. `TestTheConventionsFileBindsTheSharedStateRuleToMolecule.test_the_conventions_file_carries_the_binding_section`
7. `TestTheConventionsFileBindsTheSharedStateRuleToMolecule.test_the_binding_names_an_entry_point_committed_to_this_repository`
8. `TestTheConventionsFileBindsTheSharedStateRuleToMolecule.test_the_conventions_file_no_longer_says_coordination_is_the_whole_safeguard`

### One test that passes today, investigated rather than recorded as coverage

`test_no_two_authored_scenarios_resolve_to_one_name_within_a_working_tree`
passes before the implementation exists. Investigated: the current literal
instance names are already pairwise distinct, so the property genuinely holds
already — the benign one of the two explanations a first-run pass can have. It
is kept because the namespacing edit is where an accidental collapse to one name
would be introduced, and it will fail if that happens.

Two other checks would have passed vacuously — reading an empty set, since no
name interpolates anything and no `hostname` is declared today. Both carry an
explicit guard so their silence cannot be mistaken for a result: they now fail
until there is something to read.

---

## 9. Bounds this pass held to

- **Additive only.** This pass adds tests and never subtracts. No existing test
  was edited, deleted or disabled, under any delta operation.
- No file was written outside `.github/tests/*.py` and this manifest.
- **No implementation was written.** No `molecule.yml` was touched, no entry
  point was created, `AGENTS.md` was not edited, and no stub was added to make a
  test execute.
- The change's planning artifacts — `proposal.md`, `design.md`, `tasks.md` and
  the delta specifications — were read as material and not edited. No task was
  marked complete.
- The implementation of the behaviour under test was not read. The `MODIFIED`
  delta was established by comparing it against the requirement as it stands in
  `openspec/specs/iac-cicd-pipeline/spec.md`, not against code.
