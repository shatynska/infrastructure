## 1. Key material (out-of-band, before any converge)

- [x] 1.1 Generate the `ops-claude` keypair on the operator's workstation
      (`ssh-keygen -t ed25519 -f ~/.ssh/ops_claude -C ops-claude`). The private
      half stays there and is never committed, mirroring how every other
      keypair in this project is generated out-of-band.
- [x] 1.2 Record its public half as the single seeded entry of
      `ops_user_accounts` in `ansible/inventory/group_vars/prod.yml`
      (plaintext, as `deploy_apps`'s public keys already are).

## 2. Role

- [x] 2.1 Create `ansible/roles/ops_user/` with `tasks/main.yml`,
      `defaults/main.yml` and `README.md`. `defaults/main.yml` sets
      `ops_user_accounts: []` — an empty list is both safe and fail-safe here
      (unlike `deploy_user`'s credential variables, which have no safe
      default), so a host group that names no operators converges cleanly
      instead of aborting the whole playbook on an undefined variable.
      The name carries the role prefix deliberately: `ops_users` would trip
      ansible-lint's `var-naming[no-role-prefix]` the moment it is given a
      default, putting this task in direct conflict with 4.1. Prefixed-and-
      defaulted is what `hardening_web_allowed_cidrs` already does.
- [x] 2.2 Tasks: create each `present` entry's account (home directory,
      `/bin/bash`, `password: "!"`, `system: false`), append it to the `docker`
      group, and install its `authorized_keys` entry with `exclusive: true` and
      **no** `key_options`.
- [x] 2.3 Honour a per-entry `state`, defaulting to `present`. For an entry
      marked `absent`, revocation must actually complete in that one converge,
      not fail against a holder who happens to be logged in:
      1. terminate the account's live sessions and processes first
         (`loginctl terminate-user <name>` where systemd-logind is running,
         plus `pkill -KILL -u <name>`), guarded so it is a no-op — and reports
         `changed: false` — when the account does not exist or has no
         processes;
      2. then remove the account with `remove: true` (home directory) **and**
         `force: true`, so `userdel` does not refuse an account whose session
         has only just been torn down.
      Containers the account started through the Docker API are **not** killed
      by this: they run as root under `dockerd`, not as the account, and
      stopping another application's containers is not what revoking an
      operator should do. See design.md for what revocation does and does not
      reach.
- [x] 2.4 Assert no `sudoers.d` file is written by this role — this is an
      omission the role must never acquire, so state it in `README.md` rather
      than leaving it to be inferred from the absence of a task. `README.md`
      also records two standing obligations: (a) if an `AllowUsers`/
      `AllowGroups` directive is ever added to this host's `sshd_config`, every
      `ops_user_accounts` entry's account must be included in it, or these
      accounts are silently locked out; and (b) revocation means setting an entry's `state`
      to `absent` and **leaving the entry in the list** — deleting the entry
      outright is not revocation, since the role can only act on entries it is
      given, and produces a converge that leaves the account and its key live
      with no error to notice.
- [x] 2.5 Register the role in `ansible/playbooks/host-baseline.yml`, ordered
      after `docker` so the `docker` group exists before an account joins it.
      Add `ops_user` to `.ansible-lint`'s `mock_roles`, as every other
      by-name-referenced role in that playbook already is.

## 3. Tests

- [x] 3.1 Molecule scenario `ansible/roles/ops_user/molecule/default/`,
      following `deploy_user`'s scenario shape (systemd-capable image, galaxy
      requirements file, `ANSIBLE_ROLES_PATH` pointing at `roles/`). The
      converge runs `docker`, then **`deploy_user`**, then `ops_user` —
      `deploy_user` is included deliberately, because two of the delta spec's
      scenarios (the `/opt/<app>/.env` refusal and `deploy`'s restrictions
      being unaffected) are only meaningfully testable against the real
      `deploy` account and real `/opt/<app>` directories that role creates,
      not against a hand-rolled fixture. Supply `ghcr_pull_token` /
      `ghcr_pull_username` with the `MOLECULE_GHCR_PULL_*` env-lookup-with-
      placeholder-fallback pattern already proven in
      `ansible/roles/deploy_user/molecule/default/converge.yml`.
