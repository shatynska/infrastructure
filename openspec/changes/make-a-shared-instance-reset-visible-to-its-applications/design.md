# Design

## Context

See proposal.md for why. What shapes the approach is four things established on the host rather than reasoned about, all measured against staging's live instance on 2026-09-16:

- **An absent role and a wrong password are indistinguishable over the wire.** A bogus role and `commerce-ops` with a wrong password both return `psql: error: connection to server at "postgres" (172.20.0.5), port 5432 failed: FATAL: password authentication failed for user "<name>"`, both at `psql` exit status 2. Whatever the probe does, it cannot reach `absent` through the application's credential.
- **Unreachability is not separable by exit status either.** `could not translate host name` and `Connection refused` also land on status 2. The three outcomes differ only in stderr text.
- **The instance's own state is readable from the host with no database credential at all.** `docker exec platform-postgres-1 sh -c 'psql -U "$POSTGRES_USER" …'` connects over the container's local socket, which the official image trusts, so nothing has to hold, pass or even read the superuser's password. `pg_controldata -D "$PGDATA"` likewise answers from inside the container.
- **The operator account holds `docker` and no `sudo` whatsoever.** *Unprivileged Operator Accounts Support Interactive Host Inspection* (`openspec/specs/iac-host-configuration/spec.md`) makes that omission the requirement rather than an oversight, and `ops_user` writes no `sudoers.d` file of any kind. Anything an operator must do mid-window has to be doable with `docker` group membership alone.

## Goals / Non-Goals

**Goals:**

- One mechanism that answers both halves of the problem — an application's before-delivery check and the operator's window announcement — rather than two that have to agree with each other.
- An answer to "does my database still exist" that does not depend on the application's credential being right, since the case being reported is the one where it cannot be.
- A window declaration an operator can raise and withdraw in the middle of a window, with no pipeline in the loop.

**Non-Goals:**

- **Automating provisioning.** `automate-per-application-database-provisioning` stays owed and untouched. This change makes the loss visible; it does not prevent or repair it.
- **Binding a key to one host.** This was written while `deploy_apps` still lived in `ansible/inventory/group_vars/<environment>.yml`, where an entry authorised its key on every host in the environment; the non-goal was to leave that to the change that owned it. `bound-a-deploy-key-to-one-host-when-an-environment-holds-two-stacks` archived on 2026-09-16, mid-implementation, and moved `deploy_apps` to `host_vars/<server name>.yml`. The probe key follows the deploy key there and inherits the binding rather than the exposure. Nothing in this change decided that layout, which is what the non-goal was for.
- **Holding platform deploys for the window.** `hold-every-platform-deploy-for-the-length-of-a-window` is a separate entry about this repository's own merges and dispatches. The declaration here is read by applications, not by `platform-deploy.yml`.
- **Making any application call the probe.** `Fuperia-IT/commerce-ops` decides that for itself.

## Decisions

### 1. `absent` is resolved from the host, not through the application's credential

The probe runs as root on the host and asks the instance directly, inside the container, whether the application's role and database exist — one fixed query, filtered to the application name the forced command carries. Only if both exist does it go on to attempt the application's own connection from `platform_edge`.

**No superuser credential is involved.** The connection is `docker exec platform-postgres-1 sh -c 'psql -U "$POSTGRES_USER" …'`, over the container's local socket, which the image trusts; `$POSTGRES_USER` is expanded inside the container, where it lives. Nothing reads `POSTGRES_PASSWORD`, nothing passes it, and nothing can disclose it. What the probe needs is `docker exec` — that is, root on the host — and the `sudoers` rule that grants it is fully qualified to one application name, exactly as `app-deploy`'s is.

**Alternatives considered and rejected:**

- *Report the cluster's system identifier and let the application compare.* Verified readable without a credential (`pg_controldata` gave staging `7685799100635226154`). Rejected because it only works for an application that stores the identifier it last saw, so `credential-refused` stays ambiguous for anything that does not — and the application that most needs the answer is the one deploying for the first time after a reset, which has nothing to compare against.
- *A marker file written by the provisioning recipe in `docs/onboard-an-application.md` §3.2.* Self-contained and superuser-free, but it grows the manual workstation paste a second host write, and a re-provisioning that skips it leaves a marker that lies — the failure mode being one where a stale marker reports health. The recipe is a credential-handling block that has been deliberately kept minimal.

### 2. Two scripts, mirroring the deploy path exactly

`deploy-probe <app>` is the SSH-layer half — `deploy`-owned, reads standard input, holds no privilege — and it invokes `sudo /usr/local/bin/app-probe <app>`, which is root-owned and is the half that reaches the runtime. That is `deploy-receive` → `app-deploy` again, and it is deliberate: the two independent layers that pin an application's name (which key connected, which `sudoers` rule matched) are what *Restricted Deploy Account Supports Per-Application Forced-Command Deploys* requires, and a probe that collapsed them into one script would have one.

