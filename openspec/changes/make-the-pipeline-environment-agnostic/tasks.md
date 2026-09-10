## 0. A note on what this task list may contain

Branch and working-tree removal happen after this change's record has merged, which is
after the commit that writes this file — a task for them would be unticked by
construction forever. They are recorded in prose in the archive group instead. This is
the repository's own convention (`AGENTS.md`, "Task lists, archived records, and
disclosing what was not done"); the archive step itself is a task and is unaffected.

## 1. Establish the mechanism before building on it

- [x] 1.1 Confirm that indexing the `secrets` context by a matrix-supplied name
  (`${{ secrets[matrix.<field>] }}`) resolves a repository secret, by running a
  scratch workflow on a branch that echoes only whether the value is non-empty —
  never the value. Decision 4 rests on this; if it does not hold, the read-only
  credential scheme needs rework before any workflow is edited.
- [x] 1.2 Create a scratch GitHub Environment with no protection rules and no secrets,
  and confirm that a `matrix` value can supply a job's `environment:` name against it.
  Decision 5 rests on this. The scratch workflow SHALL be `push:`-triggered, not
  `workflow_dispatch:` — dispatch resolves the workflow through the default branch's
  listing, so a branch-only workflow cannot be dispatched.
- [x] 1.3 Delete the scratch workflow **and the scratch GitHub Environment**, and
  confirm both are absent — the workflow from the branch, the Environment from
  repository settings — before any other task's work is committed. The Environment is a
  repository-settings change existing only for tasks 1.1–1.2; leaving it behind would
  falsify design.md's Migration Plan.

  **Result (2026-09-10, run 34431719684, both jobs green).** 1.1: `secrets[matrix.ro_secret]`
  resolved a non-empty 64-character value for `HCLOUD_TOKEN` in a job declaring no
  `environment:` — masked as `***` in the log, with only its length printed. 1.2: the job
  declaring `environment: ${{ matrix.environment_name }}` attached to
  `scratch-matrix-probe` and ran. Decisions 4 and 5 hold. Workflow deleted in this
  branch; the GitHub Environment deleted via the API, leaving `production` as the only
  one.

## 2. The per-environment declaration

- [x] 2.1 Decide and document the declaration file's name, format and fields, and
  record the choice in `design.md` Decision 1 if it differs from what is written
  there. Verify by writing the file for prod in 2.2 against it.
- [x] 2.2 Add prod's declaration under `terraform/environments/prod/`, naming
  `HCLOUD_TOKEN` as its read-only secret, `production` as its GitHub Environment, and
  the destroy-policy gate as applicable. Verify that `terraform validate` and
  `terraform fmt -check` still pass for that directory — the file must not be picked
  up as Terraform configuration.

  **Decided (2.1):** `pipeline.yml` in the environment's own directory, YAML, three
  fields — `github_environment` and `read_only_secret` required, `destroy_policy_gate`
  optional and defaulting to `true`. The gate field names the gate rather than its
  inverse, per the delta's polarity rule. `.yml` keeps it out of Terraform's reach:
  `terraform fmt -check` and `terraform validate` both pass unchanged in
  `terraform/environments/prod/`. Suite 47 → 31 failures on this file alone.

## 3. Discovery and change detection

- [x] 3.1 Write the discovery step that enumerates `terraform/environments/*/`, reads
  each declaration, and emits a matrix. Verify by running its body standalone against
  the working tree and confirming it emits exactly one entry, for prod.
- [x] 3.2 Make discovery fail closed on an absent, unparseable or incomplete
  declaration, on an empty result, and on **two environments declaring the same
  read-only secret name or the same GitHub Environment name**. Verify by running its
  body against a scratch tree carrying each of those five shapes and confirming each
  exits non-zero — the first three naming the directory and the missing field, the last
  two naming both colliding environments.
- [x] 3.3 Write the change-detection step mapping changed paths to affected
  environments (`terraform/modules/**` → all; `terraform/environments/<name>/**` →
  that one), refusing an unresolvable filter result rather than reading it as "nothing
  changed". Verify by running its body standalone across each case.
