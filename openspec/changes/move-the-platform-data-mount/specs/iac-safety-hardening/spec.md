## MODIFIED Requirements

### Requirement: No Store on This Host Holds Data Requiring Backup
Every store in which a platform-stack service or an application deployed to this host persists data outside its container's writable layer — any volume, named or anonymous, including one an image declares rather than the stack definition, or a host bind mount — SHALL be one that needs no backup of its own — either its contents are recoverable without one, or their loss is acceptable under a policy recorded here — unless the logical backup and rehearsed restore described below are in place before its data lands. For a store needing no backup, the reason SHALL be one of the following, or — where a store's contents divide — one of them for each part, with the division stated:

- its contents are bounded by a rolling retention the service enforces on itself;
- its contents are reproduced from this repository by a redeploy;
- its contents are re-issued on demand by an external authority;
- its contents are derived from a source that still exists, and are regenerated in use without a copy being restored — the source SHALL be named where the reason is stated, and SHALL itself either satisfy this requirement or live outside this host under backups of its own;
- its contents are non-durable by a policy recorded as a requirement in this repository's specifications, which states whose loss that policy treats as tolerable.

Host system state outside those stores — the converged filesystem, the container runtime's own state — is not in scope here: it is reproduced by convergence and by redeploy, and is separately covered by *Data Durability for Stateful Resources*.

Where data is placed in such a store and meets none of those reasons, a logical backup of it written outside this host, together with a restore rehearsed on representative data whose result was checked, SHALL be in place **before** that data first lands — not after.

This fallback reaches every store on this host **except** the shared PostgreSQL instance, which admits no durable data at all under *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) — a prohibition no backup lifts, because that instance's classification above depends on it holding unconditionally.

The platform stack's stores as at 2026-09-08, and the reason each satisfies this requirement. One further store, an application's own, does not satisfy it and is named below rather than omitted:

| Store | Reason |
|---|---|
| The shared PostgreSQL instance's data — `postgres_data`, on the host `platform_postgres_data` | Non-durable by policy — *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) limits it to technical or temporary records whose loss is tolerable to the application that wrote them |
| Prometheus's time-series database (`/mnt/main/prometheus`) | Rolling retention it enforces on itself, bounded by both time and size |
| Grafana's data directory (`/mnt/main/grafana`) | Split, and both halves are covered: the datasource and the dashboards this repository provisions are reproduced by a redeploy, and the rest is non-durable under the dashboard-state policy stated below |
| Traefik's ACME storage — `traefik_letsencrypt`, on the host `platform_traefik_letsencrypt` | Certificates are re-issued on demand by the certificate authority |
| Alertmanager's state, in the anonymous volume its image declares at `/alertmanager` | Non-durable under the alerting-state policy stated below. This store is declared by the image rather than by the stack definition, which is why the scope above reaches an anonymous volume and why the table was built from the host rather than from `platform/docker-compose.yml` |

That table is the classification on one date and will age; the obligation above is what does not. A store added later SHALL state which of the reasons above it satisfies, in the artifacts of the change that adds it — or, where the store is added outside this repository, in the change here that records it. That is where the second scenario below finds a reason to test, and it costs no delta to this table. Such a store is in scope whether or not the table names it, and a store already named is in breach the moment its stated reason stops being true — a retention flag removed from Prometheus, the provisioning stanza that reproduces Grafana's dashboards deleted from `platform/docker-compose.yml` — whether or not any new data landed.

**One divergence is stated rather than hidden, as of 2026-09-08.** The `commerce-ops` application keeps durable data in a PostgreSQL container of its own on this host, which is what *Single Shared PostgreSQL Instance, Per-Application Databases* forbids and what this requirement is not satisfied by. Its resolution — that application's durable data moves to an external managed service — is work in that application's own repository, over which this repository has no authority. Until it lands, this host holds data no backup covers, and this requirement SHALL be read as unmet in that one respect rather than as describing the host accurately. This divergence SHALL NOT be read to permit another application to do the same.

Resolving it takes two steps, and no change in this repository would otherwise prompt the second: the migration, in that application's own repository, and the deletion of this paragraph. Until both are done the divergence stands as written.

**Grafana state created outside this repository is non-durable.** Dashboards saved or edited through Grafana's own interface, and the users, preferences and annotations its internal database holds, SHALL be treated as data whose loss is tolerable **to the operator**, who is the only party that creates it, because committing a dashboard to the platform stack's definition is the mechanism by which a dashboard worth keeping is kept. The stack permits such edits — its dashboard provider sets `allowUiUpdates` true and `disableDeletion` false — so this is a standing property of that store rather than a hypothetical, and it is stated here rather than in the table above because the table is dated and this policy is not.

**Alerting state is non-durable.** Alertmanager's silences and its notification log SHALL be treated as data whose loss is tolerable **to the operator**: a lost silence lapses into a notification, which is the safe direction to fail in, and the notification log only suppresses repeats of an alert still firing.

This requirement is distinct from *Data Durability for Stateful Resources* in this capability, which requires the server's own automatic backups. Those are daily, crash-consistent, cover the root disk but not the attached data volume, and are retained on Hetzner's schedule; they shorten a rebuild and are a last-resort recovery of the root disk. They are not a substitute for a logical backup taken and restored per database, and their existence SHALL NOT discharge the obligation above.

Durable application data is expected to live in an external managed service that owns its own backups. That such a service's backups are in fact enabled and retained is a fact outside this repository: this requirement states the dependency, and nothing here verifies it.

#### Scenario: A persistent store is added to the host
- **WHEN** a service that persists data outside its container's writable layer is added to the platform stack, or an existing service begins persisting there — including through a volume a bumped image newly declares — or an application deployed to this host persists data of its own in any volume — named or anonymous, declared by the stack definition or by the image — or in a host bind mount
- **THEN** that store SHALL be recoverable without a backup of it, for one of the reasons above
- **OR** a logical backup written outside this host, and a restore rehearsed on representative data whose result was checked, SHALL be in place before the store first holds data

#### Scenario: A store's stated reason ceases to hold
- **WHEN** a change would remove the property a classified store's reason rests on — the retention settings that bound Prometheus's database, or the provisioning from this repository that reproduces Grafana's dashboards
- **THEN** that change SHALL either preserve the property, or restate the store's reason as another of the reasons above, or put the backup and rehearsed restore above in place before it lands

#### Scenario: An application asks for durable storage on this host
- **WHEN** an application would keep data on this host whose loss would not be tolerable
- **THEN** it SHALL be directed to an external managed service that owns its own backups, unless the backup and the rehearsed restore above are already in place

#### Scenario: The stated divergence is not a precedent
- **WHEN** an application proposes keeping durable data on this host on the grounds that `commerce-ops` already does
- **THEN** that SHALL NOT be treated as permission, because the divergence is recorded as unmet rather than as allowed
