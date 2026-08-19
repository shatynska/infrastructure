## 1. Workflow changes

- [ ] 1.1 In `.github/workflows/pr-validation.yml`, replace the `terraform validate (modules/server)` and `terraform validate (environments/prod)` steps with a single loop-based step that iterates `modules/*/` and `environments/*/`, running `terraform init -backend=false && terraform validate` in each directory that contains `.tf` files directly in it, failing fast on the first error.
- [ ] 1.2 Replace the `tflint` step's two named `--chdir` invocations with a loop over the same directory list from 1.1, running `tflint --config="${{ github.workspace }}/.tflint.hcl" --chdir=<dir>` per directory, failing fast on the first error.
- [ ] 1.3 Add a new step, gated on the same `steps.changes.outputs.terraform == 'true'` condition as the other Terraform steps, that loops over `modules/*/` and runs `terraform test` in any directory containing `tests/*.tftest.hcl`, failing fast on the first failing test.
- [ ] 1.4 Add a short comment above the new loop-based steps (matching this file's existing comment style) explaining the discovery glob and pointing at this change, so a future reader understands why directories aren't named literally.

## 2. Verification

- [ ] 2.1 Run `terraform fmt -check -recursive`, `terraform validate`, and `tflint` locally against `modules/server`, `modules/volume`, and `environments/prod` to confirm the discovery loop would pass on the current tree before pushing.
- [ ] 2.2 Run `terraform test` locally in `modules/volume` to confirm it still passes (already run and passing per `add-prod-data-volume` task 3.2; re-run here only to confirm no regression from the workflow edit itself — the module code doesn't change).
- [ ] 2.3 A PR touching only `pr-validation.yml` does NOT trip the workflow's own `Detect Terraform changes` path filter (`environments/**`/`modules/**`), so all Terraform-conditioned steps — including the new ones — would be skipped rather than exercised, masking a broken loop under a green check. To actually verify the new steps run, include in the same PR a no-op touch under a covered directory (e.g. a comment-only edit to `modules/volume/versions.tf`) so the filter evaluates true, then confirm the `validate` job's plan/comment run shows the new loop-based steps executing against all three directories (`modules/server`, `modules/volume`, `environments/prod`), and that the `terraform test` step runs for `modules/volume`.
- [ ] 2.4 Confirm the PR shows zero Terraform resource changes (this is a CI-only change; the plan comment should be a no-op plan).

## 3. Rollout

- [ ] 3.1 Merge the PR once the `validate` check passes with the new steps green.
- [ ] 3.2 Mark this change's tasks complete and archive it.
