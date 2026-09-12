## MODIFIED Requirements

### Requirement: Platform Data Volume Is Mounted at a Fixed Host Path
Ansible SHALL mount the platform's dedicated data volume (the Terraform-provisioned `main` Hetzner Volume) at a fixed host path, and that mount SHALL persist across a host reboot without manual intervention. Ansible SHALL also ensure the subdirectories a `platform/` service depends on exist under that mount, with ownership and permissions matching what that service's container requires, before that service can rely on them.

This requirement covers only the mount and its filesystem layout — it does not extend Ansible's scope to templating or starting any `platform/` service, consistent with the existing "Configuration Scope Stops at the Container Runtime" requirement.

Where the device path is not supplied by the caller, it SHALL be discovered on the host itself rather than carried across from the provisioning layer's output. Discovery SHALL yield the same device on every run given the same set of attached volumes, and SHALL be treated as capable of yielding nothing: a host with no matching device attached is the ordinary state of a host provisioned with the volume disabled, or observed while a volume is still attaching, and is reported by this requirement's own scenario below rather than raised as an error about the discovery expression.

**Discovery SHALL NOT be keyed on the volume's name.** The device is identified by the volume's id, so the mount is unaffected by the volume being renamed — which is the property that lets the provisioning layer rename a volume without a migration, and the reason the mount path and the volume's name are allowed to differ.

A host in that state cannot be brought to the state this requirement describes, and the run SHALL fail rather than converge — the volume is a stated dependency of the `platform/` services that bind-mount it, so a host without one is not a host this requirement can be satisfied on.

**Where the fixed path is changed, the path it supersedes SHALL NOT be left persisting across a reboot.** Establishing a mount at a new fixed path does not by itself retire the old one: a host that has converged at both is a host whose reboot mounts one device at two paths, with two sets of the subdirectories above underneath it and nothing to say which a service reads. That state is not detected by anything that observes a running host, because it arrives only at the next boot — so the obligation is on the converge that moves the path, and it SHALL hold on a host that has never carried the superseded path as much as on one that has.

**Which paths are superseded SHALL be declared to the converge rather than discovered by it.** A host cannot tell a path this repository has retired from one an operator mounted for a purpose of their own, so an obligation discharged by inspecting the host would reach beyond what this repository owns. The declaration SHALL admit being empty, which is the ordinary state of a host whose fixed path has never moved.

**A declaration naming the fixed path in force SHALL fail the run, and SHALL fail it before anything on the host is changed.** Such a declaration is self-defeating: retiring it would remove the very boot-time entry the same run establishes, leaving a host that mounts and serves correctly until it reboots and then comes up with no data volume at all — the failure this requirement's persistence obligation exists to prevent, reached from the opposite direction and equally invisible on a running host. It SHALL NOT be resolved by silently excluding the fixed path from what is retired: that converges a contradictory declaration cleanly and hides the inventory mistake that produced it. The comparison SHALL be made on paths normalised for a trailing separator, so that a declaration differing from the path in force only in that respect is refused rather than passing the check and reaching the retirement.

**Retiring the superseded path SHALL NOT require disturbing a service that currently holds it.** At the moment the path moves, the services that bind-mount subdirectories of the old path are running and holding it, and they are retired from it by their own redeployment rather than by the converge — whose scope stops at the container runtime. So this obligation is discharged by removing the superseded path from what the host mounts at boot, and a converge SHALL NOT satisfy it by unmounting a path a running service holds, nor fail because one does.

#### Scenario: Volume is mounted at a known path
- **WHEN** the host-baseline playbook runs with the data volume attached
- **THEN** that volume SHALL be mounted at a fixed, documented host path

#### Scenario: Mount survives a reboot
- **WHEN** the host reboots
- **THEN** the data volume SHALL be mounted at the same fixed path afterward, without a manual step

#### Scenario: Dependent subdirectories exist before a service needs them
- **WHEN** a `platform/` service is configured to bind-mount a subdirectory of the data volume
- **THEN** that subdirectory SHALL already exist, with the ownership and permissions that service's container requires, before that service is deployed

#### Scenario: No device is supplied and none can be discovered
- **WHEN** the host-baseline playbook runs against a host where no device path was supplied and on-host discovery matches nothing
- **THEN** the run SHALL fail with the diagnostic that names the missing device path and the attachment it depends on, and SHALL NOT fail instead on an error raised by indexing an empty discovery result

#### Scenario: More than one candidate device is attached
- **WHEN** on-host discovery matches more than one attached volume device
- **THEN** the device selected SHALL be the same on every run against that same set of attached devices, rather than depending on the order the discovery happened to return them in

#### Scenario: A superseded mount path is declared
- **WHEN** the host-baseline playbook runs against a host whose boot-time mount configuration names a path declared as superseded, alongside the fixed path in force
- **THEN** the device SHALL be mounted at the fixed path in force, **AND** the superseded path SHALL NOT remain in what the host mounts at boot, so that a reboot mounts the device at exactly one path

#### Scenario: No superseded mount path is declared
- **WHEN** the host-baseline playbook runs against a host for which no superseded path is declared — a host newly built, or one whose superseded paths have already been retired
- **THEN** the run SHALL change nothing about the host's boot-time mount configuration beyond the fixed path in force, and SHALL NOT fail for the absence

#### Scenario: A path is declared superseded and is also the path in force
- **WHEN** the host-baseline playbook runs with the fixed path in force also named among the superseded paths, whether spelled identically or differing only in a trailing separator
- **THEN** the run SHALL fail with a diagnostic naming that path and both inputs it was read from — the fixed path's and the superseded declaration's — **AND** SHALL fail before any task that changes the host has run

#### Scenario: A running service still holds the superseded path
- **WHEN** the superseded path is retired on a host where a running service holds a bind mount into it
- **THEN** the run SHALL succeed, **AND** SHALL NOT unmount that path or otherwise interrupt that service's access to the data under it
