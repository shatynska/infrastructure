## Purpose

Defines the GitHub Actions workflow that validates and deploys `platform/`'s Compose stack — the mechanism `iac-platform-services` requires to exist outside Ansible's configuration-management scope.

## Requirements

### Requirement: Pull Request Validation Runs Without Deploy Credentials
Every pull request that changes `platform/**` SHALL trigger a GitHub Actions job that runs `docker compose config` against the changed Compose file to validate it renders and parses correctly. This job SHALL NOT declare a `production` (or equivalent) GitHub Environment and SHALL NOT have access to the deploy SSH credential.

The pull request's diff on the Compose YAML serves as the change under review — no computed "plan" step against the live host is produced or required.

This check SHALL be a required branch-protection status check on `main`, and SHALL therefore report a conclusion on every pull request — including one that touches no `platform/**` file — consistent with the Required Status Checks Report on Every Pull Request requirement in `iac-cicd-pipeline`. It SHALL be implemented as a path-filtered step inside that same always-running required check (e.g. an additional key in its existing internal path-filter step), not as a separate workflow gated by a workflow-level `paths:` trigger, since a workflow-level `paths:` trigger never reports for non-matching pull requests and would leave them permanently unmergeable.

#### Scenario: PR with invalid Compose syntax fails validation
- **WHEN** a pull request changes `platform/docker-compose.yml` in a way that fails to parse or resolve
- **THEN** the validation job SHALL fail and report the error on the pull request, without ever attempting to reach the host

#### Scenario: Validation requires no deploy secret
- **WHEN** the validation job runs on a pull request
- **THEN** it SHALL complete without reading the deploy SSH private key or any host-reachability secret

#### Scenario: Pull request touching no platform file remains mergeable
- **WHEN** a pull request changes no file under `platform/**`
- **THEN** the required status check SHALL still report success rather than remaining pending, and the pull request SHALL be mergeable

### Requirement: Gated Deploy Reuses the Terraform Production Environment
The deploy job SHALL run only after a pull request changing `platform/**` is merged to `main`, and SHALL require manual approval via the same `production` GitHub Environment protection rule already used by the Terraform apply workflow.

#### Scenario: Merge does not deploy immediately
- **WHEN** a pull request changing `platform/**` is merged to `main`
- **THEN** the deploy job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before connecting to the host

#### Scenario: Same approvers gate both kinds of production change
- **WHEN** either a Terraform apply or a platform-stack deploy is pending
- **THEN** both SHALL be gated by the same `production` Environment's required reviewers, rather than each defining its own separate approval list

### Requirement: Reviewer Sees the Exact Diff Before Approving
Before the `production` Environment approval gate is presented, a job running under no `environment:` (and therefore with no access to the deploy credential) SHALL compute the diff this merge introduces under `platform/**` and write it to the workflow run's job summary, mirroring the Pull Request Plan Visibility requirement in `iac-cicd-pipeline`. This SHALL hold regardless of whether any reviewing approval was required or given on the originating pull request — the guarantee this requirement establishes is that the `production` Environment's required reviewer sees the exact content about to be deployed at the moment they are asked to approve it, not that some review occurred earlier.

#### Scenario: Approver sees the diff without leaving the workflow run
- **WHEN** the deploy workflow run reaches the pending-approval state
- **THEN** the run's job summary SHALL already display the full diff this merge introduces under `platform/**`, computed by a job that ran before the approval gate and without the deploy credential

#### Scenario: Diff visibility does not depend on pull request review having occurred
- **WHEN** a pull request changing `platform/**` was merged without any human's approving review (only the automated validation check passing)
- **THEN** the `production` Environment's required reviewer SHALL still see the exact diff at approval time, independent of whatever review, if any, happened on the pull request itself

### Requirement: Deploy Job Reaches the Host Over a Private Tailnet
The deploy job SHALL join the same private tailnet the host is a member of (via an ephemeral, tagged node authenticated by a Tailscale OAuth client) before attempting any SSH connection to the host, and SHALL connect to the host's tailnet address rather than a publicly-routable one reachable outside the tailnet.

#### Scenario: Deploy job joins the tailnet before SSH
- **WHEN** the deploy job runs
- **THEN** it SHALL establish tailnet connectivity before its first SSH attempt, and that attempt SHALL succeed only if the host is reachable over the tailnet

#### Scenario: Tailnet join credential is confined to the gated job
- **WHEN** the deploy workflow run is pending `production` Environment approval
- **THEN** the Tailscale OAuth client secret SHALL NOT be readable by any job that has not passed that environment's approval gate, consistent with the existing Deploy Credential Confined to the Gated Job requirement

### Requirement: Deploy Credential Confined to the Gated Job
The deploy SSH private key SHALL be stored as a secret scoped to the `production` GitHub Environment and SHALL NOT be readable by any job that has not passed that environment's approval gate.

#### Scenario: Deploy key is inaccessible before approval
- **WHEN** the deploy workflow run is pending `production` Environment approval
- **THEN** the deploy SSH private key SHALL NOT be readable by the pending job

### Requirement: Platform Secrets Rendered from CI at Deploy Time
The `.env` file consumed by `platform/docker-compose.yml` SHALL be rendered from GitHub Actions secrets by the deploy job at deploy time and transferred to the host alongside the Compose file. It SHALL NOT be committed to the repository in any form, plaintext or encrypted.

