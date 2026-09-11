# Test plan — `cache-the-apt-index-within-a-converge`

Derived from this change's delta specification by an author other than whoever
implements it, before any implementation existed. Read this before implementing:
it records the interfaces the tests assume, the classification of every
assertion, and what deliberately has no test.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among `openspec instructions apply`'s context files and must be opened on
purpose.

**This pass adds tests and never subtracts.** No existing test file was edited,
deleted or disabled. The two Molecule scenario files were extended by insertion
only — `git diff --numstat` reports `145 / 0` and `125 / 0`, insertions and
deletions — and no existing line of either was altered.

---

## Baseline

| Suite | Command | Result |
|---|---|---|
| `.github/tests` | `python3 -m unittest discover --start-directory .github/tests` | **634 tests, OK**, taken before any file was written |
| `hardening` Molecule | `ansible/scripts/run-molecule test --all` from `ansible/roles/hardening` | **Not run.** See below. |

The Molecule baseline was **not taken**, and the reason is recorded rather than
worked around: a full `molecule test --all` for this role costs a container and
upwards of fifteen minutes under the degraded archive this change exists to
respond to, and it establishes nothing this pass needs — the scenario is green on
the trunk, and the assertions added here are new. What *was* exercised instead is
the part of this pass a green suite could not vouch for: the back-dating fixture's
mechanics, against the digest the scenario pins. See *The fixture was exercised*
below.

**One pre-existing failure surfaced during this pass and is not caused by it.**
`test_ci_configuration.TestEveryComposeFileDeclaringAServiceImageIsCovered`
`.test_every_compose_file_declaring_a_service_image_is_covered` goes red as soon
as this working tree is provisioned: `.molecule-home/collections/` acquires six
Compose files belonging to `community.docker` and `community.general`, the
walker behind that check does not prune `.molecule-home/`, and every reported
path sits under it. It was green at the baseline above, at a moment when
`.molecule-home/` did not yet exist in the tree. It is the same class of defect
this change's own `tasks.md` 1.5 warns about — a check that disagrees with
itself between a provisioned working tree and continuous integration — and it is
reported rather than fixed, being outside this change.

---

## Assumptions — the interfaces the tests are written against

The implementation does not exist yet, so three names had to be invented. **They
are stated here so the implementation can be written to them rather than around
them.** None traces to the delta; the delta names an obligation, not an option
and not a register.

| Assumed name | Where it must exist | Which tests depend on it |
|---|---|---|
| `hardening_apt_cache_valid_time` | `ansible/roles/hardening/defaults/main.yml`, referenced from both `apt` tasks in `ansible/roles/hardening/tasks/main.yml` as `cache_valid_time: "{{ hardening_apt_cache_valid_time }}"` | `converge.yml`'s first assertion; `test_every_declared_bound_is_a_role_variable_carrying_a_default` |
| `hardening_ufw_install` | the `register:` on `hardening`'s **first** `apt` task (`ufw`) | `converge.yml`'s first assertion; `verify.yml`'s bound-refresh assertion |
| `hardening_fail2ban_install` | the `register:` on `hardening`'s **second** `apt` task (`fail2ban`) | `converge.yml`'s second assertion |

`image_prune`'s bound variable name is **not** assumed by any test. The static
checks read whatever name that role's task file references and require only that
it be defaulted in that role's own `defaults/main.yml`, and that the role use one
name rather than several. `tasks.md` 2.2 asks for it to be named consistently
with `hardening`'s so a reader sees the two are one judgment; nothing here
enforces that, and it is worth doing anyway.

Two further properties the tests rest on, which are **not** free choices:

- `hardening`'s `converge.yml` must keep invoking the role through `roles:`.
  That is what puts the role's defaults in the play's scope, which is what lets
  the first assertion read `hardening_apt_cache_valid_time`. Under `include_role`
  it would need `public: true`, and without it the assertion fails on an
  undefined name pointing at the expression rather than at the cause.
- `update_cache` must stay on all three tasks. The bound is being added to the
  option, not substituted for it.

---

## Scenario coverage

Seven `#### Scenario:` blocks in the delta. Seven accounted for, none twice.

