## Purpose

Defines the shared platform Compose stack — services common to the whole server such as the reverse proxy, shared database, and metrics/alerting/dashboards — as distinct from per-application stacks, including its deployment boundary relative to Ansible and its single-host placement.

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

### Requirement: Host and Container Metrics Are Collected
The platform stack SHALL collect host-level resource metrics (CPU, memory, disk) and per-container metrics (including restart count, exit code, and out-of-memory kills) for every container running on the host, not only the platform stack's own services.

#### Scenario: Host resource metrics are available
- **WHEN** the monitoring stack is running
- **THEN** current host CPU, memory, and disk usage SHALL be queryable as metrics

#### Scenario: Any container's health is observable
- **WHEN** a container is added to the host — whether one of the platform stack's own services or a separate application repository's container joining `platform_edge` — and that container restarts, exits non-zero, or is OOM-killed
- **THEN** that event SHALL be visible as a metric without any change to the container's own image or configuration

### Requirement: Per-Application HTTP Error Visibility Without Per-App Instrumentation
The platform stack SHALL expose per-application HTTP request and error-rate metrics, derived from the shared Traefik reverse proxy's own metrics, so that an application routed through Traefik has observable error rates without adding any metrics instrumentation of its own.

#### Scenario: An application's error rate is observable
- **WHEN** an application routed through the platform's Traefik instance returns HTTP 5xx responses
- **THEN** the rate of those responses SHALL be queryable as a metric attributed to that specific application, without that application exposing its own metrics endpoint

### Requirement: Shared PostgreSQL Instance Metrics Are Collected
The platform stack SHALL collect metrics from the shared PostgreSQL instance defined in the "Single Shared PostgreSQL Instance, Per-Application Databases" requirement.

#### Scenario: Postgres metrics are available
- **WHEN** the monitoring stack is running
- **THEN** metrics for the shared PostgreSQL instance SHALL be queryable

### Requirement: Metrics-Based Alerting Covers Host and Service Health
The platform stack SHALL evaluate alert rules covering, at minimum: per-application HTTP error rate, container crash-looping or repeated restarts, container out-of-memory kills, and host resource pressure (disk, CPU, memory). An alert SHALL be based on collected metrics, not on parsing container log content.

#### Scenario: Sustained per-application error rate triggers an alert
- **WHEN** an application's HTTP 5xx rate, as observed via Traefik's metrics, exceeds a configured threshold for a sustained period
- **THEN** an alert SHALL fire identifying that application

#### Scenario: A crash-looping container triggers an alert
- **WHEN** any container on the host restarts repeatedly within a short window, or is OOM-killed
- **THEN** an alert SHALL fire identifying that container

#### Scenario: Host resource pressure triggers an alert
- **WHEN** host disk usage, CPU usage, or memory usage exceeds a configured threshold for a sustained period
- **THEN** an alert SHALL fire identifying the affected resource

#### Scenario: A metrics source becoming unreachable triggers an alert
- **WHEN** a metrics source the platform stack scrapes (for example postgres-exporter) becomes unreachable for a sustained period
- **THEN** an alert SHALL fire identifying that it can no longer be scraped, rather than that metrics gap going unnoticed

### Requirement: Monitoring Services Are Not Reachable From Application Containers
Prometheus, Alertmanager, Grafana, cAdvisor, node-exporter, and postgres-exporter SHALL NOT be reachable from the Docker network that application repositories' own containers join, so that an application container cannot query cross-application or host-level observability data it was not given credentials for.

The one stated exception is the shared reverse proxy's own metrics endpoint: because the reverse proxy must itself remain reachable from that same network to perform application routing, its metrics endpoint (per-application HTTP status/error-rate counts only) is reachable from application containers too. This exception SHALL NOT be read to permit any other monitoring service to be reachable from that network.

#### Scenario: An application container cannot query Prometheus or an exporter
- **WHEN** a container attached only to the network application repositories join (`platform_edge`) attempts to reach Prometheus's query API, Alertmanager, Grafana, or any metrics exporter other than the reverse proxy's own metrics endpoint
- **THEN** that attempt SHALL NOT succeed, because those services are not attached to that network

