## Context

See `proposal.md` — Why, and `handoff.md` for the audit findings this change
closes. Constraints that shape the approach:

- `pr-validation.yml` is the registered required status check. Its top comment
  and the **Required Status Checks Report on Every Pull Request** requirement
  forbid a workflow-level `paths:` filter on it — filtering must stay inside
  the job. `apply.yml` is under the opposite constraint and is not a required
  check.
- No pull-request-time job may declare `environment:`. That absence is what
  keeps the read-write Hetzner token out of PR runs (**Credential Scoping by
  Privilege**). Nothing added here may introduce one.
- `terraform validate`/`tflint`/`terraform test` discover directories rather
  than naming them, deliberately (`fix-ci-module-coverage`). Anything added
  for Ansible follows that shape.
- Every external dependency is pinned exactly (AGENTS.md). CI must install the
  Molecule toolchain from `ansible/requirements-test.txt` and
  `ansible/requirements.yml`, never a fresh resolve.
- Five roles carry a `molecule/` directory — `deploy_user`, `docker`,
  `hardening`, `ops_user`, `platform_data_volume` — holding eight scenarios
  between them. `handoff.md` says six roles; that count is stale (`tailscale`
  has no scenarios). The scenario count it gives is correct.
- GitHub-hosted `ubuntu-latest` jobs run on the VM itself, not inside a
  container, and Docker is preinstalled. Molecule's Docker driver therefore
  launches sibling containers against the host daemon — not Docker-in-Docker.
  The scenarios need `privileged: true`, `cgroupns_mode: host` and a writable
  `/sys/fs/cgroup` for systemd, which that arrangement can supply.

## Goals / Non-Goals

**Goals:**

- No verification hole that depends on which directory a pull request touched.
- The capability's guarantees about its own configuration become machine-checked
  rather than resting on a reviewer noticing.
- The destroy-policy gate fails closed, with an uninspectable plan clearly
  distinguishable from an inspected-and-clean one.
- One pinned version per tool, in one place, for both local and CI runs.
- Ansible checks discover roles and scenarios rather than enumerating them.

**Non-Goals:**

- Making Molecule a required status check in this change. That promotion is
  recorded as a queue entry and depends on evidence this change produces.
- Changing any Molecule scenario, role, or `verify.yml`. This change makes the
  existing suite run in CI; it does not modify what it asserts.
- Changing the destroy-policy gate's mechanism, its `destroy-override` label,
  or its PR-number resolution logic. Only its failure direction changes.
- Touching Terraform configuration or any production resource.

## Decisions

### Decision 1: `gitleaks dir`, not `gitleaks detect`

Bumping the CI pin from `8.24.2` to the pre-commit pin `v8.30.0` requires
revisiting the invocation. Verified against the 8.30.0 binary: `detect` is no
longer a listed command (the CLI now exposes `dir`, `git`, `stdin`); it still
resolves as a deprecated alias for `git`, but it is not the documented surface
and is on a path to removal.

`git` scans commit history; `dir` scans the working tree. CI uses `dir`:

- `actions/checkout` clones at `fetch-depth: 1` by default. A history scan on a
  shallow clone scans whatever commits happen to be present — one — and reports
  success on the rest. That is the same "absence of evidence read as evidence of
  absence" shape as the destroy gate this change is fixing.
- Verified: run against a git-less directory, `gitleaks detect` logs the git
  failure and still concludes `no leaks found`. A working-tree scan has no such
  failure mode; the files are either there or the step errors.
- What matters on a pull request is whether a secret is in the tree being
  merged, not when it entered.

Verified on this repository at the change's base commit: `gitleaks dir . --redact --exit-code 1`
exits 0, including over `ansible/inventory/group_vars/prod.yml` and its Vault
blob. Ungating the scan does not introduce a pre-existing failure to clean up.

### Decision 2: CI derives the gitleaks version from `.pre-commit-config.yaml`

A comment saying "keep these in sync" is what produced the current drift. The
workflow instead reads the pinned `rev` out of `.pre-commit-config.yaml` at run
time and installs that version, so the two cannot diverge and the pre-commit
file is the single source of truth the spec requires.

