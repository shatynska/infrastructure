## Purpose

GitHub Actions workflows covering PR validation/planning, saved-plan gated apply, the destroy-policy gate, branch protection and least-privilege permissions, and scheduled drift detection. Also covers Ansible verification — lint and syntax checks and a Molecule suite, all of which block a merge — and an executable test suite over this pipeline's own configuration, so the guarantees above are machine-checked rather than resting on a reviewer noticing. Finally, it covers validation of this repository's own specification record: the specifications, the active deltas and the task lists of archived changes are checked on every pull request by the tool that authors them, so the description of what this pipeline is for is verified to the same standard as the pipeline itself.

## Requirements

### Requirement: Pull Request Validation Checks
Every pull request that changes Terraform configuration SHALL trigger a GitHub Actions workflow that runs `terraform fmt -check`, `terraform validate`, `tflint`, Trivy misconfiguration scanning, and `gitleaks` secret scanning.

`gitleaks` SHALL run on **every** pull request, whether or not Terraform configuration changed. A secret scanner whose entire value is being unconditional cannot be gated on a path filter: a credential committed under `ansible/`, `platform/` or `docs/` is exactly as exposed as one committed under `terraform/`.

The `gitleaks` version invoked in continuous integration SHALL match the revision pinned in the repository's `pre-commit` configuration, so that a scan passing locally and a scan passing in continuous integration are the same scan. Where the two drift, the pre-commit pin is the source of truth.

`terraform validate` and `tflint` SHALL run against every directory under `terraform/modules/` and `terraform/environments/` that contains Terraform configuration, discovered rather than enumerated by a fixed list of directory names. A directory added under `terraform/modules/` or `terraform/environments/` SHALL be covered by these checks without any workflow edit.

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

### Requirement: Required Status Checks Report on Every Pull Request
Every workflow registered as a required status check SHALL report a conclusion on every pull request, including pull requests that touch none of the files that workflow's work is about.

That work MAY be path-filtered, but the filtering SHALL occur *inside* an always-running job rather than via a workflow-level `paths` or `paths-ignore` filter. A workflow-level path filter on a required check never reports for non-matching pull requests, leaving those pull requests permanently pending and unmergeable under the branch protection rule below.

Where a required check's work is performed by a job whose name is generated rather than literal — a matrix job, whose context names vary with the matrix — that job SHALL NOT be the registered context. A job whose name is a literal SHALL depend on it, run regardless of its outcome, and conclude on its behalf. A generated context cannot be enumerated in branch protection in advance; a role or directory added to the matrix would introduce a context nobody registered; and a matrix that is empty or skipped produces no context at all, which is the same permanent pending reached by another route.

Such an aggregating job SHALL distinguish a skipped dependency from a successful one, and SHALL conclude failure where a dependency was skipped while the pull request changed files that dependency's work covers. `skipped` and `success` are different conclusions; read as one — which `success()` over a skipped dependency does — the check reports green having verified nothing, the same defect this capability's discovery, destroy-policy gate and secret-scanning requirements each forbid elsewhere.

An aggregating job SHALL treat its own change-detection input as trustworthy only where the job producing it concluded successfully. Where that job did not, its outputs are empty, and an empty "nothing changed" is indistinguishable from a genuine one.

#### Scenario: Documentation-only pull request remains mergeable
- **WHEN** a pull request changes only files outside the paths a required check's work covers (e.g. a README)
- **THEN** that required status check SHALL report success rather than remaining pending, and the pull request SHALL be mergeable

#### Scenario: A required check reports without doing work it was not asked to do
- **WHEN** a pull request changes no file a required check's path-filtered work covers
- **THEN** that work SHALL be skipped rather than executed, and the check SHALL still conclude

#### Scenario: A required check whose work was skipped does not report success
- **WHEN** a pull request changes files a required check's work covers, and that work concludes as skipped rather than as executed
- **THEN** the required status check SHALL report failure rather than success

#### Scenario: A required check whose change detection did not conclude does not report success
- **WHEN** the job producing a required check's change-detection output fails
- **THEN** the required status check SHALL report failure, rather than reading that job's empty output as "nothing changed"

#### Scenario: A cancelled dependency does not report success
- **WHEN** a required check's work concludes as cancelled
- **THEN** the required status check SHALL report failure, whether or not the pull request changed files that work covers — a cancelled job has verified nothing

#### Scenario: A failed dependency reports failure whatever the change detection said
- **WHEN** a required check's work concludes as failed on a pull request that changed none of the files that work covers
- **THEN** the required status check SHALL report failure, rather than treating the absence of relevant changes as licence to disregard the result

### Requirement: Pull Request Plan Visibility
The workflow SHALL run `terraform plan` for every environment the pull request can affect and post each plan's full output as a comment on the pull request, identifying which environment each plan belongs to.

**A secret scan SHALL precede every plan, in the job that runs it.** The other validation checks — formatting, `terraform validate`, `tflint`, vulnerability scanning, and this pipeline's two test suites — no longer all precede the plan, because the job carrying them concludes on the plan's behalf and therefore runs after it. That is a deliberate narrowing of what a plan waits for, and it is stated rather than left to be inferred: the scan is the check whose ordering is load-bearing, since a plan authenticates to a cloud API and writes its output to a pull request comment, and a leaked credential reaching either is the failure that ordering exists to prevent. A plan that runs on a pull request with invalid HCL wastes a plan; a plan that runs on one carrying a live credential does not.

The environments a pull request can affect SHALL be determined from the paths it changes: a change under `terraform/modules/` affects every environment, and a change under `terraform/environments/<name>/` affects only that environment. A pull request affecting no environment SHALL produce no plan.

That determination SHALL fail closed. Where the set of affected environments cannot be resolved, the workflow SHALL fail rather than resolve it to the empty set: an unresolvable result and a genuine "nothing affected" are indistinguishable, and reading the first as the second plans nothing while reporting success.

An environment whose plan fails SHALL NOT prevent the remaining environments from being planned and reported. A reviewer shown one environment's failure and nothing about the others cannot tell whether the rest were clean or merely unexamined.

Where this work runs as a job whose name is generated from a matrix, it SHALL NOT be the registered required status check context — see the Required Status Checks Report on Every Pull Request requirement, which governs how it concludes.

#### Scenario: A secret scan precedes every plan
- **WHEN** any job in the pull-request workflow runs `terraform plan`
- **THEN** that same job SHALL have run the secret scan earlier in its own step sequence, and SHALL fail before the plan where the scan fails

#### Scenario: Reviewer sees the plan without leaving GitHub
- **WHEN** a pull request changes `terraform/environments/<name>/` or `terraform/modules/`
- **THEN** the workflow SHALL post the resulting `terraform plan` output as a PR comment, viewable directly in the GitHub pull request

#### Scenario: A shared module change is planned against every environment
- **WHEN** a pull request changes a file under `terraform/modules/`
- **THEN** the workflow SHALL post a plan for every environment, each identifying the environment it belongs to, rather than a plan for one environment alone

#### Scenario: One environment's plan failure does not hide the others
- **WHEN** the plan for one environment fails on a pull request affecting several
- **THEN** every other affected environment SHALL still be planned and its result posted, and the check SHALL report failure

#### Scenario: An environment-scoped change is planned against that environment only
- **WHEN** a pull request changes files under `terraform/environments/<name>/` and no shared module
- **THEN** the workflow SHALL post a plan for that environment only

### Requirement: Credential Scoping by Privilege
Authentication secrets SHALL be split by privilege so that automatically-running jobs (PR-time and scheduled `terraform plan`) only ever have read-only access to Hetzner Cloud, while write access is confined to the approval-gated apply job. This split SHALL hold per environment: a job planning one environment SHALL NOT hold a credential capable of writing to any environment.

