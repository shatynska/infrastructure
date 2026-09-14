# Test plan: provision-commerce-ops-database-in-the-shared-instance

Written by the independent test author, before any implementation, from this change's delta specification at commit `2315199` (the approved plan). This file is not an artifact the OpenSpec schema knows about: it does not appear among `openspec instructions apply`'s context files and must be read on purpose.

## Where the tests are, and how to run them

One new module: `.github/tests/test_the_shared_instance_has_its_first_database.py`. No existing test was edited, deleted or disabled.

Whole suite, from the repository root:

    python3 -m unittest discover --start-directory .github/tests

A single test, from the repository root — the form used for every test ID below, abbreviated as `<M>.<Class>.<test>` where `<M>` is `test_the_shared_instance_has_its_first_database`:

    python3 -m unittest discover --start-directory .github/tests -k <M>.<Class>.<test>

`python3 -m unittest <M>.<Class>.<test>` from the root does **not** work — it errors importing the sibling `test_ci_configuration`. Verified both ways on this tree.

### Which of the three test commands applies

Only `.github/tests`. The change touches no Terraform module and no Ansible role (proposal, Impact: "No Terraform, Ansible, Compose or workflow change"), so neither `terraform test` nor Molecule has a subject. Everything the delta states that a committed file can show is a static read; everything else is host state or policy, which none of the three commands reaches (design.md decision 9).

## Baseline

- **Before**: `python3 -m unittest discover --start-directory .github/tests` on this tree, full suite — **1125 tests, OK** (recorded by the dispatcher for task 1.1; PyYAML 6.0.1 per `.github/requirements-ci.txt`).
- **After adding the module**: full suite — **1185 tests, 9 failures, 0 errors**. All 9 failures are in the new module; the 1125 existing tests pass. 60 new tests: 51 pass, 9 fail.
- During this pass the new module briefly turned an existing test red — `test_ci_configuration.TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation.test_no_committed_file_outside_openspec_carries_a_pre_archive_citation` — because a fixture path in the new file spelled `openspec/changes/` followed by a kebab-case segment. The fixture was reassembled from parts in the new file; the existing test was not touched and is green again.

## What the implementation must make pass

The nine tests red at authoring, each red on real content, and the property each is red on:

| Test | Red on | Made green by |
|---|---|---|
| `<M>.TestTheBacklogCarriesTheEntryTheRequirementNames.test_the_backlog_carries_that_entry` | `docs/backlog.md` does not name `automate-per-application-database-provisioning` | task 3.1 |
| `<M>.TestTheRecipeIsReadAtAll.test_that_block_generates_the_password_it_delivers` | the recipe block assigns no variable from `openssl rand` | task 2.1 |
| `<M>.TestTheRecipeKeepsThePasswordOffCommandLines.test_the_password_is_expanded_only_into_standard_input` | its **precondition** — no generated password variable — so its own assertion has not yet executed on real content (see Discriminators) | task 2.1 |
| `<M>.TestTheRecipeRunsItsStatementsOverStandardInput.test_no_statement_is_passed_to_psql_as_an_option` | `psql … -c`, statements on a command line, no here-document carrying `CREATE DATABASE` | task 2.1 |
| `<M>.TestTheRecipeQuotesItsIdentifiers.test_every_role_and_database_identifier_is_double_quoted` | no `CREATE DATABASE` in standard input to check | task 2.1 |
| `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_the_database_is_owned_by_the_role_the_recipe_creates` | no `CREATE DATABASE` in standard input | task 2.1 |
| `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_connect_is_revoked_from_public` | nothing revoked from `PUBLIC` | task 2.1 |
| `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_temporary_is_revoked_from_public` | nothing revoked from `PUBLIC` | task 2.1 |
| `<M>.TestTheRecipeRefusesAnAlreadySetSecretName.test_secret_names_are_read_and_a_refusal_precedes_any_write` | neither `gh secret list` nor `gh secret set` in the block | task 2.1 |

A recipe matching design.md decision 5's block satisfies every recipe detector — the module's conforming fixture is modelled on it.

