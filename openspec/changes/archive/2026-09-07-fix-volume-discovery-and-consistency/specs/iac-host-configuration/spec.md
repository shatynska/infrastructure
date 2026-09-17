## ADDED Requirements

### Requirement: A Role's Absent Required Input Is Reported by Name
Where a role takes an input that has no safe default, must therefore be supplied by its caller, and is consumed on every run of that role, the role SHALL detect that the input was not supplied and fail with a diagnostic naming the input and where it is expected to be set, before any task that acts on the host runs.

The obligation is stated over inputs consumed unconditionally because those are the ones whose absence is knowable before the role acts. An input consumed only under a condition — a step skipped when the host is already in the state it would establish — is not required on a run where that step does not execute, and a role SHALL NOT be made to demand it on such a run. Reporting that class well is a separate obligation this requirement does not make.

What counts as "not supplied" is the role's own contract, not a uniform emptiness test. A role MAY define an empty value as meaningful — a signal to discover the value, or a deliberately empty list — and where it does, an empty value is supplied and this requirement is satisfied by whatever that value then means. The obligation is that the unsupplied case is decided by the role and reported, not left to whichever task first evaluates the input.

This requirement reaches only inputs whose absence leaves the role with nothing to do but stop. Where a requirement recorded in this repository already specifies what a role SHALL do when a particular input is absent, that specification governs and this one does not apply — the existing "Host Authenticates to GHCR for Application Image Pulls" requirement, which obliges an absent registry credential to be tolerated and the login skipped rather than failed, is such a case and is unaffected by this requirement.

Such a role SHALL NOT satisfy this obligation by adopting a default value: for an input whose safe value is environment-specific — a source CIDR for a firewall rule, a block-device path, a key that grants network membership — any literal default silently substitutes a wrong answer for a stated one, which is the outcome the absence of a default exists to prevent.

Nor SHALL the obligation be treated as satisfied by an operator's ability to infer the cause from whatever error the first consuming task happens to raise. An undefined-variable error from a loop, or an index error from an empty search result, names the expression that failed rather than the decision the operator has to make, and is indistinguishable from a defect in the role itself.

#### Scenario: A required input is not supplied
- **WHEN** a role that consumes a caller-supplied input with no safe default on every run is run without that input having been supplied at all
- **THEN** the run SHALL fail with a message naming that input and how to supply it, rather than with an undefined-variable, index, or type error raised by a task that consumed it

#### Scenario: An input consumed only under a condition is not demanded when that condition does not hold
- **WHEN** a role whose only use of an input is a step that is skipped because the host is already in the state that step would establish is run without that input
- **THEN** the run SHALL converge, rather than failing for the absence of an input nothing on that run needed

#### Scenario: An empty value the role gives a meaning to is not a missing input
- **WHEN** such a role is run with the input set to an empty value that the role's own contract defines as meaningful
- **THEN** the run SHALL proceed with the meaning that role assigns the empty value, rather than reporting the input as missing

#### Scenario: The check precedes the tasks that consume the input
- **WHEN** such a role is run without its required input
- **THEN** the run SHALL fail before any task that acts on the host has changed it, so the failure is a refusal to proceed rather than a partial application

## MODIFIED Requirements

### Requirement: Platform Data Volume Is Mounted at a Fixed Host Path
Ansible SHALL mount the platform's dedicated data volume (the Terraform-provisioned `main-data` Hetzner Volume) at a fixed host path, and that mount SHALL persist across a host reboot without manual intervention. Ansible SHALL also ensure the subdirectories a `platform/` service depends on exist under that mount, with ownership and permissions matching what that service's container requires, before that service can rely on them.

This requirement covers only the mount and its filesystem layout — it does not extend Ansible's scope to templating or starting any `platform/` service, consistent with the existing "Configuration Scope Stops at the Container Runtime" requirement.

Where the device path is not supplied by the caller, it SHALL be discovered on the host itself rather than carried across from the provisioning layer's output. Discovery SHALL yield the same device on every run given the same set of attached volumes, and SHALL be treated as capable of yielding nothing: a host with no matching device attached is the ordinary state of a host provisioned with the volume disabled, or observed while a volume is still attaching, and is reported by this requirement's own scenario below rather than raised as an error about the discovery expression.

A host in that state cannot be brought to the state this requirement describes, and the run SHALL fail rather than converge — the volume is a stated dependency of the `platform/` services that bind-mount it, so a host without one is not a host this requirement can be satisfied on.

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
