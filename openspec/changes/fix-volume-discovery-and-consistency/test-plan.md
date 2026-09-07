# Test plan — `fix-volume-discovery-and-consistency`

Derived from this change's delta specs alone, before any implementation of it
existed, by an author who has not read the implementation. This file is **not**
an artifact the OpenSpec schema knows about: it does not appear among
`openspec instructions apply`'s context files and has to be read on purpose,
before implementing.

Written against the plan committed at `7582d0c`. If the delta specs are revised,
this file is replaced wholesale rather than merged into — a manifest states the
change as it now stands.

**This pass is additive only: it adds tests and never subtracts.** No existing
test file was edited, deleted or disabled. No implementation was written; every
new test that fails does so because the behaviour it asserts does not exist yet,
and that is the expected result.

## Test commands

Both of this project's suites are in scope, plus the Molecule suite the
dispatch named (see *Unresolved project questions* 1).

| Subject | Command | Where |
|---|---|---|
| CI configuration and committed files the pipeline reads | `python3 -m unittest discover --start-directory .github/tests` | repository root |
| Ansible role behaviour | `molecule test --all`, or `molecule test -s <scenario>` | each role directory |

No test was placed under `terraform/modules/<name>/tests/*.tftest.hcl`: this
change touches no Terraform module.

## Baseline

Taken before any file was written or edited.

| Suite | Scope | Result |
|---|---|---|
| `python3 -m unittest discover --start-directory .github/tests` | full | **68 tests, OK** |
| `pre-commit run --all-files` | full | **6/6 hooks passed** |
| `molecule test --all` in `ansible/roles/platform_data_volume` | scoped: the one role whose scenarios this change adds to | **rc=0**, `default` green |
| `molecule test --all` in `ansible/roles/hardening` | scoped: same | **rc=0**, `default` green |

The Molecule baseline is scoped rather than full, and the scope is the two roles
this change adds scenarios to. It is recorded as scoped deliberately: the
purpose is attributability of the new scenarios' failures, which a run of those
two roles satisfies.

One further environment fact was measured rather than assumed, because two
assertions depend on it: the pinned base image
`geerlingguy/docker-ubuntu2204-ansible@sha256:0172e3b5…` ships **no `ufw`** and
**no `/dev/disk`** (probed 2026-09-07). The first is what makes the
"host was not changed" assertion non-vacuous; the second is why the
empty-discovery case needs no fixture.

## Scenario accounting

Eighteen `#### Scenario:` blocks across the two delta specs. Each is accounted
for exactly once below.

### `iac-host-configuration` — ADDED: A Role's Absent Required Input Is Reported by Name

| # | Scenario | Covered by | Status |
|---|---|---|---|
| 1 | A required input is not supplied | `ansible/roles/hardening/molecule/absent-ssh-cidrs/` — `Assert the run failed rather than converging without an SSH CIDR list`, `Assert the failure came from an explicit check, not from a task that consumed the variable`, `Assert the failure was not an undefined-variable error raised by a consuming task`, `Assert the diagnostic names the input and where it is expected to be set` | covered |
| 2 | An input consumed only under a condition is not demanded when that condition does not hold | — | **deliberately uncovered**, see below |
| 3 | An empty value the role gives a meaning to is not a missing input | `ansible/roles/platform_data_volume/molecule/no-device-discoverable/` — `Assert the empty device value was treated as "discover it", not as a missing input` (and the scenario's whole premise: no device is supplied anywhere, so the role's own `""` default is what it sees) | covered |
| 4 | The check precedes the tasks that consume the input | `ansible/roles/hardening/molecule/absent-ssh-cidrs/` — `Assert the host was not changed before the run stopped`, guarded by `Assert the package facts were actually gathered` | covered |

