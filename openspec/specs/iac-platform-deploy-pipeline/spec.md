## Purpose

Defines the GitHub Actions workflow that validates and deploys `platform/`'s Compose stack — the mechanism `iac-platform-services` requires to exist outside Ansible's configuration-management scope.

## Requirements

### Requirement: Pull Request Validation Runs Without Deploy Credentials
Every pull request that changes `platform/**` SHALL trigger a GitHub Actions job that runs `docker compose config` against the changed Compose file to validate it renders and parses correctly. This job SHALL NOT declare a `main-production` (or equivalent) GitHub Environment and SHALL NOT have access to the deploy SSH credential.

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

### Requirement: Reviewer Sees the Exact Diff Before Approving
Before any GitHub Environment approval gate is presented, a job running under no `environment:` (and therefore with no access to any deploy credential) SHALL compute the diff this merge introduces under `platform/**` and write it to the workflow run's job summary, mirroring the Pull Request Plan Visibility requirement in `iac-cicd-pipeline`. This SHALL hold regardless of whether any reviewing approval was required or given on the originating pull request — the guarantee this requirement establishes is that a reviewed Environment's required reviewer sees the exact content about to be deployed at the moment they are asked to approve it, not that some review occurred earlier.

One such job SHALL serve every stack the merge deploys to. The content deployed is the same for each — the committed stack definition, whose per-stack values arrive at deploy time from that stack's own Environment and are therefore in no diff — so a summary computed once is the exact content each approver is asked to approve, and a job per stack would publish the same diff several times while multiplying the number of jobs that run before the gate.

#### Scenario: Approver sees the diff without leaving the workflow run
- **WHEN** the deploy workflow run reaches a pending-approval state for any stack
- **THEN** the run's job summary SHALL already display the full diff this merge introduces under `platform/**`, computed by a job that ran before the approval gate and without any deploy credential

#### Scenario: Diff visibility does not depend on pull request review having occurred
- **WHEN** a pull request changing `platform/**` was merged without any human's approving review (only the automated validation check passing)
- **THEN** a reviewed Environment's required reviewer SHALL still see the exact diff at approval time, independent of whatever review, if any, happened on the pull request itself

### Requirement: Deploy Job Reaches the Host Over a Private Tailnet
Each stack's deploy job SHALL join the same private tailnet that stack's host is a member of (via an ephemeral, tagged node authenticated by a Tailscale OAuth client) before attempting any SSH connection to that host, and SHALL connect to the host's tailnet address rather than a publicly-routable one reachable outside the tailnet.

#### Scenario: Deploy job joins the tailnet before SSH
- **WHEN** a stack's deploy job runs
- **THEN** it SHALL establish tailnet connectivity before its first SSH attempt, and that attempt SHALL succeed only if that stack's host is reachable over the tailnet

#### Scenario: Tailnet join credential is confined to the gated job
- **WHEN** a stack's deploy workflow run is pending that stack's GitHub Environment approval
- **THEN** the Tailscale OAuth client secret SHALL NOT be readable by any job that has not passed that environment's approval gate, consistent with the existing Deploy Credential Confined to the Gated Job requirement

### Requirement: Deploy Credential Confined to the Gated Job
Each stack's deploy SSH private key SHALL be stored as a secret scoped to **that stack's** declared GitHub Environment, and SHALL NOT be readable by any job that has not attached to that Environment. The discovery and diff jobs declare no `environment:` and SHALL therefore be unable to read any stack's key.

"Gated" here names the attachment, not the pause. Confinement to an Environment holds whether or not that Environment requires a reviewer: an ungated stack's key is still unreadable by every job that has not attached to its Environment, and is still unreadable by a job attached to a *different* stack's Environment. Where the Environment does require a reviewer, confinement additionally means the key is unreadable until that approval is given.

One stack's key SHALL NOT be able to deploy to another stack's host. Each stack's key is a keypair of its own, whose public half that host authorises and no other host does.

#### Scenario: Deploy key is inaccessible before approval
- **WHEN** a stack's deploy workflow run is pending that stack's GitHub Environment approval
- **THEN** that stack's deploy SSH private key SHALL NOT be readable by the pending job

#### Scenario: A job attached to no Environment can read no stack's key
- **WHEN** the discovery or diff job runs
- **THEN** it SHALL be unable to read any stack's deploy SSH private key, having attached to no GitHub Environment

#### Scenario: One stack's key does not reach another stack's host
- **WHEN** a stack's deploy key is compromised
- **THEN** it SHALL authorise a deploy to that stack's host alone, every other stack's host authorising a different key