`deploy` is not in the `docker` group and must not be put there — it reaches the runtime only through a fully-qualified `sudo`. That is why `app-probe` exists at all.

**The handover between the two is standard input and never an argument**, for the same reason the SSH layer's is: `sudo`'s command line is in the host's process listing. `deploy-probe` forwards the object to `app-probe` unchanged, as the same JSON — one format across both hops rather than a second internal encoding for a later reader to discover by reading both scripts.

**The unprivileged half bounds its input; the privileged half validates it.** This was written the other way round and the implementation moved it, for the reason decision 5 gives about the window: `app-probe` can be invoked directly through its own `sudoers` rule, so it must validate whatever it is handed regardless of what `deploy-probe` did, and validating in both would be two implementations of one contract free to drift. The size bound stays in `deploy-probe` as well, because that is the half reading an unauthenticated stranger's pipe, and `app-probe` keeps one of its own for the direct-invocation path. Both call the same parser, installed as a file of its own so they cannot disagree about what the contract accepts.

### 3. The token is resolved by matching stderr, and an unmatched error is a failed probe

Because exit status 2 covers auth failure, name-resolution failure and connection refusal alike, the implementation matches `password authentication failed for user` for `credential-refused` and the connection-level messages for `unreachable`. This is ordinarily an implementation detail; it is stated in the requirement because getting it wrong produces the exact confusion this change exists to end, silently, and because a future `psql` could change the wording — which makes it something to pin a test to, not to leave to a reader.

**Nothing falls through to a nearest token.** `permission denied for database`, a `pg_hba` rejection, and any message emitted under a non-English `lc_messages` match neither pattern, and the probe exits non-zero with a diagnostic rather than guessing. A probe that guessed would turn a wording change into a wrong answer about somebody's database, which is worse than a deploy that stops and says it could not tell.

### 4. Precedence puts `window-open` first and never reaches `absent` from an instance it could not read

`window-open` wins outright. During a window the instance may look perfectly healthy — before step 2 has run, or after step 3 has brought it back but before any database is re-provisioned — and an application that delivered on the strength of that would be delivering into something about to be destroyed, or into an instance that does not yet hold its database.

**`unreachable` comes second, and it covers the root-side read failing as much as the application's connection failing.** This was wrong in the first draft of this design and the plan review caught it: with `absent` evaluated first, an instance that was merely stopped — a crash, a restart, a `docker compose down` — would have been reported as a destroyed database. `absent`'s documented remedy is the recipe in `docs/onboard-an-application.md` §3.2 with `rotate=yes`, so the answer would have invited an operator to re-provision and rotate the credential of a database nothing had happened to, breaking a healthy application. `absent` is an assertion about what the instance holds and is only ever made from a reading that succeeded.

`credential-refused` then comes after both, for the plain reason that a connection that never happened cannot have had its credential refused.

### 5. The declaration is a file at a fixed path, in a directory the `docker` group can write

Ansible creates `/var/lib/platform-maintenance/`, root-owned, group `docker`, mode `0775`; the declaration is the file `shared-postgres-window` inside it. An operator raises it with `touch /var/lib/platform-maintenance/shared-postgres-window` and withdraws it with `rm` on the same path, using the group membership they already hold, with no `sudo` and no pipeline. It sits outside the volume, so it survives the discarding it announces, and outside `/opt/platform`, which is `deploy:deploy` `0750` and which the runbook already records an operator cannot read.

The path is a literal in three places — this role, the role's README and the runbook — so it is fixed here and the tests assert it. `0775` rather than `0770`: the directory is world-readable so that nothing about who may *read* the declaration depends on group membership, while writing it stays with `docker`. **`app-probe` is what evaluates it**, not `deploy-probe`: the privileged half is where every other answer is reached, and putting this one in the unprivileged half would make the window's answer the only one a bug in `deploy-probe` could suppress.

Granting the `docker` group write access adds no capability: `ansible/roles/ops_user/README.md` records that membership as root-equivalent by escalation, so this makes an already-available act convenient rather than newly possible. Saying that plainly is better than routing an operator through an escalation to touch a flag.

**Alternatives considered and rejected:** *a Docker volume as the flag* — no new filesystem object and visible in `docker volume ls` right where step 2 works, but an unused volume is exactly what `docker volume prune` removes, so the declaration would be silently clearable by routine housekeeping. *A row in the instance* — destroyed by the very act it announces.

### 6. The runbook withdraws the declaration at the end of step 4, not after step 5