- [x] 3.4 Keep both step bodies free of `${{ }}`, taking every input through `env:`, so
  `.github/tests` can extract and execute them — the constraint `ansible-verify.yml`'s
  gate and discovery bodies already observe, and the reason its tests can exist.

  **Result (3.1-3.4).** One discovery body, duplicated verbatim into all three
  workflows, and one resolution body duplicated into the two that narrow by changed
  paths. Both are free of Actions expressions and take every input through `env:`,
  so `.github/tests` executes them rather than reading them. Discovery is exercised
  over six scratch trees by `TestDiscoveryFailsClosed` (the five refusals 3.2 names,
  plus the clean two-environment tree that stops a census refusing everything from
  satisfying them). The mapping 3.3 describes is exercised over both workflows by
  `TestTheAffectedEnvironmentMappingIsRunRatherThanRead`, added under 5.2 - see
  there for why it was not already covered.

  The declaration is read with `sed`/`awk` rather than a YAML parser. It is a flat
  mapping by design, and this keeps the body runnable with bash, jq and coreutils
  alone - which is what the suite's own no-privileged-resource constraint requires
  of anything it executes, and what `.pre-commit-config.yaml`'s gitleaks pin is
  already read with.

## 4. The three workflows

- [x] 4.1 `pr-validation.yml`: move `terraform plan` into a matrix job over the affected
  environments, reading its Hetzner token as `secrets[<the matrix's declared read-only
  secret name>]` and declaring no `environment:`. **That job SHALL run gitleaks as a
  step before its plan step**, so the scan-before-plan ordering holds within the job
  where a plan actually runs. Verify that every job in the workflow running a
  `terraform plan` also runs gitleaks earlier in that same job.
- [x] 4.1a Keep `validate` as the registered context: leave its other steps and its
  literal name untouched, move `pull-requests: write` to whichever job now posts the
  plan comment and reduce `validate`'s own scope to `contents: read` and
  `pull-requests: read` if the posting step moved — **not** dropping the block, since its
  `dorny/paths-filter` step resolves the pull request's diff through the API and needs
  that read scope, as `ansible-verify.yml`'s discovery job declares and comments on (the
  *Least-Privilege Workflow Permissions* scenario "Only the commenting job can write to
  pull requests"),
  add the plan matrix **and the discovery job** to its `needs:`, and have it conclude on
  their behalf — checking the discovery result **first**, since on discovery failure its
  outputs are empty and the "nothing to do" branch would otherwise conclude success on a
  run whose own precondition refused. **The job SHALL carry `if: always()`** — without it
  a failed plan skips `validate`, which produces no status check context and leaves the
  pull request permanently unmergeable under branch protection — distinguishing `skipped` from
  `success`, refusing a skip on a run that asked for the work, and refusing a
  `cancelled` either way. Verify by running the concluding step's body standalone across
  each row of that table.
- [x] 4.1b Set `fail-fast: false` on the plan matrix so one environment's failure does
  not abandon the others, and confirm `validate` still concludes failure when any row
  failed. Verify by running the concluding step's body with a failed row among passing
  ones.
- [x] 4.2 `pr-validation.yml`: give each environment its own PR comment, keyed by a
  marker carrying the environment name, and move `pull-requests: write` to the job that
  posts it if the posting step moves with the plan. **The current `find-comment` uses
  `body-includes: "### Terraform Plan"` with `edit-mode: replace`, so N environments
  would each match and overwrite the same comment, leaving one plan standing.** Verify
  statically — an assertion that the find-comment marker is derived from the
  environment rather than constant — not by observing one comment at N=1, which the
  defect also produces.
- [x] 4.3 `apply.yml`: matrix the plan and apply jobs over the environments the merge
  affects, take each apply job's `environment:` from the matrix, and name the `tfplan`
  artifact per environment so one environment's plan cannot be applied to another.
  Move the `concurrency` group from workflow level to **job level** on the plan and
  apply jobs, derived from the environment — a workflow-level declaration cannot read a
  matrix value. Verify the workflow parses, that no environment name appears as a
  literal anywhere in it, and that the artifact name is derived rather than constant.