#### Scenario: The reverse proxy's metrics endpoint is a stated exception
- **WHEN** a container attached only to `platform_edge` reaches the shared reverse proxy's metrics endpoint
- **THEN** it SHALL be able to read per-application HTTP status/error-rate counts, and this SHALL NOT be treated as a violation of this requirement

### Requirement: Alerts Are Routed to Slack
Alerts raised by the platform stack's monitoring SHALL be delivered to Slack via an incoming webhook. The webhook URL SHALL be sourced from outside the repository, consistent with the "Platform-Level Secrets Are Never Committed" requirement, and never committed in plaintext.

#### Scenario: A firing alert is delivered
- **WHEN** an alert rule fires
- **THEN** a notification for that alert SHALL be posted to the configured Slack destination

### Requirement: External Dead-Man's-Switch Heartbeat
The platform stack SHALL send a periodic heartbeat to an external, third-party dead-man's-switch service, independent of any alert condition, so that the loss of that heartbeat — whether from the host, the platform stack, or the alerting pipeline itself becoming unavailable — is detected by a system that does not depend on the host being reachable.

#### Scenario: Heartbeat is sent during normal operation
- **WHEN** the platform stack's alerting pipeline is running normally
- **THEN** a heartbeat SHALL be sent to the configured external dead-man's-switch service on a regular schedule

#### Scenario: Loss of the host is detected externally
- **WHEN** the host or the platform stack's alerting pipeline becomes unavailable and stops sending heartbeats
- **THEN** the external dead-man's-switch service SHALL detect the missed heartbeat and alert independently of anything running on the host

### Requirement: Metrics Dashboards Are Available
The platform stack SHALL provide a dashboard interface over the collected metrics, so host and per-service health can be inspected visually, not only through raw alert notifications. The dashboard interface SHALL be reachable only over the host's private tailnet, not through the platform's public-facing reverse proxy, and SHALL require a non-default credential to access.

Where the dashboard interface generates an absolute URL of its own — a redirect, a link embedded in a notification, or a link shared between operators — that URL SHALL address the host at the same private-tailnet address the interface is published on, not an address that resolves to whatever machine happens to open it.

#### Scenario: An operator views current health
- **WHEN** an operator on the tailnet opens the dashboard interface
- **THEN** they SHALL be able to view host resource usage, per-container health, and per-application HTTP error rates

#### Scenario: The dashboard interface is not reachable from the public internet
- **WHEN** a request for the dashboard interface arrives on the platform's public-facing reverse proxy or any other public interface
- **THEN** it SHALL NOT be served, because the dashboard interface is bound only to the host's private tailnet interface

#### Scenario: The dashboard interface has no default credential
- **WHEN** the monitoring stack is deployed
- **THEN** the dashboard interface's administrative credential SHALL be set from a secret sourced outside the repository, not left at its default value

#### Scenario: A generated link addresses the host, not the viewer's own machine
- **WHEN** the dashboard interface is asked for the absolute base URL it builds its own links and redirects from
- **THEN** that URL SHALL address the host at the private-tailnet address the interface is published on, so that following such a link from any tailnet peer reaches the dashboard rather than that peer's own loopback interface

#### Scenario: The configured base URL is not a literal that ignores where the interface is published
- **WHEN** the shared platform stack's definition is read
- **THEN** the dashboard interface's configured base URL SHALL be derived from the same value that determines the address it is published on, rather than being a literal address — including `localhost` — that is correct only on the host itself

### Requirement: Monitoring Data Has Bounded, Dedicated Storage
Persistent monitoring data (metrics storage and dashboard state) SHALL be stored on the platform's dedicated data volume rather than the host's local disk, and SHALL be subject to an explicit, bounded retention configuration rather than unbounded growth.

#### Scenario: Monitoring data survives on dedicated storage
- **WHEN** the monitoring stack's containers are recreated
- **THEN** previously collected metrics and dashboard configuration SHALL persist, because they are stored on the platform's dedicated data volume rather than container-local or ephemeral storage

