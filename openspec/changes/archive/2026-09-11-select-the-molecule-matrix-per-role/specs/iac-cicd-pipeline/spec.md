## ADDED Requirements

### Requirement: The Molecule Matrix Runs the Roles a Pull Request Owes
The Molecule suite SHALL run the roles a pull request's changed files owe, rather than every discovered role, and what a set of changed files owes SHALL be the reverse closure of a role-dependency graph derived from the scenario definitions in the checkout being tested. Nothing SHALL commit that graph: a graph recorded in a file is a list, and a list that falls behind the scenarios it describes under-selects silently — the aggregating gate sees a matrix that passed over the rows it was handed and has no way to learn which rows it should have been handed.

This narrows *which* roles run. It does not narrow what a role runs: every selected role SHALL still execute every scenario it declares, per the requirement above.

**Attribution is by role directory, and everything else widens.** A changed path SHALL attribute to role `R` where and only where it lies under that role's own directory. Every other path the suite's change detection admits SHALL select every discovered role — the shared manifests that determine what all scenarios run under, the entry point that runs them, and equally any path this attribution does not recognise. Where a rule over paths can fall behind the tree, the direction that fails safely is to run: an unrecognised path that widens costs runner time and is visible in the run, where one that narrows to nothing costs the coverage this check exists to provide and reports green.

Attribution SHALL rest on the directory name rather than on whether that role carries scenarios of its own. A role with no scenarios may still be converged by another role's, so a change to it is owed by that other role; resolving it to nothing selectable would produce an empty selection where the suite was owed.

**The selection SHALL be the closure restricted to the roles the run can execute.** Attribution and the closure both range over role directories, and only a role carrying scenarios can be run — so a role in the closure that declares none SHALL be dropped after the closure is taken and before the matrix is fed. Leaving that implicit puts a matrix row on a role with no scenarios for the runner to find, which fails on a role that never had any.

Where that restriction leaves the selection empty, the selection SHALL be every discovered role. A change *confined to* such a role is not verifiable by this suite at all, and for it the alternatives are both worse than running it in full: a matrix row for a role with no scenarios fails on a role that never had any, and an empty selection fails under the refusal below. Neither can be made green by the author of a legitimate change, and a required status check SHALL NOT be unsatisfiable for a change it cannot verify.

That widening SHALL be evaluated over the selection as a whole rather than per attributed role: a pull request touching only such a role runs every role, while one touching such a role alongside a role that can be run runs the latter's selection alone. Widening for an unverifiable role buys no coverage — it is unverifiable by this suite whether or not other roles run — so the wider run is owed only where there would otherwise be nothing to run at all.

**The derivation SHALL follow, or refuse, every construction by which a scenario reaches a role**, and SHALL refuse a construction it has no rule for rather than passing over it. Following and refusing are both conformant dispositions; passing over is not. A construction not followed under-reads the graph, and under-reading loses coverage with nothing reporting; a construction refused costs a visible edit. For the same reason, a role name that is not a literal in the scenario text SHALL be refused rather than resolved or skipped.

**Refusal SHALL extend to routes outside a scenario's own directory that reach a role.** Any construction in a role's own task or handler file reaching content outside that role's directory is such a route, and is not visible to any check that walks scenario directories alone. The rule SHALL be keyed on what is reached rather than on a role being named: an include of another role's task file by path names no role, and couples the two exactly as an invocation would. Where a route cannot be closed over — a nested playbook invocation naming its playbook by expression rather than by literal — it SHALL be refused unless an explicit entry records that instance and why it is safe, keyed on the file, the construction and the target it resolves to, in the same form this repository already uses to permit such a read. A blanket exemption for the construction SHALL NOT be written in place of an entry for the instance.

**Two refusals, over different sets.** Discovery's existing obligation to fail where it finds no role carrying scenarios SHALL continue to read the tree rather than the selection — it is a fact about the repository, not about the diff, and a vanished suite SHALL NOT be reportable as a correct skip. Separately, a selection that is empty on a run that owes the suite SHALL fail: it cannot arise from the widening above, so it means the derivation is broken, and the run SHALL say so rather than hand the matrix an empty list and let the resulting skip be read.

**The aggregating job SHALL distinguish a narrowed run from a skipped one**, and SHALL name the subset it ran. Its existing refusals SHALL be unchanged: a discovery that did not succeed, and a skip on a run that asked for the suite, SHALL each still fail. It SHALL additionally fail where the matrix ran on a run that owed the suite nothing. That state is unreachable while the matrix job remains gated on whether the suite is owed rather than on the selection, and the refusal is owed anyway: the two outputs disagreeing would mean the selection and the decision to run were computed from different things, which is the defect this whole requirement exists to make visible.

Where the workflow is started by an event carrying no diff, the selection SHALL be every discovered role, by the same branch that already resolves the suite as owed on such an event, so that the two cannot come to disagree.

The derivation and its closure SHALL be checked statically, by the checks that already read these scenario definitions, under the same enumeration of this repository's own roles — so that installed Galaxy content cannot make the check report one result on a provisioned developer machine and another on a runner that has installed nothing.

