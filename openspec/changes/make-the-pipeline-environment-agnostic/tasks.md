## 0. A note on what this task list may contain

Branch and working-tree removal happen after this change's record has merged, which is
after the commit that writes this file — a task for them would be unticked by
construction forever. They are recorded in prose in the archive group instead. This is
the repository's own convention (`AGENTS.md`, "Task lists, archived records, and
disclosing what was not done"); the archive step itself is a task and is unaffected.

## 1. Establish the mechanism before building on it

- [ ] 1.1 Confirm that indexing the `secrets` context by a matrix-supplied name
  (`${{ secrets[matrix.<field>] }}`) resolves a repository secret, by running a
  scratch workflow on a branch that echoes only whether the value is non-empty —
  never the value. Decision 4 rests on this; if it does not hold, the read-only
  credential scheme needs rework before any workflow is edited.
- [ ] 1.2 Create a scratch GitHub Environment with no protection rules and no secrets,
  and confirm that a `matrix` value can supply a job's `environment:` name against it.
  Decision 5 rests on this. The scratch workflow SHALL be `push:`-triggered, not
  `workflow_dispatch:` — dispatch resolves the workflow through the default branch's
  listing, so a branch-only workflow cannot be dispatched.
- [ ] 1.3 Delete the scratch workflow **and the scratch GitHub Environment**, and
  confirm both are absent — the workflow from the branch, the Environment from
  repository settings — before any other task's work is committed. The Environment is a
  repository-settings change existing only for tasks 1.1–1.2; leaving it behind would
  falsify design.md's Migration Plan.

## 2. The per-environment declaration

- [ ] 2.1 Decide and document the declaration file's name, format and fields, and
  record the choice in `design.md` Decision 1 if it differs from what is written
  there. Verify by writing the file for prod in 2.2 against it.
- [ ] 2.2 Add prod's declaration under `terraform/environments/prod/`, naming
  `HCLOUD_TOKEN` as its read-only secret, `production` as its GitHub Environment, and
  the destroy-policy gate as applicable. Verify that `terraform validate` and
  `terraform fmt -check` still pass for that directory — the file must not be picked
  up as Terraform configuration.

## 3. Discovery and change detection

- [ ] 3.1 Write the discovery step that enumerates `terraform/environments/*/`, reads
  each declaration, and emits a matrix. Verify by running its body standalone against
  the working tree and confirming it emits exactly one entry, for prod.
- [ ] 3.2 Make discovery fail closed on an absent, unparseable or incomplete
  declaration, on an empty result, and on **two environments declaring the same
  read-only secret name or the same GitHub Environment name**. Verify by running its
  body against a scratch tree carrying each of those five shapes and confirming each
  exits non-zero — the first three naming the directory and the missing field, the last
  two naming both colliding environments.
- [ ] 3.3 Write the change-detection step mapping changed paths to affected
  environments (`terraform/modules/**` → all; `terraform/environments/<name>/**` →
  that one), refusing an unresolvable filter result rather than reading it as "nothing
  changed". Verify by running its body standalone across each case.
- [ ] 3.4 Keep both step bodies free of `${{ }}`, taking every input through `env:`, so
  `.github/tests` can extract and execute them — the constraint `ansible-verify.yml`'s
  gate and discovery bodies already observe, and the reason its tests can exist.

## 4. The three workflows

- [ ] 4.1 `pr-validation.yml`: move `terraform plan` into a matrix job over the affected
  environments, reading its Hetzner token as `secrets[<the matrix's declared read-only
  secret name>]` and declaring no `environment:`. **That job SHALL run gitleaks as a
  step before its plan step**, so the scan-before-plan ordering holds within the job
  where a plan actually runs. Verify that every job in the workflow running a
  `terraform plan` also runs gitleaks earlier in that same job.
- [ ] 4.1a Keep `validate` as the registered context: leave its other steps and its
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
- [ ] 4.1b Set `fail-fast: false` on the plan matrix so one environment's failure does
  not abandon the others, and confirm `validate` still concludes failure when any row
  failed. Verify by running the concluding step's body with a failed row among passing
  ones.
- [ ] 4.2 `pr-validation.yml`: give each environment its own PR comment, keyed by a
  marker carrying the environment name, and move `pull-requests: write` to the job that
  posts it if the posting step moves with the plan. **The current `find-comment` uses
  `body-includes: "### Terraform Plan"` with `edit-mode: replace`, so N environments
  would each match and overwrite the same comment, leaving one plan standing.** Verify
  statically — an assertion that the find-comment marker is derived from the
  environment rather than constant — not by observing one comment at N=1, which the
  defect also produces.
- [ ] 4.3 `apply.yml`: matrix the plan and apply jobs over the environments the merge
  affects, take each apply job's `environment:` from the matrix, and name the `tfplan`
  artifact per environment so one environment's plan cannot be applied to another.
  Move the `concurrency` group from workflow level to **job level** on the plan and
  apply jobs, derived from the environment — a workflow-level declaration cannot read a
  matrix value. Verify the workflow parses, that no environment name appears as a
  literal anywhere in it, and that the artifact name is derived rather than constant.
