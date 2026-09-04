## ADDED Requirements

### Requirement: Shared-Stack Services Define a Real Healthcheck
Every service in the shared platform Compose stack SHALL define a Docker healthcheck that reflects that service's own process and readiness layer actually becoming ready (e.g. its HTTP API responding on its documented readiness/health endpoint, or an equivalent readiness probe such as `pg_isready` for PostgreSQL), not merely that its process is running. A service covered by this requirement SHALL NOT rely on the absence of a healthcheck to be treated as successfully started.

Any service added to the shared platform Compose stack after this requirement's adoption SHALL likewise define a real healthcheck.

This requirement covers a service's own startup readiness. It does NOT require a healthcheck to detect every failure of an external dependency that service talks to once running (for example, a database credential that stops working after startup) where that dependency's own state is not reflected in the service's readiness layer — such failures may be covered by a different mechanism (for example, an alert on the affected metric) instead.

#### Scenario: A service that fails to become ready is not reported healthy
- **WHEN** a service starts but its own process or readiness layer cannot reach a ready state (for example, due to a filesystem permission error or a missing dependency that prevents startup)
- **THEN** its healthcheck SHALL fail, and Docker SHALL NOT report that service as healthy while it remains in that state

#### Scenario: A newly added shared-stack service includes a healthcheck
- **WHEN** a new service is added to the shared platform Compose stack
- **THEN** its definition SHALL include a healthcheck reflecting its own readiness, not be left to rely on process liveness alone
