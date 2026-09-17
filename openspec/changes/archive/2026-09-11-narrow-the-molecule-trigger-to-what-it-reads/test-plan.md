# Test plan

Tests derived from this change's delta specifications by an author other than
whoever implements it, before any implementation existed. This file is **not an
artifact the OpenSpec schema knows about**: it will not appear among
`openspec instructions apply`'s context files and has to be read on purpose.

- **Change:** `narrow-the-molecule-trigger-to-what-it-reads`
- **Deltas read:** `iac-cicd-pipeline`, two MODIFIED requirements, at commit
  `5b190b5` (the commit holding the approved plan)
- **Test row** (of this project's three): the `.github/tests` row. Every scenario
  this change carries is a static read of a committed file; neither the
  `terraform test` row nor the Molecule row can place a test for any of them.
- **Test command:** `python3 -m unittest discover --start-directory .github/tests`,
  from the repository root
- **Test-path glob:** `.github/tests/*.py`
- **File written:** `.github/tests/test_the_suite_is_triggered_by_what_it_reads.py`
  (28 tests). Nothing else under the glob was touched — this pass adds tests and
  never subtracts.

## Baseline

Taken before writing anything, over the whole of this row's suite:

    $ python3 -m unittest discover --start-directory .github/tests
    Ran 601 tests in 9.358s
    OK

A **full** baseline for this row, not a scoped one: the row's suite is nine
seconds, so there was nothing to buy by narrowing it. Nothing failed beforehand,
so every failure recorded below is attributable to this pass.

The other two rows were not run. The Molecule row needs a container runtime and
the working tree's namespace brought to its initial state, and this change owes
it no new test; that run is this change's own tasks.md 1.7 and 4.2. The
Terraform row has no subject here.

After the pass:

    Ran 629 tests in 10.437s
    FAILED (failures=31)

28 new tests, 24 of them red. The 31st failure is an **existing** test — see
*Obsolete and insufficient tests*, entry 3.

## Which failure state each red is in

Per `ai-toolkit:testing`'s enumeration, and stated because the two states mean
different things to whoever implements next:

- **State 1 — the code ran and produced a wrong value** (5 tests). The workflow
  files exist and are read; what they declare is not yet what the delta
  requires. These are the strongest reds available before an implementation: the
  assertion executed and discriminated. Verified by running the matcher against
  the target declaration as well as the current one — with `ansible/**` plus the
  four negations, both filter assertions pass; with today's bare `ansible/**`,
  both fail. So the red is not an artifact of an assertion that can never be
  satisfied.
- **State 2 — the target does not exist yet** (19 tests). They name a symbol the
  implementation must add to `test_ci_configuration.py` and fail saying so, via
  `suite_symbol()`. **Their assertions never executed**, so whether they are any
  good is still unverified; do not read a green run of them later as
  confirmation that they were right all along — read it as the first time they
  ran at all.

The symbols are fetched lazily rather than imported at module scope precisely so
that these two states stay separable: a module-level import of an absent name
would have collapsed all 24 into one import error and hidden the five real ones.

## Four tests are green at the baseline, and that is not the alarm it looks like

`testing` treats a test passing on its first run before implementation as an
alarm. Four do, and each was investigated rather than recorded as coverage:

| Test | Why it is already green |
|---|---|
| `TestTheLintTierStaysUnexcluded.test_the_lint_filter_declares_the_directory_with_no_negation` | The lint tier is already unexcluded. The delta's new clause requires that it **stay** so; the test's job is to go red on the edit that narrows it, not to drive one. Discrimination confirmed by construction — it asserts the negation list is empty. |
| `TestTheLintTierStaysUnexcluded.test_the_lint_filter_selects_the_paths_the_suite_no_longer_does` | Same. `ansible/**` selects both paths today and must keep doing so. |
| `TestTheSuiteFilterNamesWhatTheSuiteReads.test_the_filter_still_selects_what_the_scenarios_do_read` | The converse guard for the narrowing. Green before because `ansible/**` selects everything; it must stay green after, which is what makes an over-narrowed filter visible. |
| `TestACorrectSkipSaysWhatWasActuallyUnchanged.test_a_failed_discovery_is_not_reported_as_a_correct_skip` | The gate already reads `DISCOVER_RESULT` before anything else, so the row already refuses. The delta states the behaviour rather than introducing it (design.md Decision 6: the gate's structure does not change). The row itself — discovery `failure` paired with change detection `false` — is not in the gate's existing table, which pairs a failed discovery with an **empty** output. |

None is the "asserts nothing" branch of that alarm; all four are the "behaviour
already exists" branch, where the delta's clause is a preservation obligation.

## Scenario coverage

35 `#### Scenario:` blocks across the two MODIFIED requirements; 35 accounted
for below. Tests are named in a form the runner selects individually:

    python3 -m unittest discover --start-directory .github/tests \
        -p 'test_the_suite_is_triggered_by_what_it_reads.py'
    python3 -m unittest test_the_suite_is_triggered_by_what_it_reads.<Class>.<test>
    # (run from .github/tests for the second form, or with that directory on PYTHONPATH)

### Requirement: Ansible Configuration Is Verified in Continuous Integration and Gates the Merge

| # | Scenario | Covered by | State |
|---|---|---|---|
| 1 | Ansible-only pull request is linted and syntax-checked | existing `test_ci_configuration.TestAnsibleBlockingTier.test_the_blocking_tier_runs_ansible_lint`, `.test_the_blocking_tier_runs_an_ansible_syntax_check` | unchanged by this delta; no new test |
| 2 | Narrowing the lint tier's trigger fails the pipeline's own checks | `TestTheLintTierStaysUnexcluded.test_the_lint_filter_declares_the_directory_with_no_negation`, `.test_the_lint_filter_selects_the_paths_the_suite_no_longer_does` | green at baseline (preservation) |
| 3 | A pull request changing only Ansible content no scenario reads starts no container | `TestTheSuiteFilterNamesWhatTheSuiteReads.test_the_filter_does_not_select_the_paths_no_scenario_reads` (declaration half); `TestTheLintTierStaysUnexcluded.test_the_lint_filter_selects_the_paths_the_suite_no_longer_does` (the lint tier still running over them); `TestACorrectSkipSaysWhatWasActuallyUnchanged.test_the_correct_skip_says_nothing_the_suite_reads_changed` (the aggregating job concluding success) | state 1 / green / state 1 |
| 4 | An unconsidered new path under the configuration directory runs the suite | `TestTheSuiteFilterNamesWhatTheSuiteReads.test_the_filter_still_selects_what_the_scenarios_do_read` (carries `ansible/a-directory-nobody-has-considered/new-file.yml`), `.test_the_filter_declares_the_directory_and_exactly_the_established_negations` (the positive at the head, and no negation beyond the four) | green / state 1 |
| 5 | A correct skip says what was actually unchanged | `TestACorrectSkipSaysWhatWasActuallyUnchanged.test_the_correct_skip_says_nothing_the_suite_reads_changed` | state 1 |
| 6 | A committed credential is caught wherever in the repository it lands | `TestTheRelocatedScansMatchOverASuppliedFileList.test_a_token_marker_is_caught_wherever_in_the_repository_it_lands`, `.test_a_private_key_marker_is_caught_wherever_in_the_repository_it_lands`, `.test_a_clean_file_list_yields_no_offender`; independence-from-change-detection half by `TestTheRepositoryScopeScansNoLongerRunOnlyWhenAnsibleChanges.test_no_relocated_scan_remains_in_the_verify_plays` plus existing `test_ci_configuration.TestRequiredCheckIsNotPathFiltered` | state 2 / state 1 |
| 7 | A credential assigned across a folded scalar's continuation is still caught | `TestTheRelocatedScansMatchOverASuppliedFileList.test_a_folded_scalar_assignment_of_a_literal_is_caught`, `.test_a_folded_scalar_assignment_of_an_environment_lookup_is_accepted`, `.test_an_inline_vault_value_is_accepted` | state 2 |
| 8 | A second read of an already-permitted path is still refused | `TestThePremiseTheExclusionsRestOnIsChecked.test_a_second_read_of_an_already_permitted_path_is_refused` | state 2 |
| 9 | Editing a scenario above a permitted read does not invalidate the permitted set | `TestThePremiseTheExclusionsRestOnIsChecked.test_a_permitted_read_shifted_to_another_line_is_still_recognised` | state 2 |
| 10 | A scenario reaching an excluded path fails the pipeline's own checks | `TestThePremiseTheExclusionsRestOnIsChecked.test_a_scenario_reaching_an_excluded_path_is_named` | state 2 |
| 11 | A controller read that does not delegate is still a controller read | `TestThePremiseTheExclusionsRestOnIsChecked.test_a_controller_read_that_does_not_delegate_is_still_a_controller_read` (five subTests, one per route); `.test_an_unrecognised_construction_carrying_a_repository_path_is_refused` for the closing refusal | state 2 |
| 12 | A read of the managed node is not held to the enumerated paths | `TestThePremiseTheExclusionsRestOnIsChecked.test_a_read_of_the_managed_node_is_not_held_to_the_enumerated_paths` | state 2 |
| 13 | A newly added role scenario runs without a workflow change | existing `test_ci_configuration.TestMoleculeDiscoveryAndScenarioCoverage` | unchanged; no new test |
| 14 | Every scenario a role declares is executed | existing, same class | unchanged; no new test |
| 15 | Discovering no roles fails rather than passes | existing, same class | unchanged; no new test |
| 16 | Discovery failing is not reported as a correct skip | `TestACorrectSkipSaysWhatWasActuallyUnchanged.test_a_failed_discovery_is_not_reported_as_a_correct_skip` | green at baseline (preservation) |
| 17 | A failing Molecule scenario blocks the merge | existing `test_ci_configuration.TestTheAggregatingGateDiscriminates.test_the_gate_concludes_as_the_table_says_on_every_row` (rows 4 and 7) | unchanged; no new test |
| 18 | A pull request touching no Ansible file starts no container | existing `test_ci_configuration.TestChangeDetectionResolvesTheGatesInput.test_the_change_filter_selects_the_whole_configuration_directory` (its over-match half, which this change does **not** retire) | unchanged; no new test |
| 19 | Role discovery runs even where the suite does not | existing `test_ci_configuration.TestOnlyTheMoleculeMatrixIsGated` | unchanged; no new test |
| 20 | A manual run verifies the whole suite | existing `test_ci_configuration.TestChangeDetectionResolvesTheGatesInput` | unchanged; no new test |
| 21 | A change to a pinned manifest runs the suite | `TestTheSuiteFilterNamesWhatTheSuiteReads.test_the_filter_still_selects_what_the_scenarios_do_read` (carries both `ansible/requirements.yml` and `ansible/requirements-test.txt`) | green at baseline |
| 22 | Ansible verification receives no production credential | existing `test_ci_configuration.TestVerificationJobsCarryNoCredential` | unchanged; no new test |
| 23–29 | Every scenario's platform image is pinned by digest; A scenario declaring no platform image fails rather than being skipped; Scenarios sharing an image repository agree on its digest; Installed Galaxy content is not held to this repository's pinning obligation; An upstream re-push cannot change what the suite ran against; Every authored scenario bounds its instance's host name; Every authored scenario's instance name carries the namespace | existing `test_ci_configuration.TestMoleculeScenarioImagesArePinnedByDigest` and `TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest` | unchanged; no new test |

### Requirement: The Continuous-Integration Configuration Is Itself Verified

| # | Scenario | Covered by | State |
|---|---|---|---|
| 30 | A regression in CI configuration fails the pull request that introduces it | existing `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck`, `TestTheSuiteDiscriminates` | unchanged; no new test |
| 31 | The suite runs regardless of what a pull request touched | existing `test_ci_configuration.TestRequiredCheckIsNotPathFiltered` | unchanged; no new test |
| 32 | A repository-scope scan is not confined to one directory's trigger | `TestTheRepositoryScopeScansNoLongerRunOnlyWhenAnsibleChanges.test_no_relocated_scan_remains_in_the_verify_plays` | state 1 |
| 33 | An ignored file is not scanned and does not fail the suite | `TestTheScansReadTheRepositorysTrackedFiles.test_ignored_content_is_not_scanned_and_does_not_fail_the_suite` (the tracked-set half, against a real throwaway repository); `TestTheRelocatedScansMatchOverASuppliedFileList.test_the_scans_report_only_what_the_supplied_file_list_holds` (the scans-are-a-function-of-the-list half) | state 2 |
| 34 | A scan that cannot enumerate tracked files fails rather than skipping | `TestTheScansReadTheRepositorysTrackedFiles.test_an_unavailable_enumeration_fails_rather_than_skipping` | state 2 |
| 35 | The suite needs no privileged or external resource | existing `test_ci_configuration.TestTheSuiteNeedsNoPrivilegedResource` and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` — **which this change must re-point**, see entry 3 below | unchanged by me |

### Requirement prose covered outside any scenario

Two clauses of the delta are normative prose that no scenario reaches, and both
are asserted anyway because losing either is silent:

- "Matching within a tracked file SHALL be over its bytes rather than over a
  decoded string" →
  `TestTheRelocatedScansMatchOverASuppliedFileList.test_matching_is_over_bytes_so_an_undecodable_file_fails_nothing`
  and `TestTheScansReadTheRepositorysTrackedFiles.test_the_enumeration_returns_the_bytes_of_each_tracked_file`.
- "a tracked path absent from the working tree SHALL fail naming that path" →
  `TestTheScansReadTheRepositorysTrackedFiles.test_a_tracked_path_absent_from_the_working_tree_fails_naming_it`.

## Deliberately untested

Recorded so that the absence of a test is distinguishable from the absence of
the thought.

1. **What `dorny/paths-filter` DOES with the declared patterns.** Asserted as a
   declaration only. Reproducing picomatch needs a dependency this suite is
   forbidden from taking and running the action needs a network call it is
   forbidden from making — the delta itself says so ("the suite SHALL assert the
   declaration and the behaviour SHALL be established by observation on a real
   pull request"). The matcher in the new module is a deliberate approximation
   for this suite's own use; where it and the action disagree, the action wins.
   The behaviour is this change's tasks.md section 6.
2. **That the correct-skip message names the lint tier** as what did run over the
   excluded paths. tasks.md 2.2 says it *should*; no delta clause requires it.
   Asserting it would constrain wording nobody agreed to.
3. **That the `ghcr_pull_token` scan reads *only* YAML.** The positive is
   asserted (`.test_the_assignment_scan_reads_yaml_files`); the exclusion of
   non-YAML is not. Reporting a `.txt` would be harmless, and an assertion that
   the scan reads *less* is one this author would be inventing.
4. **That the three scans are clean on the real tree**, and that the premise
   check is green over the real scenario set. Those are the production
   assertions themselves — tasks.md 1.2–1.4, 1.6 and 3.1–3.3 — and are the
   implementing author's, not this pass's. The fixtures here establish that the
   scans and the check are *capable of red and of green*; the standing
   assertions over the repository are what make them checks.
5. **That branch protection blocks a merge.** Repository settings; this suite
   makes no network call. Unchanged by this change.

## Assertion classification

Every assertion in the new module is annotated in its own docstring. Summary:

- **SPECIFIED** — all but two. Each traces to SHALL text or to a scenario in the
  delta.
- **DERIVED** — exactly two, each saying so in its docstring and each naming
  what to reconsider rather than weaken:
  - `TestTheRelocatedScansMatchOverASuppliedFileList.test_the_assignment_scan_reads_yaml_files`
    — the YAML restriction traces to tasks.md 1.3, not to a scenario.
  - `TestThePremiseTheExclusionsRestOnIsChecked.test_a_delegated_task_that_opens_no_file_is_passed_over`
    — design.md Decision 1's second deliberately-excluded class. The scenario
    states the managed-node case; this is the other half of the same criterion
    (*of a repository file*, as distinct from *on the controller*), and it is
    what keeps someone from reaching for "touches the controller".
- **Deliberately untested** — the five above.

## Interface assumptions

These tests were written before the implementation, so the names below are
assumptions, recorded here so they can be implemented **to** rather than around.
Every one of them takes its file set or its root as an argument, which is what
tasks.md 1.5 and 3.4 require in order for the negative cases to be exercisable
against a fixture. All 19 state-2 tests depend on them.

In `.github/tests/test_ci_configuration.py` (the home tasks.md 1.1 fixes):

    class TrackedFilesUnavailable(AssertionError): ...
        # raised where the enumeration cannot be made, and where a listed path
        # is absent from the working tree. An AssertionError subclass for the
        # reason ManifestNotUsable already is: an unhandled one FAILS the
        # calling test rather than erroring it.

    def tracked_files(root: Path | None = None) -> dict[str, bytes]
    def files_carrying_a_token_marker(files) -> list[str]
    def files_carrying_a_private_key_marker(files) -> list[str]
    def ghcr_token_literal_assignments(files) -> list[str]   # "<path>:<line>"
    def unpermitted_controller_reads(root: Path | None = None) -> list[str]

`files` is the mapping `tracked_files()` returns: repository-relative POSIX path
to that file's **bytes**. Each offender string must name the file it refers to;
the premise check's must additionally name the read (its construction or its
target) — the delta requires the refusal to identify "that scenario and that
read", and the tests assert the file path appears and, for the excluded-path
case, that the target does too. A different set of names is fine; re-point the
tests' `suite_symbol(...)` calls rather than reshaping the assertions.

## Unresolved project questions

No channel exists to ask on from a dispatched pass, so each is recorded with the
assumption taken and what depends on it.

1. **Where a test-writing pass may place tests when the change's implementation
   lands in the same file.** `AGENTS.md` fixes the test command and the glob but
   records nothing about this collision. **Assumption:** a new module under
   `.github/tests/`, importing the implementation's helpers from
   `test_ci_configuration`, because this pass may only add and that module is an
   existing test file. The sibling-import idiom is the directory's established
   one (four modules already do it) and
   `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` explicitly
   admits it. **Depends on it:** the whole new module. If the implementing author
   would rather these lived inside `test_ci_configuration.py`, moving them is
   their edit to make, not this pass's.
2. **Whether `git` is admitted as a spawned binary in this suite.** The delta
   admits the enumeration exception in prose; no committed check yet reflects
   it. **Assumption:** it will be, and the implementation must widen
   `TestTheSuiteNeedsNoPrivilegedResource.SPAWNABLE` regardless of this file.
   **Depends on it:** the four tests in
   `TestTheScansReadTheRepositorysTrackedFiles`, and — until the widening — the
   existing directory-wide assertion, entry 3 below.
3. **Whether the premise check's permitted set is keyed on repository-relative
   paths.** The fixtures reproduce real scenario paths
   (`ansible/roles/docker/molecule/default/verify.yml`) inside a temporary root,
   which is the only way to exercise the "same file, same construction, same
   target" case the delta names. **Assumption:** a permitted entry's file is
   identified relative to the root passed in, not to `ROOT`. **Depends on it:**
   `test_a_second_read_of_an_already_permitted_path_is_refused` and
   `test_a_permitted_read_shifted_to_another_line_is_still_recognised`.

## Obsolete and insufficient tests

**Candidates for human confirmation, every one.** Nothing in this pass edited,
deleted or disabled any of them; the search was bounded to the dispatched
test-path glob `.github/tests/*.py`, and no earlier `test-plan.md` was supplied
to read a scenario-to-test mapping from. So: entries 1 and 2 are "no bearing
test beyond these was found by this search", not "no other bearing test exists".

1. **`test_ci_configuration.TestChangeDetectionResolvesTheGatesInput.test_the_change_filter_selects_the_whole_configuration_directory`** — obsolete in part.
   - *Superseded by:* the MODIFIED *Ansible Configuration Is Verified…*
     requirement — "What the suite reads is narrower than `ansible/`, and the
     difference SHALL be declared as exclusions" — and scenario "A pull request
     changing only Ansible content no scenario reads starts no container".
   - *Evidence:* its `CONFIGURATION_PATHS` tuple includes
     `ansible/playbooks/host-baseline.yml` and `ansible/inventory/prod.hcloud.yml`,
     and it asserts the `ansible-verify` filter selects **every** entry. Its
     matcher is `any(gh_glob_matches(pattern, path) for pattern in patterns)`,
     which is negation-blind: the positive `ansible/**` keeps matching both paths
     after the narrowing, so the assertion **keeps passing while asserting the
     opposite of the new requirement** and can never go red on it. Confirmed by
     running the module's own matcher against the target pattern list.
   - *Not obsolete in whole:* its over-match half (`NON_CONFIGURATION_PATHS`)
     still holds and still covers scenario 18.
   - *Revision task:* tasks.md 2.3.
2. **`test_ci_configuration.TestAnsibleBlockingTier.test_an_ansible_path_filter_selects_changes_under_ansible`** — insufficient rather than obsolete.
   - *Superseded by:* the new clause "That the lint tier remains unexcluded SHALL
     be asserted, not reviewed… An assertion establishing only that a filter for
     this directory exists does not establish this", and scenario "Narrowing the
     lint tier's trigger fails the pipeline's own checks".
   - *Evidence:* it reads the `filters:` block as a **string** and searches it
     for `^\s*ansible\s*:`. It therefore passes on a filter narrowed to
     `ansible/roles/**`, or one carrying negations, or one selecting nothing at
     all. Nothing it asserts becomes false; what the delta adds is a proposition
     it cannot reach.
   - *What now covers the gap:* `TestTheLintTierStaysUnexcluded`, both tests.
     Whether the older assertion is kept alongside is the implementing author's
     call — it is not weakened by keeping it.
   - *Adding task:* tasks.md 2.4.
3. **`test_ci_configuration.TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource.test_no_module_in_the_directory_spawns_a_container_runtime_or_terraform`**, and its by-name sibling **`TestTheSuiteNeedsNoPrivilegedResource.test_the_suite_spawns_no_terraform_binary_or_container_runtime`** — insufficient; both need re-pointing.
   - *Superseded by:* "Enumerating the repository's tracked files is admitted as
     an exception to the standard-library limit and to nothing else… it invokes
     the version-control binary that placed the files there."
   - *Evidence:* `SPAWNABLE = {"bash", "sh"}`. The directory-wide one is **red
     now**, on `module='test_the_suite_is_triggered_by_what_it_reads.py'`, which
     spawns `git` to build the throwaway repositories the tracked-file
     assertions read. The by-name one will go red the moment tasks.md 1.1 puts a
     `git ls-files` subprocess in `test_ci_configuration.py` — so the widening is
     owed by the implementation whether or not this new module exists.
   - *What the widening must preserve:* the delta bounds the exception to a
     binary "present because the repository was obtained at all", and says it
     SHALL NOT be read as admitting binaries generally. Add `git` and record
     that bound in the docstring; do not relax the assertion's shape.
   - *No task in `tasks.md` currently names this.* Recorded here as a gap in the
     task list rather than resolved.

No test was found that asserts the aggregating gate's correct-skip **message**,
so scenario 5 retires nothing: the existing gate table asserts that row's
conclusion and says nothing about its wording.

## A finding about the planning artifacts, not acted on

Reported rather than fixed — revising this change's artifacts is not this pass's
to do.

**design.md Decision 1's table claims completeness it does not have.** It says
"Thirteen entries cover every read of a repository file from the controller
across this repository's seventeen authored scenarios", and tasks.md 3.3
enumerates the permitted set "from design.md Decision 1's table and from nothing
else". Every one of the seventeen authored `molecule.yml` files carries

    dependency:
      name: galaxy
      options:
        requirements-file: ../../../../requirements.yml

which is a controller-side read of a committed repository file — `ansible/requirements.yml`
— by a route the table does not list and the permitted set does not name. It is
the exact counterpart of the tenth entry (`ANSIBLE_ROLES_PATH`): one declaration
repeated once per scenario, so it wants a per-file count of one, not a total of
seventeen.

**The exclusions are not endangered by it** — the path it reaches is
`ansible/requirements.yml`, which remains a trigger — so this is a completeness
defect in the enumeration rather than a safety one. What it costs is day-one
greenness: a premise check that reads `molecule.yml` wholesale and closes by
refusing unrecognised constructions will refuse seventeen of them, and the
implementer's cheapest escape is to narrow the check by a rule nobody wrote
down, which design.md itself names as how the first version of this design went
wrong.

No test in this pass asserts either polarity for it: asserting it is permitted
would invent a fourteenth entry, and asserting it is refused would force the
check red on the tree as it stands. Both are decisions for the change's
artifacts.
