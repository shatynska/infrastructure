## Purpose

Lets the prod server be decommissioned and later recreated by toggling a single variable, without losing its configuration or destroying infrastructure that predates Terraform's management of it.

## Requirements

### Requirement: Conditional Prod Server Creation
The prod environment SHALL expose a boolean variable that controls whether the server module creates any resources, independent of the rest of that server's configuration (sizing, image, location, network CIDRs).

Configuration values SHALL remain declared in the environment's variables and non-secret tfvars regardless of the toggle's current value, so re-enabling the server requires changing only the toggle, not restoring deleted configuration.

#### Scenario: Toggle enabled creates the server
- **WHEN** the prod environment's server-enabled variable is `true`
- **THEN** `terraform plan` SHALL show the server, its firewall, and their configuration exactly as declared

#### Scenario: Toggle disabled creates nothing
- **WHEN** the prod environment's server-enabled variable is `false`
- **THEN** `terraform plan` SHALL show no server or firewall resources, and any previously-created ones SHALL be planned for destruction

#### Scenario: Re-enabling requires no lost configuration
- **WHEN** the server-enabled variable is changed back from `false` to `true`
- **THEN** the server SHALL be planned for creation using the same sizing, image, location, network configuration, and SSH key already present in the environment, with no additional values needing to be reconstructed and no additional resources needing to be re-imported

### Requirement: Infrastructure Predating Terraform Stays Under Continuous Management, Decoupled From Ephemeral Resources
Infrastructure that was adopted into Terraform management via `import` after already existing outside Terraform, and whose real-world lifecycle is independent of any single conditionally-created resource, SHALL remain under continuous Terraform management at a stable address — not destroyed, and not repeatedly detached and re-imported — regardless of how many times the conditionally-created resource that references it is toggled on or off.

#### Scenario: Disabling the server does not delete or orphan a pre-existing SSH key
- **WHEN** the server-enabled variable is set to `false` and applied
- **THEN** the SSH key that was imported from a pre-existing Hetzner resource SHALL remain under Terraform management at a stable address, SHALL NOT be deleted from Hetzner, and SHALL NOT require a fresh `import` to be managed again on a future re-enable

#### Scenario: Relocation is visible in the plan before it happens
- **WHEN** a plan relocates a resource's Terraform address via a `moved` block
- **THEN** the plan output SHALL distinguish that action from a destroy or a create, so a reviewer does not mistake "address changed" for "recreated"
