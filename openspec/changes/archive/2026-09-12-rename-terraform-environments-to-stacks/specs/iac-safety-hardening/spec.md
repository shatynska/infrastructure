## MODIFIED Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match on resources that support it, as the provider requires), exposed as a module variable so each stack can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `terraform/modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-prod stack from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in a stack-specific file under `terraform/stacks/prod/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the prod server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Prod volume is protected against console deletion
- **WHEN** an operator attempts to delete the `main-data` volume through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future stack consumes `terraform/modules/server` or `terraform/modules/volume` and sets its deletion-protection variable to `false`
- **THEN** that stack's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Data Durability for Stateful Resources
The prod server SHALL have `backups = true`.

Deletion protection and destroy gating protect the *resource*; neither protects the *data* on its disk against corruption, accidental deletion inside the guest, or filesystem loss. No Terraform-level guardrail substitutes for a copy of the data. This is accepted at the cost of Hetzner's 20% backup surcharge on the server price.

What the setting buys is bounded, and stating it is what stops it being mistaken for a database backup: a daily, crash-consistent image of the **root disk only** — not of the attached data volume — retained on Hetzner's schedule and restorable only by rolling the whole server back to it. That shortens a rebuild of a host whose disk carries container images and converged configuration. It is not a backup any database is restored from selectively, and the obligation for data that would need one is *No Store on This Host Holds Data Requiring Backup* in this capability.

#### Scenario: Server is created with backups enabled
- **WHEN** the prod server is created via `terraform/stacks/prod/`
- **THEN** automatic backups SHALL be enabled on it

