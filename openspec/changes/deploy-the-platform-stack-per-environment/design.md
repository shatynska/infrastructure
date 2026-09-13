## Context

Four workflows in this repository already name no stack. They discover the set they act on by reading `terraform/stacks/*/pipeline.yml`, and each stack's declaration tells them which GitHub Environment to attach to, which repository secret holds its read-only Hetzner token, which Ansible group its converge targets, and whether the destroy-policy gate applies. `host-converge.yml` is the fifth consumer of that mechanism and the most recent; it discovers over `ansible/inventory/` and cross-checks against the stack directories, and its discovery body is a near-sibling of the Terraform one rather than a copy of it.

`platform-deploy.yml` predates all of that. It carries `environment: main-production` as a literal on its deploy job, with a long comment explaining why that literal is dangerous to move — GitHub *creates* an Environment a workflow names, with no protection rules, so a workflow and a stack declaration moving in different commits produces an unreviewed deploy rather than a failure — and `.github/tests` pairs the literal against the production stack's declaration to keep the two from drifting. That pairing is what makes this change's first obligation clear: whatever replaces the literal must keep every Environment the workflow can attach to tied to a stack that declares it, or the guard is lost along with the literal.

The host side is ready and has been since 2026-09-10. Staging is converged, its `deploy` account exists, and its `deploy_apps` list authorises a `platform` key generated out of band under a staging-only keypair whose private half sits in the operator's password manager and in no GitHub secret. `ansible/inventory/group_vars/staging.yml` says in as many words that the private half is being kept for "the change that deploys the platform stack to staging". This is that change.

## Goals / Non-Goals

**Goals.** The workflow names no stack. Every stack that should receive the shared platform stack says so in a committed file. Each deploy row attaches to its own stack's GitHub Environment, so whether it pauses for a reviewer is that Environment's property and not the workflow's. Production's existing path is preserved byte-for-byte in behaviour. Staging receives the stack.

**Non-Goals.** Opening staging on the web, parameterising the Compose file, automating the two manual post-deploy steps, and collapsing the five discovery bodies into one. The proposal states each with its reason.

## Decisions

### Decision 1 — the opt-in is a fifth field on `terraform/stacks/<name>/pipeline.yml`, not a declaration of `platform/`'s own

The backlog entry names this as the first decision this change makes, and the alternatives were a file per stack under `platform/`, a single manifest inside `platform/` listing the stacks that receive it, and reuse of the existing declaration.

**A manifest inside `platform/` was rejected first**, and it is the option that looks most natural because the fact being declared is a property of `platform/`. It is a central list of stacks, which is the exact shape *Each Stack Declares Its Own Pipeline Configuration* (`openspec/specs/iac-cicd-pipeline/spec.md`) exists to prevent — it only moves the enumeration from `.github/workflows/` to `platform/`, where the same defect has the same consequence and a weaker guard, since nothing in this repository sweeps `platform/` for stack names.

**A file per stack under `platform/` was rejected second.** It keeps the per-stack shape but splits a stack's pipeline configuration across two trees, so adding a stack stops being "add a directory" and becomes "add a directory and remember the other place". The declaration's own comment — "everything they need about this stack is below" — is a promise this would break.

**Reuse was chosen**, and the field is `deploys_platform`. The declaration is already the one file a workflow reads to learn what to do about a stack, the discovery body that reads it is already written five times over, and the field's polarity lives in its name in the way `destroy_policy_gate`'s does: the value states whether the thing named happens. `deploys_platform: false` and a hypothetical `platform_excluded: false` are the same value with opposite meanings, and nothing in a value tells a reader which was meant.

The cost is that `pipeline.yml` now carries a field about a layer that is not Terraform. That cost was already paid by `target_environment`, which is an Ansible group in a file beside a `terraform.tfvars`; the file is the stack's pipeline configuration rather than its Terraform configuration, and `.yml` rather than `.tf` precisely so Terraform never reads it.

### Decision 2 — an explicit opt-in, rather than deriving the set from the hosts that authorise `platform`

There is a fact in the repository that looks like it already answers this question: `deploy_apps` in `ansible/inventory/group_vars/<environment>.yml` enumerates the applications a host authorises a deploy key for, and `platform` is one of them on both hosts. Deriving the deploy set from it would add no field and could not disagree with itself.

