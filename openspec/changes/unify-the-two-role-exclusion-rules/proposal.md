## Why

This repository decides, in four places and by two different rules, which directories under `ansible/roles/` are its own.

**The dot rule** — exclude any directory whose name contains a `.`, the Galaxy `namespace.role` convention — is in `role_names()` (`.github/tests/test_ci_configuration.py`), in `role_directories()` and the graph's edge filter (`ansible/scripts/select_molecule_roles.py`), and in `role_files_reaching_outside()` (`.github/tests/test_the_matrix_runs_the_roles_a_pull_request_owes.py`). Two of those document themselves as "the same rule `role_names()` uses".

**The manifest rule** — exclude the directory names that `ansible/requirements.yml`'s `roles:` entries resolve to — is in `galaxy_role_directories()`, added later by `pin-and-fix-molecule-suite`, and is what the pinning checks use.

**The dot rule tests for a naming convention and reports it as provenance**, and those come apart in both directions:

- **Vendored content the manifest does not pin, under a dotted name, is silently exempted.** A directory called `someone.somerole` that nobody pinned is not installed Galaxy content — it is content this repository is carrying, and the pinning obligation is exactly what should reach it. Every dot-rule site drops it.
- **Installed Galaxy content whose directory name carries no dot is treated as this repository's own.** That is not hypothetical: `_galaxy_directory_name()` already resolves a `src:`-only entry to a bare basename, and `test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name` already exercises `https://github.com/geerlingguy/ansible-role-docker.git,8.0.0` resolving to `ansible-role-docker`. Write today's one pin in that form and the two rules disagree about the directory the very next `ansible-galaxy role install` creates — and the selector would then feed somebody else's scenarios into the CI matrix.

**The specification asks for one enumeration and does not say which.** *The Molecule Matrix Runs the Roles a Pull Request Owes* (`openspec/specs/iac-cicd-pipeline/spec.md`) closes with: "The derivation and its closure SHALL be checked statically, by the checks that already read these scenario definitions, **under the same enumeration of this repository's own roles** — so that installed Galaxy content cannot make the check report one result on a provisioned developer machine and another on a runner that has installed nothing." Separately, *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* requires the pinning checks' exclusion be derived "from the manifest's own contents rather than from a hardcoded list of role names".

So the requirement that the enumeration be **shared** is explicit, and it is satisfied today only by coincidence; which rule the shared enumeration uses is not specified, and this change settles it on the manifest — the rule the other requirement already mandates next door, and the only one of the two that reads committed content rather than a naming habit.

**That shared enumeration is asserted by a live check**, `test_the_selectors_enumeration_agrees_with_the_suites_own`, which compares the selector's `roles_with_scenarios(ROOT)` with the suite's `roles_with_molecule_scenarios()`. Moving one side onto the manifest rule and not the other would not unify anything — it would relocate the disagreement across a file boundary, behind an assertion that goes red on a provisioned developer machine and stays green in continuous integration, which is the exact failure the clause above forbids. That is why this change reaches production code and not only the test suite.

**The disagreement is already being compensated for, in two places, locally.** `test_every_role_carrying_scenarios_contributes_at_least_one` subtracts `galaxy_role_directories()` from `roles_with_molecule_scenarios()` at its own call site; `own_role_names()` in `.github/tests/test_apt_index_staleness_bound.py` is `role_names() - galaxy_role_directories()` for the same reason. Both are correct and both are per-call-site patches over a helper that should not need patching. Three other call sites have nothing standing in front of them.

**Why it was not fixed where it was found.** `pin-and-fix-molecule-suite`'s subject was the pins. Unifying the rules means editing existing, passing tests, which is a change of its own rather than a rider on one — the reasoning `docs/backlog.md`'s `unify-the-two-role-exclusion-rules` entry records, and the reason it was deferred rather than declined.

**Nothing observable is wrong today**, and that is the argument for doing it now rather than the argument against. The single pinned role is `geerlingguy.docker`, which both rules exclude, so every site agrees on every directory that exists here and the suite is green under either rule. The disagreement becomes visible on the first directory they classify differently, and at that moment one of them is silently wrong about a real role — in a suite whose whole purpose is to be the thing that notices.

## What Changes

**One rule, in one form, in each of the two places that must hold it.** The selector is production code and cannot import the test suite; the test suite is what checks the selector. So there are two implementations of the manifest rule, bound by the agreement check that already exists for exactly this reason — which is the established shape here, not a compromise invented for this change.

### `.github/tests/test_ci_configuration.py`