Step 5 re-provisions each application database and then redeploys that application. Those redeploys go through the probe like any other, so a declaration still standing at step 5 would block the step that ends the window — the mechanism deadlocking on itself. Withdrawing it once the instance is back and the exporter's role is restored leaves the gap between step 4 and each application's own re-provisioning covered by `absent`, which is the correct answer for that gap and the one the incident needed.

### 7. The credential half connects from a throwaway container on `platform_edge`, with the image read from the running one

The first draft left this unstated and the plan review was right that it is three decisions rather than an implementation detail, because each changes what a token means.

**The vantage is a throwaway client container on `platform_edge`**, not a `docker exec` into `platform-postgres-1`. The cheaper form — running `psql` inside the server's own container — would make `unreachable` almost unreachable: from inside the server, a routing failure, a name that does not resolve and a network the application cannot join are all invisible, and the token would collapse to "postgres is up but refusing its own TCP port". `platform_edge` is the network the application actually reaches the instance over, so it is the only vantage from which `unreachable` means what the requirement says it means.

**The image is read from the running container** — `docker inspect platform-postgres-1 --format '{{.Config.Image}}'` — and never written down here. `platform/docker-compose.yml` holds the pin, Dependabot proposes the next one, and a second copy in an Ansible-rendered script would drift silently and be discovered by a probe failing after an upgrade. Reading it from the container also guarantees the client's `psql` is the one that matches the server.

**The password reaches the client over standard input and becomes an environment variable inside the container**, never an argument and never part of the container's configuration. `-e PGPASSWORD=…` would put it in `docker inspect` output, which every `docker`-group account on the host can read; an argument would put it in the host's own process listing, which the requirement's *The password never reaches a command line* scenario forbids outright. So the container reads one line from its standard input and exports it, and the value exists only in that process's environment, which is readable by root alone.

**The table name travels the same channel, and this is not a stylistic parallel.** It is the only other value the client controls, and the first draft of this decision traced three transports for the password and none for it — which the plan review caught. Interpolated into the client container's `sh -c`, a name carrying a shell metacharacter is command execution *inside a container attached to `platform_edge`*, reached before any password has been checked, which is precisely the pivot the requirement's *A leaked probe key cannot be used to pivot into the host's network* scenario forbids the key from buying. So the name is the second line the container reads from standard input, into a shell variable, and `psql` is then invoked as `psql -v tbl="$tbl" -c "select to_regclass(:'tbl')"` — one invocation, in which the SQL string is a fixed literal the name is never concatenated into, and `:'tbl'` is `psql`'s own quoting of the variable's value. **What must never happen is the name being interpolated into a command string**; that it appears in the inner `psql`'s argument vector is not itself the hazard, and the name is not a secret the way the password is.

The hazard the delta states normatively is therefore about execution rather than disclosure: a name carrying a shell metacharacter must not be capable of running anything, at any layer. The password carries the disclosure obligation as well, and keeps it.

**The belt over that is a shape check, and its shape is decided here rather than left to a reader**: an optionally schema-qualified identifier — one identifier, or two separated by a dot. `public.alembic_version` is a legitimate thing for a consumer to send and `to_regclass` resolves it, so a check admitting only an unqualified name would refuse a correct request and stop a deploy for nothing. A name outside that shape **refuses non-zero** rather than answering `empty`: `empty` is an assertion that the database was read and held no such table, and the belt refuses before any reading happens, so answering `empty` there would be a claim about a database nobody looked at. It is a belt and is labelled one — a pattern-based refusal is denylist-shaped and would be the wrong thing to rely on alone — but a refusal is already a defined outcome under decision 3, so it costs nothing.

**The client container takes no fixed `--name`.** Two probes running at once would collide on one, and the collision would surface as an unclassified failure rather than as anything a reader could act on.

The whole connection is bounded in time, the way `app-deploy`'s reclamation step is, so that a probe against a wedged instance ends in `unreachable` rather than holding an SSH session open.

Starting a throwaway container is not an application-lifecycle command and does not cross *Configuration Scope Stops at the Container Runtime* (`openspec/specs/iac-host-configuration/spec.md`): it starts, and reads, nothing that is part of any application's service definition.

### 8. The marker table is named by the client

`alembic_version` is one application's migration tool's bookkeeping and may not be a literal in this repository — the fitted-to-one-consumer trap `automate-per-application-database-provisioning` and this change's own backlog entry both record. The name arrives on stdin and is resolved through `to_regclass`, which returns NULL for a name that resolves to nothing rather than erroring the way a `regclass` cast would — so an unknown name is an ordinary `empty`. It is the one client-supplied string that reaches SQL, as a quoted `to_regclass` argument and nowhere else; the earlier wording here claimed no client string reached SQL at all, which was false and is the claim decision 7 and the risk list now state correctly.

It is **required**, not optional. An omitted name could plausibly mean "just tell me whether I can connect", but that would make `empty` cover two conditions that a consumer cannot tell apart — a database with no marker table, and a consumer that asked no question about one. A missing field is a malformed input object and refuses, per decision 3's rule that a probe with nothing to say says nothing.

