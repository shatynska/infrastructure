# Test plan — alert-on-certificate-expiry

Derived from this change's delta spec by an author other than whoever
implements it, before any implementation existed. The requirement covered is
**An Expiring TLS Certificate Is Alerted On Before It Expires**, which will be
held in `openspec/specs/iac-platform-services/spec.md` once this change is
archived; until then it is the change's own delta spec.

This file is not an artifact the OpenSpec schema knows about. It will not
appear among the context files `openspec instructions apply` lists, so it has to
be read on purpose before implementing.

## Where the tests are

    .github/tests/test_certificate_expiry_alerting.py

Test command, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

A single test is selectable by its identifier, for example:

    python3 -m unittest \
      test_certificate_expiry_alerting.TestTheThresholdLeavesNormalRenewalAlone \
      .test_the_alert_threshold_is_strictly_below_the_renewal_lead_time

`AGENTS.md`'s testing table routes this change to that command and to the
`.github/tests/*.py` glob: every property here is a static read of committed
text in `platform/docker-compose.yml`. No Terraform module and no Ansible role
is touched, so the `terraform test` and `molecule test --all` rows do not apply.

A **new file** rather than an addition to `test_ci_configuration.py`: task 2.9
requires the derived tests committed as their author wrote them before any
folding or relocation, and this pass is additive only — it edits no existing
test. See "Unresolved project questions" below for what folding it in later
costs and gains.

## Baseline

Full-suite baseline, taken before any test was written:

    python3 -m unittest discover --start-directory .github/tests
    Ran 257 tests in 2.243s — OK

After this pass: **290 tests, 13 failures**, every failure in the new module and
every one of them attributable to the alert rules not existing yet. The 257
pre-existing tests still pass, unchanged and unedited.

## Scenario coverage

The delta spec states **five** scenarios under one ADDED requirement. All five
are accounted for below: five covered, none uncovered.

### 1. A certificate approaching expiry raises an alert

| Test | Provenance |
|---|---|
| `TestAnExpiringCertificateIsAlertedOn.test_the_stack_definition_is_read_at_all` | DERIVED — non-vacuity guard |
| `TestAnExpiringCertificateIsAlertedOn.test_an_alert_reads_the_certificate_expiry_the_proxy_publishes` | SPECIFIED |
| `TestAnExpiringCertificateIsAlertedOn.test_that_alert_waits_for_a_sustained_period` | SPECIFIED — the scenario's "for a sustained period" |
| `TestAnExpiringCertificateIsAlertedOn.test_that_alert_names_the_certificate_rather_than_describing_it_generically` | SPECIFIED — "identifying that certificate by the hostname it was issued for" |
| `TestTheseAssertionsAreARealReadOfTheFile.test_removing_the_expiry_rule_is_caught` | SPECIFIED — discriminating half |

### 2. Several certificates approaching expiry are each identified

| Test | Provenance |
|---|---|
| `TestSeveralCertificatesAreEachIdentifiedOnDelivery.test_the_alert_has_a_route_of_its_own` | SPECIFIED |
| `TestSeveralCertificatesAreEachIdentifiedOnDelivery.test_that_route_groups_by_the_certificate_as_well_as_the_alertname` | SPECIFIED — the clause "rather than the group collapsing into a single notification that names none" |
| `TestSeveralCertificatesAreEachIdentifiedOnDelivery.test_that_route_delivers_to_a_receiver_the_configuration_declares` | DERIVED — bears on "a notification that is delivered" |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_route_grouped_by_alertname_alone_is_caught` | SPECIFIED — discriminating half |
| `TestTheseAssertionsAreARealReadOfTheFile.test_an_alert_with_no_route_of_its_own_is_caught` | SPECIFIED — discriminating half |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_route_in_the_deprecated_matcher_form_is_still_found` | DERIVED — spelling tolerance |

### 3. A certificate renewing normally raises no alert

