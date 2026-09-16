The change edits its own verification, so two things shape the list below.

**A green suite establishes less here than usual.** Today's tree is a fixed point of both the rule being removed and the rule replacing it, so every test that existed before this change passes either way. Green means "nothing regressed" and never "the unification works" — which is why section 3 exists, and why the order within it is prescribed rather than convenient.

**The baseline is recorded before anything is edited**, on a working tree with the pinned Galaxy role installed. `ansible/roles/geerlingguy.docker/` is gitignored and per-working-tree, and it is the one directory every rule had to exclude — a tree without it cannot exercise the case the change is about. Baseline: `python3 -m unittest discover --start-directory .github/tests`, **1276 tests, OK**.

## 1. Move the manifest resolution into the shared helpers

- [x] 1.1 In `.github/tests/test_ci_configuration.py`, move `GALAXY_MANIFEST`, `ManifestNotUsable`, `_galaxy_directory_name()` and `galaxy_role_directories()` out of the `iac-cicd-pipeline` image-pinning section and into the *Repository access helpers* section, immediately above `role_names()`. Move the bodies verbatim: no renaming, no signature change, no reflow. `SCENARIO_GLOB`, `CONTENT_DIGEST` and everything from `authored_scenario_files()` onward stay where they are.
- [x] 1.2 Carry the provenance with the moved block — a comment naming `pin-and-fix-molecule-suite` as the change it was derived from and the requirement it traces to, in the citation form this repository requires (the requirement's own name plus `openspec/specs/iac-cicd-pipeline/spec.md`, never a path under `openspec/changes/`). Without it the move strands the block under a banner that says nothing about it.
- [x] 1.3 Adjust `ManifestNotUsable`'s docstring where it names the pinning check as the only thing the exclusion serves, and nowhere else. The failure polarity it describes is unchanged and its wording stays.
- [x] 1.4 Confirm the move changed no behaviour before going further: run the suite and expect the baseline's 1276 tests, OK. A move that alters a body shows here.

## 2. Thread `root`, with the dot rule still in place

This section deliberately changes no rule. It exists so that section 3's discrimination baseline is executable at all: run against a `role_names()` that takes no root, a fixture-based test raises `TypeError` and says nothing about which rule is in force (design.md decision 6).

- [x] 2.1 `role_names(root: Path | None = None)` and `roles_with_molecule_scenarios(root: Path | None = None)` in `test_ci_configuration.py`, resolving `base = ROOT if root is None else root` as the helpers beside them do, and passing `base` through. **Keep the dot exclusion exactly as it is.** Every existing call site passes nothing and must keep working unchanged.
- [x] 2.2 Run the suite: 1276 tests, OK, unchanged.
- [x] 2.3 Commit this state. Section 3's evidence is read against this commit, so it has to exist as a commit rather than as a moment.

## 3. Write the discriminating tests and record what they say about the old rule

Everything in this section is written against a fixture tree, because the real tree is agnostic between the rules. **Gated:** 3.1, 3.2, 3.3, and the *content* assertion of 3.3a — each is run against the commit from 2.3 (the dot rule, with `root` threaded), confirmed to **fail**, and its message recorded in the verification record. **Not gated:** 3.3a's *agreement* assertion, 3.4 and 3.5, which cannot discriminate between the rules for reasons each states in its own docstring. Nothing in this section falls outside those two lists.

- [x] 3.1 In `test_ci_configuration.py`, using `ScenarioTreeFixtureMixin`: a dotted directory the manifest does not name **is** this repository's own. This is the direction the old rule got wrong in a way that matters — unpinned vendored content silently exempted from a pinning obligation.
- [x] 3.2 Same module: a dotless directory the manifest **does** name is not this repository's own. Use the `src:`-only manifest spelling that `test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name` already uses, so the two tests are about the same resolution rather than about two inventions.
- [x] 3.3 In `test_the_matrix_runs_the_roles_a_pull_request_owes.py`, rewrite `test_a_dotted_role_directory_carrying_scenarios_is_not_discovered`. Its fixture `Tree` writes `MINIMAL_MANIFEST` (`roles: []`), so under the unified rule its dotted `vendor.theirs` is correctly discovered and the test as written would fail for the right reason — which is the discrimination evidence, and is recorded as such rather than patched away. Rewrite it as two cases: a role **named in the fixture manifest** is not discovered, and a dotted role the manifest does not name **is**. Keep it SPECIFIED: the SHALL text it traces to requires a shared enumeration and never mentions a dot, so the fixture changes and the tracing does not.

      **Do not change `Tree`'s signature to do it.** `Tree.__init__` hardcodes `MINIMAL_MANIFEST` and nothing else in the module wants that parameterised; overwrite the fixture's `ansible/requirements.yml` in the test body with the module's existing `write()` helper. Reshaping a fixture that thirty-odd tests depend on, to serve two, is a change to a module this one was not meant to reshape.
- [x] 3.3a Extend `test_the_selectors_enumeration_agrees_with_the_suites_own` to compare the two enumerations over a **shared fixture root** as well as over `ROOT` (design.md decision 2). Over `ROOT` the comparison cannot reach the case this change exists for: that manifest holds one `name:` entry, so the `src:`-basename resolution task 4.3 duplicates into production code would ship exercised by nothing while the suite's copy has a test of its own. Build one tree carrying a `src:`-form pin, a dotted unpinned directory and an ordinary role — **all three created with `tree.scenario(...)`, so that each carries a `molecule/` directory.** Both enumerations restrict to roles carrying scenarios, so a directory built with `role_dir()` alone drops out of both for a reason that has nothing to do with the manifest. The `src:` case would then be excluded correctly by accident, in both states, while the resolution this task exists to bind went unexercised — and the content assertion would still fail at 2.3 on the dotted case, so the gate would trip and report nothing amiss.

      **Two assertions, and the order in which they can fail is the point.** First assert the shared enumeration equals the manifest-correct set on that fixture — the ordinary role and the dotted unpinned directory, with the `src:`-pinned dotless directory excluded. Then assert the two implementations agree with each other.

      **The agreement half cannot discriminate and the content half can, so only the content half carries the gate.** At the 2.3 commit both implementations still apply the dot rule — section 2 touches `test_ci_configuration.py` alone — so they agree there, agree again after section 4, and disagree only in the window between tasks 4.1 and 4.3. An agreement assertion recorded as discrimination evidence would be an unfailable test trusted in the one section whose purpose is that no such test is trusted. The content assertion fails at 2.3 for the right reason: both sides answer with the dot rule, which excludes the dotted unpinned directory and admits the `src:`-pinned one — the two errors this change exists to remove, visible in one set.

      Fixture handling as in 3.3: overwrite the tree's `ansible/requirements.yml` with the module's `write()` helper, and do not change `Tree`'s signature.
- [x] 3.4 Property test, gate not claimed: the enumeration returns the same set on a tree that has installed the pinned Galaxy role and on one that has installed nothing — the requirement's own words for the checks it governs. Build both trees as `test_discovery_is_identical_with_and_without_installed_galaxy_content` does, rather than reading `ROOT`, which is in one state or the other and never both.
- [x] 3.5 Property test, gate not claimed: an unusable manifest fails the enumeration rather than widening it. `role_names()` raises `ManifestNotUsable` on a tree with no `ansible/requirements.yml`, and the selector's enumeration raises `DerivationRefused` on the same tree. Assert each exception names the file, as the pinning checks' equivalents do — the message is what tells an operator their tree is unprovisioned rather than their code broken.
- [x] 3.6 Annotate each new or rewritten test SPECIFIED or DERIVED per each file's convention and cite what it traces to. 3.3, 3.3a and 3.4 trace to SHALL text — 3.3a to the same clause as the test it extends, since a binding between the two implementations is what "the same enumeration of this repository's own roles" asks for. 3.1, 3.2 and 3.5 constrain the implementation beyond what a scenario states and are DERIVED, naming this change's design decisions.

## 4. Unify the rule

- [x] 4.1 `role_names()` — exclude `galaxy_role_directories(base)` instead of any name containing a `.`. Keep the `startswith(".")` guard and say in the docstring why it is not the rule being removed: it excludes hidden directories, not installed content.
- [x] 4.2 Say in the same docstring what the function now does when the manifest cannot be read — it propagates `ManifestNotUsable` rather than falling back — and why no fallback is available (design.md decision 3). Note there that a caller invoking it from `setUp` reports as an error rather than a failure, so the docstring does not promise a uniformity that does not hold.
- [x] 4.3 `ansible/scripts/select_molecule_roles.py`: give it its own manifest resolution and make `role_directories(root)` exclude what that returns, plus a `startswith(".")` guard the dot rule previously gave it for free. A manifest that is missing, unparseable, not a mapping, or carries an entry resolving to no directory name raises `DerivationRefused` naming `ansible/requirements.yml` and the entry — the refusal this module already raises for a scenario file it cannot read, for the reason its own `_documents` docstring gives. Resolve an entry by `name` where given, else the `src` basename with any version qualifier and `.git` suffix stripped, matching `_galaxy_directory_name()`; the two implementations are bound by the agreement test, not by shared code (design.md decision 2).
- [x] 4.4 Same file: replace the graph's edge filter `{edge for edge in edges if "." not in edge and edge != role}` with a test for membership in the role enumeration, and rewrite the comment above it, which currently explains the dot. Both properties it asserts stay true — an external Galaxy role contributes nothing, and a literal naming no role directory contributes nothing and is not refused — so `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` must still pass unaltered. If it needs altering, stop: that is a finding about decision 8, not a task to push through.
- [x] 4.5 Update `role_directories()`'s docstring, which claims the dot rule is "the same rule `role_names()` in `.github/tests` uses, and the same rule the workflow's own discovery uses". After this change the first half is true of a different rule and the second half is false — `ansible-verify.yml` keeps its own enumeration (design.md decision 2). Say both accurately.
- [x] 4.6 Remove the `- galaxy_role_directories()` term from `test_every_role_carrying_scenarios_contributes_at_least_one` and rewrite its docstring: it currently records that this file holds two rules and that the weaker one was left untouched, which is the state this change ends.
- [x] 4.7 `.github/tests/test_apt_index_staleness_bound.py`: reduce `own_role_names()` to `role_names()` — or drop it and call `role_names()` at its three call sites, whichever reads better — and rewrite the module docstring passage that states the dot rule as fact and explains the subtraction.
- [x] 4.8 `.github/tests/test_the_matrix_runs_the_roles_a_pull_request_owes.py`: bring `role_files_reaching_outside()` onto the manifest rule, and correct the assumed-interface comment for `roles_with_scenarios(root)`, which reads "under the same enumeration `role_names()` uses — dotted (Galaxy) directory names excluded". Correct the docstrings of `TestTheSelectorEnumeratesRolesLikeTheRestOfTheSuite` and `test_the_selectors_enumeration_agrees_with_the_suites_own`, both of which explain the agreement in terms of a dot in a directory name.
- [x] 4.9 `.github/tests/test_the_hosts_own_name_is_set_by_the_converge.py`: confirm it needs no edit. It imports `roles_with_molecule_scenarios` and calls it once with no argument, and carries no prose about the rule. Confirm rather than assume, and record the confirmation.
- [x] 4.10 Run the suite. The tests from section 3 now pass; every pre-existing test still passes, with the count unchanged from the baseline plus section 3's additions. **Any pre-existing test that changes verdict here is a regression, not progress** — today's tree cannot tell the rules apart, so a test that moves was reading something else.

      **One carve-out, by name.** `test_a_dotted_role_directory_carrying_scenarios_is_not_discovered` is a pre-existing test that legitimately changes verdict, which is why 3.3 rewrites it; it is exempt from the sentence above and from nothing else. There is no second exemption — if another pre-existing test moves, stop and find out why rather than adding it here.

## 5. Verification

- [x] 5.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, on the provisioned working tree, passing. State the count rather than "OK", so the record shows the additions ran.
- [x] 5.2 Run the same suite once with `ansible/roles/geerlingguy.docker/` absent, and confirm the result is identical. The suite runs on a runner that has installed nothing and on a developer machine that has, and this change moves every enumeration onto a rule that reads a file rather than a directory listing — so the two-state check is the one thing here that a fixture cannot stand in for.
- [x] 5.3 `pre-commit run --all-files`, passing. Note what it establishes about this change specifically: nothing beyond formatting and the hooks' own scope, since no hook reads a Python test for whether its assertion is the right one. `ansible-lint` and `--syntax-check` do reach `ansible/`, so they read the selector's syntax and nothing about its rule.
- [x] 5.4 `openspec validate --all`, passing, with `skip_specs: true` in place — the required pull-request check runs it and fails a change carrying no deltas without it.
- [x] 5.5 Record the successor in `docs/backlog.md`: `ansible-verify.yml`'s shell discovery is a third enumeration of this repository's own roles, left on its own rule by design.md decision 2. Write it as an entry in that file's established form, cited by slug.

## Verification record

**Baseline, before any edit**, on this working tree with `ansible/roles/geerlingguy.docker/` installed: `python3 -m unittest discover --start-directory .github/tests` — **1276 tests, OK**.

**1.4** After the move, 1276 tests, OK — unchanged, so no body moved with it altered. **2.2** After threading `root` with the dot rule still in place, 1276 tests, OK. **2.3** Committed as `a1f00d2`, which is the commit every gated assertion below was read against.

**Section 3 — the discrimination gate, run against `a1f00d2`.** Each gated assertion failed, and each failed for the reason it was written for rather than incidentally:

| Assertion | Failure against the dot rule |
|---|---|
| 3.1 dotted, unpinned, in `role_names()` | `Items in the first set but not the second: 'vendor.theirs'` |
| 3.2 dotless, pinned by `src:`, in `role_names()` | `Items in the second set but not the first: 'ansible-role-docker'` |
| 3.3 selector, dotted unpinned directory discovered | `Items in the first set but not the second: 'vendor.theirs'` |
| 3.3a content assertion, both enumerations over one tree | `'vendor.theirs'` missing **and** `'ansible-role-docker'` present, in one set |
| 3.5 selector, unreadable manifest | `DerivationRefused not raised` |

3.3a's content assertion is the one that shows both errors of the replaced rule at once, and it stops before the agreement assertion is reached — which confirms the plan's reasoning that agreement alone could not have discriminated: at `a1f00d2` both implementations still read the directory name and agree with each other while being wrong together.

**Two corrections to what the plan predicted, neither in the change's favour and both recorded rather than quietly absorbed.**

The plan classified **3.5 as a property test with the gate not claimed**. It discriminates: against `a1f00d2` the `role_names()` half fails with `ManifestNotUsable not raised` and the selector half with `DerivationRefused not raised`, because neither enumeration read the manifest at all under the old rule. The gate is therefore satisfied for it too, which is stronger than the plan claimed. The classification was conservative rather than wrong, and the stronger result is stated here rather than left to be rediscovered.

**3.4 is the only item in section 3 that genuinely cannot discriminate**, and it passed against `a1f00d2` exactly as the plan said it would. Its docstring says so in its own words, so a later reader is not left to infer that it establishes something about the rule.

**Section 4.** `test_a_role_directory_the_manifest_names_is_not_discovered` — 3.3's first case — also passes against `a1f00d2`, because its fixture role is dotted and the old rule excluded it too. It is the surviving half of the SPECIFIED test that was rewritten, and it is not evidence for this change; 3.3's second case is.

**4.9 — confirmed, not assumed.** `.github/tests/test_the_hosts_own_name_is_set_by_the_converge.py` imports `roles_with_molecule_scenarios` and calls it once with no argument, in one assertion about the `hostname` role; it carries no prose about the enumeration's rule. No edit was needed and none was made.

**4.10 / 5.1** `python3 -m unittest discover --start-directory .github/tests` — **1283 tests, OK**. That is the baseline's 1276 plus seven: four added to `test_ci_configuration.py`, and a net three in the matrix module, where one rewritten test became four. **No pre-existing test changed verdict**, which is what the section required.

**5.2 — the two-state run.** The same suite with `ansible/roles/geerlingguy.docker/` moved out of the tree: **1283 tests, OK**, identical to the provisioned run in count and result. This is the one check a fixture cannot stand in for, since the enumeration now reads a committed file rather than a directory listing.

**5.3** `pre-commit run --all-files` — every hook passes: `terraform fmt`, `tflint`, `terraform validate`, `gitleaks`, `ansible-lint`, `ansible-playbook --syntax-check`. What it establishes about this change is narrow and worth stating: `ansible-lint` and the syntax check reach `ansible/` and so read the selector's syntax, and nothing about its rule. No hook reads a Python test for whether its assertion is the right one.

**5.4** `openspec validate --all` — 10 passed, 0 failed, with the expected `skip_specs` INFO line.

### After the code review

The review returned four findings and no blocker. Three were applied; the fourth was recorded rather than fixed, for the reason the plan gave for not touching it.

**A claim this change wrote into two docstrings was false, and it came from the plan review rather than from the tree.** Round 2 of the plan review raised that `unittest` reports an `AssertionError` raised in `setUp` as an *error* rather than a failure. It was accepted without probing, written into design.md decision 3, the proposal and two docstrings, and survived two further plan-review rounds. It is wrong: `TestCase.run` routes by whether the exception is an instance of `failureException`, not by which part raised it. Probed on the pinned Python 3.12 — `setUp` and test method each give `errors=0 failures=1`. All four places corrected to say the property is uniform, and design.md records that it got it wrong rather than quietly restating it. **The lesson is the one this change is otherwise about:** a claim about behaviour is checked against the thing that behaves, and a reviewer asserting it is not that thing.

**A divergence the change had introduced without noticing.** `galaxy_role_directories()` guarded only `yaml.YAMLError`, so a manifest that `read_text` could not decode or open escaped as a raw `UnicodeDecodeError` or `OSError` — past the refusal `ManifestNotUsable` exists to deliver, and past this change's own promise that the message names the file. The selector's copy already covered both. That was survivable while the pinning checks alone reached this function and stopped being so when the whole suite's enumeration was put on it, which is this change's doing. Widened to match the selector, with two tests added: one per implementation, and the matrix-module one asserts **both** refuse the same undecodable manifest, which is the binding this change claims for the duplication. Bytes rather than `chmod`, since an unreadable file is readable to root.

**A dead import** of `galaxy_role_directories` in `test_apt_index_staleness_bound.py`, left when `own_role_names()` was reduced. Removed. Nothing in this repository's toolchain would have caught it: neither `ruff` nor `pyflakes` is installed here or run by any hook.

**Not fixed, recorded instead.** `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` filters graph targets with `if "." in target` — the heuristic this change removed — and passes today only because its fixture builds no dotted role directory. The plan required that test to pass **unaltered**, because it is the guard establishing that the edge-filter change is behaviour-preserving; editing it in the same change that changes the filter would have removed the evidence. Carried to `docs/backlog.md` beside entry 54, which asks the same question of the workflow.

**Re-verification after the fixes.** `python3 -m unittest discover --start-directory .github/tests` — **1285 tests, OK**, and identical with `ansible/roles/geerlingguy.docker/` absent. `pre-commit run --all-files` — every hook passes. `openspec validate --all` — 10 passed, 0 failed.

**What the reviewer checked that this record should not claim for itself.** Both guards the plan asked a reviewer to test were verified rather than inferred: each moved symbol was compared across revisions through its AST with docstrings stripped, and all four are executable-identical, so no body moved altered; and `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` is byte-identical across the diff. The review also reproduced the discrimination gate independently, by exporting `5dad086` and running the new classes against it — 3 of 4 and 3 of 6 failing, matching the table above.

### After the second review round

The round-2 verdict on the fixes above was clean: the widened `except` is right in scope (`UnicodeDecodeError` is a `ValueError`, not an `OSError`, so listing it separately was necessary rather than redundant), and both new tests were confirmed to discriminate by reverting the clause and watching them fail. One gap noted and accepted: the undecodable-manifest test exercises the `UnicodeDecodeError` half only, and nothing provokes the `OSError` half — a directory or dangling symlink fails `is_file()` first, and `chmod` proves nothing on a runner that is root.

**The round also carried findings from the background `code-review` skill, and one goes to this change's premise.** The manifest resolver — written by `pin-and-fix-molecule-suite`, and *promoted into production code by this change* — disagrees with `ansible-galaxy` on two entry spellings. Verified here against the installed Ansible 2.21.3 rather than taken from the report:

| entry | `ansible-galaxy` installs to | the resolver said |
|---|---|---|
| `- src: …/ansible-role-docker.git,8.0.0` | `ansible-role-docker.git` | `ansible-role-docker` |
| `- role: geerlingguy.docker` | `geerlingguy.docker` | refused the manifest |

`repo_url_to_role_name` strips `.git` from the trailing path segment and only *then* splits the comma, so where a version follows, the string does not end in `.git` at the moment the suffix is tested for and it survives. The resolver stripped the comma first — which reads more sensibly and names a directory that is never created, so a genuinely installed role would not be excluded and its scenarios would reach the matrix and the pinning checks. The `role:` spelling is one `role_yaml_parse` accepts, so refusing it fails the discovery job on a manifest Ansible reads without complaint.

**Both were fixed in both copies**, mirroring `repo_url_to_role_name`'s order and accepting all three spellings. A differential probe over thirteen entry shapes — `name:`, `role:`, bare `src:`, comma-qualified `src:`, `.tar.gz`, `git+`-prefixed, `scp`-style, and the string forms including the two-comma explicit-name form — now agrees three ways: Ansible, the suite's copy, the selector's copy, **13/13**.

**Three fixtures asserted the name Ansible would never create**, this change's own discriminating ones among them, and were corrected. Where a fixture's point is a *dotless* installed directory, the version is now given as its own key rather than after a comma — only that form resolves to `ansible-role-docker`, and with the comma the case stops being the one the test is about. The pre-existing `test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name` now asserts both forms and says why they differ.

**The check that would have caught this could not be written here, and that is recorded rather than worked around.** A test comparing the resolution against `RoleRequirement.role_yaml_parse` was written, and it failed two of this suite's own assertions: *The Suite Needs No Privileged or External Resource* requires the suite depend only on the standard library and on `.github/requirements-ci.txt`, which does not pin `ansible-core`. That check is AST-based and catches a lazy import inside a function as readily as a top-level one. The test was removed rather than the constraint weakened, and `docs/backlog.md` entry 55 carries the conformance check to the tier that already has the pinned Ansible.

**What this leaves standing, stated plainly.** Every expected value in these fixtures now matches what Ansible computes, verified in this session. None of it is *asserted against Ansible* by anything that runs — so the same class of error can recur, and entry 55 is what closes it. The binding between the two copies remains what it was: a guard against them drifting apart, and no guard at all against them being wrong together, which is exactly how this survived four rounds of plan review and a code review.

**One slip, caught and corrected.** Removing the ansible-importing test with a scripted slice cut backwards and duplicated ninety-five lines instead of deleting them. Caught by reading the diffstat and grepping for duplicate definitions, not by the suite — though the suite would have caught it too. Excised, the seam checked, the module re-parsed.

**Re-verification.** `python3 -m unittest discover --start-directory .github/tests` — **1285 tests, OK**, and identical with `ansible/roles/geerlingguy.docker/` absent. `pre-commit run --all-files` — every hook passes, `ansible-lint` and `--syntax-check` among them, which do read the selector. `openspec validate --all` — 10 passed, 0 failed. The selector's command-line entry point still loads.

## 6. Ship

- [x] 6.1 Commit the implementation and dispatch the code review over the committed diff, as `AGENTS.md`'s `build` stage requires. Give the reviewer two things explicitly: decision 7's guard — the moved block is read with `git diff --color-moved`, and a body altered under cover of the move is what to look for — and decision 2's scope argument, since the diff reaches production code and a reviewer is entitled to ask why.
- [x] 6.2 **Open the pull request as a draft**, once verification passes and the review has cleared, and say in its body what merging it does. A draft is the gate; a warning in a body is not, and this repository has already had a merge run past one. The operator undrafts it when they choose the window.

      **The merge runs the whole Molecule suite.** `select_molecule_roles.py` is under `ansible/`, so it triggers `ansible-verify.yml` and is a path the selector's own attribution does not recognise, which widens the selection to every role. That is the correct blast radius for a change to what the selector selects, and it is expected rather than a surprise to diagnose.

      **The merge also converges every host.** `host-converge.yml` fires on `push` to `main` filtered on `ansible/**`, and its `converge` job declares `needs: [discover, publish]` and no diff condition — the diff in the job summary is a courtesy to a reader, which that workflow says in as many words. Nothing a converge applies has changed, so each run is a re-application of the committed host configuration; staging's Environment takes no reviewer and so converges unattended, and whether production's pauses is a property of its Environment's protection rules, which no file here can verify. State all of that in the pull-request body rather than leaving the operator to derive it from a path filter.

      **Nothing deploys**: no filter in `apply.yml` or `platform-deploy.yml` matches any of the five files.
## Ship record

**6.1** The code review ran over the committed diff in two rounds. It verified both guards the plan asked it to test rather than infer: each moved symbol compared across revisions through its AST with docstrings stripped — all four executable-identical, so no body moved altered — and `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` byte-identical across the diff. It also reproduced the discrimination gate independently by exporting the test-only commit and running the new classes against it. Findings and their disposition are in the two sections above; the substantive ones were a false claim about `unittest` that this change had written into two docstrings, an unreadable manifest escaping the refusal, and the resolver's disagreement with `ansible-galaxy`.

**6.2** Rebased onto the freshly fetched trunk at `ed1b512` and opened as **pull request #214, a draft**, on 2026-09-15. Draft rather than a warning in the body, per the reason `docs/backlog.md`'s pre-merge-window entry records: a body does not stop a merge. The body states what merging does — a converge per stack, a full Molecule run, no deploy — and the operator undrafts it when they choose the window.

One thing noted in passing and deliberately not fixed: the trunk this rebased onto archived `correct-the-tfvars-parenthetical-that-names-labels`, which deleted backlog entry 49 and left a gap in a list the repository numbers without gaps. That is the archiving change's residue, not this one's, and renumbering here would put this change's diff across every entry below it for no reason of its own.

**6.2a — both converges read, and both are what this change asserted.** Pull request #214 merged as `f6251eb` at 22:47:30Z on 2026-09-15, read from the pull request's own state rather than from branch ancestry. It raised Host Converge run `35032682456`, whose four jobs — `discover`, `publish`, `converge (main-staging)`, `converge (main-production)` — all succeeded. Both recaps:

    main-staging     : ok=87  changed=0  unreachable=0  failed=0  skipped=20
    main-production  : ok=87  changed=0  unreachable=0  failed=0  skipped=20

`changed=0` is the expected result on an already-converged host, and it is the figure this change predicted: nothing a converge applies moved, because no role, playbook, `group_vars` file or inventory was touched. It is not the `changed=2` of check mode, which belongs to `drift.yml`.

**6.3 — confirmed, and by a better observation than the plan expected.** The plan anticipated offering the discrimination evidence alone and named the first waivable class as the fallback. No waiver was needed: the production code path ran for real.

**The selector derived a matrix through the changed code.** `Ansible Verify` run `35031712181` ran `select_molecule_roles.py` with the manifest-derived rule and selected exactly `deploy_user`, `docker`, `hardening`, `hostname`, `image_prune`, `ops_user`, `platform_data_volume`, `swap` — every role carrying scenarios that is this repository's own, with `geerlingguy.docker` excluded because `ansible/requirements.yml` names it and `tailscale` excluded because it carries no `molecule/`. All eight passed, and the `discover` job read the manifest without refusing, so the new read path executed rather than being reasoned about.

**The gated assertions discriminate**, as recorded above: each failed against `a1f00d2` and passes against its replacement, and the same suite ran green in continuous integration on a runner that has installed nothing.

**And the converges establish the absence of effect** the change claims for the hosts.

The operator accepted these as confirmation on 2026-09-15. What remains unobservable is unchanged and was never promised: no directory in this repository is classified differently by the two rules, so nothing here distinguishes them, which is why the discriminating cases live on fixture trees. Backlog entry 55 remains outstanding and is not a condition of this confirmation — it closes the *class* of defect the review found, not anything this change left broken.

- [x] 6.2a Read the converge runs the merge raises, before calling the change shipped. Each stack's `PLAY RECAP` is expected to show **`changed=0`**, which `docs/bootstrap-a-new-host.md` states as the expected result on an already-converged host. A non-zero `changed` means something a converge applies moved, which this change asserts did not, and is worth understanding before anything else. **It is not the `changed=2` of check mode** — that is `drift.yml`'s baseline, and `host-converge.yml`'s own header says so; this is a real converge and the two figures are not interchangeable. That document's "Hand the converge to the pipeline" stage carries the route for reading staging's log while production's job is still waiting for approval.
- [x] 6.3 **Confirmation.** The observation is section 3's discrimination evidence — its **gated** assertions failing against the rule being removed, at the commit from 2.3, and passing against its replacement — offered in place of anything observable on a host. Say gated assertions rather than "the new tests": three of section 3's six items cannot discriminate and are not evidence for this, and an operator handed the broader claim is being told more than the section establishes. There is nothing on a host to observe: the converges 6.2a reads confirm that the change moved nothing there, which is the absence of an effect rather than the presence of one. What the merge's green build establishes is only that nothing regressed, and that is stated rather than dressed up. If the operator judges this a demonstration rather than a confirmation, it falls in the first waivable class and the successor named is 5.5's backlog entry; record the waiver here either way.
- [x] 6.4 Bring the branch back to the freshly fetched trunk and archive the record, deleting `docs/backlog.md`'s `unify-the-two-role-exclusion-rules` entry in the same commit. Cite it by slug: the backlog was renumbered two commits ago and its numbers are not stable. Verify `openspec validate --archived` passes.

Branch and working-tree removal happen after the commit that writes this file, so they are recorded in prose rather than as tasks that could never be ticked in the file containing them.
