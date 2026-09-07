# Test plan — decide-archived-change-reference-policy

Derived from this change's delta spec (`specs/iac-repo-foundations/spec.md`,
requirement *Source Files Cite Specifications by Path and Changes by Name*)
before any implementation of the change existed, by an author who has read the
change's artifacts and the specifications under `openspec/specs/` and has not
read any implementation of the behaviour under test.

**This file is not an artifact the OpenSpec schema knows about.** It does not
appear among the context files `openspec instructions apply` lists, and has to
be read on purpose before implementing.

## Where the tests are

All of them are in `.github/tests/test_ci_configuration.py`, appended as a new
section (`iac-repo-foundations / Source Files Cite Specifications by Path and
Changes by Name`) immediately before the file's `if __name__ == "__main__":`
guard. Nothing already in that file was edited, deleted or disabled: the diff is
511 insertions and 0 deletions.

Test command, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

A single test, individually selectable, run from `.github/tests`:

    python3 -m unittest test_ci_configuration.<Class>.<method>

## Baseline

**Full baseline, taken before any test was written**, at the working tree's
current state:

    $ python3 -m unittest discover --start-directory .github/tests
    Ran 89 tests in 0.493s
    OK

No pre-existing failure. Every failure recorded below is therefore attributable
to this pass.

**After the tests were written**, same command:

    Ran 111 tests in 0.554s
    FAILED (failures=1)

    FAIL: test_no_committed_file_outside_openspec_carries_a_pre_archive_citation
    AssertionError: Lists differ: [] != ['README.md:6: openspec/changes/bootstrap-…']
    Second list contains 75 additional elements.

The one failure is the state the specification names: the tree still carries the
pre-archive citation form. It is **not** an import failure, a collection error,
or an absent-target failure — the check executed, walked the tree, and reported
each offending file, line and citation. The other 21 new tests pass, which is
what makes that single failure readable: the matcher, the walk, the prune list
and the reporting format are all exercised against fixtures and are green.

**75 offences across 44 files** — the count and the per-file distribution
reproduce design.md's measurement table exactly, which is independent evidence
that the matcher keys on the same thing the design measured.

An earlier run of this pass reported a 76th offence, in
`.github/tests/__pycache__/test_ci_configuration.cpython-312.pyc`: the compiled
copy of this suite's own module docstring, written by the run itself. That was
raised as an open question, accepted as a defect in design Decision 7 rather
than left open, and the artifacts were revised — `__pycache__` is now pruned
wherever it occurs. The check no longer reads compiled bytecode, and the count
is 75, not 76. The reasoning, now recorded in design Decision 7: `.gitignore`
ignores `__pycache__/`, so a compiled module is not a committed file and the
requirement does not reach it; and running the suite is what creates it, so it
is a false positive the check would inflict on itself every run rather than one
a developer provokes and can see — which is what separates it from the untracked
scratch file Decision 7 deliberately accepts.

## Scenario coverage

Four `#### Scenario:` blocks in the delta spec; four accounted for.

### Scenario: A pull request reintroducing the pre-archive citation form is rejected

Covered. The scenario has two halves — the citation is detected, and the
required status check fails on it — and both are covered.

| Test | Class |
|---|---|
| `test_a_citation_naming_an_artifact_inside_a_change_is_flagged` | `TestThePreArchiveCitationCheckIsARealReadOfTheTree` |
| `test_a_citation_that_names_the_change_and_stops_is_flagged` | same |
| `test_a_wrapped_citation_naming_a_further_component_is_flagged` | same |
| `test_a_wrapped_citation_that_names_the_change_and_stops_is_flagged` | same |
| `test_an_offence_names_the_file_the_line_and_the_citation` | same |
| `test_the_citation_check_lives_in_the_suite_the_required_check_invokes` | `TestThePreArchiveCitationCheckGatesEveryPullRequest` |

The "SHALL fail on that pull request" half rests additionally on two tests that
already exist and are not duplicated here:
`TestTheSuiteIsWiredIntoTheRequiredCheck.test_the_step_invoking_the_suite_is_unconditional`
and `…test_the_step_invoking_the_suite_does_not_swallow_its_result`.

### Scenario: Archiving a change breaks no citation

