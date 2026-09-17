## MODIFIED Requirements

### Requirement: Ansible Configuration Is Verified in Continuous Integration and Gates the Merge
Every pull request that changes files under `ansible/` SHALL trigger continuous-integration checks over that configuration. Both tiers block a merge; they remain distinguished by cost, which governs how each is triggered rather than whether it gates.

**Lint tier.** `ansible-lint` and `ansible-playbook --syntax-check` SHALL run as part of the required pull request status check, using the same invocation the repository's `pre-commit` configuration uses locally, so that a pull request cannot merge with Ansible content that fails either. These checks require no container runtime and no credential. This tier SHALL be triggered by any change under `ansible/`, without exclusion: it is the tier that covers the paths the suite tier does not read.

**That the lint tier remains unexcluded SHALL be asserted, not reviewed.** It is the compensating coverage for every path the suite tier stops selecting, so a narrowing of it would withdraw that coverage with nothing failing — and "which checks are gated on which paths" is exactly what this capability requires its own executable suite to assert. An assertion establishing only that a filter for this directory exists does not establish this.

**Suite tier.** The Molecule suite SHALL run in continuous integration on pull requests changing the Ansible content its scenarios read, and SHALL be registered as a required status check. Its scenarios exercise host-level firewalling, `fail2ban` and service management inside containers; that these are reproducible on a hosted runner is established by consecutive green runs on pull requests with independent subjects, which is what the previously advisory tier existed to observe. A scenario that fails SHALL block the merge.

Because the suite is costly and the lint tier is not, the suite SHALL be triggered by change detection *inside* an always-running workflow rather than by a workflow-level path filter, per the requirement above, and a pull request touching nothing the suite reads SHALL start no container. Its conclusion SHALL be reported by an aggregating job whose name is a literal, which SHALL fail where the suite was skipped on a pull request that did change content the suite reads.

**What the suite reads is narrower than `ansible/`, and the difference SHALL be declared as exclusions rather than as inclusions.** Change detection SHALL match the whole of `ansible/` and then subtract the paths established, by reading the scenarios themselves, to be unread by any of them. A path added under `ansible/` and considered by nobody SHALL therefore trigger the suite. The opposite spelling — naming the paths that do trigger it — makes such a path silently skip, and a skip that reports green is the failure this capability's discovery refusal, its gate and its resolution step are each written to prevent. Wasteful and visible is the recoverable direction; economical and silent is not.

An exclusion SHALL be justified by what scenario text does, not by what a directory is named. A path a scenario names in a comment, or asserts as a substring of an expected failure message, is not a path that scenario reads.

**A static property of committed files reaching outside the role directory whose scenario holds it SHALL NOT be verified only by the suite.** It SHALL be asserted by the pipeline's own executable test suite instead, which runs on every pull request unconditionally. Such an assertion held inside a scenario covers only the pull requests that happen to trigger that scenario, which is not the scope it claims; and it is what would make narrowing the suite's trigger unsafe, since excluding a path would silently withdraw the only check that reads it. The scan that establishes a repository-scope credential property SHALL be rooted at the repository rather than at whichever directory motivated it, so that its root matches the scope its requirement states. A narrower scan retained **in addition** — one whose claim is bounded by the directory it reads, and which therefore states nothing about the repository — is not that scan and is not held to this.

**The premise the exclusions rest on SHALL itself be checked.** That no scenario reads an excluded path is a static read of committed scenario text, and SHALL be asserted as one: a scenario reaching the controller's filesystem outside the paths the exclusions were established against SHALL fail the pipeline's own configuration checks. A check on the filter's declared patterns does not establish this and is not a substitute for it — the filter can be correct about a premise that has stopped being true.

**What that check looks for is a scenario reading a repository file from the controller**, and both halves of that are load-bearing. A read of the managed node cannot be affected by a filter over this repository and is out of scope; so is a controller-side task that derives a value from an already-registered fact without opening a file. A check drawn wider than this fires on the bulk of ordinary scenario text, and the only recoveries from that are to permit those sites wholesale — which makes the check meaningless — or to narrow it by an unstated rule, which is the defect it exists to prevent.