| # | Scenario | Covered by | Row |
|---|---|---|---|
| 1 | A second install task in the same converge does not re-fetch | `ansible/roles/hardening/molecule/default/converge.yml` → *Assert the second bounded apt task in the same converge did not re-fetch the index* | Molecule |
| 2 | An install on a host with no record of a fetch still fetches | `ansible/roles/hardening/molecule/default/converge.yml` → *Assert the first bounded apt task fetched exactly when the recorded index age was outside the role's bound* | Molecule |
| 3 | An index older than the bound is refreshed | `ansible/roles/hardening/molecule/default/verify.yml` → *Assert the first bounded apt task refreshed an index older than the bound* | Molecule |
| 4 | A pinned-version install declares no bound | `test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed.test_a_pinned_version_apt_task_declares_no_bound` | `.github/tests` |
| 5 | An install from a source the same run added declares no bound | `test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed.test_an_apt_task_installing_from_a_same_run_source_declares_no_bound` | `.github/tests` |
| 6 | The bound is a variable, not a literal per task | `test_apt_index_staleness_bound.TestTheBoundIsARoleVariableRatherThanALiteral.test_every_declared_bound_is_a_role_variable_carrying_a_default` | `.github/tests` |
| 7 | A test fixture play is not held to the bound | `test_apt_index_staleness_bound.TestFixturePlaysAreNotHeldToTheBound.test_a_prepare_play_may_refresh_unconditionally` | `.github/tests` |

The requirement's **positive SHALL** — the sentence the scenarios sit under — is
not itself a scenario and so appears in no row above. It is covered all the same,
by `TestTheBoundIsDeclaredWhereItIsOwed.test_every_qualifying_own_role_apt_task_declares_a_bound`,
and without it the requirement could regress silently in the one direction the
change exists to establish: `image_prune`'s single bound is asserted by no
Molecule scenario of this change.

**Runner-selectable names.** Every static test above is selectable individually,
run from the repository root:

    python3 -m unittest discover --start-directory .github/tests \
        --pattern 'test_apt_index_staleness_bound.py'

    # one class or one method, via discovery's sys.path:
    python3 -m unittest test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed
    python3 -m unittest \
        test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed.test_a_pinned_version_apt_task_declares_no_bound

(the last two need `.github/tests` on `sys.path`; discovery puts it there, or
`PYTHONPATH=.github/tests` does.)

The Molecule assertions are selectable only at scenario granularity, which is all
that row of the test table offers:

    ansible/scripts/run-molecule test -s default   # from ansible/roles/hardening

---

## Assertion classification

### Molecule — `ansible/roles/hardening/molecule/default/converge.yml`

| Assertion | Class |
|---|---|
| First bounded apt task's `cache_updated` **equals** whether the recorded last-fetch time was outside the role's bound | **SPECIFIED** — scenario 2, stated as the requirement's own biconditional so it holds on both passes of a play Molecule runs twice |
| Second bounded apt task reported `cache_updated: false` | **SPECIFIED** — scenario 1 |
| `hardening_ufw_install` / `hardening_fail2ban_install` are defined and carry `cache_updated` | **DERIVED** — a channel precondition, not a requirement. Without it an absent register fails as an undefined-variable error pointing at the expression rather than at the missing `register:` |
| The pre-task recording the last-fetch time reproduces the apt module's three branches (success stamp → lists directory → epoch) | **DERIVED** — `design.md` Decision 1's reading of the module, not delta text |
| The comparison instant is recorded alongside the mtime rather than read at assertion time | **DERIVED** — `tasks.md` 1.1 |

### Molecule — `ansible/roles/hardening/molecule/default/verify.yml`

| Assertion | Class |
|---|---|
| The bound-overridden invocation's first apt task reported `cache_updated: true` | **SPECIFIED** — scenario 3 |
| `/var/lib/apt/lists` exists before the fixture back-dates it | **DERIVED** — a fixture precondition; without it the assertion after would pass or fail for a reason unrelated to the bound |
| Emptying the directory, restoring `partial/`, then back-dating — in that order | **DERIVED** — `design.md` Decision 1 and `tasks.md` 1.4; the two other back-dating forms do not move the mtime the module reads |

### `.github/tests/test_apt_index_staleness_bound.py`

| Assertion | Class |
|---|---|
| Every qualifying own-role apt task declares a bound | **SPECIFIED** — the requirement's SHALL |
| A pinned-version apt task declares no bound | **SPECIFIED** — scenario 4 |
| An apt task following a same-file write under `/etc/apt/sources.list.d/` declares no bound | **SPECIFIED** — scenario 5 |
| Every declared bound is a `{{ variable }}` reference, not a literal | **SPECIFIED** — scenario 6 |
| That variable is defaulted in **that role's** `defaults/main.yml` | **SPECIFIED** — scenario 6's "a variable of that role carrying a default" |
| A role declares its bound through exactly **one** variable | **SPECIFIED** — scenario 6's "in one place", read as one place *per role*, which is how `tasks.md` 2.2 reads it too |
| No Molecule play is inside the file set the checks above read, and at least one fixture play declares `cache_valid_time: 0` unreported | **SPECIFIED** — scenario 7 |
| Non-vacuity preconditions: the qualifying set, the pinned set and the same-run-source set are each non-empty | **DERIVED** — each names a way the check could report success having examined nothing |
| `TestThePredicatesAreARealReadOfATaskFile` — nine assertions over synthetic fixture text | **DERIVED** — traces to no scenario. Every real-file check above is red until the change is implemented, so nothing else establishes that they would go *green* on a conforming shape or stay red on the specific defects they name. The idiom is this suite's own |

