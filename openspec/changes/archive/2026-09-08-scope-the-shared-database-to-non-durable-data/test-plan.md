# Test plan — `scope-the-shared-database-to-non-durable-data`

Derived from this change's delta specs by an author who has not read and will not write its implementation. Written after the plan was approved and committed at `8923a91`, and before any file the change proposes to edit was touched.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among the context files `openspec instructions apply` lists, so whoever implements this change has to open it on purpose.

## Baseline

Taken before any test was written, from inside this change's own working tree.

| Test command | Scope | Result |
|---|---|---|
| `python3 -m unittest discover --start-directory .github/tests`, from the repository root | Full suite for that row | **146 tests, green** |
| `terraform test`, from `terraform/modules/server/` (after `terraform init -backend=false`) | Full suite for that module | **18 passed, 0 failed** |
| `molecule test --all` | Not run | See below |

After this pass: **170 tests, green** in `.github/tests` — 146 baseline plus **24 added**. Nothing in `terraform/` or `ansible/` was touched, so the Terraform baseline stands unchanged.

**Why the Molecule row was not run.** A baseline is only owed where a row bears on the change. No delta scenario in this change is about what an Ansible role converges to or how it fails: every scenario is either a policy about what an application may persist, or a property of `platform/docker-compose.yml`. The nearest candidate was considered and rejected — the `platform_data_volume` role's scenarios bear on the *existence and ownership* of `/mnt/main-data/prometheus` and `/mnt/main-data/grafana`, not on their classification, and this change alters neither. Recorded rather than skipped silently, per this project's own rule that verification which cannot reach what it needs reports success having verified nothing.

## Scenario accounting

Eight `#### Scenario:` blocks across the two delta specs. Each is accounted for exactly once below: three covered, five uncovered with a stated reason.

Every test identifier below is individually selectable. Run from `.github/tests`:

    python3 -m unittest test_ci_configuration.<Class>.<method>

### `iac-platform-services` — MODIFIED

#### 1. *Shared Services Live in a Dedicated Platform Stack* / "A new application reuses the platform stack"

**UNCOVERED.** The scenario's `THEN` limbs state what a *future application, deployed from a different repository*, shall do. No committed file in this repository expresses it: there is no application manifest here to read, no Terraform resource that could encode it, and no host state an Ansible role converges that would differ. The reverse-proxy limb is likewise unchanged and equally unplaceable. This is enforced by the human review every application deployment passes through, not by any of this project's three test commands.

#### 2. *Single Shared PostgreSQL Instance, Per-Application Databases* / "A new application requests a database"

**UNCOVERED.** The requirement it belongs to deliberately does not define how a database is provisioned inside the instance — the change's own tasks record that deferral in `docs/deferred-work.md`, with the first application that wants technical storage as the revisit trigger. There is therefore no committed provisioning artifact to read statically, and nothing for a `terraform test` or a Molecule scenario to converge. A test written today would have to assert of a mechanism the change states is not yet designed.

#### 3. *Single Shared PostgreSQL Instance, Per-Application Databases* / "An application needs durable storage"

**UNCOVERED.** Its `THEN` directs an application to an external managed service that owns its own backups. That service is outside this repository, and the requirement itself says so: it states the dependency on the Supabase project keeping a plan with backups, and states that nothing here verifies it. A test asserting the direction was taken would have to observe another repository's deployment; a test asserting the external backups exist would need a network call and a credential, which the `.github/tests` suite is specified not to make.

### `iac-safety-hardening` — ADDED: *No Store on This Host Holds Data Requiring Backup*

#### 4. "A persistent store is added to the host"

**COVERED — partially, and the partiality is asserted rather than assumed.**

