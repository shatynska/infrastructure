## Why

`docs/backlog.md` entry 49. *Version Control Excludes State and Secrets* (`openspec/specs/iac-repo-foundations/spec.md`) describes `terraform/stacks/<name>/terraform.tfvars` as holding "server type, region, image, labels, allowed CIDRs". Neither stack's `terraform.tfvars` assigns a `labels` value — no stack passes `labels` to the `server` or `volume` module at all, so each module's own default applies. The only `labels` block under `terraform/stacks/main-production/` is a literal one inside `ssh_key.tf`, unrelated to the variable-file mechanism the requirement is describing. The row has been factually wrong since before `refresh-readme-accuracy` (archived 2026-09-08) first found it, and two changes have since touched this exact row without correcting it: that change deliberately left it disagreeing with the tree, and `rename-terraform-environments-to-stacks` (2026-09-11) rewrote the row's path without correcting its contents. It is small enough to be its own change now that no larger one has picked it up.

## What Changes

- Correct the parenthetical in *Version Control Excludes State and Secrets*'s table to name what `terraform.tfvars` actually carries, dropping `labels`.
- No behavioral scenario changes: the requirement's normative content (the file is committed, split from secrets by naming convention, and CI needs it present in a clean checkout) is untouched. Only the illustrative list of examples is corrected.
- Argue explicitly, in `design.md`, why this `MODIFIED` delta owes no new derived test — specifically not the cross-file assertion "the requirement's parenthetical agrees with `terraform.tfvars`", which this repository has already declined twice, both inside `refresh-readme-accuracy`'s own design: once by choosing not to touch this requirement at all rather than take on that derived test, and once by deferring the assertion itself as needing a requirement of its own and a scope decision nobody has made.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-repo-foundations`: *Version Control Excludes State and Secrets* — the table row describing `terraform/stacks/<name>/terraform.tfvars`'s contents is corrected to match the tree; no normative clause changes.

## Impact

**Specification corrected**: `openspec/specs/iac-repo-foundations/spec.md`, one table cell.

**No code changes.** No `.tf`, `.tfvars`, `.yml` or `.github/tests` file changes.

**Tests**: none owed beyond confirming the existing suite stays green — see `design.md` for why the obvious cross-file assertion is not this change's to add.

**Backlog**: entry 49 is deleted from `docs/backlog.md` at archive.