For each environment, two Hetzner Cloud API tokens SHALL be provisioned — a **Read Only** token and a **Read & Write** token — and placed as follows, relying on GitHub resolving an environment-scoped secret ahead of a repository-scoped secret of the same name (a job declaring `environment: <name>` receives that Environment's value; any other job receives the repository value):

| Secret | Location | Value |
|---|---|---|
| The read-only secret named by the environment's own pipeline declaration | Repository secret | That environment's Read Only Hetzner token |
| `HCLOUD_TOKEN` | That environment's GitHub Environment secret | That environment's Read & Write Hetzner token |
| `TF_API_TOKEN` | Repository secret | HCP Terraform token (unsplit — see iac-state-management) |
| `TF_API_TOKEN` | Each environment's GitHub Environment secret | Same HCP Terraform token value, kept as a separate secret so a future privilege split needs no workflow changes |

Each environment's GitHub Environment SHALL define `HCLOUD_TOKEN`. GitHub resolves an *absent* Environment secret to the repository secret of the same name rather than failing, so an Environment that omits it supplies whatever the repository holds under that name — at more than one environment, a different environment's token, and therefore a different Hetzner project. An apply job SHALL establish that the token it resolved is not the repository-scoped `HCLOUD_TOKEN`, and SHALL fail rather than apply where it is. The comparison is against that name specifically, because that is what GitHub falls back to — not against whatever secret the environment declares as its read-only one, which coincides with it for at most one environment and would leave the guard passing wherever the hazard is real.

The read-only secret is named **per environment** rather than shared, because a repository secret holds one value: a single repository-scoped `HCLOUD_TOKEN` cannot carry a distinct read-only token for each environment, and a plan job cannot reach an Environment-scoped secret without declaring an `environment:`, which the rule below forbids. Its name comes from the environment's own declaration (see Each Environment Declares Its Own Pipeline Configuration) rather than from workflow text.

`TF_API_TOKEN` (HCP Terraform access) is placed using the same repository/Environment secret pair for structural consistency, but SHALL NOT be assumed to carry the same privilege split — see the HCP Terraform Access via a Static Token, Unsplit by Privilege requirement in the iac-state-management capability, which is the actual source of truth for what that token can and cannot do.

`HCLOUD_TOKEN` and the per-environment read-only secrets SHALL NOT be organization-wide or admin-level credentials, and the Read Only/Read & Write split remains the load-bearing privilege boundary for this pipeline, precisely because `TF_API_TOKEN` is currently unsplit by necessity (see iac-state-management).

This requirement governs where the tokens live *inside GitHub*. Confining the Read & Write token so that it never reaches a workstation — where the workspace's Local execution mode would let it bypass this pipeline entirely — is specified by the Write Credentials Confined to the Gated Pipeline requirement in the iac-safety-hardening capability.

**No job that runs `terraform plan` SHALL declare an `environment:`.** Doing so would both block the job on that Environment's protection rules — making every pull request require an approval click where those rules require a reviewer — and resolve `HCLOUD_TOKEN` to the write-capable token in an ungated job, defeating the split entirely. This holds for every environment, including one whose Environment requires no reviewer: the credential consequence does not depend on whether the gate pauses.

#### Scenario: Plan jobs receive only a read-only Hetzner token
- **WHEN** a PR-time or scheduled `terraform plan` job runs without declaring an `environment:`
- **THEN** its Hetzner token SHALL resolve to the repository-scoped Read Only secret named by that environment's own declaration, which cannot create, modify, or destroy Hetzner resources

#### Scenario: A plan job holds no credential for another environment
- **WHEN** a plan job runs for one environment
- **THEN** the token it resolves SHALL grant no access to any other environment's Hetzner resources

#### Scenario: An Environment omitting the write token does not apply with another's
- **WHEN** an apply job runs for an environment whose GitHub Environment does not define `HCLOUD_TOKEN`, so the value resolves to the repository-scoped secret instead
- **THEN** the job SHALL fail before applying, rather than authenticating against whichever Hetzner project that repository-scoped token belongs to

#### Scenario: Apply job receives the read-write Hetzner token only after approval
- **WHEN** the apply job for an environment runs after that environment's GitHub Environment protection rules are satisfied
- **THEN** its `HCLOUD_TOKEN` SHALL resolve to that Environment's Read & Write token, and that token SHALL NOT be readable by any job that has not passed those rules

#### Scenario: Pull request validation requires no manual approval
- **WHEN** a pull request opens and the validation and plan workflow runs
- **THEN** it SHALL execute to completion without pausing for any GitHub Environment approval, for every environment it plans

### Requirement: Gated Production Apply Applies the Reviewed Plan
`terraform apply` against an environment SHALL run only after a pull request is merged to `main`, SHALL attach to that environment's own GitHub Environment, and SHALL apply a **saved plan file produced before that Environment's protection rules were satisfied** rather than recomputing a plan afterwards.

Every environment's apply job SHALL declare an `environment:`. Whether that pauses for a human is a property of the GitHub Environment's protection rules — repository settings, which no file in this repository can verify — and not of the workflow. The `production` Environment SHALL require a reviewer. An environment whose Environment requires no reviewer is still gated in the sense this requirement means: its write credential remains confined to that job, per Credential Scoping by Privilege.

The apply workflow SHALL be structured as two jobs per environment in a single run:

1. A **plan job** that declares no `environment:`, runs `terraform plan -out=tfplan`, writes the human-readable plan to the run's job summary, and uploads `tfplan` as a workflow artifact.
2. An **apply job** that depends on the plan job, declares that environment's `environment:`, and on satisfaction of its protection rules downloads `tfplan` and runs `terraform apply tfplan`.

This ensures the approving reviewer sees the exact diff that will be applied. A workflow that approves first and plans afterwards gives the reviewer no diff to evaluate, and the plan computed after approval may differ from the one reviewed on the pull request due to the merge commit, intervening drift, or a provider version change.

**An environment SHALL be applied only where its own plan was produced, and an environment whose plan failed SHALL NOT prevent any other environment from being applied.** These are one obligation because a single mechanism decides both, and the two failures it stands between are opposite: an apply stage that begins for an environment with no saved plan raises that environment's approval request with nothing to approve, which this requirement forbids by name; an apply stage that waits on the plan stage as a whole stops every environment when any one of them fails, so a correct change does not reach production because an unrelated environment is broken.

Declaring the apply stage dependent on the plan stage is therefore **not sufficient**, and the reason is mechanical rather than stylistic: such a dependency is scoped to the stage, not to the environment, so it cannot distinguish *this* environment's plan from another's. The set of environments to apply SHALL instead be resolved from which environments actually produced a saved plan.

**An environment counts as having produced a saved plan only where every check its plan job performs has passed.** The saved plan's *existence* is not that fact and SHALL NOT be substituted for it: the Destroy Policy Gate runs inside the plan job and after the plan exists, so a plan the gate refused is a plan that was produced and must not be applied. Reading existence alone would leave the gate defeated for exactly the plans it exists to stop, behind an approval it exists because it does not trust. Where the resolution is made by observing an artifact, the artifact SHALL therefore be published only after every such check has passed, and unconditionally on their having passed — never on the plan job having merely reached that point.

That resolution SHALL run outside any GitHub Environment, since it decides which Environments the run will ask for and so cannot be gated on one of them.

It SHALL fail closed in the same sense the affected-environment resolution above does, and with the same distinction: where the set can be neither read as a valid set nor read as an explicit empty one, the workflow SHALL fail with a message identifying that resolution as the cause. An **explicitly empty** planned set is not that case and SHALL NOT fail the run — a merge matching this workflow's path filter while affecting no environment reaches the apply stage with nothing to apply, and that is the correct outcome rather than an error.

The apply stage SHALL NOT reach its conclusion through the plan stage's aggregate result. A dependency whose outcome propagates the plan stage's result reinstates exactly the coupling this obligation removes, and does so while every other part of the mechanism appears correct — the resolution runs, the set is right, and the apply stage is skipped anyway.

The apply workflow SHALL be triggered only by pushes that can affect the Terraform configuration, identified by a workflow-level path filter. **An environment SHALL enter the run only where the merge could affect that environment**, determined by the same path rule the Pull Request Plan Visibility requirement states: a change under `terraform/modules/` affects every environment, a change under `terraform/environments/<name>/` affects only that environment. A merge that cannot change an environment's infrastructure SHALL NOT raise that environment's Environment approval request. An approval prompt that appears with nothing to approve trains the approver to grant it without reading, which defeats the gate it exists to enforce; out-of-band divergence remains covered by scheduled drift detection rather than by an approval request per merge.

The set of affected environments SHALL be resolved fail-closed, and this workflow runs on `push`, where no pull-request diff is available and the base of the comparison may be absent — a first push to a branch, a force-push, or a merge whose `before` commit no longer resolves. Where that set cannot be determined, the workflow SHALL fail with a message identifying the resolution as the cause. Resolving it to the empty set instead would apply nothing for a merge that did change infrastructure, report a green run, and leave the divergence to be found by the next nightly drift sweep.

This path filter is permissible **only** because the apply workflow is not a required status check. Any workflow that is registered as a required check SHALL NOT be path-filtered at the workflow level — see the Required Status Checks Report on Every Pull Request requirement, whose constraint is the opposite of this one and takes precedence for those workflows. There is more than one such workflow, and the constraint holds of each.

Because a saved plan file stores sensitive values in cleartext, the `tfplan` artifact SHALL be treated as a secret: retention SHALL be set to the shortest workable period, the artifact SHALL be named per environment so that one environment's plan cannot be applied to another, and the artifact SHALL NOT be produced in a public repository without symmetric encryption using a key held in repository secrets.

#### Scenario: Merge does not apply immediately
- **WHEN** a pull request changing `terraform/environments/prod/` is merged to `main`
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before running `terraform apply`

#### Scenario: A merge affecting one environment raises no other environment's approval
- **WHEN** a pull request changing only `terraform/environments/staging/` is merged to `main`
- **THEN** no `production` Environment approval SHALL be requested, and prod SHALL NOT be planned or applied by that run

#### Scenario: A shared module change reaches every environment
- **WHEN** a pull request changing a file under `terraform/modules/` is merged to `main`
- **THEN** each environment SHALL be planned and applied under its own GitHub Environment's protection rules

#### Scenario: A plan its own gate refused is not applied
- **WHEN** an environment's plan job produces a plan and then fails one of that job's own checks, such as the Destroy Policy Gate
- **THEN** that environment SHALL NOT be applied and SHALL NOT raise its Environment's approval request, because a plan that exists is not thereby a plan that passed

#### Scenario: One environment's failed plan does not block another's apply
- **WHEN** a merge affects two environments and one of them fails to plan
- **THEN** the other environment SHALL still be applied under its own GitHub Environment's protection rules, and no approval SHALL be requested for the environment whose plan failed

#### Scenario: An unresolvable set of planned environments fails the run
- **WHEN** which environments produced a saved plan cannot be determined
- **THEN** the workflow SHALL fail with a message identifying that resolution as the cause, and SHALL NOT proceed as though no environment had been planned

#### Scenario: Reviewer sees the exact diff before approving
- **WHEN** an apply job is pending approval
- **THEN** the completed plan job's summary SHALL already display the full plan output for the merge commit and identify which environment it belongs to, so the reviewer can read the pending changes before granting approval

#### Scenario: Applied changes match the approved plan
- **WHEN** approval is granted and the apply job runs
- **THEN** it SHALL apply the saved `tfplan` artifact produced by the plan job for that same environment, and SHALL error rather than apply divergent changes if remote state has changed since that plan was saved

#### Scenario: Apply credentials are inaccessible before approval
- **WHEN** an apply workflow run is pending approval
- **THEN** the read-write `HCLOUD_TOKEN` scoped to that environment's GitHub Environment SHALL NOT be readable by the workflow job until approval is granted

#### Scenario: An unresolvable set of affected environments fails the run
- **WHEN** a merge's set of affected environments cannot be determined, because the resolution step did not conclude or produced a value that is neither a valid set nor an explicit empty one
- **THEN** the workflow SHALL fail with a message identifying that resolution as the cause, and SHALL NOT proceed as though no environment were affected

#### Scenario: A merge that cannot change infrastructure raises no approval request
- **WHEN** a pull request changing only documentation, Ansible or platform files is merged to `main`
- **THEN** the apply workflow SHALL NOT run, and no Environment approval SHALL be requested

### Requirement: Destroy Policy Gate
The gated apply workflow's plan job SHALL inspect its plan's machine-readable form (`terraform show -json`) and SHALL fail the workflow when the plan contains any resource action of `delete` or `replace`, unless the change carries an explicit override signal (assumed to be a pull request label).

**Whether this gate applies is a per-environment policy**, declared by the environment itself (see Each Environment Declares Its Own Pipeline Configuration) rather than fixed in workflow text. It SHALL apply to `prod`. An environment whose declared purpose is to be rebuilt — one that exists to rehearse changes, or to be torn down between uses — MAY declare the gate inapplicable, and where it does, a destructive plan for that environment SHALL proceed to its Environment's protection rules without an override label. Requiring a label to destroy a disposable environment is friction on the operation that environment exists to make cheap, and friction on a routine operation is routed around rather than heeded.

An environment declaring the gate inapplicable SHALL NOT thereby weaken it anywhere else: the gate's applicability is read per environment on every run, and an environment that declares nothing SHALL be treated as though the gate applies.

The gate SHALL fail closed. It SHALL proceed only on a positive determination that the plan contains no destructive action; any outcome in which that determination could not be made — the plan could not be rendered to JSON, the inspection command failed, or the inspection produced anything other than an explicit negative result — SHALL fail the workflow with a message distinguishing it from a plan that was inspected and found clean. Treating "the plan could not be inspected" as "the plan is safe" removes the gate precisely when something is already wrong.

This gate applies only to the plan the apply job would apply. It does NOT apply to the pull request's informational `terraform plan` (Pull Request Plan Visibility) — which gates nothing yet, since apply happens only after merge — nor to the nightly drift-detection plan (Scheduled Drift Detection), which is read-only and reports rather than blocks.

This is the Terraform-side guard against destructive applies. It replaces reliance on `lifecycle { prevent_destroy = true }` in shared modules, which cannot be parameterized per environment and only covers individually annotated resources. The gate covers every resource in the plan automatically and surfaces the objection where it can be discussed rather than as an opaque Terraform error.

#### Scenario: Unintended resource replacement blocks the pipeline
- **WHEN** the apply workflow's plan job for an environment the gate applies to shows the server being replaced because an immutable attribute changed, and the pull request carries no override label
- **THEN** the destroy-policy gate SHALL fail the workflow and report which resources would be destroyed or replaced, and no apply SHALL run

#### Scenario: Deliberate teardown is possible with explicit acknowledgement
- **WHEN** an operator intends a destructive change and applies the override label to the pull request
- **THEN** the destroy-policy gate SHALL pass and the change SHALL proceed to that environment's Environment protection rules, which still apply

#### Scenario: A disposable environment is destroyed without an override label
- **WHEN** the apply workflow plans a destructive change for an environment whose declaration states the gate does not apply
- **THEN** the gate SHALL NOT fail the workflow, and the change SHALL proceed to that environment's Environment protection rules

#### Scenario: An environment declaring nothing is gated
- **WHEN** an environment's declaration does not state whether the gate applies
- **THEN** the gate SHALL apply to that environment

#### Scenario: An uninspectable plan blocks the pipeline
- **WHEN** the destroy-policy gate cannot determine whether the plan contains a destructive action, because rendering or inspecting the plan's machine-readable form failed
- **THEN** the gate SHALL fail the workflow with a message identifying the inspection as the cause, and SHALL NOT report that the plan contains no destructive actions

#### Scenario: Drift-detection plan is not affected by this gate
- **WHEN** the nightly drift-detection plan (Scheduled Drift Detection) shows a resource being deleted or replaced
- **THEN** the destroy-policy gate SHALL NOT fail that workflow; the drift is instead reported per the Scheduled Drift Detection requirement

### Requirement: Serialized Terraform Runs
Workflows that run `terraform apply` against an environment SHALL declare a GitHub Actions `concurrency` group per environment with `cancel-in-progress: false`, so that runs queue rather than overlap or cancel each other.

The group SHALL be derived from the environment's own identity, so that two environments do not share one, and SHALL be declared **at job level** on the jobs that plan and apply an environment. A workflow-level `concurrency` declaration cannot read a per-environment value, so a workflow covering more than one environment cannot express this requirement there. State is per environment, so a run against one environment contends with nothing in another; a shared group would serialize them for no reason and make a slow apply in one environment delay another.

**Within the apply workflow, its plan job and its apply job SHALL NOT share a group.** This sentence is about that workflow alone; a plan run on a pull request or on the drift schedule is not serialized by this requirement at all, and SHALL NOT be placed in either group — the nightly drift plan in particular runs with `-lock=false` precisely so that it contends with nothing.

Declaring the group per job rather than per workflow costs the run its atomicity over that group: the group is acquired twice with a gap between, so a shared one no longer holds a run's plan and its apply together and buys neither of this requirement's two scenarios above, both of which are about applies. What it does buy is a hazard. GitHub cancels a *previously pending* job in a group when a new one queues, so — **where a job awaiting its Environment's protection rules counts as pending for this purpose, which this repository has not established** — a plan job sharing its environment's apply group can cancel an apply that is waiting for its reviewer. An approved change would then never reach the cloud, and would do so as a *cancellation* rather than as a failure, which no alarm here reads.

The separation is chosen rather than the experiment, and the reasoning is recorded so the unestablished premise is not later read as settled: separating the groups is correct under **both** answers. Where a waiting apply is pending, separation removes a silent-loss path; where it is not, separation costs only the stale plan described below. The experiment would establish whether that cost is necessary, not whether the separation is right. Applies contend with applies; plans contend with plans.

The cost of that separation is stated rather than left to be discovered: a plan computed while another run's apply is pending may be stale by the time it reaches its own apply, and SHALL then be refused. That refusal is the Gated Production Apply Applies the Reviewed Plan requirement's scenario "Applied changes match the approved plan" working exactly as specified — loud, after an approval was granted, and correctable by re-running. It is preferred to a silently cancelled apply, which is the same change not reaching production with nothing said at all.

State locking alone prevents concurrent state mutation but does not prevent two runs from applying out of order — the later merge's apply may acquire the lock first and be overwritten by the earlier one.

#### Scenario: Two merges in quick succession apply in order
- **WHEN** two pull requests affecting the same environment are merged to `main` within a short interval
- **THEN** the second apply run SHALL queue until the first completes, and SHALL NOT cancel it or run concurrently with it

#### Scenario: Two environments do not queue behind each other
- **WHEN** an apply against one environment is in progress and an apply against a different environment begins
- **THEN** the second SHALL proceed without waiting on the first

#### Scenario: A queued plan does not cancel an apply awaiting approval
- **WHEN** an apply against an environment is waiting on that environment's protection rules and a later merge's plan for the same environment is queued
- **THEN** the queued plan SHALL NOT cancel or displace the waiting apply, because the two do not share a concurrency group

### Requirement: Branch Protection on the Default Branch
The `main` branch SHALL be protected such that changes arrive only via pull request: direct pushes and force-pushes SHALL be rejected, branch deletion SHALL be rejected, a pull request SHALL be required, and the status checks named below SHALL be required to pass before merge. The protection SHALL apply to administrators, and SHALL require a branch to be up to date with `main` before it merges.

The required status check contexts SHALL be `validate`, from `pr-validation.yml`, and `ansible-verify`, from `ansible-verify.yml`. Each names a job whose name is a literal in its workflow; neither names a job whose name is generated from a matrix, per the requirement above.

Requiring a branch to be up to date means an Ansible pull request re-runs the Molecule suite after each trunk update. That cost is accepted: the alternative is merging Ansible changes against a trunk they were never verified against.

Registering a context is repository settings rather than repository content, so nothing in this repository can verify that it happened — the pipeline's own test suite makes no network call. What that suite SHALL assert instead is that each named workflow is shaped so that it can be registered safely: no workflow-level path filter, and a literal job name to register. It SHALL NOT be written so as to imply it has established more than that.

Every other safeguard in this capability — plan review, the destroy-policy gate, and the approval-gated apply — assumes changes reach `main` through a reviewed pull request. Without branch protection, a direct push to `main` bypasses all of them and triggers an apply.

#### Scenario: Direct push to main is rejected
- **WHEN** a developer attempts to push a commit directly to `main`
- **THEN** the push SHALL be rejected, requiring the change to go through a pull request

#### Scenario: Pull request with failing checks cannot merge
- **WHEN** a pull request's validation workflow fails
- **THEN** the pull request SHALL be blocked from merging until the checks pass

#### Scenario: Every registered context names a literal job
- **WHEN** the workflow behind each registered required status check is read
- **THEN** the job that context names SHALL carry a literal `name:`, containing no GitHub Actions expression

### Requirement: Least-Privilege Workflow Permissions
The repository's default `GITHUB_TOKEN` permission SHALL be set to read-only, and each workflow or job SHALL declare only the additional permissions it requires.

#### Scenario: Only the commenting job can write to pull requests
- **WHEN** the validation workflow runs
- **THEN** only the job that posts the plan comment SHALL hold `pull-requests: write`, and no job SHALL hold `contents: write` unless it needs to push

#### Scenario: No job declares an OIDC permission it cannot use
- **WHEN** a job authenticates to HCP Terraform or Hetzner Cloud
- **THEN** it SHALL do so using the static, privilege-scoped tokens (`TF_API_TOKEN`, `HCLOUD_TOKEN`) described by the Credential Scoping by Privilege requirement, and SHALL NOT declare `id-token: write` — neither HCP Terraform's CLI-driven backend nor Hetzner Cloud's API accepts a GitHub OIDC token

### Requirement: Scheduled Drift Detection
A scheduled GitHub Actions workflow SHALL run `terraform plan` against every environment on a recurring nightly schedule, without applying any changes, to surface divergence between the committed configuration and actual infrastructure state. These plans are read-only and reporting-only: they do not invoke the Destroy Policy Gate, which applies only to the apply workflow's plan (see that requirement).

When an environment's plan shows a non-empty diff, the workflow SHALL create or update a **single, deduplicated** GitHub issue for that environment containing the diff, and SHALL close or resolve it when a later run finds no drift in that environment. The issue SHALL be identified per environment, so that drift in one environment neither opens a second issue for another nor closes another's. Failing the workflow alone is insufficient: a persistently red scheduled job is muted in practice, leaving drift undetected.

An environment whose plan fails SHALL NOT prevent the remaining environments from being planned and reported. A scheduled sweep that stops at the first failure leaves every environment after it unchecked and unreported, which is silence indistinguishable from no drift.

The workflow SHALL also be triggerable via `workflow_dispatch`, and its plans SHALL run with `-lock=false`. GitHub automatically disables scheduled workflows after 60 days of repository inactivity — a likely occurrence for an infrastructure repository — so manual triggering is required both as a fallback and to verify the workflow after re-enabling. Running without the state lock prevents a read-only nightly plan from colliding with an in-flight apply and reporting a spurious failure.

#### Scenario: Manual out-of-band change is detected
- **WHEN** a resource in an environment's Hetzner Cloud project is modified outside of Terraform (e.g. via the Hetzner console) and the nightly drift-detection workflow next runs
- **THEN** the resulting `terraform plan` SHALL show a non-empty diff, and the workflow SHALL record it on that environment's dedicated drift issue, without applying any change

#### Scenario: Repeated drift does not open duplicate issues
- **WHEN** the drift-detection workflow runs on consecutive nights and the same drift is still present
- **THEN** it SHALL update the existing drift issue rather than opening an additional one

#### Scenario: Drift in one environment does not resolve another's report
- **WHEN** one environment drifts while another does not
- **THEN** the workflow SHALL report the drift on the drifting environment's own issue, and SHALL NOT close it on the strength of another environment's clean plan

#### Scenario: Resolved drift closes the report
- **WHEN** drift previously reported on an environment's drift issue is resolved and the next scheduled run produces an empty plan for that environment
- **THEN** the workflow SHALL close or mark that environment's drift issue resolved

#### Scenario: One environment's failure does not silence the rest
- **WHEN** the scheduled plan for one environment fails
- **THEN** every other environment SHALL still be planned and reported, and the run SHALL surface the failure rather than concluding successfully

#### Scenario: Drift plan does not contend with an apply
- **WHEN** the scheduled drift plan runs while an approved `terraform apply` holds the state lock
- **THEN** the drift plan SHALL proceed without waiting on or failing due to the lock, because it runs with `-lock=false`

### Requirement: The Continuous-Integration Configuration Is Itself Verified
The properties this capability requires of its own configuration — which checks are gated on which paths, which versions are pinned where, which jobs declare a deployment `environment:`, and which directories a dependency-update configuration covers — SHALL be asserted by an executable test suite, and that suite SHALL run on every pull request as part of the required status check, unconditionally. Where the enclosing job declares `needs:` — that is, where it aggregates other jobs' results — it MAY carry the single condition `always()` and no other. A job declaring dependencies is otherwise skipped whenever one of them fails, and a skipped job produces no status check context at all, which under branch protection is a required check that never reports: the same permanent-pending state a path filter produces. `always()` is admitted because it cannot evaluate false — it is the strongest available guarantee that a dependent job still runs, not a weakening of unconditionality. It is admitted as that exact literal and not as a class: in either the bare or the `${{ }}`-wrapped spelling, containing nothing else, and only on a job declaring `needs:`. No other expression is permitted by it, and neither is `always()` joined to anything.

These properties are assertions about repository files rather than about infrastructure, so the project's module-level Terraform test mechanism cannot reach them. A capability whose guarantees are checked only by a reviewer noticing is guaranteed only until someone does not notice; the gaps this change closes were each introduced that way.

**This suite is also where a static property of committed files is asserted whenever it reaches beyond the directory whose own check would otherwise hold it.** Its subject is not `.github/`. A scan at repository scope, or over any directory outside the one holding the check — for a committed credential, a key marker, or any other property established by reading files rather than by running them — SHALL live here rather than inside a check that runs only when some particular directory changes, because unconditional execution is exactly what makes such a claim true. A scan of that kind held elsewhere claims a scope its trigger does not give it. That predicate is the same one the Ansible verification requirement states from its own side; they are one obligation read from two directions, not two.

**The file set such a scan reads SHALL be the repository's tracked files.** This suite runs on developer machines as well as on runners, and a working tree holds ignored content a checkout does not — caches, virtual environments, other working trees, and the very environment files a credential is legitimately kept in. Walking those produces failures that are not defects, and the remedy reached for is a path-exclusion list, which permanently blinds the scan in whichever directory acquired the exclusion. Reading tracked files instead matches what this suite's subject already is: a committed file. An uncommitted credential is the commit hook's to catch, not this suite's.

The suite SHALL depend only on its runtime's standard library and on dependencies pinned exactly in a repository manifest, and SHALL require no network access, credential, container runtime or Terraform binary — it gates every pull request, including those that change nothing it asserts about. Enumerating the repository's tracked files is admitted as an exception to the standard-library limit and to nothing else: it invokes the version-control binary that placed the files there, which is present wherever the repository was checked out, and it reaches no network and needs no credential.

**That exception is bounded by how the binary comes to be present, and SHALL NOT be read as admitting binaries generally.** A tool that exists because the repository was obtained at all is available in every environment this suite runs in, by construction; a tool that must be installed for the suite to work is a dependency the suite would have to pin, provision and keep current, and it is that class the limit excludes. The prohibition on running a separately installed binary from inside this suite — stated by the requirement governing verification of the specification record — is unaffected, and this exception SHALL NOT be cited against it.

Matching within a tracked file SHALL be over its bytes rather than over a decoded string, so that a file this suite cannot decode fails no assertion it was not going to fail anyway; and a tracked path absent from the working tree SHALL fail naming that path, a partial checkout being unable to establish a property over the committed tree.

**Where that enumeration is unavailable, the affected assertion SHALL fail rather than skip.** A guarded skip is the correct shape for an assertion whose absence leaves another check standing; it is the wrong shape for a scan for committed credential material, where a skip reports success for a property nothing examined. This suite's other external-tool guards are not precedent for this one.

Where a property can be asserted only by executing a third-party matcher or by reaching the network — the behaviour of a change-detection action's glob patterns, as opposed to their declaration — the suite SHALL assert the declaration and the behaviour SHALL be established by observation on a real pull request, rather than the constraint being relaxed to reach it.

#### Scenario: A regression in CI configuration fails the pull request that introduces it
- **WHEN** a pull request changes the continuous-integration configuration such that a property this capability requires no longer holds
- **THEN** the required status check SHALL fail on that pull request

#### Scenario: The suite runs regardless of what a pull request touched
- **WHEN** a pull request changes no file under `.github/`
- **THEN** the required status check SHALL still run the suite and report its result

#### Scenario: A repository-scope scan is not confined to one directory's trigger
- **WHEN** a static property is asserted over files the whole repository may hold
- **THEN** it SHALL be asserted by this suite, and SHALL NOT be held inside a check whose trigger is a single directory

#### Scenario: An ignored file is not scanned and does not fail the suite
- **WHEN** the suite runs on a working tree holding ignored content — a dependency cache, a virtual environment, another working tree, or an ignored environment file carrying a real credential
- **THEN** the scans SHALL read the repository's tracked files only, and SHALL NOT report that ignored content as a committed secret

#### Scenario: A scan that cannot enumerate tracked files fails rather than skipping
- **WHEN** the suite runs where the repository's tracked files cannot be enumerated
- **THEN** the affected assertion SHALL fail, naming the enumeration as the cause, rather than skipping and allowing the suite to report success for a property nothing examined

#### Scenario: The suite needs no privileged or external resource
- **WHEN** the suite runs in continuous integration
- **THEN** it SHALL complete without a network call, a credential, a container runtime or a Terraform binary

### Requirement: Ansible Configuration Is Verified in Continuous Integration and Gates the Merge
Every pull request that changes files under `ansible/` SHALL trigger continuous-integration checks over that configuration. Both tiers block a merge; they remain distinguished by cost, which governs how each is triggered rather than whether it gates.

**Lint tier.** `ansible-lint` and `ansible-playbook --syntax-check` SHALL run as part of the required pull request status check, using the same invocation the repository's `pre-commit` configuration uses locally, so that a pull request cannot merge with Ansible content that fails either. These checks require no container runtime and no credential. This tier SHALL be triggered by any change under `ansible/`, without exclusion: it is the tier that covers the paths the suite tier does not read.

**That the lint tier remains unexcluded SHALL be asserted, not reviewed.** It is the compensating coverage for every path the suite tier stops selecting, so a narrowing of it would withdraw that coverage with nothing failing — and "which checks are gated on which paths" is exactly what this capability requires its own executable suite to assert. An assertion establishing only that a filter for this directory exists does not establish this.

**Suite tier.** The Molecule suite SHALL run in continuous integration on pull requests changing the Ansible content its scenarios read, and SHALL be registered as a required status check. Its scenarios exercise host-level firewalling, `fail2ban` and service management inside containers; that these are reproducible on a hosted runner is established by consecutive green runs on pull requests with independent subjects, which is what the previously advisory tier existed to observe. A scenario that fails SHALL block the merge.

Because the suite is costly and the lint tier is not, the suite SHALL be triggered by change detection *inside* an always-running workflow rather than by a workflow-level path filter, per the requirement above, and a pull request touching nothing the suite reads SHALL start no container. Its conclusion SHALL be reported by an aggregating job whose name is a literal, which SHALL fail where the suite was skipped on a pull request that did change content the suite reads.

**What the suite reads is narrower than `ansible/`, and the difference SHALL be declared as exclusions rather than as inclusions.** Change detection SHALL match the whole of `ansible/` and then subtract the paths established, by reading the scenarios themselves, to be unread by any of them. A path added under `ansible/` and considered by nobody SHALL therefore trigger the suite. The opposite spelling — naming the paths that do trigger it — makes such a path silently skip, and a skip that reports green is the failure this capability's discovery refusal, its gate and its resolution step are each written to prevent. Wasteful and visible is the recoverable direction; economical and silent is not.

An exclusion SHALL be justified by what scenario text does, not by what a directory is named. A path a scenario names in a comment, or asserts as a substring of an expected failure message, is not a path that scenario reads.

**A static property of committed files reaching outside the role directory whose scenario holds it SHALL NOT be verified only by the suite.** It SHALL be asserted by the pipeline's own executable test suite instead, which runs on every pull request unconditionally. Such an assertion held inside a scenario covers only the pull requests that happen to trigger that scenario, which is not the scope it claims; and it is what would make narrowing the suite's trigger unsafe, since excluding a path would silently withdraw the only check that reads it. The scan that establishes a repository-scope credential property SHALL be rooted at the repository rather than at whichever directory motivated it, so that its root matches the scope its requirement states. A narrower scan retained **in addition** — one whose claim is bounded by the directory it reads, and which therefore states nothing about the repository — is not that scan and is not held to this.

**The premise the exclusions rest on SHALL itself be checked.** That no scenario reads an excluded path is a static read of committed scenario text, and SHALL be asserted as one: a scenario reaching the controller's filesystem outside the paths the exclusions were established against SHALL fail the pipeline's own configuration checks. A check on the filter's declared patterns does not establish this and is not a substitute for it — the filter can be correct about a premise that has stopped being true.

**What that check looks for is a scenario reading a repository file from the controller**, and both halves of that are load-bearing. A read of the managed node cannot be affected by a filter over this repository and is out of scope; so is a controller-side task that derives a value from an already-registered fact without opening a file. A check drawn wider than this fires on the bulk of ordinary scenario text, and the only recoveries from that are to permit those sites wholesale — which makes the check meaningless — or to narrow it by an unstated rule, which is the defect it exists to prevent.

Within that scope the check SHALL recognise **every** route, not the one route a particular scan happened to use. Delegation to the controller is one. A file-reading lookup expression is another and needs no delegation, executing on the controller wherever it appears. Controller-resolved inclusion is a third, and covers the inclusion of **tasks and plays** as much as of variables — a scenario importing a play by path reads that file from the controller exactly as one loading variables from it does, and it is the likeliest route by which a scenario would come to read the playbook directory, which is excluded. A source path on a module that sends a file to the managed node is a fourth, being a controller path unless the module declares otherwise — where a module that reads *from* the managed node instead is a controller read only when the task delegates, so delegation rather than any option on the module is what decides it. A path declared in a scenario's own configuration file is a fifth — in its provisioner environment or in the options it passes to its dependency resolution — being neither a task nor a play. A check recognising only delegation passes a scenario that reads an excluded path through any of the others, which is the same vacuous green this capability refuses everywhere else.

**Where the check meets a construction it does not recognise, carrying a path that resolves into this repository, it SHALL refuse rather than pass over it.** A list of routes goes stale exactly as a list of paths does, and the polarity that answers one answers the other: an unrecognised construction that is ignored is a silent gap, where one that is refused costs a visible edit to permit. This obligation is bounded by the criterion above, which already excludes reads of the managed node, so breadth here does not reach ordinary scenario text.

**The permitted reads SHALL be enumerated individually, and each SHALL be identified by the file that holds it together with the construction and the target it resolves to — never by a line offset.** Enumerating the permitted *paths* instead would admit a second, newly added read of an already-permitted path without anyone considering it, which is the thing this check exists to refuse. Enumerating by line offset would make the permitted set wrong on any commit that edits a scenario above one of them — including the very commit that relocates the reads this check is written alongside — and a permitted set that is stale reports the surviving reads as violations, or silently permits whatever text has moved onto the recorded offsets. Identity that survives ordinary editing is a property of the mechanism, not a convenience.

**Each entry SHALL additionally record how many occurrences it permits within the file that holds it, and a count above that SHALL fail.** Where an entry names a declaration every scenario carries rather than a read in one file, its permitted count is per file on the same terms. An identity built from a file, a construction and a target does not by itself separate one read from two of the same shape, and the second read of an already-permitted target is most naturally added in the file that already holds the first — so membership alone would admit precisely the addition this enumeration exists to make someone look at.

Change detection resolves against a pull request's diff. Where the workflow is started by any other event there is no diff to resolve against, and the suite SHALL run in full rather than defaulting to skipped. A default of skipped would report a green conclusion on precisely the trigger this repository uses to observe the suite against the trunk.

Where the suite is correctly skipped, the message the aggregating job reports SHALL say that nothing the suite reads changed, rather than that nothing under the configuration directory changed. Once the two differ, the second is false on exactly the runs a reader consults it about.

Discovery SHALL declare the least privilege its change detection needs, per the *Least-Privilege Workflow Permissions* requirement, and SHALL receive no write scope: reading which files a pull request touched is a read.

The Molecule run SHALL discover role scenarios rather than enumerate them, so that a role or scenario added under `ansible/roles/` is covered without a workflow edit, and SHALL execute every scenario a role declares rather than only its `default` scenario.

Discovery SHALL fail loudly rather than succeed vacuously: where it finds no role to run, the run SHALL fail with a message identifying discovery as the cause, and SHALL NOT report success. A discovery that silently matches nothing is indistinguishable from a suite that passed, which is the same defect this capability's destroy-policy gate and secret scanning requirements each forbid elsewhere. Discovery SHALL run on every pull request rather than only on those changing `ansible/`: a repository state in which no role carries scenarios has lost the check that gates every merge, and the pull request that removes it is not the only one that should stop. That refusal is over the roles the tree carries and SHALL remain independent of what the diff selected, so that a discovery failure cannot be reported as a correct skip.

The Molecule run SHALL install its toolchain from the repository's exact pinned manifests — `ansible/requirements-test.txt` for the Python toolchain and `ansible/requirements.yml` for Galaxy content — and SHALL NOT resolve any dependency version freshly at run time. Neither manifest SHALL be excluded from change detection: a change to either changes what every scenario runs under.

That obligation SHALL extend to the container image each scenario executes inside, which is as much a run-time-resolved dependency as either manifest and determines what the pinned toolchain runs against. Every scenario SHALL declare its platform image by immutable content digest, so that every machine resolves the same immutable reference and an upstream re-push of a tag cannot change what the suite tested without a reviewable commit. Where the image publishes no version tag, the digest is the only exact form available and SHALL be used; where a multi-architecture image is published, the digest declared SHALL be the multi-architecture one, so that each architecture resolves deterministically beneath a single pinned reference rather than the pin excluding an architecture the suite is expected to run on.

Where two scenarios name the same image repository, they SHALL name the same digest. Scenarios are defined one per file with no shared inclusion, so a pin repeated across them drifts when one is refreshed and the others are not — leaving the suite running against two versions of the same image while appearing pinned. This constrains only scenarios that already agree on an image; it does not require the suite to standardise on a single base image.

A scenario SHALL NOT be exempt from this by being newly added: the obligation is over every scenario this repository authors, and a scenario reintroducing a mutable tag, or disagreeing with its siblings' digest, SHALL fail the pipeline's own configuration checks rather than being caught by review alone.

The obligation SHALL NOT extend to scenarios shipped by Galaxy content installed from `ansible/requirements.yml`, which install beside this repository's own roles and are not committed here. Such content is already pinned as a whole by that manifest, and its scenario definitions are neither editable in place — a reinstall discards local edits — nor reachable by review. The check SHALL derive that exclusion from the manifest's own contents rather than from a hardcoded list of role names, so that adding or removing pinned Galaxy content cannot leave the exclusion stale in either direction.

Every scenario SHALL declare its instance name so that it resolves to a value unique to the working tree the run was started from, rather than to a literal shared by every working tree on the machine. Its default, where no working tree supplies one, SHALL be a value that cannot name a container at all, rather than one that merely reads as wrong: a default that would successfully create an instance reinstates the shared literal under a different spelling. Every scenario SHALL additionally declare an explicit host name for its instance, bounded independently of the instance name, because a host name derived from a namespaced instance name is not bounded by anything the scenario controls and fails once a working tree's own name grows long enough.

The run-time obligation the first of these serves belongs to `iac-repo-foundations`'s *Verification Writing to Shared State Is Namespaced per Working Tree*; what this requirement adds is that the scenario definitions SHALL be checked, statically, to carry all three.

Those obligations SHALL be checked statically over the same scenario definitions this repository authors, by the same checks that read their platform images, and SHALL derive its exclusion of installed Galaxy content from `ansible/requirements.yml` in the same way. A scenario added later SHALL be covered without an edit to the check.

Neither tier SHALL declare a deployment `environment:` or receive any production credential; the Molecule suite runs offline against local containers.

#### Scenario: Ansible-only pull request is linted and syntax-checked
- **WHEN** a pull request changes a file under `ansible/` and no Terraform file
- **THEN** the required status check SHALL run `ansible-lint` and `ansible-playbook --syntax-check` and SHALL fail if either reports an error

#### Scenario: Narrowing the lint tier's trigger fails the pipeline's own checks
- **WHEN** the lint tier's change detection is edited so that a path under `ansible/` which the suite tier excludes no longer selects it
- **THEN** the pipeline's own configuration checks SHALL fail, rather than the compensating coverage for the suite tier's exclusions being withdrawn with nothing reporting

#### Scenario: A pull request changing only Ansible content no scenario reads starts no container
- **WHEN** a pull request's whole `ansible/` footprint is paths change detection excludes as unread by any scenario
- **THEN** the Molecule matrix SHALL be skipped rather than executed, the lint tier SHALL still run over those paths, and the aggregating job SHALL conclude success

#### Scenario: An unconsidered new path under the configuration directory runs the suite
- **WHEN** a pull request adds a file under `ansible/` that change detection's exclusions do not name
- **THEN** the Molecule suite SHALL run, rather than being skipped for want of an inclusion naming it

#### Scenario: A correct skip says what was actually unchanged
- **WHEN** the aggregating job concludes success having correctly skipped the suite
- **THEN** its message SHALL state that nothing the suite reads changed, rather than that nothing under the configuration directory changed

#### Scenario: A committed credential is caught wherever in the repository it lands
- **WHEN** a pull request commits a GitHub or GHCR token marker, or an operator private-key marker, in any tracked file — including one under no directory the Molecule suite is triggered by
- **THEN** the pipeline's own executable test suite SHALL fail on that pull request naming the file, and that failure SHALL NOT depend on whether change detection selected the Molecule suite

#### Scenario: A credential assigned across a folded scalar's continuation is still caught
- **WHEN** a tracked file assigns the registry pull token as a YAML folded or block scalar, so that the assignment line carries no value and the value occupies the following more-indented lines
- **THEN** the scan SHALL read the assignment together with its continuation and SHALL fail where that value is a committed literal, accepting it only where it is an inline vault value or an environment lookup — a line-oriented reading, which passes over every such assignment, SHALL NOT satisfy this

#### Scenario: A second read of an already-permitted path is still refused
- **WHEN** a scenario adds a controller-side read of a path some other permitted read already reaches — including one in the same file, by the same construction, resolving to the same target, so that it is indistinguishable from the permitted read by identity alone
- **THEN** those checks SHALL refuse it until it is itself enumerated, the permitted set being over individual reads rather than over the paths they reach, and each entry's permitted occurrence count being what separates one such read from two

#### Scenario: Editing a scenario above a permitted read does not invalidate the permitted set
- **WHEN** a commit inserts or removes lines in a scenario file above a read the permitted set names — including the commit that relocates reads out of that same file
- **THEN** those checks SHALL continue to recognise that read as the permitted one, its identity resting on the file, the construction and the target it resolves to rather than on a line offset

#### Scenario: A scenario reaching an excluded path fails the pipeline's own checks
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors and find a controller-side read outside the paths change detection's exclusions were established against
- **THEN** those checks SHALL fail identifying that scenario and that read, rather than leaving the exclusion silently covering a path that is now read

#### Scenario: A controller read that does not delegate is still a controller read
- **WHEN** a scenario reaches the controller's filesystem on a task or play that does not delegate to the controller — through a file-reading lookup expression, a controller-resolved inclusion of variables, tasks or plays, or a controller-side source path — or through a path declared in its own scenario configuration, which carries no task at all
- **THEN** those checks SHALL treat it as a controller read and hold it to the same enumerated paths, rather than passing over it for carrying no delegation

#### Scenario: A read of the managed node is not held to the enumerated paths
- **WHEN** a scenario reads a path on the host it converges — an absolute path inside the container, through a module that reads from the managed node on a task that does not delegate to the controller
- **THEN** those checks SHALL pass over it, no filter over this repository being capable of affecting it, and SHALL NOT require it to be enumerated among the permitted controller reads

#### Scenario: A newly added role scenario runs without a workflow change
- **WHEN** a pull request adds a scenario directory under `ansible/roles/<role>/molecule/`, and no change is made to the workflow to name that role or scenario
- **THEN** the Molecule run SHALL still execute that scenario

#### Scenario: Every scenario a role declares is executed
- **WHEN** the Molecule run reaches a role that declares more than one scenario
- **THEN** it SHALL execute all of that role's scenarios, not only the `default` scenario

#### Scenario: Discovering no roles fails rather than passes
- **WHEN** the Molecule run's role discovery yields an empty set
- **THEN** the run SHALL fail with a message identifying discovery as the cause, rather than concluding successfully having executed no scenario

#### Scenario: Discovery failing is not reported as a correct skip
- **WHEN** role discovery fails on a pull request whose diff change detection would have excluded
- **THEN** the aggregating job SHALL fail identifying discovery as the cause, rather than concluding success on the ground that the suite was not owed

#### Scenario: A failing Molecule scenario blocks the merge
- **WHEN** a Molecule scenario fails on a pull request
- **THEN** the failure SHALL be visible on the pull request, the aggregating job SHALL conclude failure, and the pull request SHALL be blocked from merging

#### Scenario: A pull request touching no Ansible file starts no container
- **WHEN** a pull request changes no file under `ansible/`
- **THEN** the Molecule matrix SHALL be skipped rather than executed, and the workflow SHALL still conclude and report

#### Scenario: Role discovery runs even where the suite does not
- **WHEN** a pull request changes no file under `ansible/`
- **THEN** role discovery SHALL still run, and where it finds no role its failure SHALL fail the required status check — the suite that gates every merge having silently disappeared is not a fact only pull requests touching `ansible/` should learn

#### Scenario: A manual run verifies the whole suite
- **WHEN** the Molecule workflow is started other than by a pull request
- **THEN** the suite SHALL run in full rather than being skipped for want of a diff to inspect, and the workflow SHALL NOT conclude success having skipped it

#### Scenario: A change to a pinned manifest runs the suite
- **WHEN** a pull request changes `ansible/requirements-test.txt` or `ansible/requirements.yml` and no file under `ansible/roles/`
- **THEN** the Molecule suite SHALL run, both manifests determining what every scenario executes under

#### Scenario: Ansible verification receives no production credential
- **WHEN** any Ansible verification job runs on a pull request
- **THEN** it SHALL complete without a Hetzner API token, an SSH deploy key, a registry credential, or a declared deployment `environment:`

#### Scenario: Every scenario's platform image is pinned by digest
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every declared platform image SHALL carry an immutable content digest, and a scenario declaring an image by mutable tag alone SHALL fail those checks

#### Scenario: A scenario declaring no platform image fails rather than being skipped
- **WHEN** those checks reach a scenario definition that declares no platform, or a platform with no image
- **THEN** the checks SHALL fail identifying that scenario, rather than passing over it — a scenario silently exempted from a pinning check is indistinguishable from a scenario that satisfies it

#### Scenario: Scenarios sharing an image repository agree on its digest
- **WHEN** two or more scenario definitions name the same image repository
- **THEN** they SHALL name the same digest, and a partial refresh leaving one at a different digest SHALL fail those checks

#### Scenario: Installed Galaxy content is not held to this repository's pinning obligation
- **WHEN** Galaxy content pinned in `ansible/requirements.yml` is installed into `ansible/roles/` and ships a scenario definition of its own
- **THEN** those checks SHALL exclude it, deriving the exclusion from that manifest, and SHALL report the same result on a provisioned developer machine as on a continuous-integration runner that has installed nothing

#### Scenario: An upstream re-push cannot change what the suite ran against
- **WHEN** the upstream registry re-publishes the tag a scenario's image was originally named by, and no commit is made to this repository
- **THEN** the scenario SHALL continue to resolve the same image content it resolved before the re-push

#### Scenario: Every authored scenario bounds its instance's host name
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every scenario SHALL declare an explicit host name for its instance, and a scenario declaring none SHALL fail those checks — its host name would otherwise be derived from a namespaced instance name and fail to create once a working tree's name grew long enough

#### Scenario: Every authored scenario's instance name carries the namespace
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every declared instance name SHALL carry the working-tree namespace, and its default SHALL be one that cannot name a container at all rather than one that merely looks wrong; a scenario declaring a bare literal name, or a default that would successfully create a shared instance, SHALL fail those checks

### Requirement: The Molecule Matrix Runs the Roles a Pull Request Owes
The Molecule suite SHALL run the roles a pull request's changed files owe, rather than every discovered role, and what a set of changed files owes SHALL be the reverse closure of a role-dependency graph derived from the scenario definitions in the checkout being tested. Nothing SHALL commit that graph: a graph recorded in a file is a list, and a list that falls behind the scenarios it describes under-selects silently — the aggregating gate sees a matrix that passed over the rows it was handed and has no way to learn which rows it should have been handed.

This narrows *which* roles run. It does not narrow what a role runs: every selected role SHALL still execute every scenario it declares, per the requirement above.

**Attribution is by role directory, and everything else widens.** A changed path SHALL attribute to role `R` where and only where it lies under that role's own directory. Every other path the suite's change detection admits SHALL select every discovered role — the shared manifests that determine what all scenarios run under, the entry point that runs them, and equally any path this attribution does not recognise. Where a rule over paths can fall behind the tree, the direction that fails safely is to run: an unrecognised path that widens costs runner time and is visible in the run, where one that narrows to nothing costs the coverage this check exists to provide and reports green.

Attribution SHALL rest on the directory name rather than on whether that role carries scenarios of its own. A role with no scenarios may still be converged by another role's, so a change to it is owed by that other role; resolving it to nothing selectable would produce an empty selection where the suite was owed.

**The selection SHALL be the closure restricted to the roles the run can execute.** Attribution and the closure both range over role directories, and only a role carrying scenarios can be run — so a role in the closure that declares none SHALL be dropped after the closure is taken and before the matrix is fed. Leaving that implicit puts a matrix row on a role with no scenarios for the runner to find, which fails on a role that never had any.

Where that restriction leaves the selection empty, the selection SHALL be every discovered role. A change *confined to* such a role is not verifiable by this suite at all, and for it the alternatives are both worse than running it in full: a matrix row for a role with no scenarios fails on a role that never had any, and an empty selection fails under the refusal below. Neither can be made green by the author of a legitimate change, and a required status check SHALL NOT be unsatisfiable for a change it cannot verify.

That widening SHALL be evaluated over the selection as a whole rather than per attributed role: a pull request touching only such a role runs every role, while one touching such a role alongside a role that can be run runs the latter's selection alone. Widening for an unverifiable role buys no coverage — it is unverifiable by this suite whether or not other roles run — so the wider run is owed only where there would otherwise be nothing to run at all.

**The derivation SHALL follow, or refuse, every construction by which a scenario reaches a role**, and SHALL refuse a construction it has no rule for rather than passing over it. Following and refusing are both conformant dispositions; passing over is not. A construction not followed under-reads the graph, and under-reading loses coverage with nothing reporting; a construction refused costs a visible edit. For the same reason, a role name that is not a literal in the scenario text SHALL be refused rather than resolved or skipped.

**Refusal SHALL extend to routes outside a scenario's own directory that reach a role.** Any construction in a role's own task or handler file reaching content outside that role's directory is such a route, and is not visible to any check that walks scenario directories alone. The rule SHALL be keyed on what is reached rather than on a role being named: an include of another role's task file by path names no role, and couples the two exactly as an invocation would. Where a route cannot be closed over — a nested playbook invocation naming its playbook by expression rather than by literal — it SHALL be refused unless an explicit entry records that instance and why it is safe, keyed on the file, the construction and the target it resolves to, in the same form this repository already uses to permit such a read. A blanket exemption for the construction SHALL NOT be written in place of an entry for the instance.

**Two refusals, over different sets.** Discovery's existing obligation to fail where it finds no role carrying scenarios SHALL continue to read the tree rather than the selection — it is a fact about the repository, not about the diff, and a vanished suite SHALL NOT be reportable as a correct skip. Separately, a selection that is empty on a run that owes the suite SHALL fail: it cannot arise from the widening above, so it means the derivation is broken, and the run SHALL say so rather than hand the matrix an empty list and let the resulting skip be read.

**The aggregating job SHALL distinguish a narrowed run from a skipped one**, and SHALL name the subset it ran. Its existing refusals SHALL be unchanged: a discovery that did not succeed, and a skip on a run that asked for the suite, SHALL each still fail. It SHALL additionally fail where the matrix ran on a run that owed the suite nothing. That state is unreachable while the matrix job remains gated on whether the suite is owed rather than on the selection, and the refusal is owed anyway: the two outputs disagreeing would mean the selection and the decision to run were computed from different things, which is the defect this whole requirement exists to make visible.

Where the workflow is started by an event carrying no diff, the selection SHALL be every discovered role, by the same branch that already resolves the suite as owed on such an event, so that the two cannot come to disagree.

The derivation and its closure SHALL be checked statically, by the checks that already read these scenario definitions, under the same enumeration of this repository's own roles — so that installed Galaxy content cannot make the check report one result on a provisioned developer machine and another on a runner that has installed nothing.

#### Scenario: A pull request confined to one role runs that role and the roles converging it
- **WHEN** a pull request changes only files under one role's own directory, and other roles' scenarios converge that role
- **THEN** the matrix SHALL run that role together with every role whose scenarios converge it, directly or transitively, and SHALL NOT run any other role

#### Scenario: A role no scenario converges runs alone
- **WHEN** a pull request changes only files under the directory of a role that carries scenarios of its own and that no other role's scenarios converge
- **THEN** the matrix SHALL run that role alone

#### Scenario: A shared input runs every role
- **WHEN** a pull request changes a manifest, entry point or configuration file that determines what every scenario runs under, rather than a file under one role's directory
- **THEN** the matrix SHALL run every discovered role

#### Scenario: A path the attribution does not recognise runs every role
- **WHEN** a pull request changes a path the suite's change detection admits and this attribution has no rule for
- **THEN** the matrix SHALL run every discovered role, rather than selecting none — a path nobody anticipated SHALL widen the run rather than silently narrow it

#### Scenario: A change to a role that nothing converges and nothing tests runs every role
- **WHEN** a pull request changes only files under the directory of a role that declares no scenarios of its own and that no other role's scenarios converge
- **THEN** the matrix SHALL run every discovered role, rather than resolving to an empty selection or to a row for a role with no scenarios — a required status check SHALL NOT be left unsatisfiable for a change this suite cannot verify

#### Scenario: A role's own tasks reaching outside that role is refused
- **WHEN** the derivation reaches a construction in a role's own task or handler file that reaches content outside that role's directory, whether by naming another role or by naming a path into one
- **THEN** it SHALL fail identifying that file, rather than deriving a graph missing that edge — such a route lies outside every scenario directory and no check that walks those alone can see it

#### Scenario: An unverifiable role alongside a verifiable one does not widen the run
- **WHEN** a pull request changes files under the directory of a role that declares no scenarios and that nothing converges, and also under the directory of a role that can be run
- **THEN** the matrix SHALL run the latter's selection alone, rather than widening to every role — the unverifiable role is unverifiable whether or not the others run, so widening for it buys no coverage

#### Scenario: A role in the closure that carries no scenarios is not given a matrix row
- **WHEN** a closure contains a role declaring no scenarios alongside roles that do
- **THEN** the selection SHALL carry only the roles that can be run, and SHALL NOT carry a row for the role with no scenarios — a row the runner cannot execute fails on a role that never had anything to execute

#### Scenario: A route that cannot be closed over is permitted by instance, not by construction
- **WHEN** the derivation reaches a nested playbook invocation naming its playbook by expression rather than by literal
- **THEN** it SHALL refuse unless an explicit entry records that instance, keyed on file, construction and resolved target; exempting the construction wholesale SHALL NOT be accepted in place of such an entry

#### Scenario: A change to a role carrying no scenarios still runs the roles that converge it
- **WHEN** a pull request changes files under the directory of a role that declares no scenarios of its own, and another role's scenarios converge it
- **THEN** the matrix SHALL run those other roles, rather than resolving the change to an empty selection

#### Scenario: A construction the derivation cannot resolve fails the run
- **WHEN** the derivation reaches a scenario construction it has no rule for, or one naming a role by something other than a literal
- **THEN** it SHALL fail identifying that construction and the file holding it, rather than passing over it and deriving a graph missing that edge

#### Scenario: An empty selection on a run that owes the suite fails
- **WHEN** the suite is owed and the selection resolves to no role at all
- **THEN** the run SHALL fail identifying the selection as the cause, and the matrix SHALL NOT be handed an empty list

#### Scenario: Discovery still refuses a tree carrying no scenarios
- **WHEN** no role under the roles directory carries a scenario directory, whatever the pull request changed
- **THEN** discovery SHALL fail as it does today, reading the tree rather than the selection — a suite that has disappeared SHALL NOT be reportable as a correct skip

#### Scenario: The aggregating job names the subset it ran
- **WHEN** the matrix runs on a narrowed selection and passes
- **THEN** the aggregating job SHALL conclude success and SHALL state which roles ran and why that subset, so that a wrongly narrow run is legible to a reader of the check

#### Scenario: A matrix that ran where nothing was owed fails
- **WHEN** the matrix concludes having run on a pull request whose changed files owe the suite nothing
- **THEN** the aggregating job SHALL fail rather than conclude success — the two outputs disagreeing means the selection and the decision to run were computed from different things

#### Scenario: A run carrying no diff runs every role
- **WHEN** the workflow is started by an event that carries no diff to attribute
- **THEN** the selection SHALL be every discovered role, resolved by the same branch that resolves the suite as owed on such an event

#### Scenario: A scenario added later is covered without editing the check
- **WHEN** a scenario is added that converges a role it did not converge before, and no change is made to the static check that reads these definitions
- **THEN** the derived graph SHALL carry the new edge and the check SHALL assert the closure including it

### Requirement: The Specification Record Is Verified in Continuous Integration
This repository's own specification record — the capability specifications, the active changes and their deltas, and the task lists of archived changes — SHALL be validated by its authoring tool as part of the required pull request status check, unconditionally.

The record is the only description this pipeline has of what it is for, and it was the one thing the pipeline did not check. A specification that no longer parses, a delta that is malformed, or an archived change whose task list still claims outstanding work are each invisible to every other check here: they are not Terraform, not Ansible, and not continuous-integration configuration, so no existing tier reaches them.

Validation SHALL cover both the active record and the archived one. These are distinct properties reached by distinct invocations, and neither implies the other: the active record can be well-formed while an archived change's task list is incomplete, which is the state this requirement was introduced from.

The check SHALL run on every pull request rather than only on those that change a file under the specification directory. A record is falsified by what merged before it, not by the diff under review; a path filter would report green on precisely the pull request that carries an unrelated stale failure past it. The job enclosing the check SHALL itself be unconditional, and the workflow SHALL NOT reach it through a workflow-level path filter — a step that cannot be skipped inside a job that can is skippable. Where the enclosing job declares `needs:` — that is, where it aggregates other jobs' results — it MAY carry the single condition `always()` and no other. A job declaring dependencies is otherwise skipped whenever one of them fails, and a skipped job produces no status check context at all, which under branch protection is a required check that never reports: the same permanent-pending state a path filter produces. `always()` is admitted because it cannot evaluate false — it is the strongest available guarantee that a dependent job still runs, not a weakening of unconditionality. It is admitted as that exact literal and not as a class: in either the bare or the `${{ }}`-wrapped spelling, containing nothing else, and only on a job declaring `needs:`. No other expression is permitted by it, and neither is `always()` joined to anything.

The validating tool SHALL be installed from a manifest that pins it to an exact version and is committed to this repository, and SHALL NOT be resolved freshly at run time.

The runtime that executes it SHALL be pinned to an explicit major version, declared in the workflow and in the manifest's `engines`, rather than left to whatever the runner defaults to. This is deliberately weaker than the tool's exact pin, and the difference is stated rather than glossed: an exact patch pin on a language runtime rots into a version that stops receiving security fixes, and the failure it would prevent — a patch release changing what the validator concludes — is not one this tool's behaviour is sensitive to, where the major version is (it requires import attributes, which the runner's own default may not provide). A floating *major* would leave the pin describing nothing; an exact patch would buy precision this check cannot use at a cost it would pay every month. That manifest SHALL be covered by the repository's dependency-update configuration, so that the pin is maintained rather than left to rot — a pinned dependency nothing watches is the failure this repository has recorded against itself four times over.

