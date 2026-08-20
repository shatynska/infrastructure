## 1. Tailscale on the host

- [x] 1.1 Add a `tailscale` Ansible role: install Tailscale via its
      official apt repository, pinned to an exact package version
      (`1.102.3`) per this project's external-dependency convention.
      Confirmed directly against `pkgs.tailscale.com` that the repo
      publishes a `resolute` line and that exact version — not assumed.
- [x] 1.2 Added `tailscale_auth_key` (no default, required, `no_log:
      true`). `tailscale up` only runs when `tailscale status --json`
      shows the host isn't already `Running`, so a re-run doesn't
      re-register an already-joined node.
- [x] 1.3 Wired the `tailscale` role into
      `ansible/playbooks/host-baseline.yml`.
- [x] 1.4 Added `ansible/roles/tailscale/README.md`.

## 2. Host firewall

- [x] 2.1 Added a UFW rule to the `hardening` role allowing SSH (22) via
      `src: 100.64.0.0/10` — additive, `hardening_ssh_allowed_cidrs` and
      the existing public-interface rule untouched.
- [x] 2.2 Verified against the real host: `ufw status verbose` shows
      `22/tcp ALLOW IN 176.104.184.0/24` (unchanged) and
      `22/tcp ALLOW IN 100.64.0.0/10` (new) side by side.

## 3. GitHub Actions

- [x] 3.1 Added a `tailscale/github-action@v4` step to `platform-deploy.yml`'s
      `deploy` job, before "Set up the deploy SSH key", authenticating via
      `TAILSCALE_OAUTH_CLIENT_ID`/`TAILSCALE_OAUTH_SECRET`. Also added
      `ping: ${{ secrets.PLATFORM_DEPLOY_HOST }}` (not originally
      speced) — the action's own docs note new tailnet peers propagate
      with a brief, eventually-consistent delay; without waiting for
      that, the deploy steps immediately after could race it.
- [x] 3.2 Confirmed by code inspection: the new step adds no `permissions:`
      beyond what the `deploy` job already declares (no `id-token: write`
      needed — using an OAuth client, not workload identity federation),
      and both new secrets are referenced only inside the `deploy` job,
      which already requires `production` Environment approval — same
      gating as `PLATFORM_DEPLOY_SSH_KEY`.

## 4. Cutover

- [x] 4.1 **Operator action, done.** Generated the host's Tailscale auth
      key (reusable, non-ephemeral) and the CI OAuth client
      (`tag:ci`-scoped).
- [x] 4.2 **Operator action, done.** `TAILSCALE_OAUTH_CLIENT_ID` and
      `TAILSCALE_OAUTH_SECRET` added to the `production` GitHub Environment.
- [x] 4.3 Ran the host-baseline playbook with the auth key supplied; the
      host joined the tailnet (`tailscale status --json` showing
      `BackendState: Running` on a subsequent idempotent re-run,
      `changed=0`).
- [x] 4.4 **Operator action, done.** `PLATFORM_DEPLOY_HOST` repointed to
      the host's tailnet address.
- [x] 4.5 Verified against a real merge to `main`
      (github.com/shatynska/infrastructure/actions/runs/32350184847): the
      `diff` job posted to the job summary, the `deploy` job connected via
      Tailscale (DERP-relayed — direct P2P didn't establish, which is
      normal/expected, not a failure), SSHed in, and
      `platform-compose-deploy` pulled both images and brought up
      `platform-traefik-1`/`platform-postgres-1`, both reporting
      `Healthy`. The `ssh-keyscan` timeout that prompted this change did
      not recur.

## 5. Verification

- [x] 5.1 Ran `ansible-lint ansible/` — clean at the `production` profile.
      Two new findings fixed along the way: the `tailscale` role needed
      adding to `.ansible-lint`'s `mock_roles` (same false-positive class
      as the other three roles, and — corrected here — that mocking turns
      out to be needed for the real playbook's role resolution too, not
      only Molecule scenario files, per `.ansible-lint`'s updated
      comment), and the `tailscale up` command task needed an explicit
      `changed_when: true`.
- [x] 5.2 Ran `ansible-playbook ansible/playbooks/host-baseline.yml
      --syntax-check` — passes.
- [x] 5.3 Confirmed: the operator's own `ssh root@<public IP>` access
      continued working throughout this change's implementation and after
      (used directly to run diagnostic commands like `ufw status verbose`
      post-rollout) — unaffected by the new tailnet-scoped rule.
