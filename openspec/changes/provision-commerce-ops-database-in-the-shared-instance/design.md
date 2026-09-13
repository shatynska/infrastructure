## Context

See proposal.md - Why, and `handoff.md` in this change's directory for why it was opened. What was measured on 2026-09-13, from a session on each host, read-only except where stated:

| | staging | production |
|---|---|---|
| shared instance | `platform-postgres-1`, `postgres:16.15`, healthy | same |
| databases in it | `postgres` | `postgres` |
| roles in it, excluding `pg_*` | `pgexporter`, `platform_admin` | same |
| `datacl` of a database created with defaults | `NULL` — `PUBLIC` holds `CONNECT` and `TEMPORARY` | same |
| `log_statement` / `log_min_error_statement` | `none` / `error` | same |
| `log_min_duration_statement` / `log_min_duration_sample` | `-1` / `-1` | same |
| `shared_preload_libraries` | empty — no `pg_stat_statements` | same |
| `password_encryption` | `scram-sha-256` | same |
| `commerce-ops` containers | none | `commerce-ops-app-1`, `commerce-ops-worker-1`, **`commerce-ops-postgres-1`** (`postgres:16-alpine`) |
| `commerce-ops` volumes | none | **`commerce-ops_commerce_ops_pgdata`** |
| `commerce-ops` repository's Environment for this target | **does not exist** — `gh secret list --env staging` returns 404 | `production`, already holding **`POSTGRES_PASSWORD`** (set 2026-08-21), which the private PostgreSQL uses |

Two behaviours of `psql` were checked on staging with statements that change nothing:

- **Transaction blocks.** `psql -c "SELECT 1; DISCARD ALL"` returns `ERROR: DISCARD ALL cannot run inside a transaction block`; the same two statements piped to `psql` over stdin return `DISCARD ALL` and exit 0. `DISCARD ALL` cannot run in a transaction block, as `CREATE DATABASE` cannot, so the committed recipe's `CREATE ROLE …; CREATE DATABASE …;` in one `-c` fails the same way.
- **Conditionals over stdin.** A script piped to `psql` computing `NOT EXISTS (SELECT FROM pg_roles WHERE rolname = …)` into variables with `\gset` and branching on them with `\if … \else … \endif` took the create branch for an absent role and the alter branch for `pgexporter`, exit 0.

The recipe's workstation-side control flow (decision 5) was run on 2026-09-13 with `gh`, `ssh` and `openssl` stubbed, against six cases, and re-run in full after `rotate` moved into the block: the Environment absent (`gh secret list` fails) stops with nothing set and no `ssh`; the secret name already present without `rotate=yes` refuses with nothing set and no `ssh`; `gh secret set` failing stops before `ssh`; the name absent proceeds; the name present with `rotate=yes` proceeds; and the name present with `rotate=no` in the block, while both `ROTATE=yes` and `rotate=yes` were exported in the calling shell, refuses — a value left set in the shell does not reach the check. In the two that proceed, the here-document reaching `ssh` carried the expanded application name and password and left `\gset`, `\if` and `:create_role` literal.

`platform/docker-compose.yml`'s exporter connects as `pgexporter` to database `postgres` alone (`DATA_SOURCE_NAME`) and sets no database auto-discovery.

## Goals / Non-Goals

**Goals:**
- `commerce-ops` has a database and role in each host's shared instance, reachable by that role alone, each with its own password delivered to that target's Environment in the `commerce-ops` repository.
- The specification says the automation trigger fired and the obligation is unmet, in the shape this repository already uses for a due, unmet obligation.
- The committed recipe runs as written, converges when re-run, and leaks its password nowhere a `docker`-group account can read.
- The classification that makes each database legal is recorded: staging's whole database under a stated rehearsal-data policy, production's under a table-by-table division.

