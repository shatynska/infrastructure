## Context

See proposal.md - Why. The `hardening` role already has a working pattern
for this exact problem: `ansible/roles/hardening/tasks/main.yml`'s "Allow
SSH (22) from the tailnet CGNAT range" task, added for the same
default-deny-applies-to-tailscale0 reason. This change reuses that pattern
for Grafana's port 3000 rather than introducing a new one.

## Goals / Non-Goals

**Goals:**
- Close the gap so a fresh environment or host rebuild doesn't repeat
  incident 2 from the `add-platform-monitoring` rollout.
- Keep the diff minimal and structurally identical to the existing
  SSH-tailnet task.

**Non-Goals:**
- Generalizing to a list/loop of tailnet-allowed ports. Only one such port
  exists today (3000); introducing a variable-driven abstraction for a
  single value would be speculative. If a second tailnet-only service shows
  up later, that's the point to generalize, not now.
- Anything about the cloud firewall (Terraform) — port 3000 is correctly
  absent there today (Grafana was never meant to be publicly reachable) and
  stays that way.

## Decisions

**Hardcode port 3000, matching the SSH task's own hardcoded port 22,
rather than adding a new `hardening_tailnet_allowed_ports` variable.**
Alternatives considered: a looped variable list (rejected — no second
caller/value exists yet; matches this project's stated preference to avoid
designing for hypothetical future requirements over three similar lines).

**Place the new task immediately after the existing SSH-tailnet task**,
reusing the same comment block's rationale by cross-referencing it rather
than duplicating the full explanation, so the two tailnet-carve-out rules
read as one coherent group in the file.

## Risks / Trade-offs

- [Risk] A future port added to Grafana's tailnet exposure (unlikely) would
  need its own task, same as this one. → Mitigation: none needed; this is
  the accepted cost of not over-generalizing for a single case (see
  Non-Goals).
- [Risk] None to production availability — this only adds an allow rule; it
  cannot make anything less reachable than it already is.

## Migration Plan

Standard Ansible re-converge against `main-server` (`ansible-playbook
playbooks/host-baseline.yml` or equivalent), same mechanism already used to
apply the `hardening` role. No data migration, no downtime — UFW rule
additions apply without disrupting existing connections. No rollback
concern beyond re-running the role with the task reverted, if ever needed.
