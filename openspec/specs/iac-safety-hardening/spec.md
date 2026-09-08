## Purpose

Guardrails against destructive, unnoticed, or externally-exposed changes — deletion protection, backups, network baseline, resource labeling, and automated dependency updates.

## Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match on resources that support it, as the provider requires), exposed as a module variable so each environment can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `terraform/modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-prod environment from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in an environment-specific file under `terraform/environments/prod/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the prod server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Prod volume is protected against console deletion
- **WHEN** an operator attempts to delete the `main-data` volume through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future environment consumes `terraform/modules/server` or `terraform/modules/volume` and sets its deletion-protection variable to `false`
- **THEN** that environment's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Data Durability for Stateful Resources
The prod server SHALL have `backups = true`.

Deletion protection and destroy gating protect the *resource*; neither protects the *data* on its disk against corruption, accidental deletion inside the guest, or filesystem loss. Restoring from a backup is the only remedy for those, and no Terraform-level guardrail substitutes for it. This is accepted at the cost of Hetzner's 20% backup surcharge on the server price.

#### Scenario: Server is created with backups enabled
- **WHEN** the prod server is created via `terraform/environments/prod/`
- **THEN** automatic backups SHALL be enabled on it

### Requirement: Default-Deny Network Baseline
Every server managed by this repository SHALL have an `hcloud_firewall` attached, configured default-deny for inbound traffic, with allowed inbound rules enumerated explicitly including their source CIDRs.

The module SHALL make firewall attachment structural rather than optional, so that a server without a firewall is not expressible through it.

#### Scenario: Prod server is not reachable on unspecified ports
- **WHEN** the prod server is created and a connection is attempted to an inbound port not explicitly allowed by its firewall rules
- **THEN** the connection SHALL be refused by the firewall

#### Scenario: SSH exposure is explicitly scoped
- **WHEN** the firewall permits inbound SSH
- **THEN** it SHALL do so only from explicitly enumerated source CIDRs, and SHALL NOT permit SSH from `0.0.0.0/0`

### Requirement: Key-Only SSH Access
Servers SHALL be provisioned with SSH public key authentication via `hcloud_ssh_key`, and password authentication SHALL be disabled.

#### Scenario: Password login is unavailable
- **WHEN** the prod server has been created
- **THEN** SSH password authentication SHALL be disabled, and access SHALL require a registered key pair

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry an `environment` label matching its environment folder and a `managed_by = "terraform"` label.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `terraform/environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

#### Scenario: Prod volume is labeled
- **WHEN** the `main-data` `hcloud_volume` resource is created via `terraform/environments/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

### Requirement: Write Credentials Confined to the Gated Pipeline
The **Read & Write** Hetzner Cloud API token SHALL exist in exactly one location: the `production` GitHub Environment secret. It SHALL NOT be exported into a shell environment, written to a dotfile, `direnv` file, or any `.tfvars` file, or stored in a local credential helper on any workstation.

Local Terraform work SHALL authenticate with the **Read Only** token, which is sufficient for `terraform plan` and refresh and which causes any local `terraform apply` to fail at the Hetzner Cloud API.

Because the workspace's Execution Mode is Local, the destroy-policy gate, the saved-plan approval gate, and branch protection are properties of the GitHub Actions path to production rather than of Terraform itself — a workstation holding a write-capable token bypasses all three in a single command. This requirement extends the split established by the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability from CI jobs to workstations.

The prohibition SHALL be recorded where it is loaded without being sought: the repository README runbook for human operators, and a repository-root `AGENTS.md` for coding agents.

#### Scenario: Local apply is refused by the API
- **WHEN** an operator or coding agent runs `terraform apply` from a workstation against `terraform/environments/prod/`
- **THEN** the Hetzner Cloud API SHALL reject the write, because the only token available locally is read-only

#### Scenario: Local plan remains available
- **WHEN** an operator runs `terraform plan` from a workstation against `terraform/environments/prod/`
- **THEN** it SHALL succeed using the read-only token, so that local iteration never requires write credentials

#### Scenario: An agent opening the repository is told the boundary
- **WHEN** a coding agent begins work in this repository
- **THEN** a repository-root `AGENTS.md` SHALL state that production changes reach Hetzner only through the gated pipeline and that `terraform apply` is not run locally

### Requirement: Automated Dependency Updates
The repository SHALL configure Dependabot for both the `terraform` and `github-actions` package ecosystems, opening pull requests when newer versions become available.

The `terraform` ecosystem configuration SHALL cover **every** directory in the repository that carries a `.terraform.lock.hcl`. A directory holding a lockfile that no Dependabot entry names is not partially covered — it is uncovered, and its provider pins rot with no signal at all. Because Dependabot's `terraform` ecosystem requires each directory to be listed explicitly and offers no discovery mechanism, adding a Terraform module or environment SHALL include adding it here, and the two SHALL be kept in agreement.

The `github-actions` ecosystem is required, not optional: a compromised or abandoned third-party action is a more realistic supply-chain risk for this repository than a stale Terraform provider.