**Non-Goals:**
- Building the provisioning mechanism or the credential path. Owed and recorded, not built.
- The `commerce-ops` repository's cutover, and deleting *No Store on This Host Holds Data Requiring Backup*'s divergence paragraph unless that cutover is observed to have happened (decision 7).
- Touching `web_allowed_cidrs` or `hardening_web_allowed_cidrs`.

## Decisions

### 1. Record the trigger as fired and unmet; do not build the mechanism

The requirement's own reasoning against a mechanism with no consumer applies with little less force to one: a credential path, naming rule and failure mode fitted to `commerce-ops` alone are fitted to one application's Compose file and one repository's secret names — and this change has already found one such fit going wrong, in decision 5's secret name. So the delta records the obligation as due and unmet rather than moving the trigger — moving it would be a second deferral written by the change the first deferral was waiting for — and the mechanism gets its own change, tracked as `automate-per-application-database-provisioning`. The obligation itself is restated in the present tense, so the requirement still says the automation SHALL be done rather than only reporting that it once said so. The divergence form is copied from *No Store on This Host Holds Data Requiring Backup* because it is the form this repository already reads as "unmet, not permitted": dated, naming the application, stating what discharges it, and saying it is not a precedent. That last clause is widened on purpose to cover a second application provisioned by hand before the mechanism exists, which adds to what the mechanism has to cover and discharges nothing.

Alternative rejected: recording the fired trigger only in `docs/backlog.md`. The requirement already says why not — a document is rewritten when the procedure changes, and a backlog entry is deleted when its change is archived.

### 2. State the staging rehearsal-data policy inside the requirement's own definition

*No Store on This Host Holds Data Requiring Backup*'s fifth reason admits "non-durable by a policy recorded as a requirement in this repository's specifications, which states whose loss that policy treats as tolerable". Staging's `commerce-ops` database will hold rows shaped exactly like production's hand-curated ones — `playbook_steps`, `roles`, `products` — and "technical or temporary records whose loss is tolerable to the application that wrote them" does not describe them. What makes them non-durable is that they are rehearsal data the operator writes and can lose, and no requirement says so. Without the policy, staging's database is classified by an argument in an archived design rather than by a policy, which is the thing that reason exists to refuse.

The policy is written into the requirement's **first sentence** as well as its own paragraph. A paragraph alone would leave the definition that limits the instance saying one thing and the paragraph admitting another, and a test derived from the first would forbid what the second permits. It names the operator as the party whose tolerance counts, as the Grafana and alerting-state policies already do; it reaches the application's database in the shared instance and no other store, since this requirement excludes non-relational stores and the policy must not become a way to classify a staging upload directory; and it carries its own breach condition: production data copied in, or anything intolerable to lose.

It lives in *Single Shared PostgreSQL Instance, Per-Application Databases* rather than a new requirement because it scopes what that instance may hold, and a second requirement would split one classification across two names.

*No Store on This Host Holds Data Requiring Backup*'s table row for the shared instance paraphrases the reason as "limits it to technical or temporary records whose loss is tolerable to the application that wrote them". It needs no delta: the row's reason is "non-durable by policy" and it points at this requirement by name, which is where the policy now lives in full; the table is dated 2026-09-08 and says of itself that it "will age" while the obligation does not; and a delta rewriting one dated row would be the restatement that goes stale next.

### 3. Classify production's database table by table, and state the division here

The `procrastinate_*` tables — about 17,000 rows on 2026-09-08 (`docs/backlog.md` `move-commerce-ops-durable-data-to-supabase`) — are non-durable: a job queue is the worked example of technical records whose loss the application tolerates. The hand-curated tables are durable and SHALL NOT be placed in the shared instance: 358 `playbook_steps`, 35 `launch_journal_entries`, 26 `launch_clickup_tasks`, 11 `roles`, 8 `role_holders`, 7 `known_work`, 5 `products`. **Every other table is unclassified** and may not be placed there until a change in this repository classifies it. This paragraph is that statement for `commerce-ops`, which is where *No Store on This Host Holds Data Requiring Backup* says a store added outside this repository is classified ("in the change here that records it").

