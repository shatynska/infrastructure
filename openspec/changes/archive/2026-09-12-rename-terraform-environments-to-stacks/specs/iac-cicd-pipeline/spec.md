## MODIFIED Requirements

### Requirement: Pull Request Validation Checks
Every pull request that changes Terraform configuration SHALL trigger a GitHub Actions workflow that runs `terraform fmt -check`, `terraform validate`, `tflint`, Trivy misconfiguration scanning, and `gitleaks` secret scanning.

`gitleaks` SHALL run on **every** pull request, whether or not Terraform configuration changed. A secret scanner whose entire value is being unconditional cannot be gated on a path filter: a credential committed under `ansible/`, `platform/` or `docs/` is exactly as exposed as one committed under `terraform/`.

The `gitleaks` version invoked in continuous integration SHALL match the revision pinned in the repository's `pre-commit` configuration, so that a scan passing locally and a scan passing in continuous integration are the same scan. Where the two drift, the pre-commit pin is the source of truth.

`terraform validate` and `tflint` SHALL run against every directory under `terraform/modules/` and `terraform/stacks/` that contains Terraform configuration, discovered rather than enumerated by a fixed list of directory names. A directory added under `terraform/modules/` or `terraform/stacks/` SHALL be covered by these checks without any workflow edit.

Any module directory containing `*.tftest.hcl` test files SHALL also have `terraform test` run against it as part of the same workflow.

`gitleaks` SHALL be invoked as its CLI binary rather than via the `gitleaks/gitleaks-action` marketplace action, because that action requires a paid license key for organization-owned repositories and its v2 runtime is removed from GitHub-hosted runners on 2026-09-16.

#### Scenario: PR with a misconfiguration fails validation
- **WHEN** a pull request introduces a Terraform resource with a Trivy-detectable misconfiguration (e.g. an overly permissive firewall rule)
- **THEN** the validation workflow SHALL fail and report the finding on the pull request

#### Scenario: PR with a leaked credential fails validation
- **WHEN** a pull request's diff contains content matching a `gitleaks` secret pattern
- **THEN** the validation workflow SHALL fail before any `terraform plan` is executed

#### Scenario: A credential outside Terraform is still caught
- **WHEN** a pull request changes no Terraform file and introduces content matching a `gitleaks` secret pattern anywhere in the repository
- **THEN** the validation workflow SHALL run the secret scan and SHALL fail

#### Scenario: Local and CI secret scans agree
- **WHEN** the `gitleaks` revision pinned in the `pre-commit` configuration is compared with the version the validation workflow installs
- **THEN** the two SHALL be the same version

#### Scenario: Secret scanning requires no third-party license
- **WHEN** the validation workflow runs its secret-scanning step
- **THEN** it SHALL complete without requiring a `GITLEAKS_LICENSE` secret or any other paid license credential

#### Scenario: A newly added module is validated and linted without a workflow change
- **WHEN** a pull request adds a new directory under `terraform/modules/` containing Terraform configuration, and no change is made to `pr-validation.yml` to name that directory
- **THEN** the validation workflow SHALL still run `terraform validate` and `tflint` against that directory

#### Scenario: A module's tests run in CI
- **WHEN** a pull request changes a directory under `terraform/modules/` that contains `*.tftest.hcl` files
- **THEN** the validation workflow SHALL run `terraform test` against that directory and fail the check if any test fails

### Requirement: Pull Request Plan Visibility
The workflow SHALL run `terraform plan` for every stack the pull request can affect and post each plan's full output as a comment on the pull request, identifying which stack each plan belongs to.

**A secret scan SHALL precede every plan, in the job that runs it.** The other validation checks — formatting, `terraform validate`, `tflint`, vulnerability scanning, and this pipeline's two test suites — no longer all precede the plan, because the job carrying them concludes on the plan's behalf and therefore runs after it. That is a deliberate narrowing of what a plan waits for, and it is stated rather than left to be inferred: the scan is the check whose ordering is load-bearing, since a plan authenticates to a cloud API and writes its output to a pull request comment, and a leaked credential reaching either is the failure that ordering exists to prevent. A plan that runs on a pull request with invalid HCL wastes a plan; a plan that runs on one carrying a live credential does not.

