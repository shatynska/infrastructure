## 1. Key material (out-of-band, before any converge)

- [ ] 1.1 Generate the `ops-claude` keypair on the operator's workstation
      (`ssh-keygen -t ed25519 -f ~/.ssh/ops_claude -C ops-claude`). The private
      half stays there and is never committed, mirroring how every other
      keypair in this project is generated out-of-band.
- [ ] 1.2 Record its public half as the single seeded entry of `ops_users` in
      `ansible/inventory/group_vars/prod.yml` (plaintext, as `deploy_apps`'s
      public keys already are).

## 2. Role

- [ ] 2.1 Create `ansible/roles/ops_user/` with `tasks/main.yml`,
      `defaults/main.yml` and `README.md`. `defaults/main.yml` sets
      `ops_users: []` — an empty list is both safe and fail-safe here (unlike
      `deploy_user`'s credential variables, which have no safe default), so a
      host group that names no operators converges cleanly instead of aborting
      the whole playbook on an undefined variable.
- [ ] 2.2 Tasks: create each `present` entry's account (home directory,
      `/bin/bash`, `password: "!"`, `system: false`), append it to the `docker`
      group, and install its `authorized_keys` entry with `exclusive: true` and
      **no** `key_options`.
- [ ] 2.3 Honour a per-entry `state`, defaulting to `present`. For an entry
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
- [ ] 2.4 Assert no `sudoers.d` file is written by this role — this is an
      omission the role must never acquire, so state it in `README.md` rather
      than leaving it to be inferred from the absence of a task. `README.md`
      also records two standing obligations: (a) if an `AllowUsers`/
      `AllowGroups` directive is ever added to this host's `sshd_config`, every
      `ops_users` account must be included in it, or these accounts are
      silently locked out; and (b) revocation means setting an entry's `state`
      to `absent` and **leaving the entry in the list** — deleting the entry
      outright is not revocation, since the role can only act on entries it is
      given, and produces a converge that leaves the account and its key live
      with no error to notice.
- [ ] 2.5 Register the role in `ansible/playbooks/host-baseline.yml`, ordered
      after `docker` so the `docker` group exists before an account joins it.
      Add `ops_user` to `.ansible-lint`'s `mock_roles`, as every other
      by-name-referenced role in that playbook already is.

## 3. Tests

- [ ] 3.1 Molecule scenario `ansible/roles/ops_user/molecule/default/`,
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
- [ ] 3.2 `verify.yml` covering each scenario in the delta spec:
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
- [ ] 3.3 Re-assert, from the same converge, that `deploy`'s keys still carry
      `restrict` + their per-application forced command after `ops_user` has
      run alongside `deploy_user`, and that no `ops_users` account owns or has
      group access to any `/opt/<app>` path.

## 4. Verification

- [ ] 4.1 `ansible-lint` / `pre-commit run --all-files` introduces no new
      violation. Note the pre-existing baseline: `ansible-lint ansible/`
      already reports 3 failures in
      `ansible/roles/deploy_user/molecule/default/verify.yml`
      (2 × `risky-shell-pipe`, 1 × `yaml[line-length]`), unrelated to this
      change and out of its scope to fix.
- [ ] 4.2 `molecule test -s default` green for the new role.
## 5. Rollout (operator-run; there is no CI for Ansible)

- [ ] 5.1 Converge: `ansible-playbook playbooks/host-baseline.yml`, with the
      Vault password and the tailnet auth key available (the whole playbook
      re-runs, not just the new role — see design.md's Risks).
- [ ] 5.2 Verify from the workstation, in one deliberate attempt rather than a
      retry loop (fail2ban's sshd jail is active, and a self-ban locks out root
      too — see design.md's Risks for the recovery route):
      `ssh -i ~/.ssh/ops_claude ops-claude@<host> 'id && docker ps'`, where
      `<host>` is this host's address as the repository itself supplies it —
      `terraform -chdir=terraform/environments/prod output -raw
      server_ipv4_address`, or the `ansible_host` the `hcloud` dynamic
      inventory resolves for the `prod` group — not a hostname carried only in
      an operator's own `~/.ssh/config`.
- [ ] 5.3 Confirm `sudo -n true` fails, `cat /opt/commerce-ops/.env` is
      refused, and writing to `/opt/commerce-ops/docker-compose.yml` is
      refused, from that session.
- [ ] 5.4 Confirm the operator's own root access still works, before closing
      the session that proved it.
- [ ] 5.5 Idempotence: re-run `ansible-playbook playbooks/host-baseline.yml
      --check --diff` and confirm it reports no remaining change for this
      role. This lives here, after the converge, rather than in §4 with the
      other verification: on a host where the account does not yet exist,
      `ansible.posix.authorized_key` resolves its target user with
      `pwd.getpwnam` and errors in check mode rather than reporting a
      would-be change, so a pre-converge `--check` run reports a tooling
      artefact, not a defect.

## 6. Consumer wiring (in the operator's environment, not this repository)

Recorded here, and in proposal.md's Impact, because it is a prerequisite for
the account being usable by its intended holder — not because this repository
carries it.

- [ ] 6.1 Add a `prod` host entry to `~/.ssh/config` pinning `User ops-claude`,
      the identity file, and `IdentitiesOnly yes`.
- [ ] 6.2 Add a Claude Code permission rule for that command shape — without
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
