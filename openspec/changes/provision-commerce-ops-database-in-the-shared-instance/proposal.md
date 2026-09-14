## Why

`commerce-ops` is about to become the shared PostgreSQL instance's first tenant, on both hosts. The operator decided on 2026-09-13 that staging's `commerce-ops` takes a database in staging's shared instance and runs no PostgreSQL container of its own, and that production's `commerce-ops` takes one in production's shared instance as the second destination of a split: its durable business data goes to Supabase, and its technical tables — the `procrastinate_*` job queue — stay on the host, where the shared instance is their proper place. Both instances hold nothing but `postgres` today, measured on each host on 2026-09-13. **Superseded for production on 2026-09-14, after this change merged:** the operator moved production's whole `commerce-ops` database, queue included, to Supabase, so the database this change provisioned in production's shared instance is unused and owed removal; staging is unchanged. See design.md decision 3.

That falsifies the stated premise of *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) — provisioning is not automated "because no application has needed one" — and brings its SHALL due: automating provisioning and credential delivery "SHALL be done when the first application needs technical storage in this instance". It also puts the committed manual recipe, `docs/bootstrap-a-new-host.md` stage 8.3, into use for the first time, and that recipe does not work as written: run on staging on 2026-09-13, a single `psql -c` carrying two statements where the second cannot run in a transaction block fails with `cannot run inside a transaction block`, while the same statements over stdin succeed.

The handoff that opened this change scoped it to staging. The operator widened it to both hosts on 2026-09-13; this proposal is written to that scope, and the handoff is kept as the record of why the change was opened.

## What Changes

- **A MODIFIED delta on *Single Shared PostgreSQL Instance, Per-Application Databases***, recording that the trigger fired — dated, naming `commerce-ops` as the application that fired it — that provisioning is discharged by hand, and that the mechanism and its credential path are owed and not built. The shape copies *No Store on This Host Holds Data Requiring Backup*'s "One divergence is stated rather than hidden". The same delta records two things the provisioning rests on and no requirement yet states: that each application's database is reachable by that application's role alone, and that a staging host's application data is rehearsal data whose loss is tolerable to the operator — which is the policy the whole of staging's `commerce-ops` database is classified under, and which forbids copying production data there.
- **Stage 8.3 of `docs/bootstrap-a-new-host.md` corrected into a recipe that runs**: statements over stdin rather than one `-c`; identifiers double-quoted, because `commerce-ops` carries a hyphen; the password generated on the workstation and never placed on any command line, in any history, or in the instance's log; `CONNECT` and `TEMPORARY` revoked from `PUBLIC`; a script that converges on re-run, so the role's password always matches the secret the run just set; one role and one independently generated password per host, delivered to that target's own Environment in the application's repository **under a secret name nothing in that Environment, the repository or its organisation already uses** — production's `commerce-ops` Environment already holds `POSTGRES_PASSWORD`, for the private PostgreSQL that still runs. Its deferral sentence is replaced by what is now true, and its closing `commerce-ops` paragraph is qualified to the production host and kept.
- **`commerce-ops`'s database and role provisioned by hand in both shared instances** by the corrected recipe, each run whole by the operator in one shell and verified by this session from the host: staging's during `build`, which is the recipe's verification, and production's only after `build`'s code review has cleared and before the pull request opens.
- **`docs/backlog.md`**: a new entry for the owed mechanism; `move-commerce-ops-durable-data-to-supabase` updated with what now exists on production for its cutover to point at; `expose-staging-on-the-web`'s dependency on this change marked satisfied; `write-and-rehearse-the-rebuild-runbook`, `upgrade-the-shared-postgres-major` and Appendix B of the bootstrap document given the step a rebuild now needs — re-provisioning each application's database, whose loss is tolerable but whose absence stops the application.
- **Every other sentence describing where `commerce-ops`'s data lives**, found by `grep -rn 'commerce-ops' --include='*.md' .`, read and corrected where this change makes it false or ambiguous.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-services`: *Single Shared PostgreSQL Instance, Per-Application Databases* — the automation trigger recorded as fired and unmet; per-application isolation and per-host credentials stated; the staging rehearsal-data policy stated.

`iac-safety-hardening` is **not** modified. *No Store on This Host Holds Data Requiring Backup*'s divergence paragraph describes production's private PostgreSQL, which still runs — `commerce-ops-postgres-1` and the volume `commerce-ops_commerce_ops_pgdata` were both present on 2026-09-13 — and its table already classifies the shared instance's data as non-durable by policy. That paragraph and the scenario "The stated divergence is not a precedent" are dated 2026-09-08, when one host carried `commerce-ops`, and describe the host that runs the private container; they are not qualified here, because the only edit to them that this change could justify is their deletion, and that has its own condition. See design.md decision 7 for when that deletion would enter this change and what happens if it does not.

## Impact

- `openspec/specs/iac-platform-services/spec.md`, through the delta.
- `docs/bootstrap-a-new-host.md`: stage 8.3, stage 8.4's secrets table, Appendix B, and any further hit the sweep finds.
- `docs/backlog.md`: one new entry and edits to `move-commerce-ops-durable-data-to-supabase`, `expose-staging-on-the-web`, `write-and-rehearse-the-rebuild-runbook` and `upgrade-the-shared-postgres-major`.
- `.github/tests/`: whatever the derived tests add.
- **Host state outside any pipeline**: one role and one database in each host's shared instance. No Terraform, Ansible, Compose or workflow change; no converge and no platform deploy is triggered.
- **The `commerce-ops` repository**: one Environment secret per target, set by the operator, under one new name used in both Environments. Staging's Environment does not exist yet (`gh secret list --env staging` returned 404 on 2026-09-13), so staging's provisioning waits on that repository creating it. That repository's cutover — pointing its queue at `postgres:5432`, its durable tables at Supabase, and removing its own PostgreSQL service — is not this change's.
- **Releases staging's `commerce-ops` deploy key**, held back by `onboard-commerce-ops-to-staging` until this change lands.

## Out of scope

- **The provisioning mechanism and its credential path.** Owed, recorded, and left to a change of its own with room to design against more than one consumer.
- **Moving `commerce-ops`'s durable data to Supabase and removing its production PostgreSQL**, which is work in that application's repository (`docs/backlog.md` `move-commerce-ops-durable-data-to-supabase`).
- **Staging's web ports and DNS** — `web_allowed_cidrs` and `hardening_web_allowed_cidrs` stay `[]` (`docs/backlog.md` `expose-staging-on-the-web`).