The stacks a pull request can affect SHALL be determined from the paths it changes: a change under `terraform/modules/` affects every stack, and a change under `terraform/stacks/<name>/` affects only that stack. A pull request affecting no stack SHALL produce no plan.

That determination SHALL fail closed. Where the set of affected stacks cannot be resolved, the workflow SHALL fail rather than resolve it to the empty set: an unresolvable result and a genuine "nothing affected" are indistinguishable, and reading the first as the second plans nothing while reporting success.

A stack whose plan fails SHALL NOT prevent the remaining stacks from being planned and reported. A reviewer shown one stack's failure and nothing about the others cannot tell whether the rest were clean or merely unexamined.

Where this work runs as a job whose name is generated from a matrix, it SHALL NOT be the registered required status check context — see the Required Status Checks Report on Every Pull Request requirement, which governs how it concludes.

#### Scenario: A secret scan precedes every plan
- **WHEN** any job in the pull-request workflow runs `terraform plan`
- **THEN** that same job SHALL have run the secret scan earlier in its own step sequence, and SHALL fail before the plan where the scan fails

#### Scenario: Reviewer sees the plan without leaving GitHub
- **WHEN** a pull request changes `terraform/stacks/<name>/` or `terraform/modules/`
- **THEN** the workflow SHALL post the resulting `terraform plan` output as a PR comment, viewable directly in the GitHub pull request

#### Scenario: A shared module change is planned against every environment
- **WHEN** a pull request changes a file under `terraform/modules/`
- **THEN** the workflow SHALL post a plan for every stack, each identifying the stack it belongs to, rather than a plan for one stack alone

#### Scenario: One environment's plan failure does not hide the others
- **WHEN** the plan for one stack fails on a pull request affecting several
- **THEN** every other affected stack SHALL still be planned and its result posted, and the check SHALL report failure

#### Scenario: An environment-scoped change is planned against that environment only
- **WHEN** a pull request changes files under `terraform/stacks/<name>/` and no shared module
- **THEN** the workflow SHALL post a plan for that stack only

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
- **WHEN** a pull request changing `terraform/stacks/prod/` is merged to `main`
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before running `terraform apply`

#### Scenario: A merge affecting one environment raises no other environment's approval
- **WHEN** a pull request changing only `terraform/stacks/staging/` is merged to `main`
- **THEN** no `production` Environment approval SHALL be requested, and prod SHALL NOT be planned or applied by that run

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

The read-only secret is named **per stack** rather than shared, because a repository secret holds one value: a single repository-scoped `HCLOUD_TOKEN` cannot carry a distinct read-only token for each stack, and a plan job cannot reach an Environment-scoped secret without declaring an `environment:`, which the rule below forbids. Its name comes from the stack's own declaration (see Each Environment Declares Its Own Pipeline Configuration) rather than from workflow text.

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

**Whether this gate applies is a per-stack policy**, declared by the stack itself (see Each Environment Declares Its Own Pipeline Configuration) rather than fixed in workflow text. It SHALL apply to `prod`. A stack whose declared purpose is to be rebuilt — one that exists to rehearse changes, or to be torn down between uses — MAY declare the gate inapplicable, and where it does, a destructive plan for that stack SHALL proceed to its Environment's protection rules without an override label. Requiring a label to destroy a disposable stack is friction on the operation that stack exists to make cheap, and friction on a routine operation is routed around rather than heeded.

A stack declaring the gate inapplicable SHALL NOT thereby weaken it anywhere else: the gate's applicability is read per stack on every run, and a stack that declares nothing SHALL be treated as though the gate applies.

