# Test plan — `write-and-rehearse-the-rebuild-runbook`

Derived from this change's delta specification for `iac-server-lifecycle` — one ADDED requirement, *A Host's Rebuild Procedure Is Recorded, and Its Rehearsal State With It* — by an author other than whoever writes `docs/runbook-rebuild.md`, and before that document exists. Nothing below was derived from implementation code; there is none to read.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files and must be opened on purpose by whoever implements next.

**The module this pass wrote:** `.github/tests/test_the_rebuild_runbook_records_its_rehearsal.py`. Nothing else was written, edited or deleted. No existing test was touched, and `docs/runbook-rebuild.md` was not created.

## Count of assertions derived

Task 5.1 reads this figure.

| | |
|---|---|
| Test methods added | **71** |
| Suite count before | 1475 |
| Suite count after | **1546** |

Of the 71: **7** guard assertions (the "read at all" class), **13** property assertions over committed files, **51** fixture-driven detector-fires cases. Individually selectable by `python3 -m unittest test_the_rebuild_runbook_records_its_rehearsal.<Class>.<method>` from the repository root.

The figure that matters to task 5.1 is the whole 71: every one of them is a test `unittest` counts, so the suite's reported total rises by exactly that. It is not 13; a check on "count exceeds the baseline by the number of assertions derived" reading 13 would pass a module that had lost 58 of its tests.

## Baseline

Measured in this working tree on 2026-09-16, at `8d6e536`, before this module existed — the module was moved out of the directory and the whole suite run:

    python3 -m unittest discover --start-directory .github/tests
    Ran 1475 tests in 32.698s — OK

A **full** baseline, not a scoped one. It agrees with the figure `design.md` records at the merge base `d0b27f5`, which is expected: the only commit between them writes this change's planning artifacts, which no test reads.

**After this module:** 1546 tests, 18 failures, all 18 in this module. Every other module stays green, and every one of the 51 detector-fires cases passes.

## What each failing test currently establishes

All 18 failures are in the **target-absent** state: they establish that `docs/runbook-rebuild.md` does not exist, that Appendix B still carries the sequence, and that Appendix A still records no settings for the per-stack Alertmanager checks. They establish nothing yet about whether the assertions are any good.

**That is the expected outcome and is not a defect to repair by creating the document from this module.** The 51 detector-fires cases are what establishes, today, that each matcher discriminates — each runs its detector over material the test itself supplies, one string that must match and one that must not.

One test defect was found and corrected inside this pass: a detector-fires case asserted the destroy marker sat at line 10 of its own fixture when it sits at line 8. That was a miscount in the fixture's expected value, not a property of the code under test; the corrected case now also asserts that line 8 is *not* among the fixture's unfenced lines, which is the property it exists for.

## Scenario-by-scenario account

The delta carries **ten** `#### Scenario:` blocks, not the eight the dispatch named. All ten are accounted for below.

| # | Scenario | Covered by | Status |
|---|---|---|---|
| 1 | A host has to be rebuilt | `TestTheRunbookGivesTheStepsInTheOrderTheyArePerformed`, `TestEveryPhaseNamesTheCredentialItNeeds` (both methods), `TestEveryStepPerformedElsewhereIsWrittenAsAStep` | covered |
| 2 | The procedure is also described somewhere else | `TestTheSequenceHasExactlyOneHome.test_appendix_b_names_the_runbook_and_restates_no_sequence` | covered |
| 3 | A rehearsal is performed | `TestTheRehearsalRecordIsInExactlyOneOfThreeStates` (the rehearsed state: an ISO date beside `Duration:` and `Stack:`) | partly covered — see below |
| 4 | The procedure has never been rehearsed | `TestTheRehearsalRecordIsInExactlyOneOfThreeStates` (the never state, and the blank-field prohibition) | covered |
| 5 | A run stops before the host is serving | `TestTheRehearsalRecordIsInExactlyOneOfThreeStates` (the partial state; accumulation read as more than one `Last rehearsed:` line or `Partial run:` block) | covered |
| 6 | A rebuild silences the host's own reporters | `TestTheAlarmsARebuildRaisesArePredictedBeforeTheyFire`, `TestTheObserverPhaseIsOwedOnceTheHostIsBack` | covered |
| 7 | A check's intended settings are recorded nowhere | `TestEveryCheckAHostReportsToHasItsSettingsRecordedOnce`, `TestTheRunbookCitesTheRegisterRatherThanCopyingIt` (both methods) | covered |
| 8 | A rehearsal is proposed against a stack whose loss is not tolerable | `TestARehearsalNamesAStackWhoseLossIsTolerable` | partly covered — see below |
| 9 | A rehearsal finds the procedure wrong | `TestTheRehearsalRecordIsInExactlyOneOfThreeStates` (a rehearsed record with no `Corrected:` line) | partly covered — see below |
| 10 | A store the rebuilt host held does not come back | `TestWhatARebuildLosesIsStatedBeforeItIsLost` | covered |

