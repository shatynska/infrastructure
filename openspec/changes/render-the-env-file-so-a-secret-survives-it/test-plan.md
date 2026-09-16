# Test plan

Derived from this change's approved delta specification at commit `f488c21`, by an author other than whoever implements it, before any implementation existed. The delta MODIFIES one requirement of `iac-platform-deploy-pipeline` — *Platform Secrets Rendered from CI at Deploy Time* (`openspec/specs/iac-platform-deploy-pipeline/spec.md`) — and the restated requirement carries **ten** `#### Scenario:` blocks: three it carries forward unchanged and seven it adds. All ten are accounted for below.

This file is not an artifact the OpenSpec schema knows about. It does not appear among `openspec instructions apply`'s context files and has to be read on purpose.

**The pass that produced it was additive only.** One file was created, `.github/tests/test_the_rendered_env_survives_its_parser.py`, and one more — this one. No existing test was edited, deleted or disabled, and no implementation was written. The render step, the documents and the harness are all still exactly as commit `f488c21` left them.

## Test command and path

`python3 -m unittest discover --start-directory .github/tests`, run from the repository root. Test-path glob `.github/tests/*.py`. This is `AGENTS.md`'s third row, and it is the only one of the three that can hold any of this change's assertions: every one of them is a static read of a committed file.

## Baseline

**Full**, taken before anything was written: `python3 -m unittest discover --start-directory .github/tests` from the repository root — **1285 tests, 0 failures, 0 errors, 29.7s.**

After this pass: **1350 tests, 15 failures, 0 errors, 34.8s.** The 65 new tests account for the whole difference, and the 15 failures are all in the new module. Nothing that was green before this pass is red after it.

## Scenario-to-test map

Every test below is individually selectable as
`python3 -m unittest test_the_rendered_env_survives_its_parser.<Class>.<test>`, run from the repository root.

### Carried forward unchanged by the MODIFIED delta

These three scenarios are unaltered by this change, and this pass wrote no test for them. They are covered by tests that already existed and that this delta does not supersede.

| Scenario | Covered by | Note |
|---|---|---|
| Rendered .env never enters version control | `test_the_platform_stack_deploys_per_stack.TestTheRenderedEnvIsNeverCommitted.test_no_env_file_is_committed_under_the_stack_definition` | Already annotated SPECIFIED against this scenario in that module. |
| Deploy job authenticates as the provisioned deploy account | `test_the_platform_stack_deploys_per_stack.TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount.test_every_connection_authenticates_as_the_provisioned_deploy_account` | Same. |
| Two stacks render two different sets of values | `test_the_platform_stack_deploys_per_stack.TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares.test_every_deploy_row_attaches_to_an_environment`, and `TestThePlatformDeployNamesNoStack.test_no_matrix_row_carries_a_secret_name` | Covered only in the form a committed file can carry, as that module's own header records: whether an Environment holds two different values is a repository setting and this suite makes no network call. This pass does not change that, and adds nothing to it. |

### Added by this change — covered here

#### Scenario: Every rendered value passes through the escaping point

| Test | Provenance |
|---|---|
| `TestTheRenderStepHasOneEscapingPoint.test_one_step_writes_the_rendered_file` | SPECIFIED — "no line SHALL write a value into that file by any other route", read across the whole workflow. |
| `TestTheRenderStepHasOneEscapingPoint.test_the_render_step_defines_exactly_one_escaping_point` | SPECIFIED — "that the escaping point exists". |
| `TestTheRenderStepHasOneEscapingPoint.test_the_escaping_point_writes_the_assignment_itself` | DERIVED — tasks.md 2.1, `design.md` Decision 5. Exactly one emitting line inside the point, because the point's output *is* the file. |
| `TestTheRenderStepHasOneEscapingPoint.test_the_step_takes_no_command_substitution` | DERIVED — tasks.md 2.1: `$(…)` strips trailing newlines and a secret may end in one. |
| `TestTheEscapingPointSubstitutesInOrder.test_the_three_substitutions_are_applied_in_the_order_the_design_fixes` | SPECIFIED that an order is asserted ("in the order it claims them"); DERIVED (`design.md` Decisions 3 and 4) as to which order and which replacements. Asserted as an ordered list, never as a set — a set-wise check passes a rendering that escapes the quote first and then doubles the backslash it introduced itself. |
| `TestTheEscapingPointSubstitutesInOrder.test_each_substitution_replaces_every_occurrence` | DERIVED — Decision 4 states the rule over a value, and `${v/x/y}` replaces only the first occurrence. |
| `TestTheEscapingPointSubstitutesInOrder.test_the_three_substitutions_act_on_one_variable` | DERIVED — Decision 5. Three substitutions on three variables are three escapings of three different strings, and the order above would constrain nothing. |
| `TestEveryRenderedValueGoesThroughTheEscapingPoint.test_the_written_block_contains_calls_and_nothing_else` | SPECIFIED — the scenario, and "that the file is written by nothing else". |
| `TestEveryRenderedValueGoesThroughTheEscapingPoint.test_every_variable_the_env_example_documents_is_rendered` | SPECIFIED — "reaching every value the deploy job writes into that file rather than only the ones that are credentials". **The floor is derived, not a literal**: it is `env_example_variables()` from `test_the_platform_stack_deploys_per_stack.py`, reading the committed `platform/.env.example`, per tasks.md 1.4. A ninth value is in the floor the day it is documented. |
| `TestEveryRenderedValueGoesThroughTheEscapingPoint.test_the_file_is_written_once` | SPECIFIED — the same clause, read within the step. |

