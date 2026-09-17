## ADDED Requirements

### Requirement: The Specification Record Is Verified in Continuous Integration
This repository's own specification record — the capability specifications, the active changes and their deltas, and the task lists of archived changes — SHALL be validated by its authoring tool as part of the required pull request status check, unconditionally.

The record is the only description this pipeline has of what it is for, and it was the one thing the pipeline did not check. A specification that no longer parses, a delta that is malformed, or an archived change whose task list still claims outstanding work are each invisible to every other check here: they are not Terraform, not Ansible, and not continuous-integration configuration, so no existing tier reaches them.

Validation SHALL cover both the active record and the archived one. These are distinct properties reached by distinct invocations, and neither implies the other: the active record can be well-formed while an archived change's task list is incomplete, which is the state this requirement was introduced from.

The check SHALL run on every pull request rather than only on those that change a file under the specification directory. A record is falsified by what merged before it, not by the diff under review; a path filter would report green on precisely the pull request that carries an unrelated stale failure past it. The job enclosing the check SHALL itself be unconditional, and the workflow SHALL NOT reach it through a workflow-level path filter — a step that cannot be skipped inside a job that can is skippable.

The validating tool SHALL be installed from a manifest that pins it to an exact version and is committed to this repository, and SHALL NOT be resolved freshly at run time.

The runtime that executes it SHALL be pinned to an explicit major version, declared in the workflow and in the manifest's `engines`, rather than left to whatever the runner defaults to. This is deliberately weaker than the tool's exact pin, and the difference is stated rather than glossed: an exact patch pin on a language runtime rots into a version that stops receiving security fixes, and the failure it would prevent — a patch release changing what the validator concludes — is not one this tool's behaviour is sensitive to, where the major version is (it requires import attributes, which the runner's own default may not provide). A floating *major* would leave the pin describing nothing; an exact patch would buy precision this check cannot use at a cost it would pay every month. That manifest SHALL be covered by the repository's dependency-update configuration, so that the pin is maintained rather than left to rot — a pinned dependency nothing watches is the failure this repository has recorded against itself four times over.

An archived change whose task list records outstanding work SHALL fail this check.

Work that was not performed SHALL be disclosed in prose rather than marked complete, and the disclosure SHALL state why. Marking it complete would make a completed task mean either that the work was done or that it was not, which is no signal at all. The obligation is over work not performed for **any** reason — declined on judgment, unreachable in the authoring environment, or omitted and no longer recoverable — because an author facing a case the disclosure does not authorize will tick the box or invent a disposition, and both are worse than either honest option.

That disclosure SHALL itself be machine-checked. A prose escape from a gate, guarded only by review, is the *"guaranteed only until someone does not notice"* condition that the requirement *The Continuous-Integration Configuration Is Itself Verified* exists to refuse; an unguarded one would let this check be satisfied by relabelling an inconvenient task rather than by disclosing anything. A disclosed item that states no reason SHALL fail the check exactly as an unticked task does.

So that the reason is checkable without judging prose, a disclosure SHALL take a fixed form: under a `## Not performed` heading, a list item naming the task it replaces, carrying its reason on a following line introduced by a `Reason:` label. The heading is part of the form and not merely conventional — it is what the check scans for, so a disclosure written outside one is a disclosure the check never sees. The label is what makes silence detectable; the check SHALL assert that the label is present and its text non-empty, and SHALL NOT attempt to assess whether the reason is a good one.

A section that presents itself as such a heading SHALL NOT pass by yielding nothing. A heading the check does not recognise, or one under which no disclosure is found, SHALL fail rather than scan an empty set successfully: a disclosure section that discloses nothing is indistinguishable from a section the scanner could not read, and the second is how this check would fail open.

The check therefore reaches silence, not sufficiency, and it does not reach a task deleted outright rather than disclosed. Deletion is governed instead by the repository's own convention that an archived record may be corrected only to say what actually happened. That convention SHALL be stated in the repository-root `AGENTS.md`, and that it is stated there SHALL itself be asserted by the suite — a delegation to a rule nothing checks for is a delegation to nothing, and this is the one blind spot the check above openly concedes. That assertion establishes only that the rule is **stated**, never that it is followed; the deletion case still ends at a reviewer, and this obligation makes the rule they are reviewing against durable rather than replacing them. The assertion SHALL be written so that rephrasing the rule fails it, rather than so that a rephrasing which inverts the rule passes: this rule's wording is precisely what a reviewer relies on, and a change to it is a reviewed event rather than an editorial one.

