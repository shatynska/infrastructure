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
When validation checks pass, the workflow SHALL run `terraform plan` against the prod environment and post the full plan output as a comment on the pull request.

#### Scenario: Reviewer sees the plan without leaving GitHub
- **WHEN** validation checks pass on a pull request that changes `terraform/environments/prod/` or `terraform/modules/`
- **THEN** the workflow SHALL post the resulting `terraform plan` output as a PR comment, viewable directly in the GitHub pull request

### Requirement: Credential Scoping by Privilege
Authentication secrets SHALL be split by privilege so that automatically-running jobs (PR-time and scheduled `terraform plan`) only ever have read-only access to Hetzner Cloud, while write access is confined to the approval-gated apply job.

Two Hetzner Cloud API tokens SHALL be provisioned: a **Read Only** token and a **Read & Write** token. `TF_API_TOKEN` (HCP Terraform access) is placed using the same repository/Environment secret pair for structural consistency, but SHALL NOT be assumed to carry the same privilege split — see the HCP Terraform Access via a Static Token, Unsplit by Privilege requirement in the iac-state-management capability, which is the actual source of truth for what that token can and cannot do. All SHALL be placed as follows, relying on GitHub resolving an environment-scoped secret ahead of a repository-scoped secret of the same name (a job declaring `environment: production` receives the environment value; any other job receives the repository value):

| Secret | Location | Value |
|---|---|---|
| `HCLOUD_TOKEN` | Repository secret (Settings → Secrets and variables → Actions) | Read Only Hetzner token |
| `HCLOUD_TOKEN` | `production` Environment secret | Read & Write Hetzner token |
| `TF_API_TOKEN` | Repository secret | HCP Terraform token (unsplit — see iac-state-management) |
| `TF_API_TOKEN` | `production` Environment secret | Same HCP Terraform token value, kept as a separate secret so a future privilege split needs no workflow changes |

`HCLOUD_TOKEN` SHALL NOT be an organization-wide or admin-level credential, and its Read Only/Read & Write split remains the load-bearing privilege boundary for this pipeline, precisely because `TF_API_TOKEN` is currently unsplit by necessity (see iac-state-management).

This requirement governs where the two tokens live *inside GitHub*. Confining the Read & Write token so that it never reaches a workstation — where the workspace's Local execution mode would let it bypass this pipeline entirely — is specified by the Write Credentials Confined to the Gated Pipeline requirement in the iac-safety-hardening capability.

No job that runs `terraform plan` SHALL declare `environment: production`. Doing so would both block the job on manual approval — making every pull request require an approval click — and resolve `HCLOUD_TOKEN` to the write-capable token in an ungated job, defeating the split entirely.

#### Scenario: Plan jobs receive only a read-only Hetzner token
- **WHEN** a PR-time or scheduled `terraform plan` job runs without declaring `environment: production`
- **THEN** its `HCLOUD_TOKEN` SHALL resolve to the repository-scoped Read Only token, which cannot create, modify, or destroy Hetzner resources

#### Scenario: Apply job receives the read-write Hetzner token only after approval
- **WHEN** the apply job runs after the `production` Environment approval is granted
- **THEN** its `HCLOUD_TOKEN` SHALL resolve to the environment-scoped Read & Write token, and that token SHALL NOT be readable by any job that has not passed the approval gate

#### Scenario: Pull request validation requires no manual approval
- **WHEN** a pull request opens and the validation and plan workflow runs
- **THEN** it SHALL execute to completion without pausing for any GitHub Environment approval

### Requirement: Gated Production Apply Applies the Reviewed Plan
`terraform apply` against the prod environment SHALL run only after a pull request is merged to `main`, SHALL require manual approval via the `production` GitHub Environment protection rule, and SHALL apply a **saved plan file produced before approval** rather than recomputing a plan after approval.

The apply workflow SHALL be structured as two jobs in a single run:

1. A **plan job** that declares no `environment:`, runs `terraform plan -out=tfplan`, writes the human-readable plan to the run's job summary, and uploads `tfplan` as a workflow artifact.
2. An **apply job** that depends on the plan job, declares `environment: production`, and on approval downloads `tfplan` and runs `terraform apply tfplan`.

This ensures the approving reviewer sees the exact diff that will be applied. A workflow that approves first and plans afterwards gives the reviewer no diff to evaluate, and the plan computed after approval may differ from the one reviewed on the pull request due to the merge commit, intervening drift, or a provider version change.

