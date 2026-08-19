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
- [ ] 3.2 **Partially done.** The operator generated the deploy keypair
      out-of-band (`ssh-keygen -t ed25519`, no passphrase — required since
      the CI job in `deploy-platform-compose-stack` invokes it
      non-interactively) and its public half is confirmed installed and
      working on the real host (see 3.5/3.6 below). **Still outstanding:**
      the private half currently exists only as a local file on the
      operator's machine — it SHALL still be added to the `production`
      Environment's GitHub secret (`PLATFORM_DEPLOY_SSH_KEY`, per
      `deploy-platform-compose-stack`'s tasks.md 3.4), not left there
      long-term. Leave this task open until that's done.
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
- [x] 3.4 Confirmed on the real target during implementation: `requiretty`
      isn't a setting this sudo build recognizes at all (`visudo -cf`
      rejects it as "unknown setting"), and Debian/Ubuntu's stock sudoers
      never sets it globally either — there is no default to be exempted
      from. No override line needed; see design.md's Risks entry.
- [x] 3.5 **Verified against the real host.** SSH as `deploy@<host>` with
      the generated key, non-interactively (`-o IdentitiesOnly=yes`, no
      PTY): `sudo /usr/local/bin/platform-compose-deploy` reached the real
      `docker compose pull` and failed only with "no configuration file
      provided" (expected — no `docker-compose.yml` exists in
      `/opt/platform` yet; that only lands once the CI deploy job runs).
      `sudo` itself did not reject the invocation. Along the way, two real
      bugs surfaced and were fixed: Ansible's legacy `-e "key=value"`
      extra-vars syntax silently truncates a value containing spaces at
      the first space (only `ssh-ed25519` was ever installed until the
      operator switched to JSON-form `-e`), and `group_vars/prod.yml` was
      missing `ansible_user: root` (this host has no other login).
- [x] 3.6 **Verified against the real host.** `sudo whoami` was denied
      (non-zero exit, sudo's own denial message — this host's sudo has
      `Defaults insults` enabled, unrelated to this change, but the
      denial itself is what matters). (This deliberately does not test
      whether `deploy` can influence the *content* the wrapper applies by
      writing to `/opt/platform` — it can, and that's an accepted trust
      boundary per design.md's Risks section, not a gap for this task to
      close.)

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
- [x] 4.3 Ran against the real `prod` host (`main-server`). The diff
      looked correct (default-deny UFW, SSH from the configured CIDR,
      HTTP/HTTPS from `0.0.0.0/0`) — but the `--check` run itself was
      misleading for the `apt`-heavy tasks: it reported "changed" for
      adding the Docker repo and running `apt update` without actually
      applying either, so the subsequent "install docker-ce"/"install
      fail2ban" tasks then failed for real against a stale, unrefreshed
      apt cache. Not a bug in this change — a known limitation of
      Ansible's check mode for tasks with real interdependencies. Noted
      here so a future re-run of this playbook against a fresh host isn't
      surprised by the same false alarm.
- [x] 4.4 Ran the full (non-check) playbook against `main-server` and
      confirmed: Docker installed and running (real `docker-ce`/
      `docker-compose-plugin`, resolved fine once the apt cache was
      actually refreshed), UFW active with the expected rules, fail2ban
      active, and the `deploy` account working end-to-end (3.5/3.6). Two
      more real fixes came out of this run: `visudo` on this host's sudo
      build rejects `requiretty` as an unrecognized setting (see 3.4;
      Debian/Ubuntu never set it globally anyway, so the defensive
      override line was simply removed), and `ansible_user: root` was
      missing from `group_vars/prod.yml` (this host has no other login,
      per `terraform/modules/server`'s key-only-at-creation design) —
      added.
- [x] 4.5 Re-ran the full playbook a second time against `main-server`
      after all fixes above: `ok=29 changed=0` — confirmed idempotent.
