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

### Requirement: HCP Terraform Access Split by Privilege
Authentication to HCP Terraform from GitHub Actions SHALL use a static HCP Terraform API token, split by privilege exactly as `HCLOUD_TOKEN` is (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability): a token from a team granted only **Plan** permission on the `infrastructure-prod` workspace, stored as the repository-scoped `TF_API_TOKEN` secret, and a token from a team granted **Write** permission, stored as the `production` Environment-scoped `TF_API_TOKEN` secret.

GitHub OIDC dynamic credentials were the original design here, on the assumption that it could eliminate a long-lived HCP token the same way it can for a cloud provider. That assumption does not hold: HCP Terraform's dynamic-credentials / workload-identity feature authenticates a *provider* during a run HCP Terraform itself executes remotely — it has no mechanism for authenticating the Terraform CLI's own backend/state access when the CLI runs externally, as it does under this repository's CLI-driven, Local-execution workspace (see the Workspace Execution Mode Set to Local requirement). This was discovered during implementation; a static, narrowly-scoped token is the actual supported mechanism.

Neither token SHALL be an organization-level or admin-level credential; each SHALL be scoped to a team with access to only the `infrastructure-prod` workspace, at the minimum permission level that job needs.

#### Scenario: No overprivileged HCP token exists in repository secrets
- **WHEN** the repository's Actions secrets are inspected
- **THEN** every stored HCP Terraform token SHALL be scoped to a team with access to only the `infrastructure-prod` workspace, and none SHALL carry organization-wide or admin permissions

#### Scenario: Plan jobs cannot write state
- **WHEN** a PR-time or scheduled `terraform plan` job runs without declaring `environment: production`
- **THEN** its `TF_API_TOKEN` SHALL resolve to the repository-scoped Plan-level token, which can read state and acquire a read lock but cannot write state

#### Scenario: Apply job receives write access only after approval
- **WHEN** the apply job runs after the `production` Environment approval is granted
- **THEN** its `TF_API_TOKEN` SHALL resolve to the environment-scoped Write-level token, and that token SHALL NOT be readable by any job that has not passed the approval gate

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
