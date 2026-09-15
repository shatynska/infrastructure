# Test plan — `record-how-an-application-is-onboarded`

Derived from this change's delta specification at commit `e0ef360`, the commit holding the approved plan, by an author other than whoever implements the change and without reading the implementation of anything under test. This file is **not** an artifact the OpenSpec schema knows about: it does not appear among `openspec instructions apply`'s context files and must be read on purpose, before implementing.

**This pass adds tests and never subtracts.** No existing test was edited, deleted or disabled, and nothing was written outside `.github/tests/*.py` except this file.

`<M>` below abbreviates the one module added: `.github/tests/test_the_requirement_names_where_the_recipe_lives.py`.

## Baseline

Taken in this working tree at `e0ef360`, immediately before any test was written, over the whole static suite — the only one of this repository's three test commands that can place a test for this change, its delta's subject being a static read of committed files:

    python3 -m unittest discover --start-directory .github/tests   # from the working tree root

**1210 tests, OK, 28.8 s.** Nothing was failing beforehand, so every failure recorded below is attributable to this pass. PyYAML 6.0.1 and Python 3.12.3 were present; nothing was installed.

After this pass: **1236 tests, 3 failures, 29.1 s.** The 26 added tests are all in `<M>`; the 3 failures are the 3 named under *Red at authoring* and are expected until the implementation moves the recipe. No test outside `<M>` changed its result.

## What this change owes, and what it does not

The delta MODIFIES one requirement, *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`). Diffed against the delta of `provision-commerce-ops-database-in-the-shared-instance`, which is live and archives first, it differs in exactly three places: the document path naming where the manual recipe lives, one added normative paragraph, and one added scenario — *The document this requirement names holds the recipe*.

Every other paragraph and scenario in the block is carried over unchanged and is already covered by `.github/tests/test_the_shared_instance_has_its_first_database.py`, whose author was that change's test writer. Re-asserting them here would duplicate an existing module, so the added scenario is the whole of what this pass writes.

## Scenarios

The delta carries **six** `#### Scenario:` blocks. Six are accounted for below.

### 1. A new application requests a database — uncovered here

Reason: carried over unchanged from the live delta of `provision-commerce-ops-database-in-the-shared-instance`. Covered, in the part a static read can reach, by `test_the_shared_instance_has_its_first_database.py`'s recipe classes; that change's own `test-plan.md` records which clauses are host state and why they are uncovered. Nothing in this delta changes any of it.

### 2. An application needs durable storage — uncovered here

Reason: carried over unchanged. Uncovered by that change's test plan too, with the reason recorded there: it is a rule for an application's choice of store, with no committed file here that would show it being obeyed.

### 3. An application's data divides into durable and non-durable parts — uncovered here

Reason: carried over unchanged. Covered by `test_the_shared_instance_has_its_first_database.py`'s `TestTheChangeRecordStatesTheTableDivision`, over that change's own record.

### 4. A staging database holds rehearsal data — uncovered here

Reason: carried over unchanged, and uncovered by that change's test plan for a reason this change does not alter: the THEN clauses are about how data is treated on a host, which no read of a committed file can observe.

### 5. The automation trigger has fired and the mechanism is not built — uncovered here

Reason: carried over unchanged. Covered by `test_the_shared_instance_has_its_first_database.py`'s `TestTheRequirementStatesTheTriggerHasFired` and `TestTheBacklogCarriesTheEntryTheRequirementNames`.

### 6. The document this requirement names holds the recipe — covered

The scenario this change adds, and the only one it owes tests for.

