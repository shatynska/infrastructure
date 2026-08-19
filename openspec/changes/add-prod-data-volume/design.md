## Context

`modules/server` is the only existing module: a single-purpose "server + firewall" building block consumed once by `environments/prod/main.tf`, gated by `server_enabled` via `count`. `environments/prod` currently declares no block storage — the prod server's boot disk is its only disk. See proposal.md for the motivation; this document covers how the volume is added and attached.

The Hetzner Cloud Terraform provider's `hcloud_volume` resource takes a `server_id` (optional) to attach the volume to a server at creation, and a `location` that is required only when `server_id` is not set — when a server is given, the volume's location is derived from it, and the provider rejects a `location` that mismatches the server's own. `hcloud_volume` also supports `delete_protection`, `format`/`automount`, and `labels`, and has no `rebuild_protection` attribute (that concept applies to servers only).

## Goals / Non-Goals

**Goals:**
- A `production_data` volume, 10 GB, attached to the prod server at creation, protected from console deletion, correctly labeled.
- Match the existing `modules/server` conventions closely enough that the two modules read as one system: same labeling locals, same `*_enabled`/`count` toggle idiom, same `delete_protection` variable style.

**Non-Goals:**
- Filesystem provisioning inside the guest (mounting, `/etc/fstab`, partitioning) — out of scope for this Terraform-layer change; see Decision 4.
- A generic multi-volume or multi-server attachment mechanism — this covers the single `production_data` volume attached to the single prod server, matching the project's existing single-environment, single-server scope.
- Detach/reattach-across-servers lifecycle — the volume is expected to stay attached to the prod server for its lifetime; if that ever needs to change, `hcloud_volume_attachment` as a separate resource can be introduced then.
- The volume outliving the prod server it was created against — see Decision 3. The volume has no location of its own, so it cannot exist while the server is disabled; a future change can add an explicit `location` variable if that independence is ever actually needed.

## Decisions

**1. A new `modules/volume`, not an addition to `modules/server`.**
`modules/server` currently expresses "given these inputs, create a server + firewall" as a single, structurally-forced unit (see `iac-safety-hardening`'s Default-Deny Network Baseline requirement — a server without a firewall isn't expressible). A volume has an independent real-world lifecycle: it can be toggled off while the server stays up, or (in a future change) resized or reattached without touching the server at all. Folding it into `modules/server` would either force the volume to share the server's `count` (defeating the independent-toggle goal in proposal.md) or require a second, unrelated `count` inside the same module, which breaks the "one module, one responsibility" pattern the project has used since `modules/server` was written. A separate module keeps both building blocks independently toggleable and independently reusable by a future non-prod environment.

Considered and rejected: adding an optional `hcloud_volume` block directly inside `modules/server`, gated by a `volume_enabled` variable passed through to the module — rejected for the coupling reason above, and because it would make the server module's interface grow with every future storage-shaped need.

**2. Attachment via `hcloud_volume`'s own `server_id`, not a separate `hcloud_volume_attachment` resource.**
The provider offers two ways to attach a volume to a server: setting `server_id` directly on `hcloud_volume`, or a standalone `hcloud_volume_attachment` resource. The user's requirement is "attach automatically to the prod server," with no need to attach/detach independently of the volume's own lifecycle. `server_id` on the volume resource itself is the simpler mechanism for that case — one resource instead of two, and it attaches at creation rather than as a follow-up step. `hcloud_volume_attachment` earns its complexity only when a volume's attachment target needs to change independently of the volume (e.g. moving one volume between two servers), which is explicitly out of scope (Non-Goals).

**3. `modules/volume` takes a `server_id` input; it does not look up or own the server. `location` is omitted entirely, which couples the volume's existence to the server's.**
Mirrors how `modules/server` takes `ssh_key_id` as an input rather than creating or looking up the key itself (see the `prod-server-lifecycle-toggle` change) — a resource with an independent lifecycle is passed in by the caller, not reached for. `environments/prod/main.tf` passes `one(module.server[*].id)`, matching the existing `count`-based output pattern from that same change.

`location` is omitted from the module entirely (not even as a passthrough variable) since it's redundant once `server_id` is set and the provider derives it — declaring it independently would risk a mismatch the provider would then reject. But Hetzner requires *either* `location` or `server_id` — a volume can't exist with neither. Since this module never supplies `location`, `server_id` must always be non-null whenever the volume is created, which is stronger than "the volume happens to be attached to a server most of the time." `environments/prod/main.tf` enforces this directly at the call site: the `module "volume"` block's `count` is gated on `var.volume_enabled && var.server_enabled`, not `var.volume_enabled` alone, so the volume is never asked to exist without a server to derive its location from. This is a deliberate trade-off (see Non-Goals and the `Conditional Prod Volume Creation` requirement as revised): the volume's toggle is not fully independent of the server's — disabling the server also removes the volume. Adding an explicit `location` variable would restore full independence, but at the cost of a second location input that must be kept consistent with the server's own `hel1`, for a capability (a volume outliving the server it was created against) nothing in this change actually needs; see Migration Plan and Risks.