#### Scenario: A rendered value the previous rendering would have altered is reported by name

| Test | Provenance |
|---|---|
| `TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered.test_the_step_reports` | SPECIFIED — the scenario's THEN. |
| `TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered.test_what_it_reports_is_a_name` | SPECIFIED — "SHALL report that variable's name". What the naming branch expands must be an accumulator assigned somewhere in the step from the escaping point's own first positional parameter. |
| `TestTheReportTestsTheMeasuredSetByPresenceAnywhere.test_the_set_is_decision_nines_set_character_for_character` | DERIVED — `design.md` Decision 9's table. The delta deliberately carries no set ("a fact about the rendering being replaced rather than about this capability"), so this is the only thing binding the implementation to the measurement. Asserted as an **equality**: a dropped member and an added one are both reported. |
| `TestTheReportTestsTheMeasuredSetByPresenceAnywhere.test_leading_and_trailing_whitespace_are_both_tested_for` | DERIVED — Decision 9's seventh member. Asserted at both ends and as a whitespace *class*, because round 6 measured both ends stripping a tab as well as a space. |
| `TestTheReportTestsTheMeasuredSetByPresenceAnywhere.test_no_member_is_detected_by_position` | DERIVED — Decision 9's "detection is by presence anywhere in the value, not by position", and tasks.md 1.5's second half. This is the assertion a set-only check cannot make: narrowing `#` to `" #"` leaves the set unchanged. It guards on `detections(body)` being non-empty first, so it cannot pass by having nothing to read. |

#### Scenario: A deploy that altered no value says so

| Test | Provenance |
|---|---|
| `TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered.test_a_deploy_that_altered_no_value_says_so` | SPECIFIED — "SHALL report that explicitly, rather than reporting nothing". Asserted as a report line that expands no variable of its own, alongside the naming branch that does. |

#### Scenario: The escaped form of a value is never emitted

| Test | Provenance |
|---|---|
| `TestNoLineEmitsARenderedValueOrItsEscapedForm.test_nothing_but_the_assignment_emits_the_escaped_value` | SPECIFIED — "Nor SHALL any escaped form of a value be emitted", and "That report SHALL name variables only". The escaped variable is named explicitly, per tasks.md 1.5: masking is registered against the secret's own value, so the escaped variant is the one shape a check written against the raw name alone would not see. |
| `TestNoLineEmitsARenderedValueOrItsEscapedForm.test_the_exempt_write_is_the_assignment_and_not_a_log_line` | DERIVED — tasks.md 2.1. The sweep above exempts one line; this is what stops that exemption being claimed by a debug print. |

### Added by this change — deliberately uncovered

Three scenarios, all for the same reason, and the dispatch named it rather than leaving it to be discovered.

| Scenario | Reason |
|---|---|
| A secret containing a character the parser treats specially survives the parse | Compose parser behaviour. Observing it needs a Compose run, and this suite may not spawn a container — a constraint it asserts over itself (`TestTheSuiteNeedsNoPrivilegedResource` and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in `test_ci_configuration.py`). `terraform test` exercises Terraform modules and Molecule's subject is an Ansible role's behaviour on a host, so neither other row can hold it either. |
| A secret that spells a variable reference is not resolved from the rendering environment | Same. |
| A secret containing the quote character is not yielded as empty | Same. |