Within that scope the check SHALL recognise **every** route, not the one route a particular scan happened to use. Delegation to the controller is one. A file-reading lookup expression is another and needs no delegation, executing on the controller wherever it appears. Controller-resolved inclusion is a third, and covers the inclusion of **tasks and plays** as much as of variables — a scenario importing a play by path reads that file from the controller exactly as one loading variables from it does, and it is the likeliest route by which a scenario would come to read the playbook directory, which is excluded. A source path on a module that sends a file to the managed node is a fourth, being a controller path unless the module declares otherwise — where a module that reads *from* the managed node instead is a controller read only when the task delegates, so delegation rather than any option on the module is what decides it. A path declared in a scenario's own configuration file is a fifth — in its provisioner environment or in the options it passes to its dependency resolution — being neither a task nor a play. A check recognising only delegation passes a scenario that reads an excluded path through any of the others, which is the same vacuous green this capability refuses everywhere else.

**Where the check meets a construction it does not recognise, carrying a path that resolves into this repository, it SHALL refuse rather than pass over it.** A list of routes goes stale exactly as a list of paths does, and the polarity that answers one answers the other: an unrecognised construction that is ignored is a silent gap, where one that is refused costs a visible edit to permit. This obligation is bounded by the criterion above, which already excludes reads of the managed node, so breadth here does not reach ordinary scenario text.

**The permitted reads SHALL be enumerated individually, and each SHALL be identified by the file that holds it together with the construction and the target it resolves to — never by a line offset.** Enumerating the permitted *paths* instead would admit a second, newly added read of an already-permitted path without anyone considering it, which is the thing this check exists to refuse. Enumerating by line offset would make the permitted set wrong on any commit that edits a scenario above one of them — including the very commit that relocates the reads this check is written alongside — and a permitted set that is stale reports the surviving reads as violations, or silently permits whatever text has moved onto the recorded offsets. Identity that survives ordinary editing is a property of the mechanism, not a convenience.

**Each entry SHALL additionally record how many occurrences it permits within the file that holds it, and a count above that SHALL fail.** Where an entry names a declaration every scenario carries rather than a read in one file, its permitted count is per file on the same terms. An identity built from a file, a construction and a target does not by itself separate one read from two of the same shape, and the second read of an already-permitted target is most naturally added in the file that already holds the first — so membership alone would admit precisely the addition this enumeration exists to make someone look at.

Change detection resolves against a pull request's diff. Where the workflow is started by any other event there is no diff to resolve against, and the suite SHALL run in full rather than defaulting to skipped. A default of skipped would report a green conclusion on precisely the trigger this repository uses to observe the suite against the trunk.

Where the suite is correctly skipped, the message the aggregating job reports SHALL say that nothing the suite reads changed, rather than that nothing under the configuration directory changed. Once the two differ, the second is false on exactly the runs a reader consults it about.

Discovery SHALL declare the least privilege its change detection needs, per the *Least-Privilege Workflow Permissions* requirement, and SHALL receive no write scope: reading which files a pull request touched is a read.

The Molecule run SHALL discover role scenarios rather than enumerate them, so that a role or scenario added under `ansible/roles/` is covered without a workflow edit, and SHALL execute every scenario a role declares rather than only its `default` scenario.

Discovery SHALL fail loudly rather than succeed vacuously: where it finds no role to run, the run SHALL fail with a message identifying discovery as the cause, and SHALL NOT report success. A discovery that silently matches nothing is indistinguishable from a suite that passed, which is the same defect this capability's destroy-policy gate and secret scanning requirements each forbid elsewhere. Discovery SHALL run on every pull request rather than only on those changing `ansible/`: a repository state in which no role carries scenarios has lost the check that gates every merge, and the pull request that removes it is not the only one that should stop. That refusal is over the roles the tree carries and SHALL remain independent of what the diff selected, so that a discovery failure cannot be reported as a correct skip.

The Molecule run SHALL install its toolchain from the repository's exact pinned manifests — `ansible/requirements-test.txt` for the Python toolchain and `ansible/requirements.yml` for Galaxy content — and SHALL NOT resolve any dependency version freshly at run time. Neither manifest SHALL be excluded from change detection: a change to either changes what every scenario runs under.

