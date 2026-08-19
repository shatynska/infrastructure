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

## Variables

| Variable | Default | Description |
|---|---|---|
| `hardening_ssh_allowed_cidrs` | *(required, no default)* | List of CIDR strings allowed to reach SSH (22). |
| `hardening_web_allowed_cidrs` | `[]` | List of CIDR strings allowed to reach HTTP/HTTPS (80/443). Empty means closed. |
