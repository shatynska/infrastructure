# Test plan — correct-the-documents-against-the-tree

Written by the independent test-authoring step, before any of this change's implementation existed. It maps every scenario in the delta specification to the tests derived from it, records what each assertion traces to, and states what a green run will and will not establish. Nothing in this pass edited, deleted or disabled an existing test: **this pass adds tests and never subtracts.**

The tests live in one new module, `.github/tests/test_a_retired_requirement_name_is_reported.py`, per `tasks.md` 1.12. Run them with the third row of `AGENTS.md`'s testing table:

    python3 -m unittest discover --start-directory .github/tests

Each test below is named in the form that runner selects individually:

    python3 -m unittest test_a_retired_requirement_name_is_reported.<Class>.<test>

## Baseline

Full suite, taken before any file was written, at commit `9456de7` of the working tree `.claude/worktrees/correct-the-documents-against-the-tree`: `python3 -m unittest discover --start-directory .github/tests` — **927 tests, OK**. Nothing was failing beforehand.

After this pass, the same command runs 958 tests and reports 36 failures. Every one of them is in the new module and every one carries the same message: `test_the_retired_requirement_names_are_gone` does not exist. That is the absent-target state — the assertions never executed, so nothing about the check's behaviour has yet been established — and it is the expected state per `AGENTS.md`'s independent-test-authoring step and this change's `tasks.md` 1.12. The failure count exceeds the number of test methods because four tests use `subTest`. No pre-existing test changed state.

Two of the module's 31 test methods pass on this run: `TestARetiredNameSurvivingInsideALongerLiveNameIsNotReported.test_the_fixture_pair_really_is_a_prefix` and `TestANameWrappedAcrossACommentsLineBreakIsRead.test_the_fixture_fragments_are_the_name_split`. A pass before the implementation exists is normally an alarm; these two are not, and the distinction is recorded rather than assumed: neither touches the absent module. Each asserts a property of this file's **own fixtures** — that the prefix pair really stands in a prefix relation, and that the two wrapped fragments really join into the name — which is a premise every other assertion in its class rests on and which would otherwise fail silently by ceasing to exercise anything.

## Which situation these tests are in

All of them are the third situation in `ai-toolkit:testing`'s sense: the assertion does not execute the behaviour it asserts — the subject is a static read of committed text. That is why every test here is a **fixture-driven discriminator** by construction. Each hands the finder a corpus the test itself supplies, built to falsify it, and each positive case has a negative counterpart so that neither a finder reporting nothing nor a finder reporting everything can satisfy the class. No test in this module reads a file from disk.

The obligation is therefore discharged in this pass rather than deferred: the fixtures are written beside checks that are still red and do not wait for them to go green.

## Scenario accounting

The delta specification carries nine `#### Scenario:` blocks: the five this change adds, and four it carries through unchanged. All nine are accounted for.

### Scenarios this change adds

| Scenario | Tests |
|---|---|
| A pull request naming a retired requirement is rejected | `TestAPullRequestNamingARetiredRequirementIsRejected.test_a_swept_file_naming_a_retired_requirement_is_reported`, `.test_the_line_reported_is_the_line_the_name_is_on`, `.test_every_occurrence_is_reported_rather_than_the_first`, `.test_a_corpus_naming_no_retired_requirement_reports_nothing`, `.test_a_file_inside_openspec_is_not_reported`, `.test_a_path_merely_resembling_an_exempt_one_is_still_swept` |
| … its **AND** clause, the replacement the report names | `TestTheReportNamesWhatTheRequirementIsCalledNow.test_a_recorded_replacement_a_specification_holds_is_offered`, `.test_a_chained_replacement_resolves_to_the_first_live_name`, `.test_a_chain_reaching_no_live_name_offers_none`, `.test_a_removed_block_recording_no_replacement_offers_none`, `.test_a_name_a_later_change_reintroduced_is_not_retired`, `.test_a_name_an_archived_delta_added_rather_than_removed_is_not_retired`, `.test_a_change_still_in_flight_retires_nothing`, `.test_a_corpus_holding_no_archived_removal_derives_nothing` |
| A retired name surviving inside a longer live name is not reported | `TestARetiredNameSurvivingInsideALongerLiveNameIsNotReported.test_the_fixture_pair_really_is_a_prefix`, `.test_a_citation_of_the_longer_live_name_is_not_reported`, `.test_the_longer_live_name_wrapped_across_lines_is_not_reported`, `.test_the_retired_name_standing_alone_is_still_reported`, `.test_a_bare_retired_name_beside_a_live_citation_is_reported` |
| A name wrapped across a comment's line break is read | `TestANameWrappedAcrossACommentsLineBreakIsRead.test_the_fixture_fragments_are_the_name_split`, `.test_a_name_split_across_two_comment_lines_is_reported`, `.test_the_line_reported_is_the_line_the_name_starts_on`, `.test_each_rendering_the_tree_wraps_a_name_in_is_read`, `.test_fragments_separated_by_other_text_are_not_joined_into_a_name` |
| An exemption that no longer excuses anything fails the check | `TestAnExemptionThatNoLongerExcusesAnythingFailsTheCheck.test_an_exemption_over_a_file_naming_no_retired_requirement_is_reported`, `.test_an_exemption_over_a_file_still_naming_one_is_not_reported`, `.test_an_exemption_over_a_file_naming_one_across_a_line_break_is_not_reported` |
| The test suite's own citations are read | `TestTheTestSuitesOwnCitationsAreRead.test_a_suite_modules_own_citation_is_reported`, `.test_the_one_module_that_must_name_them_is_exempt`, `.test_this_module_is_swept_like_any_other_file`, `.test_a_sibling_suite_module_is_not_exempt_by_the_directory` |

