## ADDED Requirements

### Requirement: The Address a Converge Connects To Is Selected Per Run
The address a host-configuration run connects to SHALL be selected per run, and SHALL default to the address an operator's first converge of a host can reach.

Two callers need different addresses and neither is wrong. An operator converging a host for the first time must reach it on its public address, because joining the private tailnet is something that run has not done yet. An unattended run reaching the host from outside the operator's own network must reach it over the tailnet, because the cloud firewall admits SSH from the operator's range and from nothing else — and widening it to the address range of a continuous-integration provider would replace a boundary with a formality.

The default SHALL be the public address, so that a run supplying nothing behaves as it does today and the bootstrap path stays reachable. Selecting the tailnet address SHALL be a deliberate act of the run that wants it.

The selection SHALL decide only which address is dialled. It SHALL NOT relax any other guard: the environment the run names, the refusal when that environment's group holds no host, and each role's own required-input assertions apply identically under either address.

A selection the inventory cannot honour SHALL fail the run rather than falling back to another address. A run that silently reached a host by a route its operator did not choose is worse than one that did not connect.

#### Scenario: A run supplying no selection reaches the public address
- **WHEN** a host-configuration run is started without selecting a connection address
- **THEN** it SHALL connect to the host's public address, as a first converge of a host not yet on the tailnet requires

#### Scenario: A run selecting the tailnet address reaches the host over the tailnet
- **WHEN** a host-configuration run selects the tailnet address, from a machine that is a member of that tailnet
- **THEN** it SHALL connect to the host over the tailnet, without any allowance for that machine in the cloud firewall

#### Scenario: An unrecognised selection fails the run
- **WHEN** a host-configuration run selects a connection address the inventory cannot resolve or does not recognise
- **THEN** the run SHALL fail, rather than falling back to another address

#### Scenario: The selection adds no reachable host and removes no guard
- **WHEN** a run selects either address
- **THEN** the set of hosts it configures SHALL be the environment's group exactly as before, and every refusal that applied to the run SHALL still apply

## MODIFIED Requirements

### Requirement: Dynamic Inventory via hcloud Plugin
Ansible SHALL discover target hosts via the `hcloud` dynamic inventory plugin rather than a static or hand-maintained inventory file. Hosts SHALL be grouped by the `environment` label already applied to Hetzner resources.

Each environment SHALL declare its own inventory source, and each source SHALL authenticate with that environment's own read-only Hetzner credential, supplied from an environment variable whose name is distinct from every other environment's. A Hetzner credential is scoped to one project and each environment has a project of its own, so a source reaches exactly one environment; a single source that every environment shares would reach whichever project the credential in scope happened to belong to, and nothing in a run would say which.

Bringing a further environment into inventory SHALL therefore be adding a source and a credential name, and SHALL NOT require editing an existing environment's source.

An inventory source whose credential is absent or is rejected SHALL fail the run. It SHALL NOT resolve to an empty environment, which is indistinguishable from an environment whose server does not exist.

An environment that carries a pipeline declaration SHALL carry an inventory source and a variables file of its own. An environment that can be provisioned but not converged is one whose host configuration nothing applies, and nothing in a provisioning run says so.

The environment-variable name a source reads its credential from SHALL be the same name that environment declares as its read-only secret. A workflow converging an environment holds that credential under the declared name and must supply it under the name the source reads; where the two differ, the workflow would have to carry the mapping, which is the environment-naming in workflow text the pipeline's own requirements forbid. Requiring the two to be *distinct per environment* does not make them *equal to each other*, and the difference is what this clause states: without it, "adding an environment needs no workflow edit" rests on a coincidence rather than on an obligation.


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

#### Scenario: An environment that can be provisioned but not converged is reported
- **WHEN** an environment carries a pipeline declaration but no inventory source or no variables file of its own
- **THEN** that SHALL be reported as a failure naming the environment, rather than leaving an environment whose host configuration nothing applies

#### Scenario: A source's credential variable is the name the environment declares
- **WHEN** an environment's inventory source and its pipeline declaration are read together
- **THEN** the environment variable the source takes its credential from SHALL carry the same name the declaration states as that environment's read-only secret