### Requirement: Platform Secrets Rendered from CI at Deploy Time
The `.env` file consumed by `platform/docker-compose.yml` SHALL be rendered from GitHub Actions secrets by the deploy job at deploy time and transferred to the host alongside the Compose file. It SHALL NOT be committed to the repository in any form, plaintext or encrypted.

Each stack SHALL have a complete set of values of its own, held in its own GitHub Environment: its own host, its own database credentials, its own dashboard credential, its own certificate-registration address, and its own alert-delivery targets. A value SHALL NOT be shared between stacks by being held as a repository secret of the same name, since a repository secret holds one value and every stack reading it would render the same value into `.env` — a shared database password or a single alert target reached by two hosts.

Where a stack's alerts are delivered to a destination shared with another stack's, the running stack definition carries nothing identifying which host an alert came from, so the delivery target is what distinguishes them. Each stack's alert-delivery secret SHOULD therefore address a destination of its own. This is a property of the values an operator enters into an Environment; nothing in the repository can verify it.

#### Scenario: Rendered .env never enters version control
- **WHEN** a deploy job renders `.env` from GitHub Actions secrets
- **THEN** the rendered file SHALL exist only in the workflow run's ephemeral workspace and on the host, and SHALL NOT be committed to the repository

#### Scenario: Deploy job authenticates as the provisioned deploy account
- **WHEN** a stack's deploy job connects to that stack's host
- **THEN** it SHALL authenticate as the restricted `deploy` account provisioned by the host-configuration change, not as any operator's personal account

#### Scenario: Two stacks render two different sets of values
- **WHEN** a merge deploys to two stacks
- **THEN** each stack's `.env` SHALL be rendered from that stack's own GitHub Environment's secrets, so that neither host receives the other's database credential, dashboard credential or alert targets

### Requirement: Serialized Deploys
Each stack's deploy job SHALL run under a GitHub Actions `concurrency` group naming that stack, so that two merges in quick succession queue rather than run concurrently or cancel each other against one host.

The group SHALL name the stack rather than being shared across stacks. What it protects is the deploy state on one host, which two stacks do not share; a group shared across stacks would serialise deploys that contend for nothing and would make one stack's pending approval hold another stack's deploy in a queue — which is the promotion ordering *Each Stack's Deploy Attaches to the Environment Its Own Declaration Names* forbids, reached by a route that declares no dependency.

#### Scenario: Two merges in quick succession deploy in order
- **WHEN** two pull requests changing `platform/**` are merged within a short interval
- **THEN** the second deploy run SHALL queue, for each stack, until the first completes for that stack, and SHALL NOT run concurrently with it against the same host

#### Scenario: One stack's queued deploy does not hold another's
- **WHEN** a deploy to one stack is queued or awaiting approval
- **THEN** a deploy to a different stack SHALL proceed, the two being serialised independently

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
The shared platform stack embeds its monitoring, alerting and dashboard configuration inside the stack definition itself rather than in separate files — a choice made to keep the deploy-receive script's fixed two-member extraction list narrow, recorded with its reason at that list in `ansible/roles/deploy_user/tasks/main.yml` — and the runtime copies that configuration into each container when the container is created. A service's embedded configuration therefore changes only when its container is replaced.

Where the runtime decides whether to replace a container by comparing a digest of the service definition, and that digest does not cover embedded configuration content, the stack definition SHALL carry — for each service that mounts embedded configuration — a property the digest does cover, whose value changes whenever that service's own embedded configuration changes and does not change when any other service's does.

Satisfying this by replacing every service on every deploy SHALL NOT be used, because it would replace stateful services whose configuration did not change.

"Embedded configuration" here means the configuration **as committed**. Where a value inside it is interpolated at deploy time from outside the repository — a secret rendered into the deploy environment, say — this requirement does not reach it: the committed text is unchanged when such a value is rotated, so no property derived from the committed text can move. Changing a secret that an embedded configuration interpolates therefore does NOT cause the service to be replaced, and the running container keeps the previous value until something else replaces it.

**What this requirement establishes, and what it does not.** It makes a change to the committed configuration visible to the comparison that decides replacement, which is what was absent. It does NOT establish that a deploy reporting success has applied everything it shipped: a container can fail to be replaced for reasons no property of the definition can express, an interpolated value can change with no committed text moving, and nothing here compares a running container against the definition after the deploy. That confirmation is a strictly wider guarantee, it is not implied by this requirement, and it is not to be read as discharged by it.

#### Scenario: A configuration-only change reaches the running service
- **WHEN** a deploy ships a change confined to a service's embedded configuration and to the property this requirement obliges, with no change to that service's image or runtime properties
- **THEN** that service's definition SHALL differ from the one its running container carries, so that the runtime replaces the container rather than leaving it in place

