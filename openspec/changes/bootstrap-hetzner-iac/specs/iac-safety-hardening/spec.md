## ADDED Requirements

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
