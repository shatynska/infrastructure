## REMOVED Requirements

### Requirement: Each Environment Declares Its Own Pipeline Configuration

**Reason**: Renamed, and extended. The word *environment* in this title named the unit the pipeline iterates, which entry 61 renamed to *stack* throughout the body while deferring the title; five of its six scenario titles name the same unit by the old word, and a scenario cannot be renamed inside a `MODIFIED` block — see design.md decision 3. The requirement also gains a third required field, which is the substantive half of this change: a stack's name and its environment stop coinciding, so the environment can no longer be read off the stack.

**Migration**: Replaced in full by *Each Stack Declares Its Own Pipeline Configuration* below. Every existing obligation is carried across unchanged. Added rather than carried: one required field, the two paragraphs that govern it, and two scenarios — *A converge reads its Ansible group from the declaration, not from the stack's name* and *Two stacks declaring the same Ansible group are accepted*. One existing paragraph is widened: the fail-closed clause now says a field is required of the discovery that reads it.

## ADDED Requirements

### Requirement: Each Stack Declares Its Own Pipeline Configuration
Every directory under `terraform/stacks/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that stack. Three fields are **required**: the name of the GitHub Environment its apply job attaches to, the name of the repository secret holding its read-only Hetzner token, and the name of the Ansible group its host-configuration converge targets. A fourth is **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves).

**The declared Ansible group SHALL NOT be derived from the stack's name.** A stack is a *(tenant, environment)* pair and the group it converges is the environment alone, so the two are equal only where a repository has one tenant. Parsing one out of the other is a rule that holds on the names a repository happens to have and fails silently on the next one — as a group that does not exist, reported several steps after the run began. It is declared for the same reason the GitHub Environment's name is: the pipeline reads it rather than computing it.

**Unlike the other two required fields, the declared Ansible group carries no uniqueness obligation**, and the difference is not an oversight. Two stacks naming one GitHub Environment share its write token and its protection rules; two naming one read-only secret share one credential. Two stacks naming one Ansible group share a set of host variables, which is what an environment-wide baseline across tenants *is*. Distinctness SHALL NOT be required of it.

The optional field SHALL name the **gate**, not its inverse — the value states whether the gate applies, rather than whether the stack is disposable. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting this one silently removes the strongest guard on an apply.

Adding a stack SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate stacks, name them in a condition, or map a stack to its secrets, its Environment name or its Ansible group in workflow text. A pipeline that must be edited to add a stack is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. A stack still needs its own state workspace, its own GitHub Environment and secrets, an inventory source and a `group_vars` file of its own for the host-configuration workflow to converge it, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each stack's declared read-only secret name SHALL be distinct from every other stack's, and so SHALL its declared GitHub Environment name. Two stacks naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so a stack intended to be ungated would hold the reviewed stack's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each stack's Read & Write token in that stack's own GitHub Environment. Both are the defect a per-stack declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

**No stack's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every stack.** Credential Scoping by Privilege requires each stack's GitHub Environment to define `HCLOUD_TOKEN` as that stack's Read & Write token, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. A declaration naming `HCLOUD_TOKEN` as its read-only secret is therefore correct only for a job that declares no `environment:`; read from a job that declares one, the same name yields the **write** token, silently and with no error. The declared name is read by gated jobs as well as ungated ones, so the name SHALL be one no Environment shadows.

Discovery SHALL fail closed. A stack directory whose declaration is absent, unparseable, or missing a **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. A field is required of the discovery that reads it: a workflow that runs no converge SHALL NOT refuse a stack for the absence of a field only a converge consumes, since failing a Terraform-only pull request for a host-configuration reason names a cause the change does not have. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped stack is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the stack not existing and is exactly the condition this capability is meant to make impossible.

#### Scenario: A new stack needs no workflow edit
- **WHEN** a directory is added under `terraform/stacks/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply, drift and host-converge workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: A converge reads its Ansible group from the declaration, not from the stack's name
- **WHEN** a stack whose name differs from the Ansible group its host belongs to is converged
- **THEN** the play's target group, the vault-id label and the `group_vars` file SHALL be taken from the declared field, and nothing SHALL parse them out of the stack's directory name

