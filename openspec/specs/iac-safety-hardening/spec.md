## Purpose

Guardrails against destructive, unnoticed, or externally-exposed changes — deletion protection, backups, network baseline, resource labeling, and automated dependency updates.

## Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match, as the provider requires), exposed as a module variable so each environment can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-prod environment from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in an environment-specific file under `environments/prod/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the prod server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future environment consumes `modules/server` and sets its deletion-protection variable to `false`
- **THEN** that environment's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Data Durability for Stateful Resources
The prod server SHALL have `backups = true`.

Deletion protection and destroy gating protect the *resource*; neither protects the *data* on its disk against corruption, accidental deletion inside the guest, or filesystem loss. Restoring from a backup is the only remedy for those, and no Terraform-level guardrail substitutes for it. This is accepted at the cost of Hetzner's 20% backup surcharge on the server price.

#### Scenario: Server is created with backups enabled
- **WHEN** the prod server is created via `environments/prod/`
- **THEN** automatic backups SHALL be enabled on it

### Requirement: Default-Deny Network Baseline
Every server managed by this repository SHALL have an `hcloud_firewall` attached, configured default-deny for inbound traffic, with allowed inbound rules enumerated explicitly including their source CIDRs.

The module SHALL make firewall attachment structural rather than optional, so that a server without a firewall is not expressible through it.

#### Scenario: Prod server is not reachable on unspecified ports
- **WHEN** the prod server is created and a connection is attempted to an inbound port not explicitly allowed by its firewall rules
- **THEN** the connection SHALL be refused by the firewall

#### Scenario: SSH exposure is explicitly scoped
- **WHEN** the firewall permits inbound SSH
- **THEN** it SHALL do so only from explicitly enumerated source CIDRs, and SHALL NOT permit SSH from `0.0.0.0/0`

### Requirement: Key-Only SSH Access
Servers SHALL be provisioned with SSH public key authentication via `hcloud_ssh_key`, and password authentication SHALL be disabled.

#### Scenario: Password login is unavailable
- **WHEN** the prod server has been created
- **THEN** SSH password authentication SHALL be disabled, and access SHALL require a registered key pair

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry an `environment` label matching its environment folder and a `managed_by = "terraform"` label.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

### Requirement: Write Credentials Confined to the Gated Pipeline
The **Read & Write** Hetzner Cloud API token SHALL exist in exactly one location: the `production` GitHub Environment secret. It SHALL NOT be exported into a shell environment, written to a dotfile, `direnv` file, or any `.tfvars` file, or stored in a local credential helper on any workstation.

Local Terraform work SHALL authenticate with the **Read Only** token, which is sufficient for `terraform plan` and refresh and which causes any local `terraform apply` to fail at the Hetzner Cloud API.

Because the workspace's Execution Mode is Local, the destroy-policy gate, the saved-plan approval gate, and branch protection are properties of the GitHub Actions path to production rather than of Terraform itself — a workstation holding a write-capable token bypasses all three in a single command. This requirement extends the split established by the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability from CI jobs to workstations.

The prohibition SHALL be recorded where it is loaded without being sought: the repository README runbook for human operators, and a repository-root `AGENTS.md` for coding agents.

#### Scenario: Local apply is refused by the API
- **WHEN** an operator or coding agent runs `terraform apply` from a workstation against `environments/prod/`
- **THEN** the Hetzner Cloud API SHALL reject the write, because the only token available locally is read-only

#### Scenario: Local plan remains available
- **WHEN** an operator runs `terraform plan` from a workstation against `environments/prod/`
- **THEN** it SHALL succeed using the read-only token, so that local iteration never requires write credentials

#### Scenario: An agent opening the repository is told the boundary
- **WHEN** a coding agent begins work in this repository
- **THEN** a repository-root `AGENTS.md` SHALL state that production changes reach Hetzner only through the gated pipeline and that `terraform apply` is not run locally

### Requirement: Automated Dependency Updates
The repository SHALL configure Dependabot for both the `terraform` and `github-actions` package ecosystems, opening pull requests when newer versions become available.

The `github-actions` ecosystem is required, not optional: a compromised or abandoned third-party action is a more realistic supply-chain risk for this repository than a stale Terraform provider.

Dependabot has **no `pre-commit` ecosystem**, so pinned hook revisions SHALL instead be maintained by a scheduled workflow that runs `pre-commit autoupdate` and opens a pull request with the result.

#### Scenario: Provider version update is proposed automatically
- **WHEN** a newer version of the Hetzner Cloud Terraform provider is released that satisfies or extends the current version constraint
- **THEN** Dependabot SHALL open a pull request updating the `required_providers` constraint and `.terraform.lock.hcl`, subject to the same validation pipeline as any other change

#### Scenario: Action version update is proposed automatically
- **WHEN** a newer version of a GitHub Action referenced by a workflow is released
- **THEN** Dependabot SHALL open a pull request updating that reference

#### Scenario: Pre-commit hook revisions are refreshed on a schedule
- **WHEN** the scheduled hook-update workflow runs and `pre-commit autoupdate` changes any pinned revision
- **THEN** the workflow SHALL open a pull request with the updated `.pre-commit-config.yaml`
