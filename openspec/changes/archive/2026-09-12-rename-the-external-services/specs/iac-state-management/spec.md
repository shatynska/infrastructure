## MODIFIED Requirements

### Requirement: Remote State Backend
Terraform state for **every** stack SHALL be stored remotely in HCP Terraform (formerly Terraform Cloud), configured for the CLI-driven workflow (no VCS connection, no HCP-triggered runs), rather than as a local state file.

Each stack SHALL have a workspace of its own, and no two stacks SHALL share one. A workspace holds one state, so two stacks sharing one would have each `terraform apply` read the other's resources as its own and plan them for destruction — a failure that appears only once a second stack exists and that no file in this repository can detect, because the workspace name is read from that stack's own `versions.tf` and its uniqueness is a property of the HCP Terraform organization.

**A workspace's name SHALL NOT be computed from its stack's directory name.** The two names MAY agree, and a convention bringing them into agreement is not forbidden — what is forbidden is a rule that derives one from the other, whether stated as a requirement or implemented as an expression. The two are renamed by different mechanisms and in an order that cannot be reversed: a stack directory is renamed by a commit, and a workspace is renamed in the HCP Terraform interface *before* any `versions.tf` naming it is pushed — pushing first points the `cloud` block at a workspace that does not exist, and `terraform init` **creates** one rather than failing. Execution mode is a per-workspace setting, as the Workspace Execution Mode Set to Local requirement below states, and a newly created workspace takes that requirement's remote default — this organization's `default-execution-mode` was read as `remote` on 2026-09-12. A workspace created this way is therefore misconfigured in exactly the sense that requirement means, and a remote run yields no locally applicable plan file, so the saved-plan flow has none to save and the run fails rather than producing something appliable. What it does cost is the name: the empty workspace now holds the name the rename was going to take, and an interface will not rename a workspace onto a name already in use. Any derivation is therefore false for the interval between the two, and that interval is bounded by nothing in the repository. The convention the two are brought into agreement under lives in `docs/naming-conventions.md`; what this requirement obliges is that each stack names one workspace, in its own `versions.tf`, and that no two name the same.

#### Scenario: State is not stored locally
- **WHEN** `terraform init` is run in a stack directory under `terraform/stacks/`
- **THEN** Terraform SHALL configure that stack's own HCP Terraform workspace as the backend, and no persistent `.tfstate` file SHALL be written to the local filesystem or committed to git

#### Scenario: Two environments do not share a workspace
- **WHEN** a stack is added under `terraform/stacks/`
- **THEN** its configuration SHALL name a workspace no other stack names, so that its state is separate from every other stack's

#### Scenario: Plan and apply run outside HCP Terraform's own execution
- **WHEN** `terraform plan` or `terraform apply` is executed for a stack directory from GitHub Actions
- **THEN** the Terraform CLI SHALL perform the run locally within the GitHub Actions runner, using HCP Terraform only to read and write state and to acquire the state lock
