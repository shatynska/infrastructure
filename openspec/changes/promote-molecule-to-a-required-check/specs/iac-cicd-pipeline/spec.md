## REMOVED Requirements

### Requirement: Ansible Configuration Is Verified in Continuous Integration
Replaced by *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge*, added below. The subject is unchanged; what the requirement asserts about the Molecule suite is not. It described verification split into a tier that blocks a merge and a tier that deliberately does not, and its scenario *A failing Molecule scenario does not block a merge* asserted the second half. Both tiers now gate, so that scenario is dropped rather than reworded.

A MODIFIED block cannot carry that drop — it may not omit a scenario the current specification still has, a guard against losing one by accident rather than by decision. Nor can a rename: the same guard follows a rename through to the block it renames. Removal and re-addition under a name that states the new obligation is what OpenSpec supports, and it marks in the specification's own history that the tiering changed character rather than gaining a paragraph. Every other scenario is carried through verbatim.

## MODIFIED Requirements

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

## ADDED Requirements

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
