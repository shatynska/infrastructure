## ADDED Requirements

### Requirement: A Host's Rebuild Procedure Is Recorded, and Its Rehearsal State With It

This repository SHALL carry one document giving the ordered steps that take a host of this repository from a destroyed server to a serving one — `docs/runbook-rebuild.md`. That document SHALL be the only place that sequence is written. Another document MAY name it, and MAY say what only that document can say, but SHALL NOT restate the sequence — two accounts of one procedure drift, and the drift is invisible until the procedure is next needed.

Each step SHALL name the credential it needs and where that credential is held, or SHALL state that it needs none. A step performed outside this repository — at the DNS provider, at the tailnet, at the heartbeat observer, in an application's own repository — SHALL be written as a step of the sequence rather than left to be inferred, and SHALL name where it is performed.

A **rehearsal** is a run of the whole sequence against a real host, beginning with that host's server destroyed and ending with that host serving what it served before. Reading the steps, checking that each credential exists, or performing the sequence in part is not a rehearsal and SHALL NOT be recorded as one.

The document SHALL carry a rehearsal record, and that record SHALL be in exactly one of three states. Each state SHALL be expressed in labelled lines rather than in prose, for the reason the credential line above is: a label is what makes an absence detectable, and prose cannot be read by a check. The record SHALL carry a `Last rehearsed:` line in every state, and a `Partial run:` block in exactly one:

- **Never rehearsed** — `Last rehearsed: never`, and no `Partial run:` block. The never-state SHALL be stated outright in that fixed form rather than by leaving a date field blank, because a blank field is indistinguishable from one someone forgot to fill in and the two mean opposite things.
- **Partially rehearsed** — a run began and did not reach a serving host. `Last rehearsed:` SHALL still read `never`, because a run that did not complete rehearsed nothing, and the record SHALL additionally carry a `Partial run:` block holding a `Reached:` line, a `Wall clock:` line and a `Stopped by:` line. A partial run is worth recording and is not evidence the procedure works; these two facts are what make the record readable as the first and not as the second.
- **Rehearsed** — `Last rehearsed:` SHALL carry the date, beside a `Duration:` line and a `Stack:` line naming the stack it was performed against, and no `Partial run:` block.

A partial run that is later completed replaces the partial record rather than accumulating beside it; what the partial run found is preserved by the corrections it caused in the steps, which is where a later reader needs it.

A rehearsal SHALL be performed against a stack whose loss is tolerable, and SHALL NOT be performed against a stack carrying data or service whose loss is not. The stack it was performed against SHALL be named in the record, because a sequence rehearsed on one stack is evidence about another only as far as their declarations agree.

Where a rehearsal finds a step wrong, missing, or out of order, the correction SHALL be made in the document itself rather than recorded beside it as a finding, so that the next reader reads the corrected procedure rather than the original plus an erratum. The rehearsal record SHALL still name what was corrected, so that a reader can tell a procedure that has been exercised from one that has merely been written.

A rebuild silences the host's own reporters while it runs, so the document SHALL state which of this system's alarms a rebuild is expected to raise, for roughly how long, and what to do about each before the server is destroyed. It SHALL also carry the steps owed at the external observer once the host is back, naming that observer as where they are performed, and including re-reading each of that host's checks against its intended period and grace — a check re-created by its own first ping carries the observer's default rather than the one the reporter needs. An alarm that fires because a rebuild is in progress and that no step predicted is indistinguishable from a real one, and is what teaches an operator to stop reading the list.

**Every check a host of this repository reports to SHALL have its intended period and grace recorded in one place in this repository, and the rebuild sequence SHALL cite that place rather than copy the values into itself.** The distinction from the single-account rule above is the kind of content: a *sequence* is followed step by step and must be in front of its reader, while a register of settings is looked up and verified against, and a copied lookup is what goes stale. A check whose intended settings are recorded nowhere cannot be verified after a rebuild at all, so recording them is part of satisfying this requirement rather than a precondition of it.

For the stores the rebuilt host held, the document SHALL state which contents come back and which do not, deriving that from *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) rather than restating its classification, and SHALL name any store that requirement records as unmet — a store whose loss a rebuild makes real is the one fact a rebuild's operator most needs before starting, and the one no green run will report.

#### Scenario: A host has to be rebuilt

- **WHEN** an operator has to take a host of this repository from a destroyed server back to serving
- **THEN** one document in this repository SHALL give the steps in the order they are performed
- **AND** each of those steps SHALL name the credential it needs and where that credential is held, or state that it needs none
- **AND** a step performed outside this repository SHALL appear in that sequence and name where it is performed

#### Scenario: The procedure is also described somewhere else

- **WHEN** another document in this repository has occasion to refer to rebuilding a host
- **THEN** it SHALL name the recorded procedure rather than restate its steps
- **AND** what it keeps SHALL be what only it can say, not a second copy of the sequence

#### Scenario: A rehearsal is performed

- **WHEN** the recorded procedure is rehearsed
- **THEN** the run SHALL begin with a real host's server destroyed and end with that host serving what it served before
- **AND** the document SHALL record the date, the wall-clock duration, and the stack the rehearsal was performed against

#### Scenario: The procedure has never been rehearsed

- **WHEN** the document exists and no rehearsal of it has been performed
- **THEN** its rehearsal record SHALL say so outright, in a fixed form
- **AND** that state SHALL NOT be expressed by leaving the date and the duration blank, which is indistinguishable from an unfilled field

#### Scenario: A run stops before the host is serving

- **WHEN** a run of the sequence begins and does not reach a serving host
- **THEN** the record SHALL carry a `Partial run:` block holding a `Reached:` line, a `Wall clock:` line and a `Stopped by:` line
- **AND** its `Last rehearsed:` line SHALL read `never`, since a run that did not complete rehearsed nothing
- **AND** a later completed run SHALL replace that record rather than accumulate beside it

#### Scenario: A rebuild silences the host's own reporters

- **WHEN** the sequence destroys a server whose host reports to an external observer
- **THEN** the document SHALL say, before that step, which alarms the rebuild is expected to raise and for roughly how long
- **AND** it SHALL carry the steps owed at that observer once the host is back, naming the observer as where they are performed, including re-reading each of that host's checks against its intended period and grace

#### Scenario: A check's intended settings are recorded nowhere

- **WHEN** a host of this repository reports to a check whose intended period and grace no committed file records
- **THEN** those settings SHALL be recorded in the one place this repository keeps them
- **AND** the rebuild sequence SHALL cite that place rather than carry a second copy of the values

#### Scenario: A rehearsal is proposed against a stack whose loss is not tolerable

- **WHEN** a rehearsal would be performed against a stack carrying data or service whose loss is not tolerable
- **THEN** it SHALL NOT be performed against that stack
- **AND** the rehearsal SHALL be performed against a stack whose loss is tolerable instead, and the record SHALL name which stack that was

#### Scenario: A rehearsal finds the procedure wrong

- **WHEN** a rehearsal finds a step wrong, missing, or out of order
- **THEN** the document's own steps SHALL be corrected
- **AND** the rehearsal record SHALL name what was corrected, rather than the correction being left as the record's only trace

#### Scenario: A store the rebuilt host held does not come back

- **WHEN** a store on the host being rebuilt holds contents that a rebuild does not restore
- **THEN** the document SHALL say so before the step that destroys the server
- **AND** where *No Store on This Host Holds Data Requiring Backup* records a store as unmet on that stack, the document SHALL name that store and that stack rather than describing the host as fully recoverable
