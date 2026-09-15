## MODIFIED Requirements

### Requirement: Version Control Excludes State and Secrets
The repository's `.gitignore` SHALL exclude Terraform local state files and the `.terraform/` working directory.

Variable files SHALL be split by sensitivity rather than excluded wholesale:

| File | Tracked | Contents |
|---|---|---|
| `terraform/stacks/<name>/terraform.tfvars` | Committed | Non-secret stack configuration (server type, region, image, allowed CIDRs) |
| `*.secret.tfvars`, `secrets.auto.tfvars` | Ignored | Any values that must not enter version control |

A blanket `*.tfvars` ignore rule SHALL NOT be used: CI runs `terraform plan` and `apply` from a clean checkout and requires the non-secret stack configuration to be present in the repository.

#### Scenario: Local state is never staged
- **WHEN** `terraform init` or `terraform plan` produces local artifacts such as `.terraform/` or a local `.tfstate` file
- **THEN** `git status` SHALL NOT show these files as trackable/stageable

#### Scenario: CI has the environment configuration it needs
- **WHEN** a CI job checks out the repository and runs `terraform plan` against `terraform/stacks/main-production/`
- **THEN** the non-secret `terraform.tfvars` values SHALL be present in the checkout, requiring no out-of-band file injection

#### Scenario: Secret-bearing variable file is not committable
- **WHEN** a developer creates a file matching `*.secret.tfvars` and attempts to stage it
- **THEN** `git status` SHALL NOT show it as trackable
