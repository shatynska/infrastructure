## Context

Four implementations of "which directories under `ansible/roles/` are this repository's own", two rules between them, and a repository on which they cannot be told apart. The decisions below settle which rule survives, what each survivor does when it cannot read the manifest, where the shared code lives, how far the change reaches, and how a test proves any of it on a tree whose single Galaxy role satisfies every rule at once.

Read alongside `pin-and-fix-molecule-suite`'s design.md, whose decision 3a established the manifest resolution and its failure polarity, and `select-the-molecule-matrix-per-role`'s design.md, whose decision 6 explains why the selector lives under `ansible/scripts/`. This change adopts both; it reopens neither.

## Decision 1 — the manifest rule survives, and the dot heuristic is deleted rather than kept alongside

Every surviving enumeration excludes `galaxy_role_directories(root)` — or, in the selector, its own equivalent — and nothing else.

The alternative of keeping both, excluding a directory that is either dotted *or* named in the manifest, was rejected: the union is the weaker classification of the two, and a dotted directory nobody pinned still drops out of it. A rule that is wrong in one direction is not made right by also being right in the other.

The reverse union — excluding only a directory that is both dotted and pinned — is worse: it reads the manifest and then second-guesses it with a naming convention, and would classify `ansible-role-docker` as this repository's own while `ansible-galaxy` is actively reinstalling it.

**What is lost by deleting the heuristic, stated so that it is a decision rather than an oversight.** The dot rule needed no file read and could not fail. The manifest rule reads `ansible/requirements.yml` and can. Decision 3 is where that is paid for, twice.

## Decision 2 — the change reaches the selector, because the alternative relocates the defect behind a live assertion

Scope covers `ansible/scripts/select_molecule_roles.py` as well as the test modules.

Confining the change to `.github/tests/` was the smaller diff and was rejected on evidence rather than on taste. `test_the_selectors_enumeration_agrees_with_the_suites_own` asserts set equality between the selector's `roles_with_scenarios(ROOT)` and the suite's `roles_with_molecule_scenarios()`, and traces to SHALL text requiring "the same enumeration of this repository's own roles, so that installed Galaxy content cannot make the check report one result on a provisioned developer machine and another on a runner that has installed nothing". Move one side and that assertion compares two rules: green in continuous integration, where nothing is installed, and red on a provisioned machine the first time a pin is written in `src:` form. A check that disagrees with itself between the two environments is what the clause forbids in its own words, and its own docstring calls "worse than no check".

So the choice was not between a small change and a large one. It was between unifying the rule and moving the disagreement to a place where a future pin turns it into an environment-dependent red, with the original defect — a Galaxy role reaching the CI matrix — still there underneath.

**Two implementations of one rule, not one shared implementation.** The selector is production code and cannot import `.github/tests`; the test suite is what checks the selector, so it cannot take the selector as its own authority for what the rule is without checking nothing. The binding between them is the agreement test that already exists for this reason, and decision 6 adds the fixture case that makes that test non-vacuous in continuous integration.

**The binding has to be widened, or it does not reach the case this change exists for.** `test_the_selectors_enumeration_agrees_with_the_suites_own` compares the two enumerations over `ROOT` alone, and `ROOT`'s manifest holds a single `name:` entry — so the `src:`-basename resolution, which is the shape the whole motivating example turns on, would ship duplicated into production code with nothing exercising the copy. The suite's copy has `test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name`; the selector's would have nothing, and the two could drift silently in the one direction that matters. Both enumerations take a root after this change, so the agreement test is extended to compare them over a shared fixture tree carrying a `src:`-form pin and a dotted unpinned directory. That turns decision 2's binding from a claim about one tree into a property the two implementations actually share, and it is what makes "two implementations" a design rather than a duplication.

**An agreement assertion alone would be unfailable at the commit decision 6 reads it against**, so the extended test carries a content assertion as well. Both implementations apply the dot rule at that commit and both apply the manifest rule after, so they agree in each state and disagree only in the window between the two edits — which makes agreement a permanent divergence detector and no evidence at all about which rule is in force. Asserting the *set* on that fixture is what fails at the baseline, for the reason that matters: the dot rule excludes the dotted unpinned directory and admits the `src:`-pinned one, both errors visible at once. The test carries both because the change wants both properties and one fixture supplies them.

**The third implementation is left alone**, and named. `ansible-verify.yml`'s shell discovery enumerates roles by its own rule. No assertion binds it to either of the other two, so leaving it puts no check into disagreement with itself — which is exactly the property that forced the selector into scope and that the workflow lacks. Changing a workflow's discovery is a change to what CI runs, with failure modes of its own, and it gets a backlog entry rather than a place in this diff.

## Decision 3 — a manifest that cannot be read fails, in each tree's own idiom, and the failure is not caught

