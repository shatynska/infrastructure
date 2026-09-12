## REMOVED Requirements

### Requirement: Dynamic Inventory via hcloud Plugin

**Reason**: Rewritten, because this change separates two things the requirement wrote as one word. An inventory source belongs to a **stack** — one Hetzner project, one credential — while the group a play targets is the **environment**, and the `group_vars` file belongs to the group. The requirement said *environment* for all three, which was correct while a repository had one tenant and stops being correct here. Four of its seven scenario titles say *environment* where they mean *stack*, and a scenario cannot be renamed inside a `MODIFIED` block — see design.md decision 3.

**Migration**: Replaced in full by *Dynamic Inventory via the hcloud Plugin, One Source per Stack* below. Every obligation is carried across with the two senses separated; two obligations are added — the tenant grouping, and the rule that a source's name and its group's name are not assumed equal.

## ADDED Requirements

### Requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack
Ansible SHALL discover target hosts via the `hcloud` dynamic inventory plugin rather than a static or hand-maintained inventory file. Hosts SHALL be grouped by the Hetzner labels already applied to every resource, one group per axis: by the `environment` label, and by the `tenant` label. A group per axis is what lets a baseline be written for an axis without special-casing the stacks that carry it.

Each **stack** SHALL declare its own inventory source, and each source SHALL authenticate with that stack's own read-only Hetzner credential, supplied from an environment variable whose name is distinct from every other stack's. A Hetzner credential is scoped to one project and each stack has a project of its own, so a source reaches exactly one stack; a single source that every stack shares would reach whichever project the credential in scope happened to belong to, and nothing in a run would say which.

**A source is named for its stack and a group is named for its axis, and neither SHALL be derived from the other.** An inventory source's filename follows the stack it reaches, because what it reaches is a Hetzner project. The group a play targets, the vault-id label its secrets are labelled under and the `group_vars` file that supplies its variables follow the *environment*, because that is what those things describe. The two coincide only where a repository has one tenant, and the value is read from the stack's own pipeline declaration (see *Each Stack Declares Its Own Pipeline Configuration*, `iac-cicd-pipeline`) rather than parsed out of either name.

Bringing a further stack into inventory SHALL therefore be adding a source and a credential name, and SHALL NOT require editing an existing stack's source. It does not necessarily add a `group_vars` file: a stack whose environment another stack already declares reads that environment's existing variables, which is what an environment-wide baseline means.

An inventory source whose credential is absent or is rejected SHALL fail the run. It SHALL NOT resolve to an empty group, which is indistinguishable from a stack whose server does not exist.

A stack that carries a pipeline declaration SHALL carry an inventory source of its own, and the `group_vars` file its declared group names SHALL exist. A stack that can be provisioned but not converged is one whose host configuration nothing applies, and nothing in a provisioning run says so.

The environment-variable name a source reads its credential from SHALL be the same name that stack declares as its read-only secret. A workflow converging a stack holds that credential under the declared name and must supply it under the name the source reads; where the two differ, the workflow would have to carry the mapping, which is the stack-naming in workflow text the pipeline's own requirements forbid. Requiring the two to be *distinct per stack* does not make them *equal to each other*, and the difference is what this clause states: without it, "adding a stack needs no workflow edit" rests on a coincidence rather than on an obligation.

#### Scenario: Inventory resolved live from Hetzner
- **WHEN** a playbook run targets an environment's group
- **THEN** inventory SHALL be resolved live from Hetzner Cloud's API via the label-keyed groups, not from a committed hosts file

#### Scenario: Hosts are grouped by every axis their labels carry
- **WHEN** a source resolves a host carrying both a `tenant` and an `environment` label
- **THEN** that host SHALL appear in a group named for each label's value, so that a baseline may be written for either axis

#### Scenario: Disabled server yields no stale inventory entry
- **WHEN** a stack's server lifecycle toggle is set to disabled and the server no longer exists
- **THEN** the `hcloud` dynamic inventory SHALL return no host for that stack, rather than a stale or unreachable static entry

