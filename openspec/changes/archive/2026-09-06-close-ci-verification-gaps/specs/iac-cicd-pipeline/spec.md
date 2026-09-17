## ADDED Requirements

### Requirement: Ansible Configuration Is Verified in Continuous Integration
Every pull request that changes files under `ansible/` SHALL trigger continuous-integration checks over that configuration. Verification SHALL be split into two tiers by cost and by confidence in the check itself.

**Blocking tier.** `ansible-lint` and `ansible-playbook --syntax-check` SHALL run as part of the required pull request status check, using the same invocation the repository's `pre-commit` configuration uses locally, so that a pull request cannot merge with Ansible content that fails either. These checks require no container runtime and no credential.

**Advisory tier.** The Molecule suite SHALL run in continuous integration on pull requests changing `ansible/`, and SHALL NOT be registered as a required status check while its behavior on a hosted runner is unestablished. Its scenarios exercise host-level firewalling, `fail2ban` and service management inside containers; whether every scenario is reproducible on a containerised runner has never been observed. An advisory result makes that observable without a failure of the runner environment blocking every merge.

The Molecule run SHALL discover role scenarios rather than enumerate them, so that a role or scenario added under `ansible/roles/` is covered without a workflow edit, and SHALL execute every scenario a role declares rather than only its `default` scenario.

Discovery SHALL fail loudly rather than succeed vacuously: where it finds no role to run, the run SHALL fail with a message identifying discovery as the cause, and SHALL NOT report success. A discovery that silently matches nothing is indistinguishable from a suite that passed, which is the same defect this capability's destroy-policy gate and secret scanning requirements each forbid elsewhere.

The Molecule run SHALL install its toolchain from the repository's exact pinned manifests — `ansible/requirements-test.txt` for the Python toolchain and `ansible/requirements.yml` for Galaxy content — and SHALL NOT resolve any dependency version freshly at run time.

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

#### Scenario: A failing Molecule scenario does not block a merge
- **WHEN** a Molecule scenario fails on a pull request
- **THEN** the failure SHALL be visible on the pull request, and the required status checks SHALL be unaffected by it

#### Scenario: Ansible verification receives no production credential
- **WHEN** any Ansible verification job runs on a pull request
- **THEN** it SHALL complete without a Hetzner API token, an SSH deploy key, a registry credential, or a declared deployment `environment:`

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

## MODIFIED Requirements

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

### Requirement: Gated Production Apply Applies the Reviewed Plan
`terraform apply` against the prod environment SHALL run only after a pull request is merged to `main`, SHALL require manual approval via the `production` GitHub Environment protection rule, and SHALL apply a **saved plan file produced before approval** rather than recomputing a plan after approval.

The apply workflow SHALL be structured as two jobs in a single run:

1. A **plan job** that declares no `environment:`, runs `terraform plan -out=tfplan`, writes the human-readable plan to the run's job summary, and uploads `tfplan` as a workflow artifact.
2. An **apply job** that depends on the plan job, declares `environment: production`, and on approval downloads `tfplan` and runs `terraform apply tfplan`.

This ensures the approving reviewer sees the exact diff that will be applied. A workflow that approves first and plans afterwards gives the reviewer no diff to evaluate, and the plan computed after approval may differ from the one reviewed on the pull request due to the merge commit, intervening drift, or a provider version change.

The apply workflow SHALL be triggered only by pushes that can affect the Terraform configuration, identified by a workflow-level path filter. A merge that cannot change infrastructure SHALL NOT raise a `production` Environment approval request. An approval prompt that appears on merges with nothing to approve trains the approver to grant it without reading, which defeats the gate it exists to enforce; out-of-band divergence remains covered by scheduled drift detection rather than by an approval request per merge.

This path filter is permissible **only** because the apply workflow is not a required status check. The workflow that is registered as a required check SHALL NOT be path-filtered at the workflow level — see the Required Status Checks Report on Every Pull Request requirement, whose constraint is the opposite of this one and takes precedence for that workflow.

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
