## ADDED Requirements

### Requirement: Each Environment Declares Its Own Pipeline Configuration
Every directory under `terraform/environments/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that environment. Two fields are **required**: the name of the GitHub Environment its apply job attaches to, and the name of the repository secret holding its read-only Hetzner token. A third is **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves).

The optional field SHALL name the **gate**, not its inverse — the value states whether the gate applies, rather than whether the environment is disposable. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting this one silently removes the strongest guard on an apply.

Adding an environment SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate environments, name them in a condition, or map an environment to its secrets or its Environment name in workflow text. A pipeline that must be edited to add an environment is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. An environment still needs its own state workspace, its own GitHub Environment and secrets, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each environment's declared read-only secret name SHALL be distinct from every other environment's, and so SHALL its declared GitHub Environment name. Two environments naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so an environment intended to be ungated would hold the reviewed environment's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each environment's Read & Write token in that environment's own GitHub Environment. Both are the defect a per-environment declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

Discovery SHALL fail closed. An environment directory whose declaration is absent, unparseable, or missing either **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped environment is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the environment not existing and is exactly the condition this capability is meant to make impossible.

#### Scenario: A new environment needs no workflow edit
- **WHEN** a directory is added under `terraform/environments/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply and drift workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: Two environments declaring the same read-only secret are refused
- **WHEN** two environment declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both environments, rather than running two environments' plans under one credential

#### Scenario: Two environments declaring the same GitHub Environment are refused
- **WHEN** two environment declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both environments, rather than applying two environments under one write token and one set of protection rules

#### Scenario: An environment missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/environments/` has no pipeline declaration, or one lacking either required field
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the environment from the matrix

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over `terraform/environments/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

## MODIFIED Requirements

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

State locking alone prevents concurrent state mutation but does not prevent two runs from applying out of order — the later merge's apply may acquire the lock first and be overwritten by the earlier one.

#### Scenario: Two merges in quick succession apply in order
- **WHEN** two pull requests affecting the same environment are merged to `main` within a short interval
- **THEN** the second apply run SHALL queue until the first completes, and SHALL NOT cancel it or run concurrently with it

#### Scenario: Two environments do not queue behind each other
- **WHEN** an apply against one environment is in progress and an apply against a different environment begins
- **THEN** the second SHALL proceed without waiting on the first

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

The suite SHALL depend only on its runtime's standard library and on dependencies pinned exactly in a repository manifest, and SHALL require no network access, credential, container runtime or Terraform binary — it gates every pull request, including those that change nothing it asserts about.

#### Scenario: A regression in CI configuration fails the pull request that introduces it
- **WHEN** a pull request changes the continuous-integration configuration such that a property this capability requires no longer holds
- **THEN** the required status check SHALL fail on that pull request

#### Scenario: The suite runs regardless of what a pull request touched
- **WHEN** a pull request changes no file under `.github/`
- **THEN** the required status check SHALL still run the suite and report its result

#### Scenario: The suite needs no privileged or external resource
- **WHEN** the suite runs in continuous integration
- **THEN** it SHALL complete without a network call, a credential, a container runtime or a Terraform binary

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
