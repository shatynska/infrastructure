## Why

`.github/workflows/platform-deploy.yml` is the last workflow in this repository that can reach exactly one host. The Terraform validation, plan, apply and drift workflows read each stack's own `terraform/stacks/<name>/pipeline.yml` and name no stack; `host-converge.yml` does the same over `ansible/inventory/`. The platform deploy names `main-production` as a literal on its deploy job and sends the stack to whatever single host the `PLATFORM_DEPLOY_HOST` secret holds.

Staging is a fully configured host with nothing on it. `configure-the-staging-host` converged it on 2026-09-10; `ansible/inventory/group_vars/staging.yml` already authorises a `platform` deploy key of staging's own, generated out of band and held in the operator's password manager rather than in any GitHub secret, precisely so that this change could put it in one. Everything on staging's side of the deploy is in place and has been for three days. What is missing is a workflow that can be pointed at it.

The cost of that is not only an idle server. Staging's weekly image prune reports failure every week — a host with nothing deployed has an empty keep set, which the prune treats as a refusal rather than as licence to remove everything — and that red check was accepted deliberately, bounded by this change. A recurring red check with a known cause is the kind that gets tuned out. `docs/backlog.md` entry 17, which opens staging on the web, is blocked on this one and cannot start until there is a stack behind the ports it would open.

## What Changes

- **`platform-deploy.yml` becomes a discover/diff/matrix-deploy workflow** in the shape `make-the-pipeline-environment-agnostic` proved and `host-converge.yml` reused: a `discover` job that reads the committed per-stack declarations, a credential-less `diff` job that writes the merge's `platform/**` diff to the run summary, and a `deploy` job per stack that attaches to **that stack's** declared GitHub Environment. No stack, GitHub Environment or Ansible group is named anywhere in the file.

- **`pipeline.yml` gains a fifth field, `deploys_platform`, optional and defaulting to `false`.** A stack receives the shared platform stack only where its own declaration says so. This is the decision the backlog entry left open — reuse the existing per-stack declaration, or grow one for `platform/` — and it is taken in favour of reuse; `design.md` Decision 1 gives the reasoning and what was rejected.

- **The opt-in is checked against the host that would receive the deploy.** A stack declaring `deploys_platform: true` whose target environment's `group_vars` does not enumerate `platform` among `deploy_apps` is refused by `.github/tests`, on the pull request, rather than discovered as a deploy that authenticates with a key the host does not authorise.

- **Both stacks opt in.** `main-production` declares `deploys_platform: true` so the existing deploy path is preserved exactly; `main-staging` declares it so the stack reaches staging for the first time.

- **The nine `PLATFORM_*` secrets stay fixed names and gain a second set of values.** Nothing in the workflow maps a stack to a secret: each deploy row attaches to its stack's Environment, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one. Staging's set is created by the operator in the `main-staging` Environment, and that includes registrations this repository cannot make for it — a second Slack webhook target, a second dead-man's-switch check, an ACME mailbox and a Postgres superuser credential of staging's own.

- **A deploy job refuses before it connects where its stack's secret set is not complete.** An undefined GitHub secret resolves to an empty string rather than to an error, so a stack opted in before its Environment holds its values would reach the tailnet check and the SSH connection with empty arguments, and would render an empty assignment into `.env` for whichever value is missing. The second is the sharper half: an empty value need not fail at all — a service that tolerates one starts, satisfies the deploy's wait for health, and leaves the run green having deployed a stack with no credential on it. A pre-flight step reads the whole set and fails naming the stack, the Environment and each empty name.

- **Deploys are serialised per stack rather than globally, and no stack's deploy waits on another's.** The concurrency group carries the stack's name, the matrix sets `fail-fast: false`, and no `needs:` edge joins two deploy rows — the same decoupling `add-a-staging-environment` established for the Terraform apply, for the same reason: promotion ordering is exercised at the production Environment's approval, not by the workflow.

- **A `workflow_dispatch` trigger naming one stack**, mirroring `host-converge.yml`'s. A rebuilt host needs the stack redeployed to it alone; re-running the last run would redeploy every stack and wake production's approval gate for a host that did not change.

- **`docs/bootstrap-a-new-host.md` stops describing the platform stack as production's alone.** Stage 7 becomes a per-stack stage, §0.3's "staging's key is not stored here" row and the "two hosts, only one of them runs anything" section are rewritten, and Appendix A gains staging's checks.

