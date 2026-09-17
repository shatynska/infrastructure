# Test plan — scope-the-restart-alert-to-real-containers

Written before any implementation of this change existed, by an author other than whoever implements it, from the delta specification at commit `60e17eb` — the commit holding the approved plan — and never from the rule itself. This file is not an artifact the OpenSpec schema knows about: it does not appear among `openspec instructions apply`'s context files and has to be read on purpose.

**This pass added tests and subtracted nothing.** No existing test file was edited, deleted or disabled; no implementation was written; nothing was written outside `.github/tests/*.py` and this file.

## Where the tests are

One new module: `.github/tests/test_the_container_alert_names_a_container.py`.

Runner, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

    # one test, individually selectable:
    python3 -m unittest discover --start-directory .github/tests \
        -p "test_the_container_alert_names_a_container.py" -v

    # or, with .github/tests on sys.path:
    python3 -m unittest \
        test_the_container_alert_names_a_container.TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert.test_the_restart_half_selects_only_series_carrying_a_container_name

This is AGENTS.md's third testing row: the property is a static read of one committed file (`platform/docker-compose.yml`). The module opens no network connection, reads no credential, and spawns no container runtime, Terraform binary or subprocess of any kind; it imports only the standard library, `yaml`, and the sibling `test_ci_configuration` — which is what `TestTheSuiteNeedsNoPrivilegedResource` and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in `test_ci_configuration.py` require of it.

## The baseline

| When | Command | Result |
|---|---|---|
| Before the module was added | `python3 -m unittest discover --start-directory .github/tests` | **1550 tests, OK** — nothing failing beforehand |
| After the module was added | same | **1573 tests, 3 failures**, all three in the new module |

The three failures are exactly the assertions that trace to the delta's new material. Every other new assertion passes, for reasons recorded per scenario below. Nothing that was green went red.

The three, verbatim in identity and in substance:

- `test_the_container_alert_names_a_container.TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert.test_the_restart_half_selects_only_series_carrying_a_container_name`
  `AssertionError: Lists differ: [] != ['container_start_time_seconds{}']`
- `test_the_container_alert_names_a_container.TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert.test_the_out_of_memory_half_selects_only_series_carrying_a_container_name`
  `AssertionError: Lists differ: [] != ['container_oom_events_total{}']`
- `test_the_container_alert_names_a_container.TestEveryContainerSubjectRuleSelectsOnlyContainers.test_every_series_a_container_rule_reads_carries_a_container_name`
  `AssertionError: [] != ['ContainerRestartingOrOOMKilled: container_oom_events_total{}', 'ContainerRestartingOrOOMKilled: container_start_time_seconds{}']`

Each names the selector it found unrestricted rather than reporting an absent target: the rule exists, the expression parsed, the assertion executed, and the value it produced is wrong. That is the strongest failure state available before an implementation exists — the assertions are already known to discriminate, rather than merely to fail.

**Established, not assumed, that they go green on the change and not on something else.** The module's readers were run over a throwaway copy of the committed file with `{name!=""}` added to both selectors and nothing else changed: the offender list went from `['container_oom_events_total{}', 'container_start_time_seconds{}']` to `[]`. The copy was written to a temporary directory; `platform/docker-compose.yml` was not touched.

## Every scenario in the delta, accounted for

The delta carries one `MODIFIED` requirement — *Metrics-Based Alerting Covers Host and Service Health*, `openspec/specs/iac-platform-services/spec.md` — with **five** `#### Scenario:` blocks. Five accounted for below, none omitted.

### 1. Sustained per-application error rate triggers an alert — covered

Text unchanged by the delta.

| Test | Classification |
|---|---|
| `TestSustainedApplicationErrorRateTriggersAnAlert.test_an_alert_reads_the_proxys_per_application_request_counts` | SPECIFIED |
| `TestSustainedApplicationErrorRateTriggersAnAlert.test_that_alert_waits_for_a_sustained_period_and_identifies_the_application` | SPECIFIED |

**Passes from the moment it was written**, and is recorded as such rather than as coverage of this change: the property holds of the rule at the plan commit. It is here because the requirement is MODIFIED as a whole, and because a change editing this config entry is the occasion on which an unrelated rule can be lost with nothing noticing.

### 2. A crash-looping container triggers an alert — covered

Revised by the delta: the alert identifies that container **by name**.

| Test | Classification |
|---|---|
| `TestACrashLoopingContainerTriggersAnAlert.test_the_stack_definition_is_read_at_all` | DERIVED — non-vacuity guard, no scenario states it |
| `TestACrashLoopingContainerTriggersAnAlert.test_an_alert_reads_the_restart_and_out_of_memory_counters` | SPECIFIED |
| `TestACrashLoopingContainerTriggersAnAlert.test_that_alert_names_the_container_rather_than_describing_it_generically` | SPECIFIED |

