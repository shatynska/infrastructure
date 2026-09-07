# Test plan — `pin-and-fix-molecule-suite`

Derived from this change's delta spec
(`specs/iac-cicd-pipeline/spec.md`) before any implementation of the change
existed, by an author who has read none of the implementation.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among `openspec instructions apply`'s context files and must be read on
purpose, before implementing.

Everything written by this pass is **additive**: one file was appended to, no
existing test was edited, deleted or disabled, and no implementation was
written.

---

## What was written

All new tests live in
`.github/tests/test_ci_configuration.py`, appended as one section between
`TestToolchainIsInstalledFromPinnedManifests` and the
`Gated Production Apply` section. That destination is the "CI configuration"
row of `AGENTS.md`'s Testing table, whose Subject column task 5.1 widens to
name it; the glob is `.github/tests/*.py` and the file already holds every
other assertion about this requirement.

A new file under the same glob was considered and rejected: three existing
tests (`test_the_suite_imports_only_the_standard_library_and_pinned_dependencies`,
`test_the_suite_imports_no_network_capable_module`,
`test_the_suite_spawns_no_terraform_binary_or_container_runtime`) read
`SUITE_PATH`, which is that one file. New code in a sibling file would escape
all three.

The module docstring gained one paragraph saying that later sections carry
their own provenance comment. No existing sentence was altered.

**Test command:** `python3 -m unittest discover --start-directory .github/tests`,
run from the repository root. Individually selectable, e.g.:

```
PYTHONPATH=.github/tests python3 -m unittest \
  test_ci_configuration.TestMoleculeScenarioImagesArePinnedByDigest\
.test_every_scenario_declares_its_platform_image_by_immutable_digest
```

### Helpers added (not tests)

`galaxy_role_directories`, `authored_scenario_files`, `parse_image_reference`,
`scenario_platform_images`, `scenarios_declaring_no_platform_image`,
`scenarios_with_an_unpinned_platform_image`,
`image_repositories_named_at_disagreeing_digests`, `scenario_document`,
`ScenarioTreeFixtureMixin`, `ManifestNotUsable`.

Each takes its repository root as an argument, defaulting to `ROOT`. That is
what lets every negative case be exercised against a throwaway fixture tree
instead of by temporarily damaging the real tree — tasks 2.1a, 2.2, 2.4, 2.5
and 2.6 each describe a temporary edit-and-revert against the working tree;
the fixture form asserts the same properties without one, and without a revert
that can be forgotten.

These helpers are test-support code for assertions over committed YAML. They
are **not** the implementation of the change: they do not pin any image, do not
edit any `molecule.yml`, and do not touch `verify.yml`.

---

## Baseline

Taken before any test was written, on the provisioned worktree
`/home/shatynska/projects/infrastructure/.claude/worktrees/pin-and-fix-molecule-suite`.

- **Full suite** (`python3 -m unittest discover --start-directory .github/tests`):
  **46 tests, 0 failures, 0 errors — OK.** Nothing was failing beforehand, so
  every failure below is attributable to this pass.
- Interpreter: CPython 3.12.3 with PyYAML 6.0.1, identical under system
  `python3` and under `/home/shatynska/.venvs/ci/bin/python`. Both were run;
  both give the same result.
- Tree state: **provisioned.** `ansible/roles/geerlingguy.docker/` exists and
  ships `molecule/default/molecule.yml` on the floating tag
  `geerlingguy/docker-${MOLECULE_DISTRO:-rockylinux9}-ansible:latest`. The raw
  glob `ansible/roles/*/molecule/*/molecule.yml` therefore matches **nine**
  files here and would match **eight** on a runner that has installed nothing.
- All eight repository-owned scenarios name
  `geerlingguy/docker-ubuntu2204-ansible:latest` with no digest.

### After this pass

`python3 -m unittest discover --start-directory .github/tests` →
**68 tests, 1 failure.**

The failure is
`TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest`,
naming all eight repository-owned scenarios and correctly **excluding** the
installed Galaxy one. This is failure state 1 of the testing standard — the
check ran and discriminated — not state 2: the assertion executed against real
committed YAML and produced a wrong-value verdict. Making it pass is task 3.1's
job.

The three suite-constraint tests named in the dispatch were re-run explicitly
after the append and all pass: no import outside stdlib + `yaml` was added, no
network-capable module, no new `subprocess` spawn (the fixtures are built with
`tempfile`/`pathlib`, not by shelling out).

### Two out-of-band verifications, recorded because they used real content

Neither is a committed test; both were run once to check that the committed
tests assert what they claim.