**Scenario 2, deliberately uncovered, with the reason.** The only input in this
repository in that class is `tailscale_auth_key`, and this change deliberately
does not touch it (design.md Decision 3a; tasks.md 4.3 completes when the
reasoning is recorded, not when code is written). The `tailscale` role carries
no Molecule scenario at all, and standing one up needs a fixture that puts the
host in the "already joined" state the guard skips on — which is the work
tasks.md 7.2 queues rather than folds in. An alternative was considered and
rejected: a static assertion that `tailscale/tasks/main.yml` contains no
unconditional `assert`. It would assert the shape of an implementation rather
than a behaviour, and would pass equally against a role that had never been
looked at. The absence of a test here is a recorded decision, not an oversight.

Note also what this requirement does **not** rest on: `platform_data_volume`'s
no-device scenario demonstrates the *volume* requirement, not this one — its
`""` is a supplied value the role gives a meaning to, which this requirement's
empty-value clause explicitly excludes (design.md Decision 3b). Scenario 1's
coverage is `hardening`'s scenario alone. `deploy_user` gets no scenario of its
own by the same decision; its regression cover is that its three existing
scenarios stay green, which is tasks.md 4.2's check and not a test this pass
wrote.

### `iac-host-configuration` — MODIFIED: Platform Data Volume Is Mounted at a Fixed Host Path

| # | Scenario | Covered by | Status |
|---|---|---|---|
| 5 | Volume is mounted at a known path | `ansible/roles/platform_data_volume/molecule/default/verify.yml` — `Assert the data volume is mounted at the fixed path, on the expected device and filesystem` | already covered, unchanged by this change |
| 6 | Mount survives a reboot | `…/molecule/default/verify.yml` — `Assert a well-formed, active fstab entry exists…`, `Assert the mount comes back at the same path from 'mount -a' alone` | already covered (by proxy, as that file records), unchanged |
| 7 | Dependent subdirectories exist before a service needs them | `…/molecule/default/verify.yml` — `Assert every dependent subdirectory exists with the ownership and permissions its container requires`, `…is genuinely on the mounted volume…` | already covered, unchanged |
| 8 | No device is supplied and none can be discovered | `ansible/roles/platform_data_volume/molecule/no-device-discoverable/` (whole scenario) | covered, new |
| 9 | More than one candidate device is attached | `ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/` (whole scenario, run in both fixture orders) | covered, new |

Scenarios 5–7 are carried through the MODIFIED delta verbatim: the revision adds
prose and two scenarios and changes none of the three. Their existing tests were
neither edited nor re-authored — re-writing a passing test for an unchanged
scenario would be churn, and editing one is forbidden here regardless. They must
stay green through the change; tasks.md 3.2 and 3.3 make that a check.

### `iac-platform-services` — ADDED: Shared-Stack Service Images Are Pinned to an Exact Release

| # | Scenario | Covered by (all in `.github/tests/test_ci_configuration.py`) | Status |
|---|---|---|---|
| 10 | A service declares a tag that names no specific release | `TestSharedStackServiceImagesArePinnedToAnExactRelease.test_every_shared_stack_service_names_an_exact_release`, `.test_a_bare_series_tag_is_rejected`, `.test_a_channel_tag_is_rejected`, `TestTheSharedStackPinningCheckIsARealReadOfTheFile.test_a_service_added_with_a_moving_tag_is_caught_with_no_test_edit` | covered |
| 11 | The automated check enforces a floor and says so | `.test_a_channel_tag_is_rejected`, `.test_a_bare_series_tag_is_rejected`, `.test_a_more_specific_tag_is_never_rejected_for_being_specific`, and — for the second limb, "SHALL record that passing establishes only a necessary condition" — `.test_the_check_records_that_it_establishes_only_a_necessary_condition` | covered |
| 12 | The check does not reject a correctly pinned release | `.test_a_two_component_postgresql_release_is_accepted`, `.test_a_more_specific_tag_is_never_rejected_for_being_specific` | covered |
| 13 | A version change is visible to the deploy approver | — | **deliberately uncovered**: the scenario says of itself that it "states why the requirement above matters rather than imposing a new obligation", and is "already discharged by `iac-platform-deploy-pipeline`'s 'Reviewer Sees the Exact Diff Before Approving' requirement, and needs no separate mechanism". There is no new obligation to assert; a test here would re-assert another capability's requirement. |

