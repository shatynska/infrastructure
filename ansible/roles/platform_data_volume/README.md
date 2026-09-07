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
`openspec/specs/iac-host-configuration/spec.md`, and
`add-platform-monitoring`'s `design.md`, for the full rationale, including why
the volume's device path is discovered on-host rather than hand-copied from
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
an attached Volume). Pass `platform_data_volume_device` explicitly only to
override this (as the `default` Molecule scenario does, pointing it at a
fixture loop device standing in for the real attached volume).

Two properties of that discovery are specified requirements, not incidental:

- **It is deterministic.** `find` returns directory-read order and guarantees
  none, so the match is sorted and the lexicographically first device chosen.
  With one volume attached — production today — sorted and unsorted agree, so
  the difference only appears once a second volume is attached, which is
  exactly when a silent, run-to-run-varying pick would be worst. Whether an
  ambiguous match should instead be a hard failure is a policy question
  recorded in `docs/change-queue.md`, not settled here.
- **Finding nothing is reported, not raised.** A host with the volume disabled
  in `terraform.tfvars`, or one where the volume is still attaching, matches
  nothing — the ordinary state of such a host, not an exotic one. The run
  fails with a message naming the missing device and the `volume_enabled`
  toggle, rather than with a Jinja error about an empty list.

Four Molecule scenarios cover this: `default` (device supplied explicitly),
`no-device-discoverable`, and `multiple-devices-discoverable` plus
`multiple-devices-reverse-order` — one per directory-read arrangement, since a
single arrangement cannot tell a sorted selection from an order-dependent one.

## Variables

| Variable | Default | Description |
|---|---|---|
| `platform_data_volume_device` | `""` (discovered) | Block device path. Empty means "discover it" (see above); set explicitly to override. |
| `platform_data_volume_mount_path` | `/mnt/main-data` | Fixed host path the volume is mounted at. |
| `platform_data_volume_fs_type` | `ext4` | Filesystem created if the device is unformatted, and expected on an already-formatted one. |
| `platform_data_volume_subdirs` | `[]` | List of `{path, owner, group, mode}` — one entry per `platform/` service that bind-mounts a subdirectory of the volume. Empty means no subdirectory is created. |
