## Purpose

Repo scaffolding and local developer quality gates — stack/module folder structure, formatting, linting, pre-commit hooks, commit message linting, gitignore/tfvars sensitivity split, lockfile conventions, and locally-encoded Hetzner guardrails.

## Requirements

### Requirement: Terraform Formatting Enforced
All committed Terraform code SHALL be formatted according to `terraform fmt` canonical style.

#### Scenario: Unformatted code is rejected locally
- **WHEN** a developer attempts to commit a `.tf` file that does not match `terraform fmt` canonical style
- **THEN** the pre-commit hook SHALL block the commit until the file is reformatted

### Requirement: Terraform Linting Enforced
All committed Terraform code SHALL pass `tflint` checks.

`tflint` SHALL be configured with its bundled `terraform` ruleset. No Hetzner/`hcloud` `tflint` ruleset exists, so no provider-specific ruleset SHALL be declared; `tflint`'s role here is Terraform-language correctness and style, not Hetzner resource validation.

#### Scenario: Lint violation is caught before commit
- **WHEN** a developer attempts to commit a `.tf` file containing a `tflint`-detectable issue (e.g. an unused declared variable)
- **THEN** the pre-commit hook SHALL block the commit and report the violation

### Requirement: Hetzner Guardrails Are Encoded Locally, Not Assumed From Scanners
Because off-the-shelf misconfiguration scanners provide essentially no Hetzner Cloud rule coverage — Trivy's and tfsec's built-in policy packs target AWS, Azure, GCP, Kubernetes, and Docker — the repository SHALL NOT rely on scanner defaults as its Hetzner security control.

Hetzner-specific rules that matter SHALL be encoded by, in order of preference: module structure that makes the unsafe configuration unrepresentable, `variable validation` blocks that reject bad inputs at plan time, and a small set of custom Trivy or Conftest policies committed to the repository for rules the first two cannot express.

#### Scenario: Invalid module input is rejected at plan time
- **WHEN** a caller passes a value that violates a module's declared input constraints (e.g. an SSH source CIDR of `0.0.0.0/0`, or a malformed server type)
- **THEN** `terraform plan` SHALL fail with the validation block's error message, before any API call is made

#### Scenario: Custom policies are versioned with the code
- **WHEN** a custom misconfiguration policy is written for a Hetzner-specific rule
- **THEN** it SHALL be committed to the repository and evaluated by the pull request validation workflow

### Requirement: Pre-commit Hooks Run Local Quality Checks
The repository SHALL provide a `pre-commit` configuration using `antonbabenko/pre-commit-terraform` hooks that runs formatting, linting, validation, and secret scanning on staged changes before a commit is created.

#### Scenario: Developer installs hooks and commits a change
- **WHEN** a developer runs `pre-commit install` after cloning the repo and then commits a Terraform change
- **THEN** `terraform fmt`, `tflint`, `terraform validate`, and a secret scan SHALL run automatically against the staged files before the commit completes

### Requirement: Commit Message Linting
Commit messages SHALL be validated against the Conventional Commits format before a commit is finalized.

#### Scenario: Non-conventional commit message is rejected
- **WHEN** a developer attempts to commit with a message that does not follow the Conventional Commits format
- **THEN** the commit SHALL be rejected by the commit-msg hook with an explanation of the expected format

### Requirement: Version Control Excludes State and Secrets
The repository's `.gitignore` SHALL exclude Terraform local state files and the `.terraform/` working directory.

Variable files SHALL be split by sensitivity rather than excluded wholesale:

| File | Tracked | Contents |
|---|---|---|
| `terraform/stacks/<name>/terraform.tfvars` | Committed | Non-secret stack configuration (server type, region, image, labels, allowed CIDRs) |
| `*.secret.tfvars`, `secrets.auto.tfvars` | Ignored | Any values that must not enter version control |

A blanket `*.tfvars` ignore rule SHALL NOT be used: CI runs `terraform plan` and `apply` from a clean checkout and requires the non-secret stack configuration to be present in the repository.

#### Scenario: Local state is never staged
- **WHEN** `terraform init` or `terraform plan` produces local artifacts such as `.terraform/` or a local `.tfstate` file
- **THEN** `git status` SHALL NOT show these files as trackable/stageable

#### Scenario: CI has the environment configuration it needs
- **WHEN** a CI job checks out the repository and runs `terraform plan` against `terraform/stacks/main-production/`
- **THEN** the non-secret `terraform.tfvars` values SHALL be present in the checkout, requiring no out-of-band file injection

#### Scenario: Secret-bearing variable file is not committable
- **WHEN** a developer creates a file matching `*.secret.tfvars` and attempts to stage it
- **THEN** `git status` SHALL NOT show it as trackable

### Requirement: Provider Lockfile Committed
The `.terraform.lock.hcl` provider dependency lockfile SHALL be committed to version control to ensure reproducible provider versions across machines and CI runs.

