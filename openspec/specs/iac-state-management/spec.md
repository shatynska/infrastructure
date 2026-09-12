## Purpose

HCP Terraform backend configuration (CLI-driven, local execution, static tokens split by privilege) and the dedicated Hetzner Cloud project each stack operates against.

## Requirements

### Requirement: Remote State Backend
Terraform state for **every** stack SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

Each stack SHALL have a workspace of its own, and no two stacks SHALL share one. A workspace holds one state, so two stacks sharing one would have each `terraform apply` read the other's resources as its own and plan them for destruction — a failure that appears only once a second stack exists and that no file in this repository can detect, because the workspace name is read from that stack's own `versions.tf` and its uniqueness is a property of the HCP Terraform organization.

**A workspace's name SHALL NOT be computed from its stack's directory name.** The two names MAY agree, and a convention bringing them into agreement is not forbidden — what is forbidden is a rule that derives one from the other, whether stated as a requirement or implemented as an expression. The two are renamed by different mechanisms and in an order that cannot be reversed: a stack directory is renamed by a commit, and a workspace is renamed in the HCP Terraform interface *before* any `versions.tf` naming it is pushed — pushing first points the `cloud` block at a workspace that does not exist, and the next plan proposes creating every resource from scratch. Any derivation is therefore false for the interval between the two, and that interval is bounded by nothing in the repository. The convention the two are brought into agreement under lives in `docs/naming-conventions.md`; what this requirement obliges is that each stack names one workspace, in its own `versions.tf`, and that no two name the same.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in a stack directory under `terraform/stacks/`
- **THEN** Terraform SHALL configure that stack's own HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Two environments do not share a workspace
- **WHEN** a stack is added under `terraform/stacks/`
- **THEN** its configuration SHALL name a workspace no other stack names, so that its state is separate from every other stack's

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for a stack directory from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock

### Requirement: Workspace Execution Mode Set to Local
**Every** stack's HCP Terraform workspace SHALL have its Execution Mode explicitly set to **Local**.

A workspace configured with a `cloud` block defaults to **remote** execution, which would dispatch plans and applies to HCP Terraform's own runners instead of the GitHub Actions runner. That default silently contradicts the CLI-driven requirement above and breaks the saved-plan approval flow in the iac-cicd-pipeline capability, since `terraform plan -out=tfplan` does not yield a locally applicable plan file under remote execution. This setting is therefore part of every workspace's definition of done, not an incidental console preference.

It is a per-workspace setting rather than an organization one, so a workspace created for a new stack carries the remote default until it is changed, whatever every existing workspace is set to. Adding a stack therefore includes setting it, and the setting lives in the HCP Terraform UI or API rather than in any file this repository commits.

#### Scenario: Saved plan files are usable by the pipeline
- **WHEN** the apply workflow's plan job runs `terraform plan -out=tfplan` against a stack directory
- **THEN** a plan file SHALL be written to the runner's filesystem and SHALL be applicable by a later `terraform apply tfplan` in the same run

#### Scenario: A newly created workspace is set to Local before its environment is used
- **WHEN** a workspace is created for a new stack
- **THEN** its Execution Mode SHALL be set to Local as part of adding that stack, rather than left at the remote default

#### Scenario: Remote execution mode is treated as misconfiguration
- **WHEN** any stack's workspace is found to be in remote execution mode
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
Concurrent `terraform plan` or `terraform apply` operations against the same stack's state SHALL be prevented via HCP Terraform's state locking.

Read-only, non-mutating plans (specifically the scheduled drift-detection plan) are exempt and run with `-lock=false`, as specified in the iac-cicd-pipeline capability.

#### Scenario: Concurrent apply attempts are serialized
- **WHEN** two `terraform apply` operations against `terraform/stacks/main-production/` are attempted at overlapping times
- **THEN** the second operation SHALL be blocked from proceeding until the first releases the state lock

### Requirement: Each Stack Has a Dedicated Hetzner Cloud Project
Every stack SHALL operate against a Hetzner Cloud project dedicated to that stack alone, authenticated via tokens scoped to that project only. No stack's token SHALL grant access to another stack's project.

A Hetzner Cloud API token is scoped to exactly one project, so the project boundary is what makes the per-stack credential split in the iac-cicd-pipeline capability's Credential Scoping by Privilege requirement mean anything: two stacks sharing a project would hold two tokens over one set of resources, and an ungated stack's Read & Write token would be capable of destroying a reviewed stack's server. The gate would remain in place and would no longer be the only path to those resources.

Resource names are unique per project rather than globally, so stacks in separate projects MAY carry identically named resources. This is a consequence worth stating rather than an incidental one: it lets every stack use the same volume name, and therefore the same on-host mount path, so host-side configuration that hardcodes a path stays correct across stacks instead of needing a per-stack value.

#### Scenario: One stack's credentials do not reach another's project
- **WHEN** any job or operator authenticates to the Hetzner Cloud API for one stack
- **THEN** the token used SHALL grant access only to that stack's dedicated project, and SHALL NOT be able to read, modify or destroy any resource belonging to another stack

#### Scenario: An ungated stack cannot reach a reviewed stack's resources
- **WHEN** a stack whose GitHub Environment requires no reviewer runs its apply job with its own Read & Write token
- **THEN** that token SHALL be incapable of affecting any resource in a reviewed stack's project, so that the reviewed stack's approval gate remains the only path to its resources

#### Scenario: Two stacks may name a resource identically
- **WHEN** two stacks each declare a resource of the same name, such as a volume named `main`
- **THEN** both SHALL be creatable, because each exists in its own project, and neither stack's configuration SHALL need a name chosen to avoid the other
