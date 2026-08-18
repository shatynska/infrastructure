## Why

The prod server was just created for the first time through the gated pipeline (PR #2, #8), confirming the whole pipeline works end-to-end. The operator now wants to tear it down again, but `environments/prod` currently has no way to stop creating the server short of deleting the module block and its supporting variables/outputs/tfvars entirely — which would lose the working configuration (server type, image, location, SSH CIDRs) and require digging through git history to recreate it. A conditional toggle keeps that configuration in place and makes "decommission now, recreate later" a one-line change instead of an archaeology exercise.

## What Changes

- Add a `server_enabled` boolean variable to `environments/prod` (default `true`) that gates whether the `module "server"` block creates anything at all, via `count = var.server_enabled ? 1 : 0`.
- Adjust `environments/prod/outputs.tf` to read through `one(module.server[*].id)` / `one(module.server[*].ipv4_address)` instead of direct attribute access, since `count` makes `module.server` a 0-or-1-element list rather than a single instance.
- Move ownership of the pre-existing SSH key (Hetzner id `117088533`, imported into Terraform in the bootstrap-hetzner-iac change) out of `modules/server` and into `environments/prod` as a standalone, always-present resource, relocated via a `moved` block rather than destroyed or detached. **Revised from an earlier version of this proposal**, which tried to detach the key from Terraform via a `removed` block while leaving it inside the module — that failed during implementation (Terraform requires a `removed` target's resource block to be genuinely deleted from source, not merely non-instantiated via `count = 0`) and would have needed a fresh `import` on every future re-enable regardless. Moving the key out of the toggle's scope entirely fixes this permanently. `modules/server` now takes an `ssh_key_id` input instead of creating its own key.
- Roll this out by setting `server_enabled = false` in `environments/prod/terraform.tfvars`, decommissioning the currently-running server and firewall through the normal gated pipeline (this trips the destroy-policy gate, so the rollout PR needs the override label).

## Capabilities

### New Capabilities
- `iac-server-lifecycle`: Conditional creation of the prod server via a boolean toggle, so it can be decommissioned and recreated without losing its configuration, and safe detachment (not destruction) of infrastructure that predates Terraform's management of it.

### Modified Capabilities
(none — `openspec/specs/` has no synced capabilities yet; bootstrap-hetzner-iac has not been archived. This change's delta stands alone until that sync happens.)

## Impact

- Affected code: `environments/prod/main.tf`, `environments/prod/outputs.tf`, `environments/prod/variables.tf`, `environments/prod/terraform.tfvars`, a new `environments/prod/ssh_key.tf` (standalone SSH key resource + `moved` block), and the deletion of `environments/prod/import.tf` (superseded). Also `modules/server/main.tf` and `modules/server/variables.tf` — the module's `ssh_public_key` input is replaced with `ssh_key_id`; this is a real (if small) change to the module's public interface, not just the environment layer.
- Affected infrastructure: the live prod server and firewall will be destroyed as part of rolling this out; the pre-existing SSH key remains under continuous Terraform management, relocated to a new address, never destroyed.
- No changes to the CI/CD pipeline itself — the existing destroy-policy gate, plan review, and approval flow apply unchanged.