The apply workflow SHALL be triggered only by pushes that can affect the Terraform configuration, identified by a workflow-level path filter. A merge that cannot change infrastructure SHALL NOT raise a `production` Environment approval request. An approval prompt that appears on merges with nothing to approve trains the approver to grant it without reading, which defeats the gate it exists to enforce; out-of-band divergence remains covered by scheduled drift detection rather than by an approval request per merge.

This path filter is permissible **only** because the apply workflow is not a required status check. Any workflow that is registered as a required check SHALL NOT be path-filtered at the workflow level — see the Required Status Checks Report on Every Pull Request requirement, whose constraint is the opposite of this one and takes precedence for those workflows. There is more than one such workflow, and the constraint holds of each.

Because a saved plan file stores sensitive values in cleartext, the `tfplan` artifact SHALL be treated as a secret: retention SHALL be set to the shortest workable period, and the artifact SHALL NOT be produced in a public repository without symmetric encryption using a key held in repository secrets.

#### Scenario: Merge does not apply immediately
- **WHEN** a pull request changing `terraform/environments/prod/` is merged to `main`
- **THEN** the apply job SHALL pause and wait for a required reviewer to approve the `production` GitHub Environment before running `terraform apply`

#### Scenario: Reviewer sees the exact diff before approving
- **WHEN** the apply job is pending approval
- **THEN** the completed plan job's summary SHALL already display the full plan output for the merge commit, so the reviewer can read the pending changes before granting approval

#### Scenario: Applied changes match the approved plan
- **WHEN** approval is granted and the apply job runs
- **THEN** it SHALL apply the saved `tfplan` artifact produced by the plan job, and SHALL error rather than apply divergent changes if remote state has changed since that plan was saved

#### Scenario: Apply credentials are inaccessible before approval
- **WHEN** the apply workflow run is pending approval
- **THEN** the read-write `HCLOUD_TOKEN` scoped to the `production` Environment SHALL NOT be readable by the workflow job until approval is granted

#### Scenario: A merge that cannot change infrastructure raises no approval request
- **WHEN** a pull request changing only documentation, Ansible or platform files is merged to `main`
- **THEN** the apply workflow SHALL NOT run, and no `production` Environment approval SHALL be requested

### Requirement: Destroy Policy Gate
The gated production apply workflow's plan job (Job A, per the Gated Production Apply Applies the Reviewed Plan requirement) SHALL inspect its plan's machine-readable form (`terraform show -json`) and SHALL fail the workflow when the plan contains any resource action of `delete` or `replace`, unless the change carries an explicit override signal (assumed to be a pull request label).

The gate SHALL fail closed. It SHALL proceed only on a positive determination that the plan contains no destructive action; any outcome in which that determination could not be made — the plan could not be rendered to JSON, the inspection command failed, or the inspection produced anything other than an explicit negative result — SHALL fail the workflow with a message distinguishing it from a plan that was inspected and found clean. Treating "the plan could not be inspected" as "the plan is safe" removes the gate precisely when something is already wrong.

This gate applies only to the plan Job B would apply. It does NOT apply to the pull request's informational `terraform plan` (Pull Request Plan Visibility) — which gates nothing yet, since apply happens only after merge — nor to the nightly drift-detection plan (Scheduled Drift Detection), which is read-only and reports rather than blocks.

This is the Terraform-side guard against destructive applies. It replaces reliance on `lifecycle { prevent_destroy = true }` in shared modules, which cannot be parameterized per environment and only covers individually annotated resources. The gate covers every resource in the plan automatically and surfaces the objection where it can be discussed rather than as an opaque Terraform error.

#### Scenario: Unintended resource replacement blocks the pipeline
- **WHEN** the apply workflow's plan job shows the server being replaced because an immutable attribute changed, and the pull request carries no override label
- **THEN** the destroy-policy gate SHALL fail the workflow and report which resources would be destroyed or replaced, and no apply SHALL run

#### Scenario: Deliberate teardown is possible with explicit acknowledgement
- **WHEN** an operator intends a destructive change and applies the override label to the pull request
- **THEN** the destroy-policy gate SHALL pass and the change SHALL proceed to the normal approval gate, which still requires reviewer approval

#### Scenario: An uninspectable plan blocks the pipeline
- **WHEN** the destroy-policy gate cannot determine whether the plan contains a destructive action, because rendering or inspecting the plan's machine-readable form failed
- **THEN** the gate SHALL fail the workflow with a message identifying the inspection as the cause, and SHALL NOT report that the plan contains no destructive actions