**The evidence for these three is the measurement in this change's `design.md`, rounds 1 to 7, together with the harness committed by tasks.md 3.1 — not a test.** `design.md` Decision 6 states this directly and states its residual (the rule was measured on Compose v5.4.0; the host parses with v5.5.0). No check in the new module reads the workflow and calls it parser behaviour, which tasks.md 1.2 forbids and which would be worse than no check at all: it would read as the evidence that the measurement is.

## What was red on arrival, and what was green

Fifteen of the new tests are red against the current tree, which is every assertion that reads a property the change introduces. The step today has no escaping point and no report at all.

Red (15): `TestTheRenderStepHasOneEscapingPoint` — `test_the_render_step_defines_exactly_one_escaping_point`, `test_the_escaping_point_writes_the_assignment_itself`; `TestTheEscapingPointSubstitutesInOrder` — all three; `TestEveryRenderedValueGoesThroughTheEscapingPoint` — `test_the_written_block_contains_calls_and_nothing_else`, `test_every_variable_the_env_example_documents_is_rendered`; `TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered` — all three; `TestTheReportTestsTheMeasuredSetByPresenceAnywhere` — all three; `TestNoLineEmitsARenderedValueOrItsEscapedForm` — both.

**Green on arrival, and why** — recorded rather than contorted into failing, per tasks.md 1.6:

- `TestTheRenderStepHasOneEscapingPoint.test_one_step_writes_the_rendered_file` — exactly one step of `platform-deploy.yml` redirects into `platform/.env` today. The property is already true; the test exists to keep it true once a report step and a helper are added.
- `TestEveryRenderedValueGoesThroughTheEscapingPoint.test_the_file_is_written_once` — same property, read within the step. One redirect today.
- `TestTheRenderStepHasOneEscapingPoint.test_the_step_takes_no_command_substitution` — the current step has no `$(…)`. The prohibition arrives with this change because this change is what creates the temptation (a helper that prints and a caller that captures), not because the step violates it today.

Both `TestTheConformingFixtureSatisfiesEveryRead` (13 tests) and `TestTheseReadsDiscriminate` (34 tests) are green from the moment they were written, by design, and each says so in its own docstring so that its passing is not mistaken for coverage of the change.

## Fixture-driven discriminators

Every assertion in the new module is a static read, so a green run establishes nothing on its own. Two classes answer that:

- **`TestTheseReadsDiscriminate`** runs each predicate over material this file supplies, carrying the one defect that predicate names — the substitutions reordered, a `${v/…}` in place of `${v//…}`, `\$` in place of `$$`, a `printf` smuggled into the write block, a ninth documented variable the block does not render, a second redirect into the file, a second step writing the file, a dropped set member, an added one, `#` narrowed to `" #"`, an apostrophe anchored to the opening position, a whitespace edge dropped, a literal space in place of the class, a report with no silent branch, a report with no naming branch, an accumulator built from the value rather than the name, a debug `echo` of the escaped variable, and a notice carrying a rendered value. Each asserts the predicate responds.
- **`TestTheConformingFixtureSatisfiesEveryRead`** runs every predicate over one step that satisfies them all at once. Without it, a predicate no implementation could satisfy would be indistinguishable from one whose implementation has not landed, and the implementer would discover the difference by rewriting the workflow to fit a check rather than to fit the design. The fixture is the smallest shape every reader can see; it is **not** a recommended implementation.

## Obsolete tests

**Searched, and none found.** Stated as "no such test exists" rather than "none was found", because the basis is readable:

- The delta is a MODIFIED operation that **adds** clauses to the requirement and retires none. Every sentence the requirement carried at `f488c21` is carried forward verbatim, and all three of its pre-existing scenarios survive unchanged — so nothing an existing test asserts about this requirement has been superseded.
- The search was bounded to the dispatched glob, `.github/tests/*.py`, and swept it for anything asserting the rendering being replaced: `printf`, `Render .env`, `platform/.env`. The only module asserting anything about this requirement is `test_the_platform_stack_deploys_per_stack.py`, and its three relevant classes (`TestTheRenderedEnvIsNeverCommitted`, `TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount`, `TestTheSecretSetIsEstablishedBeforeAnythingIsWritten`) read the commit state, the SSH account and the secret set — none of them reads the `printf` shape this change replaces.
- No earlier `test-plan.md` exists for this change, so no scenario-to-test mapping was available to draw on beyond the above.

