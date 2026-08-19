## ADDED Requirements

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
