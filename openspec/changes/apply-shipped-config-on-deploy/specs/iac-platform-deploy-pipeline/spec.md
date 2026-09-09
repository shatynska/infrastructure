## ADDED Requirements

### Requirement: A Shipped Configuration Change Is Visible to the Container Runtime
The shared platform stack embeds its monitoring, alerting and dashboard
configuration inside the stack definition itself rather than in separate files —
a choice recorded, with its reason, under "Splitting
`platform/docker-compose.yml` into multiple files" in `docs/deferred-work.md` —
and the runtime copies that configuration into each container when the container
is created. A service's embedded configuration therefore changes only when its
container is replaced.

Where the runtime decides whether to replace a container by comparing a digest
of the service definition, and that digest does not cover embedded configuration
content, the stack definition SHALL carry — for each service that mounts
embedded configuration — a property the digest does cover, whose value changes
whenever that service's own embedded configuration changes and does not change
when any other service's does.

Satisfying this by replacing every service on every deploy SHALL NOT be used,
because it would replace stateful services whose configuration did not change.

"Embedded configuration" here means the configuration **as committed**. Where a
value inside it is interpolated at deploy time from outside the repository — a
secret rendered into the deploy environment, say — this requirement does not
reach it: the committed text is unchanged when such a value is rotated, so no
property derived from the committed text can move. Changing a secret that an
embedded configuration interpolates therefore does NOT cause the service to be
replaced, and the running container keeps the previous value until something
else replaces it.

**What this requirement establishes, and what it does not.** It makes a
change to the committed configuration visible to the comparison that decides
replacement, which is what was absent. It does NOT establish that a deploy
reporting success has applied everything it shipped: a container can fail to be
replaced for reasons no property of the definition can express, an interpolated
value can change with no committed text moving, and nothing here compares a
running container against the definition after the deploy. That confirmation is
a strictly wider guarantee, it is not implied by this requirement, and it is not
to be read as discharged by it.

#### Scenario: A configuration-only change reaches the running service
- **WHEN** a deploy ships a change confined to a service's embedded configuration and to the property this requirement obliges, with no change to that service's image or runtime properties
- **THEN** that service's definition SHALL differ from the one its running container carries, so that the runtime replaces the container rather than leaving it in place

#### Scenario: Only the service whose configuration changed is replaced
- **WHEN** a deploy ships a change to one service's embedded configuration
- **THEN** every other service SHALL be left in place, including other services that also mount embedded configuration, because each service's property is a function of its own configuration alone

#### Scenario: A stale marker fails before it reaches a deploy
- **WHEN** embedded configuration is edited and the property this requirement obliges is maintained in the stack definition rather than computed at deploy time, and that property is not updated to match
- **THEN** that discrepancy SHALL fail a check that blocks the pull request, rather than being discovered as a deploy that reports success and changes nothing