- [x] 4.3a `apply.yml`: detect an Environment that omits `HCLOUD_TOKEN`, per design.md
  decision 4a. The **plan** job — which declares no `environment:` and therefore sees
  the repository-scoped read-only token — emits `sha256(token + github.run_id)` as a job
  output; the apply job computes the same digest over its own resolved `HCLOUD_TOKEN`
  and fails before applying if they match. A job declaring `environment:` cannot read
  past its Environment's value, so the comparison **cannot** be done inside the apply
  job alone; and for prod, whose declared read-only name is `HCLOUD_TOKEN`, a naive
  same-job comparison would compare a value with itself. Verify by running both step
  bodies standalone over known inputs, confirming equal inputs fail and unequal inputs
  pass, and that neither body prints either token.
- [x] 4.4 `apply.yml`: read the destroy-policy gate's applicability from the
  environment's declaration, treating an absent statement as applicable. Verify by
  running the gate's body standalone with the flag set both ways against a saved plan
  containing a delete.
- [x] 4.5 `drift.yml`: matrix the plan over every environment regardless of changed
  paths, title each drift issue per environment, and ensure one environment's failure
  does not prevent the others being planned and reported. Verify the workflow parses,
  that the issue title is derived rather than literal, and that `report`'s `needs:`
  names every other job in the workflow — including any new discovery job — since a
  skipped dependency reads as non-failure to its heartbeat.
- [x] 4.6 Update every workflow comment that cites a requirement by name where this
  change altered what that requirement says. Verify by grepping the three workflows for
  requirement names and reading each against the delta spec.

  **Result (4.1-4.6).** `pr-validation.yml` gains a `discover` job and a `plan`
  matrix carrying its own gitleaks install and scan; `validate` keeps its literal
  name, its other steps and its registered context, drops to `contents: read` plus
  `pull-requests: read`, gains `needs: [discover, plan]` and `if: always()`, and
  concludes last so every other check still runs and reports on a pull request whose
  plan failed. `apply.yml` and `drift.yml` gain the same `discover` job and matrix
  the plan and apply over it; `apply.yml`'s `concurrency` moved to job level on both.
  No environment name appears in any of the three.

  Three bodies were run standalone across their cases, and each verification is now
  a committed test rather than a run someone did once: 4.1a/4.1b's conclusion over
  eight rows (`TestThePlanAggregationDiscriminates`), 4.3a's digest pair
  (`TestTheApplyJobEstablishesItResolvedItsOwnWriteToken`), and 4.4's gate with
  applicability `true`, `false` and absent against a stubbed destructive plan - the
  last confirming that only an explicit `false` exempts, that an absent value is
  gated, and that the override label still lets a deliberate teardown through.

  4.6: the three workflows' requirement citations were re-read against the delta.
  All still hold; `apply.yml` gained an explicit citation of *Gated Production Apply
  Applies the Reviewed Plan* naming the fact that it now governs every environment,
  with the declined rename pointed at `docs/deferred-work.md`.

## 5. Tests

- [x] 5.1 Dispatch `ai-toolkit:change-test-writer` with this change's name, its
  absolute `changeRoot` and artifact paths, this repository's convention files, the
  test command `python3 -m unittest discover --start-directory .github/tests` run from
  the repository root, and the test-path glob `.github/tests/*.py`. That is the only
  row of this project's three that applies: every property this change adds is a
  static read of a committed file. Verify that the tests it writes fail against the
  unmodified tree.
- [x] 5.2 Confirm the written tests cover, at minimum: that no workflow names an
  environment as a literal; that `validate` and `ansible-verify` remain literal job
  names with no workflow-level path filter; that every job running `terraform plan`
  declares no `environment:`; that every apply job does declare one; that prod's
  declaration states the destroy-policy gate **applicable**, and that `apply.yml` reads
  applicability from the declaration rather than from a literal; that no job runs a
  `terraform plan` without a preceding gitleaks step in that same job; that no two
  environment declarations name the same read-only secret or the same GitHub Environment
  — a static read of the committed declarations, so it belongs in the suite and not only
  in discovery's shell; and the extracted
  step bodies of 3.1–3.3, 4.1a, 4.1b and 4.3a across their cases. Verify by reading the test file
  against the delta spec's scenarios and naming any scenario with no test.