It was rejected because the two facts are genuinely different and today's staging is the proof. Staging has authorised `platform` since 2026-09-10 and must not have been receiving deploys since 2026-09-10 — it had no secrets, no ACME mailbox, no dead-man's-switch check and no Slack target. "This host will accept the platform deploy key" and "the platform pipeline deploys to this stack" were true at different times, three days apart, and the second is the one this change flips. A derivation would have made them one fact and would have had staging deploying from the moment its key was committed, which is the state `add-a-staging-environment` deliberately avoided in the analogous case of opening ports in front of a host with nothing behind them.

The second reason is mechanical: `group_vars` is vault-tagged YAML, and the discovery bodies in this repository read fields with `sed` rather than a YAML parser. Reading a list of mappings out of a file carrying `!vault` blocks with `sed` is the kind of parse that works until it does not.

### Decision 3 — absent means `false`, and an empty discovery result still fails

`destroy_policy_gate` defaults to *applying* when absent, so that a mistake in the file fails safe. The safe direction here is the opposite value and the same principle: a stack directory added without a `deploys_platform` line does not receive the shared platform stack. A new stack has no `PLATFORM_*` secrets when its directory is first committed, and a default of `true` would have its first merge touching `platform/**` attempt a deploy under credentials that do not exist — against a host that may not yet authorise the key, over a tailnet the host may not yet have joined.

That default is an opt-*out* by omission, which is the shape *Each Stack Declares Its Own Pipeline Configuration* warns about elsewhere: "a skipped stack is one that is planned by nothing, applied by nothing and drift-checked by nothing". The distinction is that a stack this workflow skips is still planned, applied, drift-checked and converged by the other four — it is not invisible, it simply runs no application stack, which is a legitimate state and is exactly what staging has been in for three days. What stays unacceptable is *every* stack being skipped: discovery fails when no stack opts in, with the same message shape the sibling workflows use, because a platform stack deployed to nowhere is a pipeline reporting green over nothing.

### Decision 4 — the opt-in is checked against the host's own authorisation, and the check lives in `.github/tests`

A stack can declare `deploys_platform: true` while its target environment's `group_vars` does not enumerate `platform` in `deploy_apps`. The deploy would then authenticate with a key the host has never been told to accept, and would fail at the SSH step — after the tailnet join, after the Environment gate, and on production after a human approved it. That is late, and the cause is two committed files disagreeing, which is the class this repository checks statically.

The check reads two committed files and asserts a one-directional implication: `deploys_platform: true` requires `platform` in that stack's `target_environment` group's `deploy_apps`. The converse is deliberately not required — a host may authorise the key before the pipeline is pointed at it, which is Decision 2's entire argument.

It lives in `.github/tests` rather than in the workflow's discovery for two reasons. It fails the pull request rather than the deploy, which is earlier by one merge. And `deploy_apps` is a list of mappings, which a line reader is the wrong tool for — the suite reads `group_vars` by lines today, and `test_the_platform_data_mount_moved.py` records at that read why it does: `yaml.safe_load` refuses the `!vault` tags these files carry.

**The loader to copy already exists, and copying it means copying its refusal.** `_AnsibleTolerantLoader` in `ansible/scripts/select_molecule_roles.py` is a `SafeLoader` subclass registering `!vault` and `!unsafe` **by name**, and its docstring states the rule: never a catch-all, because a multi-constructor over `!` maps every unknown tag to `None`, which turns a document the reader has never seen into an empty one rather than into a refusal. `.github/tests/test_the_derivation_follows_or_refuses_every_route.py` asserts exactly that, having found the catch-all shipped once. A catch-all here would be worse than there: `deploy_apps` read out of a `None` document is an absent list, so the cross-check this decision exists for would pass vacuously on the very pair it compares — fail-open on the one guard this change adds.

What is genuinely absent is a loader `.github/tests` can reach: that one lives under `ansible/scripts/` and no module in the suite imports it today. So the check's author either imports it or writes the same explicitly-tagged shape beside the assertion, and either way an unknown tag refuses rather than constructs. That is a small cost, it lands on whoever writes the check, and it is named here so it is not met as a surprise.

### Decision 5 — the nine `PLATFORM_*` secrets keep their names; nothing maps a stack to a secret