#### Scenario: CI uses the same provider version as local development
- **WHEN** a CI run executes `terraform init` against a commit that includes `.terraform.lock.hcl`
- **THEN** the provider versions installed SHALL match those recorded in the committed lockfile

### Requirement: Source Files Cite Specifications by Path and Changes by Name

A change's planning artifacts move when the change is archived — from `openspec/changes/<name>/` to `openspec/changes/archive/<date>-<name>/` — and the archive date does not exist until archiving happens. A citation of the pre-archive path therefore cannot be written correctly in advance and breaks at the moment its change succeeds, in the same commit that proves the change worked.

Committed files outside `openspec/` SHALL cite the repository's own specifications and change records in one of two forms, chosen by what is being cited:

| What is cited | Form |
|---|---|
| A requirement | The path of the specification that holds it — `openspec/specs/<capability>/spec.md` — together with the requirement's own name |
| Rationale or history held only inside a change — its `proposal.md`, `design.md`, `test-plan.md` or `test-manifest.md` | The change's name and the artifact's name, in prose, with no path |

Archiving merges a change's delta specifications into the main specification, so the first form's path is permanent and names the requirement as it currently stands rather than as one change once proposed it. The second form has no path to break. A citation MAY additionally give a change's archived location as `openspec/changes/archive/<date>-<name>/…` once that location exists.

The first form names the requirement's post-archive home. Where a change introduces a **new** capability, archiving is what creates `openspec/specs/<capability>/spec.md`, so a citation written during that change does not resolve until the change is archived. That interval is accepted: it is bounded by the change's own lifetime, after which the path is permanent, and it is the inverse of the defect this requirement exists to remove.

No committed file outside `openspec/` SHALL contain a path naming a change's own directory under `openspec/changes/` — that is, `openspec/changes/<segment>` where `<segment>` is a change name rather than `archive`, **whether or not a further path component follows it**.

The trailing qualification is load-bearing rather than pedantic. Better than a third of the citations this requirement removes name the change and stop there — `requirement (openspec/changes/connect-platform-deploy-via-tailscale)` — and a prohibition written as `openspec/changes/<segment>/` permits every one of them. Two earlier attempts to measure this problem each undercounted it by exactly that class.

This prohibition SHALL be asserted by the executable test suite that gates every pull request, because the author of such a citation cannot detect it: the citation is correct when written, correct when reviewed, and wrong only once the change it cites has succeeded.

That assertion is a static text match, and one rendering lies outside it: a citation split across a line break immediately after `openspec/changes/` whose change name is a single word with no hyphen. Distinguishing that from ordinary prose describing this rule is not possible by text, since a continuation line's first word is itself a valid single-word change name. Every change this repository has recorded is named in multiple hyphenated words, so the excluded rendering is the intersection of two shapes neither of which has occurred.

#### Scenario: A pull request reintroducing the pre-archive citation form is rejected
- **WHEN** a pull request adds, to a committed file outside `openspec/`, a path naming a change's own directory under `openspec/changes/`
- **THEN** the required status check SHALL fail on that pull request, naming the file, the line and the citation

#### Scenario: Archiving a change breaks no citation
- **WHEN** a change is archived and its directory moves to `openspec/changes/archive/<date>-<name>/`
- **THEN** no citation in any committed file outside `openspec/` SHALL be invalidated by the move

#### Scenario: A requirement is cited at its permanent location
- **WHEN** a committed file outside `openspec/` cites a requirement that a change introduced or modified
- **THEN** it SHALL name `openspec/specs/<capability>/spec.md` and the requirement's own name, rather than the delta specification inside the change that proposed it

#### Scenario: A change's own artifacts are out of scope
- **WHEN** a change's planning artifacts, live or archived, cite that change's own paths
- **THEN** the prohibition SHALL NOT apply to them, since they move together with what they cite

### Requirement: Verification Writing to Shared State Is Namespaced per Working Tree
Where a verification mechanism in this repository writes to state that outlives a single run and is reachable from more than one working tree on the same machine, that state SHALL be namespaced per working tree, and the namespace SHALL be derived deterministically from the working tree it belongs to.

Determinism is normative rather than incidental: a later session in the same working tree SHALL resolve the same namespace, so that state an earlier run left behind can be found and removed rather than orphaned.

Where the namespace is absent, the mechanism SHALL refuse to run and SHALL report what is missing. It SHALL fail before producing any result, and SHALL NOT fall back to state whose sharing could make a run report success — a run that silently shares such state can report success having verified nothing about the change under test, since it may equally pass against another session's state as fail against it, and a verification result that can mean either is not a result.

This prohibition is over state that can carry a result between working trees. It does not extend to state whose sharing can only cause a run to fail: a refusal reached noisily is not the defect this requirement exists to prevent, and demanding that nothing whatever be shared before the refusal would forbid mechanisms that are in fact safe.

