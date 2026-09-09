# Test plan — `notice-when-a-periodic-job-stops-reporting`

Derived from this change's two delta specs, before any implementation of it
existed and without reading any implementation of it. Written by an author
other than whoever implements the change, per `AGENTS.md`'s *derive tests*
step.

**This file is not an artifact the OpenSpec schema knows about.** It does not
appear among `openspec instructions apply`'s context files and has to be read
on purpose. Read it before implementing: it carries what each test asserts,
which assertions are SPECIFIED and which DERIVED, the shape assumptions the
tests take about the implementation, and the delta scenarios no test covers.

## Both rows, and how to select a single test

| Row | Command | Where from |
|---|---|---|
| A — static reads of committed files | `python3 -m unittest discover --start-directory .github/tests` | repository root |
| B — what `image_prune` converges to on a host | `molecule test -s <scenario>` | `ansible/roles/image_prune/` |

A single Row A test, individually selectable:

```
cd .github/tests
python3 -m unittest test_ci_configuration.TestEveryScheduledWorkflowReportsItsOwnLiveness \
    .test_every_scheduled_workflow_carries_a_liveness_report
```

Row B has four scenarios now: `abandon-paths`, `absent-heartbeat-key`,
`default`, `heartbeat`. **Run them individually with `-s` while the role is
red.** `molecule test --all` runs them in sorted order and stops at the first
failure, so every scenario sorting after a failing one is silently not
executed and absent from the SCENARIO RECAP (`AGENTS.md`, "Testing"). Note
that `absent-heartbeat-key` sorts second and `heartbeat` sorts last.

**No Molecule scenario was executed while writing these tests.** Molecule's
container name and its ephemeral directory are shared across working trees,
and another session may have been running it; a collision corrupts both runs
and can pass falsely. The Row B files are written and statically checked, not
run.

## Baseline

| What | Result |
|---|---|
| Row A, full suite, before any test was written | **264 tests, 0 failures, 0 errors, 0 skips** (`python3 -m unittest discover --start-directory .github/tests`, 2026-09-09) |
| Row A, full suite, after | **302 tests, 22 failure records over 20 failing test methods** — unittest counts a `subTest` failure separately, and two of the new tests fail once per subject they read. Every failure is one of the 38 tests added here; the 264 pre-existing tests are still green |
| Row B | **Not run**, deliberately — see above. No baseline exists for it, and no claim below rests on one |
| `ansible-lint ansible/roles/image_prune/` | Passed, 0 failures, 19 files processed, profile `production` — run **after** the new scenarios were written, with the pinned toolchain installed (`ansible-core==2.21.3`, `molecule==26.8.0`, matching `ansible/requirements-test.txt`) |

Row A needs `python3` and PyYAML 6.0.1 (`.github/requirements-ci.txt`) and
nothing else — no network, no credential, no container runtime, no Terraform.

## Scenario accounting

Seventeen `#### Scenario:` blocks across the two deltas — 8 in
`iac-cicd-pipeline`, 9 in `iac-host-configuration`. Every one is accounted for
below exactly once.

Test names are given as `Class.test_method` for Row A and as the scenario plus
its assertion task's name for Row B.

### `iac-cicd-pipeline` — Scheduled Workflows Report Their Own Liveness

