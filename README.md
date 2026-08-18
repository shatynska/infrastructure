# infrastructure

Terraform-managed infrastructure on Hetzner Cloud. State lives in HCP Terraform
(CLI-driven, local execution); GitHub Actions runs the `terraform` CLI and
gates every apply behind manual approval. See
`openspec/changes/bootstrap-hetzner-iac/design.md` for the full rationale
behind these choices.

Manual, ad-hoc server provisioning is hard to audit and drifts silently from
whatever's documented. This repository replaces that with declarative,
version-controlled infrastructure — every change goes through a reviewed
`terraform plan`, an exact saved plan approved before apply, and nightly
drift detection — prioritizing reliability, drift prevention, and
auditability of the infrastructure layer itself, ahead of any specific
workload. It's operated primarily by agentic/automated workflows (e.g.
Claude Code), with a human required to approve every change that reaches
production; see `AGENTS.md` for the conventions that assumes.

## Non-goals

- **Multi-cloud support.** Hetzner Cloud only.
- **Multi-region deployment.** Single region (`fsn1`) for the foreseeable
  future.
- **Container orchestration.** Plain VMs via `hcloud_server`; no
  Kubernetes, Nomad, or similar.

A staging environment is *not* a non-goal — it's an anticipated near-term
addition (see Status below), not a rejected idea.

## Repository layout

- `modules/` — shared, reusable Terraform modules (e.g. `modules/server`).
- `environments/<name>/` — one folder per environment (currently only `prod`),
  each calling the shared modules with environment-specific variables. New
  environments are added as new folders, never as branches.

## Local setup

1. Install [pre-commit](https://pre-commit.com/) and the tools its hooks
   shell out to: `terraform`, [`tflint`](https://github.com/terraform-linters/tflint),
   and [`gitleaks`](https://github.com/gitleaks/gitleaks).
2. From the repo root, run:

   ```sh
   pre-commit install --hook-type pre-commit --hook-type commit-msg
   ```

   This installs the formatting/linting/validation/secret-scan hooks (running
   on `git commit`) and the Conventional Commits message check (running on
   the commit message itself).
3. Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, ...) — enforced locally by the
   `commitlint` hook and mirrored by CI.
4. Local `terraform plan`/`validate` needs the **Read Only** Hetzner token as
   `HCLOUD_TOKEN`. Recommended: [`direnv`](https://direnv.net/) so it's only
   loaded while you're in this directory:

   ```sh
   cp .envrc.example .envrc   # fill in the real token; .envrc is gitignored
   direnv allow
   ```

   Never put the **Read & Write** token here or in any other local file — it
   lives exclusively in the `production` GitHub Environment secret. See
   `AGENTS.md`.

## Environment variables and secrets

Each `environments/<env>/terraform.tfvars` is committed and holds **non-secret**
configuration only (server type, region, image, allowed CIDRs, labels). Files
matching `*.secret.tfvars` or `secrets.auto.tfvars` are gitignored and must
never be committed.

## CI/CD

- **Pull requests**: `terraform fmt -check`, `terraform validate`, `tflint`,
  Trivy misconfiguration scanning, `gitleaks` secret scanning, then
  `terraform plan` posted as a PR comment.
- **Merge to `main`**: a two-job apply — a plan job (read-only Hetzner token)
  saves a plan file and posts its diff to the run summary and a destroy-policy
  check; an apply job (read-write Hetzner token) applies that exact saved plan
  only after a required reviewer approves the `production` GitHub Environment.
- **Nightly**: a nightly drift-detection plan (no apply) that opens or updates
  a single GitHub issue when the committed configuration diverges from real
  infrastructure, and closes it once resolved.

### Testing

Terraform has no traditional unit-test layer here; verification is the
static checks and plan review above, plus (as `modules/` grows past
`modules/server`) module-level tests in `modules/<name>/tests/*.tftest.hcl`,
run via `terraform test`. See
`openspec/changes/project-foundation/design.md` for the full testing
strategy.

### Re-enabling the drift-detection workflow

GitHub automatically disables `schedule`-triggered workflows after 60 days
without any repository activity. If the nightly drift check appears to have
stopped running, check **Actions → Drift Detection → ⋯ → Enable workflow**,
then trigger it once manually (`workflow_dispatch`) to confirm it runs clean.

## Status

This repository is being bootstrapped per
`openspec/changes/bootstrap-hetzner-iac/`. Several setup steps require
manual action outside version control (HCP Terraform org/workspace, Hetzner
Cloud project and tokens, GitHub environment/branch settings) — see that
change's `tasks.md` for the current checklist. Project identity, scope, and
non-goals are recorded in `openspec/changes/project-foundation/design.md`.

A staging environment (a second `environments/<name>/` folder reusing the
same modules) is anticipated as the next environment after `prod` is fully
stood up, but is not yet in scope.
