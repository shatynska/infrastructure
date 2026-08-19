## Context

`.github/workflows/pr-validation.yml` currently has three separate steps that name directories literally: `terraform validate (modules/server)`, `terraform validate (environments/prod)`, and a `tflint` step that runs `--chdir=modules/server` then `--chdir=environments/prod`. Today `modules/` holds `server` and `volume`, and `environments/` holds only `prod`; `modules/volume` is not in either list. See proposal.md - Why.

Both `modules/*` directories and `environments/prod` validate cleanly with `terraform init -backend=false` — `environments/prod`'s HCP Terraform Cloud backend (`versions.tf`'s `cloud {}` block) is only needed for the real `terraform plan`/`apply` steps later in the same job, which are unaffected by this change. `tflint` already runs a single `--init` for plugins at the repo root before its per-directory `--chdir` invocations.

## Goals / Non-Goals

**Goals:**
- `terraform validate` and `tflint` run against every `modules/*` and `environments/*` directory that has `.tf` files directly in it, discovered at CI run time.
- `terraform test` runs against every `modules/*` directory that has `*.tftest.hcl` files, discovered at CI run time.
- Adding a new module or environment directory requires no edit to `pr-validation.yml`.

**Non-Goals:**
- Changing `terraform fmt -check -recursive`, Trivy, or `gitleaks` — already repo-wide.
- Changing the `terraform plan`/apply steps, which only ever target `environments/prod`.
- Adding a Hetzner-specific tflint ruleset (out of scope, unrelated to this gap).
- Recursing into nested directories beyond one level under `modules/`/`environments/` (matches current layout; no nested modules exist).

## Decisions

**Discovery: shell glob loop, not a matrix.** Iterate `for dir in modules/*/ environments/*/` in a single step's `run:` block, testing `compgen -G "$dir"'*.tf'` (or equivalent) before acting, rather than a GitHub Actions `strategy.matrix` computed by a separate job. A matrix would need a prior job to emit the directory list as JSON, adding a job dependency and an artifact hand-off for no benefit at this repo's current size (three directories total). A plain loop keeps the change to the existing single `validate` job.
- Alternative considered: `dorny/paths-filter` (already a dependency) with a per-directory output — rejected, it filters *changed* paths, not *existing* directories; a module added but not yet touched by the current PR should still be checked once merged, and this framing conflates "what changed" with "what to validate."

**One loop covers both `terraform validate` and `tflint`.** Replace the three named steps with two loop-based steps (one for `validate`, one for `tflint`), each iterating the same directory list, rather than a single step doing both per directory. Keeping them as separate steps preserves today's behavior of two distinct check names in the GitHub UI, so a validate failure and a lint failure remain distinguishable at a glance.

**`terraform test` is a new, separate step**, looping only over `modules/*/` (not `environments/*/` — environments are compositions, not independently tested units per `AGENTS.md`), running `terraform test` in any directory where `tests/*.tftest.hcl` exists. `terraform test` handles its own module init; no separate `terraform init` is required first.

**Fail-fast, matching existing behavior.** Each loop runs directories in sequence and exits non-zero on the first failure (`set -euo pipefail`), the same fail-fast behavior the current three named steps already have as sequential steps. Collecting and reporting all failures across all directories before exiting is not pursued — it would change existing behavior for `modules/server`/`environments/prod` beyond this change's scope.

## Risks / Trade-offs

- [A directory under `modules/` with `.tf` files but not yet meant to be validated (e.g. mid-refactor, deliberately broken)] → None today; if this becomes a real need, an explicit skip marker (e.g. a `.tflintignore`-style file) can be added later — not needed for the current two-module repo, so not built preemptively.
- [Loop-based steps are slightly harder to read in the workflow YAML than named steps] → Mitigated by a comment in the workflow explaining the discovery glob, consistent with this file's existing comment style.
- [`terraform test` step increases CI time as more modules gain tests] → Acceptable; this is the intended effect of wiring it in at all, and Terraform tests are expected to stay fast (no real infrastructure is created — HCP Terraform Cloud `cloud {}` blocks are absent from `modules/*`).