1. **Environment parity on real content** — discovery was run against the real
   tree and against a scratch tree symlinking every role directory except
   `geerlingguy.docker`, plus the real `ansible/requirements.yml`. Both returned
   the **same eight** scenario paths. This is the concrete form of task 2.1's
   "same eight files provisioned as unprovisioned"; the committed test
   `test_discovery_is_identical_with_and_without_installed_galaxy_content`
   asserts the property on a fixture, because the real tree is in one state or
   the other and never both.
2. **The assertions are satisfiable, and still discriminate, on real content** —
   the eight real scenario files were copied with
   `:latest` replaced by
   `:latest@sha256:0172e3b586fc316491b5ac080e6b24c5f66cde985c27c625025f13f66a8cd21f`
   (the digest `proposal.md` names). All three checks then returned empty.
   Reverting exactly one of the eight put one entry back in the unpinned list
   and produced a digest disagreement. So the failing test is not
   unconditionally red, and the agreement check is not unconditionally green.

---

## Scenario accounting

The delta reproduces the requirement whole and is **purely additive**: a
line-by-line diff of the requirement as it stands at
`openspec/specs/iac-cicd-pipeline/spec.md:211` against the delta shows five
added paragraphs and five added scenarios, with **no existing paragraph or
scenario altered or removed**.

The delta contains **11** `#### Scenario:` blocks. Six pre-date this change; **5**
are added by it. Every one is accounted for below exactly once.

> Note for the dispatcher: the dispatch described "four scenarios" added. The
> count is **five** — `An upstream re-push cannot change what the suite ran
> against` is the fifth. It is accounted for below rather than dropped.

### Pre-existing scenarios (6) — not this pass's work, no test written or edited

| Scenario | Status |
|---|---|
| Ansible-only pull request is linted and syntax-checked | Already covered by `TestAnsibleBlockingTier`. Unchanged by the delta. No test written. |
| A newly added role scenario runs without a workflow change | Already covered by `TestMoleculeDiscoveryAndScenarioCoverage.test_the_workflow_names_no_role_literally`. Unchanged. No test written. |
| Every scenario a role declares is executed | Already covered by `…test_molecule_is_invoked_across_all_scenarios`. Unchanged. No test written. |
| Discovering no roles fails rather than passes | Already covered by `…test_role_discovery_fails_when_it_finds_nothing`. Unchanged. No test written. |
| A failing Molecule scenario does not block a merge | Already covered by `…test_the_workflow_uses_no_continue_on_error`. Unchanged. No test written. |
| Ansible verification receives no production credential | Already covered by `TestVerificationJobsCarryNoCredential`. Unchanged. No test written. |

Not duplicated and not edited, per the dispatch.

### Added scenarios (5)

**1. `Every scenario's platform image is pinned by digest`** — covered.

- `TestMoleculeScenarioImagesArePinnedByDigest.test_every_scenario_declares_its_platform_image_by_immutable_digest`
  — the real-tree assertion. **Fails before implementation**, naming all eight.
- `TestMoleculeScenarioImagesArePinnedByDigest.test_every_platform_a_scenario_declares_is_checked_not_only_the_first`
  — task 2.3's "every entry in `platforms:`, not only the first".
- `TestMoleculeScenarioImagesArePinnedByDigest.test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name`
  — the "SHALL NOT be exempt by being newly added" clause, as task 2.6 requires
  it: a scenario is placed at a role path named nowhere in the test file and
  all three checks are asserted to reach it.
- `TestImageReferenceParsing.test_the_combined_tag_and_digest_form_is_read_as_pinned`,
  `…test_the_bare_digest_form_is_read_as_pinned`,
  `…test_a_mutable_tag_alone_yields_no_digest`,
  `…test_a_digest_that_is_not_a_content_address_is_not_accepted`
  — the reference splitting the check depends on, at the smallest level that
  observes it.
- `TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest.test_discovery_finds_the_scenarios_this_repository_authors`
  and `…test_every_role_carrying_scenarios_contributes_at_least_one`
  — non-vacuity guards, so no assertion above can pass over an empty discovery.

**2. `A scenario declaring no platform image fails rather than being skipped`** — covered.

- `TestMoleculeScenarioImagesArePinnedByDigest.test_no_scenario_declares_a_platform_without_an_image`
  — the real-tree half. Passes today (all eight declare an image); see the
  first-run-pass note below.
- `TestMoleculeScenarioImagesArePinnedByDigest.test_a_scenario_declaring_no_platform_image_is_reported_by_name`
  — the discriminating half, over three shapes: no `platforms:` key, a platform
  with no `image:`, and an empty `platforms:` list. Asserts each offender is
  reported **by name** and that a satisfying scenario is not.

**3. `Scenarios sharing an image repository agree on its digest`** — covered.

- `TestMoleculeScenarioImagesArePinnedByDigest.test_scenarios_sharing_an_image_repository_name_the_same_digest`
  — the real-tree half.
