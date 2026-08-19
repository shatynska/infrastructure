## MODIFIED Requirements

### Requirement: Pull Request Validation Checks
Every pull request that changes Terraform configuration SHALL trigger a GitHub Actions workflow that runs `terraform fmt -check`, `terraform validate`, `tflint`, Trivy misconfiguration scanning, and `gitleaks` secret scanning.

`terraform validate` and `tflint` SHALL run against every directory under `modules/` and `environments/` that contains Terraform configuration, discovered rather than enumerated by a fixed list of directory names. A directory added under `modules/` or `environments/` SHALL be covered by these checks without any workflow edit.

Any module directory containing `*.tftest.hcl` test files SHALL also have `terraform test` run against it as part of the same workflow.

`gitleaks` SHALL be invoked as its CLI binary rather than via the `gitleaks/gitleaks-action` marketplace action, because that action requires a paid license key for organization-owned repositories and its v2 runtime is removed from GitHub-hosted runners on 2026-09-16.

#### Scenario: PR with a misconfiguration fails validation
- **WHEN** a pull request introduces a Terraform resource with a Trivy-detectable misconfiguration (e.g. an overly permissive firewall rule)
- **THEN** the validation workflow SHALL fail and report the finding on the pull request

#### Scenario: PR with a leaked credential fails validation
- **WHEN** a pull request's diff contains content matching a `gitleaks` secret pattern
- **THEN** the validation workflow SHALL fail before any `terraform plan` is executed

#### Scenario: Secret scanning requires no third-party license
- **WHEN** the validation workflow runs its secret-scanning step
- **THEN** it SHALL complete without requiring a `GITLEAKS_LICENSE` secret or any other paid license credential

#### Scenario: A newly added module is validated and linted without a workflow change
- **WHEN** a pull request adds a new directory under `modules/` containing Terraform configuration, and no change is made to `pr-validation.yml` to name that directory
- **THEN** the validation workflow SHALL still run `terraform validate` and `tflint` against that directory

#### Scenario: A module's tests run in CI
- **WHEN** a pull request changes a directory under `modules/` that contains `*.tftest.hcl` files
- **THEN** the validation workflow SHALL run `terraform test` against that directory and fail the check if any test fails