- **`role_names()` derives its exclusion from `ansible/requirements.yml`**, through the existing `galaxy_role_directories()`, instead of from the dot in a directory name.
- **The hidden-directory guard stays.** `entry.name.startswith(".")` is not one of the two rules: it excludes `.git`-style directories, not installed content, and no manifest would name one.
- **`role_names()` and `roles_with_molecule_scenarios()` take `root`** like every other helper in this family, so the rule is exercisable against a fixture tree instead of only against whatever the real tree happens to hold. Today's tree is agnostic between the two rules, so a test that can only read it cannot tell them apart — which is how this survived review in the first place.
- **The manifest resolution moves into the *Repository access helpers* section**, where `role_names()` lives: a pure move of `GALAXY_MANIFEST`, `ManifestNotUsable`, `_galaxy_directory_name()` and `galaxy_role_directories()`, bodies unchanged. They stop being the pinning section's private business the moment the file's general role enumeration rests on them.
- **The local compensation is removed** and its docstring rewritten.
- **Tests are added** for the properties the unification creates, none of which the existing suite can observe.

### `ansible/scripts/select_molecule_roles.py`

- **`role_directories()` derives its exclusion from the manifest**, and gains the `startswith(".")` guard the dot rule gave it for free.
- **A manifest it cannot read is a `DerivationRefused`**, the refusal this module already raises for a scenario file it cannot read or parse — the same polarity, for the same reason: what this repository's roles are is then unknown, and an unknown answered silently is how a role stops being tested with nothing reporting.
- **The graph's edge filter stops testing for a dot.** `{edge for edge in edges if "." not in edge and edge != role}` becomes a test for membership in `role_directories(root)`, which is what the surrounding comment already says the filter is for: an external Galaxy role contributes nothing, and so does a literal naming no role directory at all. Left as a dot test, it would drop an edge to a vendored unpinned role that the new enumeration has just established *is* one of this repository's own.

### The three modules that import the helper

- **`.github/tests/test_apt_index_staleness_bound.py`**: `own_role_names()` loses the subtraction that is now a no-op, and the module docstring stops stating the dot rule as fact.
- **`.github/tests/test_the_matrix_runs_the_roles_a_pull_request_owes.py`**: the assumed-interface comment and `role_files_reaching_outside()` are brought onto the manifest rule. `test_a_dotted_role_directory_carrying_scenarios_is_not_discovered` is rewritten — its fixture, not its tracing: it stays SPECIFIED, because the SHALL text it traces to requires a shared enumeration and never mentions a dot. `test_the_selectors_enumeration_agrees_with_the_suites_own` keeps its assertion and gains a second one over a shared fixture root, since comparing the two implementations over `ROOT` alone cannot reach the case the change is about. `test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused` must pass **unaltered**, and is named here because it is the guard on the edge-filter change rather than something the change rewrites.
- **`.github/tests/test_the_hosts_own_name_is_set_by_the_converge.py`**: a plain call site with no prose about the rule; confirmed unaffected rather than assumed to be.

**One consequence is stated rather than discovered.** `role_names()` can now raise `ManifestNotUsable`. On a tree whose `ansible/requirements.yml` is missing, undecodable or unparseable, a test resting on it fails naming that file instead of carrying on against a silently different role set — in `setUp` as much as in a test method, since `unittest` routes by the exception's type and not by where it was raised. An earlier draft of this proposal claimed otherwise; see design.md decision 3, which records the correction and what prompted it.

### Not in scope

**The pinning checks are not touched.** `authored_scenario_files()`, `scenario_platform_images()`, `unpermitted_controller_reads()` and everything reading them already used the manifest rule and continue to, unchanged.

**`ansible-verify.yml`'s own role-discovery snippet.** It is shell in a workflow, with a third implementation of the enumeration, and it is left alone. It is not bound to the other two by any assertion — `test_the_workflow_names_no_role_literally` checks only that the workflow names no role literally — so leaving it does not put a check into disagreement with itself, which is what forced the selector into scope. **It does leave a third rule in the repository**, and that is a residue this change names rather than hides: a successor backlog entry is recorded for it, and the reason it is not folded in is that changing a workflow's shell discovery is a change to what CI runs, with its own failure modes, and not a rider on this one.

**No role, playbook, Compose file or specification is edited.** `ansible/requirements.yml` is read, never written.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None, and `.openspec.yaml` therefore carries `skip_specs: true` — the established form here and one of the two cases `AGENTS.md` names for it.

**The honest version of that claim, since this change does reach production code.** What the requirement obliges is that the enumeration be *shared*, and it is shared before this change and after it. Which rule the shared enumeration uses is not SHALL text, and the change does not make it SHALL text: it settles an implementation choice the specification left open, in the direction the neighbouring requirement already takes for the pinning checks.

**The enumeration returns the same set here**, which is the precise claim rather than the broad one: `geerlingguy.docker` is excluded by both rules, so the matrix selects the same roles, the suite discovers the same scenarios, and every check reports what it reported before.

