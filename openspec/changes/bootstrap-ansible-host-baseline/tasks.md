## 1. Docker role

- [x] 1.1 Add `ansible/playbooks/host-baseline.yml` targeting the `prod`
      inventory group.
- [x] 1.2 Add a `docker` role (or a play referencing `geerlingguy.docker`
      directly) that installs Docker per the pinned version in
      `ansible/requirements.yml`.
- [x] 1.3 Verify: `ansible-galaxy install -r ansible/requirements.yml`
      succeeds, then `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check` passes.
- [x] 1.4 Add `ansible/inventory/group_vars/prod.yml` (read automatically
      by the `prod` group the dynamic inventory already resolves) setting
      `hardening_ssh_allowed_cidrs: ["176.104.184.0/24"]` and
      `hardening_web_allowed_cidrs: ["0.0.0.0/0"]`, mirroring
      `terraform/environments/prod/terraform.tfvars`'s `ssh_allowed_cidrs`
      and `web_allowed_cidrs` exactly (see task 2.3's sync-documentation
      requirement — these values are duplicated by hand, not generated
      from Terraform, so they can drift).

## 2. Host hardening role

- [x] 2.1 Add a `hardening` role: UFW with a default-deny incoming policy,
      allowing SSH (22) from `ssh_allowed_cidrs`-equivalent sources, and
      HTTP/HTTPS (80/443) gated behind a variable that defaults to closed
      (a safe default for the role in general) but, in this project's
      actual `prod` group_vars, set to `["0.0.0.0/0"]` — matching
      `web_allowed_cidrs`, which is already set in
      `terraform/environments/prod/terraform.tfvars` (corrected from an
      earlier, incorrect assumption that it was unset — see design.md's
      Context). Leaving it at the role's closed default in prod's
      group_vars would leave the host firewall stricter than the cloud
      layer, silently blocking the Traefik traffic the cloud firewall
      already permits.
- [x] 2.2 Add fail2ban to the same role with a sane default jail for SSH.
- [x] 2.3 Document in the role's README or a comment that UFW's allowed
      ports must be kept in sync with `terraform/modules/server`'s
      `hcloud_firewall` rules — one is not the source of truth for the
      other.

## 3. Deploy account role

- [x] 3.1 Add a `deploy_user` role: creates the `deploy` system account (no
      password, key-only, no group membership beyond its own primary
      group), with home directory `/opt/platform` (mode `0750`, owned
      `deploy:deploy` — created by this task, not left to the follow-up
      platform change), and installs an authorized public key sourced from
      Ansible Vault or a variable supplied at run time (not committed in
      plaintext).
- [ ] 3.2 **Operator action, not completable by this implementation pass:**
      generate the deploy keypair out-of-band (not by the playbook) and
      store the private key in Ansible Vault, or hand it directly to a
      GitHub Actions secret. If a GitHub Actions secret: it SHALL be added
      to the `production` Environment's secrets specifically, never a
      plain repository-level secret — design.md's accepted content-layer
      risk depends on this key being unreadable until the `production`
      Environment's approval gate is passed, which only holds if it's
      Environment-scoped from the moment it's created. The role's README
      already documents this path (`ansible/roles/deploy_user/README.md`);
      generating and storing the actual keypair requires deciding on/access
      to the real secret store, which this pass does not have.
- [x] 3.3 Add the fixed wrapper script `/usr/local/bin/platform-compose-deploy`
      (root:root, mode `0755`) containing exactly:
      `cd /opt/platform && docker compose pull && docker compose up -d --wait`
      (as a template/copy, not built from any user-supplied argument). Add a
      `sudoers.d` drop-in granting `deploy` exactly
      `ALL=(root) NOPASSWD: /usr/local/bin/platform-compose-deploy` — no
      wildcard, no arguments accepted. Do NOT add `deploy` to the `docker`
      group and do NOT grant `sudo` on raw `docker`/`docker compose`
      invocations — both allow argument injection (`run`/`exec` with `-v`,
      `--privileged`, `--user root`) that is root-equivalent.
- [x] 3.4 Ensure `deploy` is exempted from any `requiretty` sudo default (or
      confirm none is set), since the follow-up platform change's CI job
      will invoke `sudo` non-interactively over SSH with no PTY.
- [ ] 3.5 **Blocked on 3.2 and a real/disposable host** (not available in
      this implementation pass — no live host, no generated keypair to
      SSH with): using a minimal placeholder `docker-compose.yml` placed
      in `/opt/platform` for this verification only (not committed — no
      real Compose content is part of this change), SSH as `deploy@<host>`
      with the generated key, run `sudo /usr/local/bin/platform-compose-deploy`,
      and confirm it succeeds non-interactively (no PTY, matching how CI
      will invoke it). The equivalent behavior is exercised statically by
      `ansible/roles/deploy_user/molecule/default/verify.yml`, but Molecule
      itself could not be run in this environment either — see task 4.1's
      note.
- [ ] 3.6 **Blocked, same reason as 3.5.** Verify: the same session CANNOT
      run any other `sudo` command — `sudo whoami`, `sudo docker ...`, and
      `sudo /usr/local/bin/platform-compose-deploy` with any extra argument
      appended — confirm each attempt is denied. (This deliberately does
      not test whether `deploy` can influence the *content* the wrapper
      applies by writing to `/opt/platform` — it can, and that's an
      accepted trust boundary per design.md's Risks section, not a gap for
      this task to close.)

## 4. Verification

- [x] 4.1 Run `ansible-lint` against the new playbook and roles. Passes
      clean at the `production` profile (`ansible-lint ansible/`). Also
      added `.ansible-lint` (excludes the gitignored, third-party
      `ansible/roles/geerlingguy.docker/` from linting, and mocks this
      project's own three roles for Molecule scenario files, whose role
      references resolve only via each `molecule.yml`'s
      `ANSIBLE_ROLES_PATH`, not standalone `ansible-lint`/`ansible.cfg`).
      **`molecule test` itself could not be run** — this sandbox has no
      Docker daemon reachable (WSL without Docker Desktop's WSL
      integration enabled) — so the Molecule scenarios are unexecuted,
      not just unreviewed; only static `ansible-lint`/YAML-parse checks
      ran against them.
- [x] 4.2 Run `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check`. Passes (inventory itself doesn't resolve without a
      real `HCLOUD_TOKEN`, which this pass has no reason to hold — that's
      an expected, separate warning, not a syntax failure).
- [ ] 4.3 **Blocked — needs a real/disposable host and credentials this
      pass does not have.** Run the playbook in `--check` mode against a
      disposable/staging host (or the `prod` host if no staging
      environment exists yet) and review the diff before an unchecked run.
- [ ] 4.4 **Blocked, same reason as 4.3.** Run the full playbook against
      the target host and confirm: Docker is installed and running, UFW is
      active with the expected rules, fail2ban is active, and the `deploy`
      account can reach the host and trigger
      `sudo /usr/local/bin/platform-compose-deploy` (per tasks 3.5–3.6).
- [ ] 4.5 **Blocked, same reason as 4.3.** Re-run the full playbook a
      second time against the same host and confirm it reports no changes
      (idempotent run).
