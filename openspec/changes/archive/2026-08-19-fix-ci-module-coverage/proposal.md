## Why

`add-prod-data-volume` added `modules/volume`, and CI never validated or linted it: `.github/workflows/pr-validation.yml` hardcodes `terraform validate`/`tflint` to only `modules/server` and `environments/prod` via literal `working-directory`/`--chdir` steps (lines 58–83). The PR that added the module still passed all required checks, because `terraform fmt -check -recursive` and the repo-wide Trivy/gitleaks scans covered it but validate/tflint silently did not (see `add-prod-data-volume` task 3.6). Separately, `terraform test` — this project's module-level test command per `AGENTS.md`, with tests already present at `modules/volume/tests/*.tftest.hcl` — has never been wired into the pipeline at all; it has only ever been run locally by hand. Both gaps mean a module can ship to prod without the checks the `iac-cicd-pipeline` capability's "Pull Request Validation Checks" requirement already promises.

## What Changes

- Replace the hardcoded `modules/server` / `environments/prod` enumeration in the `terraform validate` and `tflint` steps with directory discovery, so every directory under `modules/*` and `environments/*` (containing `.tf` files) is validated and linted automatically — not just the two that happen to be named today.
- Add a `terraform test` step that runs, for each directory under `modules/*` containing a `tests/*.tftest.hcl` glob match, `terraform test`.
- No change to `terraform fmt -check -recursive`, Trivy, or `gitleaks` — those are already repo-wide and out of scope.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `iac-cicd-pipeline`: "Pull Request Validation Checks" — validate/tflint coverage must extend to every `modules/*`/`environments/*` directory, discovered rather than enumerated by name, and `terraform test` must run in CI for any module that has tests.

## Impact

- `.github/workflows/pr-validation.yml`: the `terraform validate (modules/server)`, `terraform validate (environments/prod)`, and `tflint` steps are replaced with loop/discovery-based equivalents; a new step runs `terraform test` where applicable.
- No Terraform resource changes; no impact on `environments/prod` state.