That obligation SHALL extend to the container image each scenario executes inside, which is as much a run-time-resolved dependency as either manifest and determines what the pinned toolchain runs against. Every scenario SHALL declare its platform image by immutable content digest, so that every machine resolves the same immutable reference and an upstream re-push of a tag cannot change what the suite tested without a reviewable commit. Where the image publishes no version tag, the digest is the only exact form available and SHALL be used; where a multi-architecture image is published, the digest declared SHALL be the multi-architecture one, so that each architecture resolves deterministically beneath a single pinned reference rather than the pin excluding an architecture the suite is expected to run on.

Where two scenarios name the same image repository, they SHALL name the same digest. Scenarios are defined one per file with no shared inclusion, so a pin repeated across them drifts when one is refreshed and the others are not — leaving the suite running against two versions of the same image while appearing pinned. This constrains only scenarios that already agree on an image; it does not require the suite to standardise on a single base image.

A scenario SHALL NOT be exempt from this by being newly added: the obligation is over every scenario this repository authors, and a scenario reintroducing a mutable tag, or disagreeing with its siblings' digest, SHALL fail the pipeline's own configuration checks rather than being caught by review alone.

The obligation SHALL NOT extend to scenarios shipped by Galaxy content installed from `ansible/requirements.yml`, which install beside this repository's own roles and are not committed here. Such content is already pinned as a whole by that manifest, and its scenario definitions are neither editable in place — a reinstall discards local edits — nor reachable by review. The check SHALL derive that exclusion from the manifest's own contents rather than from a hardcoded list of role names, so that adding or removing pinned Galaxy content cannot leave the exclusion stale in either direction.

Every scenario SHALL declare its instance name so that it resolves to a value unique to the working tree the run was started from, rather than to a literal shared by every working tree on the machine. Its default, where no working tree supplies one, SHALL be a value that cannot name a container at all, rather than one that merely reads as wrong: a default that would successfully create an instance reinstates the shared literal under a different spelling. Every scenario SHALL additionally declare an explicit host name for its instance, bounded independently of the instance name, because a host name derived from a namespaced instance name is not bounded by anything the scenario controls and fails once a working tree's own name grows long enough.

The run-time obligation the first of these serves belongs to `iac-repo-foundations`'s *Verification Writing to Shared State Is Namespaced per Working Tree*; what this requirement adds is that the scenario definitions SHALL be checked, statically, to carry all three.

Those obligations SHALL be checked statically over the same scenario definitions this repository authors, by the same checks that read their platform images, and SHALL derive its exclusion of installed Galaxy content from `ansible/requirements.yml` in the same way. A scenario added later SHALL be covered without an edit to the check.

**A scenario's fixtures reach handles the scenario definition does not declare, and those SHALL be held to the same obligation.** A fixture play that claims a handle the machine's kernel holds — a loop device minor is the instance in this repository — SHALL derive it from a value the entry point supplies rather than name it as a literal, and the entry point SHALL supply that value **resolved to one unique to the working tree the run was started from**, on the same terms as the instance name above and not merely as a value that exists. An entry point supplying a constant satisfies the plumbing and reinstates the shared literal the obligation exists to remove, so that it derives from the working tree SHALL be checked and not left to reading. The first of these SHALL be checked statically over the fixture plays beside each authored scenario definition, on the same terms and with the same Galaxy exclusion as the definitions themselves; the second and third SHALL be checked over the entry point itself. Checking one alone establishes nothing: the entry point and the fixtures are written in different languages with nothing but a variable name between them, so a rename on either side resolves to an unset value rather than to an error.

**The fixture plays are a second enumeration, and it SHALL refuse to pass over nothing.** Where the checks over them find no fixture play *deriving* such a handle from the value the entry point supplies, they SHALL fail naming the enumeration as the cause rather than reporting success for a property nothing examined. The set counted is that subset and not the wider one of plays claiming such a handle by any means: the wider set is non-empty wherever a play names a literal, which is the very state these obligations forbid, so counting it would report the enumeration healthy in exactly the condition that withdraws every other check over it. This is the obligation the discovery, image-pin and tracked-file refusals in this requirement each place on their own enumerations, and it is owed here for the same reason: every check over this set reports green on an empty one, so a path change, a rename or an edit to the helper that builds it withdraws the whole static half of these obligations with nothing failing.

