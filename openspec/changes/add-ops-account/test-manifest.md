# Test manifest — add-ops-account

Written by the `openspec-test-writer` dispatch, before implementation.
**This file is not part of the OpenSpec schema** — `openspec instructions
apply` will not surface it among a task's context files. Read it on purpose
before implementing any task in `tasks.md`. (It is also pointed to by this
library's `rules/` fragment directing that it be read before implementing;
this is the second, redundant pointer, since that fragment's import path is
machine-local and would not otherwise reach this repository.)

Location: `openspec/changes/add-ops-account/test-manifest.md`.

No implementation exists. `ansible/roles/ops_user/` contained nothing before
this pass and contains only `molecule/default/` after it — no `tasks/`, no
`defaults/`, no `README.md`. Every assertion below traces to the change's
delta spec
(`openspec/changes/add-ops-account/specs/iac-host-configuration/spec.md`),
to `tasks.md`/`design.md`, or — where marked DERIVED — to this pass's own
judgement.

## What was written

Four new files, all inside the dispatched test-path glob
(`ansible/roles/*/molecule/*/`), forming the `default` Molecule scenario for
the unwritten role:

- `ansible/roles/ops_user/molecule/default/molecule.yml`
- `ansible/roles/ops_user/molecule/default/converge.yml`
- `ansible/roles/ops_user/molecule/default/side_effect.yml`
- `ansible/roles/ops_user/molecule/default/verify.yml`

**This pass adds tests and never subtracts.** No existing file — test or
otherwise — was edited, deleted, or disabled. `ansible/roles/deploy_user/`,
`ansible/roles/docker/`, `ansible/playbooks/host-baseline.yml`,
`.ansible-lint`, `ansible/inventory/group_vars/prod.yml` and the change's own
planning artifacts are untouched.

**Edited afterwards, at implementation time, by the implementer** (recorded
here because the independent-test-author rule is what makes these files worth
anything): two changes, both to `verify.yml`, neither touching an assertion's
subject or strength.
1. The private-key-marker scan matched `verify.yml` itself — a scan whose
   pattern is written out literally must contain the string it searches for,
   and the scan's target directory contains the scan. The pattern is now
   assembled from two halves at run time. Same three markers, same `|| true`,
   same assertion; re-verified by planting synthetic OpenSSH, RSA and PKCS#8
   keys and watching it fire on each, then fall silent when removed.
2. The header gained a dated note saying so.
Plus a mechanical `ops_users` → `ops_user_accounts` rename across all three
playbooks, following the project's resolution of unresolved question 1 below.

**No implementation was written.** In particular, no `ops_user/tasks/`,
`ops_user/defaults/` or `ops_user/README.md` was created — not even an empty
stub to let the scenario converge. The scenario failing because the role is
absent is the expected outcome of this pass, not a defect to repair.