#### Scenario: Rendered .env never enters version control
- **WHEN** the deploy job renders `.env` from GitHub Actions secrets
- **THEN** the rendered file SHALL exist only in the workflow run's ephemeral workspace and on the host, and SHALL NOT be committed to the repository

#### Scenario: Deploy job authenticates as the provisioned deploy account
- **WHEN** the deploy job connects to the host
- **THEN** it SHALL authenticate as the restricted `deploy` account provisioned by the host-configuration change, not as any operator's personal account

### Requirement: Serialized Deploys
The deploy job SHALL run under a GitHub Actions `concurrency` group so that two merges in quick succession queue rather than run concurrently or cancel each other.

#### Scenario: Two merges in quick succession deploy in order
- **WHEN** two pull requests changing `platform/**` are merged within a short interval
- **THEN** the second deploy run SHALL queue until the first completes, and SHALL NOT run concurrently with it

### Requirement: Deploy Fails When Any Healthchecked Service Does Not Become Healthy
The deploy job SHALL fail, rather than report success, when any service that defines a Docker healthcheck does not reach a healthy state within the deploy's wait for service startup. This SHALL hold regardless of which such service fails to become healthy or why.

A service with no Docker healthcheck defined is only guaranteed to be waited on until it reaches a `running` state at least transiently — this does NOT reliably detect a service that starts, crashes, and is automatically restarted (for example, under a `restart: unless-stopped` policy), since such a service can satisfy a "reached running" check during the brief window between restarts while genuinely crash-looping. This requirement does not claim otherwise. As of this requirement's adoption, every service in the shared platform stack defines a real healthcheck (`iac-platform-services`'s corresponding requirement), so this limitation is not currently exercised by any service in the stack — it is stated here so a future service added without a healthcheck is not mistakenly assumed to be safely covered by the deploy job's wait.

#### Scenario: A crash-looping healthchecked service fails the deploy
- **WHEN** a service with a defined healthcheck is deployed but repeatedly fails that healthcheck (for example, crash-looping on startup)
- **THEN** the deploy job SHALL fail and report a non-zero result, rather than completing successfully with that service left unhealthy

#### Scenario: A service with no healthcheck that never starts running still fails the deploy
- **WHEN** a service with no defined healthcheck fails to reach a running state at all (not even transiently)
- **THEN** the deploy job SHALL fail and report a non-zero result

#### Scenario: A service with no healthcheck that crash-loops is not guaranteed to fail the deploy
- **WHEN** a service with no defined healthcheck starts, crashes, and is automatically restarted, reaching a `running` state at least transiently on each cycle
- **THEN** the deploy job is NOT guaranteed to fail on account of that service, even though it is not genuinely healthy

#### Scenario: A fully healthy deploy succeeds
- **WHEN** every service that defines a healthcheck reaches a healthy state, and every service that does not reaches a running state, within the deploy's wait
- **THEN** the deploy job SHALL report success

### Requirement: A Shipped Configuration Change Is Visible to the Container Runtime
The shared platform stack embeds its monitoring, alerting and dashboard
configuration inside the stack definition itself rather than in separate files —
a choice recorded, with its reason, under "Splitting
`platform/docker-compose.yml` into multiple files" in `docs/deferred-work.md` —
and the runtime copies that configuration into each container when the container
is created. A service's embedded configuration therefore changes only when its
container is replaced.

Where the runtime decides whether to replace a container by comparing a digest
of the service definition, and that digest does not cover embedded configuration
content, the stack definition SHALL carry — for each service that mounts
embedded configuration — a property the digest does cover, whose value changes
whenever that service's own embedded configuration changes and does not change
when any other service's does.

Satisfying this by replacing every service on every deploy SHALL NOT be used,
because it would replace stateful services whose configuration did not change.

"Embedded configuration" here means the configuration **as committed**. Where a
value inside it is interpolated at deploy time from outside the repository — a
secret rendered into the deploy environment, say — this requirement does not
reach it: the committed text is unchanged when such a value is rotated, so no
property derived from the committed text can move. Changing a secret that an
embedded configuration interpolates therefore does NOT cause the service to be
replaced, and the running container keeps the previous value until something
else replaces it.

**What this requirement establishes, and what it does not.** It makes a
change to the committed configuration visible to the comparison that decides
replacement, which is what was absent. It does NOT establish that a deploy
reporting success has applied everything it shipped: a container can fail to be
replaced for reasons no property of the definition can express, an interpolated
value can change with no committed text moving, and nothing here compares a
running container against the definition after the deploy. That confirmation is
a strictly wider guarantee, it is not implied by this requirement, and it is not
to be read as discharged by it.

#### Scenario: A configuration-only change reaches the running service
- **WHEN** a deploy ships a change confined to a service's embedded configuration and to the property this requirement obliges, with no change to that service's image or runtime properties
- **THEN** that service's definition SHALL differ from the one its running container carries, so that the runtime replaces the container rather than leaving it in place

#### Scenario: Only the service whose configuration changed is replaced
- **WHEN** a deploy ships a change to one service's embedded configuration
- **THEN** every other service SHALL be left in place, including other services that also mount embedded configuration, because each service's property is a function of its own configuration alone

#### Scenario: A stale marker fails before it reaches a deploy
- **WHEN** embedded configuration is edited and the property this requirement obliges is maintained in the stack definition rather than computed at deploy time, and that property is not updated to match
- **THEN** that discrepancy SHALL fail a check that blocks the pull request, rather than being discovered as a deploy that reports success and changes nothing