| Test | Provenance |
|---|---|
| `TestEveryPersistentStoreTheStackDeclaresIsClassified.test_every_persistent_store_the_stack_declares_is_classified` | SPECIFIED |
| `TestEveryPersistentStoreTheStackDeclaresIsClassified.test_the_census_reaches_every_service_the_stack_defines` | DERIVED (non-vacuity guard) |
| `TestEveryPersistentStoreTheStackDeclaresIsClassified.test_every_classified_store_is_still_declared_by_the_stack` | DERIVED (converse half) |
| `TestEveryPersistentStoreTheStackDeclaresIsClassified.test_the_census_records_that_it_cannot_see_an_image_declared_volume` | DERIVED (keeps the caveat undeletable) |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_named_volume_added_to_a_service_is_caught_with_no_test_edit` | SPECIFIED |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_host_bind_mount_added_to_a_service_is_caught_with_no_test_edit` | SPECIFIED |
| `TestTheStoreCensusIsARealReadOfTheFile.test_an_anonymous_volume_the_stack_declares_is_caught` | SPECIFIED |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_read_only_host_path_is_not_counted_as_a_store` | SPECIFIED (the scope clause's exclusion) |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_read_only_path_remounted_writable_becomes_a_store` | DERIVED |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_config_mount_is_not_counted_as_a_store` | DERIVED |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_stack_whose_stores_all_carry_a_reason_is_accepted` | DERIVED (converse half) |
| `TestTheStoreCensusIsARealReadOfTheFile.test_a_stack_declaring_no_services_fails_rather_than_reading_nothing` | DERIVED (non-vacuity guard) |

**DELIBERATELY UNTESTED, within this scenario.** The scenario's scope reaches three things a static read of `platform/docker-compose.yml` cannot see, each recorded here and in the test class's own docstring:

- a volume **an image declares** rather than the stack definition — Alertmanager's `/alertmanager` is the worked example, and it is the reason `CLASSIFIED_STACK_STORES` in the suite deliberately does *not* mirror the requirement's table;
- a store **an application deployed from another repository** persists;
- **a volume a bumped image newly declares**, which the scenario names explicitly and which needs `docker inspect` against a running host.

All three are carried by the host census the change's own tasks require. A green result here establishes a necessary condition over the stack-declared subset and nothing more.

#### 5. "A store's stated reason ceases to hold"

**COVERED.** This is the scenario the change's design (decision 4a) records as the failure mode the requirement exists to catch, and it is the one a static read can decide almost in full.

| Test | Provenance |
|---|---|
| `TestTheStatedReasonsForTheClassifiedStoresStillHold.test_prometheus_bounds_its_database_by_both_time_and_size` | SPECIFIED |
| `TestTheStatedReasonsForTheClassifiedStoresStillHold.test_the_retention_bounds_govern_the_store_the_classification_names` | SPECIFIED |
| `TestTheStatedReasonsForTheClassifiedStoresStillHold.test_grafanas_datasource_and_dashboards_are_provisioned_from_this_repository` | SPECIFIED |
| `TestTheStatedReasonsForTheClassifiedStoresStillHold.test_the_grafana_store_the_classification_names_is_the_one_grafana_writes_into` | SPECIFIED |
| `TestTheStatedReasonsForTheClassifiedStoresStillHold.test_the_dashboard_provider_still_permits_the_ui_edits_the_policy_covers` | SPECIFIED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_retention_flag_removed_is_caught` | SPECIFIED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_removing_the_dashboard_provisioning_stanza_is_caught` | SPECIFIED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_retention_flag_left_present_but_disabled_is_caught` | DERIVED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_prometheus_bounded_by_both_is_accepted` | DERIVED (converse half) |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_dashboard_provisioned_outside_the_providers_path_is_caught` | DERIVED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_config_carrying_no_inline_content_is_caught` | DERIVED |
| `TestTheStatedReasonChecksAreARealReadOfTheFile.test_a_fully_provisioned_grafana_is_accepted` | DERIVED (converse half) |

Three of the assertions above deserve their reasoning stated, because each was a judgement:

- **`allowUiUpdates` and `disableDeletion` are asserted at their stated values, not at safer ones.** The requirement's dashboard-state policy states them as fact — "its dashboard provider sets `allowUiUpdates` true and `disableDeletion` false" — and reasons from that to the whole policy. A change in *either* direction makes the requirement's own sentence false, which is what the scenario's "restate the store's reason" limb is for. The test's failure message says so, and says explicitly that the requirement is what gets restated rather than the assertion edited to match. This is classified SPECIFIED because the value traces to the requirement's body, not to a view about which setting would be preferable.
- **Prometheus's retention *numbers* are deliberately not asserted.** The stated reason is "bounded by both time and size", so shortening the window preserves it. Pinning `28d` and `4GB` would be a derived assertion over-constraining a property the requirement states qualitatively. What is asserted instead is that both flags are present and that neither carries a value with no non-zero digit — `0` being Prometheus's own spelling of "no limit", and the form a presence-only check would read as a bound.
- **The store-identification assertions exist because the two halves can come apart silently.** Retention bounds whatever `--storage.tsdb.path` names, and the classification is about `/mnt/main-data/prometheus`; the provisioned dashboards are reproduced into whatever `options.path` names, and the classification is about `/mnt/main-data/grafana`. Either pair diverging leaves every other assertion passing while the bound no longer bounds the classified data.