### Two scoping judgments, recorded because they are judgments

**The positive obligation reaches every qualifying apt task that installs a
package, whether or not it also declares `update_cache`.** The narrower reading —
that only tasks re-fetching unconditionally today are obliged — is satisfiable by
*deleting* `update_cache` rather than bounding it, which is a regression that
passes. Today the two readings select the same three tasks: every apt task in
this repository's own roles declares `update_cache: true`.

**A `deb:` install counts as pinned.** It names an exact artifact, so an index
older than it resolves to nothing for the same reason a named version does. No
such task exists here; the rule is stated so a future one is not silently
obliged.

---

## Deliberately untested

- **The bound's value.** The delta makes no normative claim about how many
  seconds is right, so nothing here guards the hour `design.md` Decision 2 chose.
  `converge.yml`'s first assertion is self-referential against the role's own
  bound variable on purpose, and `verify.yml`'s back-date distance is a literal
  (1970) because the role's bound is not in scope ahead of a non-`public:`
  include — so that assertion catches an **absurd** default, one longer than
  fifty-six years, and not a merely wrong one. Stating this plainly beats
  implying a check that does not exist.
- **The same-run-source rule across files.** The static check reports an apt task
  as installing from a same-run source only when an earlier task **in its own
  task file** writes under `/etc/apt/sources.list.d/`. A source written by
  another file of the same role, by a preceding role in the same play, or by a
  playbook outside `ansible/roles/` is outside its reach — and such an install
  would be reported as qualifying and required to carry a bound it must not
  carry. This is a real gap, not a completeness claim.
- **`apt_repository`'s `filename:`.** It is a bare name rather than a path, so a
  destination-keyed read does not see it. `TestThePredicatesAreARealReadOfATaskFile`
  asserts that gap explicitly, so it is a decision rather than a surprise.
- **`include_tasks` / `import_tasks`.** The walker does not follow them. A task
  file reached only through one is still read on its own when the enumeration
  reaches it, so no task is missed; what does not cross the include is "an
  earlier task in the same file".
- **`image_prune`'s bound, behaviourally.** `tasks.md` 3.3 deliberately gives that
  task no register, so no scenario of that role can observe whether it fetched.
  What covers it is the positive static check alone. This is the plan's decision,
  not this pass's.
- **What the idempotence pass stops exercising.** `design.md` Decision 3 records
  that after this change the idempotence re-run no longer performs a second
  fetch. That is a reduction in what the suite observes, accepted and argued
  there; no test is added to preserve it, and none is removed on its account.
- **`tailscale`'s behaviour.** The role carries no Molecule scenario, so nothing
  in this project observes what it does to a host (`docs/change-queue.md` entry
  3b owns that gap). Scenarios 4 and 5 are established against it statically, and
  that is the only mechanism available.

---

## Obsolete tests

**Not applicable, with that reason: this change's delta carries no `MODIFIED`,
`REMOVED` or `RENAMED` operation.** It is a single `ADDED` requirement against
`iac-host-configuration`, so no existing requirement is superseded and no
existing test can be retired by it.

A bounded search was made all the same, within the two dispatched test-path
globs and nowhere else, and it found **no bearing test in either direction**:

- `.github/tests/*.py` — no committed module mentions `cache_valid_time`,
  `update_cache`, or apt-index freshness in any form. Searched by text across all
  nine pre-existing modules. **No such test exists**, as opposed to none having
  been found.
- `ansible/roles/*/molecule/*/` — ten own-role `prepare.yml` files declare
  `cache_valid_time: 0`. **None is obsolete**: they are fixture setup, the delta
  exempts them by name in scenario 7, and the change's `proposal.md` and
  `design.md` Decision 5 both keep them as they are. They are recorded here
  because a reader scanning for the option will find them and should not mistake
  them for candidates.

One item is **not** an obsolete-test entry but is adjacent enough to state: the
eleventh file carrying `cache_valid_time` is
`ansible/roles/geerlingguy.docker/molecule/default/converge.yml`, which is
gitignored Galaxy content. It is outside every check added here, by the role
enumeration rather than by a path exclusion — and it is the concrete instance of
the disagreement `tasks.md` 1.5 and 1.6 warn about.

---

## Unresolved project questions

