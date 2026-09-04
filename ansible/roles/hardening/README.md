# hardening

UFW (default-deny incoming, SSH always allowed, HTTP/HTTPS opt-in) and
fail2ban (sshd jail). Implements `iac-host-configuration`'s "Host-Level
Security Owned by Ansible, Cloud Firewall Owned by Terraform" requirement.

## Keeping UFW in sync with the cloud firewall

**`terraform/modules/server`'s `hcloud_firewall` resource is not the
source of truth for this role's variables, and vice versa.** The two are
maintained by hand in two separate places:

- Cloud firewall (what's reachable from the internet at all):
  `terraform/environments/prod/terraform.tfvars`'s `ssh_allowed_cidrs`
  and `web_allowed_cidrs`.
- Host firewall (defense-in-depth on top of whatever the cloud layer
  already allows): `ansible/inventory/group_vars/prod.yml`'s
  `hardening_ssh_allowed_cidrs` and `hardening_web_allowed_cidrs`.

Whenever either side's CIDR list changes, check the other. Leaving UFW
stricter than the cloud firewall silently blocks traffic the cloud layer
already permits (this happened once already — see
`openspec/changes/bootstrap-ansible-host-baseline/design.md`'s Context
section for the `web_allowed_cidrs` correction that prompted this note).
Leaving UFW looser than the cloud firewall doesn't expose anything new
(the cloud layer still blocks it first), but defeats the point of having
host-level defense-in-depth at all.

## Tailnet-scoped rules

UFW's default-deny-incoming policy applies to the `tailscale0` interface
the same as the public one, so any service meant to be reachable only from
tailnet peers needs its own explicit allow rule here, in addition to
whatever binds it to the tailnet interface at the application level. Two
such rules exist today, both restricted to `100.64.0.0/10` (the tailnet's
CGNAT range — not publicly routable, so only authenticated tailnet peers
can present it as a source):

- SSH (22) — additive to the public-interface SSH rule above, not a
  replacement for it. See `connect-platform-deploy-via-tailscale`'s
  design.md for why this is needed.
- Grafana (3000) — the platform monitoring stack's dashboard, added by
  `add-platform-monitoring`. Grafana binds to the host's tailnet-literal
  IP rather than `0.0.0.0`; this rule is what actually lets tailnet peers
  reach it despite that binding.

## Variables

| Variable | Default | Description |
|---|---|---|
| `hardening_ssh_allowed_cidrs` | *(required, no default)* | List of CIDR strings allowed to reach SSH (22). |
| `hardening_web_allowed_cidrs` | `[]` | List of CIDR strings allowed to reach HTTP/HTTPS (80/443). Empty means closed. |