Dependabot has **no `pre-commit` ecosystem**, so pinned hook revisions SHALL instead be maintained by a scheduled workflow that runs `pre-commit autoupdate` and opens a pull request with the result.

**Any** workflow in this repository that opens a pull request SHALL open it with an identity **other than** that workflow's own default `GITHUB_TOKEN`. The constraint is written over all of them rather than over the hook-update workflow alone because nothing about it is specific to hook revisions, and a second such workflow written later would otherwise reintroduce the defect without violating anything.

An event caused by `GITHUB_TOKEN` does not start a workflow run, so a pull request it authors receives no `on: pull_request` run at all — and every required status check on `main` is triggered that way. Such a pull request opens, reports no check, and stays pending and unmergeable for as long as it exists. That is the same permanent-pending state the Required Status Checks Report on Every Pull Request requirement in `iac-cicd-pipeline` forbids, reached by a route that requirement does not name: authorship rather than a check's path filter. It is worse than the workflow simply failing, because a failure is red whereas this is an open pull request that merely never finishes.

The credential such an identity is drawn from SHALL be scoped to this repository, and SHALL carry no authority beyond what the workflow's pull-request step actually exercises. Where that credential assumes authority the workflow's `GITHUB_TOKEN` previously held, the job's `GITHUB_TOKEN` SHALL be reduced accordingly, per the Least-Privilege Workflow Permissions requirement in `iac-cicd-pipeline`.

That credential SHALL NOT be one that expires on a schedule. A one-time setup step is bounded by the change that introduces it — it either happened or the automation never worked. A scheduled expiry is unbounded: it recurs indefinitely, at a date chosen by the credential's form rather than by anyone, long after the change that established it was archived and by which point no one is watching for it. The failure it would produce is this requirement's own — an automation that stops opening pull requests — and the repository would rediscover it the way it discovered this one. A credential whose short-lived tokens are minted per run from a long-lived, non-expiring secret satisfies this; a personal access token with a mandatory expiry date does not.

Because such an identity is supplied by repository secrets rather than by repository content, the workflow's correctness is not fully readable from the tree. What **is** committed SHALL nonetheless be verifiable statically: that the pull-request step is given a token that is not the default one, that whatever produces that token runs before it, and that an explicit `permissions:` declaration is in force for the job and grants it no write the separate identity performs instead. The permissions obligation is satisfied by a declaration that grants no write, and **not** by the absence of any declaration — an absent declaration falls back to the repository default, which is a setting rather than repository content and can change without any commit.

The existence, scope and rotation procedure of any such credential SHALL be recorded in the repository README's runbook, on the same reasoning as the Write Credentials Confined to the Gated Pipeline requirement: a credential whose only description lives in the change that introduced it becomes undocumented the moment that change is archived.

#### Scenario: Provider version update is proposed automatically
- **WHEN** a newer version of the Hetzner Cloud Terraform provider is released that satisfies or extends the current version constraint
- **THEN** Dependabot SHALL open a pull request updating the `required_providers` constraint and `.terraform.lock.hcl`, subject to the same validation pipeline as any other change

#### Scenario: Every lockfile-bearing directory is covered
- **WHEN** the set of directories containing a `.terraform.lock.hcl` is compared against the directories listed under the `terraform` ecosystem in the Dependabot configuration
- **THEN** every such directory SHALL appear in that configuration

#### Scenario: Action version update is proposed automatically
- **WHEN** a newer version of a GitHub Action referenced by a workflow is released
- **THEN** Dependabot SHALL open a pull request updating that reference

#### Scenario: Pre-commit hook revisions are refreshed on a schedule
- **WHEN** the scheduled hook-update workflow runs and `pre-commit autoupdate` changes any pinned revision
- **THEN** the workflow SHALL open a pull request with the updated `.pre-commit-config.yaml`

#### Scenario: A workflow-opened pull request receives the required status checks
- **WHEN** a workflow in this repository opens a pull request
- **THEN** that pull request SHALL be authored by an identity whose events start workflow runs, so that each required status check on `main` reports a conclusion on it and the pull request is mergeable once they pass

#### Scenario: No workflow opens a pull request with the default workflow token
- **WHEN** the committed workflows are read and any step among them opens a pull request
- **THEN** that step SHALL be given an explicit token input that is neither `secrets.GITHUB_TOKEN` nor `github.token`, and a step producing that token SHALL appear before it in the same job

#### Scenario: The default workflow token is not left holding unused write authority
- **WHEN** the committed workflow is read and its pull request is opened with a separate identity
- **THEN** an explicit `permissions:` declaration SHALL be in force for that job, and the permissions it grants SHALL NOT include a write that the separate identity performs instead

#### Scenario: A permissions declaration is present rather than merely absent
- **WHEN** a job's effective `permissions:` are determined from the committed workflow
- **THEN** they SHALL come from an explicit declaration at workflow or job level, and a workflow declaring none at either level SHALL NOT satisfy the preceding scenario

#### Scenario: A long-lived automation credential is documented where it can be found
- **WHEN** a workflow opens pull requests using a credential held in repository secrets
- **THEN** the README runbook SHALL name that credential, the secrets holding it, the authority it is scoped to, and how it is rotated