Extraction uses `awk` against the gitleaks repo block — no `yq`, no `python3`
dependency on the runner image, and it fails loudly on an empty result rather
than falling back to a default. Alternative considered: a repository variable
holding the version, which just relocates the drift to a place Dependabot and
`pre-commit autoupdate` cannot see.

### Decision 3: Ansible lint and syntax-check run through `pre-commit`, gitleaks does not

`ansible-lint` and the syntax-check hook are already defined in
`.pre-commit-config.yaml`, pinned, with non-obvious arguments (`ansible-lint`
needs an explicit `ansible/` target or it scans the whole repo;
`--syntax-check` must run with cwd `ansible/` or `ansible.cfg`'s `roles_path`
never resolves). Re-expressing those invocations in the workflow would
duplicate both the pins and the subtleties. CI runs
`pre-commit run <hook-id> --all-files` for those two hooks, with
`~/.cache/pre-commit` cached.

**gitleaks is deliberately excluded from that treatment.** Its upstream
pre-commit hook runs `gitleaks git --pre-commit --staged`. Nothing is staged in
a CI checkout, so `pre-commit run gitleaks --all-files` would scan zero changes
and pass unconditionally — a vacuous green exactly where the spec demands a
real scan. gitleaks therefore keeps its direct CLI invocation, with Decision 2
supplying version parity instead.

`ansible-galaxy install -r ansible/requirements.yml` runs before the hooks so
`ansible-lint` can resolve `geerlingguy.docker`.

The blocking tier installs `ansible/requirements-test.txt` whole, which pins
`ansible-core==2.21.3` — the source of `ansible-galaxy` and `ansible-playbook`,
without which the tier fails at its first step. That manifest also carries
Molecule and its Docker driver, which this tier does not use. Installing a
subset would mean either a second copy of the `ansible-core` pin or extracting
one line out of a pinned manifest, both of which reintroduce the drift problem
Decision 2 exists to close. Paying a few seconds of unused `pip` install to
keep one pin in one place is the better trade.

`pre-commit` itself needs a pin, and nothing in this repository pins it —
`pre-commit-autoupdate.yml` installs it with a bare `pip install pre-commit`.
A new `.github/requirements-ci.txt` holds that pin, and the new steps install
from it. Bringing the pre-existing unpinned install in
`pre-commit-autoupdate.yml` onto the same file is a one-line fix in a workflow
this change otherwise does not touch, and it is not a verification gap; it is
recorded as a change-queue entry rather than folded in.

### Decision 4: Molecule runs in its own workflow, on a discovered role matrix

A separate `ansible-verify.yml`, not a job inside `pr-validation.yml`. A job
inside the required workflow contributes to that check's conclusion, so it
cannot be advisory there without `continue-on-error` swallowing failures into a
green check.

**Promotion is not free, and the plan must say so.** The workflow carries a
workflow-level `paths: ['ansible/**']` filter, which is correct while it is
advisory and disqualifying the moment it is not: the **Required Status Checks
Report on Every Pull Request** requirement states that such a filter leaves
every non-matching pull request permanently pending, and so unmergeable. This
is the same trap `pr-validation.yml`'s top comment records. Promoting this
workflow to a required check therefore means *first* removing the
workflow-level filter and moving the gating inside an always-running job — the
shape `pr-validation.yml` already uses — and only then adding it to branch
protection. The change-queue entry records that, not just the green-run
condition, so a future session does not read "add it to branch protection" as
the whole job.

Building it in the always-running shape now was considered and rejected: it
would put a job on every pull request, including ones touching nothing
Ansible-related, to collect evidence that only Ansible-touching pull requests
can produce.

The workflow has two jobs: a `discover` job that enumerates
`ansible/roles/*/molecule/` and emits the role list as a JSON matrix output,
and a `molecule` job consuming it via `strategy.matrix`. This satisfies the
spec's discovery requirement, parallelises the eight scenarios across roles,
and names each role in the checks UI so a failure identifies itself.

