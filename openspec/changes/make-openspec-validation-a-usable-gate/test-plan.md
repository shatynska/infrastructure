# Test plan — `make-openspec-validation-a-usable-gate`

Derived from this change's delta spec for `iac-cicd-pipeline`, before any
implementation of it existed, by an author who has not read the implementation
and cannot: none exists yet. This file is **not** an artifact the OpenSpec
schema knows about, so it does not appear among `openspec instructions apply`'s
context files and has to be read on purpose.

**This pass added tests and subtracted none.** No existing test was edited,
deleted, disabled, weakened or renamed. No implementation was written: the
workflow step, `.github/package.json`, its lockfile, the `npm` Dependabot
stanza, the three `AGENTS.md` rules and the first `## Not performed` section all
remain absent, which is why nineteen of the new tests are red.

## Where the tests live, and why they were appended

All new assertions are appended as one section to
`.github/tests/test_ci_configuration.py`, ahead of that file's
`if __name__ == "__main__":` footer. Nothing above the insertion point was
touched.

A new module under `.github/tests/` was considered and rejected for two reasons.
This change's own `tasks.md` names that file as the home of these assertions;
and the suite's self-assertions
(`TestTheSuiteNeedsNoPrivilegedResource.*`) read `Path(__file__)` — the single
file — so assertions placed in a *new* module would sit outside the suite's own
"stdlib and pinned dependencies only", "spawns nothing but `bash`/`sh`" and "no
network-capable import" guarantees. Appending keeps the new code under those
three checks. See *Unresolved project questions* below: that the self-assertions
are file-scoped rather than directory-scoped is a standing gap in the suite,
recorded here rather than fixed, because fixing it is not this change's subject.

## Test command

    python3 -m unittest discover --start-directory .github/tests

run from the repository root (AGENTS.md, "Testing", third row: any property that
is a static read of a committed file). Individual tests are selectable as, for
example:

    python3 -m unittest test_ci_configuration.TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_validating_step_script_is_the_invocations_and_nothing_else

## Baseline

**Full baseline, taken before any test was written**, on this change's working
tree at commit `50ed821`:

    python3 -m unittest discover --start-directory .github/tests
    Ran 170 tests in 1.285s — OK

Nothing was failing beforehand, so every failure reported below is attributable
to the new tests alone.

**After this pass:** `Ran 207 tests — FAILED (failures=19)`. All 170 pre-existing
tests still pass; 37 tests were added, of which 18 pass and 19 fail because the
target does not exist yet. That is the expected pre-implementation state, not a
defect, and it must not be resolved by writing implementation into this suite.

## Scenario accounting

The delta carries **one ADDED requirement** — *The Specification Record Is
Verified in Continuous Integration* — with **seven** `#### Scenario:` blocks. All
seven are accounted for below: five covered, two deliberately uncovered.

### 1. A malformed specification or delta fails the pull request that introduces it

**Deliberately uncovered as a whole.** `design.md`'s "Where each delta scenario
is verified" table decomposes it, per Decision 8, into three facts:

- *`openspec validate` exits non-zero on a bad record* — the observed premise of
  the whole change; the command exits 1 on this repository today, which is why
  the change exists. Not re-established here, and not establishable here: this
  suite is specified never to run the tool (Decision 5), and routing it through
  `bash -c` to evade the AST check is on the record as refused.
- *The step does not discard that exit status* — **covered**, statically, by
  `TestTheRecordValidationCannotReportSuccessOverAFailure` (see scenario 4).
- *GitHub reports a failed step as a failed required check* — observed manually
  at `tasks.md` 12.3.

No end-to-end test is attempted. One would require spawning `openspec`, which
breaks two properties this suite asserts about itself.

### 2. An archived change with outstanding tasks fails the pull request that archives it

