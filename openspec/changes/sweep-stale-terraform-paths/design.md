## Context

See `proposal.md` - Why. This is a mechanical text sweep, not an
architectural change — none of the "when to include design.md" triggers
(cross-cutting change, new dependency, security/performance/migration
complexity, ambiguity needing resolution) apply. Recorded briefly so the
change has a design artifact per this workflow's dependency chain, not
because there's a technical decision to make here.

## Goals / Non-Goals

**Goals:**
- Every literal `environments/`/`modules/` path reference left stale by
  `integrate-ansible-host-config`'s move to `terraform/environments/`/
  `terraform/modules/` is corrected to the new path.

**Non-Goals:**
- Changing any requirement's SHALL/SHALL NOT behavior — see proposal.md's
  Capabilities section (none).
- Sweeping path references outside `openspec/specs/` (already handled by
  `integrate-ansible-host-config` itself for code, CI, and README).

## Decisions

Find-and-replace each literal `environments/` → `terraform/environments/`
and `modules/` → `terraform/modules/` occurrence in the four affected spec
files, verifying each one is genuinely a path reference (not, for example, a
plain-English use of the word "modules") before changing it.

## Risks / Trade-offs

- [Risk] A search-and-replace could catch a false positive (e.g. "modules"
  used generically, not as the directory). → Mitigation: review each match
  individually rather than a blind global substitution.
