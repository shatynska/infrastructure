## MODIFIED Requirements

### Requirement: The Host Carries an Operator-Declared Maintenance Window for the Shared Instance

The host SHALL carry a declaration, raised and withdrawn by an operator, that a destructive maintenance window on the shared PostgreSQL instance is in progress. Ansible SHALL provision whatever the declaration is held in, so that it exists on a host before any window does, and so that an operator account — which holds no `sudo` of any kind — can raise and withdraw it with the capability it already has.

The declaration SHALL live outside the store whose destruction is the window, so that it survives the act it describes — and, where that store is a directory on an attached volume rather than a volume of its own, outside that volume too, so that the obligation does not turn on which form the store currently takes — and outside every `/opt/<app_name>`, which an operator account cannot read. It SHALL be host-wide rather than per-application, since the instance is shared and one window reaches every database in it. It SHALL NOT require an application's credential to read.

**Its location SHALL be a fixed, documented path**, since an operator types it under time pressure and the runbook, the role's own documentation and the probe must name the same thing. It SHALL be evaluated by the privileged half of the probe, so that one place decides whether a window is in force; the unprivileged half SHALL NOT be where that answer is reached, whatever it can or cannot read.

Raising it SHALL be enough to make every probe on that host answer `window-open`, and withdrawing it SHALL be enough to stop that, with no converge, no deploy and no restart in between — an operator in the middle of a window cannot wait on a pipeline.

A declaration left raised SHALL fail safe: applications continue to be told a window is open and continue not to deliver, which is the direction that costs a delayed deploy rather than a delivery into a destroyed instance.

#### Scenario: A declared window is reported to every application on that host
- **WHEN** a window is declared on a host and any application's probe key connects
- **THEN** the probe SHALL answer `window-open`
- **AND** it SHALL answer `window-open` whatever the state of the role, the database, the credential or the instance beneath it

#### Scenario: Raising and withdrawing the declaration needs no pipeline
- **WHEN** an operator raises or withdraws the declaration on the host
- **THEN** the next probe SHALL reflect it, without a converge, a deploy or a restart of any service

#### Scenario: An operator can declare a window without sudo
- **WHEN** an operator account provisioned per *Unprivileged Operator Accounts Support Interactive Host Inspection* raises or withdraws the declaration
- **THEN** it SHALL succeed using only the capability that account is already granted, and no `sudoers` rule SHALL be added for it

#### Scenario: The declaration survives the volume being discarded
- **WHEN** the shared instance's store is discarded, cleared or re-initialised during the window it declares, whatever form that store takes
- **THEN** the declaration SHALL still be in force afterwards, until an operator withdraws it
