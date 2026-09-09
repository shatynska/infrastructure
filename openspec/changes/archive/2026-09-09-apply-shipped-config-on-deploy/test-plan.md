# Test plan — apply-shipped-config-on-deploy

Derived from this change's delta spec for `iac-platform-deploy-pipeline`, by an
author who has not read and will not read the implementation, before any part of
section 1 of `tasks.md` was written.

This file is **not** an artifact the OpenSpec schema knows about. It will not
appear among the context files `openspec instructions apply` lists, so whoever
implements section 1 has to open it on purpose.

## Where the tests are

One new module, added whole; nothing existing was edited, deleted or disabled:

- `.github/tests/test_shipped_config_reaches_the_container.py` — 21 tests in 6
  classes.

Test command, from the repository root:

```
python3 -m unittest discover --start-directory .github/tests
```

A single test is selectable as, for example:

```
python3 -m unittest test_shipped_config_reaches_the_container\
.TestTheChecksumEqualsTheConfigurationItCovers\
.test_every_committed_checksum_equals_a_recomputation_from_the_content
```

Why this suite: every property asserted is a static read of one committed file,
`platform/docker-compose.yml`, its `services:` and `configs:` blocks. `AGENTS.md`'s
testing table routes exactly that here; the change touches no Terraform module
and no Ansible role, so the other two rows cannot hold it.

## Baseline

**Full**, not scoped. Before the new module existed:

```
python3 -m unittest discover --start-directory .github/tests
Ran 297 tests in 2.857s
OK
```

After the new module, on the current tree (no labels yet):

```
Ran 318 tests in 4.441s
FAILED (failures=3)
```

The 21 added tests account for the whole difference. The 3 failures are all in
the new module and are all **state 2 — the target does not exist yet**: the
three services carry no checksum label at all. No pre-existing test changed
verdict. The added ~1.5 s is after memoising the parsed stack definition; before
that the module alone took 14.6 s, which would have quadrupled a check that
gates every pull request.

## Scenario coverage

The delta spec declares **3** scenarios, all under the single ADDED requirement
*A Shipped Configuration Change Is Visible to the Container Runtime*. All 3 are
accounted for below; none is uncovered.

### Scenario: A configuration-only change reaches the running service

| Test | Status now |
|---|---|
| `TestTheChecksumEqualsTheConfigurationItCovers.test_every_committed_checksum_equals_a_recomputation_from_the_content` | FAILS (no label) |
| `TestEveryServiceMountingConfigurationCarriesTheChecksum.test_every_service_mounting_embedded_configuration_carries_the_label` | FAILS (no label) |
| `TestTheChecksumCoversEveryConfigTheServiceMounts.test_editing_any_one_of_a_services_configs_moves_that_services_checksum` | passes (guard) |
| `TestTheChecksumCoversEveryConfigTheServiceMounts.test_editing_grafanas_last_dashboard_moves_grafanas_checksum` | passes (guard) |
| `TestTheChecksumFramesEachConfigByName.test_a_block_moved_between_two_of_a_services_configs_moves_the_checksum` | passes (guard) |
| `TestTheChecksumFramesEachConfigByName.test_the_moved_block_leaves_the_bare_concatenation_identical` | passes (guard) |
| `TestTheChecksumCheckIsARealReadOfTheConfiguration.test_an_edited_rule_with_the_label_left_alone_is_caught` | passes (guard) |

### Scenario: Only the service whose configuration changed is replaced

| Test | Status now |
|---|---|
| `TestEachChecksumIsAFunctionOfThatServicesOwnConfigsAlone.test_the_committed_checksums_are_pairwise_distinct` | FAILS (no label) |
| `TestEachChecksumIsAFunctionOfThatServicesOwnConfigsAlone.test_editing_one_services_configuration_moves_only_its_own_checksum` | passes (guard) |
| `TestEveryServiceMountingConfigurationCarriesTheChecksum.test_no_service_without_embedded_configuration_carries_the_label` | passes, vacuously today |
| `TestTheMissingLabelCheckIsARealReadOfTheFile.test_a_label_on_a_service_mounting_nothing_is_caught` | passes (guard) |