#### Scenario: A pull request confined to one role runs that role and the roles converging it
- **WHEN** a pull request changes only files under one role's own directory, and other roles' scenarios converge that role
- **THEN** the matrix SHALL run that role together with every role whose scenarios converge it, directly or transitively, and SHALL NOT run any other role

#### Scenario: A role no scenario converges runs alone
- **WHEN** a pull request changes only files under the directory of a role that carries scenarios of its own and that no other role's scenarios converge
- **THEN** the matrix SHALL run that role alone

#### Scenario: A shared input runs every role
- **WHEN** a pull request changes a manifest, entry point or configuration file that determines what every scenario runs under, rather than a file under one role's directory
- **THEN** the matrix SHALL run every discovered role

#### Scenario: A path the attribution does not recognise runs every role
- **WHEN** a pull request changes a path the suite's change detection admits and this attribution has no rule for
- **THEN** the matrix SHALL run every discovered role, rather than selecting none — a path nobody anticipated SHALL widen the run rather than silently narrow it

#### Scenario: A change to a role that nothing converges and nothing tests runs every role
- **WHEN** a pull request changes only files under the directory of a role that declares no scenarios of its own and that no other role's scenarios converge
- **THEN** the matrix SHALL run every discovered role, rather than resolving to an empty selection or to a row for a role with no scenarios — a required status check SHALL NOT be left unsatisfiable for a change this suite cannot verify

#### Scenario: A role's own tasks reaching outside that role is refused
- **WHEN** the derivation reaches a construction in a role's own task or handler file that reaches content outside that role's directory, whether by naming another role or by naming a path into one
- **THEN** it SHALL fail identifying that file, rather than deriving a graph missing that edge — such a route lies outside every scenario directory and no check that walks those alone can see it

#### Scenario: An unverifiable role alongside a verifiable one does not widen the run
- **WHEN** a pull request changes files under the directory of a role that declares no scenarios and that nothing converges, and also under the directory of a role that can be run
- **THEN** the matrix SHALL run the latter's selection alone, rather than widening to every role — the unverifiable role is unverifiable whether or not the others run, so widening for it buys no coverage

#### Scenario: A role in the closure that carries no scenarios is not given a matrix row
- **WHEN** a closure contains a role declaring no scenarios alongside roles that do
- **THEN** the selection SHALL carry only the roles that can be run, and SHALL NOT carry a row for the role with no scenarios — a row the runner cannot execute fails on a role that never had anything to execute

#### Scenario: A route that cannot be closed over is permitted by instance, not by construction
- **WHEN** the derivation reaches a nested playbook invocation naming its playbook by expression rather than by literal
- **THEN** it SHALL refuse unless an explicit entry records that instance, keyed on file, construction and resolved target; exempting the construction wholesale SHALL NOT be accepted in place of such an entry

#### Scenario: A change to a role carrying no scenarios still runs the roles that converge it
- **WHEN** a pull request changes files under the directory of a role that declares no scenarios of its own, and another role's scenarios converge it
- **THEN** the matrix SHALL run those other roles, rather than resolving the change to an empty selection

#### Scenario: A construction the derivation cannot resolve fails the run
- **WHEN** the derivation reaches a scenario construction it has no rule for, or one naming a role by something other than a literal
- **THEN** it SHALL fail identifying that construction and the file holding it, rather than passing over it and deriving a graph missing that edge

#### Scenario: An empty selection on a run that owes the suite fails
- **WHEN** the suite is owed and the selection resolves to no role at all
- **THEN** the run SHALL fail identifying the selection as the cause, and the matrix SHALL NOT be handed an empty list

#### Scenario: Discovery still refuses a tree carrying no scenarios
- **WHEN** no role under the roles directory carries a scenario directory, whatever the pull request changed
- **THEN** discovery SHALL fail as it does today, reading the tree rather than the selection — a suite that has disappeared SHALL NOT be reportable as a correct skip

#### Scenario: The aggregating job names the subset it ran
- **WHEN** the matrix runs on a narrowed selection and passes
- **THEN** the aggregating job SHALL conclude success and SHALL state which roles ran and why that subset, so that a wrongly narrow run is legible to a reader of the check

#### Scenario: A matrix that ran where nothing was owed fails
- **WHEN** the matrix concludes having run on a pull request whose changed files owe the suite nothing
- **THEN** the aggregating job SHALL fail rather than conclude success — the two outputs disagreeing means the selection and the decision to run were computed from different things

#### Scenario: A run carrying no diff runs every role
- **WHEN** the workflow is started by an event that carries no diff to attribute
- **THEN** the selection SHALL be every discovered role, resolved by the same branch that resolves the suite as owed on such an event

#### Scenario: A scenario added later is covered without editing the check
- **WHEN** a scenario is added that converges a role it did not converge before, and no change is made to the static check that reads these definitions
- **THEN** the derived graph SHALL carry the new edge and the check SHALL assert the closure including it
