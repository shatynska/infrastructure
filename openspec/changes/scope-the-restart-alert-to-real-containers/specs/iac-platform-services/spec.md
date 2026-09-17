## MODIFIED Requirements

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
