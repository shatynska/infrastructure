## ADDED Requirements

### Requirement: Verification Writing to Shared State Is Namespaced per Working Tree
Where a verification mechanism in this repository writes to state that outlives
a single run and is reachable from more than one working tree on the same
machine, that state SHALL be namespaced per working tree, and the namespace
SHALL be derived deterministically from the working tree it belongs to.

Determinism is normative rather than incidental: a later session in the same
working tree SHALL resolve the same namespace, so that state an earlier run left
behind can be found and removed rather than orphaned.

Where the namespace is absent, the mechanism SHALL refuse to run and SHALL
report what is missing. It SHALL fail before producing any result, and SHALL NOT
fall back to state whose sharing could make a run report success — a run that
silently shares such state can report success having verified nothing about the
change under test, since it may equally pass against another session's state as
fail against it, and a verification result that can mean either is not a result.

This prohibition is over state that can carry a result between working trees. It
does not extend to state whose sharing can only cause a run to fail: a refusal
reached noisily is not the defect this requirement exists to prevent, and
demanding that nothing whatever be shared before the refusal would forbid
mechanisms that are in fact safe.

This requirement governs state shared *between working trees on one machine*. It
places no obligation on continuous integration, where each job is an isolated
checkout and the condition cannot arise.

`AGENTS.md` SHALL carry a section binding this requirement to each service it
governs, naming the state, the namespace, and how a session takes one. A stated
rule with nothing bound to it is not enforceable by a reviewer, and this
repository has already run for months in exactly that state.

#### Scenario: Two working trees verify the same subject concurrently
- **WHEN** two working trees on one machine run the same verification subject at the same time
- **THEN** each SHALL write only to state named for its own working tree, and neither run's result SHALL depend on the other's

#### Scenario: A run with no namespace refuses rather than sharing
- **WHEN** a verification run is started without a namespace
- **THEN** it SHALL fail, identifying the missing namespace, and SHALL NOT create or reuse state shared with another working tree from which a result could be produced

#### Scenario: The instance name is resolvable within the limits that govern it
- **WHEN** a namespace of the length this repository's own naming produces is supplied
- **THEN** the run SHALL create its instance successfully, rather than failing on a limit the namespace pushed it past

#### Scenario: A later session reclaims what an earlier one left
- **WHEN** a run in a working tree leaves state behind, and a later session runs in that same working tree
- **THEN** the later session SHALL resolve the same namespace and SHALL be able to remove that state

#### Scenario: The binding is stated, not merely implied
- **WHEN** this repository binds this requirement to a particular service
- **THEN** `AGENTS.md` SHALL state that binding, and the pipeline's own configuration checks SHALL fail where that statement is absent
