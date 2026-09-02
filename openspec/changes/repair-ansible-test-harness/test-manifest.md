# Test manifest — repair-ansible-test-harness

Written by the `openspec-test-writer` dispatch, before implementation.
**This file is not part of the OpenSpec schema** — `openspec instructions
apply` will not surface it among a task's context files. Read it on purpose
before implementing any task in `tasks.md`.

Location: `openspec/changes/repair-ansible-test-harness/test-manifest.md`.

The library's `rules/` fragment that would normally act as the second,
redundant pointer to this file **is not installed in this repository** —
`AGENTS.md` imports nothing from it, and `CLAUDE.md` imports only `AGENTS.md`.
The dispatch report and this file's own location are therefore the only
pointers. Recorded below as an unresolved project question.

**This pass adds tests and never subtracts.** No existing file — test or
otherwise — was edited, deleted, weakened or disabled. In particular the four
`ansible/roles/deploy_user/molecule/default/` playbooks, the two
`ansible/roles/ops_user/molecule/*/` scenarios, `ansible/roles/docker/`,
`ansible/roles/hardening/`, `ansible/roles/tailscale/`,
`ansible/requirements-test.txt` and this change's own planning artifacts are
untouched.

**No implementation was written.** `deploy_user`'s GHCR login is still
unconditional and the two existing scenario `converge.yml` placeholders are
still the non-empty `dummy-molecule-placeholder-token-not-real`. Nothing was
stubbed, created or adjusted to make a test executable.