**Deliberately uncovered as a whole**, decomposed identically to scenario 1, and
for the same reason. The additional fact this scenario rests on — that
`openspec validate --archived` reads unticked boxes in archived task lists — is
the tool's behaviour, and `design.md` Decision 5 rejects reimplementing it here
("a reimplementation would encode this version's notion of a completed task and
then silently disagree with the tool the moment either moved"). What *is*
covered is that the `--archived` invocation runs at all
(`test_both_the_active_and_the_archived_record_are_validated`).

### 3. Unperformed work disclosed without a reason fails the check

**Covered.**

| Test | Provenance |
|---|---|
| `TestUnperformedWorkIsDisclosedWithAReason.test_every_disclosure_carries_a_reason_with_text` | SPECIFIED |
| `TestUnperformedWorkIsDisclosedWithAReason.test_the_scan_reaches_the_repositorys_task_lists` | DERIVED — vacuity guard |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_disclosure_with_a_reason_is_accepted` | SPECIFIED — converse half |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_disclosure_with_no_reason_label_is_rejected` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_disclosure_with_an_empty_reason_is_rejected` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_reason_of_whitespace_alone_is_rejected` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_an_ordinary_task_list_raises_no_offence` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_an_active_change_is_scanned_as_well_as_an_archived_one` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_reason_wrapped_across_lines_is_accepted` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_reason_written_as_a_sibling_item_is_accepted` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_reason_stated_outside_the_section_does_not_satisfy_a_disclosure` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_each_silent_disclosure_is_reported_separately` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_the_section_ends_at_the_next_heading` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_heading_with_trailing_punctuation_still_opens_the_section` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_heading_with_a_trailing_parenthetical_still_opens_the_section` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_disclosure_written_as_prose_is_rejected` | SPECIFIED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_prose_introducing_the_entries_is_accepted` | SPECIFIED — converse half |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_section_that_discloses_nothing_is_rejected` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_numbered_section_merely_mentioning_the_phrase_is_not_a_disclosure` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_heading_quoted_inside_a_code_fence_opens_no_section` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_a_fenced_block_inside_a_real_section_does_not_end_it` | DERIVED |
| `TestTheDisclosureCheckIsARealReadOfTheFile.test_an_unterminated_fence_over_a_disclosure_heading_is_rejected` | DERIVED |

**Read this one carefully.** The repository-scoped test
(`test_every_disclosure_carries_a_reason_with_text`) is green, and greenness
alone does not say why: it reads identically whether the scan judged four
well-formed disclosures or found nothing at all. It was written when the second
was true — this change writes the repository's first `## Not performed` sections
— and the twenty fixture tests in `TestTheDisclosureCheckIsARealReadOfTheFile`
are what carry the discrimination either way. Each builds a synthetic changes
tree in a temporary directory and asserts the scanner's verdict.

**The check refuses three kinds of silence**, not one:

- an entry with no `Reason:` label, or one whose text is empty — the scenario's
  own case;
- a section that discloses **nothing**: a heading followed by prose alone, or by
  nothing at all. Prose is not a disclosure this check can read, so a section
  shaped that way would report zero offences while carrying exactly the silence
  the label exists to expose — and `openspec validate --archived` is green over
  it too, there being no checkbox left. Prose *introducing* the entries is fine
  and is the shape the settled archived records use;
- a file leaving a code fence open while naming the heading, where the scan
  cannot tell a quoted heading from a real one and says so rather than guessing
  in the direction that reports nothing.

The heading is matched **loosely** — any heading whose text *begins with* "not
performed", so `## Not performed:` and `## Not performed (two tasks)` open the
section. An exact match fails open on both. It must begin with the phrase rather
than merely contain it, so an ordinary numbered section like `## 4. Settle the
work not performed` is not read as a disclosure and its outstanding tasks are not
read as silent ones. Fenced blocks are skipped, so a `tasks.md` quoting the
heading as documentation does not open a section that swallows the rest of the
file.

The delta's own scoping is honoured: the check asserts that the `Reason:` label
is present and its text non-empty, and does **not** judge whether the reason is a
good one. Also asserted over active changes as well as archived ones, per the
delta, because this change's own first disclosure (at 12.3, if it happens) lands
in an active `tasks.md`.

The delegated blind spot the delta concedes — a task deleted outright rather than
disclosed — is covered only by the `AGENTS.md` assertions below, exactly as the
delta says.

### 4. The check cannot report success over a failed validation

**Covered, as a closed positive shape and never as a blocklist.**

| Test | Provenance |
|---|---|
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_validating_step_script_is_the_invocations_and_nothing_else` | SPECIFIED |
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_validating_step_declares_no_shell_override` | SPECIFIED |
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_job_enclosing_the_validating_step_declares_no_shell_default` | SPECIFIED |
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_workflow_declares_no_shell_default` | SPECIFIED |
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_validating_step_declares_no_continue_on_error` | SPECIFIED |
| `TestTheRecordValidationCannotReportSuccessOverAFailure.test_the_job_enclosing_the_validating_step_declares_no_continue_on_error` | SPECIFIED |
| `TestTheClosedFormIsARealReadOfTheScript.test_a_suppressed_invocation_is_rejected` | SPECIFIED |
| `TestTheClosedFormIsARealReadOfTheScript.test_a_line_that_is_not_the_validation_is_rejected` | SPECIFIED |
| `TestTheClosedFormIsARealReadOfTheScript.test_the_permitted_invocations_are_recognised` | DERIVED — converse half |
| `TestTheClosedFormIsARealReadOfTheScript.test_an_invocation_outside_the_pinned_install_tree_is_rejected` | SPECIFIED |

The shape is asserted positively and completely by `validating_invocation_flag`:
a script line must be an optional `npx`, then a command whose basename is
`openspec`, then `validate`, then exactly one of `--all` / `--archived`, and no
other token. Nothing is enumerated as forbidden, so `|| true`, `|| :`, `; true`,
a pipe, a redirection, a command substitution, a background `&`, an `if !` and
every construction nobody has thought of yet are rejected identically — by
contributing a token the permitted shape has no place for.

`continue-on-error` is asserted **absent as a key**, at both the step and the job
level, rather than asserted falsy: an expression-valued setting reads as a
harmless string statically and is true on the runner, and a step that cannot
suppress its failure inside a job that can is suppressible.

Relocating the invocations into a called workflow or composite action is
foreclosed by `test_the_required_check_validates_the_specification_record` (the
locator finds `run:` steps of this workflow, so a relocated invocation is simply
not found) and named directly by
`test_the_validation_is_invoked_by_a_run_step_rather_than_delegated`.

Accepted cost, per the delta and Decision 9: a legitimate future edit to that
step's script fails
`test_the_validating_step_script_is_the_invocations_and_nothing_else` until the
assertion is updated with it. That is the intended behaviour.

### 5. The validation runs regardless of what a pull request touched

**Covered.**

| Test | Provenance |
|---|---|
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_required_check_validates_the_specification_record` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_both_the_active_and_the_archived_record_are_validated` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_validating_step_is_unconditional` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_job_enclosing_the_validating_step_is_unconditional` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_workflow_carrying_the_validation_declares_no_path_filter` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_validation_runs_on_every_pull_request` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_validation_is_invoked_by_a_run_step_rather_than_delegated` | SPECIFIED |
| `TestTheSpecificationRecordIsValidatedByTheRequiredCheck.test_the_validating_step_runs_inside_a_registered_required_context` | SPECIFIED |

`if:` is asserted absent as a key rather than falsy, for the same reason as
`continue-on-error`. The path-filter assertion deliberately duplicates
`TestRequiredCheckIsNotPathFiltered`, which asserts the same property of the same
file for a *different* requirement: this requirement's obligation must not rest
on a test another requirement's change could legitimately retire. That class's own
docstring documents the same duplication pattern.

`test_the_validation_is_invoked_by_a_run_step_rather_than_delegated` is **green
today** over a workflow that has no such step at all — it is a prohibition, and a
prohibition passes vacuously until there is something to prohibit. It is listed
here so its greenness is not mistaken for coverage.

### 6. The validating tool is not resolved freshly at run time

**Covered.**

| Test | Provenance |
|---|---|
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_the_manifest_and_its_lockfile_are_committed` | SPECIFIED |
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_the_manifest_pins_the_tool_to_an_exact_version` | SPECIFIED |
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_the_lockfile_records_the_version_the_manifest_pins` | SPECIFIED |
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_the_workflow_installs_the_tool_with_a_lockfile_exact_install` | SPECIFIED, with one DERIVED element (see below) |
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_no_package_is_installed_by_a_resolving_command` | SPECIFIED |
| `TestTheValidatingToolIsInstalledFromAPinnedManifest.test_the_runtime_that_executes_the_tool_is_pinned` | SPECIFIED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_manifest_matcher_finds_the_scoped_package` | SPECIFIED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_lockfile_matcher_reads_a_scoped_install_path` | SPECIFIED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_lockfile_matcher_reads_a_nested_install_path` | DERIVED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_lockfile_matcher_reads_the_legacy_dependencies_block` | DERIVED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_lockfile_matcher_ignores_another_scopes_package_of_the_same_name` | DERIVED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_manifest_matcher_does_not_answer_to_the_binary_name` | DERIVED |
| `TestThePinMatchersReadTheScopedPackageName.test_the_lockfile_matcher_does_not_answer_to_the_binary_name` | DERIVED |
| `TestThePinMatchersReadTheScopedPackageName.test_an_npm_alias_is_not_an_exact_version` | DERIVED |

The "manifest and lockfile disagree" clause is asserted twice over: statically,
by comparing the manifest's pin against the lockfile's recorded version — so a
disagreement is a red test rather than a red pipeline — and by requiring the
install to be the lockfile-exact one, which is what enforces it at run time.

`test_no_package_is_installed_by_a_resolving_command` is written as a closed
shape too: every package-manager line anywhere in the required check must be the
lockfile-exact install, so `npm install`, `npm i`, `yarn add` and an inline
global pin are rejected together by not being it. It is **green today**
(the workflow runs no package manager at all) and only bites once section 9
lands.

### 7. The pin is watched by the dependency-update configuration

**Covered** by
`TestThePinIsWatchedByTheDependencyUpdateConfiguration.test_the_dependency_update_configuration_covers_the_manifests_directory`
(SPECIFIED) and, in the reverse direction, by
`…test_every_directory_holding_an_npm_manifest_is_watched` (DERIVED): every
directory holding a committed `package.json` must appear in an `npm` stanza, so
a second manifest added anywhere cannot go unwatched in silence. Both of this
stanza's neighbours — `terraform` and the Compose ecosystem — already carry that
converse; the `npm` one did not until the gate's review. The directory is computed from where the manifest actually is, so
moving the manifest moves the assertion with it. Membership is asserted, not an
exact ecosystem set, so `TestDependabotCoverage`'s existing entries are
unaffected.

## The `AGENTS.md` obligation

Not a scenario — it is a body clause of the requirement ("That convention SHALL
be stated in the repository-root `AGENTS.md`, and that it is stated there SHALL
itself be asserted by the suite").

| Test | Provenance |
|---|---|
| `TestTheArchivedRecordCorrectionRuleIsStated.test_the_conventions_file_states_the_correction_rule` | SPECIFIED |
| `TestTheArchivedRecordCorrectionRuleIsStated.test_the_correction_rule_requires_the_evidence_to_be_cited` | DERIVED |
| `TestTheArchivedRecordCorrectionRuleIsStated.test_the_correction_rule_is_stated_outside_the_generated_block` | DERIVED |

The delta requires the assertion to be "written so that rephrasing the rule fails
it, rather than so that a rephrasing which inverts the rule passes", so it
matches three literal fragments carrying the rule's polarity — `corrected only
to`, `what actually happened`, `never to change what was decided or built` —
after collapsing whitespace, so an eighty-column wrap does not break it. **A
rephrasing failing this test is the intended behaviour**, not friction: the
wording is what a reviewer relies on when adjudicating a deleted task, so a change
to it is a reviewed event.

Confirmed by fixture: an inverted rule ("including to change what was decided or
built") fails, and a rephrasing ("updated where it is inaccurate") fails.

The evidence-clause and outside-the-generated-block tests are DERIVED — the delta
states neither; they come from this change's `design.md` Decisions 2 and 4 and
its `tasks.md` 5.2. The second exists because a rule written inside the managed
`ai-toolkit:development-workflow` block would satisfy the first test today and
disappear silently on the next regeneration.

## Assertions deliberately untested

- **That a disclosure names the task it replaces.** The delta specifies the form
  but scopes the check explicitly: "the check SHALL assert that the label is
  present and its text non-empty, and SHALL NOT attempt to assess whether the
  reason is a good one". Naming cannot be checked without judging prose.
- **That the `Reason:` label sits on a line *following* the entry** rather than
  anywhere within it. The check asserts presence and non-emptiness, which is what
  the delta obliges it to assert; a positional assertion would add a failure mode
  the delta does not ask for.
- **That the reason is a good one.** Explicitly excluded by the delta. The remedy
  for a bad reason is review; the remedy for no reason is this check.
- **That a task deleted rather than disclosed is caught.** The delta concedes this
  openly — no static check can see a deleted line. It is delegated to the
  `AGENTS.md` rule, and what is asserted is that the rule is *stated*, never that
  it is followed.
- **The two other `AGENTS.md` rules `tasks.md` 5.2 writes** — that a change's
  `tasks.md` ends at the archive commit, and the `## Not performed` disclosure
  format itself. The delta obliges the suite to assert only the *correction*
  rule; asserting the other two would be scope this delta does not carry.
- **That `openspec validate` exits non-zero on a bad record.** Unreachable from
  this suite by design (Decision 5), and already the change's observed premise.
- **That a failed step becomes a failed required check.** GitHub's behaviour, not
  this repository's file content; observed manually at `tasks.md` 12.3.

## Obsolete tests

**Not applicable.** The change carries a single `ADDED` delta and no `MODIFIED`,
`REMOVED` or `RENAMED` operation, so no existing test asserts behaviour this
change supersedes, and there is nothing for an obsolete list to hold. No existing
test was edited, deleted or disabled.

## Unresolved project questions

Recorded rather than resolved silently: this pass ran as a dispatched subagent
with no channel to ask on.

1. **The `openspec` version to pin and the Node major version.** Neither is named
   in the artifacts — `tasks.md` 9.1 says "pin the version this change was
   verified against". *Assumption taken:* no test may depend on a literal value.
   The tests assert the *shape* of the pin (exact semver, manifest/lockfile
   agreement, an explicitly named Node version or a committed
   `node-version-file`), never a specific number. *Depends on it:*
   `test_the_manifest_pins_the_tool_to_an_exact_version`,
   `test_the_lockfile_records_the_version_the_manifest_pins`,
   `test_the_runtime_that_executes_the_tool_is_pinned`.
1a. **The tool's npm package name — assumed wrong, corrected during
   implementation.** These tests were written assuming the npm package and the
   binary it installs share a name, and carried one constant,
   `VALIDATING_TOOL = "openspec"`, for both roles. They do not share a name: the
   package is **`@fission-ai/openspec`** (1.12.0 at the time of writing) and the
   binary it puts on `PATH` is **`openspec`**. Nothing in this change's artifacts
   states either, and the assumption was never flagged because both assertions
   were red for the ordinary pre-implementation reason and so looked correct.

   The effect was worse than a red test: `manifest_pin(VALIDATING_TOOL, …)`
   required the literal key `openspec` in `dependencies`, which a *correct*
   manifest cannot carry — the assertion was unsatisfiable, and the only way to
   turn it green would have been to bend the manifest to it. That is a test
   dictating a fact about the world rather than reading one, and it is the same
   shape of defect as everything else this change exists to remove.

   *Fixed by splitting the constant, not renaming it:* `VALIDATING_PACKAGE` for
   the manifest, lockfile and Dependabot assertions; `VALIDATING_TOOL` for the
   script-shape assertion, where the binary name was right all along.
   `lockfile_versions` was checked at the same time — npm keys `packages` by
   install path, so the package appears as `node_modules/@fission-ai/openspec`,
   which the existing split on the last `node_modules/` already recovered
   correctly; it is now documented and covered rather than accidentally right.

   *The reconciliation refused:* an npm alias,
   `"openspec": "npm:@fission-ai/openspec@1.12.0"`, which would make the literal
   key the old assertion wanted appear. It bends the manifest to fit the test,
   and the alias string is not an exact version, so `EXACT_NPM_VERSION` fails on
   it. `test_an_npm_alias_is_not_an_exact_version` pins that refusal so it cannot
   be reintroduced quietly.

   *Depends on it:* every test in `TestThePinMatchersReadTheScopedPackageName`,
   plus `test_the_manifest_pins_the_tool_to_an_exact_version` and
   `test_the_lockfile_records_the_version_the_manifest_pins`.
2. **How the binary is invoked after a local `npm ci` in `.github/` — asked,
   answered, and the first answer was wrong.** These tests originally
   admitted `npx openspec validate --flag`, a bare `openspec validate --flag` off
   `PATH`, and a path form, on the stated belief that npx "resolves the locally
   installed binary that the lockfile-exact install places in
   `node_modules/.bin`". **That belief is false**, and this install is exactly the
   case where it fails: `npm ci` installs into `.github/node_modules`, npx
   searches `node_modules/.bin` *upward* from the working directory, and
   `.github` is a child of the repository root rather than an ancestor. Verified
   during the gate's implementation: with the install moved aside,
   `npx openspec validate --all` still exited 0 — from the npx cache. A runner has
   no cache, so the same line resolves off the registry at run time, which delta
   ¶12 forbids.

   The old permission was worse than a gap: a future edit "tidying" the path form
   back to `npx` would have kept every assertion green while CI resolved a fresh
   version, so the test would have licensed exactly what the requirement forbids.

   *Now:* the invocation must **resolve to** the binary the lockfile-exact
   install places — `.github/node_modules/.bin/openspec` — read from whatever
   directory the step runs in (its own `working-directory`, its job's default, or
   the workflow's). `npx`, a bare name off `PATH`, and a path into any other
   install tree are all rejected. *Depends on it:*
   `test_the_validating_step_script_is_the_invocations_and_nothing_else`,
   `test_both_the_active_and_the_archived_record_are_validated`, and both
   fixtures in `TestTheClosedFormIsARealReadOfTheScript`.
3. **That npm's lockfile-exact install is spelled `npm ci`.** The delta states
   the property; `design.md` Decision 7 states "a clean lockfile-exact install".
   *Assumption:* `npm ci`, with any flags after it, and it must target the
   manifest's directory via `working-directory` (step or job default) or
   `--prefix`/`-C`. *Depends on it:*
   `test_the_workflow_installs_the_tool_with_a_lockfile_exact_install`,
   `test_no_package_is_installed_by_a_resolving_command`.
4. **Whether the validating step may carry `working-directory:` or a YAML
   comment.** *Assumption:* yes to both — neither is part of the script and
   neither can suppress an exit status. Blank lines and whole-line `#` comments
   inside the `run:` block are skipped; a backslash continuation is not, because
   the trailing backslash is an extra token the shape rejects. *Depends on it:*
   `test_the_validating_step_script_is_the_invocations_and_nothing_else`.
5. **How this repository pins actions.** Observed convention, not a recorded rule:
   every `uses:` in `.github/workflows/` is a major-version tag (`@v7`, `@v4`).
   *Assumption:* the setup-node action must carry a reference that is not a
   mutable branch name; `@v6` passes, `@main` fails. *Depends on it:*
   `test_the_runtime_that_executes_the_tool_is_pinned`.
6. **How loosely the disclosure heading should be matched.** Neither the delta
   nor `tasks.md` says what happens to `## Not performed:` or
   `## Work not performed`. *Assumption taken:* a heading whose text **begins
   with** "not performed" opens the section; one that merely contains the phrase
   does not. The two failure directions are not symmetric — too strict fails
   open and silently, too loose fails a change that did nothing wrong and blocks
   every pull request until an archived record is edited — so the boundary was
   drawn where every heading in this repository's task lists is either an
   unnumbered `## Not performed…` or a numbered `## N. Title`. A project that
   later writes `## Work not performed` gets no offence and no coverage.
   *Depends on it:* `test_a_heading_with_trailing_punctuation_still_opens_the_section`,
   `test_a_heading_with_a_trailing_parenthetical_still_opens_the_section`,
   `test_a_numbered_section_merely_mentioning_the_phrase_is_not_a_disclosure`.
7. **"Committed" is asserted as "present on disk", and the two differ.**
   `test_the_manifest_and_its_lockfile_are_committed` reads the working tree, and
   nothing available to this suite can tell a tracked file from an untracked one:
   a tracked-file listing needs `git`, and the suite is specified to spawn
   nothing outside `bash`/`sh`. *Assumption taken:* the working tree stands in
   for the committed tree. *Consequence, in the safe direction:* an untracked
   `.github/package.json` passes locally and fails in continuous integration,
   where the file is simply absent — a real failure, correctly attributed, but
   discovered a step later than it could be. This is the "local tree masks CI
   gaps" hazard this project has recorded against itself before. *Depends on it:*
   `test_the_manifest_and_its_lockfile_are_committed`,
   `test_the_manifest_pins_the_tool_to_an_exact_version`,
   `test_the_lockfile_records_the_version_the_manifest_pins`.
8. **A standing gap in the suite, reported not fixed.** The suite's own
   constraint assertions (`test_the_suite_imports_only_the_standard_library_and_pinned_dependencies`,
   `test_the_suite_spawns_no_terraform_binary_or_container_runtime`,
   `test_the_suite_imports_no_network_capable_module`) read `Path(__file__)` and
   therefore cover `test_ci_configuration.py` alone. A second module added under
   `.github/tests/` would run in the required check while sitting outside all
   three. This pass appended rather than adding a module, so nothing here relies
   on the gap — but the gap is real, belongs to *The Continuous-Integration
   Configuration Is Itself Verified* rather than to this change, and is a
   candidate for `docs/change-queue.md`.

## How these tests are apportioned across the three pull requests

Per this change's `tasks.md` preamble. Both groups were authored here, before any
implementation; they are **committed** at different points, because
`.github/tests` is an unconditional required check and a gate assertion riding in
pull request 1 would fail against a workflow pull request 1 does not contain.
Neither group is ever skipped, marked expected-fail, or otherwise softened to
travel.

**The disclosure group — travels with pull request 1 (the settled records),
green there once sections 1–5 land:**

- `TestUnperformedWorkIsDisclosedWithAReason` (2 tests)
- `TestTheDisclosureCheckIsARealReadOfTheFile` (11 tests)
- `TestTheArchivedRecordCorrectionRuleIsStated` (3 tests)

**The gate group — travels with pull request 2 (the gate), red until section 9
lands:**

- `TestTheSpecificationRecordIsValidatedByTheRequiredCheck` (7 tests)
- `TestTheRecordValidationCannotReportSuccessOverAFailure` (4 tests)
- `TestTheClosedFormIsARealReadOfTheScript` (3 tests — matcher fixtures, green in
  both pull requests, since they read no repository file)
- `TestTheValidatingToolIsInstalledFromAPinnedManifest` (6 tests)
- `TestThePinIsWatchedByTheDependencyUpdateConfiguration` (1 test)

The module-level helpers this section adds are shared by both groups and must
travel with whichever commit goes first.

### How the split was actually carried out

Recorded here because the first attempt got it wrong in the way this section
exists to prevent. All 37 tests were initially committed together, which would
have put 21 red gate assertions into pull request 1 — a pull request that cannot
satisfy them, gated by an unconditional required check. The commit was undone
before it was pushed and the groups were separated.

The five gate classes sit contiguously between the shared helpers and the three
disclosure classes, so the split is a clean cut rather than an interleaving. The
gate block was held out of the tree and is restored in the commit that wires the
gate, immediately above `TestUnperformedWorkIsDisclosedWithAReason`, where it was
authored. Helpers travel with pull request 1; a few of them are unused until the
gate block returns, which is harmless and is the stated consequence of "travel
with whichever commit goes first".

**Verified after the split:** 209 tests, all passing — 193 pre-existing plus the
16 disclosure-group tests, whose subject pull request 1 implements. `discover`
and a direct `python3 .github/tests/test_ci_configuration.py` report the same
count, so the reachability property `cover-platform-images-with-dependabot`
established still holds after this append.

**Verified after the review fixes below:** **218** tests, all passing, by both
`discover` and a direct run — 193 pre-existing plus 25 disclosure-group tests.
The held-back gate block gains one test, taking the gate group to 22 and the
restored total to 240.

### Review findings folded in

The records pull request's code review raised four findings against the
disclosure scanner. Three were real and are fixed; all three fixes make the check
**stricter**, and each is now covered by fixtures that fail if the fix is
reverted.

1. **The heading matcher failed open.** An exact `## Not performed` match made
   `## Not performed:` and `## Not performed (two tasks)` invisible, and an exact
   heading with a prose disclosure yielded no entries — zero offences in both
   cases, with no checkbox left for `openspec validate --archived` either. Fixed
   by the loose begins-with match and by treating a section with no entries as an
   offence in its own right. Six fixtures, including two converse-half tests that
   keep the new rules from over-firing on the shape the settled records use.
2. **No fence awareness.** A `tasks.md` quoting the heading inside a fenced block
   opened the section for the rest of the file, turning every later top-level task
   into an entry owing a `Reason:` — an unsatisfiable red on a change that did
   nothing wrong. Fixed with a fence-state toggle in the line walk, plus a refusal
   where a fence is left open in a file that names the heading, which is the same
   fail-open reached from the other side. Three fixtures.
3. **`install_targets` passing a job name where a mapping is expected — not
   reproducible.** The finding reads `install_targets`' signature against
   `steps()`, which does yield the job *name*, but the helper's one call site
   resolves the mapping first: `install_targets(jobs(self.workflow)[job] or {},
   step)`. Verified by restoring the held-back gate block into a scratch copy and
   running `test_the_workflow_installs_the_tool_with_a_lockfile_exact_install`
   against three fixtures — a compliant one, a perturbed one, and one where the
   manifest directory is reachable **only** through the job-level
   `defaults.run.working-directory`, which is precisely the
   `job_defaults_working_directory(job)` path the finding says raises. Green, red,
   green; no `AttributeError` on any of them. The underlying asymmetry it points
   at is real, though — every other helper here takes the job name — so
   `job_defaults_working_directory` now refuses a non-mapping by name instead of
   raising a bare `AttributeError` from inside, and the held-back block gains
   `test_the_install_target_helper_takes_the_jobs_mapping_not_its_name`, pinning
   both halves. **The guard therefore travels untested in pull request 1 and
   tested in pull request 2**, because its only caller does.
4. **Stale docstring** on `TestTheDisclosureCheckIsARealReadOfTheFile`, fixed. The
   reasoning it records still holds and is now stated in a tense that survives:
   the repository-scoped test is green either way, and these fixtures are what
   separate "judged four well-formed disclosures" from "found nothing to judge".

## What the implementation must make pass

Nineteen tests were red at derive time and named exactly what was missing:

| Missing thing | Tests it turns green |
|---|---|
| The step in `pr-validation.yml`'s `validate` job, in its closed form | `TestTheSpecificationRecordIsValidatedByTheRequiredCheck` (6 of 7), `TestTheRecordValidationCannotReportSuccessOverAFailure` (4) |
| `.github/package.json` + its lockfile, a `npm ci` step, a pinned setup-node | `TestTheValidatingToolIsInstalledFromAPinnedManifest` (5 of 6) |
| The `npm` stanza in `.github/dependabot.yml` | `TestThePinIsWatchedByTheDependencyUpdateConfiguration` (1) |
| The correction rule in `AGENTS.md`'s project-conventions section | `TestTheArchivedRecordCorrectionRuleIsStated` (3) |

**All of them are now green.** With the gate implemented in the working tree, the
suite runs **255 tests, all passing**, by `discover` and by a direct
`python3 .github/tests/test_ci_configuration.py` alike. No test in this section
was softened to reach that state: the two manifest assertions were corrected to
read the package's real name (question 1a above) and were then confirmed to fail
against a manifest keyed on the binary name, against an npm alias, against a
range, and against a lockfile that disagrees with the manifest.

### The gate review's findings, folded in

The gate pull request's code review raised four gaps. All four made the checks
**weaker** than the delta requires; none was a case of a test being too strict,
and each fix was confirmed by the mutation that motivated it.

1. **`npx` was admitted, and it is the unsafe form.** See question 2 above, which
   is where the corrected assumption is recorded. Fixed by requiring the command
   to resolve to the pinned install tree. *Mutations confirmed red:* the run line
   tidied back to `npx openspec validate --all`, and reduced to a bare `openspec`
   off `PATH`.
2. **The closed form was not closed at the `defaults` levels for `shell:`.** The
   `continue-on-error` assertion already read both step and job; the shell
   assertion read the step alone. A `defaults: run: shell:` on the job — or at
   workflow level — applies to both validating steps, and a custom shell is an
   argv template with `{0}` substituted, so a wrapper of the shape
   `bash -c 'bash "$0"; exit 0'` runs the script and discards its status. That is
   the construction nobody listed, which is the whole reason the form is closed
   rather than blocklisted, and delta ¶24 requires the both-levels reading in so
   many words. *Mutations confirmed red:* that wrapper at the job level, and a
   `defaults.run.shell` at workflow level.
3. **Nothing bound the step to a *registered* required context.** The
   requirement's opening SHALL is "as part of the required pull request status
   check", and every assertion located the step by scanning all jobs and then read
   whichever job held it. Moving the steps into a new `spec-check` job left every
   gate assertion green while a pull request with the record validation red stayed
   mergeable — green-because-unregistered, the same defect as
   green-because-skipped. `REQUIRED_STATUS_CHECK_WORKFLOWS` was in the same module
   and never consulted; it is now. *Mutation confirmed red:* a second,
   unregistered `spec-check` job holding a validating step.
4. **The `npm` Dependabot stanza had no reverse coverage check.** Fixed as
   described under scenario 7. *Mutation confirmed red:* a second `package.json`
   added in a directory no stanza names.

### What the git history does and does not show

`test-plan.md` says nineteen assertions were red at derive time, and that is
true of the tree they were authored against — but **the history does not
witness it for the gate group**. Pull request 1 shipped the shared helpers and
constants together with the disclosure group, and the gate classes were held out
of it deliberately (see the apportionment above), so `origin/main` carries the
helpers and none of the six gate test classes. There is therefore no commit on
the trunk where a gate assertion is present and red.

That is a consequence of the apportionment, not a defect in it — a red gate
assertion in pull request 1 would have blocked a pull request that cannot satisfy
it — but it means the derive-then-implement ordering for the gate group rests on
this document and on the review record rather than on something a reader can
reconstruct from `git log`. Stated here so the claim is not read as more than it
is.

## Confirmation that these tests bite

Task 10.2 asks the implementer to confirm the derived tests fail against a broken
target rather than passing over an absent one. That confirmation was performed at
derive time, against synthetic repositories in a temporary directory — no
repository file was written — and every probe behaved as expected. A compliant
fixture is green; each of the following turns it red, and the failing test is
named:

`|| true` · `|| :` · `; true` · a captured status · `set +e` · a redirection ·
a `shell:` override · `continue-on-error: true` on the step · an
expression-valued `continue-on-error` on the step · `continue-on-error` on the
job · `if:` on the step · `if:` on the job · the `--archived` invocation dropped ·
the step removed · the invocations relocated into a composite action · a
workflow-level `paths:` filter · the manifest absent · the lockfile absent · a
range in the manifest · manifest and lockfile disagreeing · `npm install` in
place of `npm ci` · an install outside the manifest directory · setup-node
removed · `node-version: lts/*` · `actions/setup-node@main` · the `npm` stanza
dropped · a stripped `Reason:` label · an emptied `Reason:` label · the
correction rule deleted, rephrased, inverted, stripped of its evidence clause,
and moved inside the generated block.

The `|| :` and job-level `continue-on-error` probes are the ones a
blocklist-shaped test passes and a shape-shaped test catches. Both are red.

**The three review fixes were confirmed the same way**, by reverting each on a
scratch copy of the suite and running the fixture class against it. Each revert
fails exactly the two fixtures written for it, and the unmodified suite is green:

| Reverted | Fixtures that fail |
|---|---|
| the loose heading match | `test_a_heading_with_trailing_punctuation_still_opens_the_section`, `test_a_heading_with_a_trailing_parenthetical_still_opens_the_section` |
| the empty-section offence | `test_a_disclosure_written_as_prose_is_rejected`, `test_a_section_that_discloses_nothing_is_rejected` |
| fence awareness | `test_a_heading_quoted_inside_a_code_fence_opens_no_section`, `test_an_unterminated_fence_over_a_disclosure_heading_is_rejected` |

A fail-open fix that was itself untested would be the same defect one level up,
which is why each fix is listed here with the revert that reddens it.

**The package-name correction was confirmed the same way.** Reverting
`VALIDATING_PACKAGE` to the binary's name turns
`test_the_manifest_pins_the_tool_to_an_exact_version` and
`test_the_lockfile_records_the_version_the_manifest_pins` red against the
committed, correct manifest — the reported defect, reproduced and then closed —
plus the two fixtures written to hold the distinction. Re-keying
`lockfile_versions` on the bare basename reddens the two fixtures covering scope.
And against synthetic repositories carrying the scoped package, the following
each turn a compliant fixture red: a manifest keyed on the binary name, a
manifest using an npm alias, a lockfile keyed on the unscoped install path, a
lockfile disagreeing with the manifest, and a range in place of an exact version.