### Scenarios the delta carries through unchanged

The delta is strictly additive. Compared line by line against the requirement as `openspec/specs/iac-repo-foundations/spec.md` currently holds it, every existing paragraph and every existing scenario survives verbatim; the delta only adds three paragraphs and five scenarios. These four are therefore **uncovered by this pass, with the reason that this change states no new behaviour for them** — each is already asserted, over the committed tree, by tests this pass must not touch:

| Scenario | Why uncovered here | Already asserted by |
|---|---|---|
| A pull request reintroducing the pre-archive citation form is rejected | Unchanged by this delta | `test_ci_configuration.TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation`, `…TestThePreArchiveCitationCheckIsARealReadOfTheTree`, `…TestThePreArchiveCitationCheckGatesEveryPullRequest` |
| Archiving a change breaks no citation | Unchanged by this delta; it is a property of the two citation forms rather than an executable read | the same classes, for the prohibition half |
| A requirement is cited at its permanent location | Unchanged by this delta | the same classes |
| A change's own artifacts are out of scope | Unchanged by this delta | `…TestThePreArchiveCitationCheckIsARealReadOfTheTree`, which exercises the exemption against a fixture tree |

## Assertion classification

Every test in the new module carries its own `SPECIFIED` or `DERIVED` label in its docstring, with the scenario text or the design/task it traces to. In summary:

**SPECIFIED** — traces to scenario or SHALL text: that an offence names the file, the line and the retired name; that a file inside `openspec/` is out of scope; that the replacement offered is one a specification currently holds, resolved through the chain where the recorded replacement is itself retired; that no replacement is offered where the chain reaches no live name or none is recorded; that a name a later change reintroduced is not retired; that a citation of the longer live name is not reported while the bare retired name still is; that a name wrapped across a comment's line break, in each rendering the tree uses, is read as the one name it is; that an exemption over a file no longer naming a retired requirement is reported and one over a file still naming it is not; that the suite's own modules are read and exactly one of them is exempt.

**DERIVED** — traces to `design.md` or `tasks.md`, or is a discriminator no scenario states:

- every occurrence reported rather than the first (`tasks.md` 2.6–2.11 work from the finder's own output)
- a clean corpus reports nothing; a corpus with no archived removal derives nothing (without these, a finder or a derivation that returned a fixed answer would satisfy every positive case)
- a path merely resembling an exempt one is still swept
- a name an archived delta **added** rather than removed is not retired, and a change still in flight retires nothing (design decision 1 reads `REMOVED` blocks in the **archive**)
- the prefix suppression runs over the flattened text (`tasks.md` 1.4), and is per occurrence rather than per file
- fragments separated by other text are not joined into a name that no file states
- an exemption over a file that names a retired requirement only across a line break is not reported as idle — the conjunction of the exemption scenario with the wrapping scenario
- the two fixture-premise tests described under *Baseline*

**Deliberately untested**, recorded with the reason rather than dropped:

- **That the reader's failure message carries the replacement.** The scenario's AND clause says "the report SHALL name what the requirement is called now". This pass asserts which name is offered, through `retirements()`; composing it into the message is the implementing module's own (`tasks.md` 1.5) and cannot be exercised from a fixture without inventing a second interface for the message.
- **An exemption naming a path the repository no longer tracks.** The sibling sweep asserts it and the implementing module will too; it is a property of the real listing rather than of the scenario, which turns on the file no longer containing a retired name.
- **A retired name occurring inside a live name other than as a prefix** (as a suffix, or mid-string). The scenario states the prefix case, which is the one the archive actually contains, and design decision 2 argues explicitly against widening the predicate.
- **The truncated citation design decision 2 discloses** (`test_terraform_stacks_are_the_iterated_unit.py:2951`). The design states that no predicate here catches it and that `tasks.md` 2.7 corrects it by hand; writing a test for it would assert behaviour the design declines.
- **Everything over the committed tree**: that the sweep's anchors are reached, that the derived retired set over the real archive is non-empty and holds the name decision 3 pins, and that the check is wired into the required status check. Those are `tasks.md` 1.9–1.11 in the implementing module, which reads `tracked_files()`; this module reads no file on disk by design.

## The interface this pass assumes

The check module does not exist yet, so the names below are assumptions this pass took, not facts it read. They are recorded here so the implementation is written **to** them rather than around them. Each is fetched lazily by `check_symbol()`, so a run before the implementation exists fails naming the absent target instead of erroring at import — and so that `test_ci_configuration.TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`, which admits a sibling import only where the directory already holds that sibling, stays green over a file it has no quarrel with.

- `retirements(files) -> dict[str, str | None]` — every name retired by a `## REMOVED Requirements` block in an archived delta, less every name a specification currently holds, mapped to the first live name in the recorded replacement chain, or `None`.
- `retired_name_offences(files, names=…, live=…) -> list[str]` — entries `"<path>:<line>: <name>"`, one per occurrence, matched over the flattened rendering, suppressing an occurrence that opens a longer name in `live`. Called by keyword in every test.
- `idle_exemptions(files, names=…, paths=…) -> list[str]` — one message per whole-path exemption whose file no longer contains any of `names`, naming that exemption.

The entry format `"<path>:<line>: <name>"` is `tasks.md` 1.3's, not a scenario's. The three functions take their file set as an argument, which `tasks.md` 1.1 requires ("a pure offence-finder plus a thin reader"); the parameter names and the split into three functions are this pass's, chosen so each scenario is exercisable against a fixture rather than against the real tree.

**Where a test's expectation and the implementation's shape disagree, the disagreement is a finding to report, not a test to weaken.** A specified assertion that does not match means the implementation is wrong. Only the derived ones above may be reconsidered, and reconsidering one is recorded as a change to a derived assertion.

## Why the fixtures name requirements this repository does not have

Every requirement name in the new module — retired, live, chained and prefixed — is invented and structurally identical to the case `design.md` records rather than equal to it. The check reads `.github/tests/` and exempts exactly one module, which is not this one: a fixture naming a genuinely retired requirement would make this file an offence against the check it asserts, and would have to be answered with an exemption that design decision 5 spends a page arguing against. It also keeps the fixtures stable across the next rename. `TestTheTestSuitesOwnCitationsAreRead.test_this_module_is_swept_like_any_other_file` pins that this module stays swept.

## Obsolete tests

**Candidates for human confirmation. Nothing in this list was edited, deleted or disabled by this pass.**

The delta is strictly additive — the line-by-line comparison above found no paragraph and no scenario of the standing requirement superseded — so **no existing test asserts behaviour this change retires.** One entry stands all the same, for a different reason: a committed literal it asserts moves in the same commit as the sweep.

| Test | Superseded by | Evidence |
|---|---|---|
| `test_terraform_stacks_are_the_iterated_unit.TestTheStackDirectoryReadsDiscriminate.test_the_widened_needles_stay_silent_on_the_real_keeper_prose` | Not by a delta scenario, but by the sweep the delta's new obligation compels — `tasks.md` 2.2 and 2.3 | Its class constant `REAL_KEEPER_PROSE` (around line 2944) is documented as "Verbatim from the two `pipeline.yml` files and the two `versions.tf` files as they stand at HEAD". Two of its entries carry retired requirement names: `'# discovery step -- see "Each Environment Declares Its Own Pipeline'` at line 2951 and `"#     nothing in prod's (see the Each Environment Has a Dedicated Hetzner"` at line 2953. `tasks.md` 2.3 already owns the second ("the literal that asserts the `versions.tf` comment of 2.2, which moves in the same commit") and `tasks.md` 2.7 the first. |

What the candidate asks of the implementer is narrow: **move the literal, do not delete the test.** Its assertion — that the over-sweep needles stay silent on correct committed prose — is unaffected by this change and still holds; what expires is the fixture's claim to reproduce HEAD.

The rest of the 38 per-line occurrences of a retired requirement name under `.github/tests/*.py` — in `test_a_second_environment.py`, `test_environment_agnostic_pipeline.py`, `test_host_configuration_names_its_environment.py`, `test_host_converge_workflow.py`, and the seven prose occurrences in `test_terraform_stacks_are_the_iterated_unit.py` — were read and are **not** obsolete-test candidates. Every one is a section banner or a docstring stating which requirement an assertion traces to, so correcting it changes no assertion. That agrees with design decision 5's own measurement ("None is a fixture") and is stated here as a separate finding rather than inherited from it.

### What this search covered, and what it did not

Bounded to the dispatched test-path glob `.github/tests/*.py`, searched by the four retired names `tasks.md` section 2 names plus the three the design records as unswept. No earlier `test-plan.md` was available to this pass as a scenario-to-test map, so the search rests on that predicate alone. Two consequences worth stating rather than leaving to be inferred:

- The per-line search does not see a name wrapped across lines, which is the very blind spot this change exists to close — it found 38 occurrences where `design.md` measures 47. Any bearing test whose literal states a name only across a line break would have been missed. None of the 38 found is a literal except the one entry above, so the residual risk is small but not zero.
- Tests outside `.github/tests/*.py` were not searched. `terraform test` and Molecule are the other two rows of `AGENTS.md`'s testing table, and neither asserts a requirement name in prose; but this pass did not read them, and "none was found by this search" is not the same as "none exists".

## Unresolved project questions

Each was raised by this pass, is not answered by `AGENTS.md` or `CLAUDE.md`, and could not be asked — a dispatched test-authoring pass has no channel. The assumption taken and the tests that depend on it are recorded so the answer can be supplied rather than discovered.

1. **The check module's interface.** No convention records it, and the module does not exist. *Assumption*: the three functions above, in the idiom of `test_the_external_service_names_are_retired.py`, called by keyword. *Depends on it*: every test in the new module.
2. **Whether the new test module is itself exempt from the sweep.** `tasks.md` 1.6 names one exemption, the check module; it does not say what becomes of the module testing it. *Assumption*: it is **not** exempt, read straight off the scenario's "exempted only for the one module that must name a retired requirement", and the fixtures are invented so that being swept costs nothing. *Depends on it*: `TestTheTestSuitesOwnCitationsAreRead.test_this_module_is_swept_like_any_other_file`.
3. **The exact renderings the flattening must read.** The scenario says "each line carrying the comment marker and its indentation"; design decision 2 says leading whitespace and a leading comment marker are stripped and runs of whitespace collapsed, without enumerating markers. *Assumption*: the two renderings the tree actually carries — a `#` comment in YAML/Terraform/`.cfg`, and the bare indentation of a Python docstring — plus unmarked Markdown prose. *Depends on it*: `TestANameWrappedAcrossACommentsLineBreakIsRead.test_each_rendering_the_tree_wraps_a_name_in_is_read`.
4. **Whether the idle-exemption check reads its file flattened.** The scenario says "no longer contains any retired requirement name" without saying how "contains" is read. *Assumption*: flattened, the same way the sweep reads it, because a per-line read would retire an exemption the file still needs. *Depends on it*: `TestAnExemptionThatNoLongerExcusesAnythingFailsTheCheck.test_an_exemption_over_a_file_naming_one_across_a_line_break_is_not_reported`, labelled DERIVED.
5. **No stack skill for this runner.** `ai-toolkit:testing` was loaded and `python` alongside it, but `python`'s testing material is `pytest`-shaped while this suite is `unittest` and the library carries no `unittest` skill. *Assumption*: the project's own convention governs — `AGENTS.md`'s testing table, and the idiom of the eighteen modules already in `.github/tests`. The floor's rules were applied unchanged.

## A note on where this file is read

`test-plan.md` is not an artifact the OpenSpec schema knows about. It will **not** appear among the context files `openspec instructions apply` lists, and must be read on purpose before implementing.