**A kernel-held handle is not covered by the instance-name obligation above, and the difference is why this is stated separately.** An instance name is shared between working trees and a container is destroyed when its scenario ends; a loop association is made by the machine's kernel, survives the container that made it, and is therefore shared between a single working tree's *consecutive* runs as well as between trees. A fixture inheriting one silently inherits whatever state the previous run left on it, which for a scenario whose subject is what the role does to an unformatted device is a pass that exercised nothing.

**Where such a handle is derived rather than chosen, the fixture SHALL establish that the handle is free before claiming it, and SHALL refuse a handle it cannot attribute to its own fixtures rather than reclaiming it.** A derived handle is a number nothing outside this repository has agreed to leave alone, and a privileged fixture reclaiming one the host is using damages the machine the verification runs on. Refusing is the recoverable direction and reclaiming is not.

**That the fixture acts on what it reads SHALL be checked, and not only that it reads.** A play that reads what holds the handle, registers the result and then releases the handle regardless satisfies every check a read-only assertion can make while doing the exact thing this obligation forbids, so the check SHALL establish that a refusal stands between the read and the release. What is checked is the committed file's shape. The run-time refusal it produces is not reachable without a fixture whose purpose is to contaminate another scenario's handle — which would leak an association of its own, and would require the guard to be restructured out of the first task of the first play into a unit something could catch failing. Neither is owed for a guard whose static shape is checked.

**The workflow that runs the suite SHALL invoke it through the entry point that supplies these values**, and that SHALL be asserted statically rather than left to the workflow's author. A workflow invoking the tool directly supplies neither, which makes the fixture plays that derive a handle refuse and every other scenario fail at `create` on the instance-name default above — a required check failing for a reason no assertion names.

Neither tier SHALL declare a deployment `environment:` or receive any production credential; the Molecule suite runs offline against local containers.

#### Scenario: Ansible-only pull request is linted and syntax-checked
- **WHEN** a pull request changes a file under `ansible/` and no Terraform file
- **THEN** the required status check SHALL run `ansible-lint` and `ansible-playbook --syntax-check` and SHALL fail if either reports an error

#### Scenario: Narrowing the lint tier's trigger fails the pipeline's own checks
- **WHEN** the lint tier's change detection is edited so that a path under `ansible/` which the suite tier excludes no longer selects it
- **THEN** the pipeline's own configuration checks SHALL fail, rather than the compensating coverage for the suite tier's exclusions being withdrawn with nothing reporting

#### Scenario: A pull request changing only Ansible content no scenario reads starts no container
- **WHEN** a pull request's whole `ansible/` footprint is paths change detection excludes as unread by any scenario
- **THEN** the Molecule matrix SHALL be skipped rather than executed, the lint tier SHALL still run over those paths, and the aggregating job SHALL conclude success

#### Scenario: An unconsidered new path under the configuration directory runs the suite
- **WHEN** a pull request adds a file under `ansible/` that change detection's exclusions do not name
- **THEN** the Molecule suite SHALL run, rather than being skipped for want of an inclusion naming it

#### Scenario: A correct skip says what was actually unchanged
- **WHEN** the aggregating job concludes success having correctly skipped the suite
- **THEN** its message SHALL state that nothing the suite reads changed, rather than that nothing under the configuration directory changed

#### Scenario: A committed credential is caught wherever in the repository it lands
- **WHEN** a pull request commits a GitHub or GHCR token marker, or an operator private-key marker, in any tracked file — including one under no directory the Molecule suite is triggered by
- **THEN** the pipeline's own executable test suite SHALL fail on that pull request naming the file, and that failure SHALL NOT depend on whether change detection selected the Molecule suite

#### Scenario: A credential assigned across a folded scalar's continuation is still caught
- **WHEN** a tracked file assigns the registry pull token as a YAML folded or block scalar, so that the assignment line carries no value and the value occupies the following more-indented lines
- **THEN** the scan SHALL read the assignment together with its continuation and SHALL fail where that value is a committed literal, accepting it only where it is an inline vault value or an environment lookup — a line-oriented reading, which passes over every such assignment, SHALL NOT satisfy this