The delta states the rule and not the table names. Table names are the application's, change in its repository, and would rot in a specification; the rule that an undivided or unnamed table stays out does not.

This change cannot enforce the division — the application's repository decides which connection each table uses — and says so rather than implying otherwise. What it controls is that the record exists before anything writes to the database.

### 4. Name the database and role after the application, and quote them

`commerce-ops`, matching `deploy_apps`, `/opt/commerce-ops` and the image's last segment (stage 8.1). The alternative, `commerce_ops`, needs no quoting but introduces a second spelling of the application's name that nothing else uses, and the next application with a hyphen would face the same choice again. The quoting cost is paid once, inside the recipe: every identifier is written `"<app>"`, and every string comparison against a catalog `'<app>'`. A connection URL carries a hyphen unescaped (`postgresql://commerce-ops:…@postgres:5432/commerce-ops`).

### 5. The corrected recipe

Pasted whole, as it stands, into one shell on the operator's workstation, once per deploy target, after that target's Environment exists in the application's repository (stage 8.4 creates it, so 8.3 says to create it first). Rotation is the same block with `rotate=yes` in its own first assignment line. That value is filled in per paste like every other placeholder, rather than set in the operator's shell, because a variable left set in the shell would outlive the paste and silently turn the name check off for the next one — which, under tasks 6.1 then 6.2, can be production's.

```sh
(
set -eu
app=<app> secret=<SECRET> repo=<org>/<app> env=<environment> host=<operator>@<host> rotate=no
env_names=$(gh secret list --repo "$repo" --env "$env" --json name --jq '.[].name')
repo_names=$(gh secret list --repo "$repo" --json name --jq '.[].name')
org_names=$(gh api --paginate "repos/$repo/actions/organization-secrets" --jq '.secrets[].name')
if printf '%s\n' "$env_names" "$repo_names" "$org_names" | grep -qx "$secret" && [ "$rotate" != yes ]; then
  echo "refusing: $secret is already set in $env, the repository or its organisation; set rotate=yes in this block only to rotate it" >&2; exit 1
fi
pw=$(openssl rand -hex 32)
printf '%s' "$pw" | gh secret set "$secret" --repo "$repo" --env "$env"
ssh "$host" 'docker exec -i platform-postgres-1 sh -c '\''psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'\' <<SQL
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SET log_min_duration_statement = -1;
SET log_min_duration_sample = -1;
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$app') AS create_role,
       NOT EXISTS (SELECT FROM pg_database WHERE datname = '$app') AS create_database \gset
\if :create_role
CREATE ROLE "$app" WITH LOGIN PASSWORD '$pw';
\else
ALTER ROLE "$app" WITH LOGIN PASSWORD '$pw';
\endif
\if :create_database
CREATE DATABASE "$app" OWNER "$app";
\endif
REVOKE CONNECT, TEMPORARY ON DATABASE "$app" FROM PUBLIC;
SQL
)
```

- **A subshell with `set -eu`.** Every step's failure ends the run before the next step, and the password variable dies with the subshell, so there is nothing to `unset`. Measured with stubs, see Context. `set -e` is suspended for anything run as the condition of an `if`, `||` or `&&`, which is why the block is pasted as it stands rather than wrapped.

Each element answers something found:

- **Statements over stdin.** `psql` runs a script read from stdin statement by statement in autocommit, so `CREATE DATABASE` is not inside a transaction block. Measured, see Context.
- **A script that converges.** Every run leaves a role whose password is the one this run just stored, a database owned by it, and the revoke applied, whatever an earlier run left: the branches are chosen from the catalog, measured to work over stdin, and `REVOKE` is idempotent. So a partial run is recovered by running it again, and a run against an existing role **is a rotation**: the application holds the old password until its next deploy renders the new secret, and the recipe says so. The alternative — stopping at `CREATE ROLE` on a re-run — cannot be made correct with the secret set first, because by then the secret has already changed.
- **Secret first, then the host, and what each failure leaves.** The reverse order would leave, on a failed secret step, a role whose password exists only in a variable that is about to disappear. With this order:
  - `gh secret list` fails — the Environment does not exist, or `gh` is not authorised: nothing is set and the host is untouched. This is staging's state today (Context).
  - The name is already present and `rotate` is not `yes`: refused, nothing set, host untouched.
  - `gh secret set` fails: host untouched; the Environment is unchanged or, at worst, holds a value no deploy has rendered yet.
  - The host step fails **on a first provisioning**: the Environment holds a password no role has, which is inert because nothing uses the database yet. Re-run with `rotate=yes`; the script converges.
  - The host step fails **on a rotation**: the Environment is now ahead of the role, and the application's next deploy renders a password the role does not accept. Re-run with `rotate=yes` before that deploy; the script converges the role to the newest secret.
- **A secret name nothing in that Environment already uses.** Production's `commerce-ops` Environment holds `POSTGRES_PASSWORD` for the private PostgreSQL, measured. Setting that name would change what the next production deploy renders for a database that ignores it once initialised — an outage of the durable half, with the overwritten value unrecoverable from GitHub. So the recipe reads the secret names first — the Environment's, the repository's, and those the organisation shares with the repository; names, never values — and **refuses** if the name is in any of them, because an Environment secret overrides a repository or organisation secret of the same name for that environment's jobs, so setting any of the three is an overwrite from the application's side (added at code review, which found the Environment-only check missed the other two). Each listing is its own assignment, because several commands inside one `$(…)` report only the last one's exit status and `set -e` would not see an earlier failure. It refuses unless the operator has set `rotate=yes` to say this run is a rotation of that very secret. A comment advising the check would be read after the overwrite had already happened, since the block runs whole. For `commerce-ops` that name is `SHARED_POSTGRES_PASSWORD`, the same in both Environments because one workflow renders both; which name the application reads is otherwise that repository's to choose.
- **The password never on a command line.** It is generated into a shell variable and expanded into a here-document, which bash hands to `ssh` on stdin; neither the workstation's history (which records `$pw` literally), nor any process's `/proc/<pid>/cmdline` on either machine, carries the value. `gh secret set` reads it from stdin for the same reason. The here-document is unquoted so that `$pw` and `$app` expand; nothing else in it contains `$` or a backtick, and bash leaves `\gset`, `\if` and `:create_role` alone — both measured with the stubbed run.
- **Every setting that writes statement text to the log pinned off for the session.** At the measured `log_min_error_statement = error`, a failing `CREATE ROLE … PASSWORD '…'` writes the whole statement, password included, to the container log, which every `docker`-group account reads with `docker logs`. `log_statement`, `log_min_duration_statement` and `log_min_duration_sample` all write statement text on success when enabled, and all three are off today; they are pinned anyway so a later diagnostic change to the instance does not start logging passwords. All four are superuser-settable per session, and the recipe connects as the superuser. `shared_preload_libraries` is empty, so no `pg_stat_statements` retains the text either.
- **`ON_ERROR_STOP`**, so an error anywhere ends the run with a non-zero exit rather than carrying on past it.
- **`$POSTGRES_USER` read inside the container**, which is the superuser the instance was initialised with — `PLATFORM_POSTGRES_USER` — so the operator does not transcribe it. The single quotes keep the host's shell from expanding it.
- **`REVOKE CONNECT, TEMPORARY … FROM PUBLIC`.** A database created with defaults grants both to `PUBLIC`, measured, so every other role in the instance — `pgexporter` today, the next application tomorrow — could connect. The owner keeps both by ownership. `pgexporter` connects to `postgres` alone and discovers no other database (Context), so the revoke costs monitoring nothing.
- **Hex password.** No character in it needs escaping in a SQL literal, a URL or a `.env` line.

