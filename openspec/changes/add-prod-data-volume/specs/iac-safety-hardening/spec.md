## MODIFIED Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match on resources that support it, as the provider requires), exposed as a module variable so each environment can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-prod environment from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in an environment-specific file under `environments/prod/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the prod server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Prod volume is protected against console deletion
- **WHEN** an operator attempts to delete the `production_data` volume through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future environment consumes `modules/server` or `modules/volume` and sets its deletion-protection variable to `false`
- **THEN** that environment's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry an `environment` label matching its environment folder and a `managed_by = "terraform"` label.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

#### Scenario: Prod volume is labeled
- **WHEN** the `production_data` `hcloud_volume` resource is created via `environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`