`side_effect.yml` is the one structural departure from `deploy_user`'s
reference scenario. Two of the nine scenarios ("rotating an operator's key
removes the previous one", "revoking an operator who is currently logged in
still completes") describe what a **second converge with a changed list**
does, which a single converge cannot observe. Molecule's default
`test_sequence` already runs `side_effect` between `idempotence` and
`verify`, so no `test_sequence` override was needed.

## Files read, and one disclosure

Read: the change's four artifacts and its `.openspec.yaml`;
`openspec/specs/iac-host-configuration/spec.md`; `AGENTS.md` / `CLAUDE.md`;
the archived `add-per-app-deploy-keys/test-manifest.md`; and, inside the
test-path glob, `deploy_user`'s and `docker`'s Molecule scenarios.

**Disclosure:** `ansible/roles/deploy_user/tasks/main.yml` and
`defaults/main.yml` were also read. They are not the implementation of the
behaviour under test — that role is a converged dependency of this scenario,
not its target — but they are implementation source, and the boundary is
worth stating rather than leaving to be noticed. Nothing about `ops_user` was
inferred from them. The expected `deploy` key-option string asserted in
`verify.yml` (`restrict,command="/usr/local/bin/deploy-receive <app>"`) traces
to `openspec/specs/iac-host-configuration/spec.md`'s existing "Restricted
Deploy Account Supports Per-Application Forced-Command Deploys" requirement,
which this change leaves unmodified — not to that role's tasks file.

## Baseline

Two baselines were taken, both **scoped**, both recorded with their scope.

### 1. `ansible-lint ansible/` — taken, red, and unchanged by this pass

Before: **3 failures**, all in
`ansible/roles/deploy_user/molecule/default/verify.yml` —
2 × `risky-shell-pipe` (lines 57, 120) and 1 × `yaml[line-length]`
(line 379). This exactly matches the pre-existing baseline `tasks.md` §4.1
already records.

After: **4 failures** — the same 3, plus one attributable to this pass:

```
syntax-check[specific]: The role 'ops_user' was not found in: ...
ansible/roles/ops_user/molecule/default/converge.yml:74:7
```

That is the absent target, not a defect in the tests. It clears when
`ops_user/tasks/main.yml` exists **and** `ops_user` is added to
`.ansible-lint`'s `mock_roles` (`tasks.md` §2.5) — standalone `ansible-lint`
does not resolve role references through `ansible.cfg`'s `roles_path`, which
is why every other by-name role in this repository is mocked there.

No other new violation was introduced. One was found and removed during this
pass: passing the accounts list as an `include_role` task var inside a role
directory trips `var-naming[no-role-prefix]`; `side_effect.yml` declares it at
play level instead, which the rule does not reach. See the unresolved
questions below — the same rule bears on `tasks.md` §2.1, and that part is
**not** something this pass can resolve.

**Resolved after this pass**, at implementation time: the project renamed the
variable from `ops_users` to `ops_user_accounts`, which carries the required
`ops_user_` prefix. Every occurrence below that names `ops_users` is
describing the state of things *when this manifest was written*, before that
decision; the tests themselves now use `ops_user_accounts` throughout.

### 2. `molecule test -s default` — taken, and red before this change

Run against the **existing, implemented** `deploy_user` role (the only role
in this repository with a comparable scenario), from
`ansible/roles/deploy_user/`:

- Plain run: fails at the very first `destroy` action.
  `molecule_plugins.docker`'s `destroy.yml` uses
  `when: (lookup('env', 'HOME'))`, which ansible-core 2.21 rejects:
  *"Conditionals must have a boolean result."* Exit 2.
- With `ANSIBLE_ALLOW_BROKEN_CONDITIONALS=1`: gets past `destroy`, then fails
  at `create`. `molecule_plugins.docker`'s `create.yml` reads
  `item.invocation.module_args.dest` from a registered result that no longer
  carries `invocation`: *"object of type 'dict' has no attribute
  'invocation'"*. Exit 1.

Both are incompatibilities between `molecule-plugins` 23.5.3's docker driver
and ansible-core 2.21 (molecule 24.12.0, Python 3.12) in the environment this
pass ran in. Neither is caused by this repository's content, and both hit an
already-implemented role's scenario, so:

> **No Molecule scenario in this repository can execute in this environment,
> and the new `ops_user` scenario has therefore never been run.** Its
> assertions are unexecuted. A later report that "the ops_user tests fail"
> must separate this from the role's absence and from any real defect.

What *was* executed, to reduce how much rests on that:

- `ansible-lint ansible/` over all four new files (above) — clean apart from
  the absent-role syntax check.
- Every non-obvious Jinja expression in `verify.yml` (the
  `split`/`select`/`reject`/`map`/`unique` chains, the `~` concatenation
  against `deploy`'s option string, `is search`, the `| lower` parenthesised
  comparisons) evaluated in a throwaway playbook against **both** synthetic
  passing data and synthetic failing data, confirming each one discriminates
  rather than merely evaluating. The `find /opt -maxdepth 2 ( ... )` shape
  passed through `ansible.builtin.command` was confirmed to reach `find`
  correctly with unescaped parentheses.
- The claim that `ops_users:` in a role's `defaults/main.yml` trips
  `var-naming[no-role-prefix]` was confirmed empirically in a throwaway role
  outside this repository, then deleted. (Confirmed again at implementation
  time, along with the converse: the renamed `ops_user_accounts: []` lints
  clean.)

That covers assertion-expression defects (failure state 3), not behavioural
correctness against a converged host, which remains unverified here.

## Scenario accounting — ADDED Requirement: Unprivileged Operator Accounts Support Interactive Host Inspection (9 scenarios)

All nine are covered. Test names below are runner-selectable as Ansible task
names within the named file; the whole scenario runs via
`cd ansible/roles/ops_user && molecule test -s default`.

| # | Scenario | Test(s) | Status |
|---|----------|---------|--------|
| 1 | An operator key opens an interactive session | `verify.yml` — "Assert ops-claude has a real home directory and an interactive shell", "Assert ops-claude's home directory exists and is owned by ops-claude", "Assert ops-claude has no usable password (password-based login is not provisioned)", "Assert ops-claude's authorized_keys line carries neither a forced command nor restrict" | Covered (proxy on the pty itself — see note A) |
| 2 | Container state and logs are inspectable without privilege escalation | `verify.yml` — "Assert ops-claude is a member of the docker group", "Run docker ps as ops-claude, with no sudo anywhere in the invocation", "Assert docker ps succeeded by group membership alone", "Attempt docker logs against a non-existent container as ops-claude", "Attempt docker exec against a non-existent container as ops-claude", "Assert the log and exec attempts reached the daemon rather than being refused at the socket" | Covered (`docker ps` direct; logs/exec proxy — see note B) |
| 3 | The account has no sudo capability | `verify.yml` — "Attempt a sudo invocation as ops-claude, non-interactively", "Assert sudo refuses ops-claude", "Confirm no sudoers.d file is named after an operator account", "Search every sudoers file on the host for an operator account name", "Assert no sudoers file exists that names an operator account", "Assert ops-claude is in no privilege-granting group" | Covered |
| 4 | An operator cannot read another application's deployed secrets from the filesystem | `verify.yml` — "Confirm each /opt/<app> directory's ownership and mode", "Assert every /opt/<app> path is deploy-owned and closed to others", "Assert no operator account owns or has group access to any /opt/<app> path", "Assert ops-claude is not a member of the deploy group", "Attempt to read commerce-ops's deployed .env as ops-claude", "Assert the .env read was refused by filesystem permissions", "Attempt to overwrite commerce-ops's docker-compose.yml as ops-claude", "Read commerce-ops's docker-compose.yml back as root", "Assert the overwrite was refused and the file is unchanged" | Covered (both halves, per `tasks.md` §3.2) |
| 5 | Revoking an operator is a converge, not a manual cleanup | `side_effect.yml` — "Include the ops_user role with the mutated ops_user_accounts list"; `verify.yml` — "Look up ops-revoke's passwd entry after revocation", "Confirm ops-revoke's home directory after revocation", "Assert ops-revoke's account and home directory are gone", "Look up the surviving operator accounts", "Assert revoking one operator affected no other entry and not the deploy account" | Covered |
| 6 | Revoking an operator who is currently logged in still completes | `side_effect.yml` — "Start a long-running process owned by ops-revoke, under a PAM session", "Assert ops-revoke really is in use before revocation is attempted", "Record the pre-revocation pid and uid for verify.yml to read", "Record that the re-converge completed rather than failing", "Report which delta-spec scenario this run failed"; `verify.yml` — "Check whether the process ops-revoke owned is still alive", "Check whether any process still runs under the revoked account's uid", "Assert the run completed and left the revoked account with no surviving process" | Covered (proxy on "session" — see note C) |
| 7 | Rotating an operator's key removes the previous one | `side_effect.yml` (play var `ops_user_accounts`, ops-rotate's NEW key); `verify.yml` — "Read ops-rotate's authorized_keys after rotation", "Assert the rotated key replaced the previous one rather than being appended to it" | Covered |
| 8 | Operator private keys are never committed | `verify.yml` — "Scan this role's committed files for embedded private-key material", "Scan the committed inventory for embedded private-key material (DERIVED)", "Assert no operator private key is committed under the role or the inventory" | Covered |
| 9 | The deploy account's restrictions are unaffected | `verify.yml` — "Assert every key on deploy still carries restrict and its own forced command", "Assert no operator key was installed onto the deploy account"; supported by "Assert ops-claude is not a member of the deploy group" and the /opt ownership scan | Covered |

