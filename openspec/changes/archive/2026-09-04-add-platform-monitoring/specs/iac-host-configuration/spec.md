## ADDED Requirements

### Requirement: Platform Data Volume Is Mounted at a Fixed Host Path
Ansible SHALL mount the platform's dedicated data volume (the Terraform-provisioned `main-data` Hetzner Volume) at a fixed host path, and that mount SHALL persist across a host reboot without manual intervention. Ansible SHALL also ensure the subdirectories a `platform/` service depends on exist under that mount, with ownership and permissions matching what that service's container requires, before that service can rely on them.

This requirement covers only the mount and its filesystem layout — it does not extend Ansible's scope to templating or starting any `platform/` service, consistent with the existing "Configuration Scope Stops at the Container Runtime" requirement.

#### Scenario: Volume is mounted at a known path
- **WHEN** the host-baseline playbook runs with the data volume attached
- **THEN** that volume SHALL be mounted at a fixed, documented host path

#### Scenario: Mount survives a reboot
- **WHEN** the host reboots
- **THEN** the data volume SHALL be mounted at the same fixed path afterward, without a manual step

#### Scenario: Dependent subdirectories exist before a service needs them
- **WHEN** a `platform/` service is configured to bind-mount a subdirectory of the data volume
- **THEN** that subdirectory SHALL already exist, with the ownership and permissions that service's container requires, before that service is deployed