An archived change whose task list records outstanding work SHALL fail this check.

Work that was not performed SHALL be disclosed in prose rather than marked complete, and the disclosure SHALL state why. Marking it complete would make a completed task mean either that the work was done or that it was not, which is no signal at all. The obligation is over work not performed for **any** reason — declined on judgment, unreachable in the authoring environment, or omitted and no longer recoverable — because an author facing a case the disclosure does not authorize will tick the box or invent a disposition, and both are worse than either honest option.

That disclosure SHALL itself be machine-checked. A prose escape from a gate, guarded only by review, is the *"guaranteed only until someone does not notice"* condition that the requirement *The Continuous-Integration Configuration Is Itself Verified* exists to refuse; an unguarded one would let this check be satisfied by relabelling an inconvenient task rather than by disclosing anything. A disclosed item that states no reason SHALL fail the check exactly as an unticked task does.

So that the reason is checkable without judging prose, a disclosure SHALL take a fixed form: under a `## Not performed` heading, a list item naming the task it replaces, carrying its reason on a following line introduced by a `Reason:` label. The heading is part of the form and not merely conventional — it is what the check scans for, so a disclosure written outside one is a disclosure the check never sees. The label is what makes silence detectable; the check SHALL assert that the label is present and its text non-empty, and SHALL NOT attempt to assess whether the reason is a good one.

