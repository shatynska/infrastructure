# Tasks

**Group 1 runs before every other group.** The tests are derived from the approved specification deltas by an author other than whoever implements, and they fail by design until group 3 is complete. A list worked top-down is therefore the right order, and this note is here because the first draft of this file put the tests last while their own task said "before any implementation".

## 1. Derive the tests

- [x] 1.1 Commit this plan, then dispatch `ai-toolkit:change-test-writer` with both relevant rows of `AGENTS.md`'s test table — the Molecule row (`ansible/scripts/run-molecule test --all`, `ansible/roles/<name>/molecule/<scenario>/`) and the static row (`python3 -m unittest discover --start-directory .github/tests`, `.github/tests/*.py`) — and verify a `test-plan.md` mapping every scenario in both delta specs to a test. **Say in the dispatch that the derivation covers the requirements' normative prose as well as their scenarios**: several obligations added during plan review — the size bound, the ignored unknown fields, the identifier shape — are stated in prose, and a derivation reading only `#### Scenario:` headings would leave them to nobody
- [x] 1.2 Confirm the derived Molecule coverage stands up a real PostgreSQL fixture inside the instance — `deploy_user`'s `default` scenario already runs real containers there — and reaches `unreachable`, `absent`, `credential-refused`, `empty` and `populated`, verified by each failing before the implementation lands
- [x] 1.3 Confirm a scenario covers the stopped instance answering `unreachable` and never `absent`, and one covers an unclassified error emitting no token and a non-zero exit — the two cases the plan review found undefined
- [x] 1.4 Confirm a scenario covers `window-open` taking precedence over a healthy instance, and one covers a probe key that can neither deliver, deploy nor write
- [x] 1.5 Confirm the derived `.github/tests` coverage asserts the static properties — the `sudoers` line's shape, the declaration's path and mode, an entry declaring a probe key without a deploy key, and the fixture image being pinned — and verify `python3 -m unittest discover --start-directory .github/tests` runs them

## 2. The window declaration

- [x] 2.1 Add a task to `ansible/roles/deploy_user` creating `/var/lib/platform-maintenance/` root-owned, group `docker`, mode `0775`, and verify a converge of the `default` scenario leaves it with exactly those owner, group and mode
- [x] 2.2 Document in the role's README the declaration's full path, that raising it is a `touch` and withdrawing it an `rm`, that an operator needs no `sudo` for either, that `app-probe` is what evaluates it, and that one left raised fails safe — verify by reading the README against design.md decision 5

## 3. The probe

- [x] 3.1 Extend `deploy_apps` with an optional `probe_public_key` field, defaulting to absent, and verify a converge of an entry that omits it installs no probe entry and no probe `sudoers` rule and does not fail
- [x] 3.2 Install `/usr/local/bin/app-probe`, root-owned `0755`, evaluating the declaration first, then the root-side existence read inside `platform-postgres-1`, then the application's own connection — verify each of the six tokens is reachable by the scenarios group 1 derived
- [x] 3.3 Implement the credential half per design.md decision 7 — a throwaway client container on `platform_edge` taking no fixed `--name`, its image read from `docker inspect platform-postgres-1 --format '{{.Config.Image}}'`, the whole connection time-bounded — and verify no password appears in the host's process listing or in `docker inspect` output during a probe
- [x] 3.4 Carry **both** client-supplied values — the password and the table name — on that container's standard input, interpolate the name into no command string at any layer, and dereference it as a `psql` variable (`-v tbl="$tbl"` against a fixed SQL literal using `:'tbl'`) so the quoting is `psql`'s; verify with a name carrying shell metacharacters and one carrying a quote that nothing executes and the probe answers `empty` or refuses, never anything else
- [x] 3.5 Require the table name to be an optionally schema-qualified identifier and refuse anything else non-zero rather than answering `empty`; verify `public.alembic_version` is accepted and resolved, since a check refusing a schema-qualified name would stop a correct deploy for nothing
- [x] 3.6 Resolve the token by matching stderr rather than exit status, and make any unmatched error exit non-zero with a diagnostic and no token — verify against the messages design.md's Context records, and verify `permission denied for database` emits no token
- [x] 3.7 Install `/usr/local/bin/deploy-probe`, `deploy`-owned `0755`, parsing one JSON object from standard input with `python3`, requiring `password` and `table`, refusing a `role` or `database` that disagrees with its fixed argument, and invoking `sudo /usr/local/bin/app-probe <app>` — verify a refusal emits no token and exits non-zero
- [x] 3.8 Render `/etc/sudoers.d/app-probe-<app>` per application declaring a probe key, fully qualified with no wildcard and `visudo`-validated, and verify `sudo` refuses `app-probe` with any other application name
- [x] 3.9 Install each probe key's `authorized_keys` entry with `restrict` and `command="/usr/local/bin/deploy-probe <app>"`, and verify both options are present on the probe entry and that the application's deploy entry is unchanged beside it

## 4. Inventory and key material

