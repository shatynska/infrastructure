## ADDED Requirements

### Requirement: Shared-Stack Service Images Are Pinned to an Exact Release
Every service defined in the shared platform Compose stack SHALL declare its container image by an exact release — an immutable content digest, or the tag its publisher assigns to one release and does not repoint at a later one — and SHALL NOT declare it by a tag the publisher continues to repoint as new releases are published.

The stack is deployed by re-running the deploy pipeline against whatever the tag resolves to at that moment, so a repointed tag makes the version actually running a function of when the last deploy happened rather than of what is committed. The pipeline's approver sees the exact diff before approving, and a version change that leaves no diff is a change that reaches production without passing that gate.

Which tags float is a property of the publisher, not of the tag's shape. Publishers here differ: most release `MAJOR.MINOR.PATCH`, so a two-component tag of theirs is a series that floats; PostgreSQL's release version has two components, so `postgres:16` floats while `postgres:16.15` is a release. No rule stated over the shape of a tag alone can therefore decide the question for every image, and this requirement SHALL NOT be restated as one that does.

Because the property cannot be read off a committed file, the obligation SHALL be split. An automated check SHALL enforce a **necessary** condition — one no correctly pinned tag can fail — and SHALL record in its own text that this is all it establishes. Whether a tag that passes it also names a release its publisher leaves in place SHALL be established by the human review every change to the stack definition already passes through. A check that presented its necessary condition as the whole obligation would report a floating tag as pinned, which is worse than not checking.

The necessary condition SHALL be a **floor on specificity, never a ceiling**: a tag naming fewer version components than any publisher uses for a release cannot name a release under any publisher's scheme, and is rejected. A ceiling — rejecting tags at or above some component count — would reject correctly pinned releases, `postgres:16.15` among them. What the floor does not catch is a tag specific enough to be a release under one publisher's scheme but a series under its own; that residue is what the human half of the obligation carries, and SHALL be named rather than left implied.

This mirrors the pinning obligation `iac-cicd-pipeline` already places on the container images the Molecule suite executes inside, and applies for the same reason: a dependency resolved at run time is not pinned by the manifest that names it. It does not adopt that requirement's remedy — a digest is admissible here but not mandated, because a stack image is deployed to one host from a diff a human approves, where a legible version tag carries information a digest does not.

#### Scenario: A service declares a tag that names no specific release
- **WHEN** a service in the shared platform Compose stack declares its image by `latest`, by another tag that names a channel rather than a release, or by a tag naming a version series that its publisher repoints at each new release within that series
- **THEN** that declaration SHALL be rejected, and the service SHALL instead name the exact release it is intended to run, or that release's content digest

#### Scenario: The automated check enforces a floor and says so
- **WHEN** the statically decidable part of this obligation is enforced by an automated check
- **THEN** that check SHALL reject `latest`, any other tag naming a channel rather than a version, and any tag naming **fewer than two** version components — two being the fewest any publisher represented here uses for a release, and therefore a floor no correctly pinned tag can fail
- **AND** it SHALL record that passing establishes only a necessary condition — a tag specific enough to pass may still be a series under its own publisher's scheme, and that residue is carried by human review

#### Scenario: The check does not reject a correctly pinned release
- **WHEN** a service names a release using the number of version components its own publisher uses, such as a two-component PostgreSQL release
- **THEN** the check SHALL accept it, because the condition it enforces is a floor on specificity and never a ceiling

#### Scenario: A version change is visible to the deploy approver
- **WHEN** the version of a shared-stack service changes
- **THEN** that change SHALL appear as a committed diff in the stack definition, so the approver of the gated deploy sees which version they are approving
- **AND** this scenario states why the requirement above matters rather than imposing a new obligation: it is already discharged by `iac-platform-deploy-pipeline`'s "Reviewer Sees the Exact Diff Before Approving" requirement, and needs no separate mechanism

## MODIFIED Requirements

### Requirement: Metrics Dashboards Are Available
The platform stack SHALL provide a dashboard interface over the collected metrics, so host and per-service health can be inspected visually, not only through raw alert notifications. The dashboard interface SHALL be reachable only over the host's private tailnet, not through the platform's public-facing reverse proxy, and SHALL require a non-default credential to access.

Where the dashboard interface generates an absolute URL of its own — a redirect, a link embedded in a notification, or a link shared between operators — that URL SHALL address the host at the same private-tailnet address the interface is published on, not an address that resolves to whatever machine happens to open it.

#### Scenario: An operator views current health
- **WHEN** an operator on the tailnet opens the dashboard interface
- **THEN** they SHALL be able to view host resource usage, per-container health, and per-application HTTP error rates

#### Scenario: The dashboard interface is not reachable from the public internet
- **WHEN** a request for the dashboard interface arrives on the platform's public-facing reverse proxy or any other public interface
- **THEN** it SHALL NOT be served, because the dashboard interface is bound only to the host's private tailnet interface

#### Scenario: The dashboard interface has no default credential
- **WHEN** the monitoring stack is deployed
- **THEN** the dashboard interface's administrative credential SHALL be set from a secret sourced outside the repository, not left at its default value

#### Scenario: A generated link addresses the host, not the viewer's own machine
- **WHEN** the dashboard interface is asked for the absolute base URL it builds its own links and redirects from
- **THEN** that URL SHALL address the host at the private-tailnet address the interface is published on, so that following such a link from any tailnet peer reaches the dashboard rather than that peer's own loopback interface

#### Scenario: The configured base URL is not a literal that ignores where the interface is published
- **WHEN** the shared platform stack's definition is read
- **THEN** the dashboard interface's configured base URL SHALL be derived from the same value that determines the address it is published on, rather than being a literal address — including `localhost` — that is correct only on the host itself