#### Scenario: Drift-detection plan is not affected by this gate
- **WHEN** the nightly drift-detection plan (Scheduled Drift Detection) shows a resource being deleted or replaced
- **THEN** the destroy-policy gate SHALL NOT fail that workflow; the drift is instead reported per the Scheduled Drift Detection requirement

### Requirement: Serialized Terraform Runs
Workflows that run `terraform apply` against an environment SHALL declare a GitHub Actions `concurrency` group per environment with `cancel-in-progress: false`, so that runs queue rather than overlap or cancel each other.

State locking alone prevents concurrent state mutation but does not prevent two runs from applying out of order — the later merge's apply may acquire the lock first and be overwritten by the earlier one.

#### Scenario: Two merges in quick succession apply in order
- **WHEN** two pull requests are merged to `main` within a short interval
- **THEN** the second apply run SHALL queue until the first completes, and SHALL NOT cancel it or run concurrently with it

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
A scheduled GitHub Actions workflow SHALL run `terraform plan` against the prod environment on a recurring nightly schedule, without applying any changes, to surface divergence between the committed configuration and actual infrastructure state. This plan is read-only and reporting-only: it does not invoke the Destroy Policy Gate, which applies only to the apply workflow's plan (see that requirement).

When the plan shows a non-empty diff, the workflow SHALL create or update a **single, deduplicated** GitHub issue containing the diff, and SHALL close or resolve it when a later run finds no drift. Failing the workflow alone is insufficient: a persistently red scheduled job is muted in practice, leaving drift undetected.

The workflow SHALL also be triggerable via `workflow_dispatch`, and its plan SHALL run with `-lock=false`. GitHub automatically disables scheduled workflows after 60 days of repository inactivity — a likely occurrence for an infrastructure repository — so manual triggering is required both as a fallback and to verify the workflow after re-enabling. Running without the state lock prevents a read-only nightly plan from colliding with an in-flight apply and reporting a spurious failure.

#### Scenario: Manual out-of-band change is detected
- **WHEN** a resource in the dedicated prod Hetzner Cloud project is modified outside of Terraform (e.g. via the Hetzner console) and the nightly drift-detection workflow next runs
- **THEN** the resulting `terraform plan` SHALL show a non-empty diff, and the workflow SHALL record it on a dedicated drift issue, without applying any change

#### Scenario: Repeated drift does not open duplicate issues
- **WHEN** the drift-detection workflow runs on consecutive nights and the same drift is still present
- **THEN** it SHALL update the existing drift issue rather than opening an additional one

#### Scenario: Resolved drift closes the report
- **WHEN** drift previously reported on the drift issue is resolved and the next scheduled run produces an empty plan
- **THEN** the workflow SHALL close or mark the drift issue resolved

#### Scenario: Drift plan does not contend with an apply
- **WHEN** the scheduled drift plan runs while an approved `terraform apply` holds the state lock
- **THEN** the drift plan SHALL proceed without waiting on or failing due to the lock, because it runs with `-lock=false`

### Requirement: The Continuous-Integration Configuration Is Itself Verified
The properties this capability requires of its own configuration — which checks are gated on which paths, which versions are pinned where, which jobs declare a deployment `environment:`, and which directories a dependency-update configuration covers — SHALL be asserted by an executable test suite, and that suite SHALL run on every pull request as part of the required status check, unconditionally.

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

### Requirement: Ansible Configuration Is Verified in Continuous Integration and Gates the Merge
Every pull request that changes files under `ansible/` SHALL trigger continuous-integration checks over that configuration. Both tiers block a merge; they remain distinguished by cost, which governs how each is triggered rather than whether it gates.

**Lint tier.** `ansible-lint` and `ansible-playbook --syntax-check` SHALL run as part of the required pull request status check, using the same invocation the repository's `pre-commit` configuration uses locally, so that a pull request cannot merge with Ansible content that fails either. These checks require no container runtime and no credential.

**Suite tier.** The Molecule suite SHALL run in continuous integration on pull requests changing `ansible/`, and SHALL be registered as a required status check. Its scenarios exercise host-level firewalling, `fail2ban` and service management inside containers; that these are reproducible on a hosted runner is established by consecutive green runs on pull requests with independent subjects, which is what the previously advisory tier existed to observe. A scenario that fails SHALL block the merge.

