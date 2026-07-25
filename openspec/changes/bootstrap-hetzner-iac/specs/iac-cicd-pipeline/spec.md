## ADDED Requirements

### Requirement: Pull Request Validation Checks
Every pull request that changes Terraform configuration SHALL trigger a GitHub Actions workflow that runs `terraform fmt -check`, `terraform validate`, `tflint`, Trivy misconfiguration scanning, and `gitleaks` secret scanning.

#### Scenario: PR with a misconfiguration fails validation
- **WHEN** a pull request introduces a Terraform resource with a Trivy-detectable misconfiguration (e.g. an overly permissive firewall rule)
- **THEN** the validation workflow SHALL fail and report the finding on the pull request

#### Scenario: PR with a leaked credential fails validation
- **WHEN** a pull request's diff contains content matching a `gitleaks` secret pattern
- **THEN** the validation workflow SHALL fail before any `terraform plan` is executed

### Requirement: Pull Request Plan Visibility
When validation checks pass, the workflow SHALL run `terraform plan` against the prod environment and post the full plan output as a comment on the pull request.

#### Scenario: Reviewer sees the plan without leaving GitHub
- **WHEN** validation checks pass on a pull request that changes `environments/prod/` or `modules/`
- **THEN** the workflow SHALL post the resulting `terraform plan` output as a PR comment, viewable directly in the GitHub pull request

### Requirement: Gated Production Apply
`terraform apply` against the prod environment SHALL run only after a pull request is merged to `main`, and SHALL require manual approval via a GitHub Environment (`production`) protection rule before executing.

#### Scenario: Merge does not apply immediately
- **WHEN** a pull request changing `environments/prod/` is merged to `main`
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before running `terraform apply`

#### Scenario: Apply credentials are inaccessible before approval
- **WHEN** the apply workflow run is pending approval
- **THEN** the `HCLOUD_TOKEN` and Terraform Cloud credentials scoped to the `production` Environment SHALL NOT be readable by the workflow job until approval is granted

### Requirement: Scheduled Drift Detection
A scheduled GitHub Actions workflow SHALL run `terraform plan` against the prod environment on a recurring nightly schedule, without applying any changes, to surface divergence between the committed configuration and actual infrastructure state.

#### Scenario: Manual out-of-band change is detected
- **WHEN** a resource in the dedicated prod Hetzner Cloud project is modified outside of Terraform (e.g. via the Hetzner console) and the nightly drift-detection workflow next runs
- **THEN** the resulting `terraform plan` SHALL show a non-empty diff, and the workflow SHALL surface this as a failure or notification, without applying any change