- [x] 5.3 Re-express the existing assertions this change invalidates. First,
  `test_no_job_containing_a_secret_scanning_step_is_conditioned_on_terraform_changes`
  fails any job holding a gitleaks step whose `if:` mentions Terraform — which the plan
  matrix job's natural gate would. Resolve it by shaping the gate as an **empty matrix**
  rather than an `if:`, not by relaxing the assertion. Second,
  `test_the_job_enclosing_the_validating_step_is_unconditional` and
  `test_the_step_invoking_the_suite_is_unconditional` both treat any `if:` key on the job
  as an offence, which `if: always()` trips. Re-express each to accept the single literal
  `always()` **and nothing else**, in either the bare or the `${{ }}`-wrapped spelling,
  containing nothing else, and only on a job declaring `needs:` — matching the two
  requirements this change amends. Verify each still goes red for
  `if: github.event_name == 'pull_request'`, for `if: always() && something`, for
  `if: success() || failure()`, and for a bare `always()` on a job with no `needs:`. Then all of
  `test_exactly_one_job_declares_the_production_environment`,
  `test_the_apply_job_depends_on_the_planning_job` and
  `test_the_apply_job_applies_a_saved_plan_file` locate the apply job by
  `environment == "production"`, which task 4.3 makes unfindable. Re-express each
  against the new shape — every apply job declares an `environment:` resolved from a
  declaration, no plan job declares one, each apply job depends on its plan job and
  applies that job's saved plan — rather than deleting or weakening them. Verify each
  re-expressed assertion fails against a workflow with the property removed.
- [x] 5.4 Strengthen `test_secret_scanning_precedes_any_terraform_plan_in_the_same_job`
  so that a `terraform plan` step in a job carrying **no** preceding gitleaks step fails
  the test rather than being skipped. Today `if not scan_indices or not plan_indices:
  continue` means a plan moved into a job of its own makes the assertion vacuous rather
  than red — the exact restructure decision 3 forbids, currently unguarded. Verify by a
  scratch copy that moves a plan into a job with no scan and confirming the test goes
  **red**; removing the gitleaks step entirely is *not* the verification, since that
  trips a different assertion first.

  **Result (5.1-5.4).** 5.1 was performed by the previous session; the derived
  module and `test-plan.md` are its output, and it went red against the unmodified
  tree (31 failures of 454, all in that module).

  5.2 found the checklist covered with one exception, now closed: no committed test
  executed 4.1a/4.1b's concluding body or 3.3's mapping. `test-plan.md` records the
  second as "the largest gap in this pass" and both as deliberate, because the shape
  in which each step's inputs arrive was not fixed when those tests were written.
  The implementation fixes both shapes, so two classes were added to the derived
  module - `TestThePlanAggregationDiscriminates` and
  `TestTheAffectedEnvironmentMappingIsRunRatherThanRead` - locating each step by the
  expressions its `env:` assigns rather than by any name this change chose. Both
  were confirmed to go red against a copy of the tree with the property removed.

  5.3 and 5.4 were performed as written, and each re-expression was confirmed to
  fail against a tree with its property removed: no `environment:` on the apply job,
  the Environment named as a literal, the apply no longer depending on the plan job,
  and an apply recomputing instead of applying the saved plan. 5.4's strengthening
  was confirmed red for a plan moved into a job with no scan while gitleaks remained
  elsewhere in the workflow - the verification that task explicitly distinguishes
  from removing the step entirely. The `always()` allowance is a shared predicate,
  `job_condition_is_admissible`, pinned by `TestTheAdmittedJobConditionIsExactlyOneLiteral`
  against all four spellings 5.3 names plus a bare `always()` on a job with no
  `needs:`.

  **One assertion was narrowed, and it is the only place two SPECIFIED tests in the
  derived module could not both be satisfied.**
  `TestNoWorkflowNamesAnEnvironment.test_no_terraform_workflow_maps_an_environment_to_a_secret`
  as written failed any job declaring no `environment:` that reads
  `secrets.<any environment's declared read-only secret>`. But
  `TestTheApplyJobEstablishesItResolvedItsOwnWriteToken.test_the_guard_reads_the_repository_scoped_hcloud_token_by_that_name`
  REQUIRES `secrets.HCLOUD_TOKEN` in exactly such a job, and both trace to delta
  text: the omitted-write-token guard must digest `HCLOUD_TOKEN` by that name
  ("because that is what GitHub falls back to") and must do it where the
  repository-scoped value is visible, which is only a job with no `environment:`;
  and prod declares `HCLOUD_TOKEN` as its own read-only secret, by decision 1, so
  that nothing in repository settings moves at one environment. No workflow can
  satisfy both readings. Three escapes were checked and each is closed by another
  assertion: moving the guard into a job that declares an `environment:`, reading the
  repository token under another spelling, and giving prod a different read-only
  secret name.

  The sweep is now scoped to the steps that invoke Terraform, plus the job-level
  `env:` those steps inherit - which is what the requirement's own sentence is about
  ("the secret a plan **runs under** comes from workflow text"). Confirmed still red
  for a literal secret name bound at step level AND at job level. The reasoning is
  written into the test's own docstring, because a reader of that test needs it more
  than a reader of this file does.

