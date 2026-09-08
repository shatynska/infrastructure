## Context

See the proposal's *Why* for the motivation and for the host facts it rests on. What shapes the approach here is that the change is entirely a matter of what this repository *states*: no service is added, removed or reconfigured, and no host is converged. The design questions are therefore about where each statement belongs and how it is worded so that it survives the next person, not about mechanism.

One constraint is not obvious from the specifications alone. *Shared PostgreSQL Instance Metrics Are Collected* (`openspec/specs/iac-platform-services/spec.md`) refers to the instance "defined in the 'Single Shared PostgreSQL Instance, Per-Application Databases' requirement" — by name. The requirement being narrowed here is that one.

## Goals / Non-Goals

**Goals:**

- State what the shared PostgreSQL instance is for, in a way that makes the absence of a backup of it a decision a reader can find rather than a gap they discover.
- State what becomes owed if durable data ever does land on this host, in wording that outlives the current list of stores.
- Leave the running system untouched.

**Non-Goals:**

- Any backup, dump, retention or restore mechanism. The classification is the deliverable; a mechanism is what the trigger clause demands *later*, if the classification stops holding.
- Defining how an application is given a database inside the shared instance. No application needs one today.
- Migrating commerce-ops off its own PostgreSQL container. That is work in that application's repository.
- Anything about the host's other operational gaps — container log rotation, swap, container resource limits. Those are separate queue entries and are untouched here.

## Decisions

**1. Scope the instance rather than remove it.** With durable data going to Supabase and no application using the shared instance, deleting `platform-postgres` and `postgres-exporter` was the obvious alternative, and on an 8 GB host with no container limits it would give back real memory. The operator decided against it: an instance for non-critical technical or temporary records is worth keeping precisely because the alternative — an application inventing its own container for a task queue — is what produced today's divergence. Keeping it costs one running service and keeps `postgres-exporter` and its alerts meaningful.

**2. The requirement keeps its name.** *Single Shared PostgreSQL Instance, Per-Application Databases* now says something narrower than its title suggests, and renaming it to match would break the by-name reference in *Shared PostgreSQL Instance Metrics Are Collected*. A rename would also make the archived history harder to follow for no behavioural gain. The name stays; the body carries the scoping.

**3. The new requirement goes in `iac-safety-hardening`, not `iac-platform-services`.** Its subject is the host's data durability as a whole — including data an *application* persists, which is outside the platform stack — and it defines itself against *Data Durability for Stateful Resources*, which is already in that capability. Placing it beside the requirement it must not be confused with is what makes the distinction readable.

**4. The obligation is generic; the store list is dated and informative.** Enumerating the five current stores normatively would mean a `MODIFIED` delta every time a service is added, and a stale list would read as permission. Instead the requirement states the properties a store must satisfy — rolling retention, reproduced from this repository, re-issued by an external authority, derived and regenerated in use, or non-durable by a policy recorded as a requirement here — and carries the platform stack's current five stores in a table dated to the day it was read.

The enumeration is closed — a store's reason SHALL be one of the listed properties — which puts the burden on the list being complete rather than on each author inventing a justification. Five properties cover it: rolling retention, reproduced from this repository, re-issued by an external authority, derived and regenerated in use, and non-durable by a recorded policy. The fourth exists because the first draft had only the other four and a plain cache fell through all of them: it is recoverable without a backup by inspection, yet the only escape was the policy reason, which demands a statement about whose loss is tolerable that makes no sense for a store nobody's loss depends on. A requirement that forces an author to misdescribe a store to comply is one that will be ignored instead.

The obligation's scope is bounded to data persisted **outside a container's writable layer**: a named volume or a host bind mount. Unbounded, it would reach the converged filesystem and the container runtime's own state, which nothing in this change classifies and which convergence already reproduces. Bounded this way it is also enumerable — but **not from the stack definition**, and finding that out is what set the scope's wording. `platform/docker-compose.yml` declares two named volumes and two bind mounts under `/mnt/main-data`, and reading only that file yields the conclusion that Alertmanager persists nothing, because it is given no volume there. The host says otherwise: `prom/alertmanager` declares its own `VOLUME /alertmanager`, and the container holds an anonymous volume for it. So the scope reaches any volume, named or anonymous and whoever declared it, and the table was built from `docker volume ls` and each container's mounts rather than from the file. Five platform stores, not four.

**4a. The list ageing is a failure mode, not just an inconvenience, so it gets its own scenario.** The trigger for a *backup* fires when durable data lands. It does not fire when a classified store quietly stops satisfying its stated reason — someone drops Prometheus's retention flags, or deletes the stanza that provisions Grafana's dashboards from the stack definition. No new data arrives, no clause is breached, and the host is now holding unrecoverable data under a specification asserting it holds none. The requirement therefore states that a store is in breach the moment its reason stops being true, and carries a scenario for the change that would do it.

Grafana is why that table row classifies the store in two halves rather than one. `platform/docker-compose.yml` sets `allowUiUpdates: true` and `disableDeletion: false` on the dashboard provider, so a dashboard saved through the UI is permitted, produces no diff, and is invisible to any static check. Classifying the store solely as "provisioned from this repository" would have asserted of the whole directory a property true only of part of it, and made that routine act a breach.

So the UI-created half is not an example of the ageing trigger — it is covered, by a policy stated in the requirement's own body rather than in its dated table. The trigger's examples are the ones that survive the split: a retention flag dropped from Prometheus, or the provisioning stanza itself deleted, which is what would take the reproducible half away. The row therefore covers the provisioned artifacts by redeploy and everything else — Grafana's own database, UI-created dashboards, users, preferences — as non-durable by policy. Changing `allowUiUpdates` would be the other way to close it; that touches the running stack and belongs to a change that can deploy it.