| Test | Provenance |
|---|---|
| `TestTheThresholdLeavesNormalRenewalAlone.test_the_alert_threshold_is_strictly_below_the_renewal_lead_time` | SPECIFIED — the requirement's second normative paragraph |
| `TestTheThresholdLeavesNormalRenewalAlone.test_the_stack_leaves_the_certificate_duration_unset` | DERIVED — the precondition making the 30-day constant real |
| `TestTheThresholdLeavesNormalRenewalAlone.test_the_provenance_of_the_renewal_lead_time_is_still_recorded` | DERIVED — keeps the constant's origin undeletable |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_threshold_raised_to_the_renewal_lead_time_is_caught` | SPECIFIED — discriminating half |
| `TestTheseAssertionsAreARealReadOfTheFile.test_the_threshold_is_read_in_each_form_its_unit_can_be_written_in` | DERIVED — unit correctness of the reader |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_certificate_duration_added_to_the_proxy_is_caught` | DERIVED — discriminating half of the precondition |

### 4. A superseded certificate does not raise an alert against a healthy hostname

| Test | Provenance |
|---|---|
| `TestASupersededCertificateCannotFireAgainstAHealthyHostname.test_the_expression_aggregates_per_certificate` | SPECIFIED |
| `TestTheseAssertionsAreARealReadOfTheFile.test_removing_the_per_certificate_aggregation_is_caught` | SPECIFIED — discriminating half |

### 5. Certificate expiry no longer being observed raises an alert

| Test | Provenance |
|---|---|
| `TestExpiryNoLongerBeingObservedRaisesAnAlert.test_a_rule_reports_the_measurement_no_longer_being_published` | SPECIFIED — the scenario's second limb |
| `TestExpiryNoLongerBeingObservedRaisesAnAlert.test_the_scrape_job_feeding_both_rules_is_still_declared` | SPECIFIED — the static half of the first limb |
| `TestExpiryNoLongerBeingObservedRaisesAnAlert.test_that_rule_covers_the_label_the_expiry_alert_reads` | DERIVED — the label-rename route, from this change's design.md Decision 5 |
| `TestExpiryNoLongerBeingObservedRaisesAnAlert.test_that_rule_waits_before_reporting` | DERIVED — no scenario states a duration |
| `TestTheseAssertionsAreARealReadOfTheFile.test_removing_the_absence_rule_is_caught` | SPECIFIED — discriminating half |
| `TestTheseAssertionsAreARealReadOfTheFile.test_an_absence_rule_that_ignores_the_certificate_label_is_caught` | DERIVED — discriminating half of the label limb |
| `TestTheseAssertionsAreARealReadOfTheFile.test_removing_the_scrape_job_is_caught` | SPECIFIED — discriminating half |

### Standing guards, tracing to no single scenario

| Test | Provenance |
|---|---|
| `TestEveryCertificateAlertCarriesADurationAndASeverity.test_every_rule_reading_the_expiry_metric_declares_a_severity` | DERIVED — this change's design.md Decision 6 |
| `TestEveryCertificateAlertCarriesADurationAndASeverity.test_every_rule_reading_the_expiry_metric_waits_for_a_duration` | DERIVED |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_stack_satisfying_every_property_is_accepted` | DERIVED — the converse half; without it, helpers that rejected everything would satisfy every discrimination test |
| `TestTheseAssertionsAreARealReadOfTheFile.test_an_alert_missing_its_duration_or_severity_is_caught` | DERIVED |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_rules_config_with_no_rules_fails_rather_than_reading_nothing` | DERIVED — non-vacuity |
| `TestTheseAssertionsAreARealReadOfTheFile.test_a_stack_declaring_none_of_the_configs_fails_rather_than_reading_nothing` | DERIVED — non-vacuity |
| `TestTheseAssertionsAreARealReadOfTheFile.test_the_committed_file_is_the_one_these_assertions_read` | DERIVED — ties the fixture-based class to the deployed file |

### Task-list coverage

Every assertion tasks.md section 2 names has a test above: 2.1 → scenario 1's
rows; 2.2 → scenario 3's threshold row; 2.3 → the `certificatesDuration` row;
2.4 → scenario 4; 2.5 → scenario 2's `group_by` row; 2.6 → scenario 5's two
halves; 2.7 → the standing guards. Task 2.8's "run the whole suite" is the
baseline recorded above.

## Deliberately untested

- **That a real multi-certificate Slack notification names both hostnames.**
  Observing it needs two certificates actually approaching expiry together;
  nothing static can produce one. The configuration under which that outcome
  follows is asserted instead, and task 6.3 already requires the change to
  record that the delivery was confirmed as configuration rather than as an
  observed notification.
- **The `slack` receiver's `CommonAnnotations` templating.** It is the reason
  the grouping matters, but pinning it would freeze a template this change
  deliberately does not touch and which a queued change intends to replace with
  a `{{ range .Alerts }}` form. Asserting it would turn that later fix into a
  test failure for doing the right thing. Recorded in the delivery class's
  prose instead.
- **`repeat_interval: 24h`.** Per this change's design.md Decision 4: reverting
  it makes the alert noisy, not wrong, and no scenario states a cadence.
  Pinning it would freeze a number the requirement leaves open.
- **The `platform-monitoring` group name, the alert names, and the `21`
  threshold itself.** The requirement bounds the threshold from above and says
  nothing about the rest. Tests assert the bound, not the value.
- **That the rules load and evaluate against real series.** A rule that is
  loaded and permanently empty is indistinguishable from a working one by any
  static read. That is what the four confirmation steps in this change's
  design.md perform against the running stack; nothing here discharges them.

## Obsolete tests

**Not applicable.** The delta carries one ADDED requirement and no `MODIFIED`,
`REMOVED` or `RENAMED` operation, so no existing test can have been superseded
by it. No existing test was edited, deleted or disabled by this pass.

## Unresolved project questions

1. **Where in the suite these tests belong.** `AGENTS.md` names the suite and
   its glob but not its internal layout, and the suite is today a single
   8626-line file whose sections carry per-change provenance headers. The
   assumption taken: a separate file now, foldable later, because task 2.9
   requires the derived tests committed as written before any relocation.
   *Every test in this plan depends on this.* What folding would gain is
   stated below.
2. **Whether `TestTheSuiteNeedsNoPrivilegedResource` should cover a second
   file.** It reads `Path(__file__)` — its own module and no other — so the new
   file is outside the suite's own import, subprocess and network self-checks
   while it sits separately. It was held to them by hand (standard library,
   `yaml`, no subprocess). Folding the file into `test_ci_configuration.py`
   closes this; leaving it separate and widening those three assertions to every
   `.github/tests/*.py` module would close it differently. Not decided here,
   because widening them would change an existing test, which this pass does
   not do.
3. **Cross-module import.** The new file imports `ROOT`, `PLATFORM_COMPOSE`,
   `compose_services`, `config_content`, `service_config_mounts` and
   `stack_configs` from `test_ci_configuration` rather than restating them.
   Assumption: acceptable, because `unittest discover` puts `.github/tests` on
   `sys.path`, which was verified by running the command above. No TestCase
   class is imported, so no test is collected twice. Every test in the new file
   depends on this import resolving.

## Notes for whoever implements next

- The 13 failing tests are the target-absent state, not defects: they establish
  that the rules are missing, and nothing about whether the assertions
  discriminate. What establishes *that* is the fixture-based class
  `TestTheseAssertionsAreARealReadOfTheFile`, which passes today by running the
  same helpers over throwaway stack definitions differing in one property each.
- Two assertions pass **now**, against the tree as it stands, and are standing
  preconditions rather than new coverage: the `traefik` scrape job is declared,
  and the stack sets no `certificatesDuration`. If either stops holding, the
  threshold constant or the rules' data source has moved.
- If a rule is written with its threshold in seconds rather than days, the
  threshold test reports that it could not read the expression rather than
  passing — the message names the three forms the reader understands.