**Count check: 9 scenarios in the delta spec, 9 accounted for. None
uncovered.**

### Note A — the pty is proxy coverage

Whether `sshd` actually allocates a pty for the key is live OpenSSH
behaviour, not this role's logic, and would need `sshd` running inside the
Molecule instance with a real client connecting to it. What the role controls
is asserted directly and completely: interactive shell in the passwd entry, a
real home directory, no password login, and an `authorized_keys` line
carrying neither `command=` nor `restrict` — `restrict` being precisely the
option that disables pty allocation on every `deploy` key (`design.md`). The
live proof is `tasks.md` §5.2's operator-run Rollout step.

### Note B — `docker logs` / `docker exec` are proxy coverage

`docker ps` is exercised for real, as the account, with no `sudo` in the
invocation. `docker logs` and `docker exec` are aimed at a container that does
not exist, because this scenario deliberately runs no application container —
following this repository's own `services: {}` convention, which keeps the
scenario free of any registry pull. That still discriminates: being answered
*"No such container"* means the daemon was reached and the call authorised,
whereas a socket permission failure reports a connection/permission error
instead. The assertions check both directions explicitly. Live proof against a
running container is `tasks.md` §5.2/§5.3.

### Note C — "logged in" is proxied by an in-use account

`side_effect.yml` establishes a process owned by `ops-revoke`, started through
`su -` so it comes up under a full PAM session stack, then marks the entry
`absent` and re-runs the role. A real SSH session is not reproducible inside
the Molecule instance. What is **not** a proxy is the load-bearing half: the
account is genuinely in use at revocation time, which is the case `design.md`
says a bare `state: absent` fails on (`userdel` exit 8), and `verify.yml`
asserts the exact recorded pid and the revoked uid have no surviving process
afterwards.