- `TestMoleculeScenarioImagesArePinnedByDigest.test_a_partial_digest_refresh_is_reported`
  — the discriminating half. Also covers a scenario left at a mutable tag while
  its sibling is pinned, because the check treats "no digest" as a value rather
  than an absence.
- `TestMoleculeScenarioImagesArePinnedByDigest.test_a_scenario_on_a_different_image_repository_is_not_reported`
  — the delta's scoping clause ("does not require the suite to standardise on a
  single base image"), which task 2.5 also names.

**4. `Installed Galaxy content is not held to this repository's pinning obligation`** — covered.

- `TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest.test_installed_galaxy_content_is_excluded_from_discovery`
  — real tree. Its second half runs only where the installed directory is
  actually present, so the test asserts the same thing on a bare runner and
  **never skips**.
- `…test_discovery_is_identical_with_and_without_installed_galaxy_content`
  — the "same result provisioned as unprovisioned" clause, on two fixture trees
  differing only by that directory.
- `…test_the_exclusion_is_derived_from_the_manifest_rather_than_hardcoded`
  — both directions, per task 2.2: a name added to the manifest drops out of
  discovery, and `geerlingguy.docker` is discovered once the manifest stops
  naming it. A hardcoded `"geerlingguy.docker"` passes the two tests above and
  fails this one.
- `…test_a_manifest_entry_that_cannot_be_named_fails_the_check`,
  `…test_a_missing_galaxy_manifest_fails_the_check`,
  `…test_an_unparseable_galaxy_manifest_fails_the_check`
  — task 2.1a's fail-closed requirement: never an empty or partial exclusion set.
- `…test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name`
  — the `src`-basename resolution. **DERIVED**; see the classification section.

**5. `An upstream re-push cannot change what the suite ran against`** —
**partially covered, and the uncovered part is recorded here rather than
omitted.**

- What a static, offline suite can assert is the *enabling condition*: that
  every reference is a content address (`sha256:` plus exactly 64 lowercase hex),
  which is what makes a re-published tag unable to change what the reference
  resolves to. That is asserted by
  `…test_every_scenario_declares_its_platform_image_by_immutable_digest`
  together with
  `TestImageReferenceParsing.test_a_digest_that_is_not_a_content_address_is_not_accepted`,
  and the first test's docstring names this scenario.
- **Deliberately untested:** the registry's own behaviour under a re-push. It
  needs a network call to a registry and an upstream re-publish, and the same
  requirement forbids this suite any network access
  ("The suite needs no privileged or external resource"). No test in
  `.github/tests/*.py` can observe it, and a test that appeared to would be
  asserting something else.

---

## Assertion classification

Per the testing standard, every assertion is **specified** (traces to SHALL
text or a scenario in the delta), **derived** (inferred; traces to `design.md`
or `tasks.md` rather than to a scenario), or **deliberately untested**. Each
test's docstring in the file carries its own label; the two non-`SPECIFIED`
ones are surfaced here so they are visible without reading the file.

**DERIVED — 2 assertions.** Whoever implements is being asked to satisfy these,
and they trace to design decisions rather than to SHALL text:

1. `…test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name`
   — the exact resolution rule (`name` where given, else the `src` basename with
   any `.git` suffix and version qualifier stripped) is stated in `design.md`
   decision 3a, not in the delta, which requires only that the exclusion be
   *derived from the manifest*. Nothing in the repository exercises this path
   today: the manifest holds one entry, in `name` form.
2. `TestImageReferenceParsing.test_a_registry_port_is_not_mistaken_for_a_tag`
   — no scenario requires a registry host to be supported. It guards the
   parsing against a reference form this repository does not currently use.

**DELIBERATELY UNTESTED — 1 case**, recorded above: the registry's behaviour
under an upstream re-push.

Everything else is **SPECIFIED** and labelled as such in place.

### One test passes on its first run, and why that is not the state-4 alarm

`test_scenarios_sharing_an_image_repository_name_the_same_digest` and
`test_no_scenario_declares_a_platform_without_an_image` both pass against the
pre-implementation tree. That is correct, not vacuous:

- The digest-agreement property genuinely holds today — all eight scenarios
  agree, on *carrying no digest*. The scenario they violate is a different one
  ("pinned by digest"), and the test for that one fails as it must.
- Their discriminating power is established by
  `test_a_partial_digest_refresh_is_reported` and
  `test_a_scenario_declaring_no_platform_image_is_reported_by_name`, plus the
  real-content check recorded under the baseline, rather than by a red run.

The check that must go from red to green for this change is the digest one,
and only that one.

---

## Obsolete tests

**None found, and the search that establishes it is stated so the claim is
readable.**

The delta is a `MODIFIED` operation, so this list is applicable rather than
"not applicable" — but the modification is **purely additive**, established by
the line-diff recorded under *Scenario accounting*: no paragraph and no
scenario of the existing requirement was altered or removed, so no existing
assertion has been superseded.