Neither enumeration falls back to the dot heuristic, to an empty exclusion, or to the raw directory listing. Each fallback answers silently a question the code cannot answer, and they fail in opposite directions: an empty exclusion and the raw listing both hold installed Galaxy content to this repository's obligations, while falling back to the dot rule reinstates the rule being removed at exactly the moment nobody is watching.

**In `.github/tests`, `ManifestNotUsable` propagates.** `pin-and-fix-molecule-suite` made it an `AssertionError` subclass precisely so an unhandled one fails a test rather than erroring it.

**In the selector, it is `DerivationRefused`** — the refusal that module already raises for a scenario file it cannot read or parse, whose docstring gives the reason this case shares: a file that silently contributes nothing is how a role stops being tested with nothing reporting. The module's stated polarity, *to run rather than to skip*, is not in tension with this. That polarity governs a selection that is merely under-determined, where widening costs runner time; it has never governed a tree the module cannot read, which is what `_documents` refusing an unparseable scenario already establishes.

**This widens the blast radius of an unreadable manifest** from the pinning checks to every test resting on `role_names()` and to the selector itself. That is intended: a missing `ansible/requirements.yml` is an unprovisioned or damaged tree, not a condition under which some checks should carry on quietly.

**It is not a new class of fragility.** `authored_scenario_files()` already raises on the same condition and is read by the scenario-discovery, image-pinning and controller-read checks, so such a tree already failed this suite loudly. What changes is which checks carry the message — and, in the pipeline, when: a pull request breaking `ansible/requirements.yml` now fails the selector's discovery job rather than each matrix row's `ansible-galaxy role install`. That is a reachable change in what CI reports, and the proposal names it rather than letting "nothing observable moves" cover it.

**The selector's new read is safe against the fixture trees that already exist, contingently.** Two step-body tests in the matrix module build scratch trees carrying no `ansible/requirements.yml`, which would meet the new refusal. They do not, because `_discovery_steps` prefers `ansible-verify.yml`'s own shell `discover` step over the `select` step, and the workflow has both. That is a property of the workflow's current shape rather than of this change: folding the shell discovery into the selector step — which the backlog successor from decision 2 might well propose — would make those fixtures start meeting the refusal. Stated here so that whoever takes that successor meets the coupling as a recorded consequence rather than as a mysterious red.

**The `AssertionError` property is uniform, and an earlier draft of this document said it was not.** The plan review raised, and this design accepted without checking, that an `AssertionError` raised in `setUp` is reported by `unittest` as an *error* rather than a failure — which would have mattered, since several inheriting call sites call the enumeration in `setUp`. It is false. `TestCase.run` routes a raised exception by whether it is an instance of `failureException`, never by which part of the test raised it; probed on this repository's pinned Python 3.12, an `AssertionError` subclass raised in `setUp` and one raised in a test method both report as one failure and zero errors. The code review caught it, the probe is reproducible in four lines, and the docstrings that had carried the claim were corrected rather than softened. Recorded here because a design document asserting a property of the test runner should say when it got one wrong.

**What the read path costs, which is the real non-uniformity and was found in the same review.** `galaxy_role_directories()` guarded only `yaml.YAMLError`, so a manifest that `read_text` could not decode or open raised `UnicodeDecodeError` or `OSError` raw, past the refusal this class exists to deliver. Survivable while the pinning checks alone reached it; not once the whole suite's enumeration does. The selector's copy already covered both, so the narrow guard had the two implementations answering differently on the one input neither can read. Widened to match, with a test that asserts both refuse it.

## Decision 4 — `root` is threaded through, because the real tree cannot discriminate between the rules

`role_names(root=None)` and `roles_with_molecule_scenarios(root=None)` default to `ROOT` exactly as `galaxy_role_directories()` and `authored_scenario_files()` already do. Every existing call site passes nothing and is unaffected. The selector's helpers already take `root` and need no change of shape.

This is not tidiness. The repository's one pinned role is `geerlingguy.docker`: dotted *and* in the manifest, so every rule returns the same set for every directory that exists here. A test that can only read `ROOT` therefore passes identically against the code being replaced and the code replacing it, which is the definition of a test that establishes nothing. The discriminating cases exist only on a fixture tree, and both suites already build those — `ScenarioTreeFixtureMixin` in `test_ci_configuration.py`, `Tree` in the matrix module, whose `__init__` already writes an `ansible/requirements.yml`.

## Decision 5 — every dead compensation is removed, in both modules that carry one

`test_every_role_carrying_scenarios_contributes_at_least_one` reads `roles_with_molecule_scenarios() - galaxy_role_directories() - discovered_roles`; `own_role_names()` in the apt module is `role_names() - galaxy_role_directories()`. Both middle terms become no-ops once the enumeration excludes the manifest's directories itself, and both are deleted.

