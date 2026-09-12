## MODIFIED Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match on resources that support it, as the provider requires), exposed as a module variable so each stack can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `terraform/modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-production stack from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in a stack-specific file under `terraform/stacks/main-production/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the production server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Prod volume is protected against console deletion
- **WHEN** an operator attempts to delete the `main` volume through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future stack consumes `terraform/modules/server` or `terraform/modules/volume` and sets its deletion-protection variable to `false`
- **THEN** that stack's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Data Durability for Stateful Resources
The production server SHALL have `backups = true`.

Deletion protection and destroy gating protect the *resource*; neither protects the *data* on its disk against corruption, accidental deletion inside the guest, or filesystem loss. No Terraform-level guardrail substitutes for a copy of the data. This is accepted at the cost of Hetzner's 20% backup surcharge on the server price.

What the setting buys is bounded, and stating it is what stops it being mistaken for a database backup: a daily, crash-consistent image of the **root disk only** — not of the attached data volume — retained on Hetzner's schedule and restorable only by rolling the whole server back to it. That shortens a rebuild of a host whose disk carries container images and converged configuration. It is not a backup any database is restored from selectively, and the obligation for data that would need one is *No Store on This Host Holds Data Requiring Backup* in this capability.

#### Scenario: Server is created with backups enabled
- **WHEN** the production server is created via `terraform/stacks/main-production/`
- **THEN** automatic backups SHALL be enabled on it

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry a `managed_by = "terraform"` label and one label per axis its stack is identified on: an `environment` label naming the environment its stack belongs to, and a `tenant` label naming the tenant.

**Each axis SHALL be its own label rather than a segment of a name.** A stack's name is one ordering of its axes and a resource can carry only one name, so a consumer that wants to select on an axis the name puts second has to parse the name — which is a rule that holds on the names a repository happens to have. Labels are queryable individually and are what the Ansible inventory's groups are keyed on, so an axis added later adds a group rather than changing how an existing one is derived.

**Environment values SHALL be spelled in full.** `prod` and `preprod` share a prefix, and a label value is read by prefix in more places than it is read whole — inventory group names, secret names derived from it, a person scanning a console list. The four characters saved are not worth a value that is ambiguous under the commonest way of reading it.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `terraform/stacks/main-production/`
- **THEN** it SHALL carry the labels `environment = "production"`, `tenant = "main"` and `managed_by = "terraform"`

#### Scenario: Prod volume is labeled
- **WHEN** the `main` `hcloud_volume` resource is created via `terraform/stacks/main-production/`
- **THEN** it SHALL carry the labels `environment = "production"`, `tenant = "main"` and `managed_by = "terraform"`

#### Scenario: An SSH key a stack owns directly is labeled
- **WHEN** a `hcloud_ssh_key` resource is declared in a stack directory rather than inside a shared module
- **THEN** it SHALL carry the same axis labels every resource that stack's modules create carries, because a resource outside a module is not outside this obligation
