## 1. Implement

- [x] 1.1 Add a "Allow Grafana (3000) from the tailnet CGNAT range" UFW task to `ansible/roles/hardening/tasks/main.yml`, placed immediately after the existing SSH-tailnet task, allowing `100.64.0.0/10` on TCP port 3000
- [x] 1.2 Document the new rule in `ansible/roles/hardening/README.md`. Neither tailnet rule is documented there today (only the CIDR-variable table exists) — add a short note covering both the pre-existing SSH-tailnet rule and this new Grafana-tailnet rule together, so the README doesn't end up documenting one tailnet rule while silently omitting the other
- [x] 1.3 Extend `ansible/roles/hardening/molecule/default/verify.yml` to assert the new rule is present. No tailnet-scoped rule is verified there today (only the public SSH CIDR, HTTP/HTTPS, and fail2ban are) — add an assertion for the pre-existing SSH-tailnet rule alongside the new Grafana one, following the file's existing assertion style for the public-CIDR rules

## 2. Verify

- [x] 2.1 Run `ansible-lint` and `ansible-playbook --syntax-check` against the changed role — both pass
- [x] 2.2 Run the role's Molecule scenario (`molecule test` in `ansible/roles/hardening/`) if runnable in this environment — not runnable here: `molecule`'s `create` step fails building the `geerlingguy/docker-ubuntu2204-ansible` test container ("Exec format error"), an environment/architecture limitation, not a defect in this change. The `syntax` step (which does run) passes.
- [x] 2.3 Confirm `openspec validate --strict` passes for this change — passes

## 3. Deploy and confirm

- [x] 3.1 Re-converge `main-server` with the updated `hardening` role — ran clean, `changed=0`
- [x] 3.2 Confirm the manually-added rule (`ufw allow from 100.64.0.0/10 to any port 3000 proto tcp`, added by hand during the `add-platform-monitoring` rollout) is now also produced by Ansible — i.e. re-running the role is idempotent and doesn't attempt to add a duplicate or conflicting rule — confirmed by the `changed=0` result itself: the UFW module recognized the manually-added rule as already matching Ansible's managed state, no duplicate/conflicting rule was added
- [x] 3.3 Confirm Grafana is still reachable over the tailnet after the converge — confirmed, `GET /api/health` returns `200` over the tailnet; all platform/commerce-ops containers remained up and unaffected throughout
