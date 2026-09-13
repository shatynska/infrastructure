# Handoff: provision commerce-ops's database in the shared PostgreSQL instance

Opened on 2026-09-13 by `onboard-commerce-ops-to-staging`, which authorised a `commerce-ops` deploy on the staging host and deliberately did not provision the database that deploy will need. This change is the other half. It has no proposal yet; whoever takes it writes one.

## Why it is its own change rather than a task in that one

Provisioning the first database inside the shared instance is not a quiet operator step. *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) defers automating provisioning and credential delivery **because no application has needed one**, and says automating it SHALL be done when the first application does. Provisioning staging's `commerce-ops` database falsifies that stated premise and brings that SHALL due.

So this change owes a **MODIFIED delta** on that requirement and cannot carry `skip_specs: true` the way the change that opened it does. Its `.openspec.yaml` carries `skip_specs: true` only until its deltas are written — drop that line then, and keep `schema:` and `created:`, because dropping `schema:` fails validation with the same message and reads as though `skip_specs` did not work.

What the delta has to record — and the shape to copy is *No Store on This Host Holds Data Requiring Backup*'s own "One divergence is stated rather than hidden, as of 2026-09-08", which the repository already uses for an obligation that is due and unmet:

- the trigger fired, dated, naming staging's `commerce-ops` as the application that fired it;
- the provisioning itself is discharged by hand, by the recipe below;
- the mechanism and its credential path are owed and not yet built.

**Do not build that mechanism here.** The requirement's own reasoning is that a provisioning mechanism and a credential path designed against a single consumer are guesswork discovered wrong by the first real user rather than by review. One consumer is what exists. Record the obligation, provision by hand, and let the mechanism be its own change with room to design the credential path.

## The decision that is already taken

The operator decided on 2026-09-13, and the reasoning is in `onboard-commerce-ops-to-staging`'s proposal and design: **staging's `commerce-ops` takes a database inside the shared instance and runs no PostgreSQL container of its own.**

What makes that legal is the classification, and it is a constraint rather than an observation: staging holds **rehearsal data whose loss is tolerable to the operator**, who is the only party that writes it. Durable data may not enter the shared instance under any circumstances, whatever else is true — so production's `commerce-ops` database is not to be copied to staging, and a store there that starts holding anything whose loss would not be tolerable puts the host in breach of *No Store on This Host Holds Data Requiring Backup* from that moment.

The alternative — mirroring production, which runs a PostgreSQL container of its own — rehearses more faithfully and was rejected: it would record a second divergence in a specification that names the first one as unmet and not a precedent.

## The recipe, and two defects in it found while reading it

`docs/bootstrap-a-new-host.md` stage 8.3 carries the committed recipe. **It does not work as written**, and this change is the first thing that would run it:

- **`psql -c` sends a multi-statement string as one implicit transaction, and `CREATE DATABASE` cannot run inside a transaction block.** The committed `CREATE ROLE …; CREATE DATABASE …;` in a single `-c` is expected to error. Two `-c` options, or a here-document over stdin, is the fix. Verify this against the running instance rather than taking it from here — it is inference from `psql`'s documented behaviour, not something that was executed.
- **The generated password is passed as a command-line argument**, so it lands in the operator's shell history and in the `psql` process's `/proc` entry, readable by anything on the host that can read it — which includes every `docker`-group operator account, `ops_user`'s own README recording that membership as root-equivalent by escalation. Feed it over stdin instead.

One more thing the recipe does not say and this application needs: **`commerce-ops` carries a hyphen**, so its identifiers need double quotes. Unquoted, `CREATE ROLE commerce-ops` is parsed as a subtraction and is a syntax error — a loud failure rather than a role named something unexpected, but a confusing one.

Correcting stage 8.3 belongs here rather than in a documentation change of its own: this change is what makes its deferral sentence false, and correcting a recipe while leaving it unrunnable would be half the work.

## What it must not undo

- **The classification above is not a formality.** If the staging deploy turns out to bring a PostgreSQL container of its own after all, that is not a detail to accept quietly — it is the host acquiring an unclassified store, and it satisfies none of the reasons *No Store on This Host Holds Data Requiring Backup* lists. Confirm it does not: from a session on the host, after the deploy, `docker ps --filter name=commerce-ops` and `docker volume ls` should show the application's own service containers and **no** PostgreSQL container and no new volume. That observation is this change's, because the change that opened it puts no store on the host at all.
- **Do not resolve it by moving durable data into the shared instance.** That prohibition is unconditional and no backup lifts it; it is what makes that instance classifiable as needing no backup.
- **Every sentence naming `commerce-ops`'s own PostgreSQL now reads ambiguously and should be qualified, not deleted.** All were written when `commerce-ops` was one deployment on one host; once staging has it, a reader cannot tell which host any of them means, and the divergence paragraph carries a deletion condition that then cannot be scoped. Name the production host in each. **Build the list with the grep rather than from a list written here**: `grep -rn 'commerce-ops' --include='*.md' .`, and read every hit that describes where its data lives. An enumeration in this handoff would be the same kind of stale text it is asking you to fix — the one written during review was two of at least five, missing `docs/backlog.md` entries 10 and 20 and `docs/bootstrap-a-new-host.md`'s rebuild appendix, which is exactly how it will go wrong again. The hits in `openspec/specs/` go inside the delta this change already owes; the rest are ordinary prose edits.
- **Do not touch `web_allowed_cidrs` or `hardening_web_allowed_cidrs`.** Both are `[]` on staging deliberately; opening them is `docs/backlog.md` entry 17 and needs a DNS record. Nothing here requires them: the application is reachable from the host itself over loopback, which UFW does not filter.

## Facts you will need

| | |
|---|---|
| staging tailnet IP | `100.85.219.36` |
| operator access | `ssh -i ~/.ssh/shatynska-ops ops-claude@100.85.219.36` — no `staging` alias in `~/.ssh/config` |
| the instance's container | `platform-postgres-1`, the Compose project being `platform` under `/opt/platform` |
| the superuser | `PLATFORM_POSTGRES_USER`, in staging's `main-staging` GitHub Environment secrets |
| how the application reaches it | `postgres:5432` over the external `platform_edge` network |
| where the generated password goes | the `commerce-ops` repository's own Environment secret, the way a deploy key is delivered — never into this repository |
| the deploy key this change releases | staging's `commerce-ops` deploy key is deliberately **not** handed to that repository until this change has landed. `onboard-commerce-ops-to-staging` authorised the deploy and holds the private half back on the workstation for exactly this reason: an application that deploys and finds no database provisioned brings a PostgreSQL container of its own, which is the breach above. Landing this change is what releases it |

## Read before starting

`AGENTS.md`; *Single Shared PostgreSQL Instance, Per-Application Databases* and *No Store on This Host Holds Data Requiring Backup*, both in full; stage 8.3 of `docs/bootstrap-a-new-host.md`; and `onboard-commerce-ops-to-staging`'s proposal and design, whose store section and database decision are where this change's reasoning was worked out.