### 6. Who runs it, where, and when

**The operator runs the whole recipe, on each host, in one shell; this session verifies from the host.** The recipe's guarantees rest on one shell holding the password for both `gh secret set` and `psql`, so splitting it between two actors would need a way to pass the password that is itself a leak, and this session's shell state does not persist between calls anyway. Verification needs a session checking the result, not a session having typed the commands. It also needs no authority this session lacks: setting another repository's Environment secrets is outside this repository's authority, and this session's production access is read-only.

**Staging during `build`, production after `build`'s code review.** Staging's run is the recipe's verification, so it precedes review of the diff describing it. Production's run waits until the code review has cleared, so that defects review would catch in the recipe do not reach production first, and happens before the pull request opens, so that what the pull request says — the delta's "provisioned and delivered by hand" on both hosts, the backlog edits — is true when it merges. If review changes the recipe, staging is re-run by the changed recipe before production.

**Why this is not a breach of "a change reaches production by merging and by nothing else".** That rule governs how this repository's content reaches production: nothing deployed from a workstation, no apply outside the pipeline. The recipe deploys no content of this repository. It is the manual operator step *Single Shared PostgreSQL Instance, Per-Application Databases* prescribes until a mechanism exists, and that it is manual is exactly the divergence this change records. It is still held behind review, which is what the rule's ordering protects. The same holds of the sentence beside it, that local credentials for production "are for reading … and not for applying": this session's production access stays read-only throughout, and the write is the operator's, performed as the operator step the requirement prescribes rather than as a session applying anything.

**Staging waits on the `commerce-ops` repository.** The recipe's first step cannot succeed until that repository has a `staging` Environment, which it does not have (Context), and it refuses before changing anything. Until it does, staging's run — and everything ordered after it — is `blocked:commerce-ops-staging-environment`.

### 7. The divergence paragraph in *No Store on This Host Holds Data Requiring Backup*

Production's private PostgreSQL ends in three steps, of which this repository owns the first and the last: provision the shared-instance database (decision 6); the `commerce-ops` repository moves its durable tables to Supabase, points `procrastinate_*` at `postgres:5432` over `platform_edge`, and removes its own PostgreSQL service and volume; and the divergence paragraph is deleted here.

This change does not take the third step on the strength of the first. Before archiving, it checks on production: `docker ps --filter name=commerce-ops` shows no PostgreSQL container **and** `docker volume ls` shows `commerce-ops_commerce_ops_pgdata` gone. If both hold, the change re-enters `plan` to add a delta on `iac-safety-hardening` removing that paragraph and the scenario "The stated divergence is not a precedent", with its own derived tests and review. If either does not, the paragraph stays, and tasks.md records the deletion under `## Not performed` with the Supabase backlog entry named as where the remainder lives. A specification claiming the divergence is closed while the container runs is worse than one admitting it.

**Other prose outside `openspec/specs/`** naming `commerce-ops`'s own PostgreSQL follows the same rule: qualified to the production host now where two hosts make it ambiguous, deleted only once the container is gone. **Hits inside `openspec/specs/`** are not qualified: they are dated 2026-09-08, when one host carried `commerce-ops`, they describe the host running the private container, and the only edit this change could justify to them is the deletion above, which has its own condition and its own delta.

### 8. The rebuild step this change creates

Until now a rebuilt host's shared instance needed no restore and no re-provisioning beyond `pgexporter`. Once an application has a database there, a rebuild loses it — tolerable by classification — and the application cannot start until the database and role exist again. So Appendix B of `docs/bootstrap-a-new-host.md` and `write-and-rehearse-the-rebuild-runbook` gain a step: re-run stage 8.3 per application — a rotation, by decision 5 — before that application's deploy. The same holds after a volume reset under `upgrade-the-shared-postgres-major`, which that entry's "applications told first" already implies; it gets a sentence rather than an inference.