The project's conventions (`AGENTS.md`, `CLAUDE.md`) were read. Three questions
arose that they do not answer; each is recorded with the assumption taken and
the tests that depend on it, since a dispatched author has no channel to ask on.

1. **Which module in `.github/tests` should hold a new change's assertions?**
   `AGENTS.md` names the suite and its subject but not its internal layout.
   *Assumption:* a new module per change, following
   `test_the_suite_is_triggered_by_what_it_reads.py`, which was written by the
   same kind of pass and says in its own docstring why it is a separate file.
   *Depends on it:* all twelve tests in
   `.github/tests/test_apt_index_staleness_bound.py`. Moving them into
   `test_ci_configuration.py` later costs nothing but an import.

2. **Whether a "predicates against fixture text" class is wanted for every new
   static check, or only where the repository has already done it.**
   `test_ci_configuration.py` does it in `TestTheLivenessChecksAreARealReadOfTheFile`
   and states the reasoning; `AGENTS.md` does not generalise it.
   *Assumption:* wanted here, because every real-file assertion in this module is
   red until the change is implemented, and a check that can only fail is worth as
   little as one that can only pass.
   *Depends on it:* `TestThePredicatesAreARealReadOfATaskFile` (nine assertions).
   It reads no committed file and passes from the moment it was written, which is
   the opposite of the rest of the module — recorded so its passing is not
   mistaken for coverage of the change.

3. **Whether a non-vacuity precondition may fail the suite when its subject
   legitimately disappears.** Three checks here assert their own subject is
   non-empty — that some apt task qualifies, that some install is pinned, that
   some fixture play refreshes unconditionally. If the last pinned install is
   ever removed, that check goes red for a reason that is not a defect.
   *Assumption:* a hard failure, not a skip, matching this suite's own stated
   position that a check which does not run reports success for a property
   nothing examined. Each message says what to do instead of relaxing it.
   *Depends on it:* the three preconditions named above.

---

## The fixture was exercised

The riskiest thing in this pass is `verify.yml`'s back-dating fixture: `design.md`
Decision 1 records that two of the three obvious ways to back-date an index leave
`cache_updated` false however much the task fetches, so a fixture defect here
would surface later as what looks like an implementation defect. It was therefore
run in isolation, against the digest the scenarios pin
(`geerlingguy/docker-ubuntu2204-ansible@sha256:0172e3b5…`), in a container named
after this working tree and removed afterwards.

**Design.md Decision 1's premise re-confirmed on that digest:**
`/var/lib/apt/periodic/update-success-stamp` **absent**; `/var/lib/apt/lists`
present, empty, mtime **2026-08-10**. So the module falls through to the lists
directory and the first apt task fetches.

The probe playbook reproduced all three behavioural assertions' mechanics against
a literal bound of 3600 — first install, second install, then empty → restore
`partial/` → back-date → third install. **`first=True second=False third=True`**,
with the fixture leaving `/var/lib/apt/lists` at `1970-01-02 00:00:00` and
`partial/` present. That is scenario 2, scenario 1 and scenario 3 respectively,
observed on the pinned image with a bound in place.

Two details worth carrying into the implementation:

- The third install reported `changed: false` (ufw was already present) and
  `cache_updated: true` in the same result. That is the whole reason these
  assertions read `cache_updated` and not `changed` — the effect is invisible in
  host state.
- The `find` step reaches `partial/` and `auxfiles` as well as the list files,
  and removes them. Restoring `partial/` afterwards is what keeps apt from
  failing with `E: List directory /var/lib/apt/lists/partial is missing`;
  `auxfiles` needed no restoring, and the refetch succeeded without it.

The container was removed afterwards; `docker ps -a` shows none left behind.

---

## What the implementation must make pass

Two tests are red today and are expected to go green:

- `test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed`
  `.test_every_qualifying_own_role_apt_task_declares_a_bound` — currently names
  the three tasks `tasks.md` 3.1–3.3 will edit, by file and task name.
- `test_apt_index_staleness_bound.TestTheBoundIsARoleVariableRatherThanALiteral`
  `.test_every_declared_bound_is_a_role_variable_carrying_a_default` — currently
  fails on having nothing to read.

Three static tests are **green already**, and that is not coverage of anything
this change adds — it is a prohibition holding over a state that does not yet
exist. Their job is to **stay** green: they go red if the implementation adds a
bound to `tailscale`'s pinned, same-run-source install, or holds a fixture play
to the bound. Read a change in their colour as a signal, not as noise.

The three Molecule assertions cannot run at all until the registers and the bound
variable exist; a `molecule test` today aborts in `converge.yml` on the first of
them, before `verify.yml` is ever reached. That is the target being absent, not a
defect in the assertions.