#### Scenario: Only the service whose configuration changed is replaced
- **WHEN** a deploy ships a change to one service's embedded configuration
- **THEN** every other service SHALL be left in place, including other services that also mount embedded configuration, because each service's property is a function of its own configuration alone

#### Scenario: A stale marker fails before it reaches a deploy
- **WHEN** embedded configuration is edited and the property this requirement obliges is maintained in the stack definition rather than computed at deploy time, and that property is not updated to match
- **THEN** that discrepancy SHALL fail a check that blocks the pull request, rather than being discovered as a deploy that reports success and changes nothing

### Requirement: Each Stack's Deploy Attaches to the Environment Its Own Declaration Names
The shared platform stack SHALL be deployed to every stack whose own committed pipeline declaration opts in, and to no other. Each such stack SHALL be deployed by a job of its own, attached to the GitHub Environment **that stack's** declaration names — the same Environment that stack's Terraform apply and host converge attach to.

Whether a deploy pauses for a human is therefore a property of that Environment's protection rules, which are repository settings, and not of the workflow. A stack whose Environment requires a reviewer deploys only after that reviewer approves; a stack whose Environment requires none deploys on merge. Both are the same mechanism under different settings, and the workflow SHALL NOT distinguish them — a condition in workflow text that treated one stack's deploy differently from another's would be the stack-naming this capability forbids, and would put the approval decision somewhere no repository setting can reach.

One Environment gating both kinds of change to a stack is what this requirement preserves from the production-only requirement it replaces: the approvers who gate a stack's Terraform apply are the approvers who gate its platform deploy, rather than each mechanism defining an approval list of its own.

Each such GitHub Environment is named for the **stack** rather than for the environment axis, per `docs/naming-conventions.md`. That is carried forward from the requirement this one replaces, and it matters more now than it did there: while one deploy attached to one Environment, a name on the wrong axis was untidy; with a deploy row per stack, two stacks of one environment would collide on an environment-axis name and share the write token and protection rules of whichever created it first.

Deploying to two stacks SHALL NOT impose an order on them. No stack's deploy SHALL be made to depend on another stack's deploy, whether by a dependency edge between them, by cancelling sibling deploys when one fails, or by running them one at a time. Promotion ordering is exercised at a reviewed Environment's approval — by an approver free to withhold it until a lower stack has been seen to work — and not by the workflow, for the reason *Stack and Module Folder Structure* (`openspec/specs/iac-repo-foundations/spec.md`) gives for the Terraform apply: a workflow that sequences them also withholds a correct change from one stack because another stack broke.

#### Scenario: A merge does not deploy to a reviewed stack immediately
- **WHEN** a pull request changing `platform/**` is merged to `main`
- **THEN** the deploy job for a stack whose declared GitHub Environment requires a reviewer SHALL pause and wait for that approval before connecting to that stack's host

#### Scenario: Same approvers gate both kinds of change to one stack
- **WHEN** either a Terraform apply or a platform-stack deploy is pending for a given stack
- **THEN** both SHALL be gated by that stack's own declared GitHub Environment and its required reviewers, rather than each defining a separate approval list

#### Scenario: An unreviewed stack deploys without an approval prompt
- **WHEN** a pull request changing `platform/**` is merged and a stack whose declared GitHub Environment requires no reviewer has opted in
- **THEN** that stack's deploy SHALL proceed without waiting for approval, by that Environment's protection rules and not by any condition in the workflow

#### Scenario: One stack's failed deploy does not withhold another's
- **WHEN** a merge deploys to two stacks and the deploy to one of them fails
- **THEN** the other stack's deploy SHALL still run and SHALL NOT be cancelled, sequenced behind it, or made to depend on its outcome

### Requirement: The Platform Deploy Names No Stack
The workflow that deploys the shared platform stack SHALL NOT enumerate stacks, name one in a condition, or map one to its secrets or to its GitHub Environment in workflow text. Which stacks receive the stack, and which GitHub Environment each one's deploy attaches to, SHALL be discovered by reading the committed per-stack pipeline declarations that *Each Stack Declares Its Own Pipeline Configuration* (`openspec/specs/iac-cicd-pipeline/spec.md`) obliges.

The per-stack secrets this deploy reads SHALL be reached by their own fixed names, resolved against the Environment each deploy job attaches to, rather than by any name derived from or mapped to the stack. A stack's values are distinguished by which Environment holds them and by nothing in the workflow.