A section that presents itself as such a heading SHALL NOT pass by yielding nothing. A heading the check does not recognise, or one under which no disclosure is found, SHALL fail rather than scan an empty set successfully: a disclosure section that discloses nothing is indistinguishable from a section the scanner could not read, and the second is how this check would fail open.

The check therefore reaches silence, not sufficiency, and it does not reach a task deleted outright rather than disclosed. Deletion is governed instead by the repository's own convention that an archived record may be corrected only to say what actually happened. That convention SHALL be stated in the repository-root `AGENTS.md`, and that it is stated there SHALL itself be asserted by the suite — a delegation to a rule nothing checks for is a delegation to nothing, and this is the one blind spot the check above openly concedes. That assertion establishes only that the rule is **stated**, never that it is followed; the deletion case still ends at a reviewer, and this obligation makes the rule they are reviewing against durable rather than replacing them. The assertion SHALL be written so that rephrasing the rule fails it, rather than so that a rephrasing which inverts the rule passes: this rule's wording is precisely what a reviewer relies on, and a change to it is a reviewed event rather than an editorial one.

A check that cannot fail is not a check. Neither the step nor its enclosing job SHALL suppress the validating command's failure. This obligation is stated separately because every other property in this requirement is satisfied by a step that runs unconditionally, installs from the pinned manifest, and then swallows its result: such a step exists, is not skipped, is exactly pinned, and reports green forever. That is the same defect this capability's discovery, destroy-policy gate and secret-scanning requirements each forbid elsewhere, reached by suppression rather than by omission. It SHALL be read at both levels for the same reason the unconditionality obligation above is: a step that cannot suppress its failure inside a job that can is suppressible.

