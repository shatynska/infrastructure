## 1. Baseline, before changing anything

- [x] 1.1 Record the current failure of the two defects observable today, so
      the fixes are shown to change something rather than assumed to. From a
      clean toolchain install: `molecule test -s default` in
      `ansible/roles/deploy_user/` (expect the driver failure), and
      `ansible-playbook playbooks/host-baseline.yml --check --diff` against
      prod (expect the abort inside `tailscale`). **Capture the exact error
      text of each** — 5.2 is written against the second one, so a paraphrase
      is not sufficient.
- [x] 1.2 Record the `ansible-lint ansible/` baseline. It is currently 3
      failures, all in `ansible/roles/deploy_user/molecule/default/verify.yml`
      (2 × `risky-shell-pipe`, 1 × `yaml[line-length]`) — pre-existing, and
      out of scope to fix here. Confirm the number before starting so a new
      violation is distinguishable. Run it the way this project runs it, from
      the `pre-commit` hook's own isolated environment; a hand-installed
      `ansible-lint` resolves a different `ansible-core` and is not the thing
      being baselined.

**Baselines captured (2026-09-01).**

- **1.1, defect 1 (driver).** On exactly what `requirements-test.txt` pins
  today plus an unpinned `ansible-core` (resolving 2.21.3),
  `molecule test -s default` in `ansible/roles/deploy_user/` exits **2** at
  the very first `destroy` action:
  `A 'when' expression failed: Conditional result (True) was derived from
  value of type 'str' at "<environment variable 'HOME'>". Conditionals must
  have a boolean result.` — raised from `molecule_plugins/docker/playbooks/
  destroy.yml`. The scenario never reaches `create`.
- **1.1, defect 4 (check mode).** Captured from the operator's own prod run:
  `[ERROR]: Task failed: A 'when' expression failed: The filter plugin
  'ansible.builtin.from_json' failed: Expecting value: line 1 column 1
  (char 0)`, origin `ansible/roles/tailscale/tasks/main.yml:56:9` — the
  `when:` of "Bring the host onto the tailnet", with "Check current tailnet
  connection status" reported as `skipping:` immediately above. This is the
  text 5.2's guard must be written against: `from_json` **was** reached, so
  the left limb evaluated false.
- **1.2, lint.** 3 failures, all pre-existing in
  `ansible/roles/deploy_user/molecule/default/verify.yml`; 45 files
  processed. **Deviation from the task as written:** `pre-commit` is not
  installed on this machine, so the hook's isolated environment could not be
  used. The baseline was taken with `ansible-lint` 26.8.0 on `ansible-core`
  2.21.3, and 7.3 must use the same build for the comparison to mean
  anything.

## 2. Toolchain pins

