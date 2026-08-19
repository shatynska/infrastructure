## Why

`iac-host-configuration` already specifies dynamic inventory, a pinned Docker
runtime, host-level hardening, and a scope boundary that stops at the
container runtime — but none of it is implemented yet: `ansible/playbooks/`
and `ansible/roles/` hold only `.gitkeep`. Meanwhile, `platform/` (the
Traefik + Postgres Compose stack, proposed separately) needs a way to reach
the host that isn't a human's personal SSH key. This change writes the
missing playbook and adds the one piece of host state that stack's deploy
mechanism will depend on: a restricted deploy account.

## What Changes

- Add an Ansible playbook (and supporting role structure) that installs
  Docker via the already-pinned `geerlingguy.docker` role
  (`ansible/requirements.yml`), satisfying the existing "Container Runtime
  Installed via Pinned External Role or Equivalent" requirement.
- Add host-level hardening: a UFW firewall mirroring what the Hetzner cloud
  firewall allows (SSH from the configured CIDRs today; HTTP/HTTPS once
  `web_allowed_cidrs` is set in Terraform) and fail2ban, satisfying the
  existing "Host-Level Security Owned by Ansible, Cloud Firewall Owned by
  Terraform" requirement.
- **New requirement** on `iac-host-configuration`: provision a dedicated,
  restricted `deploy` system account and SSH keypair, scoped to operating
  Docker Compose within `platform/`'s directory on the host rather than a
  general-purpose login. This is consumed by a separate, not-yet-proposed
  change that builds the GitHub Actions workflow deploying `platform/`'s
  Compose stack over SSH — this change only prepares the account and access
  that workflow will authenticate as. The account's home directory is
  `/opt/platform`, and its only privileged capability is triggering one
  fixed, argument-free wrapper script via `sudoers` that runs `docker
  compose pull && docker compose up -d --wait` there — not `docker`-group
  membership, and not a `sudoers` rule that forwards raw `docker compose`
  arguments, both of which were tried and rejected on review for being
  root-equivalent (`docker compose run`/`exec` accept flags that bind-mount
  the host filesystem or run as root). This closes escalation via the
  *invocation* (no arguments, no alternate command) but, because the
  account necessarily owns the directory the wrapper reads from, not
  escalation via the *content* of the Compose file it writes there —
  that residual trust is accepted deliberately and documented in
  design.md, not silently assumed away.
- No application or Compose content is added. Ansible's scope stops at the
  container runtime and host security, per `iac-platform-services`'s
  existing "Platform Stack Deployment Is Not Ansible's Responsibility"
  requirement — this change does not template a Compose file or invoke any
  Compose lifecycle command.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `iac-host-configuration`: implements the existing Docker-runtime and
  host-security requirements (previously specified, not yet built), and adds
  a new requirement for a restricted deploy account/keypair that a future
  platform-deploy workflow will use.

## Impact

- `ansible/playbooks/`, `ansible/roles/` — new playbook and role content
  (currently empty).
- `ansible/inventory/hcloud.yml` — unchanged, but this is the inventory the
  new playbook targets.
- No changes to `terraform/`, `platform/`, or any application repository.
- Depends on nothing outside this repo. A follow-up change (platform Compose
  stack + its GitHub Actions deploy workflow) depends on this one: it needs
  the deploy account/key this change creates to exist first.