### Requirement: Consistent Resource Labeling
Every `hcloud_*` resource managed by this repository SHALL carry an `environment` label naming the environment its stack belongs to and a `managed_by = "terraform"` label.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `terraform/stacks/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

#### Scenario: Prod volume is labeled
- **WHEN** the `main-data` `hcloud_volume` resource is created via `terraform/stacks/prod/`
- **THEN** it SHALL carry the labels `environment = "prod"` and `managed_by = "terraform"`

### Requirement: Write Credentials Confined to the Gated Pipeline
Each stack's **Read & Write** Hetzner Cloud API token SHALL exist in exactly one location: that stack's own GitHub Environment secret, named `HCLOUD_TOKEN`. No such token SHALL be exported into a shell environment, written to a dotfile, `direnv` file, or any `.tfvars` file, or stored in a local credential helper on any workstation.

Local Terraform work SHALL authenticate with that stack's **Read Only** token — the one its declaration names as its read-only secret (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability) — which is sufficient for `terraform plan` and refresh and which causes any local `terraform apply` to fail at the Hetzner Cloud API. This states which token a workstation uses, not where the workstation obtains it.

Because the workspace's Execution Mode is Local, the destroy-policy gate, the saved-plan approval gate, and branch protection are properties of the GitHub Actions path to production rather than of Terraform itself — a workstation holding a write-capable token bypasses all three in a single command. This requirement extends the split established by the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability from CI jobs to workstations.

This holds of every stack, not of production alone. A stack whose GitHub Environment requires no reviewer is not thereby exempt: the reviewer and the credential confinement are independent properties, and an unreviewed stack's write token reaching a workstation is the same bypass with a smaller blast radius rather than a permitted one.

The prohibition SHALL be recorded where it is loaded without being sought: the repository README runbook for human operators, and a repository-root `AGENTS.md` for coding agents. **That record SHALL state the prohibition over every stack rather than naming one.** A record naming a single stack is read as silent about the others, which is the reading that matters here: a stack named nowhere in the record is one whose write token a reader has been given no reason to treat as confined, and the stack most likely to be omitted is the one added last.

#### Scenario: Local apply is refused by the API
- **WHEN** an operator or coding agent runs `terraform apply` from a workstation against any stack directory under `terraform/stacks/`
- **THEN** the Hetzner Cloud API SHALL reject the write, because the only token available locally is that stack's read-only one

#### Scenario: Local plan remains available
- **WHEN** an operator runs `terraform plan` from a workstation against any stack directory under `terraform/stacks/`
- **THEN** it SHALL succeed using that stack's read-only token, so that local iteration never requires write credentials

#### Scenario: A non-production environment's write token is confined identically
- **WHEN** a stack exists whose GitHub Environment requires no reviewer
- **THEN** its Read & Write token SHALL still exist only in that Environment's secrets, and SHALL NOT be available on any workstation

#### Scenario: An agent opening the repository is told the boundary
- **WHEN** a coding agent begins work in this repository
- **THEN** a repository-root `AGENTS.md` SHALL state that infrastructure changes reach Hetzner only through the gated pipeline and that `terraform apply` is not run locally

#### Scenario: The record covers an environment added after it was written
- **WHEN** a stack is added to `terraform/stacks/`
- **THEN** the README runbook and `AGENTS.md` SHALL already state the prohibition in terms that cover it, rather than requiring an edit naming it before its write token is treated as confined

### Requirement: Automated Dependency Updates
The repository SHALL configure Dependabot for the `terraform`, `github-actions` and `docker-compose` package ecosystems, opening pull requests when newer versions become available.

The `terraform` ecosystem configuration SHALL cover **every** directory in the repository that carries a `.terraform.lock.hcl`. A directory holding a lockfile that no Dependabot entry names is not partially covered — it is uncovered, and its provider pins rot with no signal at all. Because Dependabot's `terraform` ecosystem requires each directory to be listed explicitly and offers no discovery mechanism, adding a Terraform module or stack directory SHALL include adding it here, and the two SHALL be kept in agreement.

The `github-actions` ecosystem is required, not optional: a compromised or abandoned third-party action is a more realistic supply-chain risk for this repository than a stale Terraform provider.

The `docker-compose` ecosystem is required for the same reason the pinning obligation on the shared stack exists. *Shared-Stack Service Images Are Pinned to an Exact Release* (`openspec/specs/iac-platform-services/spec.md`) forbids that stack a floating tag, so that a version change reaches production as a committed diff the deploy approver sees. A pinned tag never moves on its own, which means the requirement that makes an upgrade reviewable is also the one that makes it depend on a person remembering. This ecosystem supplies the proposal that review acts on. It reads Compose files directly, and is distinct from the `docker` ecosystem, which reads Dockerfiles.

The `docker-compose` ecosystem configuration SHALL cover **every** Compose file in the repository that declares a service image, and the two SHALL be kept in agreement — for the same reason as the `terraform` list above, and by a stronger mechanism than that one's absent discovery. Dependabot's Compose file fetcher lists the contents of the configured directory only; it does not descend into subdirectories, and it fails outright when the configured directory holds no Compose file at all. A Compose file that no configured directory names is therefore not partially covered but uncovered, while every configured entry continues to report success.

Coverage SHALL be read as requiring **both** conditions the fetcher applies, and a check enforcing only one of them SHALL NOT be treated as enforcing this obligation. The fetcher selects files by **name** as well as by directory, so a Compose file sitting in a configured directory under a name the fetcher does not match — one containing no `compose` — is as uncovered as one in a directory the configuration omits, and is the harder of the two to notice, because the directory it sits in is named and reports success. What decides that a file is a stack definition owing coverage is its **content** — a top-level service mapping declaring an image — and the fetcher's filename pattern SHALL be used only to decide whether a file so identified can be reached, never to decide whether a file is a stack definition at all.

Automation SHALL NOT be read as discharging an obligation the stack definition already carries. A pull request this ecosystem opens remains subject to the pinning requirement above — both its automated floor and the human half that floor deliberately does not decide — and to *No Store on This Host Holds Data Requiring Backup* in this capability, whose scope reaches a store "a bumped image newly declares". That last is decidable by no static read of a committed file, because the store is declared by the image rather than by the stack definition, and SHALL be established by review of the pull request rather than assumed absent.

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

#### Scenario: Platform image update is proposed automatically
- **WHEN** a newer release is published of a container image the shared platform Compose stack pins
- **THEN** Dependabot SHALL open a pull request updating that pin, subject to the same validation pipeline and the same gated deploy approval as any other change to the stack definition

#### Scenario: Every Compose file declaring a service image is covered
- **WHEN** the set of files in the repository whose content declares a service image is compared against the `docker-compose` ecosystem's configuration
- **THEN** every such file SHALL sit in a directory that configuration names, **and** SHALL carry a name the fetcher matches
- **AND** a file failing either condition SHALL be reported as uncovered, rather than the configured entries' own success being read as coverage of the repository

#### Scenario: A stack file the fetcher's name pattern does not match is reported
- **WHEN** a file declaring a service image sits in a directory the `docker-compose` ecosystem names, under a name that pattern does not match
- **THEN** it SHALL be reported as uncovered, because the configured directory's own success says nothing about a file within it that is never fetched

#### Scenario: A proposed image update is not exempt from the stack's own obligations
- **WHEN** Dependabot opens a pull request changing an image pin in the shared platform Compose stack
- **THEN** that pull request SHALL pass the pinning requirement's automated floor check, and SHALL receive the human review the remaining half of that requirement depends on
- **AND** whether the proposed image declares a persistent store the current one does not SHALL be established by that review, because no static read of a committed file can establish it

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
