## MODIFIED Requirements

### Requirement: Environment and Module Folder Structure
The repository SHALL organize Terraform configuration as environment folders under `terraform/environments/` that consume shared, reusable code from `terraform/modules/`, rather than using git branches to represent environments.

Environments consume modules by relative path, which means every environment runs the same module code as of the merged commit — there is no per-environment module version pinning. Consequently, when additional environments are added, ordered promotion SHALL be achieved by sequencing apply jobs within a single workflow (lower environment first, then the gated production environment), not by pinning different module versions per environment.

#### Scenario: Prod environment consumes a shared module
- **WHEN** the `terraform/environments/prod/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `terraform/modules/` (e.g. `terraform/modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a future environment does not require restructuring
- **WHEN** a new environment (e.g. staging) is added in the future
- **THEN** it SHALL be added as a new `terraform/environments/<name>/` folder consuming the same shared modules, without moving or renaming existing files
