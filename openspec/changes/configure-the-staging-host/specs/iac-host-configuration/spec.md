## MODIFIED Requirements

### Requirement: Dynamic Inventory via hcloud Plugin
Ansible SHALL discover target hosts via the `hcloud` dynamic inventory plugin rather than a static or hand-maintained inventory file. Hosts SHALL be grouped by the `environment` label already applied to Hetzner resources.

Each environment SHALL declare its own inventory source, and each source SHALL authenticate with that environment's own read-only Hetzner credential, supplied from an environment variable whose name is distinct from every other environment's. A Hetzner credential is scoped to one project and each environment has a project of its own, so a source reaches exactly one environment; a single source that every environment shares would reach whichever project the credential in scope happened to belong to, and nothing in a run would say which.

Bringing a further environment into inventory SHALL therefore be adding a source and a credential name, and SHALL NOT require editing an existing environment's source.

An inventory source whose credential is absent or is rejected SHALL fail the run. It SHALL NOT resolve to an empty environment, which is indistinguishable from an environment whose server does not exist.

#### Scenario: Inventory resolved live from Hetzner
- **WHEN** a playbook run targets an environment's group
- **THEN** inventory SHALL be resolved live from Hetzner Cloud's API via the `environment` label filter, not from a committed hosts file

#### Scenario: Disabled server yields no stale inventory entry
- **WHEN** an environment's server lifecycle toggle is set to disabled and the server no longer exists
- **THEN** the `hcloud` dynamic inventory SHALL return no host for that environment, rather than a stale or unreachable static entry

#### Scenario: An environment's source reaches only its own project
- **WHEN** a run resolves one environment's inventory source
- **THEN** it SHALL authenticate with that environment's own credential, and SHALL NOT depend on which environment's credential is otherwise in scope in the shell that started the run

#### Scenario: A further environment is brought into inventory
- **WHEN** an environment is added to this repository and needs to be reachable by Ansible
- **THEN** it SHALL be brought into inventory by adding a source of its own and a credential name of its own, without editing any existing environment's inventory source

#### Scenario: An inventory source cannot authenticate
- **WHEN** a run names an inventory source whose credential is absent, empty or rejected by the API
- **THEN** the run SHALL fail reporting that the source could not be parsed, rather than continuing with an inventory in which that environment holds no host

## ADDED Requirements

### Requirement: Host Configuration Names the Environment It Targets
The host-baseline play SHALL take the environment it configures as an input supplied per run, rather than naming one environment in the play itself.

That input SHALL have no default. A default would make the environment a property of what the operator forgot to type rather than of what they asked for, and the environment that a forgotten input would fall back to is the one whose misconfiguration is least recoverable.

A run that supplies no environment SHALL fail before any task acts on a host, rather than converging some environment chosen for it.

#### Scenario: A run names the environment it configures
- **WHEN** the host-baseline play is run with an environment supplied
- **THEN** it SHALL configure the hosts of that environment's group, and no host outside it

#### Scenario: A run supplying no environment refuses
- **WHEN** the host-baseline play is run without an environment supplied
- **THEN** the run SHALL fail before any task acts on a host, rather than defaulting to an environment

### Requirement: A Run Whose Target Group Resolves to No Host Refuses
A host-configuration run whose target group resolves to no host SHALL fail with a diagnostic naming the environment that resolved to nothing, before any task acts on a host.

Ansible's own behaviour is the reason this is stated. A play whose `hosts:` matches no host is skipped and the run exits successfully, so a converge that reached nothing reports exactly what a converge with nothing to do reports. Every way of reaching that state is a mistake: an environment misspelled, an inventory source whose project holds no such environment, or a server that does not exist. None of them is a run that should be reported as having succeeded.

This obligation is distinct from *A Role's Absent Required Input Is Reported by Name*, which reaches a role acting on a host that resolved. This one reaches the case where no host resolved at all, so no role runs and no role-scope check can fire.

#### Scenario: A targeted environment resolves to no host
- **WHEN** a host-configuration run targets an environment whose group is empty
- **THEN** the run SHALL fail with a diagnostic naming that environment, rather than reporting success having changed nothing

#### Scenario: A run that resolves hosts is unaffected
- **WHEN** a host-configuration run targets an environment whose group holds at least one host
- **THEN** the run SHALL proceed to configure those hosts, and the check SHALL add no further required input to it