`discover` fails explicitly when the discovered set is empty. An empty matrix
skips the dependent job and the workflow concludes success — a discovery
regression or a directory rename would otherwise read as a green run that
verified nothing, which is the failure shape Decision 1 rejects elsewhere and
would become a silent required-check pass on promotion.

The workflow also declares `workflow_dispatch:`, and the **timing of the first
dispatch is post-merge, not pre-merge**. GitHub resolves a manual dispatch
through the default branch's workflow listing: a workflow file that exists only
on a feature branch is not offered in the Actions UI and `gh workflow run
--ref <branch>` returns a 404 saying the workflow has no `workflow_dispatch`
trigger. The `ref` input chooses which branch's *code* runs, not whether the
workflow can be found.

So the trigger is what makes the suite observable at all — this change's own
pull request touches no path under `ansible/`, and the `paths:` filter would
otherwise leave the workflow unrun until someone unrelated next edited a
role — but the run happens on `main` after merge. That also gives this change
the observation its `ship:confirm` gate would otherwise lack: per-role outcomes
and durations from a real run, rather than a waiver.

Alternatives considered and rejected: a temporary `push:` trigger on the
feature branch, which is a workflow edit that must then be reverted; and
widening the `pull_request` paths filter for one run, which reintroduces
exactly the workflow-level filter problem this decision spent a paragraph on.

Each matrix leg runs `molecule test --all` from `ansible/roles/<role>`, per
README. `--all` is required: `ops_user` has two scenarios and `deploy_user`
three, and `molecule test` without it runs only `default`.
`fail-fast: false`, so one role's failure does not hide the others' results —
the point of the advisory tier is to learn which scenarios survive a runner.

Advisory status is achieved by *not registering the workflow as a required
check*, not by `continue-on-error`. The job reports its true conclusion; branch
protection simply does not require it. `continue-on-error` would make the run
green and destroy the signal this tier exists to collect.

### Decision 5: The destroy gate proves the plan is clean, or fails

The current gate's shape is `has_destructive=$(jq ... || true)` followed by
`[ "$has_destructive" != "true" ]` — the empty string a failed `jq` leaves
behind takes the pass branch. Inverting the comparison is not sufficient on its
own. Three distinct routes have to be closed, and the ordering matters:

1. **The plan cannot be rendered.** `terraform show -json tfplan >plan.json`
   runs under `set -e` and is not tolerated; a failure aborts the step.

2. **The document is not a Terraform plan.** A well-formed JSON file that is
   not a plan — an empty object, a truncated-then-valid artifact, the wrong
   file entirely — is the case a naive fix misses: `.resource_changes[]?`
   suppresses the missing-key error, `length > 0` evaluates to a legitimate
   `false`, and the gate reports inspected-and-clean. The `?` cannot simply be
   dropped, because `terraform show -json` genuinely omits `resource_changes`
   for a no-op plan; identity must be asserted separately instead. The step
   therefore first requires `format_version` to be present, and fails to the
   inspection-failure branch if it is not.

3. **`jq` itself fails.** Its exit status is captured explicitly with
   `if ! has_destructive=$(jq ... 2>&1); then` rather than left to `set -e`.
   This matters: under `bash -e` — the default shell for a `run:` step — a
   failing command substitution in an assignment aborts the step *at the
   assignment*, so a later three-way match would never execute and the message
   the spec requires would never be printed. The gate would fail closed but
   report a raw `jq` parse error indistinguishable from any other crash.

   `jq` is invoked without `-e`, since `-e` exits non-zero on a `false`
   result — the *good* outcome here — which would conflate "the answer is no"
   with "the inspection failed".

Only after those three does the result get matched against exactly `true` and
exactly `false`, with any other value falling to the same inspection-failure
branch. Every route to "we could not tell" ends in a failed workflow carrying a
message that names plan inspection as the cause, distinct from the message a
plan that was inspected and found clean produces.

Alternative considered: `set -o pipefail` plus keeping the current comparison.
Rejected — it closes one route to an empty value and leaves the other two, and
it produces no distinguishable message.

