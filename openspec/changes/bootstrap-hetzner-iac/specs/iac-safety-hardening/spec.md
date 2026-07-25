## ADDED Requirements

### Requirement: Destroy Protection on Critical Resources
Stateful or critical resources (the prod server and any future attached volumes) SHALL declare `lifecycle { prevent_destroy = true }`, so that a plan implying their destruction fails instead of executing.

#### Scenario: Accidental destructive plan is blocked
- **WHEN** a `terraform plan` or `terraform apply` against `environments/prod/` would destroy a resource that has `prevent_destroy = true`
- **THEN** Terraform SHALL error out and refuse to proceed, rather than destroying the resource

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry an `environment` label matching its environment folder and a `managed_by = "terraform"` label.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

### Requirement: Automated Dependency Updates
The repository SHALL configure Dependabot for the `terraform` package ecosystem to open pull requests when newer versions of declared providers or pinned pre-commit hook revisions become available.

#### Scenario: Provider version update is proposed automatically
- **WHEN** a newer version of the Hetzner Cloud Terraform provider is released that satisfies or extends the current version constraint
- **THEN** Dependabot SHALL open a pull request updating the `required_providers` constraint, subject to the same validation pipeline as any other change
