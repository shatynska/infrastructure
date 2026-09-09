## Context

See proposal.md — Why. Three constraints already in `iac-cicd-pipeline` shape every
decision below, and none of them is being relaxed:

- **No plan job may declare an `environment:`.** It would both pause on protection
  rules and resolve `HCLOUD_TOKEN` to the write-capable token in an ungated job. This
  is what makes per-environment read-only credentials awkward: a plan job can reach
  repository secrets only, and a repository secret holds one value.
- **A matrix-generated job name may not be a registered required status check.** A
  literal-named job must depend on it and conclude on its behalf. `ansible-verify.yml`
  implements that shape and decision 3 follows it.
- **The registered `validate` job runs gitleaks before `terraform plan`, as a step
  ordering within one job**, and the assertion guarding that ordering is scoped to a
  single job. Any restructure that separates them is unguarded, not merely riskier.
- **The apply workflow's path filter must not raise an approval request with nothing
  to approve.** Extending this to multiple environments strengthens it: an approval
  request for prod raised by a staging-only merge is the same defect.

`pr-validation.yml` already discovers `terraform/modules/*/ terraform/environments/*/`
for `fmt` and `validate`. Discovery is an established idiom in this repository, not a
new one; only plan, apply and drift were left behind.

## Goals / Non-Goals

**Goals:**

- Adding an environment requires no change to any file under `.github/workflows/`. It
  still requires that environment's own state workspace, GitHub Environment, secrets
  and Dependabot entry — see the delta's ADDED requirement, which bounds the claim.
- Prod's observable behaviour, credentials and repository settings are unchanged at
  N=1, so this change is verifiable before its second consumer exists.
- Every property above is asserted by `.github/tests/`, which is the only mechanism in
  this repository that can read a committed workflow file.

**Non-Goals:**

- Creating any environment. That is entry 49.
- Anything under `ansible/`. See proposal.md — What Changes.
- Splitting `TF_API_TOKEN` by privilege. It remains unsplit by necessity
  (`iac-state-management`), and this change neither improves nor worsens that.

## Decisions

### 1. Each environment directory carries its own pipeline declaration

A committed file per `terraform/environments/<name>/` declaring the GitHub Environment
name, the read-only secret name, and whether the destroy-policy gate applies.

*Why:* the alternative is a mapping in workflow text — a `case` on the environment
name, or a hand-maintained matrix `include:`. Both reintroduce exactly what discovery
removes: adding an environment would mean editing three workflows, which is the state
this change exists to end and the state the README already claims does not exist.
Putting the declaration next to the `terraform.tfvars` it belongs to keeps the folder
self-describing.

*Alternative considered:* deriving everything by convention from the directory name
(`prod` → `production` Environment, `HCLOUD_TOKEN_PROD`). Rejected because it forces a
rename of prod's existing repository secret, which is a repository-settings change that
must land in the same instant as the merge, and because the destroy-gate policy is a
genuine per-environment decision that no naming convention can express.

*Consequence, and it is the point:* prod declares its read-only secret as
`HCLOUD_TOKEN`, so **nothing in repository settings changes for N=1.**

### 2. The matrix is derived from changed paths, not from the directory listing alone

`terraform/modules/**` → every environment. `terraform/environments/<name>/**` → that
environment only.

*Why:* without it, a staging-only merge raises a prod approval request, which the
*Gated Production Apply* requirement forbids on the ground that an empty approval
prompt trains the approver not to read. The gate is only as good as the approver's
attention, so protecting that attention is protecting the gate.

*Fail-closed, following `ansible-verify.yml`'s precedent:* where change detection did
not conclude, its output is an empty string, and an empty "nothing changed" is
indistinguishable from a real one. An unresolvable value is refused rather than read as
"no environments affected" — otherwise a broken filter silently applies nothing and
reports green.