Each deploy row declares `environment: ${{ matrix.stack.github_environment }}`, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. So `secrets.PLATFORM_DEPLOY_HOST` read from the row attached to `main-staging` is staging's, with no expression naming staging anywhere. This is the property that lets the workflow satisfy "SHALL NOT ... map a stack to its secrets ... in workflow text" without any per-stack indirection at all, and it is why the declaration gains an opt-in flag rather than a list of secret names.

It also means the failure mode of a missing secret is an empty string rather than an error, and the refusal has to cover the **whole** set rather than the host alone. `tailscale ping ""` and `ssh deploy@` fail in ways that do not name the cause, which is the obvious half. The dangerous half is quieter: `platform/docker-compose.yml` interpolates every value as `${VAR}` with no `:?` error form, so an absent secret renders an empty assignment into `.env` and the stack may come up *healthy*. An empty `GRAFANA_ADMIN_PASSWORD` is the sharpest case — Grafana starts, the deploy's `--wait` is satisfied, the run is green, and *Metrics Dashboards Are Available* (`openspec/specs/iac-platform-services/spec.md`), which obliges a non-default credential, is violated by a deploy that reported success.

So the deploy job's first step reads every value its `.env` render will consume, plus the host, and fails naming the stack, the Environment and each empty name — before the tailnet join and before anything is written. This mirrors `host-converge.yml`'s refusal on an empty read-only credential and widens it, because that job reads one credential and this one reads nine.

### Decision 6 — per-stack serialisation, and no stack's deploy waits on another's

The workflow-level `concurrency: platform-deploy` group cannot survive this change for a mechanical reason — a workflow-level declaration cannot read a matrix — and should not survive it for a substantive one: two stacks' deploys have no shared state to contend for. The group moves onto the deploy job as `platform-deploy-<stack>`, which keeps *Serialized Deploys* true where it is about something real (two merges racing over one host's `/opt/platform`) and drops it where it is not.

Ordering is the sharper half. *Stack and Module Folder Structure* (`openspec/specs/iac-repo-foundations/spec.md`) already settles the same question for Terraform: promotion ordering is not a property of the apply workflow, a merge affecting several stacks applies each independently under its own Environment's protection rules, and no stack's apply is made to depend on another's. Three mechanisms would reintroduce it here without any `needs:` edge to read — `fail-fast` at its default cancels every sibling row when one fails, `max-parallel: 1` sequences the rows in an order nobody chose, and a `needs:` between deploy rows states it outright. None is used, and the reason is the one that requirement gives: ordering is exercised at the production Environment's approval, by a human who can decline until staging has been seen to work, rather than by a workflow that would also withhold a correct change from production because staging broke.

### Decision 7 — one `diff` job, not one per stack

The diff a reviewer reads is the `platform/**` diff this merge carries, and it is the same content for every stack — the Compose file is unparameterised and every per-stack value arrives through `.env`, which is never committed and therefore never in the diff. One credential-less job writes it once, before the matrix. *Reviewer Sees the Exact Diff Before Approving* is satisfied for each stack's approver by the same summary, which is what the requirement asks for: the approver sees the exact content about to be deployed at the moment they are asked to approve it.

### Decision 8 — a `workflow_dispatch` naming one stack

`docs/bootstrap-a-new-host.md`'s rebuild sequence says to redeploy the platform stack "by re-running the last Platform Deploy from Actions". With a matrix that redeploys every stack, and on production it wakes an approval gate for a host that did not change. The dispatch input mirrors `host-converge.yml`'s exactly, including its refusal: a name discovery did not find fails the run and reports what it did find, rather than producing an empty matrix and a green run.

This does not open a second path to production. The dispatch deploys the committed content at the ref it runs on, under the same Environment gate; it re-applies what merging already delivered, which is what the rebuild sequence needs. Nothing here lets a deploy carry content that has not merged.

### Decision 9 — staging's alerts are separated by their Slack target, not by a label on the alert

Nothing in `platform/docker-compose.yml` labels an alert with the host or stack it came from: Prometheus declares no `external_labels`, so a `MetricsTargetDown` from staging and one from production are identical text. Pointing both stacks' `PLATFORM_SLACK_WEBHOOK_URL` at one channel would therefore produce alerts nobody can attribute.