That obligation SHALL be asserted statically rather than established by observing a failure, so that it holds for every later edit of the workflow and not only on the day it was introduced.

**Suppression SHALL be excluded by asserting a closed form rather than by enumerating evasions.** A check written as a list of forbidden constructions is complete only until someone writes a construction nobody listed, and each entry is added after the gap it closes has already been exploited. So the step SHALL take a shape the check can state positively and completely: its script SHALL consist of the validating invocations and nothing else — no shell operator joining them to anything, no redirection or capture of their status, and no shell override — and neither the step nor its enclosing job SHALL declare a continue-on-error setting in any form, including one whose value is an expression. Relocating the invocations into a called workflow or composite action SHALL NOT be used to escape that shape.

That closed form has a cost, which is accepted deliberately: a legitimate future edit to this step's script fails the check until the assertion is updated. For a step whose entire purpose is to be un-bypassable, an edit that must be noticed is the intended behaviour rather than friction to be designed away.

This validation SHALL NOT be performed by the executable suite that verifies the continuous-integration configuration. The requirement *The Continuous-Integration Configuration Is Itself Verified* binds that suite to its runtime's standard library and to dependencies pinned exactly in a repository manifest, and forbids it a network call, a credential, a container runtime or a Terraform binary; running a separately installed binary from inside it would defeat the first constraint whether or not it defeated the second. That suite's obligation here is the one it holds over every other check in this pipeline — to assert statically that the step exists, that it and its enclosing job are unconditional (or that the job carries `always()` alone, under the allowance above), that it installs from the pinned manifest, that neither the step nor its enclosing job suppresses the validating command's failure and that the step still holds the closed form above, and that every disclosure of unperformed work — in any `tasks.md` under the changes directory, archived or active — carries a `Reason:` label with non-empty text, and that the correction convention above is stated in `AGENTS.md`.

