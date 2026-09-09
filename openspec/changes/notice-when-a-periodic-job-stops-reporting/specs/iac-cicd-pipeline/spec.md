## ADDED Requirements

### Requirement: Scheduled Workflows Report Their Own Liveness
Every workflow in this repository triggered by `schedule:` SHALL report the
outcome of each scheduled run to an **external** observer that raises an alarm
when the report does not arrive. Reporting a failure is not sufficient on its
own and SHALL NOT be treated as satisfying this requirement: the observer SHALL
alarm on **silence**, so that a run that failed, a run killed mid-flight, and a
run that never started at all are equally visible.

The second of those is the one no failure-triggered mechanism can reach. GitHub
disables schedule-triggered workflows after 60 days of repository inactivity —
the condition the *Scheduled Drift Detection* requirement in this capability
already names, and for which the README carries a manual re-enable procedure —
and a disabled workflow emits no failure, no run and no notification. A
mechanism that only reacts to red runs reports a disabled workflow as healthy
forever.

The observer SHALL NOT be a workflow in this repository. A watcher that is
itself schedule-triggered is subject to every failure mode it exists to detect,
and its own silence would be indistinguishable from the silence it is watching
for.

Each such workflow SHALL address its own report by an identifier that is a
**literal in the workflow file**, distinct per workflow, so that the obligation
is a static read of a committed file. That the repository's schedule-triggered
workflows each carry such a report SHALL be asserted by the executable suite
required by *The Continuous-Integration Configuration Is Itself Verified* in
this capability — a scheduled workflow added later without one is a pull request
that fails, not a gap discovered by a reader.

The credential that report is sent under SHALL be repository-scoped and SHALL
NOT be an Environment secret. Secrets on the `production` Environment are
readable only by a job that declares that Environment, and such a job waits on
required-reviewer approval per *Gated Production Apply Applies the Reviewed
Plan* in this capability. An alarm that waits for a human to approve its own
delivery is not an alarm.

The report SHALL be emitted from a job that runs whatever the outcome of the
rest of the workflow, and that depends on every other job in it. A report
emitted only on the success path leaves an early failure to be caught by the
observer's silence timeout, which is slower than the failure signal that was
available at the time.

A run that is **cancelled** SHALL report neither success nor failure. A
cancellation is an operator's act rather than a defect, and reporting it as
failure would train the alarm to be ignored; the observer's silence timeout
remains the backstop if cancellations continue.

Where these reports are delivered SHALL be configured separately from the
destination used by *External Dead-Man's-Switch Heartbeat*
(`openspec/specs/iac-platform-services/spec.md`). That destination is
deliberately out-of-band — it is the alarm for when the host and everything on
it is gone — and routing a weekly continuous-integration failure to it would
erode the one alarm that is supposed to be rare and unambiguous.

Because the observer is a third-party service, the configuration that decides
when silence becomes an alarm does not live in this repository and SHALL NOT be
presented as though it did. The identifier each workflow reports under, the
expected period and the tolerated delay SHALL be recorded in the host-bootstrap
documentation alongside the secret inventory, and SHALL be referenced from the
repository's runbook — one location holding the values and one pointing at it,
because two copies of a table nobody re-reads is how the second one comes to
disagree with the vendor. This is the same reasoning as the
credential-documentation obligation in *Automated
Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`): a
configuration whose only description lives in the change that introduced it
becomes undocumented the moment that change is archived.

The tolerated delay SHALL be set against GitHub's **observed** scheduling
behaviour rather than the declared cron expression. Scheduled runs in this
repository start hours after the minute their `cron:` names — a delay of over
four hours has been observed on a nightly schedule — so a tolerance derived from
the declared time alarms on a healthy system.

#### Scenario: A scheduled run that fails is reported as a failure
- **WHEN** a schedule-triggered workflow completes with a failed job
- **THEN** it SHALL report that failure to the external observer, without waiting for the observer's silence timeout to expire

#### Scenario: A workflow that stops running at all is detected
- **WHEN** a schedule-triggered workflow does not run at its expected time — because it was disabled after 60 days of repository inactivity, because its trigger was removed, or for any other reason
- **THEN** no report SHALL arrive, and the external observer SHALL raise an alarm once the expected period and its tolerance have elapsed

#### Scenario: A run in which a conditional job is skipped reports success
- **WHEN** a schedule-triggered workflow completes with no job having failed, but with one or more jobs skipped by their own conditions
- **THEN** it SHALL report success, because a skipped job is an ordinary outcome of a healthy run and an alarm that fires when nothing is wrong is an alarm that stops being read

#### Scenario: A failure in an early job is still reported
- **WHEN** a schedule-triggered workflow's first job fails and later jobs are skipped
- **THEN** the reporting job SHALL still run and SHALL report a failure

#### Scenario: A cancelled run raises no alarm of its own
- **WHEN** a scheduled run is cancelled
- **THEN** no failure SHALL be reported for that run

#### Scenario: A scheduled workflow added without a report fails the pull request
- **WHEN** a pull request adds a workflow triggered by `schedule:` that carries no liveness report, or removes the report from one that has it
- **THEN** the required status check SHALL fail on that pull request

#### Scenario: The report needs no human approval
- **WHEN** the reporting job runs
- **THEN** it SHALL read its credential from a repository-scoped secret and SHALL declare no deployment `environment:`, so that it is never queued behind a required-reviewer approval

#### Scenario: The routine alarm does not consume the last-resort one
- **WHEN** the external observer is configured for these reports
- **THEN** their alert destination SHALL be the routine alert destination, and SHALL NOT be the out-of-band destination the platform stack's dead-man's-switch heartbeat alerts to
