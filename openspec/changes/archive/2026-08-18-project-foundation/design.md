## Identity

- **What it is**: A Terraform-managed Infrastructure-as-Code repository
  that provisions and operates infrastructure on Hetzner Cloud, currently
  a single production server built from a reusable `modules/server`
  module, with remote state in HCP Terraform and a review-gated GitHub
  Actions CI/CD pipeline. See `openspec/changes/bootstrap-hetzner-iac/`
  for the full technical build-out this identity rests on.
- **Problem it solves**: Manual, ad-hoc server provisioning and
  configuration are hard to audit, drift silently from whatever is
  documented, and offer no review step before a change reaches
  production. This repository replaces that with declarative,
  version-controlled infrastructure: every change is a `terraform plan`
  reviewed before merge, an exact saved plan approved before apply, and a
  nightly drift check that surfaces divergence between the committed
  configuration and what is actually running. The specific product or
  service this infrastructure will ultimately back is not yet decided —
  right now the priority is reliability, drift prevention, and
  auditability of the infrastructure layer itself, ahead of any workload.
- **Intended audience**: Primarily agentic/automated workflows (Claude
  Code and similar) operating the infrastructure day to day — writing and
  extending Terraform, running plans, opening PRs — with a human required
  to approve every change that reaches production via the gated
  `production` GitHub Environment. This is not yet a multi-person team;
  the README and `AGENTS.md` are written so an agent picking this repo up
  cold has enough context to work safely without a human re-explaining it
  each time.

## Scope

- A single production environment (`environments/prod/`) provisioning
  Hetzner Cloud resources through shared, reusable modules under
  `modules/` (currently `modules/server`, encapsulating an `hcloud_server`
  plus its attached firewall and SSH key).
- Remote state and locking via HCP Terraform (CLI-driven backend, Local
  execution mode), authenticated via GitHub OIDC dynamic credentials.
- A GitHub Actions pipeline: PR-time static and plan checks, a two-job
  gated apply on merge to `main` (read-only plan job, human-approved
  read-write apply job), and a nightly drift-detection check.
- Local development tooling: `pre-commit` (fmt, tflint, validate,
  gitleaks), `commitlint` for Conventional Commits, `.tflint.hcl` with the
  bundled Terraform ruleset.
- A staging environment is anticipated as the near-term next environment
  (a second `environments/<name>/` folder reusing the same modules), but
  is not part of this initial scope — it will be proposed as its own
  change once prod is fully stood up.

## Non-Goals

- **Multi-cloud support.** Hetzner Cloud only — no abstraction layer for
  AWS, GCP, or any other provider.
- **Multi-region deployment.** A single region (`fsn1`, per the existing
  module variables) for the foreseeable future.
- **Container orchestration.** Plain VMs via `hcloud_server`; no
  Kubernetes, Nomad, or similar orchestrator layer. Workloads run
  directly on the provisioned server(s).

A staging environment is deliberately *not* listed as a non-goal — see
Scope above. It is a near-term follow-up, not a rejected idea, and should
not be treated as out of scope by a future reader of this document.

## Technology

- **Language**: Terraform (HCL), `required_version >= 1.9.0`.
- **Provider**: `hetznercloud/hcloud` (`~> 1.52`).
- **State backend**: HCP Terraform (formerly Terraform Cloud), CLI-driven
  / Local execution mode — HCP stores state and provides locking only; it
  never runs plans or applies itself. Authenticated via GitHub OIDC
  dynamic credentials rather than a long-lived API token.
- **CI/CD**: GitHub Actions.

Already established by `bootstrap-hetzner-iac`; recorded here so it is
visible without reading that change's specs.

## Architecture

- `modules/<name>/` — shared, reusable Terraform modules (currently
  `modules/server`). Modules take no environment-specific literals;
  everything environment-specific is a variable.
- `environments/<name>/` — one folder per environment (currently only
  `prod`), each calling the shared modules with environment-specific
  variables via a committed, non-secret `terraform.tfvars` and its own
  `backend.tf` pointing at a dedicated HCP Terraform workspace
  (`infrastructure-<name>`). New environments are added as new folders,
  never as branches.
- **Credential scoping**: two Hetzner API tokens split by privilege — a
  Read Only token for automatic PR-time plan jobs, and a Read & Write
  token confined to the human-approved apply job — both named
  `HCLOUD_TOKEN` but scoped as a repository secret vs. a `production`
  Environment secret respectively, so environment scope shadows
  repository scope only for the gated job.
- **Pipeline shape**: PR checks (fmt/validate/tflint/Trivy/gitleaks plus a
  posted plan) never touch the write-capable token; the merge-to-`main`
  apply is a two-job saved-plan flow (a plan job produces and summarizes
  an exact plan; an apply job, gated by required-reviewer approval on the
  `production` GitHub Environment, applies that exact saved plan) so the
  approver always approves precisely what will run.
- `terraform apply` is never run locally — production changes reach
  Hetzner only through this gated pipeline (see `AGENTS.md`).

## Testing Strategy

Terraform infrastructure code has no traditional unit-test layer yet;
verification today is static analysis plus mandatory human review of an
exact plan:

- **Static checks** (pre-commit and PR CI): `terraform fmt -check`,
  `terraform validate`, `tflint` (bundled ruleset), Trivy misconfiguration
  scanning, `gitleaks` secret scanning.
- **Plan review**: every PR gets a `terraform plan` posted as a comment;
  the merge-to-`main` apply reuses that exact saved plan rather than
  re-planning, so the human approver is approving precisely what will
  run.
- **Drift detection**: a nightly plan-only run opens or updates a GitHub
  issue when live infrastructure diverges from the committed
  configuration, and closes it once resolved.
- **Module-level testing**: as `modules/` grows beyond `modules/server`,
  add Terraform's native test framework (`*.tftest.hcl`, run via
  `terraform test`) for module-level assertions — e.g. the firewall
  default-denies inbound, `delete_protection` is set — that do not
  require a live plan against real infrastructure. Test files live
  alongside each module as `modules/<name>/tests/*.tftest.hcl`; the test
  command is `terraform test`, run from the module directory.

This is the first point this project has a defined test command
(`terraform test`) and test-path glob (`modules/*/tests/*.tftest.hcl`).
Deriving tests from a specification before implementation, as
`AGENTS.md`'s development workflow requires, was structurally impossible
for this change — the foundation change is exempt, since the command and
glob it defines are this change's own output, not an input to it. Test
authoring applies normally to every change after this one, including the
remaining `bootstrap-hetzner-iac` work.

## Development Tooling

Already in place; confirmed here rather than changed:

- `pre-commit` running `terraform_fmt`, `terraform_tflint` (via
  `.tflint.hcl`), `terraform_validate`, and `gitleaks`
  (`antonbabenko/pre-commit-terraform` + `gitleaks/gitleaks` hooks).
- `commitlint` (`@commitlint/config-conventional`) enforcing Conventional
  Commits on the commit-msg hook.
- `.tflint.hcl`: the bundled `terraform` ruleset only — there is no
  Hetzner/`hcloud`-specific tflint plugin to enable.
- `.gitignore`: already Terraform-aware (`.terraform/`, `*.tfstate*`,
  override files, `.terraformrc`/`terraform.rc`, `*.secret.tfvars`,
  `secrets.auto.tfvars`, OS/editor cruft). This decision's concrete
  deliverable — extending `.gitignore` once the stack is known — is
  already satisfied; no further extension is needed for the current
  stack.
