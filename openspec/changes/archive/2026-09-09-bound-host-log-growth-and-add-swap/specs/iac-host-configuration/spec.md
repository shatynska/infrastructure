## ADDED Requirements

### Requirement: Container Logs Are Bounded by the Host's Daemon Configuration
Ansible SHALL configure the host's container runtime daemon so that a container the daemon subsequently creates writes a bounded on-disk log unless that container's own definition specifies its logging otherwise: a maximum size per log file and a maximum number of retained files, both recorded in the daemon's own configuration file on the host.

The exception is what a daemon-level default is: a value a container's own definition may override. The obligation this requirement makes is that the default is bounded, so that a container which says nothing about its logging is bounded rather than unlimited — not that no container can ever choose otherwise.

**The bound SHALL be a property of the daemon, not of any application's service-definition file.** An application's Compose file can only bound the services its author remembered to annotate, and only for applications whose Compose files this repository is able to edit — which excludes every application deployed here from its own repository. A daemon-level default binds both, and binds a service added later without anyone editing it. Placing the bound at the daemon SHALL NOT be read as an exception to "Configuration Scope Stops at the Container Runtime": the daemon is the runtime, and configuring it is inside that boundary, whereas writing a `logging:` stanza into an application's Compose file would not be.

**The bound SHALL be a ceiling rather than a retention target.** Its purpose is that no container can consume the host's root filesystem, not that logs be small. Where the host has no log aggregation, the runtime's own files are the only history an incident has to read, and a limit chosen to minimise disk rather than to bound it destroys that history for a resource the host has in surplus. The chosen values SHALL be justified against the host's actual free space, and revisited if log aggregation is introduced.

**The guarantee SHALL be stated as reaching containers created after the configuration is applied.** The runtime resolves a container's log options when the container is created, so containers already running when the daemon is reconfigured retain the configuration they were created with, and a restart of the daemon does not change them. A converge SHALL NOT be reported, in this repository's documentation or its verification, as having bounded a container that predates it.

#### Scenario: A container created after configuration has a bounded log
- **WHEN** the container runtime daemon creates a container, whose definition specifies no logging options, on a host Ansible has configured
- **THEN** that container's effective log configuration SHALL carry both a maximum log file size and a maximum retained file count, rather than the runtime's unbounded default

#### Scenario: An application that declares no logging configuration is still bounded
- **WHEN** an application's service-definition file declares no logging options for a service
- **THEN** that service's containers SHALL still be bounded by the daemon's configuration, including for an application whose service-definition file is maintained outside this repository

#### Scenario: Containers predating the configuration are not claimed as bounded
- **WHEN** the daemon is reconfigured on a host with containers already running
- **THEN** those containers SHALL retain the log configuration they were created with, and the run SHALL NOT be recorded as having bounded them

#### Scenario: The daemon's configuration is what carries the bound
- **WHEN** the host's container runtime daemon configuration is read after a converge
- **THEN** it SHALL name the logging driver and both bounds, so that the guarantee is verifiable from the host's own configuration rather than inferred from each container

### Requirement: The Host Carries Swap That Survives a Reboot
Ansible SHALL provide the configured host with swap space, and that swap SHALL be active after a converge and again after a reboot without a manual step.

Swap SHALL be backed by a file on the host's root filesystem rather than by a partition or an attached volume: a partition cannot be added to an already provisioned host without repartitioning it, and an attached network volume makes the kernel's last-resort memory tier depend on a network device — the dependency least able to tolerate the pressure that makes swap necessary. The host's dedicated data volume in particular SHALL NOT be used.

**The swap file SHALL be readable and writable only by `root`.** Its contents are whatever the kernel evicted from process memory, so it is a file that can hold any secret any process on the host held. This obligation is stated here rather than inherited: the existing "Secrets Never Committed in Plaintext and Never Left World-Readable on Host" requirement reaches a file that a task renders a protected value into, which a swap file is not. The reason is the same one, and this host has an unprivileged interactive account for which the difference is not academic.

**The kernel's swap tendency SHALL be set so that swap is an overflow reserve rather than a routine memory tier, and that setting SHALL persist across a reboot.** Swap exists here to convert an out-of-memory kill — which selects its victim by resident size rather than by which process leaked, so on this host it would most likely stop a database or the monitoring stack rather than the culprit — into a slowdown that the host's memory-pressure alerting has time to report. A default tendency that pages out a working set the host has room for serves neither purpose.