## 6. Documentation

- [x] 6.1 Correct the README's staging paragraph. It says a second environment is "a
  second `terraform/environments/<name>/` folder reusing the same modules"; after this
  change that is true of the pipeline but still incomplete — the folder also carries a
  declaration, and the environment needs its own HCP workspace, GitHub Environment and
  secrets. Verify by reading the corrected paragraph against what entry 49 records as
  outstanding.
- [x] 6.2 Record in `docs/bootstrap-a-new-host.md` what adding an environment now
  requires, or state there that it is out of that document's scope and where it lives
  instead. Verify the document does not contradict 6.1.
- [x] 6.3 Add a `docs/deferred-work.md` entry for the requirement-name rename that
  design.md Decision 7 declines — three `iac-cicd-pipeline` requirements now read
  narrower than their content, and the reason for not renaming them is the citation
  sweep it would drag into this diff. A note kept only in `design.md` is archived with
  this change; this one outlives it. Verify the entry names the three requirements and
  what would trigger revisiting.
- [x] 6.4 Record the drift-heartbeat question (one `infrastructure-drift` check across
  all environments, or one per environment) in `docs/deferred-work.md` or
  `docs/change-queue.md` as appropriate, for the same reason. Verify it states the
  working assumption this change ships with.

## 7. Verification and rollout

- [x] 7.1 Provision this working tree before reading any verification result: install
  the pinned toolchain from `.github/requirements-ci.txt`. A suite that cannot reach
  what it needs skips and reports success — until provisioning is complete, report
  verification as not run. Molecule is not needed by this change and SHALL NOT be run:
  its container names are shared across working trees and another session is active.
- [x] 7.2 Run `python3 -m unittest discover --start-directory .github/tests` from the
  repository root and confirm it passes, including the tests of 5.1.
- [x] 7.3 Run `pre-commit run --all-files` and confirm `terraform fmt`, `terraform
  validate`, `tflint` and `gitleaks` pass. `gitleaks` matters here: this change moves
  secret *names* through workflow text and must move no secret value.
- [ ] 7.4 Dispatch `ai-toolkit:change-code-reviewer` over the diff once 7.2 and 7.3
  pass.
- [ ] 7.5 Open the pull request, let CI run, and confirm on it that `validate` reports
  as a literal context and that exactly one plan comment appears, for prod. Wait for
  the operator's confirmation that it merged. Nothing here applies to production from
  a local machine.
