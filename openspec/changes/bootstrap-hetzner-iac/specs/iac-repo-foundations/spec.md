## ADDED Requirements

### Requirement: Environment and Module Folder Structure
The repository SHALL organize Terraform configuration as environment folders under `environments/` that consume shared, reusable code from `modules/`, rather than using git branches to represent environments.

#### Scenario: Prod environment consumes a shared module
- **WHEN** the `environments/prod/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `modules/` (e.g. `modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a future environment does not require restructuring
- **WHEN** a new environment (e.g. staging) is added in the future
- **THEN** it SHALL be added as a new `environments/<name>/` folder consuming the same shared modules, without moving or renaming existing files

### Requirement: Terraform Formatting Enforced
All committed Terraform code SHALL be formatted according to `terraform fmt` canonical style.

#### Scenario: Unformatted code is rejected locally
- **WHEN** a developer attempts to commit a `.tf` file that does not match `terraform fmt` canonical style
- **THEN** the pre-commit hook SHALL block the commit until the file is reformatted

### Requirement: Terraform Linting Enforced
All committed Terraform code SHALL pass `tflint` checks.

#### Scenario: Lint violation is caught before commit
- **WHEN** a developer attempts to commit a `.tf` file containing a `tflint`-detectable issue (e.g. an unused declared variable)
- **THEN** the pre-commit hook SHALL block the commit and report the violation

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
The repository's `.gitignore` SHALL exclude Terraform local state files, the `.terraform/` working directory, and any `.tfvars` files that may contain secret values.

#### Scenario: Local state is never staged
- **WHEN** `terraform init` or `terraform plan` produces local artifacts such as `.terraform/` or a local `.tfstate` file
- **THEN** `git status` SHALL NOT show these files as trackable/stageable

### Requirement: Provider Lockfile Committed
The `.terraform.lock.hcl` provider dependency lockfile SHALL be committed to version control to ensure reproducible provider versions across machines and CI runs.

#### Scenario: CI uses the same provider version as local development
- **WHEN** a CI run executes `terraform init` against a commit that includes `.terraform.lock.hcl`
- **THEN** the provider versions installed SHALL match those recorded in the committed lockfile