### Scenario: A stale marker fails before it reaches a deploy

| Test | Status now |
|---|---|
| `TestTheChecksumEqualsTheConfigurationItCovers.test_every_committed_checksum_equals_a_recomputation_from_the_content` | FAILS (no label) |
| `TestTheChecksumCheckIsARealReadOfTheConfiguration.test_an_edited_rule_with_the_label_left_alone_is_caught` | passes (guard) |
| `TestTheChecksumCheckIsARealReadOfTheConfiguration.test_the_failure_names_the_value_the_label_should_hold` | passes (guard) |
| `TestTheChecksumFramesEachConfigByName.test_the_moved_block_is_caught_against_a_stale_label` | passes (guard) |
| `TestTheChecksumCoversEveryConfigTheServiceMounts.test_editing_grafanas_last_dashboard_moves_grafanas_checksum` (second assertion) | passes (guard) |

The scenario's "blocks the pull request" limb is not re-asserted here. This
suite's invocation by the required status check is already asserted by
`TestTheSuiteIsWiredIntoTheRequiredCheck` in `.github/tests/test_ci_configuration.py`,
and this change's `design.md` Decision 2 records that as the reason the scenario
is satisfied. Duplicating it would add a second place to maintain and no
evidence.

## Why most of the added tests pass on their first run

That would ordinarily be an alarm. Here it is the shape the task list asked for,
and the distinction is worth stating so a reviewer can check it rather than
take it:

- **3 tests assert on the committed labels.** They are the ones that constrain
  the implementation, and all 3 fail today because the labels do not exist.
- **18 tests are guards and falsification checks.** The task list requires each
  assertion to be verified against a mutated copy, and — as `tasks.md` 2.4 says
  outright — a committed literal cannot respond to a mutated copy. So those
  tests are properties of this module's own recomputation and of its check
  functions, both of which exist as of this commit. They pass because they are
  correct, not because the implementation is present.

Every fixture starts from the committed definition **with correct labels written
onto it by this module's own `expected_checksum`**, then mutates exactly one
property. Starting from the unlabelled committed file would make every fixture
fail for the reason the committed file already fails, and would establish
nothing about the mutation.

## Falsification checks actually performed

Each was run, not reasoned about. The recomputation was replaced with a
deliberately wrong construction and the suite re-run; the table records which
tests caught it. The wrong constructions were injected from a scratch script
outside the repository, and the committed module is unmodified.

| Wrong construction | Caught by |
|---|---|
| digests only the **first** config a service mounts | `test_editing_any_one_of_a_services_configs_moves_that_services_checksum` (4 grafana subtests + `prometheus_rules`), `test_editing_grafanas_last_dashboard_moves_grafanas_checksum`, `test_an_edited_rule_with_the_label_left_alone_is_caught`, `test_the_committed_checksums_are_pairwise_distinct` — 9 failures |
| **bare concatenation of contents**, config name absent | `test_a_block_moved_between_two_of_a_services_configs_moves_the_checksum`, `test_the_moved_block_is_caught_against_a_stale_label`, `test_the_committed_checksums_are_pairwise_distinct` — 3 failures |
| digests **every config in the stack**, identical for all three services | `test_editing_one_services_configuration_moves_only_its_own_checksum` (6 subtests), plus 5 others — 11 failures |
| digests a service's **own configs together with all of them** — distinct per service, yet moves all three on any edit | `test_editing_one_services_configuration_moves_only_its_own_checksum` (6 subtests), plus 4 others — 10 failures |
| a **constant** | 16 failures, i.e. every guard |

The fourth row is the one `tasks.md` 2.4 names as the awkward variant that
distinctness alone would let through. It is caught — by 2.4's *second* clause,
the guard on the recomputation, not by the distinctness assertion.

Additionally, the task-named falsifications are themselves committed tests
rather than one-time manual checks:

| Task | Named falsification | Test that carries it |
|---|---|---|
| 2.1 | a fourth service gains `configs:` and no label | `TestTheMissingLabelCheckIsARealReadOfTheFile.test_a_service_added_with_configuration_and_no_label_is_caught` |
| 2.2 | one alert rule edited, label left alone | `TestTheChecksumCheckIsARealReadOfTheConfiguration.test_an_edited_rule_with_the_label_left_alone_is_caught` |
| 2.3 | only grafana's last dashboard edited | `TestTheChecksumCoversEveryConfigTheServiceMounts.test_editing_grafanas_last_dashboard_moves_grafanas_checksum` |
| 2.4 | one config edited, the other two services' expected values recomputed | `TestEachChecksumIsAFunctionOfThatServicesOwnConfigsAlone.test_editing_one_services_configuration_moves_only_its_own_checksum` |
| 2.5 | the label added to `postgres` | `TestTheMissingLabelCheckIsARealReadOfTheFile.test_a_label_on_a_service_mounting_nothing_is_caught` |
| 2.6 | a block moved from `prometheus_config` into `prometheus_rules`, total content unchanged | `TestTheChecksumFramesEachConfigByName.test_a_block_moved_between_two_of_a_services_configs_moves_the_checksum`, with `…test_the_moved_block_leaves_the_bare_concatenation_identical` establishing the fixture really does isolate framing |

## Assertion classification

**SPECIFIED** — traces to text in the delta spec:

- `test_every_service_mounting_embedded_configuration_carries_the_label` — "the
  stack definition SHALL carry — for each service that mounts embedded
  configuration — a property the digest does cover".
- `test_no_service_without_embedded_configuration_carries_the_label`,
  `test_a_label_on_a_service_mounting_nothing_is_caught` — "Satisfying this by
  replacing every service on every deploy SHALL NOT be used, because it would
  replace stateful services whose configuration did not change".
- `test_a_service_added_with_configuration_and_no_label_is_caught` — the central
  clause holds of *each* such service, including one that does not exist yet.
- `test_every_committed_checksum_equals_a_recomputation_from_the_content`,
  `test_an_edited_rule_with_the_label_left_alone_is_caught`,
  `test_the_failure_names_the_value_the_label_should_hold`,
  `test_the_moved_block_is_caught_against_a_stale_label` — third scenario.
- `test_editing_any_one_of_a_services_configs_moves_that_services_checksum`,
  `test_editing_grafanas_last_dashboard_moves_grafanas_checksum`,
  `test_a_block_moved_between_two_of_a_services_configs_moves_the_checksum` —
  first scenario, which restricts the change to "a service's embedded
  configuration" without restricting it to any one of that service's configs.
- `test_the_committed_checksums_are_pairwise_distinct`,
  `test_editing_one_services_configuration_moves_only_its_own_checksum` — second
  scenario.

**DERIVED** — inferred, or traced to `design.md`/`tasks.md` rather than to a
scenario. Each is labelled as such in its own docstring:

- `test_the_check_discovers_the_services_from_the_file` — `design.md` Risks, "A
  service that gains a `configs:` entry later, with no label, is uncovered".
- `test_the_check_covers_every_service_that_mounts_configuration` — a
  non-vacuity guard; nothing states it.
- `test_a_correctly_labelled_stack_is_accepted`,
  `test_a_correctly_labelled_stack_reports_no_disagreement` — the converse
  halves, without which a check reporting every service as an offender would
  satisfy the falsifications while failing every pull request.
- `test_the_list_form_of_labels_is_read_as_well_as_the_mapping_form` — Compose
  accepts both forms; reading one would fail a pull request for a formatting
  choice.
- `test_a_config_with_no_inline_content_fails_rather_than_digesting_nothing`,
  `test_a_service_mounting_a_config_the_stack_does_not_define_fails` —
  non-vacuity on both sides of the config reference.
- `test_the_moved_block_leaves_the_bare_concatenation_identical` — what makes
  the 2.6 falsification non-tautological.

**DELIBERATELY UNTESTED**, each recorded with its reason:

- **That the runtime's per-service digest actually covers a service-level
  label.** The whole mechanism rests on it. It is a measured fact recorded in
  this change's `proposal.md` and is unreachable by a static read of a committed
  file; this suite may not spawn a container runtime. Recorded in the module's
  own docstring so it cannot be deleted without the record going too.