*The precedent is followed, not copied.* `ansible-verify.yml` conditions its filter on
`github.event_name == 'pull_request'` precisely because no other event carries a diff,
and `apply.yml` runs on `push`. There the comparison base is `github.event.before`,
which is all-zeroes on a branch's first push and unresolvable after a force-push or a
history rewrite. The resolution step therefore determines the affected set from the
push's own commit range where that resolves, and **fails** where it does not. It never
falls back to "no environment affected", which on this workflow means applying nothing
for a merge that did change infrastructure, reporting green, and leaving the divergence
to the next nightly drift sweep.

### 3. The pull-request plan is a matrix job that carries its own secret scan

**Revised twice.** Draft 1 made the plan a matrix job `validate` concluded for. Plan
review found that this breaks the *Pull Request Validation Checks* scenario "PR with a
leaked credential fails validation", which obliges the workflow to fail "before any
`terraform plan` is executed" — and breaks it *silently*, because
`test_secret_scanning_precedes_any_terraform_plan_in_the_same_job` skips any job in
which it finds no gitleaks step (`if not scan_indices or not plan_indices: continue`).

Draft 2 moved the plan into a shell loop inside `validate`, preserving that ordering.
Review round 2 found the loop cannot select a per-environment credential: `${{ }}` is
evaluated before a step runs, so one step binds one compile-time-known secret and a
loop over N environments cannot hold N tokens. That is not a purity concern. At N≥2
staging's plan would run against staging's HCP state holding **prod's** token, see none
of staging's resources, and either error or report every resource as absent — so the
loop degrades *Pull Request Plan Visibility* itself, not merely credential hygiene.

**The plan is therefore a matrix job, and the secret scan is duplicated into it.** Each
matrix job runs gitleaks and then its environment's plan, so the scan-before-plan
ordering holds *within the job where a plan actually runs* — which is what the
requirement is about and what the existing assertion measures. `validate` keeps every
other step, its literal name, its `pull-requests: write` permission and its registered
context, and gains a dependency on the matrix plus a step concluding on its behalf,
distinguishing `skipped` from `success` exactly as `ansible-verify` does.

*Why this over the alternatives review round 2 costed:*

- *Keep the loop and drop per-environment PR credentials* — rejected: it does not
  merely amend two scenarios, it makes the second environment's PR plan produce a
  meaningless diff, which is the requirement's whole subject.
- *Three jobs (scan → plan matrix → aggregator)* — rejected: it evacuates every step
  from `validate`, including the OpenSpec step separately required to sit in an
  unconditional job, for the same guarantee this buys with one duplicated scan.

*The cost, accepted:* gitleaks runs once per environment instead of once. The step is
not cached — it reads the pin, downloads a release tarball and scans the whole tree — so
this is a real if modest addition per environment. Version drift between the two copies
is not a risk: `test_ci_installs_the_version_the_precommit_config_pins` quantifies over
every gitleaks step in the workflow.

`apply.yml` and `drift.yml` get a matrix for a different and structural reason: a job
attaches to exactly one GitHub Environment, so per-environment gating cannot be a loop
at all. Neither is a required status check, so neither raises the generated-context
problem.

*Consequence for the assertion:* under this shape the existing ordering test finds both
steps in each matrix job and asserts rather than skipping. Task 5.4 additionally
strengthens it so that a plan in a job with **no** preceding same-job scan fails rather
than being skipped — closing the vacuity path for good, rather than relying on this
change's shape to avoid it.

### 3a. `validate` becomes an aggregator, so two requirements admit `always()`

Aggregating forces `if: always()` on `validate`: a job with `needs:` is skipped whenever
a dependency fails, and a skipped job produces no status check context — under branch
protection, a required check that never reports.

But `validate` is also the job holding the specification-record check and the
CI-configuration suite, and both *The Specification Record Is Verified in Continuous
Integration* and *The Continuous-Integration Configuration Is Itself Verified* require
that job to be unconditional, enforced by assertions treating the presence of any `if:`
key as the offence.

