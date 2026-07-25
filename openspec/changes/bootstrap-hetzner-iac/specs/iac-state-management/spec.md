## ADDED Requirements

### Requirement: Remote State Backend
Terraform state for the prod environment SHALL be stored remotely in Terraform Cloud, configured for the CLI-driven workflow (no VCS connection, no TFC-triggered runs), rather than as a local state file.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in `environments/prod/`
- **THEN** Terraform SHALL configure the `infrastructure-prod` Terraform Cloud workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Plan and apply run outside Terraform Cloud's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for `environments/prod/` from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using Terraform Cloud only to read and write state and to acquire the state lock

### Requirement: State Locking
Concurrent `terraform plan` or `terraform apply` operations against the same environment's state SHALL be prevented via Terraform Cloud's state locking.

#### Scenario: Concurrent apply attempts are serialized
- **WHEN** two `terraform apply` operations against `environments/prod/` are attempted at overlapping times
- **THEN** the second operation SHALL be blocked from proceeding until the first releases the state lock

### Requirement: Dedicated Hetzner Cloud Project for Prod
The prod environment SHALL operate against a Hetzner Cloud project that is dedicated to prod, authenticated via a `HCLOUD_TOKEN` scoped to that project only.

#### Scenario: Prod credentials are isolated
- **WHEN** the prod Terraform configuration authenticates to the Hetzner Cloud API
- **THEN** it SHALL use a `HCLOUD_TOKEN` that grants access only to the dedicated prod Hetzner Cloud project, not to any other project
