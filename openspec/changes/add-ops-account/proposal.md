## Why

Nobody can look at this host without being root. The prod server has exactly
one interactive login — `root`, via the operator's personal key — because
`terraform/modules/server` created it with a single SSH key and no password.
The only other account, `deploy`, is deliberately shell-less: every key on it
carries `restrict,command="/usr/local/bin/deploy-receive <app>"`, so it can
deliver a deploy and nothing else.

That was fine while the host only ever needed to receive deploys. It stopped
being fine now that a deployed application (`commerce-ops`) is misbehaving in
ways its own logs, container state and database are the only witness to.
Diagnosing that today means handing out `root` — on a box that also carries
the shared platform stack (Traefik) and will carry roughly three more
applications.

The immediate holder of this access is a Claude Code session running on the
operator's workstation. That is a reason to make the account attributable and
independently revocable, not a reason to skip it: an agent that can read logs
and container state directly is the difference between diagnosing a fault and
relaying screenshots of it.

## What Changes

- Add an `ops_user` Ansible role provisioning one or more **unprivileged,
  interactive** operator accounts, driven by a committed `ops_users` list of
  `{name, public_key, state}` entries — the same loop shape `deploy_user`
  already uses for `deploy_apps`.
- Each account: a normal home directory, `/bin/bash`, no password (`!`),
  membership of the `docker` group, its own `authorized_keys` entry with **no**
  forced command and **no** `restrict` (an operator needs a pty), and
  **no `sudoers.d` entry of any kind**.
- Seed the list with one entry, `ops-claude`, whose public key is generated
  out-of-band on the operator's workstation; only its public half is committed.
- Register the role in `ansible/playbooks/host-baseline.yml`, after `docker`
  (the `docker` group must exist before an account can join it).
- Molecule scenario covering the role, mirroring `deploy_user`'s.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `iac-host-configuration`: adds one requirement, "Unprivileged Operator
  Accounts Support Interactive Host Inspection". No existing requirement
  changes — in particular the `deploy` account's forced-command model is
  untouched, and this change deliberately does **not** relax it.

## Impact

- `ansible/roles/ops_user/` — new role (tasks, defaults, README, molecule).
- `ansible/playbooks/host-baseline.yml` — one added role entry.
- `ansible/inventory/group_vars/prod.yml` — new `ops_users` list. Public keys
  only; safe to commit, exactly as `deploy_apps`'s public keys already are.
- No Terraform change. No cloud-firewall change. No UFW change: SSH (22) is
  already permitted from the operator CIDR and from the tailnet, and this
  change adds an account on that existing path rather than a new path.
- No sshd configuration change: this host's `sshd_config` carries no
  `AllowUsers`/`AllowGroups` directive (the `hardening` role configures UFW and
  fail2ban only), so a new account with an authorized key is reachable without
  touching sshd.
- Convergence is a manual `ansible-playbook` run by the operator, as every
  Ansible change on this host is — there is no CI pipeline for Ansible.

## Non-goals

- **Not a confidentiality or integrity boundary against the account's own
  holder.** `docker` group membership is root-equivalent by escalation. See
  design.md; this change buys blast-radius containment, attribution and
  revocability, and claims nothing more.
- Not a replacement for the operator's root key.
- Not a tightening of the `deploy` account, and not a Docker socket proxy —
  both noted as deferred alternatives in design.md.
