## ADDED Requirements

### Requirement: A Host-Scoped Variable Lives in the Host's Own Vars File
A variable SHALL be supplied from a host's own vars file, named for the Hetzner server name that host carries, wherever a second host of a different tenant in the same environment would require a different value or none at all. Such a variable SHALL NOT be supplied from an environment's `group_vars`. An environment's `group_vars` file SHALL carry only what is true of every host in that environment whichever tenant owns it — which is what an environment-wide baseline across tenants *is*, and is what makes it safe for two stacks to read one file.

**The test is the variable's blast radius, not the number of hosts that happen to exist.** Where a repository has one stack per environment the two files are interchangeable and a variable placed in either resolves identically, so a misplacement is wrong before it is observably wrong. It becomes observably wrong at the moment a second tenant's stack declares the same environment, and it does so by silently widening what an existing entry reaches rather than by failing — which is why the placement is obliged here rather than left to be corrected when it starts to matter.

**The deploy-key authorisations a host grants are such a variable, and the invariant behind them is stated rather than left implied: one leaked private half SHALL reach one host.** A deploy key's public half therefore sits in the vars file of the one host it authorises, the shared platform stack's included. Where one application deploys to two hosts it SHALL do so with two keypairs, one enumerated in each host's file, and no single entry SHALL authorise a deploy to more than one host.

**The placements this requirement's own change examined and did not correct are named here rather than left to be discovered, and this requirement SHALL be read as unmet in those respects.** They are three, and three is what was assessed rather than what exists: no audit of the remaining variables in any environment's `group_vars` has been performed, and this list SHALL NOT be read as one. `hardening_ssh_allowed_cidrs` and `hardening_web_allowed_cidrs` mirror one *stack's* committed Terraform variables, and two tenants' stacks in one environment may open different ports to different places; `ops_user_accounts` grants an interactive login, and an operator of one tenant's host is not thereby an operator of another's. All three sit in an environment's `group_vars` today. Each needs a decision this requirement does not make — whether a per-stack firewall pair defeats the point of an environment-wide hardening baseline, and whether operator access is per environment or per tenant — and they are tracked in `docs/backlog.md` as `put-the-remaining-host-scoped-variables-on-the-host-axis`, which covers the audit as well as the three. The obligation is stated here as well as there, because a backlog entry is deleted when its change is archived. **This paragraph is replaced when those three move, and not before**, and a further variable placed in an environment's `group_vars` on the strength of it is a breach rather than a precedent.

A host vars file carries no vaulted content today, and the labelling of one is outside this requirement. Where a secret-bearing variable first lands in a host's own file, the `--vault-id` label it is encrypted under follows the *run* — which is the environment, per *Host Configuration Names the Environment It Targets* — and not the file it sits in.

This requirement governs where a value is written, not what any role does with it. A role consumes a host variable without regard to which file supplied it, so nothing here obliges a role to change, and a role's own refusal when a required input is absent is *A Role's Absent Required Input Is Reported by Name* rather than this.

#### Scenario: Two stacks share an environment
- **WHEN** two stacks of different tenants declare the same Ansible group, and one application is deployed to both of their hosts
- **THEN** each host's deploy-key authorisation SHALL be enumerated in that host's own vars file, each naming a keypair of its own
- **AND** neither SHALL be enumerated in the environment's `group_vars` file, where one entry would authorise both hosts

#### Scenario: A value that is a property of the environment
- **WHEN** a variable's value is a property of the environment rather than of a host — a baseline every host in that environment receives, whichever stack provisions it
- **THEN** it SHALL be supplied from that environment's `group_vars` file
- **AND** it SHALL NOT be repeated in each host's vars file, which would make an environment-wide correction a per-host edit that nothing enumerates

#### Scenario: A stack whose declared server has no vars file is reported
- **WHEN** a stack's committed Terraform configuration declares a server name for which no committed host vars file exists
- **THEN** that SHALL be reported as a failure on the pull request, naming the stack and the file expected of it, rather than left to surface as a role refusing a required input part-way through a converge

