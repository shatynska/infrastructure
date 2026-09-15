Verification commands referenced below, from this project's conventions:

- `openspec validate correct-the-tfvars-parenthetical-that-names-labels --strict`, from the repository root
- `openspec validate --all`, from the repository root
- `python3 -m unittest discover --start-directory .github/tests`, from the repository root

**This change has no `build:apply` step in the ordinary sense.** The correction lives entirely in `specs/iac-repo-foundations/spec.md`'s delta and lands in `openspec/specs/iac-repo-foundations/spec.md` only when this change is archived — the tree shows every prior change's spec merge happening in its own archive commit, never during `build`. Nothing outside `openspec/changes/correct-the-tfvars-parenthetical-that-names-labels/` is touched before then, so section 1 is verification of the plan and the fact it corrects, not implementation.

## 1. Verify the plan resolves and the fact still holds

- [x] 1.1 Run `openspec validate correct-the-tfvars-parenthetical-that-names-labels --strict` and confirm the delta resolves against the current main spec with no error.
      **Performed 2026-09-15.** Reports "Change 'correct-the-tfvars-parenthetical-that-names-labels' is valid". Independently re-confirmed by `ai-toolkit:change-plan-reviewer`, which resolved the delta itself and returned APPROVED.
- [x] 1.2 Re-confirm the fact this change corrects, against the tree at implementation time rather than trusting `proposal.md`'s earlier measurement: neither `terraform/stacks/main-production/terraform.tfvars` nor `terraform/stacks/main-staging/terraform.tfvars` assigns `labels`, and neither stack's `main.tf` passes `labels` to a module. Record the command used and its result in this task's completion note.
      **Performed 2026-09-15.** `grep -rn "labels" terraform/stacks/main-production/ terraform/stacks/main-staging/` finds `labels` only inside each stack's own `ssh_key.tf` (a literal resource block, not a `terraform.tfvars`-sourced value); neither `terraform.tfvars` file and neither `main.tf`'s module blocks assign it. Independently re-verified by both `ai-toolkit:change-plan-reviewer` and `ai-toolkit:change-test-writer`, each reading the files directly rather than trusting this note.

## 2. Verify the suite stays green

- [x] 2.1 Run `python3 -m unittest discover --start-directory .github/tests` and confirm it passes; no assertion in that suite reads this table cell today, so no output is expected to change.
      **Performed 2026-09-15** by `ai-toolkit:change-test-writer`, as this change's derived-test dispatch: 1276 tests, OK, unscoped. It also confirmed independently that all three of the requirement's scenarios are byte-identical to the currently recorded spec, so this `MODIFIED` delta owes no new test — see `test-plan.md`.
- [x] 2.2 Run `openspec validate --all` and confirm no other change in flight is broken by this one.
      **Performed 2026-09-15.** Totals: 10 passed, 0 failed (10 items); only pre-existing `[INFO]`-level length notices, no `[ERROR]`.

## 3. Archive

- [ ] 3.1 Merge this change's delta into `openspec/specs/iac-repo-foundations/spec.md` via `openspec archive`, and confirm the merged requirement's table row reads "server type, region, image, allowed CIDRs".
- [ ] 3.2 Delete `docs/backlog.md` entry 47 (`correct-the-tfvars-parenthetical-that-names-labels`) in the archive commit.

Removing the branch and the working tree happens after this change's record pull request merges, which is after the commit that writes this file, so those steps are not tasks here — see `AGENTS.md`, "ship" and "Throughout".