### What is deliberately untested, and why

Each is a clause of a scenario that is not a static read of a committed file. Recorded rather than dropped, so the absence of a test is distinguishable from the absence of the thought.

- **Scenario 3 — *"the run SHALL begin with a real host's server destroyed and end with that host serving what it served before."*** No committed file can say whether that happened. The record's own claim is checked; the claim's truth is tasks 6.3–6.6's, and a reviewer's.
- **Scenario 8 — *"it SHALL NOT be performed against"* a stack whose loss is not tolerable.** An act, not a file. What is checked is the record's `Stack:` value, against the set of stacks whose own `pipeline.yml` sets `destroy_policy_gate: false`. A rehearsal performed against production and then recorded as staging is outside anything static.
- **Scenario 9 — *"the document's own steps SHALL be corrected."*** A corrected step and an original step are the same shape in a committed file; nothing distinguishes them statically, and diffing against an earlier revision is not a static read of the tree. Only the second clause — that the record names what was corrected — is checked.
- **Scenario 1 — whether the credential named is the *correct* one**, and whether the step is *right*. design.md states both as out of scope for this module.
- **The runbook citing rather than copying the database recipe** (design.md, tasks 2.2a) is **already covered by an existing module**: `.github/tests/test_the_requirement_names_where_the_recipe_lives.py` reads every committed Markdown document outside `openspec/`, which the new runbook joins automatically. No assertion was duplicated here. The *count* of `platform/README.md`'s two manual steps is not covered by anything — tasks 2.2a says only the first is mechanically caught, and this module adds nothing there.

## Assertion provenance

**SPECIFIED** — traces to SHALL text or to a scenario in the delta:

- the document exists at `docs/runbook-rebuild.md` and is the only place the sequence is written;
- every step names the credential it needs or states it needs none;
- every step names *where* that credential is held;
- each of the four external venues the delta enumerates is written as a step of the sequence;
- Appendix B names the recorded procedure and restates no sequence;
- the rehearsal record is in exactly one of the three states, with that state's lines, with `Last rehearsed:` present in all three and `Partial run:` in exactly one;
- the never state is written out rather than left blank;
- a partial run keeps `Last rehearsed: never`;
- a later record replaces rather than accumulates;
- a rehearsed record names the stack;
- the alarms are named before the step that destroys the server, with a duration;
- the observer phase names the observer, names this host's checks individually, and re-reads them against period and grace;
- every check a host reports to has its period and grace recorded in Appendix A;
- the runbook cites Appendix A and carries no second copy of the values;
- the losses are stated before the destroy step, citing *No Store on This Host Holds Data Requiring Backup* by its capability spec path and naming the store that requirement records as unmet.

**DERIVED** — invented by this pass to make a specified property statically readable. Each is a form the implementer must meet without having chosen it, which is why each is listed:

1. **A step is a level-2 heading beginning with a number** (`## 3. …` or `## Phase 3. …`). tasks.md 2.1 speaks of phase headings; the level and the numbering are this module's.
2. **`PHASE_FLOOR = 6`** — a floor under how many phases exist, so a document whose headings stopped parsing cannot report clean.
3. **Phase numbers strictly increase** — rather than being contiguous from 1.
4. **`CREDENTIAL_HOLDERS`** — the vocabulary that counts as "naming where a credential is held": this repository's actual holders plus three generic locatives (`held in/at/by`). **Extend it, never narrow it**: a holder nobody anticipated is added in the commit that introduces it.
5. **`Corrected:`** as the label a rehearsed record names its corrections on. The delta requires the record to name what was corrected and requires labelled lines, but fixes no spelling for this one. `Corrected: none` is conformant.
6. **`MAX_STAGE_REFERENCES_IN_A_POINTER = 4`** — a pointer legitimately names the two or three stages its kept claim is about; Appendix B names nine today. Raise it deliberately, not by sliding.
7. **`SEQUENCE_PHRASES`** — Appendix B's own words, read because the count in (6) cannot see a sequence rewritten into prose with the numbers dropped.
8. **`server_enabled = false` is the step that destroys the server** — the point two scenarios order content against. Matched over raw text because it is written inside a fenced snippet.
9. **Stacks whose loss is tolerable = `destroy_policy_gate: false`** — read from each stack's own `pipeline.yml`, on the strength of that field's declaration in `terraform/stacks/main-production/pipeline.yml`: *"A stack that exists to be rebuilt may set this `false`; this one may not."*
10. **Prometheus and Grafana** named as the stores that do not come back — proposal.md's Impact and design.md's Non-Goals, not the delta.
11. **`REGISTER_WINDOW = 4`** — a check's period and grace sit on its own table row or within the four lines under its name.
12. **A second copy of the register is a `| … Period … Grace … |` header row or a `Period:`/`Grace:` labelled line carrying a duration** — narrow on purpose, so that saying how long an alarm lasts (which scenario 6 requires) is not read as copying a value. That non-collision is itself a detector-fires case.
13. **`DURATION`'s spellings** — `7 days`, `5 minutes`, `a few minutes`, `several days`. A bare number is not a duration.