Search performed, bounded to the dispatched test-path glob `.github/tests/*.py`
(one file, `test_ci_configuration.py`):

- case-insensitive search for `molecule`, `platforms`, `sha256`,
  `geerlingguy`, `image`, `requirements.yml` across the pre-existing 736 lines;
- read of every test in `TestMoleculeDiscoveryAndScenarioCoverage`,
  `TestToolchainIsInstalledFromPinnedManifests`,
  `TestVerificationJobsCarryNoCredential` and `TestAnsibleBlockingTier`.

Result: **no existing test asserts anything about a scenario's platform image,
its tag, or its digest.** The existing Molecule tests read
`.github/workflows/ansible-verify.yml`, not `molecule.yml`. This is "no such
test exists", established by the search above — not "none was found".

No earlier `test-plan.md` was supplied for this change and none exists in its
directory, so no scenario-to-test mapping from a previous pass was available to
draw on.

---

## Unresolved project questions

Recorded rather than resolved, because a dispatched subagent has no channel to
ask on. Each names the assumption taken and the tests that depend on it.

1. **`tasks.md` 2.1a and `design.md` decision 3a disagree about a `src`-only
   manifest entry.** 2.1a lists "a temporary `src:`-only entry" among the cases
   that "must fail the check identifying the entry"; decision 3a states that a
   `src`-only entry **resolves**, to the basename with `.git` and version
   qualifier stripped, and that only an entry the resolution *cannot* name
   fails.
   *Assumption taken:* `design.md` governs, because it states the rule
   constructively and `tasks.md` reads as a compressed restatement of it.
   *Tests depending on it:*
   `test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name`
   (asserts it resolves) and
   `test_a_manifest_entry_that_cannot_be_named_fails_the_check` (uses an entry
   with neither `name` nor `src`, which is unresolvable on either reading).
   If the intended rule is 2.1a's, the first of those two is wrong and must be
   inverted — that is a planning-artifact question for
   `openspec-update-change`, not something this pass may decide.

2. **No Python linter or formatter is recorded for `.github/tests/`.**
   `AGENTS.md` names `terraform fmt`, `tflint`, `terraform validate`,
   `gitleaks`, `ansible-lint` and `ansible-playbook --syntax-check`; none
   applies to Python, and `.github/requirements-ci.txt` pins no `ruff` or
   `mypy`. *Assumption taken:* match the surrounding file's existing style
   (~95-column lines, `from __future__ import annotations`, docstring-first
   annotations) and run no linter. *Tests depending on it:* all 22 new ones,
   stylistically only — none would change verdict under a linter.

3. **What a repository-owned role directory whose name contains a `.` should
   do.** `test_every_role_carrying_scenarios_contributes_at_least_one` compares
   discovery against the pre-existing helper `roles_with_molecule_scenarios()`,
   which excludes any directory name containing a `.` — a naming heuristic that
   pre-dates this change and that `design.md` decision 3a explicitly rejects as
   a basis for the *exclusion*. *Assumption taken:* the helper is fine as an
   independent cross-check because no repository-owned role is named that way
   today. *Test depending on it:* that one. If such a role is ever added, the
   cross-check silently weakens (it under-reports); the manifest-derived
   exclusion is unaffected.

---

## What the implementation must make pass

One check, and it is the whole of tasks 3.1–3.4:

```
PYTHONPATH=.github/tests python3 -m unittest \
  test_ci_configuration.TestMoleculeScenarioImagesArePinnedByDigest\
.test_every_scenario_declares_its_platform_image_by_immutable_digest
```

It passes when all eight repository-owned `molecule.yml` files declare their
platform image with an `@sha256:<64 hex>` digest, at the **same** digest as
each other (the agreement check enforces the second half). Either
`repo:tag@sha256:…` or `repo@sha256:…` satisfies it, so `design.md` decision
1's fallback needs no test change.

Then the whole suite:

```
python3 -m unittest discover --start-directory .github/tests
```

should report **68 tests, OK** — task 3.4 and task 6.3.

Nothing in this pass bears on tasks 4.x (`verify.yml`'s ownership assertion) or
6.1 (`molecule test --all`). Those are verified by Molecule, not by this suite,
and no test here asserts anything about them.

---

## Environment finding, unrelated to this pass

`git status`, `git diff` and `git cat-file` fail in this worktree with
`fatal: unable to read <sha>` for objects `4a1c2899…` and `1c715e60…`, while
`git log -1` succeeds (`4eec9d4 docs(openspec): plan pin-and-fix-molecule-suite`).
No git operation was performed by this pass — the only write was to
`.github/tests/test_ci_configuration.py`, by `cp`. Whoever implements will need
this repaired before task 6.4's `git diff --stat` gate can be run.