- [x] 2.1 In `ansible/requirements-test.txt`: bump `molecule` and
      `molecule-plugins[docker]` to current, and add an exact `ansible-core`
      pin. Keep the file's existing comment explaining why these are pinned
      exactly, and add why the pins moved forward rather than `ansible-core`
      moving back (design.md's first decision).
- [x] 2.2 Install exactly what the file now pins, into a clean environment,
      and confirm `molecule --version` reports the intended versions. An
      install that silently resolves something else means the pin is wrong.
- [x] 2.3 Confirm a hand-installed `ansible-lint` still runs on the new
      `ansible-core` pin. Note that the `pre-commit` hook is insulated from
      this pin — it resolves its own `ansible-core` in an isolated
      environment — so this check is about the local/manual invocation only,
      not about the hook.
- [x] 2.4 **Second baseline.** On the new toolchain, re-run `molecule test -s
      default` in `ansible/roles/deploy_user/`: the driver failure should be
      gone and the run should now reach and fail at
      `geerlingguy.docker`'s `python3-debian` install. Record it. This is the
      apt-cache defect becoming observable for the first time.

**§2 results.** `ansible/requirements-test.txt` now pins
`ansible-core==2.21.3`, `molecule==26.8.0`,
`molecule-plugins[docker]==26.7.15`. A clean install of that file resolves
exactly those three (2.2), and `ansible-lint` 26.8.0 installs and runs on
that `ansible-core` (2.3).

**2.4, second baseline.** On the new pins, `molecule test -s default` in
`ansible/roles/deploy_user/` no longer fails at `destroy` — it now passes
`destroy`, `syntax`, `create` and `prepare`, reaches `converge`, and exits
**2** on
`fatal: [deploy_user-role-instance]: FAILED! => {"changed": false, "msg":
"No package matching 'python3-debian' is available"}`. The driver defect is
fixed and the apt-cache defect is now the front-most one, which is exactly
the ordering this task predicted.

## 3. Molecule `prepare.yml` for scenarios that converge `docker`

- [x] 3.1 Add `prepare.yml` to each scenario that converges the `docker` role:
      `ansible/roles/docker/molecule/default/`,
      `ansible/roles/deploy_user/molecule/default/`, and
      `ansible/roles/ops_user/molecule/default/`. Each refreshes the apt cache
      and installs `python3-requests`.
      Two scenarios deliberately get nothing: `ops_user`'s
      `revocation-steady-state` (its own `prepare.yml` creates the `docker`
      group and seeds an account through the role, installing no engine) and
      `hardening` (its apt tasks already set `update_cache: true` — verify
      that rather than assuming it). The vendored
      `ansible/roles/geerlingguy.docker/molecule/` scenario is out of scope
      entirely: it is third-party content, gitignored, and not this
      repository's to run.
- [x] 3.2 Comment each file as fixture only, naming the upstream defect it
      works around (`geerlingguy.docker`'s `setup-Debian.yml` installing
      `python3-debian` with no `update_cache`) and the version checked, so a
      later reader can tell by version comparison whether it is still needed.
- [x] 3.3 Confirm `prepare` is not masking anything: it must not create,
      configure or pre-empt any artifact that a scenario's own `converge`
      or `verify` is responsible for.
- [x] 3.4 **Third baseline.** Re-run `molecule test -s default` in
      `ansible/roles/deploy_user/`: the apt failure should be gone and the run
      should now reach and fail at `docker_login` with a 403 from ghcr.io.
      Record it. This is the GHCR defect becoming observable, and it is the
      last of the three harness defects to surface.

**§3 results.** `prepare.yml` added to the three scenarios that converge
`docker` (`docker/default`, `deploy_user/default`, `ops_user/default`).

Both stated exclusions were verified rather than assumed (3.1):
`ansible/roles/hardening/tasks/main.yml` sets `update_cache: true` on both
its apt tasks (lines 12 and 70), so `hardening` needs none; and a sweep of
every `converge.yml` confirms exactly three scenarios converge the `docker`
role. The two scenarios added by the test-writing pass
(`ghcr-credential-absent`, `ghcr-credential-rejected`) already carry their
own `prepare.yml` of the same shape and converge no engine.

3.3: each file is fixture-only, in the sense that matters -- nothing in it
is the SUBJECT of an assertion, and nothing in it sets up the role under
test.

**Amended after 6b.2/6b.4.** As first written this said the files create "no
file that any `converge` or `verify` asserts on", and that is no longer
true of `deploy_user`'s: it now also writes `/etc/docker/daemon.json` and
seeds the two pre-migration artifacts (`platform-compose-deploy` and
`/etc/sudoers.d/deploy`) whose REMOVAL `verify.yml` asserts. That is
deliberate and is the point of 6b.2 -- the fixture must exist before
converge so the role is seen removing something real, and must not be
re-created between converge and idempotence. The distinction 3.3 exists to
protect still holds: `prepare` creates the precondition, the role performs
the behaviour, and `verify` asserts the role's effect, never the fixture's.

**3.4, third baseline.** `molecule test -s default` in `deploy_user/` now
passes `prepare`, gets through the whole `docker` role and almost all of
`deploy_user`, and exits **2** at the GHCR login with a real registry
refusal: `Forbidden ("Get "https://ghcr.io/v2/": denied: denied")`. The
apt-cache defect is fixed and the GHCR defect is now the front-most one --
the last of the three harness defects to surface, as predicted.

## 4. GHCR login guard

- [x] 4.1 Guard the GHCR login in `ansible/roles/deploy_user/tasks/main.yml`
      on **both** credential halves being non-empty — token *and* username.
      Guarding on the token alone lets a token-without-username configuration
      through, which then fails on an undefined variable rather than on
      anything the spec describes. Comment it with what the guard does and
      does not tolerate: an absent credential, not a rejected one.
- [x] 4.2 Make the skip **visible**. An absent credential is a legitimate
      configuration but must never be an invisible one: the likeliest
      real-world instance is a misnamed variable or an unloaded vars file on a
      host that does need the credential, and a bare `skipping:` line is
      indistinguishable from a deliberate absence. Emit an explicit message on
      the skip branch saying no GHCR credential was supplied and that private
      image pulls will fail.
- [x] 4.3 **Empty the placeholder** in both scenario converge files
      (`ansible/roles/deploy_user/molecule/default/converge.yml` and
      `ansible/roles/ops_user/molecule/default/converge.yml`): the
      `MOLECULE_GHCR_PULL_*` env lookup stays, but its fallback becomes an
      empty string. Without this the guard never fires — the current fallback
      is a non-empty dummy token, so the login still runs and still gets a 403
      (design.md's third decision). Update each file's surrounding comment,
      which currently explains the placeholder as if it were load-bearing.
- [x] 4.4 Record the accepted trade-off in
      `ansible/roles/deploy_user/README.md`: a rotated, revoked or mistyped
      token no longer fails the converge, and neither does a misnamed or
      unloaded variable — both instead surface at the next
      `docker compose pull` during a deploy. This is the third place it is
      written down (with design.md and the spec delta) and the one an operator
      debugging a failed pull is likeliest to reach.
- [x] 4.5 Confirm the guard does not weaken the supplied-credential path: with
      a deliberately invalid token supplied, the run must still fail. A guard
      that swallowed a 403 would satisfy the spec delta's second scenario and
      violate its third.

## 5. Check-mode safety in `tailscale`

- [x] 5.1 Add `check_mode: false` to the status probe in
      `ansible/roles/tailscale/tasks/main.yml`, with a comment saying why it
      is safe (the command is read-only) and why it is needed (Ansible skips
      `command` tasks under `--check`, and its consumer then parses an empty
      result).
- [x] 5.2 Guard the consuming task's condition so it cannot fail on an empty,
      absent or unparseable status result, independent of check mode — a
      `tailscaled` that is installed but not yet answering produces the same
      empty output. **Write the guard against the exact error 1.1 captured**,
      not against an assumed failure shape: the condition has two limbs
      (`rc != 0` and a `from_json` on `stdout`) and which one fails first
      determines what the guard has to cover.

      From the captured error, `from_json` **was** reached and received an
      empty string, so the left limb evaluated false. Since `or`
      short-circuits, the emptiness check therefore has to be its own earlier
      limb of the `or` — a filter applied inside or around the `from_json`
      call is evaluated too late to prevent it.
- [x] 5.3 State and honour the guard's polarity: an empty, absent or
      unparseable status result means **not connected**, so `tailscale up` is
      attempted. It must never be read as "already connected" — that would
      silently stop joining the tailnet on a degraded host, which is the exact
      case 5.2 exists for, and would leave the existing "Host Joins a Private
      Tailnet" requirement's first scenario unsatisfied on a real run.
- [x] 5.4 Confirm the fix did not invert the task's meaning in the other
      direction either: a host that is already connected must still be left
      alone, and `tailscale up` must still be skipped under `--check` (it is a
      `command`, so it should be — confirm rather than assume).

## 6. Scenario assertion repairs

- [x] 6.1 Repair the self-matching private-key scan in
      `ansible/roles/deploy_user/molecule/default/verify.yml`. It greps the
      role directory — which contains `verify.yml` — for the literal marker
      strings it is built from, so it matches its own text. Apply the same
      run-time pattern assembly already used in `ops_user`'s copy, and update
      that file's comment, which currently records this as latent and out of
      scope.
- [x] 6.2 Repair the GHCR plaintext scan in the same file. Its
      `head -c 15 | grep '^$ANSIBLE_VAULT'` test is a whole-file encryption
      check, so it flags `ansible/inventory/group_vars/prod.yml` — whose token
      is an **inline** `!vault` value in an otherwise plaintext file, which is
      this project's documented and correct pattern — plus both scenario
      converge files. Repair it by testing the **value** everywhere rather
      than excluding files by path: accept an assignment whose value is an
      inline `!vault` value or a `lookup('env', ...)` expression. A path
      exclusion would be simpler and is wrong — it would blind the scan
      permanently in the files most likely to acquire a pasted real token,
      since 7.2 means having a live token at the keyboard while editing
      exactly those files. Note the scope has grown: `deploy_user`'s two new
      scenarios also assign `ghcr_pull_token` as a `lookup('env', ...)`
      expression, deliberately so a value-shape test accepts them. A path
      exclusion would not list them and `molecule test --all` would go red on
      the new scenarios — which is the concrete reason this must be a value
      test, not a location test.
- [x] 6.3 Prove both repairs still fail when they should: plant a real
      private-key marker and a real plaintext `ghcr_pull_token` value, confirm
      each scan fires, then remove them. A false-positive repair that also
      stops catching true positives is worse than the false positive.
- [x] 6.4 Restructure — do not merely extend — the `sudo`-refusal assertion in
      `ansible/roles/ops_user/molecule/default/verify.yml`. It runs
      `sudo -n true` and accepts only `'password is required'` or
      `'not allowed'`. Against prod that command produced neither: its output
      was `sudo: I'm sorry ops-claude. I'm afraid I can't do that`, which
      means that host has `sudo`'s `insults` option enabled — and with it
      enabled the message is drawn at **random** from a compiled-in set, so no
      fixed string list can be reliable there. Adding one more accepted string
      would therefore buy nothing: the assertion runs inside the Molecule
      container, whose `sudo` deterministically produces `password is
      required`, which is already accepted and already passing.

      So: keep `rc != 0` as the load-bearing assertion, and replace the
      accepted-phrasing list with a discriminator that separates "refused by
      policy" from "sudo missing or broken" (a non-zero exit because `sudo` is
      not installed would otherwise satisfy the assertion for the wrong
      reason). The requirement's actual normative content — no `sudoers.d`
      file naming the account, and no privilege-granting group membership — is
      already asserted separately in this file and is what proves the policy.
      If any phrasing list survives, its comment must say it is
      container-scoped and is not a check on prod phrasing.

      Note also that the `"may not run sudo"` phrasing recorded in
      `add-ops-account`'s tasks.md came from `sudo -nl`, a *different*
      command; do not add it here and assume it covers `sudo -n true`.
- [x] 6.5 Confirm the restructured assertion still fails when it should: an
      account that *can* sudo must not satisfy it.

**§5 results.** `check_mode: false` on the status probe; the consumer's
condition gained three earlier `or` limbs (`rc | default(1)`, an
empty-stdout test, then a `^{` shape test) before the `from_json` call,
because `or` short-circuits and the captured failure showed `from_json`
being reached.

**Corrected after completion review.** The first form had only the `rc` and
empty-stdout limbs, while this record, tasks 5.2/5.3 and the role's own
comment all claimed an *unparseable* result was covered. It was not: a
non-empty, non-JSON stdout with rc 0 still reached `from_json` and raised
the identical `Expecting value: line 1 column 1` abort -- confirmed by
probe. That is the "same class of failure reachable by a different route"
design.md said must not be left open. The `^{` shape limb closes it and
cannot itself raise. Polarity verified
against five result shapes: already-connected does NOT attempt `tailscale
up`; needs-login, empty stdout, non-zero rc and a skipped task (no `rc` at
all) all DO, and none raises.

**§6 results.** The private-key scan now assembles its pattern at run time,
so it no longer matches its own text; verified it still fires on a planted
key and is silent once removed. The GHCR literal scan was rewritten to parse
each assignment's VALUE, continuation lines included -- a first attempt using
a line-oriented grep still produced two false positives, because both new
scenarios assign the token as a YAML *folded* scalar whose value sits on the
next line. Verified across four cases: inline literal caught, folded literal
caught, folded `lookup('env', ...)` accepted, clean tree silent.

6.4 restructured rather than extended the sudo assertion: exit status plus a
discriminator. It accepts prod's randomised insult phrasing, which the old
fixed string list REJECTED.

**Corrected after completion review.** The first form of the discriminator
was `'command not found' not in stderr`, and it could never fire:
`ansible.builtin.command` runs no shell, so no shell's not-found wording
ever reaches stderr -- a missing binary returns rc 2 with an EMPTY stderr and
the message on `.msg`. The limb passed unconditionally, and the result
recorded here claimed it "catches two wrong-reason passes the old form
allowed", which was false: `sudo` succeeding was already caught by
`rc != 0`. The check that appeared to prove it was run against a fabricated
`stderr` that the module cannot produce -- the expression was tested, not
the behaviour. Replaced with a POSITIVE check that sudo itself spoke
(`stderr is search('^sudo:')`), verified against the module's real output:
a missing binary now fails the assertion, and a real refusal
(`sudo: a password is required`) passes.

## 6b. Defects surfaced by the toolchain bump (added during implementation)

Two defects that no artifact predicted, both found by 7.1's first run and
both pre-existing. design.md's first risk bullet anticipated exactly this
("A failure surfaced by the bump is in scope to diagnose") and required the
finding be recorded either way.

- [x] 6b.1 `ansible/roles/docker/meta/main.yml` had no `galaxy_info`.
      Molecule 26.x's bundled `ansible-compat` resolves a fully-qualified
      role name for any role carrying a `meta/main.yml` before installing it
      locally, and refused the whole scenario with "Computed fully qualified
      role name of docker does not follow current galaxy requirements".
      Added `namespace`/`role_name` (plus the conventional descriptive
      keys). This is a metadata gap in our role, not a defect in the new
      Molecule, so it is fixed rather than treated as a reason to reconsider
      the pin.
- [x] 6b.2 `deploy_user`'s `default` scenario **could never pass
      idempotence**, by construction. Its `converge.yml` seeded the
      pre-migration `platform-compose-deploy` script and sudoers entry in
      `pre_tasks` on every run, and the role removed them again, so all four
      tasks reported `changed` on every converge. Never observed before,
      because the scenario had never run far enough to reach `idempotence`.
      Fixed by relocating the seeding to `prepare.yml`, which runs once and
      is not re-run for `idempotence` — the same pattern
      `revocation-steady-state` already uses. Coverage is identical:
      `verify.yml` still asserts the removal against real seeded artifacts.

- [x] 6b.3 `deploy_user`'s `default` scenario built its Compose fixture as
      `services: {}`, on the stated premise that this keeps
      `docker compose pull && up -d --wait` "a real, fast, no-registry-needed
      success". It is not: `docker compose pull` with zero services exits 1
      with "no service selected", so `app-deploy` failed and
      `deploy-receive`'s end-to-end assertion could never pass. Fixture now
      declares one minimal service (`alpine:3.19`, `sleep 3600`). The
      assertion is untouched -- it asserted rc == 0 before and still does.
      Note the new dependency this introduces: `deploy_user`'s `default`
      scenario now pulls `alpine:3.19` from Docker Hub inside the instance on
      every run. The suite still needs no credentials, but it does now need
      anonymous registry reachability, and a Docker Hub rate-limit would
      present as `app-deploy` returning non-zero -- i.e. it would look like a
      role defect rather than an environment one.
- [x] 6b.4 With a real service declared, container creation then failed under
      the default overlayfs snapshotter: docker-in-docker cannot stack
      another overlay ("failed to mount ... fstype: overlay ... invalid
      argument"). `prepare.yml` now writes `/etc/docker/daemon.json` with
      `storage-driver: vfs` and the containerd snapshotter disabled, before
      the `docker` role installs and first starts dockerd. Confirmed in a
      live instance: the full deploy-receive -> app-deploy -> compose pull ->
      up -d --wait chain returns 0. Scoped to this scenario alone, since it
      is the only one that runs a real container inside the instance and vfs
      is slow.

      Together, 6b.2/6b.3/6b.4 mean `deploy_user`'s `default` scenario has
      **never once run to completion** since it was written. Its assertions
      were never wrong; nothing had ever reached them.

## 7. Verification

- [x] 7.1 `molecule test --all` green from a clean checkout with **no**
      credentials supplied, for every role that has a scenario in this
      repository: `ops_user` (`default` and `revocation-steady-state`),
      `deploy_user` (`default`, `ghcr-credential-absent` and
      `ghcr-credential-rejected`), `docker`, and `hardening`. `hardening` is included
      because it is equally exposed to the toolchain bump, and design.md's
      only mitigation for that risk is every existing scenario being green.
      This is the change's primary success criterion.
- [x] 7.2 Re-run with `MOLECULE_GHCR_PULL_TOKEN` **and**
      `MOLECULE_GHCR_PULL_USERNAME` both set to real values, and confirm the
      suite is still green and that `deploy_user`'s existing conditional
      credential-store assertion actually fires rather than skipping. Both
      paths through the guard need to be exercised, not just the one that made
      the tests runnable.

      The two variables must be set **together**, and the harness must enforce
      that rather than trusting it. Once 4.3 empties the fallbacks and 4.1
      guards on both halves, a half-set environment makes the role skip the
      login while `deploy_user`'s `verify.yml` — whose two `when:` clauses key
      off the token alone — still asserts the credential store was configured.
      That fails with a message blaming the role for something the environment
      did. Condition both of those `when:` clauses on both variables, so a
      half-set environment skips instead of producing a misleading red.
- [x] 7.3 `ansible-lint ansible/` introduces no new violation against 1.2's
      baseline, run in the same environment 1.2 used.
- [x] 7.4 `ansible-playbook playbooks/host-baseline.yml --check --diff`
      against prod completes end to end instead of aborting in `tailscale`,
      and reports no unexpected change. This is the only way to observe the
      defect 5.1 fixes, so it is required, not optional.
- [x] 7.5 `ansible-playbook playbooks/host-baseline.yml` (a real converge)
      against prod still succeeds and is idempotent — the two role edits change
      behaviour, and a green `--check` is not proof that a real run is
      unaffected. Needs the Vault password available. Confirm specifically
      that the GHCR login still *runs* on prod (prod supplies a real token, so
      the guard must not skip it there).

**7.1 result — the change's primary success criterion, met.** From a clean
checkout with **no credentials supplied**, `molecule test --all` is green for
every role that has a scenario: `docker` (default), `hardening` (default),
`ops_user` (default, revocation-steady-state), `deploy_user` (default,
ghcr-credential-absent, ghcr-credential-rejected). Four roles, seven
scenarios, `failed=0` throughout, all four role exit codes 0.

`deploy_user`'s `default` completing is the notable one: between 6b.2, 6b.3
and 6b.4 it had never run to completion since it was written.

**7.3 result.** `ansible-lint ansible/` reports the same 3 pre-existing
violations as the 1.2 baseline and no new ones, now across 48 files (was
45). Same `ansible-lint` 26.8.0 / `ansible-core` 2.21.3 build as the
baseline, per 1.2's recorded deviation.

**7.4 result — the tailscale fix, proven on prod.**
`ansible-playbook playbooks/host-baseline.yml --check --diff` completes end
to end: `ok=44 changed=0..2 failed=0`. Before this change the same command
aborted inside `tailscale`, which runs third of five, so `deploy_user` and
`ops_user` were never evaluated at all. This was the only way to observe the
defect, which is why the task was mandatory rather than optional.

**7.5 result — real converge, idempotent, and the guard behaves correctly on
a credentialled host.** `ansible-playbook playbooks/host-baseline.yml`
reports `ok=44 changed=0 failed=0`: the two role edits changed nothing on
the live host. The GHCR check the task specifically demanded was confirmed
task-by-task, not inferred from the recap:

    TASK [deploy_user : Authenticate root's Docker credential store to GHCR]
    ok: [main-server]
    TASK [deploy_user : Report that GHCR authentication was skipped ...]
    skipping: [main-server]

So on prod the login runs and the skip-warning stays silent. `changed=0`
alone could not have established this -- a wrongly-skipped login raises no
error, which is precisely what makes it worth checking by name.

Note the `--check` run reported `changed=2` where the real run reported
`changed=0`. That is check mode being unable to dry-run some modules
(`docker_login` among them) and reporting "would change" where the real run
finds nothing to do -- not a discrepancy in the roles.

**7.2 complete (2026-09-02).**

Its harness half needed no token and has been completed after completion
review flagged the mis-attribution: `deploy_user`'s `verify.yml` conditioned
its two credential-store `when:` clauses on `MOLECULE_GHCR_PULL_TOKEN`
alone, so once 4.3 emptied the fallbacks a half-set environment made the
role skip the login while the assertion still fired -- a red blaming the
role for what the environment did. Both clauses now require the username
too, so a half-set environment skips instead.

Its credentialled run was then done with a real `read:packages` token.
`molecule test --all` for `deploy_user` is green on all three scenarios
(`default`, `ghcr-credential-absent`, `ghcr-credential-rejected`,
`failed=0`), and the credential-store check was confirmed **live rather
than skipped**:

    TASK [Report whether the live GHCR credential-store check will run]
    ok: "Running the GHCR credential-store check against a real supplied token."

Both halves of the task are therefore satisfied: the suite stays green with
a credential supplied, and `deploy_user`'s conditional credential-store
assertion actually fires. That matters because the assertion is skipped by
default -- a green suite alone would not have distinguished "the check
passed" from "the check never ran".

Two findings from getting there, worth keeping:

- **GHCR requires a *classic* PAT with `read:packages`.** A fine-grained
  token is refused with `403 ... denied: denied`, which reads like an
  expired or wrongly-scoped credential rather than a wrong *kind* of one.
- That first, rejected token produced an unplanned and better demonstration
  of the delta's third scenario than the synthetic one does: the real
  `deploy_user` role, mid-converge, refused to continue on a credential the
  registry rejected (`failed=1` at the login task). The guard's narrowness
  -- tolerating absence, never rejection -- is therefore proven against
  production code and a real registry, not only against a fixture. The offline path is
proven by 7.1, and `ghcr-credential-rejected` already exercises a real
registry refusal against ghcr.io, so the supplied-credential branch is not
wholly untested -- but the specific assertion that `deploy_user`'s
conditional credential-store check FIRES rather than skipping remains
unexercised. Anyone with a token can close it in one run.

## 8. Close out `add-ops-account`'s workarounds

- [x] 8.1 Run `molecule test --all` for the `ops_user` role and tick
      `add-ops-account`'s task 4.2, which is now genuinely achievable. Replace
      its recorded three-defect explanation with a short note that the defects
      were fixed by this change, keeping enough of the original text that the
      history is still legible.
- [x] 8.2 Update `add-ops-account`'s §5 note, which explains why its
      idempotence check had to be scoped to a single role, to say that the
      full `--check` run now works and to point at this change.
- [x] 8.3 With 4.2 ticked, `add-ops-account` has no open tasks. Confirm
      whether it is ready to archive (`openspec archive`) and say so
      explicitly rather than leaving it in an ambiguous state — a completed
      change should not sit un-archived on a task that is no longer blocked.

**8.3 — `add-ops-account` is ready to archive.** It now stands at 20/20
with no open tasks: its only outstanding item was 4.2, blocked solely by the
defects this change fixes, and that is now verified rather than waived. Its
account is live and proven on prod, its two Molecule scenarios pass, and
both of its recorded workarounds have been superseded in place rather than
deleted, so the history stays legible.

Archiving it is a separate, deliberate step (`openspec archive
add-ops-account`), left to the operator rather than done here — it folds
that change's delta into `openspec/specs/iac-host-configuration/` and is not
this change's to perform unasked.

## 9. Documentation

- [x] 9.1 Add a note to the README's local-setup section covering the
      environment-specific trap this change deliberately does not fix: a
      `~/.docker/config.json` naming credential helpers makes Molecule's
      Docker driver fail during `create`, and the workaround is to point
      `DOCKER_CONFIG` at a directory containing `{}`. Frame it as an
      environment note, not a repository defect (proposal.md, Non-goals).
- [x] 9.2 Note in the README that several roles now carry more than one
      Molecule scenario — `ops_user` has `default` and
      `revocation-steady-state`, and `deploy_user` has `default`,
      `ghcr-credential-absent` and `ghcr-credential-rejected` — so
      `molecule test -s default` silently skips most of the suite. It needs
      `molecule test --all`, or every scenario named explicitly.