## Non-Goals

- **Opening staging to the web.** `web_allowed_cidrs = []` and `hardening_web_allowed_cidrs: []` stay as they are, no hostname is registered, and no certificate is issued. That is `docs/backlog.md` entry 17, which this change unblocks and deliberately does not perform: it is a firewall change at two layers plus a manual DNS edit in a zone carrying live mail, and it wants the review that a change of its own gets.

- **Parameterising `platform/docker-compose.yml` per stack.** It names no hostname and no environment today, and both hosts mount their data volume at the same path with the same subdirectories — deliberately, per `ansible/inventory/group_vars/staging.yml`. Every value that differs between the two hosts already arrives through `.env`. Nothing in the Compose file changes.

- **Automating the two manual post-deploy steps on staging.** `pgexporter`'s role and the dead-man's-switch registration are operator steps on production and stay operator steps on staging. Automating them was declined when they were written, for reasons `add-platform-monitoring`'s design.md records; a second host does not change them.

- **Refactoring the discovery shell into one shared artifact.** This is the fifth near-sibling of that body. It reads a field none of the others read and makes a cross-check none of them make, so it falls outside the identity assertion in `.github/tests` exactly as `host-converge.yml`'s does. `docs/backlog.md` already carries the entry that would collapse them; this change adds a fifth copy to its case rather than pre-empting it.

- **Closing the gap between a deploy that reports success and one whose shipped configuration is running.** *A Shipped Configuration Change Is Visible to the Container Runtime* (`openspec/specs/iac-platform-deploy-pipeline/spec.md`) states what it does and does not establish, and a second host neither widens nor narrows it.

## Capabilities

- `iac-platform-deploy-pipeline` — MODIFIED, with one RENAMED requirement. The gate, the diff, the tailnet join, the deploy credential, the rendered secrets and the serialisation are all written over a single production host today; each is rewritten over the stack the deploy row belongs to. Three requirements are added — the per-stack gate that replaces the renamed one, the discovery that makes the workflow stack-agnostic, and the pre-flight refusal on an incomplete secret set — and one is renamed because its name asserts the very thing this change removes.
- `iac-cicd-pipeline` — MODIFIED. *Each Stack Declares Its Own Pipeline Configuration* enumerates the declaration's fields; it gains the fifth, its default, and the obligation that the opt-in agrees with the host's own authorisation.

## Impact

- `.github/workflows/platform-deploy.yml` — restructured.
- `terraform/stacks/main-production/pipeline.yml`, `terraform/stacks/main-staging/pipeline.yml` — one field each.
- `.github/tests/` — the assertion pairing the deploy's gate with a stack's declaration reads one literal Environment today and must read a matrix; the sweep forbidding a workflow to name a stack does not currently reach this workflow and must.
- `platform/README.md`, `docs/bootstrap-a-new-host.md` — both describe a single-host deploy path.
- `ansible/inventory/group_vars/staging.yml` carries a banner saying the file is incomplete and the host not yet converged, which was true when written and is contradicted by the same file's own values. This change cites that file as evidence and leaves the banner alone: it is `docs/backlog.md` entry 18's, `refresh-staging-group-vars-banner`, which is not blocked and touches one file. Named here so the staleness is recorded rather than met.
- Repository settings, by the operator: nine `PLATFORM_*` secrets in the `main-staging` Environment, a Slack webhook and a dead-man's-switch check for staging. Nine is the deploy host, the deploy key, and the seven secret-backed values of the eight `platform/.env.example` documents — the eighth, `GRAFANA_BIND_ADDRESS`, is derived at deploy time and is behind no secret. `docs/backlog.md` entry 16 is consistent with that, saying "the eight `PLATFORM_*` secrets **around**" the deploy host; it is entry 17 that paraphrases the pair as eight.
- The workflow is triggered by `paths: platform/**`, so **merging this change deploys only because it edits `platform/README.md`**. That is a property of this diff rather than of the mechanism, and the `workflow_dispatch` this change adds is what makes it recoverable if the documentation task is split out: dispatch the workflow for the stack rather than waiting for a run that will not start.
- The `main-staging` GitHub Environment requires no reviewer, so merging this change deploys the platform stack to staging without an approval prompt. That is the same property staging's Terraform apply has, and `terraform/stacks/main-staging/pipeline.yml` states the reasoning where it is declared.