A subtraction that cannot change the result looks like a live guard to the next reader and has to be explained by prose that no longer describes the code. Worse, it is the one thing that would keep a test green if the enumeration were later reverted to the weak rule — which makes it the opposite of a safety net: it hides exactly the regression this change exists to prevent. That argument was written for the in-file case and transfers unchanged to the other module, which is why both go rather than one.

Their surrounding prose goes with them. The apt module's docstring states the dot rule as fact and explains the subtraction; the in-file docstring records that this repository holds two rules and that the weaker was left untouched. Both are accurate descriptions of the state this change ends.

## Decision 6 — the new tests are proven to discriminate, by a procedure that is executable

Each added test is run once against the pre-change enumeration and confirmed to fail, and the failure recorded in `tasks.md`. A test written against a fixture tree that happens to pass under both rules is worth nothing here, and on this change that is the likely failure rather than a remote one: the whole difficulty is that the obvious tree does not discriminate.

**The obvious way to run that baseline does not work, so the order is specified.** The pre-change `role_names()` has signature `role_names() -> set[str]` and ignores a root entirely, so a fixture-based test run against it raises `TypeError` — which is a test failing for the wrong reason, and recording it as "confirmed to fail" would be exactly the worthless evidence this decision exists to prevent. The threading of `root` therefore lands **first, with the dot rule still in place**; the new tests are written and run against *that* state, where a failure is a statement about the rule; and only then does the rule change. Two commits, in that order, so the evidence is reconstructable from the history rather than only from a note.

**A property test that cannot discriminate is not subject to the gate, and says so.** The provisioned-versus-unprovisioned equivalence holds under both rules on any tree whose Galaxy role is dotted *and* pinned, which is every tree either rule was ever run against. It is worth asserting — it is the property the requirement states in its own words — but it is recorded as a property test rather than as discrimination evidence, and the gate is not claimed for it.

This is `AGENTS.md`'s testing standard applied rather than a local invention: a baseline recorded before the claim, and a failing state observed rather than assumed.

## Decision 7 — the manifest resolution moves up into the shared helpers, as a pure move

`GALAXY_MANIFEST`, `ManifestNotUsable`, `_galaxy_directory_name()` and `galaxy_role_directories()` move from the `iac-cicd-pipeline` image-pinning section into the *Repository access helpers* section at the top of `test_ci_configuration.py`, bodies and docstrings unchanged except where a docstring names the pinning check as its only consumer.

Python resolves a module-level name at call time, so leaving them below `role_names()` would work. It would also leave the file's most general helper depending on a block introduced by a banner scoping it to one requirement of one capability, with no reason for a reader arriving at `role_names()` to look 780 lines further down for the rule it applies. Section banners are not decoration in this file — each names the change it was derived from — so a helper that has outgrown its section is moved rather than annotated.

**The provenance is carried, not discarded**: the moved block keeps a comment naming `pin-and-fix-molecule-suite` and the requirement it traces to, so nothing the old banner supplied is lost.

**Reviewing a move is a known cost, paid deliberately.** `git diff --color-moved` reads it, and the tests exercising those helpers are untouched, so a body altered under cover of the move shows as a test failure rather than only as a reading error. That is the guard being relied on, named so a reviewer can check it rather than infer it.

## Decision 8 — the selector's edge filter stops testing for a dot

`graph[role] = {edge for edge in edges if "." not in edge and edge != role}` becomes a test for membership in the role enumeration.

This is a *fourth* dot-rule site and a different kind from the other three: it filters role names written in YAML, not directory names on disk. It is in scope because leaving it would make the change internally inconsistent in the one direction it cares about. A `meta/main.yml` dependency on a vendored, unpinned, dotted role would be dropped from the graph by the dot filter — while the enumeration this change installs has just established that such a role *is* one of this repository's own, and therefore one whose changes the matrix owes.

Membership is what the surrounding comment already says the filter is for: an external Galaxy role "contributes nothing and is not a refusal", and a plain literal naming no role directory at all likewise contributes nothing and is likewise not refused. Both remain true under membership, which is why `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` — the one test covering either of them; the typo case is described in that comment and asserted by nothing — keeps passing rather than being rewritten to suit.

**One thing does change, and the reason it is inert is given rather than asserted.** An edge to a dotless literal naming no role directory goes from kept-and-inert to dropped. It was inert because `reverse_closure` only ever compares a target against graph *keys*, and `attribute` only ever seeds from `role_directories(root)` — so both ends of any comparison are drawn from the enumeration, and a target outside it can never be reached however long it sits in the graph. Dropping it removes a value nothing could read. A reviewer meeting task 4.4's instruction to stop if a guard test needs altering should have this argument in hand, so that a real finding is distinguishable from this one.

## Open questions

**None blocking.** The residue is recorded rather than left implicit: `ansible-verify.yml`'s shell discovery is a third enumeration, unbound by any assertion, deliberately out of scope per decision 2, and carried to `docs/backlog.md` as a successor entry.
