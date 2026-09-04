## Why

`add-platform-monitoring` (merged, PR #45) requires Grafana's dashboard
interface to be reachable only over the host's private tailnet
(`openspec/changes/add-platform-monitoring/specs/iac-platform-services/spec.md`'s
"Dashboards Are Reachable Only Over the Tailnet" requirement) and binds
Grafana to the host's tailnet-literal IP, not `0.0.0.0`, to enforce it.
During rollout, Grafana was found unreachable even from the tailnet: UFW's
default-deny-incoming policy applies to the `tailscale0` interface the same
way it applies to the public interface — the same reason the `hardening`
role already carries an explicit allow rule for SSH (22) over the tailnet
CGNAT range — but no equivalent rule exists for Grafana's port 3000. The gap
was patched by hand directly on the running host
(`ufw allow from 100.64.0.0/10 to any port 3000 proto tcp`) to unblock the
rollout, but that manual fix isn't codified anywhere in this repository, so
a fresh environment or a host rebuild hits the identical gap again.

This is an implementation fix for an already-specified behavior (Grafana's
tailnet-only reachability), not a change to what the system is supposed to
do — no spec requirement's text changes as a result.

## What Changes

- Add a UFW allow rule to the `hardening` Ansible role for port 3000 from
  the tailnet CGNAT range (`100.64.0.0/10`), mirroring the role's existing
  SSH-over-tailnet task in placement, structure, and rationale.
- Update the `hardening` role's README to document both tailnet-scoped UFW
  rules — the pre-existing SSH one and this new Grafana one. Neither is
  documented there today (only the CIDR-variable table is); documenting
  only the new rule would leave the README inconsistent.
- Extend the role's Molecule `verify.yml` to assert both tailnet-scoped
  rules, for the same reason.

No other task, variable, or rule in the `hardening` role changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — `skip_specs: true` is set in this change's `.openspec.yaml`. The
tailnet-only reachability requirement already exists (see Why); this change
only closes a gap between that requirement and the `hardening` role's
implementation of it.

## Impact

- `ansible/roles/hardening/tasks/main.yml`: one new UFW task.
- `ansible/roles/hardening/README.md`: a new note documenting both
  tailnet-scoped UFW rules (SSH and Grafana).
- `ansible/roles/hardening/molecule/default/verify.yml`: extend to assert
  both tailnet-scoped rules (SSH and Grafana).
- No Terraform, cloud-firewall, or application-level changes — this is
  host-level defense-in-depth only, on top of a port that is not opened at
  the cloud firewall layer at all.