The gate SHALL fail closed. It SHALL proceed only on a positive determination that the plan contains no destructive action; any outcome in which that determination could not be made — the plan could not be rendered to JSON, the inspection command failed, or the inspection produced anything other than an explicit negative result — SHALL fail the workflow with a message distinguishing it from a plan that was inspected and found clean. Treating "the plan could not be inspected" as "the plan is safe" removes the gate precisely when something is already wrong.

This gate applies only to the plan the apply job would apply. It does NOT apply to the pull request's informational `terraform plan` (Pull Request Plan Visibility) — which gates nothing yet, since apply happens only after merge — nor to the nightly drift-detection plan (Scheduled Drift Detection), which is read-only and reports rather than blocks.

This is the Terraform-side guard against destructive applies. It replaces reliance on `lifecycle { prevent_destroy = true }` in shared modules, which cannot be parameterized per stack and only covers individually annotated resources. The gate covers every resource in the plan automatically and surfaces the objection where it can be discussed rather than as an opaque Terraform error.

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

### Requirement: Serialized Terraform Runs
Workflows that run `terraform apply` against a stack SHALL declare a GitHub Actions `concurrency` group per stack with `cancel-in-progress: false`, so that runs queue rather than overlap or cancel each other.

The group SHALL be derived from the stack's own identity, so that two stacks do not share one, and SHALL be declared **at job level** on the jobs that plan and apply a stack. A workflow-level `concurrency` declaration cannot read a per-stack value, so a workflow covering more than one stack cannot express this requirement there. State is per stack, so a run against one stack contends with nothing in another; a shared group would serialize them for no reason and make a slow apply in one stack delay another.

**Within the apply workflow, its plan job and its apply job SHALL NOT share a group.** This sentence is about that workflow alone; a plan run on a pull request or on the drift schedule is not serialized by this requirement at all, and SHALL NOT be placed in either group — the nightly drift plan in particular runs with `-lock=false` precisely so that it contends with nothing.

Declaring the group per job rather than per workflow costs the run its atomicity over that group: the group is acquired twice with a gap between, so a shared one no longer holds a run's plan and its apply together and buys neither of this requirement's two scenarios above, both of which are about applies. What it does buy is a hazard. GitHub cancels a *previously pending* job in a group when a new one queues, so — **where a job awaiting its Environment's protection rules counts as pending for this purpose, which this repository has not established** — a plan job sharing its stack's apply group can cancel an apply that is waiting for its reviewer. An approved change would then never reach the cloud, and would do so as a *cancellation* rather than as a failure, which no alarm here reads.

The separation is chosen rather than the experiment, and the reasoning is recorded so the unestablished premise is not later read as settled: separating the groups is correct under **both** answers. Where a waiting apply is pending, separation removes a silent-loss path; where it is not, separation costs only the stale plan described below. The experiment would establish whether that cost is necessary, not whether the separation is right. Applies contend with applies; plans contend with plans.

The cost of that separation is stated rather than left to be discovered: a plan computed while another run's apply is pending may be stale by the time it reaches its own apply, and SHALL then be refused. That refusal is the Gated Production Apply Applies the Reviewed Plan requirement's scenario "Applied changes match the approved plan" working exactly as specified — loud, after an approval was granted, and correctable by re-running. It is preferred to a silently cancelled apply, which is the same change not reaching production with nothing said at all.

State locking alone prevents concurrent state mutation but does not prevent two runs from applying out of order — the later merge's apply may acquire the lock first and be overwritten by the earlier one.

#### Scenario: Two merges in quick succession apply in order
- **WHEN** two pull requests affecting the same stack are merged to `main` within a short interval
- **THEN** the second apply run SHALL queue until the first completes, and SHALL NOT cancel it or run concurrently with it

#### Scenario: Two environments do not queue behind each other
- **WHEN** an apply against one stack is in progress and an apply against a different stack begins
- **THEN** the second SHALL proceed without waiting on the first