### 9. The input is JSON, fixed in the requirement rather than in the implementation

The consumer asked for JSON and has built against it; more to the point, this is a contract between two repositories, and the other one cannot read this one's scripts before depending on them. A line-oriented format would be easier to parse in a shell script, which is the only argument for it, and it is not enough. The object carries `password` and `table`, both required, and may carry `role` and `database`, which must equal the derived names — accepted only so that a consumer sending the fields the original contract named is not refused for being polite, never as a source of either name.

Parsing is `python3`, which Ansible already requires on every managed host, rather than `jq`, which nothing in this repository installs.

**Unknown fields are ignored, and the input is size-bounded.** Ignoring them is the same tolerance already extended to `role` and `database`, and it matters more than it looks: the contract is held by another repository, which may add a field before this one learns of it, and a probe that refused would break that consumer's deploy at the moment it was trying to be careful. The bound is the other half — `deploy-probe` reads an unauthenticated stranger's standard input, and a parser given no cap will buffer whatever it is sent. A few kilobytes is generous for four short fields; anything larger is malformed under decision 3 and refuses.

## Risks / Trade-offs

- **A declaration left raised blocks every application's deploy on that host** → That is the safe direction — a delayed deploy rather than a delivery into a destroyed instance — and it is stated in the requirement so it cannot be read as a defect. Mitigated by making withdrawal part of step 4's own check, where the operator is already confirming the instance came back.
- **A declaration never raised** → This is the incident's own shape, and it is worth saying plainly rather than leaving implied: an operator skipped a prose runbook step on 2026-09-15, and nothing in this change enforces the new prose step any more than it enforced the old one. Raising the declaration is unenforced, and a window run without it announces nothing. What the change still buys in that case is the second half: `absent` reports the loss at the application's next deploy instead of `credential-refused` reporting it as a password problem four and a half hours later. The enforcement gap is real, is named in the runbook task, and is the same gap `hold-every-platform-deploy-for-the-length-of-a-window` carries for this repository's own merges — a mechanism rather than a convention, and not this change's.
- **A raised declaration reaches applications with no database in the instance** → They are told `window-open` and stop delivering for a window that cannot affect them. The justification for host-wide scope — one discarded volume reaches every database in the instance — does not extend to them, so this is a real cost rather than a restatement. It is accepted because the alternative is a per-application declaration an operator raises once per application under time pressure, with the omissions that invites, and because an application with no database in the instance loses a deploy window and nothing else.
- **A new root-invoked script is reachable from an application's key** → Bounded the same way `app-deploy` is: a fully-qualified `sudoers` rule, an application name that can only come from the forced command, and a fixed query for the existence read. **Exactly one client-supplied string reaches SQL** — the table name, as a quoted `to_regclass` argument dereferenced from a `psql` variable, in a database the client has already authenticated to as its own role — and it reaches no argument list at any layer. Saying "no client-supplied string reaches SQL" would be false and was, in the first draft of this file: the value the probe exists to look up is supplied by the client by design, and the guard is where it travels and how it is quoted, not that it does not exist. The capability the script exposes is "does my own role and database exist", which the application is entitled to know.
- **`app-probe` names `platform-postgres-1`, coupling a `deploy_user` script to the platform stack** → Accepted. The probe's subject *is* the shared instance; a probe that took the container name as input would put it back on the client side, which decision 2 exists to prevent. *Configuration Scope Stops at the Container Runtime* is not crossed: this reads, and never starts, stops or updates anything.
- **Molecule's instance runs Docker on the `vfs` storage driver, and a real PostgreSQL fixture there is slow** → The `default` scenario already runs real containers inside the instance for exactly this reason, so the seam exists. Keep the probe's fixture small and its scenarios separate, and remember that `molecule test --all` stops at the first failure, so a slow new scenario sorting early can hide every one after it.
- **A second `authorized_keys` entry per application doubles what a host vars typo can mis-authorise** → The probe key grants strictly less than the deploy key beside it; a key mixed up between the two fields fails closed, since each entry's forced command is what it can run.

## Migration Plan

The probe key is optional per application, so the converge is backward compatible: an application declaring none keeps exactly the entry it has today. Order is the same as any deploy-key change and only works one way round — the infrastructure pull request merges and the converge installs the entry before any application can authenticate with it. Production's converge waits for an approval, which nothing announces.

Rollback is removing the `probe_public_key` field and re-converging: the probe entry and its `sudoers` rule go, the deploy path is untouched throughout, and an application that was calling the probe sees its connection refused rather than a wrong answer.

The window declaration has no rollback to speak of — an unraised declaration is the state every host is in today, and the runbook's steps are prose until this lands.