#### Scenario: A second read of an already-permitted path is still refused
- **WHEN** a scenario adds a controller-side read of a path some other permitted read already reaches — including one in the same file, by the same construction, resolving to the same target, so that it is indistinguishable from the permitted read by identity alone
- **THEN** those checks SHALL refuse it until it is itself enumerated, the permitted set being over individual reads rather than over the paths they reach, and each entry's permitted occurrence count being what separates one such read from two

#### Scenario: Editing a scenario above a permitted read does not invalidate the permitted set
- **WHEN** a commit inserts or removes lines in a scenario file above a read the permitted set names — including the commit that relocates reads out of that same file
- **THEN** those checks SHALL continue to recognise that read as the permitted one, its identity resting on the file, the construction and the target it resolves to rather than on a line offset

#### Scenario: A scenario reaching an excluded path fails the pipeline's own checks
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors and find a controller-side read outside the paths change detection's exclusions were established against
- **THEN** those checks SHALL fail identifying that scenario and that read, rather than leaving the exclusion silently covering a path that is now read

#### Scenario: A controller read that does not delegate is still a controller read
- **WHEN** a scenario reaches the controller's filesystem on a task or play that does not delegate to the controller — through a file-reading lookup expression, a controller-resolved inclusion of variables, tasks or plays, or a controller-side source path — or through a path declared in its own scenario configuration, which carries no task at all
- **THEN** those checks SHALL treat it as a controller read and hold it to the same enumerated paths, rather than passing over it for carrying no delegation

#### Scenario: A read of the managed node is not held to the enumerated paths
- **WHEN** a scenario reads a path on the host it converges — an absolute path inside the container, through a module that reads from the managed node on a task that does not delegate to the controller
- **THEN** those checks SHALL pass over it, no filter over this repository being capable of affecting it, and SHALL NOT require it to be enumerated among the permitted controller reads

#### Scenario: A newly added role scenario runs without a workflow change
- **WHEN** a pull request adds a scenario directory under `ansible/roles/<role>/molecule/`, and no change is made to the workflow to name that role or scenario
- **THEN** the Molecule run SHALL still execute that scenario

#### Scenario: Every scenario a role declares is executed
- **WHEN** the Molecule run reaches a role that declares more than one scenario
- **THEN** it SHALL execute all of that role's scenarios, not only the `default` scenario

#### Scenario: Discovering no roles fails rather than passes
- **WHEN** the Molecule run's role discovery yields an empty set
- **THEN** the run SHALL fail with a message identifying discovery as the cause, rather than concluding successfully having executed no scenario

#### Scenario: Discovery failing is not reported as a correct skip
- **WHEN** role discovery fails on a pull request whose diff change detection would have excluded
- **THEN** the aggregating job SHALL fail identifying discovery as the cause, rather than concluding success on the ground that the suite was not owed

#### Scenario: A failing Molecule scenario blocks the merge
- **WHEN** a Molecule scenario fails on a pull request
- **THEN** the failure SHALL be visible on the pull request, the aggregating job SHALL conclude failure, and the pull request SHALL be blocked from merging

#### Scenario: A pull request touching no Ansible file starts no container
- **WHEN** a pull request changes no file under `ansible/`
- **THEN** the Molecule matrix SHALL be skipped rather than executed, and the workflow SHALL still conclude and report

#### Scenario: Role discovery runs even where the suite does not
- **WHEN** a pull request changes no file under `ansible/`
- **THEN** role discovery SHALL still run, and where it finds no role its failure SHALL fail the required status check — the suite that gates every merge having silently disappeared is not a fact only pull requests touching `ansible/` should learn

#### Scenario: A manual run verifies the whole suite
- **WHEN** the Molecule workflow is started other than by a pull request
- **THEN** the suite SHALL run in full rather than being skipped for want of a diff to inspect, and the workflow SHALL NOT conclude success having skipped it

#### Scenario: A change to a pinned manifest runs the suite
- **WHEN** a pull request changes `ansible/requirements-test.txt` or `ansible/requirements.yml` and no file under `ansible/roles/`
- **THEN** the Molecule suite SHALL run, both manifests determining what every scenario executes under

