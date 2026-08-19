## MODIFIED Requirements

### Requirement: Conditional Prod Server Creation
The prod environment SHALL expose a boolean variable that controls whether the server module creates any resources, independent of the rest of that server's configuration (sizing, image, location, network CIDRs).

Configuration values SHALL remain declared in the environment's variables and non-secret tfvars regardless of the toggle's current value, so re-enabling the server requires changing only the toggle, not restoring deleted configuration.

Other resources MAY be coupled to this toggle where their own configuration makes them unable to exist without the server — see the `iac-data-volumes` capability's `production_data` volume, which has no location of its own and therefore exists only while the server does.

#### Scenario: Toggle enabled creates the server
- **WHEN** the prod environment's server-enabled variable is `true`
- **THEN** `terraform plan` SHALL show the server, its firewall, and their configuration exactly as declared

#### Scenario: Toggle disabled creates nothing
- **WHEN** the prod environment's server-enabled variable is `false`
- **THEN** `terraform plan` SHALL show no server or firewall resources, and any previously-created ones SHALL be planned for destruction

#### Scenario: Toggle disabled also removes resources coupled to the server
- **WHEN** the prod environment's server-enabled variable is `false`
- **THEN** `terraform plan` SHALL also show any resource that has no independent location or existence apart from the server (such as the `production_data` volume) planned for destruction, not left dangling or erroring for want of the server it depends on

#### Scenario: Re-enabling requires no lost configuration
- **WHEN** the server-enabled variable is changed back from `false` to `true`
- **THEN** the server SHALL be planned for creation using the same sizing, image, location, network configuration, and SSH key already present in the environment, with no additional values needing to be reconstructed and no additional resources needing to be re-imported