One limit, stated rather than papered over: whether
`loginctl terminate-user` specifically did the terminating is **not**
distinguished from `pkill -KILL -u` having done it. A "no logind session
remains" assertion was considered and rejected — it would pass vacuously if
no logind session was ever created, and a vacuous assertion in the suite is
worse than a recorded gap.

## Assertion classification

**Specified** — traces to the delta spec's scenario text or the requirement's
own normative prose: the shell field and home directory; the absence of
`command=`/`restrict` on the operator key; `docker` group membership; the
`docker ps` success; the `sudo -n` refusal and the absence of any `sudoers.d`
file naming the account; the `/opt/<app>/.env` read refusal and the
`docker-compose.yml` overwrite refusal; no ownership of or group access to any
`/opt/<app>` path; account and home-directory removal on `state: absent`; the
other entries and the `deploy` account surviving that removal; termination of
the revoked account's processes before removal; `authorized_keys` holding only
the rotated key; no committed private key; every `deploy` key still carrying
`restrict` plus its own forced command; no operator key on `deploy`.

**Specified by `tasks.md`/`design.md` rather than by a scenario** — recorded
separately because a reader checking against the delta spec alone will not
find them: the shadow password field being `"!"` (`tasks.md` §2.2); the
`ops_user_accounts` entry shape `{name, public_key, state}` and `state` defaulting to
`present` (`tasks.md` §2.1/§2.3 — `converge.yml` omits `state` on `ops-claude`
on purpose, so the default is exercised rather than assumed); the role
ordering `docker` → `deploy_user` → `ops_user` (`tasks.md` §2.5/§3.1); the
`/opt` ownership scan (`tasks.md` §3.3).

**Derived** — this pass's own judgement, no stated requirement covers them.
Each is individually droppable without touching scenario coverage:

- `/home/ops-claude` as the home-directory path. No artifact states where an
  operator account's home lives; the distro default was assumed. See the
  unresolved questions.
- The `authorized_keys` line beginning `ssh-ed25519 ` (i.e. options-free at
  the start of the line), as a stronger form of "no forced command and no
  `restrict`".
- `ops-claude` being in no `sudo`/`admin`/`root` group. The spec forbids a
  `sudoers` entry; group-based privilege is the adjacent hole, not a stated
  requirement.
- The `docker logs`/`docker exec` daemon-reached assertions (note B).
- Scanning `ansible/inventory/` for private-key markers. `tasks.md` §3.2 asks
  only for a scan over the role's committed files; the inventory is where
  `ops_user_accounts` and therefore the committed key material actually lives, so a
  role-only scan would not look where the risk is.