#### Scenario: A host vars file is keyed on the name Terraform declares
- **WHEN** a stack renames the server it provisions without renaming the host vars file that carries that host's variables
- **THEN** the mismatch SHALL be reported rather than resolved, so that the converge cannot proceed against a host whose variables no committed file supplies

## MODIFIED Requirements

### Requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack
Ansible SHALL discover target hosts via the `hcloud` dynamic inventory plugin rather than a static or hand-maintained inventory file. Hosts SHALL be grouped by the Hetzner labels already applied to every resource, one group per axis: by the `environment` label, and by the `tenant` label. A group per axis is what lets a baseline be written for an axis without special-casing the stacks that carry it.

Each **stack** SHALL declare its own inventory source, and each source SHALL authenticate with that stack's own read-only Hetzner credential, supplied from an environment variable whose name is distinct from every other stack's. A Hetzner credential is scoped to one project and each stack has a project of its own, so a source reaches exactly one stack; a single source that every stack shares would reach whichever project the credential in scope happened to belong to, and nothing in a run would say which.

**A source is named for its stack and a group is named for its axis, and neither SHALL be derived from the other.** An inventory source's filename follows the stack it reaches, because what it reaches is a Hetzner project. The group a play targets, the vault-id label its secrets are labelled under and the `group_vars` file that supplies its variables follow the *environment*, because that is what those things describe. The two coincide only where a repository has one tenant, and the value is read from the stack's own pipeline declaration (see *Each Stack Declares Its Own Pipeline Configuration*, `iac-cicd-pipeline`) rather than parsed out of either name.

**A third axis carries a file of its own, and is named here because two axes read as the whole list.** A host's vars file follows the *host*, which is the Hetzner server name its stack provisions and the value `inventory_hostname` resolves to under this plugin. Which variables belong in it rather than in an environment's `group_vars` is *A Host-Scoped Variable Lives in the Host's Own Vars File*, in this same capability; that they are two different files, resolved for two different scopes, is what this clause adds to the pair above.

Bringing a further stack into inventory SHALL therefore be adding a source, a credential name and a host vars file, and SHALL NOT require editing an existing stack's source. It does not necessarily add a `group_vars` file: a stack whose environment another stack already declares reads that environment's existing variables, which is what an environment-wide baseline means. It does always add a **host vars file**, because a stack provisions a host of its own and the variables scoped to that host have nowhere else they may go.

An inventory source whose credential is absent or is rejected SHALL fail the run. It SHALL NOT resolve to an empty group, which is indistinguishable from a stack whose server does not exist.

A stack that carries a pipeline declaration SHALL carry an inventory source of its own, the `group_vars` file its declared group names SHALL exist, and the host vars file named for the server that stack's committed Terraform configuration declares SHALL exist. A stack that can be provisioned but not converged is one whose host configuration nothing applies, and nothing in a provisioning run says so.

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
- **THEN** it SHALL be brought into inventory by adding a source of its own, a credential name of its own and a host vars file of its own, without editing any existing stack's inventory source

#### Scenario: An inventory source cannot authenticate
- **WHEN** a run names an inventory source whose credential is absent, empty or rejected by the API
- **THEN** the run SHALL fail reporting that the source could not be parsed, rather than continuing with an inventory in which that stack holds no host

#### Scenario: A stack that can be provisioned but not converged is reported
- **WHEN** a stack carries a pipeline declaration but no inventory source, or its declared environment has no variables file, or the server it declares has no host vars file
- **THEN** that SHALL be reported as a failure naming the stack, rather than leaving a stack whose host configuration nothing applies

#### Scenario: A source's credential variable is the name the stack declares
- **WHEN** a stack's inventory source and its pipeline declaration are read together
- **THEN** the environment variable the source takes its credential from SHALL carry the same name the declaration states as that stack's read-only secret