#### Scenario: A stack's source reaches only its own project
- **WHEN** a run resolves one stack's inventory source
- **THEN** it SHALL authenticate with that stack's own credential, and SHALL NOT depend on which stack's credential is otherwise in scope in the shell that started the run

#### Scenario: A source's name is not read as its group's name
- **WHEN** a stack whose name differs from the environment its host belongs to is converged
- **THEN** the inventory source named with `-i` SHALL be the one named for the stack, and the group targeted, the vault-id label and the `group_vars` file SHALL be the ones named for the declared environment

#### Scenario: A further stack is brought into inventory
- **WHEN** a stack is added to this repository and needs to be reachable by Ansible
- **THEN** it SHALL be brought into inventory by adding a source of its own and a credential name of its own, without editing any existing stack's inventory source

#### Scenario: An inventory source cannot authenticate
- **WHEN** a run names an inventory source whose credential is absent, empty or rejected by the API
- **THEN** the run SHALL fail reporting that the source could not be parsed, rather than continuing with an inventory in which that stack holds no host

#### Scenario: A stack that can be provisioned but not converged is reported
- **WHEN** a stack carries a pipeline declaration but no inventory source, or its declared environment has no variables file
- **THEN** that SHALL be reported as a failure naming the stack, rather than leaving a stack whose host configuration nothing applies

#### Scenario: A source's credential variable is the name the stack declares
- **WHEN** a stack's inventory source and its pipeline declaration are read together
- **THEN** the environment variable the source takes its credential from SHALL carry the same name the declaration states as that stack's read-only secret

### Requirement: The Host's Own Name Is Set by the Converge
A converge SHALL set the host's own name rather than leaving it as the host was first given one. A host's name is set once, at creation, from the name the provisioning layer gave the server, and nothing re-sets it afterwards — so renaming a server in the provisioning layer produces a host answering to a name no committed file states, and nothing fails.

The name SHALL be derived from the host's inventory identity together with a single variable naming the operating company, and that variable SHALL be held in one place, applying to every host, so that a clone of this repository operated by a different company changes it once. It is a required input in the sense of *A Role's Absent Required Input Is Reported by Name*: it has no safe default, and a converge that cannot resolve it SHALL fail by name rather than converge a host under a name assembled from a blank.

**The name a host reports to the private network SHALL be set explicitly to the name the provisioning layer gives its server, and SHALL NOT be left to be inherited from the host's own name.** The two are not the same name once the host's name carries the company: the company's namespace is the workstation, which serves more than one company, while the private network belongs to one company and holds every stack it owns. Every unattended consumer — the converge that reaches the host, the deploy that reaches the host — resolves the server's name, so leaving that name to be derived from a value this requirement has just changed would make an identifier automation depends on a by-product of one that it does not.

**Setting it explicitly SHALL precede changing the host's own name within a run**, because until it is set the reported name follows the host's own. A run that renames the host first leaves a window in which the private network is told a name nothing intends, and the window's length is however long the rest of that run takes or fails in.

**The host SHALL resolve its own name locally**, and the converge SHALL make it do so as part of setting that name rather than leaving the two to be set by different mechanisms. Setting a host's name does not by itself make it resolvable — the loopback entry that answers for it is a separate file — and on this host's distribution the symptom is not a failure but a warning emitted by every privileged command and every login thereafter. A name a host cannot resolve is a name only half set, and the half that is missing is the one an operator sees.

**A name that reaches a namespace shared across stacks SHALL be unique within it.** The private network and any external observer a host reports to hold every stack a company owns, while a server's name is unique only within its own project. A name unique per project but not per company collides in those namespaces, and at least one of those collisions fails in the direction of a green report: two hosts sharing one observer's check are indistinguishable from one host reporting, so one host's silence is masked by the other's success.

**A registry outside this repository's reach SHALL NOT be assumed to follow.** A private network may hold a registered name of its own, assigned when the host first joined and independent of what the host reports; the converge cannot set it. Where a name this repository changes is already registered under its old value in such a registry, the rename SHALL be performed there as a named step of the change that renames it, and SHALL be observed to have taken effect rather than assumed — the observation being that the new name resolves from a peer that is not the host itself. The explicit setting above is what keeps that registry from being driven somewhere else in the meantime; it is not a substitute for the rename.

