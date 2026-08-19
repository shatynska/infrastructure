## Why

The prod server currently has no persistent block storage beyond its own boot disk — any data that needs to survive independently of the server's lifecycle (e.g. being decommissioned and recreated via the `server_enabled` toggle) has nowhere to live. The operator wants a dedicated Hetzner Cloud volume, `main-data`, attached to the prod server, to hold that data.

## What Changes

- Add a new `modules/volume` module (mirroring `modules/server`'s single-responsibility, reusable-module pattern) that creates one `hcloud_volume`, given a size, a server to attach to, and a `delete_protection` toggle.
- Add a `volume_enabled` boolean variable to `environments/prod` (default `true`), mirroring the existing `server_enabled` pattern — so the volume can be detached/removed from management without losing its declared configuration (`volume_name`, `volume_size`). Because the volume has no location of its own (see below), the module call's `count` is gated on `volume_enabled AND server_enabled` together, not `volume_enabled` alone — disabling the server also removes the volume. See design.md Decision 3 for why.
- Wire the volume's `server_id` to the prod server's id so it attaches automatically at creation; the volume takes its location from the attached server (Hetzner requires both to share a location, and setting `server_id` at creation lets the provider derive it rather than declaring it redundantly).
- Add `main-data`'s non-secret configuration (`volume_name = "main-data"`, `volume_size = 10`) to `environments/prod/terraform.tfvars`, per the project's committed-tfvars convention.
- Leave the volume unformatted (no `format`/`automount`): filesystem provisioning is left to whatever configures the server's guest OS, not to Terraform — consistent with this module's existing scope (infrastructure, not guest configuration).
- Extend the existing `Provider-Level Deletion Protection` and `Consistent Resource Labeling` requirements (already anticipating "any future volumes") with volume-specific scenarios, since a concrete volume now exists to verify them against.

## Capabilities

### New Capabilities
- `iac-data-volumes`: Conditional creation of a Hetzner volume attached to the prod server, toggleable in addition to the server's own toggle, without losing its declared configuration.

### Modified Capabilities
- `iac-safety-hardening`: The `Provider-Level Deletion Protection` and `Consistent Resource Labeling` requirements already anticipate volumes generically ("Servers and any future volumes...", "Every `hcloud_*` resource..."); add scenarios covering the first concrete volume so those requirements are verified, not just stated.
- `iac-server-lifecycle`: The `Conditional Prod Server Creation` requirement's "toggle disabled creates nothing" scenario currently reads as exhaustive over server + firewall only. Since the new volume has no location of its own and is coupled to the server's toggle (see design.md Decision 3), disabling the server now also removes the volume; add a scenario noting that coupling so a reader of this capability alone isn't misled.

## Impact

- Affected code: new `modules/volume/{main,variables,outputs,versions}.tf`; `environments/prod/main.tf` (new `module "volume"` block), `environments/prod/variables.tf` (new `volume_enabled`, `volume_name`, `volume_size` variables), `environments/prod/terraform.tfvars` (new volume values), `environments/prod/outputs.tf` (new volume outputs).
- Affected infrastructure: one new `hcloud_volume` (10 GB, `hel1`, attached to `main-server`) created in prod via the gated pipeline.
- No changes to the CI/CD pipeline, firewall, or server modules themselves.
