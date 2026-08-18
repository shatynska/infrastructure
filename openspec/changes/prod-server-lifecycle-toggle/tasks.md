## 1. Terraform Configuration

- [x] 1.1 Add `variable "server_enabled"` to `environments/prod/variables.tf` (`bool`, default `true`).
- [x] 1.2 Add `count = var.server_enabled ? 1 : 0` to the `module "server"` block in `environments/prod/main.tf`.
- [x] 1.3 Update `environments/prod/outputs.tf` to read `one(module.server[*].id)` and `one(module.server[*].ipv4_address)` instead of direct attribute access.
- [x] 1.4 **Revised during implementation** (see design.md's Decisions 2/3 and the note in Context — the original `removed`-block approach failed: Terraform requires a `removed` target to be genuinely absent from source, not merely non-instantiated via `count = 0`, and it would have needed a fresh `import` on every future re-enable regardless). Remove `hcloud_ssh_key` and `ssh_public_key` from `modules/server`; add `ssh_key_id` as a required module input; update `hcloud_server.this`'s `ssh_keys` to `[var.ssh_key_id]`.
- [x] 1.5 Add `environments/prod/ssh_key.tf`: a standalone `hcloud_ssh_key` resource (using `var.ssh_public_key`, still declared at the environment layer), plus a `moved` block relocating the existing resource from `module.server.hcloud_ssh_key.this` to the new address. Pass `ssh_key_id = hcloud_ssh_key.this.id` into the module call.
- [x] 1.6 Delete `environments/prod/import.tf` (its one-time purpose — adopting the SSH key — is superseded by 1.5's relocation; keeping both would be contradictory).

## 2. Rollout (Decommission the Current Server)

- [x] 2.1 Set `server_enabled = false` in `environments/prod/terraform.tfvars`, leaving every other value (`name`, `server_type`, `image`, `location`, `ssh_public_key`, `ssh_allowed_cidrs`, `web_allowed_cidrs`) untouched.
- [x] 2.2 Verify locally: `terraform fmt -check -recursive`, `terraform validate`.
- [x] 2.3 Verify locally with a live `terraform plan` against the real HCP Terraform backend: expect the server and firewall planned for destruction, and the SSH key shown as *moved* (relocated to its new address), not created or destroyed. Confirmed: `0 to add, 1 to change, 2 to destroy` — the SSH key moved from `module.server.hcloud_ssh_key.this` to `hcloud_ssh_key.this` and updated in-place (name only, a cosmetic change), server and firewall destroyed.
- [x] 2.4 Commit and open a PR against `main`. https://github.com/shatynska/infrastructure/pull/10
- [x] 2.5 Confirm the PR's `validate` check passes and its plan comment matches the local plan from 2.3. Passed; plan comment matches exactly (SSH key moved + renamed, server and firewall destroyed).
- [x] 2.6 Add the destroy-policy gate's override label to the PR (required — this plan contains `delete` actions). Created the `destroy-override` label (didn't exist yet) and applied it.
- [ ] 2.7 Merge the PR and approve the gated `production` apply.
- [ ] 2.8 Confirm the apply succeeds: server and firewall destroyed, SSH key relocated (not touched on the Hetzner side), no errors.

## 3. Validation

- [ ] 3.1 Confirm via the Hetzner API or console that the SSH key (id `117088533`) still exists, unchanged, after the apply.
- [ ] 3.2 Confirm via the HCP Terraform workspace (resource count) that state reflects only what should remain (one managed resource — the relocated SSH key; server and firewall destroyed).
- [ ] 3.3 Confirm the full re-enable path works with no extra step: with `server_enabled` set back to `true` locally (do not apply unless the operator wants the server back), `terraform plan` shows the server and firewall recreated using the existing `terraform.tfvars` values and the existing (already-managed) SSH key, with no additional input, no fresh `import`, and no uniqueness conflict.