#### Scenario: A host renamed in the provisioning layer answers to the new name after a converge
- **WHEN** a server is renamed in the provisioning layer and the host is then converged
- **THEN** the host's own name SHALL be the one this repository states, rather than the name it was created with

#### Scenario: The host's name carries the company and the reported name does not
- **WHEN** a host is converged
- **THEN** its own name SHALL carry the operating company and its inventory identity, and the name it reports to the private network SHALL be its inventory identity alone

#### Scenario: The reported name is pinned before the host's own name changes
- **WHEN** a converge both pins the reported name and changes the host's own name
- **THEN** the pin SHALL be applied first, so that no part of the run leaves the reported name deriving from a host name this run has already changed

#### Scenario: The host resolves the name it was just given
- **WHEN** a converge sets the host's own name
- **THEN** the host SHALL resolve that name locally in the same run, so that a privileged command run afterwards emits no unresolved-host warning

#### Scenario: A host already on the private network has its reported name corrected
- **WHEN** a host that is already a member of the private network is converged after its server was renamed
- **THEN** the name it reports SHALL be set to its current inventory identity, rather than left deriving from whatever the host is called

#### Scenario: An absent company variable refuses
- **WHEN** a converge runs against a host for which the company variable is not supplied
- **THEN** the run SHALL fail with a diagnostic naming that variable and where it is expected to be set, before any task acts on the host

## MODIFIED Requirements

### Requirement: Host Configuration Names the Environment It Targets
The host-baseline play SHALL take the environment it configures as an input supplied per run, rather than naming one environment in the play itself.

That input SHALL have no default. A default would make the environment a property of what the operator forgot to type rather than of what they asked for, and the environment that a forgotten input would fall back to is the one whose misconfiguration is least recoverable.

A run that supplies no environment SHALL fail before any task acts on a host, rather than converging some environment chosen for it.

**An unattended run SHALL take that value from the stack's own committed declaration, and SHALL NOT compute it from the stack's name.** The two are equal only where a repository has one tenant; computing one from the other is a rule that holds on the names a repository happens to have and fails as a group that does not exist, several steps after the run began. The same value names the vault-id label the run's secrets are labelled under and the `group_vars` file it reads, so all three move together or the run is reading one environment's variables while targeting another's hosts.

#### Scenario: A run names the environment it configures
- **WHEN** the host-baseline play is run with an environment supplied
- **THEN** it SHALL configure the hosts of that environment's group, and no host outside it

#### Scenario: A run supplying no environment refuses
- **WHEN** the host-baseline play is run without an environment supplied
- **THEN** the run SHALL fail before any task acts on a host, rather than defaulting to an environment

### Requirement: Platform Data Volume Is Mounted at a Fixed Host Path
Ansible SHALL mount the platform's dedicated data volume (the Terraform-provisioned `main` Hetzner Volume) at a fixed host path, and that mount SHALL persist across a host reboot without manual intervention. Ansible SHALL also ensure the subdirectories a `platform/` service depends on exist under that mount, with ownership and permissions matching what that service's container requires, before that service can rely on them.

This requirement covers only the mount and its filesystem layout — it does not extend Ansible's scope to templating or starting any `platform/` service, consistent with the existing "Configuration Scope Stops at the Container Runtime" requirement.

Where the device path is not supplied by the caller, it SHALL be discovered on the host itself rather than carried across from the provisioning layer's output. Discovery SHALL yield the same device on every run given the same set of attached volumes, and SHALL be treated as capable of yielding nothing: a host with no matching device attached is the ordinary state of a host provisioned with the volume disabled, or observed while a volume is still attaching, and is reported by this requirement's own scenario below rather than raised as an error about the discovery expression.

**Discovery SHALL NOT be keyed on the volume's name.** The device is identified by the volume's id, so the mount is unaffected by the volume being renamed — which is the property that lets the provisioning layer rename a volume without a migration, and the reason the mount path and the volume's name are allowed to differ.

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
