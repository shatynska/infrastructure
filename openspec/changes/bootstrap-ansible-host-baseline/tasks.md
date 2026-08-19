## 1. Docker role

- [ ] 1.1 Add `ansible/playbooks/host-baseline.yml` targeting the `prod`
      inventory group.
- [ ] 1.2 Add a `docker` role (or a play referencing `geerlingguy.docker`
      directly) that installs Docker per the pinned version in
      `ansible/requirements.yml`.
- [ ] 1.3 Verify: `ansible-galaxy install -r ansible/requirements.yml`
      succeeds, then `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check` passes.

## 2. Host hardening role

- [ ] 2.1 Add a `hardening` role: UFW with a default-deny incoming policy,
      allowing SSH (22) from `ssh_allowed_cidrs`-equivalent sources, and
      HTTP/HTTPS (80/443) gated behind a variable that defaults to closed
      until the corresponding Terraform `web_allowed_cidrs` change lands.
- [ ] 2.2 Add fail2ban to the same role with a sane default jail for SSH.
- [ ] 2.3 Document in the role's README or a comment that UFW's allowed
      ports must be kept in sync with `terraform/modules/server`'s
      `hcloud_firewall` rules — one is not the source of truth for the
      other.

## 3. Deploy account role

- [ ] 3.1 Add a `deploy-user` role: creates the `deploy` system account (no
      password, key-only, no group membership beyond its own primary
      group), with home directory `/opt/platform` (mode `0750`, owned
      `deploy:deploy` — created by this task, not left to the follow-up
      platform change), and installs an authorized public key sourced from
      Ansible Vault or a variable supplied at run time (not committed in
      plaintext).
- [ ] 3.2 Generate the deploy keypair out-of-band (not by the playbook) and
      store the private key in Ansible Vault, or hand it directly to a
      GitHub Actions secret. If a GitHub Actions secret: it SHALL be added
      to the `production` Environment's secrets specifically, never a
      plain repository-level secret — design.md's accepted content-layer
      risk depends on this key being unreadable until the `production`
      Environment's approval gate is passed, which only holds if it's
      Environment-scoped from the moment it's created. Document the chosen
      path in the role's README.
- [ ] 3.3 Add the fixed wrapper script `/usr/local/bin/platform-compose-deploy`
      (root:root, mode `0755`) containing exactly:
      `cd /opt/platform && docker compose pull && docker compose up -d --wait`
      (as a template/copy, not built from any user-supplied argument). Add a
      `sudoers.d` drop-in granting `deploy` exactly
      `ALL=(root) NOPASSWD: /usr/local/bin/platform-compose-deploy` — no
      wildcard, no arguments accepted. Do NOT add `deploy` to the `docker`
      group and do NOT grant `sudo` on raw `docker`/`docker compose`
      invocations — both allow argument injection (`run`/`exec` with `-v`,
      `--privileged`, `--user root`) that is root-equivalent.
- [ ] 3.4 Ensure `deploy` is exempted from any `requiretty` sudo default (or
      confirm none is set), since the follow-up platform change's CI job
      will invoke `sudo` non-interactively over SSH with no PTY.
- [ ] 3.5 Verify, using a minimal placeholder `docker-compose.yml` placed
      in `/opt/platform` for this verification only (not committed — no
      real Compose content is part of this change): SSH as `deploy@<host>`
      with the generated key, run `sudo /usr/local/bin/platform-compose-deploy`,
      and confirm it succeeds non-interactively (no PTY, matching how CI
      will invoke it).
- [ ] 3.6 Verify: the same session CANNOT run any other `sudo` command —
      `sudo whoami`, `sudo docker ...`, and
      `sudo /usr/local/bin/platform-compose-deploy` with any extra argument
      appended — confirm each attempt is denied. (This deliberately does
      not test whether `deploy` can influence the *content* the wrapper
      applies by writing to `/opt/platform` — it can, and that's an
      accepted trust boundary per design.md's Risks section, not a gap for
      this task to close.)

## 4. Verification

- [ ] 4.1 Run `ansible-lint` against the new playbook and roles.
- [ ] 4.2 Run `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check`.
- [ ] 4.3 Run the playbook in `--check` mode against a disposable/staging
      host (or the `prod` host if no staging environment exists yet) and
      review the diff before an unchecked run.
- [ ] 4.4 Run the full playbook against the target host and confirm: Docker
      is installed and running, UFW is active with the expected rules,
      fail2ban is active, and the `deploy` account can reach the host and
      trigger `sudo /usr/local/bin/platform-compose-deploy` (per tasks
      3.5–3.6).
- [ ] 4.5 Re-run the full playbook a second time against the same host and
      confirm it reports no changes (idempotent run).
