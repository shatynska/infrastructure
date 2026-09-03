# platform_data_volume

Mounts the platform's dedicated data volume — the Terraform-provisioned
`main-data` Hetzner Volume (`terraform/environments/prod/terraform.tfvars`,
`terraform/modules/volume`) — at a fixed host path, formatting it if it has
no filesystem yet, and persists the mount in `/etc/fstab` so it survives a
reboot without a manual step. Also creates whatever subdirectories a
`platform/` service needs to bind-mount, each with its own declared
ownership and permissions, before that service can rely on them existing.

Implements `iac-host-configuration`'s ADDED "Platform Data Volume Is Mounted
at a Fixed Host Path" requirement — see
`openspec/changes/add-platform-monitoring/specs/iac-host-configuration/spec.md`
and that change's `design.md` for the full rationale, including why the
volume's device path is discovered on-host rather than hand-copied from
Terraform's output.

## Scope

This role stops at the mount and its filesystem layout. It never templates
or starts a `platform/` Compose service and never invokes a Compose
lifecycle command — that stays outside Ansible's responsibility entirely,
per the existing "Configuration Scope Stops at the Container Runtime"
requirement. What a `platform/` service does with the subdirectories this
role prepares (bind-mounting them into a container) is `platform/`'s own
concern, deployed by the separate `platform-deploy` GitHub Actions pipeline.

## Device discovery

`platform_data_volume_device` defaults to an empty string, which this role
reads as "not explicitly supplied" — it then globs
`/dev/disk/by-id/scsi-0HC_Volume_*` (Hetzner's stable, documented naming for
an attached Volume) and uses whatever single device that resolves to. Pass
`platform_data_volume_device` explicitly only to override this (as this
role's own Molecule scenario does, pointing it at a fixture loop device
standing in for the real attached volume).

## Variables

| Variable | Default | Description |
|---|---|---|
| `platform_data_volume_device` | `""` (discovered) | Block device path. Empty means "discover it" (see above); set explicitly to override. |
| `platform_data_volume_mount_path` | `/mnt/main-data` | Fixed host path the volume is mounted at. |
| `platform_data_volume_fs_type` | `ext4` | Filesystem created if the device is unformatted, and expected on an already-formatted one. |
| `platform_data_volume_subdirs` | `[]` | List of `{path, owner, group, mode}` — one entry per `platform/` service that bind-mounts a subdirectory of the volume. Empty means no subdirectory is created. |