#### Scenario: A queued plan does not cancel an apply awaiting approval
- **WHEN** an apply against a stack is waiting on that stack's protection rules and a later merge's plan for the same stack is queued
- **THEN** the queued plan SHALL NOT cancel or displace the waiting apply, because the two do not share a concurrency group

### Requirement: Scheduled Drift Detection
A scheduled GitHub Actions workflow SHALL run `terraform plan` against every stack on a recurring nightly schedule, without applying any changes, to surface divergence between the committed configuration and actual infrastructure state. These plans are read-only and reporting-only: they do not invoke the Destroy Policy Gate, which applies only to the apply workflow's plan (see that requirement).

When a stack's plan shows a non-empty diff, the workflow SHALL create or update a **single, deduplicated** GitHub issue for that stack containing the diff, and SHALL close or resolve it when a later run finds no drift in that stack. The issue SHALL be identified per stack, so that drift in one stack neither opens a second issue for another nor closes another's. Failing the workflow alone is insufficient: a persistently red scheduled job is muted in practice, leaving drift undetected.

A stack whose plan fails SHALL NOT prevent the remaining stacks from being planned and reported. A scheduled sweep that stops at the first failure leaves every stack after it unchecked and unreported, which is silence indistinguishable from no drift.

The workflow SHALL also be triggerable via `workflow_dispatch`, and its plans SHALL run with `-lock=false`. GitHub automatically disables scheduled workflows after 60 days of repository inactivity — a likely occurrence for an infrastructure repository — so manual triggering is required both as a fallback and to verify the workflow after re-enabling. Running without the state lock prevents a read-only nightly plan from colliding with an in-flight apply and reporting a spurious failure.

#### Scenario: Manual out-of-band change is detected
- **WHEN** a resource in a stack's Hetzner Cloud project is modified outside of Terraform (e.g. via the Hetzner console) and the nightly drift-detection workflow next runs
- **THEN** the resulting `terraform plan` SHALL show a non-empty diff, and the workflow SHALL record it on that stack's dedicated drift issue, without applying any change

#### Scenario: Repeated drift does not open duplicate issues
- **WHEN** the drift-detection workflow runs on consecutive nights and the same drift is still present
- **THEN** it SHALL update the existing drift issue rather than opening an additional one

#### Scenario: Drift in one environment does not resolve another's report
- **WHEN** one stack drifts while another does not
- **THEN** the workflow SHALL report the drift on the drifting stack's own issue, and SHALL NOT close it on the strength of another stack's clean plan

#### Scenario: Resolved drift closes the report
- **WHEN** drift previously reported on a stack's drift issue is resolved and the next scheduled run produces an empty plan for that stack
- **THEN** the workflow SHALL close or mark that stack's drift issue resolved

#### Scenario: One environment's failure does not silence the rest
- **WHEN** the scheduled plan for one stack fails
- **THEN** every other stack SHALL still be planned and reported, and the run SHALL surface the failure rather than concluding successfully

#### Scenario: Drift plan does not contend with an apply
- **WHEN** the scheduled drift plan runs while an approved `terraform apply` holds the state lock
- **THEN** the drift plan SHALL proceed without waiting on or failing due to the lock, because it runs with `-lock=false`

