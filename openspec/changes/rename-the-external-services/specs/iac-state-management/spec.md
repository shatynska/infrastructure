## MODIFIED Requirements

### Requirement: Remote State Backend
Terraform state for **every** stack SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

Each stack SHALL have a workspace of its own, and no two stacks SHALL share one. A workspace holds one state, so two stacks sharing one would have each `terraform apply` read the other's resources as its own and plan them for destruction — a failure that appears only once a second stack exists and that no file in this repository can detect, because the workspace name is read from that stack's own `versions.tf` and its uniqueness is a property of the HCP Terraform organization.

**A workspace's name SHALL NOT be computed from its stack's directory name.** The two names MAY agree, and a convention bringing them into agreement is not forbidden — what is forbidden is a rule that derives one from the other, whether stated as a requirement or implemented as an expression. The two are renamed by different mechanisms and in an order that cannot be reversed: a stack directory is renamed by a commit, and a workspace is renamed in the HCP Terraform interface *before* any `versions.tf` naming it is pushed — pushing first points the `cloud` block at a workspace that does not exist, and `terraform init` **creates** one rather than failing. What that costs is not a silent apply: execution mode is a per-workspace setting, as the Workspace Execution Mode Set to Local requirement below states, but a newly created workspace is initialised from the organization's `default-execution-mode` — read as `remote` on 2026-09-12 — so a workspace created this way is misconfigured in exactly the sense that requirement means, and a remote run yields no locally applicable plan file for the saved-plan flow to apply. What it does cost is the name: the empty workspace now holds the name the rename was going to take, and an interface will not rename a workspace onto a name already in use. Any derivation is therefore false for the interval between the two, and that interval is bounded by nothing in the repository. The convention the two are brought into agreement under lives in `docs/naming-conventions.md`; what this requirement obliges is that each stack names one workspace, in its own `versions.tf`, and that no two name the same.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in a stack directory under `terraform/stacks/`
- **THEN** Terraform SHALL configure that stack's own HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Two environments do not share a workspace
- **WHEN** a stack is added under `terraform/stacks/`
- **THEN** its configuration SHALL name a workspace no other stack names, so that its state is separate from every other stack's

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for a stack directory from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock

### Requirement: HCP Terraform Access via a Static Token, Unsplit by Privilege
Authentication to HCP Terraform from GitHub Actions SHALL use a static HCP Terraform API token (`TF_API_TOKEN`), stored as an identical value in both the repository-scoped secret and the `main-production` Environment-scoped secret of the same name — kept as two separate GitHub secrets, not one shared name, so the environment-secret-shadowing mechanism stays wired up for a future privilege split.

GitHub OIDC dynamic credentials were the original design here, on the assumption that it could eliminate a long-lived HCP token the same way it can for a cloud provider. That assumption does not hold: HCP Terraform's dynamic-credentials / workload-identity feature authenticates a *provider* during a run HCP Terraform itself executes remotely — it has no mechanism for authenticating the Terraform CLI's own backend/state access when the CLI runs externally, as it does under this repository's CLI-driven, Local-execution workspace (see the Workspace Execution Mode Set to Local requirement). A follow-up attempt to split this token by privilege using HCP Terraform's per-team Plan/Write permission levels also failed: Teams are a paid-tier HCP Terraform feature, unavailable on this organization's free tier, where every token has full access to every workspace regardless of who it belongs to. Both findings were discovered during implementation (see design.md Decision 9).

This is a deliberately accepted risk, not an oversight. A compromised PR-time or drift-detection job holding `TF_API_TOKEN` can read or corrupt Terraform *state* — it cannot mutate real Hetzner infrastructure, because it still lacks the write-capable `HCLOUD_TOKEN`, which remains genuinely split by privilege (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability) and is the actual load-bearing security boundary in this design.

#### Scenario: HCP token cannot reach real infrastructure on its own
- **WHEN** a job holding only `TF_API_TOKEN` (no write-capable `HCLOUD_TOKEN`) is compromised
- **THEN** it SHALL be able to read or write Terraform state but SHALL NOT be able to create, modify, or destroy any Hetzner Cloud resource

#### Scenario: The split mechanism remains wired for a future upgrade
- **WHEN** this organization is upgraded to a paid HCP Terraform tier and team-scoped Plan/Write tokens become available
- **THEN** only the repository-scoped and environment-scoped `TF_API_TOKEN` secret *values* need to change to achieve a real privilege split — no workflow SHALL require code changes to adopt it