Covered by
`TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation.test_no_committed_file_outside_openspec_carries_a_pre_archive_citation`
— the assertion the sweep must turn green. Guarded against a vacuous pass by
`test_the_walk_reaches_the_committed_files_the_prohibition_covers`,
`test_the_walk_reaches_the_tracked_files_under_the_agent_directory` and, over
fixtures, `test_the_pruned_directories_are_not_read`,
`test_compiled_bytecode_beneath_a_pycache_directory_is_not_read` and
`test_a_file_outside_the_pruned_directories_is_still_read`.

Scope note: the test covers the class of citation the requirement names — a path
naming a change's own directory. A citation invalidated by the archive move in
some other rendering (obfuscated beyond a single line break) is outside the text
match, as the requirement itself states.

### Scenario: A requirement is cited at its permanent location

Covered in the direction a static check can establish:

| Test | What it establishes |
|---|---|
| `test_a_citation_of_a_delta_specification_inside_a_change_is_flagged` | the delta-spec path inside a change is rejected |
| `test_a_requirement_cited_at_its_permanent_location_is_not_flagged` | `openspec/specs/<capability>/spec.md` is accepted |

The scenario's second clause — "and the requirement's own name" — is
**deliberately untested**; see below.

### Scenario: A change's own artifacts are out of scope

Covered by
`TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation.test_the_walk_reads_nothing_inside_the_specification_directory`,
made non-vacuous by `test_a_changes_own_artifacts_do_carry_the_form_the_walk_excludes`
(archived artifacts under `openspec/` really do carry the form, so excluding the
directory is doing work) and, over a fixture, by
`test_the_pruned_directories_are_not_read`.

## Assertion classification

**SPECIFIED** — traces to SHALL text or to a scenario in the delta spec:

- `test_no_committed_file_outside_openspec_carries_a_pre_archive_citation`
- `test_the_walk_reads_nothing_inside_the_specification_directory`
- `test_a_citation_naming_an_artifact_inside_a_change_is_flagged`
- `test_a_citation_that_names_the_change_and_stops_is_flagged`
- `test_a_citation_of_a_delta_specification_inside_a_change_is_flagged`
- `test_a_wrapped_citation_naming_a_further_component_is_flagged`
- `test_a_wrapped_citation_that_names_the_change_and_stops_is_flagged`
- `test_an_offence_names_the_file_the_line_and_the_citation`
- `test_the_archived_location_is_not_flagged`
- `test_a_requirement_cited_at_its_permanent_location_is_not_flagged`
- `test_prose_ending_in_the_prefix_before_an_ordinary_word_is_not_flagged`
- `test_a_wrapped_single_word_change_name_is_knowingly_not_flagged`
- `test_the_citation_check_lives_in_the_suite_the_required_check_invokes`

One of those, `test_a_wrapped_single_word_change_name_is_knowingly_not_flagged`,
is unusual and is flagged for a reviewer: it asserts a gap the requirement
**records** rather than a behaviour it wants ("one rendering lies outside it").
It is written so that a later change closing the gap does so knowingly, and sees
at the same time that it must keep
`test_prose_ending_in_the_prefix_before_an_ordinary_word_is_not_flagged` green.

**DERIVED** — inferred by this author, or traced to `design.md`/`tasks.md`
rather than to a scenario. Each is a constraint no scenario states:

| Test | What it rests on |
|---|---|
| `test_the_walk_reaches_the_committed_files_the_prohibition_covers` | anchors on four specific committed paths; non-vacuity guard |
| `test_the_walk_reaches_the_tracked_files_under_the_agent_directory` | design Decision 7's insistence that `.claude` is pruned only at `worktrees`. Enumerates the directory and compares, rather than counting, and requires both `commands/` and `skills/` to be represented, so a prune-list edit fails it while a file the OpenSpec CLI adds or removes does not |
| `test_a_changes_own_artifacts_do_carry_the_form_the_walk_excludes` | non-vacuity guard on the `openspec/` exclusion |
| `test_a_metasyntactic_placeholder_is_not_flagged` | design Decision 5; no scenario states it |
| `test_a_tree_carrying_no_such_citation_yields_no_offence` | converse half; without it a check flagging everything would pass |
| `test_a_tree_the_walk_finds_nothing_in_fails_rather_than_reading_nothing` | non-vacuity at tree level, following this suite's existing convention |
| `test_the_pruned_directories_are_not_read` | design Decision 7's prune list |
| `test_compiled_bytecode_beneath_a_pycache_directory_is_not_read` | design Decision 7 as revised, and task 3.4's added case |
| `test_a_file_outside_the_pruned_directories_is_still_read` | converse of the two above |

