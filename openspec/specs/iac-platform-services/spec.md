## Purpose

Defines the shared platform Compose stack — services common to the whole server such as the reverse proxy, shared database, and metrics/alerting/dashboards — as distinct from per-application stacks, including its deployment boundary relative to Ansible and its single-host placement.

## Requirements

### Requirement: Shared Services Live in a Dedicated Platform Stack
Services common to the whole server (reverse proxy, shared database, and — when added — monitoring) SHALL be defined in a single Compose stack under `platform/`, separate from any per-application Compose file.

#### Scenario: A new application reuses the platform stack
- **WHEN** a new application is deployed to the server
- **THEN** it SHALL reuse the existing platform-managed reverse proxy rather than defining its own
- **AND** for any **non-durable** data it keeps in a relational database on this host, it SHALL reuse the platform-managed database rather than defining a PostgreSQL container of its own
- **AND** any other store it persists on this host is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) rather than by this scenario

### Requirement: Single Shared PostgreSQL Instance, Per-Application Databases
The platform stack SHALL run one shared PostgreSQL instance, and the data kept in it SHALL be limited to **non-durable application data**: technical or temporary records whose loss is tolerable to the application that wrote them, or data admitted under the staging rehearsal-data policy below, whose loss is tolerable to the operator. An application that keeps data of that class **in a relational database** on this host SHALL be given its own database within that shared instance rather than running a PostgreSQL container of its own. A non-relational store — a cache, a queue file, an upload directory — is not in scope for this requirement at all, and falls to *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) instead. An application whose data is **durable** — data whose loss would not be tolerable — SHALL NOT keep it in the shared instance under any circumstances. That is unconditional, and it is what makes this instance classifiable as needing no backup at all. Elsewhere on this host, durable data is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which admits it only where the logical backup and rehearsed restore it requires are already in place. Absent those, durable application data belongs in an external managed service that owns its own backups, and that is the expected answer rather than the exception.

The instance exists so that several small services can share one PostgreSQL rather than each running theirs, and this scoping is what makes the absence of any backup of it a decision rather than an oversight. The corresponding obligation is recorded as *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which states what becomes owed if durable data ever does land here.

This requirement binds when an application actually keeps data on this host. An application that keeps none is not in scope for it and is not owed a database.

**An application whose data divides is classified table by table.** Where some of an application's relational data is durable and some is not, only the non-durable part SHALL be placed in its database in the shared instance, and the division SHALL be stated in the change in this repository that records that database. A table the stated division does not name is unclassified, and an unclassified table SHALL NOT be placed in the shared instance. Calling data "business data" or "technical data" does not classify it; the only question is whether its loss would be tolerable to the party this requirement names for it — the application that wrote it, or on a staging host the operator.

**On a staging host, application data in the shared instance is rehearsal data.** The data an application keeps in its database in the shared instance of a host whose environment is staging SHALL be treated as data whose loss is tolerable **to the operator**, who is the only party that writes it, so the whole of that database is non-durable under this requirement regardless of what the same tables hold in production. That holds only while it is true: data copied from production SHALL NOT be placed in a staging host's shared instance, and a staging database that begins holding data whose loss would not be tolerable puts that host in breach of this requirement from that moment. This policy reaches that database and nothing else the application persists on the host.

**Each application's database is its own.** An application's database SHALL be owned by a role of its own, and no other application's role SHALL be able to connect to it. The role and its password are provisioned per host: the same application on two hosts has two independently generated passwords, each delivered only to that host's deploy target, so that one leaked credential reaches one host. No such password SHALL enter a file in this repository.

How a database and its role are provisioned inside the instance, and how its password reaches the application, SHALL be automated, and the trigger for that obligation is the first application given a database in this instance. Until that automation exists, each provisioning is performed by hand by an operator, by the recipe in `docs/onboard-an-application.md`, and this requirement obliges the provisioning rather than any particular mechanism for it.

**This requirement names the document holding that recipe, and that naming SHALL be kept true.** A manual step is performed from the document, so a requirement naming a document that does not hold the recipe sends an operator to the wrong file at the moment they are provisioning a credential by hand. The document named here SHALL hold the recipe, and no other committed Markdown document outside `openspec/` SHALL hold a second copy of it: two copies of a procedure touching a credential drift, and both read as authoritative. The population is bounded that way because the other copies in this repository are deliberate and are not documents an operator would follow — change records under `openspec/` quote the recipe as history, and the test suite carries it as fixtures whose drift from the living recipe is itself a recorded decision.

**One divergence is stated rather than hidden, as of 2026-09-13.** That trigger fired on 2026-09-13, when `commerce-ops` became the first application given a database in this instance, on the staging host. The obligation is due and is not met: that database, its role and its password are provisioned and delivered by hand, and the mechanism and its credential path are owed and not yet built. This requirement SHALL be read as unmet in that one respect, and a manual provisioning SHALL NOT be read as discharging it — for `commerce-ops` or for any application provisioned by hand after it. The mechanism is tracked in `docs/backlog.md` as `automate-per-application-database-provisioning`; the obligation is stated here as well, because a backlog entry is deleted when its change is archived. This paragraph is replaced when that mechanism lands, and not before.

