## 1. External Accounts and Credentials

- [ ] 1.1 Create the Terraform Cloud organization (if not already present) and a CLI-driven workspace named `infrastructure-prod` (no VCS connection).
- [ ] 1.2 Create a dedicated Hetzner Cloud project for prod and generate a project-scoped `HCLOUD_TOKEN`.
- [ ] 1.3 Generate a Terraform Cloud API token for CLI/CI use.
- [ ] 1.4 In the GitHub repo, create a `production` Environment with a required-reviewer protection rule.
- [ ] 1.5 Add `HCLOUD_TOKEN` and the Terraform Cloud API token as secrets scoped to the `production` Environment (not repo-wide secrets).

## 2. Repo Scaffolding and Local Tooling

- [ ] 2.1 Create the `environments/prod/` and `modules/` directory structure.
- [ ] 2.2 Add a Terraform-aware `.gitignore` covering `.terraform/`, `*.tfstate*`, and secret-bearing `.tfvars` files.
- [ ] 2.3 Add `.pre-commit-config.yaml` using `antonbabenko/pre-commit-terraform` hooks for `terraform fmt`, `tflint`, `terraform validate`, and `gitleaks`.
- [ ] 2.4 Add `commitlint` configuration for Conventional Commits and wire it into a `pre-commit` (or existing) commit-msg hook.
- [ ] 2.5 Add a `tflint` configuration file (`.tflint.hcl`) with the Hetzner/Terraform ruleset enabled.
- [ ] 2.6 Document local setup (installing `pre-commit`, running `pre-commit install`) in the repo README.

## 3. Terraform Module and Prod Environment

- [ ] 3.1 Implement `modules/server` encapsulating the `hcloud_server` resource (and any associated SSH key / firewall resources), parameterized by variables (server type, region, image, labels).
- [ ] 3.2 Add `lifecycle { prevent_destroy = true }` to the server resource (and any future volumes) inside the module.
- [ ] 3.3 Ensure the module applies `environment` and `managed_by = "terraform"` labels to every `hcloud_*` resource it creates.
- [ ] 3.4 Implement `environments/prod/` calling `modules/server` with prod-specific variables, including `backend.tf` configured for the `infrastructure-prod` Terraform Cloud workspace (CLI-driven).
- [ ] 3.5 Run `terraform init` locally against the prod environment to generate and commit `.terraform.lock.hcl`.
- [ ] 3.6 Fill in `environments/prod/terraform.tfvars` with actual server sizing/region/image values.

## 4. GitHub Actions: Pull Request Validation

- [ ] 4.1 Add a workflow that runs on pull requests touching `environments/` or `modules/`, executing `terraform fmt -check`, `terraform validate`, and `tflint`.
- [ ] 4.2 Add a Trivy misconfiguration-scanning step to the same workflow.
- [ ] 4.3 Add a `gitleaks` secret-scanning step to the same workflow.
- [ ] 4.4 Add a `terraform plan` step (authenticated via the `production` Environment secrets) that runs after validation passes, and post the full plan output as a PR comment.

## 5. GitHub Actions: Gated Apply and Drift Detection

- [ ] 5.1 Add a workflow that runs `terraform apply` against `environments/prod/` on push to `main`, gated by the `production` GitHub Environment approval rule.
- [ ] 5.2 Verify that `production`-scoped secrets are unreadable by the apply job until the required reviewer approves.
- [ ] 5.3 Add a scheduled (nightly) workflow that runs `terraform plan` (no apply) against `environments/prod/` and fails/notifies when the plan shows a non-empty diff.

## 6. Dependency Automation

- [ ] 6.1 Add a `dependabot.yml` entry for the `terraform` package ecosystem targeting `environments/prod/` and `modules/server/`.
- [ ] 6.2 Add a `dependabot.yml` entry (or equivalent) to keep pinned `pre-commit` hook revisions up to date.

## 7. End-to-End Validation

- [ ] 7.1 Open a pull request with a trivial change to validate the full PR pipeline (fmt/lint/Trivy/gitleaks/plan-comment) end-to-end before any real apply.
- [ ] 7.2 Merge the validated PR, approve the gated `production` apply, and confirm the server is created successfully on Hetzner Cloud.
- [ ] 7.3 Manually trigger (or wait for) the nightly drift-detection workflow once to confirm it runs cleanly against the newly created infrastructure.