No dispatched artifact supplied one either. Nothing in the implementation step needs to delete or rewrite a test.

## Unresolved project questions, and the assumptions taken

These are recorded rather than resolved, because a dispatched subagent has no channel to ask on. Each names the assumption and the tests that depend on it.

1. **The escaping point is a shell function using bash parameter expansion.** `design.md` Decision 5 and tasks.md 2.1 say the helper escapes into a variable and forbid `$(…)`, which rules out `sed`; neither fixes the construct. The readers locate the point as a *function definition* whose body applies `${var//…/…}` to one of the three characters. A `sed`-based or inline-in-the-block escaping would be reported as "no escaping point", not as a wrong one. **Depends on it:** every test in `TestTheRenderStepHasOneEscapingPoint`, `TestTheEscapingPointSubstitutesInOrder`, `TestEveryRenderedValueGoesThroughTheEscapingPoint` and `TestNoLineEmitsARenderedValueOrItsEscapedForm`.
2. **The report's detection is written as a `case` arm or a `[[ … == … ]]` comparison.** Nothing fixes a construct; these are the two ways bash asks "does this value contain that", and the failure messages name both so the implementer is not left guessing which forms the reader can see. A detection written some other way (a `grep`, which `$(…)` is forbidden for anyway, or a loop over an array) would be reported as an absent detector. **Depends on it:** all three tests in `TestTheReportTestsTheMeasuredSetByPresenceAnywhere`.
3. **The report lives in the render step.** Nothing states it; it follows from the values reaching the shell only through that step's own `env:` block, so no later step can see them to test them. **Depends on it:** all three tests in `TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered` and all three in `TestTheReportTestsTheMeasuredSetByPresenceAnywhere`.
4. **The report is a `::notice::` or `::warning::` workflow command.** tasks.md 2.3 says notice; the delta says only "report" and fixes no severity, so both are admitted and a report written some third way would be reported as absent.
5. **A line break is spelled `$'\n'`, or as a single-character bracket expression.** Decision 9 names the member; nothing fixes its spelling in a glob. A line break carried in a variable (`*"$LF"*`) would be read as the three characters `L`, `F` rather than as a newline, and reported as a missing member. **Depends on it:** `test_the_set_is_decision_nines_set_character_for_character`.

## Deliberately untested, within covered scenarios

- **"or any count of such characters."** The delta forbids a count in the report. Nothing static distinguishes a variable holding a count from a variable holding a name, so the narrower readable property is asserted instead: that no report line emits a value or an escaped value, and that what the naming branch expands is an accumulator built from the escaping point's name parameter. A count computed into a second variable and emitted would pass. Recorded rather than approximated.
- **That the escaped form goes nowhere outside the render step.** The escaped variable is local to that step's shell, so the sweep is scoped to it. A step that somehow received the escaped form would be outside what any static read of this workflow can follow.
- **Whether `platform/.env.example` documents the right variables.** The floor is derived from that file; whether the file itself is complete is a property this change does not touch and is not re-litigated here.

## The static suite's own constraints are not checked over this module

Per tasks.md 1.7, and stated so the next reader does not assume a check stood behind it. `AGENTS.md` records that the static suite's self-constraints — no network call, no credential, no container runtime, no Terraform binary, standard library only — "currently read only `test_ci_configuration.py`, the module they live in". One half is wider: `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` reads every module in `.github/tests/`, and the new module passes it (it imports only `re`, `tempfile`, `unittest` and `pathlib`, and spawns nothing). The rest — including whether its assertions are genuinely static reads of committed files — is a reviewer's to check rather than a check's. `docs/backlog.md` `hold-the-whole-static-suite-to-its-own-constraints` is the entry that would widen them.

## What the implementation step must make pass

The fifteen red tests above, and nothing in this file marks a task complete. In summary, the render step must:

1. Define one shell function that applies `\`→`\\`, then `"`→`\"`, then `$`→`$$`, each globally (`${v//…}`) and to one variable, and emit exactly one line — the assignment, carrying both the name and the escaped value.
2. Write `platform/.env` from a block containing calls to that function and nothing else, one per variable `platform/.env.example` documents, with one redirect into the file and no `$(…)` anywhere in the step.
3. Test each value, by presence anywhere, for `$`, `"`, `'`, `#`, a line break and `\`, and positionally for leading and trailing whitespace as a whitespace class; report the qualifying names as a notice, and report explicitly when none qualifies.
4. Emit the escaped value on no line but the assignment, and no rendered value on any line at all.