**5. `backups = true` stays, and both requirements are made to say the same thing about it.** Once no store needs a backup, Hetzner's 20% backup surcharge invites removal. It is kept because the daily snapshot buys something the classification does not: a shorter rebuild of a root disk holding the container images, the Docker daemon state and the converged host configuration — and the rebuild runbook has never been rehearsed (`docs/change-queue.md`, the rebuild-runbook entry).

That leaves *Data Durability for Stateful Resources* saying restoring from a backup is the remedy for data loss while the new requirement says those snapshots are not a database's backup. Both readings are defensible in isolation and together they are a contradiction a future operator would have to adjudicate, so the older requirement takes a small `MODIFIED` delta: the normative clause is unchanged, and its rationale now states what the snapshot actually is — daily, crash-consistent, root disk only and not the attached volume, restorable only by rolling the whole server back. Saying it is *not* a database backup, without saying that, would also overstate: PostgreSQL does recover from a crash-consistent copy the way it recovers from a power cut. What it cannot do is restore one database, or reach data on `main-data`.

**6. Per-application provisioning moves from an open README statement to a recorded deferral.** `platform/README.md` currently says the mechanism "is not yet defined", which reads as an oversight. Defining it now would mean designing against no consumer. It goes to `docs/deferred-work.md` with the revisit trigger that matters: the first application that actually wants technical storage in the shared instance. The README then states policy rather than trailing an open question.

**6a. The shared instance is categorical; the rest of the host is conditional.** These two must not be the same rule, and an earlier draft made them the same rule in the permissive direction — durable data allowed anywhere on the host, the shared instance included, provided a backup and rehearsed restore existed. That quietly dissolved the change's own subject: the safety requirement's table cites *Single Shared PostgreSQL Instance, Per-Application Databases* as the reason `postgres_data` needs no backup, and a policy with an exception cannot carry that citation.

So the instance is closed absolutely — no durable data in it, under any circumstances — which keeps the classification's load-bearing row true by construction. The escape lives once, in the safety requirement's own fallback, and reaches the rest of the host: an application that must keep durable data here may, if the logical backup and the rehearsed restore are in place before it lands. One rule per place, and the two do not overlap.

**7. commerce-ops's divergence is named in the requirement, and tracked in the queue.** Under the new wording that application keeps durable data on this host, which the requirement says it should not, so the requirement is unmet on the day it archives. Weakening it to match the host was rejected: a requirement written around a divergence can no longer name it. But silence was the wrong alternative — a queue entry is the only other place the correction would live, and `AGENTS.md` says queue entries are deleted when their change archives, so the specification would be left asserting a false property of the host with nothing to correct it.

So the requirement carries a dated *divergence* paragraph: what it is, why it violates, what resolves it, that the resolution is outside this repository's authority, and that it is not a precedent. The **layout** is borrowed from *Monitoring Services Are Not Reachable From Application Containers* (`openspec/specs/iac-platform-services/spec.md`) — dated, resolution named, explicitly not a precedent — but what it records differs in kind, and conflating the two would be the worse mistake. That precedent carves an exception, after which the system conforms. This paragraph records a **nonconformance**: the requirement is unmet, and says so in those words. A future author must not read it as licence to file a breach as an exception. The queue entry stays as the tracker; the requirement is the record.

Worth noting for whoever takes the migration: roughly 17,000 of that database's rows are `procrastinate_*` queue tables, which are exactly the non-durable class the shared instance is for. The migration is not all-or-nothing.

## Risks / Trade-offs

- **The requirement is not met on the day it archives**, because commerce-ops keeps durable data on the host → Recorded explicitly as a named divergence with a stated resolution and an owner, which is this repository's established treatment for a fact it has no authority to change. Not mitigated by softening the requirement: a requirement written to match a divergence stops being able to name it.
- **The classification depends on a fact outside this repository** — that the Supabase project keeps a plan with backups → The requirement states the dependency in its own text rather than assuming it. Nothing here can verify it, and pretending otherwise would be worse than naming it.
- **A spec-only change is easy to declare untestable, and that would be wrong here** → Two of the five classification reasons are static reads of a committed file — Prometheus's `--storage.tsdb.retention.*` flags and Grafana's provisioned datasource and dashboards, both in `platform/docker-compose.yml` — which is precisely `.github/tests`'s subject, and precisely the properties whose silent removal the scenario in decision 4a exists to catch. The test author is therefore dispatched with all three rows of this project's test table and no verdict from this change about which apply. What genuinely may not be placeable is the policy half; that outcome is the author's to report, not this change's to pre-authorise.
- **"Non-durable" is a judgement, and an application author is the one making it** → The requirement gives the test in the words a reader can apply — data whose loss would not be tolerable — and pairs it with the consequence of getting it wrong: no backup exists, and none is coming.

## Migration Plan

None. The change alters no running service, no host state and no deployed artifact; it reaches production by merging, and merging is the whole of it.

This makes `ship:confirm` unanswerable in the normal way: there is no observation that would show the change working, because nothing observable changed. That is the first waivable class in `AGENTS.md` — no observation can actually be made — and the waiver is the operator's to give, not this change's to assume.

## Open Questions

- Whether `backups = true` remains worth its surcharge once the rebuild runbook has been rehearsed and its duration is known. Deferrable: it changes neither these specs, this approach, nor the task breakdown, and it belongs with the rehearsal rather than here.