**Both requirements are amended here to admit the single literal `always()` and nothing
else.** Argued rather than absorbed as a test edit, because those requirements are
deliberately suppression-resistant and say so. The argument: their stated intent is that
the job must not be *skippable* — "a step that cannot be skipped inside a job that can is
skippable" — and `always()` cannot evaluate false. For a job that has dependencies it is
the strongest available guarantee that the job still runs, so admitting it preserves the
intent rather than relaxing it. Admitting the exact literal rather than a class of truthy
expressions is what keeps the closed form those requirements insist on: `always() &&
<anything>` stays forbidden.

*The cost, accepted:* `always()` runs a job even when the run is cancelled, so this
workflow's `cancel-in-progress: true` stops reaching `validate` — its heaviest job,
installing Python, Node, gitleaks, Terraform, tflint and the Ansible toolchain. A push
that supersedes another now pays for that job twice. `drift.yml` escapes this by pairing
a job-level `always()` with a step-level `if: ${{ !cancelled() }}`, which is unavailable
here: the suite and OpenSpec steps must carry no step-level `if:` at all. The cost is CI
minutes and slower feedback, not correctness.

*Alternatives considered and rejected:* not aggregating at all, which dissolves this and
two related findings but silently stops a failed `terraform plan` blocking the merge — a
real reduction that would have to be recorded as deferred work rather than made quietly;
and registering a second required context for a plan aggregator, which needs a
branch-protection change, contradicts this change's N=1 goal, and leaves two contexts to
keep in step.

### 4. Per-environment read-only secrets, selected by name from the declaration

Every job that plans — the pull-request matrix, `apply.yml`'s plan matrix and
`drift.yml`'s matrix — declares no `environment:` and reads
`secrets[<name from the declaration>]`, carried on the matrix. Apply jobs declare their
`environment:` and read `HCLOUD_TOKEN`, which GitHub resolves to that Environment's
value. Decision 3's shape is what keeps this available on the pull-request path: a
matrix exists there, so the indexed read has a name to use.

*Why:* it is the only shape that keeps the two hard constraints simultaneously —
plan jobs reach repository secrets only, and each environment needs a distinct
read-only token once it has its own Hetzner project. Indexing the `secrets` context by
a matrix-supplied name is the mechanism; task 1.1 verifies it behaves as documented
before anything is built on it.

### 4a. Detecting an Environment that omits its write token, without reaching past it

GitHub resolves an *absent* Environment secret to the repository secret of the same
name, so an Environment created without `HCLOUD_TOKEN` silently supplies whatever the
repository holds — at N≥2, another environment's token and therefore another Hetzner
project.

The obvious check does not work, and review round 2 caught it: a job declaring
`environment:` resolves *every* read of that name to the Environment value, so it
cannot obtain the repository-scoped value to compare against. For prod the two operands
would be the same expression outright, since prod declares `HCLOUD_TOKEN` as its
read-only secret name (decision 1).

**The plan job is where the repository value is visible.** It declares no
`environment:`, so it reads the repository-scoped read-only token by construction. It
emits `sha256(secrets.HCLOUD_TOKEN + <this run's id>)` as a job output — that read is
the repository-scoped value by construction — and the apply job computes the same digest
over its own resolved `HCLOUD_TOKEN` and fails if they match.

**The operand is `HCLOUD_TOKEN` specifically, not the environment's declared read-only
secret.** GitHub falls back to the repository secret *of the same name*, and the two
coincide only for prod. Digesting the declared name would compare against a secret the
apply job could never have fallen back to, so the guard would pass in exactly the
N≥2 cases it exists to catch. Salting with the
run id makes the digest useless outside the run it was produced in, so nothing durable
about either secret is published to the workflow's output graph.

This is live at N=1 rather than dormant: on every prod apply the plan job holds the
read-only token and the apply job holds the read-write one, so the digests differ and
the check passes *for the right reason*. Were prod's Environment secret ever removed,
it would fire.