| # | Scenario | Covered by | Notes |
|---|---|---|---|
| 1 | A scheduled run that fails is reported as a failure | `TestEveryScheduledWorkflowReportsItsOwnLiveness.test_the_reporting_job_runs_whatever_the_outcome`, `.test_the_failure_branch_keys_on_a_needed_job_having_failed`, `.test_every_ping_url_requests_the_check_be_created` | Static: that the reporter is SHAPED to report a failure without waiting for the silence timeout. Nothing in this repository executes a workflow, so that it does report is the confirm gate's |
| 2 | A workflow that stops running at all is detected | **Uncovered** | The alarm is the observer's SILENCE, configured at a third party. No assertion in this tree can observe a vendor's period and grace, and `design.md` says so rather than implying otherwise. Approximating it would assert something else. Established by task 6.6's scratch five-minute check |
| 3 | A run in which a conditional job is skipped reports success | `.test_the_failure_branch_keys_on_a_needed_job_having_failed` | The `success()` half of that test IS this scenario: under `if: always()`, `success()` is false for a merely skipped job |
| 4 | A failure in an early job is still reported | `.test_the_reporting_job_depends_on_every_other_job_in_its_workflow`, `.test_the_reporting_job_runs_whatever_the_outcome` | |
| 5 | A cancelled run raises no alarm of its own | `.test_a_cancelled_run_reports_neither_success_nor_failure` | Asserts the reporting job mentions `cancelled()` at all. It does not assert WHICH branch is guarded — a static read cannot evaluate the condition |
| 6 | A scheduled workflow added without a report fails the pull request | `.test_every_scheduled_workflow_carries_a_liveness_report` + the pre-existing `TestTheSuiteIsWiredIntoTheRequiredCheck` | The first is the check; the second is what makes it gate a pull request. Discovery is over `schedule:`-triggered workflows, so a workflow added later is covered with no test edit |
| 7 | The report needs no human approval | `.test_no_reporting_job_declares_a_deployment_environment`, `.test_the_reporting_job_reads_a_repository_scoped_secret` | |
| 8 | The routine alarm does not consume the last-resort one | **Partially covered** by `.test_the_reporting_job_reads_a_repository_scoped_secret` | The in-tree half: the reporter reads no `PLATFORM_*` secret, `PLATFORM_DEADMANSWITCH_URL` among them. The alert DESTINATION is provider-side configuration and is not in this tree (Decision 10); task 1.3 and the confirm gate are where it is established |

### `iac-host-configuration` — Scheduled Host Units Report Their Own Liveness

| # | Scenario | Covered by | Notes |
|---|---|---|---|
| 1 | A failed activation is reported as a failure | `heartbeat` → *Assert a failed activation reports a failure under this unit's own identifier*; statically `TestEveryTimerInstallingRoleReportsItsUnitsLiveness.test_every_such_service_unit_reports_from_the_init_system` | The failure is the prune's real abandon path, not a substituted command |
| 2 | A run killed by its own bound is reported | `heartbeat` → *Assert a run killed on its own bound still reports a failure*; statically `TestTheHostReporterKeepsTheAddressOffTheCommandLine.test_the_report_branches_on_the_service_result_not_the_exit_status` | **Partly substituted — read the next section before judging it.** |
| 3 | A successful activation is reported | `heartbeat` → *Assert a successful activation reports success under this unit's own identifier* | Runs the real prune to completion |
| 4 | A timer that stops firing is detected | **Uncovered** | Same reason as the workflow half: the alarm is a third party's silence timeout, which is not in this tree |
| 5 | An undeliverable report leaves a local trace | `heartbeat` → *Assert an undeliverable report leaves the unit successful and the journal informative*; statically `TestEveryTimerInstallingRoleReportsItsUnitsLiveness.test_a_failed_report_cannot_fail_the_unit` and `TestTheHostReporterKeepsTheAddressOffTheCommandLine.test_an_undeliverable_report_is_written_to_the_hosts_log` | |
| 6 | The report address is not world-readable on the host | `heartbeat` → *Assert the address is readable only by the account the unit runs as* | |
| 7 | An absent report address is reported by name | `absent-heartbeat-key` → all five of its assertions | Modelled on `hardening/molecule/absent-ssh-cidrs`, including its success branch |
| 8 | A report is observable without reaching the external observer | `TestNoTimerRoleScenarioReachesTheExternalObserver.test_no_scenario_leaves_the_reporter_pointed_at_the_external_observer` and `.test_every_scenario_supplies_the_ping_key_the_role_requires`; demonstrated by the `heartbeat` scenario as a whole | The static test is what makes "no scenario reaches the vendor" a property of ALL of them rather than of the reporting ones |
| 9 | Installing the report does not activate the unit | `heartbeat` → *Assert installing the reporting neither reported nor pruned* | Reads a sink that received nothing AND an unchanged image list; the scenario's default `test_sequence` converges twice, which is the scenario's "already installed" premise |

Also asserted, though no scenario states them on their own: the slug
derivation (`.test_every_reporter_addresses_the_slug_derived_from_its_own_filename`),
the per-host slug template
(`.test_every_host_reporter_addresses_a_slug_templated_per_host`), pairwise
distinctness across both halves
(`TestEveryReportersIdentifierIsDistinct.test_every_reporter_this_repository_defines_addresses_its_own_check`),
that every timer-installing role has a service unit to hang the report on, and
`?create=1` on every URL both halves build.

## Shape assumptions these tests take, and where they could be wrong