Alternative considered: moving the inspection into a version-controlled script
with its own test fixtures, so the gate's logic is reviewable and testable as
code rather than as inline workflow shell. Genuinely better for the
highest-consequence logic in this repository, and rejected here only as scope:
it is a change to how the gate is structured, not to its failure direction.
Recorded as a change-queue entry instead.

### Decision 6: `apply.yml`'s path filter is `terraform/**`

Broader than `terraform/environments/prod/**`, because a module change alters
the prod plan without touching the environment directory. Narrower than adding
`.github/workflows/apply.yml` itself: a workflow edit that changes how apply
behaves is reviewed on its pull request and takes effect on the next
Terraform-affecting merge, and self-triggering would restore the approval noise
this decision removes for the case that needs it least.

`drift.yml` continues to run nightly, so nothing that a per-merge plan would
have caught goes undetected for longer than a day.

### Decision 7: The CI configuration is tested by a stdlib `unittest` suite

Deriving this change's tests from its delta specs established that most of its
scenarios are not analogies to assertions — they *are* assertions over
repository files. "No gitleaks step carries the Terraform condition", "the CI
gitleaks version equals the pre-commit pin", "every `.terraform.lock.hcl`
directory appears in `dependabot.yml`" are each one line of YAML parsing. So
the suite exists, and this change is the right place for it: fifteen of its
assertions fail on the tree as it stands and discriminate, which is
what makes it a test suite rather than a description.

**Location:** `.github/tests/test_ci_configuration.py`. Everything it asserts
about lives in `.github/` bar `.pre-commit-config.yaml`, and the repository's
only other tests are module-local `terraform/modules/*/tests/*.tftest.hcl` — a
top-level `tests/` root would imply a general test tree this project does not
have.

**Runner:** `python3 -m unittest discover -s .github/tests`. Not
`terraform test`, which can only exercise Terraform modules and cannot reach a
workflow file. This change therefore introduces a *second* test command, and
the project's conventions say so explicitly rather than leaving a reader to
infer that `terraform test` covers everything.

**Dependencies:** the standard library plus PyYAML. PyYAML currently reaches
this repository only transitively through `ansible-core==2.21.3`, which is not
a pin under AGENTS.md's convention — a transitive dependency is not pinned, it
is merely currently resolved. It is pinned exactly in
`.github/requirements-ci.txt` alongside `pre-commit`.

**Gating:** unconditional, not path-filtered. The suite asserts invariants that
a pull request touching nothing under `.github/` can still violate — a module
added under `terraform/modules/` breaks Dependabot coverage without editing a
workflow. The suite's own runtime is negligible — a fraction of a second; the
step's real cost is Python setup plus a two-package install, still far below
anything gating would save.

This scope was not in the reviewed plan. It was added on the operator's
decision after test derivation, and the plan-review gate is re-run over the
addition rather than the change proceeding on the strength of the earlier
verdict.

## Risks / Trade-offs

- **Molecule does not survive a hosted runner** (privileged systemd containers,
  cgroup v2, the `deploy_user` scenario installing Docker Engine inside a
  container) → This is why the tier is advisory. A red advisory workflow is the
  intended, informative outcome; it blocks nothing, and the queue entry gates
  promotion on it going green.
- **The advisory tier is ignored forever** — the standing failure mode of every
  non-blocking check → Mitigated only partially, by recording the promotion in
  `docs/change-queue.md` with a concrete condition rather than leaving it as an
  intention. Honest limitation: nothing enforces that entry.
- **Molecule run time makes pull requests feel slow** → Separate workflow,
  role-level matrix, `fail-fast: false`. It never blocks a merge, so its
  duration costs attention, not throughput. Real durations are one of the
  things this change is run to find out.
- **Ungated gitleaks surfaces a pre-existing finding and blocks unrelated pull
  requests** → Checked before proposing: `gitleaks dir` exits 0 on the current
  tree. If a finding appears later it is a true positive by definition.
- **The `awk` extraction of the gitleaks pin breaks if
  `.pre-commit-config.yaml`'s layout changes** → The step fails loudly on an
  empty extraction rather than defaulting, so the failure is a red check with a
  clear message, not a silently skipped scan.
