## MODIFIED Requirements

### Requirement: Gated Production Apply Applies the Reviewed Plan
`terraform apply` against a stack SHALL run only after a pull request is merged to `main`, SHALL attach to that stack's own GitHub Environment, and SHALL apply a **saved plan file produced before that Environment's protection rules were satisfied** rather than recomputing a plan afterwards.

Every stack's apply job SHALL declare an `environment:`. Whether that pauses for a human is a property of the GitHub Environment's protection rules — repository settings, which no file in this repository can verify — and not of the workflow. The `main-production` Environment SHALL require a reviewer. A stack whose Environment requires no reviewer is still gated in the sense this requirement means: its write credential remains confined to that job, per Credential Scoping by Privilege.

The apply workflow SHALL be structured as two jobs per stack in a single run:

1. A **plan job** that declares no `environment:`, runs `terraform plan -out=tfplan`, writes the human-readable plan to the run's job summary, and uploads `tfplan` as a workflow artifact.
2. An **apply job** that depends on the plan job, declares that stack's `environment:`, and on satisfaction of its protection rules downloads `tfplan` and runs `terraform apply tfplan`.

This ensures the approving reviewer sees the exact diff that will be applied. A workflow that approves first and plans afterwards gives the reviewer no diff to evaluate, and the plan computed after approval may differ from the one reviewed on the pull request due to the merge commit, intervening drift, or a provider version change.

**A stack SHALL be applied only where its own plan was produced, and a stack whose plan failed SHALL NOT prevent any other stack from being applied.** These are one obligation because a single mechanism decides both, and the two failures it stands between are opposite: an apply stage that begins for a stack with no saved plan raises that stack's approval request with nothing to approve, which this requirement forbids by name; an apply stage that waits on the plan stage as a whole stops every stack when any one of them fails, so a correct change does not reach production because an unrelated stack is broken.

Declaring the apply stage dependent on the plan stage is therefore **not sufficient**, and the reason is mechanical rather than stylistic: such a dependency is scoped to the stage, not to the stack, so it cannot distinguish *this* stack's plan from another's. The set of stacks to apply SHALL instead be resolved from which stacks actually produced a saved plan.

**A stack counts as having produced a saved plan only where every check its plan job performs has passed.** The saved plan's *existence* is not that fact and SHALL NOT be substituted for it: the Destroy Policy Gate runs inside the plan job and after the plan exists, so a plan the gate refused is a plan that was produced and must not be applied. Reading existence alone would leave the gate defeated for exactly the plans it exists to stop, behind an approval it exists because it does not trust. Where the resolution is made by observing an artifact, the artifact SHALL therefore be published only after every such check has passed, and unconditionally on their having passed — never on the plan job having merely reached that point.

That resolution SHALL run outside any GitHub Environment, since it decides which Environments the run will ask for and so cannot be gated on one of them.

It SHALL fail closed in the same sense the affected-stack resolution above does, and with the same distinction: where the set can be neither read as a valid set nor read as an explicit empty one, the workflow SHALL fail with a message identifying that resolution as the cause. An **explicitly empty** planned set is not that case and SHALL NOT fail the run — a merge matching this workflow's path filter while affecting no stack reaches the apply stage with nothing to apply, and that is the correct outcome rather than an error.

The apply stage SHALL NOT reach its conclusion through the plan stage's aggregate result. A dependency whose outcome propagates the plan stage's result reinstates exactly the coupling this obligation removes, and does so while every other part of the mechanism appears correct — the resolution runs, the set is right, and the apply stage is skipped anyway.

The apply workflow SHALL be triggered only by pushes that can affect the Terraform configuration, identified by a workflow-level path filter. **A stack SHALL enter the run only where the merge could affect that stack**, determined by the same path rule the Pull Request Plan Visibility requirement states: a change under `terraform/modules/` affects every stack, a change under `terraform/stacks/<name>/` affects only that stack. A merge that cannot change a stack's infrastructure SHALL NOT raise that stack's Environment approval request. An approval prompt that appears with nothing to approve trains the approver to grant it without reading, which defeats the gate it exists to enforce; out-of-band divergence remains covered by scheduled drift detection rather than by an approval request per merge.

The set of affected stacks SHALL be resolved fail-closed, and this workflow runs on `push`, where no pull-request diff is available and the base of the comparison may be absent — a first push to a branch, a force-push, or a merge whose `before` commit no longer resolves. Where that set cannot be determined, the workflow SHALL fail with a message identifying the resolution as the cause. Resolving it to the empty set instead would apply nothing for a merge that did change infrastructure, report a green run, and leave the divergence to be found by the next nightly drift sweep.

This path filter is permissible **only** because the apply workflow is not a required status check. Any workflow that is registered as a required check SHALL NOT be path-filtered at the workflow level — see the Required Status Checks Report on Every Pull Request requirement, whose constraint is the opposite of this one and takes precedence for those workflows. There is more than one such workflow, and the constraint holds of each.

Because a saved plan file stores sensitive values in cleartext, the `tfplan` artifact SHALL be treated as a secret: retention SHALL be set to the shortest workable period, the artifact SHALL be named per stack so that one stack's plan cannot be applied to another, and the artifact SHALL NOT be produced in a public repository without symmetric encryption using a key held in repository secrets.

#### Scenario: Merge does not apply immediately
- **WHEN** a pull request changing `terraform/stacks/main-production/` is merged to `main`
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `main-production` GitHub Environment before running `terraform apply`

#### Scenario: A merge affecting one environment raises no other environment's approval
- **WHEN** a pull request changing only `terraform/stacks/main-staging/` is merged to `main`
- **THEN** no `main-production` Environment approval SHALL be requested, and the `main-production` stack SHALL NOT be planned or applied by that run

