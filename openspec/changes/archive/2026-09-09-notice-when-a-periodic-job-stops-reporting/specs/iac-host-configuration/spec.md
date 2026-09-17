## ADDED Requirements

### Requirement: Scheduled Host Units Report Their Own Liveness
Every scheduled unit **whose definition a role in this repository writes** SHALL report the outcome of each activation to the same **external** observer the repository's schedule-triggered workflows report to, so that a unit that fails, a unit killed by its own bound, and a timer that has stopped being scheduled are equally visible. The scope is units this repository defines, not every timer present on the host: a package this repository installs may ship timers of its own — unattended security updates do — and those are the packager's to define, report and bound. As on the continuous-integration side, the observer SHALL alarm on silence rather than only on a reported failure: a timer that stops firing leaves no failed unit behind, and `systemctl list-units --failed` is a manual read that nothing performs on a schedule.

The report SHALL come from the init system rather than from inside the unit's own script, for the same reason the run's duration bound is the unit's rather than a `timeout` inside the script: a run killed from outside the process cannot report its own death, and that kill is precisely the case the bound exists for. It follows that a unit terminated on expiry of that bound SHALL report a failure.

The report SHALL NOT mutate what the unit manages. Installing or updating the reporting SHALL NOT itself perform the unit's work, on the same reasoning *Unreferenced Host Images Are Pruned on a Schedule* in this capability already gives for its own installation.

The address the report is sent to SHALL be delivered from an encrypted source and SHALL NOT be left world-readable on the host, per *Secrets Never Committed in Plaintext and Never Left World-Readable on Host* in this capability. It grants access to nothing, but a party who holds it can suppress the alarm by reporting success on the unit's behalf, which is the outcome this requirement exists to prevent.

The identifier the unit reports under SHALL be distinct from every other reporter's — every other unit's and every schedule-triggered workflow's — so that one silent reporter is distinguishable from another, and SHALL be recorded in the host-bootstrap documentation alongside the secret inventory.

Where the address is not supplied, the role SHALL fail naming it, before it changes anything on the host, per *A Role's Absent Required Input Is Reported by Name* in this capability. It SHALL NOT install the unit with reporting silently omitted: a scheduled unit that runs unobserved is the state this requirement exists to end, so an absent address is a misconfiguration rather than a mode of operation.

A report that could not be delivered SHALL be recorded in the host's own log. Where delivery failing is deliberately not allowed to fail the unit — so that a unit which did its work correctly is not recorded as having failed because a third party was briefly unreachable — the local record is the only trace the host keeps, and an operator answering the resulting silence days later otherwise finds a successful unit and no account of why nothing was reported.

The mechanism by which a report is delivered SHALL be verifiable without reaching the external observer, so that the obligations above can be asserted by this project's role-behaviour tests, which run with no credential and no network egress to a third party.

#### Scenario: A failed activation is reported as a failure
- **WHEN** a scheduled unit exits non-zero
- **THEN** a failure SHALL be reported to the external observer under that unit's own identifier

#### Scenario: A run killed by its own bound is reported
- **WHEN** a scheduled unit is terminated by the init system on expiry of its configured start timeout, producing no output of its own
- **THEN** a failure SHALL still be reported, because the report is emitted by the init system rather than by the terminated process

#### Scenario: A successful activation is reported
- **WHEN** a scheduled unit completes successfully
- **THEN** a success SHALL be reported, resetting the observer's silence timeout

#### Scenario: A timer that stops firing is detected
- **WHEN** a scheduled unit's timer stops activating it — because the timer was disabled, removed, or never re-enabled after a rebuild
- **THEN** no report SHALL arrive, and the external observer SHALL raise an alarm once the expected period and its tolerance have elapsed

#### Scenario: An undeliverable report leaves a local trace
- **WHEN** a unit completes and its report cannot be delivered to the external observer
- **THEN** the attempted endpoint and the delivery's outcome SHALL be written to the host's log, and the unit's own result SHALL be unaffected by the delivery having failed

#### Scenario: The report address is not world-readable on the host
- **WHEN** the role has converged
- **THEN** the on-host file carrying the report address SHALL be readable only by the account the unit runs as

#### Scenario: An absent report address is reported by name
- **WHEN** the role converges with no report address supplied
- **THEN** it SHALL fail naming that input, before changing anything on the host, and SHALL NOT install the unit with reporting omitted

#### Scenario: A report is observable without reaching the external observer
- **WHEN** the role's behaviour is exercised by this project's role-behaviour tests
- **THEN** the report SHALL be directable to a local destination, so that what a failing, a killed and a successful activation report can be asserted without a credential or a call to the third-party observer

#### Scenario: Installing the report does not activate the unit
- **WHEN** the role converges on a host where the unit is already installed
- **THEN** adding or updating the reporting SHALL NOT itself run the unit's work