- [ ] 4.3a `apply.yml`: detect an Environment that omits `HCLOUD_TOKEN`, per design.md
  decision 4a. The **plan** job — which declares no `environment:` and therefore sees
  the repository-scoped read-only token — emits `sha256(token + github.run_id)` as a job
  output; the apply job computes the same digest over its own resolved `HCLOUD_TOKEN`
  and fails before applying if they match. A job declaring `environment:` cannot read
  past its Environment's value, so the comparison **cannot** be done inside the apply
  job alone; and for prod, whose declared read-only name is `HCLOUD_TOKEN`, a naive
  same-job comparison would compare a value with itself. Verify by running both step
  bodies standalone over known inputs, confirming equal inputs fail and unequal inputs
  pass, and that neither body prints either token.
- [ ] 4.4 `apply.yml`: read the destroy-policy gate's applicability from the
  environment's declaration, treating an absent statement as applicable. Verify by
  running the gate's body standalone with the flag set both ways against a saved plan
  containing a delete.
- [ ] 4.5 `drift.yml`: matrix the plan over every environment regardless of changed
  paths, title each drift issue per environment, and ensure one environment's failure
  does not prevent the others being planned and reported. Verify the workflow parses,
  that the issue title is derived rather than literal, and that `report`'s `needs:`
  names every other job in the workflow — including any new discovery job — since a
  skipped dependency reads as non-failure to its heartbeat.
- [ ] 4.6 Update every workflow comment that cites a requirement by name where this
  change altered what that requirement says. Verify by grepping the three workflows for
  requirement names and reading each against the delta spec.

## 5. Tests

- [ ] 5.1 Dispatch `ai-toolkit:change-test-writer` with this change's name, its
  absolute `changeRoot` and artifact paths, this repository's convention files, the
  test command `python3 -m unittest discover --start-directory .github/tests` run from
  the repository root, and the test-path glob `.github/tests/*.py`. That is the only
  row of this project's three that applies: every property this change adds is a
  static read of a committed file. Verify that the tests it writes fail against the
  unmodified tree.
- [ ] 5.2 Confirm the written tests cover, at minimum: that no workflow names an
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
- [ ] 5.3 Re-express the existing assertions this change invalidates. First,
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
- [ ] 5.4 Strengthen `test_secret_scanning_precedes_any_terraform_plan_in_the_same_job`
  so that a `terraform plan` step in a job carrying **no** preceding gitleaks step fails
  the test rather than being skipped. Today `if not scan_indices or not plan_indices:
  continue` means a plan moved into a job of its own makes the assertion vacuous rather
  than red — the exact restructure decision 3 forbids, currently unguarded. Verify by a
  scratch copy that moves a plan into a job with no scan and confirming the test goes
  **red**; removing the gitleaks step entirely is *not* the verification, since that
  trips a different assertion first.

## 6. Documentation

- [ ] 6.1 Correct the README's staging paragraph. It says a second environment is "a
  second `terraform/environments/<name>/` folder reusing the same modules"; after this
  change that is true of the pipeline but still incomplete — the folder also carries a
  declaration, and the environment needs its own HCP workspace, GitHub Environment and
  secrets. Verify by reading the corrected paragraph against what entry 49 records as
  outstanding.
- [ ] 6.2 Record in `docs/bootstrap-a-new-host.md` what adding an environment now
  requires, or state there that it is out of that document's scope and where it lives
  instead. Verify the document does not contradict 6.1.
- [ ] 6.3 Add a `docs/deferred-work.md` entry for the requirement-name rename that
  design.md Decision 7 declines — three `iac-cicd-pipeline` requirements now read
  narrower than their content, and the reason for not renaming them is the citation
  sweep it would drag into this diff. A note kept only in `design.md` is archived with
  this change; this one outlives it. Verify the entry names the three requirements and
  what would trigger revisiting.
- [ ] 6.4 Record the drift-heartbeat question (one `infrastructure-drift` check across
  all environments, or one per environment) in `docs/deferred-work.md` or
  `docs/change-queue.md` as appropriate, for the same reason. Verify it states the
  working assumption this change ships with.

## 7. Verification and rollout

- [ ] 7.1 Provision this working tree before reading any verification result: install
  the pinned toolchain from `.github/requirements-ci.txt`. A suite that cannot reach
  what it needs skips and reports success — until provisioning is complete, report
  verification as not run. Molecule is not needed by this change and SHALL NOT be run:
  its container names are shared across working trees and another session is active.
- [ ] 7.2 Run `python3 -m unittest discover --start-directory .github/tests` from the
  repository root and confirm it passes, including the tests of 5.1.
- [ ] 7.3 Run `pre-commit run --all-files` and confirm `terraform fmt`, `terraform
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
