## ADDED Requirements

### Requirement: An Application Can Probe Its Own Database Through a Read-Only Forced Command

Ansible SHALL provision, for each application that declares a probe key, a second forced-command `authorized_keys` entry on the `deploy` account, distinct from that application's deploy key and bound to exactly one invocation (`/usr/local/bin/deploy-probe <app_name>`), carrying the `restrict` option exactly as the deploy key does. A probe key is optional per application: an application declaring none SHALL receive no probe entry and no probe `sudoers` rule, and this SHALL NOT be an error.

The application name SHALL reach `deploy-probe` and every privileged script it invokes only as the fixed argument its forced command carries and the fully-qualified `sudoers.d` rule that matches it, never as data supplied by the connecting client — the same two independent layers that bind a deploy key to one application. The role and the database the probe reads SHALL be derived from that name. Where the client supplies a role or database name at all, the probe SHALL refuse unless it equals the name the forced command carries; refusal SHALL NOT be reported as any of the tokens below, so that a misdirected probe is never mistaken for an answer about the instance.

`deploy-probe` SHALL read its input from the SSH session's standard input as a single JSON object, and SHALL NOT accept any operand beyond that fixed argument, so that no password reaches a command line or a process listing on either machine. The object SHALL carry `password` and `table`, both required; it MAY carry `role` and `database`, which SHALL equal the names derived from the forced command's argument. The encoding is fixed here rather than left to the implementation because the contract is held by another repository, which cannot read this one's scripts before depending on them. `deploy-probe` SHALL write to no database, create, alter or drop nothing, deliver no content to `/opt/<app_name>`, and trigger no deploy.

The probe SHALL emit exactly one token on standard output and nothing else, drawn from this set and resolved in this order of precedence:

1. `window-open` — a maintenance window is declared on this host, whatever the state of the instance beneath it.
2. `unreachable` — the instance could not be reached, or its own state could not be read.
3. `absent` — the instance was read and the application's role or its database does not exist in it.
4. `credential-refused` — the role and database exist and the supplied password was refused.
5. `empty` — the connection succeeded and the table the client named does not exist, or exists and holds no row.
6. `populated` — the connection succeeded and that table exists and holds at least one row.

**`unreachable` SHALL precede `absent`, and the precedence SHALL NOT be read as an evaluation order that reaches `absent` first.** `absent` is an assertion about what the instance holds and SHALL be made only from a reading of the instance that actually succeeded. A stopped, restarting or absent instance is not a database that ceased to exist, and reporting it as one is the more dangerous error of the two: the operator's documented remedy for `absent` re-provisions the role and rotates its password, which breaks a healthy application whose instance was merely down.

`absent` SHALL be resolved without the application's credential, because the condition it reports is one in which no application credential can be authenticated: a PostgreSQL instance answers an absent role and a wrong password identically. A probe that could not distinguish them would report the reset exactly as it reports a stale password, which is the failure this requirement exists to end.

The table SHALL be named by the client rather than fixed in this repository, and SHALL be resolved by an identifier lookup that cannot execute client-supplied SQL. A name that resolves to no table SHALL answer `empty`, not an error.

**A token and a failure SHALL be distinguishable without parsing either.** The probe SHALL exit zero when and only when it emits a token, and SHALL exit non-zero, emitting no token and a diagnostic on standard error, in every other case — a malformed, oversized or incomplete input object, a `role` or `database` disagreeing with the derived name, and any error the token set does not classify, **whatever layer raised it**. The container runtime failing to give the probe a client is as unclassified as a message from the instance the implementation does not recognise; neither is `unreachable`, which is an assertion about the instance and not about the probe's own machinery. An unclassified error SHALL NOT be resolved to the nearest token: a message the implementation does not recognise, in any language the instance may be configured to emit, is a probe that failed rather than an answer about the database.

An input object carrying fields beyond those named SHALL be accepted and the unknown fields ignored, so that the repository holding the other half of this contract can add one without breaking the deploy of an application that was being careful.

**The table name SHALL NOT be interpolated into a command string at any layer**, and SHALL reach SQL only as a quoted identifier argument. It is the one client-supplied value that reaches SQL at all, and a name carrying a shell metacharacter SHALL NOT be capable of executing anything, anywhere, whether or not the password supplied with it would have been accepted. Unlike the password, the name is not secret and its presence in a process listing is not itself a defect; what is forbidden is its being able to run.

The name SHALL additionally be required to take the shape of an optionally schema-qualified identifier. A name outside that shape SHALL refuse non-zero rather than answering `empty` — `empty` asserts that the database was read and held no such table, and a name refused before any reading would make that assertion about a database nothing looked at. The shape SHALL admit a schema-qualified name, which is legitimate and resolvable, so that a correct request is not refused.

An application's probe public key SHALL be enumerated in version control alongside its deploy key, and the two SHALL be distinct keys: one `authorized_keys` entry carries one forced command, so a key that could do both would be a key bound to neither.

