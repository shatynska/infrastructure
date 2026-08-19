## ADDED Requirements

### Requirement: Host Joins a Private Tailnet for Non-Operator SSH Access
Ansible SHALL join the prod host to a private tailnet (Tailscale), and SHALL permit SSH (22) on that tailnet's interface in addition to — not instead of — the existing operator-CIDR-restricted SSH rule on the public interface. This exists so that a mechanism other than the operator's own network (e.g. the GitHub Actions deploy job in `iac-platform-deploy-pipeline`) can reach the host without widening SSH access on the public internet.

This requirement does not change, and SHALL NOT be used to justify changing, the existing prohibition on `ssh_allowed_cidrs`/`hardening_ssh_allowed_cidrs` containing `0.0.0.0/0` — the tailnet is an additional, private access path, not a replacement for the public-interface restriction.

#### Scenario: Host is reachable over the tailnet
- **WHEN** the host-baseline playbook runs with a valid Tailscale auth key supplied
- **THEN** the host SHALL join the configured tailnet and SHALL accept SSH connections arriving on the tailnet interface

#### Scenario: Public-interface SSH restriction is unaffected
- **WHEN** the tailnet is configured
- **THEN** the existing UFW rule restricting SSH on the public interface to the operator's CIDR SHALL remain unchanged, and no rule permitting SSH from `0.0.0.0/0` on any interface SHALL be introduced

#### Scenario: Tailscale auth key is never committed
- **WHEN** the host's Tailscale auth key is generated or rotated
- **THEN** it SHALL be stored outside version control (Ansible Vault or a run-time variable) and SHALL NOT appear in plaintext anywhere in the repository