### Requirement: Each Environment Declares Its Own Pipeline Configuration
Every directory under `terraform/stacks/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that stack. Two fields are **required**: the name of the GitHub Environment its apply job attaches to, and the name of the repository secret holding its read-only Hetzner token. A third is **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves).

The optional field SHALL name the **gate**, not its inverse — the value states whether the gate applies, rather than whether the stack is disposable. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting this one silently removes the strongest guard on an apply.

Adding a stack SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate stacks, name them in a condition, or map a stack to its secrets or its Environment name in workflow text. A pipeline that must be edited to add a stack is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. A stack still needs its own state workspace, its own GitHub Environment and secrets, an inventory source and a `group_vars` file of its own for the host-configuration workflow to converge it, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each stack's declared read-only secret name SHALL be distinct from every other stack's, and so SHALL its declared GitHub Environment name. Two stacks naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so a stack intended to be ungated would hold the reviewed stack's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each stack's Read & Write token in that stack's own GitHub Environment. Both are the defect a per-stack declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

**No stack's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every stack.** Credential Scoping by Privilege requires each stack's GitHub Environment to define `HCLOUD_TOKEN` as that stack's Read & Write token, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. A declaration naming `HCLOUD_TOKEN` as its read-only secret is therefore correct only for a job that declares no `environment:`; read from a job that declares one, the same name yields the **write** token, silently and with no error. The declared name is read by gated jobs as well as ungated ones, so the name SHALL be one no Environment shadows.

Discovery SHALL fail closed. A stack directory whose declaration is absent, unparseable, or missing either **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped stack is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the stack not existing and is exactly the condition this capability is meant to make impossible.

#### Scenario: A new environment needs no workflow edit
- **WHEN** a directory is added under `terraform/stacks/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply, drift and host-converge workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: Two environments declaring the same read-only secret are refused
- **WHEN** two stack declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both stacks, rather than running two stacks' plans under one credential

#### Scenario: Two environments declaring the same GitHub Environment are refused
- **WHEN** two stack declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both stacks, rather than applying two stacks under one write token and one set of protection rules

#### Scenario: A declaration naming the write token's own name is refused
- **WHEN** a stack declaration names as its read-only secret a name that every GitHub Environment defines for its Read & Write token
- **THEN** the required status check SHALL fail, naming that stack, rather than leaving a gated job to resolve a write credential from a field that says read-only