#### Scenario: A probe key can only probe its own application
- **WHEN** an application's probe key connects and supplies another application's role or database name
- **THEN** the probe SHALL refuse, emitting no token and exiting non-zero
- **AND** it SHALL NOT report that refusal as `absent`, `credential-refused`, `unreachable`, `empty`, `populated` or `window-open`

#### Scenario: A stopped instance is not reported as a destroyed database
- **WHEN** the shared instance is not running, is restarting, or its own state cannot be read for any other reason
- **THEN** the probe SHALL answer `unreachable`
- **AND** it SHALL NOT answer `absent`, whether or not the application's role and database would have been found had the instance been readable

#### Scenario: An unclassified failure is not resolved to the nearest token
- **WHEN** the instance returns an error the token set does not classify, or the input object is malformed or incomplete
- **THEN** the probe SHALL emit no token, exit non-zero, and write a diagnostic to standard error
- **AND** it SHALL NOT emit the token whose condition most nearly resembles the failure

#### Scenario: A probe key cannot deliver or deploy
- **WHEN** an application's probe key connects and pipes an archive, a command, or any other content over standard input
- **THEN** nothing SHALL be extracted into `/opt/<app_name>`, no deploy SHALL be triggered, and no write of any kind SHALL be made to any database in the instance

#### Scenario: A leaked probe key cannot be used to pivot into the host's network
- **WHEN** an application's probe key is used to open a port-forwarding, agent-forwarding, X11-forwarding, or pty-allocating channel, rather than the one forced command
- **THEN** the connection SHALL be refused, independent of and in addition to the forced-command restriction on what that key can execute

#### Scenario: An absent role is told apart from a refused credential
- **WHEN** the application's role or database does not exist in the instance
- **THEN** the probe SHALL answer `absent`
- **AND** it SHALL answer `absent` whether or not the password supplied would have been the right one, and without that password having to be correct for the answer to be reached

#### Scenario: A stale password is told apart from a reset instance
- **WHEN** the application's role and database both exist and the supplied password is refused
- **THEN** the probe SHALL answer `credential-refused`

#### Scenario: An unreachable instance is not reported as a credential problem
- **WHEN** the instance cannot be reached at all — no route, no name resolution, or nothing listening
- **THEN** the probe SHALL answer `unreachable`, and SHALL NOT answer `credential-refused`

#### Scenario: A marker table that does not exist is an ordinary answer
- **WHEN** the connection succeeds and the table the client named does not exist in that database
- **THEN** the probe SHALL answer `empty`, and SHALL NOT report an error

#### Scenario: A table name cannot execute anything
- **WHEN** the client supplies a table name carrying shell metacharacters, a quote, or a statement separator
- **THEN** nothing SHALL execute as a result, at any layer, whether or not the password supplied alongside it is correct
- **AND** the probe SHALL answer `empty` or refuse non-zero, and SHALL reach no other outcome

#### Scenario: A schema-qualified table name is not refused for being qualified
- **WHEN** the client supplies a schema-qualified table name that resolves in its database
- **THEN** the probe SHALL answer `empty` or `populated` on what that name resolves to, and SHALL NOT refuse it for carrying a schema

#### Scenario: An oversized or unrecognised input object
- **WHEN** the client sends an input object larger than the probe accepts
- **THEN** the probe SHALL refuse non-zero, emitting no token, without having read it all
- **AND** **WHEN** the object carries fields beyond those the contract names, those fields SHALL be ignored and the probe SHALL answer as though they were absent

#### Scenario: An application that declares no probe key gets none
- **WHEN** an application is enumerated for deployment without a probe public key
- **THEN** the converge SHALL install its deploy entry as before, install no probe entry and no probe `sudoers` rule, and SHALL NOT fail

#### Scenario: The password never reaches a command line
- **WHEN** a probe is invoked
- **THEN** the password SHALL travel only over the SSH session's standard input, and SHALL appear in no process listing and no shell history on either machine

### Requirement: The Host Carries an Operator-Declared Maintenance Window for the Shared Instance

The host SHALL carry a declaration, raised and withdrawn by an operator, that a destructive maintenance window on the shared PostgreSQL instance is in progress. Ansible SHALL provision whatever the declaration is held in, so that it exists on a host before any window does, and so that an operator account — which holds no `sudo` of any kind — can raise and withdraw it with the capability it already has.

The declaration SHALL live outside the volume whose discarding is the window, so that it survives the act it describes, and outside every `/opt/<app_name>`, which an operator account cannot read. It SHALL be host-wide rather than per-application, since the instance is shared and one window reaches every database in it. It SHALL NOT require an application's credential to read.

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
- **WHEN** the shared instance's volume is removed and re-created during the window it declares
- **THEN** the declaration SHALL still be in force afterwards, until an operator withdraws it
