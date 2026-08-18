## Context

`environments/prod` currently calls `module "server"` unconditionally — no `count`/`for_each` on the block. The server was just created for the first time (PR #2, #8) and its `delete_protection`/`rebuild_protection` have already been separately flipped to `false` in a prior, already-merged-and-applied PR (#9), so this change can assume Hetzner will actually accept a delete when it comes to that.

An earlier version of this design tried to detach the pre-existing SSH key (Hetzner id `117088533`) from Terraform via a `removed` block while leaving it declared inside `modules/server`. That failed during implementation: Terraform's `removed` block requires the target resource to be genuinely absent from the `.tf` source, not merely non-instantiated via `count = 0` — since `modules/server` still declares `hcloud_ssh_key` unconditionally, Terraform rejected the plan with "Removed resource still exists." This revision fixes that by decoupling the key's lifecycle from the module entirely, per the user's explicit choice over the cheaper alternative (a one-time `state rm`, which would not have prevented the same conflict from recurring on every future re-enable).

See proposal.md for the motivation. This document covers how the toggle is implemented and the addressing subtlety it introduces.

## Goals / Non-Goals

**Goals:**
- Let `environments/prod` stop creating the server without deleting its configuration.
- Keep the pre-existing, imported SSH key under continuous Terraform management, permanently decoupled from the server's own on/off lifecycle — not merely detached once, but never at risk of the same create-conflict again.
- Roll the toggle out by actually decommissioning the current server + firewall through the normal gated pipeline.

**Non-Goals:**
- Preserving the server's disk/data across a toggle-off/toggle-on cycle — see Risks. This is a presence/absence toggle, not a stop/start or snapshot-restore mechanism.
- A generic multi-environment or multi-server toggle pattern — this covers the single `environments/prod` server only, matching the project's existing single-environment scope (bootstrap-hetzner-iac design.md Decision 3).
- Any broader `modules/server` redesign beyond relocating SSH key ownership (see Decision 3). The module's server/firewall responsibilities are unchanged.

## Decisions

**1. `count` on the module block, at the environment call site, not inside `modules/server`.**
`count = var.server_enabled ? 1 : 0` is Terraform's standard idiom for "this may or may not exist." Putting it on the `module "server" { ... }` call in `environments/prod/main.tf` — not inside the module itself — keeps the module's remaining responsibility (server + firewall, given an SSH key it doesn't own) a pure "given these inputs, create a server" building block; whether prod currently wants a server running is an environment-level operational concern.

Considered and rejected: a `for_each` toggle (unnecessary — this is a single on/off switch, not a keyed set); a second Terraform workspace per enabled/disabled state (fragments state for no benefit); powering the server off via the Hetzner API instead of destroying it (a different mechanism entirely — `hcloud server poweroff` stops billing for compute but the resource and its disk still exist and are still billed at a reduced rate; the user asked to destroy it via the pipeline we built, not pause it, and a stop/start toggle doesn't go through `terraform plan`/apply at all, so it wouldn't get the review-and-approve treatment every other prod change does).

**2. The SSH key is relocated with a `moved` block, not detached with a `removed` block.**
The key was never something to stop managing — it's something that shouldn't have been owned by an ephemeral, conditionally-created module in the first place. So instead of asking Terraform to forget it (which hit the `removed`-block constraint described in Context), this revision keeps the key under continuous management, just at a new, permanent address: a standalone `hcloud_ssh_key` resource in `environments/prod` (see Decision 3), independent of `module.server`'s `count`.

`moved { from = module.server.hcloud_ssh_key.this; to = hcloud_ssh_key.this }` tells Terraform these are the same real-world object at a new configuration address — no destroy, no recreate, no re-import, ever, regardless of how many times `server_enabled` flips. This is the correct tool for "this resource's address changed"; `removed` is for "this resource is no longer managed by Terraform at all," which was never actually the goal.

Server and firewall get no such treatment: this rollout is destroying them anyway (that's the point), so letting their old, unindexed addresses (`module.server.hcloud_server.this`, etc.) simply disappear as `count` moves future addresses to `module.server[0].*` — planned as a destroy — produces exactly the intended outcome with no extra mechanism.

**3. `modules/server` no longer creates the SSH key; it takes one as an input.**
`modules/server/main.tf` drops the `hcloud_ssh_key` resource and the `ssh_public_key` variable. `hcloud_server.this`'s `ssh_keys` argument now reads `[var.ssh_key_id]`, a new required string input. `environments/prod` owns the `hcloud_ssh_key` resource directly (in a new `ssh_key.tf`) and passes its `id` into the module call.

This is a real, if small, change to the module's public interface — the one thing the original version of this design explicitly tried to avoid (see Context). It's justified because the original module design conflated two things with genuinely different lifecycles: a login credential that predates this project and should outlive any particular server instance, and the ephemeral compute the module's actual name describes. Nothing else about the module's responsibilities changes, and no other consumer of `modules/server` exists yet to be broken by the interface change.

**4. Outputs read through `one(module.server[*].id)`, not direct attribute access.**
`count` makes `module.server` a 0-or-1-element list rather than a single object, so `module.server.id` is no longer valid. `one(...)` is the idiomatic builtin for exactly this shape: it returns the single value when the list has one element, `null` when it has zero, and errors if it somehow has more than one (which `count = 0/1` makes impossible here).

## Risks / Trade-offs

- **Toggling off destroys Hetzner's automatic backups along with the server.** Hetzner Cloud backups are not a separable/restorable-independently resource the way e.g. an AWS EBS snapshot is — they're tied to the server and are gone once it's deleted. *Mitigation*: none available at the infrastructure layer; this is a Hetzner platform constraint. The toggle is a presence/absence switch, not a stop/restore mechanism (see Non-Goals) — anyone using it should understand "recreate" means a fresh server with the same *configuration*, not the same *data*.
- **The rollout PR trips the existing destroy-policy gate** (bootstrap-hetzner-iac's CI/CD capability) and needs the override label to merge. *Mitigation*: none needed — this is the gate working as designed, not a defect to work around.
- **`modules/server`'s public interface changes** (`ssh_public_key` removed, `ssh_key_id` added) — a breaking change for any future consumer expecting the old contract. *Mitigation*: no other consumer exists yet (the project is still single-environment, per bootstrap-hetzner-iac design.md Decision 3); the module isn't published or versioned externally, so there's no compatibility surface to break today.

## Migration Plan

1. (Already done, PR #9) `delete_protection`/`rebuild_protection` set to `false` on the live server — precondition for any destroy to succeed at all.
2. This change: remove `hcloud_ssh_key` and `ssh_public_key` from `modules/server`, add `ssh_key_id` as a module input, add a standalone `hcloud_ssh_key` resource plus a `moved` block in `environments/prod/ssh_key.tf`, add `server_enabled`/`count`/`one(...)`-based outputs for the server/firewall toggle.
3. Set `server_enabled = false` in `environments/prod/terraform.tfvars` as part of the same PR, so the rollout itself performs the decommission.
4. Merge with the destroy-policy gate's override label; approve the gated apply. Expect the plan to show the SSH key *moved* (not created, not destroyed), and the server + firewall destroyed.
5. To recreate later: set `server_enabled = true` (or remove the line, since the variable defaults to `true`) and go through the same PR/plan/approve flow — no other file needs to change and no fresh import is ever needed, since the key was never tied to the toggle in the first place.

Rollback: none needed beyond the toggle itself — setting `server_enabled` back to `true` and reapplying is the rollback path, by construction.