Discovery SHALL fail closed and SHALL report what it found. A declaration that is absent, unparseable, or carries a malformed value for a field this workflow reads SHALL fail the workflow with a message naming the stack and the field. Where no stack opts in, the workflow SHALL fail rather than report success over an empty matrix: a shared platform stack deployed to nowhere is a pipeline reporting green over nothing, which is the condition the sibling discoveries in this repository each refuse. A stack that has not opted in is not such a case — it is excluded by its own declaration, is named as excluded in the run's output, and continues to be planned, applied, drift-checked and converged by the workflows that do not read this field.

#### Scenario: A stack opting in needs no workflow edit
- **WHEN** a stack's committed pipeline declaration opts that stack in to the platform deploy
- **THEN** the next merge changing `platform/**` SHALL deploy to it, with no change to any file under `.github/workflows/`

#### Scenario: A stack that has not opted in is excluded and named
- **WHEN** a merge changing `platform/**` is deployed and a discovered stack's declaration does not opt in
- **THEN** no deploy job SHALL run for that stack, and the run SHALL report that stack as excluded rather than omitting it silently

#### Scenario: No stack opting in fails the workflow
- **WHEN** discovery finds no stack whose declaration opts in to the platform deploy
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow the deploy job to be skipped and the run reported as successful

#### Scenario: A deploy requested for an unknown stack is refused
- **WHEN** a deploy is requested by hand for a stack name discovery did not find
- **THEN** the run SHALL fail, naming the requested stack and reporting the stacks discovery did find, rather than producing an empty matrix and reporting success

### Requirement: An Incomplete Per-Stack Secret Set Is Reported by Name
Before joining the tailnet, rendering any file or attempting any connection, each stack's deploy job SHALL establish that every secret **whose absence would not by itself stop the deploy** resolved to a value — the secret naming that stack's host, the deploy key it authenticates with, and each value rendered into the `.env` the stack definition reads that comes from a secret (the tailnet bind address is derived at deploy time, is behind no secret, and is resolved after this obligation is discharged) — and SHALL fail where any did not, naming the stack, the GitHub Environment the values should have come from, and each name that resolved empty. It SHALL NOT emit any value in doing so.

**The scope is that class and not "every secret the job reads"**, and the difference is what this requirement is for rather than a narrowing of it. A credential that an absent value makes unusable — the tailnet OAuth client, say — already fails the step that consumes it, before anything is written, which is the guarantee this requirement exists to supply elsewhere. Restating it here would add no protection, and would make this step indistinguishable from the join it is obliged to precede.

A GitHub Actions secret that is not defined resolves to an empty string rather than to an error, and the two halves of the set fail differently. An empty host reaches the tailnet-reachability check and the SSH connection as an empty argument, and both fail in terms that name neither the stack nor the missing secret — late, and with a cause that has to be inferred.

An empty rendered value is worse, because it need not fail at all. The stack definition interpolates each one with no error-if-unset form, so an absent secret renders an empty assignment, and a service that tolerates an empty value starts, satisfies the deploy's wait for health, and leaves the run green. Where that value is a credential the service would otherwise require, the deploy has reported success while violating a requirement of the stack it deployed — *Metrics Dashboards Are Available* (`openspec/specs/iac-platform-services/spec.md`), which obliges a non-default credential, is the live case. A deploy SHALL NOT be able to reach that state by way of an absent secret.

The obligation is discharged before anything is written or connected to, rather than by checking afterwards: a partially entered secret set is the expected first error when a stack's Environment is populated by hand for the first time, and the refusal is what makes it a named failure instead of a silent one.

#### Scenario: A stack opted in before its secrets exist fails by name
- **WHEN** a stack's declaration opts it in to the platform deploy and its GitHub Environment defines none of that deploy's secrets
- **THEN** that stack's deploy job SHALL fail before joining the tailnet, with a message naming the stack and the Environment, rather than failing at a connection attempt against an empty address

#### Scenario: A partially entered secret set fails rather than deploying
- **WHEN** a stack's GitHub Environment defines the secret naming its host but omits one of the values rendered into `.env`
- **THEN** that stack's deploy job SHALL fail before rendering that file, naming the omitted secret, rather than deploying a stack whose service received an empty value

#### Scenario: An absent credential secret fails the deploy rather than starting the service
- **WHEN** the secret holding a service's administrative credential resolves to nothing, and that service would start and satisfy the deploy's wait for health with an empty value
- **THEN** the deploy SHALL fail before rendering it, rather than reporting success over a service the healthcheck cannot distinguish from a correctly configured one

#### Scenario: The refusal names what is missing without disclosing what is present
- **WHEN** a deploy job refuses on an incomplete secret set
- **THEN** its message SHALL name the secrets that resolved empty and SHALL NOT emit any secret's value
