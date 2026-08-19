## Purpose

Defines the GitHub Actions workflow that validates and deploys `platform/`'s Compose stack — the mechanism `iac-platform-services` requires to exist outside Ansible's configuration-management scope.

## ADDED Requirements

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