#### Scenario: Ansible verification receives no production credential
- **WHEN** any Ansible verification job runs on a pull request
- **THEN** it SHALL complete without a Hetzner API token, an SSH deploy key, a registry credential, or a declared deployment `environment:`

#### Scenario: Every scenario's platform image is pinned by digest
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every declared platform image SHALL carry an immutable content digest, and a scenario declaring an image by mutable tag alone SHALL fail those checks

#### Scenario: A scenario declaring no platform image fails rather than being skipped
- **WHEN** those checks reach a scenario definition that declares no platform, or a platform with no image
- **THEN** the checks SHALL fail identifying that scenario, rather than passing over it — a scenario silently exempted from a pinning check is indistinguishable from a scenario that satisfies it

#### Scenario: Scenarios sharing an image repository agree on its digest
- **WHEN** two or more scenario definitions name the same image repository
- **THEN** they SHALL name the same digest, and a partial refresh leaving one at a different digest SHALL fail those checks

#### Scenario: Installed Galaxy content is not held to this repository's pinning obligation
- **WHEN** Galaxy content pinned in `ansible/requirements.yml` is installed into `ansible/roles/` and ships a scenario definition of its own
- **THEN** those checks SHALL exclude it, deriving the exclusion from that manifest, and SHALL report the same result on a provisioned developer machine as on a continuous-integration runner that has installed nothing

#### Scenario: An upstream re-push cannot change what the suite ran against
- **WHEN** the upstream registry re-publishes the tag a scenario's image was originally named by, and no commit is made to this repository
- **THEN** the scenario SHALL continue to resolve the same image content it resolved before the re-push

#### Scenario: Every authored scenario bounds its instance's host name
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every scenario SHALL declare an explicit host name for its instance, and a scenario declaring none SHALL fail those checks — its host name would otherwise be derived from a namespaced instance name and fail to create once a working tree's name grew long enough

#### Scenario: Every authored scenario's instance name carries the namespace
- **WHEN** the pipeline's own configuration checks read every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** every declared instance name SHALL carry the working-tree namespace, and its default SHALL be one that cannot name a container at all rather than one that merely looks wrong; a scenario declaring a bare literal name, or a default that would successfully create a shared instance, SHALL fail those checks

#### Scenario: A fixture naming a kernel-held handle as a literal fails the checks
- **WHEN** the pipeline's own configuration checks read the fixture plays beside every scenario definition this repository authors under `ansible/roles/*/molecule/`
- **THEN** a fixture naming a loop device minor as a literal SHALL fail those checks, and one deriving it from the value the entry point supplies SHALL pass

#### Scenario: The entry point and the fixtures are checked against each other
- **WHEN** the name of the value the entry point supplies is changed on one side alone — renamed in the entry point, or renamed in the fixtures
- **THEN** those checks SHALL fail identifying the mismatch, rather than the fixtures resolving it to an unset value at run time

#### Scenario: The supplied value is derived from the working tree rather than fixed
- **WHEN** those checks read how the entry point produces the value it supplies
- **THEN** it SHALL be found to derive that value from the working tree's own path, and an entry point supplying a constant SHALL fail those checks even though every fixture reading it still resolves to a usable handle

#### Scenario: A fixture claiming a kernel-held handle establishes it is free first
- **WHEN** those checks read a fixture play that associates a loop device
- **THEN** that play SHALL be found to release the handle earlier in the same file, to read what holds it before releasing it, and to refuse on that read, and a play that associates without a release, or that reads what holds the handle without acting on the result, SHALL fail those checks

#### Scenario: Checks over the fixture plays fail rather than passing over an empty set
- **WHEN** those checks find no fixture play beside any authored scenario definition deriving a handle the machine's kernel holds from the value the entry point supplies
- **THEN** they SHALL fail naming the enumeration as the cause, rather than reporting success for a property nothing examined — and a tree in which every such play names its handle by literal instead SHALL therefore fail these checks twice over, once for the literal and once for the empty set

#### Scenario: The workflow reaches the suite through the entry point
- **WHEN** those checks read the workflow that runs the Molecule suite
- **THEN** it SHALL be found to invoke the entry point that supplies the namespace and the derived handles, and a workflow invoking the tool directly SHALL fail those checks
