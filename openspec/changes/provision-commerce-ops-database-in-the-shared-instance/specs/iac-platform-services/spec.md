## MODIFIED Requirements

### Requirement: Single Shared PostgreSQL Instance, Per-Application Databases
The platform stack SHALL run one shared PostgreSQL instance, and the data kept in it SHALL be limited to **non-durable application data**: technical or temporary records whose loss is tolerable to the application that wrote them, or data admitted under the staging rehearsal-data policy below, whose loss is tolerable to the operator. An application that keeps data of that class **in a relational database** on this host SHALL be given its own database within that shared instance rather than running a PostgreSQL container of its own. A non-relational store — a cache, a queue file, an upload directory — is not in scope for this requirement at all, and falls to *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) instead. An application whose data is **durable** — data whose loss would not be tolerable — SHALL NOT keep it in the shared instance under any circumstances. That is unconditional, and it is what makes this instance classifiable as needing no backup at all. Elsewhere on this host, durable data is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which admits it only where the logical backup and rehearsed restore it requires are already in place. Absent those, durable application data belongs in an external managed service that owns its own backups, and that is the expected answer rather than the exception.

The instance exists so that several small services can share one PostgreSQL rather than each running theirs, and this scoping is what makes the absence of any backup of it a decision rather than an oversight. The corresponding obligation is recorded as *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), which states what becomes owed if durable data ever does land here.

This requirement binds when an application actually keeps data on this host. An application that keeps none is not in scope for it and is not owed a database.

**An application whose data divides is classified table by table.** Where some of an application's relational data is durable and some is not, only the non-durable part SHALL be placed in its database in the shared instance, and the division SHALL be stated in the change in this repository that records that database. A table the stated division does not name is unclassified, and an unclassified table SHALL NOT be placed in the shared instance. Calling data "business data" or "technical data" does not classify it; the only question is whether its loss would be tolerable to the party this requirement names for it — the application that wrote it, or on a staging host the operator.

**On a staging host, application data in the shared instance is rehearsal data.** The data an application keeps in its database in the shared instance of a host whose environment is staging SHALL be treated as data whose loss is tolerable **to the operator**, who is the only party that writes it, so the whole of that database is non-durable under this requirement regardless of what the same tables hold in production. That holds only while it is true: data copied from production SHALL NOT be placed in a staging host's shared instance, and a staging database that begins holding data whose loss would not be tolerable puts that host in breach of this requirement from that moment. This policy reaches that database and nothing else the application persists on the host.

**Each application's database is its own.** An application's database SHALL be owned by a role of its own, and no other application's role SHALL be able to connect to it. The role and its password are provisioned per host: the same application on two hosts has two independently generated passwords, each delivered only to that host's deploy target, so that one leaked credential reaches one host. No such password SHALL enter a file in this repository.

How a database and its role are provisioned inside the instance, and how its password reaches the application, SHALL be automated, and the trigger for that obligation is the first application given a database in this instance. Until that automation exists, each provisioning is performed by hand by an operator, by the recipe in `docs/bootstrap-a-new-host.md`, and this requirement obliges the provisioning rather than any particular mechanism for it.

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