Every one is a DERIVED assertion. If the implementation satisfies the
requirement by another means, that is a reconsideration to be made
deliberately and recorded — not a test to be weakened until it passes. The
testing floor's rule holds: a SPECIFIED assertion that fails means the code is
wrong; only a DERIVED one may be reconsidered.

1. **`?create=1` is read as two whole URLs.** Both halves assume the reporter
   builds a complete success URL and a complete `/fail` URL, each carrying its
   own query string (`tasks.md` 2.1 and 3.3 are written that way). An
   implementation that builds one URL and appends `/fail` and `?create=1`
   separately satisfies the requirement and fails
   `.test_every_ping_url_requests_the_check_be_created` and
   `.test_both_endpoints_the_reporter_builds_request_the_check_be_created`.
2. **`curl`'s command line is read positionally.** The negative task 4.8a
   demands is implemented as three rules — no `://`, no expansion of a
   variable whose NAME could hold the address or key, and no operand at all,
   since curl's operands are URLs. It deliberately permits an expansion whose
   name is unrelated in a flag's value, because Decision 9 carries
   `$EXIT_STATUS` in the ping body. The residual hole is stated in the test's
   own docstring: `curl --silent "$X"`, where `X` was assigned the URL earlier
   under an unrelated name, passes. Closing it needs dataflow, not text.
3. **The reporting script is discovered as "committed text in the role that
   invokes `curl`".** A reporter that shelled out to something else — `wget`,
   a Python one-liner — would be read as no reporter at all and fail loudly
   rather than silently, which is the right direction, but it is an assumption.
4. **Units are read inline from `tasks/main.yml`** via `copy:`/`content:`,
   which is the shape this repository writes them in and the shape task 4.7
   names. A role that moves its units into files under `templates/` would fall
   out of discovery — which is why every assertion quantified over that
   discovery is guarded by a test that FAILS when the discovery finds nothing.
5. **Role variable names** `image_prune_heartbeat_base_url` and
   `image_prune_heartbeat_ping_key`, and the on-host path
   `/etc/prune-host-images/heartbeat.env`, are taken from `tasks.md` 3.1. The
   reporting script's own path is NOT assumed: the `heartbeat` scenario reads
   it out of the installed unit's `ExecStopPost=` line.
6. **The journal message's wording.** The undeliverable-report assertion looks
   for the slug and for the string `curl` in the unit's journal. The slug half
   is the requirement's ("the attempted endpoint"); the `curl` half assumes
   `--show-error`'s own message reaches the journal, which is what task 3.3
   prescribes.
7. **The absent-input diagnostic names `group_vars/prod.yml`.** "Naming the
   input" is SPECIFIED; that particular path as the way to satisfy "and how to
   supply it" is DERIVED from task 1.2 — the same classification
   `hardening/molecule/absent-ssh-cidrs` records for its own.

### What the killed-activation arrangement substitutes

Task 4.9 says to record this rather than approximate it, so it is recorded
plainly. `heartbeat`'s last arrangement writes a systemd drop-in replacing the
unit's `ExecStart=` with a command that outlives a three-second
`TimeoutStartSec=`.

