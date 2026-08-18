## ADDED Requirements

### Requirement: Pull Request Validation Checks
Every pull request that changes Terraform configuration SHALL trigger a GitHub Actions workflow that runs `terraform fmt -check`, `terraform validate`, `tflint`, Trivy misconfiguration scanning, and `gitleaks` secret scanning.

`gitleaks` SHALL be invoked as its CLI binary rather than via the `gitleaks/gitleaks-action` marketplace action, because that action requires a paid license key for organization-owned repositories and its v2 runtime is removed from GitHub-hosted runners on 2026-09-16.

#### Scenario: PR with a misconfiguration fails validation
- **WHEN** a pull request introduces a Terraform resource with a Trivy-detectable misconfiguration (e.g. an overly permissive firewall rule)
- **THEN** the validation workflow SHALL fail and report the finding on the pull request

#### Scenario: PR with a leaked credential fails validation
- **WHEN** a pull request's diff contains content matching a `gitleaks` secret pattern
- **THEN** the validation workflow SHALL fail before any `terraform plan` is executed

#### Scenario: Secret scanning requires no third-party license
- **WHEN** the validation workflow runs its secret-scanning step
- **THEN** it SHALL complete without requiring a `GITLEAKS_LICENSE` secret or any other paid license credential

### Requirement: Required Status Checks Report on Every Pull Request
The pull request check that is registered as a required status check SHALL report a conclusion on every pull request, including pull requests that touch no Terraform files.

Terraform work MAY be path-filtered, but the filtering SHALL occur *inside* an always-running job rather than via a workflow-level `paths` filter. A workflow-level `paths` filter on a required check never reports for non-matching pull requests, leaving those pull requests permanently unmergeable under the branch protection rule below.

#### Scenario: Documentation-only pull request remains mergeable
- **WHEN** a pull request changes only files outside `environments/` and `modules/` (e.g. a README)
- **THEN** the required status check SHALL report success rather than remaining pending, and the pull request SHALL be mergeable

### Requirement: Pull Request Plan Visibility
When validation checks pass, the workflow SHALL run `terraform plan` against the prod environment and post the full plan output as a comment on the pull request.

#### Scenario: Reviewer sees the plan without leaving GitHub
- **WHEN** validation checks pass on a pull request that changes `environments/prod/` or `modules/`
- **THEN** the workflow SHALL post the resulting `terraform plan` output as a PR comment, viewable directly in the GitHub pull request

### Requirement: Credential Scoping by Privilege
Authentication secrets SHALL be split by privilege so that automatically-running jobs (PR-time and scheduled `terraform plan`) only ever have read-only access to Hetzner Cloud, while write access is confined to the approval-gated apply job.

Two Hetzner Cloud API tokens SHALL be provisioned: a **Read Only** token and a **Read & Write** token. The same split-by-privilege pattern SHALL apply to HCP Terraform access, per the HCP Terraform Access Split by Privilege requirement in the iac-state-management capability. All SHALL be placed as follows, relying on GitHub resolving an environment-scoped secret ahead of a repository-scoped secret of the same name (a job declaring `environment: production` receives the environment value; any other job receives the repository value):

| Secret | Location | Value |
|---|---|---|
| `HCLOUD_TOKEN` | Repository secret (Settings → Secrets and variables → Actions) | Read Only Hetzner token |
| `HCLOUD_TOKEN` | `production` Environment secret | Read & Write Hetzner token |
| `TF_API_TOKEN` | Repository secret | HCP Terraform token from a team with Plan-only permission on `infrastructure-prod` |
| `TF_API_TOKEN` | `production` Environment secret | HCP Terraform token from a team with Write permission on `infrastructure-prod` |

Neither `HCLOUD_TOKEN` nor `TF_API_TOKEN` SHALL be an organization-wide or admin-level credential.

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

Because a saved plan file stores sensitive values in cleartext, the `tfplan` artifact SHALL be treated as a secret: retention SHALL be set to the shortest workable period, and the artifact SHALL NOT be produced in a public repository without symmetric encryption using a key held in repository secrets.

#### Scenario: Merge does not apply immediately
- **WHEN** a pull request changing `environments/prod/` is merged to `main`
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

### Requirement: Destroy Policy Gate
The gated production apply workflow's plan job (Job A, per the Gated Production Apply Applies the Reviewed Plan requirement) SHALL inspect its plan's machine-readable form (`terraform show -json`) and SHALL fail the workflow when the plan contains any resource action of `delete` or `replace`, unless the change carries an explicit override signal (assumed to be a pull request label).

This gate applies only to the plan Job B would apply. It does NOT apply to the pull request's informational `terraform plan` (Pull Request Plan Visibility) — which gates nothing yet, since apply happens only after merge — nor to the nightly drift-detection plan (Scheduled Drift Detection), which is read-only and reports rather than blocks.

This is the Terraform-side guard against destructive applies. It replaces reliance on `lifecycle { prevent_destroy = true }` in shared modules, which cannot be parameterized per environment and only covers individually annotated resources. The gate covers every resource in the plan automatically and surfaces the objection where it can be discussed rather than as an opaque Terraform error.

#### Scenario: Unintended resource replacement blocks the pipeline
- **WHEN** the apply workflow's plan job shows the server being replaced because an immutable attribute changed, and the pull request carries no override label
- **THEN** the destroy-policy gate SHALL fail the workflow and report which resources would be destroyed or replaced, and no apply SHALL run

#### Scenario: Deliberate teardown is possible with explicit acknowledgement
- **WHEN** an operator intends a destructive change and applies the override label to the pull request
- **THEN** the destroy-policy gate SHALL pass and the change SHALL proceed to the normal approval gate, which still requires reviewer approval

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
The `main` branch SHALL be protected such that changes arrive only via pull request: direct pushes and force-pushes SHALL be rejected, a pull request SHALL be required, and the validation workflow's status check SHALL be required to pass before merge.

Every other safeguard in this capability — plan review, the destroy-policy gate, and the approval-gated apply — assumes changes reach `main` through a reviewed pull request. Without branch protection, a direct push to `main` bypasses all of them and triggers an apply.

#### Scenario: Direct push to main is rejected
- **WHEN** a developer attempts to push a commit directly to `main`
- **THEN** the push SHALL be rejected, requiring the change to go through a pull request

#### Scenario: Pull request with failing checks cannot merge
- **WHEN** a pull request's validation workflow fails
- **THEN** the pull request SHALL be blocked from merging until the checks pass

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
