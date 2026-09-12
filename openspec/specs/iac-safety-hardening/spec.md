## Purpose

Guardrails against destructive, unnoticed, or externally-exposed changes — deletion protection, backups, the classification of what data this host's persistent stores may hold, network baseline, resource labeling, and automated dependency updates.

## Requirements

### Requirement: Provider-Level Deletion Protection
Servers and any future volumes managed by this repository SHALL set the Hetzner provider's `delete_protection` attribute (with `rebuild_protection` set to match on resources that support it, as the provider requires), exposed as a module variable so each stack can choose its own value.

This attribute SHALL NOT be hardcoded, and `lifecycle { prevent_destroy = true }` SHALL NOT be declared inside shared modules under `terraform/modules/`. `prevent_destroy` accepts only a literal value — it cannot read a variable — so placing it in a shared module would make that module permanently undestroyable for every consumer, preventing a future non-production stack from ever being torn down. Literal `prevent_destroy` MAY be used for genuinely never-destroy resources declared in a stack-specific file under `terraform/stacks/main-production/`.

#### Scenario: Prod server is protected against console deletion
- **WHEN** an operator attempts to delete the production server through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Prod volume is protected against console deletion
- **WHEN** an operator attempts to delete the `main` volume through the Hetzner Cloud console or API
- **THEN** the deletion SHALL be refused because the resource carries a server-side protection lock

#### Scenario: Shared module remains reusable by a future non-prod environment
- **WHEN** a future stack consumes `terraform/modules/server` or `terraform/modules/volume` and sets its deletion-protection variable to `false`
- **THEN** that stack's resources SHALL be destroyable via `terraform destroy` without editing the shared module

### Requirement: Data Durability for Stateful Resources
The production server SHALL have `backups = true`.

Deletion protection and destroy gating protect the *resource*; neither protects the *data* on its disk against corruption, accidental deletion inside the guest, or filesystem loss. No Terraform-level guardrail substitutes for a copy of the data. This is accepted at the cost of Hetzner's 20% backup surcharge on the server price.

What the setting buys is bounded, and stating it is what stops it being mistaken for a database backup: a daily, crash-consistent image of the **root disk only** — not of the attached data volume — retained on Hetzner's schedule and restorable only by rolling the whole server back to it. That shortens a rebuild of a host whose disk carries container images and converged configuration. It is not a backup any database is restored from selectively, and the obligation for data that would need one is *No Store on This Host Holds Data Requiring Backup* in this capability.

#### Scenario: Server is created with backups enabled
- **WHEN** the production server is created via `terraform/stacks/main-production/`
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
Every `hcloud_*` resource managed by this repository SHALL carry a `managed_by = "terraform"` label and one label per axis its stack is identified on: an `environment` label naming the environment its stack belongs to, and a `tenant` label naming the tenant.

**Each axis SHALL be its own label rather than a segment of a name.** A stack's name is one ordering of its axes and a resource can carry only one name, so a consumer that wants to select on an axis the name puts second has to parse the name — which is a rule that holds on the names a repository happens to have. Labels are queryable individually and are what the Ansible inventory's groups are keyed on, so an axis added later adds a group rather than changing how an existing one is derived.

**Environment values SHALL be spelled in full.** `prod` and `preprod` share a prefix, and a label value is read by prefix in more places than it is read whole — inventory group names, secret names derived from it, a person scanning a console list. The four characters saved are not worth a value that is ambiguous under the commonest way of reading it.

#### Scenario: Prod resources are labeled
- **WHEN** a `hcloud_server` resource is created via `terraform/stacks/main-production/`
- **THEN** it SHALL carry the labels `environment = "production"`, `tenant = "main"` and `managed_by = "terraform"`

#### Scenario: Prod volume is labeled
- **WHEN** the `main` `hcloud_volume` resource is created via `terraform/stacks/main-production/`
- **THEN** it SHALL carry the labels `environment = "production"`, `tenant = "main"` and `managed_by = "terraform"`

#### Scenario: An SSH key a stack owns directly is labeled
- **WHEN** a `hcloud_ssh_key` resource is declared in a stack directory rather than inside a shared module
- **THEN** it SHALL carry the same axis labels every resource that stack's modules create carries, because a resource outside a module is not outside this obligation

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

### Requirement: No Store on This Host Holds Data Requiring Backup
Every store in which a platform-stack service or an application deployed to this host persists data outside its container's writable layer — any volume, named or anonymous, including one an image declares rather than the stack definition, or a host bind mount — SHALL be one that needs no backup of its own — either its contents are recoverable without one, or their loss is acceptable under a policy recorded here — unless the logical backup and rehearsed restore described below are in place before its data lands. For a store needing no backup, the reason SHALL be one of the following, or — where a store's contents divide — one of them for each part, with the division stated:

- its contents are bounded by a rolling retention the service enforces on itself;
- its contents are reproduced from this repository by a redeploy;
- its contents are re-issued on demand by an external authority;
- its contents are derived from a source that still exists, and are regenerated in use without a copy being restored — the source SHALL be named where the reason is stated, and SHALL itself either satisfy this requirement or live outside this host under backups of its own;
- its contents are non-durable by a policy recorded as a requirement in this repository's specifications, which states whose loss that policy treats as tolerable.

Host system state outside those stores — the converged filesystem, the container runtime's own state — is not in scope here: it is reproduced by convergence and by redeploy, and is separately covered by *Data Durability for Stateful Resources*.