Also DERIVED, and recorded because it is an interface decision an implementer
inherits rather than chooses: an offence is reported as
`<path>:<line>: <matched text>`, and the matched text is the prefix plus the
change-name segment — **not** the whole citation including any trailing path
component, because the requirement forbids requiring anything after the segment.
The file and line locate the rest.

**DELIBERATELY UNTESTED** — identified and left uncovered, with the reason:

- **"…and the requirement's own name"** (scenario *A requirement is cited at its
  permanent location*). A static text match cannot establish that a cited
  requirement name is the requirement's actual name without resolving it into
  `openspec/specs/<capability>/spec.md` and matching prose near the path — a
  heuristic with false positives in both directions. Left to human review.
- **That a cited `openspec/specs/<capability>/spec.md` path resolves to an
  existing file.** Tempting, and deliberately not asserted: the requirement
  explicitly accepts an interval in which it does not resolve — where a change
  introduces a **new** capability, archiving is what creates that file. A test
  asserting resolution would fail during exactly the interval the requirement
  accepts.
- **That `AGENTS.md` carries the rule** (proposal's second bullet, design
  Decision 2, task 1.1). No scenario obliges it — the requirement's enforcement
  clause names the executable suite, not the conventions file — and any
  assertion strong enough to be worth writing would key on wording an
  implementer has not chosen yet. Left to `build`'s review against tasks 1.1
  and 1.2.
- **That the check catches a citation obfuscated beyond a single line break.**
  The requirement scopes itself to a static text match and says so.

## Obsolete tests

**Not applicable.** This change's only delta operation is `ADDED`: one new
requirement, no `MODIFIED`, `REMOVED` or `RENAMED` delta. Nothing in the existing
suite is superseded, so there is no candidate for deletion or rewrite, and no
search was performed. For the record: the pass added tests and subtracted
nothing — 511 insertions, 0 deletions, no existing test edited, disabled or
weakened.

## Unresolved project questions

Recorded rather than resolved silently. Each names the assumption taken and the
tests that depend on it.

1. **The comment markers a wrapped citation may open its continuation line
   with.** The requirement says "a leading comment marker and whitespace"
   without enumerating markers. *Assumption taken:* `#`, `>`, `*`, `//`, `--`,
   or none — covering YAML, Python, Markdown prose and Markdown quoting, which
   is every file type in the swept set. *Depends on it:*
   `test_a_wrapped_citation_naming_a_further_component_is_flagged` and
   `test_a_wrapped_citation_that_names_the_change_and_stops_is_flagged`.

Two questions this pass raised have since been settled and are recorded here so
the reasoning is not lost with the conversation:

- **`__pycache__` in the prune list** — accepted as a defect in design
  Decision 7, artifacts revised, prune entry and fixture case added. See the
  baseline section above.
- **Where a test-derivation pass ends and implementation begins for a change
  whose subject is the test suite** — settled: the check *is* the assertion the
  requirement calls for, there is no separate implementation of it, and the code
  under test is the repository's citations, which section 4 of `tasks.md`
  changes and section 3 does not touch. Tasks 3.1–3.4 are delivered by this
  pass; verify them rather than re-authoring them.

## Status after the sweep

The baseline above records the tree as it stood when the tests were derived, and
is left unedited: it is what makes the failure attributable. What has happened
since, recorded separately rather than merged into it:

- Task 4's sweep landed. The suite now runs **111 tests, all passing** — the red
  assertion went green by the citations changing, which is the only way it could.
- `test_the_walk_reaches_the_tracked_files_under_the_agent_directory` was
  strengthened after `build`'s code review found it passed on reaching a single
  file under `.claude/`. It now enumerates the directory and compares, and
  requires both `commands/` and `skills/` to be represented. Verified to
  discriminate: with `.claude/skills` added to `PRUNED_AT_ROOT_RELATIVE` in
  memory it fails, with `.claude` pruned wholesale it fails, and unmodified it
  passes. The repository was not mutated to establish that.

## What the implementation must make pass

`python3 -m unittest discover --start-directory .github/tests` from the
repository root, with all 111 tests green. One was red when this plan was
written, and is the assertion the sweep exists to satisfy (see *Status after
the sweep* above for where it now stands):

    python3 -m unittest test_ci_configuration\
      .TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation\
      .test_no_committed_file_outside_openspec_carries_a_pre_archive_citation

It goes green when task 4's sweep converts all 75 citations across 44 files,
including this suite's own three.