#### Scenario: Retention is bounded
- **WHEN** the monitoring stack has been running long enough to reach its configured retention period
- **THEN** data older than that configured retention period SHALL be discarded rather than accumulating indefinitely

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

### Requirement: Shared-Stack Service Images Are Pinned to an Exact Release
Every service defined in the shared platform Compose stack SHALL declare its container image by an exact release — an immutable content digest, or the tag its publisher assigns to one release and does not repoint at a later one — and SHALL NOT declare it by a tag the publisher continues to repoint as new releases are published.

The stack is deployed by re-running the deploy pipeline against whatever the tag resolves to at that moment, so a repointed tag makes the version actually running a function of when the last deploy happened rather than of what is committed. The pipeline's approver sees the exact diff before approving, and a version change that leaves no diff is a change that reaches production without passing that gate.

Which tags float is a property of the publisher, not of the tag's shape. Publishers here differ: most release `MAJOR.MINOR.PATCH`, so a two-component tag of theirs is a series that floats; PostgreSQL's release version has two components, so `postgres:16` floats while `postgres:16.15` is a release. No rule stated over the shape of a tag alone can therefore decide the question for every image, and this requirement SHALL NOT be restated as one that does.

Because the property cannot be read off a committed file, the obligation SHALL be split. An automated check SHALL enforce a **necessary** condition — one no correctly pinned tag can fail — and SHALL record in its own text that this is all it establishes. Whether a tag that passes it also names a release its publisher leaves in place SHALL be established by the human review every change to the stack definition already passes through. A check that presented its necessary condition as the whole obligation would report a floating tag as pinned, which is worse than not checking.

The necessary condition SHALL be a **floor on specificity, never a ceiling**: a tag naming fewer version components than any publisher uses for a release cannot name a release under any publisher's scheme, and is rejected. A ceiling — rejecting tags at or above some component count — would reject correctly pinned releases, `postgres:16.15` among them. What the floor does not catch is a tag specific enough to be a release under one publisher's scheme but a series under its own; that residue is what the human half of the obligation carries, and SHALL be named rather than left implied.

This mirrors the pinning obligation `iac-cicd-pipeline` already places on the container images the Molecule suite executes inside, and applies for the same reason: a dependency resolved at run time is not pinned by the manifest that names it. It does not adopt that requirement's remedy — a digest is admissible here but not mandated, because a stack image is deployed to one host from a diff a human approves, where a legible version tag carries information a digest does not.

#### Scenario: A service declares a tag that names no specific release
- **WHEN** a service in the shared platform Compose stack declares its image by `latest`, by another tag that names a channel rather than a release, or by a tag naming a version series that its publisher repoints at each new release within that series
- **THEN** that declaration SHALL be rejected, and the service SHALL instead name the exact release it is intended to run, or that release's content digest

#### Scenario: The automated check enforces a floor and says so
- **WHEN** the statically decidable part of this obligation is enforced by an automated check
- **THEN** that check SHALL reject `latest`, any other tag naming a channel rather than a version, and any tag naming **fewer than two** version components — two being the fewest any publisher represented here uses for a release, and therefore a floor no correctly pinned tag can fail
- **AND** it SHALL record that passing establishes only a necessary condition — a tag specific enough to pass may still be a series under its own publisher's scheme, and that residue is carried by human review

#### Scenario: The check does not reject a correctly pinned release
- **WHEN** a service names a release using the number of version components its own publisher uses, such as a two-component PostgreSQL release
- **THEN** the check SHALL accept it, because the condition it enforces is a floor on specificity and never a ceiling

#### Scenario: A version change is visible to the deploy approver
- **WHEN** the version of a shared-stack service changes
- **THEN** that change SHALL appear as a committed diff in the stack definition, so the approver of the gated deploy sees which version they are approving
- **AND** this scenario states why the requirement above matters rather than imposing a new obligation: it is already discharged by `iac-platform-deploy-pipeline`'s "Reviewer Sees the Exact Diff Before Approving" requirement, and needs no separate mechanism
