## Why

`deploy-platform-compose-stack`'s deploy job SSHes into the prod host as
the `deploy` account, but SSH is restricted (at both the Hetzner cloud
firewall and the host's UFW) to the operator's own home/office CIDR. A
real deploy run confirmed this: `ssh-keyscan` timed out, because
GitHub-hosted Actions runners connect from an unpredictable IP range
outside that CIDR. Opening SSH to `0.0.0.0/0` was considered and rejected
— `terraform/modules/server/variables.tf`'s `ssh_allowed_cidrs` variable
has a hard validation forbidding it, and the archived
`bootstrap-hetzner-iac` change's design.md names "a firewall is required,
not optional" as this project's #1 security control, anticipating this
exact scenario and explicitly warning against defaulting to `0.0.0.0/0`
under pressure. This change gives the deploy job a way to reach the host
without widening that guardrail: a private tunnel (Tailscale) both sides
join.

## What Changes

- Add a `tailscale` Ansible role, installing and joining the prod host to
  a private tailnet, wired into `ansible/playbooks/host-baseline.yml`
  alongside the existing `docker`/`hardening`/`deploy_user` roles.
- Add a narrow UFW rule allowing SSH (22) on the host's `tailscale0`
  interface / from the tailnet's CGNAT range — distinct from, and not a
  widening of, the existing public-interface SSH rule scoped to the
  operator's CIDR. No change to the Hetzner cloud firewall: Tailscale
  connectivity is outbound-initiated on both ends and doesn't route
  through the public interface at all.
- Add a `tailscale/github-action` step to `platform-deploy.yml`'s
  `deploy` job, joining the runner to the same tailnet (via a Tailscale
  OAuth client, new secrets scoped to the `production` Environment like
  every other secret this job already uses) before the existing SSH
  steps run.
- Repoint the existing `PLATFORM_DEPLOY_HOST` secret's value from the
  host's public IP to its Tailscale address — no new secret, no workflow
  code change for that value; only its content changes (an operator
  action, tracked in tasks.md, not something this change itself sets).
- Explicitly out of scope: the operator's own direct SSH access is
  unchanged — they keep using their existing CIDR-restricted public path.
  This change only gives CI a way in.

## Capabilities

### New Capabilities
- `iac-platform-deploy-pipeline`: adds a requirement that the deploy job
  reaches the host over a private tailnet rather than the public internet.
  Filed as New, not Modified: this capability was introduced by
  `deploy-platform-compose-stack`, which hasn't been archived into
  `openspec/specs/` yet, so `iac-platform-deploy-pipeline` is genuinely
  absent from specsRoot today — the same convention `deploy-platform-
  compose-stack`'s own proposal.md followed when it first introduced this
  capability.

### Modified Capabilities
- `iac-host-configuration`: adds a requirement that the prod host joins a
  private tailnet, with SSH reachable there in addition to (not instead
  of) the existing CIDR-restricted public path.

## Impact

- `ansible/roles/tailscale/`, `ansible/playbooks/host-baseline.yml` — new
  role, wired in.
- `ansible/roles/hardening/` — one new UFW rule (tailnet-scoped SSH).
- `.github/workflows/platform-deploy.yml` — one new step, no change to
  existing steps' logic (they already parameterize the host via a secret).
- New GitHub secrets: a Tailscale OAuth client id/secret, scoped to the
  `production` Environment.
- Operator action: update `PLATFORM_DEPLOY_HOST`'s value once the host is
  on the tailnet; generate/store the host's Tailscale auth key the same
  way the deploy keypair was handled (out-of-band, Vault or run-time
  variable, never committed).
- Depends on `bootstrap-ansible-host-baseline` and `deploy-platform-
  compose-stack` (both already implemented and merged) — this change only
  adds connectivity between what they already built.