**DELIBERATELY UNTESTED, within this scenario.** That the running host is deployed from this file at this commit, and that Prometheus is in fact discarding data on that schedule. Both are observations of a running host, which the `.github/tests` suite is specified not to make.

#### 6. "An application asks for durable storage on this host"

**UNCOVERED.** The `THEN` is a direction given to an application's author — "SHALL be directed to an external managed service". There is no committed file whose contents differ according to whether that direction was given, and the change's own `commerce-ops` divergence paragraph is the record of what happens when it was not. Same reason as scenario 3.

#### 7. "The stated divergence is not a precedent"

**UNCOVERED.** This is a rule of *interpretation*: it says how the divergence paragraph must be read, not what any file must contain. Nothing statically readable distinguishes a repository where the paragraph is read correctly from one where it is not.

### `iac-safety-hardening` — MODIFIED: *Data Durability for Stateful Resources*

#### 8. "Server is created with backups enabled"

**COVERED BY AN EXISTING TEST. No new test owed, and nothing to supersede.**

The delta leaves the normative clause (`The prod server SHALL have `backups = true``) and the scenario's `WHEN`/`THEN` byte-identical to what is already in `openspec/specs/iac-safety-hardening/spec.md`. Only the rationale paragraph changes, to state what the snapshot actually covers. Existing coverage, confirmed green at baseline:

- `terraform/modules/server/tests/creation.tftest.hcl`, run `plan_backups_default_to_true`
- `terraform/modules/server/tests/creation.tftest.hcl`, run `plan_backups_can_be_disabled`

Run with `terraform test` from `terraform/modules/server/`.

## Obsolete tests

**Applicable** — the change carries `MODIFIED` deltas in both capabilities.

**Result: no such test exists.** This is the "no bearing test exists" answer, not the "none was found" one, and the distinction is argued rather than asserted: what the deltas supersede is prose that no test in any of the three globs ever asserted.

Searched, exhaustively, within the dispatched test-path globs and nowhere else: `.github/tests/*.py`, `terraform/modules/*/tests/*.tftest.hcl`, and all fifteen `ansible/roles/*/molecule/*/` scenario directories. No earlier `test-plan.md` was supplied and none exists in this change's directory, so no scenario-to-test mapping was available to draw on. Searched for the vocabulary of every superseded clause: `shared instance`, `per-application`, `own database`, `new database`, `own instance`, `shared postgres`, `postgres_data`, `reverse proxy and`, `reuses this stack`, `backup`.

What the deltas supersede, and why nothing asserted it:

- *Single Shared PostgreSQL Instance, Per-Application Databases* previously read "Each application SHALL be given its own database within that shared instance" unconditionally. It is now conditional on the data being non-durable and relational. Nothing tested the unconditional form: there is no provisioning mechanism in this repository to have tested it against.
- *Shared Services Live in a Dedicated Platform Stack*'s reuse scenario previously read "reuse the existing platform-managed reverse proxy **and database** rather than defining its own instance of either". The database half is now qualified. Nothing tested it, for the same reason.
- *Data Durability for Stateful Resources* loses one rationale sentence ("Restoring from a backup is the only remedy for those"). A rationale sentence is not something a test can assert, and none did.

**Three near-hits examined and deliberately NOT listed**, because each is the entry a careless sweep would have deleted:

| Not listed | Evidence it is unaffected |
|---|---|
| `terraform/modules/server/tests/creation.tftest.hcl`, runs `plan_backups_default_to_true` and `plan_backups_can_be_disabled` | They assert `hcloud_server.this.backups`, the normative clause the `MODIFIED` delta leaves byte-identical. They are scenario 8's coverage, not superseded by it. Deleting them on the strength of the word "backup" appearing in this change would remove the only test of the clause the change deliberately keeps. |
| `ansible/roles/deploy_user/molecule/default/` and `ansible/roles/ops_user/molecule/default/`, which mention "per-application" throughout | They verify *Restricted Deploy Account Supports Per-Application Forced-Command Deploys* — SSH forced commands per application, an unrelated requirement in `iac-host-configuration`. The shared phrase is a coincidence of vocabulary. |
| `.github/tests/test_ci_configuration.py`, the `postgres_data` literal at the shared-stack pinning section's empty-stack fixture | It is a fixture proving a stack with no `services:` fails rather than reading nothing. It asserts nothing about the instance's role. |

