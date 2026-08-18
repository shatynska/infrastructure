## 1. External Accounts and Credentials

- [ ] 1.1 Create the HCP Terraform organization (if not already present) and a CLI-driven workspace named `infrastructure-prod` (no VCS connection).
- [ ] 1.2 Set the `infrastructure-prod` workspace's Execution Mode to **Local**. (A `cloud` block defaults to remote execution, which would run plans on HCP's runners and break the saved-plan apply flow.)
- [ ] 1.3 Create two teams in the HCP Terraform organization, each scoped to only the `infrastructure-prod` workspace: one with **Plan** permission, one with **Write** permission. Generate a team API token from each, for the repository-scoped and `production` Environment-scoped `TF_API_TOKEN` secrets (task 2.8/2.9). GitHub OIDC does **not** apply here: HCP Terraform's dynamic-credentials/workload-identity feature authenticates providers during a run HCP Terraform executes remotely, not the CLI's own backend/state access for a CLI-driven, Local-execution workspace like this one — confirmed during implementation (see design.md Decision 9).
- [ ] 1.4 Create a dedicated Hetzner Cloud project for prod.
- [ ] 1.5 In that project, generate two API tokens: one **Read Only** and one **Read & Write**.
- [ ] 1.6 Decide and record the SSH source CIDRs the prod firewall will allow (see the open question in `design.md` — do not default to `0.0.0.0/0`).
- [ ] 1.7 Create or select the SSH key pair for prod access and register its public key.
- [ ] 1.8 Confirm the **Read & Write** token is stored only as the `production` Environment secret (task 2.3) and is not exported into any local shell, dotfile, `direnv` file, `.tfvars` file, or credential helper. Configure local shells with the **Read Only** token instead — it is enough for `terraform plan`, and it makes a local `terraform apply` fail at the API rather than by convention.
- [ ] 1.9 Investigate whether HCP Terraform workspace permissions can grant the operator's own user enough access for local `terraform plan` (state read plus locking) while denying the state write a local `terraform apply` needs. Record the finding; adopt this second layer only if it does not break local plan.

## 2. Repository Settings and Protection

- [x] 2.1 Create a `production` GitHub Environment with a required-reviewer protection rule.
- [ ] 2.2 Add the **Read Only** Hetzner token as a *repository* secret named `HCLOUD_TOKEN`.
- [ ] 2.3 Add the **Read & Write** Hetzner token as a `production` *Environment* secret, also named `HCLOUD_TOKEN`, so environment scope shadows repository scope for gated jobs only.
- [ ] 2.4 Confirm no static HCP Terraform API token is stored as a repository or environment secret.
- [ ] 2.5 Enable branch protection on `main`: require a pull request, require status checks to pass, block force-pushes and direct pushes.
- [ ] 2.6 Set the repository's default `GITHUB_TOKEN` workflow permissions to read-only.
- [ ] 2.7 Set workflow artifact retention to the shortest workable period (saved plan files contain sensitive values in cleartext).

## 3. Repo Scaffolding and Local Tooling

- [x] 3.1 Create the `environments/prod/` and `modules/` directory structure.
- [x] 3.2 Add a Terraform-aware `.gitignore` covering `.terraform/`, `*.tfstate*`, `*.secret.tfvars`, and `secrets.auto.tfvars`. Do **not** add a blanket `*.tfvars` rule — CI needs the committed non-secret `terraform.tfvars`.
- [x] 3.3 Add `.pre-commit-config.yaml` using `antonbabenko/pre-commit-terraform` hooks for `terraform fmt`, `tflint`, `terraform validate`, and `gitleaks`.
- [x] 3.4 Add `commitlint` configuration for Conventional Commits and wire it into a `pre-commit` (or existing) commit-msg hook.
- [x] 3.5 Add `.tflint.hcl` enabling only the bundled `terraform` ruleset. (There is no Hetzner/`hcloud` tflint ruleset — do not attempt to enable one.)
- [x] 3.6 Verify the repo README already documents local setup (installing `pre-commit`, running `pre-commit install`) and the drift-workflow re-enable runbook step (both added by the already-archived `project-foundation` change); extend if any detail is missing or out of date once the actual workflows exist.
- [x] 3.7 Verify the repository-root `AGENTS.md` already states that `terraform apply` is never run locally and that production changes reach Hetzner only through the gated pipeline (added by the already-archived `project-foundation` change, under "Production changes never bypass the pipeline"), and that the same prohibition is recorded in the README runbook; extend if anything is missing.