#### Scenario: Two stacks declaring the same read-only secret are refused
- **WHEN** two stack declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both stacks, rather than running two stacks' plans under one credential

#### Scenario: Two stacks declaring the same GitHub Environment are refused
- **WHEN** two stack declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both stacks, rather than applying two stacks under one write token and one set of protection rules

#### Scenario: Two stacks declaring the same Ansible group are accepted
- **WHEN** two stack declarations name the same Ansible group, each with an inventory source reaching its own Hetzner project
- **THEN** discovery SHALL accept both, because a shared group is a shared set of host variables rather than a shared credential

#### Scenario: A declaration naming the write token's own name is refused
- **WHEN** a stack declaration names as its read-only secret a name that every GitHub Environment defines for its Read & Write token
- **THEN** the required status check SHALL fail, naming that stack, rather than leaving a gated job to resolve a write credential from a field that says read-only

#### Scenario: A stack missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/stacks/` has no pipeline declaration, or one lacking a field the running workflow requires
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the stack from the matrix

#### Scenario: Discovery finding no stack fails rather than reporting success
- **WHEN** discovery over `terraform/stacks/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

## MODIFIED Requirements

### Requirement: Credential Scoping by Privilege
Authentication secrets SHALL be split by privilege so that automatically-running jobs (PR-time and scheduled `terraform plan`) only ever have read-only access to Hetzner Cloud, while write access is confined to the approval-gated apply job. This split SHALL hold per stack: a job planning one stack SHALL NOT hold a credential capable of writing to any stack.

For each stack, two Hetzner Cloud API tokens SHALL be provisioned — a **Read Only** token and a **Read & Write** token — and placed as follows, relying on GitHub resolving an environment-scoped secret ahead of a repository-scoped secret of the same name (a job declaring `environment: <name>` receives that Environment's value; any other job receives the repository value):

| Secret | Location | Value |
|---|---|---|
| The read-only secret named by the stack's own pipeline declaration | Repository secret | That stack's Read Only Hetzner token |
| `HCLOUD_TOKEN` | That stack's GitHub Environment secret | That stack's Read & Write Hetzner token |
| `TF_API_TOKEN` | Repository secret | HCP Terraform token (unsplit — see iac-state-management) |
| `TF_API_TOKEN` | Each stack's GitHub Environment secret | Same HCP Terraform token value, kept as a separate secret so a future privilege split needs no workflow changes |

Each stack's GitHub Environment SHALL define `HCLOUD_TOKEN`. GitHub resolves an *absent* Environment secret to the repository secret of the same name rather than failing, so an Environment that omits it supplies whatever the repository holds under that name — at more than one stack, a different stack's token, and therefore a different Hetzner project. An apply job SHALL establish that the token it resolved is not the repository-scoped `HCLOUD_TOKEN`, and SHALL fail rather than apply where it is. The comparison is against that name specifically, because that is what GitHub falls back to — not against whatever secret the stack declares as its read-only one, which coincides with it for at most one stack and would leave the guard passing wherever the hazard is real.

The read-only secret is named **per stack** rather than shared, because a repository secret holds one value: a single repository-scoped `HCLOUD_TOKEN` cannot carry a distinct read-only token for each stack, and a plan job cannot reach an Environment-scoped secret without declaring an `environment:`, which the rule below forbids. Its name comes from the stack's own declaration (see Each Stack Declares Its Own Pipeline Configuration) rather than from workflow text.

`TF_API_TOKEN` (HCP Terraform access) is placed using the same repository/Environment secret pair for structural consistency, but SHALL NOT be assumed to carry the same privilege split — see the HCP Terraform Access via a Static Token, Unsplit by Privilege requirement in the iac-state-management capability, which is the actual source of truth for what that token can and cannot do.

`HCLOUD_TOKEN` and the per-stack read-only secrets SHALL NOT be organization-wide or admin-level credentials, and the Read Only/Read & Write split remains the load-bearing privilege boundary for this pipeline, precisely because `TF_API_TOKEN` is currently unsplit by necessity (see iac-state-management).

This requirement governs where the tokens live *inside GitHub*. Confining the Read & Write token so that it never reaches a workstation — where the workspace's Local execution mode would let it bypass this pipeline entirely — is specified by the Write Credentials Confined to the Gated Pipeline requirement in the iac-safety-hardening capability.

**No job that runs `terraform plan` SHALL declare an `environment:`.** Doing so would both block the job on that Environment's protection rules — making every pull request require an approval click where those rules require a reviewer — and resolve `HCLOUD_TOKEN` to the write-capable token in an ungated job, defeating the split entirely. This holds for every stack, including one whose Environment requires no reviewer: the credential consequence does not depend on whether the gate pauses.

#### Scenario: Plan jobs receive only a read-only Hetzner token
- **WHEN** a PR-time or scheduled `terraform plan` job runs without declaring an `environment:`
- **THEN** its Hetzner token SHALL resolve to the repository-scoped Read Only secret named by that stack's own declaration, which cannot create, modify, or destroy Hetzner resources

#### Scenario: A plan job holds no credential for another environment
- **WHEN** a plan job runs for one stack
- **THEN** the token it resolves SHALL grant no access to any other stack's Hetzner resources

#### Scenario: An Environment omitting the write token does not apply with another's
- **WHEN** an apply job runs for a stack whose GitHub Environment does not define `HCLOUD_TOKEN`, so the value resolves to the repository-scoped secret instead
- **THEN** the job SHALL fail before applying, rather than authenticating against whichever Hetzner project that repository-scoped token belongs to

#### Scenario: Apply job receives the read-write Hetzner token only after approval
- **WHEN** the apply job for a stack runs after that stack's GitHub Environment protection rules are satisfied
- **THEN** its `HCLOUD_TOKEN` SHALL resolve to that Environment's Read & Write token, and that token SHALL NOT be readable by any job that has not passed those rules

#### Scenario: Pull request validation requires no manual approval
- **WHEN** a pull request opens and the validation and plan workflow runs
- **THEN** it SHALL execute to completion without pausing for any GitHub Environment approval, for every stack it plans

### Requirement: Destroy Policy Gate
The gated apply workflow's plan job SHALL inspect its plan's machine-readable form (`terraform show -json`) and SHALL fail the workflow when the plan contains any resource action of `delete` or `replace`, unless the change carries an explicit override signal (assumed to be a pull request label).

**Whether this gate applies is a per-stack policy**, declared by the stack itself (see Each Stack Declares Its Own Pipeline Configuration) rather than fixed in workflow text. It SHALL apply to `main-production`. A stack whose declared purpose is to be rebuilt — one that exists to rehearse changes, or to be torn down between uses — MAY declare the gate inapplicable, and where it does, a destructive plan for that stack SHALL proceed to its Environment's protection rules without an override label. Requiring a label to destroy a disposable stack is friction on the operation that stack exists to make cheap, and friction on a routine operation is routed around rather than heeded.

A stack declaring the gate inapplicable SHALL NOT thereby weaken it anywhere else: the gate's applicability is read per stack on every run, and a stack that declares nothing SHALL be treated as though the gate applies.

The gate SHALL fail closed. It SHALL proceed only on a positive determination that the plan contains no destructive action; any outcome in which that determination could not be made — the plan could not be rendered to JSON, the inspection command failed, or the inspection produced anything other than an explicit negative result — SHALL fail the workflow with a message distinguishing it from a plan that was inspected and found clean. Treating "the plan could not be inspected" as "the plan is safe" removes the gate precisely when something is already wrong.

This gate applies only to the plan the apply job would apply. It does NOT apply to the pull request's informational `terraform plan` (Pull Request Plan Visibility) — which gates nothing yet, since apply happens only after merge — nor to the nightly drift-detection plan (Scheduled Drift Detection), which is read-only and reports rather than blocks.

This is the Terraform-side guard against destructive applies. It replaces reliance on `lifecycle { prevent_destroy = true }` in shared modules, which cannot be parameterized per stack and only covers individually annotated resources. The gate covers every resource in the plan automatically and surfaces the objection where it can be discussed rather than as an opaque Terraform error.

**A rename reaches this gate like any other plan, and the gate does not know it is one.** Renaming a Hetzner resource is an in-place update for some attributes and a replacement for others, and which one a given attribute takes is a property of the provider rather than of the intent behind the change. A plan that renames a resource and reports it as `must be replaced` is therefore a destructive plan and SHALL be stopped by this gate as one. Whether to then apply the override label is the approver's judgment and not something this gate can decide — the label carries no reason and the gate cannot tell a rehearsed teardown from a rename nobody expected to be destructive. This paragraph states the discipline rather than adding a mechanism: **a rename is not a ground for the label**, and a change that meets `must be replaced` on a resource it meant to rename in place has learned that its premise was wrong.

#### Scenario: Unintended resource replacement blocks the pipeline
- **WHEN** the apply workflow's plan job for a stack the gate applies to shows the server being replaced because an immutable attribute changed, and the pull request carries no override label
- **THEN** the destroy-policy gate SHALL fail the workflow and report which resources would be destroyed or replaced, and no apply SHALL run

#### Scenario: Deliberate teardown is possible with explicit acknowledgement
- **WHEN** an operator intends a destructive change and applies the override label to the pull request
- **THEN** the destroy-policy gate SHALL pass and the change SHALL proceed to that stack's Environment protection rules, which still apply

#### Scenario: A disposable environment is destroyed without an override label
- **WHEN** the apply workflow plans a destructive change for a stack whose declaration states the gate does not apply
- **THEN** the gate SHALL NOT fail the workflow, and the change SHALL proceed to that stack's Environment protection rules

#### Scenario: An environment declaring nothing is gated
- **WHEN** a stack's declaration does not state whether the gate applies
- **THEN** the gate SHALL apply to that stack

#### Scenario: An uninspectable plan blocks the pipeline
- **WHEN** the destroy-policy gate cannot determine whether the plan contains a destructive action, because rendering or inspecting the plan's machine-readable form failed
- **THEN** the gate SHALL fail the workflow with a message identifying the inspection as the cause, and SHALL NOT report that the plan contains no destructive actions

#### Scenario: Drift-detection plan is not affected by this gate
- **WHEN** the nightly drift-detection plan (Scheduled Drift Detection) shows a resource being deleted or replaced
- **THEN** the destroy-policy gate SHALL NOT fail that workflow; the drift is instead reported per the Scheduled Drift Detection requirement

### Requirement: Gated Production Apply Applies the Reviewed Plan
`terraform apply` against a stack SHALL run only after a pull request is merged to `main`, SHALL attach to that stack's own GitHub Environment, and SHALL apply a **saved plan file produced before that Environment's protection rules were satisfied** rather than recomputing a plan afterwards.

Every stack's apply job SHALL declare an `environment:`. Whether that pauses for a human is a property of the GitHub Environment's protection rules — repository settings, which no file in this repository can verify — and not of the workflow. The `production` Environment SHALL require a reviewer. A stack whose Environment requires no reviewer is still gated in the sense this requirement means: its write credential remains confined to that job, per Credential Scoping by Privilege.

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
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before running `terraform apply`

#### Scenario: A merge affecting one environment raises no other environment's approval
- **WHEN** a pull request changing only `terraform/stacks/main-staging/` is merged to `main`
- **THEN** no `production` Environment approval SHALL be requested, and `main-production` SHALL NOT be planned or applied by that run

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
