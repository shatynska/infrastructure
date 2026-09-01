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
      `defaults/main.yml` (documenting `ops_users` with no committed default)
      and `README.md`.
- [ ] 2.2 Tasks: create each entry's account (home directory, `/bin/bash`,
      `password: "!"`, `system: false`), append it to the `docker` group, and
      install its `authorized_keys` entry with `exclusive: true` and **no**
      `key_options`.
- [ ] 2.3 Honour a per-entry `state`: `absent` removes the account and its home
      directory. Default `present`.
- [ ] 2.4 Assert no `sudoers.d` file is written by this role — this is an
      omission the role must never acquire, so state it in `README.md` rather
      than leaving it to be inferred from the absence of a task.
- [ ] 2.5 Register the role in `ansible/playbooks/host-baseline.yml`, ordered
      after `docker` so the `docker` group exists before an account joins it.

## 3. Tests

- [ ] 3.1 Molecule scenario `ansible/roles/ops_user/molecule/default/`,
      converging `docker` then `ops_user`, following `deploy_user`'s scenario
      shape (systemd-capable image, galaxy requirements file,
      `ANSIBLE_ROLES_PATH` pointing at `roles/`).
- [ ] 3.2 `verify.yml` covering each scenario in the delta spec: interactive
      shell (shell field and no forced command in `authorized_keys`), docker
      access without sudo, absence of any `sudoers.d` entry naming the account,
      inability to read a `0600 deploy:deploy` fixture under `/opt/<app>`, key
      rotation replacing rather than appending, and `state: absent` removing
      the account.
- [ ] 3.3 Re-assert that `deploy`'s keys still carry `restrict` + forced
      command after this role has converged alongside `deploy_user`.

## 4. Verification

- [ ] 4.1 `ansible-lint` / `pre-commit run --all-files` clean.
- [ ] 4.2 `molecule test -s default` green for the new role.
- [ ] 4.3 `ansible-playbook playbooks/host-baseline.yml --check --diff` against
      prod shows only the intended additions.

## 5. Rollout (operator-run; there is no CI for Ansible)

- [ ] 5.1 Converge: `ansible-playbook playbooks/host-baseline.yml`, with the
      Vault password and the tailnet auth key available (the whole playbook
      re-runs, not just the new role — see design.md's Risks).
- [ ] 5.2 Verify from the workstation, in one deliberate attempt rather than a
      retry loop (fail2ban's sshd jail is active): `ssh -i ~/.ssh/ops_claude
      ops-claude@fuperia.shatynska.com 'id && docker ps'`.
- [ ] 5.3 Confirm `sudo -n true` fails and `cat /opt/commerce-ops/.env` is
      refused from that session.
- [ ] 5.4 Confirm the operator's own root access still works, before closing
      the session that proved it.

## 6. Consumer wiring (in the operator's environment, not this repository)

- [ ] 6.1 Add a `prod` host entry to `~/.ssh/config` pinning `User ops-claude`,
      the identity file, and `IdentitiesOnly yes`.
- [ ] 6.2 Add an explicit Claude Code permission rule for that command shape —
      without one, prod-targeted SSH is refused by the auto-mode classifier
      (`prod` is a configured sensitive remote target), so the account would
      exist but be unusable by its intended holder.