#### Scenario: A malformed specification or delta fails the pull request that introduces it
- **WHEN** a pull request changes the specification record such that it no longer validates
- **THEN** the required status check SHALL fail on that pull request

#### Scenario: An archived change with outstanding tasks fails the pull request that archives it
- **WHEN** a pull request archives a change whose task list still records work as outstanding
- **THEN** the required status check SHALL fail on that pull request rather than reporting success

#### Scenario: Unperformed work disclosed without a reason fails the check
- **WHEN** an archived change discloses work as not performed and carries no `Reason:` label, or carries one whose text is empty
- **THEN** the required status check SHALL fail on that pull request, as it would for an unticked task

#### Scenario: A disclosure section the check cannot read fails rather than passing
- **WHEN** an archived change carries a section that presents itself as disclosing unperformed work, and the check recognises no disclosure within it
- **THEN** the required status check SHALL fail, rather than reporting success over a section it could not read

#### Scenario: The check cannot report success over a failed validation
- **WHEN** the validating command exits non-zero
- **THEN** the step SHALL fail and the required status check SHALL fail with it, and neither the step nor its enclosing job SHALL be configured to continue past it or to discard its exit status

#### Scenario: The validation runs regardless of what a pull request touched
- **WHEN** a pull request changes no file under the specification directory
- **THEN** the required status check SHALL still validate the record and report its result