### 9. What verifies which scenario

Most of the delta's scenarios are about host state or policy, and the three test commands in `AGENTS.md` reach little of it. Stated here so neither the test author nor a reviewer assumes coverage that does not exist:

| Scenario | Verified by |
|---|---|
| A new application requests a database — database in the shared instance, own role, no other role can connect | Host checks on each host (tasks 4.1 and 6.2): the database and its owner in `\l`, `datacl` granting nothing to `PUBLIC`, `SELECT has_database_privilege('pgexporter', '<app>', 'CONNECT')` returning `f` — a catalog answer that does not depend on how a local connection authenticates. `pgexporter` stands in for "another application's role", being the only other non-superuser role there is |
| …password generated per host, delivered only to that target, in no file here | Partly static: a read of committed files can assert the recipe keeps the password off command lines and out of the repository, and that no committed file carries one. Per-host independence is a property of two runs and is observed only as two separate runs |
| An application needs durable storage | Unchanged by this delta; existing coverage |
| An application's data divides | Static, for the record's existence: this design's decision 3. Whether the application's tables obey it is not observable from this repository without reading application data, and nothing here does |
| A staging database holds rehearsal data — no production data copied in | Not verifiable by any check this repository has; it is a policy an operator obeys |
| The automation trigger has fired | Static read of the specification text |

The log check does not need the password: `docker logs --since <run start> platform-postgres-1 2>&1 | grep -ciE 'create role|alter role'` expecting `0`, which can run on both hosts.

## Risks / Trade-offs

- [Risk] **A durable table lands in production's shared-instance database**, which silently reclassifies the store and breaches *No Store on This Host Holds Data Requiring Backup*. → This change controls only the record and the credential. The division is stated here and the rule in the requirement, and `move-commerce-ops-durable-data-to-supabase` names which tables go where. Nothing in this repository can observe a table's contents without reading application data, and nothing here tries.
- [Risk] **Production's shared-instance database exists beside the private PostgreSQL** until the cutover, which is more moving parts with no obligation discharged. → Accepted and stated: the database is inert until the application points at it, and the divergence stays recorded as unmet (decision 7).
- [Risk] **Staging's deploy brings a PostgreSQL container anyway** — production's Compose file has one, and Compose starts what the file declares whether or not a database has been provisioned. → Two guards, one before and one after. Before: the staging deploy key is handed over only once the operator has confirmed that what the application's staging deploy renders declares no PostgreSQL service (task 6.4) — the key is the one step this repository still controls, so it carries the precondition. After: `confirm` observes `docker ps --filter name=commerce-ops` and `docker volume ls` on staging. A PostgreSQL container or new volume there is a breach to raise, not a detail.
- [Risk] **A re-run rotates a live password** and the application loses its connection until redeployed. → Stated in the recipe; the re-run is the recovery path and the redeploy is part of it.
- [Risk] **The password in the operator's terminal.** The variable lives in the recipe's subshell for the duration of the recipe. → It is never echoed and dies with the subshell. Stronger isolation is the mechanism's job.
- [Risk] **This change's progress depends on the `commerce-ops` repository twice**: its staging Environment must exist before staging's run (decision 6), and its staging deploy path before `confirm`. → Either missing is reported as `blocked:` naming it, rather than worked around or confirmed by inference.
- [Trade-off] **Host state changed by hand, outside any pipeline.** It is what the requirement prescribes until the mechanism exists, and it is exactly what the divergence paragraph records as unmet.

## Migration Plan

Host steps are additive and reversible: `DROP DATABASE "commerce-ops"; DROP ROLE "commerce-ops";` on the host, plus deleting `SHARED_POSTGRES_PASSWORD` from that target's Environment, returns each instance to its measured state. Reverting the documentation without that leaves an unrecorded database in the instance, so a revert does both.