*Alternative considered:* asserting the token's Hetzner project against a project
identifier in the declaration. It checks the property that actually matters rather than
a proxy for it, but the Hetzner API exposes no project-identity endpoint, so it would
have to be inferred from a resource listing — more moving parts, and one that fails
differently on an empty project.

### 5. Every apply job declares an `environment:`; the protection rules decide whether it pauses

Staging is not made ungated by omitting `environment:` — it is made ungated by its
GitHub Environment having no required reviewer.

*Why:* omitting `environment:` would put the write-capable token in an ungated job,
which is the precise failure *Credential Scoping by Privilege* exists to prevent. The
confinement of the write credential and the presence of a human approver are two
different things, and only the second should vary by environment.

### 6. The destroy-policy gate is declared per environment, defaulting to on

An environment that declares nothing is gated.

*Why:* requiring a `destroy-override` label to tear down a disposable environment puts
friction on the operation that environment exists to make cheap, and friction on a
routine operation gets routed around rather than heeded — at which point the label
means nothing anywhere. Defaulting to on means a mistake in the declaration fails
safe.

### 7. Requirement names are left unchanged, though three now read narrower than they are

*Gated Production Apply Applies the Reviewed Plan* now governs every environment's
apply. The name says "Production".

*Why not rename:* requirement names are this repository's citation form
(`AGENTS.md`, "Citing this repository's own specifications and change records"), and
they are cited from workflow comments in `apply.yml`, `drift.yml` and
`pr-validation.yml`. Renaming would sweep those in the same change that restructures
them, mixing a mechanical rename into a diff that needs to be read closely.

Recorded here *and* in `docs/deferred-work.md`: a note kept only inside a change is
archived with it, and this one outlives the change (`AGENTS.md`, "A second change
surfacing"). The same applies to the drift-heartbeat question under Open Questions.

## Risks / Trade-offs

- **An abstraction built before its second consumer exists.** → Mitigated by deciding
  the varying axes up front rather than discovering them: the declaration's three
  fields are exactly the three things found to vary. It is a real risk that a fourth
  appears when entry 49 lands; the declaration file is extensible, so a fourth field
  is an additive change rather than a restructure.
- **The two most important properties cannot be verified by anything in this
  repository.** Whether the required status check context is registered, and whether
  each GitHub Environment has the intended protection rules, are repository settings.
  `.github/tests/` can assert only that the workflows are *shaped* so that registering
  them is safe — a literal job name, no workflow-level path filter — and must not be
  written to imply more. This is the same boundary the *Branch Protection* requirement
  already draws for itself.
- **A staging Environment with no required reviewer holds a write-capable Hetzner
  token reachable by any merge to `main`.** → Contained only if staging is a separate
  Hetzner project, which is what entry 49 records as the recommendation. If staging
  ends up in prod's project, its Environment must require a reviewer, and this
  change's mechanism supports either — the choice is 49's to make, not this one's.
- **Restructuring three gated workflows at once.** → N=1 is the mitigation: the
  acceptance test is that prod plans, applies and drifts exactly as before, and the
  first real apply through the restructured `apply.yml` is a prod apply that can be
  compared against the plan it was supposed to reproduce.

## Migration Plan

The *merged state* requires no infrastructure change and no repository-settings change,
by design of decision 1. Tasks 1.1 and 1.2 do create a scratch GitHub Environment to
verify two mechanism assumptions before anything is built on them; it is removed by
task 1.3 and exists only on the branch. Rollout is the merge itself, and the first post-merge apply is the verification: it
must produce a plan identical in shape to what the pre-change workflow produced, and
the `production` approval must still be requested.

Rollback is a revert of the workflow files; nothing outside the repository has been
altered to roll back.

## Open Questions

- Whether the nightly drift heartbeat (`infrastructure-drift`) stays a single check
  across all environments or becomes one per environment. It answers "did the sweep
  run at all", which is per-run rather than per-environment, so a single check is the
  working assumption. Deferrable: it changes no requirement here, and the second
  environment is the first moment the answer matters.