- The `README.md` content assertion ("Assert the README records the escalation
  grant, the sudoers omission, and the sshd obligation"). The requirement says
  the capability *SHALL be documented* as root-equivalent by escalation and
  that the account SHALL NOT be described as a boundary against its own key
  holder; `tasks.md` §2.4 puts that plus the sshd `AllowUsers`/`AllowGroups`
  obligation in the README. No scenario reaches those sentences. Matching is
  deliberately loose (presence of `root-equivalent`, `sudoers`, and
  `allowusers`/`allowgroups`, case-insensitive) rather than wording-exact —
  but it is still this pass dictating that a documentation file exist and
  contain particular terms, so it is flagged for confirmation rather than
  presented as required.

**Deliberately untested** — identified and knowingly left uncovered:

- **Live pty allocation, live SSH session, live `docker logs`/`exec` against
  a running container.** Notes A–C; assigned to `tasks.md` §5.2/§5.3.
- **Which of `loginctl terminate-user` / `pkill` performed the termination.**
  Note C.
- **"Deleting an entry from the list is not revocation."** `design.md` records
  this trap (a converge over a list the entry has left touches nothing and
  leaves the account in place, with no error). No scenario covers it, and the
  assertion it would need is "after removing the entry, nothing changed" —
  which is what a role that does nothing at all also produces. Left to the
  README, where `design.md` puts it.
- **Idempotence of the role's own tasks** is not asserted by any task in
  `verify.yml`; it is delegated to Molecule's `idempotence` action, which the
  scenario keeps in the default `test_sequence` on purpose. That is what
  exercises `tasks.md` §2.3's requirement that the termination step report
  `changed: false` when there is nothing to terminate — a role that runs
  `pkill` unconditionally fails the `idempotence` action rather than any
  single assertion here.
- **`--check` mode behaviour** (`tasks.md` §5.5). Deliberately out of
  Molecule's reach, for the reason that task itself gives.
- **The out-of-repository consumer wiring** (`tasks.md` §6, `~/.ssh/config`
  and the Claude Code permission rule). Not in this repository; not testable
  from it.

## Obsolete tests

**Not applicable, with that reason:** this change's delta spec carries a
single `ADDED` requirement and no `MODIFIED`, `REMOVED`, or `RENAMED` delta.
Nothing existing is superseded, so no existing test can be superseded either.

For the avoidance of the ambiguity an empty list would create: this is *"no
such test can exist"*, not *"none was found by this search."* The change's own
`proposal.md` states that no existing requirement changes and that the
`deploy` account's forced-command model is untouched — and this pass's tests
actively **re-assert** that model (scenario 9) rather than replacing it. No
existing test in `ansible/roles/*/molecule/*/` should be deleted, rewritten,
or weakened on account of this change.

## Unresolved project questions / assumptions taken

Recorded rather than resolved: this pass runs without a channel to ask on.
Each carries the assumption taken and which tests depend on it.

1. **`ops_users` versus `ansible-lint`'s `var-naming[no-role-prefix]` — a
   conflict inside the change's own artifacts. RESOLVED at implementation
   time; recorded here as written.** Confirmed empirically: a
   role at `ansible/roles/ops_user/` whose `defaults/main.yml` sets
   `ops_users: []` produces
   `var-naming[no-role-prefix]: Variables names from within roles should use
   ops_user_ as a prefix. (vars: ops_users)`. `tasks.md` §2.1 mandated exactly
   that line; `tasks.md` §4.1 requires the change to introduce no new
   violation. Both could not hold. The resolutions were a project decision —
   rename the variable, add a `# noqa` / `.ansible-lint`
   `skip_list` entry, or accept a new baseline violation — and this pass took
   none of them.
   *Assumption taken:* the tests use `ops_users`, since `tasks.md` §2.1 was the
   stated interface. *Tests depending on it:* `converge.yml` (play var),
   `side_effect.yml` (play var). Both are at play
   level in a playbook, where the rule does not apply, so **the tests
   themselves introduce no violation either way** — but they will need renaming
   in step with the role if the variable is renamed.
   **Resolution taken:** renamed to `ops_user_accounts` (prefixed *and*
   defaulted, as `hardening_web_allowed_cidrs` already is), across the
   artifacts, the tests and `group_vars/prod.yml`. No lint suppression was
   added and no baseline violation was accepted.
2. **Where an operator account's home directory lives.** No artifact says.
   *Assumption:* the distro default, `/home/<name>`. *Tests depending on it:*
   `verify.yml`'s "Assert ops-claude has a real home directory and an
   interactive shell", "Confirm ops-claude's home directory exists on disk and
   is its own", "Read ops-claude's authorized_keys", "Confirm ops-revoke's home
   directory after revocation", "Read ops-rotate's authorized_keys after
   rotation". If the role sets an explicit `home:`, these paths must move with
   it.
3. **The two extra fixture account names.** `ops-claude` is the seeded
   production identity (`tasks.md` §1.2); `ops-rotate` and `ops-revoke` are
   this pass's own invention, needed because rotation and revocation must not
   be exercised against the account every other assertion depends on.
   *Assumption:* inventing two test-only names is acceptable. They appear in
   `converge.yml`, `side_effect.yml`, and every `verify.yml` block.
4. **Whether a Molecule scenario may depend on a registry pull.** *Assumption:*
   no — following this repository's existing `services: {}` convention. This is
   what makes note B's proxy necessary rather than testing `docker logs`
   against a real container.
5. **Whether asserting `README.md` content is in scope for a Molecule
   scenario.** *Assumption:* yes, since the requirement's own prose makes
   documentation normative and no other test reaches it, and since `deploy_user`
   already precedents delegating repository-content scans to `localhost` from
   `verify.yml`. *Test depending on it:* "Read the role's README", "Assert the
   README records the escalation grant, the sudoers omission, and the sshd
   obligation". Drop both if the project would rather documentation not be
   asserted mechanically.
6. **No stack skill covering Molecule scenario authoring beyond the floor.**
   The `ansible` skill names Molecule as a role-level harness and defers the
   decision to use it to the project (which `AGENTS.md` has already made), but
   carries no scenario-authoring idiom. Recorded as an absence, per this pass's
   own instructions; the reference scenario at
   `ansible/roles/deploy_user/molecule/default/` was followed instead.
7. **The environment cannot run Molecule at all** (see Baseline 2). *Assumption:*
   the scenario is written to the shape `deploy_user`'s proven scenario uses and
   validated statically, on the expectation that whoever implements the change
   runs it in an environment with a compatible `molecule-plugins`/ansible-core
   pairing. If that pairing has to be fixed first, that is a separate concern
   from this change and affects the existing `deploy_user` scenario equally.

## Test command and test-path glob (as given by the dispatch)

- Test command: `molecule test -s default`, run with the role directory as
  cwd — `cd ansible/roles/ops_user && molecule test -s default`.
- Test-path glob: `ansible/roles/*/molecule/*/`. Nothing was written outside
  it except this manifest.

## What the implementation step must make pass

1. `ansible/roles/ops_user/tasks/main.yml`, `defaults/main.yml` and
   `README.md` must exist. Until they do, `converge.yml` cannot resolve
   `role: ops_user` and the scenario fails at converge — the expected
   absent-target state, and the only failure state the tests are currently
   in.
2. `ops_user` must be added to `.ansible-lint`'s `mock_roles` (`tasks.md`
   §2.5) for the `syntax-check[specific]` violation this pass's baseline
   records to clear.
3. The role must accept `ops_user_accounts` as a list of `{name, public_key, state}`,
   treat a missing `state` as `present`, and default to `[]`.
4. `authorized_key` must be used with `exclusive: true` — the rotation
   assertion checks that the superseded key is **gone**, which a run at the
   module's default (`exclusive: false`) passes halfway and fails on.
5. Revocation must terminate first and remove second, and the termination step
   must be a no-op reporting `changed: false` when there is nothing to
   terminate — otherwise Molecule's `idempotence` action fails on the second
   converge, before any assertion is reached.
6. The role must write **no** `sudoers.d` file, add the account to **no**
   privilege-granting group, and grant **no** ownership of or group access to
   any `/opt/<app>` path.
7. `README.md` must record that `docker` group membership is root-equivalent by
   escalation, that this role writes no `sudoers` file of any kind, and the
   standing sshd `AllowUsers`/`AllowGroups` obligation — per the DERIVED
   assertion flagged above, which is the one item on this list a reviewer may
   legitimately decide to drop.