Where data is placed in such a store and meets none of those reasons, a logical backup of it written outside this host, together with a restore rehearsed on representative data whose result was checked, SHALL be in place **before** that data first lands — not after.

This fallback reaches every store on this host **except** the shared PostgreSQL instance, which admits no durable data at all under *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) — a prohibition no backup lifts, because that instance's classification above depends on it holding unconditionally.

The platform stack's stores as at 2026-09-08, and the reason each satisfies this requirement. One further store, an application's own, does not satisfy it and is named below rather than omitted:

| Store | Reason |
|---|---|
| The shared PostgreSQL instance's data — `postgres_data`, on the host `platform_postgres_data` | Non-durable by policy — *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) limits it to technical or temporary records whose loss is tolerable to the application that wrote them |
| Prometheus's time-series database (`/mnt/main-data/prometheus`) | Rolling retention it enforces on itself, bounded by both time and size |
| Grafana's data directory (`/mnt/main-data/grafana`) | Split, and both halves are covered: the datasource and the dashboards this repository provisions are reproduced by a redeploy, and the rest is non-durable under the dashboard-state policy stated below |
| Traefik's ACME storage — `traefik_letsencrypt`, on the host `platform_traefik_letsencrypt` | Certificates are re-issued on demand by the certificate authority |
| Alertmanager's state, in the anonymous volume its image declares at `/alertmanager` | Non-durable under the alerting-state policy stated below. This store is declared by the image rather than by the stack definition, which is why the scope above reaches an anonymous volume and why the table was built from the host rather than from `platform/docker-compose.yml` |

That table is the classification on one date and will age; the obligation above is what does not. A store added later SHALL state which of the reasons above it satisfies, in the artifacts of the change that adds it — or, where the store is added outside this repository, in the change here that records it. That is where the second scenario below finds a reason to test, and it costs no delta to this table. Such a store is in scope whether or not the table names it, and a store already named is in breach the moment its stated reason stops being true — a retention flag removed from Prometheus, the provisioning stanza that reproduces Grafana's dashboards deleted from `platform/docker-compose.yml` — whether or not any new data landed.

**One divergence is stated rather than hidden, as of 2026-09-08.** The `commerce-ops` application keeps durable data in a PostgreSQL container of its own on this host, which is what *Single Shared PostgreSQL Instance, Per-Application Databases* forbids and what this requirement is not satisfied by. Its resolution — that application's durable data moves to an external managed service — is work in that application's own repository, over which this repository has no authority. Until it lands, this host holds data no backup covers, and this requirement SHALL be read as unmet in that one respect rather than as describing the host accurately. This divergence SHALL NOT be read to permit another application to do the same.

Resolving it takes two steps, and no change in this repository would otherwise prompt the second: the migration, in that application's own repository, and the deletion of this paragraph. Until both are done the divergence stands as written.

**Grafana state created outside this repository is non-durable.** Dashboards saved or edited through Grafana's own interface, and the users, preferences and annotations its internal database holds, SHALL be treated as data whose loss is tolerable **to the operator**, who is the only party that creates it, because committing a dashboard to the platform stack's definition is the mechanism by which a dashboard worth keeping is kept. The stack permits such edits — its dashboard provider sets `allowUiUpdates` true and `disableDeletion` false — so this is a standing property of that store rather than a hypothetical, and it is stated here rather than in the table above because the table is dated and this policy is not.

**Alerting state is non-durable.** Alertmanager's silences and its notification log SHALL be treated as data whose loss is tolerable **to the operator**: a lost silence lapses into a notification, which is the safe direction to fail in, and the notification log only suppresses repeats of an alert still firing.

This requirement is distinct from *Data Durability for Stateful Resources* in this capability, which requires the server's own automatic backups. Those are daily, crash-consistent, cover the root disk but not the attached data volume, and are retained on Hetzner's schedule; they shorten a rebuild and are a last-resort recovery of the root disk. They are not a substitute for a logical backup taken and restored per database, and their existence SHALL NOT discharge the obligation above.

Durable application data is expected to live in an external managed service that owns its own backups. That such a service's backups are in fact enabled and retained is a fact outside this repository: this requirement states the dependency, and nothing here verifies it.

#### Scenario: A persistent store is added to the host
- **WHEN** a service that persists data outside its container's writable layer is added to the platform stack, or an existing service begins persisting there — including through a volume a bumped image newly declares — or an application deployed to this host persists data of its own in any volume — named or anonymous, declared by the stack definition or by the image — or in a host bind mount
- **THEN** that store SHALL be recoverable without a backup of it, for one of the reasons above
- **OR** a logical backup written outside this host, and a restore rehearsed on representative data whose result was checked, SHALL be in place before the store first holds data

#### Scenario: A store's stated reason ceases to hold
- **WHEN** a change would remove the property a classified store's reason rests on — the retention settings that bound Prometheus's database, or the provisioning from this repository that reproduces Grafana's dashboards
- **THEN** that change SHALL either preserve the property, or restate the store's reason as another of the reasons above, or put the backup and rehearsed restore above in place before it lands

#### Scenario: An application asks for durable storage on this host
- **WHEN** an application would keep data on this host whose loss would not be tolerable
- **THEN** it SHALL be directed to an external managed service that owns its own backups, unless the backup and the rehearsed restore above are already in place

#### Scenario: The stated divergence is not a precedent
- **WHEN** an application proposes keeping durable data on this host on the grounds that `commerce-ops` already does
- **THEN** that SHALL NOT be treated as permission, because the divergence is recorded as unmet rather than as allowed
