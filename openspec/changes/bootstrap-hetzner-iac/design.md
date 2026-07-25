## Context

The repository is currently empty aside from OpenSpec scaffolding. This is a greenfield Terraform setup targeting Hetzner Cloud, starting with one production server. There is no existing state, no existing CI, and no prior Terraform conventions in this repo to reconcile with — every decision below is a fresh choice, not a migration.

## Goals / Non-Goals

**Goals:**
- Establish a repo structure, local tooling, and CI/CD pipeline that are safe to run against real infrastructure from the first `terraform apply`.
- Make destructive or unnoticed changes hard by default (review gates, destroy protection, secret scanning, drift visibility).
- Keep the pipeline's source of truth in one place (GitHub), consistent with existing developer habits.
- Leave a clean seam for adding further environments later without restructuring what's built now.

**Non-Goals:**
- Multi-environment (staging) setup — deferred to a future change. This change scopes to `environments/prod/` only.
- Specific server sizing/region/image decisions — left as `terraform.tfvars` values to fill in during implementation, not a design concern.
- Terraform Cloud's VCS-driven workflow — considered and explicitly not used (see Decisions).

## Decisions

**1. Terraform Cloud CLI-driven workflow, not VCS-driven.**
TFC supports a VCS-driven workflow (TFC connects directly to the GitHub repo and runs plan/apply itself on webhook events, with approval via TFC's own "Confirm & Apply" UI) and a CLI-driven workflow (TFC is used purely as remote state + locking backend, while GitHub Actions runs the `terraform` CLI and gates apply via a GitHub Environment approval rule). VCS-driven is genuinely less to configure — no apply-orchestration workflow to write. We chose CLI-driven anyway: PR-time checks (fmt, lint, Trivy, gitleaks) must run in GitHub Actions regardless, so VCS-driven would split one logical pipeline (validate → plan → review → apply) across two UIs — GitHub for checks, TFC for plan/apply/approval. CLI-driven keeps the entire pipeline in one place, matching the GitHub-PR-centric workflow already used for this project's other tooling (commitlint, etc.). The trade-off is losing TFC's built-in run history/UI and having to build the apply-gating workflow ourselves; GitHub Actions logs become the source of truth instead.

**2. Environment folders, not environment branches.**
`environments/prod/` (and any future `environments/<env>/`) as directories in `main`, not long-lived `prod`/`staging` branches. Branch-per-environment invites drift between branches and ambiguity about which branch is "truth." A single `main` branch with folder-scoped state keeps one linear history. Even though this change only adds `prod`, the structure is chosen so a later `environments/staging/` slots in without moving anything.

**3. Single environment (prod) for this change.**
Originally scoped with a staging environment from day one, but narrowed to prod-only to keep this bootstrap change small and immediately shippable. This simplifies the CI/CD pipeline for now — no cross-environment sequencing logic is needed since there's only one environment to gate. Adding staging later is a follow-up change that primarily adds a new folder + workspace + pipeline job, not a redesign.

**4. `pre-commit` + `antonbabenko/pre-commit-terraform`, not a Husky-based setup.**
Husky is a Node-ecosystem git-hooks runner; the closest tool with first-class Terraform hook support is `pre-commit` (Python-based) via the `pre-commit-terraform` hook collection, which wraps `terraform fmt`, `tflint`, `terraform validate`, and can invoke security/secret scanners in one config file. This is the de facto standard in the Terraform community, so it's chosen over trying to wire Husky to shell out to Terraform tooling manually.

**5. Trivy for misconfiguration scanning, not tfsec.**
`tfsec` was acquired by Aqua Security and merged into Trivy; the `tfsec` project itself is in maintenance mode and points users to Trivy's `trivy config` misconfiguration scanning as the successor — same underlying rule engine, actively maintained. Trivy is used specifically in its misconfig-scanning role here.

**6. `gitleaks` kept as a separate secret scanner, not consolidated into Trivy's built-in secret scanner.**
Trivy also has a secret-scanning mode, which would reduce the toolchain to one tool. `gitleaks` is kept as a dedicated second tool because it's purpose-built for fast, diff-scoped scanning of staged changes in pre-commit and has a more battle-tested secret-pattern ruleset for that specific job. `gitleaks` and Trivy check different concerns (leaked credentials vs. misconfigurations) and both run in pre-commit and CI.

**7. `lifecycle { prevent_destroy = true }` on stateful/critical resources.**
Applied to the server resource (and any future volumes). Turns an accidental destroy-and-recreate plan (e.g., from a renamed resource or changed immutable attribute) into a hard error requiring explicit removal of the lifecycle block, rather than a silent destructive apply.

**8. Nightly scheduled drift-detection workflow (plan-only, no apply).**
Runs `terraform plan` against prod on a schedule and surfaces any diff, without applying anything. Justified as free: each run costs roughly 1-2 minutes of GitHub Actions runtime, well within GitHub's free-tier Actions minutes, and doesn't invoke TFC run execution since the backend is CLI-driven.

**9. Dependabot for the `terraform` package ecosystem.**
Native GitHub Dependabot support bumps `required_providers` version constraints and pre-commit hook revisions via PR — parallel to how JS dependency bumps are already handled in other repos, and low effort to configure.

## Risks / Trade-offs

- **No staging environment yet** → every change goes from PR review straight to prod. *Mitigation*: PR-posted `terraform plan` output for human review, required-reviewer approval gate on the `production` GitHub Environment, and `prevent_destroy` on critical resources. Staging can be added later as a lower-stakes environment to test against first.
- **CLI-driven means building and maintaining the apply-gating workflow ourselves**, and no TFC run UI/history. *Mitigation*: GitHub Actions run logs serve as the record; the workflow is a one-time cost, not ongoing.
- **Nightly drift detection may produce noise** from provider-managed attributes that change outside Terraform's control (e.g., Hetzner-assigned fields). *Mitigation*: address with `lifecycle.ignore_changes` on specific attributes as false positives are discovered — not solved preemptively.
- **Single Hetzner project/token for prod** means a compromised token affects the only environment that exists. *Mitigation*: acceptable for now since there is nothing to isolate from yet; revisit when staging is added.
- **GitHub Actions secrets (`HCLOUD_TOKEN`, TFC API token) must be scoped to the `production` Environment**, not repo-wide — otherwise the required-reviewer approval gate is cosmetic, since any workflow run could read the secret before approval. This must be set up correctly during implementation.

## Migration Plan

Greenfield setup — no existing state or infrastructure to migrate. Rollout order:
1. Create the Terraform Cloud organization/workspace (`infrastructure-prod`, CLI-driven — no VCS connection) and the Hetzner Cloud project + `HCLOUD_TOKEN`.
2. Scaffold repo tooling: `.gitignore`, `.pre-commit-config.yaml`, `commitlint` config, `.terraform.lock.hcl` (generated on first `terraform init`).
3. Add GitHub Actions secrets scoped to the `production` Environment (`HCLOUD_TOKEN`, TFC API token), and configure the required-reviewer protection rule.
4. Write `modules/server` and `environments/prod` consuming it.
5. Open a PR to validate the full pipeline (fmt/lint/Trivy/gitleaks/plan) end-to-end before any real `apply`.
6. Merge and manually approve the first gated apply, creating the actual server.

Rollback: since this is the first infrastructure in the account, "rollback" means `terraform destroy` via the same gated pipeline — no separate rollback path is needed at this stage.

## Open Questions

- Server sizing/region/image: left to be filled in as `terraform.tfvars` during implementation, not a blocking design decision.
- Exact trigger condition for the nightly drift-detection workflow's alerting (e.g., fail the workflow vs. post to a notification channel) — to be decided during implementation based on what's easiest to wire up first (a failing scheduled workflow is the minimum viable signal).
