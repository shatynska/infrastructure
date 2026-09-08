## MODIFIED Requirements

### Requirement: Shared Services Live in a Dedicated Platform Stack
Services common to the whole server (reverse proxy, shared database, and — when added — monitoring) SHALL be defined in a single Compose stack under `platform/`, separate from any per-application Compose file.

#### Scenario: A new application reuses the platform stack
- **WHEN** a new application is deployed to the server
- **THEN** it SHALL reuse the existing platform-managed reverse proxy rather than defining its own
- **AND** for any **non-durable** data it keeps in a relational database on this host, it SHALL reuse the platform-managed database rather than defining a PostgreSQL container of its own
- **AND** any other store it persists on this host is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) rather than by this scenario

### Requirement: Single Shared PostgreSQL Instance, Per-Application Databases
The platform stack SHALL run one shared PostgreSQL instance, and the data kept in it SHALL be limited to **non-durable application data**: technical or temporary records whose loss is tolerable to the application that wrote them. An application that keeps data of that class **in a relational database** on this host SHALL be given its own database within that shared instance rather than running a PostgreSQL container of its own. A non-relational store — a cache, a queue file, an upload directory — is not in scope for this requirement at all, and falls to *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) instead. An application whose data is **durable** — data whose loss would not be tolerable — SHALL NOT keep it in the shared instance under any circumstances. That is unconditional, and it is what makes this instance classifiable as needing no backup at all. Elsewhere on this host, durable data is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which admits it only where the logical backup and rehearsed restore it requires are already in place. Absent those, durable application data belongs in an external managed service that owns its own backups, and that is the expected answer rather than the exception.

The instance exists so that several small services can share one PostgreSQL rather than each running theirs, and this scoping is what makes the absence of any backup of it a decision rather than an oversight. The corresponding obligation is recorded as *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which states what becomes owed if durable data ever does land here.

This requirement binds when an application actually keeps data on this host. An application that keeps none is not in scope for it and is not owed a database.

How a database and its role are provisioned inside the instance is deliberately not defined here, because no application has needed one and a mechanism designed against no consumer is guesswork. It SHALL be defined when the first application needs technical storage in this instance, and until then this requirement obliges the provisioning rather than any particular mechanism for it. The deferral is tracked in `docs/deferred-work.md`; the obligation and its trigger are stated here, because that file's entries are deleted when they stop being true — which is exactly when the mechanism gets defined.

#### Scenario: A new application requests a database
- **WHEN** an application deployed to this host needs to store non-durable technical or temporary data in a relational database
- **THEN** a database SHALL be provisioned for it within the shared PostgreSQL instance, not a new PostgreSQL container

#### Scenario: An application needs durable storage
- **WHEN** an application needs to store data whose loss would not be tolerable
- **THEN** it SHALL use an external managed service that owns its own backups, unless the logical backup and rehearsed restore required by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) are already in place
- **AND** it SHALL NOT keep that data in the shared PostgreSQL instance, under any circumstances, whether or not such a backup exists
- **AND** it SHALL NOT keep that data in a PostgreSQL container of its own on this host either, unless the logical backup and rehearsed restore required by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) are in place before it lands