#### Scenario: A new application requests a database
- **WHEN** an application deployed to this host needs to store non-durable application data, as this requirement defines it, in a relational database
- **THEN** a database SHALL be provisioned for it within the shared PostgreSQL instance, not a new PostgreSQL container
- **AND** that database SHALL be owned by a role of the application's own, which no other application's role can connect to
- **AND** that role's password SHALL be generated for this host alone, delivered only to this host's deploy target, and SHALL NOT enter a file in this repository

#### Scenario: An application needs durable storage
- **WHEN** an application needs to store data whose loss would not be tolerable
- **THEN** it SHALL use an external managed service that owns its own backups, unless the logical backup and rehearsed restore required by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) are already in place
- **AND** it SHALL NOT keep that data in the shared PostgreSQL instance, under any circumstances, whether or not such a backup exists
- **AND** it SHALL NOT keep that data in a PostgreSQL container of its own on this host either, unless the logical backup and rehearsed restore required by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) are in place before it lands

#### Scenario: An application's data divides into durable and non-durable parts
- **WHEN** an application is given a database in the shared instance and some of its relational data is durable
- **THEN** the change in this repository that records that database SHALL state which tables are non-durable and which are durable
- **AND** only the tables stated as non-durable SHALL be placed in the shared instance
- **AND** a table the division does not name SHALL NOT be placed there until a change in this repository classifies it

#### Scenario: A staging database holds rehearsal data
- **WHEN** an application is given a database in a staging host's shared instance
- **THEN** that database's whole contents SHALL be treated as data whose loss is tolerable to the operator
- **AND** data copied from a production database SHALL NOT be placed in it
- **AND** that policy SHALL NOT be read to classify any other store the application persists on that host

#### Scenario: The automation trigger has fired and the mechanism is not built
- **WHEN** an application's database in the shared instance has been provisioned, or its password delivered, by hand
- **THEN** this requirement SHALL state, dated, which application fired the trigger and that the mechanism and its credential path are owed
- **AND** that manual provisioning SHALL NOT be read as discharging the obligation to automate it

#### Scenario: The document this requirement names holds the recipe
- **WHEN** this requirement names a committed document as holding the manual provisioning recipe
- **THEN** that document SHALL hold it
- **AND** no other committed Markdown document outside `openspec/` SHALL hold a second copy of it

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

An alert rule whose subject is a container SHALL select only series that identify one. The container metrics the platform stack collects are reported per control group, and a host runs many control groups that are not containers — system services, login sessions, and whatever else the init system supervises — whose ordinary starting and stopping is not an event this alerting exists to report. A rule that does not exclude them reports their churn as a container incident, and does so in a notification that can name no container, because those series carry no container name to put in it.

#### Scenario: Sustained per-application error rate triggers an alert
- **WHEN** an application's HTTP 5xx rate, as observed via Traefik's metrics, exceeds a configured threshold for a sustained period
- **THEN** an alert SHALL fire identifying that application

#### Scenario: A crash-looping container triggers an alert
- **WHEN** any container on the host restarts repeatedly within a short window, or is OOM-killed
- **THEN** an alert SHALL fire identifying that container by name

#### Scenario: A control group that is not a container raises no container alert
- **WHEN** a control group on the host that is not a container — a system service restarted by an unattended upgrade, or a login session's control group created and destroyed by repeated short-lived logins — starts repeatedly within the same window that would raise the crash-looping alert for a container
- **THEN** no container alert SHALL fire for it, because the rule's subject is restricted to series that identify a container
- **AND** an out-of-memory kill inside such a control group SHALL likewise raise no container alert, the restriction applying to every series the rule reads rather than only to the one that reports starts

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

### Requirement: An Expiring TLS Certificate Is Alerted On Before It Expires
The platform stack SHALL alert when a TLS certificate the shared reverse proxy serves is approaching expiry, with enough lead time remaining to reissue it before any client is affected. The notification a recipient actually receives SHALL identify which certificate is affected, including when more than one is approaching expiry at the same time.

The threshold SHALL be strictly less than the lead time at which the reverse proxy begins renewing a certificate on its own, so that the alert reports a renewal that did not happen rather than one that has not happened yet.

This requirement is satisfied by metrics the reverse proxy already publishes about the certificates it holds. It does not require probing a public hostname and is not a check made from outside the host, so it does not cover a failure that is invisible from the host itself.

#### Scenario: A certificate approaching expiry raises an alert
- **WHEN** a certificate the shared reverse proxy serves is within the configured number of days of its expiry timestamp, for a sustained period
- **THEN** an alert SHALL fire identifying that certificate by the hostname it was issued for

