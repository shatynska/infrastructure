## MODIFIED Requirements

### Requirement: Environment and Module Folder Structure
The repository SHALL organize Terraform configuration as environment folders under `terraform/environments/` that consume shared, reusable code from `terraform/modules/`, rather than using git branches to represent environments.

Environments consume modules by relative path, which means every environment runs the same module code as of the merged commit — there is no per-environment module version pinning, and none SHALL be introduced to obtain promotion ordering.

**Promotion ordering is not a property of the apply workflow.** A merge affecting several environments SHALL plan and apply each of them independently, each under its own GitHub Environment's protection rules, and an environment's apply SHALL NOT be made to depend on another environment's apply. Such a dependency is the mechanism this requirement previously prescribed, and it contradicts the Gated Production Apply Applies the Reviewed Plan requirement (iac-cicd-pipeline), which obliges that one environment's failure not withhold a correct change from another — an obligation stated there for plans and true here for the same reason.

Where promotion ordering is wanted, it SHALL be obtained from the reviewed environment's own approval gate: a reviewed environment's apply waits for a human, who can withhold approval until a lower environment's apply has been observed to succeed. This is a discipline available to the approver rather than a mechanism the pipeline enforces, and it is stated as what holds rather than as what is guaranteed.

#### Scenario: Prod environment consumes a shared module
- **WHEN** the `terraform/environments/prod/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `terraform/modules/` (e.g. `terraform/modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a future environment does not require restructuring
- **WHEN** a new environment is added
- **THEN** it SHALL be added as a new `terraform/environments/<name>/` folder consuming the same shared modules, without moving or renaming existing files and without pinning a module version of its own

#### Scenario: A shared module change reaches every environment without an imposed order
- **WHEN** a merge changing a file under `terraform/modules/` affects two environments
- **THEN** each environment SHALL be planned and applied under its own GitHub Environment's protection rules, and neither environment's apply SHALL be blocked by the other's outcome

#### Scenario: Promotion ordering is exercised at the approval, not by the workflow
- **WHEN** an operator wants a shared change observed in a lower environment before it reaches a reviewed one
- **THEN** the reviewed environment's approval SHALL be the point at which that is exercised, by withholding it until the lower environment's apply has been observed
