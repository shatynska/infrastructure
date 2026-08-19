## Purpose

Repo scaffolding and local developer quality gates — environment/module folder structure, formatting, linting, pre-commit hooks, commit message linting, gitignore/tfvars sensitivity split, lockfile conventions, and locally-encoded Hetzner guardrails.

## Requirements

### Requirement: Environment and Module Folder Structure
The repository SHALL organize Terraform configuration as environment folders under `terraform/environments/` that consume shared, reusable code from `terraform/modules/`, rather than using git branches to represent environments.

Environments consume modules by relative path, which means every environment runs the same module code as of the merged commit — there is no per-environment module version pinning. Consequently, when additional environments are added, ordered promotion SHALL be achieved by sequencing apply jobs within a single workflow (lower environment first, then the gated production environment), not by pinning different module versions per environment.

#### Scenario: Prod environment consumes a shared module
- **WHEN** the `terraform/environments/prod/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `terraform/modules/` (e.g. `terraform/modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a future environment does not require restructuring
- **WHEN** a new environment (e.g. staging) is added in the future
- **THEN** it SHALL be added as a new `terraform/environments/<name>/` folder consuming the same shared modules, without moving or renaming existing files

### Requirement: Terraform Formatting Enforced
All committed Terraform code SHALL be formatted according to `terraform fmt` canonical style.

#### Scenario: Unformatted code is rejected locally
- **WHEN** a developer attempts to commit a `.tf` file that does not match `terraform fmt` canonical style
- **THEN** the pre-commit hook SHALL block the commit until the file is reformatted

### Requirement: Terraform Linting Enforced
All committed Terraform code SHALL pass `tflint` checks.

`tflint` SHALL be configured with its bundled `terraform` ruleset. No Hetzner/`hcloud` `tflint` ruleset exists, so no provider-specific ruleset SHALL be declared; `tflint`'s role here is Terraform-language correctness and style, not Hetzner resource validation.

#### Scenario: Lint violation is caught before commit
- **WHEN** a developer attempts to commit a `.tf` file containing a `tflint`-detectable issue (e.g. an unused declared variable)
- **THEN** the pre-commit hook SHALL block the commit and report the violation

### Requirement: Hetzner Guardrails Are Encoded Locally, Not Assumed From Scanners
Because off-the-shelf misconfiguration scanners provide essentially no Hetzner Cloud rule coverage — Trivy's and tfsec's built-in policy packs target AWS, Azure, GCP, Kubernetes, and Docker — the repository SHALL NOT rely on scanner defaults as its Hetzner security control.

Hetzner-specific rules that matter SHALL be encoded by, in order of preference: module structure that makes the unsafe configuration unrepresentable, `variable validation` blocks that reject bad inputs at plan time, and a small set of custom Trivy or Conftest policies committed to the repository for rules the first two cannot express.

#### Scenario: Invalid module input is rejected at plan time
- **WHEN** a caller passes a value that violates a module's declared input constraints (e.g. an SSH source CIDR of `0.0.0.0/0`, or a malformed server type)
- **THEN** `terraform plan` SHALL fail with the validation block's error message, before any API call is made

#### Scenario: Custom policies are versioned with the code
- **WHEN** a custom misconfiguration policy is written for a Hetzner-specific rule
- **THEN** it SHALL be committed to the repository and evaluated by the pull request validation workflow

### Requirement: Pre-commit Hooks Run Local Quality Checks
The repository SHALL provide a `pre-commit` configuration using `antonbabenko/pre-commit-terraform` hooks that runs formatting, linting, validation, and secret scanning on staged changes before a commit is created.

#### Scenario: Developer installs hooks and commits a change
- **WHEN** a developer runs `pre-commit install` after cloning the repo and then commits a Terraform change
- **THEN** `terraform fmt`, `tflint`, `terraform validate`, and a secret scan SHALL run automatically against the staged files before the commit completes

### Requirement: Commit Message Linting
Commit messages SHALL be validated against the Conventional Commits format before a commit is finalized.

#### Scenario: Non-conventional commit message is rejected
- **WHEN** a developer attempts to commit with a message that does not follow the Conventional Commits format
- **THEN** the commit SHALL be rejected by the commit-msg hook with an explanation of the expected format

### Requirement: Version Control Excludes State and Secrets
The repository's `.gitignore` SHALL exclude Terraform local state files and the `.terraform/` working directory.

Variable files SHALL be split by sensitivity rather than excluded wholesale:

| File | Tracked | Contents |
|---|---|---|
| `terraform/environments/<env>/terraform.tfvars` | Committed | Non-secret environment configuration (server type, region, image, labels, allowed CIDRs) |
| `*.secret.tfvars`, `secrets.auto.tfvars` | Ignored | Any values that must not enter version control |

A blanket `*.tfvars` ignore rule SHALL NOT be used: CI runs `terraform plan` and `apply` from a clean checkout and requires the non-secret environment configuration to be present in the repository.

#### Scenario: Local state is never staged
- **WHEN** `terraform init` or `terraform plan` produces local artifacts such as `.terraform/` or a local `.tfstate` file
- **THEN** `git status` SHALL NOT show these files as trackable/stageable

#### Scenario: CI has the environment configuration it needs
- **WHEN** a CI job checks out the repository and runs `terraform plan` against `terraform/environments/prod/`
- **THEN** the non-secret `terraform.tfvars` values SHALL be present in the checkout, requiring no out-of-band file injection

#### Scenario: Secret-bearing variable file is not committable
- **WHEN** a developer creates a file matching `*.secret.tfvars` and attempts to stage it
- **THEN** `git status` SHALL NOT show it as trackable

### Requirement: Provider Lockfile Committed
The `.terraform.lock.hcl` provider dependency lockfile SHALL be committed to version control to ensure reproducible provider versions across machines and CI runs.

#### Scenario: CI uses the same provider version as local development
- **WHEN** a CI run executes `terraform init` against a commit that includes `.terraform.lock.hcl`
- **THEN** the provider versions installed SHALL match those recorded in the committed lockfile