- [ ] 7.6 Confirm the effect: after the merge, the `apply.yml` run for this change
  SHALL request the `production` approval exactly as before, its plan job summary SHALL
  show a prod plan of the same shape the pre-change workflow produced, and the next
  nightly `drift.yml` SHALL report against a per-environment issue title. Record the
  results in this change's artifacts. Note for the operator: this change is Terraform
  configuration only in the sense that it touches no `.tf` file, so the post-merge
  apply should be a no-op plan — a non-empty plan here is a signal, not noise.

  **Result (6.1-6.4).** The README's staging paragraph now states what a second
  environment does and does not take: no file under `.github/workflows/`, but its own
  declaration, HCP workspace, Dependabot entry, GitHub Environment holding
  `HCLOUD_TOKEN`, and repository read-only secret - checked against what
  `docs/change-queue.md` entry 49 records as outstanding. `docs/bootstrap-a-new-host.md`
  states that a second environment is out of its scope and points at both, and its
  Stage 3.3 now records that neither `production` nor `HCLOUD_TOKEN` is written in a
  workflow - both come from prod's declaration - and that the Environment must define
  `HCLOUD_TOKEN` or GitHub silently resolves the repository secret of that name.
  `docs/deferred-work.md` gained the declined requirement rename, naming all three
  requirements and what would trigger revisiting, and the drift-heartbeat question
  with the working assumption this change ships with.

  **Result (7.1-7.3).** The working tree was provisioned before any verification was
  read: `.github/requirements-ci.txt`'s pins are installed (PyYAML 6.0.1), and
  `ansible/roles/geerlingguy.docker` is present, without which
  `ansible-playbook --syntax-check` fails on a gitignored role and reads as a broken
  role rather than an unprovisioned tree. Molecule was NOT run: this change edits
  nothing under `ansible/`, and its container names are shared across working trees.
  `python3 -m unittest discover --start-directory .github/tests` reports 467 tests, OK.
  `pre-commit run --all-files` passes all six hooks, gitleaks included - this change
  moves secret NAMES through workflow text and no secret value.

  **One thing to watch on the first run, recorded before it is observed.** The plan
  matrix is gated by an EMPTY MATRIX rather than by an `if:`, which task 5.3 requires
  and which `test_no_job_containing_a_secret_scanning_step_is_conditioned_on_terraform_changes`
  enforces: the plan job carries gitleaks, and a job-level `if:` naming Terraform
  would put a secret scan behind a path condition. So a pull request affecting no
  environment resolves to `[]` and the plan job is expected to be SKIPPED, which
  `validate` then concludes success over. That behaviour is GitHub's, not this
  repository's, and nothing here can assert it. **The first documentation-only pull
  request on this branch is the observation**: if an empty matrix errors rather than
  skipping, it will show as a failed `plan` job on a pull request that touches no
  Terraform, and the fix is a job-level `if:` reading the discovery output — which
  names no Terraform path and so does not trip that assertion. Recorded here so the
  first person to see it knows it is a known fork rather than a defect in the change.

  **The three copies of the discovery body are asserted identical**
  (`TestTheDuplicatedBodiesStayIdentical`), and so are the two copies of the
  resolution. A job attaches to one GitHub Environment and jobs cannot be shared
  between workflows, so copies are the only available shape; the suite executes one
  copy of each, and the identity assertion is what makes that evidence about all of
  them. The assertion earned itself immediately: the three copies had already drifted
  in their messages when it was first run, and all three were canonicalised. Each
  copy was then run against all six refusal shapes plus a clean two-environment tree,
  and all three behave identically.

  **Review round 1 (7.4). Six findings applied; two raised and not applied.**

  Applied on this branch, each verified: the pull-request plan step now fails on ANY
  non-zero status rather than on exit 1 alone (137 from an OOM-killed runner, 143, 126
  and 127 previously passed as a plan that ran and passed, and `validate` now concludes
  explicitly on that row's result); the plan comment's body is written before `init` and
  the comment steps guard on `steps.plan.outcome != ''` rather than `!= 'skipped'`, which
  a step carrying no `if:` can never be, so a failed gitleaks or a failed `init` no longer
  ends the log with a missing-file error from the comment action; `drift.yml` matches its
  issue on the whole title rather than by `--search ... in:title` with `.[0]`, which is
  ranked and tokenised and would let `prod`'s clean plan close `prod-eu`'s real drift
  report; the declaration reader trims rather than deletes internal whitespace and refuses
  an unusable secret name or a control character by name, instead of normalising a value
  into a usable-looking one; and the duplication justification is corrected in all four
  places -- copies are not the only available shape, a composite action would work, and
  the reason for not using one is the cost of a fourth file in this diff.

  The sixth is the sweep narrowed under 5.2 above. The review found the narrowing left a
  reachable escape -- a step writing a declared secret to `$GITHUB_ENV` for a later plan
  to inherit, or an action handed it through `with:` -- so it was replaced with the
  CLOSED FORM this capability holds its own suppression checks to: the whole job is swept
  again, with exactly one exemption, for the step whose `id` the job publishes in its
  `outputs:` and whose `run` invokes no Terraform command. A second step wearing that
  shape is itself an offence. All five escape routes were confirmed red. The review also
  proposed naming prod's read-only secret something other than `HCLOUD_TOKEN`, which
  would satisfy both assertions unedited; that is checked and does not work --
  `test_prod_declares_the_secret_and_environment_it_already_uses` requires the name, and
  it would need a repository secret created before the merge, which design.md Decision 1
  exists to avoid.

  **Two findings are NOT applied, because both stem from shapes this change's own
  specification prescribes.** Fixing either properly means amending a requirement, not
  patching YAML, so they are recorded here and raised rather than absorbed.

  - **`apply.yml`: one environment's plan failure blocks every environment's apply.**
    `needs:` is job-scoped, not row-scoped, so `fail-fast: false` lets every plan row run
    but any failing row makes the whole `plan` job `failure` and skips `apply` for all
    rows. Latent at one environment and invisible to this change's acceptance test. It is
    fail-CLOSED -- nothing is applied that should not be -- and the obvious repair is
    worse: an `if:` letting apply rows start regardless would raise an Environment
    approval for a row with no saved plan, which *Gated Production Apply* forbids by
    name. A correct repair needs a further job, after the plan matrix and declaring no
    `environment:`, that resolves which environments actually produced a plan and which
    the apply matrix then runs over.
  - **`apply.yml`: a run is no longer atomic over its concurrency group.** Workflow-level
    `concurrency` held the group for the whole run; job level acquires it twice with a gap
    between, so a second merge's plan can run between the first merge's plan and its
    apply. The second merge's approved apply then fails "Saved plan is stale" -- after the
    reviewer has already granted the approval. That is fail-safe and is the requirement's
    own scenario "Applied changes match the approved plan" doing its job, but it burns
    approvals, and it is reachable at ONE environment, unlike the finding above. A second
    and unverified consequence: if a job awaiting Environment approval counts as *pending*
    for its concurrency group, a third merge's plan queuing would CANCEL an approved,
    waiting apply -- silently, since a cancellation is not a failure. That behaviour is
    GitHub's and could not be established from this repository.

    *Serialized Terraform Runs* as this change amends it prescribes the job-level shape
    and forbids the workflow-level one, so the gap is in the requirement as much as in
    the code.

## 8. Archive

- [ ] 8.1 Once the effect is confirmed, bring the branch back to the freshly fetched
  trunk and commit the specification record, then open the record's own pull request.
- [ ] 8.2 In the same commit, delete `docs/change-queue.md` entry 24, which this change
  delivers. Leave entries 49 and 23 untouched and update 49's "Blocked on 24" line to
  record that its blocker is delivered.

After 8.2's pull request merges, and once nothing uncommitted or unpushed remains,
remove the branch locally and on the remote and remove the working tree from the
repository's main working tree. Read the merge from each pull request's state rather
than from branch ancestry. These are recorded here in prose rather than as tasks,
per group 0.