The fix chosen is the one that needs no change to the stack: staging's webhook points at a channel of its own, which the per-Environment secret already allows. That is a repository setting and an operator instruction, recorded in `docs/bootstrap-a-new-host.md`.

It is not a complete fix and is not presented as one, because nothing enforces it — an operator who pastes production's webhook into staging's Environment gets unattributable alerts and no check reports it. Labelling each stack's alerts at the source is a change to the Compose file, a new `.env` variable and a checksum regeneration, which this change's Non-Goals exclude. It is recorded as a backlog entry rather than folded in.

### Decision 10 — staging's secret set exists before this merges, not after

Merging this change is what points the pipeline at staging, and `main-staging` requires no reviewer, so the staging deploy row starts as soon as the merge lands. If any of its secrets is absent, that row fails at Decision 5's refusal step — loudly and harmlessly, but red, and that is true of a partially entered set as much as of an absent one, which is why the refusal reads the whole set. The nine secrets are therefore operator work that completes *before* the pull request merges, and the task list orders them that way rather than leaving them to be discovered by a red run.

**One thing has to start that run, and it is not the opt-in.** `platform-deploy.yml` triggers on `paths: platform/**`, and the opt-in lives in `terraform/stacks/*/pipeline.yml`. This change's merge fires the workflow only because it also edits `platform/README.md`. That is a property of this diff, not of the mechanism: a change that opted a stack in and touched nothing under `platform/` would merge and deploy nothing until the next platform change. Decision 8's dispatch is the recovery, and the task list says to use it rather than wait.

The two manual steps that follow a first deploy — `pgexporter`'s Postgres role and the dead-man's-switch registration — necessarily come after, because one needs a running Postgres container and the other needs a check to exist. Between the deploy and those steps, staging's `MetricsTargetDown` fires for `postgres-exporter`. That is the documented behaviour of that alert and is the same interval production passed through.

## Risks / Trade-offs

**The literal that `.github/tests` pairs against a stack's declaration disappears.** Today the assertion reads one Environment name out of the workflow and requires exactly one stack to declare it; after this change the workflow declares an expression. The guard cannot simply be deleted — it is what stops a deploy being gated on an Environment no stack declares, which GitHub creates unprotected rather than refusing. It is replaced by the assertion that the gate is resolved per matrix row from discovery, plus the existing census that no two stacks declare one GitHub Environment. This is the same substitution `make-the-pipeline-environment-agnostic` made for the Terraform apply, and the same pair of assertions covers it.

**Staging runs a public-facing reverse proxy behind a firewall that opens no port.** Traefik binds 80 and 443 on the host; UFW and the cloud firewall both refuse inbound traffic to them. No certificate is requested, because ACME is driven by router rules and staging has no application and therefore no router with a hostname. So the state is inert rather than broken, and it is the state entry 17 ends.

**Five discovery bodies now exist where the decision to keep three was taken.** Stated rather than resolved; the backlog entry that would collapse them is the place for it, and this change makes its case one copy stronger.

**A `false` default means a stack can be added and silently receive no application stack.** That is the intended state for a stack that runs nothing, and it is visible: the run summary lists which stacks discovery included and which it excluded, so a stack omitted by a forgotten field shows up in the log of every platform deploy rather than only in its own absence.

## Migration Plan

The order is: secrets first, merge second, manual steps third.

1. The operator creates the nine `PLATFORM_*` secrets in the `main-staging` Environment, including a Slack webhook pointing at staging's own channel and a dead-man's-switch check of staging's own. Nothing in the repository changes.
2. The pull request merges, and Decision 10's second paragraph is what makes that start a run at all — the trigger is `paths: platform/**`, which this diff matches only through its documentation work. Production's deploy row waits for approval and, once approved, deploys the same content to the same host it deploys to today. Staging's row runs unapproved and deploys the stack to staging for the first time.
3. The operator runs the two manual steps against staging: `pgexporter`'s role in the shared Postgres instance, and confirming the dead-man's-switch check is receiving Watchdog pings.

**Rollback** is `deploys_platform: false` on staging's declaration, merged. That stops the pipeline deploying to staging and leaves what is already running there untouched; tearing the stack down on the host is a separate operator act and is not what this field does. Production's row is unaffected by any rollback of staging's, which is Decision 6 working.

## Open Questions

None. The one the backlog entry left open — which file declares the opt-in — is Decision 1.