- **That a deploy reporting success applied everything it shipped.** The
  requirement explicitly does not establish this, and neither does any test
  here. `tasks.md` 5.2 and 5.3 carry it, against the running host.
- **That the label's value moves the hash the host's Compose computes.** Same
  boundary; `tasks.md` 1.1 and 4.4 carry it, with a Compose binary.
- **The label's exact rendering in the file** — quoting, placement, the comment
  `tasks.md` 1.2 requires. Read by review, not asserted: an assertion on comment
  text constrains prose rather than behaviour.
- **That the checksum is 12 lowercase hex characters.** Subsumed by the equality
  assertion, which is strictly stronger; a separate shape assertion would add a
  second failure for one defect.

## Unresolved project questions

**One, and it is load-bearing.**

- **The label's key is not fixed by any artifact.** `design.md` Decision 3 fixes
  the algorithm, the truncation, the framing, the name component and the scope —
  everything except what the label is *called*. The proposal, the requirement and
  the task list say only "a service-level label".

  **Assumption taken:** `platform.config-checksum`.

  **Tests that depend on it:** all 21. Concretely, an implementation that gets
  the digest exactly right under a different key fails
  `test_every_service_mounting_embedded_configuration_carries_the_label`,
  `test_every_committed_checksum_equals_a_recomputation_from_the_content` and
  `test_the_committed_checksums_are_pairwise_distinct`, each with a message
  naming `platform.config-checksum` in full. So the disagreement surfaces in one
  run and costs one rename — but it is an assumption, not a specification, and
  the implementer is free to reject it. Rejecting it means changing
  `CHECKSUM_LABEL` in the test module, which is the one edit to these tests that
  is not a weakening.

  It was not resolved by asking, because this pass runs with no channel to ask
  on. It is recorded here rather than adopted silently.

**Not a question, but worth stating:** this module's `expected_checksum` is both
the oracle for the committed labels and the subject of the guards. That is
inherent and is what Decision 3 is for — the algorithm is specified, so the
oracle is not invented by the test author. What it means in practice is that the
two-author cross-check happens on the implementer's first run of the suite, and
only then. For that reason the computed digests are **deliberately not written
down in this file**: publishing them would turn an independent recomputation
into a paste. They surface in the failing test's own message, which
`design.md` Decision 2 requires anyway.

## Obsolete tests

**Not applicable.** Every delta in this change is `ADDED` — there is no
`MODIFIED`, `REMOVED` or `RENAMED` operation, so no existing test can have been
superseded by it, and no obsolete-test search was warranted. This is the
operation-based reason, not the result of a search that found nothing.

## Constraints held by hand

`TestTheSuiteNeedsNoPrivilegedResource` in
`.github/tests/test_ci_configuration.py` reads `Path(__file__)` — its own module
and no other — so the new module is not covered by the suite's import,
subprocess and network self-checks. It was held to them by hand and checked:
imports are `copy`, `hashlib`, `shutil`, `tempfile`, `unittest`, `pathlib`,
`yaml`, and helpers from the module beside it. No `subprocess` call of any kind,
no network-capable import, no credential, no container runtime, no Terraform
binary, and no dependency beyond the PyYAML `.github/requirements-ci.txt`
already pins.

`TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation` passes over the
new module: it cites the requirement as
`openspec/specs/iac-platform-deploy-pipeline/spec.md` plus the requirement's
name, and cites this change's rationale by change name and artifact name in
prose with no path.

## What the implementation must make pass

Adding the three labels correctly turns these three red into green, and nothing
else in the suite changes:

```
python3 -m unittest \
  test_shipped_config_reaches_the_container.TestEveryServiceMountingConfigurationCarriesTheChecksum.test_every_service_mounting_embedded_configuration_carries_the_label \
  test_shipped_config_reaches_the_container.TestTheChecksumEqualsTheConfigurationItCovers.test_every_committed_checksum_equals_a_recomputation_from_the_content \
  test_shipped_config_reaches_the_container.TestEachChecksumIsAFunctionOfThatServicesOwnConfigsAlone.test_the_committed_checksums_are_pairwise_distinct
```

The second of the three prints, for each of `prometheus`, `alertmanager` and
`grafana`, the exact value its label should hold.