- [x] 4.1 Generate one probe keypair per existing `deploy_apps` entry that is to have one — both `staging.yml` and `production.yml` currently carry `platform` and `commerce-ops` — per the convention added in 5.2, and verify `ssh-keygen -lf` prints a fingerprint for each; private halves into `~/.ssh/`, never into a checkout. **`platform`'s probe key is deliberate and is not a copy-paste**: the stack holds no role or database named `platform` in the instance, so its probe can only ever answer `window-open` or `absent`, which makes it the operator's own check that a declaration is in force. Say so where the key is declared, or a later reader will read it as an oversight and remove it
- [x] 4.2 Add each probe public key to its entry in `ansible/inventory/host_vars/main-staging.yml` and `main-production.yml`, and verify `gitleaks` passes and no private half is staged
- [x] 4.3 Deliver each `commerce-ops` private half to that repository's matching Environment as a secret, and verify by listing that Environment's secret names — the value never enters this repository

## 5. Documentation

- [x] 5.1 Add to `platform/README.md`'s *Upgrading the PostgreSQL major version*: raising the declaration in step 1, withdrawing it at the end of step 4, a sentence in step 5 saying the gap it leaves is covered by `absent`, and a sentence saying the raise step is unenforced exactly as step 5 was — verify by re-reading the whole procedure for an ordering that would deadlock on itself
- [x] 5.2 Add the probe keypair to `docs/onboard-an-application.md` §2 alongside the deploy key, with its own comment convention, and verify §2's check commands name both entries
- [x] 5.3 Add to `docs/onboard-an-application.md` §4 the whole consumer contract — the JSON object the probe reads, the shape a table name must take and that one outside it refuses rather than answering `empty`, that unknown fields are ignored and an oversized object refused, what each of the six tokens means, which of them should stop a delivery, and that a non-zero exit with no token is a failed probe rather than an answer — and verify the token list and the input fields match the requirement exactly
- [x] 5.4 Say, where `absent` and its remedy are documented — §4 here and §3.2's rotation block — that the `platform` entry answers `absent` permanently and is the one case where that remedy must not be followed, and verify a reader meeting `absent` in either place finds the exception without having to read `group_vars`
- [x] 5.5 Say in `ansible/roles/deploy_user/README.md` that `app-probe` names `platform-postgres-1` and reads the image pin from it rather than carrying a copy, and why both are deliberate — verify against design.md decisions 7 and its risk of the same name

## 6. Verification

- [x] 6.1 Run `ansible/scripts/run-molecule test -s <scenario>` for each `deploy_user` scenario individually and verify each passes; then run `--all` and verify the SCENARIO RECAP names every scenario the role has

  **Both halves done, the second by CI, and read on a stricter property than the exit status.** All four scenarios were run individually on the workstation against the merged tree, each exiting 0. `--all` is unrunnable there — killed for memory three times — so it was run by `ansible-verify.yml`'s `molecule (deploy_user)` job on pull request #229 (run 35061827962, 18m48s), whose recap names all four scenarios the role has: `default`, `ghcr-credential-absent`, `ghcr-credential-rejected` and `probe-and-window`, every one `failed=0`.

  **Checked as `verify: Executed: Successful` per scenario rather than as an exit status**, and that distinction is not pedantry: a concurrent session met a run that aborted at `idempotence`, never reached `verify` — so asserted nothing — and still exited 0 with `failed=0`. CI reads that job by exit status alone, which is the weaker of the two checks, so its log was read directly for the property that matters. All four carry it; no `Idempotence test failed` line appears. `docs/backlog.md` entry 59 is where moving that check into `ansible/scripts/run-molecule` is proposed.

- [x] 6.2 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and verify it passes
- [x] 6.3 Run `pre-commit run --all-files` and verify it passes, the pinned Galaxy role having been installed into this working tree first
- [x] 6.4 Run `openspec validate --all` and verify it passes

## 7. Review

- [ ] 7.1 Commit the implementation, then dispatch `ai-toolkit:change-code-reviewer` over the committed diff, and verify the verdict permits proceeding before opening a pull request

## 8. Ship

- [ ] 8.1 Open the pull request, let continuous integration run, and wait for the operator's confirmation that it merged and that the converge is healthy — production's waits for an approval that nothing announces
- [ ] 8.2 Confirm the effect on staging, using only entries that already exist: probe `platform`, whose entry has no role or database of its own in the instance, and verify `absent`; probe `commerce-ops` with a wrong password and verify `credential-refused`; probe it correctly and verify `empty` or `populated`; stop nothing and instead verify `unreachable` from the Molecule scenario rather than against the live instance
- [ ] 8.3 Raise the declaration on staging and verify every probe answers `window-open` whatever the instance holds; withdraw it and verify they stop — and verify by `ls` that nothing is left raised afterwards
- [ ] 8.4 Archive the change: bring the branch back to the freshly fetched trunk, delete this change's entry from `docs/backlog.md`, commit the record, and open the pull request for it

Branch and working-tree removal are not tasks here and cannot be: they happen after the record's own pull request merges, which is after the commit that writes this file. They are recorded in prose instead, per this repository's conventions — remove the branch locally and on the remote, and the working tree from the main checkout, once every pull request this change opened has merged and nothing uncommitted or unpushed remains. Nothing here removes this working tree's Molecule namespace.