#### Scenario: An environment missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/stacks/` has no pipeline declaration, or one lacking either required field
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the stack from the matrix

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over `terraform/stacks/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

### Requirement: Host Configuration Is Applied by a Gated Workflow
Host configuration SHALL reach a host through a workflow triggered by a merge to the default branch. A converge changes the host firewall, the accounts that may log in and the container runtime, so the path by which it reaches a host SHALL be gated in the same way the Terraform apply and the platform deploy are.

**One converge is exempt, and only one: a host's first.** Before that run the host is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with, so the first converge is necessarily an operator's, from a workstation, over the host's public address. Every converge after it SHALL reach the host through the workflow. The exemption is bounded by the host's own bootstrap and SHALL NOT be read as permitting a workstation converge of a host already configured.

The workflow SHALL separate publishing from converging, in a single run. A job that holds **no** credential capable of reaching a host SHALL publish, for a human to read, what the merge changes under the host-configuration directory. A converge job **per stack** SHALL declare that stack's own GitHub Environment, taken from that stack's committed pipeline declaration, and SHALL be the only job holding the credentials a converge needs.

The publishing job is **not** obliged to be per stack, and this requirement deliberately does not make it one. What it publishes is the committed diff, which is the same document whatever stack reads it — a copy per stack would be identical in every row, and would put the number of jobs a merge starts in proportion to something the diff does not depend on. What SHALL be per stack is the credential and the gate.

This layer has no saved-plan artifact and SHALL NOT pretend to one. A check-mode run is not one: it skips `command` tasks, it swallows failures in roles that ignore errors under check mode, and it must authenticate to the host — so it could only run in the job the gate exists to withhold the credential from. What the pre-approval job publishes is the committed diff, which for this layer is complete: every input a converge applies is committed, so there is no value computed elsewhere that the diff omits.

The workflow SHALL name no stack. Which stacks exist, which GitHub Environment gates each, and which repository secret holds each one's read-only credential SHALL come from discovery over committed files, and adding a stack SHALL require no change to any file under `.github/workflows/`.

Discovery SHALL fail closed, with a message naming the stack and what was wrong, rather than omitting a stack from the run. A stack that can be provisioned but not converged, and one that can be converged but is gated by nothing, are both states this discovery SHALL refuse rather than pass over: a stack whose host is converged by no job is indistinguishable from a stack that has nothing to converge.

A converge job SHALL establish that the credentials it holds are usable — that the stack's secrets decrypt and that its inventory resolves — **before** any task acts on the host. Those inputs are decrypted at the moment they are first used, which is several roles into the play, so a run that starts with a wrong secret would otherwise leave a partially-converged host for a reason that had nothing to do with the host.

A converge job SHALL install the toolchain and the external content the play needs before running it, from this repository's own pinned manifests, and SHALL run from the directory whose configuration governs the run. A continuous-integration runner carries neither, and a run that reaches a missing plugin or a missing external role fails inside a mechanism, reading as a broken mechanism rather than as an unprovisioned machine. Running from the wrong directory is worse than failing: the configuration that makes a rejected credential fail the run is not loaded, so the run continues and reports a rejected credential as a stack whose server does not exist.

The version of Ansible a converge runs SHALL be the version the role-verification suite runs. A converge applying roles under a different Ansible than the one they were verified under is verified by nothing, and the agreement SHALL be asserted rather than intended, being a static read of two committed files.

A converge SHALL NOT be cancelled in favour of a later one. Runs against one stack SHALL be serialised, and an in-flight converge SHALL be allowed to finish: interrupting a play mid-run leaves the host partially converged, which is recoverable as an exception and not as a normal case.

One stack's converge failing SHALL NOT prevent another stack's from running and reporting.

#### Scenario: A merge to the host configuration converges without a workstation
- **WHEN** a merge to the default branch changes the host-configuration directory
- **THEN** each already-configured stack's host SHALL be converged by the workflow, and no step of that converge SHALL require a command run from an operator's machine

#### Scenario: A host's first converge is the operator's
- **WHEN** a host has not been converged before, so it is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with
- **THEN** that one converge MAY be run from a workstation over the host's public address, and every converge of that host afterwards SHALL reach it through the workflow

#### Scenario: The pre-approval job holds no converge credential
- **WHEN** the job that publishes what the merge changes runs
- **THEN** it SHALL declare no GitHub Environment and SHALL consume no credential capable of reaching a host

#### Scenario: The converge job is gated on the environment's own GitHub Environment
- **WHEN** a converge job runs for a stack
- **THEN** it SHALL declare the GitHub Environment named by that stack's own pipeline declaration, so that its protection rules and its secrets are the ones that apply

#### Scenario: An environment that cannot be converged fails the workflow
- **WHEN** discovery finds a stack declaring a pipeline configuration but carrying no host-configuration inventory source, or an inventory source whose stack declares no pipeline configuration
- **THEN** the workflow SHALL fail with a message naming that stack and which side is missing, rather than converging the stacks it could resolve

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over the host-configuration inventory sources yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

#### Scenario: A run is requested for an environment that does not exist
- **WHEN** a converge is requested by hand naming a stack discovery did not find
- **THEN** the run SHALL fail naming the stacks that were found, rather than converging none and reporting success

#### Scenario: A wrong secret stops the run before the host is touched
- **WHEN** a converge job holds a credential that does not decrypt that stack's committed secrets, or a credential its inventory source rejects
- **THEN** the run SHALL fail before the first role acts on the host, rather than partway through the play

#### Scenario: The converge job supplies what the run needs
- **WHEN** a converge job runs on a continuous-integration runner, which carries no external content of its own
- **THEN** it SHALL have installed the toolchain and the external content the play needs from this repository's pinned manifests, and SHALL run from the directory whose configuration governs the run

#### Scenario: The converge runs the Ansible the roles were verified under
- **WHEN** the version the converge job installs is compared with the version the role-verification suite installs
- **THEN** the two SHALL be the same, and a difference SHALL fail the required status check

#### Scenario: One environment's failure does not silence another's
- **WHEN** a converge fails for one stack in a run covering several
- **THEN** every other stack's converge SHALL still run and report its own outcome
