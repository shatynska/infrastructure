## Why

This repository has been building toward a specific technical shape —
Terraform IaC on Hetzner Cloud, per `bootstrap-hetzner-iac` — without ever
recording *why* it exists, who it's for, or what's deliberately out of
scope. Those decisions have lived only in conversation and in inference
from the README. This change records them explicitly, once, so they're
available to whoever — human or agent — picks up work here next, instead
of needing to be re-derived or re-asked each time.

## What Changes

- Record identity (what this is, the problem it solves, its intended
  audience), scope, and non-goals — none of which were previously written
  down anywhere in the repository.
- Confirm the technology and architecture already established by
  `bootstrap-hetzner-iac`, recording them in `design.md` so they're visible
  without reading that change's specs.
- Add a testing-strategy decision that was not previously explicit:
  static analysis plus human-reviewed plan output today, with Terraform's
  native `terraform test` framework adopted for module-level tests as
  `modules/` grows.
- Confirm development tooling already in place (`pre-commit`, `commitlint`,
  `tflint`, a Terraform-aware `.gitignore`) satisfies this decision's
  concrete deliverable with no further changes needed.
- Reflect the identity/scope/non-goals/technology/architecture decisions
  into `README.md`, and the testing-strategy/development-tooling decisions
  into a new project-specific section of `AGENTS.md`, below the managed
  workflow block.
- Mark `skip_specs: true` — this change is a decisions record, not a
  capability change, and produces no spec deltas.

## Impact

- `README.md`, `AGENTS.md` — documentation only, no code or infrastructure
  changes.
- No effect on the in-progress `bootstrap-hetzner-iac` change, which this
  change does not modify.