Because the suite is costly and the lint tier is not, the suite SHALL be triggered by change detection *inside* an always-running workflow rather than by a workflow-level path filter, per the requirement above, and a pull request touching nothing under `ansible/` SHALL start no container. Its conclusion SHALL be reported by an aggregating job whose name is a literal, which SHALL fail where the suite was skipped on a pull request that did change files under `ansible/`.

Change detection resolves against a pull request's diff. Where the workflow is started by any other event there is no diff to resolve against, and the suite SHALL run in full rather than defaulting to skipped. A default of skipped would report a green conclusion on precisely the trigger this repository uses to observe the suite against the trunk.

Discovery SHALL declare the least privilege its change detection needs, per the *Least-Privilege Workflow Permissions* requirement, and SHALL receive no write scope: reading which files a pull request touched is a read.

The Molecule run SHALL discover role scenarios rather than enumerate them, so that a role or scenario added under `ansible/roles/` is covered without a workflow edit, and SHALL execute every scenario a role declares rather than only its `default` scenario.

Discovery SHALL fail loudly rather than succeed vacuously: where it finds no role to run, the run SHALL fail with a message identifying discovery as the cause, and SHALL NOT report success. A discovery that silently matches nothing is indistinguishable from a suite that passed, which is the same defect this capability's destroy-policy gate and secret scanning requirements each forbid elsewhere. Discovery SHALL run on every pull request rather than only on those changing `ansible/`: a repository state in which no role carries scenarios has lost the check that gates every merge, and the pull request that removes it is not the only one that should stop.

The Molecule run SHALL install its toolchain from the repository's exact pinned manifests — `ansible/requirements-test.txt` for the Python toolchain and `ansible/requirements.yml` for Galaxy content — and SHALL NOT resolve any dependency version freshly at run time.

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

#### Scenario: A newly added role scenario runs without a workflow change
- **WHEN** a pull request adds a scenario directory under `ansible/roles/<role>/molecule/`, and no change is made to the workflow to name that role or scenario
- **THEN** the Molecule run SHALL still execute that scenario

#### Scenario: Every scenario a role declares is executed
- **WHEN** the Molecule run reaches a role that declares more than one scenario
- **THEN** it SHALL execute all of that role's scenarios, not only the `default` scenario

#### Scenario: Discovering no roles fails rather than passes
- **WHEN** the Molecule run's role discovery yields an empty set
- **THEN** the run SHALL fail with a message identifying discovery as the cause, rather than concluding successfully having executed no scenario

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

### Requirement: The Specification Record Is Verified in Continuous Integration
This repository's own specification record — the capability specifications, the active changes and their deltas, and the task lists of archived changes — SHALL be validated by its authoring tool as part of the required pull request status check, unconditionally.

The record is the only description this pipeline has of what it is for, and it was the one thing the pipeline did not check. A specification that no longer parses, a delta that is malformed, or an archived change whose task list still claims outstanding work are each invisible to every other check here: they are not Terraform, not Ansible, and not continuous-integration configuration, so no existing tier reaches them.

Validation SHALL cover both the active record and the archived one. These are distinct properties reached by distinct invocations, and neither implies the other: the active record can be well-formed while an archived change's task list is incomplete, which is the state this requirement was introduced from.

The check SHALL run on every pull request rather than only on those that change a file under the specification directory. A record is falsified by what merged before it, not by the diff under review; a path filter would report green on precisely the pull request that carries an unrelated stale failure past it. The job enclosing the check SHALL itself be unconditional, and the workflow SHALL NOT reach it through a workflow-level path filter — a step that cannot be skipped inside a job that can is skippable.

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

This validation SHALL NOT be performed by the executable suite that verifies the continuous-integration configuration. The requirement *The Continuous-Integration Configuration Is Itself Verified* binds that suite to its runtime's standard library and to dependencies pinned exactly in a repository manifest, and forbids it a network call, a credential, a container runtime or a Terraform binary; running a separately installed binary from inside it would defeat the first constraint whether or not it defeated the second. That suite's obligation here is the one it holds over every other check in this pipeline — to assert statically that the step exists, that it and its enclosing job are unconditional, that it installs from the pinned manifest, that neither the step nor its enclosing job suppresses the validating command's failure and that the step still holds the closed form above, and that every disclosure of unperformed work — in any `tasks.md` under the changes directory, archived or active — carries a `Reason:` label with non-empty text, and that the correction convention above is stated in `AGENTS.md`.

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
