## Why

`integrate-ansible-host-config` moved `environments/` and `modules/` to
`terraform/environments/` and `terraform/modules/`, and updated the one spec
requirement whose *behavior* that move actually changed
(`iac-repo-foundations`'s "Environment and Module Folder Structure"). Several
other specs mention the old paths only incidentally — in requirement
descriptions or scenario text, not as the thing the requirement governs — and
those were deliberately left out of that change to keep it scoped to the one
requirement that changed. They are now stale.

## What Changes

- Update literal `environments/`/`modules/` path references to
  `terraform/environments/`/`terraform/modules/` in:
  - `openspec/specs/iac-cicd-pipeline/spec.md`
  - `openspec/specs/iac-safety-hardening/spec.md`
  - `openspec/specs/iac-state-management/spec.md`
  - `openspec/specs/iac-repo-foundations/spec.md`'s other requirements (e.g.
    "Version Control Excludes State and Secrets") — everything other than
    "Environment and Module Folder Structure", which
    `integrate-ansible-host-config` already updated.
- No requirement's SHALL/SHALL NOT behavior changes as a result — this is a
  text-only correction to keep path references accurate after the move, not
  a behavior change. `.openspec.yaml` sets `skip_specs: true` accordingly.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — see "What Changes": every edit is incidental path text inside
existing requirements, not a change to what those requirements require.

## Impact

- Affected: the four spec files listed above (docs-only; no code, workflow,
  or Terraform changes).
- Depends on `integrate-ansible-host-config` having landed first (that
  change is what makes these references stale).
