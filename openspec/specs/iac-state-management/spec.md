## Purpose

HCP Terraform backend configuration (CLI-driven, local execution, static tokens split by privilege) and the dedicated Hetzner Cloud project for the prod environment.

## Requirements

### Requirement: Remote State Backend
Terraform state for the prod environment SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in `terraform/environments/prod/`
- **THEN** Terraform SHALL configure the `infrastructure-prod` HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for `terraform/environments/prod/` from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock

### Requirement: Workspace Execution Mode Set to Local
The `infrastructure-prod` workspace SHALL have its Execution Mode explicitly set to **Local**.

A workspace configured with a `cloud` block defaults to **remote** execution, which would dispatch plans and applies to HCP Terraform's own runners instead of the GitHub Actions runner. That default silently contradicts the CLI-driven requirement above and breaks the saved-plan approval flow in the iac-cicd-pipeline capability, since `terraform plan -out=tfplan` does not yield a locally applicable plan file under remote execution. This setting is therefore part of the workspace's definition of done, not an incidental console preference.

#### Scenario: Saved plan files are usable by the pipeline
- **WHEN** the apply workflow's plan job runs `terraform plan -out=tfplan` against `terraform/environments/prod/`
- **THEN** a plan file SHALL be written to the runner's filesystem and SHALL be applicable by a later `terraform apply tfplan` in the same run

#### Scenario: Remote execution mode is treated as misconfiguration
- **WHEN** the `infrastructure-prod` workspace is found to be in remote execution mode
- **THEN** this SHALL be treated as a configuration defect to correct, not an acceptable alternative

### Requirement: HCP Terraform Access via a Static Token, Unsplit by Privilege
Authentication to HCP Terraform from GitHub Actions SHALL use a static HCP Terraform API token (`TF_API_TOKEN`), stored as an identical value in both the repository-scoped secret and the `production` Environment-scoped secret of the same name — kept as two separate GitHub secrets, not one shared name, so the environment-secret-shadowing mechanism stays wired up for a future privilege split.

GitHub OIDC dynamic credentials were the original design here, on the assumption that it could eliminate a long-lived HCP token the same way it can for a cloud provider. That assumption does not hold: HCP Terraform's dynamic-credentials / workload-identity feature authenticates a *provider* during a run HCP Terraform itself executes remotely — it has no mechanism for authenticating the Terraform CLI's own backend/state access when the CLI runs externally, as it does under this repository's CLI-driven, Local-execution workspace (see the Workspace Execution Mode Set to Local requirement). A follow-up attempt to split this token by privilege using HCP Terraform's per-team Plan/Write permission levels also failed: Teams are a paid-tier HCP Terraform feature, unavailable on this organization's free tier, where every token has full access to every workspace regardless of who it belongs to. Both findings were discovered during implementation (see design.md Decision 9).

This is a deliberately accepted risk, not an oversight. A compromised PR-time or drift-detection job holding `TF_API_TOKEN` can read or corrupt Terraform *state* — it cannot mutate real Hetzner infrastructure, because it still lacks the write-capable `HCLOUD_TOKEN`, which remains genuinely split by privilege (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability) and is the actual load-bearing security boundary in this design.

#### Scenario: HCP token cannot reach real infrastructure on its own
- **WHEN** a job holding only `TF_API_TOKEN` (no write-capable `HCLOUD_TOKEN`) is compromised
- **THEN** it SHALL be able to read or write Terraform state but SHALL NOT be able to create, modify, or destroy any Hetzner Cloud resource

#### Scenario: The split mechanism remains wired for a future upgrade
- **WHEN** this organization is upgraded to a paid HCP Terraform tier and team-scoped Plan/Write tokens become available
- **THEN** only the repository-scoped and environment-scoped `TF_API_TOKEN` secret *values* need to change to achieve a real privilege split — no workflow SHALL require code changes to adopt it

### Requirement: State Locking
Concurrent `terraform plan` or `terraform apply` operations against the same environment's state SHALL be prevented via HCP Terraform's state locking.

Read-only, non-mutating plans (specifically the scheduled drift-detection plan) are exempt and run with `-lock=false`, as specified in the iac-cicd-pipeline capability.

#### Scenario: Concurrent apply attempts are serialized
- **WHEN** two `terraform apply` operations against `terraform/environments/prod/` are attempted at overlapping times
- **THEN** the second operation SHALL be blocked from proceeding until the first releases the state lock

### Requirement: Dedicated Hetzner Cloud Project for Prod
The prod environment SHALL operate against a Hetzner Cloud project that is dedicated to prod, authenticated via a `HCLOUD_TOKEN` scoped to that project only.

#### Scenario: Prod credentials are isolated
- **WHEN** the prod Terraform configuration authenticates to the Hetzner Cloud API
- **THEN** it SHALL use a `HCLOUD_TOKEN` that grants access only to the dedicated prod Hetzner Cloud project, not to any other project