A check that cannot fail is not a check. Neither the step nor its enclosing job SHALL suppress the validating command's failure. This obligation is stated separately because every other property in this requirement is satisfied by a step that runs unconditionally, installs from the pinned manifest, and then swallows its result: such a step exists, is not skipped, is exactly pinned, and reports green forever. That is the same defect this capability's discovery, destroy-policy gate and secret-scanning requirements each forbid elsewhere, reached by suppression rather than by omission. It SHALL be read at both levels for the same reason the unconditionality obligation above is: a step that cannot suppress its failure inside a job that can is suppressible.

That obligation SHALL be asserted statically rather than established by observing a failure, so that it holds for every later edit of the workflow and not only on the day it was introduced.

**Suppression SHALL be excluded by asserting a closed form rather than by enumerating evasions.** A check written as a list of forbidden constructions is complete only until someone writes a construction nobody listed, and each entry is added after the gap it closes has already been exploited. So the step SHALL take a shape the check can state positively and completely: its script SHALL consist of the validating invocations and nothing else — no shell operator joining them to anything, no redirection or capture of their status, and no shell override — and neither the step nor its enclosing job SHALL declare a continue-on-error setting in any form, including one whose value is an expression. Relocating the invocations into a called workflow or composite action SHALL NOT be used to escape that shape.

That closed form has a cost, which is accepted deliberately: a legitimate future edit to this step's script fails the check until the assertion is updated. For a step whose entire purpose is to be un-bypassable, an edit that must be noticed is the intended behaviour rather than friction to be designed away.

This validation SHALL NOT be performed by the executable suite that verifies the continuous-integration configuration. The requirement *The Continuous-Integration Configuration Is Itself Verified* binds that suite to its runtime's standard library and to dependencies pinned exactly in a repository manifest, and forbids it a network call, a credential, a container runtime or a Terraform binary; running a separately installed binary from inside it would defeat the first constraint whether or not it defeated the second. That suite's obligation here is the one it holds over every other check in this pipeline — to assert statically that the step exists, that it and its enclosing job are unconditional, that it installs from the pinned manifest, that neither the step nor its enclosing job suppresses the validating command's failure and that the step still holds the closed form above, and that every disclosure of unperformed work — in any `tasks.md` under the changes directory, archived or active — carries a `Reason:` label with non-empty text, and that the correction convention above is stated in `AGENTS.md`.

#### Scenario: A malformed specification or delta fails the pull request that introduces it
- **WHEN** a pull request changes the specification record such that it no longer validates
- **THEN** the required status check SHALL fail on that pull request

#### Scenario: An archived change with outstanding tasks fails the pull request that archives it
- **WHEN** a pull request archives a change whose task list still records work as outstanding
- **THEN** the required status check SHALL fail on that pull request rather than reporting success

#### Scenario: Unperformed work disclosed without a reason fails the check
- **WHEN** an archived change discloses work as not performed and carries no `Reason:` label, or carries one whose text is empty
- **THEN** the required status check SHALL fail on that pull request, as it would for an unticked task

#### Scenario: A disclosure section the check cannot read fails rather than passing
- **WHEN** an archived change carries a section that presents itself as disclosing unperformed work, and the check recognises no disclosure within it
- **THEN** the required status check SHALL fail, rather than reporting success over a section it could not read

#### Scenario: The check cannot report success over a failed validation
- **WHEN** the validating command exits non-zero
- **THEN** the step SHALL fail and the required status check SHALL fail with it, and neither the step nor its enclosing job SHALL be configured to continue past it or to discard its exit status

#### Scenario: The validation runs regardless of what a pull request touched
- **WHEN** a pull request changes no file under the specification directory
- **THEN** the required status check SHALL still validate the record and report its result

#### Scenario: The validating tool is not resolved freshly at run time
- **WHEN** the check installs the tool it validates with
- **THEN** it SHALL install the exact version the committed manifest pins, on a runtime whose major version the workflow names explicitly, and SHALL fail rather than proceed where the manifest and its lockfile disagree

#### Scenario: The pin is watched by the dependency-update configuration
- **WHEN** a new version of the validating tool is published
- **THEN** the repository's dependency-update configuration SHALL raise it as a reviewable pull request rather than leaving the pin to be noticed by a person