This requirement governs state shared *between working trees on one machine*. It places no obligation on continuous integration, where each job is an isolated checkout and the condition cannot arise.

`AGENTS.md` SHALL carry a section binding this requirement to each service it governs, naming the state, the namespace, and how a session takes one. A stated rule with nothing bound to it is not enforceable by a reviewer, and this repository has already run for months in exactly that state.

#### Scenario: Two working trees verify the same subject concurrently
- **WHEN** two working trees on one machine run the same verification subject at the same time
- **THEN** each SHALL write only to state named for its own working tree, and neither run's result SHALL depend on the other's

#### Scenario: A run with no namespace refuses rather than sharing
- **WHEN** a verification run is started without a namespace
- **THEN** it SHALL fail, identifying the missing namespace, and SHALL NOT create or reuse state shared with another working tree from which a result could be produced

#### Scenario: The instance name is resolvable within the limits that govern it
- **WHEN** a namespace of the length this repository's own naming produces is supplied
- **THEN** the run SHALL create its instance successfully, rather than failing on a limit the namespace pushed it past

#### Scenario: A later session reclaims what an earlier one left
- **WHEN** a run in a working tree leaves state behind, and a later session runs in that same working tree
- **THEN** the later session SHALL resolve the same namespace and SHALL be able to remove that state

#### Scenario: The binding is stated, not merely implied
- **WHEN** this repository binds this requirement to a particular service
- **THEN** `AGENTS.md` SHALL state that binding, and the pipeline's own configuration checks SHALL fail where that statement is absent

### Requirement: Stack and Module Folder Structure
The repository SHALL organize Terraform configuration as stack directories under `terraform/stacks/` that consume shared, reusable code from `terraform/modules/`, rather than using git branches to represent stacks. A **stack** is one Terraform root module: one state, one Hetzner project, one blast radius. It is the unit this repository's pipeline discovers, plans, applies, drift-checks and converges, and the directory is divided by it rather than by the environment a stack belongs to. It is distinct from the shared platform Compose stack the `iac-platform-services` capability governs, which is a set of services on a host rather than a Terraform root module; where both senses could be read, this one is written as a **stack directory**.

A stack's directory name SHALL be the stack's own name, and that name SHALL NOT be assumed equal to the name of any axis it carries. A stack is a *(tenant, environment)* pair, so its name and its environment coincide only where a repository has one tenant; the environment a stack belongs to is declared rather than parsed out of the directory name (see Each Stack Declares Its Own Pipeline Configuration, `iac-cicd-pipeline`).

Stacks consume modules by relative path, which means every stack runs the same module code as of the merged commit — there is no per-stack module version pinning, and none SHALL be introduced to obtain promotion ordering.

**Promotion ordering is not a property of the apply workflow.** A merge affecting several stacks SHALL plan and apply each of them independently, each under its own GitHub Environment's protection rules, and a stack's apply SHALL NOT be made to depend on another stack's apply. Such a dependency is the mechanism this requirement previously prescribed, and it contradicts the Gated Production Apply Applies the Reviewed Plan requirement (iac-cicd-pipeline), which obliges that one stack's failure not withhold a correct change from another — an obligation stated there for plans and true here for the same reason.

Where promotion ordering is wanted, it SHALL be obtained from the reviewed stack's own approval gate: a reviewed stack's apply waits for a human, who can withhold approval until a lower-environment stack's apply has been observed to succeed. This is a discipline available to the approver rather than a mechanism the pipeline enforces, and it is stated as what holds rather than as what is guaranteed.

#### Scenario: A stack directory consumes a shared module
- **WHEN** the `terraform/stacks/main-production/` configuration defines the production server
- **THEN** it SHALL do so by calling a module under `terraform/modules/` (e.g. `terraform/modules/server`) rather than duplicating resource definitions inline

#### Scenario: Adding a stack does not require restructuring
- **WHEN** a new stack is added
- **THEN** it SHALL be added as a new `terraform/stacks/<name>/` directory consuming the same shared modules, without moving or renaming existing files and without pinning a module version of its own

#### Scenario: A stack's name is not read as its environment
- **WHEN** a stack directory is named for a *(tenant, environment)* pair, such as `terraform/stacks/main-production/`
- **THEN** nothing SHALL derive that stack's environment by parsing its directory name, and the environment SHALL be read from the stack's own declaration instead

#### Scenario: A shared module change reaches every stack without an imposed order
- **WHEN** a merge changing a file under `terraform/modules/` affects two stacks
- **THEN** each stack SHALL be planned and applied under its own GitHub Environment's protection rules, and neither stack's apply SHALL be blocked by the other's outcome

#### Scenario: Promotion ordering is exercised at the approval, not by the workflow
- **WHEN** an operator wants a shared change observed in a lower-environment stack before it reaches a reviewed one
- **THEN** the reviewed stack's approval SHALL be the point at which that is exercised, by withholding it until the lower-environment stack's apply has been observed