## 4. Terraform Module and Prod Environment

- [x] 4.1 Implement `modules/server` encapsulating the `hcloud_server` resource, parameterized by variables (server type, region, image, labels).
- [x] 4.2 Make firewall attachment structural in the module: create an `hcloud_firewall` with default-deny inbound and explicitly enumerated allow rules, and attach it to the server so a firewall-less server is not expressible.
- [x] 4.3 Register the SSH key via `hcloud_ssh_key` and ensure password authentication is disabled on the server.
- [x] 4.4 Set `backups = true` on the server.
- [x] 4.5 Expose `delete_protection` as a module variable (with `rebuild_protection` set to match, as the provider requires) and set it to `true` from `environments/prod/`. Do **not** put `lifecycle { prevent_destroy = true }` in the module — it accepts only literals and would make the module undestroyable for all future environments.
- [x] 4.6 Verify against the pinned provider version whether `delete_protection` blocks `terraform destroy` or is lifted by the provider; record the finding, and rely on the CI destroy-policy gate (task 6.4) as the Terraform-side guard regardless. **Finding recorded in design.md Decision 7:** the provider does not reliably block or fail fast on destroy/replace when `delete_protection = true` (upstream bugs hetznercloud/terraform-provider-hcloud#1014, #519 — behavior ranges from hanging indefinitely to silently destroying the "protected" resource). The CI destroy-policy gate is the actual guard; `delete_protection` is kept only for blocking deletion via the Hetzner console/API outside Terraform.
- [x] 4.7 Add `variable validation` blocks rejecting unsafe or malformed inputs at plan time — at minimum, reject `0.0.0.0/0` as an SSH source CIDR.
- [x] 4.8 Ensure the module applies `environment` and `managed_by = "terraform"` labels to every `hcloud_*` resource it creates.
- [x] 4.9 Implement `environments/prod/` calling `modules/server` with prod-specific variables, including a `cloud` block in `versions.tf` configured for the `infrastructure-prod` HCP Terraform workspace (CLI-driven). The organization name is a placeholder (`REPLACE_WITH_HCP_ORGANIZATION`) pending task 1.1 creating the actual organization.
- [ ] 4.10 Commit `environments/prod/terraform.tfvars` with the non-secret server sizing/region/image/CIDR values. **Partially done:** `name`/`server_type`/`image`/`location` are committed; `ssh_allowed_cidrs` and `ssh_public_key` are deliberately left unset (undefined vars, not guessed placeholders) — blocked on task 1.6 (CIDR decision) and task 1.7 (SSH key pair).
- [x] 4.11 Run `terraform init` locally against the prod environment to generate and commit `.terraform.lock.hcl`. Ran `terraform init -backend=false` (the real HCP backend can't be reached yet — placeholder org, task 1.1) — provider locking is independent of backend selection, so the resulting lock file (hcloud provider `1.68.0`, satisfying `~> 1.52`) is correct and committed. Re-run a plain `terraform init` once the real workspace exists to confirm the backend itself connects.

## 5. GitHub Actions: Pull Request Validation

- [ ] 5.1 Add a workflow triggered on pull requests that runs `terraform fmt -check`, `terraform validate`, and `tflint`. Register it as the required status check — and do **not** use a workflow-level `paths` filter on it, or PRs touching only non-Terraform files will hang unmergeable. Condition the Terraform steps on changed paths *inside* an always-running job instead.
- [ ] 5.2 Add a Trivy misconfiguration-scanning step, including any custom Hetzner policies committed under the repo.
- [ ] 5.3 Add a `gitleaks` secret-scanning step that invokes the **CLI binary**, not `gitleaks/gitleaks-action@v2` (which needs a paid license for org-owned repos and stops working when Node 20 leaves GitHub runners on 2026-09-16).
- [ ] 5.4 Add a `terraform plan` step that runs after validation passes and posts the plan output as a PR comment. The job MUST NOT declare `environment: production` — that would block every PR on manual approval and hand it the write-capable token.
- [ ] 5.5 Declare least-privilege `permissions:` per job: `pull-requests: write` only on the commenting job, `id-token: write` only on jobs authenticating to HCP Terraform.

## 6. GitHub Actions: Gated Apply

- [ ] 6.1 Add an apply workflow on push to `main` with `concurrency: { group: terraform-prod, cancel-in-progress: false }` so runs queue in order rather than overlapping.
- [ ] 6.2 Implement job A (plan): no `environment:` declared, authenticates with the read-only token, runs `terraform plan -out=tfplan`.
- [ ] 6.3 In job A, write the human-readable plan to `$GITHUB_STEP_SUMMARY` so the approver can read the exact diff before approving.
- [ ] 6.4 In job A, implement the destroy-policy gate: parse `terraform show -json tfplan` and fail the workflow if any resource action is `delete` or `replace`, unless the PR carries the override label (mechanism assumed to be a PR label — see design.md's Open Questions; settle before relying on it in production). Since job A runs on `push` to `main` with no direct pull-request context, resolve the pull request associated with the triggering push (e.g. via the GitHub API using the merge commit SHA) to check for the label.
- [ ] 6.5 In job A, upload `tfplan` as a workflow artifact.
- [ ] 6.6 Implement job B (apply): `needs` job A, declares `environment: production`, downloads `tfplan`, runs `terraform apply tfplan`.
- [ ] 6.7 Verify the read-write `HCLOUD_TOKEN` is unreadable by any job until the `production` approval is granted, and that job A completed using only the read-only token.
- [ ] 6.8 Define and document the behavior when reviewer approval outlasts the `tfplan` artifact's retention window: job B SHALL fail cleanly (not apply a stale or missing plan) if the artifact has expired, requiring job A to rerun and produce a fresh plan for re-review.

## 7. GitHub Actions: Drift Detection

- [ ] 7.1 Add a scheduled nightly workflow that runs `terraform plan -lock=false` (no apply) against `environments/prod/`, and also accepts `workflow_dispatch`.
- [ ] 7.2 On a non-empty diff, create or update a **single** deduplicated GitHub issue containing the diff; close or resolve it when a later run finds no drift.
- [ ] 7.3 Note in the README runbook that GitHub auto-disables scheduled workflows after 60 days of repository inactivity, and how to re-enable this one.

## 8. Dependency Automation

- [ ] 8.1 Add a `dependabot.yml` entry for the `terraform` package ecosystem targeting `environments/prod/` and `modules/server/`.
- [ ] 8.2 Add a `dependabot.yml` entry for the `github-actions` ecosystem.
- [ ] 8.3 Add a scheduled workflow that runs `pre-commit autoupdate` and opens a PR when hook revisions change. (Dependabot has no `pre-commit` ecosystem.)

## 9. End-to-End Validation

- [ ] 9.1 Open a pull request with a trivial change to validate the full PR pipeline (fmt/lint/Trivy/gitleaks/plan-comment) end-to-end before any real apply.
- [ ] 9.2 Open a documentation-only pull request and confirm the required status check reports success rather than hanging pending.
- [ ] 9.3 Merge the validated PR, read the plan summary in job A, approve the gated `production` apply, and confirm the server is created successfully on Hetzner Cloud.
- [ ] 9.4 Verify the firewall: confirm a non-allowed inbound port is refused and that SSH succeeds only from an allowed CIDR with key authentication.
- [ ] 9.5 Verify the destroy-policy gate fires: open a throwaway PR forcing a resource replacement and confirm the pipeline fails without the override label.
- [ ] 9.6 Manually trigger the drift-detection workflow to confirm it runs cleanly, then make a deliberate out-of-band change in the Hetzner console and confirm the drift issue is opened, deduplicated on a second run, and closed after reverting.
- [ ] 9.7 Verify the workstation boundary: with the local shell holding the Read Only token, confirm `terraform plan` against `environments/prod/` succeeds and `terraform apply` fails with an authorization error from the Hetzner Cloud API.