Nothing in this pass was edited, deleted or disabled. Every entry above would be a **candidate for human confirmation** had there been one; there is none.

## Unresolved project questions

No channel exists to ask on. Each question below was resolved by an assumption, recorded with the tests that depend on it.

1. **New file in `.github/tests/`, or a new section in `test_ci_configuration.py`?** AGENTS.md's glob (`.github/tests/*.py`) permits either and says nothing more. *Assumption taken:* append a section to `test_ci_configuration.py`. Its own header states that "sections added later carry their own provenance comment", so the file is designed for it — and, decisively, the suite's self-assertions (`TestTheSuiteNeedsNoPrivilegedResource`) read `SUITE_PATH`, which is `test_ci_configuration.py` alone. A separate file would have escaped the no-network, no-subprocess and stdlib-only checks silently, weakening a requirement this repository already holds. *Depends on it:* all 24 new tests. Nothing existing in that file was edited; the section is appended whole.

2. **May a test read the new requirement's own text from `openspec/specs/`?** No: a delta merges into the main specification only at archive, which happens *after* the pull request whose CI must be green. A test reading the requirement's table would be red from implementation until archive. Citing the change's own directory instead is forbidden by AGENTS.md and is itself asserted by this suite. *Assumption taken:* the classification is restated as `CLASSIFIED_STACK_STORES` in the suite, with a comment saying it is not a copy of the requirement's table and a failure message directing the author back to the requirement. *Depends on it:* `TestEveryPersistentStoreTheStackDeclaresIsClassified` and `TestTheStoreCensusIsARealReadOfTheFile` in full. The cost is that the enumeration and the requirement's table can drift; the mitigation is that they drift *loudly* — adding a store to the stack fails until both are updated.

3. **Should the policy scenarios be covered by asserting documentation prose?** Considered and rejected. `platform/README.md` and `docs/bootstrap-a-new-host.md` are committed files this suite may read, so a test asserting they contain particular sentences would be placeable. But no scenario's `THEN` is "the README says X" — each states what an application shall do — so such a test would substitute a derived assertion about wording for the specified one it cannot reach, and would pin phrasing that tasks 2.1 to 2.4 deliberately leave to the author. *Depends on it:* scenarios 1, 2, 3, 6 and 7 staying uncovered.

4. **Should the superseded-model sweep (task 3.4) be enforced by a test?** Considered and rejected. Its pass condition is that every remaining hit is "correct under the new scoping, dated as a historical record, or explained" — three judgements no static check can make. A grep-shaped test would be red on the change's own dated review document and on every legitimate historical record. Left to task 3.4's human sweep.

## What the implementation step must make pass

All 24 new tests are **green already**, and that is the expected result rather than an alarm — read against the testing floor's two situations, the target here already exists. The change writes specification text; the properties its classification rests on are in `platform/docker-compose.yml` today, and this change is specified to leave that file untouched. So:

1. **Run `python3 -m unittest discover --start-directory .github/tests` from inside this worktree and expect 170 green.** Task 4.2's count is 146 + 24. The suite fails from the repository's *main* working tree while any `.claude/worktrees/` tree exists — the known false failure task 3.3 records.
2. **Any new test turning red means the change grew beyond what it proposed.** Every one of the 24 asserts of `platform/docker-compose.yml`, which task 4.4 forbids this change from touching — including the "tempting one-line fix to `allowUiUpdates`" that task names, which `test_the_dashboard_provider_still_permits_the_ui_edits_the_policy_covers` would catch.
3. **Five delta scenarios have no test.** Scenarios 1, 2, 3, 6 and 7 are carried entirely by tasks 4.5 and 4.6's readings and by the code review at 5.1. Nothing in the suite will notice if the two delta specs contradict each other on what an application may persist.
4. **Scenario 4 is covered only over the stack-declared subset.** Task 3.6's host census — `docker volume ls` and every running container's mounts — is not replaced, reduced or partially discharged by anything here. It is what covers Alertmanager's image-declared volume, and it is the step that found that store in the first place.

That the checks discriminate was confirmed, not assumed: the five committed-file assertions were re-run against a mutated copy of the stack definition (retention size set to `0`, `allowUiUpdates` set to `false`, the three dashboard config mounts deleted, `postgres_data` renamed to an unclassified bind mount) and all five failed with the intended messages, while the same five pass against the committed file.
