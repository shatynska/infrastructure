## Why

This repository is currently empty except for OpenSpec scaffolding. We need to stand up a Terraform-based IaC foundation for infrastructure on Hetzner Cloud, starting with a single production server, with production-quality repo practices — formatting, linting, secret scanning, safe deploys, and CI/CD — in place from the first commit rather than retrofitted later.

## What Changes

- Scaffold the repo structure: `environments/prod/` as a folder, consuming shared modules from `modules/` (starting with `modules/server`). The folder-based layout leaves room to add further environments later without restructuring.
- Configure Terraform Cloud as a backend-only (CLI-driven) remote state store — no VCS connection, no TFC-run execution — with a single workspace: `infrastructure-prod`.
- Use a dedicated Hetzner Cloud project for prod, with its own `HCLOUD_TOKEN`.
- Add local quality tooling: `terraform fmt`, `tflint`, the `pre-commit` framework with `antonbabenko/pre-commit-terraform` hooks (fmt, tflint, validate, gitleaks), `commitlint` for Conventional Commits, a Terraform-aware `.gitignore`, and a committed `.terraform.lock.hcl`.
- Add a GitHub Actions CI/CD pipeline:
  - On pull request: `fmt -check`, `validate`, `tflint`, `Trivy` (misconfiguration scanning), `gitleaks` (secret scanning), then `terraform plan`, posted as a PR comment.
  - On merge to `main`: `terraform apply` to prod, gated behind a GitHub Environment (`production`) requiring manual reviewer approval.
  - Scheduled nightly drift-detection workflow: plan-only against prod, no apply, to surface divergence between code and real infrastructure.
- Add safety hardening: `lifecycle { prevent_destroy = true }` on stateful/critical resources, consistent `environment`/`managed_by` labels on all `hcloud_*` resources, and Dependabot configured for the `terraform` ecosystem.

## Capabilities

### New Capabilities
- `iac-repo-foundations`: Repo scaffolding and local developer quality gates — environment/module folder structure, formatting, linting, pre-commit hooks, commit message linting, gitignore, and lockfile conventions.
- `iac-state-management`: Terraform Cloud backend configuration and the dedicated Hetzner Cloud project/credentials for the prod environment.
- `iac-cicd-pipeline`: GitHub Actions workflows covering PR validation/planning, gated apply to prod, and scheduled drift detection.
- `iac-safety-hardening`: Guardrails against destructive or unnoticed changes — destroy protection, resource labeling, secret scanning, and automated dependency updates.

### Modified Capabilities
(none — repository has no existing specs)

## Impact

- Affected: entire repository (currently empty aside from OpenSpec scaffolding). This change creates the initial `environments/prod/`, `modules/`, `.github/workflows/`, and root-level tooling config files.
- New external dependencies: Terraform Cloud account/organization, one Hetzner Cloud project, GitHub Actions, and the CLI tools `tflint`, `Trivy`, `gitleaks`, `pre-commit`, `terraform-docs` (via pre-commit hooks), and `commitlint`.
- No existing infrastructure or state to migrate — this is a greenfield setup.