| Clause | Test | Classification |
|---|---|---|
| WHEN this requirement names a committed document as holding the manual provisioning recipe | `<M>.TestTheRequirementNamesOneDocumentForTheRecipe.test_the_requirement_names_exactly_one_markdown_document` | **specified** that a document is named; **derived** that it is exactly one, from the clause's singular "a committed document" |
| THEN that document SHALL hold it | `<M>.TestTheNamedDocumentHoldsTheRecipe.test_the_named_document_exists` | **specified** — a document absent from the repository holds nothing. Asserted separately so an absent document reports its own absence |
| THEN that document SHALL hold it | `<M>.TestTheNamedDocumentHoldsTheRecipe.test_the_named_document_holds_the_recipe` | **specified** |
| AND no other committed Markdown document outside `openspec/` SHALL hold a second copy of it | `<M>.TestNoSecondDocumentHoldsACopyOfTheRecipe.test_no_other_markdown_document_outside_the_specifications_holds_a_copy` | **specified** |
| AND … "outside `openspec/`" | `<M>.TestNoSecondDocumentHoldsACopyOfTheRecipe.test_the_sweep_does_not_reach_the_specification_directory` | **specified** — the bound is a property of the sweep, and it is what keeps the change records that quote the recipe as history from breaching the obligation on the day it lands |
| — (precondition) | `<M>.TestTheRequirementNamesOneDocumentForTheRecipe.test_the_requirement_is_resolved_from_exactly_one_source` | **derived** — tasks.md 3.5's resolution rule; without it every assertion below could pass having read nothing |
| — (precondition) | `<M>.TestTheRequirementNamesOneDocumentForTheRecipe.test_this_changes_record_exists_once_live_or_archived` | **derived** — the premise the resolution rule rests on: "while live" and "once archived" are two states, and a record in both layouts at once is neither |
| — (precondition) | `<M>.TestNoSecondDocumentHoldsACopyOfTheRecipe.test_the_sweep_reaches_the_committed_markdown_documents` | **derived** — the assertion above concludes from an EMPTY list, which a sweep that reached no file produces identically |

**Deliberately untested, with reasons:**

- **That an operator actually opens the named document.** What a static read reaches is the naming. Whether the document can be followed is this change's own ship-confirm observation (tasks.md 6.3).
- **That the recipe in the named document is correct** — an isolated role, a password never on a command line, the log settings pinned, each refusal branch. Those are `test_the_shared_instance_has_its_first_database.py`'s assertions, and they follow the recipe to whichever document holds it (tasks.md 3.1). Restating them here would put two modules in charge of one property.
- **That the named document holds exactly one copy.** The scenario forbids a second copy in another document; a second block inside the named one is that module's `test_the_document_carries_exactly_one_provisioning_block`, once re-pointed.
- **A document named under an extension other than `.md`.** The detector's candidate pattern reads Markdown paths, because the scenario's second clause bounds its population to Markdown and every document in `docs/` is one. A requirement naming a `.txt` yields no candidate and fails the exactly-one assertion loudly, which is the safe direction.

## How the document name is resolved, and why not the obvious way

Not through `requirement_sources()` in the sibling module, which reads the requirement from **every** live change's delta. While `provision-commerce-ops-database-in-the-shared-instance` is live it names `docs/bootstrap-a-new-host.md` where this change names `docs/onboard-an-application.md`, and a detector faithful to the scenario over both sources would demand that two documents each hold the recipe while forbidding a second copy — unsatisfiable.

`<M>.requirement_source()` implements the rule tasks.md 3.5 states instead: **this** change's delta while that delta is live, and the main specification once **this** change is archived; a live delta naming a document this change supersedes is not a source. A live change whose delta has lost the requirement returns nothing and fails loudly, rather than falling back to the main specification, which still names the superseded document. The change is located **by name** across the live and archived layouts, never by a written path into the changes directory, which this repository's citation check forbids.

Its bound, stated in the module: a **later** change modifying this requirement again is read only once it archives. That change's own test author lists these assertions as superseded, exactly as the obsolete list below does for its predecessors'.

## Discriminators

Every check in `<M>` is a static read, so a check whose target already carries the property passes having shown nothing about whether it can fail. Each detector is therefore also run over material the module supplies to falsify it. All fixture trees are temporary directories; every helper takes its root as an argument, which is what makes the negative cases exercisable without damaging the real tree.

