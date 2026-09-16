## MODIFIED Requirements

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