**Configuring swap SHALL be separable from activating it.** Activation writes to the kernel, and the swap-tendency setting is not namespaced, so on any host sharing a kernel with others — a container, and therefore this project's role-verification harness — activation reaches state the run does not own. Splitting the two means the configuration can be verified where activation cannot be performed safely, and obliges this repository to state which of the two any given verification established.

**Persistence SHALL be established by the records the host reads at boot** — the boot-time mount table and the kernel-parameter directory — and this repository SHALL state whether a given verification observed those records or observed an actual boot. The two are not the same claim, and the weaker one is what a configuration run can make.

**A converge against a host whose swap is already active SHALL NOT reformat or recreate the backing file.** Writing a fresh swap signature over a file the kernel is currently swapping to corrupts the pages it holds, so the run SHALL establish the file's current state before acting on it rather than acting unconditionally and relying on the file's absence.

#### Scenario: Swap is active after a converge
- **WHEN** the host-baseline playbook completes against a host with no swap
- **THEN** the host SHALL report active swap of the configured size, backed by a file on the root filesystem

#### Scenario: Swap survives a reboot
- **WHEN** the host reboots
- **THEN** swap SHALL be active afterwards at the same size, without a manual step

#### Scenario: The boot-time records are what carry persistence
- **WHEN** the host's boot-time mount table and kernel-parameter directory are read after a converge
- **THEN** they SHALL name the swap file and the swap-tendency value, and re-reading those records by the same mechanism the host uses at boot SHALL yield active swap and the configured tendency

#### Scenario: The swap file is not readable by an unprivileged account
- **WHEN** the swap file exists on the host
- **THEN** its ownership and permissions SHALL admit only `root`, so that an unprivileged account with a login on this host cannot read evicted memory

#### Scenario: Swap tendency is set and persists
- **WHEN** the host is inspected after a converge, and again after a reboot
- **THEN** the kernel's swap tendency SHALL read the configured overflow-reserve value rather than the distribution default, and the setting SHALL be recorded in a file the kernel reads at boot

#### Scenario: Configuration is established without activation
- **WHEN** the role is run with activation disabled
- **THEN** the swap file, its permissions, its boot-time mount record and the swap-tendency file SHALL all be established, and no kernel state outside the run's ownership SHALL be written

#### Scenario: A re-converge leaves active swap intact
- **WHEN** the host-baseline playbook runs again against a host whose swap is already active
- **THEN** the run SHALL make no change to the backing file's contents, and SHALL NOT write a new swap signature over a file the kernel is swapping to

## MODIFIED Requirements

### Requirement: Configuration Scope Stops at the Container Runtime
Ansible's responsibility SHALL end once the container runtime engine is installed and ready to run containers. Ansible content SHALL NOT template an application service-definition file (for example, a Compose file) and SHALL NOT invoke a runtime's application-lifecycle commands (starting, stopping, or restarting an application stack).

Configuring the runtime engine itself is inside that boundary. A runtime restarted to adopt its new configuration stops the containers it was holding and returns them by their own restart policies, and that return SHALL NOT be read as Ansible starting an application: no task names an application, its service-definition file or its stack, and what comes back is what the runtime was already holding. What this requirement forbids is Ansible directing an application's lifecycle, not the runtime resuming what it was already running.

This is not a licence introduced by the ability to reconfigure the daemon. Installing or upgrading the runtime already restarts it, so this reading describes what a converge has always done; stating it makes the boundary checkable rather than widening it.

The distinction is observable, and the observation is the stricter of the two: after such a run, the set of running applications SHALL be exactly the set that was running before it.

#### Scenario: A completed run starts no application
- **WHEN** a playbook run completes successfully
- **THEN** no application container SHALL have been started by a task of that run, and no application service-definition file SHALL have been generated by it

#### Scenario: Restarting the runtime to adopt configuration adds no application
- **WHEN** a run reconfigures the container runtime engine and the runtime restarts to adopt that configuration
- **THEN** the applications running afterwards SHALL be exactly those running before, returned by their own restart policies, and the run SHALL NOT have brought up any application the runtime was not already holding
