## Purpose

Repo scaffolding and local developer quality gates — stack/module folder structure, formatting, linting, pre-commit hooks, commit message linting, gitignore/tfvars sensitivity split, lockfile conventions, and locally-encoded Hetzner guardrails.

## MODIFIED Requirements

### Requirement: Environment and Module Folder Structure
The repository SHALL organize Terraform configuration as stack directories under `terraform/stacks/` that consume shared, reusable code from `terraform/modules/`, rather than using git branches to represent stacks. A **stack** is one Terraform root module: one state, one Hetzner project, one blast radius. It is the unit this repository's pipeline discovers, plans, applies, drift-checks and converges, and the directory is divided by it rather than by the environment a stack belongs to. It is distinct from the shared platform Compose stack the `iac-platform-services` capability governs, which is a set of services on a host rather than a Terraform root module; where both senses could be read, this one is written as a **stack directory**.

Stacks consume modules by relative path, which means every stack runs the same module code as of the merged commit — there is no per-stack module version pinning, and none SHALL be introduced to obtain promotion ordering.

**Promotion ordering is not a property of the apply workflow.** A merge affecting several stacks SHALL plan and apply each of them independently, each under its own GitHub Environment's protection rules, and a stack's apply SHALL NOT be made to depend on another stack's apply. Such a dependency is the mechanism this requirement previously prescribed, and it contradicts the Gated Production Apply Applies the Reviewed Plan requirement (iac-cicd-pipeline), which obliges that one stack's failure not withhold a correct change from another — an obligation stated there for plans and true here for the same reason.

Where promotion ordering is wanted, it SHALL be obtained from the reviewed stack's own approval gate: a reviewed stack's apply waits for a human, who can withhold approval until a lower-environment stack's apply has been observed to succeed. This is a discipline available to the approver rather than a mechanism the pipeline enforces, and it is stated as what holds rather than as what is guaranteed.

#### Scenario: Prod environment consumes a shared module
- **WHEN** the `terraform/stacks/prod/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `terraform/modules/` (e.g. `terraform/modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a future environment does not require restructuring
- **WHEN** a new stack is added
- **THEN** it SHALL be added as a new `terraform/stacks/<name>/` directory consuming the same shared modules, without moving or renaming existing files and without pinning a module version of its own

#### Scenario: A shared module change reaches every environment without an imposed order
- **WHEN** a merge changing a file under `terraform/modules/` affects two stacks
- **THEN** each stack SHALL be planned and applied under its own GitHub Environment's protection rules, and neither stack's apply SHALL be blocked by the other's outcome

#### Scenario: Promotion ordering is exercised at the approval, not by the workflow
- **WHEN** an operator wants a shared change observed in a lower-environment stack before it reaches a reviewed one
- **THEN** the reviewed stack's approval SHALL be the point at which that is exercised, by withholding it until the lower-environment stack's apply has been observed

### Requirement: Version Control Excludes State and Secrets
The repository's `.gitignore` SHALL exclude Terraform local state files and the `.terraform/` working directory.

Variable files SHALL be split by sensitivity rather than excluded wholesale:

| File | Tracked | Contents |
|---|---|---|
| `terraform/stacks/<name>/terraform.tfvars` | Committed | Non-secret stack configuration (server type, region, image, labels, allowed CIDRs) |
| `*.secret.tfvars`, `secrets.auto.tfvars` | Ignored | Any values that must not enter version control |

A blanket `*.tfvars` ignore rule SHALL NOT be used: CI runs `terraform plan` and `apply` from a clean checkout and requires the non-secret stack configuration to be present in the repository.

#### Scenario: Local state is never staged
- **WHEN** `terraform init` or `terraform plan` produces local artifacts such as `.terraform/` or a local `.tfstate` file
- **THEN** `git status` SHALL NOT show these files as trackable/stageable

#### Scenario: CI has the environment configuration it needs
- **WHEN** a CI job checks out the repository and runs `terraform plan` against `terraform/stacks/prod/`
- **THEN** the non-secret `terraform.tfvars` values SHALL be present in the checkout, requiring no out-of-band file injection

#### Scenario: Secret-bearing variable file is not committable
- **WHEN** a developer creates a file matching `*.secret.tfvars` and attempts to stage it
- **THEN** `git status` SHALL NOT show it as trackable
