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

### Requirement: Reverse Proxy Is Traefik with ACME-Issued TLS
The shared reverse proxy in the platform stack SHALL be Traefik, configured to obtain and renew TLS certificates automatically via ACME.

#### Scenario: Application gets HTTPS without its own certificate handling
- **WHEN** a new application is routed through the platform's Traefik instance
- **THEN** it SHALL receive a valid TLS certificate without provisioning or renewing one itself

### Requirement: Shared Docker Network for Application Reuse
The platform stack SHALL expose an externally-joinable Docker network that a separate application repository's own Compose file can attach to, so that application containers can be discovered and routed by the platform's Traefik instance without being defined in the platform stack itself.

#### Scenario: An application repository's Compose file joins the platform network
- **WHEN** an application repository's own `docker-compose.yml` declares the platform's network as external and attaches a service to it
- **THEN** Traefik SHALL be able to route to that service using the same mechanism it uses for any other backend

### Requirement: Platform-Level Secrets Are Never Committed
Credentials consumed by the platform stack (for example the shared PostgreSQL superuser password, or Traefik's ACME registration email where it must be kept private) SHALL never be committed to the repository in plaintext, and any rendered on-host file containing them SHALL have restrictive permissions.

#### Scenario: Platform secrets exist only outside the repository
- **WHEN** the platform stack's secrets are needed to run `docker compose up`
- **THEN** they SHALL be sourced from outside the repository (e.g. GitHub Actions secrets rendered at deploy time) rather than from a committed file