All three pass at the plan commit: the rule already interpolates `$labels.name`. They are the half of the scenario this change must not break — narrowing the selector must scope the alert, not delete it.

### 3. A control group that is not a container raises no container alert — covered (this is the delta's new scenario)

| Test | Classification |
|---|---|
| `TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert.test_the_restart_half_selects_only_series_carrying_a_container_name` | SPECIFIED — the scenario's WHEN/THEN |
| `TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert.test_the_out_of_memory_half_selects_only_series_carrying_a_container_name` | SPECIFIED — the scenario's **AND** |

The two limbs are separate tests because the scenario states them separately, and because a half-applied selector passes one and fails the other — the outcome a single combined assertion would hide.

The delta's added normative paragraph — *"An alert rule whose subject is a container SHALL select only series that identify one"* — is covered by a class of its own, stated over every rule reading a `container_*` series rather than over the one rule this change narrows:

| Test | Classification |
|---|---|
| `TestEveryContainerSubjectRuleSelectsOnlyContainers.test_every_series_a_container_rule_reads_carries_a_container_name` | SPECIFIED |

### 4. Host resource pressure triggers an alert — covered

Text unchanged by the delta.

| Test | Classification |
|---|---|
| `TestHostResourcePressureTriggersAnAlert.test_an_alert_reads_each_resource_the_scenario_names` | SPECIFIED (three subtests: disk, CPU, memory) |

Passes from the moment it was written, for the reason scenario 1 gives.

### 5. A metrics source becoming unreachable triggers an alert — covered

Text unchanged by the delta.

| Test | Classification |
|---|---|
| `TestAnUnreachableMetricsSourceTriggersAnAlert.test_an_alert_reports_a_scrape_target_that_stopped_answering` | SPECIFIED |

Passes from the moment it was written, for the reason scenario 1 gives.

## The discrimination class

`TestTheseAssertionsAreARealReadOfTheFile` runs the same readers over throwaway stack definitions built from scratch, each differing from a satisfying one in exactly one property. This is what establishes that the checks above can fail — a static read whose target already carries the asserted property passes without discriminating, so the fixtures are the only thing that separates a check from a formality. The fixtures reproduce the Compose `$` doubling, so nothing here depends on what the committed file contains today.

| Test | Classification |
|---|---|
| `test_a_rule_restricted_on_both_halves_is_accepted` | DERIVED — the converse half |
| `test_a_half_applied_selector_is_caught` | SPECIFIED — the scenario's **AND** |
| `test_a_rule_with_no_restriction_at_all_is_caught` | SPECIFIED |
| `test_a_reformatted_or_differently_spelled_restriction_is_still_accepted` | DERIVED — design.md's "a reformat must not fail" |
| `test_a_restriction_that_still_admits_the_empty_name_is_caught` | SPECIFIED |
| `test_a_restriction_on_some_other_label_alone_is_caught` | DERIVED — design.md's `name!=""` over an `id` pattern |
| `test_an_annotation_that_names_no_container_is_caught` | SPECIFIED |
| `test_a_matcher_this_reader_cannot_parse_is_reported_rather_than_passed` | DERIVED |
| `test_the_compose_escaping_is_undone_before_the_rules_are_read` | DERIVED — design.md's `$$` decision |
| `test_the_selector_reader_ignores_functions_grouping_labels_and_durations` | DERIVED |
| `test_a_rules_config_with_no_rules_fails_rather_than_reading_nothing` | DERIVED — non-vacuity |
| `test_a_stack_declaring_no_rules_config_fails_rather_than_reading_nothing` | DERIVED — non-vacuity |
| `test_the_committed_file_is_the_one_these_assertions_read` | DERIVED |

All thirteen pass, which is the expected result for a fixture-driven discriminator: each supplies its own material.

## Deliberately untested

- **That no alert fires at runtime for a system service or a login session.** No static read can establish it: it needs a Prometheus evaluating real series against a host whose control groups are churning, and this suite may spawn neither. `tasks.md` 5.3 provokes exactly that churn on the deployed staging host and reads the silence against it. Nothing in this module discharges that gate, and the module's docstring says so.
- **The container rule's `for:` duration.** The delta's scenario says "within a short window", not "for a sustained period", and the committed rule carries `for: 0m`. Asserting a non-immediate `for:` here would be an invented requirement that the implementation would have to satisfy — out of this change's scope, which narrows the selector and leaves the thresholds and the `for:` untouched. The three unchanged scenarios (1, 4 and 5) *do* say "for a sustained period", and those tests assert it.
- **That the notification is delivered.** Routing and receivers are another requirement's subject and are untouched by this change.
- **The general property this defect generalizes to** — every rule interpolating `$labels.<L>` excluding an empty `<L>`. `design.md` puts it out of scope and `docs/backlog.md`'s `hold-every-alert-to-naming-what-it-fires-about` carries it; asserting it here would fail on two rules this change does not touch.