**Tasks 6.1, 6.2 and 6.3 were deliberately not attempted.** They repair two
self-failing assertions inside
`ansible/roles/deploy_user/molecule/default/verify.yml` (its private-key scan
matches `verify.yml` itself; its plaintext-token scan flags the legitimately
inline-`!vault` `ansible/inventory/group_vars/prod.yml`). Repairing an
existing test is implementation-time work, and this pass is additive only.
They are named here so they are not mistaken for gaps this manifest failed to
cover. The same applies to 6.4/6.5 (`ops_user`'s `sudo`-refusal assertion) —
also an existing-test repair, also untouched here.

## What was written

Eight new files, all inside the dispatched test-path glob
(`ansible/roles/*/molecule/*/`), forming two new Molecule scenarios for the
`deploy_user` role:

- `ansible/roles/deploy_user/molecule/ghcr-credential-absent/molecule.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-absent/prepare.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-absent/converge.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-absent/verify.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-rejected/molecule.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-rejected/prepare.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-rejected/converge.yml`
- `ansible/roles/deploy_user/molecule/ghcr-credential-rejected/verify.yml`

Plus this manifest, at `<changeRoot>/test-manifest.md` — the one permitted
write outside the glob.

### How to run them

From `ansible/roles/deploy_user/`:

    molecule test -s ghcr-credential-absent
    molecule test -s ghcr-credential-rejected

Both are picked up by `molecule test --all`, which is what tasks.md 7.1 and
7.2 call for. Note that `deploy_user` now has **three** scenarios, so
`molecule test -s default` alone silently skips two — the same trap tasks.md
9.2 already records for `ops_user`. Consider widening 9.2's README note to
say `deploy_user` has three.

Neither new scenario reads `MOLECULE_GHCR_PULL_TOKEN` or
`MOLECULE_GHCR_PULL_USERNAME`, so both behave identically under tasks.md
7.1 (no credentials) and 7.2 (real credentials). That is deliberate: a
scenario whose premise is "no credential supplied" cannot be one that a
7.2-style run turns into a credential-present scenario.

## Baseline

Taken before any file was written. **Scoped**, not full-suite: the scope is
`deploy_user` (the only role whose behaviour this delta constrains) plus the
repository-wide `ansible-lint` run, which is what tasks.md 1.2 baselines.
`ops_user`, `docker`, `hardening` and `tailscale` were not run — they are in
scope for the change's own verification (7.1, 7.4) but nothing this pass
wrote bears on them.

Toolchain used: the modern stack this change is about to pin, not the stack
`ansible/requirements-test.txt` currently pins — `molecule` 26.8.0,
`molecule-plugins` 26.7.15 (docker), `ansible-core` 2.21.3, `ansible-lint`
26.8.0, Python 3.12, with `DOCKER_CONFIG` pointed at a directory holding `{}`
(this workstation's credential-helper trap, tasks.md 9.1).

1. **`molecule test -s default` in `ansible/roles/deploy_user/` — exit 2.**
   `dependency`, `destroy`, `syntax` and `create` all succeeded; `converge`
   failed with:

       [ERROR]: Task failed: Module failed: No package matching
       'python3-debian' is available
       fatal: [deploy_user-role-instance]: FAILED! => {"changed": false, ...}
       deploy_user-role-instance : ok=9 changed=2 unreachable=0 failed=1

   This is precisely the state tasks.md **2.4** predicts as its "second
   baseline": on a modern toolchain the driver failure is gone and the run
   reaches and fails at `geerlingguy.docker`'s `python3-debian` install. The
   driver failure tasks.md 1.1 baselines belongs to the *currently pinned*
   toolchain and was not re-reproduced here — it is already recorded in
   `add-ops-account`'s tasks.md 4.2.

2. **`ansible-lint ansible/` — exit 2, 3 violations**, all in
   `ansible/roles/deploy_user/molecule/default/verify.yml`: 2 ×
   `risky-shell-pipe` (lines 57, 120) and 1 × `yaml[line-length]` (line 379).
   Exactly the baseline tasks.md 1.2 states. Run from a hand-installed
   `ansible-lint`, **not** from the `pre-commit` hook's isolated environment —
   tasks.md 1.2 requires the hook's environment, so treat this as a
   corroborating count, not as a substitute for 1.2.

   After this pass: `ansible-lint ansible/` — exit 2, **still exactly those 3
   violations**, 45 files processed (up from 37). No new violation was
   introduced by the eight new files.

## Scenario accounting

The delta contains **one** requirement with **four** `#### Scenario:` blocks.
All four are accounted for below — two by new tests, two as already covered by
existing tests whose text the delta does not change.

| # | Scenario | Operation | Accounted for by |
|---|---|---|---|
| 1 | A private GHCR package can be pulled during deploy | carried over verbatim from the existing spec | **Existing** coverage, unchanged: `deploy_user/molecule/default/verify.yml` — "Assert root's Docker credential store contains a ghcr.io entry (only when a real token was supplied)", plus the operational proof `add-per-app-deploy-keys` assigned to a manual rollout step. No new test. |
| 2 | Host configuration completes when no GHCR credential is supplied | **NEW** | **New**: the whole `ghcr-credential-absent` scenario (see per-assertion table below). |
| 3 | A supplied credential that the registry rejects still fails the run | **NEW** | **New**: the whole `ghcr-credential-rejected` scenario (see per-assertion table below). |
| 4 | GHCR token is never committed | carried over verbatim from the existing spec | **Existing** coverage, unchanged: `deploy_user/molecule/default/verify.yml`'s two repository-wide scans (literal token markers; `ghcr_pull_token` assigned outside a Vault-encrypted file). Both are the subject of tasks.md 6.2/6.3, which this pass does not touch. No new test. |

Four scenarios in the delta; four accounted for.

### Normative clauses that are not scenarios

The MODIFIED requirement's prose carries three obligations beyond its
scenarios. Recorded here so the absence of a test for each is distinguishable
from the absence of the thought:

- *"Where a GHCR credential is supplied, Ansible SHALL configure root's
  Docker credential store…"* — **covered** by scenario 1's existing
  conditional assertion, which only fires under tasks.md 7.2's
  credentials-supplied run. Not re-tested here.
- *"This tolerance … SHALL NOT be extended to a credential that is present
  and rejected"* — **covered**, this is scenario 3.
- *"The consequence of skipping SHALL be documented"* — **DELIBERATELY
  UNTESTED.** It is a documentation obligation, discharged by tasks.md 4.4
  (`deploy_user/README.md`), design.md and the delta itself. A regex over
  committed prose would break on any rewording while asserting almost
  nothing, so no test was written. The obligation stands; it is checked by
  human review of 4.4, not by the suite.

## Per-assertion classification

Per the testing floor: **SPECIFIED** = traces to a stated requirement;
**DERIVED** = this pass inferred it; **DELIBERATELY UNTESTED** = identified
and knowingly left uncovered, with the reason.

### `ghcr-credential-absent`

Runner-selectable identity: `molecule test -s ghcr-credential-absent` from
`ansible/roles/deploy_user/`. Individual assertions are the named tasks below,
in `.../ghcr-credential-absent/verify.yml`.

| Assertion (task name) | Class | Traces to |
|---|---|---|
| `Assert no ghcr.io credential was written when no credential was supplied` | **SPECIFIED** | Delta scenario 2, THEN limb (a): "the registry authentication step SHALL be skipped". |
| The converge completing at all (all three plays) | **SPECIFIED** | Delta scenario 2, THEN limb (b): "the run SHALL complete successfully". Asserted by molecule's own sequence rather than by a task — `verify` runs only if `converge` exited 0. Stated explicitly so its absence from the table above is not read as an omission. |
| `Assert the deploy account exists after a credential-free converge` | **SPECIFIED** | Delta scenario 2, THEN limb (c): "every other host configuration step SHALL be applied as it would be with a credential present". |
| `Assert app-deploy landed root-owned, mode 0755` | **SPECIFIED** in intent, **DERIVED** in its expected values | Limb (c). The *artifact list and its expected ownership/modes* are copied from `default/verify.yml`, which is the operative meaning of "as it would be with a credential present" — but the delta itself names no path, owner or mode. If `default`'s expectations change, these must change with them. |
| `Assert deploy-receive landed deploy-owned, mode 0755` | as above | as above |
| `Assert each application directory landed deploy:deploy, mode 0750` | as above | as above |
| `Assert each application's sudoers.d entry landed` | as above | as above |
| `Assert deploy's authorized_keys exists` | as above | as above |
| `Assert each application's forced-command key landed` | as above | as above |
| The **third** converge play, `Converge again with a token supplied but no username` | **DERIVED** | See "The both-halves question" below. No delta scenario names it. |
| The **first** converge play, `…both GHCR credential variables left entirely undefined` | **SPECIFIED** by the delta, reinforced by design.md | "runs with no GHCR token supplied" reads most naturally as *not defined*; design.md's GHCR decision names "a variable that is misnamed, or a vars file that is not loaded" as the likeliest real-world instance and says it must become "an ordinary `skipping:` line". A guard written `when: ghcr_pull_token \| length > 0` fails this play; one written with `\| default('', true)` passes it. **This is the single most likely way the implementation can satisfy the spec's letter and fail this test.** |
| The **second** converge play, `…both halves defined but empty` | **SPECIFIED** | The shape the repository's own fixtures produce once tasks.md 4.3 empties the placeholder fallbacks. |

**Deliberately untested in this scenario:**

- *tasks.md 4.2's "make the skip visible" message.* A `debug`/message emitted
  on the skip branch is converge-log output; molecule exposes nothing of the
  converge log to the `verify` playbook, so there is no artifact to assert
  against. Verifying it is a human read of the converge output. Recorded, not
  covered.
- *`deploy-receive`'s extraction pipeline and `app-deploy`'s trigger actually
  running.* Those need a real Docker CLI and are `default`'s subject; this
  scenario asserts that a credential-free converge lands the same host
  **state**, not that that state behaves correctly. Duplicating `default`'s
  behavioural checks here would buy nothing and would force Docker Engine
  into a scenario that otherwise does not need it.

### `ghcr-credential-rejected`

Runner-selectable identity: `molecule test -s ghcr-credential-rejected` from
`ansible/roles/deploy_user/`.

| Assertion (task name) | Class | Traces to |
|---|---|---|
| `Assert the run failed rather than continuing as though no credential had been supplied` | **SPECIFIED** | Delta scenario 3: "the run SHALL fail". Also the requirement's prose: "an authentication failure against a supplied credential SHALL remain a failure of the run, not a skipped step". |
| `Assert the failure came from the registry login itself, not from somewhere else in the role` | **DERIVED** | The delta says the run must fail "rather than continuing as though no credential had been supplied", which this pass reads as *the login was attempted, not skipped*. The delta names no module; matching `'docker_login' in failed_action` is this pass's choice. Without it the scenario would go green on **any** unrelated converge failure. If the login step's module legitimately changes, this is the assertion to revisit — and it should be revisited, not deleted. |

**Deliberately untested in this scenario:**

- *That no `ghcr.io` entry is written to root's credential store on a rejected
  login.* Considered and dropped: with the engine installed but the login
  refused, the check is nearly always vacuously true, and a vacuously-true
  assertion in a scenario this load-bearing is noise that reads as coverage.
- *Distinguishing "the registry refused the credential" from "the login step
  failed for some other reason".* The recorded observation below shows a real
  403 from ghcr.io on this machine, but an instance with no route to ghcr.io
  would fail the same login task with a connection error and the scenario
  would still pass. That residue is accepted: the delta's normative content is
  that the run **fails rather than skipping**, and both cases establish it.
  `prepare.yml` installs `python3-requests` and the converge installs Docker
  Engine specifically to remove the two *avoidable* wrong-reason failures (a
  missing Python library, an unreachable daemon).

## Observed results, pre-implementation

Both scenarios were actually executed against the current, unimplemented tree
on 2026-09-01, on the modern toolchain described under Baseline. Exit codes
are the playbook's/molecule's own, read directly, not a pipeline's last stage.

**`molecule test -s ghcr-credential-absent` — exit 2. RED, as expected.**
`create`, `prepare` and the first converge play all ran; the role failed 9
tasks in with:

    Error while resolving value for 'password': 'ghcr_pull_token' is undefined
    fatal: [deploy_user-ghcr-absent-instance]: FAILED! => {"changed": false,
      "msg": "Task failed: Finalization of task args for
      'community.docker.docker_login' failed: Error while resolving value for
      'password': 'ghcr_pull_token' is undefined"}

This is failure **state 2** in the testing floor's enumeration — *the target
does not exist yet*. It establishes that the guard is absent and nothing more;
the scenario's own assertions never executed on this run, because `verify`
never ran. Their quality is established separately, below.

**`molecule test -s ghcr-credential-rejected` — exit 0. GREEN, pre-implementation.**
This is failure **state 4** — a test passing before the implementation exists —
and per the floor it was investigated rather than recorded as coverage. The
investigation's answer: **the behaviour genuinely already exists.** Today's
login is unconditional, so a supplied-but-rejected credential already fails
the run. The captured outcome was a real registry refusal:

    "failed_action": "community.docker.docker_login",
    "failed_task_name": "Authenticate root's Docker credential store to GHCR",
    "failed_msg": "Logging into ghcr.io for user
      molecule-fixture-account-that-does-not-exist failed - 403 Client Error
      ... (\"Get \"https://ghcr.io/v2/\": denied: denied\")",
    "outcome": "failed"

So this scenario is a **regression guard on a property the change must
PRESERVE**, not coverage of new behaviour. It is the one thing standing
between "guard the login" and "ignore login errors" — design.md's own words —
and it will only start doing work the moment tasks.md 4.1 lands. Read its
current green as "nothing is broken yet", not as "this is done".

### Assertion quality was established by mutation, not by the runs above

Because neither run exercised its scenario's assertions on real converged
state (one never reached `verify`, the other passed), each assertion was
driven directly against a hand-controlled host state — a throwaway container
over `community.docker.docker`, running the scenario's real `verify.yml`
unmodified — and confirmed to **fail when it should**:

- Marker planted as `outcome: succeeded` (i.e. the role swallowed the login
  error) → `Assert the run failed…` fires, exit 2.
- Marker planted as failed at `ansible.builtin.user` instead → `Assert the
  failure came from the registry login itself…` fires, exit 2.
- Marker planted with the real recorded outcome → both pass, exit 0.
- `/root/.docker/config.json` planted containing a `ghcr.io` auth → `Assert no
  ghcr.io credential was written…` fires, exit 2.
- Host state built up one artifact at a time (no account → account only →
  scripts missing → script mode `0644` → `/opt` dirs missing → `sudoers.d`
  entries missing → `authorized_keys` missing → only one app's key present):
  **every one of the limb-(c) assertions fired at its own step**, and the
  fully-correct state passed with `ok=14 failed=0`.

No repository file was mutated to do this. The mutations were to a throwaway
container's state and to the recorded-outcome marker, never to the role under
test and never to a committed test.

## Obsolete tests

The delta is `MODIFIED`, so an obsolete list is required. It was produced by
comparing `openspec/specs/iac-host-configuration/spec.md`'s existing
requirement with the delta — **not** by reading `deploy_user/tasks/main.yml`.

What the delta supersedes: the existing requirement's opening sentence is
unconditional — *"Ansible SHALL configure root's Docker credential store on
the host with a read-only … token"* — and the delta narrows it to *"Where a
GHCR credential is supplied…"*, adding the absent-credential tolerance and its
explicit rejection boundary. Neither carried-over scenario's text changes.

**Search bound:** `ansible/roles/*/molecule/*/` only, which is the dispatched
test-path glob. The dispatch supplied **no** earlier `test-manifest.md` path,
so no scenario-to-test mapping from a previous pass was used, and none was
sought.

Two entries. **Both are candidates for human confirmation, not conclusions.**

1. `ansible/roles/deploy_user/molecule/default/converge.yml`, lines 35–36 —
   the `ghcr_pull_token` / `ghcr_pull_username` fallback values
   `dummy-molecule-placeholder-token-not-real` /
   `dummy-molecule-placeholder-user-not-real`, and the file's lines 16–19
   comment explaining the placeholder as though it were load-bearing.
   - *Superseded by:* the delta's "Where no GHCR credential is supplied,
     Ansible SHALL skip the registry authentication step", operationalised by
     tasks.md 4.3.
   - *Evidence:* design.md's third decision states these exact two lines
     verbatim and concludes that with a non-empty fallback "the guard
     evaluates true, the login runs, and ghcr.io returns the same 403" — i.e.
     the fixture actively defeats the new requirement.
   - *Not a deletion:* 4.3 empties the fallback and keeps the `lookup('env',
     …)`. This pass did not touch it.
   - **Candidate for human confirmation.**

2. `ansible/roles/ops_user/molecule/default/converge.yml`, lines 69–70 — the
   same two placeholder fallbacks.
   - *Superseded by:* the same clause, same task (4.3 names both files).
   - *Evidence:* byte-identical values to entry 1; the file's own line 29
     comment says its GHCR credentials follow "that scenario's proven"
     pattern.
   - **Candidate for human confirmation.**

**No superseded *assertion* was found, and that is a finding rather than an
empty result.** The only existing assertion bearing on the GHCR credential
store —
`deploy_user/molecule/default/verify.yml`'s "Assert root's Docker credential
store contains a ghcr.io entry (only when a real token was supplied)" — is
already conditioned on a real token being supplied, so it asserts only the
credential-**present** branch, which the delta preserves verbatim. It is not
superseded. tasks.md 7.2 requires its two `when:` clauses be widened to test
both credential halves; that is a repair to a still-valid assertion, not a
supersession, and this pass did not make it.

Distinguishing the two possible meanings of "nothing found", as required: for
**assertions**, this is "no such test exists" — the glob was searched
exhaustively for `ghcr`/`GHCR`/`docker_login` and the four hits are the two
fixture pairs above plus the one conditional assertion just discussed. For
anything outside the glob, it is "none was found by this search", because the
search never went there.

## Unresolved project questions

Recorded per the floor's rule that a project-specific question with no
recorded answer is surfaced with the assumption taken, never resolved
silently. This pass is a dispatched subagent with no channel to ask on.

1. **Does tasks.md 6.2's repaired plaintext-token scan accept a
   `lookup('env', …) | default(…)` value?** *Assumption taken:* yes.
   *Tests depending on it:* **all eight new files**, via the
   `ghcr_pull_token:` assignments in both new `converge.yml` files.
   6.2 requires the repair be "accept an assignment whose value is an inline
   `!vault` value or a `lookup('env', ...)` expression", explicitly rejecting
   a path exclusion. Both new converge files write their assignments in
   **exactly the form the two existing scenario converge files use**, so a
   repair that accepts those accepts these. **But if the implementer instead
   excludes files by path (which 6.2 forbids, for good reasons), the two new
   files will not be in the exclusion list and `molecule test -s default`
   will go red on them.** This is the single highest-value line in this
   manifest for whoever implements 6.2.
2. **Neither new fixture credential is shaped like a real GitHub token.**
   `default/verify.yml` scans the whole repository for
   `gh[pousr]_[A-Za-z0-9]{20,}` and `github_pat_[A-Za-z0-9_]{20,}`. The
   fixture strings were chosen to match neither. *Assumption taken:* that scan
   keeps its current pattern. If 6.3's "plant a real marker, confirm it fires"
   work changes the pattern, re-check these two files.
3. **`deploy_user` now has three Molecule scenarios.** tasks.md 9.2 documents
   the `-s default` trap for `ops_user` only. *Assumption taken:* the README
   note should be widened to `deploy_user` as well; this pass did not edit
   `tasks.md` (not its file to edit) and records it here instead.
4. **`ghcr-credential-rejected` omits `idempotence` and `side_effect` from its
   `test_sequence`.** *Assumption taken:* this is acceptable and is not the
   suite silently losing an idempotence check. Reason, stated in the file:
   the converge deliberately aborts the role partway, so any role task after
   the login never runs on converge 1 and necessarily reports `changed` on
   converge 2 — `idempotence` there would fail for a reason unrelated to what
   the scenario tests. Role idempotence remains covered by `default` and by
   `ghcr-credential-absent`, both of which converge the role to completion.
   If the project would rather keep `idempotence` everywhere, that is a real
   decision to make, not an oversight to fix silently.
5. **The library's `rules/` fragment pointing here is not installed in this
   repository.** `AGENTS.md` imports nothing from it. *Assumption taken:* the
   dispatch report plus this file's location are sufficient pointers for now.
   Installing the fragment, or adding a line to `AGENTS.md`, is a project
   decision and out of this pass's scope (`AGENTS.md` is outside the
   test-path glob).
6. **Two new `prepare.yml` files exist that tasks.md 3.1 does not enumerate.**
   3.1 lists the three scenarios that get one and names two that
   deliberately get none. The two new scenarios each need one, for the same
   reason and with the same fixture-only framing. *Assumption taken:* the
   implementer extends 3.1's mental list rather than treating these as
   unaccounted files. `ghcr-credential-absent`'s does not install Docker
   Engine, so its apt refresh is insurance plus `python3-requests`;
   `ghcr-credential-rejected`'s is load-bearing for both reasons.

## What the implementation must make pass

- **`molecule test -s ghcr-credential-absent`** must go from exit 2 to exit 0.
  This requires tasks.md **4.1** (guard both credential halves) and it
  requires the guard to tolerate the variables being **undefined**, not merely
  empty — the first converge play supplies neither variable at all.
- **`molecule test -s ghcr-credential-rejected`** must **stay** at exit 0.
  It is already green; the risk is 4.1 or 4.5 turning it red, which is
  precisely the outcome design.md says must not happen.
- Both must stay green under tasks.md 7.1 (no credentials) and 7.2 (real
  credentials supplied), unchanged, because neither reads those variables.
- `ansible-lint ansible/` must stay at the 3 pre-existing violations; the
  eight new files add none.