- **Real:** the systemd path (asserted as `Result=timeout`, which is that
  arrangement's own vacuity guard), the kill from outside the process, the
  absence of any output from the killed process, the installed
  `ExecStopPost=`, and the reporting script. That is the whole of what the
  scenario states.
- **Substituted:** the REASON the process hung. In production that is a
  container runtime that stopped answering, which cannot be produced
  deterministically inside a Molecule instance — wedging the daemon breaks the
  same daemon this scenario's own fixture needs, as `default`'s verify.yml
  already records for the duration bound.

If the project judges that substitution unacceptable, the arrangement can be
deleted without touching any other assertion in the file, and this scenario
then joins the uncovered list with that reason.

## Obsolete tests

**Not applicable.** Both deltas are `ADDED`; the change carries no `MODIFIED`,
`REMOVED` or `RENAMED` delta, so no existing requirement is superseded and no
existing test can be bearing on superseded behaviour. Nothing existing was
edited, deleted or disabled — see below.

## Unresolved project questions, and the assumptions taken

Recorded rather than resolved silently, because this pass had no channel to
ask on.

1. **Task 4.8b versus task 4.10 conflict, and how it was resolved.** 4.8b says
   *every* `image_prune` scenario supplies a ping key; 4.10 requires a scenario
   that converges with none supplied. Both cannot hold. The static test exempts
   a scenario that converges EXPECTING a refusal, identified by its
   `rescue:` — a structural marker, not its name — and does **not** waive that
   scenario's base-URL obligation. If the project wants the exemption spelled
   differently, that is a change to
   `TestNoTimerRoleScenarioReachesTheExternalObserver.test_every_scenario_supplies_the_ping_key_the_role_requires`.
2. **The existing `REQUIRED_INPUT_ASSERTIONS` map was not extended.** It names
   `hardening` and `deploy_user` and asserts the four limbs plus
   first-task-ness for each. `image_prune`'s new required input is not in it,
   and adding it would edit existing tests, which this pass may not do. The
   implementer may want to add the entry; task 3.2 and Decision 13 put
   `image_prune` in that class.
3. **Which of `image_prune`'s two assertions comes first** is not asserted
   anywhere. The delta requires the refusal before any host change; both
   asserts satisfy that, and `absent-heartbeat-key` supplies `deploy_apps` so
   that the refusal it observes is the one it is about.
4. **The documentation clause is untested.** Both deltas require the slugs,
   period and grace to be recorded in the host-bootstrap documentation and
   referenced from the runbook. That is a static read of a committed file and
   could be asserted in Row A — but `tasks.md` section 4 assigns it no test, so
   none was written rather than one being invented. Named here so the absence
   of the test is distinguishable from the absence of the thought.
5. **`heartbeat`'s success case needs the container runtime and one pulled
   image** (`alpine:3.19`, inside the instance, as `default` and
   `abandon-paths` already do). The prune abandons on a host whose keep set is
   empty, so a successful activation is not otherwise reachable. If the project
   would rather this scenario carry no runtime, the success case would have to
   be reached through a substituted `ExecStart=`, which weakens it.

## Assertion classification

Per-assertion SPECIFIED / DERIVED classification lives in each test's own
docstring (Row A) and in each verify.yml's header and inline comments (Row B),
in the form `test_ci_configuration.py` already uses throughout. The summary:
every assertion tracing to SHALL text or to a `#### Scenario:` block is marked
SPECIFIED; the slug derivation, `?create=1`, `ExecStopPost=` as the directive,
the `PLATFORM_` prefix as the marker of an Environment secret, the variable
names, and the discovery guards are marked DERIVED with the decision or task
they trace to.

## What is red now, and what implementing this change must make green

20 of the 38 Row A tests added here fail today (unittest reports 22 failure
records; two of them fail once per subject they read). Every one fails in the
**target-absent** state — no reporting job exists in either workflow, the role
installs no `ExecStopPost=`, no reporting script and no `heartbeat.env`, and no
scenario supplies the new variables. None of them has executed its assertions
against a reporter yet, so none establishes that the assertion is any good.

18 pass, and none of them is coverage of this change:

- three guards, which assert the repository still has what the universal
  assertions quantify over: two scheduled workflows, one timer-installing
  role, and a service unit for every installed timer (that last is the
  requirement's premise rather than the requirement — `image_prune` already
  satisfied it before this change);
- three module audits over `.github/tests/*.py`, which hold the no-network,
  no-credential, no-container, no-Terraform constraint for the directory as a
  whole rather than for one file (task 4.11);
- twelve fixture tests in `TestTheLivenessChecksAreARealReadOfTheFile`, which
  exercise the new predicates against fixture text — one conforming shape and
  one defect per assertion. They are what establishes that the 22 red tests
  would go GREEN on a conforming reporter and stay red on the specific defects
  they name; a check that can only fail is worth as little as one that can only
  pass. Two real defects in this pass's own predicates were caught by that
  class before it shipped.

Both Row B scenarios fail today: `heartbeat` fails at converge on the
undefined ping key, and `absent-heartbeat-key` records `succeeded` — because
the role currently converges happily with no address — which its first
assertion then fails on.

## This pass added tests and subtracted nothing

No existing test was edited, deleted or disabled. The Row A work is a new
section appended to `.github/tests/test_ci_configuration.py` — no existing
assertion, helper or constant in that file was changed. Row B is two new
scenario directories; `default`'s and `abandon-paths`' files were not touched,
and task 3.6's additions to them remain the implementer's.

## Files

- `.github/tests/test_ci_configuration.py` — new section at the end, 38 tests
- `ansible/roles/image_prune/molecule/heartbeat/{molecule,prepare,converge,verify}.yml`
- `ansible/roles/image_prune/molecule/absent-heartbeat-key/{molecule,converge,verify}.yml`
