## 1. `modules/volume`

- [x] 1.1 Create `modules/volume/versions.tf` (mirror `modules/server/versions.tf`: `required_version >= 1.9.0`, `hcloud ~> 1.52`).
- [x] 1.2 Create `modules/volume/variables.tf`: `environment` (string, non-empty validation, matching `modules/server`'s style), `name` (string), `size` (number), `server_id` (string, `nullable = false` with a non-empty validation — the volume has no `location` of its own, so `server_id` must always be supplied, see design.md Decision 3), `delete_protection` (bool, default `true`), `labels` (map(string), default `{}`).
- [x] 1.3 Create `modules/volume/main.tf`: `locals.labels` merging `environment`/`managed_by = "terraform"` with `var.labels` (same pattern as `modules/server/main.tf`); an `hcloud_volume "this"` resource with `name`, `size`, `server_id`, `delete_protection`, `labels = local.labels`, and no `location` (derived from `server_id`).
- [x] 1.4 Create `modules/volume/outputs.tf`: `id` and `linux_device` (the device path the guest will see, useful for a future mount step).

## 2. Wire into `environments/prod`

- [x] 2.1 Add `volume_enabled` (bool, default `true`), `volume_name` (string), and `volume_size` (number) to `environments/prod/variables.tf`, following the existing variable description/validation style.
- [x] 2.2 Add a `module "volume"` block to `environments/prod/main.tf`: `count = var.volume_enabled && var.server_enabled ? 1 : 0` (the volume has no location of its own — see design.md Decision 3 — so it can only exist while the server does), `source = "../../modules/volume"`, `environment = "prod"`, `name = var.volume_name`, `size = var.volume_size`, `server_id = one(module.server[*].id)`, `delete_protection = true`.
- [x] 2.3 Add `volume_enabled = true`, `volume_name = "main-data"`, and `volume_size = 10` to `environments/prod/terraform.tfvars`.
- [x] 2.4 Add `volume_id` and `volume_linux_device` outputs to `environments/prod/outputs.tf`, reading through `one(module.volume[*].id)` / `one(module.volume[*].linux_device)`.

## 3. Verification

- [x] 3.1 Run `terraform fmt -check -recursive` from the repo root. Clean, no diff.
- [x] 3.2 Run `terraform test` in `modules/volume` (independently authored tests already exist at `modules/volume/tests/*.tftest.hcl` — see `openspec/changes/add-prod-data-volume/test-manifest.md`); confirm all 8 `run` blocks pass. Confirmed: `Success! 8 passed, 0 failed.`
- [x] 3.3 Run `terraform validate` in `environments/prod`. Confirmed: `Success! The configuration is valid.`
- [ ] 3.4 Run a live `terraform plan` in `environments/prod` (read-only token) with `volume_enabled = true` (the committed default): confirm it shows exactly one addition (the `main-data` volume, attached to the existing server, 10 GB, `hel1`, correctly labeled), and no changes to the server or firewall. **Blocked**: no `HCLOUD_TOKEN` is available in this session (the sandboxed agent environment has no local read-only token configured) — needs to be run by the operator, or the token supplied.
- [ ] 3.5 Locally (uncommitted) set `volume_enabled = false` and re-plan: confirm the volume is planned for destruction and nothing else changes. Locally (uncommitted) set `server_enabled = false` instead (`volume_enabled` back to `true`): confirm the plan destroys the server, firewall, **and** the volume together, per the `volume_enabled && server_enabled` coupling (design.md Decision 3). Revert both local-only changes afterward — this task exercises the coupling that `modules/volume/tests/` cannot (see test-manifest.md's "Unresolved project questions" — resolved by the user in favor of this live-plan review step, not an added automated test). **Blocked**: same as 3.4, needs `HCLOUD_TOKEN`.
- [ ] 3.6 Run `tflint` and the `gitleaks`/pre-commit hooks (or `pre-commit run --all-files`) before committing. **Blocked**: none of `pre-commit`, `tflint`, `gitleaks` are installed in this session's sandboxed environment. The repository's `pre-commit` hook (installed per the README's Local setup) runs these automatically on `git commit` for anyone with it installed; the GitHub Actions pipeline also runs `terraform fmt`/`validate`/`tflint`/Trivy/`gitleaks` on the PR regardless. Needs to be run by the operator, or in CI, before merge.

## 4. Rollout

- [x] 4.1 Commit and open a PR against `main`. https://github.com/shatynska/infrastructure/pull/25
- [x] 4.2 Confirm the PR's `validate` check passes and its plan comment matches the local plan from 3.4. `validate` passed. Plan comment differs from what 3.4 anticipated (that assumed the server already existed) — CI's plan revealed the live prod server had drifted (deleted outside of Terraform), so this PR now also recreates the server under the corrected `main-server`/`cx33` config (a pending, previously-uncommitted local edit, folded into this PR by user decision) alongside the volume: `2 to add, 1 to change (firewall rename, cosmetic), 0 to destroy`. No destroy-policy override label needed.
- [ ] 4.3 Merge the PR and approve the gated `production` apply.
- [ ] 4.4 Confirm the apply succeeds: `main-data` volume created and attached, server and firewall unchanged, no errors.
- [ ] 4.5 Confirm via the Hetzner API or console that the volume is attached to `main-server`, sized 10 GB, and carries `environment = prod` / `managed_by = terraform` labels.