**One reachable behaviour does change, and it is named rather than folded into that sentence.** The selector acquires a refusal it did not have: a pull request whose `ansible/requirements.yml` is missing or unparseable now fails the discovery job, naming the manifest, where today the selector never reads that file and each matrix row fails later at `ansible-galaxy role install`. That is better behaviour and it is a real change in what the pipeline reports. The matrix requirement is careful to enumerate its refusals — "Two refusals, over different sets" — and gives each a scenario; this would be a third with none. A delta carrying a refusal scenario for an unreadable manifest is therefore the defensible delta here, rather than one asserting the enumeration SHALL be manifest-derived. It is not written because the refusal is a consequence of where the rule now reads from rather than a decision taken about the pipeline's contract, because `openspec/specs/` is not the place to record which of two equivalent-on-this-tree implementations was chosen, and because the failure it produces is the same class the suite already produces for the same tree. The reasoning lives in this change's design.md, which is where `AGENTS.md` says it belongs. An operator who reads that differently should say so: the delta is cheap and the change would take it.

Because the change declares no deltas, it owes no independently derived tests under the exemption `AGENTS.md` states — only that the suite stays green. The tests listed above are not that exemption being quietly ignored: they are the change's own subject, since its substance is what these modules assert, and there is no implementation for them to be derived independently of.

## Impact

**Five files, in two trees.**

| File | What changes |
|---|---|
| `ansible/scripts/select_molecule_roles.py` | production: the enumeration, its refusal, the edge filter |
| `.github/tests/test_ci_configuration.py` | the helper, the moved block, one compensation, new tests |
| `.github/tests/test_the_matrix_runs_the_roles_a_pull_request_owes.py` | interface comment, one helper, two SPECIFIED tests' fixtures |
| `.github/tests/test_apt_index_staleness_bound.py` | one helper, one module docstring |
| `.github/tests/test_the_hosts_own_name_is_set_by_the_converge.py` | nothing expected; confirmed, not assumed |

**The merge runs the whole Molecule suite.** `select_molecule_roles.py` lives under `ansible/` deliberately — its own module docstring records why — so editing it is a trigger under `ansible-verify.yml`'s change filter and a path its attribution does not recognise, which widens the selection to every role. That is the correct blast radius for a change to what the selector selects, and it is roughly six minutes of hosted-runner time rather than a risk.

**The merge also converges every host, and this is the change's one outward-facing consequence.** `host-converge.yml` fires on `push` to `main` filtered on `ansible/**`, and `ansible/scripts/select_molecule_roles.py` is under `ansible/`. Its `converge` job declares `needs: [discover, publish]` and nothing else — the diff written to the job summary is a courtesy to a reader, explicitly not a condition — so a converge starts per stack whether or not anything a converge applies has changed. Nothing a converge applies **has** changed: not a role, not a playbook, not `group_vars`, not the inventory. The run is a re-application of the committed host configuration at the merge commit, and the expected result is a `PLAY RECAP` whose changed count matches an unchanged tree.

Whether each stack's job pauses for a human is a property of that stack's GitHub Environment protection rules — repository settings that no file here can verify, as the workflow itself says. Staging's Environment requires no reviewer, so staging converges unattended.

**This is why the pull request is opened as a draft.** A warning in a pull-request body does not stop a merge; a draft does. The operator undrafts it when they want the converge, rather than discovering it afterwards in a run they did not expect.

**Nothing deploys.** No path filter in `apply.yml` or `platform-deploy.yml` matches any of the five files, so no Terraform apply and no platform-stack deploy is raised.

**Records.** `docs/backlog.md`'s `unify-the-two-role-exclusion-rules` entry is deleted by the archive commit, as an entry is when its change is archived. Cited by slug, not by number: the backlog was renumbered two commits ago, and `AGENTS.md` cites entries by slug for that reason.

**Verification.** `python3 -m unittest discover --start-directory .github/tests` from the repository root, on a working tree with the pinned Galaxy role installed — load-bearing here rather than routine, since a tree without `ansible/roles/geerlingguy.docker/` cannot exercise the one directory every rule had to exclude. Baseline before any edit, on this change's working tree with the role installed: **1276 tests, OK**. Then the same suite with that directory absent, which is the state a runner is in. `pre-commit run --all-files` alongside both.

**Confirmation.** The effect is observable, and this change proposes an observation rather than reaching for a waiver — but the honest form of it is narrow, and the narrowness is the point.

The unified rule's behaviour is observable **in the suites themselves**, on fixture trees holding the directories today's tree does not: a dotted directory the manifest does not name, and a dotless directory it does. Those are the added tests, and each is confirmed to fail against the rule being replaced before it is trusted — a procedure design.md decision 6 specifies precisely, because the obvious version of it does not work: the pre-change `role_names()` takes no `root`, so a fixture test run against it raises `TypeError` and establishes nothing about which rule is in force.

What cannot be observed is any change in what the pipeline reports on *this* repository, because there is none: the tree is a fixed point of every rule involved, and the merge's green build establishes only that nothing regressed. That is stated rather than dressed up. If the operator judges the discrimination evidence to be a demonstration rather than a confirmation, this falls in the first waivable class — no observation can actually be made — and the successor named is the backlog entry for `ansible-verify.yml`'s third enumeration.