## Obsolete tests

Applicable — the delta carries a `MODIFIED` operation — and the result is: **no bearing test was found by this search**, which is a different statement from "no such test exists".

What was searched: `.github/tests/*.py`, the dispatched test-path glob, and nothing else. No earlier `test-plan.md` was supplied to this pass, so no scenario-to-test mapping was available to draw on. Patterns: `ContainerRestartingOrOOMKilled`, `container_start_time_seconds`, `container_oom_events_total`, `Metrics-Based Alerting`, `cadvisor`. The first four match nothing anywhere in the suite. `cadvisor` matches only `test_ci_configuration.py`, where it appears as a service name in image-pinning and network-membership assertions that say nothing about any alert rule's expression.

So there is no candidate for human confirmation, and nothing is proposed for deletion or rewriting. This is consistent with the proposal's own claim that nothing today reads the expression.

**One test that is NOT obsolete and will nonetheless go red on the implementation**, recorded here because `tasks.md` does not mention it:

- `test_shipped_config_reaches_the_container.TestTheChecksumEqualsTheConfigurationItCovers.test_every_committed_checksum_equals_a_recomputation_from_the_content`

  Editing the `prometheus_rules` content changes the digest that the `prometheus` service's `platform.config-checksum` label must hold (`"921a970cfbc8"` today). The test is correct and must not be weakened; what has to change is the label value in `platform/docker-compose.yml`, and the test's failure message names the value it should hold. Task 2.1's "leaving ... the labels ... untouched" refers to the rule's own `labels:` block, not to that service-level label.

## Unresolved project questions

Recorded rather than resolved silently: this pass had no channel to ask on.

1. **The rule is located by the metrics it reads, not by its `alert` name.** `design.md`'s decision *The assertion parses the expression rather than matching its text* says the module "locates the rule by its `alert` name". It does not: `container_subject_rules()` selects every alert rule with a `container_*` metric selector. Assumption taken — the delta's normative sentence binds "an alert rule whose subject is a container" rather than one named rule, and a name-based read would be defeated by a rename while the defect survived. `ContainerRestartingOrOOMKilled` is named in the module only as a fixture's alert name and for orientation in comments; no assertion requires it. Tests depending on this: every test in `TestACrashLoopingContainerTriggersAnAlert`, `TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert` and `TestEveryContainerSubjectRuleSelectsOnlyContainers`. If the project wants the name-based read design.md describes, this is a one-constant change and the tests' shape is unaffected.

2. **"Identifying that container by name" is asserted as an annotation interpolating the `name` label.** The scenario states the outcome, not the mechanism. Assumption taken — an annotation carrying `$labels.name` is what makes a notification name the container in this stack, which is also the form the committed rule already uses. Test depending on it: `TestACrashLoopingContainerTriggersAnAlert.test_that_alert_names_the_container_rather_than_describing_it_generically`, and its fixture half `test_an_annotation_that_names_no_container_is_caught`.

3. **What counts as "a series that identifies a container" was resolved as "a `name` matcher excluding the empty string".** Accepted spellings: `name!=""`, `name="<literal>"`, `name=~"<regex that cannot match empty>"`, `name!~"<regex that matches empty>"`. Rejected: no `name` matcher at all, `name=""`, `name=~".*"`, `name!="<something>"`. An `id` pattern alone is rejected, following design.md's decision, and `test_a_restriction_on_some_other_label_alone_is_caught` records that. If the project later prefers the `id` form, that test and `restricts_to_a_named_container` are what change.

4. **No Python linter is configured for this suite in this tree.** `ruff` is not installed here and `.pre-commit-config.yaml` runs no Python hook, so the completion check was `python3 -m py_compile` plus the full-suite run rather than a lint pass. The library's `python` skill was loaded and the module read against its traps (no mutable default argument, no loop-captured closure, no list mutated while iterated, no reused generator, `except re.error` narrow rather than broad).

5. **No stack-specific testing skill exists for "static assertions over a committed YAML/PromQL file".** The library carries `python` (loaded) and `testing` (loaded); there is no closer match, so the floor plus this repository's own precedent module — `test_certificate_expiry_alerting.py`, whose idiom, annotation convention and docstring sections this module follows — is what the module was written against.

## What the implementation step must make pass

The three failing tests listed under *The baseline*. They go green when both metric selectors in `ContainerRestartingOrOOMKilled`'s expression carry a matcher excluding an empty `name`, and on nothing else — a half-applied selector leaves one of them red by construction.

Then the whole suite: 1573 tests green, which additionally requires regenerating the `prometheus` service's `platform.config-checksum` label, per *Obsolete tests* above.
