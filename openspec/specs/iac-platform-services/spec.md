## Purpose

Defines the shared platform Compose stack — services common to the whole server such as the reverse proxy, shared database, and eventual monitoring — as distinct from per-application stacks, including its deployment boundary relative to Ansible and its single-host placement.

## Requirements

### Requirement: Shared Services Live in a Dedicated Platform Stack
Services common to the whole server (reverse proxy, shared database, and — when added — monitoring) SHALL be defined in a single Compose stack under `platform/`, separate from any per-application Compose file.

#### Scenario: A new application reuses the platform stack
- **WHEN** a new application is deployed to the server
- **THEN** it SHALL reuse the existing platform-managed reverse proxy and database rather than defining its own instance of either

### Requirement: Single Shared PostgreSQL Instance, Per-Application Databases
The platform stack SHALL run one shared PostgreSQL instance. Each application SHALL be given its own database within that shared instance rather than its own PostgreSQL container.

#### Scenario: A new application requests a database
- **WHEN** a new application needs a database
- **THEN** a new database SHALL be provisioned within the shared PostgreSQL instance, not a new PostgreSQL container

### Requirement: Platform Stack Deployment Is Not Ansible's Responsibility
The mechanism that starts, stops, or updates the `platform/` Compose stack SHALL be something other than Ansible content, consistent with the configuration-scope boundary stated in `iac-host-configuration`.

#### Scenario: Platform stack changes bypass Ansible
- **WHEN** the platform stack is deployed or updated
- **THEN** the action SHALL be performed by a mechanism outside the `ansible/` directory's content

### Requirement: No Dedicated Monitoring Server
Monitoring services (for example Prometheus or Grafana), when introduced, SHALL run on the same host as the rest of the platform stack rather than on a separate server dedicated to observability.

#### Scenario: Monitoring is added to the existing host
- **WHEN** monitoring services are added to the platform stack
- **THEN** they SHALL be scheduled on the existing single Hetzner server, not on a newly provisioned host
