## REMOVED Requirements

### Requirement: Each Environment Has a Dedicated Hetzner Cloud Project

**Reason**: Renamed. Entry 61 rewrote this requirement's body in terms of stacks and deferred the title; its three scenario titles name the same unit by the old word, and a scenario cannot be renamed inside a `MODIFIED` block — see design.md decision 3.

**Migration**: Replaced in full by *Each Stack Has a Dedicated Hetzner Cloud Project* below. No obligation is dropped; the volume name in the last scenario follows this change's rename.

## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: State Locking
Concurrent `terraform plan` or `terraform apply` operations against the same stack's state SHALL be prevented via HCP Terraform's state locking.

Read-only, non-mutating plans (specifically the scheduled drift-detection plan) are exempt and run with `-lock=false`, as specified in the iac-cicd-pipeline capability.

#### Scenario: Concurrent apply attempts are serialized
- **WHEN** two `terraform apply` operations against `terraform/stacks/main-production/` are attempted at overlapping times
- **THEN** the second operation SHALL be blocked from proceeding until the first releases the state lock