- [x] 3.2 `verify.yml` covering each scenario in the delta spec:
      - interactive shell (the account's shell field, and no forced command and
        no `restrict` in its `authorized_keys` line);
      - docker access without sudo (a real `docker ps` as the account);
      - absence of any `sudoers.d` file naming the account, and `sudo -n`
        refused;
      - inability to read `/opt/<app>/.env` **and** inability to overwrite
        `/opt/<app>/docker-compose.yml` — both halves of that scenario;
      - key rotation replacing rather than appending (`exclusive: true`);
      - `state: absent` removing the account **while a process owned by it is
        running**, so the revocation path is exercised in the case it exists
        for rather than only against an idle account;
      - a private-key-marker scan over the role's committed files, mirroring
        `deploy_user`'s equivalent.
      Note, recorded because the independent-test-author rule depends on it:
      `verify.yml` was edited once at implementation time, by the
      implementer rather than its author. Its private-key-marker scan
      matched `verify.yml` itself, since a scan written out literally
      contains the string it searches for and its target directory contains
      the scan — a false positive no implementation could clear. The pattern
      is now assembled at run time; no assertion was added, removed or
      loosened, and the same three key markers still match (re-verified
      against planted OpenSSH, RSA and PKCS#8 keys). Attributed in the
      file's own header and in test-manifest.md.
- [x] 3.3 Re-assert, from the same converge, that `deploy`'s keys still carry
      `restrict` + their per-application forced command after `ops_user` has
      run alongside `deploy_user`, and that no `ops_user_accounts` entry's
      account owns or has group access to any `/opt/<app>` path.

- [x] 3.4 Second Molecule scenario
      `ansible/roles/ops_user/molecule/revocation-steady-state/`, closing a
      gap a completion review found in 3.2: tasks.md 2.3 requires the
      session/process-termination step to report `changed: false` when the
      account does not exist, and the manifest delegated that to molecule's
      `idempotence` action — but every converge in the `default` scenario
      carries only `present` entries, so `idempotence` never reaches those
      guarded tasks. Because a revoked entry stays in `ops_user_accounts`
      permanently (deleting it is not revocation), a list carrying an
      `absent` tombstone is the steady state of any host that has ever
      revoked anyone, and it must converge to no change at all. The scenario
      seeds an account, revokes it on the first converge, and asserts the
      second reports `changed=0` — via `idempotence` and via an explicit
      named assertion, since an unreached runner action is exactly what went
      unnoticed the first time. It also asserts the account stayed gone and
      the live operator beside it was untouched, so `changed=0` cannot be
      satisfied by a role that does nothing.

      **This means `molecule test -s default` no longer runs the whole test
      suite for this role** — `molecule test --all` does, or each scenario
      by name. Whoever wires Ansible CI must invoke both.

## 4. Verification

- [x] 4.1 `ansible-lint` / `pre-commit run --all-files` introduces no new
      violation. Note the pre-existing baseline: `ansible-lint ansible/`
      already reports 3 failures in
      `ansible/roles/deploy_user/molecule/default/verify.yml`
      (2 × `risky-shell-pipe`, 1 × `yaml[line-length]`), unrelated to this
      change and out of its scope to fix.
- [x] 4.2 `molecule test --all` green for the new role. **Achieved
      2026-09-01**, once `repair-ansible-test-harness` fixed the defects that
      made it impossible. Both scenarios pass from a clean checkout with no
      credentials supplied: `default` (actions=12, failed=0) and
      `revocation-steady-state` (actions=12, failed=0).

      Note the command changed: this role has two scenarios, so
      `molecule test -s default` alone silently skips half its coverage.

      Recorded for history, because it shaped how this change was verified:
      when this change was implemented, `molecule test` could not run at all,
      for three defects that predated it and were reproduced here — an
      unpinned `ansible-core` resolving against a 2023-era Molecule docker
      driver, `geerlingguy.docker` installing a package with no
      `update_cache`, and `deploy_user`'s `docker_login` taking a real 403
      from the placeholder its own scenario supplied. All three reproduced
      identically against the existing `deploy_user` scenario on an
      unmodified tree, so `molecule test` was red on `main` independently of
      this change. The role was therefore verified by driving the scenario's
      own playbooks by hand — converge, a second converge reporting
      `changed=0`, `side_effect`, then `verify` at 0 failures, reproduced
      from a clean container. That workaround is no longer needed; see
      `openspec/changes/repair-ansible-test-harness`.

## 5. Rollout (operator-run; there is no CI for Ansible)

- [x] 5.1 Converge: `ansible-playbook playbooks/host-baseline.yml`, with the
      Vault password and the tailnet auth key available (the whole playbook
      re-runs, not just the new role — see design.md's Risks).
- [x] 5.2 Verify from the workstation, in one deliberate attempt rather than a
      retry loop (fail2ban's sshd jail is active, and a self-ban locks out root
      too — see design.md's Risks for the recovery route):
      `ssh -i ~/.ssh/ops_claude ops-claude@<host> 'id && docker ps'`, where
      `<host>` is this host's address as the repository itself supplies it —
      `terraform -chdir=terraform/environments/prod output -raw
      server_ipv4_address`, or the `ansible_host` the `hcloud` dynamic
      inventory resolves for the `prod` group — not a hostname carried only in
      an operator's own `~/.ssh/config`.
- [x] 5.3 Confirm `sudo -n true` fails, `cat /opt/commerce-ops/.env` is
      refused, and writing to `/opt/commerce-ops/docker-compose.yml` is
      refused, from that session.
- [x] 5.4 Confirm the operator's own root access still works, before closing
      the session that proved it.
- [x] 5.5 Idempotence: re-run `ansible-playbook playbooks/host-baseline.yml
      --check --diff` and confirm it reports no remaining change for this
      role. This lives here, after the converge, rather than in §4 with the
      other verification: on a host where the account does not yet exist,
      `ansible.posix.authorized_key` resolves its target user with
      `pwd.getpwnam` and errors in check mode rather than reporting a
      would-be change, so a pre-converge `--check` run reports a tooling
      artefact, not a defect.

**Rollout results (2026-09-01, against `main-server` / `2.29.14.98`).**
The account is live and behaves as the delta spec requires. Every assertion
`verify.yml` could only cover by proxy is now proven against the real host:

- Interactive session with a pty, and `docker ps` succeeding by `docker`
  group membership alone — the two things Molecule could not demonstrate.
- `id -nG` returns exactly `ops-claude docker`: no `sudo`, `admin` or
  `deploy` group.
- `sudo -nl` returns "user ops-claude may not run sudo on main-server" —
  the no-sudoers-entry refusal, not a password prompt. `/etc/sudoers.d/` is
  not even readable by the account.
- `cat /opt/commerce-ops/.env` and writing to that application's
  `docker-compose.yml` both refused by filesystem permissions.
- The operator's own root access confirmed still working before the session
  that proved it was closed.

**5.5 had to be scoped to this role, and why — no longer true, see below.**
The full `host-baseline.yml --check` run could not reach `ops_user`: the
`tailscale` role was not check-mode safe. Its "Check current tailnet connection status"
task is a plain `command`, which Ansible skips in check mode, and the next
task's `when` then calls `from_json` on an empty string and fails the run —
in a role that runs *before* `deploy_user` and `ops_user`. So `--check`
aborts before this change's role is ever evaluated. This is a pre-existing
defect in `tailscale`, unrelated to this change and outside its scope; the
fix is `check_mode: false` on the read-only status task, and it wants its
own change. Idempotence for `ops_user` was therefore verified by a
one-off check-mode play running only this role against `prod`:
`changed=0`.

**Superseded 2026-09-01.** `repair-ansible-test-harness` fixed that defect
(`check_mode: false` on the read-only status probe, plus a guard so the
consumer cannot parse an empty result). The full
`ansible-playbook playbooks/host-baseline.yml --check --diff` now completes
end to end against prod — `ok=44 failed=0` — and a real converge reports
`changed=0`. The scoped one-off play is no longer necessary; this role is
covered by the full playbook's own check run.

## 6. Consumer wiring (in the operator's environment, not this repository)

Recorded here, and in proposal.md's Impact, because it is a prerequisite for
the account being usable by its intended holder — not because this repository
carries it.

- [x] 6.1 Add a `prod` host entry to `~/.ssh/config` pinning `User ops-claude`,
      the identity file, and `IdentitiesOnly yes`.
- [x] 6.2 Add a Claude Code permission rule for that command shape — without
      one, prod-targeted SSH is refused outright by the auto-mode classifier
      (`prod` is a configured sensitive remote target), so the account would
      exist but be unusable by its intended holder. The rule is **ask-on-use
      and scoped to the `ops-claude` command shape** — not a blanket allow for
      prod SSH. That distinction is load-bearing, not cosmetic: design.md's
      only non-technical mitigation for this account's escalation path is that
      its key is used under the operator's supervision, and the per-command
      prompt *is* that supervision. A blanket allow would remove the
      mitigation, and would require design.md's Risks section to be re-argued
      without it.

**Consumer wiring done (2026-09-01), and verified end to end.** `~/.ssh/config`
gained a `Host prod` block pinning `User ops-claude`, the identity file and
`IdentitiesOnly yes` (`ssh -G prod` confirms all four). The permission rule
went into `.claude/settings.local.json` as an **`ask`** entry, not `allow`,
scoped to two command shapes — `Bash(ssh prod:*)` and
`Bash(ssh -i ~/.ssh/ops_claude ops-claude@:*)`. That file is gitignored (it is
a personal override), so this is recorded here rather than committed.

Proven working: `ssh prod 'id -nG && hostname && docker ps'` returns
`ops-claude docker` on `main-server` and lists the running platform and
commerce-ops containers. The account now does the thing it was created for.