- **`pre-commit run --all-files` scans files a pull request did not touch** →
  Accepted, and preferable: it is the same behavior as the Terraform checks,
  and a repository that cannot pass its own linter on every file has a problem
  worth surfacing.
- **`apply.yml`'s path filter hides a genuine prod-affecting change made
  outside `terraform/`** → No such path exists today; Terraform state is driven
  only by `terraform/`. `drift.yml` remains the backstop.
- **The Molecule promotion condition measures a moving target.** Every scenario
  pins its platform image as `geerlingguy/docker-ubuntu2204-ansible:latest`, a
  floating tag. "Consecutive green runs" is therefore evidence about a base
  image that can change underneath it, and a red run may be attributable to an
  upstream image rather than to the runner — the ambiguity task 8.3 exists to
  remove → The floating tag is out of this change's scope and is queued
  separately; the promotion entry records that it depends on that pin landing
  first, so the condition is not evaluated against a moving base.
- **The CI-configuration suite asserts today's workflow shape and becomes a
  brake on legitimate restructuring** — a test that fails whenever a workflow
  is reorganised, rather than when a guarantee breaks → The assertions are
  written against properties the specs state (which step is gated on what,
  which version equals which, which job declares no `environment:`), not
  against step ordering or naming. The one exception is the gitleaks/plan
  ordering check, which the spec does require. Where a future restructuring
  makes an assertion wrong, the spec it came from is the thing to change first.
- **Eight of the suite's tests cannot execute their assertions until
  `ansible-verify.yml` exists** → They fail on a missing file today. That is
  the correct state before implementation, and it is recorded in
  `test-plan.md` so those eight are not read as coverage until the workflow
  lands.
- **The blocking Ansible tier reaches production CI unexercised in CI** → Its
  behavior is verified locally on the branch and reported as such. The residual
  risk is a workflow-syntax or runner-environment error that a local
  `pre-commit run` cannot surface; `actionlint` covers the syntax half, and the
  tier blocks only pull requests that touch `ansible/`, so a defect there
  cannot block unrelated work.

## Migration Plan

No migration. Every change is to CI configuration and takes effect on the pull
request that carries it. Which of the new checks that pull request actually
exercises needs stating precisely, because it is less than it first appears:

- **The ungated gitleaks scan runs.** It is unconditional now, and the pull
  request changes files. This is a real exercise of the primary fix.
- **The CI-configuration suite runs, unconditionally, and passes.** It is the
  second check this pull request genuinely exercises, and the only one
  asserting the change's own guarantees — fifteen of its assertions were
  failing before the implementation landed. This is a real exercise of the
  second added requirement, including its "runs regardless of what the pull
  request touched" scenario.
- **The Terraform steps skip**, as they do today — no `terraform/**` path is
  touched.
- **The blocking Ansible steps skip.** They are gated on `ansible/**`, and this
  change edits `.github/`, `docs/`, `openspec/` and `README.md`, none of which
  that filter matches. Their evidence is therefore the local `pre-commit run`
  in task 8.2, not a CI run, and the change reports it that way rather than
  claiming a CI observation that did not occur.
- **The Molecule workflow does not trigger on the pull request either**, for
  the same reason, and cannot be dispatched manually before merge — the trigger
  is only exposed once the file is on the default branch (Decision 4).

Rollback is reverting the pull request. No infrastructure state is involved.

Three facts are not observable until after merge, and are recorded as tasks
rather than assumed:

- `apply.yml`'s new path filter means the first merge after this change will
  not run a prod plan. Intended, and the operator should know it rather than
  read a missing approval request as a broken pipeline.
- The Molecule workflow's first run is a manual `workflow_dispatch` on `main`,
  once merged. Its per-role outcomes and durations are this change's confirm
  observation and the evidence the promotion queue entry depends on.
- The blocking Ansible tier's first CI exercise will be whichever later pull
  request first touches `ansible/`. Until then it is verified locally only, and
  said to be.

## Open Questions

- Whether Molecule should eventually run on a schedule rather than per pull
  request, if per-PR duration proves poor value. Deferrable: it changes a
  trigger, not the specs, and belongs with the promotion decision once real
  durations exist.
