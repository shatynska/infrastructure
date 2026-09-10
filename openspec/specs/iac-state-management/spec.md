## Purpose

HCP Terraform backend configuration (CLI-driven, local execution, static tokens split by privilege) and the dedicated Hetzner Cloud project each environment operates against.

## Requirements

### Requirement: Remote State Backend
Terraform state for **every** environment SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

Each environment SHALL have a workspace of its own, named `infrastructure-<environment>`, and no two environments SHALL share one. A workspace holds one state, so two environments sharing one would have each `terraform apply` read the other's resources as its own and plan them for destruction — a failure that appears only once a second environment exists and that no file in this repository can detect, because the workspace name is read from that environment's own `versions.tf` and its uniqueness is a property of the HCP Terraform organization.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in an environment directory under `terraform/environments/`
- **THEN** Terraform SHALL configure that environment's own HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Two environments do not share a workspace
- **WHEN** an environment is added under `terraform/environments/`
- **THEN** its configuration SHALL name a workspace no other environment names, so that its state is separate from every other environment's

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for an environment directory from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock

### Requirement: Workspace Execution Mode Set to Local
**Every** environment's HCP Terraform workspace SHALL have its Execution Mode explicitly set to **Local**.

A workspace configured with a `cloud` block defaults to **remote** execution, which would dispatch plans and applies to HCP Terraform's own runners instead of the GitHub Actions runner. That default silently contradicts the CLI-driven requirement above and breaks the saved-plan approval flow in the iac-cicd-pipeline capability, since `terraform plan -out=tfplan` does not yield a locally applicable plan file under remote execution. This setting is therefore part of every workspace's definition of done, not an incidental console preference.

It is a per-workspace setting rather than an organization one, so a workspace created for a new environment carries the remote default until it is changed, whatever every existing workspace is set to. Adding an environment therefore includes setting it, and the setting lives in the HCP Terraform UI or API rather than in any file this repository commits.

#### Scenario: Saved plan files are usable by the pipeline
- **WHEN** the apply workflow's plan job runs `terraform plan -out=tfplan` against an environment directory
- **THEN** a plan file SHALL be written to the runner's filesystem and SHALL be applicable by a later `terraform apply tfplan` in the same run

#### Scenario: A newly created workspace is set to Local before its environment is used
- **WHEN** a workspace is created for a new environment
- **THEN** its Execution Mode SHALL be set to Local as part of adding that environment, rather than left at the remote default

#### Scenario: Remote execution mode is treated as misconfiguration
- **WHEN** any environment's workspace is found to be in remote execution mode
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

### Requirement: Each Environment Has a Dedicated Hetzner Cloud Project
Every environment SHALL operate against a Hetzner Cloud project dedicated to that environment alone, authenticated via tokens scoped to that project only. No environment's token SHALL grant access to another environment's project.

A Hetzner Cloud API token is scoped to exactly one project, so the project boundary is what makes the per-environment credential split in the iac-cicd-pipeline capability's Credential Scoping by Privilege requirement mean anything: two environments sharing a project would hold two tokens over one set of resources, and an ungated environment's Read & Write token would be capable of destroying a reviewed environment's server. The gate would remain in place and would no longer be the only path to those resources.

Resource names are unique per project rather than globally, so environments in separate projects MAY carry identically named resources. This is a consequence worth stating rather than an incidental one: it lets every environment use the same volume name, and therefore the same on-host mount path, so host-side configuration that hardcodes a path stays correct across environments instead of needing a per-environment value.

#### Scenario: One environment's credentials do not reach another's project
- **WHEN** any job or operator authenticates to the Hetzner Cloud API for one environment
- **THEN** the token used SHALL grant access only to that environment's dedicated project, and SHALL NOT be able to read, modify or destroy any resource belonging to another environment

#### Scenario: An ungated environment cannot reach a reviewed environment's resources
- **WHEN** an environment whose GitHub Environment requires no reviewer runs its apply job with its own Read & Write token
- **THEN** that token SHALL be incapable of affecting any resource in a reviewed environment's project, so that the reviewed environment's approval gate remains the only path to its resources

#### Scenario: Two environments may name a resource identically
- **WHEN** two environments each declare a resource of the same name, such as a volume named `main-data`
- **THEN** both SHALL be creatable, because each exists in its own project, and neither environment's configuration SHALL need a name chosen to avoid the other
