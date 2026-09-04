## ADDED Requirements

### Requirement: Shared-Stack Services Define a Real Healthcheck
Monitoring/alerting services in the shared platform Compose stack (Prometheus, Alertmanager, Grafana, node-exporter, cAdvisor, postgres-exporter) SHALL each define a Docker healthcheck that reflects that service's own process and HTTP layer actually becoming ready (e.g. its HTTP API responding on its documented readiness/health endpoint), not merely that its process is running. A service covered by this requirement SHALL NOT rely on the absence of a healthcheck to be treated as successfully started.

Any service added to the shared platform Compose stack after this requirement's adoption SHALL likewise define a real healthcheck. This requirement does NOT retroactively apply to Traefik or the shared PostgreSQL instance, which predate it and are not covered here — extending healthchecks to those two is separate, unstarted future work, not something this requirement already claims.

This requirement covers a service's own startup readiness. It does NOT require a healthcheck to detect every failure of an external dependency that service talks to once running (for example, a database credential that stops working after startup) where that dependency's own state is not reflected in the service's HTTP-layer readiness — such failures may be covered by a different mechanism (for example, an alert on the affected metric) instead.

#### Scenario: A service that fails to become ready is not reported healthy
- **WHEN** one of the services this requirement covers starts but its own process or HTTP layer cannot reach a ready state (for example, due to a filesystem permission error or a missing dependency that prevents startup)
- **THEN** its healthcheck SHALL fail, and Docker SHALL NOT report that service as healthy while it remains in that state

#### Scenario: A newly added shared-stack service includes a healthcheck
- **WHEN** a new service is added to the shared platform Compose stack
- **THEN** its definition SHALL include a healthcheck reflecting its own readiness, not be left to rely on process liveness alone

#### Scenario: Traefik and Postgres are not yet covered
- **WHEN** this requirement is evaluated against the shared platform Compose stack
- **THEN** the absence of a healthcheck on Traefik or the shared PostgreSQL instance SHALL NOT be treated as a violation of this requirement