#### Scenario: The validating tool is not resolved freshly at run time
- **WHEN** the check installs the tool it validates with
- **THEN** it SHALL install the exact version the committed manifest pins, on a runtime whose major version the workflow names explicitly, and SHALL fail rather than proceed where the manifest and its lockfile disagree

#### Scenario: The pin is watched by the dependency-update configuration
- **WHEN** a new version of the validating tool is published
- **THEN** the repository's dependency-update configuration SHALL raise it as a reviewable pull request rather than leaving the pin to be noticed by a person

### Requirement: Scheduled Workflows Report Their Own Liveness
Every workflow in this repository triggered by `schedule:` SHALL report the outcome of each scheduled run to an **external** observer that raises an alarm when the report does not arrive. Reporting a failure is not sufficient on its own and SHALL NOT be treated as satisfying this requirement: the observer SHALL alarm on **silence**, so that a run that failed, a run killed mid-flight, and a run that never started at all are equally visible.

The second of those is the one no failure-triggered mechanism can reach. GitHub disables schedule-triggered workflows after 60 days of repository inactivity — the condition the *Scheduled Drift Detection* requirement in this capability already names, and for which the README carries a manual re-enable procedure — and a disabled workflow emits no failure, no run and no notification. A mechanism that only reacts to red runs reports a disabled workflow as healthy forever.

