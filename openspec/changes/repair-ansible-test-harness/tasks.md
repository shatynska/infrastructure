## 1. Baseline, before changing anything

- [ ] 1.1 Record the current failure of the two defects observable today, so
      the fixes are shown to change something rather than assumed to. From a
      clean toolchain install: `molecule test -s default` in
      `ansible/roles/deploy_user/` (expect the driver failure), and
      `ansible-playbook playbooks/host-baseline.yml --check --diff` against
      prod (expect the abort inside `tailscale`). **Capture the exact error
      text of each** — 5.2 is written against the second one, so a paraphrase
      is not sufficient.
- [ ] 1.2 Record the `ansible-lint ansible/` baseline. It is currently 3
      failures, all in `ansible/roles/deploy_user/molecule/default/verify.yml`
      (2 × `risky-shell-pipe`, 1 × `yaml[line-length]`) — pre-existing, and
      out of scope to fix here. Confirm the number before starting so a new
      violation is distinguishable. Run it the way this project runs it, from
      the `pre-commit` hook's own isolated environment; a hand-installed
      `ansible-lint` resolves a different `ansible-core` and is not the thing
      being baselined.

## 2. Toolchain pins

- [ ] 2.1 In `ansible/requirements-test.txt`: bump `molecule` and
      `molecule-plugins[docker]` to current, and add an exact `ansible-core`
      pin. Keep the file's existing comment explaining why these are pinned
      exactly, and add why the pins moved forward rather than `ansible-core`
      moving back (design.md's first decision).
- [ ] 2.2 Install exactly what the file now pins, into a clean environment,
      and confirm `molecule --version` reports the intended versions. An
      install that silently resolves something else means the pin is wrong.
- [ ] 2.3 Confirm a hand-installed `ansible-lint` still runs on the new
      `ansible-core` pin. Note that the `pre-commit` hook is insulated from
      this pin — it resolves its own `ansible-core` in an isolated
      environment — so this check is about the local/manual invocation only,
      not about the hook.
- [ ] 2.4 **Second baseline.** On the new toolchain, re-run `molecule test -s
      default` in `ansible/roles/deploy_user/`: the driver failure should be
      gone and the run should now reach and fail at
      `geerlingguy.docker`'s `python3-debian` install. Record it. This is the
      apt-cache defect becoming observable for the first time.

## 3. Molecule `prepare.yml` for scenarios that converge `docker`

- [ ] 3.1 Add `prepare.yml` to each scenario that converges the `docker` role:
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
- [ ] 3.2 Comment each file as fixture only, naming the upstream defect it
      works around (`geerlingguy.docker`'s `setup-Debian.yml` installing
      `python3-debian` with no `update_cache`) and the version checked, so a
      later reader can tell by version comparison whether it is still needed.
- [ ] 3.3 Confirm `prepare` is not masking anything: it must not create,
      configure or pre-empt any artifact that a scenario's own `converge`
      or `verify` is responsible for.
- [ ] 3.4 **Third baseline.** Re-run `molecule test -s default` in
      `ansible/roles/deploy_user/`: the apt failure should be gone and the run
      should now reach and fail at `docker_login` with a 403 from ghcr.io.
      Record it. This is the GHCR defect becoming observable, and it is the
      last of the three harness defects to surface.

## 4. GHCR login guard

- [ ] 4.1 Guard the GHCR login in `ansible/roles/deploy_user/tasks/main.yml`
      on **both** credential halves being non-empty — token *and* username.
      Guarding on the token alone lets a token-without-username configuration
      through, which then fails on an undefined variable rather than on
      anything the spec describes. Comment it with what the guard does and
      does not tolerate: an absent credential, not a rejected one.
- [ ] 4.2 Make the skip **visible**. An absent credential is a legitimate
      configuration but must never be an invisible one: the likeliest
      real-world instance is a misnamed variable or an unloaded vars file on a
      host that does need the credential, and a bare `skipping:` line is
      indistinguishable from a deliberate absence. Emit an explicit message on
      the skip branch saying no GHCR credential was supplied and that private
      image pulls will fail.
- [ ] 4.3 **Empty the placeholder** in both scenario converge files
      (`ansible/roles/deploy_user/molecule/default/converge.yml` and
      `ansible/roles/ops_user/molecule/default/converge.yml`): the
      `MOLECULE_GHCR_PULL_*` env lookup stays, but its fallback becomes an
      empty string. Without this the guard never fires — the current fallback
      is a non-empty dummy token, so the login still runs and still gets a 403
      (design.md's third decision). Update each file's surrounding comment,
      which currently explains the placeholder as if it were load-bearing.
- [ ] 4.4 Record the accepted trade-off in
      `ansible/roles/deploy_user/README.md`: a rotated, revoked or mistyped
      token no longer fails the converge, and neither does a misnamed or
      unloaded variable — both instead surface at the next
      `docker compose pull` during a deploy. This is the third place it is
      written down (with design.md and the spec delta) and the one an operator
      debugging a failed pull is likeliest to reach.
- [ ] 4.5 Confirm the guard does not weaken the supplied-credential path: with
      a deliberately invalid token supplied, the run must still fail. A guard
      that swallowed a 403 would satisfy the spec delta's second scenario and
      violate its third.

## 5. Check-mode safety in `tailscale`

- [ ] 5.1 Add `check_mode: false` to the status probe in
      `ansible/roles/tailscale/tasks/main.yml`, with a comment saying why it
      is safe (the command is read-only) and why it is needed (Ansible skips
      `command` tasks under `--check`, and its consumer then parses an empty
      result).
- [ ] 5.2 Guard the consuming task's condition so it cannot fail on an empty,
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
- [ ] 5.3 State and honour the guard's polarity: an empty, absent or
      unparseable status result means **not connected**, so `tailscale up` is
      attempted. It must never be read as "already connected" — that would
      silently stop joining the tailnet on a degraded host, which is the exact
      case 5.2 exists for, and would leave the existing "Host Joins a Private
      Tailnet" requirement's first scenario unsatisfied on a real run.
- [ ] 5.4 Confirm the fix did not invert the task's meaning in the other
      direction either: a host that is already connected must still be left
      alone, and `tailscale up` must still be skipped under `--check` (it is a
      `command`, so it should be — confirm rather than assume).

## 6. Scenario assertion repairs

- [ ] 6.1 Repair the self-matching private-key scan in
      `ansible/roles/deploy_user/molecule/default/verify.yml`. It greps the
      role directory — which contains `verify.yml` — for the literal marker
      strings it is built from, so it matches its own text. Apply the same
      run-time pattern assembly already used in `ops_user`'s copy, and update
      that file's comment, which currently records this as latent and out of
      scope.
- [ ] 6.2 Repair the GHCR plaintext scan in the same file. Its
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
- [ ] 6.3 Prove both repairs still fail when they should: plant a real
      private-key marker and a real plaintext `ghcr_pull_token` value, confirm
      each scan fires, then remove them. A false-positive repair that also
      stops catching true positives is worse than the false positive.
- [ ] 6.4 Restructure — do not merely extend — the `sudo`-refusal assertion in
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
- [ ] 6.5 Confirm the restructured assertion still fails when it should: an
      account that *can* sudo must not satisfy it.

## 7. Verification

- [ ] 7.1 `molecule test --all` green from a clean checkout with **no**
      credentials supplied, for every role that has a scenario in this
      repository: `ops_user` (`default` and `revocation-steady-state`),
      `deploy_user` (`default`, `ghcr-credential-absent` and
      `ghcr-credential-rejected`), `docker`, and `hardening`. `hardening` is included
      because it is equally exposed to the toolchain bump, and design.md's
      only mitigation for that risk is every existing scenario being green.
      This is the change's primary success criterion.
- [ ] 7.2 Re-run with `MOLECULE_GHCR_PULL_TOKEN` **and**
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
- [ ] 7.3 `ansible-lint ansible/` introduces no new violation against 1.2's
      baseline, run in the same environment 1.2 used.
- [ ] 7.4 `ansible-playbook playbooks/host-baseline.yml --check --diff`
      against prod completes end to end instead of aborting in `tailscale`,
      and reports no unexpected change. This is the only way to observe the
      defect 5.1 fixes, so it is required, not optional.
- [ ] 7.5 `ansible-playbook playbooks/host-baseline.yml` (a real converge)
      against prod still succeeds and is idempotent — the two role edits change
      behaviour, and a green `--check` is not proof that a real run is
      unaffected. Needs the Vault password available. Confirm specifically
      that the GHCR login still *runs* on prod (prod supplies a real token, so
      the guard must not skip it there).

## 8. Close out `add-ops-account`'s workarounds

- [ ] 8.1 Run `molecule test --all` for the `ops_user` role and tick
      `add-ops-account`'s task 4.2, which is now genuinely achievable. Replace
      its recorded three-defect explanation with a short note that the defects
      were fixed by this change, keeping enough of the original text that the
      history is still legible.
- [ ] 8.2 Update `add-ops-account`'s §5 note, which explains why its
      idempotence check had to be scoped to a single role, to say that the
      full `--check` run now works and to point at this change.
- [ ] 8.3 With 4.2 ticked, `add-ops-account` has no open tasks. Confirm
      whether it is ready to archive (`openspec archive`) and say so
      explicitly rather than leaving it in an ambiguous state — a completed
      change should not sit un-archived on a task that is no longer blocked.

## 9. Documentation

- [ ] 9.1 Add a note to the README's local-setup section covering the
      environment-specific trap this change deliberately does not fix: a
      `~/.docker/config.json` naming credential helpers makes Molecule's
      Docker driver fail during `create`, and the workaround is to point
      `DOCKER_CONFIG` at a directory containing `{}`. Frame it as an
      environment note, not a repository defect (proposal.md, Non-goals).
- [ ] 9.2 Note in the README that several roles now carry more than one
      Molecule scenario — `ops_user` has `default` and
      `revocation-steady-state`, and `deploy_user` has `default`,
      `ghcr-credential-absent` and `ghcr-credential-rejected` — so
      `molecule test -s default` silently skips most of the suite. It needs
      `molecule test --all`, or every scenario named explicitly.
