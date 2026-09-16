# Make a shared-instance reset visible to its applications

## Why

Discarding the shared PostgreSQL volume destroys every application role and database in it, and nothing tells the applications. On 2026-09-15 the upgrade window ran, its step 5 did not, and `commerce-ops` on staging learnt of it four and a half hours later as `password authentication failed for user "commerce-ops"` — a message that names a credential and not a reset, in a repository that had changed nothing. This repository found out from `Fuperia-IT/commerce-ops`.

Two gaps produced that, and each survives the other being closed. An application cannot see that the database it is configured for has ceased to exist: PostgreSQL declines to distinguish an absent role from a wrong password, which was confirmed against staging's live instance on 2026-09-16 — a bogus role and `commerce-ops` with a wrong password return byte-identical `FATAL: password authentication failed for user "<name>"` at `psql` exit status 2. And an operator has no way to tell an instance's applications that a destructive window is coming: the runbook's step 1 is a sentence addressed to a human, holding a list read from `\l` that step 2 then discards, and nothing survives the reset that a later deploy could read.

`automate-per-application-database-provisioning` is the durable fix for *recurrence* and is a separate change. This is the half that stays owed even after it lands, because a mechanism that re-provisions on a schedule of its own still leaves a gap between the reset and the re-provisioning.

## What Changes

- **A read-only probe an application calls before it delivers.** A second forced-command key class on the `deploy` account — `deploy-probe <app>`, on a key of its own, since an `authorized_keys` entry carries one `command=` — reading a JSON object on standard input carrying a password and a table name, and answering with exactly one token. It writes nothing, in any database, and cannot deliver or deploy.
- **Six tokens, in precedence order**: `window-open`, `unreachable`, `absent`, `credential-refused`, `empty`, `populated`. `absent` is what the incident lacked — the probe resolves it by a root-side existence read inside `platform-postgres-1`, needing no application credential, so it answers in exactly the case where the credential path yields nothing. It is reached only from a reading of the instance that succeeded: a stopped instance answers `unreachable`, because `absent`'s documented remedy rotates a credential and would break a healthy application whose instance was merely down.
- **A token is distinguishable from a failure without parsing either** — the probe exits zero when and only when it emits one, and an error it cannot classify is a failed probe rather than the nearest-looking token.
- **An operator-declared window.** A host-level declaration an operator raises at the start of a destructive window and withdraws when the instance is back; while it stands, every probe on that host answers `window-open`. This is what turns the runbook's step 1 from prose into an act, and it closes the gap between step 2 and step 4 that no credential check can see into.
- **The application name never arrives as data.** `deploy-probe` derives the role and the database from the argument its forced command carries, exactly as `deploy-receive` does, and refuses a `role` or `database` field on stdin that disagrees with it. Only the password and the marker table name are read from the client.
- **The table is the client's to name.** No application's migration-tool bookkeeping table is a literal in this repository; the name is resolved through an identifier lookup, so an unknown one is an ordinary `empty` rather than an error.
- **`platform/README.md`'s upgrade runbook gains the two acts** — raise the declaration at step 1, withdraw it at the end of step 4, so that step 5's own re-provisioning and redeploys run with the window closed and are covered by `absent` rather than blocked by `window-open`.
- **`docs/onboard-an-application.md` gains the probe key** alongside the deploy key in §2, and the consumer contract in §4.

## Capabilities

### New Capabilities

None. Both halves belong to capabilities this repository already has.

### Modified Capabilities

- `iac-host-configuration`: the `deploy` account gains a second class of forced-command key, with its own script, its own `sudoers` rule and its own read-only obligation; and the host gains the window declaration the probe reads.
- `iac-platform-services`: the shared instance gains an obligation that a destructive window on it is announced to the applications that hold databases in it, and that an application can determine whether its own database still exists.

## Impact

- `ansible/roles/deploy_user` — two new scripts (`deploy-probe`, `app-probe`), a `sudoers.d` rule per application, a `probe_public_key` field on `deploy_apps`, and `/var/lib/platform-maintenance/`, which holds the window declaration.
- `ansible/inventory/group_vars/production.yml` and `staging.yml` — a probe public key per application entry.
- `platform/README.md` — *Upgrading the PostgreSQL major version*, steps 1, 4 and 5.
- `docs/onboard-an-application.md` — §2 (the second keypair) and §4 (what the application does with each token).
- `docs/backlog.md` — entry `make-a-shared-instance-reset-visible-to-its-applications` is deleted when this archives; `automate-per-application-database-provisioning` is untouched and stays owed.
- `Fuperia-IT/commerce-ops`, over which this repository has no authority, is the first consumer. Nothing here can make it call the probe; the infrastructure pull request and a converge land first, as they must for a deploy key.