The observer SHALL NOT be a workflow in this repository. A watcher that is itself schedule-triggered is subject to every failure mode it exists to detect, and its own silence would be indistinguishable from the silence it is watching for.

Each such workflow SHALL address its own report by an identifier that is a **literal in the workflow file**, distinct per workflow, so that the obligation is a static read of a committed file. That the repository's schedule-triggered workflows each carry such a report SHALL be asserted by the executable suite required by *The Continuous-Integration Configuration Is Itself Verified* in this capability — a scheduled workflow added later without one is a pull request that fails, not a gap discovered by a reader.

The credential that report is sent under SHALL be repository-scoped and SHALL NOT be an Environment secret. Secrets on the `production` Environment are readable only by a job that declares that Environment, and such a job waits on required-reviewer approval per *Gated Production Apply Applies the Reviewed Plan* in this capability. An alarm that waits for a human to approve its own delivery is not an alarm.

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

### Requirement: Each Environment Declares Its Own Pipeline Configuration
Every directory under `terraform/environments/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that environment. Two fields are **required**: the name of the GitHub Environment its apply job attaches to, and the name of the repository secret holding its read-only Hetzner token. A third is **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves).

The optional field SHALL name the **gate**, not its inverse — the value states whether the gate applies, rather than whether the environment is disposable. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting this one silently removes the strongest guard on an apply.

Adding an environment SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate environments, name them in a condition, or map an environment to its secrets or its Environment name in workflow text. A pipeline that must be edited to add an environment is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. An environment still needs its own state workspace, its own GitHub Environment and secrets, an inventory source and a `group_vars` file of its own for the host-configuration workflow to converge it, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each environment's declared read-only secret name SHALL be distinct from every other environment's, and so SHALL its declared GitHub Environment name. Two environments naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so an environment intended to be ungated would hold the reviewed environment's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each environment's Read & Write token in that environment's own GitHub Environment. Both are the defect a per-environment declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

**No environment's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every environment.** Credential Scoping by Privilege requires each environment's GitHub Environment to define `HCLOUD_TOKEN` as that environment's Read & Write token, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. A declaration naming `HCLOUD_TOKEN` as its read-only secret is therefore correct only for a job that declares no `environment:`; read from a job that declares one, the same name yields the **write** token, silently and with no error. The declared name is read by gated jobs as well as ungated ones, so the name SHALL be one no Environment shadows.

Discovery SHALL fail closed. An environment directory whose declaration is absent, unparseable, or missing either **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped environment is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the environment not existing and is exactly the condition this capability is meant to make impossible.

#### Scenario: A new environment needs no workflow edit
- **WHEN** a directory is added under `terraform/environments/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply, drift and host-converge workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: Two environments declaring the same read-only secret are refused
- **WHEN** two environment declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both environments, rather than running two environments' plans under one credential

#### Scenario: Two environments declaring the same GitHub Environment are refused
- **WHEN** two environment declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both environments, rather than applying two environments under one write token and one set of protection rules

#### Scenario: A declaration naming the write token's own name is refused
- **WHEN** an environment declaration names as its read-only secret a name that every GitHub Environment defines for its Read & Write token
- **THEN** the required status check SHALL fail, naming that environment, rather than leaving a gated job to resolve a write credential from a field that says read-only

#### Scenario: An environment missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/environments/` has no pipeline declaration, or one lacking either required field
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the environment from the matrix

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over `terraform/environments/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

### Requirement: Host Configuration Is Applied by a Gated Workflow
Host configuration SHALL reach a host through a workflow triggered by a merge to the default branch. A converge changes the host firewall, the accounts that may log in and the container runtime, so the path by which it reaches a host SHALL be gated in the same way the Terraform apply and the platform deploy are.

**One converge is exempt, and only one: a host's first.** Before that run the host is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with, so the first converge is necessarily an operator's, from a workstation, over the host's public address. Every converge after it SHALL reach the host through the workflow. The exemption is bounded by the host's own bootstrap and SHALL NOT be read as permitting a workstation converge of a host already configured.

The workflow SHALL separate publishing from converging, in a single run. A job that holds **no** credential capable of reaching a host SHALL publish, for a human to read, what the merge changes under the host-configuration directory. A converge job **per environment** SHALL declare that environment's own GitHub Environment, taken from that environment's committed pipeline declaration, and SHALL be the only job holding the credentials a converge needs.

The publishing job is **not** obliged to be per environment, and this requirement deliberately does not make it one. What it publishes is the committed diff, which is the same document whatever environment reads it — a copy per environment would be identical in every row, and would put the number of jobs a merge starts in proportion to something the diff does not depend on. What SHALL be per environment is the credential and the gate.

This layer has no saved-plan artifact and SHALL NOT pretend to one. A check-mode run is not one: it skips `command` tasks, it swallows failures in roles that ignore errors under check mode, and it must authenticate to the host — so it could only run in the job the gate exists to withhold the credential from. What the pre-approval job publishes is the committed diff, which for this layer is complete: every input a converge applies is committed, so there is no value computed elsewhere that the diff omits.

The workflow SHALL name no environment. Which environments exist, which GitHub Environment gates each, and which repository secret holds each one's read-only credential SHALL come from discovery over committed files, and adding an environment SHALL require no change to any file under `.github/workflows/`.

Discovery SHALL fail closed, with a message naming the environment and what was wrong, rather than omitting an environment from the run. An environment that can be provisioned but not converged, and one that can be converged but is gated by nothing, are both states this discovery SHALL refuse rather than pass over: an environment whose host is converged by no job is indistinguishable from an environment that has nothing to converge.

A converge job SHALL establish that the credentials it holds are usable — that the environment's secrets decrypt and that its inventory resolves — **before** any task acts on the host. Those inputs are decrypted at the moment they are first used, which is several roles into the play, so a run that starts with a wrong secret would otherwise leave a partially-converged host for a reason that had nothing to do with the host.

A converge job SHALL install the toolchain and the external content the play needs before running it, from this repository's own pinned manifests, and SHALL run from the directory whose configuration governs the run. A continuous-integration runner carries neither, and a run that reaches a missing plugin or a missing external role fails inside a mechanism, reading as a broken mechanism rather than as an unprovisioned machine. Running from the wrong directory is worse than failing: the configuration that makes a rejected credential fail the run is not loaded, so the run continues and reports a rejected credential as an environment whose server does not exist.

The version of Ansible a converge runs SHALL be the version the role-verification suite runs. A converge applying roles under a different Ansible than the one they were verified under is verified by nothing, and the agreement SHALL be asserted rather than intended, being a static read of two committed files.

A converge SHALL NOT be cancelled in favour of a later one. Runs against one environment SHALL be serialised, and an in-flight converge SHALL be allowed to finish: interrupting a play mid-run leaves the host partially converged, which is recoverable as an exception and not as a normal case.

One environment's converge failing SHALL NOT prevent another environment's from running and reporting.

#### Scenario: A merge to the host configuration converges without a workstation
- **WHEN** a merge to the default branch changes the host-configuration directory
- **THEN** each already-configured environment's host SHALL be converged by the workflow, and no step of that converge SHALL require a command run from an operator's machine

#### Scenario: A host's first converge is the operator's
- **WHEN** a host has not been converged before, so it is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with
- **THEN** that one converge MAY be run from a workstation over the host's public address, and every converge of that host afterwards SHALL reach it through the workflow

#### Scenario: The pre-approval job holds no converge credential
- **WHEN** the job that publishes what the merge changes runs
- **THEN** it SHALL declare no GitHub Environment and SHALL consume no credential capable of reaching a host

#### Scenario: The converge job is gated on the environment's own GitHub Environment
- **WHEN** a converge job runs for an environment
- **THEN** it SHALL declare the GitHub Environment named by that environment's own pipeline declaration, so that its protection rules and its secrets are the ones that apply

#### Scenario: An environment that cannot be converged fails the workflow
- **WHEN** discovery finds an environment declaring a pipeline configuration but carrying no host-configuration inventory source, or an inventory source whose environment declares no pipeline configuration
- **THEN** the workflow SHALL fail with a message naming that environment and which side is missing, rather than converging the environments it could resolve

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over the host-configuration inventory sources yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

#### Scenario: A run is requested for an environment that does not exist
- **WHEN** a converge is requested by hand naming an environment discovery did not find
- **THEN** the run SHALL fail naming the environments that were found, rather than converging none and reporting success

#### Scenario: A wrong secret stops the run before the host is touched
- **WHEN** a converge job holds a credential that does not decrypt that environment's committed secrets, or a credential its inventory source rejects
- **THEN** the run SHALL fail before the first role acts on the host, rather than partway through the play

#### Scenario: The converge job supplies what the run needs
- **WHEN** a converge job runs on a continuous-integration runner, which carries no external content of its own
- **THEN** it SHALL have installed the toolchain and the external content the play needs from this repository's pinned manifests, and SHALL run from the directory whose configuration governs the run

#### Scenario: The converge runs the Ansible the roles were verified under
- **WHEN** the version the converge job installs is compared with the version the role-verification suite installs
- **THEN** the two SHALL be the same, and a difference SHALL fail the required status check

#### Scenario: One environment's failure does not silence another's
- **WHEN** a converge fails for one environment in a run covering several
- **THEN** every other environment's converge SHALL still run and report its own outcome
