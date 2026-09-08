## Why

The Molecule suite is this repository's largest test asset and the only thing
that observes what an Ansible role actually does to a host. It runs on every
pull request touching `ansible/` and cannot block a merge. A red run is
information nobody is obliged to read.

It was made advisory for one stated reason: whether its privileged-systemd, UFW
and `fail2ban` scenarios are reproducible on a hosted runner had never been
observed. They are. Five consecutive workflow runs are green, three of them on
independent subjects — pull requests #66, #68 and #70, each a change about
something other than the suite itself. The condition the advisory tier was
waiting on is met.

Two things stand in the way of the promotion, and neither is a
branch-protection toggle:

**`ansible-verify.yml` is filtered at the workflow level.** A `paths:`-filtered
required check never reports on a non-matching pull request, leaving it
permanently pending and unmergeable — exactly what the *Required Status Checks
Report on Every Pull Request* requirement forbids, and what the workflow's own
top comment says must be fixed first.

**A required context must have a fixed name.** The work is done by a matrix job
whose context names are generated from the matrix. Registering those is
impossible; registering the matrix job under an empty matrix is worse, because
a skipped job is not a failed one and GitHub reports no context at all.

Branch protection did not exist at all until 2026-09-07 — the *Branch
Protection on the Default Branch* requirement was unsatisfied. It now requires
`validate`, with `strict: true` and `enforce_admins: true`. So there is a real
contexts list to add to, and the requirement recording it is out of date.

## What Changes

**`ansible-verify.yml` becomes an always-running workflow with the gating
inside it**, the shape `pr-validation.yml` already uses. The workflow-level
`paths:` filter is removed and replaced by a `dorny/paths-filter` step in the
discovery job; the Molecule matrix is conditioned on its output. A pull request
touching nothing under `ansible/` runs discovery (four seconds) and the
aggregating job, and reports success — it does not start a single container.

**A new fixed-name `ansible-verify` job aggregates the matrix**, and is what
gets registered as a required check. It runs with `if: always()`, reads the
discovery job's result, the matrix job's result and the change-detection
output, and decides. It exists because the matrix jobs cannot be required and
because `success()` over a skipped job is true — the empty-matrix vacuous green
the discovery step's own comment already refuses.

**A skipped Molecule matrix is a failure when `ansible/` changed.** `skipped`
and `success` are not the same conclusion. Read as one, the promotion would
re-create the "green having verified nothing" defect at the aggregation layer
rather than at the discovery layer.

**The suite gains executable coverage of the gate.** The aggregating job's
script is kept free of `${{ }}` — its inputs arrive through `env:` — so
`.github/tests` can extract it from the workflow and run it under `bash`
against a truth table of *(discovery result, matrix result, Ansible changed)*,
the way that suite already exercises the role-discovery snippet. Structural
assertions cover the rest: no workflow-level path filter on either required
workflow, a literal aggregating-job name, and the matrix gated on change
detection rather than on nothing.

**The specification catches up in four places** — the advisory tier becomes a
blocking one, the required-check requirement generalises from "the pull request
check" to every workflow registered as one, branch protection records the
contexts it actually requires, and the apply requirement's cross-reference to
"the workflow that is registered as a required check" stops being singular.

**The operator applies the branch-protection edit.** Adding `ansible-verify` to
`required_status_checks.contexts` is repository settings, not code; this change
cannot deliver it, and `.github/tests` cannot verify it — the suite may make no
network call. The tests assert what the workflow file says, and say so.

## Non-goals

**A matrix over scenarios rather than roles.** `molecule test --all` stops at
the first failing scenario, so a red run under-reports; a per-scenario matrix
would fix that and parallelise the longest role. It is a rewrite of discovery,
of every scenario-coverage test, and of the matrix job's identity, and the
promotion is correct without it: a red check blocks a merge whether or not it
enumerated every failure. Recorded in `docs/change-queue.md` rather than folded
in — entry 4's own note about it is deleted when this change is archived.

**Namespacing the Molecule suite per working tree.** `docs/change-queue.md`
entry 8. Concurrent local runs collide; continuous integration checks out one
tree and does not.

**Moving the destroy gate's inline shell into a script.** `docs/change-queue.md`
entry 6 defers it on merit-vs-scope grounds. The gate this change adds is
exercised in place, by the extract-and-run pattern already in the suite, so it
neither needs nor pre-empts that decision.

## Impact

- `.github/workflows/ansible-verify.yml` — trigger, change detection, matrix
  condition, the new aggregating job, and the top comment that documents all of
  it
- `.github/tests/test_ci_configuration.py` — the gate's truth table, the
  structural assertions, and the two existing classes whose subject moves
- `README.md` — the local-setup paragraph describing the suite as advisory
- `docs/change-queue.md` — entry 4 is this change; the per-scenario matrix it
  names becomes an entry of its own
- `openspec/specs/iac-cicd-pipeline/spec.md`, at archive — four requirements:
  three modified, one replaced. The replacement is a removal plus an addition
  under a new name rather than a modification, because a modified requirement
  may not drop a scenario the specification still has, and one scenario here
  asserts the opposite of what this change delivers. `design.md` Decision 7
  records why that is the only supported shape.
- **Repository settings, applied by the operator**: `ansible-verify` added to
  `main`'s required status check contexts

Cost: a doc-only pull request gains two short jobs. A pull request touching
`ansible/` gains nothing it was not already paying — those six minutes are
spent today; what changes is whether a red run blocks the merge. With
`strict: true`, an Ansible pull request re-runs the suite after each trunk
update, which is the existing cost of `validate` applied to a longer check.