### `iac-platform-services` — MODIFIED: Metrics Dashboards Are Available

| # | Scenario | Covered by | Status |
|---|---|---|---|
| 14 | An operator views current health | — | **deliberately uncovered**: a runtime property of a deployed Grafana, unchanged by this change. Nothing in the two test commands can reach a running stack. |
| 15 | The dashboard interface is not reachable from the public internet | — | **deliberately uncovered**: same class, unchanged by this change. |
| 16 | The dashboard interface has no default credential | — | **deliberately uncovered**: same class, unchanged by this change. (No pre-existing test covers it either; that is stated as an observation, not proposed as work for this change.) |
| 17 | A generated link addresses the host, not the viewer's own machine | — | **deliberately uncovered by an automated test**, and assigned instead to observation: design.md's Migration Plan step 3 reads Grafana's own `appUrl` from `/login` on the live host, and tasks.md 1.5 records the "before" value. Neither test command may make a network call — `.github/tests`' own tests forbid it — so the server-side half of this obligation is not placeable in either suite. |
| 18 | The configured base URL is not a literal that ignores where the interface is published | `TestDashboardBaseUrlIsNotALiteralAddress.test_the_configured_base_url_is_derived_from_where_the_interface_is_published`, `.test_any_literal_host_is_rejected_not_only_localhost`, `.test_interpolating_a_different_variable_is_rejected`, `.test_the_expected_form_is_accepted`, `.test_an_absent_root_url_is_reported_rather_than_skipped` | covered |

Scenarios 14–16 are carried through the MODIFIED delta verbatim; the revision
adds one paragraph of prose and two scenarios (17 and 18).

**Count check.** 18 scenarios in the delta specs; 18 accounted for here, none
omitted:

- **12 covered** — 3 by pre-existing tests this pass did not touch (5, 6, 7) and
  9 by tests this pass wrote (1, 3, 4, 8, 9, 10, 11, 12, 18);
- **6 recorded as uncovered, each with its reason** (2, 13, 14, 15, 16, 17).

## Tests written, and the failure each produced against the current tree

Every one of these was run. The failures below are observed, not predicted.

### Molecule — `ansible/roles/platform_data_volume/molecule/no-device-discoverable/`

Run as `cd ansible/roles/platform_data_volume && molecule test -s no-device-discoverable`.

**Observed: rc=2, failing at `Assert the failure came from the role's own device
check, not from indexing an empty discovery result`.** The recorded outcome was:

- `failed_task_name`: `Resolve the discovered device path`
- `failed_action`: `ansible.builtin.set_fact`
- `failed_msg`: `Task failed: Finalization of task args for 'ansible.builtin.set_fact' failed: Error while resolving value for 'platform_data_volume_device': …_AnsibleLazyTemplateList object has no element 0`

This is the wrong-reason failure tasks.md 2.3 warns about, and it is why the
scenario does not stop at "the run failed": the assertion
`Assert the run failed rather than converging without a device` **passed**
against the unfixed role. A scenario asserting only that would have gone green
having established nothing.

### Molecule — `ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/`

Run as `cd ansible/roles/platform_data_volume && molecule test -s multiple-devices-discoverable`.

**Observed: rc=2, failing at `Assert the selected device is the
lexicographically-first candidate, not the one a directory read returns first`:**
`/mnt/main-data is mounted from '/dev/loop89', but a deterministic selection over
the two candidates (…scsi-0HC_Volume_100000001 -> /dev/loop88,
…scsi-0HC_Volume_200000002 -> /dev/loop89) must yield '/dev/loop88'`. So the
unfixed `files[0]` selects **`/dev/loop89`**, the lexicographic loser.

**The order-sensitivity check (tasks.md 2.5b) found a defect in the first draft
of this fixture, and that is recorded rather than quietly fixed.** The draft
assumed a tmpfs directory read returns entries in creation order and created the
links loser-first. Measured, the opposite holds on this kernel: `/dev`'s readdir
returns the **last-created** entry first. Under that draft the unfixed role
selected `/dev/loop88` — the right answer, by luck — and the scenario passed
(rc=0), discriminating nothing. The fixture now creates the winner first, and:

| Fixture order | Unfixed role selects | Result |
|---|---|---|
| default (`MOLECULE_MULTI_DEVICE_REVERSE_ORDER` unset) | `/dev/loop89` | **rc=2** — the discriminating failure |
| `MOLECULE_MULTI_DEVICE_REVERSE_ORDER=true` | `/dev/loop88` | rc=0 — passes |

That the answer *changes with creation order* is the defect itself, stated as an
observation. After the fix, **both rows must be rc=0**; that pair is what
establishes determinism, and running only one of them establishes nothing.

To stop the by-luck pass from ever returning silently, `verify.yml` now carries
`Assert the fixture achieved the directory-read order it intended`, which
re-reads the directory with the same module the role's discovery uses and fails
loudly if the arrangement is not the intended one. Readdir order is measured, not
contracted; this assertion is what turns a future change in it into a visible
failure rather than a scenario that quietly stops discriminating.

### Molecule — `ansible/roles/hardening/molecule/absent-ssh-cidrs/`

Run as `cd ansible/roles/hardening && molecule test -s absent-ssh-cidrs`.

**Observed: rc=2, failing at `Assert the failure came from an explicit check, not
from a task that consumed the variable`.** The recorded outcome was:

- `failed_task_name`: `Allow SSH (22) from the configured CIDRs`
- `failed_action`: `community.general.ufw`
- `failed_msg`: `Task failed: 'hardening_ssh_allowed_cidrs' is undefined`

As with the volume scenario, `Assert the run failed …` **passed** against the
unfixed role, so it is not the assertion that discriminates.

`Assert the host was not changed before the run stopped` is **not reached** on
the current tree, because an earlier assertion fails first. Its non-vacuity was
therefore established separately, by two observations rather than by assertion:

1. the converge log shows `TASK [hardening : Ensure UFW is installed]` reporting
   **changed**, and a direct read of the instance after that converge
   (`molecule converge -s absent-ssh-cidrs`, then `ls -l /usr/sbin/ufw`) shows
   **`/usr/sbin/ufw` present** — so the assertion evaluates to *false* on the
   current tree and would fail if reached;
2. the pinned base image ships no `ufw` at all, so after the fix the assertion
   is evaluated over a real absence rather than over a package that was never
   going to be there.

### `.github/tests/test_ci_configuration.py` — 17 tests appended

Nothing existing in that file was modified; the new section was appended before
the `if __name__ == "__main__":` guard, carrying its own provenance comment as
the module header requires of later sections. No import was added.

`python3 -m unittest discover --start-directory .github/tests` now reports
**85 tests, 2 failures** — up from the 68-test green baseline, with 15 of the 17
new tests passing (they exercise the check against fixtures) and exactly the two
that read the committed file failing:

| Test | Observed failure |
|---|---|
| `TestSharedStackServiceImagesArePinnedToAnExactRelease.test_every_shared_stack_service_names_an_exact_release` | `Lists differ: [] != ['postgres: postgres:16']` — `postgres` named for its bare `16`; the other seven services pass |
| `TestDashboardBaseUrlIsNotALiteralAddress.test_the_configured_base_url_is_derived_from_where_the_interface_is_published` | `GF_SERVER_ROOT_URL is 'http://localhost:3000', whose host 'localhost' is a literal address rather than an interpolation of the value that determines where the interface is published` |

Full list of the tests added, each individually selectable as
`python3 -m unittest test_ci_configuration.<Class>.<method>` run from
`.github/tests`:

`TestSharedStackServiceImagesArePinnedToAnExactRelease`
— `test_the_check_reads_every_service_the_stack_defines`,
`test_every_shared_stack_service_names_an_exact_release`,
`test_a_two_component_postgresql_release_is_accepted`,
`test_a_bare_series_tag_is_rejected`,
`test_a_channel_tag_is_rejected`,
`test_a_more_specific_tag_is_never_rejected_for_being_specific`,
`test_a_content_digest_is_accepted_whatever_its_tag`,
`test_the_check_records_that_it_establishes_only_a_necessary_condition`.