#### Scenario: A shared module change reaches every environment
- **WHEN** a pull request changing a file under `terraform/modules/` is merged to `main`
- **THEN** each stack SHALL be planned and applied under its own GitHub Environment's protection rules

#### Scenario: A plan its own gate refused is not applied
- **WHEN** a stack's plan job produces a plan and then fails one of that job's own checks, such as the Destroy Policy Gate
- **THEN** that stack SHALL NOT be applied and SHALL NOT raise its Environment's approval request, because a plan that exists is not thereby a plan that passed

#### Scenario: One environment's failed plan does not block another's apply
- **WHEN** a merge affects two stacks and one of them fails to plan
- **THEN** the other stack SHALL still be applied under its own GitHub Environment's protection rules, and no approval SHALL be requested for the stack whose plan failed

#### Scenario: An unresolvable set of planned environments fails the run
- **WHEN** which stacks produced a saved plan cannot be determined
- **THEN** the workflow SHALL fail with a message identifying that resolution as the cause, and SHALL NOT proceed as though no stack had been planned

#### Scenario: Reviewer sees the exact diff before approving
- **WHEN** an apply job is pending approval
- **THEN** the completed plan job's summary SHALL already display the full plan output for the merge commit and identify which stack it belongs to, so the reviewer can read the pending changes before granting approval

#### Scenario: Applied changes match the approved plan
- **WHEN** approval is granted and the apply job runs
- **THEN** it SHALL apply the saved `tfplan` artifact produced by the plan job for that same stack, and SHALL error rather than apply divergent changes if remote state has changed since that plan was saved

#### Scenario: Apply credentials are inaccessible before approval
- **WHEN** an apply workflow run is pending approval
- **THEN** the read-write `HCLOUD_TOKEN` scoped to that stack's GitHub Environment SHALL NOT be readable by the workflow job until approval is granted

#### Scenario: An unresolvable set of affected environments fails the run
- **WHEN** a merge's set of affected stacks cannot be determined, because the resolution step did not conclude or produced a value that is neither a valid set nor an explicit empty one
- **THEN** the workflow SHALL fail with a message identifying that resolution as the cause, and SHALL NOT proceed as though no stack were affected

#### Scenario: A merge that cannot change infrastructure raises no approval request
- **WHEN** a pull request changing only documentation, Ansible or platform files is merged to `main`
- **THEN** the apply workflow SHALL NOT run, and no Environment approval SHALL be requested

### Requirement: Scheduled Workflows Report Their Own Liveness
Every workflow in this repository triggered by `schedule:` SHALL report the outcome of each scheduled run to an **external** observer that raises an alarm when the report does not arrive. Reporting a failure is not sufficient on its own and SHALL NOT be treated as satisfying this requirement: the observer SHALL alarm on **silence**, so that a run that failed, a run killed mid-flight, and a run that never started at all are equally visible.

The second of those is the one no failure-triggered mechanism can reach. GitHub disables schedule-triggered workflows after 60 days of repository inactivity — the condition the *Scheduled Drift Detection* requirement in this capability already names, and for which the README carries a manual re-enable procedure — and a disabled workflow emits no failure, no run and no notification. A mechanism that only reacts to red runs reports a disabled workflow as healthy forever.

The observer SHALL NOT be a workflow in this repository. A watcher that is itself schedule-triggered is subject to every failure mode it exists to detect, and its own silence would be indistinguishable from the silence it is watching for.

Each such workflow SHALL address its own report by an identifier that is a **literal in the workflow file**, distinct per workflow, so that the obligation is a static read of a committed file. That the repository's schedule-triggered workflows each carry such a report SHALL be asserted by the executable suite required by *The Continuous-Integration Configuration Is Itself Verified* in this capability — a scheduled workflow added later without one is a pull request that fails, not a gap discovered by a reader.

The credential that report is sent under SHALL be repository-scoped and SHALL NOT be an Environment secret. Secrets on the `main-production` Environment are readable only by a job that declares that Environment, and such a job waits on required-reviewer approval per *Gated Production Apply Applies the Reviewed Plan* in this capability. An alarm that waits for a human to approve its own delivery is not an alarm.

The report SHALL be emitted from a job that runs whatever the outcome of the rest of the workflow, and that depends on every other job in it. A report emitted only on the success path leaves an early failure to be caught by the observer's silence timeout, which is slower than the failure signal that was available at the time.

A run that is **cancelled** SHALL report neither success nor failure. A cancellation is an operator's act rather than a defect, and reporting it as failure would train the alarm to be ignored; the observer's silence timeout remains the backstop if cancellations continue.

Where these reports are delivered SHALL be configured separately from the destination used by *External Dead-Man's-Switch Heartbeat* (`openspec/specs/iac-platform-services/spec.md`). That destination is deliberately out-of-band — it is the alarm for when the host and everything on it is gone — and routing a weekly continuous-integration failure to it would erode the one alarm that is supposed to be rare and unambiguous.

Because the observer is a third-party service, the configuration that decides when silence becomes an alarm does not live in this repository and SHALL NOT be presented as though it did. The identifier each workflow reports under, the expected period and the tolerated delay SHALL be recorded in the host-bootstrap documentation alongside the secret inventory, and SHALL be referenced from the repository's runbook — one location holding the values and one pointing at it, because two copies of a table nobody re-reads is how the second one comes to disagree with the vendor. This is the same reasoning as the credential-documentation obligation in *Automated Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`): a configuration whose only description lives in the change that introduced it becomes undocumented the moment that change is archived.

The tolerated delay SHALL be set against GitHub's **observed** scheduling behaviour rather than the declared cron expression. Scheduled runs in this repository start hours after the minute their `cron:` names — a delay of over four hours has been observed on a nightly schedule — so a tolerance derived from the declared time alarms on a healthy system.

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
