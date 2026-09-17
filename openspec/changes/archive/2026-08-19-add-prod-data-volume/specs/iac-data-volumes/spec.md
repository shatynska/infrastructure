## Purpose

Lets the prod environment provision a persistent Hetzner Cloud volume, attached to the prod server, that can be toggled out of management without losing its declared configuration — mirroring how the prod server itself is toggled.

## ADDED Requirements

### Requirement: Conditional Prod Volume Creation
The prod environment SHALL expose a boolean variable that controls whether the volume module creates any resources, independent of the rest of the volume's configuration (size, name).

The volume SHALL NOT be created without a location of its own (see Requirement: Volume Attached to Prod Server at Creation), and Hetzner requires every volume to have either an explicit location or an attached server. The volume's effective existence therefore SHALL depend on both toggles together — the volume-enabled variable AND the prod server's own toggle — not on the volume-enabled variable alone. This is a deliberate coupling introduced by omitting a location from the volume's own configuration, not an accident of implementation.

Configuration values SHALL remain declared in the environment's variables and non-secret tfvars regardless of either toggle's current value, so re-enabling the volume requires changing only the toggle(s), not restoring deleted configuration.

#### Scenario: Toggle enabled creates the volume
- **WHEN** the prod environment's volume-enabled variable is `true` and the prod server is also enabled
- **THEN** `terraform plan` SHALL show the `main-data` volume and its configuration exactly as declared

#### Scenario: Volume toggle disabled creates nothing
- **WHEN** the prod environment's volume-enabled variable is `false`
- **THEN** `terraform plan` SHALL show no volume resource, and any previously-created volume SHALL be planned for destruction

#### Scenario: Disabling the server also removes the volume
- **WHEN** the prod server's own toggle is `false`, regardless of the volume-enabled variable's value
- **THEN** `terraform plan` SHALL show no volume resource, and any previously-created volume SHALL be planned for destruction, because no location is available for it to exist without an attached server

#### Scenario: Re-enabling requires no lost configuration
- **WHEN** the volume-enabled variable and the server's own toggle are both changed back to `true`
- **THEN** the volume SHALL be planned for creation using the same size and name already present in the environment, with no additional values needing to be reconstructed

### Requirement: Volume Attached to Prod Server at Creation
The prod volume SHALL be attached to the prod server at creation by setting the volume's server reference, rather than created unattached and attached in a separate step.

The volume SHALL take its location from the server it is attached to rather than declaring a redundant, independently-specified location, since Hetzner requires a volume and the server it is attached to share the same location.

#### Scenario: Volume is created already attached
- **WHEN** the `main-data` volume is created with the prod server enabled
- **THEN** the volume SHALL be attached to that server, with no separate attachment step required after creation

#### Scenario: Volume shares the server's location
- **WHEN** the `main-data` volume is created
- **THEN** its location SHALL match the prod server's location, derived from the attachment rather than independently configured
