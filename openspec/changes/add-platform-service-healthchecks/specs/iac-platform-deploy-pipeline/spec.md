## ADDED Requirements

### Requirement: Deploy Fails When Any Healthchecked Service Does Not Become Healthy
The deploy job SHALL fail, rather than report success, when any service that defines a Docker healthcheck does not reach a healthy state within the deploy's wait for service startup. This SHALL hold regardless of which such service fails to become healthy or why.

A service with no Docker healthcheck defined (for example, the pre-existing Traefik and shared PostgreSQL services, which `iac-platform-services`'s healthcheck requirement does not retroactively cover) SHALL still be required to reach a running state within that same wait; the deploy job SHALL fail if it does not. This requirement does not claim that a healthcheck-less service's readiness — beyond having started running — is verified by the deploy job.

#### Scenario: A crash-looping healthchecked service fails the deploy
- **WHEN** a service with a defined healthcheck is deployed but repeatedly fails that healthcheck (for example, crash-looping on startup)
- **THEN** the deploy job SHALL fail and report a non-zero result, rather than completing successfully with that service left unhealthy

#### Scenario: A service with no healthcheck that never starts running still fails the deploy
- **WHEN** a service with no defined healthcheck (for example, Traefik or Postgres) fails to reach a running state at all
- **THEN** the deploy job SHALL fail and report a non-zero result

#### Scenario: A fully healthy deploy succeeds
- **WHEN** every service that defines a healthcheck reaches a healthy state, and every service that does not reaches a running state, within the deploy's wait
- **THEN** the deploy job SHALL report success