`TestTheSharedStackPinningCheckIsARealReadOfTheFile`
— `test_a_service_added_with_a_moving_tag_is_caught_with_no_test_edit`,
`test_a_service_declaring_no_image_fails_by_name_rather_than_being_skipped`,
`test_a_stack_declaring_no_services_fails_rather_than_reading_nothing`,
`test_a_stack_whose_services_all_name_releases_is_accepted`.

`TestDashboardBaseUrlIsNotALiteralAddress`
— `test_the_configured_base_url_is_derived_from_where_the_interface_is_published`,
`test_any_literal_host_is_rejected_not_only_localhost`,
`test_interpolating_a_different_variable_is_rejected`,
`test_the_expected_form_is_accepted`,
`test_an_absent_root_url_is_reported_rather_than_skipped`.

### The check is a real read of the file, verified against the file itself (tasks.md 2.7)

Beyond the fixture-based tests above, both mutations tasks.md 2.7 names were
applied to the committed `platform/docker-compose.yml`, observed, and reverted:

| Temporary mutation | Observed, with no test edit | Reverted |
|---|---|---|
| added `temporary-fixture:` declaring `redis:latest` | `['postgres: postgres:16', 'temporary-fixture: redis:latest']` | yes, byte-identical (`cmp`) |
| removed `grafana`'s `image:` key | `['grafana: declares no image:', 'postgres: postgres:16']` | yes, byte-identical (`cmp`) |

`git status --porcelain` after both showed `platform/docker-compose.yml`
unmodified.

### The suite still needs no privileged resource (tasks.md 2.9)

The three existing self-checks were run individually and all pass:
`TestTheSuiteNeedsNoPrivilegedResource.test_the_suite_imports_only_the_standard_library_and_pinned_dependencies`,
`.test_the_suite_imports_no_network_capable_module`,
`.test_the_suite_spawns_no_terraform_binary_or_container_runtime`.
That is the whole of what is claimed here — those three assert imports and
`subprocess` argv heads read out of the suite's own AST, and nothing more.

### Static analysis

`pre-commit run --all-files` after every file was written: **6/6 passed**,
`ansible-lint` included, matching the baseline.

## Assertion classification

Per-assertion SPECIFIED / DERIVED annotations are written beside the assertions
themselves — in each `verify.yml`'s header block and in each Python test's
docstring — so they survive next to what they classify. Summarised:

**SPECIFIED** (traces to SHALL text in a delta scenario):

- the run fails; the failure comes from an explicit check rather than from the
  consuming expression; the diagnostic names the input; the empty value is
  treated as the role's own signal; the host is unchanged when the run stops;
- the selected device is deterministic and is not the entry the directory read
  returned first;
- every stack service names an exact release; `latest` and other channel tags
  are rejected; a tag naming fewer than two version components is rejected; a
  correctly pinned two-component PostgreSQL release is accepted; a more specific
  tag is never rejected for being specific; a digest is accepted; the check
  records that it establishes only a necessary condition;
- the dashboard base URL is derived from the value that determines where the
  interface is published; a literal host is rejected, `localhost` included.