**4. Volume is created unformatted (`format`/`automount` left unset).**
`hcloud_volume`'s optional `format` would have the provider run `mkfs` once, at creation, with no idempotent way to change it later without recreating the volume. This repository's modules stop at infrastructure — nothing under `modules/` or `environments/` currently configures guest-OS state (no `hcloud_server` `user_data`, no provisioner). Setting a filesystem format here would be the first exception to that boundary for a single-purpose, easily-revisited choice. Leaving the volume unformatted keeps filesystem choice (ext4 vs. xfs, mount options) a guest-config concern, decided whenever that layer is actually built, rather than committing to it now as an infrastructure default. This can be revisited in a future change without affecting this one's specs or approach.

**5. `delete_protection` variable, no `rebuild_protection`.**
`modules/server` sets `rebuild_protection = var.delete_protection` because the provider requires the two to match on servers. `hcloud_volume` has no `rebuild_protection` attribute at all — "rebuild" isn't a concept that applies to a volume — so `modules/volume` exposes only `delete_protection`, matching the `iac-safety-hardening` requirement as modified by this change ("with `rebuild_protection` set to match on resources that support it").

## Risks / Trade-offs

- **An unformatted volume needs a manual (or future-automated) `mkfs`/mount step before it's usable from inside the guest.** *Mitigation*: none needed at this layer — this is the accepted boundary from Decision 4; tracked as a follow-on concern, not a defect in this change.
- **Disabling the prod server also destroys the volume**, since the module block's `count` is `var.volume_enabled && var.server_enabled` (Decision 3) — there is no configuration in which the volume outlives a disabled server. Unlike the server, Hetzner volumes have no automatic-backup equivalent, so this destroy has no data-durability net beyond `delete_protection` (and, per the existing `iac-safety-hardening` requirement, that only blocks console/API deletion, not a `terraform destroy` the CI destroy-policy gate lets through with human approval). *Mitigation*: this is an accepted, explicit consequence of Decision 3, not an oversight — anyone disabling the prod server must understand it also discards the volume's data, exactly as disabling the server already discards its own boot-disk backups (see `iac-safety-hardening`'s Data Durability requirement). The CI destroy-policy gate's human-approval step is the actual safeguard against doing this unintentionally, same as for the server.
- **`modules/volume`'s attachment is create-time only** (`server_id` set at creation) — since the volume and server are now created and destroyed together (Decision 3), there is no case where a running volume needs to be reattached to a *different* server instance; a fresh `server_enabled` cycle recreates both together, and the new volume attaches to the new server's id via the same `one(module.server[*].id)` reference. *Mitigation*: none needed — this is ordinary Terraform dependency resolution, not special-cased logic.

## Migration Plan

1. Add `modules/volume/{main,variables,outputs,versions}.tf`.
2. Add `volume_enabled`, `volume_name`, and `volume_size` variables to `environments/prod/variables.tf`; add the `module "volume"` block to `environments/prod/main.tf`, gated by `count = var.volume_enabled && var.server_enabled ? 1 : 0`, with `name = var.volume_name`, `size = var.volume_size`, `server_id = one(module.server[*].id)`.
3. Add `volume_name = "production_data"`, `volume_size = 10`, `volume_enabled = true` to `environments/prod/terraform.tfvars`.
4. Add volume outputs to `environments/prod/outputs.tf` (id, `linux_device`) via `one(module.volume[*].*)`.
5. Verify locally: `terraform fmt -check -recursive`, `terraform validate`, `terraform plan` (read-only token) — expect one `hcloud_volume` addition, attached to the existing server, no changes to the server or firewall.
6. Open a PR, confirm the plan comment matches, merge, approve the gated apply.

Rollback: set `volume_enabled = false` (or `server_enabled = false`, though that also removes the server) and reapply through the same pipeline — the volume is destroyed, its configuration stays declared for a future re-enable, per the `iac-data-volumes` capability's toggle requirement.

## Open Questions

**Resolved: does the `volume_enabled && server_enabled` coupling get an automated test?** No — this project's testing convention (AGENTS.md's Testing section) covers module-level tests under `modules/<name>/tests/` only; it has no location for environment-level `count`/toggle composition, and `modules/volume` alone can't express a coupling that lives in `environments/prod/main.tf`. The user chose to leave this coupling to the existing human-reviewed live-plan step rather than introduce a new test location/convention as part of this change. Tasks.md 3.5 makes that review step explicit (plan with each toggle combination locally, uncommitted) so the coupling is actually exercised before rollout, not merely asserted in prose.