## Interface assumptions the implementer must meet

Two structural assumptions, stated in the module's docstring and repeated here because they are the likeliest way the document fails a check it actually satisfies:

1. **The rehearsal record's own labelled lines sit directly under `## Rehearsal record`**, and the prose documenting the three states (tasks 2.6) sits under a *following* heading of any level. The record is read from its heading to the next heading.
2. **A labelled line quoted as documentation is written in backticks or inside a fence.** `` `Last rehearsed: never` `` in a sentence is documentation; a bare `Last rehearsed: never` is the record. Without that, the state documentation would be read as a second record.

## An ordering conflict this pass found — raised, not resolved

`TestEveryCheckAHostReportsToHasItsSettingsRecordedOnce` fails today, naming `main-production-alertmanager` and `main-staging-alertmanager` as recorded nowhere in Appendix A. Its two prune siblings pass, which is the positive control that the check reads the register correctly.

The delta specifies that register entry (*"Every check a host of this repository reports to SHALL have its intended period and grace recorded in one place … recording them is part of satisfying this requirement rather than a precondition of it"*). **tasks.md schedules it at 7.4 — after the rehearsal, in pull request 4 — while this module lands in pull request 1.** So pull request 1's required check is red on that one test unless the block lands with it.

The assertion was not softened, because the delta states it outright. The remedy is available and cheap: the values are read *at the observer*, which needs no rebuild and can be done at any time — task 6.1's read of them is what makes the rehearsal checkable, not what makes them knowable. Reading them before pull request 1 and writing the Appendix A block there satisfies the delta, satisfies this check, and leaves task 7.4 to correct them against what the rehearsal actually found. **This is a decision for whoever sequences the pull requests, not for the test author**, and `openspec-update-change` is where tasks.md would be revised if it should move.

Nothing else in this module is red for a reason other than `docs/runbook-rebuild.md` being unwritten and Appendix B being unreduced, both of which pull request 1 does anyway.

## Obsolete tests

**Not applicable.** This change's delta carries one `ADDED` requirement and no `MODIFIED`, `REMOVED` or `RENAMED` delta, so no existing test can have been superseded by it. No existing test was edited, deleted or disabled, and none was searched for on a basis this pass could not evidence.

For completeness: `openspec/specs/iac-server-lifecycle/spec.md` carries two requirements today — *Conditional Prod Server Creation* and *Infrastructure Predating Terraform Stays Under Continuous Management, Decoupled From Ephemeral Resources* — and neither is touched by this delta.

## Unresolved project questions

Recorded rather than resolved, because this pass had no channel to ask on. Each names the assumption taken and the tests that depend on it.

1. **Is there a stack-neutral name for the observer?** The repository names healthchecks.io in prose and addresses it through `PLATFORM_DEADMANSWITCH_URL` and `HEARTBEAT_PING_KEY`, with no committed file naming the vendor as a value. *Assumption:* the runbook's observer phase names it as "healthchecks" or "heartbeat". *Depends on it:* `TestTheObserverPhaseIsOwedOnceTheHostIsBack`, and the heartbeat row of `TestEveryStepPerformedElsewhereIsWrittenAsAStep`.
2. **Which spelling does the record's correction line take?** No project convention exists. *Assumption:* `Corrected:`. *Depends on it:* the rehearsed branch of `TestTheRehearsalRecordIsInExactlyOneOfThreeStates`.
3. **Is `destroy_policy_gate: false` the repository's operative definition of "a stack whose loss is tolerable"?** It is the only committed declaration that speaks to disposability. *Assumption:* yes. *Depends on it:* `TestARehearsalNamesAStackWhoseLossIsTolerable`, and the production-stack half of `TestWhatARebuildLosesIsStatedBeforeItIsLost`.
4. **No stack-specific testing skill exists for this row.** The project's three test commands are recorded in `AGENTS.md`, and the static row is stdlib `unittest`; the toolkit carries no skill for it beyond the general testing floor and `python`. Recorded as an absence, proceeded on the floor alone.

## Fixture-driven discriminators

Every matcher this module introduces is exercised over material the module itself supplies, in the five `…DetectorFires` classes — 51 cases, all passing today. One case per rehearsal-record state and one per way each state can be malformed, per the delta's own three-state table; one case proving the destroy marker is found inside a fence where an unfenced sweep would miss it; one proving that saying how long an alarm lasts is not read as a copied register value, so that two clauses of the same delta do not contradict each other.

No discriminator was written but left unrun, and none came back negative.
