## ADDED Requirements

### Requirement: Deploy Fails When Any Healthchecked Service Does Not Become Healthy
The deploy job SHALL fail, rather than report success, when any service that defines a Docker healthcheck does not reach a healthy state within the deploy's wait for service startup. This SHALL hold regardless of which such service fails to become healthy or why.

A service with no Docker healthcheck defined is only guaranteed to be waited on until it reaches a `running` state at least transiently — this does NOT reliably detect a service that starts, crashes, and is automatically restarted (for example, under a `restart: unless-stopped` policy), since such a service can satisfy a "reached running" check during the brief window between restarts while genuinely crash-looping. This requirement does not claim otherwise. As of this requirement's adoption, every service in the shared platform stack defines a real healthcheck (`iac-platform-services`'s corresponding requirement), so this limitation is not currently exercised by any service in the stack — it is stated here so a future service added without a healthcheck is not mistakenly assumed to be safely covered by the deploy job's wait.

#### Scenario: A crash-looping healthchecked service fails the deploy
- **WHEN** a service with a defined healthcheck is deployed but repeatedly fails that healthcheck (for example, crash-looping on startup)
- **THEN** the deploy job SHALL fail and report a non-zero result, rather than completing successfully with that service left unhealthy

#### Scenario: A service with no healthcheck that never starts running still fails the deploy
- **WHEN** a service with no defined healthcheck fails to reach a running state at all (not even transiently)
- **THEN** the deploy job SHALL fail and report a non-zero result

#### Scenario: A service with no healthcheck that crash-loops is not guaranteed to fail the deploy
- **WHEN** a service with no defined healthcheck starts, crashes, and is automatically restarted, reaching a `running` state at least transiently on each cycle
- **THEN** the deploy job is NOT guaranteed to fail on account of that service, even though it is not genuinely healthy

#### Scenario: A fully healthy deploy succeeds
- **WHEN** every service that defines a healthcheck reaches a healthy state, and every service that does not reaches a running state, within the deploy's wait
- **THEN** the deploy job SHALL report success
