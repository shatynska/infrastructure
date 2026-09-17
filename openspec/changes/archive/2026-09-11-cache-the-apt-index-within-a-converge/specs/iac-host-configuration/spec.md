## ADDED Requirements

### Requirement: A Converge Bounds How Often It Re-Fetches the Package Index
A task in this repository's own roles that installs a package at no pinned version, from a source the same run did not add or change, SHALL declare how stale a package index it is willing to install from, rather than re-fetching the index unconditionally on every such task. The bound SHALL be expressed as a role variable with a default, not as a literal repeated at each task, so that an operator disagreeing with the judgment changes it in one place and so that the sites cannot drift apart.

The scope of that obligation is narrow on purpose. It reaches the **task files of this repository's own roles**. It does not reach pinned external content, which is installed wholesale from a manifest and is not editable here; and it does not reach the fixture plays a role's tests use to prepare an instance, which deliberately declare an unconditional refresh and SHALL keep doing so — their purpose is to leave a freshly created container with an index at all, which is the precondition the external container-runtime role's own installs depend on. The two exclusions it carries are stated below as obligations in their own right, because each names a case where a bound does not merely save less but actively breaks the install.

Re-fetching unconditionally is not a stronger guarantee, only a repeated one: several tasks in a single converge each download the whole index minutes apart, and every one after the first re-establishes what the run already knows. What that costs is ordinarily small and is therefore invisible, which is the problem — it becomes visible only when the upstream archive is slow, and it then multiplies by the number of tasks rather than being paid once.

**An index that has never been fetched SHALL NOT be treated as one inside the bound.** Where a host or container has no record of a successful fetch, the task SHALL fetch. Staleness here is measured from *when the index was last fetched*, not from whether index files are present — an image may ship an empty index directory whose timestamp is its own build date, and it is that age, not the emptiness, that must force the refresh. A bound resolving such a host to "recent enough" is the one way this obligation could break an install that works today, so it resolves to fetching.

**A task installing a pinned version SHALL NOT declare such a bound.** Where an exact version is named, an index older than that version's publication does not resolve to an older candidate; it resolves to nothing, and the install fails. The saving is not worth converting a slow converge into a broken one.

**A task installing from a source the same run added or changed SHALL NOT declare such a bound either**, and this is the sharper of the two. A run that writes a new apt source and then installs from it has an index that is *recent* and *wrong*: recent because an earlier task in the same converge fetched it, wrong because it predates the source that was just added. A bound consults the timestamp, finds it well inside the window, skips the fetch, and the package is reported as having no installation candidate — while every other package on the host installs normally. The failure names the package rather than the cause, and it appears only on the run that adds the source, which is the run least likely to be repeated. The bound's cost is a fetch; its cost here is the converge.

*A converge is not a host's security-update mechanism, and this bound does not weaken one.* This paragraph is framing rather than an obligation — it carries no SHALL and nothing checks it, because what it describes is a fact about what a converge does rather than a constraint on what it may do. What a converge installs is the set of packages the host's roles require, which on an already-configured host is installed already and is therefore unaffected by the age of any index: `state: present` over an installed package consults no candidate. What keeps a *running* host's packages current is unattended upgrades, which this capability assigns elsewhere. The point is stated so it cannot be read backwards: this bound does not make a host less current, because a converge was never what made it current.

#### Scenario: A second install task in the same converge does not re-fetch
- **WHEN** a converge installs one package and then, minutes later in the same run, installs another
- **THEN** the second task SHALL install from the index the first task fetched, rather than fetching the whole index again

#### Scenario: An install on a host with no record of a fetch still fetches
- **WHEN** a task installs a package on a host or container carrying no record of a successful index fetch — including one whose index directory exists but was last written when its image was built
- **THEN** it SHALL fetch the index before installing, that recorded time being older than any bound this repository declares. The obligation rests on the recorded time and not on the absence itself: a host whose record is recent installs from it, so an image built inside the bound is a case to keep out by choosing the pin, not one the bound protects against

#### Scenario: An index older than the bound is refreshed
- **WHEN** a task installs a package and the host's index was last fetched longer ago than the task's declared bound
- **THEN** it SHALL fetch the index before installing

#### Scenario: A pinned-version install declares no bound
- **WHEN** a task installs a package at an exact named version
- **THEN** it SHALL NOT declare a staleness bound, an index predating that version resolving to no candidate rather than to an older one

#### Scenario: An install from a source the same run added declares no bound
- **WHEN** a task installs a package from an apt source that an earlier task in the same run wrote or changed
- **THEN** it SHALL NOT declare a staleness bound — an index fetched earlier in that same run is inside any bound and predates the source, so the package resolves to no candidate while every other install on the host succeeds

#### Scenario: The bound is a variable, not a literal per task
- **WHEN** a task in a role's own task files declares a staleness bound, whether or not that role declares more than one
- **THEN** it SHALL take the bound from a variable of that role carrying a default, so that a role's declared bounds cannot drift apart and an operator changes that role's judgment in one place

#### Scenario: A test fixture play is not held to the bound
- **WHEN** a play that prepares an instance for a role's tests refreshes the index unconditionally
- **THEN** it SHALL NOT be held to this requirement, its purpose being to establish an index where none exists rather than to install economically
