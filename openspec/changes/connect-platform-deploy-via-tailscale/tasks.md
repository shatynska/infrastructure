## 1. Tailscale on the host

- [ ] 1.1 Add a `tailscale` Ansible role: install Tailscale via its
      official apt repository, pinned to an exact package version per
      this project's external-dependency convention. Verify the repo
      actually publishes a line for this host's Ubuntu codename
      (`resolute`) before assuming it — Docker's repo needed no fallback
      in the end, but that was confirmed, not assumed; do the same check
      here.
- [ ] 1.2 Add a `tailscale_auth_key` variable (no default, required —
      same shape as `deploy_user_public_key`'s "no default" pattern, but
      this one is a genuine secret, sourced from Vault or a run-time
      variable, never committed). Run `tailscale up --authkey=...`
      (idempotently — check `tailscale status` first so re-running the
      playbook doesn't re-register or error on an already-joined node).
- [ ] 1.3 Wire the `tailscale` role into
      `ansible/playbooks/host-baseline.yml`.
- [ ] 1.4 Add a README to the role documenting the auth-key storage
      pattern (mirror `ansible/roles/deploy_user/README.md`'s "Key
      storage" section) and that Tailscale ACL configuration is out of
      scope for this repo's IaC (done in Tailscale's admin console).

## 2. Host firewall

- [ ] 2.1 Add a UFW rule to the `hardening` role allowing SSH (22) via
      `src: 100.64.0.0/10` (the tailnet CGNAT range) — consistent with
      this role's existing rules, which are all `src:`-scoped rather than
      interface-scoped (see `ansible/roles/hardening/tasks/main.yml`'s
      current SSH/HTTP/HTTPS rules). Additive to, not replacing, the
      existing public-interface SSH rule. Do not touch
      `hardening_ssh_allowed_cidrs`'s existing value or that rule.
- [ ] 2.2 Verify: after this role runs, `ufw status verbose` shows both
      the original public-interface SSH rule (unchanged) and the new
      tailnet-scoped one.

## 3. GitHub Actions

- [ ] 3.1 Add a `tailscale/github-action` step to `platform-deploy.yml`'s
      `deploy` job, before the existing "Set up the deploy SSH key" step,
      authenticating via a Tailscale OAuth client (`TAILSCALE_OAUTH_CLIENT_ID`
      / `TAILSCALE_OAUTH_SECRET` — new secrets, scoped to the `production`
      Environment, same as every other secret this job uses).
- [ ] 3.2 Confirm the new step declares no broader permissions than the
      job already has, and that the two new secrets are unreadable by any
      job that hasn't passed the `production` Environment gate (same
      check as `deploy-platform-compose-stack`'s tasks.md 4.1, extended to
      cover these two).

## 4. Cutover

- [ ] 4.1 **Operator action.** Generate the host's Tailscale auth key in
      the Tailscale admin console; generate the OAuth client for CI
      (scoped/tagged appropriately). Store both per task 1.2/1.4's and
      3.1's documented paths.
- [ ] 4.2 **Operator action.** Add `TAILSCALE_OAUTH_CLIENT_ID` and
      `TAILSCALE_OAUTH_SECRET` to the `production` GitHub Environment.
- [ ] 4.3 Run the host-baseline playbook with the auth key supplied;
      confirm the host appears in the Tailscale admin console and has a
      stable tailnet address (IP or MagicDNS name).
- [ ] 4.4 **Operator action.** Update the `PLATFORM_DEPLOY_HOST` secret's
      value to that tailnet address.
- [ ] 4.5 Verify: trigger the deploy workflow (e.g. a no-op `platform/**`
      change) and confirm the `deploy` job joins the tailnet and
      successfully SSHes into the host over it — the specific failure
      that prompted this change (`ssh-keyscan` timing out) SHALL NOT
      recur.

## 5. Verification

- [ ] 5.1 Run `ansible-lint` against the new role.
- [ ] 5.2 Run `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check`.
- [ ] 5.3 Confirm the operator's own direct SSH access (public IP, their
      CIDR) still works unchanged after this change lands.
