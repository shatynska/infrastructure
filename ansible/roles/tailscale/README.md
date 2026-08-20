# tailscale

Joins the prod host to a private tailnet, so the
`deploy-platform-compose-stack` GitHub Actions deploy job can reach it over
SSH without widening `ssh_allowed_cidrs`/`hardening_ssh_allowed_cidrs`
beyond the operator's own CIDR. See
`openspec/changes/connect-platform-deploy-via-tailscale/design.md` for the
full rationale, including why a UFW rule (not just this role) was needed
for SSH to actually be reachable over the new `tailscale0` interface.

## Key storage

`tailscale_auth_key` is a genuine secret — it grants tailnet-join
capability, unlike `deploy_user`'s `deploy_user_public_key`. Generate it
in the Tailscale admin console (Settings → Keys → Generate auth key):
**reusable**, **not ephemeral** (this host is a persistent tailnet member,
not a throwaway CI node), and store it the same way as the deploy
account's private key — Ansible Vault, or a run-time variable, never
committed.

After the host successfully joins for the first time, go to the admin
console's device list and enable **"Disable key expiry"** on this
specific device — otherwise the tailnet connection will eventually require
re-authentication, which isn't automated by this role.

## Not covered by this role

**Tailscale ACL configuration** (which tailnet members can reach which
others) is done in the Tailscale admin console / API, entirely outside
this repo's IaC. At implementation time this tailnet has only two kinds of
member — this host, and short-lived CI runners — and no ACL restricts CI
runners to only the host; any tailnet member can reach this host's
tailnet-scoped SSH port. Accepted as a real, current gap (see the parent
change's design.md Risks) rather than solved here — revisit if the
tailnet's membership grows.

**The GitHub Actions side** (the deploy job joining the same tailnet via
`tailscale/github-action`, authenticated by a separate OAuth client) is
not part of this role — see `.github/workflows/platform-deploy.yml`.

## Variables

| Variable | Default | Description |
|---|---|---|
| `tailscale_auth_key` | *(required, no default)* | Auth key used to join this host to the tailnet. Reusable, non-ephemeral. |
