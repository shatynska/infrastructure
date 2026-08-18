## Why

This repository is currently empty except for OpenSpec scaffolding. We need to stand up a Terraform-based IaC foundation for infrastructure on Hetzner Cloud, starting with a single production server, with production-quality repo practices — formatting, linting, secret scanning, safe deploys, and CI/CD — in place from the first commit rather than retrofitted later.

## What Changes

- Scaffold the repo structure: `environments/prod/` as a folder, consuming shared modules from `modules/` (starting with `modules/server`). The folder-based layout leaves room to add further environments later without restructuring.
- Configure HCP Terraform (formerly Terraform Cloud) as a backend-only (CLI-driven) remote state store — no VCS connection, no HCP-run execution, workspace Execution Mode set to **Local** — with a single workspace: `infrastructure-prod`. Authenticate to it with a static HCP Terraform API token, split by privilege (Plan vs. Write) the same way the Hetzner tokens are — GitHub OIDC dynamic credentials do not apply here, since that HCP Terraform feature authenticates providers during a remotely-executed run, not the CLI's own backend access (discovered during implementation; see design.md Decision 9).
- Use a dedicated Hetzner Cloud project for prod, with two project-scoped tokens split by privilege: a Read Only token for automatic plan jobs and a Read & Write token confined to the approval-gated apply.
- Add local quality tooling: `terraform fmt`, `tflint` (bundled `terraform` ruleset only), the `pre-commit` framework with `antonbabenko/pre-commit-terraform` hooks (fmt, tflint, validate, gitleaks), `commitlint` for Conventional Commits, a Terraform-aware `.gitignore`, and a committed `.terraform.lock.hcl`.
- Protect the repository so the pipeline's gates can't be bypassed: branch protection on `main` (require PR, require status checks, no force-push) and read-only default `GITHUB_TOKEN` permissions with per-job escalation.
- Add a GitHub Actions CI/CD pipeline:
  - On pull request: `fmt -check`, `validate`, `tflint`, `Trivy` (misconfiguration scanning), `gitleaks` (secret scanning via the CLI binary), then `terraform plan`, posted as a PR comment.
  - On merge to `main`: a two-job apply that plans first and applies the **saved plan file** after approval, so the reviewer approves the exact diff rather than an uncomputed run. Gated behind a GitHub Environment (`production`) requiring manual reviewer approval, and serialized with a `concurrency` group.
  - A destroy-policy gate that parses the plan JSON and fails on any `delete` or `replace` action unless explicitly overridden.
  - Scheduled nightly drift-detection workflow: plan-only against prod, no apply, reporting divergence to a single deduplicated GitHub issue.
- Add safety hardening: provider-level `delete_protection` (parameterized, so shared modules stay reusable), consistent `environment`/`managed_by` labels on all `hcloud_*` resources, and Dependabot configured for the `terraform` and `github-actions` ecosystems plus a scheduled `pre-commit autoupdate` job.
- Confine write-capable Hetzner credentials to the gated pipeline: the Read & Write token lives only as a `production` Environment secret and never on a workstation, so the workspace's Local execution mode cannot be used to apply straight to prod past the approval, destroy-policy, and branch-protection gates. Record the prohibition in the README runbook and in a repository-root `AGENTS.md`.
- Give the server a network baseline it is safe to expose: a structurally required default-deny `hcloud_firewall` with explicitly enumerated source CIDRs, key-only SSH with password auth disabled, and `backups = true`.

## Capabilities

### New Capabilities
- `iac-repo-foundations`: Repo scaffolding and local developer quality gates — environment/module folder structure, formatting, linting, pre-commit hooks, commit message linting, gitignore/tfvars sensitivity split, lockfile conventions, and locally-encoded Hetzner guardrails.
- `iac-state-management`: HCP Terraform backend configuration (CLI-driven, local execution, static tokens split by privilege) and the dedicated Hetzner Cloud project for the prod environment.
- `iac-cicd-pipeline`: GitHub Actions workflows covering PR validation/planning, saved-plan gated apply, the destroy-policy gate, branch protection and least-privilege permissions, and scheduled drift detection.
- `iac-safety-hardening`: Guardrails against destructive, unnoticed, or externally-exposed changes — deletion protection, backups, network baseline, resource labeling, and automated dependency updates.

### Modified Capabilities
(none — repository has no existing specs)

## Impact

- Affected: entire repository (currently empty aside from OpenSpec scaffolding). This change creates the initial `environments/prod/`, `modules/`, `.github/workflows/`, and root-level tooling config files, and changes GitHub repository settings (branch protection, default token permissions, environment and secrets).
- New external dependencies: HCP Terraform account/organization, one Hetzner Cloud project, GitHub Actions, and the CLI tools `tflint`, `Trivy`, `gitleaks`, `pre-commit`, `terraform-docs` (via pre-commit hooks), and `commitlint`. No paid third-party action licenses are required.
- Recurring cost note: Hetzner charges a 20% surcharge for server backups, accepted deliberately because no Terraform-level guardrail protects data on disk.
- No existing infrastructure or state to migrate — this is a greenfield setup.