**DERIVED** (this pass's inference; no scenario states it):

- *`volume_enabled` as the token naming "the attachment it depends on"* — the
  clause is specified, the token comes from the role's existing `fail_msg` and
  from tasks.md 2.3.
- *`ansible/inventory/group_vars/prod.yml` as "how to supply it"* — the clause is
  specified, the path comes from tasks.md 2.4/4.1.
- *"lexicographically first" as the deterministic rule* — the spec fixes
  determinism, not which device. Sorting is design.md Decision 2's choice. A
  different deterministic rule would be a spec-legal implementation this
  assertion must be **re-pointed at, not weakened**.
- *the explicit "not an index error" / "not an undefined-variable error"
  assertions* — redundant with the task-identity assertions, kept so a run
  reports *which* wrong failure occurred.
- *both candidates are present; the fixture achieved its intended read order;
  package facts were actually gathered; the check reads every service; a
  service with no `image:` is reported by name; a stack with no services fails*
  — non-vacuity guards.
- *the converse "this passes" tests* (`test_the_expected_form_is_accepted`,
  `test_a_stack_whose_services_all_name_releases_is_accepted`) — without them a
  check that rejected everything would satisfy the negative tests.
- *the choice of `assert` as a substring of the recorded action* — follows
  `ghcr-credential-rejected/verify.yml:56`, which the change's own tasks name as
  the pattern.

**Deliberately untested**, each with its reason: scenarios 2, 13, 14, 15, 16 and
17 above; and, within `no-device-discoverable`, the *success* branch of the
marker file — it is written and asserted on, but no run in this pass exercised
it, because on the current tree the role always fails there. It exists to catch a
later widening of the guard.

## Obsolete tests

**Not vacuous, and not skipped.** The change carries two `MODIFIED` deltas, so a
search was owed and was performed.

**Basis, established by comparing each MODIFIED delta with the requirement as it
stands under `openspec/specs/`:** both revisions are **purely additive**. For
`Platform Data Volume Is Mounted at a Fixed Host Path`, the three pre-existing
scenarios appear in the delta verbatim and two are added; for `Metrics
Dashboards Are Available`, the three pre-existing scenarios appear verbatim and
two are added. In both, the added text is new normative prose plus new
scenarios. **No previously specified behaviour is superseded**, so there is no
superseded behaviour for an existing test to bear on.

The search was run anyway, bounded to the two dispatched test-path globs and
nowhere else:

| Glob | Terms searched | Found |
|---|---|---|
| `.github/tests/*.py` | `postgres:16`, `GF_SERVER_ROOT_URL`, `localhost:3000`, `docker-compose`, `grafana`, `GF_SECURITY`, `GRAFANA_BIND` | one hit only: `platform/docker-compose.yml` appears as a *fixture string* in `TestApplyWorkflowTriggerIsPathFiltered.NON_INFRASTRUCTURE_PATHS`, which asserts that a non-Terraform path does not trigger the apply workflow. Unrelated to either delta and unaffected by this change. |
| `ansible/roles/*/molecule/*/` | `platform_data_volume_by_id`, `files[0]`, `hardening_ssh_allowed_cidrs`, `deploy_apps` | seven scenario files, all of which **supply** the variable in question and assert the success path. None asserts behaviour this change supersedes; all must stay green (tasks.md 3.2, 4.1, 4.2). |

**Result: no obsolete test. Nothing is to be deleted or rewritten.** This is the
stronger of the two readings — "no such test exists", not merely "none was found
by this search" — because it rests on the additive-only comparison above rather
than on the search alone. No dispatched earlier `test-plan.md` was supplied, and
none was sought.

Two tasks outside the delta specs touch files that a test could in principle have
been written against, and are named here so their absence from the list is
visible rather than silent: tasks.md 5.3 deletes `platform/docker-compose.yml`'s
header block, and 6.1 moves a comment in `ansible/inventory/group_vars/prod.yml`.
No test in either glob reads either of those regions.

## Unresolved project questions

Recorded rather than resolved silently. This pass runs non-interactively and has
no channel to ask on; each entry states the assumption taken and which tests
depend on it.

1. **AGENTS.md's "Testing" table names two suites, and Molecule is not one of
   them.** Its rows are `terraform test` and `.github/tests`. The dispatch
   supplied a third pair — `molecule test --all` from each role directory, with
   the glob `ansible/roles/<name>/molecule/<scenario>/`. *Assumption taken:* the
   Molecule suite is where a role's behaviour is asserted in this project,
   supported by `ansible-verify.yml` running it in CI and by the six scenarios
   already committed. *Tests depending on it:* all three new Molecule scenarios.
   *Recommendation:* AGENTS.md's table should gain the row, so the next
   test-authoring dispatch does not have to be told.

2. **No project convention for a scenario-level fixture switch.**
   `MOLECULE_MULTI_DEVICE_REVERSE_ORDER` is this pass's invention. *Assumption
   taken:* an environment variable read with `lookup('env', …)`, modelled on the
   form `deploy_user/molecule/ghcr-credential-rejected/converge.yml` already
   uses. *Tests depending on it:* `multiple-devices-discoverable` (its default
   behaviour is unaffected; the switch only selects the fixture's link order).

3. **Loop-device minor numbers are chosen, not allocated.** 88 and 89, to avoid
   `default`'s 87. A loop association is kernel-global and outlives the
   container, so a CI host with those claimed would need different numbers —
   the same unresolved question `default`'s own `prepare.yml` already records
   for 87, and the same right answer (a shared fact-caching or allocation
   mechanism) is still a repository-wide decision this pass has no authority to
   make. *Tests depending on it:* `multiple-devices-discoverable`.

4. **A tmpfs directory-read order is measured, not contracted.** The
   discriminating power of `multiple-devices-discoverable` rests on `/dev`'s
   readdir returning the last-created entry first, observed 2026-09-07 on this
   kernel and image. *Mitigation taken, not an assumption left bare:*
   `verify.yml` asserts the intended order was achieved, so a kernel that
   ordered differently produces a visible failure rather than a silent loss of
   discrimination. *Tests depending on it:* `multiple-devices-discoverable`.

5. **`prepare` is left in the two failure-path scenarios' `test_sequence`
   although neither has a `prepare.yml`.** Molecule reports it as a missing
   playbook and continues; the existing scenarios' recaps already show missing
   steps, so this is assumed acceptable rather than noisy. *Assumption taken:*
   leaving the step in place costs nothing and means a fixture added later needs
   no sequence edit. *Tests depending on it:* `no-device-discoverable`,
   `absent-ssh-cidrs`.

6. **No version-dated Molecule idiom is available in the toolkit.** The
   `ansible` skill covers Molecule as a mechanism but carries no
   version-verified idiom for scenario authoring. *Assumption taken:* this
   repository's six existing scenarios are the pattern of record, and every new
   file follows them (galaxy dependency stanza, `ANSIBLE_ROLES_PATH`, the
   digest-pinned platform block, the `block`/`rescue` marker-file shape).
   *Tests depending on it:* all three new scenarios.

## What the implementation must make pass

After tasks.md groups 3–6, all of the following must be green:

```
cd ansible/roles/platform_data_volume && molecule test --all
cd ansible/roles/hardening            && molecule test --all
MOLECULE_MULTI_DEVICE_REVERSE_ORDER=true \
  molecule test -s multiple-devices-discoverable   # from ansible/roles/platform_data_volume
python3 -m unittest discover --start-directory .github/tests   # from the repository root
pre-commit run --all-files
```

Mapping from task to the tests it must satisfy:

| Task | Must make pass |
|---|---|
| 3.1 (guard the discovery result) | `no-device-discoverable` |
| 3.2 (sort the discovery result) | `multiple-devices-discoverable`, in **both** fixture orders |
| 3.3 | all three `platform_data_volume` scenarios |
| 4.1 (`hardening` assert) | `absent-ssh-cidrs`, and `hardening`'s `default` stays green |
| 4.2 (`deploy_user` assert) | `deploy_user`'s three existing scenarios stay green |
| 5.1 (`postgres:16.15`) | `TestSharedStackServiceImagesArePinnedToAnExactRelease.test_every_shared_stack_service_names_an_exact_release` |
| 5.2 (`GF_SERVER_ROOT_URL`) | `TestDashboardBaseUrlIsNotALiteralAddress.test_the_configured_base_url_is_derived_from_where_the_interface_is_published` |

Two reminders that follow from the failures observed above rather than from
general caution:

- **`no-device-discoverable` and `absent-ssh-cidrs` each already pass their
  "the run failed" assertion against the unfixed role.** Reading a partial green
  in those scenarios as progress would be reading the wrong signal; the
  discriminating assertions are the ones naming the failing task.
- **`multiple-devices-discoverable` must be run in both fixture orders.** One
  order alone can pass against an unsorted implementation — it did, in this
  pass's first draft.