- `<M>.TestTheResolutionRuleResolves` (5 tests). The interval the rule exists for, exactly as it stands today: another live delta of the same requirement naming the superseded document, the main specification naming it too, and this change's delta read in preference to both. The main specification read once this change is archived. A live delta that has lost the requirement not falling back. A tree carrying the requirement nowhere. The record found by name in both layouts.
- `<M>.TestTheNamingDetectorFires` (6 tests). A requirement naming the document yields it; naming none yields none; naming two yields both, reported rather than resolved; a specification citation and the backlog entry are not read as the recipe's document; a Markdown path in a sentence that does not speak of the recipe is not read; an emphasised sentence does not run into the next one — without the emphasis stripping, the divergence paragraph's bolded lead-in merges with the sentence naming `docs/backlog.md` and makes it a candidate.
- `<M>.TestTheCopyDetectorFires` (7 tests). The named document holding the recipe is found. A second Markdown document holding a copy is reported. Each of the three deliberate copy classes is **not** reported: a prose mention in inline code (`platform/README.md`'s shape), a fenced `CREATE ROLE pgexporter` block carrying no `CREATE DATABASE` (that same file's other block, the likeliest remaining false positive), a fenced copy inside a change record under `openspec/`, and a fenced copy inside a Python module of this suite (the sibling's three recipe fixtures, one an exact copy of the living recipe). A tree holding no Markdown document at all refuses rather than reporting a clean result.

**Observed red on real content, recorded here as the check discriminating on the property it exists to assert** — not on a fixture: the three tests under *Red at authoring*. No second record is owed once they go green; the ordinary suite result is the confirmation, read against this record.

Every discriminator above was written and **run** in this pass. None was owed and left unexecuted.

## Red at authoring, and expected to stay red until the implementation lands

The document the requirement names does not exist yet, and the recipe has not moved. Three tests are red, by design, and **no assertion was softened to make one pass**:

| Test | What its failure establishes now |
|---|---|
| `<M>.TestTheNamedDocumentHoldsTheRecipe.test_the_named_document_exists` | `docs/onboard-an-application.md` is absent. The absent-target state: the assertion never reached the recipe |
| `<M>.TestTheNamedDocumentHoldsTheRecipe.test_the_named_document_holds_the_recipe` | the documents that do hold a fenced provisioning block are `['docs/bootstrap-a-new-host.md']` — the requirement names a file the procedure has not reached |
| `<M>.TestNoSecondDocumentHoldsACopyOfTheRecipe.test_no_other_markdown_document_outside_the_specifications_holds_a_copy` | a real wrong value: `docs/bootstrap-a-new-host.md` still carries the recipe the requirement now names another document for |

All three go green when tasks 1.4 and 2.1 land — the recipe moved into `docs/onboard-an-application.md`, and stage 8 reduced to a pointer carrying no fenced block. The remaining 23 tests in `<M>` are green at authoring and expected to stay green.

The other 1210 tests in the suite are green and must stay so. `openspec validate --all` is unaffected by this file.

## Obsolete-test candidates

Searched **within `.github/tests/*.py` and nowhere else**, which is this change's dispatched test-path glob, using the earlier `test-plan.md` of `provision-commerce-ops-database-in-the-shared-instance` as a scenario-to-test map for the requirement this delta modifies. No implementation was read.

**Every entry is a candidate for human confirmation, not a conclusion.** Each names what supersedes it and the evidence the match was made on. Nothing here was edited, deleted or disabled by this pass, and the remedy for both entries is a **re-pointing that keeps every assertion** — not a deletion.

| Test | Superseded by | Evidence | Remedy |
|---|---|---|---|
| `test_the_shared_instance_has_its_first_database.RecipeMixin.recipe`, and through it every test in `TestTheRecipeIsReadAtAll`, `TestTheRecipeKeepsThePasswordOffCommandLines`, `TestTheRecipeRunsItsStatementsOverStandardInput`, `TestTheRecipeQuotesItsIdentifiers`, `TestTheRecipeGivesTheDatabaseToItsOwnRole`, `TestTheRecipeRefusesAnAlreadySetSecretName` and `TestTheRecipeCannotRegressSilently` | the delta's changed sentence: "each provisioning is performed by hand by an operator, by the recipe in `docs/onboard-an-application.md`" | that module's `BOOTSTRAP = ROOT / "docs" / "bootstrap-a-new-host.md"` (line 102) is the document every one of those tests reads through `RecipeMixin.recipe()`; the delta names another document, and after the move the constant points at a file holding no fenced provisioning block, so `recipe()` fails its own single-block precondition and every test in those seven classes errors | **Re-point the constant, keep every assertion** — this change's tasks.md 3.1, which also moves the module's prose and renames `BOOTSTRAP`. Superseded here is the *path*, never an assertion about the recipe. Deleting any of them would drop coverage this change does not replace |
| `test_the_bootstrap_documents_static_conventions.TestTheDocumentIsReadAtAll.test_the_document_carries_the_key_generation_commands`, and `TestEveryGeneratedKeyLandsInTheSshDirectory.test_no_ssh_keygen_writes_outside_the_ssh_directory` | not the delta, but this change's proposal and tasks.md 1.3 / 2.3: the application deploy key's `ssh-keygen` moves out of `docs/bootstrap-a-new-host.md` §0.3 into the new document | that module's `BOOTSTRAP` constant scopes both checks to the bootstrap document, and its docstring states the scoping is deliberate; the population they sweep loses the invocation that moves | **Widen to read the new document too, with a per-document anchor** — tasks.md 3.2 — and restate the `>= 6` floor's rationale without touching the figure — tasks.md 3.3. Listed here because a reader of this file must not mistake the narrowing for drift; it is not a deletion candidate |

**No other bearing test was found**, and the distinction matters: this is "none was found by this search", bounded to `.github/tests/*.py`, not "no such test exists". Specifically checked and found **not** to bear on the superseded document naming: `test_the_github_environments_are_named_for_their_stacks.py` (names the bootstrap document as the authoritative bootstrap procedure, for Environment creation), `test_the_platform_data_mount_moved.py`, `test_the_external_service_names_are_retired.py` and `test_the_retired_requirement_names_are_gone.py` (each carries `docs/bootstrap-a-new-host.md` as a **sweep anchor**, not as an exemption, so a repository-wide sweep reads the new document as soon as it is committed and no exemption is owed), and `test_environment_agnostic_pipeline.py` (uses the path as fixture text).

## Unresolved project questions

Recorded rather than resolved silently. This pass ran as a dispatched subagent with no channel to ask on.

1. **What counts as "the recipe" for the purpose of the second clause.** The delta does not define it mechanically. Assumption taken: a fenced code block carrying `CREATE DATABASE`, which is the sibling module's own `recipe_blocks()` — imported rather than reimplemented, so this suite has one definition of it. Answered in substance by this change's design.md decision 6, which names that keying and the `CREATE ROLE` false positive it excludes, but not by the delta itself. **Depends on it:** every test in `TestTheNamedDocumentHoldsTheRecipe`, `TestNoSecondDocumentHoldsACopyOfTheRecipe` and `TestTheCopyDetectorFires`. If a copy is ever written with the `CREATE DATABASE` spelled differently — a `psql` `\gexec`, an `ansible` module — this check does not see it.
2. **Whether the sibling module's helpers are stable enough to import.** `<M>` imports `recipe_blocks` and `requirement_block` from `test_the_shared_instance_has_its_first_database`, and `ROOT`, `ARCHIVE_SEGMENT` and `walked_files` from `test_ci_configuration`. Assumption taken: tasks.md 3.1 re-points a path constant and rewrites prose, and does not change those helpers. The suite's own audit permits a sibling import, and two modules on the trunk already do it. **Depends on it:** the whole module — a rename there is an import error here, which fails loudly rather than silently.
3. **The project's testing skill is `unittest`-shaped, and the library's `python` skill carries `pytest` idiom.** Resolved against the project rather than the skill: AGENTS.md names `python3 -m unittest discover --start-directory .github/tests` and the 25 modules already in that directory are the idiom `<M>` follows. Recorded because the floor obliges a project-specific question to be surfaced rather than assumed away.

## What no assertion in this pass establishes

That the recipe in the named document works, or carries any of the properties the sibling module asserts of it. That the new document can be followed by an operator. That a database exists on any host. Those are, in order: the sibling module's, this change's ship-confirm observation, and host state no read of a committed file can reach.
