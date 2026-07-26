## ADDED Requirements

### Requirement: Remote State Backend
Terraform state for the prod environment SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in `environments/prod/`
- **THEN** Terraform SHALL configure the `infrastructure-prod` HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for `environments/prod/` from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock

### Requirement: Workspace Execution Mode Set to Local
The `infrastructure-prod` workspace SHALL have its Execution Mode explicitly set to **Local**.

A workspace configured with a `cloud` block defaults to **remote** execution, which would dispatch plans and applies to HCP Terraform's own runners instead of the GitHub Actions runner. That default silently contradicts the CLI-driven requirement above and breaks the saved-plan approval flow in the iac-cicd-pipeline capability, since `terraform plan -out=tfplan` does not yield a locally applicable plan file under remote execution. This setting is therefore part of the workspace's definition of done, not an incidental console preference.

#### Scenario: Saved plan files are usable by the pipeline
- **WHEN** the apply workflow's plan job runs `terraform plan -out=tfplan` against `environments/prod/`
- **THEN** a plan file SHALL be written to the runner's filesystem and SHALL be applicable by a later `terraform apply tfplan` in the same run

#### Scenario: Remote execution mode is treated as misconfiguration
- **WHEN** the `infrastructure-prod` workspace is found to be in remote execution mode
- **THEN** this SHALL be treated as a configuration defect to correct, not an acceptable alternative

### Requirement: Dynamic Credentials for State Access
Authentication to HCP Terraform from GitHub Actions SHALL use GitHub OIDC dynamic credentials, exchanging a short-lived per-run token, rather than storing a long-lived HCP Terraform API token as a repository secret.

Hetzner Cloud does not support OIDC, so `HCLOUD_TOKEN` remains a static secret split by privilege (see the Credential Scoping requirement in the iac-cicd-pipeline capability). Eliminating the static state-access token removes the one long-lived secret that could be replaced with a short-lived one.

#### Scenario: No static HCP token exists in repository secrets
- **WHEN** the repository's Actions secrets are inspected
- **THEN** there SHALL be no long-lived HCP Terraform API token stored as a repository or environment secret

#### Scenario: Workflow authenticates per run
- **WHEN** a workflow job needs to read or write Terraform state
- **THEN** it SHALL obtain credentials by presenting its GitHub OIDC token to HCP Terraform, receiving credentials valid only for that run

### Requirement: State Locking
Concurrent `terraform plan` or `terraform apply` operations against the same environment's state SHALL be prevented via HCP Terraform's state locking.

Read-only, non-mutating plans (specifically the scheduled drift-detection plan) are exempt and run with `-lock=false`, as specified in the iac-cicd-pipeline capability.

#### Scenario: Concurrent apply attempts are serialized
- **WHEN** two `terraform apply` operations against `environments/prod/` are attempted at overlapping times
- **THEN** the second operation SHALL be blocked from proceeding until the first releases the state lock

### Requirement: Dedicated Hetzner Cloud Project for Prod
The prod environment SHALL operate against a Hetzner Cloud project that is dedicated to prod, authenticated via a `HCLOUD_TOKEN` scoped to that project only.

#### Scenario: Prod credentials are isolated
- **WHEN** the prod Terraform configuration authenticates to the Hetzner Cloud API
- **THEN** it SHALL use a `HCLOUD_TOKEN` that grants access only to the dedicated prod Hetzner Cloud project, not to any other project