#### Scenario: Several certificates approaching expiry are each identified
- **WHEN** more than one certificate is within the configured number of days of expiry at the same time
- **THEN** each affected hostname SHALL be named in a notification that is delivered, rather than the group collapsing into a single notification that names none

#### Scenario: A certificate renewing normally raises no alert
- **WHEN** the shared reverse proxy renews a certificate on its own schedule and the replacement's expiry moves further out
- **THEN** no alert SHALL fire, because the threshold leaves normal renewal strictly more lead time than the alert requires

#### Scenario: A superseded certificate does not raise an alert against a healthy hostname
- **WHEN** a certificate is renewed and a record of the superseded certificate's earlier expiry remains observable
- **THEN** no alert SHALL fire for that hostname on account of the superseded record, because the hostname's certificate is not in fact approaching expiry

#### Scenario: Certificate expiry no longer being observed raises an alert
- **WHEN** certificate expiry stops being observable at all — whether because the source publishing it has become unreachable, or because it remains reachable but no longer publishes that measurement
- **THEN** an alert SHALL fire reporting that condition, rather than the certificate alert silently evaluating an empty result and never firing again

### Requirement: A Destructive Window on the Shared Instance Is Announced to the Applications That Hold Databases in It

The shared PostgreSQL instance is disposable by design: *Single Shared PostgreSQL Instance, Per-Application Databases* holds nothing durable in it precisely so that its store can be discarded, and discarding it destroys every application role and database it held. **The store is named here by what it holds rather than by the form it takes**: it has been a named volume and is a directory on the attached data volume, and a procedure that clears a directory destroys exactly what a procedure that removed a volume destroyed. A requirement whose trigger named the form would have stopped binding at the moment the form changed, which is a silent way for an announcement obligation to lapse. That act SHALL be announced to the applications it reaches, and this host SHALL make available to every application holding a database in the instance a means of determining, before it delivers anything, whether the database it is configured for still exists.

What is obliged is the availability of that means, not any application's use of it: an application that does not take it up is choosing the position every application is in today, and this requirement is not met or unmet by that choice. It is unmet if the means does not exist, or exists and cannot be reached by an application entitled to it.

A procedure in this repository that discards, re-creates or re-initialises that instance's data SHALL declare a window on that host before the first destructive step, and SHALL withdraw that declaration once the instance is serving again — before the step that re-provisions the application databases, so that re-provisioning and the redeploys it requires are not themselves blocked by the declaration they came after.

Between the withdrawal and an application's own re-provisioning, that application's role and database do not exist, and that state SHALL be reported to the application as such rather than as a credential failure. An application deploying in that gap SHALL therefore be able to refuse to deliver, with a reason naming the reset rather than its password.

The announcement SHALL NOT be a sentence addressed to a human, and SHALL NOT depend on a list read from the instance before it is destroyed. A procedure whose only announcement is prose satisfies nothing here: the 2026-09-15 window was announced exactly that way, its re-provisioning step was not performed, and the application that lost its database learnt of it four and a half hours later, from a message naming a credential, reported to this repository by the application's own repository rather than by anything here.

This requirement obliges the announcement and the determinability, not any particular mechanism for either. The mechanism this repository provides is *An Application Can Probe Its Own Database Through a Read-Only Forced Command* and *The Host Carries an Operator-Declared Maintenance Window for the Shared Instance* (`openspec/specs/iac-host-configuration/spec.md`).

Whether an application actually consults the announcement is that application's own decision and lies outside this repository. What this requirement binds is that the announcement exists, is machine-readable, can be taken up by any application holding a database in the instance that asks to, and survives the destruction it describes. An application that has not taken it up is not evidence against this requirement; a means that could not be taken up would be.

#### Scenario: A destructive procedure declares a window before its first destructive step
- **WHEN** a procedure in this repository discards, re-creates or re-initialises the shared instance's data on a host
- **THEN** it SHALL declare a window on that host before the first step that destroys anything
- **AND** it SHALL withdraw that declaration once the instance is serving again, before the step that re-provisions the application databases

#### Scenario: An application can determine that its database has ceased to exist
- **WHEN** an application's database and role have been destroyed and not yet re-provisioned
- **THEN** the means this host provides SHALL be able to determine that, before the application delivers anything to the host
- **AND** that determination SHALL report the absence as such, and SHALL NOT be reported as a refused credential
- **AND** it SHALL report absence only from a reading of the instance that succeeded, never from an instance it could not read

#### Scenario: The announcement outlives what it announces
- **WHEN** the store holding the shared instance's data is discarded, cleared or re-initialised during the window
- **THEN** the declaration SHALL still be readable afterwards

#### Scenario: Prose alone does not discharge the announcement
- **WHEN** a destructive procedure's only announcement is a written instruction addressed to a human
- **THEN** this requirement SHALL be read as unmet by that procedure