Green at authoring and expected to stay green through implementation and archive: the requirement-text tests (they read this change's live delta), the change-record division tests, `<M>.TestTheRecipeIsReadAtAll.test_the_document_carries_exactly_one_provisioning_block`, and every `…DetectorFires` / locator-fixture test.

## Scenarios

The delta carries five scenarios. Five are accounted for below.

### 1. A new application requests a database — covered in part; the rest uncovered with reasons

Covered, as necessary conditions over the recipe the requirement names as how each provisioning is performed (`docs/bootstrap-a-new-host.md`):

| Clause | Test | Classification |
|---|---|---|
| owned by a role of the application's own | `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_the_database_is_owned_by_the_role_the_recipe_creates` | specified (as a recipe property) |
| which no other application's role can connect to | `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_connect_is_revoked_from_public` | specified (as a recipe property) |
| — | `<M>.TestTheRecipeGivesTheDatabaseToItsOwnRole.test_temporary_is_revoked_from_public` | derived — design.md decision 5; the scenario names connecting only |
| password generated for this host alone | `<M>.TestTheRecipeIsReadAtAll.test_that_block_generates_the_password_it_delivers` | derived — per-run generation is a necessary condition of per-host independence |
| delivered only to this host's deploy target | `<M>.TestTheRecipeKeepsThePasswordOffCommandLines.test_the_password_is_expanded_only_into_standard_input` | derived — design.md decision 5, "The password never on a command line" |
| — | `<M>.TestTheRecipeRunsItsStatementsOverStandardInput.test_no_statement_is_passed_to_psql_as_an_option` | derived — design.md decision 5, "Statements over stdin" |
| — | `<M>.TestTheRecipeQuotesItsIdentifiers.test_every_role_and_database_identifier_is_double_quoted` | derived — design.md decision 4 |
| — | `<M>.TestTheRecipeRefusesAnAlreadySetSecretName.test_secret_names_are_read_and_a_refusal_precedes_any_write` | derived — design.md decision 5, "A secret name nothing in that Environment already uses" |
| — (precondition) | `<M>.TestTheRecipeIsReadAtAll.test_the_document_carries_exactly_one_provisioning_block` | derived — design.md decisions 5 and 6, one block pasted whole into one shell |

Uncovered, with reasons:

- **A database in the shared instance, not a new PostgreSQL container; its owner; that no other role can connect.** Host state. Verified by tasks 4.1 and 6.2 from each host (`\l`, `datacl`, `has_database_privilege('pgexporter', …)`); whether the application's deploy brings a container is observed by tasks 6.4–6.5. No test command reaches either host or the application's repository.
- **Generated for this host alone, as opposed to per run.** Two hosts' passwords differing is a property of two runs, observed only as two runs (tasks 4.1, 6.2).
- **Delivered only to this host's deploy target.** Where a secret lands is in another repository's Environment, read by `gh secret list` in tasks 4.1 and 6.2, which needs a credential and a network call this suite may not make.
- **SHALL NOT enter a file in this repository.** No static read can recognise a secret whose value this repository never sees. The recipe tests assert only that the recipe itself neither embeds nor echoes a generated password onto a command line. The existing `gitleaks` hook is the repository's scan for credential-shaped content, and is unchanged.

### 2. An application needs durable storage — uncovered

Reason: the delta leaves this scenario's text unchanged. It is a rule for applications' choice of store, with no committed file here that would show it being obeyed, and no host check this change runs is about it (design.md decision 9: "Unchanged by this delta"). The obsolete-test search found no existing test for it either.

### 3. An application's data divides into durable and non-durable parts — covered for the record; the rest uncovered

| Clause | Test | Classification |
|---|---|---|
| the change that records the database SHALL state the division | `<M>.TestTheChangeRecordStatesTheTableDivision.test_its_design_states_the_division` | specified (that a division is stated); the table names asserted are derived from design.md decision 3 |
| — (precondition) | `<M>.TestTheChangeRecordStatesTheTableDivision.test_the_change_record_exists_exactly_once` | derived |

Uncovered: **only the non-durable tables placed in the shared instance; an unnamed table not placed there.** The application's repository decides which connection each table uses. Nothing in this repository can observe a table's contents without reading application data (design.md decision 3 and Risks).

### 4. A staging database holds rehearsal data — uncovered

Reason: a policy an operator obeys — treat the contents as tolerable to lose, never copy production data in, never read the policy as classifying another store. No check this repository has can observe any of it (design.md decision 9). A test that the requirement *states* the policy was deliberately not written: this scenario's THEN is about how data is treated, not about the text, so such a test would check the specification against itself.

### 5. The automation trigger has fired and the mechanism is not built — covered

| Clause | Test | Classification |
|---|---|---|
| the requirement SHALL state that the trigger fired | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_the_requirement_states_that_the_trigger_fired` | specified |
| dated | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_that_statement_is_dated` | specified |
| which application | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_that_statement_names_the_application_that_fired_it` | specified (`commerce-ops`, as the delta names it) |
| mechanism and credential path owed | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_it_states_the_mechanism_and_its_credential_path_are_owed` | specified |
| manual provisioning SHALL NOT be read as discharging | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_it_says_manual_provisioning_does_not_discharge_the_obligation` | specified |
| — | `<M>.TestTheRequirementStatesTheTriggerHasFired.test_the_superseded_premise_is_no_longer_stated` | derived — the requirement as it stood said "no application has needed one" |
| the requirement names the backlog entry | `<M>.TestTheBacklogCarriesTheEntryTheRequirementNames.test_the_requirement_names_the_backlog_entry` | specified (requirement body) |
| `docs/backlog.md` carries that entry | `<M>.TestTheBacklogCarriesTheEntryTheRequirementNames.test_the_backlog_carries_that_entry` | specified (requirement body); necessary condition only — a mention of the name satisfies it |
| — (precondition) | `<M>.TestTheRequirementIsReadAtAll.test_the_requirement_block_is_found_with_its_prose_and_scenarios` | derived |

**Which text is read, and why.** Chosen: the requirement block in any live, unarchived change's delta for `iac-platform-services`, falling back to `openspec/specs/iac-platform-services/spec.md` only where no live delta carries it (`requirement_sources`). The alternative — reading only the main specification — would be red on every commit of this change's implementation pull request, because the delta is merged into the main specification only at archive, which comes after that pull request merges. The chosen form passes now, passes after archive, and fails if archiving drops the text. A later change modifying this requirement again (the mechanism landing) is read in its place, and supersedes these tests. The change directory is found by name in both the live and the archived layout; no path naming the change's own directory is written in the module.

## Discriminators

Every check in the module is a static read, so each detector is also run over material the module supplies to falsify it:

- `<M>.TestTheDivergenceDetectorFires` (9 tests): a conforming requirement yields nothing; the requirement as it stood is reported; each of undated, no application, credential path not owed, discharge permitted, and no backlog entry is reported; a paragraph that names the trigger without saying it fired does not satisfy the check; a block ends at the next requirement.
- `<M>.TestTheRequirementIsReadWhereItIsAboutToStand` (4 tests): a live delta is read in place of the main specification; the main specification is read once only an archived delta carries the requirement; a live delta of another requirement is ignored; a tree carrying the requirement nowhere yields nothing, which the precondition test turns into a failure.
- `<M>.TestTheRecipeDetectorsFire` (20 tests): a conforming recipe (design.md decision 5) yields nothing on every detector. The recipe shape the handoff describes (`psql -c`, password on the line, unquoted, nothing revoked) is reported on every property. Each property is reported when broken on its own: `--body "$pw"`, `${pw}`, `-c`, a here-document not fed to psql, unquoted identifiers, an owner other than the created role, no owner, no revoke, CONNECT without TEMPORARY, a revoke from a named role rather than `PUBLIC`, a revoke inside a SQL comment, a name check with no exit, the refusal placed after the secret is set, and no `gh secret list`. Also accepted: psql's `:"var"` quoting and `REVOKE ALL PRIVILEGES`.
- `<M>.TestTheDivisionDetectorFires` (7 tests): a conforming division yields nothing; no division, no unclassified remainder, a dropped durable table, all tables called non-durable, and a division split across paragraphs are each reported; the record is found live and archived.

**Observed red on real content, recorded here as the check discriminating:** the eight recipe/backlog tests in the table above whose own assertion executed.

**Not yet observed on real content:** `test_the_password_is_expanded_only_into_standard_input`, red on its precondition only. Its assertion is established by the fixture discriminators alone until task 2.1 lands. **Known limit of that detector:** it follows expansions of the variable assigned from `openssl rand`. A password written literally onto a command line — as the committed recipe's `'<generated>'` placeholder invites — is caught only because `test_that_block_generates_the_password_it_delivers` requires generation inside the block, not by this detector.

## Deliberately untested (derived properties of the recipe)

design.md decision 5 names further elements. Each was identified and knowingly not asserted, because decision 9 does not list it as a static property the scenarios rest on. The operator's staging run and task 4.1's host checks establish each by running it:

- the `set -eu` subshell;
- `ON_ERROR_STOP`;
- the four logging settings pinned for the session — the password-in-log risk is checked on the host by task 4.1's `docker logs … | grep -ciE 'create role|alter role'`;
- the `\gset` / `\if` converging branches;
- the secret set before the host is reached;
- `rotate` assigned in the block rather than read from the shell;
- the unquoted here-document delimiter that lets `$pw` expand;
- stage 8.3's prose (Environment first, rotation, failure recovery), stage 8.4's secrets table, and Appendix B's re-provisioning step (tasks 2.2–2.5). These are prose whose wording this author has not seen and should not predict. `test_the_bootstrap_documents_static_conventions` already resolves their section cross-references.
- the backlog edits of tasks 3.2–3.4 and the sweep of task 3.5.

## Obsolete tests

Applicable: the change carries one `MODIFIED` delta. It supersedes, in the requirement as it stands under `openspec/specs/iac-platform-services/spec.md`: the first sentence's definition limited to technical or temporary records; the premise that provisioning is not automated "because no application has needed one", and the trigger worded as a future event; and the first scenario's WHEN clause ("non-durable technical or temporary data"), whose THEN gains three clauses.

Search, bounded to `.github/tests/*.py`: `grep -iE` for `Single Shared PostgreSQL`, `no application has needed`, `technical or temporary`, `8\.3`, `commerce-ops`, `per-application database`, `shared postgres`, `provision`, `postgres`, with each hit read.

- **None found by this search.** That is not the same as "no such test exists"; it is what a bounded text search found.
- Examined and judged not bearing, recorded so the judgment can be checked: `test_ci_configuration.py`, `CLASSIFIED_STACK_STORES["postgres_data"]`. Its value paraphrases the requirement as "limits it to technical or temporary records", but only the dictionary's keys are asserted against `platform/docker-compose.yml`; the value is never compared with specification text. The revised first sentence also still contains that phrase. It is not a candidate. A human may still wish to refresh the label.
- `test_the_bootstrap_documents_static_conventions.py` reads the document stage 8.3 lives in, for key paths and cross-references only. It is not superseded, and it will read the rewritten recipe.
- No earlier `test-plan.md` path was supplied, so none was consulted.

## Unresolved project questions

Assumptions taken, with the tests depending on each:

1. **The recipe is the only fenced code block (``` or ~~~) in `docs/bootstrap-a-new-host.md` carrying `CREATE DATABASE`.** An indented code block would not be read, and a second such block — a rollback, an Appendix B copy — fails the precondition. Depends: every `<M>.TestTheRecipe…` test. This follows decision 5's "pasted whole" rather than any recorded project convention for how recipes are laid out.
2. **Here-documents are the standard-input form**, and a line is a command unless it is a here-document body or a `#` comment. A recipe feeding psql by another stdin form (`printf … | ssh`) would be reported. Depends: `…KeepsThePasswordOffCommandLines`, `…RunsItsStatementsOverStandardInput`, `…QuotesItsIdentifiers`, `…GivesTheDatabaseToItsOwnRole`.
3. **The requirement's divergence paragraph keeps the delta's own wording through archive**: "trigger" and "fired" in one paragraph; "mechanism", "credential path", "owed"; "manual provisioning SHALL NOT be read as discharging"; and `` `docs/backlog.md` as `<entry>` ``. Depends: `<M>.TestTheRequirementStatesTheTriggerHasFired.*`, `<M>.TestTheBacklogCarriesTheEntryTheRequirementNames.*`.
4. **design.md decision 3's division stays one paragraph naming `procrastinate_*` as non-durable, the seven hand-curated tables as durable, and the remainder as unclassified.** Depends: `<M>.TestTheChangeRecordStatesTheTableDivision.test_its_design_states_the_division`.
5. **Test layout within `.github/tests`.** AGENTS.md fixes the glob but not whether a change adds a module or extends an existing one. A new module was added, following the sibling modules written by earlier independent test authors. No recorded convention decides it.
6. **Stack skill.** `ai-toolkit:python` was loaded for the suite's idiom; no library skill covers `unittest` specifically.

## Added at code review

Not written by the independent author. The code-review gate, round 1, mutated a copy of the tree and found recipe regressions every test above let through, each failing silently on a real run. They are closed in the same module, marked `ADDED AT CODE REVIEW`, as derived properties of design.md decision 5. No author test's result changed and the author's conforming fixture is left as written; the new fixture class works from `CODE_REVIEW_RECIPE_DOCUMENT`, the recipe as it stands after both review rounds.

- **Here-document termination.** `heredoc_openers` compared `line.strip()` with the delimiter, accepting an indented `SQL` that bash does not — so the recipe as it stood before `431f101`, indented under stage 8.3's list, passed all 60 tests while its paste hangs. Termination now follows bash (`heredoc_terminates`: the delimiter alone, preceded by nothing for `<<`, tabs only for `<<-`), and `<TestTheRecipeCannotRegressSilently>.test_every_here_document_terminates` reports a here-document left open. Changing that shared helper is the one change to the author's code, and it is **not** purely stricter: an unterminated here-document now swallows every line after it, so `password_on_command_lines` and `statements_not_over_standard_input` see nothing past it — a recipe whose closing `SQL` is indented and which then puts the password on a command line is reported by the termination test alone, where the old helper had those two detectors report it too. The suite still goes red on such a recipe, and every author fixture terminates at column 0, so no author test's result changed. Found by code review round 2.
- **Quoted delimiter** — `test_the_here_document_expanding_the_password_is_not_quoted`: `<<'SQL'` sends `$app` and `$pw` to psql literally and exits 0.
- **Log settings pinned** — `test_every_statement_logging_setting_is_pinned_before_the_password`: all four, before the first `CREATE ROLE` or `ALTER ROLE` carrying a password.
- **`rotate` assigned in the block** — `test_rotate_is_assigned_in_the_block_and_tested_by_the_refusal`.

- **The three secret-name listings** — `test_every_secret_name_listing_is_its_own_assignment_and_reaches_the_check` (round 2): the Environment's, the repository's and the organisation's names each read in an assignment of its own before the secret is set, each fed to the check, and the repository and organisation check not conditioned on `rotate`.
- **Each refusal branch, and case** — `test_each_refusal_branch_refuses_what_it_should` (round 3): with three refusal branches, the detectors above were each satisfied by one non-zero exit or one `rotate` test anywhere in the block, so a single branch could be removed, inverted or made to exit 0 unseen. This asserts each branch on its own — the repository and organisation `if` exits non-zero without consulting `rotate`; the Environment `if` refuses unless `rotate` is `yes`; its `else` refuses `rotate=yes` — and that both name comparisons are whole-line and case-insensitive, as GitHub's secret names are.

**Not asserted, by decision: that design.md decision 5's copy of the recipe equals stage 8.3's.** Both are identical at this change's head, checked line for line by both review rounds. A test binding them would bind the living document to an archived record, so that every later change to the recipe had to edit an archived design; keeping them equal is a reviewer's check for the life of this change and nothing after it.

`TestTheCodeReviewDetectorsFire` runs each over fixtures that falsify it — for the listings, both removed, one never fed to the check, two merged into one substitution, and the repository check conditioned on `rotate`; for the branches, the repository check folded into the Environment's, the Environment guard made a no-op or inverted, the `else` guard made a no-op, the repository refusal exiting 0, and a case-sensitive comparison; and: an indented terminator, the whole block indented under a list item, `<<-` with tabs (accepted) and with spaces (reported), both quoting styles, each log setting removed and one moved after the password, `rotate=no` removed and `${ROTATE:-no}` read from the shell.
